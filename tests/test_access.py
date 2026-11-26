"""The easy-access layer: built into the invented pack of ``tests.test_pack`` (invented labels, no
real label text), checked row for row, and broken on purpose."""

import gzip
import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from plainpairs import access, codes, pack, xlsx
from tests.test_pack import made  # noqa: F401  (the fixture)
from tests.test_release import _nci_tables, built  # noqa: F401  (the fixture made needs)

ROOT = Path(__file__).resolve().parents[1]


def manifest(p):
    return json.loads((p / "manifest.json").read_text(encoding="utf-8"))


# --- cells ---------------------------------------------------------------------------------------


def test_cells_are_written_one_way():
    f32 = pa.float32()
    assert access.cell(None) == "" and access.cell(True) == "1" and access.cell(False) == "0"
    assert access.cell(["a", "b"], pa.list_(pa.string())) == "a; b"
    assert access.cell(pa.scalar(0.2, f32).as_py(), f32) == "0.2"  # not 0.20000000298023224
    assert access.cell(pa.scalar(10.0, f32).as_py(), f32) == "10.0"
    assert access.cell(0.1 + 0.2) == repr(0.1 + 0.2)  # a 64-bit float keeps every digit
    assert access.cell(float("nan")) == "NaN" and access.cell(float("-inf")) == "-Inf"
    assert access.cell(date(2026, 11, 26)) == "2026-11-26" and access.cell(7) == "7"
    assert access.book_value(True) == 1 and access.book_value(None) is None
    assert access.book_value(pa.scalar(0.2, f32).as_py(), f32) == 0.2
    assert access.book_value(["x"], pa.list_(pa.string())) == "x"


def test_structs_are_flattened_at_every_level():
    t = pa.table({"a": [{"b": 1, "c": {"d": "x"}}], "e": [2]})
    assert access.flat(t).column_names == ["a.b", "a.c.d", "e"]


def test_the_same_rows_give_the_same_gzipped_bytes(tmp_path):
    rows = [["1", "a, with a comma"], ["2", 'a "quote"']]
    one = access.write_csv(tmp_path / "one.csv.gz", ["n", "s"], rows)
    two = access.write_csv(tmp_path / "two.csv.gz", ["n", "s"], rows)
    assert (tmp_path / "one.csv.gz").read_bytes() == (tmp_path / "two.csv.gz").read_bytes()
    assert one == two and one["rows"] == 2
    plain = gzip.decompress((tmp_path / "one.csv.gz").read_bytes())
    assert len(plain) == one["csv_bytes"]
    assert list(access.read_csv(tmp_path / "one.csv.gz")) == [["n", "s"], *rows]


def test_a_field_past_the_csv_modules_default_limit_reads_back(tmp_path):
    long = "w " * 100_000  # 200,000 characters: a long prescriber section
    access.write_csv(tmp_path / "t.csv.gz", ["text"], [[long]])
    assert list(access.read_csv(tmp_path / "t.csv.gz")) == [["text"], [long]]


# --- the layer in a built pack -------------------------------------------------------------------


def test_the_layer_is_built_and_passes(made):  # noqa: F811
    _out, p, m = made
    assert [f["path"] for f in m["access_files"]] == access.expected_names(m)
    assert m["access_files"][0]["path"] == access.START_HERE
    assert access.problems(p, m) == [] and pack.check_pack(p) == []
    header, rows = access.table_cells(p / "data/current/labels.parquet")
    got = list(access.read_csv(p / access.START_HERE))
    assert got[0] == header and got[1:] == list(rows)
    assert "t_medication_guide.flesch_kincaid" in header and "served_by_dailymed" in header
    assert not any(c == "text" for c in header)  # no label text
    a = m["access"]
    assert a["start_here_rows"] == m["facts"]["current_labels"] and a["workbook"] == "whole"
    for f in m["files"]:  # a gzipped CSV beside every Parquet file
        assert (p / f["path"].replace(".parquet", ".csv.gz")).exists()


