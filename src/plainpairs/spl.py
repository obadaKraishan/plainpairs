"""The structure of a label in Structured Product Labeling (SPL), the XML DailyMed serves.

openFDA's JSON keeps each section as one flat string. The XML it comes from keeps the
structure: nested sections with their titles, paragraphs, lists and their items, tables and
their cells, and line breaks. :func:`parse_document` reads one SPL document (with defusedxml,
since it is outside data) into **blocks**, one per unit of structure, for the sections this
corpus uses. Each section is found by its LOINC code, filed under the openFDA field that holds
the same section in the JSON (:data:`FIELD_CODES`).

**Blocks.** A block is one line of one structural unit, in reading order:

- ``title``: a section's or subsection's title;
- ``heading``: a line set wholly in bold or underline, of at most 30 words, that does not end
  as a sentence does (``.``, ``:``, ``;``, ``!``, ``,``). Medication Guides set their questions
  this way. A bold question that opens a paragraph ("**What is X?** X is ...") is split off as
  a heading of its own;
- ``paragraph``, ``item`` (a list item, or a piece of a line after a typed list mark), ``cell``
  (a cell of a table that holds prose, as patient texts use for boxes) and ``caption``;
- ``data_cell``: a cell of a data table (short cells, by :func:`plainpairs.text.is_data_table`),
  which the JSON measures cut as well.

A line break (``<br/>``) ends a line, so a heading and its body set apart by a break become two
blocks. A newer-format section's Highlights excerpt is read too, with ``highlights`` set, since
the JSON keeps it in the same field. Images (``renderMultiMedia``), media descriptions and
product data are not read.

**Sentences from structure** (:func:`units`): every ``paragraph``, ``item``, ``cell`` and
``caption`` block is cut into sentences by the first sentence rule (``s1``), and every block
ends a sentence. Titles, headings and data cells are not sentences and are not measured.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from defusedxml import ElementTree

from plainpairs import readability, text
from plainpairs.schema import OLDER_WARNINGS, PATIENT_SOURCES, PRESCRIBER_SOURCES

NS = "{urn:hl7-org:v3}"
#: openFDA field -> the LOINC section codes (FDA's SPL section headings) filed under it.
FIELD_CODES: dict[str, tuple[str, ...]] = {
    "boxed_warning": ("34066-1",),
    "indications_and_usage": ("34067-9",),
    "dosage_and_administration": ("34068-7",),
    "contraindications": ("34070-3",),
    "warnings_and_cautions": ("43685-7",),
    "warnings": ("34071-1",),
    "precautions": ("42232-9",),
    "adverse_reactions": ("34084-4",),
    "drug_interactions": ("34073-7",),
    "use_in_specific_populations": ("43684-0",),
    "information_for_patients": ("34076-0",),
    "description": ("34089-3",),
    "how_supplied": ("34069-5",),
    "storage_and_handling": ("44425-7",),
    "spl_medguide": ("42231-1",),
    "spl_patient_package_insert": ("42230-3",),
    "instructions_for_use": ("59845-8",),
    "patient_medication_information": ("68498-5",),
}
_FIELD_OF = {code: f for f, codes in FIELD_CODES.items() for code in codes}
PROSE_KINDS = ("paragraph", "item", "cell", "caption")
BLOCK_KINDS = ("title", "heading", *PROSE_KINDS, "data_cell")
#: The longest line read as a heading (words).
HEADING_MAX_WORDS = 30
_SENTENCE_LIKE_END = ".:;!,"
_STYLED = re.compile(r"bold|underline|emphasis", re.I)
#: Typed list marks: those the JSON's ``s2`` rule breaks at, and the white circle.
_TYPED_MARK = re.compile(r"\s*[\u2022\u25cf\u25aa\u25a0\u25e6\u2023\u25cb]\s*")
_SKIP = {"renderMultiMedia", "observationMedia", "subject", "id", "code"}
_INLINE = {"content", "sub", "sup", "linkHtml", "footnoteRef", "footnote", "span", "a"}


class SplError(ValueError):
    """An SPL document that cannot be read (not XML, or without a set id)."""


@dataclass(frozen=True)
class Block:
    kind: str
    text: str
    #: Section depth below the top section of its field (0 = the section itself).
    depth: int = 0
    #: How many lists this block sits in (0 = none).
    list_depth: int = 0
    #: 1-based number of the table it sits in within its section (0 = not in a table).
    table: int = 0
    #: True for the section's Highlights excerpt (newer-format labels), which the JSON keeps
    #: in the same field.
    highlights: bool = False


def _local(tag: Any) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _styled(el: Any) -> bool:
    return bool(_STYLED.search(el.get("styleCode") or ""))


@dataclass
class _Line:
    parts: list[tuple[str, bool]] = field(default_factory=list)

    def add(self, s: str | None, styled: bool) -> None:
        if s:
            self.parts.append((s, styled))


@dataclass(frozen=True)
class _Ctx:
    depth: int = 0
    list_depth: int = 0
    table: int = 0
    highlights: bool = False


class _Walker:
    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self.tables = 0

    # -- one line --------------------------------------------------------------------------------
    def _emit(self, line: _Line, kind: str, ctx: _Ctx) -> None:
        whole = text.clean("".join(s for s, _ in line.parts))
        if not whole:
            return

        def add(k: str, s: str) -> None:
            self.blocks.append(Block(k, s, ctx.depth, ctx.list_depth, ctx.table, ctx.highlights))

        if kind in ("title", "data_cell"):
            add(kind, whole)
            return
        styled_chars = sum(len(s.strip()) for s, st in line.parts if st)
        all_chars = sum(len(s.strip()) for s, _ in line.parts)
        if (
            styled_chars == all_chars
            and len(readability.words(whole)) <= HEADING_MAX_WORDS
            and whole[-1] not in _SENTENCE_LIKE_END
        ):
            add("heading", whole)
            return
        # a bold question opening a line ("What is X? X is ..."): a heading, then the body
        lead: list[str] = []
        for s, st in line.parts:
            if st or (lead and not s.strip()):
                lead.append(s)
            else:
                break
        head = text.clean("".join(lead))
        if head.endswith("?") and len(readability.words(head)) <= HEADING_MAX_WORDS:
            rest = text.clean("".join(s for s, _ in line.parts[len(lead) :]))
            if rest:
                add("heading", head)
                whole = rest
        pieces = _TYPED_MARK.split(whole)
        lead_mark = bool(_TYPED_MARK.match(whole))
        for i, piece in enumerate(pieces):
            piece = piece.strip()
            if piece:
                add("item" if (i > 0 or lead_mark) else kind, piece)

    def _inline(
        self, el: Any, state: dict[str, _Line], styled: bool, flush, kind: str, ctx: _Ctx
    ) -> None:
        """Inline markup inside a line. ``state["line"]`` is the open line; a break inside
        the markup closes it and opens a new one, so it is looked up every time."""
        tag = _local(el.tag)
        if tag == "br":
            flush()
        elif tag in _SKIP:
            return
        elif tag in _INLINE:
            st = styled or _styled(el)
            state["line"].add(el.text, st)
            for ch in el:
                self._inline(ch, state, st, flush, kind, ctx)
                state["line"].add(ch.tail, st)
        else:  # a block inside a line: end the line, then read the block
            flush()
            self._child(el, kind, ctx)

    # -- containers ------------------------------------------------------------------------------
    def container(self, el: Any, kind: str, ctx: _Ctx) -> None:
        """One paragraph, item, cell, caption or title (or a section's loose text), by lines."""
        styled = _styled(el)
        state = {"line": _Line()}

        def flush() -> None:
            self._emit(state["line"], kind, ctx)
            state["line"] = _Line()

        state["line"].add(el.text, styled)
        for ch in el:
            tag = _local(ch.tag)
            if tag in ("list", "table", "paragraph", "caption"):
                flush()
                self._child(ch, kind, ctx)
            elif tag == "br":
                flush()
            elif tag not in _SKIP:
                self._inline(ch, state, styled, flush, kind, ctx)
            state["line"].add(ch.tail, styled)
        flush()

    def _child(self, el: Any, kind: str, ctx: _Ctx) -> None:
        """A block element met inside a container; nested paragraphs keep an item's or a
        cell's kind."""
        tag = _local(el.tag)
        if tag == "list":
            inner = _Ctx(ctx.depth, ctx.list_depth + 1, ctx.table, ctx.highlights)
            item_kind = "data_cell" if kind == "data_cell" else "item"
            for ch in el:
                t = _local(ch.tag)
                if t == "item":
                    self.container(ch, item_kind, inner)
                elif t == "caption":
                    self.container(ch, "caption", inner)
        elif tag == "table":
            self.table(el, ctx)
        elif tag == "paragraph":
            nested = kind if kind in ("item", "cell", "data_cell") else "paragraph"
            self.container(el, nested, ctx)
        elif tag == "caption":
            self.container(el, "caption", ctx)

    def table(self, el: Any, ctx: _Ctx) -> None:
        self.tables += 1
        here = _Ctx(ctx.depth, ctx.list_depth, self.tables, ctx.highlights)
        cells = _own_cells(el)
        flat = [text.clean("".join(c.itertext())) for c in cells]
        kind = "data_cell" if text.is_data_table([c for c in flat if c]) else "cell"
        for ch in el:
            if _local(ch.tag) == "caption":
                self.container(ch, "caption", here)
        for c in cells:
            self.container(c, kind, here)

    def section(self, sec: Any, depth: int) -> None:
        ctx = _Ctx(depth)
        for ch in sec:
            tag = _local(ch.tag)
            if tag == "title":
                self.container(ch, "title", ctx)
            elif tag == "text":
                self.container(ch, "paragraph", ctx)
            elif tag == "excerpt":
                hl = _Ctx(depth, highlights=True)
                for h in ch:
                    for t in h if _local(h.tag) == "highlight" else ():
                        if _local(t.tag) == "text":
                            self.container(t, "paragraph", hl)
            elif tag == "component":
                for sub in ch:
                    if _local(sub.tag) == "section":
                        self.section(sub, depth + 1)


def _own_cells(table: Any) -> list[Any]:
    """The cells of one table, row by row, without the cells of tables nested in them."""
    cells: list[Any] = []

    def rows(el: Any) -> None:
        for ch in el:
            tag = _local(ch.tag)
            if tag in ("thead", "tbody", "tfoot"):
                rows(ch)
            elif tag == "tr":
                cells.extend(c for c in ch if _local(c.tag) in ("td", "th"))

    rows(table)
    return cells


def _attr(root: Any, tag: str, name: str) -> str | None:
    el = root.find(f"{NS}{tag}")
    return el.get(name) if el is not None else None


def _top_sections(root: Any) -> list[tuple[str, Any]]:
    """(field, section) for every section of a known code that is not inside another section
    of the same field, in document order."""
    out: list[tuple[str, Any]] = []

    def walk(el: Any, open_fields: frozenset[str]) -> None:
        for ch in el:
            if _local(ch.tag) == "section":
                code = ch.find(f"{NS}code")
                f = _FIELD_OF.get(code.get("code") if code is not None else "")
                if f and f not in open_fields:
                    out.append((f, ch))
                walk(ch, open_fields | {f} if f else open_fields)
            else:
                walk(ch, open_fields)

    walk(root, frozenset())
    return out


def identity(xml: bytes) -> dict[str, Any]:
    """Set id, version, document id, effective time and document type of one SPL document."""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise SplError(f"not well-formed XML ({exc})") from exc
    return _identity(root)


IDENTITY = ("set_id", "version", "document_id", "effective_time", "document_type")


def _identity(root: Any) -> dict[str, Any]:
    set_id = _attr(root, "setId", "root")
    if not set_id:
        raise SplError("the document has no setId")
    version = _attr(root, "versionNumber", "value")
    return {
        "set_id": set_id.lower(),
        "version": int(version) if version and version.isdigit() else None,
        "document_id": (_attr(root, "id", "root") or "").lower() or None,
        "effective_time": _attr(root, "effectiveTime", "value"),
        "document_type": _attr(root, "code", "code"),
    }


def parse_document(
    xml: bytes, keep: bool | Callable[[dict[str, Any]], bool] = True
) -> dict[str, Any]:
    """Identity and (with ``keep``) the blocks of every known field of one SPL document.

    ``keep`` may be a function of the identity, so a document is parsed only once and its
    sections read only when they are wanted.

    Returns ``{"set_id", "version", "document_id", "effective_time", "document_type",
    "fields": {field: [Block, ...]}, "codes": Counter of every section code seen}``. A field
    found in several places has the blocks of each, in document order.
    """
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise SplError(f"not well-formed XML ({exc})") from exc
    out: dict[str, Any] = {**_identity(root), "fields": {}, "codes": Counter()}
    if not (keep(out) if callable(keep) else keep):
        return out
    for sec in root.iter(f"{NS}section"):
        code = sec.find(f"{NS}code")
        out["codes"][code.get("code") if code is not None else "(none)"] += 1
    for f, sec in _top_sections(root):
        w = _Walker()
        w.section(sec, 0)
        out["fields"].setdefault(f, []).extend(w.blocks)
    return out


def section_blocks(fields: dict[str, list[Block]]) -> dict[str, list[Block]]:
    """The blocks of each corpus section (the names of :mod:`plainpairs.schema`), joined from
    its fields as the JSON reader joins them."""
    out: dict[str, list[Block]] = {}
    for section, sources in PRESCRIBER_SOURCES.items():
        blocks = [b for s in sources for b in fields.get(s, [])]
        if blocks:
            out[section] = blocks
    if "warnings_and_precautions" not in out:
        blocks = [b for s in OLDER_WARNINGS for b in fields.get(s, [])]
        if blocks:
            out["warnings_and_precautions"] = blocks
    for name, source in PATIENT_SOURCES.items():
        if fields.get(source):
            out[name] = list(fields[source])
    return out


# --- comparing words with the JSON --------------------------------------------------------------

_TOKEN = re.compile(r"[0-9a-z]+")


def tokens(s: str) -> list[str]:
    """Lowercase letters-and-digits tokens of a cleaned text (case, marks and spaces ignored)."""
    import unicodedata

    return _TOKEN.findall(unicodedata.normalize("NFKD", text.clean(s)).casefold())


def all_text(blocks: list[Block]) -> str:
    """Every word of a section's blocks, titles and data cells included, in order."""
    return " ".join(b.text for b in blocks)


#: Word overlap (Dice over the bags of tokens) at or above which two texts "nearly" match.
NEAR = 0.98


def word_match(xml_text: str, json_text: str) -> dict[str, Any]:
    """How far the words of the XML and of the JSON agree: ``exact`` (the same tokens in the
    same order), ``near`` (Dice of the token bags at least :data:`NEAR`) or ``not``."""
    a, b = tokens(xml_text), tokens(json_text)
    if a == b:
        return {"match": "exact", "dice": 1.0, "xml_tokens": len(a), "json_tokens": len(b)}
    ca, cb = Counter(a), Counter(b)
    shared = sum((ca & cb).values())
    dice = 2 * shared / (len(a) + len(b)) if (a or b) else 1.0
    return {
        "match": "near" if dice >= NEAR else "not",
        "dice": round(dice, 4),
        "xml_tokens": len(a),
        "json_tokens": len(b),
    }


# --- sentences and measures from structure ------------------------------------------------------


def units(blocks: list[Block]) -> list[str]:
    """Sentences from structure: each prose block cut by ``s1``, and every block ends one."""
    out: list[str] = []
    for b in blocks:
        if b.kind in PROSE_KINDS:
            out.extend(readability.sentences(b.text, "s1"))
    return out


def measure(blocks: list[Block]) -> dict[str, Any]:
    """The reading measures of a section from its structure, with counts of its blocks."""
    m = readability.measure_units(units(blocks))
    kinds = Counter(b.kind for b in blocks)
    return {
        **m,
        **{f"blocks_{k}": kinds.get(k, 0) for k in BLOCK_KINDS},
        "blocks_in_highlights": sum(1 for b in blocks if b.highlights),
        "subsection_titles": sum(1 for b in blocks if b.kind == "title" and b.depth > 0),
    }
