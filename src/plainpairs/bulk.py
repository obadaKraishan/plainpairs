"""The bulk files of the label dataset: the list of parts, one part's download, and a reader.

``download.json`` lists every bulk file openFDA serves. For drug labels it gives, per part, the
file URL, its size in MB and its number of records. A part is a zip archive that holds one JSON
file shaped like an API answer: ``{"meta": {...}, "results": [label, label, ...]}``.

Downloaded archives are untrusted. :func:`iter_labels` never unpacks anything to disk: it
checks the archive's single member (its name and its unpacked size) and reads the labels one at
a time from a stream, so a part of several hundred MB never sits in memory whole.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from plainpairs.client import PoliteClient

DOWNLOAD_JSON = "https://api.fda.gov/download.json"
#: No part may unpack to more than this (the largest known part unpacks to well under it).
MAX_UNPACKED = 3_000_000_000
_RESULTS_START = re.compile(r'"results"\s*:\s*\[')
_SKIP = re.compile(r"[\s,]*")


class BulkError(ValueError):
    """A bulk file is not shaped as expected."""


@dataclass(frozen=True)
class Part:
    number: int
    of: int
    url: str
    size_mb: float
    records: int

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[1]


def label_parts(download_json: dict[str, Any]) -> tuple[str, list[Part]]:
    """The export date and the drug label parts listed in ``download.json``."""
    try:
        label = download_json["results"]["drug"]["label"]
    except KeyError as exc:
        raise BulkError("download.json has no results.drug.label entry.") from exc
    parts = []
    for p in label["partitions"]:
        m = re.search(r"part (\d+) of (\d+)", p.get("display_name", ""))
        if not m:
            raise BulkError(f"Cannot read the part number from {p.get('display_name')!r}.")
        parts.append(
            Part(
                int(m.group(1)),
                int(m.group(2)),
                p["file"],
                float(p.get("size_mb") or 0),
                int(p.get("records") or 0),
            )
        )
    return label.get("export_date", ""), sorted(parts, key=lambda q: q.number)


def smallest(parts: list[Part]) -> Part:
    return min(parts, key=lambda p: (p.size_mb, p.number))


def fetch_part(
    client: PoliteClient, part: Part, root: Path, export_date: str, max_mb: float
) -> Path:
    """Download one part to ``<root>/<export date>/<file name>`` (written once, checked)."""
    if part.size_mb > max_mb:
        raise BulkError(
            f"{part.filename} is listed at {part.size_mb} MB, over the limit of {max_mb} MB. "
            "A larger download needs the maintainer's approval."
        )
    dest = root / export_date / part.filename
    client.download(part.url, dest, max_bytes=int(max_mb * 1_000_000))
    return dest


def _member(archive: zipfile.ZipFile) -> zipfile.ZipInfo:
    members = [m for m in archive.infolist() if not m.is_dir()]
    if len(members) != 1:
        raise BulkError(f"Expected one file in the archive, found {len(members)}.")
    m = members[0]
    if "/" in m.filename or "\\" in m.filename or not m.filename.endswith(".json"):
        raise BulkError(f"Unexpected file name in the archive: {m.filename!r}.")
    if m.file_size > MAX_UNPACKED:
        raise BulkError(f"{m.filename} unpacks to {m.file_size:,} bytes, over {MAX_UNPACKED:,}.")
    return m


def iter_results(fh: IO[str], chunk_size: int = 1 << 20) -> Iterator[dict[str, Any]]:
    """Yield the objects of the top-level ``results`` array of a JSON text stream, one by one."""
    decoder = json.JSONDecoder()
    buf = ""
    while True:
        m = _RESULTS_START.search(buf)
        if m:
            buf = buf[m.end() :]
            break
        more = fh.read(chunk_size)
        if not more:
            raise BulkError("No results array in the file.")
        buf = buf[-64:] + more
    pos = 0
    while True:
        pos = _SKIP.match(buf, pos).end()  # type: ignore[union-attr]
        if pos >= len(buf):
            more = fh.read(chunk_size)
            if not more:
                raise BulkError("The file ends inside the results array.")
            buf, pos = more, 0
            continue
        if buf[pos] == "]":
            return
        try:
            obj, end = decoder.raw_decode(buf, pos)
        except json.JSONDecodeError:
            more = fh.read(chunk_size)
            if not more:
                raise BulkError("The file ends inside a label record.") from None
            buf, pos = buf[pos:] + more, 0
            continue
        if not isinstance(obj, dict):
            raise BulkError("A results entry is not a JSON object.")
        yield obj
        pos = end
        if pos > chunk_size:
            buf, pos = buf[pos:], 0


def iter_labels(zip_path: Path | str) -> Iterator[dict[str, Any]]:
    """Read the labels of one downloaded part, without unpacking it to disk."""
    with zipfile.ZipFile(zip_path) as archive:
        member = _member(archive)
        with archive.open(member) as raw:
            yield from iter_results(io.TextIOWrapper(raw, encoding="utf-8"))


def read_meta(zip_path: Path | str, limit: int = 1 << 16) -> dict[str, Any]:
    """The ``meta`` block at the head of a part (read from its first bytes)."""
    with zipfile.ZipFile(zip_path) as archive, archive.open(_member(archive)) as raw:
        head = io.TextIOWrapper(raw, encoding="utf-8").read(limit)
    m = re.search(r'"meta"\s*:\s*', head)
    if not m:
        return {}
    meta, _ = json.JSONDecoder().raw_decode(head, m.end())
    return meta if isinstance(meta, dict) else {}
