"""The ``plainpairs`` command line."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from plainpairs import (
    __version__,
    bulk,
    changes,
    codes,
    dailymed,
    label,
    listed,
    nci,
    pages,
    probe,
    release,
    sheet,
    spl_release,
    stats,
    structure,
    tables,
)
from plainpairs import profile as prof
from plainpairs.client import Budget, PoliteClient, UsageLog

USAGE_LOG = Path("data/usage_log.csv")
PAGES_ROOT = Path("data/raw/pages")
BULK_ROOT = Path("data/raw/bulk")
LISTED_ROOT = Path("data/raw/listed")
RELEASE_ROOT = Path("data/raw/dailymed/rx-release")
NCI_ROOT = Path("data/raw/nci")


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
            f"{path} does not lead to a folder on the drive. Mount the external data drive "
            "and check that data/raw is a symlink to it."
        )


def cmd_fetch_page(args: argparse.Namespace) -> int:
    raw = Path("data/raw")
    _check_drive(raw)
    client = make_client(args.since, args.max_calls, args.max_bytes)
    client.min_interval = args.min_interval
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
    if NCI_ROOT.exists():  # quotes from NCI's summary pages are checked on the saved pages
        again = pages.check_quotes(Path(args.quotes), NCI_ROOT)
        results = [
            b if (not a.found and a.reason == "no saved copy of this page") else a
            for a, b in zip(results, again, strict=True)
        ]
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


def cmd_download_all(args: argparse.Namespace) -> int:
    _check_drive(Path("data/raw"))
    client = make_client(args.since, args.max_calls, args.max_bytes)
    day = today_utc()
    first = pages.fetch_page(client, bulk.DOWNLOAD_JSON, PAGES_ROOT, day)
    listing = json.loads(first.path.read_text(encoding="utf-8"))
    export_date, parts = bulk.label_parts(listing)
    print(f"Listing: export {export_date}, {len(parts)} parts.", flush=True)
    rows = bulk.fetch_all(
        client,
        listing,
        BULK_ROOT,
        args.max_mb,
        clock=client.clock,
        log=lambda s: print(s, flush=True),
    )
    second = pages.fetch_page(client, bulk.DOWNLOAD_JSON, PAGES_ROOT, day)
    again, _ = bulk.label_parts(json.loads(second.path.read_text(encoding="utf-8")))
    total = sum(int(r["bytes"]) for r in rows)
    print(
        f"{len(rows)} parts of the {export_date} export on disk, {total:,} bytes; "
        f"{client.budget.calls} of {client.budget.max_calls} calls this session.",
        flush=True,
    )
    if again != export_date:
        print(
            f"The export date changed during the run ({export_date} -> {again}). Stop here: "
            "read the listing again once and start over from it.",
            flush=True,
        )
        return 2
    print(f"The listing still names {export_date}: all parts share one export date.", flush=True)
    return 0


def _release_listing(client: PoliteClient) -> list[spl_release.ReleasePart]:
    saved = pages.fetch_page(client, spl_release.PAGE_URL, PAGES_ROOT, today_utc())
    if saved.status != 200:
        raise SystemExit(f"{spl_release.PAGE_URL} answered HTTP {saved.status}; stop here.")
    return spl_release.parse_parts(saved.path.read_text(encoding="utf-8", errors="replace"))


def cmd_xml_download(args: argparse.Namespace) -> int:
    import shutil

    _check_drive(Path("data/raw"))
    client = make_client(args.since, args.max_calls, args.max_bytes)
    parts = _release_listing(client)
    day = spl_release.release_date(parts)
    for p in parts:
        print(
            f"part {p.number}: {p.filename}, {p.files:,} files, {p.size_text}, "
            f"MD5 {p.md5}, modified {p.last_modified}",
            flush=True,
        )
    total = spl_release.check_total(parts, int(args.max_gb * 1e9))
    free = shutil.disk_usage(Path("data/raw").resolve()).free
    print(f"Release of {day}: {total:,} bytes listed (binary reading); {free:,} free.", flush=True)
    if free < total * 1.2:
        print("Not enough free space on the drive (need 1.2 times the listed total). Stop here.")
        return 2
    if args.list_only:
        return 0
    rows = spl_release.fetch_parts(
        client, parts, RELEASE_ROOT, clock=client.clock, log=lambda s: print(s, flush=True)
    )
    again = _release_listing(client)
    print(
        f"{len(rows)} parts on disk, {sum(int(r['bytes']) for r in rows):,} bytes; "
        f"{client.budget.calls} of {client.budget.max_calls} calls this session.",
        flush=True,
    )
    if [(p.filename, p.md5) for p in again] != [(p.filename, p.md5) for p in parts]:
        print("The page changed during the download: a part was replaced. Stop and look.")
        return 2
    print("The page still lists the same parts and checksums.", flush=True)
    return 0


def release_parts(day: str, verify: bool = False) -> list[Path]:
    """The release parts of ``day``, checked against their manifest (size; SHA-256 if asked)."""
    from plainpairs import durable

    rows = spl_release.read_manifest(spl_release.manifest_path(RELEASE_ROOT, day))
    if not rows:
        raise SystemExit(f"No release manifest for {day} under {RELEASE_ROOT}; download it first.")
    out = []
    for name, row in sorted(rows.items(), key=lambda kv: int(kv[1]["part"])):
        path = RELEASE_ROOT / day / name
        if not path.exists() or path.stat().st_size != int(row["bytes"]):
            raise SystemExit(f"{path} is missing or has the wrong size; download it again.")
        if verify and durable.sha256_file(path) != row["sha256"]:
            raise SystemExit(f"{path} does not match its SHA-256 in the manifest.")
        out.append(path)
    return out


def cmd_structure(args: argparse.Namespace) -> int:
    parts = release_parts(args.release_date, args.verify)
    print(f"{len(parts)} release parts of {args.release_date} match their manifest.", flush=True)
    summary = structure.build(
        parts,
        args.release_date,
        Path(args.tables),
        Path(args.out),
        workers=args.workers,
        log=lambda s: print(s, flush=True),
    )
    print(json.dumps(summary["counts"], sort_keys=True), flush=True)
    return 0


def _read_dates(root: Path) -> dict[str, str]:
    """The day each NCI page was read, from the NCI manifest's time column."""
    import csv

    manifest = Path(root) / "manifest.csv"
    if not manifest.exists():
        return {}
    with manifest.open(newline="", encoding="utf-8") as fh:
        return {r["url"]: r["time"][:10] for r in csv.DictReader(fh) if r["status"] == "200"}


