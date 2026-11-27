"""The weekly run's own steps on GitHub Actions (`.github/workflows/weekly-update.yml`): the
next version's number, the run's report, and the signed-out check of the pull request the run
opened on the dataset.

**The report** holds counts, dates, names and hashes only. It is the job summary, the stop
issue's body and the pull request's description, so it is built from named fields of the
update's ``summary.json``, the pack's ``manifest.json`` and the usage log, never from a table.

**The check** asks the Hub with no token at all (it refuses to run when one is visible) for the
open pull request titled "PlainPairs VERSION" and compares the files of ``refs/pr/N`` with the
pack the run built: a data or easy-access file by its LFS SHA-256 and size (or by its git blob
id when the Hub keeps it outside LFS), README.md, LICENSES.md and manifest.json by git blob id,
and no file the pack does not have (``.gitattributes`` aside). huggingface_hub is not a
dependency of the package: the check imports it only when it runs, and tests pass a fake client.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

DATASET = "obadakr/plainpairs"
DOCS = ("README.md", "LICENSES.md", "manifest.json")
HUB_FILES = frozenset({".gitattributes"})
#: Files at least this large are compared by their LFS hash only (their bytes are not read).
BLOB_MAX = 50_000_000


def next_version(version: str) -> str:
    """The weekly version after ``version``: the last number raised (0.2.0 -> 0.2.1)."""
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"{version!r} is not a version of three numbers, such as 0.2.0.")
    return ".".join([parts[0], parts[1], str(int(parts[2]) + 1)])


# --- the report (counts only) ------------------------------------------------------------------


def usage(log_path: Path, since: str) -> dict[str, Any]:
    """Calls and bytes per host in the usage log since ``since`` (an ISO time in UTC)."""
    calls: Counter[str] = Counter()
    nbytes: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    if not Path(log_path).exists():
        return {"calls": 0, "bytes": 0, "hosts": {}, "statuses": {}}
    with Path(log_path).open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["time"] < since.rstrip("Z"):
                continue
            calls[r["host"]] += 1
            nbytes[r["host"]] += int(r["bytes"] or 0)
            statuses[r["status"]] += 1
    return {
        "calls": sum(calls.values()),
        "bytes": sum(nbytes.values()),
        "hosts": dict(calls),
        "statuses": dict(statuses),
    }


def report(
    summary: dict[str, Any] | None,
    manifest: dict[str, Any] | None = None,
    version: str | None = None,
    delivery: bool = False,
    calls: dict[str, Any] | None = None,
    stopped_because: str | None = None,
    previous: str | None = None,
) -> str:
    """The run's report in Markdown, from named fields only."""
    s = summary or {}
    status = "stopped" if stopped_because else s.get("status", "failed")
    lines = [f"## PlainPairs weekly update: {status}", ""]
    if version:
        lines.append(f"- version: {version}" + (f" (after {previous})" if previous else ""))
    lines.append(
        "- delivery: "
        + ("on (a draft pull request on the dataset)" if delivery else "off (nothing is uploaded)")
    )
    if stopped_because:
        lines.append(f"- stopped before building: {stopped_because}")
    if s:
        lines.append(
            f"- openFDA drug label export: {s.get('listed_export')} (the last version's: "
            f"{s.get('previous_export')})"
        )
    if s.get("stopped_because"):
        lines.append(f"- the update stopped: {s['stopped_because'].replace('_', ' ')}")
    if s.get("status") == "no_new_export":
        lines.append("- nothing new: no export newer than the last version's is listed")
    cov = s.get("dailymed_coverage")
    if cov:
        kinds = Counter(f.get("kind") for f in cov.get("files", []))
        lines.append(
            f"- DailyMed: full release {s.get('dailymed_full_release')}, read through "
            f"{s.get('dailymed_updates_through')}; files: {kinds.get('weekly', 0)} weekly, "
            f"{kinds.get('daily', 0)} daily; weekdays {cov.get('after')} to {cov.get('until')}: "
            f"{cov.get('weekdays', 0)}, covered {cov.get('weekdays_covered', 0)}, missing "
            f"{', '.join(cov.get('weekdays_missing') or []) or 'none'}, without a file "
            f"{', '.join(cov.get('weekdays_without_file') or []) or 'none'}"
        )
    ch = s.get("changes")
    if ch is not None:
        lines.append(
            f"- against the last version: {ch.get('new_label', 0):,} new labels, "
            f"{ch.get('withdrawn', 0):,} withdrawn, {ch.get('left_scope', 0):,} left scope, "
            f"{ch.get('texts_changed', 0):,} with changed texts, "
            f"{ch.get('new_version_same_texts', 0):,} new versions with the same texts, "
            f"{ch.get('record_only', 0):,} with record fields changed only"
        )
    moved = s.get("moved")
    if moved is not None:
        lines.append(
            "- moved between configurations: "
            + (
                ", ".join(f"{k.replace('_', ' ')} {v:,}" for k, v in sorted(moved.items()))
                or "none"
            )
        )
    conf = s.get("configurations")
    if conf:
        lines.append(
            f"- configurations: current {conf.get('current', 0):,} labels, unlisted "
            f"{conf.get('unlisted', 0):,}"
        )
    if "structure_rows_new" in s:
        lines.append(
            f"- structure rows: {s.get('structure_rows_carried', 0):,} carried, "
            f"{s.get('structure_rows_new', 0):,} read from the update files"
        )
    nci = s.get("nci_sha256_carried")
    if nci:
        lines.append(
            "- NCI tables carried over: "
            + ", ".join(f"{k} {v[:12]}" for k, v in sorted(nci.items()))
        )
    if "release_check" in s:
        lines.append(
            f"- release check of the build: {s['release_check']} "
            f"({s.get('release_check_problems', 0)} problems)"
        )
    if manifest:
        layer = manifest.get("access_files") or []
        held = manifest.get("held_back", {}).get("label_text_rows_marked", 0)
        lines.append(
            f"- the pack: {len(manifest.get('files', []))} Parquet files, "
            f"{manifest.get('rows', 0):,} rows, {manifest.get('bytes', 0) / 1e6:,.1f} MB; "
            f"{len(layer)} easy-access files, {sum(f['bytes'] for f in layer) / 1e6:,.1f} MB; "
            f"text rows held back {held:,}"
        )
    if calls is not None:
        hosts = ", ".join(f"{h} {n}" for h, n in sorted(calls.get("hosts", {}).items()))
        lines.append(
            f"- requests: {calls.get('calls', 0)} calls, {calls.get('bytes', 0):,} bytes"
            + (f" ({hosts})" if hosts else "")
            + "; answers "
            + (
                ", ".join(f"{k} {v}" for k, v in sorted(calls.get("statuses", {}).items()))
                or "none"
            )
        )
    if "seconds" in s:
        lines.append(f"- the update took {s['seconds']:,.0f} seconds")
    lines += ["", "Counts only; no label or summary text."]
    return "\n".join(lines) + "\n"


