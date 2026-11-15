"""Cleaning label text, reading its tables, and finding the headings of patient texts.

In the openFDA label data every section is one or more plain strings. The source markup is
gone and so are the line breaks: a section's heading runs straight into its body (for example
``"5 WARNINGS AND PRECAUTIONS 5.1 ..."``). Tables come separately, as HTML, in the fields that
end in ``_table``. So:

- :func:`clean` normalizes a string (Unicode NFC, entities, stray tags, spaces) and keeps every
  word, headings included;
- :func:`table_to_text` turns one HTML table into plain rows, cells separated by `` | ``;
- :func:`segment_patient_text` finds the standard headings of a Medication Guide (and of the
  patient package inserts that follow the same plan) by their wording, and cuts the text into
  segments, one per heading. The standard headings are the questions set out in 21 CFR 208.20
  plus the few that most guides add (storage, ingredients, "before taking").
"""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser

_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>")
_SPACE = re.compile(r"\s+")


def clean(text: str) -> str:
    """One string of label text, normalized; every word kept."""
    text = html.unescape(text)
    if "<" in text and ">" in text:
        text = _TAG.sub(" ", text)
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00a0", " ").replace("\u00ad", "")
    return _SPACE.sub(" ", text).strip()


def join(parts: list[str] | None) -> str | None:
    """The strings of one field, cleaned and joined with a blank line; None when empty."""
    if not parts:
        return None
    cleaned = [c for c in (clean(p) for p in parts) if c]
    return "\n\n".join(cleaned) if cleaned else None


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(_SPACE.sub(" ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def table_to_text(markup: str) -> str:
    """One HTML table as plain text: one line per row, cells separated by `` | ``."""
    parser = _TableParser()
    parser.feed(markup)
    parser.close()
    return "\n".join(" | ".join(row) for row in parser.rows)


#: Where the closing matter of a patient text begins: who makes or sells the medicine, the
#: approval line, the revision date. Texts that differ only there are near duplicates.
_CLOSING = re.compile(
    r"\b(?:Manufactured (?:by|for)|Distributed (?:by|for)|Marketed by|Manufactured and "
    r"distributed by|This (?:Medication Guide|Patient Information|Instructions for Use) "
    r"(?:has|have) been approved|Revised:|Issued:|For more information,? (?:go to|call|visit))",
    re.I,
)


def core(text: str) -> str:
    """A patient text without its closing matter, when that begins in the last third."""
    cut = len(text)
    for m in _CLOSING.finditer(text):
        if m.start() >= len(text) * 2 / 3:
            cut = m.start()
            break
    return text[:cut]


def core_hash(text: str) -> str:
    """:func:`loose_hash` of :func:`core`: equal for texts that differ only in closing matter."""
    return loose_hash(core(text))


def text_hash(text: str) -> str:
    """SHA-256 of a text after spaces are normalized: equal texts get equal hashes."""
    return hashlib.sha256(_SPACE.sub(" ", text).strip().encode("utf-8")).hexdigest()


def loose_hash(text: str) -> str:
    """SHA-256 of a text reduced to lowercase letters and digits, single-spaced.

    Two texts that differ only in case, punctuation, symbols or spacing get the same hash.
    """
    folded = re.sub(r"[^0-9a-z]+", " ", unicodedata.normalize("NFKD", text).casefold())
    return hashlib.sha256(folded.strip().encode("utf-8")).hexdigest()


# --- Headings of patient texts ------------------------------------------------------------

_VERB = r"(?:take|taking|use|using|receive|receiving|get|getting|give|giving|start|starting)"
_PROVIDER = r"(?:healthcare provider|health care provider|doctor|pharmacist|prescriber)"


def _name(i: int) -> str:
    """The medicine's name inside a heading, as a named group (``n1``, ``n2``, ...)."""
    return rf"(?P<n{i}>[^?]{{1,160}}?)"


#: (key, pattern). Order matters: at one place, the first pattern in this list wins.
HEADINGS: list[tuple[str, re.Pattern[str]]] = [
    (
        "most_important",
        re.compile(
            rf"What is the most important information I should know about {_name(1)}\?", re.I
        ),
    ),
    (
        "side_effects",
        re.compile(
            r"What are the (?:possible|most common|common|serious|possible or reasonably likely)"
            rf"(?: or reasonably likely)? side effects (?:of|from|with) {_name(1)}\?",
            re.I,
        ),
    ),
    ("ingredients", re.compile(rf"What are the ingredients in {_name(1)}\?", re.I)),
    ("avoid", re.compile(rf"What should I avoid (?:while|when|during|after) {_name(1)}\?", re.I)),
    (
        "before",
        re.compile(
            rf"What should I tell my {_PROVIDER} before {_VERB} {_name(1)}\?"
            rf"|Before (?:you )?{_VERB} (?P<n2>[^?,]{{1,160}}?), tell your {_PROVIDER}",
            re.I,
        ),
    ),
    (
        "who_should_not",
        re.compile(
            rf"Who should not {_VERB}(?: or be given)? {_name(1)}\?"
            rf"|Who should not be (?:given|treated with) {_name(2)}\?",
            re.I,
        ),
    ),
    (
        "how_to_take",
        re.compile(
            rf"How should I {_VERB}(?: or give| or use)? {_name(1)}\?"
            rf"|How (?:do|should) I (?:inject|apply) {_name(2)}\?",
            re.I,
        ),
    ),
    ("storage", re.compile(rf"How should I (?:store|keep) {_name(1)}\?", re.I)),
    (
        "general",
        re.compile(
            r"General information about the safe and effective use of (?P<n1>[^.?]{1,160})[.?]?",
            re.I,
        ),
    ),
    ("what_is", re.compile(rf"What (?:is|are) {_name(1)}\?", re.I)),
]
HEADING_KEYS = [key for key, _ in HEADINGS]
_PATTERNS = dict(HEADINGS)


@dataclass(frozen=True)
class Segment:
    key: str
    heading: str
    body: str


#: Words just before a heading that make it a reference to the heading, not the heading.
_REFERENCE = re.compile(
    r"""(?:\bsee|\bin|\bunder|\bread)\s*["'\u201c\u2018]?\s*$|["'\u201c\u2018]\s*$""", re.I
)


def is_reference(text: str, start: int) -> bool:
    """True when the heading at ``start`` is cited in running text (``See "What is ...?"``)."""
    return bool(_REFERENCE.search(text[max(0, start - 8) : start]))


def find_headings(text: str) -> list[tuple[int, int, str]]:
    """Standard headings in ``text``: (start, end, key), in order, never overlapping.

    A heading quoted or cited in running text (after "see", "in", "under", "read" or an
    opening quote mark) is a reference to that heading and is skipped.
    """
    found: list[tuple[int, int, str]] = []
    for key, pattern in HEADINGS:
        for m in pattern.finditer(text):
            if not is_reference(text, m.start()):
                found.append((m.start(), m.end(), key))
    found.sort(key=lambda h: (h[0], HEADING_KEYS.index(h[2])))
    kept: list[tuple[int, int, str]] = []
    for start, end, key in found:
        if kept and start < kept[-1][1]:
            continue
        kept.append((start, end, key))
    return kept


def segment_spans(text: str) -> list[tuple[str, int, int, int]]:
    """Segments of a patient text as character offsets: (key, start, heading end, end).

    The same cut as :func:`segment_patient_text`; a ``preamble`` has no heading, so its
    heading end equals its start. Offsets let the record layer point into a text it does not
    hold.
    """
    heads = find_headings(text)
    spans: list[tuple[str, int, int, int]] = []
    first = heads[0][0] if heads else len(text)
    if text[:first].strip():
        spans.append(("preamble", 0, 0, first))
    for i, (start, end, key) in enumerate(heads):
        stop = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        spans.append((key, start, end, stop))
    return spans


def segment_patient_text(text: str) -> list[Segment]:
    """Cut a patient text at its standard headings.

    Text before the first heading becomes a segment with the key ``preamble`` (title, "Read
    this before you start", and so on). A text with no standard heading is one ``preamble``.
    """
    heads = find_headings(text)
    segments: list[Segment] = []
    first = heads[0][0] if heads else len(text)
    if text[:first].strip():
        segments.append(Segment("preamble", "", text[:first].strip()))
    for i, (start, end, key) in enumerate(heads):
        stop = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        segments.append(Segment(key, text[start:end].strip(), text[end:stop].strip()))
    return segments


def heading_template(heading: str, key: str) -> str:
    """A heading with the medicine's name replaced by ``[medicine]``, for counting headings."""
    m = _PATTERNS[key].fullmatch(heading) or _PATTERNS[key].match(heading)
    if not m:
        return heading
    for group, value in m.groupdict().items():
        if value is not None and group.startswith("n"):
            start, end = m.span(group)
            return _SPACE.sub(" ", heading[:start] + "[medicine]" + heading[end:])
    return heading  # pragma: no cover - every pattern has a name group


# --- Tables repeated inline ----------------------------------------------------------------

_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
#: The longest gap allowed between two cells of one table found in running text.
_MAX_GAP = 400


def table_cells(markup: str) -> list[str]:
    """The cleaned text of each cell of one HTML table, empty cells left out."""
    return [c for c in (clean(m) for m in _CELL.findall(markup)) if c]


def strip_tables(text: str, tables: list[str], min_found: float = 0.6) -> tuple[str, int]:
    """``text`` without the tables that the source also repeats inline, and the characters cut.

    The source keeps each table twice: as HTML in a ``*_table`` field and, flattened, inside
    the section's text. For each table, its cells are looked for in order in the text, each
    within a short gap of the last; the stretch they cover is cut when at least ``min_found``
    of the table's characters were found. A table not repeated inline is left alone.
    """
    spans: list[tuple[int, int]] = []
    for markup in tables:
        cells = [c for c in table_cells(markup) if len(c) >= 3]
        if not cells:
            continue
        total = sum(len(c) for c in cells)
        found, pos, start, end = 0, 0, None, None
        for cell in cells:
            window = len(cell) + _MAX_GAP if start is not None else len(text)
            idx = text.find(cell, pos, pos + window if start is not None else None)
            if idx == -1:
                continue
            if start is None:
                start = idx
            end = idx + len(cell)
            found += len(cell)
            pos = end
        if start is not None and end is not None and found / total >= min_found:
            spans.append((start, end))
    if not spans:
        return text, 0
    spans.sort()
    merged: list[list[int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    out, last, cut = [], 0, 0
    for s, e in merged:
        out.append(text[last:s])
        cut += e - s
        last = e
    out.append(text[last:])
    return _SPACE.sub(" ", " ".join(out)).strip(), cut


_NUMBERED = re.compile(r"(?<![\d.])\d{1,2}\.\d{1,2}\s+[A-Z]")


def count_numbered_headings(text: str) -> int:
    """Numbered headings in a prescriber section (``5.1 Liver Problems``)."""
    return len(_NUMBERED.findall(text))
