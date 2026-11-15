"""One row per label, from one record of the label data.

The parser reads only the fields it names (see :mod:`plainpairs.schema`), cleans each one with
:func:`plainpairs.text.join` and keeps its headings. It never fails on a missing section: a
label without a boxed warning, or without any patient text, simply has ``None`` there. It does
fail, in plain words, on a record without an ``id`` or a ``set_id``.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from plainpairs import bulk
from plainpairs.schema import (
    OLDER_WARNINGS,
    PATIENT_SOURCES,
    PRESCRIBER_SOURCES,
    Identity,
    LabelFormat,
    LabelRow,
    PatientTexts,
    PrescriberSections,
    Table,
)
from plainpairs.text import clean, join, table_to_text

#: Sections found only in the newer prescription format (21 CFR 201.57(a) to (c)).
PLR_FIELDS = ("warnings_and_cautions", "use_in_specific_populations", "dosage_forms_and_strengths")
#: Sections found only in "Drug Facts", the format of over-the-counter labels (21 CFR 201.66).
DRUG_FACTS_FIELDS = (
    "purpose",
    "when_using",
    "stop_use",
    "do_not_use",
    "ask_doctor",
    "ask_doctor_or_pharmacist",
)
#: Sections of a prescription label in either format.
PRESCRIPTION_FIELDS = (
    "indications_and_usage",
    "contraindications",
    "warnings",
    "precautions",
    "adverse_reactions",
    "clinical_pharmacology",
)
#: A copyright mark: the sign, the word, or "all rights reserved".
COPYRIGHT = re.compile(r"\u00a9|\bcopyright\b|all rights reserved", re.I)


class LabelError(ValueError):
    """A record cannot be read as a label."""


def _strings(record: dict[str, Any], field: str) -> list[str]:
    value = record.get(field)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return value
    raise LabelError(f"Field {field!r} of label {record.get('id')!r} is not text.")


def _date(raw: str | None) -> dt.date | None:
    if not raw or len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return dt.date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))
    except ValueError:
        return None


def _version(raw: Any) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _has(record: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return any(record.get(f) for f in fields)


def label_format(record: dict[str, Any], product_type: str | None) -> LabelFormat:
    """Which kind of label this is, from the sections it has (in this order).

    1. ``plr``: a section only the newer prescription format has (Warnings and Precautions,
       Use in Specific Populations, or Dosage Forms and Strengths).
    2. ``otc_drug_facts``: a section only Drug Facts has (Purpose, When using, Stop use, Do not
       use, Ask a doctor), or the source types the label as an over-the-counter drug.
    3. ``older``: a prescription section in the older format (Indications and Usage,
       Contraindications, Warnings, Precautions, Adverse Reactions, Clinical Pharmacology).
    4. ``unknown``: none of these.
    """
    if _has(record, PLR_FIELDS):
        return "plr"
    if _has(record, DRUG_FACTS_FIELDS) or product_type == "HUMAN OTC DRUG":
        return "otc_drug_facts"
    if _has(record, PRESCRIPTION_FIELDS):
        return "older"
    return "unknown"


def format_conflicts(record: dict[str, Any], product_type: str | None) -> list[str]:
    """Signals that point two ways (counted, never used to change the format)."""
    out = []
    plr, facts = _has(record, PLR_FIELDS), _has(record, DRUG_FACTS_FIELDS)
    if plr and facts:
        out.append("plr_and_drug_facts_sections")
    if plr and product_type == "HUMAN OTC DRUG":
        out.append("plr_sections_typed_otc")
    if facts and product_type == "HUMAN PRESCRIPTION DRUG":
        out.append("drug_facts_sections_typed_prescription")
    return out


def record_has_copyright_mark(record: dict[str, Any]) -> bool:
    """True when any text of the label (every text field, not the source's ``openfda``
    block) shows the copyright sign, the word "copyright" or "all rights reserved"."""
    for key, value in record.items():
        if key == "openfda":
            continue
        values = value if isinstance(value, list) else [value]
        for v in values:
            if isinstance(v, str) and COPYRIGHT.search(v):
                return True
    return False


# --- The product name, from the label's structured product data ----------------------------

#: The words a name may run to before the generic name starts again.
PRODUCT_NAME_MAX_WORDS = 8
PRODUCT_NAME_MAX_CHARS = 200
PRODUCT_NAME_SOURCE = "spl_product_data_elements"
_SMALL = frozenset(
    {"in", "and", "for", "of", "with", "or", "the", "a", "to", "&", "-", "per", "by"}
)
_LEAD = re.compile(r"^\s*SPL\s+(?:PRODUCT|LISTING)\s+DATA\s+ELEMENTS(?:\s+SECTION)?\s+", re.I)


def _letters(word: str) -> list[str]:
    return [ch for ch in word if ch.isalpha()]


def _all_lower(word: str) -> bool:
    letters = _letters(word)
    return bool(letters) and all(ch.islower() for ch in letters)


def _all_upper(word: str) -> bool:
    letters = _letters(word)
    return bool(letters) and all(ch.isupper() for ch in letters)


def split_product_name(product_data: str) -> tuple[str | None, str | None]:
    """The product name at the head of ``spl_product_data_elements``, and the rule that found it.

    The field is the label's structured product data run together: the product name, then the
    generic name, then the ingredients (in capitals), with nothing between them. The name ends
    where the first of these rules fires, tried in this order, within its first eight words:

    1. ``restart``: the first word comes back (``Zorvan tablets Zorvan ...``: a generic product
       named after its generic name, or a second product);
    2. ``lowercase``: a word in lower case follows a word with a capital
       (``ZORVAN zorvanide ...``); short joining words such as "and" or "for" do not count;
    3. ``ingredient``: a word not in capitals comes back later in capitals, as the ingredient
       (``Zorvan Zorvanide ZORVANIDE ...``).

    Returns ``(None, None)`` when no rule fires. A leading "SPL product data elements section"
    is skipped. The name is read from product data only, never from the label's prose.
    """
    words = _LEAD.sub("", product_data).split()
    if len(words) < 2:
        return None, None
    folded = [w.casefold() for w in words]
    last = min(PRODUCT_NAME_MAX_WORDS, len(words) - 1)
    found: tuple[int, str] | None = None
    for i in range(1, last + 1):
        if folded[i] == folded[0]:
            found = (i, "restart")
            break
    if found is None:
        for i in range(1, last + 1):
            capital_before = any(ch.isupper() for w in words[:i] for ch in w)
            if _all_lower(words[i]) and folded[i] not in _SMALL and capital_before:
                found = (i, "lowercase")
                break
    if found is None:
        for i in range(1, last + 1):
            if _all_upper(words[i]) or folded[i] in _SMALL:
                continue
            later = range(i + 1, len(words))
            if any(folded[j] == folded[i] and _all_upper(words[j]) for j in later):
                found = (i, "ingredient")
                break
    if found is None:
        return None, None
    name = " ".join(words[: found[0]])
    if len(name) > PRODUCT_NAME_MAX_CHARS:
        return None, None
    return name, found[1]


def product_name(record: dict[str, Any]) -> tuple[str | None, str, str | None]:
    """(name, source, rule) for one record; the source is ``none`` when no name is read."""
    data = " ".join(_strings(record, "spl_product_data_elements"))
    if not data.strip():
        return None, "none", None
    name, rule = split_product_name(clean(data)[:2000])
    return (name, PRODUCT_NAME_SOURCE, rule) if name else (None, "none", None)


def parse_label(record: dict[str, Any], with_tables: bool = True) -> LabelRow:
    """Read one source record into a :class:`LabelRow` (``with_tables=False`` skips the
    tables, for labels whose text is only counted)."""
    if not record.get("id") or not record.get("set_id"):
        raise LabelError("A label record has no id or no set_id; it cannot be identified.")
    openfda = record.get("openfda") or {}
    types = openfda.get("product_type") or []
    product_type = types[0] if types else None
    fmt = label_format(record, product_type)
    used: list[str] = []

    def field(name: str) -> str | None:
        text = join(_strings(record, name))
        if text:
            used.append(name)
        return text

    prescriber: dict[str, str | None] = {}
    for section, sources in PRESCRIBER_SOURCES.items():
        parts = [t for t in (field(s) for s in sources) if t]
        prescriber[section] = "\n\n".join(parts) if parts else None
    if prescriber["warnings_and_precautions"] is None and fmt != "otc_drug_facts":
        parts = [t for t in (field(s) for s in OLDER_WARNINGS) if t]
        prescriber["warnings_and_precautions"] = "\n\n".join(parts) if parts else None

    patient = {name: field(source) for name, source in PATIENT_SOURCES.items()}

    section_of = {s: sec for sec, srcs in PRESCRIBER_SOURCES.items() for s in srcs}
    section_of.update({s: sec for sec, s in PATIENT_SOURCES.items()})
    section_of.update({s: "warnings_and_precautions" for s in OLDER_WARNINGS})
    tables = []
    for source, section in section_of.items() if with_tables else ():
        for markup in _strings(record, f"{source}_table"):
            text = table_to_text(markup)
            if text:
                tables.append(Table(section=section, text=text))
                used.append(f"{source}_table")

    raw_time = record.get("effective_time")
    identity = Identity(
        id=str(record["id"]),
        set_id=str(record["set_id"]),
        version=_version(record.get("version")),
        effective_date=_date(raw_time),
        effective_time_raw=raw_time,
        harmonized=bool(openfda),
        product_type=product_type,
        label_format=fmt,
        routes=tuple(openfda.get("route") or ()),
        application_numbers=tuple(openfda.get("application_number") or ()),
        manufacturers=tuple(openfda.get("manufacturer_name") or ()),
        brand_names=tuple(openfda.get("brand_name") or ()),
        generic_names=tuple(openfda.get("generic_name") or ()),
        pharm_classes_epc=tuple(openfda.get("pharm_class_epc") or ()),
    )
    return LabelRow(
        identity=identity,
        prescriber=PrescriberSections(**prescriber),
        patient=PatientTexts(**patient),
        tables=tuple(tables),
        source_fields=tuple(dict.fromkeys(used)),
    )


def iter_rows(zip_path: Path | str) -> Iterator[LabelRow]:
    """Every label of one downloaded part, as rows."""
    for record in bulk.iter_labels(zip_path):
        yield parse_label(record)
