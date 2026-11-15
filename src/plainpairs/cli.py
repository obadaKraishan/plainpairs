"""The ``plainpairs`` command line."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from plainpairs import __version__, bulk, label, pages, probe
from plainpairs import profile as prof
from plainpairs.client import Budget, PoliteClient, UsageLog

USAGE_LOG = Path("data/usage_log.csv")
PAGES_ROOT = Path("data/raw/pages")
BULK_ROOT = Path("data/raw/bulk")


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def make_client(since: str, max_calls: int, max_bytes: int) -> PoliteClient:
    """A client whose caps already count the calls logged since ``since``."""
    log = UsageLog(USAGE_LOG)
    budget = Budget.from_log(log.rows(), since=since, max_calls=max_calls, max_bytes=max_bytes)
    return PoliteClient(log=log, budget=budget)


def _check_drive(path: Path) -> None:
    if not path.resolve().parent.exists():
        raise SystemExit(
            f"{path} does not lead to a folder on the drive. Mount the Kraishan drive and check "
            "that data/raw is a symlink to it."
        )


def cmd_fetch_page(args: argparse.Namespace) -> int:
    raw = Path("data/raw")
    _check_drive(raw)
    client = make_client(args.since, args.max_calls, args.max_bytes)
    for url in args.urls:
        saved = pages.fetch_page(client, url, PAGES_ROOT, args.day)
        print(f"{saved.status} {saved.nbytes:>9,} bytes  {url}")
    print(f"Calls this session: {client.budget.calls} of {client.budget.max_calls}.")
    return 0


def cmd_page_text(args: argparse.Namespace) -> int:
    found = pages.latest_pages(PAGES_ROOT)
    if args.url not in found:
        print(f"No saved copy of {args.url}. Fetch it first with `plainpairs fetch-page`.")
        return 1
    sys.stdout.write(pages.page_text(found[args.url]) + "\n")
    return 0


def cmd_quotes_check(args: argparse.Namespace) -> int:
    results = pages.check_quotes(Path(args.quotes), PAGES_ROOT)
    bad = [r for r in results if not r.found]
    for r in bad:
        print(f"MISSING ({r.reason}): {r.url}\n    {r.quote[:120]}")
    print(f"{len(results) - len(bad)} of {len(results)} quotes found word for word.")
    return 1 if bad else 0


def cmd_counts(args: argparse.Namespace) -> int:
    client = make_client(args.since, args.max_calls, args.max_bytes)
    client.min_interval = args.min_interval
    p = probe.Probe(client, Path(args.out))
    plan = probe.standard_plan()
    if args.first:
        plan = plan[: args.first]
    before = client.budget.calls
    try:
        probe.run_plan(p, plan)
    finally:
        print(
            f"{len(p.results)} answers saved to {args.out}; {client.budget.calls - before} calls "
            f"made now, {client.budget.calls} of {client.budget.max_calls} this session."
        )
    return 0


def cmd_download_part(args: argparse.Namespace) -> int:
    _check_drive(Path("data/raw"))
    listing = pages.latest_pages(PAGES_ROOT).get(bulk.DOWNLOAD_JSON)
    if listing is None:
        print(
            f"No saved copy of {bulk.DOWNLOAD_JSON}. Fetch it first with `plainpairs fetch-page`."
        )
        return 1
    export_date, parts = bulk.label_parts(json.loads(listing.read_text(encoding="utf-8")))
    part = (
        bulk.smallest(parts) if args.part == 0 else next(p for p in parts if p.number == args.part)
    )
    client = make_client(args.since, args.max_calls, args.max_bytes)
    dest = bulk.fetch_part(client, part, BULK_ROOT, export_date, args.max_mb)
    print(f"Saved part {part.number} of {part.of} ({dest.stat().st_size:,} bytes) to {dest}.")
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    rows = label.iter_rows(args.part)
    summary = prof.profile(rows)
    summary["source_part"] = Path(args.part).name
    summary["source_meta"] = {
        k: v for k, v in bulk.read_meta(args.part).items() if k != "disclaimer"
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=1, sort_keys=True, default=str), encoding="utf-8")
    print(
        f"Profiled {summary['labels']:,} labels ({summary['paired_labels']:,} paired) into {out}."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plainpairs",
        description="Build a research corpus of how US medicine labels are worded for two readers.",
    )
    parser.add_argument("--version", action="version", version=f"plainpairs {__version__}")
    sub = parser.add_subparsers(dest="command")

    def caps(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--since",
            default=f"{today_utc()}T00:00:00Z",
            help="count the calls logged since this UTC time against the caps (default: today)",
        )
        p.add_argument("--max-calls", type=int, default=300)
        p.add_argument("--max-bytes", type=int, default=300_000_000)

    p = sub.add_parser("fetch-page", help="save source pages raw to the drive, as evidence")
    p.add_argument("urls", nargs="+")
    p.add_argument("--day", default=today_utc())
    caps(p)
    p.set_defaults(func=cmd_fetch_page)

    p = sub.add_parser("page-text", help="print the plain text of a saved page")
    p.add_argument("url")
    p.set_defaults(func=cmd_page_text)

    p = sub.add_parser("counts", help="ask the label API the standard counts (resumable)")
    p.add_argument("--out", default="data/interim/probe/counts.json")
    p.add_argument("--first", type=int, default=0, help="ask only the first N questions")
    p.add_argument("--min-interval", type=float, default=1.5)
    caps(p)
    p.set_defaults(func=cmd_counts)

    p = sub.add_parser("download-part", help="download one bulk part of the label data")
    p.add_argument("--part", type=int, default=0, help="the part number (default: the smallest)")
    p.add_argument("--max-mb", type=float, default=200.0)
    caps(p)
    p.set_defaults(func=cmd_download_part)

    p = sub.add_parser("profile", help="aggregates of one downloaded part (no label text)")
    p.add_argument("part", help="path to a downloaded part (.json.zip)")
    p.add_argument("--out", default="data/interim/profile/profile.json")
    p.set_defaults(func=cmd_profile)

    p = sub.add_parser("quotes-check", help="confirm every quote in docs/quotes.csv on its page")
    p.add_argument("--quotes", default="docs/quotes.csv")
    p.set_defaults(func=cmd_quotes_check)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return int(args.func(args))
