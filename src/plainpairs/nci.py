"""The NCI cancer information summaries as their own configuration (``nci``).

Each summary page saved by :mod:`plainpairs.nci_pages` is read here into:

- **identity**: the page's address (its canonical ``og:url``), its language (``<html lang>``),
  its version (``dcterms.audience``: health professionals or patients), its title
  (``og:title``) and the date NCI gives for its last update (the "Updated" or "Actualizacion"
  line at the foot of the summary);
- **links**: the page's link to the other version of the same summary (the box "Go to Patient
  Version" / "Go to Health Professional Version", and its Spanish forms) and to the same
  version in the other language (``hreflang`` alternates);
- **blocks**: the summary's body, in reading order: headings with their level, paragraphs, list
  items, table cells (prose cells, or data cells of tables of short cells) and table captions.

**Left out, never kept:** images and figures with their captions; the navigation (the page's
own tables of contents and the version box); the "Key Points" boxes of patient summaries (a
list of the headings that follow); the reference lists (only counted) and the citation marks
in the text ("[12]"); the closing "About This Summary" sections (purpose, reviewers, levels of
evidence, permission to use, how to cite, disclaimer, contact); and any block that carries a
credit or permission line. Each left-out kind is counted.

The summaries, the pairs and the text are three tables of the ``nci`` configuration. None of
their numbers is ever pooled with the label configurations.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import pyarrow as pa
import pyarrow.parquet as pq

from plainpairs import codes, readability, readability_es, text

CONFIGURATION = "nci"
SOURCE = "NCI cancer information summaries (https://www.cancer.gov)"
VERSIONS = {"Health Professionals": "health_professional", "Patients": "patient"}
PROSE_KINDS = ("paragraph", "item", "cell", "caption")
LEFT_OUT = (
    "figure",
    "navigation",
    "key_points",
    "reference",
    "citation_mark",
    "about_this",
    "credit_line",
)
_VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
    "track", "wbr",
}  # fmt: skip
_BLOCK = {"p", "li", "td", "th", "caption", "dt", "dd", "blockquote"}
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_SKIP_TAGS = {"script", "style", "noscript", "svg", "button", "form", "iframe", "template"}
_REFERENCE_HEADINGS = frozenset({"references", "bibliograf\u00eda", "bibliografia"})
#: A block that credits or grants permission for something is left out.
CREDIT_LINE = re.compile(
    r"\u00a9|\bcopyright\b|\b(?:reprinted|adapted|reproduced|used)\s+(?:with\s+permission|from)"
    r"|\bwith\s+permission\b|\bcourtesy\s+of\b|\ball\s+rights\s+reserved\b"
    r"|\bderechos\s+reservados\b|\bcon\s+(?:autorizaci\u00f3n|permiso)\b|\badaptad[oa]\s+de\b"
    r"|\breproducid[oa]\s+(?:con|de)\b|\bcortes\u00eda\s+de\b",
    re.I,
)
_CITATION_REMNANT = re.compile(r"\[\s*(?:[,;\u2013\-]\s*)*\]")


class NciError(ValueError):
    """A saved page that is not a summary, or not shaped as expected."""


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    children: list[Any] = field(default_factory=list)

    def cls(self) -> str:
        return self.attrs.get("class", "") or ""


class _Tree(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.stack[-1].children.append(_Node(tag, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def _tree(markup: str) -> _Node:
    t = _Tree()
    t.feed(markup)
    t.close()
    return t.root


def _iter(node: _Node) -> Iterator[_Node]:
    yield node
    for ch in node.children:
        if isinstance(ch, _Node):
            yield from _iter(ch)


def _text_of(node: _Node) -> str:
    parts: list[str] = []

    def walk(n: _Node) -> None:
        for ch in n.children:
            if isinstance(ch, str):
                parts.append(ch)
            elif ch.tag not in _SKIP_TAGS:
                walk(ch)

    walk(node)
    return text.clean("".join(parts))


@dataclass(frozen=True)
class NciBlock:
    kind: str  # heading, paragraph, item, cell, data_cell, caption
    text: str
    #: The heading level (2 to 6), or 0 for other blocks.
    level: int = 0
    #: 1-based number of the table the block sits in (0 = not in a table).
    table: int = 0


@dataclass
class Page:
    url: str
    language: str | None
    version: str | None
    title: str | None
    updated: str | None
    other_version_url: str | None
    other_language_urls: dict[str, str]
    blocks: list[NciBlock]
    left_out: Counter[str]
    references: int


class _Body:
    """Reads the summary body into blocks, leaving out what the module docstring lists."""

    def __init__(self) -> None:
        self.blocks: list[NciBlock] = []
        self.left_out: Counter[str] = Counter()
        self.references = 0
        self.tables = 0
        self._next_list_is_references = False

    def _emit(self, kind: str, raw: str, level: int = 0, table: int = 0) -> None:
        s = text.clean(_CITATION_REMNANT.sub(" ", raw))
        s = re.sub(r"\s+([,.;:])", r"\1", s)
        if not readability_es.words(s):
            return
        if CREDIT_LINE.search(s):
            self.left_out["credit_line"] += 1
            return
        self.blocks.append(NciBlock(kind, s, level, table))

    def _count_left_out(self, node: _Node, why: str) -> None:
        n = sum(1 for d in _iter(node) if d.tag in _BLOCK or d.tag in _HEADINGS) or 1
        self.left_out[why] += n

    def walk(self, node: _Node, kind: str = "paragraph", table: int = 0) -> None:
        """Walk a container; inline text is collected into the block that holds it."""
        buf: list[str] = []

        def flush() -> None:
            if buf:
                self._emit(kind, "".join(buf), table=table)
                buf.clear()

        for ch in node.children:
            if isinstance(ch, str):
                buf.append(ch)
                continue
            if self._skip(ch):
                continue
            tag = ch.tag
            if tag in _HEADINGS:
                flush()
                heading = _text_of(ch)
                if heading.lower().rstrip(":") in _REFERENCE_HEADINGS:
                    self._next_list_is_references = True
                    continue
                self._emit("heading", heading, level=_HEADINGS[tag])
            elif tag in ("ol", "ul") and self._next_list_is_references:
                flush()
                self._next_list_is_references = False
                n = sum(1 for d in ch.children if isinstance(d, _Node) and d.tag == "li")
                self.references += n
                self.left_out["reference"] += n
            elif tag == "table":
                flush()
                self._table(ch)
            elif tag in _BLOCK:
                flush()
                inner = {"li": "item", "td": kind, "th": kind, "caption": "caption"}.get(
                    tag, kind if kind in ("item", "cell", "data_cell") else "paragraph"
                )
                self.walk(ch, inner, table)
            elif tag in ("ol", "ul", "div", "section", "dl", "article", "thead", "tbody",
                         "tfoot", "tr", "header", "main", "aside"):  # fmt: skip
                flush()
                self.walk(ch, kind if kind in ("cell", "data_cell") else "paragraph", table)
            elif tag == "br":
                flush()
            else:  # inline markup: its text joins the line
                buf.append(self._inline(ch))
        flush()

    def _inline(self, node: _Node) -> str:
        parts: list[str] = []
        for ch in node.children:
            if isinstance(ch, str):
                parts.append(ch)
            elif not self._skip(ch):
                parts.append(self._inline(ch))
        return "".join(parts)

    def _skip(self, node: _Node) -> bool:
        tag, cls, ident = node.tag, node.cls(), node.attrs.get("id", "")
        if tag in _SKIP_TAGS:
            return True
        if tag == "a" and node.attrs.get("href", "").startswith("#cit/"):
            self.left_out["citation_mark"] += 1
            return True
        if tag in ("figure", "img", "picture") and "table" not in cls:
            self.left_out["figure"] += 1
            return True
        if tag == "nav" or "toggle" in cls or "on-this-page" in cls or "in-this-section" in cls:
            self._count_left_out(node, "navigation")
            return True
        if "key-points" in cls:
            self._count_left_out(node, "key_points")
            return True
        if tag == "section" and ident.startswith("_AboutThis"):
            self._count_left_out(node, "about_this")
            return True
        return False

    def _table(self, node: _Node) -> None:
        self.tables += 1
        n = self.tables
        cells = [d for d in _iter(node) if d.tag in ("td", "th")]
        flat = [_text_of(c) for c in cells]
        kind = "data_cell" if text.is_data_table([c for c in flat if c]) else "cell"
        for d in _iter(node):
            if d.tag == "caption":
                self.walk(d, "caption", n)
        for c in cells:
            self.walk(c, kind, n)


def _meta(root: _Node) -> dict[str, str]:
    out: dict[str, str] = {}
    for n in _iter(root):
        if n.tag == "meta":
            key = n.attrs.get("name") or n.attrs.get("property")
            if key and key not in out:
                out[key] = n.attrs.get("content", "")
    return out


def parse_page(markup: str, url: str = "") -> Page:
    """One saved summary page; raises :class:`NciError` for a page that is not a summary."""
    root = _tree(markup)
    meta = _meta(root)
    if meta.get("dcterms.type") != "pdqCancerInfoSummary":
        raise NciError(f"{url or 'the page'} is not a cancer information summary page.")
    html = next((n for n in _iter(root) if n.tag == "html"), None)
    page_url = meta.get("og:url") or url
    other_version = None
    other_language: dict[str, str] = {}
    updated = None
    for n in _iter(root):
        cls = n.cls()
        if n.tag == "div" and "pdq-hp-patient-toggle" in cls and other_version is None:
            a = next((d for d in _iter(n) if d.tag == "a" and d.attrs.get("href")), None)
            if a is not None:
                other_version = urljoin(page_url, a.attrs["href"])
        if n.tag == "link" and n.attrs.get("rel") == "alternate" and n.attrs.get("hreflang"):
            other_language[n.attrs["hreflang"]] = urljoin(page_url, n.attrs.get("href", ""))
        if n.tag == "div" and "document-dates" in cls and updated is None:
            t = next((d for d in _iter(n) if d.tag == "time"), None)
            if t is not None:
                updated = (t.attrs.get("datetime") or "")[:10] or None
    language = (html.attrs.get("lang") if html is not None else None) or None
    other_language.pop(language or "", None)
    body = _Body()
    accordion = next(
        (n for n in _iter(root) if n.tag == "div" and "accordion" in n.cls().split()), None
    )
    if accordion is None:
        raise NciError(f"{url or 'the page'} has no summary body (no accordion).")
    body.walk(accordion)
    return Page(
        url=page_url,
        language=language,
        version=VERSIONS.get(meta.get("dcterms.audience", "")),
        title=meta.get("og:title") or None,
        updated=updated,
        other_version_url=other_version,
        other_language_urls=other_language,
        blocks=body.blocks,
        left_out=body.left_out,
        references=body.references,
    )


def credit_line(title: str | None, url: str) -> str:
    """The credit NCI asks for a digital reproduction: the original title, and a link."""
    name = title or "This summary"
    return f'"{name}" was originally published by the National Cancer Institute. {url}'


# --- measures --------------------------------------------------------------------------------


def units(blocks: list[NciBlock]) -> list[str]:
    """Sentences from structure: each prose block cut by ``s1``; headings and data cells are
    not sentences."""
    out: list[str] = []
    for b in blocks:
        if b.kind in PROSE_KINDS:
            out.extend(readability.sentences(b.text, "s1"))
    return out


def measures(blocks: list[NciBlock], language: str | None) -> dict[str, Any]:
    """English: words, sentences, Flesch-Kincaid and SMOG (always together); Spanish: words,
    sentences and the Szigriszt-Pazos perspicuity index with its INFLESZ band."""
    u = units(blocks)
    kinds = Counter(b.kind for b in blocks)
    out: dict[str, Any] = dict.fromkeys(MEASURE_FIELDS)
    out.update(
        blocks_heading=kinds.get("heading", 0),
        blocks_paragraph=kinds.get("paragraph", 0),
        blocks_item=kinds.get("item", 0),
        blocks_cell=kinds.get("cell", 0),
        blocks_data_cell=kinds.get("data_cell", 0),
        blocks_caption=kinds.get("caption", 0),
    )
    if language == "en":
        m = readability.measure_units(u)
        out.update({k: m[k] for k in ("words", "sentences", "long_sentence_share")})
        out.update(flesch_kincaid=m["flesch_kincaid"], smog=m["smog"])
    elif language == "es":
        m = readability_es.measure_units(u)
        out.update({k: m[k] for k in ("words", "sentences", "long_sentence_share")})
        out.update(szigriszt_pazos=m["szigriszt_pazos"], inflesz_band=m["inflesz_band"])
    return out


#: The trusted codes of the codebook, read on English summaries.
CODE_FIELDS = (
    "you_words",
    "sentences_with_you",
    "command_sentences",
    "conditional_commands",
    "distinct_actions",
    "percentages",
    "one_in_n",
    "frequencies",
    "doses",
    "contact_sentences",
    "sentences_over_20",
    "sentences_over_40",
    "longest_sentence_words",
)


def trusted_codes(blocks: list[NciBlock]) -> dict[str, int]:
    """The trusted codes on an English summary, with the long-sentence codes read from its
    structure (the units)."""
    u = units(blocks)
    got = codes.code_text("\n".join(u), "prescriber")
    lengths = [len(readability.words(s)) for s in u]
    out = {k: got[k] for k in CODE_FIELDS[:10]}
    out.update(
        sentences_over_20=sum(n > readability.LONG_SENTENCE for n in lengths),
        sentences_over_40=sum(n > 40 for n in lengths),
        longest_sentence_words=max(lengths, default=0),
    )
    return out


# --- tables ----------------------------------------------------------------------------------

MEASURE_FIELDS = (
    "words",
    "sentences",
    "long_sentence_share",
    "flesch_kincaid",
    "smog",
    "szigriszt_pazos",
    "inflesz_band",
    "blocks_heading",
    "blocks_paragraph",
    "blocks_item",
    "blocks_cell",
    "blocks_data_cell",
    "blocks_caption",
)
NCI_MEASURES = pa.struct(
    [
        ("words", pa.int32()),
        ("sentences", pa.int32()),
        ("long_sentence_share", pa.float32()),
        ("flesch_kincaid", pa.float32()),
        ("smog", pa.float32()),
        ("szigriszt_pazos", pa.float32()),
        ("inflesz_band", pa.string()),
        ("blocks_heading", pa.int32()),
        ("blocks_paragraph", pa.int32()),
        ("blocks_item", pa.int32()),
        ("blocks_cell", pa.int32()),
        ("blocks_data_cell", pa.int32()),
        ("blocks_caption", pa.int32()),
    ]
)
NCI_CODES = pa.struct([(f, pa.int32()) for f in CODE_FIELDS])
LEFT_OUT_STRUCT = pa.struct([(k, pa.int32()) for k in LEFT_OUT])
_ROW_IDS = [
    ("configuration", pa.string()),
    ("source", pa.string()),
    ("url", pa.string()),
    ("date_read", pa.string()),
    ("nci_updated", pa.string()),
    ("credit_line", pa.string()),
]
SUMMARIES_SCHEMA = pa.schema(
    [
        *_ROW_IDS,
        ("language", pa.string()),
        ("version", pa.string()),
        ("title", pa.string()),
        ("topic_id", pa.string()),
        ("other_version_url", pa.string()),
        ("other_language_url", pa.string()),
        ("text_sha256", pa.string()),
        ("n_blocks", pa.int32()),
        ("references", pa.int32()),
        ("left_out", LEFT_OUT_STRUCT),
        ("measures", NCI_MEASURES),
        ("codes", NCI_CODES),
    ]
)
PAIRS_SCHEMA = pa.schema(
    [
        ("configuration", pa.string()),
        ("source", pa.string()),
        ("pair_kind", pa.string()),  # version (same language) or language (same version)
        ("language", pa.string()),  # for version pairs
        ("version", pa.string()),  # for language pairs
        ("url_a", pa.string()),
        ("url_b", pa.string()),
        ("linked_from", pa.string()),  # both, a_only, b_only
        ("topic_id", pa.string()),
        ("date_read_a", pa.string()),
        ("date_read_b", pa.string()),
        ("nci_updated_a", pa.string()),
        ("nci_updated_b", pa.string()),
        ("credit_line_a", pa.string()),
        ("credit_line_b", pa.string()),
    ]
)
TEXT_SCHEMA = pa.schema(
    [
        *_ROW_IDS,
        ("block_index", pa.int32()),
        ("kind", pa.string()),
        ("level", pa.int16()),
        ("table", pa.int16()),
        ("text", pa.string()),
        ("sha256", pa.string()),
    ]
)
TABLES = {
    "nci_summaries": SUMMARIES_SCHEMA,
    "nci_pairs": PAIRS_SCHEMA,
    "nci_text": TEXT_SCHEMA,
}


def text_hash(blocks: list[NciBlock]) -> str:
    """SHA-256 over the kept blocks (kind and text, one line each): what the rebuild checks."""
    joined = "\n".join(f"{b.kind}\t{b.level}\t{b.table}\t{b.text}" for b in blocks)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _components(edges: list[tuple[str, str]], nodes: list[str]) -> dict[str, str]:
    parent = {n: n for n in nodes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    return {n: find(n) for n in nodes}


def pair_pages(pages: dict[str, Page]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Version pairs and language pairs, from the links on NCI's own pages only.

    Returns the pair rows (without the per-page columns) and each page's topic id: the
    smallest address in its group of linked pages.
    """
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add(kind: str, a: str, b: str, from_a: bool) -> None:
        if a not in pages or b not in pages or a == b:
            return
        pa_, pb_ = pages[a], pages[b]
        if kind == "version" and (pa_.language != pb_.language or pa_.version == pb_.version):
            return
        if kind == "language" and (pa_.version != pb_.version or pa_.language == pb_.language):
            return
        # order: health professional first; English first
        swap = (
            pa_.version == "patient"
            if kind == "version"
            else (pa_.language or "") > (pb_.language or "")
        )
        if swap:
            a, b, from_a = b, a, not from_a
        key = (kind, a, b)
        row = rows.setdefault(
            key,
            {
                "pair_kind": kind,
                "language": pages[a].language if kind == "version" else None,
                "version": pages[a].version if kind == "language" else None,
                "url_a": a,
                "url_b": b,
                "_from": set(),
            },
        )
        row["_from"].add("a" if from_a else "b")

    for url, p in pages.items():
        if p.other_version_url:
            add("version", url, p.other_version_url, True)
        for other in p.other_language_urls.values():
            add("language", url, other, True)
    out = []
    for row in rows.values():
        f = row.pop("_from")
        row["linked_from"] = "both" if f == {"a", "b"} else ("a_only" if f == {"a"} else "b_only")
        out.append(row)
    topics = _components([(r["url_a"], r["url_b"]) for r in out], sorted(pages))
    for r in out:
        r["topic_id"] = topics[r["url_a"]]
    return sorted(out, key=lambda r: (r["pair_kind"], r["url_a"], r["url_b"])), topics


