"""The weekly update, on invented exports only (no network)."""

import copy
import json

import pyarrow.parquet as pq

from plainpairs import tables, update
from tests.label_samples import PLR_WITH_GUIDE
from tests.test_release import write_structure
from tests.test_tables import records, write_export

H = "https://dailymed-data.nlm.nih.gov/public-release-files/"
PAGE = (
    "<html><body><ul>"
    f'<li>dm_spl_daily_update_11132026.zip [ <a href="{H}dm_spl_daily_update_11132026.zip">'
    "HTTPS</a> / FTP ] Number of labels: 377 File size: 167.70MB MD5 checksum: "
    "54d898d11f243fa10852c60e869200c5</li>"
    f'<li>dm_spl_daily_update_11142026.zip [ <a href="{H}dm_spl_daily_update_11142026.zip">'
    "HTTPS</a> / FTP ] Number of labels: 154 File size: 72.15MB MD5 checksum: "
    "61321cc4a6d6849c94783e174ac787ba</li>"
    "<li>dm_spl_weekly_update_110226_110626.zip [ HTTPS / FTP ] Number of labels: 1,590</li>"
    "</ul></body></html>"
)


def test_daily_updates_are_read_and_chosen_by_day():
    files = update.daily_updates(PAGE)
    assert [(f.day, f.labels, f.size_text) for f in files] == [
        ("2026-11-13", 377, "167.70MB"),
        ("2026-11-14", 154, "72.15MB"),
    ]
    assert [f.day for f in update.choose(files, "2026-11-13", "2026-11-20")] == ["2026-11-14"]
    assert files[1].size_bytes_upper == int(72.15 * 2**20)


def _listing(date, n_parts):
    return {
        "results": {
            "drug": {
                "label": {
                    "export_date": date,
                    "partitions": [
                        {
                            "display_name": f"Drug Label (part {i} of {n_parts})",
                            "file": f"x{i}",
                            "size_mb": 0,
                            "records": 0,
                        }
                        for i in range(1, n_parts + 1)
                    ],
                }
            }
        }
    }


class FakeSources:
    def __init__(self, root, date, n_parts):
        self.root, self.date, self.n = root, date, n_parts
        self.asked = []

    def listing(self):
        return _listing(self.date, self.n)

    def label_parts(self, listing):
        return tables.parts_from_manifest(self.root, self.date)

    def listings(self, listing):
        return None, None

    def dailymed_updates(self, after, until):
        self.asked.append((after, until))
        return []


def _previous(tmp_path):
    root = write_export(tmp_path / "bulk")
    parts = tables.parts_from_manifest(root, "2026-11-13")
    bare = tmp_path / "bare"
    tables.Builder(parts, bare, "2026-11-13", log=lambda s: None).run()
    labels = pq.read_table(bare / "labels.parquet").to_pylist()
    st = write_structure(tmp_path / "prev-structure", labels, unlisted={labels[-1]["set_id"]})
    prev = tmp_path / "prev"
    tables.Builder(parts, prev, "2026-11-13", log=lambda s: None, structure_dir=st).run()
    return root, prev, st, labels


def test_an_update_with_no_newer_export_does_nothing(tmp_path):
    root, prev, st, _labels = _previous(tmp_path)
    s = update.run(prev, st, tmp_path / "work", FakeSources(root, "2026-11-13", 2))
    assert s["status"] == "no_new_export"
    assert json.loads((tmp_path / "work" / "summary.json").read_text())["status"] == "no_new_export"


def test_an_update_to_a_newer_invented_export(tmp_path):
    root, prev, st, _labels = _previous(tmp_path)
    parts = records()
    changed = copy.deepcopy(PLR_WITH_GUIDE)
    changed["version"] = str(int(changed["version"]) + 1)
    changed["spl_medguide"] = [changed["spl_medguide"][0] + " An invented new sentence."]
    fresh = copy.deepcopy(PLR_WITH_GUIDE)
    fresh.update(id="doc-new", set_id="set-newx")
    parts[0][0] = changed
    parts[1] = [r for r in parts[1] if r["set_id"] != "set-iiii"] + [fresh]  # set-iiii withdrawn
    write_export(root, "2026-11-20", parts)
    src = FakeSources(root, "2026-11-20", 2)
    s = update.run(prev, st, tmp_path / "work", src, timer=iter(range(100)).__next__)
    assert src.asked == [("2026-11-13", "2026-11-20")]
    assert s["status"] == "ready" and s["release_check"] == "passed"
    assert s["new_export"] == "2026-11-20"
    assert s["changes"].get("new_label") == 1
    assert s["changes"].get("withdrawn") == 1
    assert s["changes"].get("texts_changed", 0) + s["changes"].get("new_version_same_texts", 0) >= 1
    assert s["moved"].get("current_to_unlisted") == 1
    assert s["structure_rows_new"] == 0 and s["structure_rows_carried"] > 0
    assert (tmp_path / "work" / "changes.parquet").exists()
    assert (tmp_path / "work" / "tables" / "codes.parquet").exists()
    text = json.dumps(s)
    assert "invented new sentence" not in text  # counts only


def test_previous_from_a_pack(tmp_path):
    from plainpairs import codes, pack

    _root, prev, _st, _labels = _previous(tmp_path)
    codes.build(prev, log=lambda s: None)
    p = tmp_path / "pack"
    pack.build_pack(prev, p, "0.1.0", today=lambda: "2026-11-15")
    tdir, sdir = update.previous_from_pack(p, tmp_path / "from-pack")
    t = pq.read_table(tdir / "labels.parquet")
    assert t.num_rows == pq.read_table(prev / "labels.parquet").num_rows
    rows = pq.read_table(sdir / "structure.parquet").to_pylist()
    assert rows and all(r["structured"]["xml_match"] == "exact" for r in rows)
    assert json.loads((tdir / "build_summary.json").read_text())["export_date"] == "2026-11-13"
