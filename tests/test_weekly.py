"""The weekly run's own steps: the next version, the report (counts only) and the signed-out check
of the pull request, against a fake Hub client and the invented pack of ``tests.test_pack``."""

import json
from types import SimpleNamespace

import pytest

from plainpairs import weekly
from tests.test_pack import made  # noqa: F401  (the fixture)
from tests.test_release import built  # noqa: F401  (the fixture made needs)

SUMMARY = {
    "status": "ready",
    "previous_export": "2026-11-26",
    "listed_export": "2026-11-27",
    "new_export": "2026-11-27",
    "dailymed_full_release": "2026-11-13",
    "dailymed_updates_through": "2026-11-27",
    "dailymed_coverage": {
        "after": "2026-11-25",
        "until": "2026-11-27",
        "weekdays": 2,
        "weekdays_covered": 1,
        "weekdays_missing": [],
        "weekdays_without_file": ["2026-11-26"],
        "files": [{"name": "d", "kind": "daily", "labels": 5}],
    },
    "changes": {"new_label": 3, "withdrawn": 0, "left_scope": 1, "texts_changed": 2},
    "moved": {"unlisted_to_current": 1},
    "configurations": {"current": 10, "unlisted": 5},
    "structure_rows_carried": 100,
    "structure_rows_new": 4,
    "nci_sha256_carried": {"nci_text": "a" * 64},
    "release_check": "passed",
    "release_check_problems": 0,
    "seconds": 61.2,
    # a field the report never reads: nothing outside the named fields reaches it
    "notes": "An invented sentence that must never reach the report.",
}


def test_the_next_version_raises_the_last_number():
    assert weekly.next_version("0.2.0") == "0.2.1"
    assert weekly.next_version("0.2.9") == "0.2.10"
    with pytest.raises(ValueError, match="three numbers"):
        weekly.next_version("0.2")


def test_the_report_holds_counts_only():
    text = weekly.report(SUMMARY, version="0.2.1", previous="0.2.0", delivery=True)
    assert text.startswith("## PlainPairs weekly update: ready")
    assert "version: 0.2.1 (after 0.2.0)" in text and "delivery: on" in text
    assert "3 new labels" in text and "unlisted to current 1" in text
    assert "without a file 2026-11-26" in text and "missing none" in text
    assert "invented sentence" not in text
    stopped = weekly.report(None, stopped_because="1 open pull request on the dataset")
    assert "stopped before building: 1 open pull request" in stopped
    nothing = weekly.report(
        {"status": "no_new_export", "listed_export": "2026-11-27", "previous_export": "2026-11-27"}
    )
    assert "nothing new" in nothing and "delivery: off" in nothing


def test_the_usage_log_is_counted_since_the_run_started(tmp_path):
    log = tmp_path / "usage_log.csv"
    log.write_text(
        "time,method,host,path,query,status,bytes,seconds\n"
        "2026-11-27T01:00:00.000Z,GET,api.fda.gov,/download.json,,200,10,0.1\n"
        "2026-11-30T07:30:00.000Z,GET,api.fda.gov,/download.json,,200,20,0.1\n"
        "2026-11-30T07:31:00.000Z,GET,dailymed.nlm.nih.gov,/x,,200,5,0.1\n",
        encoding="utf-8",
    )
    u = weekly.usage(log, "2026-11-30T07:23:00Z")
    assert u == {
        "calls": 2,
        "bytes": 25,
        "hosts": {"api.fda.gov": 1, "dailymed.nlm.nih.gov": 1},
        "statuses": {"200": 2},
    }
    assert "2 calls, 25 bytes" in weekly.report(SUMMARY, calls=u)
    assert weekly.usage(tmp_path / "none.csv", "2026-11-30")["calls"] == 0


