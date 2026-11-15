"""The corpus tables, in two layers, built from the bulk parts of one export.

**Record layer** (always releasable; no label text):

- ``labels`` (table A): one row per label in scope, with identity, format, flags, the SHA-256
  of every text, the id of each patient text, and measures per section and per text;
- ``patient_texts`` (table B): one row per distinct patient text (grouped by the core hash),
  with the labels that carry it;
- ``section_pairs`` (table C): one row per segment of a Medication Guide or patient package
  insert, with its heading key, its character offsets in the text, the prescriber sections it
  is mapped to and the similarity scores;
- ``excluded_otc``: labels typed over the counter that carry a guide or an insert (listed, not
  in scope).

**Text layer** (released only as the switch allows; see :mod:`plainpairs.release`):

- ``text_prescriber`` and ``text_patient``: one row per label and section (or patient text),
  and one per table of that section, with the cleaned text, its SHA-256 and the label's
  ``has_copyright_mark``.

Every row carries the source, the export date and the label's set id and version.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from plainpairs import align, bulk, durable, label, listed, readability, structure, text
from plainpairs.schema import PATIENT_SOURCES, PRESCRIBER_SOURCES, LabelRow

SOURCE = "openFDA drug label bulk files (https://open.fda.gov/data/spl/)"
IN_SCOPE_FORMATS = ("plr", "older")
OTC = "HUMAN OTC DRUG"
PRESCRIBER = tuple(PRESCRIBER_SOURCES)
PATIENT = tuple(PATIENT_SOURCES)
#: Patient texts that make a label part of a pair; the other two are kept as extra texts.
PAIRING = ("medication_guide", "patient_package_insert")
RECORD_TABLES = ("labels", "patient_texts", "section_pairs", "excluded_otc")
TEXT_TABLES = ("text_prescriber", "text_patient")

MEASURES = pa.struct(
    [
        ("words", pa.int32()),
        ("words_with_tables", pa.int32()),
        ("sentences", pa.int32()),
        ("sentences_s1", pa.int32()),
        ("syllables", pa.int32()),
        ("polysyllables", pa.int32()),
        ("long_sentence_share", pa.float32()),
        ("numbers", pa.int32()),
        ("percentages", pa.int32()),
        ("flesch_kincaid", pa.float32()),
        ("flesch_kincaid_s1", pa.float32()),
        ("flesch_reading_ease", pa.float32()),
        ("smog", pa.float32()),
        ("smog_s1", pa.float32()),
        ("smog_short_text", pa.bool_()),
        ("headings", pa.int32()),
        ("table_chars_cut", pa.int32()),
    ]
)
STR_LIST = pa.list_(pa.string())
_BASE = [
    ("source", pa.string()),
    ("export_date", pa.string()),
    ("set_id", pa.string()),
    ("version", pa.int32()),
]

LABELS_SCHEMA = pa.schema(
    [
        *_BASE,
        ("id", pa.string()),
        ("source_part", pa.int16()),
        ("effective_date", pa.date32()),
        ("effective_time_raw", pa.string()),
        ("label_format", pa.string()),
        ("format_conflicts", STR_LIST),
        ("harmonized", pa.bool_()),
        ("product_type", pa.string()),
        ("routes", STR_LIST),
        ("application_numbers", STR_LIST),
        ("manufacturers", STR_LIST),
        ("brand_names", STR_LIST),
        ("generic_names", STR_LIST),
        ("pharm_classes_epc", STR_LIST),
        ("medicine_key", pa.string()),
        ("medicine_key_source", pa.string()),
        #: Read from the structured product data, never merged into the medicine key.
        ("product_name", pa.string()),
        ("product_name_source", pa.string()),
        ("product_name_rule", pa.string()),
        #: Listed now (null when the build was given no listing file; see plainpairs.listed).
        ("listed_in_ndc_directory", pa.bool_()),
        ("ndc_match", pa.string()),
        ("served_by_dailymed", pa.bool_()),
        ("dailymed_version", pa.int32()),
        #: The release configuration (null when the build was given no structure table):
        #: ``current`` (DailyMed's release holds the label in this version, with the same
        #: words; structure from its XML) or ``unlisted`` (measured from the JSON only).
        ("configuration", pa.string()),
        ("structure_source", pa.string()),
        ("unlisted_reason", pa.string()),
        ("has_boxed_warning", pa.bool_()),
        ("has_medication_guide", pa.bool_()),
        ("has_patient_package_insert", pa.bool_()),
        ("has_instructions_for_use", pa.bool_()),
        ("has_other_patient_text", pa.bool_()),
        ("has_copyright_mark", pa.bool_()),
        ("n_tables", pa.int16()),
        #: SHA-256 of each table row of the text layer, in the order the rows are written.
        ("tables_sha256", STR_LIST),
        *[(f"p_{s}_sha256", pa.string()) for s in PRESCRIBER],
        *[(f"p_{s}", MEASURES) for s in PRESCRIBER],
        *[(f"t_{k}_sha256", pa.string()) for k in PATIENT],
        *[(f"t_{k}_id", pa.string()) for k in PATIENT],
        *[(f"t_{k}", MEASURES) for k in PATIENT],
        #: Measures from structure (``current`` labels only; null for ``unlisted``).
        *[(f"p_{s}_structured", structure.STRUCTURED) for s in PRESCRIBER],
        *[(f"t_{k}_structured", structure.STRUCTURED) for k in PATIENT],
    ]
)
PATIENT_TEXTS_SCHEMA = pa.schema(
    [
        *_BASE,
        ("patient_text_id", pa.string()),
        ("kind", pa.string()),
        ("core_hash", pa.string()),
        ("n_labels", pa.int32()),
        ("n_exact_variants", pa.int32()),
        ("n_loose_variants", pa.int32()),
        ("set_ids", STR_LIST),
        ("n_manufacturers_known", pa.int32()),
        ("n_labels_without_manufacturer", pa.int32()),
        ("crosses_makers", pa.bool_()),
        ("medicine_keys", STR_LIST),
        ("has_copyright_mark_any", pa.bool_()),
        ("headings_found", STR_LIST),
        ("measures", MEASURES),
        #: ``current`` when at least one label carrying the text is ``current``.
        ("configuration", pa.string()),
        ("n_labels_current", pa.int32()),
        ("measures_structured", structure.STRUCTURED),
    ]
)
SECTION_PAIRS_SCHEMA = pa.schema(
    [
        *_BASE,
        ("kind", pa.string()),
        ("patient_text_id", pa.string()),
        ("segment_index", pa.int16()),
        ("heading_key", pa.string()),
        ("heading_template", pa.string()),
        ("seg_start", pa.int32()),
        ("heading_end", pa.int32()),
        ("seg_end", pa.int32()),
        ("measures", MEASURES),
        ("mapped_sections", STR_LIST),
        ("mapped_present", STR_LIST),
        ("best_section", pa.string()),
        ("best_similarity", pa.float32()),
        ("mapped_best_similarity", pa.float32()),
        ("best_is_mapped", pa.bool_()),
        ("section17_similarity", pa.float32()),
        ("rule_status", pa.string()),
        #: The label's configuration; every column before it is built from the JSON text.
        ("configuration", pa.string()),
    ]
)
EXCLUDED_SCHEMA = pa.schema(
    [
        *_BASE,
        ("product_type", pa.string()),
        ("label_format", pa.string()),
        ("has_medication_guide", pa.bool_()),
        ("has_patient_package_insert", pa.bool_()),
    ]
)
TEXT_SCHEMA = pa.schema(
    [
        *_BASE,
        ("section", pa.string()),
        ("part", pa.string()),
        ("part_index", pa.int16()),
        ("text", pa.string()),
        ("sha256", pa.string()),
        ("has_copyright_mark", pa.bool_()),
        ("text_has_copyright_mark", pa.bool_()),
    ]
)
SCHEMAS = {
    "labels": LABELS_SCHEMA,
    "patient_texts": PATIENT_TEXTS_SCHEMA,
    "section_pairs": SECTION_PAIRS_SCHEMA,
    "excluded_otc": EXCLUDED_SCHEMA,
    "text_prescriber": TEXT_SCHEMA,
    "text_patient": TEXT_SCHEMA,
}


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def measures(full: str, tables: list[str], headings: int) -> dict[str, Any]:
    """Measures of one text: prose (inline tables cut) by both sentence rules."""
    prose, cut = text.strip_tables(full, tables) if tables else (full, 0)
    m = readability.measure_rules(prose)
    s1, s2 = m["s1"], m["s2"]
    return {
        "words": s2.words,
        "words_with_tables": len(readability.words(full)) if cut else s2.words,
        "sentences": s2.sentences,
        "sentences_s1": s1.sentences,
        "syllables": s2.syllables,
        "polysyllables": s2.polysyllables,
        "long_sentence_share": s2.long_sentence_share,
        "numbers": s2.numbers,
        "percentages": s2.percentages,
        "flesch_kincaid": s2.flesch_kincaid_grade,
        "flesch_kincaid_s1": s1.flesch_kincaid_grade,
        "flesch_reading_ease": s2.flesch_reading_ease,
        "smog": s2.smog_grade,
        "smog_s1": s1.smog_grade,
        "smog_short_text": s2.smog_short_text,
        "headings": headings,
        "table_chars_cut": cut,
    }


def in_scope(row: LabelRow) -> bool:
    """A prescription format by sections, a guide or an insert, and not typed over the counter
    (those are listed in ``excluded_otc`` instead)."""
    return (
        row.identity.label_format in IN_SCOPE_FORMATS
        and row.identity.product_type != OTC
        and any(getattr(row.patient, k) for k in PAIRING)
    )


def _tables_by_section(row: LabelRow) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for t in row.tables:
        out[t.section].append(t.text)
    return out


def _raw_tables(record: dict[str, Any]) -> dict[str, list[str]]:
    """The HTML of each section's tables, by section name (to cut them from prose)."""
    section_of = {s: sec for sec, srcs in PRESCRIBER_SOURCES.items() for s in srcs}
    section_of.update({s: sec for sec, s in PATIENT_SOURCES.items()})
    section_of.update({s: "warnings_and_precautions" for s in label.OLDER_WARNINGS})
    out: dict[str, list[str]] = defaultdict(list)
    for source, section in section_of.items():
        for markup in record.get(f"{source}_table") or []:
            if isinstance(markup, str):
                out[section].append(markup)
    return out


