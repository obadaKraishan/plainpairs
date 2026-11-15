"""Standard readability formulas and simple text counts, computed by stated rules.

- **Flesch-Kincaid grade level** (Kincaid, Fishburne, Rogers and Chissom, 1975):
  ``0.39 * words/sentences + 11.8 * syllables/words - 15.59``.
- **Flesch reading ease** (Flesch, 1948): ``206.835 - 1.015 * words/sentences - 84.6 *
  syllables/words``.
- **SMOG grade** (McLaughlin, 1969, in the form most software uses):
  ``1.0430 * sqrt(polysyllables * 30 / sentences) + 3.1291``, where a polysyllable has three or
  more syllables. SMOG is meant for texts of at least 30 sentences; shorter texts are flagged.

Syllables are counted by rule (groups of vowels, with the usual corrections for a silent final
"e" and for "-le", "-ed" and "-es"), not looked up in a dictionary.

**Sentences.** Label text has lost its line breaks, so where a sentence ends matters. Two rules:

- ``s1`` (the first rule): a sentence ends at ``.``, ``!`` or ``?`` followed by a space; dots in
  common abbreviations and in decimals do not end one.
- ``s2`` (the rule used from now on): ``s1``, plus a break at every list mark the source keeps
  (``\u2022``, ``\u25cf``, ``\u25aa``, ``\u25a0``, ``\u25e6``, ``\u2023``), before a numbered
  heading (``5.1 Liver problems``), and around a run of capitals that reads as a heading
  (``5 WARNINGS AND PRECAUTIONS``). A list item or a heading is then a sentence of its own
  instead of part of one long run-on sentence.

Grades from either rule are comparable only within texts measured the same way.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache

from pydantic import BaseModel, ConfigDict

_WORD = re.compile(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)*")
#: Dots that do not end a sentence: abbreviations common in labels, and decimals.
_ABBREVIATIONS = re.compile(
    r"\b(?:e\.g|i\.e|etc|vs|approx|Dr|Mr|Mrs|Ms|No|St|Fig|U\.S|mg|mcg|mL|kg|min|max|hr|hrs)\.",
    re.I,
)
_DECIMAL = re.compile(r"(?<=\d)\.(?=\d)")
_SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")
#: A mark that stands in for a protected dot while sentences are split.
_KEEP = "\u2024"
_LIST_MARK = re.compile(r"\s*[\u2022\u25cf\u25aa\u25a0\u25e6\u2023]\s*")
_NUMBERED_HEADING = re.compile(r"(?<=\s)(?=\d{1,2}\.\d{1,2}\s+[A-Z])")
_CAPS_RUN = re.compile(r"(?:\b[A-Z][A-Z'\-/&,]+\b[ ]+){2,}\b[A-Z][A-Z'\-/&]+\b")
_BREAK = "\n"
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?![\w])")
_PERCENT = re.compile(r"\d+(?:\.\d+)?\s?%|\bper ?cent\b", re.I)
#: A sentence longer than this many words counts as long (federal plain-language guidance
#: suggests keeping sentences to about 20 words).
LONG_SENTENCE = 20
RULES = ("s1", "s2")


def syllables(word: str) -> int:
    """Syllables in one English word, by rule (at least 1 for a word with a letter)."""
    return _syllables(word.lower())


@lru_cache(maxsize=500_000)
def _syllables(lowered: str) -> int:
    w = re.sub(r"[^a-z]", "", lowered)
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    silent_es = w.endswith("es") and not re.search(r"(?:[sxz]|ch|sh|ce|ge)es$", w)
    silent_ed = w.endswith("ed") and not re.search(r"[td]ed$", w)
    if silent_es or silent_ed:
        w = w[:-2]
    elif w.endswith("e") and not (w.endswith("le") and w[-3] not in "aeiouy"):
        w = w[:-1]
    w = re.sub(r"^y", "", w)
    return max(len(re.findall(r"[aeiouy]+", w)), 1)


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def _protect(text: str) -> str:
    text = _ABBREVIATIONS.sub(lambda m: m.group(0)[:-1] + _KEEP, text)
    return _DECIMAL.sub(_KEEP, text)


def sentences(text: str, rule: str = "s2") -> list[str]:
    """Sentences of a text by ``rule`` (``s1`` or ``s2``, see the module docstring)."""
    if rule not in RULES:
        raise ValueError(f"Unknown sentence rule {rule!r}; use one of {RULES}.")
    t = text
    if rule == "s2":
        t = _LIST_MARK.sub(_BREAK, t)
        t = _NUMBERED_HEADING.sub(_BREAK, t)
        t = _CAPS_RUN.sub(lambda m: _BREAK + m.group(0) + _BREAK, t)
    t = _protect(t)
    parts: list[str] = []
    for block in t.split(_BREAK):
        parts.extend(_SENTENCE_END.split(block))
    return [p.strip() for p in parts if words(p)]


def count_numbers(text: str) -> int:
    """Numbers written in digits (``2``, ``0.5``, ``1,000``)."""
    return len(_NUMBER.findall(text))


def count_percentages(text: str) -> int:
    """Percentages (``12%``, ``0.5 %``, ``percent``)."""
    return len(_PERCENT.findall(text))


class Readability(BaseModel):
    """Counts and grades for one text, by one sentence rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule: str
    words: int
    sentences: int
    syllables: int
    polysyllables: int
    long_sentence_share: float | None
    numbers: int
    percentages: int
    flesch_kincaid_grade: float | None
    flesch_reading_ease: float | None
    smog_grade: float | None
    #: True when the text has fewer than 30 sentences, the minimum SMOG was made for.
    smog_short_text: bool


