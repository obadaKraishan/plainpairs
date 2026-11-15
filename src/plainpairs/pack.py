"""The release pack: one folder per version, ready for Hugging Face, checked on its own.

**Layout.** Every table of every configuration is its own file and its own Hugging Face
configuration (``<configuration>_<table>``), with a single split, ``train``:

```
README.md           the dataset card (front matter: license and the configs)
LICENSES.md         what applies to each configuration
manifest.json       every file with its rows, size and SHA-256; sources; the switch
data/current/       labels, patient_texts, section_pairs, codes, text_prescriber, text_patient
data/unlisted/      the same tables (no measures from structure: they do not exist there)
data/nci/           summaries, pairs, text
data/excluded_otc/  labels typed over the counter (listed apart, out of scope)
```

The card names no default configuration, so ``load_dataset("obadakr/plainpairs")`` asks for one
and nothing ever loads ``current``, ``unlisted`` and ``nci`` as one pooled table; one table of
one configuration is one line: ``load_dataset("obadakr/plainpairs", "current_labels")``. The
tables of one configuration have different columns, so they cannot be splits of one config
(a config's splits share one schema).

**The switch**, applied as the files are written (see :data:`SWITCH`):

- label text: only rows of labels with no copyright mark (``unmarked``), less any label on the
  takedown list; the record rows of every label stay;
- the NCI configuration: its kept text, with the credit line on every row, less any page on the
  takedown list (blocks left out by the reader were never kept);
- codes: the trusted codes only.

:func:`check_pack` runs on the pack folder alone.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from plainpairs import codes, nci, release, tables

SWITCH = {"labels": "unmarked", "nci": "kept_text_with_credit"}
LABEL_CONFIGURATIONS = ("current", "unlisted")
LABEL_TABLES = (
    "labels",
    "patient_texts",
    "section_pairs",
    "codes",
    "text_prescriber",
    "text_patient",
)
TEXT_TABLES = ("text_prescriber", "text_patient")
NCI_TABLES = {"summaries": "nci_summaries", "pairs": "nci_pairs", "text": "nci_text"}
ALLOWED_FILES = {"README.md", "LICENSES.md", "manifest.json"}
CARD_TEMPLATE = "dataset_card.md"
LICENSES_TEMPLATE = "licenses_pack.md"
TAKEDOWN_FIELDS = ("kind", "id", "received", "reason")
#: The readable name of the NCI configuration, wherever a person reads it.
NCI_NAME = (
    "text from the National Cancer Institute's cancer information summaries, with parts left out"
)


class PackError(RuntimeError):
    """The build folder is not ready for a pack."""


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_takedowns(path: Path | None) -> dict[str, set[str]]:
    """The takedown list: set ids (``kind`` = ``set_id``) and NCI page addresses (``url``)."""
    out: dict[str, set[str]] = {"set_id": set(), "url": set()}
    if path is None or not Path(path).exists():
        return out
    with Path(path).open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != TAKEDOWN_FIELDS:
            raise PackError(
                f"{path} must have the columns {', '.join(TAKEDOWN_FIELDS)}; see docs/removal.md."
            )
        for row in reader:
            kind, ident = row["kind"].strip(), row["id"].strip()
            if kind not in out or not ident:
                raise PackError(f"{path}: a row with kind {kind!r} and id {ident!r} is not valid.")
            out[kind].add(ident.lower() if kind == "set_id" else ident)
    return out


def _structured_columns(schema: pa.Schema) -> list[str]:
    return [n for n in schema.names if n.endswith("_structured") or n.startswith("structured_")]


def _write(t: pa.Table, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(t, path, compression="zstd")
    return {"rows": t.num_rows, "bytes": path.stat().st_size, "sha256": _sha(path)}


def build_pack(
    tables_dir: Path,
    out_dir: Path,
    version: str,
    takedown_path: Path | None = None,
    today: Callable[[], str] = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"),
) -> dict[str, Any]:
    """Write the pack for ``version`` from the build in ``tables_dir``; returns the manifest."""
    src = Path(tables_dir)
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise PackError(f"{out} is not empty; give a new folder for the pack.")
    summary = json.loads((src / "build_summary.json").read_text(encoding="utf-8"))
    takedown = read_takedowns(takedown_path)
    labels = pq.read_table(src / "labels.parquet")
    conf_col = labels["configuration"].to_pylist()
    if any(c not in LABEL_CONFIGURATIONS for c in conf_col):
        raise PackError("Some labels have no configuration; build with --structure first.")
    config_of = dict(zip(labels["set_id"].to_pylist(), conf_col, strict=True))
    files: list[dict[str, Any]] = []
    held: dict[str, int] = {"label_text_rows_marked": 0, "label_text_rows_taken_down": 0}
    for conf in LABEL_CONFIGURATIONS:
        for name in LABEL_TABLES:
            path = src / f"{name}.parquet"
            if name == "codes" and not path.exists():
                raise PackError("No codes.parquet; run `plainpairs codes --structure ...` first.")
            t = pq.read_table(path)
            if name in TEXT_TABLES:
                ids = t["set_id"].to_pylist()
                mask = pa.array([config_of.get(i) == conf for i in ids])
                t = t.filter(mask)
                unmarked = release.select(t, SWITCH["labels"])
                held["label_text_rows_marked"] += t.num_rows - unmarked.num_rows
                gone = pc.is_in(
                    pc.utf8_lower(unmarked["set_id"]),
                    value_set=pa.array(sorted(takedown["set_id"]), pa.string()),
                )
                held["label_text_rows_taken_down"] += pc.sum(gone).as_py() or 0
                t = unmarked.filter(pc.invert(gone))
            else:
                t = t.filter(pc.equal(t["configuration"], conf))
                if name == "codes":
                    bad = [c for c in t.column_names if codes.STATUS.get(c) == "experimental"]
                    if bad:
                        raise PackError(f"codes.parquet holds experimental codes: {bad}")
                if conf == "unlisted":
                    t = t.drop_columns(_structured_columns(t.schema))
            rel = f"data/{conf}/{name}.parquet"
            files.append(
                {
                    "path": rel,
                    "config": f"{conf}_{name}",
                    "configuration": conf,
                    "table": name,
                    "layer": "text" if name in TEXT_TABLES else "record",
                    **_write(t, out / rel),
                }
            )
    ex = pq.read_table(src / "excluded_otc.parquet")
    files.append(
        {
            "path": "data/excluded_otc/excluded_otc.parquet",
            "config": "excluded_otc",
            "configuration": None,
            "table": "excluded_otc",
            "layer": "record",
            **_write(ex, out / "data/excluded_otc/excluded_otc.parquet"),
        }
    )
    nci_read = None
    held["nci_text_rows_taken_down"] = 0
    if (src / "nci_summaries.parquet").exists():
        for short, name in NCI_TABLES.items():
            t = pq.read_table(src / f"{name}.parquet")
            if short == "text":
                gone = pc.is_in(t["url"], value_set=pa.array(sorted(takedown["url"]), pa.string()))
                held["nci_text_rows_taken_down"] = pc.sum(gone).as_py() or 0
                t = t.filter(pc.invert(gone))
            if short == "summaries" and t.num_rows:
                nci_read = max(t["date_read"].to_pylist())
            rel = f"data/nci/{short}.parquet"
            files.append(
                {
                    "path": rel,
                    "config": f"nci_{short}",
                    "configuration": "nci",
                    "table": short,
                    "layer": "text" if short == "text" else "record",
                    **_write(t, out / rel),
                }
            )
    listed = summary.get("listed_sources", {})
    manifest = {
        "name": "PlainPairs",
        "version": version,
        "created": today(),
        "switch": SWITCH,
        "sources": {
            "openfda_label_export": summary["export_date"],
            "openfda_ndc_export": (listed.get("ndc") or {}).get("date"),
            "dailymed_list_read": (listed.get("dailymed") or {}).get("date"),
            "dailymed_release": (summary.get("structure") or {}).get("release_date"),
            "nci_pages_read": nci_read,
        },
        "code_version": codes.CODE_VERSION,
        "experimental_codes_left_out": list(codes.EXPERIMENTAL),
        "takedown_entries": {k: len(v) for k, v in takedown.items()},
        "held_back": held,
        "files": files,
        "rows": sum(f["rows"] for f in files),
        "bytes": sum(f["bytes"] for f in files),
    }
    manifest["facts"] = pack_facts(files, out)
    (out / "README.md").write_text(card(manifest), encoding="utf-8")
    (out / "LICENSES.md").write_text(_template(LICENSES_TEMPLATE, manifest), encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def pack_facts(files: list[dict[str, Any]], out: Path) -> dict[str, Any]:
    """Counts the card states, read from the files themselves."""
    by = {f["config"]: f for f in files}
    facts: dict[str, Any] = {k: by[k]["rows"] for k in by}
    for conf in LABEL_CONFIGURATIONS:
        facts[f"{conf}_megabytes"] = round(
            sum(f["bytes"] for f in files if f["configuration"] == conf) / 1e6, 1
        )
    facts["nci_megabytes"] = round(
        sum(f["bytes"] for f in files if f["configuration"] == "nci") / 1e6, 1
    )
    if "nci_summaries" in by:
        s = pq.read_table(out / by["nci_summaries"]["path"], columns=["language", "version"])
        for lang, ver in zip(s["language"].to_pylist(), s["version"].to_pylist(), strict=True):
            key = f"nci_{lang}_{ver}"
            facts[key] = facts.get(key, 0) + 1
    return facts


def _template(name: str, manifest: dict[str, Any]) -> str:
    raw = (Path(__file__).with_name(name)).read_text(encoding="utf-8")
    f = manifest["facts"]
    values = {
        "version": manifest["version"],
        "created": manifest["created"],
        "export": manifest["sources"]["openfda_label_export"],
        "ndc": manifest["sources"]["openfda_ndc_export"] or "",
        "dailymed_list": manifest["sources"]["dailymed_list_read"] or "",
        "dailymed_release": manifest["sources"]["dailymed_release"] or "",
        "nci_read": manifest["sources"]["nci_pages_read"] or "",
        "configs": _configs_yaml(manifest["files"]),
        "nci_name": NCI_NAME,
        "held_marked": f"{manifest['held_back']['label_text_rows_marked']:,}",
        "megabytes": f"{manifest['bytes'] / 1e6:,.1f}",
        "files_table": _files_table(manifest["files"]),
    }
    for k, v in f.items():
        values[f"n_{k}"] = f"{v:,}" if isinstance(v, int) else str(v)
    return Template(raw).safe_substitute(values)


def card(manifest: dict[str, Any]) -> str:
    """The dataset card (README.md) for the pack."""
    return _template(CARD_TEMPLATE, manifest)


def _configs_yaml(files: list[dict[str, Any]]) -> str:
    lines = []
    for f in files:
        lines += [
            f"- config_name: {f['config']}",
            "  data_files:",
            "  - split: train",
            f"    path: {f['path']}",
        ]
    return "\n".join(lines)


def _files_table(files: list[dict[str, Any]]) -> str:
    rows = ["| config | layer | rows | MB |", "|---|---|---:|---:|"]
    for f in files:
        rows.append(f"| `{f['config']}` | {f['layer']} | {f['rows']:,} | {f['bytes'] / 1e6:,.1f} |")
    return "\n".join(rows)


# --- the check, on the pack alone ------------------------------------------------------------

_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def card_problems(text: str, files: list[dict[str, Any]]) -> list[str]:
    """The card's front matter: license fields, and one config per data file, no default."""
    m = _FRONT.match(text)
    if not m:
        return ["README.md has no front matter."]
    front = m.group(1)
    problems = []
    if not re.search(r"^license: other$", front, re.M):
        problems.append("the card's license is not 'other'")
    link = re.search(r"^license_link: (\S+)$", front, re.M)
    if not link or not link.group(1).startswith("https://"):
        problems.append("the card's license_link is not a full https link")
    if not re.search(r"^license_name: \S+", front, re.M):
        problems.append("the card has no license_name")
    names = re.findall(r"^- config_name: (\S+)$", front, re.M)
    if names != [f["config"] for f in files]:
        problems.append("the card's configs do not match the manifest's files")
    if re.search(r"^\s+default: true", front, re.M):
        problems.append("the card names a default config")
    body = text[m.end() :]
    first = body[:2500].lower()
    if "not medical information" not in first:
        problems.append("the first screen of the card does not say it is not medical information")
    return problems


