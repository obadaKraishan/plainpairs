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

from plainpairs import access, codes, nci, release, tables

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
#: The dataset's title and address, as the card, the Kaggle mirror and CITATION.cff cite it.
TITLE = (
    "PlainPairs: a research corpus pairing the prescriber and patient texts of US medicine labels"
)
HF_URL = "https://huggingface.co/datasets/obadakr/plainpairs"
#: The Zenodo DOI of the software and documents, all versions (it resolves to the latest).
SOFTWARE_DOI = "10.5281/zenodo.24267450"
#: The data paper that describes PlainPairs, as arXiv gives it. Every card, the Kaggle
#: description and the repository cite it first, before the dataset's version.
PAPER_ARXIV_ID = "2611.21160"
PAPER_TITLE = (
    "PlainPairs: A Corpus Pairing the Prescriber and Patient Texts of U.S. Prescription "
    "Medicine Labels"
)
PAPER_YEAR = "2026"
PAPER_CLASS = "cs.CL"
PAPER_URL = f"https://arxiv.org/abs/{PAPER_ARXIV_ID}"
PAPER_DOI = f"10.48550/arXiv.{PAPER_ARXIV_ID}"
#: The card's reading-level table as version 0.1.0 printed it (its manifest has no computed
#: table); every later version computes its own from its files (:func:`reading_levels`).
READING_LEVELS_0_1_0 = (
    "| | Flesch-Kincaid (median) | SMOG (median) | above grade 8, FK / SMOG |\n"
    "|---|---:|---:|---:|\n"
    "| Medication Guides, `current`, from structure | 8.67 | 11.10 | 71.9% / 99.2% |\n"
    "| the same guides, from the JSON | 10.86 | 12.94 | 95.0% / 99.5% |\n"
    "| Medication Guides, `unlisted`, from the JSON | 10.70 | 12.85 | 93.1% / 99.5% |\n"
    "| patient package inserts, `current`, from structure | 8.58 | 11.21 | 66.9% / 99.5% |\n"
    "| NCI patient summaries (English) | 8.65 | 11.11 | 83% / 100% |\n"
    "| NCI health-professional summaries (English) | 13.49 | 15.08 | 100% / 100% |"
)
#: The rows of that table: label, configuration, which texts, which measures.
READING_ROWS = (
    (
        "Medication Guides, `current`, from structure",
        "current",
        "medication_guide",
        "measures_structured",
    ),
    ("the same guides, from the JSON", "current", "medication_guide", "measures"),
    ("Medication Guides, `unlisted`, from the JSON", "unlisted", "medication_guide", "measures"),
    (
        "patient package inserts, `current`, from structure",
        "current",
        "patient_package_insert",
        "measures_structured",
    ),
    ("NCI patient summaries (English)", "nci", "patient", "measures"),
    ("NCI health-professional summaries (English)", "nci", "health_professional", "measures"),
)
#: Hugging Face's size categories by number of rows: (exclusive upper bound, category).
SIZE_CATEGORIES = (
    (1_000, "n<1K"),
    (10_000, "1K<n<10K"),
    (100_000, "10K<n<100K"),
    (1_000_000, "100K<n<1M"),
    (10_000_000, "1M<n<10M"),
    (100_000_000, "10M<n<100M"),
    (1_000_000_000, "100M<n<1B"),
    (10_000_000_000, "1B<n<10B"),
    (100_000_000_000, "10B<n<100B"),
    (1_000_000_000_000, "100B<n<1T"),
)


def size_category(rows: int) -> str:
    """Hugging Face's ``size_categories`` value for a dataset of ``rows`` rows in all."""
    for bound, name in SIZE_CATEGORIES:
        if rows < bound:
            return name
    return "n>1T"


def citation(version: str, created: str) -> str:
    """How to cite one version; the year is the year the version was built."""
    return (
        f"Kraishan, O. ({created[:4]}). {TITLE} (Version {version}) [Data set]. "
        f"Hugging Face. {HF_URL}"
    )


def paper_citation() -> str:
    """How to cite the paper that describes PlainPairs: first, before the dataset's version."""
    return (
        f"Kraishan, O. ({PAPER_YEAR}). {PAPER_TITLE}. arXiv:{PAPER_ARXIV_ID}. {PAPER_URL} "
        f"(doi:{PAPER_DOI})"
    )


