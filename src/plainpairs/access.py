"""The easy-access layer: plain files beside the Parquet tables, for readers who do not use Parquet.

Every version from 0.2.0 holds, on top of its Parquet files (which stay the full release, and
the only files the card's configurations point at):

- ``00_start_here_labels.csv``: the whole ``current`` labels table, one row per label, with its
  reading levels and its listing flags (both are columns of that table) and no label text;
- ``00_start_here_labels.xlsx``: the same rows in a workbook with a Read me sheet and a Fields
  sheet (past about 100 MB, a seeded sample of 1,000 rows whose name says so);
- ``00_start_here_pairs_sample_1000.xlsx``: a seeded sample of 1,000 ``current`` section pairs
  with the patient segment and the prescriber section side by side, released text only (the
  pack's text tables, after the switch), and the same Read me sheet;
- ``fields.csv``: every column of every table, with its type, meaning and allowed values;
- ``codebook.csv``: the trusted codes of codebook version 1 and the alignment's ten heading keys,
  each with its definition, status and check;
- a gzipped CSV of every table beside its Parquet file (``data/current/labels.csv.gz``), unless
  it passes about 500 MB.

The Kaggle mirror carries the same files under flat names (``current_labels.csv``), its
per-table CSVs plain (Kaggle unpacks a gzipped file on upload), less any plain CSV over about
500 MB. The workbooks and the two catalogues are the same bytes on both hosts.

**Cells.** A struct's fields are columns of their own, named ``<column>.<field>``
(``t_medication_guide.flesch_kincaid``); a list's items are joined with ``"; "``; yes and no are
1 and 0; dates are ``YYYY-MM-DD``; a 32-bit float is written with the fewest digits that read
back as the same value; an empty cell has no value. A gzipped file has no time in its header,
so the same rows give the same bytes.

:func:`build` writes the files and returns their manifest entries; :func:`problems` checks them
against the pack's Parquet files row for row, so a CSV can never say what its table does not.
Nothing here holds label text except the pairs workbook, whose text comes from the pack's own
released text tables.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import math
import random
import re
import shutil
import struct
import sys
from collections.abc import Iterable, Iterator, Mapping
from datetime import date
from itertools import zip_longest
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from plainpairs import align, codes, xlsx

START_HERE = "00_start_here_labels.csv"
XLSX_WHOLE = "00_start_here_labels.xlsx"
XLSX_SAMPLE = "00_start_here_labels_sample_1000.xlsx"
PAIRS_BOOK = "00_start_here_pairs_sample_1000.xlsx"
FIELDS_FILE = "fields.csv"
CODEBOOK_FILE = "codebook.csv"
#: The first version that carries the layer; the pack check fails on a later one without it.
FIRST_VERSION = "0.2.0"
#: Past this size the labels workbook becomes a seeded sample.
XLSX_MAX_BYTES = 100_000_000
#: A gzipped CSV past this size is left out on both hosts; a plain one on Kaggle.
CSV_MAX_BYTES = 500_000_000
SAMPLE_ROWS = 1_000
SAMPLE_SEED = 20261126
LIST_JOIN = "; "
BATCH = 5_000
#: Where a cut text ends (inside Excel's limit, the mark included).
CUT_MARK = (
    " [... cut here at Excel's limit of 32,767 characters; the whole text is in the {table} table]"
)
FIELDS_HEADER = ("table", "column", "type", "meaning", "allowed_values", "csv")
CODEBOOK_HEADER = (
    "kind",
    "name",
    "label",
    "codebook_version",
    "columns_or_sections",
    "definition",
    "status",
    "check",
)
#: The trusted codes of codebook version 1: label, rule and development check, in the words of
#: ``docs/codebook.md`` ("Status" and "The rules").
CODE_TEXT = {
    "direct_address": (
        "Direct address",
        'the words "you", "your", "yours", "yourself", "yourselves"',
        "hits right 10/10; misses right 10/10",
    ),
    "commands": (
        "Instructions as commands",
        "a sentence that opens with a base-form verb from a fixed list of 151 (after list marks, "
        'quote marks and "Step 1:"), or with "Do not", "Don\'t" or "Never" and such a verb; a '
        'verb followed by "in", "of", "with", "is" and the like is read as a noun and not '
        'counted. conditional_commands: "If ..., call ..." (a condition, a comma, then a '
        "command)",
        "hits right 10/10; misses right 10/10",
    ),
    "distinct_actions": (
        "Distinct actions",
        "the number of different verbs that open the text's commands; a ban counts apart "
        '("take" and "not take" are two)',
        "checked with the command code",
    ),
    "percentages": (
        "Percentages",
        'a number followed by "%" or "percent"',
        "hits right 10/10; misses right 10/10",
    ),
    "one_in_n": (
        '"1 in N"',
        '"1 in 10", "one in ten", "3 out of every 100" and the like',
        "hits right 9/10, then 9/9; misses right 10/10",
    ),
    "frequencies": (
        "Frequencies",
        '"twice a day", "3 times a week", "every 12 hours", "each morning", "daily", "q12h"',
        "hits right 9/10; misses right 10/10",
    ),
    "doses": (
        "Doses",
        "a number followed by a unit: mg, mcg, g, mL, units, IU, mEq, mmol, mg/kg, mg/m2, mcg/kg",
        "hits right 10/10; misses right 10/10",
    ),
    "whom_to_call": (
        "Whom to call",
        'a sentence with a contact verb ("call", "contact", "tell", "talk to", "ask", "notify", '
        '"inform", "report", "go to", "get help", "seek care") and someone to contact '
        '("doctor", "healthcare provider", "pharmacist", "nurse", "prescriber", "poison '
        'control", "911", "emergency", "hospital", "FDA")',
        "hits right 36/40, then 36/36",
    ),
    "long_sentences_structured": (
        "Long sentences (structure, current)",
        "sentences of more than 20 and more than 40 words, and the longest, counted on the "
        "blocks of DailyMed's XML (current labels only)",
        "hits right 19/20; misses right 20/20",
    ),
}
#: The ten heading keys: label, what opens the segment, and the blind hand check of 100 pairs by
#: one coder (``docs/method.md``, section 7): yes, partly, no, the share "yes or partly" and its
#: 95% interval.
KEY_TEXT = {
    "how_to_take": (
        "how to take",
        "how to take or use the medicine",
        (9, 1, 0),
        "100%",
        "72% to 100%",
    ),
    "ingredients": ("ingredients", "the ingredients", (9, 1, 0), "100%", "72% to 100%"),
    "most_important": (
        "most important",
        "the most important information to know",
        (7, 3, 0),
        "100%",
        "72% to 100%",
    ),
    "side_effects": ("side effects", "the possible side effects", (9, 1, 0), "100%", "72% to 100%"),
    "storage": ("storage", "how to store the medicine", (6, 3, 1), "90%", "60% to 98%"),
    "what_is": ("what is", "what the medicine is", (7, 3, 0), "100%", "72% to 100%"),
    "who_should_not": (
        "who should not",
        "who should not take or use the medicine",
        (9, 1, 0),
        "100%",
        "72% to 100%",
    ),
    "before": (
        "before taking",
        "what to tell the healthcare provider before taking or using it",
        (0, 7, 3),
        "70%",
        "40% to 89%",
    ),
    "avoid": ("avoid", "what to avoid while taking or using it", (1, 4, 5), "50%", "24% to 76%"),
    "general": (
        "general information",
        "general information about the safe and effective use of medicines",
        (0, 4, 6),
        "40%",
        "17% to 69%",
    ),
}
#: The pairs workbook's columns and what each holds.
PAIR_COLUMNS = {
    "set_id": "the label's set id",
    "version": "the label's version",
    "product_name": "the name at the head of the label's product data (labels.product_name)",
    "kind": "the patient text the segment is in: medication_guide or patient_package_insert",
    "segment_index": "the segment's place in the patient text, from 0",
    "heading_key": "the standard heading that opens the segment (codebook.csv)",
    "rule_status": "rule_released: the heading key keeps its mapping rule; similarity_only: "
    "similarity scores only",
    "best_section": "the prescriber section most similar to the segment (TF-IDF cosine): the "
    "section shown in prescriber_text",
    "best_similarity": "that section's similarity",
    "best_is_mapped": "1 when that section is one the heading key is mapped to, 0 when not",
    "mapped_present": "the mapped sections the label has",
    "patient_segment": "the segment's text: the patient text from seg_start to seg_end",
    "prescriber_text": "the text of best_section, the prescriber section",
}
#: The struct columns' field tables in ``docs/schema.md``.
NCI_STRUCTS = {"left_out": "nci_left_out", "measures": "nci_measures", "codes": "nci_codes"}


class AccessError(RuntimeError):
    """The layer cannot be built from this pack."""


# --- cells -------------------------------------------------------------------------------------


def _float(value: float, t: pa.DataType | None) -> str:
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Inf" if value > 0 else "-Inf"
    if t is not None and pa.types.is_float32(t):
        want = struct.pack("<f", value)
        for digits in range(1, 10):
            s = f"{value:.{digits}g}"
            if struct.pack("<f", float(s)) == want:
                return repr(float(s))
    return repr(value)


def cell(value: Any, t: pa.DataType | None = None) -> str:
    """A value as a CSV cell writes it (``t``: its Arrow type, for floats and lists)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (list, tuple)):
        inner = t.value_type if t is not None and pa.types.is_list(t) else None
        return LIST_JOIN.join(cell(v, inner) for v in value)
    if isinstance(value, float):
        return _float(value, t)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def book_value(value: Any, t: pa.DataType | None = None) -> Any:
    """A value as the workbook writes it: numbers as numbers, the rest as the CSV's text."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return float(_float(value, t))
    return cell(value, t)


def flat(table: pa.Table) -> pa.Table:
    """The table with every struct, at every level, flattened into ``parent.field`` columns."""
    while any(pa.types.is_struct(t) for t in table.schema.types):
        table = table.flatten()
    return table


def flat_schema(path: Path) -> pa.Schema:
    return flat(pq.read_schema(path).empty_table()).schema


def table_values(path: Path, columns: list[str] | None = None) -> Iterator[list[Any]]:
    """The rows of a Parquet file, flattened, as values (not yet cells), batch by batch."""
    pf = pq.ParquetFile(path)
    for batch in pf.iter_batches(batch_size=BATCH, columns=columns):
        t = flat(pa.Table.from_batches([batch]))
        cols = [t.column(i).to_pylist() for i in range(t.num_columns)]
        yield from (list(r) for r in zip(*cols, strict=True))


def table_cells(path: Path) -> tuple[list[str], Iterator[list[str]]]:
    """A Parquet file's CSV header and its rows as cells."""
    schema = flat_schema(path)
    types = schema.types

    def rows() -> Iterator[list[str]]:
        for r in table_values(path):
            yield [cell(v, t) for v, t in zip(r, types, strict=True)]

    return list(schema.names), rows()