def check_pack(pack_dir: Path, takedown_path: Path | None = None) -> list[str]:
    """Every problem the pack folder has; empty when it may be uploaded. With a takedown list,
    also every text row of an entry on it."""
    root = Path(pack_dir)
    takedown = read_takedowns(takedown_path)
    problems: list[str] = []
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["No readable manifest.json in the pack."]
    files = manifest.get("files", [])
    listed = {f["path"] for f in files}
    on_disk = {
        p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
    } - ALLOWED_FILES
    for extra in sorted(on_disk - listed):
        problems.append(f"{extra} is in the pack but not in the manifest.")
    for missing in sorted(listed - on_disk):
        problems.append(f"{missing} is in the manifest but not in the pack.")
    for name in ALLOWED_FILES:
        if not (root / name).exists():
            problems.append(f"{name} is missing.")
    for f in files:
        p = root / f["path"]
        if not p.exists():
            continue
        if p.stat().st_size != f["bytes"] or _sha(p) != f["sha256"]:
            problems.append(f"{f['path']} does not match its size or SHA-256 in the manifest.")
            continue
        t = pq.read_table(p)
        if t.num_rows != f["rows"]:
            problems.append(f"{f['path']} has {t.num_rows} rows; the manifest says {f['rows']}.")
        problems += _check_file(f, t)
        if f["layer"] == "text" and t.num_rows:
            col, ids = ("url", takedown["url"]) if f["configuration"] == "nci" else (
                "set_id", takedown["set_id"])  # fmt: skip
            values = t[col].to_pylist()
            hits = sum(1 for v in values if (v.lower() if col == "set_id" else v) in ids)
            if hits:
                problems.append(f"{f['path']}: {hits} text rows of entries on the takedown list.")
    if (root / "README.md").exists():
        problems += card_problems((root / "README.md").read_text(encoding="utf-8"), files)
    return problems


