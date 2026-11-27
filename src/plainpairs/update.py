"""The weekly update: from the last build (or the last published pack) to the newest export.

``plainpairs update`` does, in order:

1. reads openFDA's ``download.json``; if it lists no export newer than the last build's, it
   stops with ``status = no_new_export`` (nothing is downloaded);
2. reads DailyMed's download page and chooses the update files for the days after the last
   DailyMed release up to the new export date: the daily files of the current week and the
   weekly file of each week before it (:func:`choose`). If a weekday of that span is no longer
   covered by any listed file (:func:`coverage`), it stops with ``status = stopped`` before
   anything is downloaded;
3. downloads the new export's label parts, the NDC directory and DailyMed's label list
   (:mod:`plainpairs.bulk`, :mod:`plainpairs.listed`), and the chosen update files (each
   checked against the page's MD5);
4. builds the tables once without structure, then carries the structure of every label whose
   set id and version did not change forward from the last build, and reads the new versions
   from the update files (:mod:`plainpairs.structure`);
5. builds again with the structure (the two configurations) and the hand sheet's rule status
   carried from the last build; copies the NCI tables (read on their own three-month schedule)
   and records their SHA-256;
6. writes the ``changes`` table against the last build, counts the labels that moved between
   ``current`` and ``unlisted``, runs the codes and the release check, and writes
   ``summary.json`` (counts only, never text).

Every source is reached through a :class:`Sources` object, so tests run on invented exports.
"""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import pyarrow as pa
import pyarrow.parquet as pq

from plainpairs import (
    bulk,
    changes,
    codes,
    durable,
    listed,
    pages,
    release,
    spl_release,
    structure,
    tables,
)

#: A daily file (``dm_spl_daily_update_MMDDYYYY.zip``) or a weekly one
#: (``dm_spl_weekly_update_MMDDYY_MMDDYY.zip``, Monday to Friday, two-digit years), with the
#: page's label count, size and MD5.
_UPDATE = re.compile(
    r"(dm_spl_(daily|weekly)_update_(\d{6}|\d{8})(?:_(\d{6}))?\.zip)\s*\[\s*HTTPS\s*/\s*FTP\s*\]"
    r"\s*Number of labels:\s*([\d,]+)\s*File size:\s*([\d.]+)\s*(GB|MB|KB)\s*"
    r"MD5 checksum:\s*([0-9a-fA-F]{32})"
)


@dataclass(frozen=True)
class UpdateFile:
    name: str
    url: str
    day: str  # ISO date of the last day the file covers
    labels: int
    size_text: str
    md5: str
    start: str = ""  # ISO date of its first day (a weekly file); "" for a daily file
    kind: str = "daily"  # "daily" or "weekly"

    @property
    def first_day(self) -> str:
        return self.start or self.day

    @property
    def days(self) -> list[str]:
        """Every date the file covers, first to last."""
        return _dates(self.first_day, self.day)

    @property
    def size_bytes_upper(self) -> int:
        value, unit = re.fullmatch(r"([\d.]+)(GB|MB|KB)", self.size_text).groups()  # type: ignore[union-attr]
        return int(float(value) * {"KB": 2**10, "MB": 2**20, "GB": 2**30}[unit])


def _dates(first: str, last: str) -> list[str]:
    a, b = date.fromisoformat(first), date.fromisoformat(last)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def _weekday(day: str) -> bool:
    return date.fromisoformat(day).weekday() < 5


def _iso(token: str) -> str:
    """``MMDDYYYY`` or ``MMDDYY`` (DailyMed's weekly names) as an ISO date."""
    mm, dd, yy = token[:2], token[2:4], token[4:]
    return f"{yy if len(yy) == 4 else '20' + yy}-{mm}-{dd}"