def test_fields_cover_every_column_with_a_meaning(made):  # noqa: F811
    _out, p, m = made
    rows = list(access.read_csv(p / access.FIELDS_FILE))
    assert rows[0] == list(access.FIELDS_HEADER)
    have = {(r[0], r[1]) for r in rows[1:]}
    for f in m["files"]:
        for name in access.flat_schema(p / f["path"]).names:
            assert (f["config"], name) in have
    assert all(r[3] for r in rows[1:])  # every column has a meaning
    by = {(r[0], r[1]): r for r in rows[1:]}
    assert by[("current_labels", "configuration")][4] == "current"
    assert by[("current_labels", "has_medication_guide")][4].startswith("1 or 0")
    assert by[("current_labels", "product_name")][4] == ""  # free text: no list of values
    assert "Flesch-Kincaid" in by[("current_labels", "t_medication_guide.flesch_kincaid")][3]
    assert ("start_here", "set_id") in have and ("pairs_sample", "prescriber_text") in have


def test_the_codebook_holds_the_trusted_codes_and_the_ten_heading_keys(made):  # noqa: F811
    _out, p, _m = made
    rows = list(access.read_csv(p / access.CODEBOOK_FILE))[1:]
    names = [r[1] for r in rows if r[0] == "code"]
    assert names == [k for k, (_c, s) in codes.CODEBOOK.items() if s == "trusted"]
    assert all(r[6] == "trusted" and r[5] for r in rows if r[0] == "code")
    keys = {r[1]: r for r in rows if r[0] == "heading_key"}
    assert len(keys) == 10
    for key, r in keys.items():  # the status is the pack's own
        assert r[6] in ("rule_released", "similarity_only", "pending_hand_check", ""), key


def test_the_heading_keys_check_is_the_method_docs():
    doc = (ROOT / "docs" / "method.md").read_text(encoding="utf-8")
    for key, (label, _o, (y, pt, n), share, interval) in access.KEY_TEXT.items():
        row = f"| {label} | {y} | {pt} | {n} | {share} ({interval}) |"
        assert row in doc, key
        status = "`rule_released`" if int(share.rstrip("%")) >= 80 else "`similarity_only`"
        assert re.search(re.escape(row) + r" " + re.escape(status), doc), key


def test_the_codes_checks_are_the_codebooks():
    doc = (ROOT / "docs" / "codebook.md").read_text(encoding="utf-8").replace("`", "")
    for name, (label, _d, check) in access.CODE_TEXT.items():
        row = next(line for line in doc.splitlines() if line.startswith(f"| {label} |"))
        for fraction in re.findall(r"\d+/\d+", check):
            assert fraction in row, (name, fraction)
    trusted = {k for k, (_c, s) in codes.CODEBOOK.items() if s == "trusted"}
    assert set(access.CODE_TEXT) == trusted


def test_the_pairs_sample_holds_released_text_only(made):  # noqa: F811
    _out, p, m = made
    rows = list(xlsx.read_data_rows(p / access.PAIRS_BOOK, 2))
    assert rows[0] == list(access.PAIR_COLUMNS)
    assert len(rows) - 1 == m["access"]["pairs_rows"] > 0
    released = set(pq.read_table(p / "data/current/text_patient.parquet")["set_id"].to_pylist())
    assert {r[0] for r in rows[1:]} <= released
    readme = [r[0] for r in xlsx.read_data_rows(p / access.PAIRS_BOOK, 1) if r]
    assert any(line.startswith("Not medical information.") for line in readme)
    assert readme.index(pack.paper_citation()) < readme.index(pack.citation("0.1.0", "2026-11-15"))


def test_a_long_text_is_cut_with_a_visible_mark():
    text, cut = access._cut("x" * (xlsx.MAX_CELL + 10), "text_prescriber")
    assert cut and len(text) == xlsx.MAX_CELL and text.endswith("text_prescriber table]")
    assert access._cut("short", "text_patient") == ("short", False)


def test_the_labels_workbook_becomes_a_sample_past_its_size(made, tmp_path):  # noqa: F811
    _out, p, m = made
    schema = access.flat_schema(p / "data/current/labels.parquet")
    values = list(access.table_values(p / "data/current/labels.parquet"))
    q = tmp_path / "q"
    q.mkdir()
    path, sample, picked = access.write_labels_book(
        q, m, list(schema.names), list(schema.types), values, [], max_bytes=1
    )
    assert sample and path.name == access.XLSX_SAMPLE
    assert len(picked) == min(access.SAMPLE_ROWS, len(values))
    assert not (q / access.XLSX_WHOLE).exists()