# --- CSV files ---------------------------------------------------------------------------------


class _Counted(io.RawIOBase):
    """A sink that counts and hashes the plain bytes written through it."""

    def __init__(self, sink: Any) -> None:
        self.sink, self.n, self.h = sink, 0, hashlib.sha256()

    def writable(self) -> bool:
        return True

    def write(self, b: Any) -> int:
        data = bytes(b)
        self.sink.write(data)
        self.h.update(data)
        self.n += len(data)
        return len(data)


def write_csv(path: Path, header: Iterable[str], rows: Iterable[list[str]]) -> dict[str, Any]:
    """Write a CSV file (gzipped when the name ends in ``.gz``). Returns the data rows written
    and the plain content's bytes and SHA-256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("wb") as raw:
        gz = (
            gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9)
            if path.name.endswith(".gz")
            else None
        )
        counted = _Counted(gz if gz is not None else raw)
        buffered = io.BufferedWriter(counted, buffer_size=1 << 20)
        text = io.TextIOWrapper(buffered, encoding="utf-8", newline="")
        w = csv.writer(text)
        w.writerow(list(header))
        for row in rows:
            w.writerow(row)
            n += 1
        text.flush()
        buffered.flush()
        if gz is not None:
            gz.close()
    return {"rows": n, "csv_bytes": counted.n, "csv_sha256": counted.h.hexdigest()}


def read_csv(path: Path) -> Iterator[list[str]]:
    """The rows of a CSV file the layer wrote (gzipped or not), the header first. A prescriber
    section can pass the csv module's default field limit (131,072 characters), so the limit is
    raised first."""
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    if path.name.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8", newline="") as text:
            yield from csv.reader(text)
    else:
        with path.open(encoding="utf-8", newline="") as text:
            yield from csv.reader(text)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _plain_sha(path: Path) -> tuple[int, str]:
    h, n = hashlib.sha256(), 0
    with gzip.open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return n, h.hexdigest()


# --- fields.csv ----------------------------------------------------------------------------------


def type_words(t: pa.DataType) -> str:
    if pa.types.is_boolean(t):
        return "yes or no"
    if pa.types.is_integer(t):
        return "whole number"
    if pa.types.is_floating(t):
        return "number"
    if pa.types.is_date(t):
        return "date"
    if pa.types.is_list(t):
        return "list of " + {"text": "text", "whole number": "whole numbers"}.get(
            type_words(t.value_type), type_words(t.value_type)
        )
    return "text"


_CODE_VALUE = re.compile(r"[a-z][a-z0-9_]*")


def _allowed(column: pa.ChunkedArray, t: pa.DataType) -> str:
    """The values a column may take, when they are few codes; read from the column itself."""
    if pa.types.is_boolean(t):
        return "1 or 0 (true or false in Parquet)"
    items = column
    prefix = ""
    if pa.types.is_list(t):
        items = pc.list_flatten(column)
        prefix = "items from: "
        t = t.value_type
    if not (pa.types.is_string(t) or pa.types.is_large_string(t)):
        return ""
    values = [v for v in pc.unique(items).to_pylist() if v is not None]
    if 1 <= len(values) <= 12 and all(_CODE_VALUE.fullmatch(v) for v in values):
        return prefix + LIST_JOIN.join(sorted(values))
    return ""


def _struct_table(doc_table: str, top: str) -> str:
    if doc_table == "nci_summaries":
        return NCI_STRUCTS.get(top, "")
    return "measures_structured" if top.endswith("_structured") else "measures"


def meaning(doc: Any, doc_table: str, column: str) -> str:
    """A flattened column's meaning from ``docs/schema.md`` (its struct's field table for a
    field); empty when the doc does not give one."""
    top, _, leaf = column.partition(".")
    base = doc.describe(doc_table, top) or ""
    if not leaf:
        return base
    part = doc.describe(_struct_table(doc_table, top), leaf.split(".")[-1]) or ""
    if not base or not part:
        return ""
    return f"{base.rstrip('.')}; field {leaf}: {part[:1].lower()}{part[1:]}"


def fields_rows(
    pack_dir: Path, manifest: Mapping[str, Any], facts: Mapping[str, Any]
) -> list[list[str]]:
    """``fields.csv``: every column of every table (flattened as the CSV files write them), then
    the start-here file's and the pairs workbook's columns."""
    from plainpairs import kaggle_meta

    doc = kaggle_meta.read_schema_doc()
    hf_out = set(facts.get("csv_left_out") or [])
    kaggle_out = set(facts.get("kaggle_csv_left_out") or [])
    out = []
    for f in manifest["files"]:
        path = pack_dir / f["path"]
        schema = flat_schema(path)
        names = [n for n in schema.names if n != "text"]
        data = flat(
            pq.read_table(path, columns=[c for c in pq.read_schema(path).names if c != "text"])
        )
        gz = f["path"].replace(".parquet", ".csv.gz")
        where = (
            "none (Parquet only)"
            if gz in hf_out
            else "Hugging Face only"
            if f["config"] in kaggle_out
            else "Hugging Face and Kaggle"
        )
        for name, t in zip(schema.names, schema.types, strict=True):
            allowed = _allowed(data.column(name), t) if name in names else ""
            what = meaning(doc, kaggle_meta.doc_table(f), name)
            out.append([f["config"], name, type_words(t), what, allowed, where])
    labels = next(f for f in manifest["files"] if f["config"] == "current_labels")
    for row in [r for r in out if r[0] == labels["config"]]:
        out.append(["start_here", *row[1:5], "Hugging Face and Kaggle"])
    for name, what in PAIR_COLUMNS.items():
        out.append(["pairs_sample", name, _pair_type(name), what, "", "workbook only"])
    return out


def _pair_type(name: str) -> str:
    if name in ("version", "segment_index"):
        return "whole number"
    if name == "best_similarity":
        return "number"
    if name == "best_is_mapped":
        return "yes or no"
    if name == "mapped_present":
        return "list of text"
    return "text"


# --- codebook.csv --------------------------------------------------------------------------------


def key_statuses(pack_dir: Path, manifest: Mapping[str, Any]) -> dict[str, str]:
    """Each heading key's ``rule_status`` in the pack's section pairs (one per key)."""
    seen: dict[str, set[str]] = {}
    for f in manifest["files"]:
        if f["table"] != "section_pairs":
            continue
        t = pq.read_table(pack_dir / f["path"], columns=["heading_key", "rule_status"])
        for k, s in zip(t["heading_key"].to_pylist(), t["rule_status"].to_pylist(), strict=True):
            seen.setdefault(k, set()).add(s)
    bad = {k: sorted(map(str, v)) for k, v in seen.items() if len(v) != 1}
    if bad:
        raise AccessError(f"heading keys with more than one rule_status in the pack: {bad}")
    return {k: next(iter(v)) for k, v in seen.items()}


def codebook_rows(pack_dir: Path, manifest: Mapping[str, Any]) -> list[list[str]]:
    """``codebook.csv``: the trusted codes of the codebook, then the ten heading keys."""
    out = []
    version = str(manifest.get("code_version") or codes.CODE_VERSION)
    for name, (columns, status) in codes.CODEBOOK.items():
        if status != "trusted":
            continue
        label, definition, check = CODE_TEXT[name]
        out.append(
            ["code", name, label, version, LIST_JOIN.join(columns), definition, status, check]
        )
    statuses = key_statuses(pack_dir, manifest)
    for key, sections in align.MAPPING.items():
        label, opens, (yes, partly, no), share, interval = KEY_TEXT[key]
        source = align.mapping_source(key)
        definition = (
            f"a segment of a Medication Guide or patient package insert that opens with the "
            f"standard heading on {opens}; mapped to these prescriber sections by "
            + (
                "the Medication Guide regulation (21 CFR 208.20)"
                if source == "regulation"
                else "this project's own choice"
            )
        )
        check = (
            f"blind hand check, one coder, 10 pairs: yes {yes}, partly {partly}, no {no}; "
            f"yes or partly {share} (95% interval {interval}); a key keeps its rule at 80%"
        )
        out.append(
            [
                "heading_key",
                key,
                label,
                version,
                LIST_JOIN.join(sections),
                definition,
                statuses.get(key, ""),
                check,
            ]
        )
    return out


# --- the pairs sample ----------------------------------------------------------------------------


def _cut(text: str, table: str) -> tuple[str, bool]:
    if len(text) <= xlsx.MAX_CELL:
        return text, False
    mark = CUT_MARK.format(table=table)
    return text[: xlsx.MAX_CELL - len(mark)] + mark, True


def _keys(path: Path) -> set[tuple[str, str]]:
    t = pq.read_table(path, columns=["set_id", "section", "part"])
    t = t.filter(pc.equal(t["part"], "text"))
    return set(zip(t["set_id"].to_pylist(), t["section"].to_pylist(), strict=True))


def _texts(path: Path, wanted: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    out = {}
    pf = pq.ParquetFile(path)
    for b in pf.iter_batches(batch_size=BATCH, columns=["set_id", "section", "part", "text"]):
        for sid, sec, part, text in zip(*(b.column(i).to_pylist() for i in range(4)), strict=True):
            if part == "text" and (sid, sec) in wanted:
                out[(sid, sec)] = text
    return out


def pairs_sample(pack_dir: Path) -> tuple[list[list[Any]], dict[str, int]]:
    """The pairs workbook's rows (as the workbook writes them) and its counts: a seeded sample
    of ``current`` section pairs whose patient text and prescriber section both have released
    text in the pack."""
    base = pack_dir / "data" / "current"
    names = {
        r["set_id"]: r["product_name"]
        for r in pq.read_table(
            base / "labels.parquet", columns=["set_id", "product_name"]
        ).to_pylist()
    }
    cols = [
        c for c in PAIR_COLUMNS if c not in ("product_name", "patient_segment", "prescriber_text")
    ]
    table = pq.read_table(base / "section_pairs.parquet", columns=[*cols, "seg_start", "seg_end"])
    types = {c: table.schema.field(c).type for c in cols}
    pairs = table.to_pylist()
    patient, prescriber = (
        _keys(base / "text_patient.parquet"),
        _keys(base / "text_prescriber.parquet"),
    )
    eligible = [
        i
        for i, p in enumerate(pairs)
        if p["best_section"]
        and (p["set_id"], p["kind"]) in patient
        and (p["set_id"], p["best_section"]) in prescriber
    ]
    picked = sorted(random.Random(SAMPLE_SEED).sample(eligible, min(SAMPLE_ROWS, len(eligible))))
    chosen = [pairs[i] for i in picked]
    ptext = _texts(base / "text_patient.parquet", {(p["set_id"], p["kind"]) for p in chosen})
    rtext = _texts(
        base / "text_prescriber.parquet", {(p["set_id"], p["best_section"]) for p in chosen}
    )
    rows, cuts = [], 0
    for p in chosen:
        segment, a = _cut(
            ptext[(p["set_id"], p["kind"])][p["seg_start"] : p["seg_end"]].strip(), "text_patient"
        )
        section, b = _cut(rtext[(p["set_id"], p["best_section"])], "text_prescriber")
        cuts += a + b
        row = []
        for c in PAIR_COLUMNS:
            if c == "product_name":
                row.append(names.get(p["set_id"]))
            elif c == "patient_segment":
                row.append(segment)
            elif c == "prescriber_text":
                row.append(section)
            else:
                row.append(book_value(p[c], types[c]))
        rows.append(row)
    return rows, {"pairs_eligible": len(eligible), "pairs_rows": len(rows), "pairs_cells_cut": cuts}


# --- the workbooks -------------------------------------------------------------------------------


def read_me_rows(manifest: Mapping[str, Any], what: str) -> list[list[str]]:
    """The workbooks' Read me sheet, one sentence or quotation a row."""
    from plainpairs import pack

    s = manifest["sources"]
    version = manifest["version"]
    return [
        [f"PlainPairs {version}"],
        [""],
        [
            "Not medical information. PlainPairs is a research record of how text is worded for "
            "prescribers and for patients in United States medicine labels. The labels in it "
            "may be out of date, incomplete or replaced by newer versions. Never use any of it "
            "to decide anything about a medicine or about care. For a medicine, read the "
            "current label that comes with it and talk to a doctor or pharmacist. The "
            "project's measures describe wording only: they do not say what a medicine does, "
            "whether it is safe, or who should use it."
        ],
        [""],
        [
            "What PlainPairs is: for every label in a prescription format that carries a "
            "Medication Guide or a patient package insert, the label's sections written for "
            "prescribers next to its text written for patients, matched section by section, "
            f"with reading-level and plain-language measures on both sides. Version {version} "
            f"was built from the openFDA drug label export of {s['openfda_label_export']}."
        ],
        [what],
        [
            "Cells: 1 is yes and 0 is no; an empty cell has no value; a list's items are joined "
            "with a semicolon and a space; a struct's fields are columns of their own "
            "(t_medication_guide.flesch_kincaid). fields.csv gives every column's meaning, type "
            "and allowed values."
        ],
        [
            "The full release is the Parquet files: on Hugging Face (" + pack.HF_URL + ") under "
            "data/, on Kaggle as current_labels.parquet and the like. Never pool the current "
            "and unlisted configurations."
        ],
        [""],
        ["Sources, terms and credit:"],
        [
            f'openFDA (the labels; export of {s["openfda_label_export"]}): "Unless otherwise '
            "noted, the content, data, documentation, code, and related materials on openFDA is "
            "public domain and made available with a Creative Commons CC0 1.0 Universal "
            'dedication." Data provided by the U.S. Food and Drug Administration '
            '(https://open.fda.gov). "Do not rely on openFDA to make decisions regarding '
            "medical care. Always speak to your health provider about the risks and benefits "
            'of FDA-regulated products."'
        ],
        [
            "DailyMed, National Library of Medicine: the text structure of current labels (its "
            f"full release of human prescription labels of {pack.dailymed_words(dict(s))}) and the "
            "served flag. Courtesy of the National Library "
            "of Medicine."
        ],
        [
            "The companies that market each medicine write its label; some labels carry a "
            "company's copyright mark, and their text is held back (their record rows stay)."
        ],
        [
            "Not made, endorsed or checked by the U.S. Food and Drug Administration, the "
            "National Library of Medicine, the National Cancer Institute or any company whose "
            "labels it holds. What applies to each configuration is in LICENSES.md."
        ],
        [""],
        ["How to cite: the paper first,"],
        [pack.paper_citation()],
        ["then the dataset and its version:"],
        [pack.citation(version, manifest["created"])],
        ["Please also give the sources' credit lines above."],
    ]


