"""Alignment of patient segments to the prescriber sections they draw on.

Each standard heading of a Medication Guide or patient package insert is mapped to the
prescriber section(s) the Medication Guide regulation (21 CFR 208.20) points it to
(:data:`MAPPING`). For every segment, the similarity to each prescriber section of the same
label is also computed: TF-IDF weighted word counts compared by cosine, with the document
frequencies taken over the whole corpus, and with the words found in more than half of one
label's sections and segments (its own names, its stock phrases) left out for that label.

The mapping says where a segment is meant to come from; the similarity says where its words
come from. Both are kept, and where they disagree the pair says so; nothing is changed.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from typing import Any

from plainpairs.profile import cosine, tokens

#: Heading key -> the prescriber sections it is mapped to. ``general`` (stock wording about
#: using medicines safely) has no section in the regulation; it is mapped to section 17, its
#: closest match in the sample, and flagged as such in the method.
MAPPING: dict[str, tuple[str, ...]] = {
    "what_is": ("indications_and_usage",),
    "who_should_not": ("contraindications",),
    "how_to_take": ("dosage_and_administration",),
    "storage": ("how_supplied_storage",),
    "ingredients": ("description",),
    "most_important": ("boxed_warning", "warnings_and_precautions"),
    "side_effects": ("adverse_reactions", "warnings_and_precautions"),
    "before": ("warnings_and_precautions", "use_in_specific_populations", "drug_interactions"),
    "avoid": ("warnings_and_precautions", "drug_interactions", "patient_counseling_information"),
    "general": ("patient_counseling_information",),
}
SECTION_17 = "patient_counseling_information"


def label_counts(
    sections: dict[str, str], segments: list[tuple[str, str]]
) -> tuple[dict[str, Counter[str]], list[tuple[str, Counter[str]]]]:
    """Word counts of each section and segment of one label, its common words left out."""
    sec = {name: Counter(tokens(text)) for name, text in sections.items() if text}
    seg = [(key, Counter(tokens(body))) for key, body in segments]
    n = len(sec) + len(seg)
    spread = Counter(w for c in list(sec.values()) + [c for _, c in seg] for w in c)
    common = {w for w, k in spread.items() if k > n / 2}
    sec = {
        name: Counter({w: k for w, k in c.items() if w not in common}) for name, c in sec.items()
    }
    seg = [(key, Counter({w: k for w, k in c.items() if w not in common})) for key, c in seg]
    return sec, seg


def update_df(df: Counter[str], counters: Iterable[Counter[str]]) -> int:
    """Add each counter's words to the document frequencies; returns the documents added."""
    n = 0
    for c in counters:
        df.update(c.keys())
        n += 1
    return n


def idf_table(df: Counter[str], n_docs: int) -> dict[str, float]:
    return {w: math.log((1 + n_docs) / (1 + k)) + 1 for w, k in df.items()}


def weights(c: Counter[str], idf: dict[str, float], default: float) -> dict[str, float]:
    return {w: (1 + math.log(k)) * idf.get(w, default) for w, k in c.items()}


def score(
    key: str,
    segment: Counter[str],
    sections: dict[str, Counter[str]],
    idf: dict[str, float],
    default_idf: float,
) -> dict[str, Any]:
    """The pair record of one segment: mapped sections, similarities, best match."""
    seg_w = weights(segment, idf, default_idf)
    sims = {
        name: round(cosine(seg_w, weights(c, idf, default_idf)), 4) for name, c in sections.items()
    }
    mapped = MAPPING.get(key, ())
    present = [m for m in mapped if m in sections]
    best = max(sims.items(), key=lambda kv: (kv[1], kv[0]), default=(None, None))
    mapped_best = max((sims[m] for m in present), default=None)
    return {
        "mapped_sections": list(mapped),
        "mapped_present": present,
        "best_section": best[0] if best[1] else None,
        "best_similarity": best[1],
        "mapped_best_similarity": mapped_best,
        "best_is_mapped": bool(best[1]) and best[0] in present,
        "section17_similarity": sims.get(SECTION_17),
    }