def _quantiles(values: list[float]) -> dict[str, float | None]:
    v = sorted(x for x in values if x is not None)
    if not v:
        return {"n": 0, "median": None, "p25": None, "p75": None}
    if len(v) == 1:
        return {"n": 1, "median": v[0], "p25": v[0], "p75": v[0]}
    q = statistics.quantiles(v, n=4, method="inclusive")
    return {
        "n": len(v),
        "median": round(statistics.median(v), 2),
        "p25": round(q[0], 2),
        "p75": round(q[2], 2),
    }


class Builder:
    """Builds both layers from the parts of one export (two passes over the raw files)."""

    def __init__(
        self,
        parts: list[tuple[int, Path]],
        out_dir: Path,
        export_date: str,
        log: Callable[[str], None] = print,
        workers: int = 1,
        listings: listed.Listings | None = None,
        structure_dir: Path | None = None,
        rule_status: dict[str, str] | None = None,
    ) -> None:
        self.workers = workers
        #: heading key -> rule status, from the scored hand sheet (see :func:`rule_statuses`).
        self.rule_status = dict(rule_status or {})
        self.listings = listings or listed.Listings()
        self.structure_dir = Path(structure_dir) if structure_dir else None
        self.configuration: dict[str, str | None] = {}
        self.parts = parts
        self.out = Path(out_dir)
        self.export_date = export_date
        self.log = log
        self.stats: dict[str, Any] = {"export_date": export_date, "parts": len(parts)}
        self.labels: list[dict[str, Any]] = []
        self.df: Counter[str] = Counter()
        self.n_docs = 0
        self.in_scope_ids: set[str] = set()

    # -- pass 1 ------------------------------------------------------------------------------
    def _writer(self, name: str) -> pq.ParquetWriter:
        self.out.mkdir(parents=True, exist_ok=True)
        return pq.ParquetWriter(self.out / f"{name}.parquet", SCHEMAS[name], compression="zstd")

    def scan_part(self, number: int, path: Path) -> dict[str, Any]:
        """Pass 1 over one part: counts, records and the part's own text-layer files."""
        c: Counter[str] = Counter()
        errors: Counter[str] = Counter()
        identity: Counter[str] = Counter()
        excluded: list[dict[str, Any]] = []
        buf: dict[str, list[dict[str, Any]]] = {name: [] for name in TEXT_TABLES}
        ids: list[tuple[str, int | None]] = []
        for record in bulk.iter_labels(path):
            c["labels_read"] += 1
            ids.append((str(record.get("set_id")), label._version(record.get("version"))))
            for f in ("spl_medguide", "spl_patient_package_insert"):
                if record.get(f):
                    c[f"field:{f}"] += 1
            if record.get("spl_medguide") or record.get("spl_patient_package_insert"):
                c["field:either"] += 1
            try:
                row = label.parse_label(record, with_tables=self._candidate(record))
            except label.LabelError as exc:
                errors[str(exc).split(" of label")[0][:60]] += 1
                continue
            ident = row.identity
            c[f"format:{ident.label_format}"] += 1
            for conflict in label.format_conflicts(record, ident.product_type):
                c[f"conflict:{conflict}"] += 1
            for k in PATIENT:
                if getattr(row.patient, k):
                    c[f"parsed:{k}"] += 1
            if row.patient.medication_guide or row.patient.patient_package_insert:
                c["parsed:either"] += 1
                c[f"either_by_format:{ident.label_format}"] += 1
                if ident.product_type == "HUMAN OTC DRUG":
                    excluded.append(
                        {
                            "source": SOURCE,
                            "export_date": self.export_date,
                            "set_id": ident.set_id,
                            "version": ident.version,
                            "product_type": ident.product_type,
                            "label_format": ident.label_format,
                            "has_medication_guide": bool(row.patient.medication_guide),
                            "has_patient_package_insert": bool(row.patient.patient_package_insert),
                        }
                    )
            marked = label.record_has_copyright_mark(record)
            c["marked_any_label"] += marked
            if not in_scope(row):
                continue
            c["in_scope"] += 1
            c["in_scope_marked"] += marked
            c[f"in_scope_harmonized:{ident.harmonized}"] += 1
            self._identity(record, row, identity)
            self._label(number, record, row, marked, buf)
            for k in PAIRING:
                t = getattr(row.patient, k)
                if t:
                    c[f"restated_headings:{k}"] += text.count_restated(t)
        parts_dir = self.out / "_parts"
        parts_dir.mkdir(parents=True, exist_ok=True)
        rows = {}
        for name in TEXT_TABLES:
            pq.write_table(
                pa.Table.from_pylist(buf[name], SCHEMAS[name]),
                parts_dir / f"{name}-{number:02d}.parquet",
                compression="zstd",
            )
            rows[name] = len(buf[name])
        return {
            "number": number,
            "counts": c,
            "errors": errors,
            "identity": identity,
            "excluded": excluded,
            "labels": self.labels,
            "df": self.df,
            "n_docs": self.n_docs,
            "rows": rows,
            "ids": ids,
        }

    def _map(self, fn: Callable[[tuple[Any, ...]], dict[str, Any]], jobs: list[tuple[Any, ...]]):
        """Run ``fn`` over ``jobs``, in parallel when workers > 1; results in job order."""
        if self.workers <= 1:
            yield from map(fn, jobs)
            return
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=self.workers) as pool:
            yield from pool.map(fn, jobs)

    def _merge_parts(self, names: tuple[str, ...]) -> None:
        """Join the part files of each table, in part order, into one file per table."""
        parts_dir = self.out / "_parts"
        for name in names:
            files = sorted(parts_dir.glob(f"{name}-*.parquet"))
            with pq.ParquetWriter(
                self.out / f"{name}.parquet", SCHEMAS[name], compression="zstd"
            ) as w:
                for f in files:
                    w.write_table(pq.read_table(f))
            for f in files:
                f.unlink()

    def pass1(self) -> None:
        c: Counter[str] = Counter()
        errors: Counter[str] = Counter()
        identity: Counter[str] = Counter()
        excluded: list[dict[str, Any]] = []
        jobs = [(n, p, self.out, self.export_date) for n, p in self.parts]
        rows = self.stats.setdefault("rows", {})
        export_ids: list[tuple[str, int | None]] = []
        for res in self._map(_scan_job, jobs):
            export_ids += res["ids"]
            c.update(res["counts"])
            errors.update(res["errors"])
            identity.update(res["identity"])
            excluded += res["excluded"]
            self.labels += res["labels"]
            self.in_scope_ids.update(r["set_id"] for r in res["labels"])
            self.df.update(res["df"])
            self.n_docs += res["n_docs"]
            for name, n in res["rows"].items():
                rows[name] = rows.get(name, 0) + n
            self.log(f"pass 1: part {res['number']} read; {c['in_scope']:,} labels in scope so far")
        self._merge_parts(TEXT_TABLES)
        # every set id of the export, in scope or not: lets `changes` tell a label that left
        # the scope from one withdrawn (ids and versions only, outside the record tables). A
        # version that does not fit a 32-bit integer is written as null and counted.
        versions = [_int32(v) for _, v in export_ids]
        c["export_ids_version_out_of_range"] = sum(
            1 for (_, v), w in zip(export_ids, versions, strict=True) if v is not None and w is None
        )
        pq.write_table(
            pa.table(
                {
                    "export_date": [self.export_date] * len(export_ids),
                    "set_id": [i for i, _ in export_ids],
                    "version": pa.array(versions, pa.int32()),
                }
            ),
            self.out / "export_ids.parquet",
            compression="zstd",
        )
        self.stats["counts"] = dict(c)
        self.stats["parse_errors"] = dict(errors)
        self.stats["identity"] = dict(identity)
        self._write("excluded_otc", excluded)

    @staticmethod
    def _candidate(record: dict[str, Any]) -> bool:
        """Whether a record could be in scope (only then are its tables read)."""
        types = (record.get("openfda") or {}).get("product_type") or [None]
        fmt = label.label_format(record, types[0])
        has_text = record.get("spl_medguide") or record.get("spl_patient_package_insert")
        return fmt in IN_SCOPE_FORMATS and types[0] != OTC and bool(has_text)

    def _identity(self, record: dict[str, Any], row: LabelRow, out: Counter[str]) -> None:
        """How the medicine and maker can be told without the openfda block (counts only)."""
        harmonized = row.identity.harmonized
        tag = "harmonized" if harmonized else "not_harmonized"
        pde = " ".join(record.get("spl_product_data_elements") or [])
        panel = " ".join(record.get("package_label_principal_display_panel") or [])
        out[f"{tag}:labels"] += 1
        out[f"{tag}:has_product_data_elements"] += bool(pde)
        out[f"{tag}:has_package_label"] += bool(panel)
        if harmonized and row.identity.brand_names:
            names = [b.upper() for b in row.identity.brand_names]
            head = text.clean(pde).upper()[:200]
            out["harmonized:brand_in_product_data_start"] += any(head.startswith(n) for n in names)
            out["harmonized:brand_in_product_data_200"] += any(n in head for n in names)
            out["harmonized:brand_in_package_label"] += any(n in panel.upper() for n in names)
            out["harmonized:with_brand_name"] += 1
        if harmonized and row.identity.manufacturers:
            makers = [m.upper()[:20] for m in row.identity.manufacturers]
            out["harmonized:maker_in_package_label"] += any(m in panel.upper() for m in makers)
            out["harmonized:with_manufacturer"] += 1

    def _label(
        self,
        number: int,
        record: dict[str, Any],
        row: LabelRow,
        marked: bool,
        buf: dict[str, list[dict[str, Any]]],
    ) -> None:
        ident = row.identity
        base = {
            "source": SOURCE,
            "export_date": self.export_date,
            "set_id": ident.set_id,
            "version": ident.version,
        }
        raw_tables = _raw_tables(record)
        plain_tables = _tables_by_section(row)
        out: dict[str, Any] = {
            **base,
            "id": ident.id,
            "source_part": number,
            "effective_date": ident.effective_date,
            "effective_time_raw": ident.effective_time_raw,
            "label_format": ident.label_format,
            "format_conflicts": label.format_conflicts(record, ident.product_type),
            "harmonized": ident.harmonized,
            "product_type": ident.product_type,
            "routes": list(ident.routes),
            "application_numbers": list(ident.application_numbers),
            "manufacturers": list(ident.manufacturers),
            "brand_names": list(ident.brand_names),
            "generic_names": list(ident.generic_names),
            "pharm_classes_epc": list(ident.pharm_classes_epc),
            **dict(
                zip(
                    ("product_name", "product_name_source", "product_name_rule"),
                    label.product_name(record),
                    strict=True,
                )
            ),
            "has_boxed_warning": bool(row.prescriber.boxed_warning),
            "has_medication_guide": bool(row.patient.medication_guide),
            "has_patient_package_insert": bool(row.patient.patient_package_insert),
            "has_instructions_for_use": bool(row.patient.instructions_for_use),
            "has_other_patient_text": bool(row.patient.patient_medication_information),
            "has_copyright_mark": marked,
            "n_tables": len(row.tables),
            "tables_sha256": [],
        }
        sections: dict[str, str] = {}
        for s in PRESCRIBER:
            t = getattr(row.prescriber, s)
            out[f"p_{s}_sha256"] = sha256_text(t) if t else None
            out[f"p_{s}"] = (
                measures(t, raw_tables.get(s, []), text.count_numbered_headings(t)) if t else None
            )
            if t:
                sections[s] = t
                self._text_rows(buf["text_prescriber"], base, s, t, plain_tables.get(s, []), marked)
                out["tables_sha256"] += [sha256_text(x) for x in plain_tables.get(s, [])]
        segments: list[tuple[str, str]] = []
        for k in PATIENT:
            t = getattr(row.patient, k)
            out[f"t_{k}_sha256"] = sha256_text(t) if t else None
            out[f"t_{k}_id"] = f"{k}:{text.core_hash(t)}" if t else None
            out[f"t_{k}"] = (
                measures(t, raw_tables.get(k, []), len(text.find_headings(t))) if t else None
            )
            out[f"_{k}_exact"] = text.text_hash(t) if t else None
            out[f"_{k}_loose"] = text.loose_hash(t) if t else None
            if t:
                self._text_rows(buf["text_patient"], base, k, t, plain_tables.get(k, []), marked)
                out["tables_sha256"] += [sha256_text(x) for x in plain_tables.get(k, [])]
                if k in PAIRING:
                    segments += [
                        (key, t[head_end:end])
                        for key, start, head_end, end in text.segment_spans(t)
                        if key != "preamble"
                    ]
                    out[f"_{k}_headings"] = sorted(
                        {key for key, *_ in text.segment_spans(t)} - {"preamble"}
                    )
        sec_counts, seg_counts = align.label_counts(sections, segments)
        self.n_docs += align.update_df(self.df, [*sec_counts.values(), *(c for _, c in seg_counts)])
        self.labels.append(out)
        self.in_scope_ids.add(ident.set_id)

    @staticmethod
    def _text_rows(
        rows: list[dict[str, Any]],
        base: dict[str, Any],
        section: str,
        t: str,
        tables: list[str],
        marked: bool,
    ) -> None:
        rows.append(
            {
                **base,
                "section": section,
                "part": "text",
                "part_index": 0,
                "text": t,
                "sha256": sha256_text(t),
                "has_copyright_mark": marked,
                "text_has_copyright_mark": bool(label.COPYRIGHT.search(t)),
            }
        )
        for i, tab in enumerate(tables, start=1):
            rows.append(
                {
                    **base,
                    "section": section,
                    "part": "table",
                    "part_index": i,
                    "text": tab,
                    "sha256": sha256_text(tab),
                    "has_copyright_mark": marked,
                    "text_has_copyright_mark": bool(label.COPYRIGHT.search(tab)),
                }
            )

    # -- between the passes: medicines, table A and table B ------------------------------------
    def finish_records(self) -> None:
        # A medicine key from the openfda generic names, else from a patient text shared with
        # labels that have one (identical core text). Never from reading names in the text.
        by_text: dict[str, Counter[str]] = defaultdict(Counter)
        for r in self.labels:
            if r["generic_names"]:
                key = "|".join(sorted({g.strip().lower() for g in r["generic_names"]}))
                r["medicine_key"], r["medicine_key_source"] = key, "openfda"
                for k in PAIRING:
                    if r[f"t_{k}_id"]:
                        by_text[r[f"t_{k}_id"]][key] += 1
            else:
                r["medicine_key"], r["medicine_key_source"] = None, None
        for r in self.labels:
            if r["medicine_key"]:
                continue
            for k in PAIRING:
                tid = r[f"t_{k}_id"]
                if tid and by_text.get(tid):
                    r["medicine_key"] = by_text[tid].most_common(1)[0][0]
                    r["medicine_key_source"] = "shared_text"
                    break
            else:
                r["medicine_key_source"] = "none"
        for r in self.labels:
            r.update(listed.flags(self.listings, r["set_id"], r["id"], r["version"]))
        self.stats["listed_sources"] = self.listings.sources
        self._configurations()
        self._patient_texts()
        self._write(
            "labels", [{k: v for k, v in r.items() if not k.startswith("_")} for r in self.labels]
        )

    def _configurations(self) -> None:
        """Each label's configuration and its measures from structure (see
        :mod:`plainpairs.structure`); without a structure table every one stays null."""
        if self.structure_dir is None:
            for r in self.labels:
                r.update(configuration=None, structure_source=None, unlisted_reason=None)
                self.configuration[r["set_id"]] = None
            return
        index, rows = structure.read_structure(self.structure_dir)
        decided = structure.decide(self.labels, index, rows)
        by_section = {(x["set_id"], x["section"]): x["structured"] for x in rows}
        counts: Counter[str] = Counter()
        for r in self.labels:
            d = decided[r["set_id"]]
            r.update(d)
            self.configuration[r["set_id"]] = d["configuration"]
            counts[f"configuration:{d['configuration']}"] += 1
            counts[f"unlisted_reason:{d['unlisted_reason']}"] += bool(d["unlisted_reason"])
            current = d["configuration"] == "current"
            sid = r["set_id"].lower()
            for s in PRESCRIBER:
                r[f"p_{s}_structured"] = by_section.get((sid, s)) if current else None
            for k in PATIENT:
                r[f"t_{k}_structured"] = by_section.get((sid, k)) if current else None
        summary = json.loads(
            (self.structure_dir / "structure_summary.json").read_text(encoding="utf-8")
        )
        self.stats["structure"] = {
            "release_date": summary.get("release_date"),
            "counts": dict(counts),
        }

    def _patient_texts(self) -> None:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in self.labels:
            for k in PATIENT:
                if r[f"t_{k}_id"]:
                    groups[r[f"t_{k}_id"]].append(r)
        rows = []
        for tid, members in groups.items():
            kind = tid.split(":", 1)[0]
            members.sort(key=lambda r: (r["set_id"], r["version"] or 0))
            exact = Counter(m[f"_{kind}_exact"] for m in members)
            top = exact.most_common(1)[0][0]
            rep = next(m for m in members if m[f"_{kind}_exact"] == top)
            makers = [m["manufacturers"] for m in members if m["manufacturers"]]
            current = [m for m in members if m.get("configuration") == "current"]
            # measures from structure: a current label with the representative's exact text,
            # else any current label
            source = next((m for m in current if m[f"_{kind}_exact"] == top), None) or (
                current[0] if current else None
            )
            conf = _text_configuration(self.structure_dir is not None, bool(current))
            rows.append(
                {
                    "source": SOURCE,
                    "export_date": self.export_date,
                    "set_id": rep["set_id"],
                    "version": rep["version"],
                    "patient_text_id": tid,
                    "kind": kind,
                    "core_hash": tid.split(":", 1)[1],
                    "n_labels": len(members),
                    "n_exact_variants": len(exact),
                    "n_loose_variants": len({m[f"_{kind}_loose"] for m in members}),
                    "set_ids": [m["set_id"] for m in members],
                    "n_manufacturers_known": len({x for ms in makers for x in ms}),
                    "n_labels_without_manufacturer": len(members) - len(makers),
                    "crosses_makers": len({x for ms in makers for x in ms}) > 1,
                    "medicine_keys": sorted(
                        {m["medicine_key"] for m in members if m["medicine_key"]}
                    ),
                    "has_copyright_mark_any": any(m["has_copyright_mark"] for m in members),
                    "headings_found": rep.get(f"_{kind}_headings", []),
                    "measures": rep[f"t_{kind}"],
                    "configuration": conf,
                    "n_labels_current": len(current),
                    "measures_structured": source[f"t_{kind}_structured"] if source else None,
                }
            )
        self._write("patient_texts", rows)

    def _write(self, name: str, rows: list[dict[str, Any]]) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        pq.write_table(
            pa.Table.from_pylist(rows, SCHEMAS[name]),
            self.out / f"{name}.parquet",
            compression="zstd",
        )
        self.stats.setdefault("rows", {})[name] = len(rows)
        self.log(f"wrote {name}: {len(rows):,} rows")

    # -- pass 2: table C ---------------------------------------------------------------------
    def pairs_part(
        self, number: int, path: Path, idf: dict[str, float], default_idf: float
    ) -> dict[str, Any]:
        """Pass 2 over one part: the section pairs of its labels in scope, to a part file."""
        rows: list[dict[str, Any]] = []
        for record in bulk.iter_labels(path):
            if record.get("set_id") not in self.in_scope_ids:
                continue
            try:
                row = label.parse_label(record)
            except label.LabelError:  # pragma: no cover - refused in pass 1 already
                continue
            if not in_scope(row):  # pragma: no cover - the same rule as pass 1
                continue
            rows += self._pairs(row, idf, default_idf)
        parts_dir = self.out / "_parts"
        parts_dir.mkdir(parents=True, exist_ok=True)
        pq.write_table(
            pa.Table.from_pylist(rows, SECTION_PAIRS_SCHEMA),
            parts_dir / f"section_pairs-{number:02d}.parquet",
            compression="zstd",
        )
        return {"number": number, "rows": len(rows)}

    def pass2(self) -> None:
        idf = align.idf_table(self.df, self.n_docs)
        default_idf = max(idf.values(), default=1.0)
        ids = frozenset(self.in_scope_ids)
        conf = dict(self.configuration)
        rules = dict(self.rule_status)
        jobs = [
            (n, p, self.out, self.export_date, ids, idf, default_idf, conf, rules)
            for n, p in self.parts
        ]
        n = 0
        for res in self._map(_pairs_job, jobs):
            n += res["rows"]
            self.log(f"pass 2: part {res['number']} read; {n:,} segments so far")
        self._merge_parts(("section_pairs",))
        self.stats.setdefault("rows", {})["section_pairs"] = n

    def _pairs(
        self, row: LabelRow, idf: dict[str, float], default_idf: float
    ) -> list[dict[str, Any]]:
        ident = row.identity
        sections = {s: getattr(row.prescriber, s) for s in PRESCRIBER if getattr(row.prescriber, s)}
        out = []
        for kind in PAIRING:
            t = getattr(row.patient, kind)
            if not t:
                continue
            spans = [s for s in text.segment_spans(t) if s[0] != "preamble"]
            segs = [(key, t[head_end:end]) for key, _start, head_end, end in spans]
            sec_counts, seg_counts = align.label_counts(sections, segs)
            tid = f"{kind}:{text.core_hash(t)}"
            for i, ((key, start, head_end, end), (_k, counts)) in enumerate(
                zip(spans, seg_counts, strict=True)
            ):
                pair = align.score(key, counts, sec_counts, idf, default_idf)
                out.append(
                    {
                        "source": SOURCE,
                        "export_date": self.export_date,
                        "set_id": ident.set_id,
                        "version": ident.version,
                        "kind": kind,
                        "patient_text_id": tid,
                        "segment_index": i,
                        "heading_key": key,
                        "heading_template": text.heading_template(t[start:head_end].strip(), key),
                        "seg_start": start,
                        "heading_end": head_end,
                        "seg_end": end,
                        "measures": measures(t[head_end:end], [], 0),
                        **pair,
                        "rule_status": self.rule_status.get(key, "pending_hand_check"),
                        "configuration": self.configuration.get(ident.set_id),
                    }
                )
        return out

    def run(self) -> dict[str, Any]:
        self.pass1()
        self.finish_records()
        self.pass2()
        parts_dir = self.out / "_parts"
        if parts_dir.exists() and not any(parts_dir.iterdir()):
            parts_dir.rmdir()
        (self.out / "build_summary.json").write_text(
            json.dumps(self.stats, indent=1, sort_keys=True, default=str), encoding="utf-8"
        )
        return self.stats