class FakeApi:
    """The Hub as the check sees it: open pull requests and one revision's files."""

    def __init__(self, siblings, title="PlainPairs 0.1.0", num=2):
        self.siblings, self.title, self.num = siblings, title, num

    def get_repo_discussions(self, repo, **kw):
        assert kw["discussion_type"] == "pull_request" and kw["discussion_status"] == "open"
        return [
            SimpleNamespace(num=1, title="something else", status="open"),
            SimpleNamespace(num=self.num, title=self.title, status="draft"),
        ]

    def dataset_info(self, repo, revision=None, files_metadata=False):
        assert revision == f"refs/pr/{self.num}" and files_metadata
        return SimpleNamespace(sha="0123456789abcdef", siblings=self.siblings)


def hub_copy(p):
    """The Hub's view of a pack: big files in LFS, small text files outside it."""
    m, entries = weekly.pack_entries(p)
    out = []
    for e in entries:
        if e["path"].endswith((".csv", ".md", ".json")) and e["blob"]:
            out.append(
                SimpleNamespace(rfilename=e["path"], lfs=None, size=e["bytes"], blob_id=e["blob"])
            )
        else:
            out.append(
                SimpleNamespace(
                    rfilename=e["path"],
                    lfs=SimpleNamespace(sha256=e["sha256"]),
                    size=e["bytes"],
                    blob_id="x",
                )
            )
    for name in weekly.DOCS:
        out.append(
            SimpleNamespace(
                rfilename=name, lfs=None, size=1, blob_id=weekly.git_blob((p / name).read_bytes())
            )
        )
    out.append(SimpleNamespace(rfilename=".gitattributes", lfs=None, size=1, blob_id="g"))
    return m, out


def test_the_pull_request_check_passes_on_the_pack_and_fails_on_a_change(made):  # noqa: F811
    _out, p, _m = made
    _m, siblings = hub_copy(p)
    seen = []
    assert weekly.pr_check(p, "0.1.0", api=FakeApi(siblings), out=seen.append) == []
    assert "pull request #2 (draft)" in seen[0] and "extra none" in seen[0]
    changed = [
        SimpleNamespace(**{**vars(s), "size": s.size + 1})
        if s.rfilename.endswith(".parquet")
        else s
        for s in siblings
    ]
    assert any(
        "differs" in x for x in weekly.pr_check(p, "0.1.0", api=FakeApi(changed), out=seen.append)
    )
    extra = [*siblings, SimpleNamespace(rfilename="stray.txt", lfs=None, size=1, blob_id="s")]
    assert any(
        "stray.txt" in x for x in weekly.pr_check(p, "0.1.0", api=FakeApi(extra), out=seen.append)
    )
    assert weekly.pr_check(
        p, "0.1.0", api=FakeApi(siblings, title="PlainPairs 9.9.9"), out=seen.append
    ) == ["no open pull request titled 'PlainPairs 0.1.0' on obadakr/plainpairs"]
    assert any(
        "not 0.1.1" in x
        for x in weekly.pr_check(
            p, "0.1.1", api=FakeApi(siblings, title="PlainPairs 0.1.1"), out=seen.append
        )
    )


def test_the_command_line(made, tmp_path, capsys):  # noqa: F811
    _out, p, _m = made
    assert weekly.main(["next-version", "--manifest", str(p / "manifest.json")]) == 0
    assert capsys.readouterr().out.strip() == "0.1.1"
    s = tmp_path / "summary.json"
    s.write_text(json.dumps(SUMMARY), encoding="utf-8")
    assert (
        weekly.main(
            [
                "report",
                "--summary",
                str(s),
                "--manifest",
                str(p / "manifest.json"),
                "--version",
                "0.1.1",
                "--delivery",
                "on",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "the pack: 16 Parquet files" in out and "invented sentence" not in out
    assert (
        weekly.main(
            [
                "report",
                "--summary",
                str(tmp_path / "absent.json"),
                "--stopped-because",
                "an open pull request",
            ]
        )
        == 0
    )
    assert "stopped" in capsys.readouterr().out


def test_the_check_refuses_when_a_token_is_visible(monkeypatch):
    hub = pytest.importorskip("huggingface_hub")
    monkeypatch.setattr(hub, "get_token", lambda: "a-token")
    with pytest.raises(PermissionError, match="not signed out"):
        weekly.signed_out_api()
