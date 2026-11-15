"""The NCI cancer information summaries: the list of pages, and reading each page once.

The National Cancer Institute publishes its cancer information summaries on cancer.gov, each in
a version for health professionals and a version for patients, in English and Spanish. The
site's own sitemap (``https://www.cancer.gov/sitemaps/pageinstructions.xml``) lists every
summary page: their addresses end in ``-pdq``. :func:`summary_urls` reads them from a saved copy
of the sitemap and guesses each page's language and version from its address (the page itself
is the authority; see :mod:`plainpairs.nci`).

:func:`fetch_summaries` reads each page once through the polite client (at least 5 seconds
between requests unless told otherwise), saves it raw under ``data/raw/nci/<day>/`` with a line
in that folder's manifest, and skips every address the manifest already has, whatever its
status, so that no page is fetched twice. Only HTML pages are read: an address that ends in an
image, PDF or script extension is refused before any request.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from plainpairs import pages
from plainpairs.client import PoliteClient, SourceBlocked

HOST = "www.cancer.gov"
SITEMAP = "https://www.cancer.gov/sitemaps/pageinstructions.xml"
#: The seconds between two requests to cancer.gov.
MIN_INTERVAL = 5.0
_NOT_HTML = re.compile(r"\.(?:jpe?g|png|gif|svg|webp|pdf|js|css|zip|mp4|mp3)$", re.I)
#: Pages under these paths end in "-pdq" but describe the summaries, not one summary.
_NOT_A_SUMMARY = ("/publicaciones/pdq/proceso-editorial/",)


@dataclass(frozen=True)
class SummaryUrl:
    url: str
    language: str  # "en" or "es"
    #: From the address: "health_professional" or "patient" (checked against the page later).
    version_guess: str


def guess(url: str) -> SummaryUrl:
    """Language and version of a summary page from its address alone."""
    path = urlsplit(url).path
    language = "es" if path.startswith("/espanol/") else "en"
    parts = path.strip("/").split("/")
    last = parts[-1]
    if language == "en":
        hp = "hp" in parts[:-1] or last.endswith("-hp-pdq")
    else:
        hp = "pro" in parts[:-1] or last.endswith("-pro-pdq")
    return SummaryUrl(url, language, "health_professional" if hp else "patient")


def summary_urls(sitemap_xml: str) -> list[SummaryUrl]:
    """Every summary page the sitemap lists, once each, in sitemap order."""
    seen: set[str] = set()
    out = []
    for url in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sitemap_xml):
        parts = urlsplit(url)
        if parts.netloc != HOST or not parts.path.endswith("-pdq") or url in seen:
            continue
        if any(p in parts.path for p in _NOT_A_SUMMARY):
            continue
        seen.add(url)
        out.append(guess(url))
    return out


def fetched(root: Path) -> dict[str, str]:
    """Address -> status of every page already in ``root``'s manifest (any status)."""
    manifest = Path(root) / "manifest.csv"
    if not manifest.exists():
        return {}
    with manifest.open(newline="", encoding="utf-8") as fh:
        return {row["url"]: row["status"] for row in csv.DictReader(fh)}


def fetch_summaries(
    client: PoliteClient,
    urls: list[SummaryUrl],
    root: Path,
    day: str,
    log: Callable[[str], None] = print,
) -> dict[str, int]:
    """Read each page not yet fetched, once, in order. Returns counts by status.

    A 403 stops the run (the host has blocked the client); 429 and 5xx are retried by the
    client with backoff. The caps of ``client.budget`` stop the run when reached.
    """
    done = fetched(root)
    counts: dict[str, int] = {}
    for i, s in enumerate(urls, 1):
        if s.url in done:
            counts["skipped_already_fetched"] = counts.get("skipped_already_fetched", 0) + 1
            continue
        if urlsplit(s.url).netloc != HOST or _NOT_HTML.search(urlsplit(s.url).path):
            raise ValueError(f"{s.url} is not an HTML page on {HOST}; it is not read.")
        try:
            saved = pages.fetch_page(client, s.url, root, day)
        except SourceBlocked:
            log(f"{s.url}: the host refused (403) or kept failing; stopping here.")
            raise
        key = str(saved.status)
        counts[key] = counts.get(key, 0) + 1
        if saved.status != 200:
            log(f"{i:4}/{len(urls)} HTTP {saved.status} {s.url}")
        elif i % 50 == 0:
            log(
                f"{i:4}/{len(urls)} read; {client.budget.calls} calls, "
                f"{client.budget.nbytes:,} bytes this session"
            )
    return counts
