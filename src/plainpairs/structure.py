"""Text structure from DailyMed's release, joined to the corpus by set id and version.

One pass over the parts of DailyMed's full human prescription release (in parallel, one part per
worker; see :mod:`plainpairs.spl_release` for the download):

- every label XML is read for its identity (set id, version, document id); the **index** has one
  row per document, with whether its set id is in the corpus and whether its version is the
  corpus version;
- for a document whose set id and version both match a corpus label, the sections the corpus
  uses are read into blocks (:mod:`plainpairs.spl`). The **blocks** table keeps them (label
  text: internal, like the text layer, never part of the record layer);
- each such section is compared with the same section's JSON text, word for word after the same
  cleaning (:func:`plainpairs.spl.word_match`), and measured from its structure. The
  **structure** table has one row per label and section: the match, the token counts, the
  measures from structure and the length codes from structure. It holds counts only.

:func:`decide` then sets each label's configuration: ``current`` when DailyMed's release holds
it in the same version and every patient text of the label is there with the same words
(exactly or nearly), ``unlisted`` otherwise, with the reason.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from plainpairs import readability, spl, spl_release

#: Patient texts whose words must agree for a label to be ``current``.
PATIENT_KINDS = (
    "medication_guide",
    "patient_package_insert",
    "instructions_for_use",
    "patient_medication_information",
)
CONFIGURATIONS = ("current", "unlisted")
#: Why a label is not ``current``, in the order they are tested.
UNLISTED_REASONS = (
    "not_in_release",  # DailyMed's release has no document with this set id
    "other_version",  # it has the set id, in another version
    "patient_text_missing",  # a patient text of the JSON has no section in the XML
    "patient_text_differs",  # a patient text's words differ materially (match "not")
)

INDEX_SCHEMA = pa.schema(
    [
        ("release_date", pa.string()),
        ("part", pa.string()),
        ("member", pa.string()),
        ("xml_name", pa.string()),
        ("set_id", pa.string()),
        ("version", pa.int32()),
        ("document_id", pa.string()),
        ("effective_time", pa.string()),
        ("document_type", pa.string()),
        ("in_corpus", pa.bool_()),
        ("corpus_version", pa.int32()),
        ("version_match", pa.bool_()),
        ("fields", pa.list_(pa.string())),
        ("parse_error", pa.string()),
    ]
)
BLOCKS_SCHEMA = pa.schema(
    [
        ("set_id", pa.string()),
        ("version", pa.int32()),
        ("section", pa.string()),
        ("block_index", pa.int32()),
        ("kind", pa.string()),
        ("depth", pa.int16()),
        ("list_depth", pa.int16()),
        ("table", pa.int16()),
        ("text", pa.string()),
    ]
)
#: Measures and length codes from structure, per label and section (counts only).
STRUCTURED = pa.struct(
    [
        ("xml_match", pa.string()),
        ("xml_dice", pa.float32()),
        ("xml_tokens", pa.int32()),
        ("json_tokens", pa.int32()),
        ("words", pa.int32()),
        ("sentences", pa.int32()),
        ("syllables", pa.int32()),
        ("polysyllables", pa.int32()),
        ("long_sentence_share", pa.float32()),
        ("numbers", pa.int32()),
        ("percentages", pa.int32()),
        ("flesch_kincaid", pa.float32()),
        ("flesch_reading_ease", pa.float32()),
        ("smog", pa.float32()),
        ("smog_short_text", pa.bool_()),
        ("blocks_title", pa.int32()),
        ("blocks_heading", pa.int32()),
        ("blocks_paragraph", pa.int32()),
        ("blocks_item", pa.int32()),
        ("blocks_cell", pa.int32()),
        ("blocks_caption", pa.int32()),
        ("blocks_data_cell", pa.int32()),
        ("subsection_titles", pa.int32()),
        ("sentences_over_20", pa.int32()),
        ("sentences_over_40", pa.int32()),
        ("longest_sentence_words", pa.int32()),
        ("parts", pa.int32()),
        ("longest_part_words", pa.int32()),
        ("parts_over_250", pa.int32()),
    ]
)
STRUCTURE_SCHEMA = pa.schema(
    [
        ("set_id", pa.string()),
        ("version", pa.int32()),
        ("section", pa.string()),
        ("side", pa.string()),
        ("structured", STRUCTURED),
    ]
)
_MEASURE_KEYS = [f.name for f in STRUCTURED][4:]


def length_codes(blocks: list[spl.Block]) -> dict[str, int]:
    """Length codes from structure: sentence lengths over the units, and the length of each
    part of the text between two headings or titles (the structure's own sections)."""
    lengths = [len(readability.words(u)) for u in spl.units(blocks)]
    parts: list[int] = [0]
    for b in blocks:
        if b.kind in ("title", "heading"):
            if parts[-1]:
                parts.append(0)
        elif b.kind in spl.PROSE_KINDS:
            parts[-1] += sum(len(readability.words(u)) for u in readability.sentences(b.text, "s1"))
    parts = [p for p in parts if p]
    return {
        "sentences_over_20": sum(n > readability.LONG_SENTENCE for n in lengths),
        "sentences_over_40": sum(n > 40 for n in lengths),
        "longest_sentence_words": max(lengths, default=0),
        "parts": len(parts),
        "longest_part_words": max(parts, default=0),
        "parts_over_250": sum(p > 250 for p in parts),
    }


def structured_row(blocks: list[spl.Block], json_text: str | None) -> dict[str, Any]:
    """The ``structured`` struct of one section: the word match with the JSON, and (when the
    words agree exactly or nearly) the measures and length codes from structure."""
    m = spl.word_match(spl.all_text(blocks), json_text or "")
    out: dict[str, Any] = {
        "xml_match": m["match"] if json_text else "json_missing",
        "xml_dice": m["dice"],
        "xml_tokens": m["xml_tokens"],
        "json_tokens": m["json_tokens"],
        **dict.fromkeys(_MEASURE_KEYS),
    }
    if out["xml_match"] in ("exact", "near"):
        out.update(spl.measure(blocks))
        out.update(length_codes(blocks))
    return {k: out.get(k) for k in [f.name for f in STRUCTURED]}


# --- one part ---------------------------------------------------------------------------------


def _json_texts(tables_dir: Path, ids: list[str]) -> dict[tuple[str, str], str]:
    """The JSON text of each (set id, section) of ``ids``, read in batches (low memory)."""
    import pyarrow.compute as pc

    out: dict[tuple[str, str], str] = {}
    if not ids:
        return out
    wanted = pa.array(ids)
    for name in ("text_patient", "text_prescriber"):
        pf = pq.ParquetFile(Path(tables_dir) / f"{name}.parquet")
        for batch in pf.iter_batches(
            batch_size=5000, columns=["set_id", "section", "part", "text"]
        ):
            mask = pc.and_(
                pc.is_in(batch["set_id"], value_set=wanted), pc.equal(batch["part"], "text")
            )
            for r in batch.filter(mask).to_pylist():
                out[(r["set_id"], r["section"])] = r["text"]
    return out


def read_part(
    part_path: Path,
    release_date: str,
    corpus: dict[str, int | None],
    tables_dir: Path,
    out_dir: Path,
) -> dict[str, Any]:
    """Read one part: its index rows, and blocks and structure rows for the matched labels."""
    counts: Counter[str] = Counter()
    index: list[dict[str, Any]] = []
    blocks_rows: list[dict[str, Any]] = []
    matched: dict[str, tuple[int | None, dict[str, list[spl.Block]]]] = {}
    codes_seen: Counter[str] = Counter()
    name = Path(part_path).name
    for doc in spl_release.iter_documents(part_path, counts):
        row: dict[str, Any] = {
            "release_date": release_date,
            "part": name,
            "member": doc.member,
            "xml_name": doc.xml_name,
            **dict.fromkeys(
                ("set_id", "version", "document_id", "effective_time", "document_type")
            ),
            "in_corpus": False,
            "corpus_version": None,
            "version_match": False,
            "fields": [],
            "parse_error": None,
        }
        try:
            parsed = spl.parse_document(
                doc.xml,
                keep=lambda i: i["set_id"] in corpus and corpus[i["set_id"]] == i["version"],
            )
        except spl.SplError as exc:
            row["parse_error"] = str(exc)[:200]
            counts["parse_errors"] += 1
            index.append(row)
            continue
        ident = {k: parsed[k] for k in spl.IDENTITY}
        row.update(ident)
        sid = ident["set_id"]
        if sid in corpus:
            row["in_corpus"] = True
            row["corpus_version"] = corpus[sid]
            row["version_match"] = ident["version"] == corpus[sid]
        if row["version_match"]:
            codes_seen.update(parsed["codes"])
            row["fields"] = sorted(parsed["fields"])
            sections = spl.section_blocks(parsed["fields"])
            if sid in matched:
                counts["duplicate_matched_documents"] += 1
            matched[sid] = (ident["version"], sections)
        index.append(row)
    texts = _json_texts(tables_dir, sorted(matched))
    structure_rows: list[dict[str, Any]] = []
    for sid, (version, sections) in sorted(matched.items()):
        names = set(sections) | {s for (i, s) in texts if i == sid}
        for section in sorted(names):
            blocks = sections.get(section, [])
            side = "patient" if section in PATIENT_KINDS else "prescriber"
            if not blocks:
                structured = {k: None for k in [f.name for f in STRUCTURED]}
                structured["xml_match"] = "xml_missing"
            else:
                structured = structured_row(blocks, texts.get((sid, section)))
                for i, b in enumerate(blocks):
                    blocks_rows.append(
                        {
                            "set_id": sid,
                            "version": version,
                            "section": section,
                            "block_index": i,
                            "kind": b.kind,
                            "depth": b.depth,
                            "list_depth": b.list_depth,
                            "table": b.table,
                            "text": b.text,
                        }
                    )
            structure_rows.append(
                {
                    "set_id": sid,
                    "version": version,
                    "section": section,
                    "side": side,
                    "structured": structured,
                }
            )
    parts_dir = Path(out_dir) / "_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    stem = name.removesuffix(".zip")
    pq.write_table(pa.Table.from_pylist(index, INDEX_SCHEMA), parts_dir / f"index-{stem}.parquet")
    pq.write_table(
        pa.Table.from_pylist(blocks_rows, BLOCKS_SCHEMA),
        parts_dir / f"blocks-{stem}.parquet",
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pylist(structure_rows, STRUCTURE_SCHEMA),
        parts_dir / f"structure-{stem}.parquet",
    )
    return {"part": name, "counts": dict(counts), "codes": dict(codes_seen), "docs": len(index)}


def _job(job: tuple[Any, ...]) -> dict[str, Any]:
    return read_part(*job)


def build(
    parts: list[Path],
    release_date: str,
    tables_dir: Path,
    out_dir: Path,
    workers: int = 1,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Read every part and write ``index``, ``blocks`` and ``structure`` to ``out_dir``."""
    labels = pq.read_table(Path(tables_dir) / "labels.parquet", columns=["set_id", "version"])
    corpus = {r["set_id"].lower(): r["version"] for r in labels.to_pylist()}
    out_dir = Path(out_dir)
    jobs = [(p, release_date, corpus, Path(tables_dir), out_dir) for p in parts]
    summary: dict[str, Any] = {"release_date": release_date, "parts": [], "counts": Counter()}
    codes: Counter[str] = Counter()
    if workers <= 1:
        results = map(_job, jobs)
    else:
        from concurrent.futures import ProcessPoolExecutor

        pool = ProcessPoolExecutor(max_workers=workers)
        results = pool.map(_job, jobs)
    try:
        for res in results:
            summary["parts"].append({"part": res["part"], "docs": res["docs"]})
            summary["counts"].update(res["counts"])
            codes.update(res["codes"])
            log(f"structure: {res['part']} read ({res['docs']:,} documents)")
    finally:
        if workers > 1:
            pool.shutdown()
    parts_dir = out_dir / "_parts"
    for name, schema in (
        ("index", INDEX_SCHEMA),
        ("blocks", BLOCKS_SCHEMA),
        ("structure", STRUCTURE_SCHEMA),
    ):
        files = sorted(parts_dir.glob(f"{name}-*.parquet"))
        with pq.ParquetWriter(out_dir / f"{name}.parquet", schema, compression="zstd") as w:
            for f in files:
                w.write_table(pq.read_table(f))
        for f in files:
            f.unlink()
    if parts_dir.exists() and not any(parts_dir.iterdir()):
        parts_dir.rmdir()
    summary["counts"] = dict(summary["counts"])
    summary["section_codes_in_matched_documents"] = dict(codes.most_common())
    (out_dir / "structure_summary.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8"
    )
    return summary


# --- the configuration of each label --------------------------------------------------------


def decide(
    labels: list[dict[str, Any]], index: list[dict[str, Any]], structure: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Each label's configuration, structure source and (for ``unlisted``) the reason.

    ``labels`` are rows with ``set_id``, ``version`` and ``t_<kind>_sha256`` for the patient
    texts; ``index`` and ``structure`` are rows of the tables :func:`build` writes.
    """
    in_release: dict[str, set[int | None]] = {}
    for r in index:
        if r["set_id"]:
            in_release.setdefault(r["set_id"], set()).add(r["version"])
    sections: dict[tuple[str, str], dict[str, Any]] = {
        (r["set_id"], r["section"]): r["structured"] for r in structure
    }
    out: dict[str, dict[str, Any]] = {}
    for lab in labels:
        sid = lab["set_id"].lower()
        reason = None
        if sid not in in_release:
            reason = "not_in_release"
        elif lab["version"] not in in_release[sid]:
            reason = "other_version"
        else:
            for k in PATIENT_KINDS:
                if not lab.get(f"t_{k}_sha256"):
                    continue
                s = sections.get((sid, k))
                if s is None or s["xml_match"] == "xml_missing":
                    reason = "patient_text_missing"
                    break
                if s["xml_match"] not in ("exact", "near"):
                    reason = "patient_text_differs"
                    break
        out[lab["set_id"]] = {
            "configuration": "unlisted" if reason else "current",
            "structure_source": "json" if reason else "dailymed_xml",
            "unlisted_reason": reason,
        }
    return out


def read_structure(out_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The index and structure rows written by :func:`build` (counts only, no text)."""
    index = pq.read_table(
        Path(out_dir) / "index.parquet", columns=["set_id", "version", "version_match"]
    ).to_pylist()
    structure = pq.read_table(Path(out_dir) / "structure.parquet").to_pylist()
    return index, structure
