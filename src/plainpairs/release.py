"""The release check, the text switch, and the rebuild of the text layer.

**The switch** decides which rows of the text layer a release may carry:

- ``all``: every text row (a marked text is released only with ``allow_marked``);
- ``unmarked``: only rows of labels whose text shows no copyright mark;
- ``none``: no text; the record layer alone.

**The release check** (:func:`check`) returns every problem it finds, and a release goes ahead
only with none: counts that differ from the manifest; a record-layer table with a text column or
a long string; a text row without its mark flag; a switch setting that would release a marked
text; a duplicated id; a label out of scope; a row without its source, export date or set id;
a text whose hash does not match.

**The rebuild** (:func:`rebuild_text`) makes the text layer again from the record layer and the
source's own bulk files of the same export date, and confirms every row by its SHA-256.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from plainpairs import bulk, label, tables

SWITCH = ("all", "unmarked", "none")
#: The longest string a record-layer cell may hold (heading templates are the longest kind).
MAX_RECORD_STRING = 300
#: Columns that come from the source's openfda block (names and codes, not label text). A
#: product with many components has a long list of generic names, so these may be longer.
OPENFDA_COLUMNS = frozenset(
    {
        "medicine_key",
        "medicine_keys",
        "generic_names",
        "brand_names",
        "manufacturers",
        "pharm_classes_epc",
        "routes",
        "application_numbers",
        "product_type",
    }
)
MAX_OPENFDA_STRING = 2000
_KEYS = {
    "labels": ("set_id",),
    "patient_texts": ("patient_text_id",),
    "section_pairs": ("set_id", "kind", "segment_index"),
    "excluded_otc": ("set_id",),
    "text_prescriber": ("set_id", "section", "part", "part_index"),
    "text_patient": ("set_id", "section", "part", "part_index"),
}


def select(text_table: pa.Table, switch: str, allow_marked: bool = False) -> pa.Table:
    """The rows of one text table that a release with ``switch`` would carry."""
    if switch not in SWITCH:
        raise ValueError(f"Unknown switch {switch!r}; use one of {SWITCH}.")
    if switch == "none":
        return text_table.slice(0, 0)
    if switch == "unmarked":
        mask = pc.and_(
            pc.equal(text_table["has_copyright_mark"], False),
            pc.equal(text_table["text_has_copyright_mark"], False),
        )
        return text_table.filter(mask)
    if not allow_marked and pc.any(text_table["has_copyright_mark"]).as_py():
        raise ValueError("The switch 'all' would release marked texts; pass allow_marked to do so.")
    return text_table


def _max_len(col: pa.ChunkedArray) -> int:
    if pa.types.is_list(col.type):
        col = pc.list_flatten(col)
    if not pa.types.is_string(col.type) or len(col) == 0:
        return 0
    lengths = pc.utf8_length(col)
    m = pc.max(lengths).as_py()
    return int(m or 0)


def _strings(table: pa.Table) -> dict[str, int]:
    out = {}
    for name in table.column_names:
        col = table[name]
        if pa.types.is_struct(col.type):
            continue
        n = _max_len(col)
        if n:
            out[name] = n
    return out


def check(
    out_dir: Path,
    manifest: dict[str, dict[str, str]],
    switch: str,
    allow_marked: bool = False,
    verify_hashes: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    """Every problem a release of ``out_dir`` with ``switch`` would have, and what it holds."""
    problems: list[str] = []
    info: dict[str, Any] = {"switch": switch}
    summary = json.loads((Path(out_dir) / "build_summary.json").read_text(encoding="utf-8"))
    dates = {r["export_date"] for r in manifest.values()}
    listed = sum(int(r["listed_records"]) for r in manifest.values())
    if dates != {summary["export_date"]}:
        problems.append(
            f"The build is of {summary['export_date']}, the manifest of {sorted(dates)}."
        )
    if summary["counts"].get("labels_read") != listed:
        read = summary["counts"].get("labels_read")
        problems.append(f"The build read {read} labels; the manifest lists {listed}.")
    loaded = {name: pq.read_table(Path(out_dir) / f"{name}.parquet") for name in tables.SCHEMAS}
    for name, t in loaded.items():
        info[f"rows:{name}"] = t.num_rows
        if summary.get("rows", {}).get(name) != t.num_rows:
            problems.append(
                f"{name} has {t.num_rows} rows; the build summary says {summary['rows'].get(name)}."
            )
        if t.schema.names != tables.SCHEMAS[name].names:
            problems.append(f"{name} does not have the expected columns.")
        for col in ("source", "export_date", "set_id"):
            if col in t.column_names and t[col].null_count:
                problems.append(f"{name}: {t[col].null_count} rows have no {col}.")
        if "export_date" in t.column_names and t.num_rows:
            values = set(pc.unique(t["export_date"]).to_pylist())
            if values != {summary["export_date"]}:
                problems.append(f"{name} holds rows of other export dates: {sorted(values)}.")
        keys = _KEYS[name]
        if t.num_rows:
            grouped = t.group_by(list(keys)).aggregate([([], "count_all")])
            dupes = pc.sum(pc.greater(grouped["count_all"], 1)).as_py() or 0
            if dupes:
                problems.append(f"{name}: {dupes} ids ({', '.join(keys)}) appear more than once.")
    for name in tables.RECORD_TABLES:
        t = loaded[name]
        if "text" in t.column_names:
            problems.append(f"The record table {name} has a text column.")
        for col, n in _strings(t).items():
            limit = MAX_OPENFDA_STRING if col in OPENFDA_COLUMNS else MAX_RECORD_STRING
            if n > limit:
                problems.append(
                    f"The record table {name} holds strings of {n} characters in {col}."
                )
    codes_path = Path(out_dir) / "codes.parquet"
    if codes_path.exists():
        problems += _check_codes(pq.read_table(codes_path), loaded["labels"])
        info["rows:codes"] = pq.ParquetFile(codes_path).metadata.num_rows
    labels = loaded["labels"]
    if labels.num_rows:
        fmt_ok = pc.is_in(labels["label_format"], value_set=pa.array(tables.IN_SCOPE_FORMATS))
        pair_ok = pc.or_(labels["has_medication_guide"], labels["has_patient_package_insert"])
        not_otc = pc.fill_null(pc.not_equal(labels["product_type"], tables.OTC), True)
        ok = pc.and_(pc.and_(fmt_ok, pair_ok), not_otc)
        out = labels.num_rows - (pc.sum(ok).as_py() or 0)
        if out:
            problems.append(f"{out} labels in the labels table are out of scope.")
    for name in tables.TEXT_TABLES:
        t = loaded[name]
        for flag in ("has_copyright_mark", "text_has_copyright_mark"):
            if t[flag].null_count:
                problems.append(f"{t[flag].null_count} rows of {name} have no {flag}.")
        try:
            chosen = select(t, switch, allow_marked)
        except ValueError as exc:
            problems.append(f"{name}: {exc}")
            chosen = t.slice(0, 0)
        if switch == "unmarked" and (pc.any(chosen["has_copyright_mark"]).as_py() or False):
            problems.append(
                f"{name}: the unmarked setting would release a marked text."
            )  # pragma: no cover
        info[f"release:{name}"] = chosen.num_rows
        info[f"marked:{name}"] = pc.sum(t["has_copyright_mark"]).as_py() or 0
        if verify_hashes and t.num_rows:
            bad = 0
            pf = pq.ParquetFile(Path(out_dir) / f"{name}.parquet")
            for batch in pf.iter_batches(batch_size=20_000, columns=["text", "sha256"]):
                for text, sha in zip(
                    batch["text"].to_pylist(), batch["sha256"].to_pylist(), strict=True
                ):
                    bad += hashlib.sha256(text.encode("utf-8")).hexdigest() != sha
            if bad:
                problems.append(f"{name}: {bad} rows whose text does not match its SHA-256.")
    if verify_hashes:
        problems += _cross_hashes(labels, loaded["text_prescriber"], loaded["text_patient"])
    return problems, info


def _check_codes(t: pa.Table, labels: pa.Table) -> list[str]:
    """The codes table (optional): counts only, every label in scope, one row per text."""
    from plainpairs import codes

    problems = []
    if t.schema.names != codes.SCHEMA.names:
        problems.append("codes does not have the expected columns; run `plainpairs codes` again.")
        return problems
    for col, n in _strings(t).items():
        if n > MAX_RECORD_STRING:
            problems.append(f"The record table codes holds strings of {n} characters in {col}.")
    if t.num_rows:
        grouped = t.group_by(["set_id", "version", "section"]).aggregate([([], "count_all")])
        dupes = pc.sum(pc.greater(grouped["count_all"], 1)).as_py() or 0
        if dupes:
            problems.append(f"codes: {dupes} texts appear more than once.")
        known = pc.is_in(t["set_id"], value_set=labels["set_id"])
        out = t.num_rows - (pc.sum(known).as_py() or 0)
        if out:
            problems.append(f"codes: {out} rows are for labels not in the labels table.")
    return problems


def _cross_hashes(labels: pa.Table, prescriber: pa.Table, patient: pa.Table) -> list[str]:
    """Every text row's hash is the one the labels table records for it."""
    expected: dict[tuple[str, str], str] = {}
    tables_expected: dict[str, list[str]] = {}
    for r in labels.to_pylist():
        for s in tables.PRESCRIBER:
            if r[f"p_{s}_sha256"]:
                expected[(r["set_id"], s)] = r[f"p_{s}_sha256"]
        for k in tables.PATIENT:
            if r[f"t_{k}_sha256"]:
                expected[(r["set_id"], k)] = r[f"t_{k}_sha256"]
        tables_expected[r["set_id"]] = r["tables_sha256"] or []
    found: dict[tuple[str, str], str] = {}
    tables_found: dict[str, list[str]] = {}
    for t in (prescriber, patient):
        cols = t.select(["set_id", "section", "part", "sha256"]).to_pylist()
        for r in cols:
            if r["part"] == "text":
                found[(r["set_id"], r["section"])] = r["sha256"]
            else:
                tables_found.setdefault(r["set_id"], []).append(r["sha256"])
    problems = []
    if found != expected:
        problems.append(
            f"{len(set(found.items()) ^ set(expected.items()))} text hashes differ between the "
            "labels table and the text layer."
        )
    mismatched = sum(
        1
        for sid, shas in tables_expected.items()
        if Counter(shas) != Counter(tables_found.get(sid, []))
    )
    if mismatched:
        problems.append(f"{mismatched} labels have table rows that do not match tables_sha256.")
    return problems