def paper_bibtex() -> str:
    """The paper's BibTeX entry, with arXiv's fields (for a code block)."""
    title = PAPER_TITLE.replace("PlainPairs", "{PlainPairs}").replace("U.S.", "{U.S.}")
    return "\n".join(
        [
            f"@misc{{kraishan{PAPER_YEAR}plainpairs,",
            "  author        = {Kraishan, Obada},",
            f"  title         = {{{title}}},",
            f"  year          = {{{PAPER_YEAR}}},",
            f"  eprint        = {{{PAPER_ARXIV_ID}}},",
            "  archivePrefix = {arXiv},",
            f"  primaryClass  = {{{PAPER_CLASS}}},",
            f"  doi           = {{{PAPER_DOI}}},",
            f"  url           = {{{PAPER_URL}}}",
            "}",
        ]
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
    manifest["access_files"], manifest["access"] = access.build(out, manifest)
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
    facts["reading_levels"] = reading_levels(files, out)
    return facts


def reading_levels(files: list[dict[str, Any]], out: Path) -> list[list[Any]]:
    """The card's reading-level table from the pack's own files: per row, the median
    Flesch-Kincaid and SMOG grades over distinct texts (or NCI pages) and the shares above
    grade 8, with the number of texts measured."""
    from statistics import median

    by = {f["config"]: f for f in files}
    rows = []
    for label, conf, which, column in READING_ROWS:
        if conf == "nci":
            f = by.get("nci_summaries")
            t = (
                pq.read_table(out / f["path"], columns=["language", "version", column])
                if f
                else None
            )
            picked = [
                r[column]
                for r in (t.to_pylist() if t is not None else [])
                if r["language"] == "en" and r["version"] == which
            ]
        else:
            f = by.get(f"{conf}_patient_texts")
            t = pq.read_table(out / f["path"], columns=["kind", column]) if f else None
            picked = [
                r[column] for r in (t.to_pylist() if t is not None else []) if r["kind"] == which
            ]
        fk = [m["flesch_kincaid"] for m in picked if m and m.get("flesch_kincaid") is not None]
        sm = [m["smog"] for m in picked if m and m.get("smog") is not None]
        rows.append(
            [
                label,
                conf,
                round(median(fk), 2) if fk else None,
                round(median(sm), 2) if sm else None,
                sum(x > 8 for x in fk) / len(fk) if fk else None,
                sum(x > 8 for x in sm) / len(sm) if sm else None,
                len(fk),
            ]
        )
    return rows


def reading_table(rows: list[list[Any]] | None) -> str:
    """The card's reading-level table (0.1.0's own text when the manifest has no rows)."""
    if not rows:
        return READING_LEVELS_0_1_0
    out = [
        "| | Flesch-Kincaid (median) | SMOG (median) | above grade 8, FK / SMOG |",
        "|---|---:|---:|---:|",
    ]
    for label, conf, fk, smog, above_fk, above_smog, _n in rows:
        num = ["none" if v is None else f"{v:.2f}" for v in (fk, smog)]
        pct = [
            "none" if v is None else (f"{v:.0%}" if conf == "nci" else f"{v:.1%}")
            for v in (above_fk, above_smog)
        ]
        out.append(f"| {label} | {num[0]} | {num[1]} | {pct[0]} / {pct[1]} |")
    return "\n".join(out)


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
        "size_category": size_category(manifest["rows"]),
        "citation": citation(manifest["version"], manifest["created"]),
        "paper_citation": paper_citation(),
        "paper_bibtex": paper_bibtex(),
        "software_doi": SOFTWARE_DOI,
        "nci_name": NCI_NAME,
        "held_marked": f"{manifest['held_back']['label_text_rows_marked']:,}",
        "megabytes": f"{manifest['bytes'] / 1e6:,.1f}",
        "files_table": _files_table(manifest["files"]),
        "intro": (
            access.start_here_section(manifest)
            if manifest.get("access_files")
            else f"Version {manifest['version']}, built from the openFDA drug label export of "
            f"{manifest['sources']['openfda_label_export']}."
        ),
        "reading_levels": reading_table(f.get("reading_levels")),
        "access_table": (
            "\n\nThe easy-access files (see Start here): a CSV, two workbooks and two catalogues "
            "at the top, and a gzipped CSV beside each Parquet file.\n\n"
            + access.access_table(manifest)
            if manifest.get("access_files")
            else ""
        ),
    }
    for k, v in f.items():
        if isinstance(v, (int, str)):
            values[f"n_{k}"] = f"{v:,}" if isinstance(v, int) else v
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
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"(`+)(?:(?!\n[ \t]*\n).)+?\1", re.S)
_RAW_TAG = re.compile(
    r"<(?![A-Za-z][A-Za-z0-9+.-]*:)/?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>|<!--|<\?|<![A-Za-z]"
)