def cmd_nci_build(args: argparse.Namespace) -> int:
    dates = _read_dates(Path(args.root))
    counts = nci.build(
        Path(args.root),
        Path(args.out),
        date_read=lambda u: dates.get(u, ""),
        log=lambda s: print(s, flush=True),
    )
    print(json.dumps(counts, sort_keys=True), flush=True)
    return 0


def cmd_nci_text(args: argparse.Namespace) -> int:
    import pyarrow.parquet as pq

    summaries = pq.read_table(Path(args.tables) / "nci_summaries.parquet").to_pylist()
    if args.saved:
        saved = nci.saved_pages(Path(args.saved))

        def get_page(url: str) -> str | None:
            path = saved.get(url)
            return path.read_text(encoding="utf-8", errors="replace") if path else None

        print(f"Rebuilding the NCI text from the pages saved under {args.saved}.", flush=True)
    else:
        from plainpairs import nci_pages

        client = make_client(args.since, args.max_calls, args.max_bytes)
        client.min_interval = nci_pages.MIN_INTERVAL

        def get_page(url: str) -> str | None:
            resp = client.get(url)
            return resp.content.decode("utf-8", errors="replace") if resp.status == 200 else None

        print(
            f"Rebuilding the NCI text by reading NCI's {len(summaries)} pages again, one every "
            f"{nci_pages.MIN_INTERVAL:.0f} seconds (pages NCI has updated since will differ).",
            flush=True,
        )
    report = nci.rebuild_text(summaries, get_page)
    if args.out:
        import pyarrow as pa

        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(report["rows"]), args.out)
    print(json.dumps(report["counts"], sort_keys=True))
    return 0 if not report["counts"].get("missing") else 1


def _listing_paths(args: argparse.Namespace) -> tuple[Path | None, Path | None]:
    ndc = Path(args.ndc) if args.ndc else None
    dm = Path(args.dailymed) if args.dailymed else None
    if args.listed:
        ndc = ndc or listed.latest(LISTED_ROOT, "ndc")
        dm = dm or listed.latest(LISTED_ROOT, "dailymed")
        if ndc is None or dm is None:
            raise SystemExit(
                f"--listed needs both listing files under {LISTED_ROOT}; "
                "fetch them with `plainpairs listed-download` first."
            )
    return ndc, dm