def rebuild_text(labels_path: Path, bulk_root: Path, out_dir: Path, log=print) -> dict[str, Any]:
    """Rebuild the text layer from the record layer and the bulk files; confirm by hash."""
    labels = pq.read_table(labels_path).to_pylist()
    if not labels:
        raise ValueError(f"{labels_path} holds no labels.")
    export_date = labels[0]["export_date"]
    by_id = {r["set_id"]: r for r in labels}
    parts = tables.parts_from_manifest(bulk_root, export_date)
    out_dir.mkdir(parents=True, exist_ok=True)
    writers = {
        name: pq.ParquetWriter(out_dir / f"{name}.parquet", tables.TEXT_SCHEMA, compression="zstd")
        for name in tables.TEXT_TABLES
    }
    seen: set[str] = set()
    mismatches = 0
    try:
        for number, path in parts:
            buf: dict[str, list[dict[str, Any]]] = {name: [] for name in tables.TEXT_TABLES}
            for record in bulk.iter_labels(path):
                rec = by_id.get(record.get("set_id"))
                if rec is None or str(record.get("version")) != str(rec["version"]):
                    continue
                row = label.parse_label(record)
                base = {k: rec[k] for k in ("source", "export_date", "set_id", "version")}
                plain = tables._tables_by_section(row)
                shas: list[str] = []
                for s in tables.PRESCRIBER:
                    t = getattr(row.prescriber, s)
                    if (tables.sha256_text(t) if t else None) != rec[f"p_{s}_sha256"]:
                        mismatches += 1
                    if t:
                        tables.Builder._text_rows(
                            buf["text_prescriber"],
                            base,
                            s,
                            t,
                            plain.get(s, []),
                            rec["has_copyright_mark"],
                        )
                        shas += [tables.sha256_text(x) for x in plain.get(s, [])]
                for k in tables.PATIENT:
                    t = getattr(row.patient, k)
                    if (tables.sha256_text(t) if t else None) != rec[f"t_{k}_sha256"]:
                        mismatches += 1
                    if t:
                        tables.Builder._text_rows(
                            buf["text_patient"],
                            base,
                            k,
                            t,
                            plain.get(k, []),
                            rec["has_copyright_mark"],
                        )
                        shas += [tables.sha256_text(x) for x in plain.get(k, [])]
                if Counter(shas) != Counter(rec["tables_sha256"] or []):
                    mismatches += 1
                seen.add(rec["set_id"])
            for name in tables.TEXT_TABLES:
                if buf[name]:
                    writers[name].write_table(pa.Table.from_pylist(buf[name], tables.TEXT_SCHEMA))
            log(f"rebuild: part {number} read; {len(seen):,} of {len(by_id):,} labels rebuilt")
    finally:
        for w in writers.values():
            w.close()
    return {
        "export_date": export_date,
        "labels": len(by_id),
        "rebuilt": len(seen),
        "missing": len(by_id) - len(seen),
        "hash_mismatches": mismatches,
    }
