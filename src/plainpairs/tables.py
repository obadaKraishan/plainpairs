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

from plainpairs import align, bulk, durable, label, readability, text
from plainpairs.schema import PATIENT_SOURCES, PRESCRIBER_SOURCES, LabelRow

SOURCE = "openFDA drug label bulk files (https://open.fda.gov/data/spl/)"
IN_SCOPE_FORMATS = ("plr", "older")
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
    return row.identity.label_format in IN_SCOPE_FORMATS and any(
        getattr(row.patient, k) for k in PAIRING
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
    ) -> None:
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

    def pass1(self) -> None:
        c: Counter[str] = Counter()
        errors: Counter[str] = Counter()
        identity: Counter[str] = Counter()
        excluded: list[dict[str, Any]] = []
        writers = {name: self._writer(name) for name in TEXT_TABLES}
        try:
            for number, path in self.parts:
                buf: dict[str, list[dict[str, Any]]] = {name: [] for name in TEXT_TABLES}
                for record in bulk.iter_labels(path):
                    c["labels_read"] += 1
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
                                    "has_patient_package_insert": bool(
                                        row.patient.patient_package_insert
                                    ),
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
                for name in TEXT_TABLES:
                    if buf[name]:
                        writers[name].write_table(pa.Table.from_pylist(buf[name], SCHEMAS[name]))
                self.log(f"pass 1: part {number} read; {c['in_scope']:,} labels in scope so far")
        finally:
            for w in writers.values():
                w.close()
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
        return fmt in IN_SCOPE_FORMATS and bool(has_text)

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
        self._patient_texts()
        self._write(
            "labels", [{k: v for k, v in r.items() if not k.startswith("_")} for r in self.labels]
        )

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
    def pass2(self) -> None:
        idf = align.idf_table(self.df, self.n_docs)
        default_idf = max(idf.values(), default=1.0)
        writer = pq.ParquetWriter(
            self.out / "section_pairs.parquet", SECTION_PAIRS_SCHEMA, compression="zstd"
        )
        n = 0
        try:
            for number, path in self.parts:
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
                writer.write_table(pa.Table.from_pylist(rows, SECTION_PAIRS_SCHEMA))
                n += len(rows)
                self.log(f"pass 2: part {number} read; {n:,} segments so far")
        finally:
            writer.close()
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
                        "rule_status": "pending_hand_check",
                    }
                )
        return out

    def run(self) -> dict[str, Any]:
        self.pass1()
        self.finish_records()
        self.pass2()
        (self.out / "build_summary.json").write_text(
            json.dumps(self.stats, indent=1, sort_keys=True, default=str), encoding="utf-8"
        )
        return self.stats


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
