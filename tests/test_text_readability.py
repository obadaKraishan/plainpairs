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
    s = rd.sentences("Take 2.5 mg. daily, e.g. at noon. Ask your doctor! Why? Fine", "s1")
    assert s == [
        "Take 2\u20245 mg\u2024 daily, e.g\u2024 at noon",
        "Ask your doctor",
        "Why",
        "Fine",
    ]


def test_measure_matches_the_formulas_by_hand():
    r = rd.measure("The cat sat. The dog ran far away.", "s1")
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
    assert tx.is_reference("see \u201c", 5)
    assert not tx.is_reference("Sleepiness. ", 12)


def test_core_drops_closing_matter_only_near_the_end():
    a = "Take it daily with water. " * 5 + "Manufactured by: Example Pharma Inc. Revised: 1/2026"
    b = "Take it daily with water. " * 5 + "Distributed by: Other Maker LLC Revised: 3/2026"
    assert tx.core_hash(a) == tx.core_hash(b)
    assert tx.loose_hash(a) != tx.loose_hash(b)
    early = "Distributed by mail. " + "Take it daily. " * 2
    assert tx.core(early) == early


def test_s2_breaks_at_list_marks_numbered_headings_and_capital_headings():
    text = (
        "5 WARNINGS AND PRECAUTIONS 5.1 Sleepiness Zorvan may cause: \u2022 headache "
        "\u2022 tiredness \u2022 dizziness Tell your doctor."
    )
    assert len(rd.sentences(text, "s1")) == 1
    assert rd.sentences(text, "s2") == [
        "WARNINGS AND PRECAUTIONS",
        "5\u20241 Sleepiness Zorvan may cause:",
        "headache",
        "tiredness",
        "dizziness Tell your doctor",
    ]
    with pytest.raises(ValueError, match="Unknown sentence rule"):
        rd.sentences(text, "s9")


def test_measure_rules_counts_once_and_grades_by_each_rule():
    text = "Zorvan may cause: \u2022 headache \u2022 tiredness. Take 2 tablets, 50% of the dose."
    m = rd.measure_rules(text)
    assert m["s1"].words == m["s2"].words
    assert m["s2"].sentences > m["s1"].sentences
    assert m["s2"].flesch_kincaid_grade < m["s1"].flesch_kincaid_grade
    assert (m["s2"].numbers, m["s2"].percentages) == (2, 1)
    assert 0 <= m["s2"].long_sentence_share <= 1
    assert rd.measure("12 34 !").long_sentence_share is None


def test_counts_of_numbers_and_percentages():
    assert rd.count_numbers("Take 1 or 2.5 mg, up to 1,000 mg; not 3rd") == 3
    assert rd.count_percentages("12% and 0.5 % and five percent") == 3


def test_strip_tables_cuts_a_table_repeated_inline():
    table = (
        "<table><tr><th>Reaction</th><th>Zorvan N=100</th></tr>"
        "<tr><td>Headache</td><td>12 (12%)</td></tr></table>"
    )
    text = "Most common reactions: Reaction Zorvan N=100 Headache 12 (12%) were mild."
    prose, cut = tx.strip_tables(text, [table])
    assert prose == "Most common reactions: were mild."
    assert cut == len("Reaction Zorvan N=100 Headache 12 (12%)")
    assert tx.strip_tables("No table here.", [table]) == ("No table here.", 0)
    assert tx.strip_tables("Text.", ["<table></table>"]) == ("Text.", 0)


def test_strip_tables_merges_overlapping_tables():
    t1 = "<table><tr><td>Alpha beta</td><td>Gamma delta</td></tr></table>"
    t2 = "<table><tr><td>Gamma delta</td><td>Epsilon zeta</td></tr></table>"
    prose, _ = tx.strip_tables("Start Alpha beta Gamma delta Epsilon zeta end.", [t1, t2])
    assert prose == "Start end."


def test_numbered_headings_are_counted():
    assert tx.count_numbered_headings("5.1 Liver Problems text 5.2 Rash 2.5 mg daily 10.12 X") == 3
    assert tx.table_cells("<table><tr><td> a </td><td></td></tr></table>") == ["a"]


def test_prose_laid_out_in_a_table_is_never_cut():
    box = (
        "<table><tr><td>What is the most important information I should know about Zorvan? "
        "Zorvan may make you very sleepy during the day.</td></tr></table>"
    )
    text = (
        "What is the most important information I should know about Zorvan? Zorvan may make "
        "you very sleepy during the day. Call your doctor."
    )
    assert tx.strip_tables(text, [box]) == (text, 0)
    assert tx.is_data_table(["Headache", "2%", "Nausea", "1%"])
    assert not tx.is_data_table([])