# --- broken on purpose ---------------------------------------------------------------------------


def test_a_missing_or_changed_layer_file_fails_the_pack_check(made):  # noqa: F811
    _out, p, _m = made
    (p / access.FIELDS_FILE).write_text("table\n", encoding="utf-8")
    assert any("does not match" in x for x in pack.check_pack(p))
    (p / access.FIELDS_FILE).unlink()
    assert any(
        f"{access.FIELDS_FILE}: in the manifest but missing" in x for x in pack.check_pack(p)
    )
    m = manifest(p)
    m["access_files"] = [f for f in m["access_files"] if f["path"] != access.FIELDS_FILE]
    (p / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    assert any("a file of the easy-access layer is missing" in x for x in pack.check_pack(p))


def test_a_later_version_without_the_layer_fails(made):  # noqa: F811
    _out, p, _m = made
    m = manifest(p)
    m.pop("access_files")
    assert access.problems(p, {**m, "version": "0.1.0"}) == []
    assert "the easy-access layer is missing" in access.problems(p, {**m, "version": "0.2.0"})[0]
    assert access.problems(p, {**m, "version": "0.2.1"})


def test_a_changed_cell_fails_the_row_check(made):  # noqa: F811
    _out, p, m = made
    rows = list(access.read_csv(p / access.START_HERE))
    rows[1][2] = "changed"
    access.write_csv(p / access.START_HERE, rows[0], rows[1:])
    entry = m["access_files"][0]
    entry.update(
        bytes=(p / access.START_HERE).stat().st_size, sha256=access._sha(p / access.START_HERE)
    )
    assert any("row 1 differs" in x for x in access.problems(p, m))


def test_excel_limits_are_checked(made, monkeypatch):  # noqa: F811
    _out, p, m = made
    monkeypatch.setattr(xlsx, "MAX_ROWS", 2)
    monkeypatch.setattr(xlsx, "MAX_COLUMNS", 3)
    monkeypatch.setattr(xlsx, "MAX_CELL", 4)
    found = " ".join(access.problems(p, m))
    assert "over Excel's 2 rows" not in found  # the message gives the count with commas
    assert "rows, over Excel's" in found and "columns, over Excel's" in found
    assert "characters" in found


def test_a_csv_past_the_cap_is_left_out_and_named(made, tmp_path, monkeypatch):  # noqa: F811
    out, _p, _m = made
    monkeypatch.setattr(access, "CSV_MAX_BYTES", 1)  # every gzipped CSV passes it
    q = tmp_path / "q"
    m = pack.build_pack(out, q, "0.2.0", today=lambda: "2026-11-26")
    assert len(m["access"]["csv_left_out"]) == len(m["files"])
    assert [f["path"] for f in m["access_files"]] == access.expected_names(m)
    assert len(m["access_files"]) == 5 and pack.check_pack(q) == []
    card = (q / "README.md").read_text(encoding="utf-8")
    assert "Left out as CSV on both hosts" in card and "`data/current/labels.parquet`" in card
    k = tmp_path / "k"
    pack.build_kaggle(q, k)
    assert pack.check_kaggle(k, q) == []


def test_a_plain_csv_past_the_cap_is_left_out_on_kaggle_only(made, tmp_path, monkeypatch):  # noqa: F811
    out, _p, m = made
    gz = max(f["bytes"] for f in m["access_files"] if "config" in f)
    plain = max(f["csv_bytes"] for f in m["access_files"] if "config" in f)
    assert plain > gz
    monkeypatch.setattr(access, "CSV_MAX_BYTES", gz + 1)
    q = tmp_path / "q"
    m2 = pack.build_pack(out, q, "0.2.0", today=lambda: "2026-11-26")
    assert m2["access"]["csv_left_out"] == [] and m2["access"]["kaggle_csv_left_out"]
    k = tmp_path / "k"
    meta = pack.build_kaggle(q, k)
    gone = m2["access"]["kaggle_csv_left_out"]
    assert all(not (k / f"{c}.csv").exists() for c in gone)
    assert pack.check_kaggle(k, q) == []
    assert "Left out as CSV on Kaggle" in meta["description"]


# --- the Kaggle copies, the card -----------------------------------------------------------------


def test_the_kaggle_folder_holds_the_layer_plain(made, tmp_path):  # noqa: F811
    _out, p, _m = made
    k = tmp_path / "k"
    pack.build_kaggle(p, k)
    assert pack.check_kaggle(k, p) == []
    names = sorted(x.name for x in k.iterdir())
    assert names[0] == access.START_HERE and "README.md" not in names
    assert "current_labels.csv" in names and not any(n.endswith(".gz") for n in names)
    gz = p / "data/current/labels.csv.gz"
    assert (k / "current_labels.csv").read_bytes() == gzip.decompress(gz.read_bytes())
    assert (k / access.PAIRS_BOOK).read_bytes() == (p / access.PAIRS_BOOK).read_bytes()
    (k / "current_labels.csv").write_text("changed", encoding="utf-8")
    assert any("current_labels.csv: differs" in x for x in pack.check_kaggle(k, p))
    (k / "README.md").write_text("# a card", encoding="utf-8")
    assert any("README.md" in x for x in pack.check_kaggle(k, p))


def test_the_card_opens_with_start_here_after_the_box(made):  # noqa: F811
    _out, p, _m = made
    card = (p / "README.md").read_text(encoding="utf-8")
    body = card.split("\n---\n", 1)[1]
    assert body.index("> **Not medical information.**") < body.index("## Start here")
    assert re.findall(r"^## (.+)$", body, re.M)[0] == "Start here"
    assert "$" not in card  # no placeholder left, and nothing the Hub could read as math
    assert access.r_lines() in card and access.python_lines() in card
    assert pack.start_here_problems(card) == []
    moved = card.replace("## Start here\n", "## Start\n")
    assert pack.start_here_problems(moved)
    front = card.split("\n---\n", 1)[0]
    assert ".csv" not in front and ".xlsx" not in front  # the configs point at Parquet only


def test_the_reading_table_is_computed_and_0_1_0s_is_kept():
    assert pack.reading_table(None) == pack.READING_LEVELS_0_1_0
    rows = [
        [pack.READING_ROWS[0][0], "current", 8.67, 11.10, 0.7191, 0.9921, 7182],
        [pack.READING_ROWS[1][0], "current", 10.86, 12.94, 0.9501, 0.9951, 7182],
        [pack.READING_ROWS[2][0], "unlisted", 10.70, 12.85, 0.9311, 0.9951, 4824],
        [pack.READING_ROWS[3][0], "current", 8.58, 11.21, 0.6691, 0.9951, 4576],
        [pack.READING_ROWS[4][0], "nci", 8.65, 11.11, 0.8299, 1.0, 147],
        [pack.READING_ROWS[5][0], "nci", 13.49, 15.08, 1.0, 1.0, 242],
    ]
    assert pack.reading_table(rows) == pack.READING_LEVELS_0_1_0
    rows[0][2] = None
    assert "| none |" in pack.reading_table(rows)


def test_the_card_and_kaggle_code_runs_on_the_pack(made, tmp_path, monkeypatch):  # noqa: F811
    pd = pytest.importorskip("pandas")
    _out, p, _m = made
    monkeypatch.chdir(p)
    space: dict = {}
    exec(access.python_lines(), space)
    x = space["x"]
    assert len(x) > 0 and {"text_patient", "text_prescriber", "product_name"} <= set(x.columns)
    assert isinstance(x, pd.DataFrame)


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="R is not installed")
def test_the_r_lines_run_on_the_pack(made):  # noqa: F811
    _out, p, _m = made
    script = (
        access.r_lines()
        + '\ncat(nrow(x), "rows;", all(c("text_patient", "text_prescriber") %in% names(x)), "\\n")'
    )
    got = subprocess.run(
        ["Rscript", "-e", script], cwd=p, capture_output=True, text=True, check=True
    )
    n, _, ok = got.stdout.split()
    assert int(n) > 0 and ok == "TRUE"
