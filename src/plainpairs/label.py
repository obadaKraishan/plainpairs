"""One row per label, from one record of the label data.

The parser reads only the fields it names (see :mod:`plainpairs.schema`), cleans each one with
:func:`plainpairs.text.join` and keeps its headings. It never fails on a missing section: a
label without a boxed warning, or without any patient text, simply has ``None`` there. It does
fail, in plain words, on a record without an ``id`` or a ``set_id``.
"""

from __future__ import annotations

import datetime as dt
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
from plainpairs.text import join, table_to_text

#: Sections found only in "Drug Facts", the format of over-the-counter labels.
DRUG_FACTS_FIELDS = ("purpose", "when_using", "stop_use", "ask_doctor", "do_not_use")


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


def label_format(record: dict[str, Any], product_type: str | None) -> LabelFormat:
    """Which kind of label this is, from the sections it has."""
    if record.get("warnings_and_cautions"):
        return "plr"
    if product_type == "HUMAN OTC DRUG" or any(record.get(f) for f in DRUG_FACTS_FIELDS):
        return "otc_drug_facts"
    if any(record.get(f) for f in OLDER_WARNINGS) or record.get("indications_and_usage"):
        return "older"
    return "unknown"


def parse_label(record: dict[str, Any]) -> LabelRow:
    """Read one source record into a :class:`LabelRow`."""
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
    for source, section in section_of.items():
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
