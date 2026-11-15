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
