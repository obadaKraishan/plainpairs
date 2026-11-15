"""Whether a label's product is listed now: two small official lists, joined by set id.

- **The NDC directory** (openFDA's ``drug/ndc`` bulk file): products currently listed with FDA.
  A label counts as listed when its set id is the ``openfda.spl_set_id`` of a directory entry,
  or, failing that, when its document id is an entry's ``spl_id``.
- **DailyMed's zip file metadata** (``dm_spl_zip_files_meta_data.zip``, pipe-delimited
  ``SETID|ZIP_FILE_NAME|UPLOAD_DATE|SPL_VERSION|TITLE``): one row per label DailyMed serves, with
  its current version. Only the set id and the version are read; the title is never kept.

Both files are read straight from their archives, never unpacked to disk. The flags say only
whether a source lists the label on the day its file was made; they say nothing about a
medicine.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plainpairs import bulk, durable
from plainpairs.client import PoliteClient

NDC_ENDPOINT = ("drug", "ndc")
DAILYMED_METADATA_URL = (
    "https://dailymed-data.nlm.nih.gov/public-release-files/dm_spl_zip_files_meta_data.zip"
)
DAILYMED_COLUMNS = ("SETID", "ZIP_FILE_NAME", "UPLOAD_DATE", "SPL_VERSION", "TITLE")
#: The largest listing file this module downloads without the maintainer's approval.
MAX_MB = 300.0
MANIFEST_FIELDS = ["source", "date", "file", "url", "listed_mib", "bytes", "sha256", "md5"]
#: Members of a listing archive larger than this are refused (an untrusted archive).
MAX_MEMBER_BYTES = 2_000_000_000


class ListedError(RuntimeError):
    """A listing file is missing, too large or not in the expected shape."""


@dataclass(frozen=True)
class NdcFile:
    url: str
    size_mb: float
    records: int
    export_date: str

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def ndc_files(download_json: dict[str, Any]) -> list[NdcFile]:
    """The NDC directory's bulk files as ``download.json`` lists them (sizes in MiB)."""
    try:
        entry = download_json["results"][NDC_ENDPOINT[0]][NDC_ENDPOINT[1]]
        export_date = str(entry["export_date"])
        return [
            NdcFile(p["file"], float(p["size_mb"]), int(p.get("records") or 0), export_date)
            for p in entry["partitions"]
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ListedError(
            "download.json has no drug/ndc entry with partitions; read the listing again."
        ) from exc


# --- reading ----------------------------------------------------------------------------------


@dataclass
class Listings:
    """The set ids each list names, with what was read (for the build summary)."""

    ndc_set_ids: frozenset[str] = frozenset()
    ndc_spl_ids: frozenset[str] = frozenset()
    dailymed_versions: dict[str, int] = field(default_factory=dict)
    sources: dict[str, Any] = field(default_factory=dict)

    @property
    def has_ndc(self) -> bool:
        return "ndc" in self.sources

    @property
    def has_dailymed(self) -> bool:
        return "dailymed" in self.sources


def read_ndc(path: Path | str) -> tuple[frozenset[str], frozenset[str], dict[str, int]]:
    """(set ids, SPL document ids, counts) of the NDC directory file at ``path``."""
    set_ids: set[str] = set()
    spl_ids: set[str] = set()
    c: Counter[str] = Counter()
    for rec in bulk.iter_labels(path):
        c["records"] += 1
        of = rec.get("openfda") or {}
        found = [s for s in of.get("spl_set_id") or [] if isinstance(s, str)]
        set_ids.update(found)
        c["with_spl_set_id"] += bool(found)
        if isinstance(rec.get("spl_id"), str):
            spl_ids.add(rec["spl_id"])
            c["with_spl_id"] += 1
        c[f"finished:{rec.get('finished')}"] += 1
    c["distinct_set_ids"] = len(set_ids)
    c["distinct_spl_ids"] = len(spl_ids)
    return frozenset(set_ids), frozenset(spl_ids), dict(c)


def _version(raw: str) -> int | None:
    raw = (raw or "").strip()
    return int(raw) if raw.isdigit() else None


def read_dailymed_rows(lines: Iterable[str]) -> tuple[dict[str, int], dict[str, int]]:
    """Set id -> current version from the metadata's pipe-delimited lines, and counts."""
    reader = csv.reader(lines, delimiter="|", quoting=csv.QUOTE_NONE)
    header = next(reader, None)
    if header is None or [h.strip().upper() for h in header[:4]] != list(DAILYMED_COLUMNS[:4]):
        raise ListedError(
            "The DailyMed metadata does not start with SETID|ZIP_FILE_NAME|UPLOAD_DATE|"
            "SPL_VERSION; check the file against the mapping-files page."
        )
    versions: dict[str, int] = {}
    c: Counter[str] = Counter()
    for row in reader:
        if not row or not row[0].strip():
            continue
        c["rows"] += 1
        set_id = row[0].strip().lower()
        version = _version(row[3]) if len(row) > 3 else None
        if version is None:
            c["rows_without_version"] += 1
            versions.setdefault(set_id, 0)
            continue
        versions[set_id] = max(version, versions.get(set_id, 0))
    c["distinct_set_ids"] = len(versions)
    return versions, dict(c)


def read_dailymed(path: Path | str) -> tuple[dict[str, int], dict[str, int]]:
    """Set id -> version from every metadata member of the archive at ``path``."""
    versions: dict[str, int] = {}
    counts: Counter[str] = Counter()
    with zipfile.ZipFile(path) as archive:
        members = [m for m in archive.infolist() if not m.is_dir()]
        for m in members:
            if m.file_size > MAX_MEMBER_BYTES:
                raise ListedError(f"{m.filename} in {path} is too large to read.")
            with archive.open(m) as raw:
                head = raw.read(64).decode("utf-8", "replace").upper()
            if not head.startswith("SETID|"):
                counts["members_skipped"] += 1
                continue
            with archive.open(m) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
                found, c = read_dailymed_rows(text)
            counts["members_read"] += 1
            counts.update(c)
            for k, v in found.items():
                versions[k] = max(v, versions.get(k, 0))
    counts["distinct_set_ids"] = len(versions)
    return versions, dict(counts)


def load(ndc: Path | None, dailymed: Path | None) -> Listings:
    """The listings from the files given; a missing argument leaves its flags empty (null)."""
    out = Listings()
    if ndc is not None:
        set_ids, spl_ids, counts = read_ndc(ndc)
        out.ndc_set_ids, out.ndc_spl_ids = set_ids, spl_ids
        out.sources["ndc"] = {
            "file": Path(ndc).name,
            "date": Path(ndc).parent.name,
            "sha256": durable.sha256_file(ndc),
            "counts": counts,
        }
    if dailymed is not None:
        versions, counts = read_dailymed(dailymed)
        out.dailymed_versions = versions
        out.sources["dailymed"] = {
            "file": Path(dailymed).name,
            "date": Path(dailymed).parent.name,
            "sha256": durable.sha256_file(dailymed),
            "counts": counts,
        }
    return out


#: The columns this module adds to ``labels``.
FLAG_COLUMNS = (
    "listed_in_ndc_directory",
    "ndc_match",
    "served_by_dailymed",
    "dailymed_version",
)


def flags(listings: Listings, set_id: str, doc_id: str | None, version: int | None) -> dict:
    """The listed-now columns of one label (``None`` where a list was not given)."""
    out: dict[str, Any] = dict.fromkeys(FLAG_COLUMNS)
    if listings.has_ndc:
        if set_id in listings.ndc_set_ids:
            out["ndc_match"] = "set_id"
        elif doc_id and doc_id in listings.ndc_spl_ids:
            out["ndc_match"] = "spl_id"
        else:
            out["ndc_match"] = "none"
        out["listed_in_ndc_directory"] = out["ndc_match"] != "none"
    if listings.has_dailymed:
        served = listings.dailymed_versions.get(set_id.lower())
        out["served_by_dailymed"] = served is not None
        out["dailymed_version"] = served or None
    return out


# --- downloading ------------------------------------------------------------------------------


def manifest_path(root: Path) -> Path:
    return Path(root) / "manifest.csv"


def _append_manifest(root: Path, row: dict[str, Any]) -> None:
    path = manifest_path(root)
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
        durable.flush_file(fh)


def _md5(path: Path) -> str:
    import hashlib

    h = hashlib.md5(usedforsecurity=False)
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_ndc(
    client: PoliteClient, download_json: dict[str, Any], root: Path, max_mb: float = MAX_MB
) -> list[Path]:
    """Download the NDC directory's file(s) to ``<root>/ndc/<export date>/`` (once each)."""
    out = []
    for f in ndc_files(download_json):
        if f.size_mb > max_mb:
            raise ListedError(
                f"{f.filename} is listed at {f.size_mb} MiB, over the limit of {max_mb} MiB. "
                "Stop and ask the maintainer."
            )
        dest = Path(root) / "ndc" / f.export_date / f.filename
        if not dest.exists():
            digest, size = client.download(f.url, dest, max_bytes=int(max_mb * 1_048_576))
            _append_manifest(
                root,
                {
                    "source": "ndc",
                    "date": f.export_date,
                    "file": f.filename,
                    "url": f.url,
                    "listed_mib": f.size_mb,
                    "bytes": size,
                    "sha256": digest,
                    "md5": _md5(dest),
                },
            )
        out.append(dest)
    return out


def fetch_dailymed(
    client: PoliteClient, root: Path, day: str, max_mb: float = MAX_MB, url: str = ""
) -> Path:
    """Download DailyMed's zip file metadata to ``<root>/dailymed/<day>/`` (once)."""
    url = url or DAILYMED_METADATA_URL
    dest = Path(root) / "dailymed" / day / url.rsplit("/", 1)[-1]
    if not dest.exists():
        digest, size = client.download(url, dest, max_bytes=int(max_mb * 1_048_576))
        _append_manifest(
            root,
            {
                "source": "dailymed",
                "date": day,
                "file": dest.name,
                "url": url,
                "listed_mib": "",
                "bytes": size,
                "sha256": digest,
                "md5": _md5(dest),
            },
        )
    return dest


def latest(root: Path, source: str) -> Path | None:
    """The newest downloaded file of ``source`` (``ndc`` or ``dailymed``) under ``root``."""
    folder = Path(root) / source
    if not folder.exists():
        return None
    files = sorted(p for p in folder.glob("*/*.zip") if p.is_file())
    return files[-1] if files else None
