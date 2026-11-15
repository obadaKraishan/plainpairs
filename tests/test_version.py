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


def test_build_passes_the_workers_on(tmp_path, monkeypatch):
    from plainpairs import cli, tables

    seen = {}
    real = tables.Builder

    class Spy(real):
        def __init__(self, *a, **kw):
            seen.setdefault("workers", kw.get("workers"))
            super().__init__(*a, **kw)

    from tests.test_tables import write_export

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "BULK_ROOT", write_export(tmp_path / "bulk"))
    monkeypatch.setattr(cli.tables, "Builder", Spy)
    assert main(["build", "--export-date", "2026-11-13", "--out", "t", "--workers", "1"]) == 0
    assert seen["workers"] == 1


def _built(tmp_path, monkeypatch):
    from plainpairs import cli, tables
    from tests.test_tables import write_export

    monkeypatch.chdir(tmp_path)
    root = write_export(tmp_path / "bulk")
    monkeypatch.setattr(cli, "BULK_ROOT", root)
    tables.Builder(
        tables.parts_from_manifest(root, "2026-11-13"),
        tmp_path / "t",
        "2026-11-13",
        log=lambda s: None,
    ).run()
    return root


def test_release_check_command_passes_and_fails_loudly(tmp_path, monkeypatch, capsys):
    _built(tmp_path, monkeypatch)
    assert main(["release-check", "--tables", "t", "--switch", "unmarked"]) == 0
    assert "Release check passed" in capsys.readouterr().out
    assert main(["release-check", "--tables", "t", "--switch", "all"]) == 1
    assert "RELEASE CHECK FAILED" in capsys.readouterr().out


def test_text_command_rebuilds_and_confirms(tmp_path, monkeypatch, capsys):
    import pyarrow as pa
    import pyarrow.parquet as pq

    _built(tmp_path, monkeypatch)
    assert main(["text", "--labels", "t/labels.parquet", "--out", "r"]) == 0
    assert "every row matches its hash" in capsys.readouterr().out
    t = pq.read_table(tmp_path / "t" / "labels.parquet")
    i = t.schema.get_field_index("t_medication_guide_sha256")
    pq.write_table(
        t.set_column(i, "t_medication_guide_sha256", pa.array(["0" * 64] * t.num_rows)),
        tmp_path / "t" / "labels.parquet",
    )
    assert main(["text", "--labels", "t/labels.parquet", "--out", "r2"]) == 1


def test_stats_command(tmp_path, monkeypatch, capsys):
    _built(tmp_path, monkeypatch)
    assert main(["stats", "--tables", "t", "--out", "s/stats.json"]) == 0
    assert "4 labels" in capsys.readouterr().out


def test_dailymed_test_command_reads_robots_then_labels(tmp_path, monkeypatch, capsys):
    from plainpairs import cli
    from tests.test_client import FakeResponse
    from tests.test_client import make as make_fake
    from tests.test_dailymed import SPL

    _built(tmp_path, monkeypatch)
    (tmp_path / "data" / "raw").mkdir(parents=True)
    answers = [FakeResponse(body=b"User-agent: *\nDisallow: /search\n")] + [
        FakeResponse(body=SPL) for _ in range(4)
    ]
    fake, session, _ = make_fake(tmp_path, answers)
    monkeypatch.setattr(cli, "make_client", lambda since, calls, nbytes: fake)
    assert main(["dailymed-test", "--tables", "t", "--per-stratum", "1", "--out", "d/c.json"]) == 0
    out = capsys.readouterr().out
    assert "robots.txt: HTTP 200" in out
    assert "labels compared" in out
    assert session.calls[0]["url"].endswith("/robots.txt")
    fake2, session2, _ = make_fake(tmp_path, [FakeResponse(body=b"User-agent: *\n")])
    monkeypatch.setattr(cli, "make_client", lambda since, calls, nbytes: fake2)
    assert main(["dailymed-test", "--tables", "t", "--robots-only"]) == 0
    assert len(session2.calls) == 1


def test_build_with_listed_reads_the_newest_listing_files(tmp_path, monkeypatch, capsys):
    from plainpairs import cli
    from tests.test_listed import HEADER, NDC_RECORDS, dailymed_zip, ndc_zip
    from tests.test_tables import write_export

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "BULK_ROOT", write_export(tmp_path / "bulk"))
    monkeypatch.setattr(cli, "LISTED_ROOT", tmp_path / "listed")
    with pytest.raises(SystemExit, match="listed-download"):
        main(["build", "--export-date", "2026-11-13", "--out", "t", "--listed"])
    ndc_zip(tmp_path / "listed" / "ndc" / "2026-11-13" / "n.json.zip", NDC_RECORDS)
    dailymed_zip(tmp_path / "listed" / "dailymed" / "2026-11-15" / "d.zip", [HEADER])
    assert main(["build", "--export-date", "2026-11-13", "--out", "t", "--listed"]) == 0
    assert "listing ndc: n.json.zip of 2026-11-13" in capsys.readouterr().out


def test_listed_download_reuses_the_listing_saved_today(tmp_path, monkeypatch, capsys):
    import json

    from plainpairs import cli, pages
    from tests.test_client import FakeResponse
    from tests.test_client import make as make_fake
    from tests.test_listed import DOWNLOAD

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "raw").mkdir(parents=True)
    monkeypatch.setattr(cli, "PAGES_ROOT", tmp_path / "data" / "raw" / "pages")
    monkeypatch.setattr(cli, "LISTED_ROOT", tmp_path / "data" / "raw" / "listed")
    answers = [
        FakeResponse(body=json.dumps(DOWNLOAD).encode()),
        FakeResponse(body=b"PK-ndc"),
        FakeResponse(body=b"PK-dm"),
    ]
    fake, session, _ = make_fake(tmp_path, answers)
    monkeypatch.setattr(cli, "make_client", lambda since, calls, nbytes: fake)
    assert main(["listed-download"]) == 0
    out = capsys.readouterr().out
    assert "export 2026-11-13, 1.5 MiB listed" in out and "DailyMed zip file metadata" in out
    assert len(session.calls) == 3
    assert pages.latest_pages(cli.PAGES_ROOT)
