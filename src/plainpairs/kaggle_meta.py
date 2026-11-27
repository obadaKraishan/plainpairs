"""The Kaggle mirror's page: its description, file and column descriptions, and sources.

Everything here is built from what the card is built from: the pack's manifest, the constants
in :mod:`plainpairs.pack`, sections lifted from the built card itself (the box, the limits and
"How to cite") and the repository's schema documentation (``docs/schema.md``), whose column
tables give every column's description once. Nothing here holds label or summary text.

**What the command line can set.** ``kaggle datasets metadata --update`` sends one settings
object: title, subtitle, description, keywords, licenses, the files' and columns' descriptions,
the expected update frequency, ``userSpecifiedSources`` and a cover image. Authors, coverage,
collection methodology and citations are set on the website only. The CLI sends an empty
``userSpecifiedSources`` when the file has none, so the pack always carries it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from plainpairs import tables

#: The repository's schema documentation: one row per column of every release table.
SCHEMA_DOC = Path(__file__).resolve().parents[2] / "docs" / "schema.md"
#: The names a column pattern may stand for (``p_<section>_sha256``, ``t_<text>``).
PLACEHOLDERS = {"section": tables.PRESCRIBER, "text": tables.PATIENT}

#: The description's headings, in this order; the bold line sits between the first two.
HEADINGS = (
    "What PlainPairs is",
    "What is inside",
    "Load one table",
    "Sources, terms and credit",
    "Limits",
    "How to cite",
    "Links",
)
NOT_MEDICAL = "**Not medical information.**"
#: Kaggle publishes no length limit for a description; this is the project's own cap.
DESCRIPTION_MAX = 20_000
#: The file the load snippet reads; it must be one of the mirror's files.
LOAD_FILE = "current_labels.parquet"
KAGGLE_INPUT = "/kaggle/input/plainpairs"
REPO_URL = "https://github.com/obadaKraishan/plainpairs"
#: "not specified" for 0.1.0 (no schedule was promised); from 0.2.0, the first version with the
#: easy-access layer, Hugging Face is updated weekly and this mirror monthly.
UPDATE_FREQUENCY = "not specified"
UPDATE_FREQUENCY_LAYERED = "monthly"
#: The description's "Start here" heading, right after the first section (versions with the
#: easy-access layer).
START_HERE_HEADING = "Start here"
#: The name the Kaggle CLI looks for next to dataset-metadata.json (and never uploads as a file).
COVER_NAME = "dataset-cover-image.png"
UPDATE_FREQUENCIES = (
    "not specified",
    "never",
    "annually",
    "quarterly",
    "monthly",
    "weekly",
    "daily",
    "hourly",
)
#: Kaggle tags. Its documentation says an unknown tag is dropped, but `metadata --update`
#: refuses the whole update over one ("The following keywords are invalid", 2026-11-17), so
#: only tags Kaggle has not refused stay here.
KEYWORDS = (
    "health",
    "nlp",
    "text",
    "medicine",
    "healthcare",
    "linguistics",
    "cancer",
)
#: Tags Kaggle refused on 2026-11-17; the check fails on any of them.
REFUSED_TAGS = ("text-mining", "united-states", "drugs-and-medications", "public-health")
#: Provenance > Sources on Kaggle (``userSpecifiedSources``; Kaggle reads basic Markdown).
SOURCES = (
    "- **Medicine labels:** the openFDA drug label bulk files, U.S. Food and Drug "
    "Administration (https://open.fda.gov/apis/downloads/). Data provided by the U.S. Food and "
    "Drug Administration (https://open.fda.gov).\n"
    "- **Text structure of `current` labels and the served flag:** DailyMed, National Library "
    "of Medicine (https://dailymed.nlm.nih.gov/dailymed/). Courtesy of the National Library of "
    "Medicine.\n"
    "- **The `nci` configuration:** the National Cancer Institute's cancer information "
    "summaries (https://www.cancer.gov/publications/pdq/information-summaries), with parts "
    "left out; every row carries its credit line."
)
SOURCE_ADDRESSES = (
    "https://open.fda.gov/apis/downloads/",
    "https://dailymed.nlm.nih.gov/dailymed/",
    "https://www.cancer.gov/publications/pdq/information-summaries",
)
#: What each configuration holds, in the card's words.
CONFIGURATIONS = {
    "current": (
        "labels that DailyMed serves in the same version as the export, with reading levels "
        "measured on their text structure"
    ),
    "unlisted": "every other label, measured from the source's JSON only",
}
OTHER_FILES = {
    "LICENSES.md": (
        "What applies to each configuration: the sources, their terms, the credit each asks "
        "for and the text switch. Read it before reusing any text."
    ),
    "manifest.json": (
        "Every data file of this version with its rows, size and SHA-256, the date of each "
        "source, and the switch setting."
    ),
}


#: What each easy-access file is, for the Kaggle file list.
LAYER_FILES = {
    "00_start_here_labels.csv": (
        "Start here: every current label, one row per label, with its reading levels and listing "
        "flags and no label text (the current_labels table as a CSV)."
    ),
    "00_start_here_labels.xlsx": "The same rows in Excel, with a Read me sheet and a Fields sheet.",
    "00_start_here_labels_sample_1000.xlsx": (
        "A seeded sample of 1,000 of those rows in Excel, with a Read me sheet and a Fields sheet."
    ),
    "00_start_here_pairs_sample_1000.xlsx": (
        "A seeded sample of 1,000 current section pairs: the patient segment next to the "
        "prescriber section, released text only, with a Read me sheet."
    ),
    "fields.csv": "Every column of every table: its type, meaning and allowed values.",
    "codebook.csv": (
        "The trusted codes of codebook version 1 and the alignment's ten heading keys, each with "
        "its definition, status and check."
    ),
}


def update_frequency(manifest: dict[str, Any]) -> str:
    """The Kaggle update frequency a version's page sends."""
    return UPDATE_FREQUENCY_LAYERED if manifest.get("access_files") else UPDATE_FREQUENCY