def cmd_listed_download(args: argparse.Namespace) -> int:
    _check_drive(Path("data/raw"))
    client = make_client(args.since, args.max_calls, args.max_bytes)
    day = today_utc()
    saved = pages.latest_pages(PAGES_ROOT).get(bulk.DOWNLOAD_JSON)
    if saved is None or saved.parent.parent.name != day:
        saved = pages.fetch_page(client, bulk.DOWNLOAD_JSON, PAGES_ROOT, day).path
    listing = json.loads(saved.read_text(encoding="utf-8"))
    for f in listed.ndc_files(listing):
        print(f"NDC directory: {f.filename}, export {f.export_date}, {f.size_mb} MiB listed.")
    for path in listed.fetch_ndc(client, listing, LISTED_ROOT, args.max_mb):
        print(f"  on disk: {path} ({path.stat().st_size:,} bytes)")
    path = listed.fetch_dailymed(client, LISTED_ROOT, day, args.max_mb)
    print(f"DailyMed zip file metadata on disk: {path} ({path.stat().st_size:,} bytes)")
    print(f"Calls this session: {client.budget.calls} of {client.budget.max_calls}.")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    parts = tables.parts_from_manifest(BULK_ROOT, args.export_date)
    print(f"{len(parts)} parts of {args.export_date} match their manifest.", flush=True)
    ndc, dm = _listing_paths(args)
    listings = listed.load(ndc, dm)
    for name, src in listings.sources.items():
        print(f"listing {name}: {src['file']} of {src['date']}", flush=True)
    builder = tables.Builder(
        parts,
        Path(args.out),
        args.export_date,
        log=lambda s: print(s, flush=True),
        workers=args.workers,
        listings=listings,
        structure_dir=Path(args.structure) if args.structure else None,
    )
    stats = builder.run()
    print(json.dumps(stats.get("rows", {}), sort_keys=True), flush=True)
    return 0


def cmd_sheet(args: argparse.Namespace) -> int:
    src = Path(args.tables)
    pairs = (
        tables.read_table(src, "section_pairs")
        .select(
            [
                "set_id",
                "version",
                "kind",
                "segment_index",
                "heading_key",
                "patient_text_id",
                "mapped_present",
                "seg_start",
                "seg_end",
                "measures",
            ]
        )
        .to_pylist()
    )
    labels = tables.read_table(src, "labels").select(["set_id", "medicine_key"]).to_pylist()
    picks = sheet.draw(
        pairs, {r["set_id"]: r["medicine_key"] for r in labels}, args.per_key, args.seed
    )
    ids = sorted({p["set_id"] for p in picks})
    tp = _texts(src / "text_patient.parquet", ids)
    tr = _texts(src / "text_prescriber.parquet", ids)
    out = Path(args.out)
    x = sheet.write(
        picks,
        tp,
        tr,
        out / f"hand-sheet-seed{args.seed}.xlsx",
        out / f"hand-sheet-seed{args.seed}-key.csv",
    )
    print(f"Wrote {len(picks)} rows to {x} and its key next to it (seed {args.seed}).")
    return 0


def _texts(path: Path, ids: list[str]) -> dict[tuple[str, str], str]:
    import pyarrow.dataset as ds

    if not ids:
        return {}

    table = ds.dataset(path).to_table(
        columns=["set_id", "section", "part", "text"],
        filter=(ds.field("set_id").isin(ids)) & (ds.field("part") == "text"),
    )
    return {(r["set_id"], r["section"]): r["text"] for r in table.to_pylist()}


def cmd_sheet_check(args: argparse.Namespace) -> int:
    out = sheet.check(Path(args.sheet), Path(args.key))
    for heading, r in sorted(out.items()):
        share = "-" if r["share_yes_or_partly"] is None else f"{r['share_yes_or_partly']:.0%}"
        print(
            f"{heading:15} answered {r['answered']:>3}  yes {r['yes']:>3}  partly {r['partly']:>3}"
            f"  no {r['no']:>3}  blank {r['blank']:>3}  yes or partly {share:>5}  -> {r['rule']}"
        )
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    return 0


