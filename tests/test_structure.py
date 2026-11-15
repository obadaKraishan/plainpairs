"""The structure step: an invented release part joined to invented corpus tables."""

import io
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq

from plainpairs import structure, tables
from tests.test_spl import GUIDE, doc, section

A = "aaaaaaaa-1111-2222-3333-444444444444"
B = "bbbbbbbb-1111-2222-3333-444444444444"
C = "cccccccc-1111-2222-3333-444444444444"
D = "dddddddd-1111-2222-3333-444444444444"
E = "eeeeeeee-1111-2222-3333-444444444444"

INDICATIONS = section(
    "34067-9", "1 INDICATIONS", "<paragraph>Zorvan is indicated in invented tests.</paragraph>"
)
GUIDE_TEXT = (
    "MEDICATION GUIDE What is the most important information I should know about Zorvan? "
    "Zorvan is an invented medicine used only in tests. Tell your doctor if you: have a rash "
    "feel tired Call your doctor right away. What is Zorvan? Zorvan is a made-up word. It has "
    "no meaning. How should I store Zorvan? Keep it in a dry place. Use the cap. \u2022 Turn "
    "it left \u2022 Lift it off"
)


def inner(xml):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("label.xml", xml)
        z.writestr("picture.jpg", b"not read")
    return buf.getvalue()


def make_part(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("prescription/1_a.zip", inner(doc(GUIDE + INDICATIONS, set_id=A, version=3)))
        z.writestr("prescription/2_b.zip", inner(doc(GUIDE, set_id=B, version=2)))  # old version
        z.writestr("prescription/3_c.zip", inner(doc(INDICATIONS, set_id=C, version=1)))
        z.writestr("prescription/4_x.zip", inner(doc(GUIDE, set_id="ffffffff-0000", version=1)))
        z.writestr("prescription/5_e.zip", inner(doc(GUIDE, set_id=E, version=1)))
        z.writestr("prescription/6_bad.zip", inner(b"<document"))


def make_tables(d):
    d.mkdir()
    pq.write_table(
        pa.table(
            {
                "set_id": [A, B, C, D, E],
                "version": pa.array([3, 3, 1, 1, 1], pa.int32()),
            }
        ),
        d / "labels.parquet",
    )
    base = {
        "source": "s",
        "export_date": "2026-11-13",
        "version": 3,
        "part": "text",
        "part_index": 0,
        "sha256": "x",
        "has_copyright_mark": False,
        "text_has_copyright_mark": False,
    }
    patient = [
        {**base, "set_id": A, "section": "medication_guide", "text": GUIDE_TEXT},
        {**base, "set_id": C, "section": "medication_guide", "text": "A guide the XML lacks."},
        {**base, "set_id": E, "section": "medication_guide", "text": "Entirely other words."},
    ]
    prescriber = [
        {
            **base,
            "set_id": A,
            "section": "indications_and_usage",
            "text": "1 INDICATIONS Zorvan is indicated in invented tests.",
        },
    ]
    pq.write_table(pa.Table.from_pylist(patient, tables.TEXT_SCHEMA), d / "text_patient.parquet")
    pq.write_table(
        pa.Table.from_pylist(prescriber, tables.TEXT_SCHEMA), d / "text_prescriber.parquet"
    )


def test_build_and_decide(tmp_path):
    part = tmp_path / "dm_spl_release_human_rx_part1.zip"
    make_part(part)
    make_tables(tmp_path / "tables")
    out = tmp_path / "structure"
    lines = []
    summary = structure.build(
        [part], "2026-11-13", tmp_path / "tables", out, workers=1, log=lines.append
    )
    assert summary["counts"]["parse_errors"] == 1
    assert summary["counts"]["other:jpg"] == 6
    index = pq.read_table(out / "index.parquet").to_pylist()
    assert len(index) == 6
    by = {r["set_id"]: r for r in index if r["set_id"]}
    assert by[A]["version_match"] and by[A]["fields"] == ["indications_and_usage", "spl_medguide"]
    assert by[B]["in_corpus"] and not by[B]["version_match"]
    assert not by["ffffffff-0000"]["in_corpus"]
    rows = {
        (r["set_id"], r["section"]): r["structured"]
        for r in pq.read_table(out / "structure.parquet").to_pylist()
    }
    guide = rows[(A, "medication_guide")]
    assert guide["xml_match"] == "exact"
    assert guide["blocks_heading"] == 3 and guide["sentences"] > 0
    assert guide["parts"] >= 3
    assert rows[(A, "indications_and_usage")]["xml_match"] == "exact"
    assert rows[(C, "medication_guide")]["xml_match"] == "xml_missing"
    assert rows[(C, "indications_and_usage")]["xml_match"] == "json_missing"
    assert rows[(E, "medication_guide")]["xml_match"] == "not"
    assert rows[(E, "medication_guide")]["flesch_kincaid"] is None
    blocks = pq.read_table(out / "blocks.parquet")
    assert set(blocks["set_id"].to_pylist()) == {A, C, E}
    idx, struct = structure.read_structure(out)
    labels = [
        {"set_id": A, "version": 3, "t_medication_guide_sha256": "h"},
        {"set_id": B, "version": 3, "t_medication_guide_sha256": "h"},
        {"set_id": C, "version": 1, "t_medication_guide_sha256": "h"},
        {"set_id": D, "version": 1, "t_medication_guide_sha256": "h"},
        {"set_id": E, "version": 1, "t_medication_guide_sha256": "h"},
    ]
    got = structure.decide(labels, idx, struct)
    assert got[A] == {
        "configuration": "current",
        "structure_source": "dailymed_xml",
        "unlisted_reason": None,
    }
    assert got[B]["unlisted_reason"] == "other_version"
    assert got[C]["unlisted_reason"] == "patient_text_missing"
    assert got[D]["unlisted_reason"] == "not_in_release"
    assert got[E]["unlisted_reason"] == "patient_text_differs"
    assert {g["configuration"] for g in got.values()} == {"current", "unlisted"}


def test_length_codes_parts():
    from plainpairs import spl

    blocks = [
        spl.Block("title", "T"),
        spl.Block("paragraph", " ".join(["word"] * 45) + "."),
        spl.Block("heading", "What is it?"),
        spl.Block("item", "one two three"),
        spl.Block("data_cell", "10 mg"),
    ]
    got = structure.length_codes(blocks)
    assert got == {
        "sentences_over_20": 1,
        "sentences_over_40": 1,
        "longest_sentence_words": 45,
        "parts": 2,
        "longest_part_words": 45,
        "parts_over_250": 0,
    }