def _check_file(f: dict[str, Any], t: pa.Table) -> list[str]:
    problems: list[str] = []
    conf, table, path = f["configuration"], f["table"], f["path"]
    if f["layer"] == "record" and "text" in t.column_names:
        problems.append(f"{path}: a record file has a text column.")
    if conf in LABEL_CONFIGURATIONS and "configuration" in t.column_names and t.num_rows:
        values = set(t["configuration"].to_pylist())
        if values != {conf}:
            problems.append(
                f"{path}: rows of {sorted(map(str, values))} in the {conf} files (pooled)."
            )
    if conf == "unlisted" and _structured_columns(t.schema):
        problems.append(f"{path}: measures from structure in the unlisted configuration (pooled).")
    if table == "codes":
        bad = [c for c in t.column_names if codes.STATUS.get(c) == "experimental"]
        if bad:
            problems.append(f"{path}: experimental codes {bad}.")
    if table in TEXT_TABLES and t.num_rows:
        marked = pc.sum(pc.or_(t["has_copyright_mark"], t["text_has_copyright_mark"])).as_py()
        if marked:
            problems.append(f"{path}: {marked} text rows of marked labels.")
    if conf == "current" and table == "labels":
        rows = t.select(
            ["structure_source", *[f"t_{k}_sha256" for k in tables.PATIENT],
             *[f"t_{k}_structured" for k in tables.PATIENT]]
        ).to_pylist()  # fmt: skip
        missing = sum(
            1
            for r in rows
            if r["structure_source"] != "dailymed_xml"
            or any(
                r[f"t_{k}_sha256"] and (r[f"t_{k}_structured"] or {}).get("sentences") is None
                for k in tables.PATIENT
            )
        )
        if missing:
            problems.append(f"{path}: {missing} current labels without structure.")
    if conf == "nci":
        col, url = ("credit_line_a", "url_a") if table == "pairs" else ("credit_line", "url")
        rows = t.select([col, url]).to_pylist()
        bad = sum(
            1
            for r in rows
            if not r[col]
            or "National Cancer Institute" not in r[col]
            or not r[col].endswith(r[url])
        )
        if bad:
            problems.append(f"{path}: {bad} rows without the NCI credit line.")
        if table == "text":
            kinds = set(t["kind"].to_pylist()) - {"heading", *nci.PROSE_KINDS, "data_cell"}
            credit = sum(1 for s in t["text"].to_pylist() if nci.CREDIT_LINE.search(s))
            if kinds or credit:
                problems.append(
                    f"{path}: left-out blocks in the NCI text ({sorted(kinds)}, {credit})."
                )
    return problems