def saved_pages(root: Path) -> dict[str, Path]:
    """The saved copy (status 200) of each summary page, from the NCI manifest."""
    from plainpairs import pages as _pages

    return _pages.latest_pages(Path(root))


def build(
    root: Path,
    out_dir: Path,
    date_read: Callable[[str], str],
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Parse every saved summary page under ``root`` and write the three ``nci`` tables."""
    found = saved_pages(root)
    parsed: dict[str, Page] = {}
    counts: Counter[str] = Counter()
    by_saved_url: dict[str, str] = {}
    for url, path in sorted(found.items()):
        try:
            p = parse_page(path.read_text(encoding="utf-8", errors="replace"), url)
        except NciError:
            counts["not_a_summary"] += 1
            continue
        parsed[p.url] = p
        by_saved_url[p.url] = url
        counts[f"pages:{p.language}:{p.version}"] += 1
        if p.url != url:
            counts["canonical_differs_from_sitemap"] += 1
    pair_rows, topics = pair_pages(parsed)
    read_on = {u: date_read(by_saved_url[u]) for u in parsed}
    credit = {u: credit_line(p.title, u) for u, p in parsed.items()}
    summaries, texts = [], []
    for u, p in sorted(parsed.items()):
        base = {
            "configuration": CONFIGURATION,
            "source": SOURCE,
            "url": u,
            "date_read": read_on[u],
            "nci_updated": p.updated,
            "credit_line": credit[u],
        }
        other_lang = next(iter(p.other_language_urls.values()), None)
        summaries.append(
            {
                **base,
                "language": p.language,
                "version": p.version,
                "title": p.title,
                "topic_id": topics[u],
                "other_version_url": p.other_version_url,
                "other_language_url": other_lang,
                "text_sha256": text_hash(p.blocks),
                "n_blocks": len(p.blocks),
                "references": p.references,
                "left_out": {k: p.left_out.get(k, 0) for k in LEFT_OUT},
                "measures": measures(p.blocks, p.language),
                "codes": trusted_codes(p.blocks) if p.language == "en" else None,
            }
        )
        for i, b in enumerate(p.blocks):
            texts.append(
                {
                    **base,
                    "block_index": i,
                    "kind": b.kind,
                    "level": b.level,
                    "table": b.table,
                    "text": b.text,
                    "sha256": hashlib.sha256(b.text.encode("utf-8")).hexdigest(),
                }
            )
    pairs = []
    for r in pair_rows:
        a, b = r["url_a"], r["url_b"]
        pairs.append(
            {
                "configuration": CONFIGURATION,
                "source": SOURCE,
                **r,
                "date_read_a": read_on[a],
                "date_read_b": read_on[b],
                "nci_updated_a": parsed[a].updated,
                "nci_updated_b": parsed[b].updated,
                "credit_line_a": credit[a],
                "credit_line_b": credit[b],
            }
        )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("nci_summaries", summaries), ("nci_pairs", pairs), ("nci_text", texts)):
        pq.write_table(
            pa.Table.from_pylist(rows, TABLES[name]),
            out_dir / f"{name}.parquet",
            compression="zstd",
        )
        counts[f"rows:{name}"] = len(rows)
    counts["pairs:version"] = sum(1 for r in pairs if r["pair_kind"] == "version")
    counts["pairs:language"] = sum(1 for r in pairs if r["pair_kind"] == "language")
    log(f"nci: {len(parsed)} summaries, {len(pairs)} pairs, {len(texts)} text blocks")
    return dict(counts)


# --- rebuilding the text layer ----------------------------------------------------------------


def rebuild_text(
    summaries: list[dict[str, Any]], get_page: Callable[[str], str | None]
) -> dict[str, Any]:
    """Rebuild the ``nci`` text layer by reading each summary page again and parsing it.

    ``get_page(url)`` returns the page's HTML, or None when it cannot be had. The release does
    not need NCI's text to be redistributed: anyone can rebuild it from NCI's own pages with
    the addresses and hashes of ``nci_summaries``. A page NCI has updated since it was read
    gives a different hash; the report counts those apart (``changed``), with NCI's new update
    date when it moved.
    """
    out: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    for s in summaries:
        markup = get_page(s["url"])
        if markup is None:
            out["missing"] += 1
            continue
        try:
            p = parse_page(markup, s["url"])
        except NciError:
            out["not_a_summary"] += 1
            continue
        if text_hash(p.blocks) == s["text_sha256"]:
            out["same"] += 1
        else:
            out["changed"] += 1
            out["changed_with_new_update_date"] += p.updated != s["nci_updated"]
        for i, b in enumerate(p.blocks):
            rows.append({"url": s["url"], "block_index": i, "kind": b.kind, "text": b.text})
    return {"counts": dict(out), "rows": rows}