def daily_updates(markup: str) -> list[UpdateFile]:
    """The daily and weekly update files DailyMed's download page lists, oldest first (a file
    the page names but links nowhere on its file host is left out)."""
    plain = pages.html_to_text(markup)
    out = {}
    for m in _UPDATE.finditer(plain):
        name, kind, first, last, n, size, unit, md5 = m.groups()
        url = spl_release.FILE_HOST + name
        if f'href="{url}"' not in markup:
            continue
        if (kind == "weekly") != (last is not None):
            continue
        start, end = (_iso(first), _iso(last)) if last else ("", _iso(first))
        out[name] = UpdateFile(
            name, url, end, int(n.replace(",", "")), size + unit, md5.lower(), start, kind
        )
    return sorted(out.values(), key=lambda u: (u.first_day, u.day))


def choose(files: list[UpdateFile], after: str, until: str) -> list[UpdateFile]:
    """The files for the days after ``after`` up to ``until`` (ISO dates): every weekly file that
    reaches into that span, then a daily file for each day of the span that no chosen weekly
    file covers. A weekly file holds its whole week, so when DailyMed lists a week both ways (a
    new weekly file while the week's daily files are still listed) the week is read once, from
    the weekly file, and none of its days is left uncovered."""
    weekly = [f for f in files if f.kind == "weekly" and f.day > after and f.first_day <= until]
    by_week = {d for f in weekly for d in f.days}
    daily = [
        f for f in files if f.kind == "daily" and after < f.day <= until and f.day not in by_week
    ]
    return sorted(weekly + daily, key=lambda u: (u.first_day, u.day))


def coverage(files: list[UpdateFile], chosen: list[UpdateFile], after: str, until: str) -> dict:
    """Which weekdays after ``after`` up to ``until`` the chosen files cover (dates only).

    DailyMed lists one file per working day for the current week and one file per week before
    it. A weekday no chosen file covers is ``missing`` when it falls before the days the page
    lists day by day (its weekly file is no longer listed: the update must stop), and
    ``without_file`` when it falls among them (DailyMed published nothing that day, such as a
    holiday, or the day has not been published yet)."""
    covered = {d for f in chosen for d in f.days}
    weeks = [f.day for f in files if f.kind == "weekly"]
    dailies = [f.day for f in files if f.kind == "daily"]
    if weeks:
        by_day = (date.fromisoformat(max(weeks)) + timedelta(days=1)).isoformat()
    elif dailies:
        by_day = min(dailies)
    else:
        by_day = None
    gap = [d for d in _dates(after, until)[1:] if _weekday(d)] if after < until else []
    open_days = [d for d in gap if d not in covered]
    missing = [d for d in open_days if by_day is None or d < by_day]
    return {
        "after": after,
        "until": until,
        "weekdays": len(gap),
        "weekdays_covered": len(gap) - len(open_days),
        "weekdays_missing": missing,
        "weekdays_without_file": [d for d in open_days if d not in missing],
        "files": [{"name": f.name, "kind": f.kind, "labels": f.labels} for f in chosen],
    }


@dataclass(frozen=True)
class UpdateChoice:
    """DailyMed's update files chosen for one update, and the days they cover."""

    files: list[UpdateFile]
    coverage: dict


class Sources(Protocol):
    def listing(self) -> dict[str, Any]: ...

    def label_parts(self, listing: dict[str, Any]) -> list[tuple[int, Path]]: ...

    def listings(self, listing: dict[str, Any]) -> tuple[Path, Path]: ...

    def dailymed_choice(self, after: str, until: str) -> UpdateChoice: ...

    def dailymed_download(self, choice: UpdateChoice) -> list[Path]: ...


