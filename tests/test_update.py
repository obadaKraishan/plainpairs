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


def _item(name, n, size, md5):
    return (
        f'<li>{name} [ <a href="{H}{name}">HTTPS</a> / FTP ] Number of labels: {n} '
        f"File size: {size} MD5 checksum: {md5}</li>"
    )


#: The page as it looked on 2026-11-26 (invented checksums): three weekly files, then the
#: current week day by day.
PAGE_WEEKS = (
    "<html><body><ul>"
    + _item("dm_spl_weekly_update_111626_112026.zip", "1,263", "466.69MB", "a" * 32)
    + _item("dm_spl_weekly_update_110926_111326.zip", "1,201", "491.41MB", "b" * 32)
    + _item("dm_spl_weekly_update_110226_110626.zip", "1,590", "679.93MB", "c" * 32)
    + _item("dm_spl_daily_update_11252026.zip", "187", "78.18MB", "d" * 32)
    + _item("dm_spl_daily_update_11242026.zip", "0", "25.18MB", "e" * 32)
    + _item("dm_spl_daily_update_11232026.zip", "955", "432.28MB", "f" * 32)
    + "<li>dm_spl_weekly_update_103026_110326.zip [ HTTPS / FTP ] Number of labels: 9</li>"
    + "</ul></body></html>"
)


def test_daily_updates_are_read_and_chosen_by_day():
    files = update.daily_updates(PAGE)
    assert [(f.day, f.labels, f.size_text) for f in files] == [
        ("2026-11-13", 377, "167.70MB"),
        ("2026-11-14", 154, "72.15MB"),
    ]
    assert [f.day for f in update.choose(files, "2026-11-13", "2026-11-20")] == ["2026-11-14"]
    assert files[1].size_bytes_upper == int(72.15 * 2**20)
    assert files[0].kind == "daily" and files[0].days == ["2026-11-13"]


def test_weekly_files_are_read_and_fill_the_weeks_no_longer_listed_by_day():
    files = update.daily_updates(PAGE_WEEKS)
    weekly = [f for f in files if f.kind == "weekly"]
    assert [(f.first_day, f.day, f.labels) for f in weekly] == [
        ("2026-11-02", "2026-11-06", 1590),
        ("2026-11-09", "2026-11-13", 1201),
        ("2026-11-16", "2026-11-20", 1263),
    ]  # the unlinked one is left out
    chosen = update.choose(files, "2026-11-13", "2026-11-26")
    assert [f.name for f in chosen] == [
        "dm_spl_weekly_update_111626_112026.zip",
        "dm_spl_daily_update_11232026.zip",
        "dm_spl_daily_update_11242026.zip",
        "dm_spl_daily_update_11252026.zip",
    ]
    c = update.coverage(files, chosen, "2026-11-13", "2026-11-26")
    assert c["weekdays"] == 9 and c["weekdays_covered"] == 8
    assert c["weekdays_missing"] == [] and c["weekdays_without_file"] == ["2026-11-26"]


def test_a_week_listed_day_by_day_is_never_read_twice():
    files = update.daily_updates(PAGE_WEEKS)
    week = update.UpdateFile("w", "u", "2026-11-27", 1, "1MB", "0" * 32, "2026-11-23", "weekly")
    chosen = update.choose([*files, week], "2026-11-20", "2026-11-27")
    assert [f.kind for f in chosen] == ["daily", "daily", "daily"]


def test_a_week_no_longer_listed_stops_the_update():
    files = update.daily_updates(PAGE_WEEKS)
    chosen = update.choose(files, "2026-10-28", "2026-11-26")
    c = update.coverage(files, chosen, "2026-10-28", "2026-11-26")
    assert c["weekdays_missing"] == ["2026-10-29", "2026-10-30"]
    assert update.coverage([], [], "2026-11-13", "2026-11-16")["weekdays_missing"] == ["2026-11-16"]


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
        # one daily file for each weekday of the span (none downloaded): the days are covered
        self.files = [
            update.UpdateFile(f"d{i}", "u", f"2026-11-{i:02d}", 0, "1MB", "0" * 32)
            for i in range(14, 28)
        ]

    def listing(self):
        return _listing(self.date, self.n)

    def label_parts(self, listing):
        return tables.parts_from_manifest(self.root, self.date)

    def listings(self, listing):
        return None, None

    def dailymed_choice(self, after, until):
        self.asked.append((after, until))
        return update.UpdateChoice([], update.coverage(self.files, [], after, until))

    def dailymed_download(self, choice):
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
    assert s["dailymed_coverage"]["weekdays_missing"] == []
    assert (tmp_path / "work" / "changes.parquet").exists()
    assert (tmp_path / "work" / "tables" / "codes.parquet").exists()
    text = json.dumps(s)
    assert "invented new sentence" not in text  # counts only