def _chain(first: list, rest: Iterable) -> Iterator:
    yield from first
    yield from rest


def write_labels_book(
    pack_dir: Path,
    manifest: Mapping[str, Any],
    header: list[str],
    types: list[pa.DataType],
    rows: list[list[Any]],
    field_rows: list[list[str]],
    max_bytes: int | None = None,
) -> tuple[Path, bool, list[int]]:
    """The labels workbook: the whole table, or past ``max_bytes`` a seeded sample. Returns its
    path, whether it is the sample, and the indexes of the rows it holds."""
    start = [r[1:] for r in field_rows if r[0] == "start_here"]

    def write(name: str, picked: list[int], sample: bool) -> Path:
        what = (
            f"This workbook: a seeded random sample of {len(picked):,} of the {len(rows):,} "
            f"current labels (seed {SAMPLE_SEED}), since the whole table is too large for a "
            f"workbook; the whole table is {START_HERE}."
            if sample
            else f"This workbook: every current label of this version, {len(rows):,} rows, the "
            f"same as {START_HERE}, one row per label, with its reading levels and listing "
            "flags and no label text."
        )
        path = pack_dir / name
        data = ([book_value(v, t) for v, t in zip(rows[i], types, strict=True)] for i in picked)
        xlsx.write_data_workbook(
            path,
            (
                xlsx.DataSheet(
                    "Read me", read_me_rows(manifest, what), header=False, widths=(120,)
                ),
                xlsx.DataSheet("Labels", _chain([header], data)),
                xlsx.DataSheet("Fields", _chain([list(FIELDS_HEADER[1:])], start)),
            ),
        )
        return path

    every = list(range(len(rows)))
    path = write(XLSX_WHOLE, every, False)
    if path.stat().st_size <= (XLSX_MAX_BYTES if max_bytes is None else max_bytes):
        return path, False, every
    path.unlink()
    picked = sorted(random.Random(SAMPLE_SEED).sample(every, min(SAMPLE_ROWS, len(every))))
    return write(XLSX_SAMPLE, picked, True), True, picked


