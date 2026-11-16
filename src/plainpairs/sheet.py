"""The hand sheet: does this prescriber section cover the same topic as this patient segment?

``draw`` picks segments from table C, a fixed number per heading key, with a seed: only
segments whose label has at least one of the sections the heading is mapped to and whose body
is more than one line (at least two sentences and :data:`MIN_WORDS` words), never two rows from
the same distinct patient text anywhere on the sheet, and, where the pool allows, one per
medicine within a key. ``write``
puts them in one .xlsx sheet with the patient segment, the mapped prescriber section (its
first 300 words) and an answer cell with a list (yes, partly, no). The sheet is blind: it
shows no similarity score and no rule name. The key that links each row to its label and
heading is written to a separate CSV, never into the sheet.

``check`` reads the filled sheet with its key and reports, per heading key, the share of
"yes" or "partly" with a 95% Wilson interval, and whether the heading's rule reaches the
release line (80%).
"""

from __future__ import annotations

import csv
import math
import random
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from plainpairs import align, text, xlsx

ANSWERS = ("yes", "partly", "no")
RELEASE_LINE = 0.8
#: A segment body shorter than this (or of one sentence) is "one line" and never drawn.
MIN_WORDS = 20
MIN_SENTENCES = 2
PRESCRIBER_WORDS = 300
MAX_CELL = 32_000
KEY_FIELDS = [
    "row",
    "set_id",
    "version",
    "kind",
    "segment_index",
    "heading_key",
    "section",
    "patient_text_id",
    "seed",
]
SECTION_NAMES = {
    "boxed_warning": "Boxed warning",
    "indications_and_usage": "Indications and usage",
    "dosage_and_administration": "Dosage and administration",
    "contraindications": "Contraindications",
    "warnings_and_precautions": "Warnings and precautions",
    "adverse_reactions": "Adverse reactions",
    "drug_interactions": "Drug interactions",
    "use_in_specific_populations": "Use in specific populations",
    "patient_counseling_information": "Patient counseling information (section 17)",
    "description": "Description",
    "how_supplied_storage": "How supplied, storage and handling",
}


class SheetError(ValueError):
    """The sheet or its key cannot be read as filled."""


def draw(
    pairs: Iterable[dict[str, Any]],
    medicine_of: dict[str, str | None],
    per_key: int = 10,
    seed: int = 20261115,
) -> list[dict[str, Any]]:
    """Pick ``per_key`` segments for every heading key, reproducibly."""
    pool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in pairs:
        if p["heading_key"] in align.MAPPING and p["mapped_present"] and _long_enough(p):
            pool[p["heading_key"]].append(p)
    rng = random.Random(seed)
    picks: list[dict[str, Any]] = []
    used_texts: set[str] = set()
    for key in text.HEADING_KEYS:
        cands = sorted(
            pool.get(key, []), key=lambda p: (p["patient_text_id"], p["set_id"], p["segment_index"])
        )
        one_per_text: dict[str, dict[str, Any]] = {}
        for p in cands:
            if p["patient_text_id"] not in used_texts:
                one_per_text.setdefault(p["patient_text_id"], p)
        cands = list(one_per_text.values())
        rng.shuffle(cands)
        chosen: list[dict[str, Any]] = []
        medicines: set[str] = set()
        for p in cands:  # first pass: a new medicine each time
            med = medicine_of.get(p["set_id"])
            if med and med in medicines:
                continue
            chosen.append(p)
            if med:
                medicines.add(med)
            if len(chosen) == per_key:
                break
        for p in cands:  # then fill up if the pool is small
            if len(chosen) == per_key:
                break
            if p not in chosen:
                chosen.append(p)
        used_texts.update(p["patient_text_id"] for p in chosen)
        picks += [{**p, "section": p["mapped_present"][0], "seed": seed} for p in chosen]
    for i, p in enumerate(picks, start=1):
        p["row"] = i
    return picks


def recheck(
    key_rows: Iterable[dict[str, str]],
    pairs: dict[tuple[str, str, str, int], dict[str, Any]],
    seed: int,
) -> list[dict[str, Any]]:
    """The same pairs as a sheet's key, in a new order drawn with ``seed``, rows renumbered.

    For a second pass by the same coder: only the key (which pairs, never the answers) is read,
    each pair is found again in the build by set id, version, kind and segment index, and its
    heading key and section must be the key's."""
    picks = []
    for k in key_rows:
        ident = (k["set_id"], str(k["version"]), k["kind"], int(k["segment_index"]))
        p = pairs.get(ident)
        if p is None or p["heading_key"] != k["heading_key"]:
            raise SheetError(f"Row {k['row']} of the key is not in the build: {ident}.")
        if k["section"] not in (p.get("mapped_present") or []):
            raise SheetError(f"Row {k['row']}: section {k['section']} is not mapped in the build.")
        picks.append({**p, "section": k["section"], "seed": seed})
    random.Random(seed).shuffle(picks)
    for i, p in enumerate(picks, start=1):
        p["row"] = i
    return picks