def test_an_update_stops_before_any_download_when_a_week_is_missing(tmp_path):
    root, prev, st, _labels = _previous(tmp_path)
    write_export(root, "2026-11-20", records())
    src = FakeSources(root, "2026-11-20", 2)
    src.files = []
    src.label_parts = None  # would fail if called
    s = update.run(prev, st, tmp_path / "work", src)
    assert s["status"] == "stopped" and s["stopped_because"] == "dailymed_update_files_missing"
    assert s["dailymed_coverage"]["weekdays_missing"] == [
        "2026-11-16",
        "2026-11-17",
        "2026-11-18",
        "2026-11-19",
        "2026-11-20",
    ]


class FilesSources(FakeSources):
    """DailyMed lists a weekly file and two daily ones; none is downloaded (no zip to read)."""

    def dailymed_choice(self, after, until):
        listed = [
            update.UpdateFile("w", "u", "2026-11-20", 0, "1MB", "0" * 32, "2026-11-16", "weekly"),
            update.UpdateFile("d1", "u", "2026-11-23", 0, "1MB", "0" * 32),
            update.UpdateFile("d2", "u", "2026-11-24", 0, "1MB", "0" * 32),
        ]
        chosen = update.choose(listed, after, until)
        return update.UpdateChoice(chosen, update.coverage(listed, chosen, after, until))


def test_the_update_records_the_full_release_and_the_last_day_read(tmp_path):
    root, prev, st, _labels = _previous(tmp_path)
    write_export(root, "2026-11-26", records())
    s = update.run(prev, st, tmp_path / "work", FilesSources(root, "2026-11-26", 2))
    assert s["status"] == "ready"
    assert s["dailymed_full_release"] == "2026-11-13"
    assert s["dailymed_updates_through"] == "2026-11-24"  # not the export day: no file for it
    built = json.loads((tmp_path / "work" / "tables" / "build_summary.json").read_text())
    assert built["structure"]["release_date"] == "2026-11-24"
    assert built["dailymed"] == {
        "full_release": "2026-11-13",
        "updates_through": "2026-11-24",
        "update_files": ["w", "d1", "d2"],
    }


def test_the_card_names_the_full_release_and_the_update_files():
    from plainpairs import pack

    src = {
        "dailymed_release": "2026-11-24",
        "dailymed_full_release": "2026-11-13",
        "dailymed_updates_through": "2026-11-24",
    }
    assert pack.dailymed_words(src) == "2026-11-13, with its update files through 2026-11-24"
    assert pack.dailymed_words({"dailymed_release": "2026-11-13"}) == "2026-11-13"


def test_previous_from_a_pack(tmp_path):
    from plainpairs import codes, pack

    _root, prev, _st, _labels = _previous(tmp_path)
    from tests.test_release import _nci_tables

    _nci_tables(prev, tmp_path)
    codes.build(prev, log=lambda s: None)
    p = tmp_path / "pack"
    pack.build_pack(prev, p, "0.1.0", today=lambda: "2026-11-15")
    tdir, sdir = update.previous_from_pack(p, tmp_path / "from-pack")
    t = pq.read_table(tdir / "labels.parquet")
    assert t.num_rows == pq.read_table(prev / "labels.parquet").num_rows
    rows = pq.read_table(sdir / "structure.parquet").to_pylist()
    assert rows and all(r["structured"]["xml_match"] == "exact" for r in rows)
    assert json.loads((tdir / "build_summary.json").read_text())["export_date"] == "2026-11-13"
    assert (tdir / "nci_text.parquet").exists() and (tdir / "nci_summaries.parquet").exists()


def test_the_weekly_workflow_is_switched_off_and_pinned():
    import re
    from pathlib import Path

    wf = Path(".github/workflows/weekly-update.yml").read_text(encoding="utf-8")
    active = "\n".join(line for line in wf.splitlines() if not line.lstrip().startswith("#"))
    assert "schedule:" not in active and 'DELIVERY_ENABLED: "false"' in active
    assert "permissions: {}" in active and "if: false" in active
    for uses in re.findall(r"uses: (\S+)", active):
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", uses), uses
