"""Aggregates of a built corpus, for reports. Counts, shares and quantiles only; no text."""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from plainpairs import release, tables


def q(values: list[float | None]) -> dict[str, Any]:
    v = sorted(x for x in values if x is not None)
    if not v:
        return {"n": 0}
    if len(v) == 1:
        return {"n": 1, "median": v[0], "p25": v[0], "p75": v[0]}
    qs = statistics.quantiles(v, n=4, method="inclusive")
    return {
        "n": len(v),
        "median": round(statistics.median(v), 2),
        "p25": round(qs[0], 2),
        "p75": round(qs[2], 2),
        "mean": round(statistics.fmean(v), 2),
    }


def corpus_stats(out_dir: Path) -> dict[str, Any]:
    out_dir = Path(out_dir)
    summary = json.loads((out_dir / "build_summary.json").read_text(encoding="utf-8"))
    labels = pq.read_table(out_dir / "labels.parquet").to_pylist()
    texts = pq.read_table(out_dir / "patient_texts.parquet").to_pylist()
    pairs = pq.read_table(
        out_dir / "section_pairs.parquet",
        columns=[
            "kind",
            "heading_key",
            "best_is_mapped",
            "best_section",
            "mapped_present",
            "best_similarity",
            "mapped_best_similarity",
            "patient_text_id",
        ],
    ).to_pylist()
    s: dict[str, Any] = {"export_date": summary["export_date"], "build": summary}

    # Corpus size.
    s["labels"] = len(labels)
    s["labels_by_format"] = dict(Counter(r["label_format"] for r in labels))
    s["labels_harmonized"] = sum(r["harmonized"] for r in labels)
    s["labels_with"] = {
        k: sum(r[f"has_{k}"] for r in labels)
        for k in (
            "medication_guide",
            "patient_package_insert",
            "instructions_for_use",
            "other_patient_text",
            "boxed_warning",
            "copyright_mark",
        )
    }
    s["labels_with"]["guide_and_insert"] = sum(
        r["has_medication_guide"] and r["has_patient_package_insert"] for r in labels
    )

    # Distinct patient texts and how labels share them.
    dup: dict[str, Any] = {}
    for kind in tables.PATIENT:
        group = [t for t in texts if t["kind"] == kind]
        if not group:
            continue
        sizes = Counter(t["n_labels"] for t in group)
        bands = Counter(
            "1"
            if n == 1
            else "2"
            if n == 2
            else "3-5"
            if n <= 5
            else "6-10"
            if n <= 10
            else "11-50"
            if n <= 50
            else "51+"
            for n in (t["n_labels"] for t in group)
        )
        shared = [t for t in group if t["n_labels"] > 1]
        dup[kind] = {
            "labels": sum(t["n_labels"] for t in group),
            "distinct_exact": sum(t["n_exact_variants"] for t in group),
            "distinct_loose": sum(t["n_loose_variants"] for t in group),
            "distinct_core": len(group),
            "shared_texts": len(shared),
            "labels_in_shared_texts": sum(t["n_labels"] for t in shared),
            "shared_crossing_makers": sum(t["crosses_makers"] for t in shared),
            "shared_with_any_label_without_maker": sum(
                t["n_labels_without_manufacturer"] > 0 for t in shared
            ),
            "largest_group": max(sizes),
            "group_size_bands": dict(sorted(bands.items(), key=lambda kv: kv[0])),
        }
    s["duplicates"] = dup

    # Distinct medicines.
    src = Counter(r["medicine_key_source"] for r in labels)
    keys = {r["medicine_key"] for r in labels if r["medicine_key"]}
    keys_openfda = {r["medicine_key"] for r in labels if r["medicine_key_source"] == "openfda"}
    s["medicines"] = {
        "labels_by_key_source": dict(src),
        "distinct_keys": len(keys),
        "distinct_keys_from_openfda_alone": len(keys_openfda),
        "labels_without_key": src.get("none", 0),
        "distinct_core_texts_without_key": len(
            {
                r[f"t_{k}_id"]
                for r in labels
                if r["medicine_key_source"] == "none"
                for k in ("medication_guide", "patient_package_insert")
                if r[f"t_{k}_id"]
            }
        ),
    }

    # Measures, per side and section, by both sentence rules.
    m: dict[str, Any] = {}
    for side, names in (("p", tables.PRESCRIBER), ("t", tables.PATIENT)):
        for name in names:
            vals = [r[f"{side}_{name}"] for r in labels if r[f"{side}_{name}"]]
            if not vals:
                continue
            m[f"{'prescriber' if side == 'p' else 'patient'}.{name}"] = {
                "texts": len(vals),
                "words": q([v["words"] for v in vals]),
                "words_with_tables": q([v["words_with_tables"] for v in vals]),
                "fk": q([v["flesch_kincaid"] for v in vals]),
                "fk_s1": q([v["flesch_kincaid_s1"] for v in vals]),
                "smog": q([v["smog"] for v in vals]),
                "smog_s1": q([v["smog_s1"] for v in vals]),
                "fre": q([v["flesch_reading_ease"] for v in vals]),
                "long_sentence_share": q([v["long_sentence_share"] for v in vals]),
                "numbers": q([v["numbers"] for v in vals]),
                "percentages": q([v["percentages"] for v in vals]),
                "headings": q([v["headings"] for v in vals]),
                "with_tables_cut": sum(1 for v in vals if v["table_chars_cut"]),
                "fk_above_8": round(
                    sum(1 for v in vals if (v["flesch_kincaid"] or 0) > 8) / len(vals), 4
                ),
                "fk_s1_above_8": round(
                    sum(1 for v in vals if (v["flesch_kincaid_s1"] or 0) > 8) / len(vals), 4
                ),
                "smog_above_8": round(sum(1 for v in vals if (v["smog"] or 0) > 8) / len(vals), 4),
            }
    s["measures"] = m
    # The same, over distinct patient texts (table B), so shared texts count once.
    s["measures_distinct_texts"] = {
        kind: {
            "texts": len(vals),
            "fk": q([v["flesch_kincaid"] for v in vals]),
            "fk_s1": q([v["flesch_kincaid_s1"] for v in vals]),
            "smog": q([v["smog"] for v in vals]),
            "fk_above_8": round(
                sum(1 for v in vals if (v["flesch_kincaid"] or 0) > 8) / len(vals), 4
            ),
        }
        for kind in tables.PATIENT
        if (vals := [t["measures"] for t in texts if t["kind"] == kind and t["measures"]])
    }

    # Headings found in guides and inserts (per distinct text).
    heads: dict[str, Any] = {}
    for kind in tables.PAIRING:
        group = [t for t in texts if t["kind"] == kind]
        c = Counter(h for t in group for h in t["headings_found"])
        n = Counter(len(t["headings_found"]) for t in group)
        heads[kind] = {
            "distinct_texts": len(group),
            "share_with_heading": {k: round(v / len(group), 4) for k, v in sorted(c.items())},
            "standard_headings_per_text": dict(sorted(n.items())),
        }
    s["headings"] = heads

    # Alignment.
    al: dict[str, Any] = {}
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in pairs:
        by_key[p["heading_key"]].append(p)
    for key, ps in sorted(by_key.items()):
        with_mapped = [p for p in ps if p["mapped_present"]]
        distinct = {p["patient_text_id"] for p in ps}
        al[key] = {
            "segments": len(ps),
            "segments_in_distinct_texts": len(distinct),
            "with_a_mapped_section_present": len(with_mapped),
            "share_best_is_mapped": round(
                sum(p["best_is_mapped"] for p in with_mapped) / len(with_mapped), 4
            )
            if with_mapped
            else None,
            "best_section_top": Counter(p["best_section"] for p in ps).most_common(4),
            "best_similarity": q([p["best_similarity"] for p in ps]),
            "mapped_best_similarity": q([p["mapped_best_similarity"] for p in with_mapped]),
        }
    s["alignment"] = al
    s["section_pairs"] = len(pairs)

    # What each switch setting would release.
    sw: dict[str, Any] = {}
    for name in tables.TEXT_TABLES:
        t = pq.read_table(
            out_dir / f"{name}.parquet",
            columns=["set_id", "has_copyright_mark", "text_has_copyright_mark", "part"],
        )
        sw[name] = {
            "rows": t.num_rows,
            "text_rows": sum(1 for p in t["part"].to_pylist() if p == "text"),
            "rows_of_marked_labels": sum(t["has_copyright_mark"].to_pylist()),
            "rows_whose_own_text_is_marked": sum(t["text_has_copyright_mark"].to_pylist()),
        }
        for setting in release.SWITCH:
            chosen = release.select(t, setting, allow_marked=True)
            sw[name][f"released:{setting}"] = chosen.num_rows
    sw["labels_released_unmarked"] = sum(not r["has_copyright_mark"] for r in labels)
    s["switch"] = sw
    return s