# --- the signed-out check of the pull request ----------------------------------------------------


def git_blob(data: bytes) -> str:
    """A file's git blob id (how the Hub names a file it keeps outside LFS)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def pack_entries(pack: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The pack's manifest and its data and easy-access files (path, SHA-256, size, and the git
    blob id of each small file present on disk)."""
    pack = Path(pack)
    m = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    out = []
    for f in [*m.get("files", []), *(m.get("access_files") or [])]:
        local = pack / f["path"]
        blob = git_blob(local.read_bytes()) if f["bytes"] < BLOB_MAX and local.is_file() else None
        out.append({"path": f["path"], "sha256": f["sha256"], "bytes": f["bytes"], "blob": blob})
    return m, out


def same(sibling: Any, entry: dict[str, Any]) -> bool:
    """The Hub's file is the pack's: by LFS SHA-256 and size, or by git blob id outside LFS."""
    if sibling is None:
        return False
    lfs = getattr(sibling, "lfs", None)
    if lfs is not None:
        return lfs.sha256 == entry["sha256"] and sibling.size == entry["bytes"]
    return entry["blob"] is not None and sibling.blob_id == entry["blob"]


def compare(
    siblings: Sequence[Any], pack: Path, docs: Sequence[str] = DOCS
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], list[str]]:
    """The manifest, the pack's entries, the paths that differ and the Hub's extra files."""
    m, entries = pack_entries(pack)
    remote = {s.rfilename: s for s in siblings}
    bad = [e["path"] for e in entries if not same(remote.get(e["path"]), e)]
    for name in docs:
        local = Path(pack) / name
        s = remote.get(name)
        if s is None or not local.is_file() or s.blob_id != git_blob(local.read_bytes()):
            bad.append(name)
    known = {e["path"] for e in entries} | set(DOCS) | HUB_FILES
    extra = sorted(set(remote) - known)
    return m, entries, bad, extra