@dataclass
class OnlineSources:
    """The real sources, through the polite client and the project's raw folders."""

    client: Any
    bulk_root: Path
    listed_root: Path
    pages_root: Path
    updates_root: Path
    day: str
    log: Callable[[str], None] = print

    def listing(self) -> dict[str, Any]:
        saved = pages.fetch_page(self.client, bulk.DOWNLOAD_JSON, self.pages_root, self.day)
        return json.loads(saved.path.read_text(encoding="utf-8"))

    def label_parts(self, listing: dict[str, Any]) -> list[tuple[int, Path]]:
        export_date, _parts = bulk.label_parts(listing)
        bulk.fetch_all(
            self.client, listing, self.bulk_root, 200.0, clock=self.client.clock, log=self.log
        )
        return tables.parts_from_manifest(self.bulk_root, export_date)

    def listings(self, listing: dict[str, Any]) -> tuple[Path, Path]:
        ndc = listed.fetch_ndc(self.client, listing, self.listed_root)[0]
        dm = listed.fetch_dailymed(self.client, self.listed_root, self.day)
        return ndc, dm

    def dailymed_choice(self, after: str, until: str) -> UpdateChoice:
        saved = pages.fetch_page(self.client, spl_release.PAGE_URL, self.pages_root, self.day)
        listed_files = daily_updates(saved.path.read_text(encoding="utf-8", errors="replace"))
        files = choose(listed_files, after, until)
        return UpdateChoice(files, coverage(listed_files, files, after, until))

    def dailymed_download(self, choice: UpdateChoice) -> list[Path]:
        out = []
        for f in choice.files:
            dest = Path(self.updates_root) / f.day / f.name
            if not dest.exists():
                self.log(f"DailyMed {f.kind} update to {f.day}: {f.name} ({f.size_text})")
                self.client.download_resumable(
                    f.url, dest, max_bytes=int(f.size_bytes_upper * 1.01), expected_md5=f.md5
                )
            out.append(dest)
        return out


def previous_from_pack(pack_dir: Path, out_dir: Path) -> tuple[Path, Path]:
    """A last build rebuilt from a published pack (the record layer is public data): the
    labels, patient texts and pairs of both label configurations in one folder, and a
    structure folder whose rows come from the ``current`` labels' measures from structure."""
    pack_dir, out_dir = Path(pack_dir), Path(out_dir)
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    tdir, sdir = out_dir / "tables", out_dir / "structure"
    tdir.mkdir(parents=True, exist_ok=True)
    sdir.mkdir(parents=True, exist_ok=True)
    for name, schema in (
        ("labels", tables.LABELS_SCHEMA),
        ("patient_texts", tables.PATIENT_TEXTS_SCHEMA),
        ("section_pairs", tables.SECTION_PAIRS_SCHEMA),
    ):
        parts = []
        for conf in ("current", "unlisted"):
            t = pq.read_table(pack_dir / f"data/{conf}/{name}.parquet")
            rows = t.to_pylist()
            parts += [{k: r.get(k) for k in schema.names} for r in rows]
        pq.write_table(pa.Table.from_pylist(parts, schema), tdir / f"{name}.parquet")
    for short, name in (
        ("summaries", "nci_summaries"),
        ("pairs", "nci_pairs"),
        ("text", "nci_text"),
    ):
        src = pack_dir / f"data/nci/{short}.parquet"
        if src.exists():  # read on their own schedule: carried as they are
            shutil.copyfile(src, tdir / f"{name}.parquet")
    labels = pq.read_table(tdir / "labels.parquet").to_pylist()
    index, rows = [], []
    for r in labels:
        if r["configuration"] != "current":
            continue
        sid = r["set_id"].lower()
        index.append(
            {"set_id": sid, "version": r["version"], "version_match": True, "in_corpus": True}
        )
        for side, names in (("prescriber", tables.PRESCRIBER), ("patient", tables.PATIENT)):
            prefix = "p" if side == "prescriber" else "t"
            for n in names:
                st = r.get(f"{prefix}_{n}_structured")
                if st:
                    rows.append(
                        {
                            "set_id": sid,
                            "version": r["version"],
                            "section": n,
                            "side": side,
                            "structured": st,
                        }
                    )
    pq.write_table(pa.Table.from_pylist(index, structure.INDEX_SCHEMA), sdir / "index.parquet")
    pq.write_table(
        pa.Table.from_pylist(rows, structure.STRUCTURE_SCHEMA), sdir / "structure.parquet"
    )
    (sdir / "structure_summary.json").write_text(
        json.dumps({"release_date": manifest["sources"].get("dailymed_release")}), encoding="utf-8"
    )
    src = manifest["sources"]
    (tdir / "build_summary.json").write_text(
        json.dumps(
            {
                "export_date": src["openfda_label_export"],
                "structure": {"release_date": src.get("dailymed_release")},
                "dailymed": {
                    "full_release": src.get("dailymed_full_release") or src.get("dailymed_release")
                },
            }
        ),
        encoding="utf-8",
    )
    return tdir, sdir


