"""Aggregates of a built corpus, for reports. Counts, shares and quantiles only; no text."""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from plainpairs import codes, release, sheet, tables


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
            "measures",
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

    # Reading measures, per configuration and never pooled across them: for `current`
    # labels from structure and, for the same labels, from the JSON; for `unlisted` labels
    # from the JSON only. A build without a structure table has one group, `no_configuration`.
    confs = sorted({r["configuration"] or "no_configuration" for r in labels})
    m: dict[str, Any] = {}
    for side, names in (("p", tables.PRESCRIBER), ("t", tables.PATIENT)):
        for name in names:
            key = f"{'prescriber' if side == 'p' else 'patient'}.{name}"
            for conf in confs:
                group = [r for r in labels if (r["configuration"] or "no_configuration") == conf]
                vals = [r[f"{side}_{name}"] for r in group if r[f"{side}_{name}"]]
                if not vals:
                    continue
                entry: dict[str, Any] = {"json": json_measures(vals)}
                if conf == "current":
                    both = [
                        r
                        for r in group
                        if r[f"{side}_{name}"]
                        and (r.get(f"{side}_{name}_structured") or {}).get("sentences") is not None
                    ]
                    entry["structured"] = structured_measures(
                        [r[f"{side}_{name}_structured"] for r in both]
                    )
                    entry["json_same_labels"] = json_measures([r[f"{side}_{name}"] for r in both])
                m.setdefault(key, {})[conf] = entry
    s["measures"] = m
    # The same over distinct patient texts (table B), so shared texts count once.
    d: dict[str, Any] = {}
    for kind in tables.PATIENT:
        for conf in confs:
            group = [
                t
                for t in texts
                if t["kind"] == kind and (t["configuration"] or "no_configuration") == conf
            ]
            vals = [t["measures"] for t in group if t["measures"]]
            if not vals:
                continue
            entry = {"json": json_measures(vals)}
            if conf == "current":
                both = [
                    t
                    for t in group
                    if t["measures"]
                    and (t["measures_structured"] or {}).get("sentences") is not None
                ]
                entry["structured"] = structured_measures([t["measures_structured"] for t in both])
                entry["json_same_texts"] = json_measures([t["measures"] for t in both])
            d.setdefault(kind, {})[conf] = entry
    s["measures_distinct_texts"] = d
    s["configurations"] = {
        "labels": dict(Counter(r["configuration"] or "no_configuration" for r in labels)),
        "unlisted_reasons": dict(
            Counter(r["unlisted_reason"] for r in labels if r["unlisted_reason"])
        ),
        "distinct_texts": {
            kind: dict(
                Counter(
                    t["configuration"] or "no_configuration" for t in texts if t["kind"] == kind
                )
            )
            for kind in tables.PATIENT
        },
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
            "empty_segments": sum(1 for p in ps if not (p["measures"] or {}).get("words")),
            "one_line_segments": sum(1 for p in ps if not sheet._long_enough(p)),
            "best_section_top": Counter(p["best_section"] for p in ps).most_common(4),
            "best_similarity": q([p["best_similarity"] for p in ps]),
            "mapped_best_similarity": q([p["mapped_best_similarity"] for p in with_mapped]),
        }
    s["alignment"] = al
    s["section_pairs"] = len(pairs)
    s["section_pairs_empty"] = sum(a["empty_segments"] for a in al.values())
    s["restated_headings_merged"] = {
        k.split(":", 1)[1]: v
        for k, v in summary.get("counts", {}).items()
        if k.startswith("restated_headings:")
    }
    s["product_names"] = product_name_stats(labels)
    s["listed"] = listed_stats(labels, summary.get("listed_sources", {}))

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
    s["codes"] = codes_stats(out_dir)
    s["nci"] = nci_stats(out_dir)
    return s


def _norm(name: str) -> str:
    return " ".join(name.split()).casefold()