#: The rule status of a heading key once the hand sheet is scored (docs/method.md, section 7):
#: the mapping rule is released at 80% "yes" or "partly", otherwise only the similarity scores.
RULE_RELEASED = "rule_released"
SIMILARITY_ONLY = "similarity_only"


def rule_statuses(sheet_result: dict[str, Any]) -> dict[str, str]:
    """Heading key -> rule status, from ``plainpairs sheet-check --json`` output. A key that
    was not answered in full stays pending."""
    out = {}
    for key, r in sheet_result.items():
        if r.get("rule") == "regulation rule released":
            out[key] = RULE_RELEASED
        elif r.get("rule") == "similarity only, flagged":
            out[key] = SIMILARITY_ONLY
    return out


def _int32(v: int | None) -> int | None:
    """``v`` when it fits a 32-bit integer, else None."""
    return v if v is not None and -(2**31) <= v < 2**31 else None


def _text_configuration(have_structure: bool, any_current: bool) -> str | None:
    """A distinct patient text is ``current`` when one of its labels is (null without a
    structure table)."""
    if not have_structure:
        return None
    return "current" if any_current else "unlisted"


def _scan_job(job: tuple[Any, ...]) -> dict[str, Any]:
    number, path, out_dir, export_date = job
    return Builder([(number, path)], out_dir, export_date, log=lambda s: None).scan_part(
        number, path
    )


