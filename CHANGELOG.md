# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- The repository: Apache-2.0 license, README, NOTICE and a draft citation file.
- CI: ruff and pytest on Python 3.10 to 3.13, with every action pinned to a commit.
- Runtime dependencies: pydantic (frozen record models) and requests (HTTP).
- Commands: `fetch-page` and `quotes-check` (source pages kept as evidence, quotes checked
  word for word), `counts` (label API counts, resumable), `download-part` (one bulk part,
  200 MB at most).
- A label parser: one row per label with its identity, its prescriber sections and its
  patient texts, cleaned of markup with headings kept, and its tables as plain rows.
- Readability measures (Flesch-Kincaid grade, Flesch reading ease, SMOG) and the standard
  headings of Medication Guides found by their wording.
- `download-all`: every part of one export, checked against a hash manifest and the listing,
  resumable.
- A second sentence rule (`s2`) that breaks at list marks, numbered headings and headings in
  capitals; measures now also give the share of long sentences and counts of numbers and
  percentages.
- Runtime dependency: pyarrow, to write the tables as Parquet.
- `build`: the record layer (`labels`, `patient_texts`, `section_pairs`, `excluded_otc`) and
  the text layer (`text_prescriber`, `text_patient`) as Parquet, from the parts of one export.
- `sheet` and `sheet-check`: the blind topic-check hand sheet (.xlsx with a dropdown, its key
  kept apart) and its scores per heading, with `docs/hand-sheet-guide.md`.
- `release-check` and `text` (rebuild the text layer from the record layer and the bulk files,
  confirmed by hash); the release switch (all, unmarked, none).
- A reader for DailyMed's SPL XML, used to compare its structure with the JSON on 20 labels.
- Runtime dependency: defusedxml, because SPL XML comes from outside and is parsed without
  expanding entities or reading document type declarations.
- `stats`: aggregates of a built corpus (sizes, duplicates, medicines, grades by both sentence
  rules, headings, alignment shares, what each switch setting releases), no text.
- `docs/data-card.md` (DRAFT), `docs/xml-test.md` and `docs/hand-sheet-guide.md`; the schema
  and method now describe what the build does.
- A product name per label (`product_name`, with its source and rule), read from the label's
  structured product data and kept apart from the medicine key.
- "Listed now" flags in `labels`: in the current NDC directory, and served by DailyMed, from
  two small official lists (`listed-download`, then `build --listed`).
- `codes`: the first rule-based codes of wording, as counts per text in a `codes` table
  (`docs/codebook.md`, version 0, a draft); `release-check` inspects the table when present.
- `changes`: what changed between two builds' record layers, in a `changes` table; the build
  now writes every set id of its export (`export_ids.parquet`) so that a label that left the
  scope can be told from one withdrawn.
- `docs/benchmark-design.md` (DRAFT), replacing the benchmark sketch.

### Changed
- A heading followed at once by its restatement (the question, then "Before taking ..., tell
  your healthcare provider") is one heading with one body; `section_pairs` no longer has an
  empty "before" segment for each such guide.
- The hand sheet draws only segments of two sentences and 20 words or more, and never two rows
  from the same patient text; its guide opens with the one thing to judge.
- The mapping of "general information" to section 17 is marked as this project's choice.
- CI runs ruff and pytest on Python 3.12 for pushes and pull requests; the full matrix (3.10
  to 3.13) runs when started by hand, before a release.
- Reading-level figures are withdrawn from the data card and the sample note until text is
  measured with its structure.
- Only data tables (cells of 8 words or fewer) are cut from prose before it is measured;
  prose laid out in tables, as patient texts use it, stays.
- Labels typed over the counter are out of scope even when their sections look like a
  prescription format; they are listed in `excluded_otc`.