def write_pairs_book(pack_dir: Path, manifest: Mapping[str, Any], rows: list[list[Any]]) -> Path:
    what = (
        f"This workbook: a seeded random sample of {len(rows):,} current section pairs (seed "
        f"{SAMPLE_SEED}), each a segment of a Medication Guide or patient package insert next to "
        "the prescriber section most similar to it, drawn from the pairs whose two texts are "
        "both released (labels that show no company copyright mark). A text over Excel's "
        "32,767 characters is cut, and the cut is marked in the cell. The Columns sheet says "
        "what each column holds; codebook.csv gives the heading keys."
    )
    path = pack_dir / PAIRS_BOOK
    xlsx.write_data_workbook(
        path,
        (
            xlsx.DataSheet("Read me", read_me_rows(manifest, what), header=False, widths=(120,)),
            xlsx.DataSheet(
                "Pairs",
                _chain([list(PAIR_COLUMNS)], rows),
                widths=(38, 8, 24, 22, 8, 16, 16, 30, 10, 8, 30, 80, 80),
            ),
            xlsx.DataSheet(
                "Columns",
                _chain([["column", "what it holds"]], [list(x) for x in PAIR_COLUMNS.items()]),
            ),
        ),
    )
    return path


# --- build ---------------------------------------------------------------------------------------