def _pairs_job(job: tuple[Any, ...]) -> dict[str, Any]:
    number, path, out_dir, export_date, ids, idf, default_idf, conf, rules = job
    b = Builder([(number, path)], out_dir, export_date, log=lambda s: None, rule_status=rules)
    b.in_scope_ids = set(ids)
    b.configuration = conf
    return b.pairs_part(number, path, idf, default_idf)


def parts_from_manifest(root: Path, export_date: str) -> list[tuple[int, Path]]:
    """The parts of one export, checked against the manifest by size and SHA-256."""
    rows = bulk.read_manifest(bulk.manifest_path(root, export_date))
    if not rows:
        raise bulk.BulkError(f"No manifest for the export of {export_date} under {root}.")
    out = []
    for name, row in sorted(rows.items(), key=lambda kv: int(kv[1]["part"])):
        path = root / export_date / name
        if not path.exists() or path.stat().st_size != int(row["bytes"]):
            raise bulk.BulkError(f"{path} is missing or has the wrong size; download it again.")
        if durable.sha256_file(path) != row["sha256"]:
            raise bulk.BulkError(f"{path} does not match its SHA-256 in the manifest.")
        out.append((int(row["part"]), path))
    of = {int(r["of"]) for r in rows.values()}
    if len(of) != 1 or len(out) != of.pop():
        raise bulk.BulkError(f"The manifest for {export_date} does not list every part.")
    return out


def read_table(out_dir: Path, name: str) -> pa.Table:
    return pq.read_table(Path(out_dir) / f"{name}.parquet")


def summarize(values: Iterable[float | None]) -> dict[str, float | None]:
    return _quantiles([v for v in values if v is not None])