def headings_for(manifest: dict[str, Any]) -> tuple[str, ...]:
    """The description's headings in order for this version."""
    if manifest.get("access_files"):
        return (HEADINGS[0], START_HERE_HEADING, *HEADINGS[1:])
    return HEADINGS


class SchemaDocError(ValueError):
    """``docs/schema.md`` cannot be read as the column tables this module expects."""


# --- the schema documentation ----------------------------------------------------------------

_HEADING = re.compile(r"^(#{2,3}) (.+)$")
_NAME = re.compile(r"`([A-Za-z0-9_]+)`")
_TABLE_HEAD = "| column | type | notes |"
_ROW = re.compile(r"^\| `([a-z0-9_<>]+)` \| ([a-z]+) \| (.+) \|$")
_ONE_ROW = re.compile(r":\s+(one row per .+)$")


@dataclass(frozen=True)
class SchemaDoc:
    """The column tables of ``docs/schema.md``: table name -> column or pattern -> notes, and
    each table's "one row per ..." line."""

    columns: dict[str, dict[str, str]]
    rows: dict[str, str]

    def describe(self, table: str, column: str) -> str | None:
        """The column's description as the doc gives it (placeholders filled, backticks
        dropped), or None when the doc does not describe it."""
        notes = self.columns.get(table, {})
        if column in notes:
            return _plain(notes[column])
        for pattern, text in notes.items():
            for name, values in PLACEHOLDERS.items():
                token = f"<{name}>"
                if token not in pattern:
                    continue
                rx = re.escape(pattern).replace(re.escape(token), "(?P<v>[a-z_]+)")
                m = re.fullmatch(rx, column)
                if m and m["v"] in values:
                    return _plain(text.replace(token, m["v"]))
        return None


def _plain(text: str) -> str:
    """Notes as plain text for Kaggle: no backticks, one space, a capital first letter (unless
    the notes open with a value in backticks, which keeps its case)."""
    s = " ".join(text.replace("`", "").split())
    return s if text.startswith("`") else s[:1].upper() + s[1:]


