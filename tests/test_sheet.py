"""The hand sheet: drawing, writing, and checking a filled sheet. Invented text only."""

import csv

import pytest

from plainpairs import sheet, xlsx


def pairs():
    out = []
    for key in ("what_is", "storage"):
        for i in range(6):
            out.append(
                {
                    "set_id": f"set-{key}-{i}",
                    "version": 1,
                    "kind": "medication_guide",
                    "segment_index": 1,
                    "heading_key": key,
                    "patient_text_id": f"medication_guide:{key}{i % 4}",
                    "mapped_present": ["indications_and_usage"]
                    if key == "what_is"
                    else ["how_supplied_storage"],
                    "seg_start": 0,
                    "seg_end": 20,
                }
            )
    out.append({**out[0], "heading_key": "general", "mapped_present": []})
    return out


def test_draw_is_reproducible_and_takes_one_segment_per_text():
    meds = {f"set-what_is-{i}": "zorvanide" if i < 2 else None for i in range(6)}
    a = sheet.draw(pairs(), meds, per_key=3, seed=7)
    b = sheet.draw(pairs(), meds, per_key=3, seed=7)
    assert a == b
    assert [p["heading_key"] for p in a] == ["storage"] * 3 + ["what_is"] * 3  # heading order
    assert len({p["patient_text_id"] for p in a if p["heading_key"] == "what_is"}) == 3
    assert [p["row"] for p in a] == [1, 2, 3, 4, 5, 6]
    assert all(p["section"] for p in a)
    many = sheet.draw(pairs(), meds, per_key=10, seed=7)
    assert len([p for p in many if p["heading_key"] == "what_is"]) == 4  # only 4 distinct texts


def test_first_words_cuts_long_sections():
    assert sheet.first_words("a b c", 5) == "a b c"
    assert sheet.first_words("a b c d", 2) == "a b [... first 2 of 4 words]"


def test_wilson_interval():
    assert sheet.wilson(0, 0) == (None, None)
    low, high = sheet.wilson(8, 10)
    assert 0.4 < low < 0.5 and 0.94 < high < 0.96


def write_sheet(tmp_path):
    picks = sheet.draw(pairs(), {}, per_key=2, seed=1)
    patient = {(p["set_id"], p["kind"]): "What is Zorvan? A made-up medicine." for p in picks}
    prescriber = {
        (p["set_id"], p["section"]): "1 INDICATIONS AND USAGE For testing." for p in picks
    }
    x, k = tmp_path / "sheet.xlsx", tmp_path / "key.csv"
    sheet.write(picks, patient, prescriber, x, k)
    return picks, x, k


def test_the_sheet_is_blind_and_its_key_is_separate(tmp_path):
    picks, x, k = write_sheet(tmp_path)
    visible = next(s for s in xlsx.read_workbook(x) if not s.hidden)
    header = visible.rows[0][1]
    assert header[0] == "Row" and "similar" not in " ".join(header).lower()
    flat = " ".join(" ".join(cells) for _, cells in visible.rows)
    assert "what_is" not in flat and "mapped" not in flat and "0." not in flat
    with k.open() as fh:
        assert [r["heading_key"] for r in csv.DictReader(fh)] == [p["heading_key"] for p in picks]


def fill(x, answers):
    rows = [list(cells) for _, cells in next(s for s in xlsx.read_workbook(x) if not s.hidden).rows]
    plain = xlsx.Style()
    filled = [[(c, plain) for c in rows[0]]]
    for r, a in zip(rows[1:], answers, strict=True):
        cells = (r + [""] * 6)[:6]
        cells[4] = a
        filled.append([(c, plain) for c in cells])
    xlsx.write_workbook(x, xlsx.Sheet(name="Topic check", rows=filled))


def test_check_reports_the_share_per_heading(tmp_path):
    _, x, k = write_sheet(tmp_path)
    fill(x, ["yes", "Partly", "no", ""])
    out = sheet.check(x, k)
    assert out["storage"]["share_yes_or_partly"] == 1.0
    assert out["storage"]["rule"] == "regulation rule released"
    assert out["what_is"]["no"] == 1 and out["what_is"]["blank"] == 1
    assert out["what_is"]["rule"] == "similarity only, flagged"


def test_check_refuses_a_sheet_that_is_not_the_hand_sheet(tmp_path):
    x = tmp_path / "other.xlsx"
    xlsx.write_workbook(x, xlsx.Sheet(name="S", rows=[[("Something", xlsx.Style())]]))
    with pytest.raises(sheet.SheetError, match="header row"):
        sheet.check(x, tmp_path / "key.csv")