def _long_enough(p: dict[str, Any]) -> bool:
    """More than one line: at least two sentences and :data:`MIN_WORDS` words in the body."""
    m = p.get("measures")
    if m is None:  # an older caller without measures: keep the segment
        return True
    return (m.get("words") or 0) >= MIN_WORDS and (m.get("sentences") or 0) >= MIN_SENTENCES


def first_words(s: str, n: int = PRESCRIBER_WORDS) -> str:
    """The first ``n`` words of ``s``, with a note when it is cut."""
    words = s.split()
    if len(words) <= n:
        return s
    return " ".join(words[:n]) + f" [... first {n} of {len(words):,} words]"


def _cell(s: str) -> str:
    return s if len(s) <= MAX_CELL else s[:MAX_CELL] + " [... cut at the cell limit]"


def write(
    picks: list[dict[str, Any]],
    patient_text: dict[tuple[str, str], str],
    prescriber_text: dict[tuple[str, str], str],
    xlsx_path: Path,
    key_path: Path,
) -> Path:
    """Write the blind sheet and, separately, its key."""
    head = xlsx.Style(bold=True, fill="DDEBF7", locked=True)
    locked = xlsx.Style(wrap=True, locked=True)
    open_ = xlsx.Style(wrap=True, locked=False, fill="FFF2CC")
    rows = [
        [
            ("Row", head),
            ("Patient text: heading and segment", head),
            ("Prescriber section", head),
            (f"Prescriber text (first {PRESCRIBER_WORDS} words)", head),
            ("Same topic? (yes, partly, no)", head),
            ("Note (optional)", head),
        ]
    ]
    for p in picks:
        full = patient_text[(p["set_id"], p["kind"])]
        segment = full[p["seg_start"] : p["seg_end"]].strip()
        section = prescriber_text[(p["set_id"], p["section"])]
        rows.append(
            [
                (str(p["row"]), locked),
                (_cell(segment), locked),
                (SECTION_NAMES[p["section"]], locked),
                (_cell(first_words(section)), locked),
                ("", open_),
                ("", open_),
            ]
        )
    sheet = xlsx.Sheet(
        name="Topic check",
        rows=rows,
        widths=(6, 70, 24, 80, 16, 30),
        dropdowns=(
            xlsx.Dropdown(
                column=4,
                first_row=2,
                last_row=len(picks) + 1,
                choices=ANSWERS,
                error="Choose yes, partly or no.",
            ),
        ),
        active_cell="E2",
    )
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    xlsx.write_workbook(xlsx_path, sheet)
    with key_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=KEY_FIELDS)
        w.writeheader()
        for p in picks:
            w.writerow({k: p[k] for k in KEY_FIELDS})
    return xlsx_path


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    """The 95% Wilson score interval for ``k`` of ``n``."""
    if n == 0:
        return None, None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(centre - half, 3), round(centre + half, 3)


def check(xlsx_path: Path, key_path: Path) -> dict[str, Any]:
    """Shares of "yes or partly" per heading key, from a filled sheet and its key."""
    sheets = [s for s in xlsx.read_workbook(xlsx_path) if not s.hidden]
    if not sheets:
        raise SheetError(f"{xlsx_path} has no visible sheet.")
    rows = sheets[0].rows
    if not rows or rows[0][1][:1] != ("Row",):
        raise SheetError(f"{xlsx_path}: the first row is not the sheet's header row.")
    answers: dict[str, str] = {}
    for _, cells in rows[1:]:
        cells = (*cells, "", "", "", "", "")[:6]
        answers[cells[0].strip()] = cells[4].strip().lower()
    with key_path.open(newline="", encoding="utf-8") as fh:
        key = list(csv.DictReader(fh))
    per: dict[str, dict[str, int]] = defaultdict(
        lambda: {"yes": 0, "partly": 0, "no": 0, "blank": 0, "other": 0}
    )
    for k in key:
        a = answers.get(k["row"], "")
        bucket = a if a in ANSWERS else ("blank" if not a else "other")
        per[k["heading_key"]][bucket] += 1
    out: dict[str, Any] = {}
    for heading, c in per.items():
        n = c["yes"] + c["partly"] + c["no"]
        good = c["yes"] + c["partly"]
        low, high = wilson(good, n)
        out[heading] = {
            **c,
            "answered": n,
            "share_yes_or_partly": round(good / n, 3) if n else None,
            "wilson_95": [low, high],
            "rule": (
                "regulation rule released"
                if n and good / n >= RELEASE_LINE
                else "similarity only, flagged"
            )
            if n
            else "not answered",
        }
    return out
