"""Standard readability formulas, computed by stated rules.

- **Flesch-Kincaid grade level** (Kincaid, Fishburne, Rogers and Chissom, 1975):
  ``0.39 * words/sentences + 11.8 * syllables/words - 15.59``.
- **Flesch reading ease** (Flesch, 1948): ``206.835 - 1.015 * words/sentences - 84.6 *
  syllables/words``.
- **SMOG grade** (McLaughlin, 1969, in the form most software uses):
  ``1.0430 * sqrt(polysyllables * 30 / sentences) + 3.1291``, where a polysyllable has three or
  more syllables. McLaughlin's own procedure samples 30 sentences; this form uses every
  sentence. SMOG is meant for texts of at least 30 sentences, so :class:`Readability` flags
  shorter texts.

Syllables are counted by a rule (groups of vowels, with the usual corrections for a silent
final "e" and for "-le", "-ed" and "-es"), not looked up in a dictionary, so counts for single
words can be off by one; over a whole text the error is small. Sentences end at ``.``, ``!``,
``?`` and ``;`` is not an end. Label text has lost its line breaks, so a bulleted list with no
full stops reads as one long sentence and raises the grade; that limit is reported with the
measures (see docs/method.md).
"""

from __future__ import annotations

import math
import re

from pydantic import BaseModel, ConfigDict

_WORD = re.compile(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)*")
#: Dots that do not end a sentence: abbreviations common in labels, and decimals.
_ABBREVIATIONS = re.compile(
    r"\b(?:e\.g|i\.e|etc|vs|approx|Dr|Mr|Mrs|Ms|No|St|Fig|U\.S|mg|mcg|mL|kg|min|max|hr|hrs)\.",
    re.I,
)
_DECIMAL = re.compile(r"(?<=\d)\.(?=\d)")
_SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")


def syllables(word: str) -> int:
    """Syllables in one English word, by rule (at least 1 for a word with a letter)."""
    w = re.sub(r"[^a-z]", "", word.lower())
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


def sentences(text: str) -> list[str]:
    """Sentences of a text; dots in abbreviations and decimals do not end one."""
    protected = _DECIMAL.sub(
        "\u2024", _ABBREVIATIONS.sub(lambda m: m.group(0)[:-1] + "\u2024", text)
    )
    parts = _SENTENCE_END.split(protected)
    return [p.strip() for p in parts if words(p)]


class Readability(BaseModel):
    """Counts and grades for one text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    words: int
    sentences: int
    syllables: int
    polysyllables: int
    flesch_kincaid_grade: float | None
    flesch_reading_ease: float | None
    smog_grade: float | None
    #: True when the text has fewer than 30 sentences, the minimum SMOG was made for.
    smog_short_text: bool


def measure(text: str) -> Readability:
    """Readability of ``text``. Grades are None for a text with no words."""
    ws = words(text)
    n_sent = len(sentences(text)) or (1 if ws else 0)
    syl = [syllables(w) for w in ws]
    n_words, n_syl = len(ws), sum(syl)
    poly = sum(1 for s in syl if s >= 3)
    if not n_words:
        return Readability(
            words=0,
            sentences=0,
            syllables=0,
            polysyllables=0,
            flesch_kincaid_grade=None,
            flesch_reading_ease=None,
            smog_grade=None,
            smog_short_text=True,
        )
    wps, spw = n_words / n_sent, n_syl / n_words
    return Readability(
        words=n_words,
        sentences=n_sent,
        syllables=n_syl,
        polysyllables=poly,
        flesch_kincaid_grade=round(0.39 * wps + 11.8 * spw - 15.59, 2),
        flesch_reading_ease=round(206.835 - 1.015 * wps - 84.6 * spw, 2),
        smog_grade=round(1.0430 * math.sqrt(poly * 30 / n_sent) + 3.1291, 2),
        smog_short_text=n_sent < 30,
    )