def _entry(pack_dir: Path, path: Path, rows: int, **more: Any) -> dict[str, Any]:
    return {
        "path": path.relative_to(pack_dir).as_posix(),
        "rows": rows,
        "bytes": path.stat().st_size,
        "sha256": _sha(path),
        **more,
    }


def _longest(rows: Iterable[list[str]]) -> int:
    return max((len(c) for r in rows for c in r), default=0)


def build(
    pack_dir: Path, manifest: Mapping[str, Any], csv_max_bytes: int | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Write the layer into a pack whose Parquet files and manifest entries exist; return the
    manifest's ``access_files`` (in the order a reader meets them) and its ``access`` facts."""
    pack_dir = Path(pack_dir)
    if csv_max_bytes is None:
        csv_max_bytes = CSV_MAX_BYTES
    facts: dict[str, Any] = {"csv_max_bytes": csv_max_bytes, "sample_seed": SAMPLE_SEED}
    tables: list[dict[str, Any]] = []
    left_out, kaggle_out = [], []
    for f in manifest["files"]:
        gz = pack_dir / f["path"].replace(".parquet", ".csv.gz")
        header, rows = table_cells(pack_dir / f["path"])
        info = write_csv(gz, header, rows)
        if gz.stat().st_size > csv_max_bytes:
            gz.unlink()
            left_out.append(gz.relative_to(pack_dir).as_posix())
            continue
        if info["csv_bytes"] > csv_max_bytes:
            kaggle_out.append(f["config"])
        tables.append(
            _entry(
                pack_dir,
                gz,
                info["rows"],
                config=f["config"],
                csv_bytes=info["csv_bytes"],
                csv_sha256=info["csv_sha256"],
            )
        )
    facts["csv_left_out"] = left_out
    facts["kaggle_csv_left_out"] = kaggle_out
    labels = pack_dir / "data" / "current" / "labels.parquet"
    schema = flat_schema(labels)
    header, types = list(schema.names), list(schema.types)
    values = list(table_values(labels))
    cells = [[cell(v, t) for v, t in zip(r, types, strict=True)] for r in values]
    entries = []
    info = write_csv(pack_dir / START_HERE, header, cells)
    entries.append(_entry(pack_dir, pack_dir / START_HERE, info["rows"]))
    field_rows = fields_rows(pack_dir, manifest, facts)
    book, sample, picked = write_labels_book(pack_dir, manifest, header, types, values, field_rows)
    entries.append(_entry(pack_dir, book, len(picked)))
    pair_rows, pair_facts = pairs_sample(pack_dir)
    entries.append(
        _entry(pack_dir, write_pairs_book(pack_dir, manifest, pair_rows), len(pair_rows))
    )
    info = write_csv(pack_dir / FIELDS_FILE, FIELDS_HEADER, field_rows)
    entries.append(_entry(pack_dir, pack_dir / FIELDS_FILE, info["rows"]))
    book_rows = codebook_rows(pack_dir, manifest)
    info = write_csv(pack_dir / CODEBOOK_FILE, CODEBOOK_HEADER, book_rows)
    entries.append(_entry(pack_dir, pack_dir / CODEBOOK_FILE, info["rows"]))
    facts.update(
        {
            "start_here_rows": len(cells),
            "start_here_columns": len(header),
            "start_here_longest_cell": _longest(cells),
            "workbook": "sample" if sample else "whole",
            "workbook_rows": len(picked),
            **pair_facts,
            "codes": sum(1 for r in book_rows if r[0] == "code"),
            "heading_keys": sum(1 for r in book_rows if r[0] == "heading_key"),
            "fields": len(field_rows),
        }
    )
    return entries + tables, facts


# --- check ---------------------------------------------------------------------------------------


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version)[:3])


