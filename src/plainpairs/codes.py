"""Rule-based codes of wording (codebook version 0): counts per text, never the text.

Each code is a fixed rule over one cleaned text (a patient text or a prescriber section),
written to the record layer as counts. The rules, what they relate to and what they cannot see
are in ``docs/codebook.md``. They are PEMAT-informed text items, not PEMAT scores: the
instrument also rates layout and visual aids, which this corpus cannot see.

The rules read wording only. They never judge whether a statement is right, complete or safe.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from plainpairs import readability, text

CODE_VERSION = "0"

#: Base-form verbs that open an instruction, in patient texts and in prescriber sections.
VERBS = frozenset(
    """
    take use tell call ask talk read keep store stop avoid get go seek check wash throw
    dispose follow give swallow inject apply remove shake contact let make see bring carry
    wear drink eat chew crush split place hold insert put rinse discard protect wait write
    report continue start mix prepare open close pull push press turn twist attach clean dry
    wipe pinch breathe inhale exhale cover fill peel fold cut flush return change choose
    measure count look learn limit lie sit stand rotate record plan allow leave unscrew uncap
    recap select repeat drop tap lift set inspect warm refrigerate dilute dissolve pour stir
    sprinkle notify inform be have do stay try find show talk throw sign administer advise
    monitor discontinue reduce consider evaluate assess instruct counsel obtain adjust titrate
    initiate interrupt withhold resume perform correct treat ensure observe confirm
    reconstitute swirl withdraw verify test screen prescribe dispense educate encourage
    caution warn remind
    """.split()  # noqa: SIM905 - a word list reads better as text
)
#: A verb followed by one of these is a noun ("Use in pregnancy", "Contact with eyes").
_NOUN_NEXT = frozenset(
    "in of with and or is are was were has have may can should during after by for".split()  # noqa: SIM905
)
_OPENER_JUNK = re.compile(
    r"^(?:[\s\"'\u201c\u2018(\[*\-\u2013\u2014:;]|step\s+\d+[:.)]?|\d{1,2}[.)]|[a-z][.)](?=\s))+",
    re.I,
)
_NEGATION = re.compile(r"^(?:do\s+not|don['\u2019]t|never)\s+", re.I)
_CONDITIONAL = re.compile(r"^(?:if|when|before|after|while|until)\b[^,]{1,200},\s*", re.I)
_FIRST_WORD = re.compile(r"[A-Za-z]+")

YOU = re.compile(r"\b(?:you|your|yours|yourself|yourselves)\b", re.I)
PERCENT = re.compile(r"\d+(?:[.,\u2024]\d+)?\s?%|\bper ?cent\b", re.I)
_NUM_WORD = r"(?:\d[\d,]*|one|two|three|four|five|six|seven|eight|nine|ten)"
ONE_IN_N = re.compile(
    rf"\b{_NUM_WORD}\s+(?:in|out\s+of)\s+(?:every\s+)?"
    r"(?:\d[\d,]*|ten|a\s+hundred|one\s+hundred|hundred|a\s+thousand|one\s+thousand|thousand)\b",
    re.I,
)
FREQUENCY = re.compile(
    r"\b(?:once|twice|three\s+times|four\s+times|\d+\s+times|one\s+time|two\s+times)\s+"
    r"(?:a|per|each|every)\s+(?:day|week|month|year|night)\b"
    r"|\bevery\s+(?:\d+(?:\s*(?:to|-)\s*\d+)?\s+)?(?:hours?|days?|weeks?|months?)\b"
    r"|\b(?:each|every)\s+(?:day|week|month|morning|evening|night|other\s+day)\b"
    r"|\b(?:daily|weekly|monthly|nightly)\b"
    r"|\bq\.?\s?\d+\s?h\b",
    re.I,
)
DOSE = re.compile(
    r"(?<![\w.])\d+(?:[.,\u2024]\d+)?\s?"
    r"(?:mg/kg|mg/m2|mcg/kg|mg|mcg|\u00b5g|g|mL|ml|units?|IU|mEq|mmol)\b"
)
RISK = re.compile(
    r"\b(?:risks?|chances?|side\s+effects?|adverse\s+(?:reactions?|events?|effects?)|reactions?"
    r"|(?:may|can|could|might)\s+cause|occur(?:s|red)?|incidence|common(?:ly)?|rare(?:ly)?"
    r"|likely)\b",
    re.I,
)
NUMBER_IN_SENTENCE = re.compile(
    r"\d|%|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|half|hundred|thousand)\b", re.I
)
VAGUE_CORE = re.compile(r"\b(?:common|commonly|rare|rarely|may|can|some)\b", re.I)
VAGUE_EXTENDED = re.compile(
    r"\b(?:might|could|sometimes|often|usually|uncommon|frequent|frequently|occasional"
    r"|occasionally|likely|unlikely|possible|possibly)\b",
    re.I,
)
_BRACKET = re.compile(r"\(([^()]{1,200})\)")
_BRACKET_SKIP_FIRST = frozenset(
    "see e.g. eg such including for especially like at in on from".split()  # noqa: SIM905
    + "to with by per if when or and also".split()  # noqa: SIM905
)
_ABBREVIATION = re.compile(r"[A-Z][A-Z0-9\-]{1,9}")
CALLED = re.compile(
    r"\b(?:also\s+)?called\b(?!\s+(?:your|you|911|a\s+doctor|the\s+doctor|right\s+away))"
    r"|\b(?:also\s+)?known\s+as\b",
    re.I,
)
CONTACT_VERB = re.compile(
    r"\b(?:call|contact|tell|talk\s+(?:to|with)|ask|notify|inform|report|go\s+to"
    r"|get\s+(?:emergency\s+|medical\s+)?(?:help|treatment|care)"
    r"|seek\s+(?:emergency\s+|medical\s+)?(?:help|attention|care|treatment))\b",
    re.I,
)
CONTACT_WHOM = re.compile(
    r"\b(?:doctors?|health\s?care\s+providers?|providers?|pharmacists?|nurses?|prescribers?"
    r"|poison\s+control|911|emergency|hospital|FDA)\b",
    re.I,
)
CONTACT_WHEN = re.compile(
    r"\b(?:if|when|right\s+away|immediately|at\s+once|as\s+soon\s+as|before|after|while|within"
    r"|during|until|promptly|urgently)\b",
    re.I,
)
LONG = readability.LONG_SENTENCE  # 20 words
VERY_LONG = 40
LONG_SECTION = 250

#: The columns of one row of codes, in order (all counts; see docs/codebook.md).
FIELDS = (
    "words",
    "sentences",
    "you_words",
    "sentences_with_you",
    "command_sentences",
    "conditional_commands",
    "distinct_actions",
    "percentages",
    "one_in_n",
    "frequencies",
    "doses",
    "risk_sentences",
    "risk_sentences_with_number",
    "vague_core",
    "vague_extended",
    "explained_in_brackets",
    "explained_called",
    "abbreviations_in_brackets",
    "sentences_over_20",
    "sentences_over_40",
    "longest_sentence_words",
    "sections",
    "longest_section_words",
    "sections_over_250",
    "contact_sentences",
    "contact_sentences_with_when",
)
PATIENT_KINDS = ("medication_guide", "patient_package_insert", "instructions_for_use")


def command_verb(sentence: str) -> str | None:
    """The action an instruction names, or ``None``: ``take``, or ``not take`` for a ban.

    The sentence must open with a base-form verb from :data:`VERBS` (after list marks, quote
    marks, "Step 1:" and the like), or with "Do not", "Don't" or "Never" and such a verb. A verb
    followed by a word such as "in", "of" or "is" is read as a noun and not counted.
    """
    s = _OPENER_JUNK.sub("", sentence).strip()
    neg = _NEGATION.match(s)
    if neg:
        s = s[neg.end() :]
    words = _FIRST_WORD.findall(s[:80])
    if not words:
        return None
    first = words[0].lower()
    if first not in VERBS or (first == "do" and not neg):
        return None
    if len(words) > 1 and words[1].lower() in _NOUN_NEXT:
        return None
    return f"not {first}" if neg else first


def conditional_verb(sentence: str) -> str | None:
    """The action of "If ..., call ..." (a condition, a comma, then an instruction)."""
    m = _CONDITIONAL.match(_OPENER_JUNK.sub("", sentence).strip())
    return command_verb(sentence[m.end() :]) if m else None


def _bracket_kind(inner: str) -> str | None:
    inner = inner.strip()
    if _ABBREVIATION.fullmatch(inner):
        return "abbreviation"
    words = readability.words(inner)
    # one token (a name, a pronunciation such as "zor-VAN") or any digit: not an explanation
    if len(inner.split()) < 2 or re.search(r"\d", inner):
        return None
    if words[0].lower() in _BRACKET_SKIP_FIRST or inner.lower().startswith(("e.g", "i.e")):
        return "explained" if inner.lower().startswith("i.e") else None
    lower = sum(w.islower() for w in words)
    return "explained" if lower * 2 >= len(words) else None


def code_text(t: str, kind: str = "patient") -> dict[str, int]:
    """The codes of one text. ``kind`` is ``patient`` (sections counted at its headings) or
    ``prescriber``."""
    sents = readability.sentences(t)
    lengths = [len(readability.words(s)) for s in sents]
    out: Counter[str] = Counter()
    out["words"] = len(readability.words(t))
    out["sentences"] = len(sents)
    out["you_words"] = len(YOU.findall(t))
    actions: set[str] = set()
    for s, n in zip(sents, lengths, strict=True):
        out["sentences_with_you"] += bool(YOU.search(s))
        verb = command_verb(s)
        if verb:
            out["command_sentences"] += 1
            actions.add(verb)
        else:
            cond = conditional_verb(s)
            if cond:
                out["conditional_commands"] += 1
                actions.add(cond)
        if RISK.search(s):
            out["risk_sentences"] += 1
            out["risk_sentences_with_number"] += bool(NUMBER_IN_SENTENCE.search(s))
        out["sentences_over_20"] += n > LONG
        out["sentences_over_40"] += n > VERY_LONG
        if CONTACT_VERB.search(s) and CONTACT_WHOM.search(s):
            out["contact_sentences"] += 1
            out["contact_sentences_with_when"] += bool(CONTACT_WHEN.search(s))
    out["distinct_actions"] = len(actions)
    out["longest_sentence_words"] = max(lengths, default=0)
    out["percentages"] = len(PERCENT.findall(t))
    out["one_in_n"] = len(ONE_IN_N.findall(t))
    out["frequencies"] = len(FREQUENCY.findall(t))
    out["doses"] = len(DOSE.findall(t))
    out["vague_core"] = len(VAGUE_CORE.findall(t))
    out["vague_extended"] = len(VAGUE_EXTENDED.findall(t))
    for m in _BRACKET.finditer(t):
        k = _bracket_kind(m.group(1))
        if k == "explained":
            out["explained_in_brackets"] += 1
        elif k == "abbreviation":
            out["abbreviations_in_brackets"] += 1
    out["explained_called"] = len(CALLED.findall(t))
    if kind == "patient":
        spans = text.segment_spans(t)
        sizes = [len(readability.words(t[head_end:end])) for _k, _s, head_end, end in spans]
        out["sections"] = len(spans)
        out["longest_section_words"] = max(sizes, default=0)
        out["sections_over_250"] = sum(n > LONG_SECTION for n in sizes)
    return {f: int(out[f]) for f in FIELDS}


# --- the codes table ----------------------------------------------------------------------------

SCHEMA = pa.schema(
    [
        ("source", pa.string()),
        ("export_date", pa.string()),
        ("set_id", pa.string()),
        ("version", pa.int32()),
        ("section", pa.string()),
        ("side", pa.string()),
        ("patient_text_id", pa.string()),
        ("code_version", pa.string()),
        *[(f, pa.int32()) for f in FIELDS],
    ]
)


def _rows(batch: list[dict[str, Any]], side: str) -> list[dict[str, Any]]:
    out = []
    for r in batch:
        if r["part"] != "text":
            continue
        t = r["text"]
        out.append(
            {
                "source": r["source"],
                "export_date": r["export_date"],
                "set_id": r["set_id"],
                "version": r["version"],
                "section": r["section"],
                "side": side,
                "patient_text_id": (
                    f"{r['section']}:{text.core_hash(t)}" if side == "patient" else None
                ),
                "code_version": CODE_VERSION,
                **code_text(t, side),
            }
        )
    return out


def _job(job: tuple[list[dict[str, Any]], str]) -> list[dict[str, Any]]:
    return _rows(*job)


_COLUMNS = ["source", "export_date", "set_id", "version", "section", "part", "text"]


def _batches(path: Path, side: str, size: int) -> Iterator[tuple[list[dict[str, Any]], str]]:
    for b in pq.ParquetFile(path).iter_batches(batch_size=size, columns=_COLUMNS):
        yield b.to_pylist(), side


def build(tables_dir: Path, workers: int = 1, batch_size: int = 2000, log=print) -> int:
    """Code every text of the text layer in ``tables_dir``; writes ``codes.parquet`` there."""
    tables_dir = Path(tables_dir)
    jobs: Iterable[tuple[list[dict[str, Any]], str]] = (
        job
        for side, name in (("patient", "text_patient"), ("prescriber", "text_prescriber"))
        for job in _batches(tables_dir / f"{name}.parquet", side, batch_size)
    )
    n = 0
    with pq.ParquetWriter(tables_dir / "codes.parquet", SCHEMA, compression="zstd") as w:
        if workers <= 1:
            results: Iterable[list[dict[str, Any]]] = map(_job, jobs)
            for rows in results:
                w.write_table(pa.Table.from_pylist(rows, SCHEMA))
                n += len(rows)
        else:
            from concurrent.futures import ProcessPoolExecutor

            with ProcessPoolExecutor(max_workers=workers) as pool:
                for rows in pool.map(_job, jobs):
                    w.write_table(pa.Table.from_pylist(rows, SCHEMA))
                    n += len(rows)
                    if n and n % 50_000 < len(rows):
                        log(f"codes: {n:,} texts coded")
    log(f"codes: {n:,} texts coded into {tables_dir / 'codes.parquet'}")
    return n