def read_schema_doc(path: Path = SCHEMA_DOC) -> SchemaDoc:
    """Read every ``| column | type | notes |`` table of the schema doc. A table belongs to the
    tables named in backticks in the heading above it. A malformed row, or a column given twice
    for one table, is an error that names the line."""
    path = Path(path)
    if not path.exists():
        raise SchemaDocError(
            f"{path} not found: build the Kaggle folder from a checkout of the repository."
        )
    columns: dict[str, dict[str, str]] = {}
    rows: dict[str, str] = {}
    names: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        heading = _HEADING.match(line)
        if heading:
            names = _NAME.findall(heading.group(2))
            one = _ONE_ROW.search(heading.group(2))
            if one:
                phrase = re.sub(r"\s*\([^()]*\)$", "", one.group(1)).strip()
                for n in names:
                    rows.setdefault(n, phrase)
        elif line.strip() == _TABLE_HEAD:
            if not names:
                raise SchemaDocError(f"{path} line {i + 1}: a column table under no table name.")
            i += 2  # the header and its |---| line
            while i < len(lines) and lines[i].startswith("|"):
                m = _ROW.match(lines[i].strip())
                if not m:
                    raise SchemaDocError(
                        f"{path} line {i + 1}: a column row must read | `name` | type | notes |."
                    )
                for n in names:
                    table = columns.setdefault(n, {})
                    if m.group(1) in table:
                        raise SchemaDocError(
                            f"{path} line {i + 1}: `{m.group(1)}` is described twice for `{n}`."
                        )
                    table[m.group(1)] = m.group(3)
                i += 1
            continue
        i += 1
    return SchemaDoc(columns, rows)


def doc_table(f: dict[str, Any]) -> str:
    """The table name the schema doc uses for a manifest file (``labels``, ``nci_pairs``...)."""
    return f["config"] if f["configuration"] in (None, "nci") else f["table"]


# --- files and columns -------------------------------------------------------------------------


def kaggle_type(t: pa.DataType) -> str | None:
    """Kaggle's column type for an Arrow type; None (no type sent) for lists and structs."""
    if pa.types.is_boolean(t):
        return "boolean"
    if pa.types.is_integer(t):
        return "integer"
    if pa.types.is_floating(t):
        return "numeric"
    if pa.types.is_string(t) or pa.types.is_large_string(t):
        return "string"
    if pa.types.is_date(t) or pa.types.is_timestamp(t):
        return "datetime"
    return None


def file_description(f: dict[str, Any], doc: SchemaDoc) -> str:
    """One or two sentences for a data file: what one row is, its layer and configuration."""
    one = doc.rows.get(doc_table(f), "")
    one = one[:1].upper() + one[1:]
    if f["configuration"] is None:
        return (
            f"{one}: a list, not a configuration, of labels the source types as over-the-counter "
            "drugs that carry a Medication Guide or a patient package insert. Record fields "
            "only; these labels are in no other file."
        )
    if f["configuration"] == "nci":
        from plainpairs import pack

        held = (
            "Each row carries its credit line; a row is not an NCI summary."
            if f["layer"] == "text"
            else "No text."
        )
        layer = f["layer"]
        return f"{one}, in the {layer} layer of the nci configuration ({pack.NCI_NAME}). {held}"
    held = (
        "Label text, only of labels that show no company copyright mark."
        if f["layer"] == "text"
        else "No label text."
    )
    conf, layer = f["configuration"], f["layer"]
    what = CONFIGURATIONS[conf]
    return f"{one}, in the {layer} layer of the {conf} configuration: {what}. {held}"


def resources(pack_dir: Path, manifest: dict[str, Any], doc: SchemaDoc) -> list[dict[str, Any]]:
    """The mirror's files for dataset-metadata.json: every data file with its description and
    all its columns, in order (Kaggle matches columns by order), then LICENSES.md and the
    manifest. A column the doc does not describe gets an empty description, which
    :func:`kaggle_problems` reports."""
    out: list[dict[str, Any]] = []
    for f in manifest["files"]:
        schema = pq.read_schema(Path(pack_dir) / f["path"])
        fields = []
        for name in schema.names:
            field: dict[str, Any] = {
                "name": name,
                "description": doc.describe(doc_table(f), name) or "",
            }
            kind = kaggle_type(schema.field(name).type)
            if kind:
                field["type"] = kind
            fields.append(field)
        out.append(
            {
                "path": f"{f['config']}.parquet",
                "description": file_description(f, doc),
                "schema": {"fields": fields},
            }
        )
    from plainpairs import access

    layer = []
    for name, _source in access.kaggle_files(manifest):
        if name in LAYER_FILES:
            text = LAYER_FILES[name]
        else:
            config = name.removesuffix(".csv")
            f = next(x for x in manifest["files"] if x["config"] == config)
            text = f"The {config} table as a CSV file (the same rows as {config}.parquet)."
        layer.append({"path": name, "description": text})
    out += layer
    out += [{"path": name, "description": text} for name, text in OTHER_FILES.items()]
    return out


