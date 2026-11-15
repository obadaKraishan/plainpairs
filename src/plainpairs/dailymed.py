"""A small test of DailyMed's label XML against the openFDA JSON text of the same labels.

DailyMed's web service returns one label as Structured Product Labeling (SPL) XML:
``https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{SETID}.xml``. The XML keeps what
openFDA's JSON flattens: nested sections with their titles, paragraphs, list items and tables.
:func:`parse_spl` reads it (with defusedxml, since it is outside data) into sections keyed by
their LOINC code, each as a list of blocks (one per title, paragraph or list item; tables kept
apart). :func:`measure_blocks` measures such a section with a sentence break at the end of every
block, which is what the JSON can no longer tell.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from defusedxml import ElementTree

from plainpairs import readability, text

SERVICE = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{set_id}.xml"
NS = "{urn:hl7-org:v3}"
#: LOINC section codes (FDA's list of SPL section headings) for the sections compared.
LOINC: dict[str, tuple[str, ...]] = {
    "boxed_warning": ("34066-1",),
    "indications_and_usage": ("34067-9",),
    "dosage_and_administration": ("34068-7",),
    "contraindications": ("34070-3",),
    "warnings_and_precautions": ("43685-7", "34071-1", "42232-9"),
    "adverse_reactions": ("34084-4",),
    "drug_interactions": ("34073-7",),
    "use_in_specific_populations": ("43684-0",),
    "patient_counseling_information": ("34076-0",),
    "description": ("34089-3",),
    "how_supplied_storage": ("34069-5", "44425-7"),
    "medication_guide": ("42231-1",),
    "patient_package_insert": ("42230-3",),
    "instructions_for_use": ("59845-8",),
    "patient_medication_information": ("68498-5",),
}
_CODE_TO_NAME = {code: name for name, codes in LOINC.items() for code in codes}


def _local(tag: Any) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _flat(el: Any) -> str:
    return text.clean("".join(el.itertext()))


class _Blocks:
    def __init__(self) -> None:
        self.blocks: list[str] = []
        self.counts: Counter[str] = Counter()

    def walk(self, el: Any) -> None:
        tag = _local(el.tag)
        if tag == "table":
            self.counts["tables"] += 1
            return
        if tag in ("title", "paragraph", "caption"):
            s = _flat(el)
            if s:
                self.blocks.append(s)
                self.counts["titles" if tag == "title" else "paragraphs"] += 1
            for child in el:
                if _local(child.tag) in ("list", "table"):
                    self.walk(child)
            return
        if tag == "item":
            own = [c for c in el if _local(c.tag) not in ("list", "table")]
            s = text.clean(
                (el.text or "") + "".join("".join(c.itertext()) + (c.tail or "") for c in own)
            )
            if s:
                self.blocks.append(s)
                self.counts["list_items"] += 1
            for child in el:
                if _local(child.tag) in ("list", "table"):
                    self.walk(child)
            return
        if tag == "list":
            self.counts["lists"] += 1
        if tag == "section":
            self.counts["sections"] += 1
        for child in el:
            self.walk(child)


def parse_spl(xml: bytes) -> dict[str, Any]:
    """Version, set id and the compared sections of one SPL document."""
    root = ElementTree.fromstring(xml)
    set_id = root.find(f"{NS}setId")
    version = root.find(f"{NS}versionNumber")
    sections: dict[str, dict[str, Any]] = {}
    for sec in root.iter(f"{NS}section"):
        code = sec.find(f"{NS}code")
        name = _CODE_TO_NAME.get(code.get("code") if code is not None else "")
        if not name or name in sections:
            continue  # nested sections are read as part of their top-level section
        b = _Blocks()
        b.walk(sec)
        sections[name] = {"blocks": b.blocks, **dict(b.counts)}
    return {
        "set_id": set_id.get("root") if set_id is not None else None,
        "version": int(version.get("value"))
        if version is not None and version.get("value")
        else None,
        "sections": sections,
    }


def measure_blocks(blocks: list[str]) -> readability.Readability:
    """Readability with a sentence break at the end of every block (title, paragraph, item)."""
    joined = " ".join(b if b[-1:] in ".!?" else b + "." for b in blocks)
    return readability.measure(joined, "s1")


STRATA = (
    ("plr", "medication_guide"),
    ("older", "medication_guide"),
    ("plr", "patient_package_insert"),
    ("older", "patient_package_insert"),
)


def choose(
    labels: list[dict[str, Any]], per_stratum: int = 5, seed: int = 20261115
) -> list[dict[str, Any]]:
    """Labels for the test: guides and inserts (without a guide), in both formats."""
    import random

    rng = random.Random(seed)
    picks = []
    for fmt, kind in STRATA:
        pool = sorted(
            (
                r
                for r in labels
                if r["label_format"] == fmt
                and (
                    r["has_medication_guide"]
                    if kind == "medication_guide"
                    else r["has_patient_package_insert"] and not r["has_medication_guide"]
                )
            ),
            key=lambda r: r["set_id"],
        )
        for r in rng.sample(pool, min(per_stratum, len(pool))):
            picks.append({**r, "stratum": f"{fmt}:{kind}"})
    return picks


def compare(json_texts: dict[str, str], doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per section: words and grades from the JSON (both rules) and from the XML's blocks."""
    out: dict[str, dict[str, Any]] = {}
    for name, sec in doc["sections"].items():
        js = json_texts.get(name)
        if not js or not sec["blocks"]:
            continue
        jm = readability.measure_rules(js)
        xm = measure_blocks(sec["blocks"])
        out[name] = {
            "json_words": jm["s2"].words,
            "xml_words": xm.words,
            "json_sentences_s1": jm["s1"].sentences,
            "json_sentences_s2": jm["s2"].sentences,
            "xml_sentences": xm.sentences,
            "json_fk_s1": jm["s1"].flesch_kincaid_grade,
            "json_fk_s2": jm["s2"].flesch_kincaid_grade,
            "xml_fk": xm.flesch_kincaid_grade,
            "json_smog_s2": jm["s2"].smog_grade,
            "xml_smog": xm.smog_grade,
            "xml_titles": sec.get("titles", 0),
            "xml_paragraphs": sec.get("paragraphs", 0),
            "xml_list_items": sec.get("list_items", 0),
            "xml_tables": sec.get("tables", 0),
            "xml_subsections": max(sec.get("sections", 1) - 1, 0),
            "json_list_marks": sum(
                js.count(m) for m in ("\u2022", "\u25cf", "\u25aa", "\u25a0", "\u25e6")
            ),
            "json_standard_headings": len(text.find_headings(js)),
            "json_numbered_headings": text.count_numbered_headings(js),
        }
    return out