def cmd_release_check(args: argparse.Namespace) -> int:
    src = Path(args.tables)
    summary = json.loads((src / "build_summary.json").read_text(encoding="utf-8"))
    manifest = bulk.read_manifest(bulk.manifest_path(BULK_ROOT, summary["export_date"]))
    problems, info = release.check(src, manifest, args.switch, args.allow_marked)
    for k, v in sorted(info.items()):
        print(f"{k}: {v}")
    if problems:
        print(f"RELEASE CHECK FAILED ({len(problems)} problems):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"Release check passed for the switch setting {args.switch!r}.")
    return 0


def cmd_text(args: argparse.Namespace) -> int:
    report = release.rebuild_text(
        Path(args.labels), BULK_ROOT, Path(args.out), log=lambda s: print(s, flush=True)
    )
    print(json.dumps(report, sort_keys=True))
    ok = report["missing"] == 0 and report["hash_mismatches"] == 0
    print(
        "The text layer was rebuilt and every row matches its hash."
        if ok
        else "REBUILD DID NOT MATCH."
    )
    return 0 if ok else 1


def cmd_dailymed_test(args: argparse.Namespace) -> int:
    src = Path(args.tables)
    labels = (
        tables.read_table(src, "labels")
        .select(
            [
                "set_id",
                "version",
                "label_format",
                "has_medication_guide",
                "has_patient_package_insert",
            ]
        )
        .to_pylist()
    )
    picks = dailymed.choose(labels, args.per_stratum, args.seed)
    client = make_client(args.since, args.max_calls, args.max_bytes)
    root = Path("data/raw/dailymed")
    robots = pages.fetch_page(client, "https://dailymed.nlm.nih.gov/robots.txt", root, today_utc())
    print(f"robots.txt: HTTP {robots.status}, {robots.nbytes} bytes; read it before going on.")
    if args.robots_only:
        return 0
    ids = [p["set_id"] for p in picks]
    texts = {
        **_texts(src / "text_prescriber.parquet", ids),
        **_texts(src / "text_patient.parquet", ids),
    }
    results = []
    for p in picks:
        url = dailymed.SERVICE.format(set_id=p["set_id"])
        saved = pages.fetch_page(client, url, root, today_utc())
        row = {
            "set_id": p["set_id"],
            "stratum": p["stratum"],
            "json_version": p["version"],
            "status": saved.status,
        }
        if saved.status == 200:
            doc = dailymed.parse_spl(saved.path.read_bytes())
            own = {name: t for (sid, name), t in texts.items() if sid == p["set_id"]}
            row.update(xml_version=doc["version"], sections=dailymed.compare(own, doc))
        results.append(row)
        print(
            f"{p['stratum']:32} HTTP {saved.status} versions json {p['version']} "
            f"xml {row.get('xml_version')}",
            flush=True,
        )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=1, sort_keys=True), encoding="utf-8")
    print(f"{len(results)} labels compared into {out}; {client.budget.calls} calls this session.")
    return 0