def _carry_structure(
    prev: Path, new: Path, labels: list[dict[str, Any]], out: Path, release_date: str
) -> dict[str, int]:
    """One structure folder: the last build's rows for labels whose set id and version did not
    change, and the new rows read from the update files (``new``)."""
    keep = {(r["set_id"].lower(), r["version"]) for r in labels}
    pi = pq.read_table(Path(prev) / "index.parquet").to_pylist()
    ps = pq.read_table(Path(prev) / "structure.parquet").to_pylist()
    ni = (
        pq.read_table(Path(new) / "index.parquet").to_pylist()
        if (Path(new) / "index.parquet").exists()
        else []
    )
    ns = (
        pq.read_table(Path(new) / "structure.parquet").to_pylist()
        if (Path(new) / "structure.parquet").exists()
        else []
    )
    fresh = {(r["set_id"], r["version"]) for r in ns}
    rows = [
        r
        for r in ps
        if (r["set_id"], r["version"]) in keep and (r["set_id"], r["version"]) not in fresh
    ] + ns
    index = [
        {k: r.get(k) for k in ("set_id", "version", "version_match", "in_corpus")} for r in pi + ni
    ]
    out.mkdir(parents=True, exist_ok=True)
    schema = pa.schema(
        [
            f
            for f in structure.INDEX_SCHEMA
            if f.name in ("set_id", "version", "version_match", "in_corpus")
        ]
    )
    pq.write_table(pa.Table.from_pylist(index, schema), out / "index.parquet")
    pq.write_table(
        pa.Table.from_pylist(rows, structure.STRUCTURE_SCHEMA), out / "structure.parquet"
    )
    (out / "structure_summary.json").write_text(
        json.dumps({"release_date": release_date}), encoding="utf-8"
    )
    return {"structure_rows_carried": len(rows) - len(ns), "structure_rows_new": len(ns)}