def product_name_stats(labels: list[dict[str, Any]]) -> dict[str, Any]:
    """Labels named from their product data, distinct names, agreement with openfda names."""
    if not labels or "product_name" not in labels[0]:
        return {}
    named = [r for r in labels if r["product_name"]]
    both = [r for r in named if r["brand_names"]]
    agree = [r for r in both if _norm(r["product_name"]) in {_norm(b) for b in r["brand_names"]}]
    by_rule = Counter(r["product_name_rule"] for r in named)
    rule_agree = Counter(r["product_name_rule"] for r in agree)
    rule_both = Counter(r["product_name_rule"] for r in both)
    halves = {}
    for half, rows in (
        ("with_openfda", [r for r in labels if r["harmonized"]]),
        ("without_openfda", [r for r in labels if not r["harmonized"]]),
    ):
        got = [r for r in rows if r["product_name"]]
        halves[half] = {
            "labels": len(rows),
            "named": len(got),
            "distinct_names": len({_norm(r["product_name"]) for r in got}),
        }
    return {
        "labels_named": len(named),
        "labels_not_named": len(labels) - len(named),
        "by_rule": dict(by_rule),
        "distinct_product_names": len({_norm(r["product_name"]) for r in named}),
        "distinct_openfda_brand_names": len({_norm(b) for r in labels for b in r["brand_names"]}),
        "both_present": len(both),
        "agrees_with_an_openfda_brand_name": len(agree),
        "agreement_share": round(len(agree) / len(both), 4) if both else None,
        "agreement_by_rule": {
            k: round(rule_agree[k] / n, 4) for k, n in sorted(rule_both.items(), key=str) if n
        },
        "halves": halves,
    }