def expected_names(manifest: Mapping[str, Any]) -> list[str]:
    facts = manifest.get("access") or {}
    book = XLSX_SAMPLE if facts.get("workbook") == "sample" else XLSX_WHOLE
    out = [START_HERE, book, PAIRS_BOOK, FIELDS_FILE, CODEBOOK_FILE]
    gone = set(facts.get("csv_left_out") or [])
    for f in manifest["files"]:
        gz = f["path"].replace(".parquet", ".csv.gz")
        if gz not in gone:
            out.append(gz)
    return out


def _same(path: Path, header: list[str], rows: Iterable[list[str]], label: str) -> list[str]:
    if not path.exists():
        return [f"{label}: missing."]
    got = read_csv(path)
    if next(got, None) != header:
        return [f"{label}: its header differs from its table's columns (rebuild the pack)."]
    for n, (a, b) in enumerate(zip_longest(got, rows), start=1):
        if a is None or b is None:
            return [f"{label}: it holds a different number of rows from its table."]
        if a != b:
            return [f"{label}: row {n} differs from its table (rebuild the pack)."]
    return []


def _written(value: Any) -> str:
    """A workbook value as the sheet's XML holds it (numbers as written)."""
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return repr(value)
    return str(value)


def _lines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _sheet_problems(
    path: Path, sheet: int, header: list[str], rows: Iterable[list[str]], label: str
) -> list[str]:
    got = xlsx.read_data_rows(path, sheet)
    if [_lines(c) for c in next(got, [])] != header:
        return [f"{label}: the sheet's header differs."]
    for n, (a, b) in enumerate(zip_longest(got, rows), start=1):
        if a is None or b is None:
            return [f"{label}: the sheet holds a different number of rows."]
        want = [_lines(c) for c in b]
        a = a + [""] * (len(want) - len(a))
        if a != want:
            return [f"{label}: row {n} differs."]
    return []


def problems(pack_dir: Path | str, manifest: Mapping[str, Any]) -> list[str]:
    """Every rule the layer must pass (counts and file names only, never a cell's words)."""
    pack_dir = Path(pack_dir)
    listed = manifest.get("access_files") or []
    if not listed:
        if version_tuple(str(manifest.get("version", "0"))) >= version_tuple(FIRST_VERSION):
            return [
                f"the easy-access layer is missing: every version from {FIRST_VERSION} carries "
                f"{START_HERE} and the rest (rebuild the pack)."
            ]
        return []
    fail: list[str] = []
    names = [f["path"] for f in listed]
    want = expected_names(manifest)
    if names != want:
        missing = [n for n in want if n not in names]
        return [
            "manifest.json: access_files are not the layer's files in order"
            + (f"; a file of the easy-access layer is missing: {missing[0]}" if missing else "")
            + " (rebuild the pack)."
        ]
    for f in listed:
        path = pack_dir / f["path"]
        if not path.exists():
            fail.append(f"{f['path']}: in the manifest but missing.")
        elif path.stat().st_size != f["bytes"] or _sha(path) != f["sha256"]:
            fail.append(f"{f['path']}: does not match its size or SHA-256 in the manifest.")
    if fail:
        return fail
    facts = manifest.get("access") or {}
    labels = pack_dir / "data" / "current" / "labels.parquet"
    header, rows = table_cells(labels)
    cells = list(rows)
    fail += _same(pack_dir / START_HERE, header, iter(cells), START_HERE)
    if len(cells) + 1 > xlsx.MAX_ROWS:
        fail.append(f"{START_HERE}: {len(cells):,} rows, over Excel's {xlsx.MAX_ROWS:,}.")
    if len(header) > xlsx.MAX_COLUMNS:
        fail.append(f"{START_HERE}: {len(header):,} columns, over Excel's {xlsx.MAX_COLUMNS:,}.")
    long = sum(1 for r in cells for c in r if len(c) > xlsx.MAX_CELL)
    if long:
        fail.append(f"{START_HERE}: {long} cell(s) over Excel's {xlsx.MAX_CELL:,} characters.")
    book = names[1]
    picked = (
        sorted(random.Random(SAMPLE_SEED).sample(range(len(cells)), min(SAMPLE_ROWS, len(cells))))
        if book == XLSX_SAMPLE
        else range(len(cells))
    )
    fail += _sheet_problems(
        pack_dir / book, 2, header, (cells[i] for i in picked), f"{book}, Labels"
    )
    pair_rows, pair_facts = pairs_sample(pack_dir)
    if any(facts.get(k) != v for k, v in pair_facts.items()):
        fail.append(f"{PAIRS_BOOK}: its counts differ from the manifest's.")
    fail += _sheet_problems(
        pack_dir / PAIRS_BOOK,
        2,
        list(PAIR_COLUMNS),
        ([_written(v) for v in r] for r in pair_rows),
        f"{PAIRS_BOOK}, Pairs",
    )
    if any(len(c) > xlsx.MAX_CELL for r in pair_rows for c in r if isinstance(c, str)):
        fail.append(f"{PAIRS_BOOK}: a cell over Excel's limit.")
    field_rows = fields_rows(pack_dir, manifest, facts)
    fail += _same(pack_dir / FIELDS_FILE, list(FIELDS_HEADER), iter(field_rows), FIELDS_FILE)
    bare = sum(1 for r in field_rows if not r[3])
    if bare:
        fail.append(
            f"{FIELDS_FILE}: {bare} columns without a meaning; describe them in docs/schema.md."
        )
    try:
        book_rows = codebook_rows(pack_dir, manifest)
    except AccessError as exc:
        fail.append(f"{CODEBOOK_FILE}: {exc}")
    else:
        fail += _same(
            pack_dir / CODEBOOK_FILE, list(CODEBOOK_HEADER), iter(book_rows), CODEBOOK_FILE
        )
    by_config = {f["config"]: f for f in manifest["files"]}
    for f in listed[5:]:
        source = pack_dir / by_config[f["config"]]["path"]
        header, rows = table_cells(source)
        fail += _same(pack_dir / f["path"], header, rows, f["path"])
        if (f.get("csv_bytes"), f.get("csv_sha256")) != _plain_sha(pack_dir / f["path"]):
            fail.append(f"{f['path']}: its plain content differs from the manifest's.")
    return fail


