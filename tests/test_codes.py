"""The rule-based codes, on invented sentences only."""

import pyarrow.parquet as pq
import pytest

from plainpairs import codes, tables
from tests.test_tables import write_export


def c(t, kind="patient"):
    return codes.code_text(t, kind)


def test_direct_address_counts_you_and_your():
    got = c("Tell your doctor. You may feel tired. Zorvan is a tablet.")
    assert got["you_words"] == 2 and got["sentences_with_you"] == 2 and got["sentences"] == 3


@pytest.mark.parametrize(
    ("sentence", "verb"),
    [
        ("Take Zorvan once a day", "take"),
        ("Do not take Zorvan with food", "not take"),
        ("Don\u2019t crush the tablet", "not crush"),
        ("Never share Zorvan", None),  # "share" is not in the list: a stated limit
        ("Step 2: Wash your hands", "wash"),
        ("\u2022 Store at room temperature", "store"),
        ("Use in children has not been studied", None),  # a noun, not an instruction
        ("Contact with the eyes may sting", None),
        ("Advise patients to read the guide", "advise"),
        ("Zorvan may cause sleepiness", None),
        ("Do this every morning", None),
        ("", None),
    ],
)
def test_command_verb(sentence, verb):
    assert codes.command_verb(sentence) == verb


def test_commands_and_distinct_actions():
    got = c(
        "Take Zorvan in the morning. Take it with water. Do not chew it. "
        "If you feel dizzy, call your doctor. Zorvan is white."
    )
    assert got["command_sentences"] == 3
    assert got["conditional_commands"] == 1
    assert got["distinct_actions"] == 3  # take, not chew, call
    assert codes.conditional_verb("When you travel, keep it cool") == "keep"
    assert codes.conditional_verb("Zorvan helps, and that is all") is None


def test_numbers_of_each_kind():
    got = c(
        "About 12% of people had headache. Headache happened in 1 in 10 people, or 3 out of "
        "every 100. Take 5 mg twice a day, every 12 hours, or 0.5 mL daily. Some had a rash."
    )
    assert got["percentages"] == 1
    assert got["one_in_n"] == 2
    assert got["frequencies"] == 3  # twice a day, every 12 hours, daily
    assert got["doses"] == 2
    assert got["risk_sentences"] == 0  # "had headache" and "happened" are not risk words: a limit


def test_risk_statements_with_and_without_a_number():
    got = c(
        "Zorvan may cause headache. Headache is common and happened in 12% of people. "
        "Rash is rare. Keep it dry."
    )
    assert got["risk_sentences"] == 3
    assert got["risk_sentences_with_number"] == 1


def test_vague_words_core_and_extended():
    got = c("Some people may get a rash. It can be common or rare. It might sometimes itch.")
    assert got["vague_core"] == 5  # some, may, can, common, rare
    assert got["vague_extended"] == 2  # might, sometimes


def test_terms_followed_by_an_explanation():
    got = c(
        "You may get hypokalemia (low potassium in your blood). Your liver enzyme (ALT) may rise. "
        "Zorvan (zor-VAN) is a tablet. See the list (see section 5). It had a rash (1 in 10). "
        "A condition called neutropenia, also known as low white cells, may happen. "
        "Call your doctor right away."
    )
    assert got["explained_in_brackets"] == 1
    assert got["abbreviations_in_brackets"] == 1
    assert got["explained_called"] == 2  # "called" and "also known as", not "Call your doctor"


def test_a_bracket_without_words_is_nothing():
    got = c("A note ( - , ) and another (* *) here.")
    assert got["explained_in_brackets"] == 0 and got["abbreviations_in_brackets"] == 0


def test_long_sentences_and_long_sections():
    long = " ".join(["word"] * 45) + "."
    got = c(f"What is Zorvan? {long} How should I take Zorvan? Take it once a day.")
    assert got["sentences_over_20"] == 1 and got["sentences_over_40"] == 1
    assert got["longest_sentence_words"] == 45
    assert got["sections"] == 2 and got["longest_section_words"] == 45
    assert got["sections_over_250"] == 0
    pres = c(f"5 WARNINGS {long}", kind="prescriber")
    assert pres["sections"] == 0 and pres["longest_section_words"] == 0