# --- the Kaggle mirror -----------------------------------------------------------------------

KAGGLE_ID = "obadakraishan/plainpairs"


def build_kaggle(pack_dir: Path, out_dir: Path) -> dict[str, Any]:
    """The Kaggle mirror: the same files as the pack (flat names), the card and the licenses."""
    pack_dir, out_dir = Path(pack_dir), Path(out_dir)
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    resources = []
    for f in manifest["files"]:
        flat = f"{f['config']}.parquet"
        shutil.copyfile(pack_dir / f["path"], out_dir / flat)
        resources.append({"path": flat, "description": f"{f['config']} ({f['layer']} layer)"})
    for name in ("LICENSES.md", "manifest.json"):
        shutil.copyfile(pack_dir / name, out_dir / name)
    meta = {
        "title": "PlainPairs: prescriber and patient texts of US medicine labels",
        "subtitle": "A research record of wording, not medical information",
        "id": KAGGLE_ID,
        "licenses": [{"name": "other"}],
        "keywords": ["health", "nlp", "text"],
        "description": (
            f"Version {manifest['version']} of PlainPairs, mirrored from Hugging Face "
            "(https://huggingface.co/datasets/obadakr/plainpairs). Not medical information: a "
            "research record of how label text is worded; labels may be out of date; never use "
            "it to decide about a medicine. Three configurations, never pooled: current, "
            f"unlisted and nci ({NCI_NAME}). The terms for each are in LICENSES.md."
        ),
        "resources": resources,
    }
    (out_dir / "dataset-metadata.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def check_kaggle(out_dir: Path, pack_dir: Path) -> list[str]:
    """The Kaggle folder holds exactly the pack's files, byte for byte, and the metadata."""
    out_dir, pack_dir = Path(out_dir), Path(pack_dir)
    problems = []
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    want = {f"{f['config']}.parquet": f["sha256"] for f in manifest["files"]}
    have = {p.name for p in out_dir.iterdir() if p.is_file()} - {
        "dataset-metadata.json",
        "LICENSES.md",
        "manifest.json",
    }
    if have != set(want):
        problems.append("the Kaggle folder's files differ from the pack's.")
    for name, sha in want.items():
        p = out_dir / name
        if p.exists() and _sha(p) != sha:
            problems.append(f"{name} differs from the pack.")
    meta = json.loads((out_dir / "dataset-metadata.json").read_text(encoding="utf-8"))
    if (
        meta.get("id") != KAGGLE_ID
        or "not medical information" not in meta.get("description", "").lower()
    ):
        problems.append("the Kaggle metadata lacks its id or the not-medical-information line.")
    return problems
