"""The changes table, on invented exports only."""

import copy

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from plainpairs import changes, tables
from tests.label_samples import OLDER_WITH_INSERT, PLR_WITH_GUIDE
from tests.test_tables import write_export


def row(set_id, version=1, **kw):
    base = {"set_id": set_id, "version": version, "export_date": "2026-11-13"}
    base.update({c: None for c in changes.HASH_COLUMNS})
    base.update(harmonized=True, label_format="plr", has_copyright_mark=False)
    base.update(kw)
    return base


def test_compare_rows_names_every_kind_of_change():
    old = {
        "a": row("a", 1, p_boxed_warning_sha256="x", t_medication_guide_sha256="g"),
        "b": row("b", 1, t_medication_guide_sha256="g"),
        "c": row("c", 1, t_medication_guide_sha256="g"),
        "d": row("d", 1, t_medication_guide_sha256="g"),
        "e": row("e", 1, t_medication_guide_sha256="g"),
        "f": row("f", 2, t_patient_package_insert_sha256="i"),
        "g": row("g", 1),
    }
    new = {
        "a": row("a", 2, p_boxed_warning_sha256="x", t_medication_guide_sha256="g"),
        "b": row("b", 2, t_medication_guide_sha256="G"),
        "c": row("c", 1, t_medication_guide_sha256="g", t_patient_package_insert_sha256="i"),
        "d": row("d", 1, t_medication_guide_sha256="g", harmonized=False),
        "e": row("e", 1, t_medication_guide_sha256="g"),
        "f": row("f", 3),
        "n": row("n", 1),
    }
    got = {r["set_id"]: r for r in changes.compare_rows(old, new)}
    assert got["a"]["change"] == "new_version_same_texts"
    assert got["b"]["change"] == "texts_changed"
    assert got["b"]["sections_changed"] == ["medication_guide"]
    assert got["c"]["patient_texts_added"] == ["patient_package_insert"]
    assert got["d"]["change"] == "record_only" and got["d"]["block_changed"] is True
    assert "e" not in got  # unchanged labels get no row
    assert got["f"]["patient_texts_dropped"] == ["patient_package_insert"]
    assert got["g"]["change"] == "gone" and got["n"]["change"] == "new_label"
    told = {r["set_id"]: r for r in changes.compare_rows(old, new, new_export_ids={"g"})}
    assert told["g"]["change"] == "left_scope"
    told = {r["set_id"]: r for r in changes.compare_rows(old, new, new_export_ids=set())}
    assert told["g"]["change"] == "withdrawn"


def test_columns_missing_from_an_older_build_are_not_compared():
    old = {"a": {"set_id": "a", "version": 1}}
    new = {"a": row("a", 1)}
    assert changes.compare_rows(old, new) == []


def _build(tmp_path, name, parts):
    root = write_export(tmp_path / f"bulk-{name}", parts=parts)
    out = tmp_path / name
    tables.Builder(
        tables.parts_from_manifest(root, "2026-11-13"), out, "2026-11-13", log=lambda s: None
    ).run()
    return out


def test_two_builds_compared_end_to_end(tmp_path):
    guide = copy.deepcopy(PLR_WITH_GUIDE)
    insert = copy.deepcopy(OLDER_WITH_INSERT)
    old_dir = _build(tmp_path, "old", [[guide, insert]])
    guide2 = copy.deepcopy(guide)
    guide2["version"] = "8"
    guide2["spl_medguide"] = [guide["spl_medguide"][0] + " Keep it dry."]
    other = copy.deepcopy(insert)
    other.update(id="doc-0077", set_id="set-nnnn")
    new_dir = _build(tmp_path, "new", [[guide2, other]])
    out = tmp_path / "changes.parquet"
    summary = changes.write(old_dir, new_dir, out)
    rows = {r["set_id"]: r for r in pq.read_table(out).to_pylist()}
    assert rows["set-aaaa"]["change"] == "texts_changed"
    assert rows["set-aaaa"]["sections_changed"] == ["medication_guide"]
    assert (rows["set-aaaa"]["old_version"], rows["set-aaaa"]["new_version"]) == (7, 8)
    assert rows["set-bbbb"]["change"] == "withdrawn"  # not in the newer export at all
    assert rows["set-nnnn"]["change"] == "new_label"
    assert summary["changes"]["texts_changed"] == 1 and summary["unchanged"] == 0
    assert summary["distinct_patient_texts_new"] == 1  # the changed guide
    assert summary["distinct_patient_texts_gone"] == 1  # its old wording
    assert summary["export_ids_known"] is True
    assert "text" not in pq.read_schema(out).names
    (new_dir / "export_ids.parquet").unlink()
    gone = {r["set_id"]: r["change"] for r in changes.compare(old_dir, new_dir)[0].to_pylist()}
    assert gone["set-bbbb"] == "gone"  # without the newer export's ids


def test_a_build_of_two_export_dates_is_refused(tmp_path):
    t = pa.Table.from_pylist(
        [row("a", export_date="2026-11-13"), row("b", export_date="2026-11-20")]
    )
    (tmp_path / "x").mkdir()
    pq.write_table(t, tmp_path / "x" / "labels.parquet")
    with pytest.raises(ValueError, match="more than one export date"):
        changes.compare(tmp_path / "x", tmp_path / "x")


def test_changes_command(tmp_path, monkeypatch, capsys):
    import json

    from plainpairs.cli import main

    built = _build(tmp_path, "one", [[copy.deepcopy(PLR_WITH_GUIDE)]])
    out, js = tmp_path / "c.parquet", tmp_path / "c.json"
    args = ["changes", "--old", str(built), "--new", str(built), "--out", str(out)]
    assert main([*args, "--json", str(js)]) == 0
    assert "0 labels changed, 1 unchanged" in capsys.readouterr().out
    assert json.loads(js.read_text())["rows"] == 0


def test_the_build_lists_every_export_id_so_changes_can_tell_withdrawn_from_left_scope(tmp_path):
    guide = copy.deepcopy(PLR_WITH_GUIDE)
    insert = copy.deepcopy(OLDER_WITH_INSERT)
    old_dir = _build(tmp_path, "old", [[guide, insert]])
    ids = pq.read_table(old_dir / "export_ids.parquet").to_pylist()
    assert sorted(r["set_id"] for r in ids) == ["set-aaaa", "set-bbbb"]
    out_of_scope = copy.deepcopy(insert)
    out_of_scope.pop("spl_patient_package_insert")  # still exported, no longer in scope
    new_dir = _build(tmp_path, "new", [[out_of_scope]])
    table, summary = changes.compare(old_dir, new_dir)
    got = {r["set_id"]: r["change"] for r in table.to_pylist()}
    assert got == {"set-aaaa": "withdrawn", "set-bbbb": "left_scope"}
    assert summary["export_ids_known"] is True