def cmd_changes(args: argparse.Namespace) -> int:
    summary = changes.write(Path(args.old), Path(args.new), Path(args.out))
    if args.json:
        Path(args.json).write_text(json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")
    print(
        f"{summary['old_export_date']} -> {summary['new_export_date']}: "
        f"{summary['rows']:,} labels changed, {summary['unchanged']:,} unchanged; "
        + ", ".join(f"{k} {v:,}" for k, v in summary["changes"].items()),
        flush=True,
    )
    return 0


def cmd_codes(args: argparse.Namespace) -> int:
    n = codes.build(
        Path(args.tables),
        workers=args.workers,
        log=lambda s: print(s, flush=True),
        structure_path=Path(args.structure) if args.structure else None,
    )
    print(f"Coded {n:,} texts (codebook version {codes.CODE_VERSION}).", flush=True)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    s = stats.corpus_stats(Path(args.tables))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(s, indent=1, sort_keys=True, default=str), encoding="utf-8"
    )
    print(
        f"{s['labels']:,} labels, {s['section_pairs']:,} section pairs; aggregates in {args.out}."
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
    p.add_argument("--min-interval", type=float, default=1.0, help="seconds between requests")
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

    p = sub.add_parser("download-all", help="every part of the listed export (resumable)")
    p.add_argument("--max-mb", type=float, default=200.0, help="the largest part allowed")
    caps(p)
    p.set_defaults(func=cmd_download_all)

    p = sub.add_parser("build", help="build both layers from the parts of one export")
    p.add_argument("--export-date", required=True)
    p.add_argument("--out", default="data/interim/tables")
    p.add_argument("--workers", type=int, default=1, help="parts read in parallel")
    p.add_argument("--ndc", help="the NDC directory file for the listed-now flags")
    p.add_argument("--dailymed", help="DailyMed's zip file metadata for the listed-now flags")
    p.add_argument(
        "--listed", action="store_true", help="use the newest listing files under data/raw/listed"
    )
    p.add_argument(
        "--structure",
        help="the structure folder (plainpairs structure) for the two configurations",
    )
    p.set_defaults(func=cmd_build)

    p = sub.add_parser(
        "listed-download", help="the NDC directory and DailyMed's label list (small files)"
    )
    p.add_argument("--max-mb", type=float, default=listed.MAX_MB, help="the largest file allowed")
    caps(p)
    p.set_defaults(func=cmd_listed_download)

    p = sub.add_parser(
        "xml-download", help="DailyMed's full human prescription release (resumable, large)"
    )
    p.add_argument("--max-gb", type=float, default=20.0, help="stop if the listed total is over")
    p.add_argument("--list-only", action="store_true", help="read the page and stop")
    caps(p)
    p.set_defaults(func=cmd_xml_download)

    p = sub.add_parser(
        "structure", help="read the release's XML: index, blocks and structure per label"
    )
    p.add_argument("--release-date", required=True)
    p.add_argument("--tables", default="data/interim/tables", help="the build to join to")
    p.add_argument("--out", default="data/interim/structure")
    p.add_argument("--workers", type=int, default=1, help="parts read in parallel")
    p.add_argument("--verify", action="store_true", help="check each part's SHA-256 first")
    p.set_defaults(func=cmd_structure)

    p = sub.add_parser("nci-build", help="the NCI cancer information summaries' three tables")
    p.add_argument("--root", default=str(NCI_ROOT), help="where the summary pages are saved")
    p.add_argument("--out", default="data/interim/tables")
    p.set_defaults(func=cmd_nci_build)

    p = sub.add_parser(
        "nci-text",
        help="rebuild the NCI text by reading NCI's pages again (or from saved copies)",
    )
    p.add_argument("--tables", default="data/interim/tables")
    p.add_argument("--saved", help="read the saved copies under this folder instead of NCI")
    p.add_argument("--out", help="write the rebuilt blocks to this Parquet file")
    caps(p)
    p.set_defaults(func=cmd_nci_text)

    p = sub.add_parser("sheet", help="write the blind hand sheet (and its key)")
    p.add_argument("--tables", default="data/interim/tables")
    p.add_argument("--out", default="data/interim/sheet")
    p.add_argument("--per-key", type=int, default=10)
    p.add_argument("--seed", type=int, default=20261115)
    p.set_defaults(func=cmd_sheet)

    p = sub.add_parser(
        "sheet-check", help="share of yes or partly per heading, from a filled sheet"
    )
    p.add_argument("sheet")
    p.add_argument("--key", required=True)
    p.add_argument("--json", default="")
    p.set_defaults(func=cmd_sheet_check)

    p = sub.add_parser("release-check", help="fail loudly on anything a release must not have")
    p.add_argument("--tables", default="data/interim/tables")
    p.add_argument("--switch", choices=release.SWITCH, default="unmarked")
    p.add_argument("--allow-marked", action="store_true")
    p.set_defaults(func=cmd_release_check)

    p = sub.add_parser("text", help="rebuild the text layer from the record layer and bulk files")
    p.add_argument("--labels", default="data/interim/tables/labels.parquet")
    p.add_argument("--out", default="data/interim/rebuilt")
    p.set_defaults(func=cmd_text)

    p = sub.add_parser("dailymed-test", help="compare DailyMed XML with the JSON for a few labels")
    p.add_argument("--tables", default="data/interim/tables")
    p.add_argument("--per-stratum", type=int, default=5)
    p.add_argument("--seed", type=int, default=20261115)
    p.add_argument("--out", default="data/interim/dailymed/compare.json")
    p.add_argument("--robots-only", action="store_true")
    caps(p)
    p.set_defaults(func=cmd_dailymed_test)

    p = sub.add_parser("changes", help="what changed between two builds (record layers)")
    p.add_argument("--old", required=True, help="the older build's tables folder")
    p.add_argument("--new", required=True, help="the newer build's tables folder")
    p.add_argument("--out", required=True, help="where to write changes.parquet")
    p.add_argument("--json", help="also write the counts to this file")
    p.set_defaults(func=cmd_changes)

    p = sub.add_parser("codes", help="rule-based codes of every text (counts, no text)")
    p.add_argument("--tables", default="data/interim/tables")
    p.add_argument("--workers", type=int, default=1, help="batches coded in parallel")
    p.add_argument(
        "--structure", help="structure.parquet, for the length codes from structure (current)"
    )
    p.set_defaults(func=cmd_codes)

    p = sub.add_parser("stats", help="aggregates of a built corpus (no text)")
    p.add_argument("--tables", default="data/interim/tables")
    p.add_argument("--out", default="data/interim/stats/corpus_stats.json")
    p.set_defaults(func=cmd_stats)

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
