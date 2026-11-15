"""Readability of Spanish text: a syllable rule and the Szigriszt-Pazos perspicuity index.

**The formula.** Szigriszt-Pazos's perspicuity index (Szigriszt Pazos F. *Sistemas predictivos
de legibilidad del mensaje escrito: formula de perspicuidad.* Doctoral thesis, Universidad
Complutense de Madrid, 1993) adapts Flesch's reading ease to Spanish:
``206.835 - 62.3 * syllables/words - words/sentences``. Its scores are read on the INFLESZ
scale, which was validated on texts written for patients (Barrio-Cantalejo IM, Simon-Lorda P,
Melguizo M, Escalona I, Marijuan MI, Hernando P. Validacion de la Escala INFLESZ para evaluar
la legibilidad de los textos dirigidos a pacientes. *An Sist Sanit Navar* 2008;31(2):135-152):
below 40 very difficult, 40 to 55 somewhat difficult, 55 to 65 normal, 65 to 80 quite easy,
above 80 very easy. It is an ease score, not a school grade, and it is never compared with an
English grade.

**Syllables** are counted by rule, from Spanish spelling: every vowel group is one syllable
unless two "strong" vowels meet (a, e, o, or an accented i or u), which split it (a hiatus:
"poeta", "rio" with an accent). Two weak vowels (i, u) or a weak and a strong one form one
syllable (a diphthong: "ciudad", "tienda"), and a weak-strong-weak group one (a triphthong:
"buey"). The u of "que", "qui", "gue" and "gui" is silent (not in "gue" with a diaeresis), and
a final y after a vowel ("hoy", "muy") is a vowel. A silent h between vowels is read as a
consonant, so words such as "prohibir" count one syllable more than they are spoken: a stated
limit of the rule (the spelling's syllables, not the spoken ones).
"""

from __future__ import annotations

import re
import unicodedata

_WORD = re.compile(r"[^\W\d_]+(?:['\u2019][^\W\d_]+)*")
_VOWELS = frozenset("aeiou\u00e1\u00e9\u00ed\u00f3\u00fa\u00fc")
#: Vowels that split a vowel group when two of them meet.
_STRONG = frozenset("aeo\u00e1\u00e9\u00f3\u00ed\u00fa")
_SILENT_U = re.compile("(?<=[qg])u(?=[ei\u00e9\u00ed])")
_FINAL_Y = re.compile("(?<=[aeiou\u00e1\u00e9\u00ed\u00f3\u00fa])y$")


def words(text: str) -> list[str]:
    """Words of a Spanish text (letters with accents and the n with tilde; no digits)."""
    return _WORD.findall(unicodedata.normalize("NFC", text))


def syllables(word: str) -> int:
    """Syllables in one Spanish word, by the rule in the module docstring (at least 1)."""
    w = unicodedata.normalize("NFC", word.lower())
    w = "".join(c for c in w if c.isalpha())
    if not w:
        return 0
    if w == "y":
        return 1
    w = _SILENT_U.sub("", w)
    w = _FINAL_Y.sub("i", w)
    count, prev = 0, ""
    for c in w:
        if c in _VOWELS:
            if not prev or (prev in _STRONG and c in _STRONG):
                count += 1
            prev = c
        else:
            prev = ""
    return max(count, 1)


def szigriszt_pazos(n_words: int, n_sentences: int, n_syllables: int) -> float | None:
    """The perspicuity index (higher is easier); None for a text with no words."""
    if not n_words or not n_sentences:
        return None
    return round(206.835 - 62.3 * n_syllables / n_words - n_words / n_sentences, 2)


INFLESZ_BANDS = (
    (40.0, "very_difficult"),
    (55.0, "somewhat_difficult"),
    (65.0, "normal"),
    (80.0, "quite_easy"),
)


def inflesz(score: float | None) -> str | None:
    """The INFLESZ band of a perspicuity score."""
    if score is None:
        return None
    for upper, band in INFLESZ_BANDS:
        if score < upper:
            return band
    return "very_easy"


def measure_units(units: list[str], long_sentence: int = 20) -> dict[str, float | int | str | None]:
    """Words, sentences, syllables, the perspicuity index, its band and the share of sentences
    over ``long_sentence`` words, over sentences already cut (from structure)."""
    kept = [u for u in units if words(u)]
    lengths = [len(words(u)) for u in kept]
    n_words, n_sent = sum(lengths), len(kept)
    n_syl = sum(syllables(w) for u in kept for w in words(u))
    score = szigriszt_pazos(n_words, n_sent, n_syl)
    return {
        "words": n_words,
        "sentences": n_sent,
        "syllables": n_syl,
        "szigriszt_pazos": score,
        "inflesz_band": inflesz(score),
        "long_sentence_share": (
            round(sum(n > long_sentence for n in lengths) / n_sent, 4) if n_sent else None
        ),
    }
