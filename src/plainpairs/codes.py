"""Rule-based codes of wording (codebook version 1): counts per text, never the text.

Each code is a fixed rule over one cleaned text (a patient text or a prescriber section),
written to the record layer as counts. The rules, what they relate to and what they cannot see
are in ``docs/codebook.md``. They are PEMAT-informed text items, not PEMAT scores: the
instrument also rates layout and visual aids, which this corpus cannot see.

The rules read wording only. They never judge whether a statement is right, complete or safe.

Each code is ``trusted`` or ``experimental`` (:data:`CODEBOOK`), from a development check by
hand (20 hits and 20 misses for each code first doubted, 10 and 10 for the others; a
development check, not a validation). ``codes.parquet`` holds only the trusted codes, the
candidates for a release; ``codes_experimental.parquet`` holds the others and is never part of
a release. For labels whose structure comes from DailyMed's XML (configuration ``current``),
the length codes are also given from the structure (``structured_*``).
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

CODE_VERSION = "1"

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
#: Version 1: a number that gives a risk's size: a percentage, "1 in N" or "N of M", a rate
#: ("per 1,000"), a count of people ("12 patients"), or a multiple ("twice as likely").
_N = r"\d[\d,]*(?:[.\u2024]\d+)?"
RISK_SIZE = re.compile(
    rf"{_N}\s?%|\bper ?cent\b"
    rf"|\b{_NUM_WORD}\s+(?:in|out\s+of|of)\s+(?:every\s+)?{_N}\b"
    rf"|\bper\s+{_N}\b"
    rf"|\b{_N}\s+(?:of\s+(?:the\s+)?)?(?:patients|people|persons|subjects|women|men|children"
    r"|infants|adults|participants|cases|users|pregnancies|births)\b"
    rf"|\b(?:twice|{_N}(?:-|\s)?(?:fold|times))\s+(?:as|more|higher|greater|lower|less|the)\b",
    re.I,
)
#: Cross-references ("[see Warnings (5.1)]", "(5.1, 6)") and doses are left out before a
#: sentence is read for a risk word or a risk size.
_CROSS_REF = re.compile(
    r"\[\s*see[^\]]*\]|\(\s*see[^)]*\)|\(\s*\d+(?:[.\u2024]\d+)*(?:\s*,\s*\d+(?:[.\u2024]\d+)*)*\s*\)",
    re.I,
)
VAGUE_CORE = re.compile(
    # version 1: not the month ("May 2024") and not the permission to report side effects
    r"\b(?:common|commonly|rare|rarely|some)\b"
    r"|\b(?:may|can)\b(?!\s+(?:\d|report\b))",
    re.I,
)
VAGUE_EXTENDED = re.compile(
    r"\b(?:might|could|sometimes|often|usually|uncommon|frequent|frequently|occasional"
    r"|occasionally|likely|unlikely|possible|possibly)\b",
    re.I,
)
_BRACKET = re.compile(r"\(([^()]{1,200})\)")
_BRACKET_SKIP_FIRST = frozenset(
    "see e.g. eg such including for especially like at in on from".split()  # noqa: SIM905
    + "to with by per if when or and also".split()  # noqa: SIM905
    # version 1: qualifiers and asides, not explanations
    + "sometimes particularly mostly usually often post not only both either about".split()  # noqa: SIM905
    + "approximately up less more greater within than".split()  # noqa: SIM905
)
#: A bracket right after a trademark sign or a capitalized word names a product ("BRAND
#: (generic name)"), and a bracket of short syllables is a pronunciation ("(lor az' e pam)").
_AFTER_NAME = re.compile(r"(?:[\u00ae\u2122]|\b[A-Z][A-Za-z0-9\-]*)\s*$")
_SYLLABLES = re.compile(r"[A-Za-z]{1,4}(?:['\u2019\-][A-Za-z]{0,4})*")
_TERM = re.compile(r"[a-z][a-z\-]{3,}")
_ABBREVIATION = re.compile(r"[A-Z][A-Z0-9\-]{1,9}")
CALLED = re.compile(
    r"\b(?:also\s+)?called\b(?!\s+(?:your|you|911|a\s+doctor|the\s+doctor|right\s+away))"
    r"|\b(?:also\s+)?known\s+as\b",
    re.I,
)
CONTACT_VERB = re.compile(
    r"\b(?:call|contact|tell|talk\s+(?:to|with)|ask|notify|inform|report|go\s+to"
    r"|get\s+(?:emergency\s+|medical\s+)?(?:help|treatment|care)"
    r"|seek\s+(?:emergency\s+|medical\s+)?(?:help|attention|care|treatment))\b"
    # version 1: "inform patients", "tell you" are not the reader contacting someone
    r"(?!\s+(?:patients?|caregivers?|famil(?:y|ies)|them|the\s+patients?|you\b))",
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


def _bracket_kind(inner: str, before: str = "") -> str | None:
    """``explained``, ``abbreviation`` or ``None`` for one bracket; ``before`` is the text just
    before it (version 1 reads it to tell names and plain descriptions apart)."""
    inner = inner.strip()
    if _ABBREVIATION.fullmatch(inner):
        return "abbreviation"
    words = readability.words(inner)
    if re.search(r"\d", inner) or not words or _AFTER_NAME.search(before[-40:]):
        return None
    tokens = inner.split()
    if len(tokens) < 2:
        # version 1: a term after its plain description, "trouble sleeping (insomnia)"
        lead = readability.words(before[-60:])
        if _TERM.fullmatch(inner) and len(lead) >= 2 and lead[-1].islower():
            return "explained"
        return None
    if all(_SYLLABLES.fullmatch(t) for t in tokens) and re.search(r"['\u2019\-]", inner):
        return None  # a pronunciation
    first = words[0].lower()
    if first in _BRACKET_SKIP_FIRST or first in VERBS or inner.lower().startswith(("e.g", "i.e")):
        return "explained" if inner.lower().startswith("i.e") else None
    lower = sum(w.islower() for w in words)
    return "explained" if lower * 2 >= len(words) else None


def count_one_in_n(t: str) -> int:
    """ "1 in N" phrases; version 1 leaves out packaging counts such as "30 in 1", where the
    second number is not larger than the first."""
    n = 0
    for m in ONE_IN_N.finditer(t):
        nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", m.group(0))]
        if len(nums) == 2 and nums[1] <= nums[0]:
            continue
        n += 1
    return n


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
        plain = _CROSS_REF.sub(" ", s)
        if RISK.search(plain):
            out["risk_sentences"] += 1
            out["risk_sentences_with_number"] += bool(RISK_SIZE.search(DOSE.sub(" ", plain)))
        out["sentences_over_20"] += n > LONG
        out["sentences_over_40"] += n > VERY_LONG
        if CONTACT_VERB.search(s) and CONTACT_WHOM.search(s):
            out["contact_sentences"] += 1
            out["contact_sentences_with_when"] += bool(CONTACT_WHEN.search(s))
    out["distinct_actions"] = len(actions)
    out["longest_sentence_words"] = max(lengths, default=0)
    out["percentages"] = len(PERCENT.findall(t))
    out["one_in_n"] = count_one_in_n(t)
    out["frequencies"] = len(FREQUENCY.findall(t))
    out["doses"] = len(DOSE.findall(t))
    out["vague_core"] = len(VAGUE_CORE.findall(t))
    out["vague_extended"] = len(VAGUE_EXTENDED.findall(t))
    for m in _BRACKET.finditer(t):
        k = _bracket_kind(m.group(1), t[max(0, m.start() - 60) : m.start()])
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


# --- status of each code (codebook version 1) ----------------------------------------------------

#: Counts that other codes are shares of; not codes themselves. ``sentences`` is by rule ``s2``.
COUNTS = ("words", "sentences")
#: The length codes read from structure, for labels whose structure comes from DailyMed's XML.
STRUCTURED_FIELDS = (
    "structured_sentences",
    "structured_sentences_over_20",
    "structured_sentences_over_40",
    "structured_longest_sentence_words",
    "structured_parts",
    "structured_longest_part_words",
    "structured_parts_over_250",
)
#: code -> (columns, status). The status, the reason and the error counts of the development
#: check are in docs/codebook.md; changing a status changes the code version.
CODEBOOK: dict[str, tuple[tuple[str, ...], str]] = {
    "direct_address": (("you_words", "sentences_with_you"), "trusted"),
    "commands": (("command_sentences", "conditional_commands"), "trusted"),
    "distinct_actions": (("distinct_actions",), "trusted"),
    "percentages": (("percentages",), "trusted"),
    "one_in_n": (("one_in_n",), "trusted"),
    "frequencies": (("frequencies",), "trusted"),
    "doses": (("doses",), "trusted"),
    "risk_with_number": (("risk_sentences", "risk_sentences_with_number"), "experimental"),
    "vague_words": (("vague_core", "vague_extended"), "experimental"),
    "explained_terms": (
        ("explained_in_brackets", "explained_called", "abbreviations_in_brackets"),
        "experimental",
    ),
    "long_sentences": (
        ("sentences_over_20", "sentences_over_40", "longest_sentence_words"),
        "experimental",
    ),
    "long_sections": (("sections", "longest_section_words", "sections_over_250"), "experimental"),
    "whom_to_call": (("contact_sentences", "contact_sentences_with_when"), "trusted"),
    "long_sentences_structured": (
        (
            "structured_sentences",
            "structured_sentences_over_20",
            "structured_sentences_over_40",
            "structured_longest_sentence_words",
        ),
        "trusted",
    ),
    "long_parts_structured": (
        ("structured_parts", "structured_longest_part_words", "structured_parts_over_250"),
        "experimental",
    ),
}
STATUS = {col: status for cols, status in CODEBOOK.values() for col in cols}
TRUSTED = tuple(c for c in (*FIELDS, *STRUCTURED_FIELDS) if STATUS.get(c) == "trusted")
EXPERIMENTAL = tuple(c for c in (*FIELDS, *STRUCTURED_FIELDS) if STATUS.get(c) == "experimental")


# --- the codes table ----------------------------------------------------------------------------

_IDS = [
    ("source", pa.string()),
    ("export_date", pa.string()),
    ("set_id", pa.string()),
    ("version", pa.int32()),
    ("section", pa.string()),
    ("side", pa.string()),
    ("patient_text_id", pa.string()),
    ("code_version", pa.string()),
    ("configuration", pa.string()),
    ("structure_source", pa.string()),
]
#: ``codes.parquet``: the trusted codes only (release candidates).
SCHEMA = pa.schema([*_IDS, *[(f, pa.int32()) for f in COUNTS], *[(f, pa.int32()) for f in TRUSTED]])
#: ``codes_experimental.parquet``: the experimental codes; never released.
EXPERIMENTAL_SCHEMA = pa.schema([*_IDS, *[(f, pa.int32()) for f in EXPERIMENTAL]])
_FROM_STRUCTURE = {
    "structured_sentences": "sentences",
    "structured_sentences_over_20": "sentences_over_20",
    "structured_sentences_over_40": "sentences_over_40",
    "structured_longest_sentence_words": "longest_sentence_words",
    "structured_parts": "parts",
    "structured_longest_part_words": "longest_part_words",
    "structured_parts_over_250": "parts_over_250",
}


def _rows(
    batch: list[dict[str, Any]],
    side: str,
    config: dict[str, str] | None = None,
    structured: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    out = []
    for r in batch:
        if r["part"] != "text":
            continue
        t = r["text"]
        conf = (config or {}).get(r["set_id"])
        st = (structured or {}).get((r["set_id"], r["section"])) if conf == "current" else None
        row = {
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
            "configuration": conf,
            "structure_source": "dailymed_xml" if st is not None else "json",
            **code_text(t, side),
        }
        for col, key in _FROM_STRUCTURE.items():
            row[col] = st.get(key) if st is not None else None
        out.append(row)
    return out


def _job(job: tuple[Any, ...]) -> list[dict[str, Any]]:
    return _rows(*job)


_COLUMNS = ["source", "export_date", "set_id", "version", "section", "part", "text"]


def _batches(path: Path, side: str, size: int, config, structured) -> Iterator[tuple[Any, ...]]:
    by_id: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for key, st in (structured or {}).items():
        by_id.setdefault(key[0], {})[key] = st
    for b in pq.ParquetFile(path).iter_batches(batch_size=size, columns=_COLUMNS):
        rows = b.to_pylist()
        ids = {r["set_id"] for r in rows}
        conf = {k: config[k] for k in ids if k in config} if config else None
        st = {k: v for i in ids for k, v in by_id.get(i, {}).items()} if by_id else None
        yield rows, side, conf, st


def load_structure(tables_dir: Path, structure_path: Path | None) -> tuple[dict, dict]:
    """Each label's configuration (from ``labels``), and the structured length codes of the
    sections whose words agree with the JSON (from the structure table)."""
    labels = pq.read_table(Path(tables_dir) / "labels.parquet")
    config: dict[str, str] = {}
    if "configuration" in labels.column_names:
        config = dict(
            zip(labels["set_id"].to_pylist(), labels["configuration"].to_pylist(), strict=True)
        )
    structured: dict[tuple[str, str], dict[str, Any]] = {}
    if structure_path is not None:
        for r in pq.read_table(structure_path).to_pylist():
            st = r["structured"]
            if st and st.get("sentences") is not None:
                structured[(r["set_id"], r["section"])] = st
    return config, structured


def build(
    tables_dir: Path,
    workers: int = 1,
    batch_size: int = 2000,
    log=print,
    structure_path: Path | None = None,
) -> int:
    """Code every text of the text layer in ``tables_dir``: the trusted codes to
    ``codes.parquet``, the experimental ones to ``codes_experimental.parquet``."""
    tables_dir = Path(tables_dir)
    config, structured = load_structure(tables_dir, structure_path)
    jobs: Iterable[tuple[Any, ...]] = (
        job
        for side, name in (("patient", "text_patient"), ("prescriber", "text_prescriber"))
        for job in _batches(tables_dir / f"{name}.parquet", side, batch_size, config, structured)
    )
    n = 0
    trusted_cols = SCHEMA.names
    exp_cols = EXPERIMENTAL_SCHEMA.names
    with (
        pq.ParquetWriter(tables_dir / "codes.parquet", SCHEMA, compression="zstd") as w,
        pq.ParquetWriter(
            tables_dir / "codes_experimental.parquet", EXPERIMENTAL_SCHEMA, compression="zstd"
        ) as wx,
    ):

        def write(rows: list[dict[str, Any]]) -> None:
            w.write_table(
                pa.Table.from_pylist([{k: r[k] for k in trusted_cols} for r in rows], SCHEMA)
            )
            wx.write_table(
                pa.Table.from_pylist(
                    [{k: r[k] for k in exp_cols} for r in rows], EXPERIMENTAL_SCHEMA
                )
            )

        if workers <= 1:
            for rows in map(_job, jobs):
                write(rows)
                n += len(rows)
        else:
            from concurrent.futures import ProcessPoolExecutor

            with ProcessPoolExecutor(max_workers=workers) as pool:
                for rows in pool.map(_job, jobs):
                    write(rows)
                    n += len(rows)
                    if n and n % 50_000 < len(rows):
                        log(f"codes: {n:,} texts coded")
    log(
        f"codes: {n:,} texts coded into {tables_dir / 'codes.parquet'} (trusted) and "
        "codes_experimental.parquet"
    )
    return n
