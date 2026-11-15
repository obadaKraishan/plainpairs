"""The weekly update: from the last build (or the last published pack) to the newest export.

``plainpairs update`` does, in order:

1. reads openFDA's ``download.json``; if it lists no export newer than the last build's, it
   stops with ``status = no_new_export`` (nothing is downloaded);
2. downloads the new export's label parts, the NDC directory and DailyMed's label list
   (:mod:`plainpairs.bulk`, :mod:`plainpairs.listed`), and DailyMed's daily update files for the
   days after the last DailyMed release up to the new export date (one file a day, checked
   against the page's MD5);
3. builds the tables once without structure, then carries the structure of every label whose
   set id and version did not change forward from the last build, and reads the new versions
   from the update files (:mod:`plainpairs.structure`);
4. builds again with the structure (the two configurations) and the hand sheet's rule status
   carried from the last build; copies the NCI tables (read on their own three-month schedule);
5. writes the ``changes`` table against the last build, counts the labels that moved between
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
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import pyarrow as pa
import pyarrow.parquet as pq

from plainpairs import bulk, changes, codes, listed, pages, release, spl_release, structure, tables

_DAILY = re.compile(
    r"(dm_spl_daily_update_(\d{2})(\d{2})(\d{4})\.zip)\s*\[\s*HTTPS\s*/\s*FTP\s*\]\s*"
    r"Number of labels:\s*([\d,]+)\s*File size:\s*([\d.]+)\s*(GB|MB|KB)\s*"
    r"MD5 checksum:\s*([0-9a-fA-F]{32})"
)


@dataclass(frozen=True)
class UpdateFile:
    name: str
    url: str
    day: str  # ISO date the file covers
    labels: int
    size_text: str
    md5: str

    @property
    def size_bytes_upper(self) -> int:
        value, unit = re.fullmatch(r"([\d.]+)(GB|MB|KB)", self.size_text).groups()  # type: ignore[union-attr]
        return int(float(value) * {"KB": 2**10, "MB": 2**20, "GB": 2**30}[unit])


def daily_updates(markup: str) -> list[UpdateFile]:
    """The daily update files DailyMed's download page lists, oldest first."""
    plain = pages.html_to_text(markup)
    out = {}
    for m in _DAILY.finditer(plain):
        name, mm, dd, yyyy, n, size, unit, md5 = m.groups()
        url = spl_release.FILE_HOST + name
        if f'href="{url}"' not in markup:
            continue
        out[name] = UpdateFile(
            name, url, f"{yyyy}-{mm}-{dd}", int(n.replace(",", "")), size + unit, md5.lower()
        )
    return sorted(out.values(), key=lambda u: u.day)


def choose(files: list[UpdateFile], after: str, until: str) -> list[UpdateFile]:
    """The daily files for the days after ``after`` up to ``until`` (ISO dates)."""
    return [f for f in files if after < f.day <= until]


class Sources(Protocol):
    def listing(self) -> dict[str, Any]: ...

    def label_parts(self, listing: dict[str, Any]) -> list[tuple[int, Path]]: ...

    def listings(self, listing: dict[str, Any]) -> tuple[Path, Path]: ...

    def dailymed_updates(self, after: str, until: str) -> list[Path]: ...


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

    def dailymed_updates(self, after: str, until: str) -> list[Path]:
        saved = pages.fetch_page(self.client, spl_release.PAGE_URL, self.pages_root, self.day)
        files = choose(
            daily_updates(saved.path.read_text(encoding="utf-8", errors="replace")), after, until
        )
        out = []
        for f in files:
            dest = Path(self.updates_root) / f.day / f.name
            if not dest.exists():
                self.log(f"DailyMed daily update {f.day}: {f.name} ({f.size_text})")
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
    (tdir / "build_summary.json").write_text(
        json.dumps(
            {
                "export_date": manifest["sources"]["openfda_label_export"],
                "structure": {"release_date": manifest["sources"].get("dailymed_release")},
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
    listing = sources.listing()
    new_export, _ = bulk.label_parts(listing)
    summary: dict[str, Any] = {"previous_export": prev_export, "listed_export": new_export}
    if new_export <= prev_export:
        summary["status"] = "no_new_export"
        (work / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
        return summary
    parts = sources.label_parts(listing)
    ndc, dm = sources.listings(listing)
    updates = sources.dailymed_updates(prev_release, new_export)
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
    summary.update(_carry_structure(Path(prev_structure), fresh, labels_new, merged, new_export))
    final = work / "tables"
    tables.Builder(
        parts, final, new_export, log=lambda s: None, workers=workers, listings=listings,
        structure_dir=merged, rule_status=rules,
    ).run()  # fmt: skip
    for name in ("nci_summaries", "nci_pairs", "nci_text"):
        if (Path(prev_tables) / f"{name}.parquet").exists():
            shutil.copyfile(Path(prev_tables) / f"{name}.parquet", final / f"{name}.parquet")
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
