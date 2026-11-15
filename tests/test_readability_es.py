"""The Spanish syllable rule and the perspicuity index, on ordinary Spanish words."""

import pytest

from plainpairs import readability_es as es

# word -> syllables, from the standard syllable division of Spanish spelling
KNOWN = {
    "casa": 2,
    "computadora": 5,
    "ciudad": 2,
    "pa\u00eds": 2,
    "poeta": 3,
    "a\u00e9reo": 4,
    "Paraguay": 3,
    "r\u00edo": 2,
    "huevo": 2,
    "c\u00e1ncer": 2,
    "tratamiento": 4,
    "quimioterapia": 5,
    "guerra": 2,
    "ping\u00fcino": 3,
    "quiero": 2,
    "aqu\u00ed": 2,
    "leer": 2,
    "creer": 2,
    "o\u00eddo": 3,
    "muy": 1,
    "hoy": 1,
    "y": 1,
    "ley": 1,
    "reyes": 2,
    "ahora": 3,
    "ba\u00fal": 2,
    "europeo": 4,
    "ma\u00edz": 2,
    "riesgo": 2,
    "tambi\u00e9n": 2,
    "informaci\u00f3n": 4,
    "enfermedad": 4,
    "buey": 1,
    "averig\u00fc\u00e9is": 4,
    "ni\u00f1o": 2,
    "m\u00e9dico": 3,
    "paciente": 3,
    "c\u00e9lulas": 3,
    "est\u00f3mago": 4,
    "radiaci\u00f3n": 3,
    "cuidado": 3,
    "seguimiento": 4,
    "diagn\u00f3stico": 4,
    "biopsia": 2,
    "s\u00edntomas": 3,
    "pron\u00f3stico": 4,
}


@pytest.mark.parametrize(("word", "n"), sorted(KNOWN.items()))
def test_syllables_of_known_words(word, n):
    assert es.syllables(word) == n


def test_syllables_edge_cases():
    assert es.syllables("") == 0
    assert es.syllables("123") == 0
    assert es.syllables("prohibir") == 3  # by spelling; spoken, 2: the silent h limit


def test_words_keep_accents_and_tilde():
    assert es.words("El ni\u00f1o, 3 a\u00f1os: \u00bfqu\u00e9 tal?") == [
        "El",
        "ni\u00f1o",
        "a\u00f1os",
        "qu\u00e9",
        "tal",
    ]


def test_index_and_bands():
    assert es.szigriszt_pazos(0, 0, 0) is None
    assert es.szigriszt_pazos(10, 1, 20) == round(206.835 - 62.3 * 2 - 10, 2)
    assert [es.inflesz(x) for x in (None, 30, 45, 60, 70, 90)] == [
        None,
        "very_difficult",
        "somewhat_difficult",
        "normal",
        "quite_easy",
        "very_easy",
    ]
    m = es.measure_units(["La casa es grande.", "El ni\u00f1o come pan.", ""])
    assert (m["words"], m["sentences"], m["syllables"]) == (8, 2, 12)
    assert m["szigriszt_pazos"] == round(206.835 - 62.3 * 12 / 8 - 4, 2)
    assert m["inflesz_band"] == "very_easy" and m["long_sentence_share"] == 0
    assert es.measure_units([])["szigriszt_pazos"] is None