def test_whom_to_call_and_when():
    got = c(
        "Call your healthcare provider right away if you have a rash. Tell your doctor about "
        "all the medicines you take. Call 911. Ask questions."
    )
    assert got["contact_sentences"] == 3  # call ... provider, tell ... doctor, call 911
    assert got["contact_sentences_with_when"] == 1


def test_every_field_is_an_integer():
    got = c("")
    assert set(got) == set(codes.FIELDS) and all(v == 0 for v in got.values())


def test_the_codes_table_has_no_text_and_one_row_per_text(tmp_path):
    root = write_export(tmp_path / "bulk")
    out = tmp_path / "t"
    tables.Builder(
        tables.parts_from_manifest(root, "2026-11-13"), out, "2026-11-13", log=lambda s: None
    ).run()
    n = codes.build(out, workers=1, batch_size=3, log=lambda s: None)
    t = pq.read_table(out / "codes.parquet")
    assert t.num_rows == n > 0
    assert "text" not in t.column_names
    rows = t.to_pylist()
    pt = [r for r in rows if r["side"] == "patient"]
    assert pt and all(r["patient_text_id"].startswith(r["section"] + ":") for r in pt)
    assert all(r["patient_text_id"] is None for r in rows if r["side"] == "prescriber")
    assert {r["code_version"] for r in rows} == {codes.CODE_VERSION}
    labels = {r["set_id"]: r for r in pq.read_table(out / "labels.parquet").to_pylist()}
    guide = next(r for r in pt if r["set_id"] == "set-aaaa")
    assert guide["patient_text_id"] == labels["set-aaaa"]["t_medication_guide_id"]


def test_a_parallel_codes_run_gives_the_same_rows(tmp_path):
    root = write_export(tmp_path / "bulk")
    out = tmp_path / "t"
    tables.Builder(
        tables.parts_from_manifest(root, "2026-11-13"), out, "2026-11-13", log=lambda s: None
    ).run()
    codes.build(out, workers=1, batch_size=2, log=lambda s: None)
    one = pq.read_table(out / "codes.parquet")
    codes.build(out, workers=2, batch_size=2, log=lambda s: None)
    assert pq.read_table(out / "codes.parquet").equals(one)


def test_version_1_brackets_names_pronunciations_and_plain_first():
    got = c(
        "Take ZORVAN\u00ae (zorvanide tablets). Zorvan (zor van' ide) is a tablet. "
        "You may have trouble sleeping (insomnia). It is used with Brandex (zorvanide). "
        "Use it (sometimes taken at night) as told."
    )
    assert got["explained_in_brackets"] == 1  # only "trouble sleeping (insomnia)"


def test_version_1_vague_words_leave_out_the_month_and_reporting():
    got = c("Revised: May 2024. You may report side effects to FDA. You may get a rash.")
    assert got["vague_core"] == 1


def test_version_1_contact_is_not_informing_patients():
    got = c(
        "Inform patients about the risks. Your doctor may tell you to stop. "
        "Advise patients to contact their healthcare provider if a rash occurs."
    )
    assert got["contact_sentences"] == 1
    assert got["contact_sentences_with_when"] == 1


def test_version_1_risk_size_numbers_only():
    got = c(
        "5.6 Liver problems Zorvan may cause liver problems [see Warnings and Precautions (5.1)]. "
        "Rash may occur after 1 dose of 10 mg each day. Rash occurred in 12 patients (3%). "
        "The risk was twice as high in older adults."
    )
    assert got["risk_sentences"] == 4
    assert got["risk_sentences_with_number"] == 2


def test_version_1_one_in_n_leaves_out_packaging():
    got = c("PACKAGING: 30 in 1 BOX. About 1 in 500 people had it.")
    assert got["one_in_n"] == 1


def test_every_code_has_a_status_and_the_tables_split_by_it():
    assert set(codes.STATUS) == set(codes.FIELDS) - set(codes.COUNTS) | set(codes.STRUCTURED_FIELDS)
    assert set(codes.STATUS.values()) == {"trusted", "experimental"}
    assert not set(codes.EXPERIMENTAL) & set(codes.SCHEMA.names)
    assert set(codes.EXPERIMENTAL) <= set(codes.EXPERIMENTAL_SCHEMA.names)