def _grades(n_words: int, n_sent: int, n_syl: int, poly: int) -> tuple[float, float, float]:
    wps, spw = n_words / n_sent, n_syl / n_words
    return (
        round(0.39 * wps + 11.8 * spw - 15.59, 2),
        round(206.835 - 1.015 * wps - 84.6 * spw, 2),
        round(1.0430 * math.sqrt(poly * 30 / n_sent) + 3.1291, 2),
    )


def measure_rules(text: str, rules: tuple[str, ...] = RULES) -> dict[str, Readability]:
    """Readability of ``text`` by each sentence rule; words and syllables are counted once."""
    ws = words(text)
    syl = [syllables(w) for w in ws]
    n_words, n_syl = len(ws), sum(syl)
    poly = sum(1 for s in syl if s >= 3)
    nums, pcts = count_numbers(text), count_percentages(text)
    out: dict[str, Readability] = {}
    for rule in rules:
        sents = sentences(text, rule) if n_words else []
        n_sent = len(sents) or (1 if n_words else 0)
        if not n_words:
            out[rule] = Readability(
                rule=rule,
                words=0,
                sentences=0,
                syllables=0,
                polysyllables=0,
                long_sentence_share=None,
                numbers=nums,
                percentages=pcts,
                flesch_kincaid_grade=None,
                flesch_reading_ease=None,
                smog_grade=None,
                smog_short_text=True,
            )
            continue
        long_share = sum(1 for s in sents if len(words(s)) > LONG_SENTENCE) / n_sent
        fk, fre, smog = _grades(n_words, n_sent, n_syl, poly)
        out[rule] = Readability(
            rule=rule,
            words=n_words,
            sentences=n_sent,
            syllables=n_syl,
            polysyllables=poly,
            long_sentence_share=round(long_share, 4),
            numbers=nums,
            percentages=pcts,
            flesch_kincaid_grade=fk,
            flesch_reading_ease=fre,
            smog_grade=smog,
            smog_short_text=n_sent < 30,
        )
    return out


def measure(text: str, rule: str = "s2") -> Readability:
    """Readability of ``text`` by one sentence rule. Grades are None for a text with no words."""
    return measure_rules(text, (rule,))[rule]


def measure_units(units: list[str]) -> dict[str, float | int | bool | None]:
    """The same counts and grades as :func:`measure`, over sentences already cut (for text
    read with its structure, where every list item and paragraph ends a sentence).

    Units without a word are dropped. Keys follow the build's measures: ``words``,
    ``sentences``, ``syllables``, ``polysyllables``, ``long_sentence_share``, ``numbers``,
    ``percentages``, ``flesch_kincaid``, ``flesch_reading_ease``, ``smog``, ``smog_short_text``.
    """
    kept = [u for u in units if words(u)]
    lengths = [len(words(u)) for u in kept]
    syl = [syllables(w) for u in kept for w in words(u)]
    n_words, n_sent, n_syl = sum(lengths), len(kept), sum(syl)
    poly = sum(1 for s in syl if s >= 3)
    joined = " ".join(kept)
    out: dict[str, float | int | bool | None] = {
        "words": n_words,
        "sentences": n_sent,
        "syllables": n_syl,
        "polysyllables": poly,
        "long_sentence_share": None,
        "numbers": count_numbers(joined),
        "percentages": count_percentages(joined),
        "flesch_kincaid": None,
        "flesch_reading_ease": None,
        "smog": None,
        "smog_short_text": n_sent < 30,
    }
    if n_words:
        fk, fre, smog = _grades(n_words, n_sent, n_syl, poly)
        out.update(
            long_sentence_share=round(sum(n > LONG_SENTENCE for n in lengths) / n_sent, 4),
            flesch_kincaid=fk,
            flesch_reading_ease=fre,
            smog=smog,
        )
    return out