def raw_tags(text: str) -> list[tuple[int, str]]:
    """What a Markdown renderer would read as raw HTML, outside code: (line, tag) pairs.

    The Hub renders a card's raw HTML, so a placeholder written as ``<title>`` opens an element
    that hides the rest of the card. Code spans, fenced code and autolinks
    (``<https://...>``) are fine; the front matter is not Markdown and is skipped."""
    m = _FRONT.match(text)
    start = m.end() if m else 0
    kept, fence = [], ""
    for line in text[start:].split("\n"):
        f = _FENCE.match(line)
        if fence:
            if f and f.group(1)[0] == fence[0] and len(f.group(1)) >= len(fence):
                fence = ""
            kept.append("")
        elif f:
            fence = f.group(1)
            kept.append("")
        else:
            kept.append(line)
    body = _CODE_SPAN.sub(lambda s: re.sub(r"[^\n]", " ", s.group(0)), "\n".join(kept))
    before = text[:start].count("\n")
    return [
        (before + body.count("\n", 0, tag.start()) + 1, tag.group(0))
        for tag in _RAW_TAG.finditer(body)
    ]


def tag_problems(name: str, text: str) -> list[str]:
    """One problem per raw tag in ``text`` (see ``raw_tags``)."""
    return [
        f"{name} line {line}: {tag!r} is read as an HTML tag on Hugging Face and hides the text "
        "after it; write it in words or in backticks."
        for line, tag in raw_tags(text)
    ]


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
    want = size_category(sum(f["rows"] for f in files))
    if re.findall(r"^size_categories:\n- (\S+)$", front, re.M) != [want]:
        problems.append(f"the card's size_categories is not {want}, the files' row count")
    body = text[m.end() :]
    first = body[:2500].lower()
    if "not medical information" not in first:
        problems.append("the first screen of the card does not say it is not medical information")
    if any(f["configuration"] == "nci" for f in files) and "https://www.cancer.gov" not in first:
        problems.append("the first screen of the card does not cover the NCI text")
    problems += tag_problems("README.md", text)
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
    listed = {f["path"] for f in files} | {f["path"] for f in manifest.get("access_files") or []}
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
        text = (root / "README.md").read_text(encoding="utf-8")
        problems += card_problems(text, files)
        cite = citation(manifest.get("version", ""), manifest.get("created", ""))
        if cite not in text:
            problems.append("the card does not cite this version as the manifest gives it")
        paper = text.find(paper_citation())
        if paper < 0 or PAPER_URL not in text or paper_bibtex() not in text:
            problems.append("the card does not cite the paper (its citation and BibTeX entry)")
        elif cite in text and text.find(cite) < paper:
            problems.append("the card cites the dataset's version before the paper")
    if (root / "LICENSES.md").exists():
        problems += tag_problems("LICENSES.md", (root / "LICENSES.md").read_text(encoding="utf-8"))
    problems += access.problems(root, manifest)
    if manifest.get("access_files") and (root / "README.md").exists():
        problems += start_here_problems((root / "README.md").read_text(encoding="utf-8"))
    return problems


def start_here_problems(text: str) -> list[str]:
    """A card with the easy-access layer opens with "Start here", right after the box."""
    m = _FRONT.match(text)
    body = text[m.end() :] if m else text
    first = re.search(r"^## (.+)$", body, re.M)
    box = body.find("> **Not medical information.**")
    if not first or first.group(1).strip() != "Start here" or not 0 <= box < first.start():
        return ["the card does not open with '## Start here' right after the box."]
    return []


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
#: Kaggle takes a title of 6 to 50 characters and a subtitle of 20 to 80.
KAGGLE_TITLE = "PlainPairs: prescriber and patient label texts"
KAGGLE_SUBTITLE = "A research record of wording, not medical information"
KAGGLE_LIMITS = {"title": (6, 50), "subtitle": (20, 80)}


def kaggle_metadata(manifest: dict[str, Any], pack_dir: Path) -> dict[str, Any]:
    """The Kaggle mirror's dataset-metadata.json, from the pack's manifest, its files' columns,
    the built card and the schema documentation (see :mod:`plainpairs.kaggle_meta`). It serves
    `datasets create` and `version` (files) and `datasets metadata --update` (the page)."""
    from plainpairs import kaggle_meta

    doc = kaggle_meta.read_schema_doc()
    return {
        "title": KAGGLE_TITLE,
        "subtitle": KAGGLE_SUBTITLE,
        "id": KAGGLE_ID,
        "licenses": [{"name": "other"}],
        "keywords": list(kaggle_meta.KEYWORDS),
        "expectedUpdateFrequency": kaggle_meta.update_frequency(manifest),
        "userSpecifiedSources": kaggle_meta.SOURCES,
        "description": kaggle_meta.description(manifest, card(manifest)),
        "resources": kaggle_meta.resources(Path(pack_dir), manifest, doc),
    }