# --- the description -----------------------------------------------------------------------------


def card_section(card: str, heading: str) -> str:
    """The body of one ``## heading`` section of the built card, without its heading."""
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", card, re.S | re.M)
    if not m:
        raise ValueError(f"the card has no section '## {heading}'.")
    return m.group(1).strip()


def card_box(card: str) -> str:
    """The card's not-medical-information box as one paragraph, without its bold lead."""
    m = re.search(r"^> \*\*Not medical information\.\*\* (.*?)(?=\n\n)", card, re.S | re.M)
    if not m:
        raise ValueError("the card has no not-medical-information box.")
    return " ".join(m.group(1).replace("\n> ", " ").split())


def _files_table(manifest: dict[str, Any]) -> str:
    rows = ["| file | configuration | layer | rows |", "|---|---|---|---:|"]
    for f in manifest["files"]:
        conf = f["configuration"] or "a list, not a configuration"
        rows.append(f"| `{f['config']}.parquet` | {conf} | {f['layer']} | {f['rows']:,} |")
    rows.append("| `LICENSES.md` | all | the terms | |")
    rows.append("| `manifest.json` | all | every file's rows, size and SHA-256 | |")
    return "\n".join(rows)


def description(manifest: dict[str, Any], card: str) -> str:
    """The Kaggle description in Markdown, with the headings of :data:`HEADINGS` in order."""
    from plainpairs import pack

    f = manifest["facts"]
    s = manifest["sources"]
    version = manifest["version"]
    parts = [
        f"## {HEADINGS[0]}",
        "PlainPairs pairs the text that United States medicine labels write for prescribers "
        "with the text they write for patients (Medication Guides and patient package "
        "inserts), matched section by section, with reading-level and plain-language measures "
        f"on both sides. Version {version}, built from the openFDA drug label export of "
        f"{s['openfda_label_export']}, holds {f['current_labels']:,} labels in the `current` "
        f"configuration and {f['unlisted_labels']:,} in `unlisted`, and "
        f"{f['nci_summaries']:,} summary pages in `nci`: {pack.NCI_NAME}, in a "
        "health-professional and a patient version, in English and Spanish. It is for "
        "researchers who study health communication, readability and plain language, and for "
        "those who build and test text-simplification tools.",
        NOT_MEDICAL,
        card_box(card),
        *_start_here(manifest),
        f"## {HEADINGS[1]}",
        "Three configurations, **never pooled**: each has its own record tables (no label "
        "text) and text tables, and no file holds rows of two. They hold different sets of "
        "texts, measured in different ways, so a difference between them is not a measured "
        "change.",
        f"- `current`: {CONFIGURATIONS['current']} ({f['current_labels']:,} labels).\n"
        f"- `unlisted`: {CONFIGURATIONS['unlisted']} ({f['unlisted_labels']:,} labels).\n"
        f"- `nci`: {pack.NCI_NAME} ({f['nci_summaries']:,} summary pages).\n"
        f"- `excluded_otc` is a list, not a configuration: the {f['excluded_otc']:,} labels "
        "the source types as over-the-counter drugs that carry a Medication Guide or a "
        "patient package insert, with record fields only.",
        _files_table(manifest),
        "The repository's schema documentation describes every file and every column: "
        f"{REPO_URL}/blob/main/docs/schema.md",
        f"## {HEADINGS[2]}",
        "Read one configuration at a time; never concatenate a `current_` file with an "
        "`unlisted_` one.",
        "```python\nimport pandas as pd\n\n"
        f'labels = pd.read_parquet("{KAGGLE_INPUT}/{LOAD_FILE}")\n```',
        "On Hugging Face, the primary copy, each file is its own config: "
        f'`load_dataset("obadakr/plainpairs", "{LOAD_FILE.removesuffix(".parquet")}", '
        'split="train")`.',
        f"## {HEADINGS[3]}",
        f"- **Labels:** the openFDA drug label export of {s['openfda_label_export']}, public "
        "domain (CC0 1.0) unless otherwise noted. Credit: **Data provided by the U.S. Food and "
        "Drug Administration (https://open.fda.gov).** Some labels carry a company's copyright "
        f"mark: their text is held back ({manifest['held_back']['label_text_rows_marked']:,} "
        "text rows), their record rows stay.\n"
        "- **Text structure of `current` labels:** DailyMed's full release of human "
        f"prescription labels of {pack.dailymed_words(s)}. Courtesy of the National Library of "
        "Medicine.\n"
        f"- **`nci`:** pages read on {s['nci_pages_read']}. Credit the National Cancer "
        "Institute as the source; every row carries its credit line. Images, figures, tables "
        "credited to other publishers, references and the closing sections are left out, so a "
        "row is not an NCI summary.",
        "Not made, endorsed or checked by the U.S. Food and Drug Administration, the National "
        "Library of Medicine, the National Cancer Institute or any company whose labels it "
        "holds. The full terms for each configuration are in `LICENSES.md`, in this dataset.",
        f"## {HEADINGS[4]}",
        card_section(card, "Limits"),
        f"## {HEADINGS[5]}",
        card_section(card, "How to cite"),
        f"## {HEADINGS[6]}",
        f"- Hugging Face, the primary copy: {pack.HF_URL}\n"
        f"- The repository (code, method, schema, codebook): {REPO_URL}\n"
        f"- The paper: {pack.PAPER_URL}\n"
        f"- The software and documents on Zenodo: https://doi.org/{pack.SOFTWARE_DOI}",
    ]
    return "\n\n".join(parts) + "\n"