def find_pr(api: Any, dataset: str, title: str) -> Any:
    """The newest open pull request on the dataset with this title (a draft counts as open)."""
    prs = [
        d
        for d in api.get_repo_discussions(
            dataset, repo_type="dataset", discussion_type="pull_request", discussion_status="open"
        )
        if d.title == title
    ]
    if not prs:
        raise LookupError(f"no open pull request titled {title!r} on {dataset}")
    return max(prs, key=lambda d: d.num)


def signed_out_api() -> Any:
    """huggingface_hub's client with no token; refuses when a token is visible anyway."""
    from huggingface_hub import HfApi, get_token

    if get_token() is not None:
        raise PermissionError("a token is visible, so this is not signed out")
    return HfApi(token=False)


def pr_check(
    pack: Path, version: str, dataset: str = DATASET, api: Any = None, out: Any = print
) -> list[str]:
    """Every problem of the open pull request "PlainPairs VERSION" against the pack; empty when
    it holds the pack's files exactly."""
    api = api if api is not None else signed_out_api()
    title = f"PlainPairs {version}"
    try:
        pr = find_pr(api, dataset, title)
    except LookupError as exc:
        return [str(exc)]
    info = api.dataset_info(dataset, revision=f"refs/pr/{pr.num}", files_metadata=True)
    m, entries, bad, extra = compare(info.siblings, Path(pack))
    problems = [f"{p} differs or is missing" for p in bad]
    problems += [f"files on the pull request that the pack does not have: {extra}"] if extra else []
    if m.get("version") != version:
        problems.append(f"the pack is version {m.get('version')}, not {version}")
    out(
        f"pull request #{pr.num} ({getattr(pr, 'status', '?')}) {title!r}, refs/pr/{pr.num} at "
        f"{str(info.sha)[:8]}: {len(entries) + len(DOCS) - len(bad)} of "
        f"{len(entries) + len(DOCS)} files match the pack ({len(m.get('files', []))} Parquet, "
        f"{len(m.get('access_files') or [])} easy-access, {len(DOCS)} documents); extra "
        f"{extra or 'none'}"
    )
    return problems


# --- the command line ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m plainpairs.weekly", description=__doc__.split("\n")[0]
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("next-version", help="the version after the manifest's")
    p.add_argument("--manifest", required=True)
    p = sub.add_parser("report", help="the run's report in Markdown (counts only)")
    p.add_argument(
        "--summary", help="the update's summary.json (absent when the run stopped early)"
    )
    p.add_argument("--manifest", help="the new pack's manifest.json")
    p.add_argument("--version")
    p.add_argument("--previous", help="the last published version")
    p.add_argument("--delivery", choices=("on", "off"), default="off")
    p.add_argument("--usage-log")
    p.add_argument("--since", help="count the usage log from this UTC time")
    p.add_argument("--stopped-because")
    p = sub.add_parser("pr-check", help="signed out: the open pull request holds the pack")
    p.add_argument("--pack", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--dataset", default=DATASET)
    args = ap.parse_args(argv)
    if args.cmd == "next-version":
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        print(next_version(manifest["version"]))
        return 0
    if args.cmd == "report":

        def read(path: str | None) -> dict[str, Any] | None:
            return (
                json.loads(Path(path).read_text(encoding="utf-8"))
                if path and Path(path).is_file()
                else None
            )

        calls = usage(Path(args.usage_log), args.since) if args.usage_log and args.since else None
        print(
            report(
                read(args.summary),
                read(args.manifest),
                args.version,
                args.delivery == "on",
                calls,
                args.stopped_because,
                args.previous,
            ),
            end="",
        )
        return 0
    problems = pr_check(Path(args.pack), args.version, args.dataset)
    for p in problems:
        print("PROBLEM:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