# --- the Kaggle mirror's copies ------------------------------------------------------------------


def kaggle_files(manifest: Mapping[str, Any]) -> list[tuple[str, str]]:
    """The layer's Kaggle files in order: (Kaggle name, pack path). A table's CSV is plain on
    Kaggle (``current_labels.csv``); one whose plain CSV passes the cap is left out."""
    out = []
    kaggle_out = set((manifest.get("access") or {}).get("kaggle_csv_left_out") or [])
    for f in manifest.get("access_files") or []:
        if "config" not in f:
            out.append((f["path"], f["path"]))
        elif f["config"] not in kaggle_out:
            out.append((f"{f['config']}.csv", f["path"]))
    return out


def build_kaggle(pack_dir: Path, out_dir: Path, manifest: Mapping[str, Any]) -> list[str]:
    """Copy the layer into the Kaggle folder: the start-here file, the workbooks and the two
    catalogues as they are, and each table's CSV unpacked."""
    names = []
    for name, source in kaggle_files(manifest):
        src, dest = Path(pack_dir) / source, Path(out_dir) / name
        if source.endswith(".gz"):
            with gzip.open(src, "rb") as fh, dest.open("wb") as out:
                shutil.copyfileobj(fh, out, 1 << 20)
        else:
            shutil.copyfile(src, dest)
        names.append(name)
    return names


def kaggle_problems(pack_dir: Path, out_dir: Path, manifest: Mapping[str, Any]) -> list[str]:
    """The mirror's layer: every file present and equal to the pack's (a plain CSV to its gzipped
    file's content), and the start-here file first."""
    fail = []
    by_path = {f["path"]: f for f in manifest.get("access_files") or []}
    files = kaggle_files(manifest)
    for name, source in files:
        dest = Path(out_dir) / name
        if not dest.exists():
            fail.append(f"kaggle/{name}: missing.")
            continue
        entry = by_path[source]
        want = entry["csv_sha256"] if source.endswith(".gz") else entry["sha256"]
        if _sha(dest) != want:
            fail.append(f"kaggle/{name}: differs from the pack's {source}.")
    if files and sorted(n for n, _ in files)[0] != START_HERE:
        fail.append(f"kaggle: {START_HERE} is not the first file by name.")
    return fail


# --- "Start here", on the card and the Kaggle description ----------------------------------------

KAGGLE_INPUT = "/kaggle/input/plainpairs"


def r_lines(kaggle: bool = False) -> str:
    """Three lines of R (base R, no package) that join a label with its section pairs and both
    texts, from the CSV files."""
    path = f"{KAGGLE_INPUT}/current_%s.csv" if kaggle else "data/current/%s.csv.gz"
    return "\n".join(
        [
            f'r <- function(t) read.csv(sprintf("{path}", t), encoding = "UTF-8"); '
            'txt <- function(t) subset(r(t), part == "text", c(set_id, section, text))',
            'x <- merge(merge(r("labels")[c("set_id", "product_name")], r("section_pairs"), '
            'by = "set_id"), txt("text_patient"), by.x = c("set_id", "kind"), '
            'by.y = c("set_id", "section"))',
            'x <- merge(x, txt("text_prescriber"), by.x = c("set_id", "best_section"), '
            'by.y = c("set_id", "section"), suffixes = c("_patient", "_prescriber"))',
        ]
    )


def python_lines(kaggle: bool = False) -> str:
    """Three lines of Python (pandas) that do the same join from the Parquet files."""
    path = f"{KAGGLE_INPUT}/current_{{t}}.parquet" if kaggle else "data/current/{t}.parquet"
    return "\n".join(
        [
            f'import pandas as pd; r = lambda t: pd.read_parquet(f"{path}"); '
            'txt = lambda t: r(t).query("part == \'text\'")[["set_id", "section", "text"]]',
            'x = r("labels")[["set_id", "product_name"]].merge(r("section_pairs"), on="set_id")'
            '.merge(txt("text_patient"), left_on=["set_id", "kind"], right_on=["set_id", '
            '"section"]).drop(columns="section")',
            'x = x.merge(txt("text_prescriber"), left_on=["set_id", "best_section"], '
            'right_on=["set_id", "section"], suffixes=("_patient", "_prescriber"))',
        ]
    )