def _write_kaggle_page(pack_dir: Path, out_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """The Kaggle folder's dataset-metadata.json and cover image (no data file is touched)."""
    from plainpairs import cover, kaggle_meta

    meta = kaggle_metadata(manifest, pack_dir)
    (out_dir / "dataset-metadata.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    shutil.copyfile(cover.TRACKED, out_dir / kaggle_meta.COVER_NAME)
    return meta


def build_kaggle(pack_dir: Path, out_dir: Path) -> dict[str, Any]:
    """The Kaggle mirror: the same files as the pack (flat names), the licenses, the manifest,
    the page's settings and its cover."""
    pack_dir, out_dir = Path(pack_dir), Path(out_dir)
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in manifest["files"]:
        shutil.copyfile(pack_dir / f["path"], out_dir / f"{f['config']}.parquet")
    for name in ("LICENSES.md", "manifest.json"):
        shutil.copyfile(pack_dir / name, out_dir / name)
    access.build_kaggle(pack_dir, out_dir, manifest)
    return _write_kaggle_page(pack_dir, out_dir, manifest)


def check_kaggle(out_dir: Path, pack_dir: Path) -> list[str]:
    """The Kaggle folder holds exactly the pack's files, byte for byte, the metadata and the
    cover; the page's settings pass :func:`plainpairs.kaggle_meta.kaggle_problems`."""
    from plainpairs import cover, kaggle_meta

    out_dir, pack_dir = Path(out_dir), Path(pack_dir)
    problems = []
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    want = {f"{f['config']}.parquet": f["sha256"] for f in manifest["files"]}
    layer = [name for name, _ in access.kaggle_files(manifest)]
    have = {p.name for p in out_dir.iterdir() if p.is_file()} - {
        "dataset-metadata.json",
        "LICENSES.md",
        "manifest.json",
        kaggle_meta.COVER_NAME,
    }
    if have != set(want) | set(layer):
        problems.append("the Kaggle folder's files differ from the pack's.")
    if any(n.lower() == "readme.md" for n in have):
        problems.append("the Kaggle folder holds a README.md (the description carries the card).")
    problems += access.kaggle_problems(pack_dir, out_dir, manifest)
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
    if citation(manifest["version"], manifest["created"]) not in meta.get("description", ""):
        problems.append("the Kaggle description does not cite this version as the card does.")
    if paper_citation() not in meta.get("description", ""):
        problems.append("the Kaggle description does not cite the paper as the card does.")
    problems += tag_problems("the Kaggle description", meta.get("description", ""))
    for field, (low, high) in KAGGLE_LIMITS.items():
        n = len(meta.get(field, ""))
        if not low <= n <= high:
            problems.append(f"the Kaggle {field} has {n} characters; Kaggle takes {low} to {high}.")
    lic = out_dir / "LICENSES.md"
    if not lic.exists() or _sha(lic) != _sha(pack_dir / "LICENSES.md"):
        problems.append("the Kaggle folder's LICENSES.md differs from the pack's.")
    image = out_dir / kaggle_meta.COVER_NAME
    if not image.exists() or _sha(image) != _sha(cover.TRACKED):
        problems.append(f"the Kaggle folder's {kaggle_meta.COVER_NAME} is not the project's cover.")
    problems += kaggle_meta.kaggle_problems(meta, manifest, pack_dir)
    return problems


def write_card(pack_dir: Path, kaggle_dir: Path | None = None) -> list[Path]:
    """Write the card (README.md) and LICENSES.md again from the pack's own manifest, and the
    Kaggle folder's LICENSES.md, page settings (description, file and column descriptions,
    sources) and cover. The data files and the manifest are not touched, so a fix to the
    card's or the page's wording needs no rebuild of the tables."""
    from plainpairs import kaggle_meta

    pack_dir = Path(pack_dir)
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    written = [pack_dir / "README.md", pack_dir / "LICENSES.md"]
    written[0].write_text(card(manifest), encoding="utf-8")
    written[1].write_text(_template(LICENSES_TEMPLATE, manifest), encoding="utf-8")
    if kaggle_dir is not None:
        kaggle_dir = Path(kaggle_dir)
        shutil.copyfile(pack_dir / "LICENSES.md", kaggle_dir / "LICENSES.md")
        _write_kaggle_page(pack_dir, kaggle_dir, manifest)
        written += [
            kaggle_dir / "LICENSES.md",
            kaggle_dir / "dataset-metadata.json",
            kaggle_dir / kaggle_meta.COVER_NAME,
        ]
    return written
