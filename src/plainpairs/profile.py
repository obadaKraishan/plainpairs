"""What a set of labels holds, as aggregates only.

Nothing returned here contains label text: counts, shares, quantiles, field names, and
Medication Guide headings with the medicine's name taken out (only headings where the name
was found and replaced are reported).

- **Duplicates.** Patient texts are grouped by :func:`plainpairs.text.text_hash` (identical
  after spacing) and :func:`plainpairs.text.loose_hash` (identical after case, punctuation and
  spacing), with the number of manufacturers in each group where the source names them.
- **Lengths and reading level** of each prescriber section and patient text, in words, with
  Flesch-Kincaid and SMOG grades (:mod:`plainpairs.readability`).
- **Headings.** Which standard headings each Medication Guide has.
- **Alignment, a first look.** For each heading segment of a Medication Guide, the prescriber
  section of the same label whose words it shares most (cosine similarity of TF-IDF weighted
  word counts). This is a proposal to check by hand, not an alignment.
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from plainpairs import readability, text
from plainpairs.schema import LabelRow, PatientTexts, PrescriberSections

PRESCRIBER = tuple(PrescriberSections.model_fields)
PATIENT = tuple(PatientTexts.model_fields)
#: A copyright mark: the sign, the word, or "all rights reserved".
COPYRIGHT = re.compile(r"\u00a9|\bcopyright\b|all rights reserved", re.I)
_TOKEN = re.compile(r"[a-z]{3,}")
STOPWORDS = frozenset(
    (
        "the",
        "and",
        "for",
        "are",
        "with",
        "you",
        "your",
        "that",
        "this",
        "have",
        "has",
        "not",
        "may",
        "can",
        "been",
        "was",
        "were",
        "will",
        "from",
        "into",
        "than",
        "then",
        "them",
        "they",
        "their",
        "there",
        "these",
        "those",
        "which",
        "what",
        "when",
        "who",
        "how",
        "should",
        "would",
        "could",
        "about",
        "after",
        "before",
        "during",
        "while",
        "other",
        "such",
        "any",
        "all",
        "some",
        "each",
        "more",
        "most",
        "also",
        "only",
        "take",
        "taking",
        "use",
        "used",
        "using",
        "tell",
        "talk",
        "doctor",
        "healthcare",
        "provider",
    )
)


def quantiles(values: list[float]) -> dict[str, float | int | None]:
    """Count, median, quartiles and the 90th percentile of ``values``."""
    if not values:
        return {"n": 0, "median": None, "p25": None, "p75": None, "p90": None}
    v = sorted(values)
    if len(v) == 1:
        return {"n": 1, "median": v[0], "p25": v[0], "p75": v[0], "p90": v[0]}
    q = statistics.quantiles(v, n=20, method="inclusive")
    return {
        "n": len(v),
        "median": round(statistics.median(v), 2),
        "p25": round(q[4], 2),
        "p75": round(q[14], 2),
        "p90": round(q[17], 2),
    }


def tokens(s: str) -> list[str]:
    return [t for t in _TOKEN.findall(s.lower()) if t not in STOPWORDS]


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(w * b.get(t, 0.0) for t, w in a.items())
    na = math.sqrt(sum(w * w for w in a.values()))
    nb = math.sqrt(sum(w * w for w in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def _tfidf(counts: Counter[str], idf: dict[str, float]) -> dict[str, float]:
    return {t: (1 + math.log(n)) * idf.get(t, 0.0) for t, n in counts.items()}


def profile(rows: Iterable[LabelRow]) -> dict[str, Any]:
    """Aggregates over ``rows``; see the module docstring."""
    rows = list(rows)
    out: dict[str, Any] = {"labels": len(rows)}
    out["formats"] = dict(Counter(r.identity.label_format for r in rows))
    out["product_types"] = dict(Counter(r.identity.product_type or "(none)" for r in rows))
    out["set_ids"] = len({r.identity.set_id for r in rows})
    out["harmonized"] = sum(r.identity.harmonized for r in rows)

    # Labels with a copyright mark anywhere in the text this parser reads.
    marked: Counter[str] = Counter()
    for r in rows:
        sides = {
            "prescriber": " ".join(v for v in r.prescriber.model_dump().values() if v),
            "patient": " ".join(v for v in r.patient.model_dump().values() if v),
        }
        for side, s in sides.items():
            if COPYRIGHT.search(s):
                marked[side] += 1
    out["copyright_marks"] = {"labels_scanned": len(rows), **dict(marked)}

    # Duplicates of each patient text.
    dup: dict[str, Any] = {}
    for kind in PATIENT:
        exact: dict[str, list[LabelRow]] = defaultdict(list)
        loose: set[str] = set()
        cores: set[str] = set()
        for r in rows:
            t = getattr(r.patient, kind)
            if t:
                exact[text.text_hash(t)].append(r)
                loose.add(text.loose_hash(t))
                cores.add(text.core_hash(t))
        n = sum(len(g) for g in exact.values())
        shared = [g for g in exact.values() if len(g) > 1]
        multi_maker = [
            g for g in shared if len({m for r in g for m in r.identity.manufacturers}) > 1
        ]
        generic = {
            r.identity.generic_names for g in exact.values() for r in g if r.identity.generic_names
        }
        dup[kind] = {
            "labels": n,
            "distinct_texts_exact": len(exact),
            "distinct_texts_loose": len(loose),
            "distinct_texts_without_closing_matter": len(cores),
            "texts_shared_by_2_or_more_labels": len(shared),
            "labels_in_shared_texts": sum(len(g) for g in shared),
            "shared_texts_with_2_or_more_manufacturers": len(multi_maker),
            "largest_group": max((len(g) for g in exact.values()), default=0),
            "group_sizes": dict(sorted(Counter(len(g) for g in exact.values()).items())),
            "distinct_generic_name_sets": len(generic),
            "labels_without_generic_name": sum(
                1 for g in exact.values() for r in g if not r.identity.generic_names
            ),
        }
    out["duplicates"] = dup

    # Lengths and reading level, in the labels that have a Medication Guide or a patient
    # package insert (the pairs this corpus is about).
    paired = [r for r in rows if r.patient.medication_guide or r.patient.patient_package_insert]
    out["paired_labels"] = len(paired)
    measures: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    above8: Counter[str] = Counter()
    for r in paired:
        for side, model in (("prescriber", r.prescriber), ("patient", r.patient)):
            for name, value in model.model_dump().items():
                if not value:
                    continue
                m = readability.measure(value)
                key = f"{side}.{name}"
                measures[key]["words"].append(m.words)
                if m.flesch_kincaid_grade is not None:
                    measures[key]["fk"].append(m.flesch_kincaid_grade)
                    measures[key]["smog"].append(m.smog_grade or 0.0)
                    if side == "patient":
                        above8[f"{key}.fk_above_8"] += m.flesch_kincaid_grade > 8
                        above8[f"{key}.smog_above_8"] += (m.smog_grade or 0) > 8
    out["measures"] = {
        k: {stat: quantiles(vals) for stat, vals in v.items()} for k, v in sorted(measures.items())
    }
    out["patient_above_grade_8"] = {
        k: {"labels": int(n), "share": round(n / len(measures[k.rsplit(".", 1)[0]]["fk"]), 3)}
        for k, n in sorted(above8.items())
        if measures[k.rsplit(".", 1)[0]]["fk"]
    }

    # Headings of Medication Guides and patient package inserts.
    heads: dict[str, Any] = {}
    for kind in ("medication_guide", "patient_package_insert"):
        texts = [getattr(r.patient, kind) for r in paired if getattr(r.patient, kind)]
        has: Counter[str] = Counter()
        templates: dict[str, Counter[str]] = defaultdict(Counter)
        n_keys: Counter[int] = Counter()
        for t in texts:
            segs = text.segment_patient_text(t)
            keys = {s.key for s in segs} - {"preamble"}
            n_keys[len(keys)] += 1
            for k in keys:
                has[k] += 1
            for s in segs:
                if s.key != "preamble":
                    tpl = text.heading_template(s.heading, s.key)
                    if "[medicine]" in tpl:
                        templates[s.key][tpl] += 1
        heads[kind] = {
            "texts": len(texts),
            "with_heading": {k: has[k] for k in text.HEADING_KEYS},
            "share_with_heading": {
                k: round(has[k] / len(texts), 3) if texts else None for k in text.HEADING_KEYS
            },
            "standard_headings_per_text": dict(sorted(n_keys.items())),
            "top_templates": {k: templates[k].most_common(3) for k in text.HEADING_KEYS},
        }
    out["headings"] = heads
    out["alignment"] = _alignment(paired)
    return out


def _alignment(paired: list[LabelRow]) -> dict[str, Any]:
    """For each guide segment, which prescriber section of the same label it resembles most."""
    docs: list[tuple[str, Counter[str], list[tuple[str, Counter[str]]]]] = []
    df: Counter[str] = Counter()
    n_docs = 0
    for r in paired:
        guide = r.patient.medication_guide
        if not guide:
            continue
        sections = [
            (name, Counter(tokens(v))) for name, v in r.prescriber.model_dump().items() if v
        ]
        segments = [
            (seg.key, Counter(tokens(seg.body)))
            for seg in text.segment_patient_text(guide)
            if seg.key != "preamble"
        ]
        # Words in more than half of this label's sections and segments (its own names, its
        # stock phrases) say nothing about which section a segment draws on.
        spread = Counter(t for _, c in sections + segments for t in c)
        common = {t for t, n in spread.items() if n > (len(sections) + len(segments)) / 2}
        sections = [
            (name, Counter({t: n for t, n in c.items() if t not in common})) for name, c in sections
        ]
        segments = [
            (key, Counter({t: n for t, n in c.items() if t not in common})) for key, c in segments
        ]
        for _, c in sections + segments:
            df.update(c.keys())
            n_docs += 1
        for key, c in segments:
            docs.append((key, c, sections))
    idf = {t: math.log((1 + n_docs) / (1 + n)) + 1 for t, n in df.items()}
    best: dict[str, Counter[str]] = defaultdict(Counter)
    sims: dict[str, list[float]] = defaultdict(list)
    for key, c, sections in docs:
        if not sections or not c:
            continue
        seg_vec = _tfidf(c, idf)
        scored = [(cosine(seg_vec, _tfidf(sc, idf)), name) for name, sc in sections]
        top_score, top_name = max(scored)
        best[key][top_name] += 1
        sims[key].append(top_score)
    return {
        key: {
            "segments": sum(best[key].values()),
            "most_similar_section": dict(best[key].most_common()),
            "top_similarity": quantiles(sims[key]),
        }
        for key in text.HEADING_KEYS
        if best[key]
    }