def _start_here(manifest: dict[str, Any]) -> list[str]:
    from plainpairs import access

    if not manifest.get("access_files"):
        return []
    return [access.start_here_section(manifest, kaggle=True)]


# --- the checks ----------------------------------------------------------------------------------

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def headings(text: str) -> list[str]:
    """The ``## `` headings of a Markdown text, outside fenced code."""
    out, fence = [], False
    for line in text.splitlines():
        if _FENCE.match(line):
            fence = not fence
        elif not fence and line.startswith("## "):
            out.append(line[3:].strip())
    return out


def description_problems(text: str, manifest: dict[str, Any], files: list[str]) -> list[str]:
    """What is wrong with a Kaggle description: headings, the bold line, "How to cite", the
    length and the load snippet's file."""
    from plainpairs import pack

    problems = []
    want = list(headings_for(manifest))
    if headings(text) != want:
        problems.append(f"the Kaggle description's headings are {headings(text)}, not {want}.")
        return problems
    first, inside = (text.index(f"## {h}\n") for h in want[:2])
    if f"\n{NOT_MEDICAL}\n" not in text[first:inside]:
        problems.append(
            f"the Kaggle description lacks the bold line {NOT_MEDICAL} before 'What is inside'."
        )
    how = text[text.index(f"## {HEADINGS[5]}\n") : text.index(f"## {HEADINGS[6]}\n")]
    paper = pack.paper_citation()
    dataset = pack.citation(manifest["version"], manifest["created"])
    if paper not in how or dataset not in how or how.index(paper) > how.index(dataset):
        problems.append(
            "the Kaggle description's How to cite does not name the paper before the dataset's "
            "version."
        )
    if f"```bibtex\n{pack.paper_bibtex()}\n```" not in how:
        problems.append("the Kaggle description's How to cite lacks the paper's BibTeX entry.")
    if len(text) > DESCRIPTION_MAX:
        problems.append(
            f"the Kaggle description has {len(text):,} characters; the cap is {DESCRIPTION_MAX:,}."
        )
    if LOAD_FILE not in files:
        problems.append(f"the Kaggle description loads {LOAD_FILE}, which is not one of its files.")
    return problems


