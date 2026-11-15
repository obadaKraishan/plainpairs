"""Source pages kept as evidence, and the quotes taken from them.

A terms page, a license page or a documentation page is fetched once through the polite
client and saved raw (write once, flushed, checked) under ``data/raw/pages/<date>/<host>/``,
with one line per page in ``data/raw/pages/manifest.csv``. Every quote in ``docs/sources.md``
is listed in the tracked ``docs/quotes.csv`` with the page it comes from, and
:func:`check_quotes` confirms each one word for word on the saved page, after the page has been
reduced to plain text and its spaces normalized.
"""

from __future__ import annotations

import csv
import html
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from plainpairs import durable
from plainpairs.client import PoliteClient

MANIFEST_FIELDS = ["time", "url", "status", "path", "bytes", "sha256"]

_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}
_SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip = max(self._skip - 1, 0)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(re.sub(r"\s+", " ", data))


def html_to_text(markup: str) -> str:
    """Plain text of an HTML page: scripts and styles dropped, one line per block."""
    parser = _TextParser()
    parser.feed(markup)
    parser.close()
    text = html.unescape("".join(parser.parts))
    lines = (re.sub(r"[ \t\r\f\v\u00a0]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def normalize(text: str) -> str:
    """Text for comparing quotes: NFKC, straight quotes and dashes, single spaces."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(
        str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-"})
    )
    text = text.replace("\u2014", "-")
    return re.sub(r"\s+", " ", text).strip()


def page_path(root: Path, day: str, url: str) -> Path:
    """Where a page is saved: ``<root>/<day>/<host>/<slug>``, the slug made from the path."""
    parts = urlsplit(url)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", parts.path.strip("/")) or "index"
    if parts.query:
        slug += "__" + re.sub(r"[^A-Za-z0-9._-]+", "_", parts.query)
    if not re.search(r"\.(html?|txt|xml|json|ya?ml|pdf)$", slug):
        slug += ".html"
    return root / day / parts.netloc / slug


@dataclass(frozen=True)
class SavedPage:
    url: str
    status: int
    path: Path
    nbytes: int
    sha256: str


def fetch_page(client: PoliteClient, url: str, root: Path, day: str) -> SavedPage:
    """Fetch one page and save it raw, whatever its status, with a manifest line."""
    resp = client.get(url)
    dest = page_path(root, day, url)
    if resp.status != 200:
        dest = dest.with_name(f"{dest.name}.http{resp.status}")
    n = 2
    base = dest
    while dest.exists():  # the same page fetched again the same day: keep both copies
        dest = base.with_name(f"{base.stem}.{n}{base.suffix}")
        n += 1
    digest = durable.write_once(dest, resp.content)
    saved = SavedPage(url, resp.status, dest, len(resp.content), digest)
    manifest = root / "manifest.csv"
    new = not manifest.exists()
    with manifest.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new:
            writer.writerow(MANIFEST_FIELDS)
        writer.writerow(
            [client.clock(), url, resp.status, dest.relative_to(root), len(resp.content), digest]
        )
        durable.flush_file(fh)
    return saved


def latest_pages(root: Path) -> dict[str, Path]:
    """The newest saved copy of each URL with status 200, from the manifest."""
    manifest = root / "manifest.csv"
    found: dict[str, Path] = {}
    if not manifest.exists():
        return found
    with manifest.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["status"] == "200":
                found[row["url"]] = root / row["path"]
    return found


def page_text(path: Path) -> str:
    """Plain text of a saved page (HTML reduced to text; other files read as they are)."""
    raw = path.read_bytes().decode("utf-8", errors="replace")
    if path.suffix in {".html", ".htm"} or raw.lstrip()[:15].lower().startswith(
        ("<!doctype", "<html")
    ):
        return html_to_text(raw)
    return raw


@dataclass(frozen=True)
class QuoteResult:
    url: str
    quote: str
    found: bool
    reason: str = ""


def check_quotes(quotes_csv: Path, root: Path) -> list[QuoteResult]:
    """Confirm every quote in ``quotes_csv`` (columns ``url`` and ``quote``) on its saved page."""
    pages = latest_pages(root)
    texts: dict[str, str] = {}
    results: list[QuoteResult] = []
    with quotes_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            url, quote = row["url"], row["quote"]
            if url not in pages:
                results.append(QuoteResult(url, quote, False, "no saved copy of this page"))
                continue
            if url not in texts:
                texts[url] = normalize(page_text(pages[url]))
            found = normalize(quote) in texts[url]
            results.append(QuoteResult(url, quote, found, "" if found else "not on the page"))
    return results