def start_here_section(manifest: Mapping[str, Any], kaggle: bool = False) -> str:
    """The "Start here" section (Markdown, its heading included) for the card or, with
    ``kaggle``, for the Kaggle description (flat file names)."""
    facts = manifest.get("access") or {}
    s = manifest["sources"]
    book = XLSX_SAMPLE if facts.get("workbook") == "sample" else XLSX_WHOLE
    rows = facts.get("start_here_rows", 0)

    def at(path: str) -> str:
        if not kaggle:
            return path
        if path.startswith("data/"):
            conf, table = path.split("/")[1:3]
            stem, _, ext = table.partition(".")
            return f"{conf}_{stem}.{ext.removesuffix('.gz')}"
        return path

    gz = ".csv" if kaggle else ".csv.gz"
    lines = [
        "## Start here",
        f"Version {manifest['version']}, built from the openFDA drug label export of "
        f"{s['openfda_label_export']}. New versions come weekly on Hugging Face (0.2.1, 0.2.2, "
        "and so on) and monthly on the Kaggle mirror.",
        "",
        "**Which file.**",
        f"- **To look at the labels in a spreadsheet:** `{START_HERE}`: every `current` label "
        f"({rows:,} rows), one row per label, with its reading levels and listing flags and no "
        f"label text. The same rows in Excel: `{book}`, with a Read me sheet and a Fields "
        "sheet."
        + (
            f" The workbook holds a seeded sample of {SAMPLE_ROWS:,} rows; the CSV holds all."
            if book == XLSX_SAMPLE
            else ""
        ),
        f"- **To read pairs of texts side by side:** `{PAIRS_BOOK}`: a seeded sample of "
        f"{facts.get('pairs_rows', SAMPLE_ROWS):,} `current` section pairs, the patient segment "
        "next to the prescriber section, released text only.",
        f"- **For analysis:** the Parquet files (`{at('data/current/labels.parquet')}` and the "
        "rest), the full release. Parquet is a compressed file format for tables that keeps "
        "each column's type; R, Python and DuckDB read it directly. Every table also comes as a "
        + ("CSV" if kaggle else "gzipped CSV")
        + f" beside it (`{at('data/current/labels.csv.gz')}`).",
        f"- **What a column means:** `{FIELDS_FILE}` (every column of every table: its type, "
        f"meaning and allowed values). **The codes and the heading keys:** `{CODEBOOK_FILE}`.",
        "",
    ]
    gone = list(facts.get("csv_left_out") or [])
    if gone:
        lines += [
            "Left out as CSV on both hosts (each over 500 MB gzipped); read the Parquet file: "
            + ", ".join(f"`{at(g.replace('.csv.gz', '.parquet'))}`" for g in gone)
            + ".",
            "",
        ]
    k_gone = list(facts.get("kaggle_csv_left_out") or [])
    if kaggle and k_gone:
        lines += [
            "Left out as CSV on Kaggle (each over 500 MB unpacked): "
            + ", ".join(f"`{c}.csv`" for c in k_gone)
            + ". Their Parquet files are here, and their gzipped CSVs are on Hugging Face "
            "(https://huggingface.co/datasets/obadakr/plainpairs).",
            "",
        ]
    lines += [
        (
            f"On Kaggle the files are in `{KAGGLE_INPUT}/` (or use the Download button); each "
            "name is the configuration and the table (`current_labels.parquet`)."
            if kaggle
            else "Every file is on the Files and versions tab, or download them all with "
            "`hf download obadakr/plainpairs --repo-type dataset --local-dir plainpairs`."
        ),
        "",
        "**Opening the files.**",
        f"- **Excel:** open `{book}` or `{PAIRS_BOOK}`. For a CSV file, use Data > From "
        "Text/CSV and choose UTF-8 (a double-click can garble accented letters)"
        + ("." if kaggle else "; unzip a `.csv.gz` file first."),
        "- **SPSS:** File > Import Data > CSV Data, on a CSV file"
        + ("." if kaggle else " (unzip a `.csv.gz` file first)."),
        '- **Stata:** `import delimited using "labels.csv", varnames(1) encoding(utf-8) '
        "bindquote(strict)`"
        + ("" if kaggle else ", on an unzipped CSV file")
        + f". Stata renames columns it cannot use as they are (a dot, or more than 32 "
        f"characters); `{FIELDS_FILE}` gives every full name.",
        f'- **R:** `read.csv("{at("data/current/labels.csv.gz")}")` reads a '
        + ("CSV" if kaggle else "gzipped CSV as it is")
        + f'; `arrow::read_parquet("{at("data/current/labels.parquet")}")` reads a Parquet file.',
        f'- **Python:** `pandas.read_parquet("{at("data/current/labels.parquet")}")`, or '
        f'`pandas.read_csv("{at("data/current/labels.csv.gz")}")`.',
        "",
        "In the CSV files and the workbooks, 1 is yes and 0 is no, an empty cell has no value, a "
        "list's items are joined with \"; \", and a struct's fields are columns of their own "
        "(`t_medication_guide.flesch_kincaid`).",
        "",
        "**Joining a label with its section pairs and both texts** (`current`; the same for "
        "`unlisted`, never the two together). In R, from the CSV files:",
        "",
        "```r",
        r_lines(kaggle),
        "```",
        "",
        "In Python, from the Parquet files:",
        "",
        "```python",
        python_lines(kaggle),
        "```",
        "",
        "`x` has one row per section pair of a label whose texts are released: the label's "
        "product name, the pair's columns, the whole patient text (`text_patient`) and the text "
        "of the prescriber section it is paired with (`text_prescriber`, the pair's "
        "`best_section`). The segment itself is `with(x, substr(text_patient, seg_start + 1, "
        "seg_end))` in R and `[t[a:b] for t, a, b in zip(x.text_patient, x.seg_start, "
        "x.seg_end)]` in Python.",
    ]
    if gz == ".csv" and "current_text_prescriber" in k_gone:
        lines[-1] += (
            " On Kaggle the prescriber text has no CSV: read it in R with "
            '`arrow::read_parquet("' + KAGGLE_INPUT + '/current_text_prescriber.parquet")`.'
        )
    return "\n".join(lines)


def access_table(manifest: Mapping[str, Any]) -> str:
    """The card's table of the layer's files (path, rows, MB)."""
    rows = ["| file | rows | MB |", "|---|---:|---:|"]
    for f in manifest.get("access_files") or []:
        rows.append(f"| `{f['path']}` | {f['rows']:,} | {f['bytes'] / 1e6:,.1f} |")
    return "\n".join(rows)