def kaggle_problems(meta: dict[str, Any], manifest: dict[str, Any], pack_dir: Path) -> list[str]:
    """What is wrong with the mirror's page settings: the description, every file and column
    described (all columns, in the files' own order), the frequency and the sources."""
    problems = []
    from plainpairs import access

    res = {r.get("path"): r for r in meta.get("resources", [])}
    layer = [n for n, _ in access.kaggle_files(manifest)]
    want = [f"{f['config']}.parquet" for f in manifest["files"]] + layer + list(OTHER_FILES)
    if list(res) != want:
        problems.append(
            "the Kaggle metadata's files are not the pack's files and its two documents."
        )
    problems += description_problems(meta.get("description", ""), manifest, list(res))
    for name, r in res.items():
        if not str(r.get("description", "")).strip():
            problems.append(f"the Kaggle file {name} has no description.")
    for f in manifest["files"]:
        r = res.get(f"{f['config']}.parquet")
        if r is None:
            continue
        fields = r.get("schema", {}).get("fields", [])
        names = pq.read_schema(Path(pack_dir) / f["path"]).names
        if [x.get("name") for x in fields] != names:
            problems.append(
                f"the Kaggle columns of {r['path']} are not the file's columns in order."
            )
        bare = [x.get("name") for x in fields if not str(x.get("description", "")).strip()]
        if bare:
            problems.append(
                f"the Kaggle file {r['path']} has {len(bare)} columns without a description "
                f"({', '.join(bare[:5])}); describe them in docs/schema.md."
            )
    if meta.get("expectedUpdateFrequency") != update_frequency(manifest):
        problems.append(
            f"the Kaggle update frequency is {meta.get('expectedUpdateFrequency')!r}, not "
            f"{update_frequency(manifest)!r} (monthly from the version with the easy-access "
            "layer, not specified before it)."
        )
    sources = meta.get("userSpecifiedSources", "")
    if not all(a in sources for a in SOURCE_ADDRESSES):
        problems.append("the Kaggle sources do not name all three sources with their addresses.")
    refused = [k for k in meta.get("keywords", []) if k in REFUSED_TAGS]
    if refused:
        problems.append(
            f"Kaggle refuses the tags {', '.join(refused)}, and with them the whole update; "
            "leave them out."
        )
    return problems


# --- settings for `kaggle datasets metadata --update` ---------------------------------------------

#: The fields `metadata --update` sends; anything else in the live file is left out.
SENT = (
    "title",
    "subtitle",
    "description",
    "isPrivate",
    "licenses",
    "keywords",
    "collaborators",
    "expectedUpdateFrequency",
    "userSpecifiedSources",
)


def update_settings(live: dict[str, Any], meta: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The settings to send, starting from the live ones (``kaggle datasets metadata`` without
    ``--update`` downloads them wrapped in ``info``): the pack's description, keywords, files,
    update frequency and sources replace the live ones; title, subtitle and license must
    already agree. Returns the settings and the names of the fields that change."""
    info = live.get("info", live)
    for field in ("title", "subtitle"):
        if info.get(field) != meta.get(field):
            raise ValueError(
                f"the live {field} {info.get(field)!r} differs from the pack's "
                f"{meta.get(field)!r}; this step changes no title, subtitle or license."
            )
    if [x.get("name") for x in info.get("licenses", [])] != [
        x.get("name") for x in meta.get("licenses", [])
    ]:
        raise ValueError("the live license differs from the pack's; this step changes no license.")
    # The download leaves out fields at their defaults (a public page, no collaborators, no
    # sources); the CLI sends exactly these defaults when a field is missing.
    before = {
        "isPrivate": False,
        "collaborators": [],
        "userSpecifiedSources": "",
        **{k: info[k] for k in SENT if k in info},
    }
    out = dict(before)
    for k in ("description", "expectedUpdateFrequency", "userSpecifiedSources"):
        out[k] = meta[k]
    # a tag added on the website stays: the pack's keywords first, then any other live one
    out["keywords"] = list(dict.fromkeys([*meta["keywords"], *info.get("keywords", [])]))
    out["resources"] = meta["resources"]
    changed = [k for k in (*SENT, "resources") if out.get(k) != before.get(k)]
    return out, changed


def write_update_settings(
    live_path: Path, kaggle_dir: Path, out_dir: Path
) -> tuple[Path, list[str]]:
    """Write ``out_dir/dataset-metadata.json`` (and the cover) for
    ``kaggle datasets metadata --update -p out_dir``. The folder must be new or empty, so no
    stray file is sent with it."""
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ValueError(f"{out_dir} is not empty; give a new folder.")
    meta = json.loads((Path(kaggle_dir) / "dataset-metadata.json").read_text(encoding="utf-8"))
    live = json.loads(Path(live_path).read_text(encoding="utf-8"))
    settings, changed = update_settings(live, meta)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "dataset-metadata.json"
    path.write_text(json.dumps(settings, indent=1), encoding="utf-8")
    cover = Path(kaggle_dir) / COVER_NAME
    if cover.exists():
        (out_dir / COVER_NAME).write_bytes(cover.read_bytes())
        changed.append("image")
    return path, changed