def listed_stats(labels: list[dict[str, Any]], sources: dict[str, Any]) -> dict[str, Any]:
    """Shares listed in the NDC directory and served by DailyMed: corpus and both halves."""
    if not labels or labels[0].get("listed_in_ndc_directory") is None:
        return {"sources": sources}

    def part(rows: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(rows)
        ndc = sum(bool(r["listed_in_ndc_directory"]) for r in rows)
        dm = sum(bool(r["served_by_dailymed"]) for r in rows)
        same = sum(
            bool(r["served_by_dailymed"]) and r["dailymed_version"] == r["version"] for r in rows
        )
        both = sum(bool(r["listed_in_ndc_directory"] and r["served_by_dailymed"]) for r in rows)
        neither = sum(
            not r["listed_in_ndc_directory"] and not r["served_by_dailymed"] for r in rows
        )
        return {
            "labels": n,
            "in_ndc_directory": ndc,
            "in_ndc_directory_share": round(ndc / n, 4) if n else None,
            "ndc_match": dict(Counter(r["ndc_match"] for r in rows)),
            "served_by_dailymed": dm,
            "served_by_dailymed_share": round(dm / n, 4) if n else None,
            "dailymed_same_version": same,
            "both": both,
            "neither": neither,
            "neither_share": round(neither / n, 4) if n else None,
        }

    return {
        "sources": sources,
        "corpus": part(labels),
        "with_openfda": part([r for r in labels if r["harmonized"]]),
        "without_openfda": part([r for r in labels if not r["harmonized"]]),
        "distinct_patient_texts": _texts_listed(labels),
    }


def _texts_listed(labels: list[dict[str, Any]]) -> dict[str, int]:
    """Distinct guides and inserts carried by at least one listed (or served) label."""
    out: dict[str, int] = {}
    for kind in tables.PAIRING:
        col = f"t_{kind}_id"
        all_ = {r[col] for r in labels if r[col]}
        ndc = {r[col] for r in labels if r[col] and r["listed_in_ndc_directory"]}
        dm = {r[col] for r in labels if r[col] and r["served_by_dailymed"]}
        out[kind] = len(all_)
        out[f"{kind}:on_a_label_in_ndc_directory"] = len(ndc)
        out[f"{kind}:on_a_label_served_by_dailymed"] = len(dm)
        out[f"{kind}:on_a_label_in_either"] = len(ndc | dm)
    return out


def _above(vals: list[dict[str, Any]], key: str, grade: float = 8) -> float | None:
    got = [v[key] for v in vals if v.get(key) is not None]
    return round(sum(1 for x in got if x > grade) / len(got), 4) if got else None


def json_measures(vals: list[dict[str, Any]]) -> dict[str, Any]:
    """Reading measures from the JSON text (both sentence rules), over the texts given."""
    return {
        "texts": len(vals),
        "words": q([v["words"] for v in vals]),
        "words_with_tables": q([v["words_with_tables"] for v in vals]),
        "sentences": q([v["sentences"] for v in vals]),
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
        "fk_above_8": _above(vals, "flesch_kincaid"),
        "fk_s1_above_8": _above(vals, "flesch_kincaid_s1"),
        "smog_above_8": _above(vals, "smog"),
    }


def structured_measures(vals: list[dict[str, Any]]) -> dict[str, Any]:
    """Reading measures from structure (every list item, paragraph and cell ends a sentence;
    titles, headings and data cells are not measured)."""
    return {
        "texts": len(vals),
        "words": q([v["words"] for v in vals]),
        "sentences": q([v["sentences"] for v in vals]),
        "fk": q([v["flesch_kincaid"] for v in vals]),
        "smog": q([v["smog"] for v in vals]),
        "fre": q([v["flesch_reading_ease"] for v in vals]),
        "long_sentence_share": q([v["long_sentence_share"] for v in vals]),
        "fk_above_8": _above(vals, "flesch_kincaid"),
        "smog_above_8": _above(vals, "smog"),
        "headings": q([v["blocks_heading"] for v in vals]),
        "list_items": q([v["blocks_item"] for v in vals]),
        "subsection_titles": q([v["subsection_titles"] for v in vals]),
        "matches": dict(Counter(v["xml_match"] for v in vals)),
    }


def _per_1000(num: int, words: int) -> float | None:
    return round(1000 * num / words, 2) if words else None


def _share(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def code_summary(t: pa.Table, kind: str) -> dict[str, Any]:
    """Shares and rates of the codes over the rows of ``t`` (one text each)."""
    n = t.num_rows
    if not n:
        return {"texts": 0}
    tot = {f: pc.sum(t[f]).as_py() or 0 for f in codes.FIELDS if f in t.column_names}

    def any_(f: str) -> float | None:
        return _share(pc.sum(pc.greater(t[f], 0)).as_py() or 0, n)

    def med(f: str) -> float | None:
        v = pc.quantile(t[f], q=0.5, interpolation="midpoint").to_pylist()
        return v[0] if v else None

    w = tot["words"]
    out = {
        "texts": n,
        "words": w,
        "you_per_1000_words": _per_1000(tot["you_words"], w),
        "texts_with_you": any_("you_words"),
        "sentences_with_you_share": _share(tot["sentences_with_you"], tot["sentences"]),
        "command_sentence_share": _share(tot["command_sentences"], tot["sentences"]),
        "conditional_command_share": _share(tot["conditional_commands"], tot["sentences"]),
        "distinct_actions_median": med("distinct_actions"),
        "texts_with_a_command": any_("command_sentences"),
        "percentages_per_1000_words": _per_1000(tot["percentages"], w),
        "one_in_n_per_1000_words": _per_1000(tot["one_in_n"], w),
        "texts_with_one_in_n": any_("one_in_n"),
        "frequencies_per_1000_words": _per_1000(tot["frequencies"], w),
        "doses_per_1000_words": _per_1000(tot["doses"], w),
        "risk_sentences": tot["risk_sentences"],
        "risk_sentences_with_number_share": _share(
            tot["risk_sentences_with_number"], tot["risk_sentences"]
        ),
        "vague_core_per_1000_words": _per_1000(tot["vague_core"], w),
        "vague_extended_per_1000_words": _per_1000(tot["vague_extended"], w),
        "explained_in_brackets_per_1000_words": _per_1000(tot["explained_in_brackets"], w),
        "explained_called_per_1000_words": _per_1000(tot["explained_called"], w),
        "texts_with_an_explained_term": _share(
            pc.sum(pc.greater(pc.add(t["explained_in_brackets"], t["explained_called"]), 0)).as_py()
            or 0,
            n,
        ),
        "abbreviations_in_brackets_per_1000_words": _per_1000(tot["abbreviations_in_brackets"], w),
        "sentences_over_20_share": _share(tot["sentences_over_20"], tot["sentences"]),
        "sentences_over_40_share": _share(tot["sentences_over_40"], tot["sentences"]),
        "longest_sentence_words_median": med("longest_sentence_words"),
        "texts_with_contact": any_("contact_sentences"),
        "contact_sentences_with_when_share": _share(
            tot["contact_sentences_with_when"], tot["contact_sentences"]
        ),
    }
    if kind == "patient":
        out["longest_section_words_median"] = med("longest_section_words")
        out["texts_with_a_section_over_250_words"] = any_("sections_over_250")
    if "structured_sentences" in t.column_names:
        st = t.filter(pc.is_valid(t["structured_sentences"]))
        if st.num_rows:
            sums = {f: pc.sum(st[f]).as_py() or 0 for f in codes.STRUCTURED_FIELDS}
            out["structured"] = {
                "texts": st.num_rows,
                "sentences_over_20_share": _share(
                    sums["structured_sentences_over_20"], sums["structured_sentences"]
                ),
                "sentences_over_40_share": _share(
                    sums["structured_sentences_over_40"], sums["structured_sentences"]
                ),
                "longest_sentence_words_median": pc.quantile(
                    st["structured_longest_sentence_words"], q=0.5, interpolation="midpoint"
                ).to_pylist()[0],
                "longest_part_words_median": pc.quantile(
                    st["structured_longest_part_words"], q=0.5, interpolation="midpoint"
                ).to_pylist()[0],
                "texts_with_a_part_over_250_words": _share(
                    pc.sum(pc.greater(st["structured_parts_over_250"], 0)).as_py() or 0,
                    st.num_rows,
                ),
            }
    return out


def codes_stats(out_dir: Path) -> dict[str, Any]:
    """The codes summarized: patient texts over distinct texts, prescriber sections over labels."""
    path = Path(out_dir) / "codes.parquet"
    if not path.exists():
        return {}
    t = pq.read_table(path)
    exp = Path(out_dir) / "codes_experimental.parquet"
    if exp.exists():  # the experimental codes, row for row; summarized here, never released
        x = pq.read_table(exp)
        for name in codes.EXPERIMENTAL:
            if name in x.column_names and name not in t.column_names:
                t = t.append_column(name, x[name])
    out: dict[str, Any] = {
        "code_version": codes.CODE_VERSION,
        "rows": t.num_rows,
        "status": {k: v for k, (_cols, v) in codes.CODEBOOK.items()},
    }
    pt = t.filter(pc.equal(t["side"], "patient"))
    # one row per distinct text: the first label that carries it
    ids = pt["patient_text_id"].to_pylist()
    first: dict[str, int] = {}
    for i, tid in enumerate(ids):
        first.setdefault(tid, i)
    distinct = pt.take(pa.array(sorted(first.values())))
    for kind in codes.PATIENT_KINDS:
        sub = distinct.filter(pc.equal(distinct["section"], kind))
        out[f"patient.{kind}"] = code_summary(sub, "patient")
    pr = t.filter(pc.equal(t["side"], "prescriber"))
    for section in sorted(set(pr["section"].to_pylist())):
        out[f"prescriber.{section}"] = code_summary(
            pr.filter(pc.equal(pr["section"], section)), "prescriber"
        )
    return out


# --- text from NCI's cancer information summaries (configuration nci; never pooled) ----------


def _med(values: list[float | None]) -> float | None:
    v = sorted(x for x in values if x is not None)
    return round(statistics.median(v), 4) if v else None


def nci_stats(out_dir: Path) -> dict[str, Any]:
    """Aggregates of the ``nci`` configuration: counts, measures per language and version,
    what the pairs show, and the trusted codes by version (English). Never pooled with the
    label configurations."""
    from plainpairs import nci

    path = Path(out_dir) / "nci_summaries.parquet"
    if not path.exists():
        return {}
    s = pq.read_table(path).to_pylist()
    pairs = pq.read_table(Path(out_dir) / "nci_pairs.parquet").to_pylist()
    by = {r["url"]: r for r in s}
    out: dict[str, Any] = {"configuration": nci.CONFIGURATION}
    out["summaries"] = dict(Counter(f"{r['language']}:{r['version']}" for r in s))
    out["pairs"] = dict(Counter(f"{p['pair_kind']}:{p['linked_from']}" for p in pairs))
    in_version = {u for p in pairs if p["pair_kind"] == "version" for u in (p["url_a"], p["url_b"])}
    in_language = {
        u for p in pairs if p["pair_kind"] == "language" for u in (p["url_a"], p["url_b"])
    }
    out["unpaired"] = {
        "no_version_partner": dict(
            Counter(f"{r['language']}:{r['version']}" for r in s if r["url"] not in in_version)
        ),
        "no_language_partner": dict(
            Counter(f"{r['language']}:{r['version']}" for r in s if r["url"] not in in_language)
        ),
    }
    out["left_out"] = {k: sum((r["left_out"] or {}).get(k, 0) for r in s) for k in nci.LEFT_OUT}
    out["references"] = sum(r["references"] or 0 for r in s)
    out["updated"] = {
        "missing": sum(1 for r in s if not r["nci_updated"]),
        "earliest": min((r["nci_updated"] for r in s if r["nci_updated"]), default=None),
        "latest": max((r["nci_updated"] for r in s if r["nci_updated"]), default=None),
    }
    m: dict[str, Any] = {}
    for key in sorted({f"{r['language']}:{r['version']}" for r in s}):
        group = [r["measures"] for r in s if f"{r['language']}:{r['version']}" == key]
        entry: dict[str, Any] = {
            "summaries": len(group),
            "words": q([g["words"] for g in group]),
            "sentences": q([g["sentences"] for g in group]),
            "long_sentence_share": q([g["long_sentence_share"] for g in group]),
        }
        if key.startswith("en:"):
            entry.update(
                fk=q([g["flesch_kincaid"] for g in group]),
                smog=q([g["smog"] for g in group]),
                fk_above_8=_above(group, "flesch_kincaid"),
                smog_above_8=_above(group, "smog"),
            )
        else:
            entry.update(
                szigriszt_pazos=q([g["szigriszt_pazos"] for g in group]),
                inflesz_bands=dict(Counter(g["inflesz_band"] for g in group)),
            )
        m[key] = entry
    out["measures"] = m
    show: dict[str, Any] = {}
    for lang in ("en", "es"):
        vp = [p for p in pairs if p["pair_kind"] == "version" and p["language"] == lang]
        hp = [by[p["url_a"]]["measures"] for p in vp]
        pt = [by[p["url_b"]]["measures"] for p in vp]
        entry = {
            "pairs": len(vp),
            "patient_over_professional_words": _med(
                [b["words"] / a["words"] for a, b in zip(hp, pt, strict=True) if a["words"]]
            ),
            "patient_long_sentence_share": _med([b["long_sentence_share"] for b in pt]),
            "professional_long_sentence_share": _med([a["long_sentence_share"] for a in hp]),
        }
        if lang == "en":
            for f in ("flesch_kincaid", "smog"):
                entry[f"{f}_professional"] = _med([a[f] for a in hp])
                entry[f"{f}_patient"] = _med([b[f] for b in pt])
                entry[f"{f}_difference_median"] = _med(
                    [
                        b[f] - a[f]
                        for a, b in zip(hp, pt, strict=True)
                        if a[f] is not None and b[f] is not None
                    ]
                )
                entry[f"{f}_patient_lower_share"] = _share(
                    sum(1 for a, b in zip(hp, pt, strict=True) if (b[f] or 99) < (a[f] or 0)),
                    len(vp),
                )
        else:
            f = "szigriszt_pazos"
            entry[f"{f}_professional"] = _med([a[f] for a in hp])
            entry[f"{f}_patient"] = _med([b[f] for b in pt])
            entry[f"{f}_difference_median"] = _med(
                [
                    b[f] - a[f]
                    for a, b in zip(hp, pt, strict=True)
                    if a[f] is not None and b[f] is not None
                ]
            )
        show[f"version_pairs:{lang}"] = entry
    for version in ("health_professional", "patient"):
        lp = [p for p in pairs if p["pair_kind"] == "language" and p["version"] == version]
        en = [by[p["url_a"]]["measures"] for p in lp]
        es = [by[p["url_b"]]["measures"] for p in lp]
        show[f"language_pairs:{version}"] = {
            "pairs": len(lp),
            "spanish_over_english_words": _med(
                [b["words"] / a["words"] for a, b in zip(en, es, strict=True) if a["words"]]
            ),
            "english_words_per_sentence": _med(
                [a["words"] / a["sentences"] for a in en if a["sentences"]]
            ),
            "spanish_words_per_sentence": _med(
                [b["words"] / b["sentences"] for b in es if b["sentences"]]
            ),
        }
    out["pairs_show"] = show
    rates: dict[str, Any] = {}
    for version in ("health_professional", "patient"):
        rows = [r for r in s if r["language"] == "en" and r["version"] == version and r["codes"]]
        words = sum(r["measures"]["words"] or 0 for r in rows)
        sents = sum(r["measures"]["sentences"] or 0 for r in rows)
        tot = {f: sum(r["codes"][f] for r in rows) for f in nci.CODE_FIELDS}
        rates[version] = {
            "summaries": len(rows),
            **{
                f"{f}_per_1000_words": _per_1000(tot[f], words)
                for f in ("you_words", "percentages", "one_in_n", "frequencies", "doses")
            },
            "sentences_with_you_share": _share(tot["sentences_with_you"], sents),
            "command_sentence_share": _share(tot["command_sentences"], sents),
            "conditional_command_share": _share(tot["conditional_commands"], sents),
            "contact_sentences_per_1000_words": _per_1000(tot["contact_sentences"], words),
            "sentences_over_20_share": _share(tot["sentences_over_20"], sents),
            "sentences_over_40_share": _share(tot["sentences_over_40"], sents),
            "distinct_actions_median": _med([r["codes"]["distinct_actions"] for r in rows]),
        }
    a, b = rates.get("health_professional", {}), rates.get("patient", {})
    ratio = {
        k: round(b[k] / a[k], 2)
        for k in a
        if k != "summaries" and isinstance(a.get(k), (int, float)) and a[k] and b.get(k) is not None
    }
    out["codes_by_version"] = {**rates, "patient_over_professional": ratio}
    return out
