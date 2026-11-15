"""DailyMed's full release of human prescription labels: the part list, the download and a reader.

DailyMed's page "SPL Resources: Download All Drug Labels" lists the full release in parts
(``dm_spl_release_human_rx_part<N>.zip``), each with its number of files, its size, its MD5
checksum and the day it was last modified. :func:`parse_parts` reads that list from the saved
page; :func:`fetch_parts` downloads the parts one at a time, resumably, checks each against the
page's MD5 and records it in a manifest. The parts are read where they lie, never unpacked to
disk: :func:`iter_documents` walks a part (a zip of zips, one inner zip per label) and yields
each label's XML from memory, and only the XML member of an inner zip is ever opened. Images
and other files inside are counted by type and never read.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from plainpairs import durable, pages
from plainpairs.client import PoliteClient

PAGE_URL = "https://dailymed.nlm.nih.gov/dailymed/spl-resources-all-drug-labels.cfm"
FILE_HOST = "https://dailymed-data.nlm.nih.gov/public-release-files/"
#: The largest total this module downloads (the prompt's stop line).
MAX_TOTAL_BYTES = 20_000_000_000
MANIFEST_FIELDS = [
    "release_date",
    "part",
    "file",
    "url",
    "listed_files",
    "listed_size",
    "listed_md5",
    "bytes",
    "md5",
    "sha256",
    "retries",
    "started",
    "finished",
]
#: An inner zip (one label) larger than this is refused unread (an untrusted archive).
MAX_INNER_BYTES = 400_000_000
#: An XML member larger than this is refused unread.
MAX_XML_BYTES = 60_000_000

_PART = re.compile(
    r"(dm_spl_release_human_rx_part(\d+)\.zip)\s*\[\s*HTTPS\s*/\s*FTP\s*\]\s*"
    r"Number of files:\s*([\d,]+)\s*File size:\s*([\d.]+)\s*(GB|MB|KB)\s*"
    r"MD5 checksum:\s*([0-9a-fA-F]{32})\s*Last Modified:\s*([A-Z][a-z]{2} \d{1,2}, \d{4})"
)
_UNIT = {"KB": 2**10, "MB": 2**20, "GB": 2**30}


class ReleaseError(RuntimeError):
    """The page, a part or the manifest is not as expected. Stop and look."""


@dataclass(frozen=True)
class ReleasePart:
    number: int
    filename: str
    url: str
    files: int
    size_text: str
    md5: str
    last_modified: str  # ISO date

    @property
    def size_bytes_upper(self) -> int:
        """The listed size read as binary units, the larger reading (for limits and stops)."""
        value, unit = re.fullmatch(r"([\d.]+)(GB|MB|KB)", self.size_text).groups()  # type: ignore[union-attr]
        return int(float(value) * _UNIT[unit])


def parse_parts(markup: str) -> list[ReleasePart]:
    """The human prescription parts listed on the download page, in part order.

    Each file name must also appear as a link on DailyMed's file host; a part listed without
    one is an error, since its URL would be a guess.
    """
    plain = pages.html_to_text(markup)
    found: dict[int, ReleasePart] = {}
    for m in _PART.finditer(plain):
        name, number, files, size, unit, md5, modified = m.groups()
        url = FILE_HOST + name
        if f'href="{url}"' not in markup:
            raise ReleaseError(f"The page lists {name} but links it nowhere on {FILE_HOST}.")
        day = datetime.strptime(modified, "%b %d, %Y").strftime("%Y-%m-%d")
        found[int(number)] = ReleasePart(
            int(number), name, url, int(files.replace(",", "")), size + unit, md5.lower(), day
        )
    if not found:
        raise ReleaseError("No human prescription parts found on the page; read it by hand.")
    numbers = sorted(found)
    if numbers != list(range(1, len(numbers) + 1)):
        raise ReleaseError(f"The parts listed are {numbers}, not 1 to {len(numbers)}.")
    return [found[n] for n in numbers]


def release_date(parts: list[ReleasePart]) -> str:
    """The one "last modified" day every part shares; parts from two days are an error."""
    days = {p.last_modified for p in parts}
    if len(days) != 1:
        raise ReleaseError(
            f"The parts were modified on different days ({sorted(days)}): the release is being "
            "replaced. Wait for one day's set."
        )
    return days.pop()


def check_total(parts: list[ReleasePart], limit: int = MAX_TOTAL_BYTES) -> int:
    """The listed total in bytes (binary reading); over ``limit`` stops before any download."""
    total = sum(p.size_bytes_upper for p in parts)
    if total > limit:
        raise ReleaseError(
            f"The parts are listed at {total:,} bytes in all, over the stop line of {limit:,}."
        )
    return total


def manifest_path(root: Path, day: str) -> Path:
    return Path(root) / day / "manifest.csv"


def read_manifest(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        return {row["file"]: row for row in csv.DictReader(fh)}


def _append(path: Path, row: dict[str, Any]) -> None:
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
        durable.flush_file(fh)


def fetch_parts(
    client: PoliteClient,
    parts: list[ReleasePart],
    root: Path,
    clock: Callable[[], str],
    log: Callable[[str], None] = print,
) -> list[dict[str, str]]:
    """Make sure every part is on disk, whole and matching the page's MD5 (resumable).

    A part already in the manifest is checked by size and kept (its hashes were checked when
    it was written). A part not yet in the manifest is downloaded, one at a time, resuming a
    partial file if one is there. Returns the manifest rows in part order.
    """
    day = release_date(parts)
    check_total(parts)
    mpath = manifest_path(root, day)
    for part in parts:
        manifest = read_manifest(mpath)
        dest = Path(root) / day / part.filename
        if part.filename in manifest:
            row = manifest[part.filename]
            if not dest.exists() or dest.stat().st_size != int(row["bytes"]):
                raise ReleaseError(f"{dest} does not match its manifest line; stop and look.")
            log(f"part {part.number}: on disk and in the manifest ({int(row['bytes']):,} bytes)")
            continue
        if dest.exists():
            raise ReleaseError(f"{dest} is on disk but not in the manifest; stop and look.")
        log(f"part {part.number}: downloading {part.filename} (listed {part.size_text})")
        started = clock()
        md5, sha, size, retries = client.download_resumable(
            part.url,
            dest,
            max_bytes=int(part.size_bytes_upper * 1.01),
            expected_md5=part.md5,
            progress=log,
        )
        _append(
            mpath,
            {
                "release_date": day,
                "part": part.number,
                "file": part.filename,
                "url": part.url,
                "listed_files": part.files,
                "listed_size": part.size_text,
                "listed_md5": part.md5,
                "bytes": size,
                "md5": md5,
                "sha256": sha,
                "retries": retries,
                "started": started,
                "finished": clock(),
            },
        )
        log(
            f"part {part.number}: {size:,} bytes, MD5 as listed, SHA-256 {sha[:12]}, "
            f"{retries} retries"
        )
    manifest = read_manifest(mpath)
    return [manifest[p.filename] for p in parts]


# --- reading -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Document:
    """One label of a part: where it is, and its XML (read into memory, never to disk)."""

    part: str
    member: str
    xml_name: str
    xml: bytes


def _kind(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name.rsplit("/", 1)[-1] else "(none)"
    return ext


def iter_documents(part_path: Path | str, counts: Counter[str] | None = None) -> Iterator[Document]:
    """Each label's XML in one part, read from the inner zips in memory.

    ``counts`` (if given) collects what the part holds: inner zips, XML files, and every other
    member by its file type (``other:jpg`` and so on). Those other members are never opened.
    An inner zip or XML member over its size limit, or an inner zip that is not a zip, is
    counted and skipped.
    """
    c = counts if counts is not None else Counter()
    name = Path(part_path).name
    with zipfile.ZipFile(part_path) as outer:
        for info in outer.infolist():
            if info.is_dir():
                continue
            if not info.filename.lower().endswith(".zip"):
                c[f"outer_other:{_kind(info.filename)}"] += 1
                continue
            if info.file_size > MAX_INNER_BYTES:
                c["inner_too_large"] += 1
                continue
            c["inner_zips"] += 1
            with outer.open(info) as fh:
                data = fh.read()
            try:
                inner = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                c["inner_not_zip"] += 1
                continue
            with inner:
                xmls = []
                for m in inner.infolist():
                    if m.is_dir():
                        continue
                    if m.filename.lower().endswith(".xml"):
                        xmls.append(m)
                    else:
                        c[f"other:{_kind(m.filename)}"] += 1
                        c["other_bytes"] += m.file_size
                c[f"xml_per_inner:{len(xmls)}"] += 1
                for m in xmls:
                    if m.file_size > MAX_XML_BYTES:
                        c["xml_too_large"] += 1
                        continue
                    c["xml_files"] += 1
                    yield Document(name, info.filename, m.filename, inner.read(m))
