"""What changed between two exports: a ``changes`` table from two builds' record layers.

Every label (by set id) that differs between the older and the newer build gets one row:

- ``new_label``: in the newer build only;
- ``gone``: in the older build only. With the newer export's list of every set id
  (``export_ids.parquet``, written by the build) it is told apart as ``left_scope`` (still in
  the export, no longer in scope) or ``withdrawn`` (no longer in the export at all). A release
  keeps such labels and flags them; nothing is deleted;
- ``new_version_same_texts``: a new version whose texts all hash the same;
- ``texts_changed``: one or more texts changed (listed in ``sections_changed``), with or
  without a new version;
- ``record_only``: the same version and texts, but the openfda block, the format, the
  copyright mark or a listed-now flag changed.

Columns name the sections whose text changed and the patient texts added or dropped, and flag
each change of block, format, mark and listing. The table holds ids, versions, section names
and booleans only, never text.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from plainpairs.schema import PATIENT_SOURCES, PRESCRIBER_SOURCES

PRESCRIBER = tuple(PRESCRIBER_SOURCES)
PATIENT = tuple(PATIENT_SOURCES)
HASH_COLUMNS = [f"p_{s}_sha256" for s in PRESCRIBER] + [f"t_{k}_sha256" for k in PATIENT]
RECORD_COLUMNS = {
    "harmonized": "block_changed",
    "label_format": "format_changed",
    "has_copyright_mark": "mark_changed",
    "listed_in_ndc_directory": "ndc_listing_changed",
    "served_by_dailymed": "dailymed_listing_changed",
}
CHANGES = (
    "new_label",
    "gone",
    "left_scope",
    "withdrawn",
    "new_version_same_texts",
    "texts_changed",
    "record_only",
)
STR_LIST = pa.list_(pa.string())
SCHEMA = pa.schema(
    [
        ("old_export_date", pa.string()),
        ("new_export_date", pa.string()),
        ("set_id", pa.string()),
        ("change", pa.string()),
        ("old_version", pa.int32()),
        ("new_version", pa.int32()),
        ("sections_changed", STR_LIST),
        ("patient_texts_added", STR_LIST),
        ("patient_texts_dropped", STR_LIST),
        *[(flag, pa.bool_()) for flag in RECORD_COLUMNS.values()],
    ]
)
EXPORT_IDS = "export_ids.parquet"


def _labels(folder: Path) -> tuple[str, dict[str, dict[str, Any]]]:
    path = Path(folder) / "labels.parquet"
    names = pq.read_schema(path).names
    cols = ["export_date", "set_id", "version", *HASH_COLUMNS, *RECORD_COLUMNS]
    t = pq.read_table(path, columns=[c for c in cols if c in names])
    rows = {r["set_id"]: r for r in t.to_pylist()}
    dates = {r["export_date"] for r in rows.values()}
    if len(dates) > 1:
        raise ValueError(f"{path} holds more than one export date: {sorted(dates)}.")
    return (dates.pop() if dates else ""), rows


def _section(column: str) -> str:
    return column[2:-7]  # p_<section>_sha256 / t_<kind>_sha256


def compare_rows(
    old: dict[str, dict[str, Any]],
    new: dict[str, dict[str, Any]],
    new_export_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """One row per set id that differs (without the export dates)."""
    out = []
    for set_id in sorted(old.keys() | new.keys()):
        a, b = old.get(set_id), new.get(set_id)
        row: dict[str, Any] = {
            "set_id": set_id,
            "old_version": a["version"] if a else None,
            "new_version": b["version"] if b else None,
            "sections_changed": [],
            "patient_texts_added": [],
            "patient_texts_dropped": [],
            **dict.fromkeys(RECORD_COLUMNS.values()),
        }
        if a is None or b is None:
            if b is not None:
                row["change"] = "new_label"
            elif new_export_ids is None:
                row["change"] = "gone"
            else:
                row["change"] = "left_scope" if set_id in new_export_ids else "withdrawn"
            out.append(row)
            continue
        for col in HASH_COLUMNS:
            x, y = a.get(col), b.get(col)
            if x == y:
                continue
            row["sections_changed"].append(_section(col))
            if col.startswith("t_") and x is None:
                row["patient_texts_added"].append(_section(col))
            elif col.startswith("t_") and y is None:
                row["patient_texts_dropped"].append(_section(col))
        for col, flag in RECORD_COLUMNS.items():
            if col in a and col in b:
                row[flag] = a[col] != b[col]
        record_changed = any(row[f] for f in RECORD_COLUMNS.values())
        if row["sections_changed"]:
            row["change"] = "texts_changed"
        elif a["version"] != b["version"]:
            row["change"] = "new_version_same_texts"
        elif record_changed:
            row["change"] = "record_only"
        else:
            continue
        out.append(row)
    return out


def compare(old_dir: Path, new_dir: Path) -> tuple[pa.Table, dict[str, Any]]:
    """The changes table between two builds, and its counts."""
    old_date, old = _labels(old_dir)
    new_date, new = _labels(new_dir)
    ids_path = Path(new_dir) / EXPORT_IDS
    export_ids = (
        set(pq.read_table(ids_path, columns=["set_id"])["set_id"].to_pylist())
        if ids_path.exists()
        else None
    )
    rows = compare_rows(old, new, export_ids)
    for r in rows:
        r["old_export_date"], r["new_export_date"] = old_date, new_date
    table = pa.Table.from_pylist(rows, SCHEMA)
    by_change = Counter(r["change"] for r in rows)
    by_section = Counter(s for r in rows for s in r["sections_changed"])
    summary = {
        "old_export_date": old_date,
        "new_export_date": new_date,
        "old_labels": len(old),
        "new_labels": len(new),
        "unchanged": len(old.keys() & new.keys())
        - sum(by_change[c] for c in ("new_version_same_texts", "texts_changed", "record_only")),
        "changes": {c: by_change.get(c, 0) for c in CHANGES},
        "sections_changed": dict(sorted(by_section.items())),
        "patient_texts_added": sum(len(r["patient_texts_added"]) for r in rows),
        "patient_texts_dropped": sum(len(r["patient_texts_dropped"]) for r in rows),
        "flags": {f: sum(bool(r[f]) for r in rows) for f in RECORD_COLUMNS.values()},
        "export_ids_known": export_ids is not None,
    }
    summary.update(_distinct_texts(old_dir, new_dir))
    return table, summary


def _distinct_texts(old_dir: Path, new_dir: Path) -> dict[str, int]:
    """Distinct patient texts (by core hash) that are new, or no longer carried by any label."""
    out: dict[str, int] = {}
    paths = [Path(d) / "patient_texts.parquet" for d in (old_dir, new_dir)]
    if not all(p.exists() for p in paths):
        return out
    old, new = (set(pq.read_table(p, columns=["patient_text_id"])[0].to_pylist()) for p in paths)
    out["distinct_patient_texts_new"] = len(new - old)
    out["distinct_patient_texts_gone"] = len(old - new)
    return out


def write(old_dir: Path, new_dir: Path, out_path: Path) -> dict[str, Any]:
    table, summary = compare(old_dir, new_dir)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out_path, compression="zstd")
    summary["rows"] = table.num_rows
    return summary
