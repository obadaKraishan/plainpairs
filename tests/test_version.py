import re

import pytest

from plainpairs import __version__
from plainpairs.cli import main


def test_version_is_a_development_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.dev\d+)?", __version__)


def test_cli_prints_its_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_cli_without_a_command_prints_help(capsys):
    assert main([]) == 0
    assert "usage: plainpairs" in capsys.readouterr().out


def test_page_text_without_a_saved_page_says_how_to_fix_it(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["page-text", "https://x.gov/"]) == 1
    assert "fetch-page" in capsys.readouterr().out


def test_quotes_check_reports_missing_quotes(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "quotes.csv").write_text("url,quote\nhttps://x.gov/,hello\n")
    assert main(["quotes-check"]) == 1
    assert "0 of 1 quotes" in capsys.readouterr().out


def test_counts_runs_the_plan_through_the_client(tmp_path, monkeypatch, capsys):
    import json

    from plainpairs import cli
    from tests.test_client import FakeResponse
    from tests.test_client import make as make_fake

    monkeypatch.chdir(tmp_path)
    total = {"meta": {"results": {"total": 5}}}
    fake, session, _ = make_fake(tmp_path, [FakeResponse(body=json.dumps(total).encode())] * 3)
    monkeypatch.setattr(cli, "make_client", lambda since, calls, nbytes: fake)
    assert main(["counts", "--first", "3", "--out", "c.json"]) == 0
    assert len(session.calls) == 3
    assert "3 answers saved" in capsys.readouterr().out


def test_download_part_needs_the_saved_listing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "raw").mkdir(parents=True)
    assert main(["download-part"]) == 1
    assert "download.json" in capsys.readouterr().out


def test_commands_that_write_raw_data_need_the_drive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "raw").symlink_to(tmp_path / "gone" / "plainpairs")
    with pytest.raises(SystemExit, match="Mount the external data drive"):
        main(["download-part"])


def test_profile_writes_aggregates(tmp_path, monkeypatch, capsys):
    import json
    import zipfile

    from tests.label_samples import OLDER_WITH_INSERT, PLR_WITH_GUIDE

    monkeypatch.chdir(tmp_path)
    z = tmp_path / "p.json.zip"
    with zipfile.ZipFile(z, "w") as zf:
        body = {
            "meta": {"last_updated": "2026-11-13"},
            "results": [PLR_WITH_GUIDE, OLDER_WITH_INSERT],
        }
        zf.writestr("drug-label-0001-of-0001.json", json.dumps(body))
    assert main(["profile", str(z), "--out", "out/p.json"]) == 0
    saved = json.loads((tmp_path / "out" / "p.json").read_text())
    assert saved["labels"] == 2 and saved["source_meta"] == {"last_updated": "2026-11-13"}
    assert "2 paired" in capsys.readouterr().out


def test_download_all_checks_the_listing_before_and_after(tmp_path, monkeypatch, capsys):
    import json

    from plainpairs import cli
    from tests.test_bulk import listing, part_zip_bytes
    from tests.test_client import FakeResponse
    from tests.test_client import make as make_fake

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "raw").mkdir(parents=True)
    first = json.dumps(listing([2], 2)).encode()
    moved = json.dumps(listing([2], 2, date="2026-11-20")).encode()
    answers = [
        FakeResponse(body=first),
        FakeResponse(body=part_zip_bytes(2, 0, 2)),
        FakeResponse(body=moved),
    ]
    fake, _session, _ = make_fake(tmp_path, answers)
    monkeypatch.setattr(cli, "make_client", lambda since, calls, nbytes: fake)
    assert main(["download-all"]) == 2
    out = capsys.readouterr().out
    assert "export 2026-11-13, 1 parts" in out
    assert "changed during the run" in out
    answers2 = [FakeResponse(body=first), FakeResponse(body=first)]
    fake2, _, _ = make_fake(tmp_path, answers2)
    monkeypatch.setattr(cli, "make_client", lambda since, calls, nbytes: fake2)
    assert main(["download-all"]) == 0
    assert "share one export date" in capsys.readouterr().out


def test_build_runs_from_the_manifest(tmp_path, monkeypatch, capsys):
    from plainpairs import cli
    from tests.test_tables import write_export

    monkeypatch.chdir(tmp_path)
    root = write_export(tmp_path / "bulk")
    monkeypatch.setattr(cli, "BULK_ROOT", root)
    assert main(["build", "--export-date", "2026-11-13", "--out", "t"]) == 0
    out = capsys.readouterr().out
    assert "2 parts of 2026-11-13 match their manifest" in out
    assert (tmp_path / "t" / "build_summary.json").exists()


def test_sheet_and_sheet_check_from_built_tables(tmp_path, monkeypatch, capsys):
    import json

    from plainpairs import cli, tables
    from tests.test_tables import write_export

    monkeypatch.chdir(tmp_path)
    root = write_export(tmp_path / "bulk")
    tables.Builder(
        tables.parts_from_manifest(root, "2026-11-13"),
        tmp_path / "t",
        "2026-11-13",
        log=lambda s: None,
    ).run()
    assert main(["sheet", "--tables", "t", "--out", "s", "--per-key", "1", "--seed", "3"]) == 0
    assert "rows to" in capsys.readouterr().out
    x, k = tmp_path / "s" / "hand-sheet-seed3.xlsx", tmp_path / "s" / "hand-sheet-seed3-key.csv"
    assert main(["sheet-check", str(x), "--key", str(k), "--json", "c.json"]) == 0
    assert "not answered" in capsys.readouterr().out
    assert json.loads((tmp_path / "c.json").read_text())
    assert cli is not None
