"""Text cleaning, tables, headings and readability, on invented text only."""

import pytest
from pydantic import ValidationError

from plainpairs import readability as rd
from plainpairs import text as tx

GUIDE = (
    "MEDICATION GUIDE Zorvan (ZOR-van) tablets Read this Medication Guide before you start. "
    "What is the most important information I should know about Zorvan? Zorvan may cause "
    "sleepiness. What is Zorvan? Zorvan is a made-up medicine used in these tests. "
    "Who should not take Zorvan? Do not take Zorvan if you are allergic to it. "
    "Before taking Zorvan, tell your healthcare provider about all of your medical conditions. "
    "How should I take Zorvan? Take Zorvan 1 time each day. "
    "What should I avoid while taking Zorvan? Avoid driving. "
    "What are the possible side effects of Zorvan? Zorvan may cause headache. "
    "How should I store Zorvan? Store at room temperature. "
    "General information about the safe and effective use of Zorvan. Medicines are sometimes "
    "prescribed for other purposes. What are the ingredients in Zorvan? Active ingredient: "
    "zorvanide."
)


def test_clean_normalizes_but_keeps_every_word():
    raw = "5 WARNINGS&nbsp;AND <b>PRECAUTIONS</b>\n 5.1 Sleepiness  Cafe\u0301 \u00adrisk"
    assert tx.clean(raw) == "5 WARNINGS AND PRECAUTIONS 5.1 Sleepiness Caf\u00e9 risk"
    assert tx.clean("a < b and c > d") == "a < b and c > d"


def test_join_keeps_each_string_and_drops_empty_ones():
    assert tx.join(["  One  ", "", "Two"]) == "One\n\nTwo"
    assert tx.join([]) is None
    assert tx.join(None) is None
    assert tx.join(["   "]) is None


def test_table_to_text_reads_rows_and_cells():
    markup = (
        "<table><caption>Table 1</caption><tr><th>Reaction</th><th>Zorvan<br/>N=10</th></tr>"
        "<tr><td>Headache</td><td>2 (20%)</td></tr><tr><td></td><td></td></tr></table>"
    )
    assert tx.table_to_text(markup) == "Reaction | Zorvan N=10\nHeadache | 2 (20%)"


def test_hashes_see_through_spacing_and_case():
    assert tx.text_hash("a  b") == tx.text_hash(" a b ")
    assert tx.text_hash("a b") != tx.text_hash("A b")
    assert tx.loose_hash("Take ZORVAN, daily!") == tx.loose_hash("take zorvan daily")


def test_segment_finds_every_standard_heading_in_order():
    segs = tx.segment_patient_text(GUIDE)
    assert [s.key for s in segs] == [
        "preamble",
        "most_important",
        "what_is",
        "who_should_not",
        "before",
        "how_to_take",
        "avoid",
        "side_effects",
        "storage",
        "general",
        "ingredients",
    ]
    assert segs[1].heading == "What is the most important information I should know about Zorvan?"
    assert segs[1].body == "Zorvan may cause sleepiness."
    assert segs[-1].body == "Active ingredient: zorvanide."
    assert segs[0].body.startswith("MEDICATION GUIDE Zorvan")


def test_a_text_without_headings_is_one_preamble():
    assert [s.key for s in tx.segment_patient_text("Keep out of reach.")] == ["preamble"]
    assert tx.segment_patient_text("") == []


def test_heading_templates_take_the_name_out():
    cases = {
        (
            "What is the most important information I should know about Zorvan XR?",
            "most_important",
        ): "What is the most important information I should know about [medicine]?",
        ("What is Zorvan?", "what_is"): "What is [medicine]?",
        ("How should I take Zorvan?", "how_to_take"): "How should I take [medicine]?",
        (
            "What are the possible side effects of Zorvan?",
            "side_effects",
        ): "What are the possible side effects of [medicine]?",
        (
            "Before taking Zorvan, tell your healthcare provider",
            "before",
        ): "Before taking [medicine], tell your healthcare provider",
        (
            "General information about the safe and effective use of Zorvan.",
            "general",
        ): "General information about the safe and effective use of [medicine].",
    }
    for (heading, key), expected in cases.items():
        assert tx.heading_template(heading, key) == expected


def test_a_heading_that_does_not_match_is_left_as_it_is():
    assert tx.heading_template("Something else", "storage") == "Something else"


@pytest.mark.parametrize(
    ("word", "count"),
    [
        ("cat", 1),
        ("table", 2),
        ("medicine", 3),
        ("headache", 2),
        ("taken", 2),
        ("tablets", 2),
        ("healthcare", 2),
        ("provider", 3),
        ("information", 4),
        ("you", 1),
        ("", 0),
        ("rhythm", 1),
    ],
)
def test_syllables_by_rule(word, count):
    assert rd.syllables(word) == count


def test_sentences_ignore_abbreviations_and_decimals():
    s = rd.sentences("Take 2.5 mg. daily, e.g. at noon. Ask your doctor! Why? Fine")
    assert s == [
        "Take 2\u20245 mg\u2024 daily, e.g\u2024 at noon",
        "Ask your doctor",
        "Why",
        "Fine",
    ]


def test_measure_matches_the_formulas_by_hand():
    r = rd.measure("The cat sat. The dog ran far away.")
    # 8 words, 2 sentences, 9 syllables (a-way = 2), no polysyllables
    assert (r.words, r.sentences, r.syllables, r.polysyllables) == (8, 2, 9, 0)
    assert r.flesch_kincaid_grade == round(0.39 * 4 + 11.8 * 9 / 8 - 15.59, 2)
    assert r.flesch_reading_ease == round(206.835 - 1.015 * 4 - 84.6 * 9 / 8, 2)
    assert r.smog_grade == 3.13
    assert r.smog_short_text


def test_measure_of_an_empty_text_has_no_grades():
    r = rd.measure("12 34 !")
    assert r.words == 0
    assert r.flesch_kincaid_grade is None


def test_a_text_without_full_stops_is_one_sentence():
    assert rd.measure("one two three").sentences == 1


def test_readability_is_frozen():
    r = rd.measure("Fine words here.")
    with pytest.raises(ValidationError):
        r.words = 3


def test_a_heading_cited_in_running_text_is_not_a_heading():
    guide = (
        "What is the most important information I should know about Zorvan? Sleepiness. "
        'What are the possible side effects of Zorvan? See "What is the most important '
        'information I should know about Zorvan?" Headache.'
    )
    assert [s.key for s in tx.segment_patient_text(guide)] == ["most_important", "side_effects"]
    assert tx.is_reference("see “", 5)
    assert not tx.is_reference("Sleepiness. ", 12)


def test_core_drops_closing_matter_only_near_the_end():
    a = "Take it daily with water. " * 5 + "Manufactured by: Example Pharma Inc. Revised: 1/2026"
    b = "Take it daily with water. " * 5 + "Distributed by: Other Maker LLC Revised: 3/2026"
    assert tx.core_hash(a) == tx.core_hash(b)
    assert tx.loose_hash(a) != tx.loose_hash(b)
    early = "Distributed by mail. " + "Take it daily. " * 2
    assert tx.core(early) == early
