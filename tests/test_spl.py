"""The SPL structure reader, on invented documents (no real label text)."""

import pytest

from plainpairs import spl

SET_ID = "AAAAAAAA-1111-2222-3333-444444444444"


def doc(body: str, set_id: str = SET_ID, version: int = 3) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<document xmlns="urn:hl7-org:v3">
  <id root="BBBBBBBB-0000-0000-0000-000000000001"/>
  <code code="34391-3"/>
  <effectiveTime value="20260101"/>
  <setId root="{set_id}"/>
  <versionNumber value="{version}"/>
  <component><structuredBody>{body}</structuredBody></component>
</document>""".encode()


def section(code: str, title: str, text: str, subs: str = "") -> str:
    return (
        f'<component><section><id root="x"/><code code="{code}"/><title>{title}</title>'
        f"<text>{text}</text>{subs}</section></component>"
    )


def kinds(blocks):
    return [(b.kind, b.text) for b in blocks]


GUIDE = section(
    "42231-1",
    "MEDICATION GUIDE",
    '<paragraph><content styleCode="bold">What is the most important information I should '
    "know about Zorvan?</content></paragraph>"
    "<paragraph>Zorvan is an invented medicine used only in tests.</paragraph>"
    '<paragraph><content styleCode="bold">Tell your doctor if you:</content></paragraph>'
    "<list><item>have a rash</item><item>feel tired</item></list>"
    '<paragraph><content styleCode="bold">Call your doctor right away.</content></paragraph>'
    '<paragraph><content styleCode="bold">What is Zorvan?</content> Zorvan is a made-up '
    "word. It has no meaning.</paragraph>"
    '<paragraph><content styleCode="Bold">How should I store Zorvan?</content><br/>'
    "Keep it in a dry place.</paragraph>"
    '<paragraph><renderMultiMedia referencedObject="img1"/>Use the cap. '
    "\u2022 Turn it left \u2022 Lift it off</paragraph>",
)


def test_identity_and_guide_blocks():
    d = spl.parse_document(doc(GUIDE))
    assert d["set_id"] == SET_ID.lower()
    assert (d["version"], d["document_type"]) == (3, "34391-3")
    assert d["document_id"].startswith("bbbbbbbb")
    assert kinds(d["fields"]["spl_medguide"]) == [
        ("title", "MEDICATION GUIDE"),
        ("heading", "What is the most important information I should know about Zorvan?"),
        ("paragraph", "Zorvan is an invented medicine used only in tests."),
        ("paragraph", "Tell your doctor if you:"),
        ("item", "have a rash"),
        ("item", "feel tired"),
        ("paragraph", "Call your doctor right away."),
        ("heading", "What is Zorvan?"),
        ("paragraph", "Zorvan is a made-up word. It has no meaning."),
        ("heading", "How should I store Zorvan?"),
        ("paragraph", "Keep it in a dry place."),
        ("paragraph", "Use the cap."),
        ("item", "Turn it left"),
        ("item", "Lift it off"),
    ]
    assert d["fields"]["spl_medguide"][4].list_depth == 1
    assert d["codes"]["42231-1"] == 1


def test_identity_only():
    d = spl.identity(doc(GUIDE, version=7))
    assert d["version"] == 7
    assert spl.parse_document(doc(GUIDE), keep=False)["fields"] == {}


def test_tables_layout_and_data():
    layout = (
        "<table><caption>An invented box</caption><tbody><tr><td>This cell holds a whole "
        "invented sentence of prose, long enough to read as text.</td></tr>"
        "<tr><td>Another long invented sentence sits in this cell as well, as prose."
        "</td></tr></tbody></table>"
    )
    data = (
        "<table><thead><tr><th>Dose</th><th>Times</th></tr></thead><tbody>"
        "<tr><td>10 mg</td><td>once</td></tr><tr><td>20 mg</td><td>twice</td></tr>"
        "</tbody></table>"
    )
    d = spl.parse_document(doc(section("42230-3", "PATIENT INFORMATION", layout + data)))
    blocks = d["fields"]["spl_patient_package_insert"]
    got = [(b.kind, b.table) for b in blocks]
    assert got[:4] == [("title", 0), ("caption", 1), ("cell", 1), ("cell", 1)]
    assert got[4:] == [("data_cell", 2)] * 6


def test_subsections_nesting_and_skips():
    sub = section("42232-9", "5.1 Invented subsection", "<paragraph>Sub text here.</paragraph>")
    warn = section(
        "43685-7",
        "5 WARNINGS AND PRECAUTIONS",
        "<paragraph>Intro text.</paragraph>",
        subs=sub + "<excerpt><highlight><text>Not read.</text></highlight></excerpt>",
    )
    guide = section("42231-1", "MEDICATION GUIDE", "<paragraph>Guide words.</paragraph>")
    counsel = section("34076-0", "17 PATIENT COUNSELING", "<paragraph>Counsel.</paragraph>", guide)
    d = spl.parse_document(doc(warn + counsel))
    w = d["fields"]["warnings_and_cautions"]
    assert [(b.kind, b.depth) for b in w] == [
        ("title", 0),
        ("paragraph", 0),
        ("title", 1),
        ("paragraph", 1),
    ]
    assert "Not read." not in spl.all_text(w)
    # a section nested in a section of another field is read for both, as the JSON does
    assert spl.all_text(d["fields"]["spl_medguide"]) == "MEDICATION GUIDE Guide words."
    assert "Guide words." in spl.all_text(d["fields"]["information_for_patients"])
    # a section of the same field nested in itself is read once
    assert "precautions" in d["fields"]


def test_section_blocks_joins_fields():
    older = section("34071-1", "WARNINGS", "<paragraph>W.</paragraph>") + section(
        "42232-9", "PRECAUTIONS", "<paragraph>P.</paragraph>"
    )
    supplied = section("34069-5", "HOW SUPPLIED", "<paragraph>H.</paragraph>") + section(
        "44425-7", "STORAGE", "<paragraph>S.</paragraph>"
    )
    d = spl.parse_document(doc(older + supplied + GUIDE))
    out = spl.section_blocks(d["fields"])
    assert spl.all_text(out["warnings_and_precautions"]) == "WARNINGS W. PRECAUTIONS P."
    assert spl.all_text(out["how_supplied_storage"]) == "HOW SUPPLIED H. STORAGE S."
    assert "medication_guide" in out
    newer = section("43685-7", "5 WARNINGS", "<paragraph>N.</paragraph>")
    out = spl.section_blocks(spl.parse_document(doc(newer + older))["fields"])
    assert spl.all_text(out["warnings_and_precautions"]) == "5 WARNINGS N."


def test_units_and_measures_leave_out_headings():
    d = spl.parse_document(doc(GUIDE))
    blocks = d["fields"]["spl_medguide"]
    u = spl.units(blocks)
    assert "What is Zorvan?" not in u
    assert "MEDICATION GUIDE" not in u
    assert u[:4] == [
        "Zorvan is an invented medicine used only in tests",
        "Tell your doctor if you:",
        "have a rash",
        "feel tired",
    ]
    assert "Zorvan is a made-up word" in u and "It has no meaning" in u
    m = spl.measure(blocks)
    assert m["sentences"] == len(u)
    assert m["blocks_heading"] == 3
    assert m["blocks_item"] == 4
    assert m["words"] > 0 and m["flesch_kincaid"] is not None


def test_word_match():
    assert spl.word_match("A b, c.", "a B c")["match"] == "exact"
    near = spl.word_match("one two three " * 40 + "extra", "one two three " * 40)
    assert near["match"] == "near" and near["dice"] < 1
    assert spl.word_match("alpha beta", "gamma delta")["match"] == "not"
    assert spl.tokens("Caf\u00e9 \u2013 10 mg") == ["cafe", "10", "mg"]


def test_bad_documents():
    with pytest.raises(spl.SplError, match="well-formed"):
        spl.parse_document(b"<document><unclosed>")
    with pytest.raises(spl.SplError, match="well-formed"):
        spl.identity(b"not xml")
    with pytest.raises(spl.SplError, match="setId"):
        spl.identity(b'<document xmlns="urn:hl7-org:v3"><id root="x"/></document>')