def run(
    prev_tables: Path,
    prev_structure: Path,
    work: Path,
    sources: Sources,
    workers: int = 1,
    log: Callable[[str], None] = print,
    timer: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """One update; returns (and writes to ``work/summary.json``) its counts."""
    import time

    clock = timer or time.monotonic
    start = clock()
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    prev_summary = json.loads(
        (Path(prev_tables) / "build_summary.json").read_text(encoding="utf-8")
    )
    prev_export = prev_summary["export_date"]
    prev_release = (prev_summary.get("structure") or {}).get("release_date") or prev_export
    # The day the last build's structure was read through (its full release, or the last day its
    # update files covered), and the full release it started from.
    prev_full = (prev_summary.get("dailymed") or {}).get("full_release") or prev_release
    listing = sources.listing()
    new_export, _ = bulk.label_parts(listing)
    summary: dict[str, Any] = {"previous_export": prev_export, "listed_export": new_export}
    if new_export <= prev_export:
        summary["status"] = "no_new_export"
        (work / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
        return summary
    choice = sources.dailymed_choice(prev_release, new_export)
    summary["dailymed_coverage"] = choice.coverage
    if choice.coverage["weekdays_missing"]:
        # Checked before any download: no update file is listed any more for these weekdays,
        # so their new label versions could not be read and would fall to `unlisted` silently.
        summary["status"] = "stopped"
        summary["stopped_because"] = "dailymed_update_files_missing"
        (work / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
        return summary
    parts = sources.label_parts(listing)
    ndc, dm = sources.listings(listing)
    updates = sources.dailymed_download(choice)
    summary["dailymed_update_files"] = len(updates)
    listings = listed.load(ndc, dm)
    rules = {}
    pairs_prev = pq.read_table(
        Path(prev_tables) / "section_pairs.parquet", columns=["heading_key", "rule_status"]
    )
    for k, s in zip(
        pairs_prev["heading_key"].to_pylist(), pairs_prev["rule_status"].to_pylist(), strict=True
    ):
        if s and s != "pending_hand_check":
            rules[k] = s
    first = work / "pass1"
    tables.Builder(
        parts, first, new_export, log=lambda s: None, workers=workers, listings=listings
    ).run()
    labels_new = pq.read_table(first / "labels.parquet", columns=["set_id", "version"]).to_pylist()
    fresh = work / "structure-new"
    if updates:
        structure.build(updates, new_export, first, fresh, workers=1, log=lambda s: None)
    merged = work / "structure"
    # Read through the last day the chosen files cover (never the export day itself when it has no
    # file yet): the next update starts after that day, so a file DailyMed posts later is read.
    through = min(max((d for f in choice.files for d in f.days), default=prev_release), new_export)
    through = max(through, prev_release)
    summary["dailymed_full_release"] = prev_full
    summary["dailymed_updates_through"] = through
    summary.update(_carry_structure(Path(prev_structure), fresh, labels_new, merged, through))
    final = work / "tables"
    tables.Builder(
        parts, final, new_export, log=lambda s: None, workers=workers, listings=listings,
        structure_dir=merged, rule_status=rules,
    ).run()  # fmt: skip
    nci_sha: dict[str, str] = {}
    for name in ("nci_summaries", "nci_pairs", "nci_text"):
        if (Path(prev_tables) / f"{name}.parquet").exists():
            shutil.copyfile(Path(prev_tables) / f"{name}.parquet", final / f"{name}.parquet")
            nci_sha[name] = durable.sha256_file(final / f"{name}.parquet")
    summary["nci_sha256_carried"] = nci_sha
    ch = changes.write(Path(prev_tables), final, work / "changes.parquet")
    summary["changes"] = ch.get("changes", {})
    summary["labels_changed"] = ch.get("rows", 0)
    old = dict(
        (r["set_id"], r["configuration"])
        for r in pq.read_table(
            Path(prev_tables) / "labels.parquet", columns=["set_id", "configuration"]
        ).to_pylist()
    )
    moved: Counter[str] = Counter()
    new_conf = pq.read_table(
        final / "labels.parquet", columns=["set_id", "configuration"]
    ).to_pylist()
    for r in new_conf:
        before = old.get(r["set_id"])
        if before and before != r["configuration"]:
            moved[f"{before}_to_{r['configuration']}"] += 1
    summary["moved"] = dict(moved)
    summary["configurations"] = dict(Counter(r["configuration"] for r in new_conf))
    built = json.loads((final / "build_summary.json").read_text(encoding="utf-8"))
    built["dailymed"] = {
        "full_release": prev_full,
        "updates_through": through,
        "update_files": [f.name for f in choice.files],
    }
    (final / "build_summary.json").write_text(json.dumps(built, indent=1), encoding="utf-8")
    codes.build(
        final, workers=workers, log=lambda s: None, structure_path=merged / "structure.parquet"
    )
    manifest = bulk.read_manifest(Path(parts[0][1]).parent / "manifest.csv")
    problems, _info = release.check(final, manifest, "unmarked", verify_hashes=False)
    summary["release_check_problems"] = len(problems)
    summary["release_check"] = "passed" if not problems else "failed"
    summary["status"] = "ready" if not problems else "stopped"
    summary["new_export"] = new_export
    summary["seconds"] = round(clock() - start, 1)
    summary["finished"] = datetime.now().astimezone().isoformat(timespec="seconds")
    (work / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    if problems:
        (work / "release_check_problems.txt").write_text("\n".join(problems), encoding="utf-8")
    return summary
