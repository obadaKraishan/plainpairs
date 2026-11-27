# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-11-27

The first weekly update and the first version with the easy-access files. The corpus, version
0.2.0, is on Hugging Face with the tag `v0.2.0`: built from the openFDA drug label export of
2026-11-26, with DailyMed's full release of 2026-11-13 and its update files through 2026-11-25;
16 configs, 1,410,823 rows, 563.7 MB of Parquet, and 21 easy-access files (789.8 MB). Against
0.1.0: 41 new labels, 2 that left scope, none withdrawn, 126 with changed texts, 125 new
versions with the same texts, 181 changes to record fields only; 7 labels moved from
`unlisted` to `current`. The NCI configuration is carried over unchanged (the same SHA-256).
It was delivered as a pull request on the dataset, which the maintainer merged.

### Added
- `docs/paper-facts.md`: every figure the card and the method give for version 0.1.0 (sizes per
  configuration, the switch, reading levels per configuration and basis, the trusted codes and
  their check, the alignment sheet per heading key, the NCI pairs, the limits), each with the
  file it comes from and its date. Figures only.
- `sheet-recheck`: the same pairs as a hand sheet's key, in a new order drawn with a new seed,
  with blank answers and a separate key, for the same coder's second pass. It reads only the
  key, never the answers.
- The Zenodo DOI of the software and documents (10.5281/zenodo.24267450, all versions; version
  0.1.0 is 10.5281/zenodo.24267451): a badge and a "How to cite" section in the README,
  `doi`, `identifiers` and the release date in `CITATION.cff`, and the dataset card's "How to
  cite".
- The data paper, arXiv:2611.21160 (doi:10.48550/arXiv.2611.21160), as the first citation:
  "How to cite" in the README, the dataset card (every version's, from constants in `pack`),
  the Kaggle description and `docs/data-card.md` asks for the paper first, with a BibTeX entry,
  then the dataset and its version, then the Zenodo DOI; `CITATION.cff`'s `preferred-citation`
  is the paper and the dataset's version is under `references`; `.zenodo.json` names the paper
  (`isDescribedBy`) for the next release's Zenodo record; an arXiv badge and a "Paper" project
  link. The pack and Kaggle checks fail when the paper is missing or cited after the dataset.
- The Kaggle mirror's page, built by the pack (`plainpairs.kaggle_meta`): a Markdown
  description with headings (what PlainPairs is; a bold "Not medical information" line; what is
  inside, with the 18 files and their rows; how to load one table; sources, terms and credit;
  limits; how to cite, with the paper first and its BibTeX entry; links), a description for
  every file and every column (from `docs/schema.md`), the sources, Kaggle tags (only tags
  Kaggle accepts: it refuses the whole update over an unknown one), and a cover
  image drawn by code (`plainpairs.cover`, 560 by 280, no word from any label). `release check
  --kaggle` checks all of it; `release card` rewrites it with no data file touched; the new
  `release kaggle-settings` writes the settings for `kaggle datasets metadata --update` from the
  live ones, never changing the title, subtitle or license. The update frequency stays "not
  specified" until the weekly update runs.
- The author's ORCID iD (https://orcid.org/0009-0007-7180-8620) in `CITATION.cff` (`authors`,
  `preferred-citation` and the dataset's reference) and in `.zenodo.json` (`creators`).

- The easy-access layer, built by `release build` into every version from 0.2.0 and checked by
  `release check` (which fails on a later version without it, or with any of its files missing
  or changed): `00_start_here_labels.csv` (the whole `current` labels table, one row per
  label, with its reading levels and listing flags and no label text) and the same rows as
  `00_start_here_labels.xlsx` with a Read me sheet and a Fields sheet (a seeded 1,000-row
  sample past about 100 MB); `00_start_here_pairs_sample_1000.xlsx` (1,000 seeded `current`
  section pairs, the patient segment next to the prescriber section, released text only, a
  cell over Excel's 32,767 characters cut with a visible mark); `fields.csv` (every column of
  every table, with its type, meaning and allowed values); `codebook.csv` (the trusted codes
  and the ten heading keys); and a gzipped CSV beside each Parquet file (left out past about
  500 MB). The CSV files are checked row for row against the Parquet tables and against
  Excel's limits. The Parquet files and the 16 configurations are unchanged.
- "Start here" at the top of the card and of the Kaggle description, right after the
  not-medical-information box: which file for which need, how to open each in Excel, SPSS,
  Stata, R and Python, and three lines of R and of Python that join a label with its section
  pairs and both texts.
- The Kaggle mirror carries the layer: the start-here file first, each table's CSV unpacked
  (Kaggle unpacks a gzipped file on upload), a plain CSV past about 500 MB left out and named
  in the description, no `README.md`. Its update frequency is monthly from 0.2.0 (weekly on
  Hugging Face).

### Changed
- The README, `CITATION.cff` (the dataset's version under `references`), `.zenodo.json` (its
  `version`) and the package name version 0.2.0; `docs/data-card.md` gains a "Version 0.2.0"
  section and `docs/paper-facts.md` a separate 0.2.0 section (0.1.0's figures, which the paper
  cites, stay as they are).
- The card's reading-level table is computed from each version's own files (0.1.0's figures
  were fixed in the template and would have been shown under a later export's date; the
  computation gives 0.1.0's figures exactly on its pack, and 0.1.0's card is unchanged).
- `docs/data-card.md` is no longer marked as a draft.
- `docs/schema.md` lists every column of every release table one per row, with what it holds;
  the facts are those it gave before.
- `update` reads DailyMed's weekly update files as well as its daily ones. DailyMed lists the
  current week day by day and each earlier week as one file, so a weekly run read only daily
  files and missed the label versions of the week before; their labels would have fallen to
  `unlisted` without a word. The update now takes the daily files of the current week and the
  weekly file of each earlier week (never both for one day), and stops before downloading
  anything when a weekday of the span is no longer covered by any listed file. `summary.json`
  gives the files chosen, the days covered and the SHA-256 of the NCI tables carried over.
- `update` records the last day DailyMed's update files cover as the day the structure was read
  through (not the export day, which may have no file yet), so the next update reads a file
  DailyMed posts later for that day; and it keeps the date of the full release the structure
  started from. The manifest gives both (`dailymed_full_release`, `dailymed_updates_through`),
  and the card, LICENSES.md, the Kaggle description and the workbooks' Read me say "its full
  release of human prescription labels of 2026-11-13, with its update files through
  2026-11-25" instead of naming the export day as a full release.

## [0.1.0] - 2026-11-16

The first release. The corpus is on Hugging Face (`obadakr/plainpairs`, tag `v0.1.0`: 16
configs in three configurations that are never pooled, 1,409,294 rows, 563.0 MB) with a mirror
on Kaggle (`obadakraishan/plainpairs`); this repository's release, archived on Zenodo, holds
the software and its documents, no data table.

### Added
- `release card`: writes the card and LICENSES.md again from a pack's own manifest (and the
  Kaggle folder's LICENSES.md and metadata), leaving the data files and the manifest as they
  are, for a fix to the card's wording.
- `release build` and `release check`: the release pack, one Hugging Face config per table of
  each configuration (16, no default), the switch and the takedown list applied as it is
  written, a manifest, the dataset card and LICENSES.md, and the Kaggle mirror's folder; the
  check runs on the pack alone.
- `update`: the weekly run from the last build, or from a published pack, to the newest export
  (openFDA's parts and NDC file, DailyMed's list and daily updates), with the structure of
  unchanged labels carried forward, the `changes` table, the checks and a counts-only summary.
- The weekly workflow (`.github/workflows/weekly-update.yml`), switched off: no schedule, no
  delivery, actions pinned, least permissions.
- The removal route: an issue form, `docs/removal.md` and the takedown list `data/takedown.csv`.
- `.zenodo.json` (the code and documents only, no data table).
- Text from NCI's cancer information summaries, with parts left out, as a third configuration, `nci`: `nci-build` reads the
  summary pages (listed from NCI's sitemap and read once each, 5 seconds apart, by
  `plainpairs.nci_pages`) into three tables, `nci_summaries`, `nci_pairs` and `nci_text`. Pairs
  come from NCI's own links between versions and languages. Figures, navigation, key-point
  boxes, references, citation marks, the closing sections, credit lines and tables credited to
  other publishers are left out and counted. Every row carries the page's address, the date
  read, NCI's update date and a credit line.
- `nci-text`: rebuilds the NCI text layer by reading NCI's pages again (or, with `--saved`, the
  saved copies), and counts the pages NCI has changed since.
- Spanish readability: a syllable rule from Spanish spelling and the Szigriszt-Pazos
  perspicuity index with its INFLESZ band (`plainpairs.readability_es`).
- `release-check` and `stats` cover the `nci` configuration on its own.
- `build --sheet-result`: `rule_status` per heading key from the scored hand sheet.
- `fetch-page --min-interval`, for sources that ask for slower requests; `quotes-check` also
  reads the saved NCI pages.
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

- `xml-download`: DailyMed's full release of human prescription labels, read from its own
  download page, part by part; a cut-off part resumes with a range request, each part is
  checked against the page's MD5 and written once with its SHA-256 in a manifest.
- `structure`: reads the release's label XML in place (no file unpacked to disk; images are
  counted, never read), joins it to the corpus by set id and version, tests whether the XML
  holds the JSON's words, and measures each section from its structure (`plainpairs.spl`:
  titles, headings, paragraphs, list items, prose cells, captions and data cells).
- Two configurations, `current` (structure from DailyMed's XML) and `unlisted` (the JSON only):
  `build --structure` adds `configuration`, `structure_source`, `unlisted_reason` and the
  measures from structure (`p_<section>_structured`, `t_<text>_structured`) to `labels`, and a
  configuration to `patient_texts` and `section_pairs`. The JSON measures keep their columns.
- `codes --structure`: the length codes read from structure for `current` labels; the
  experimental codes go to `codes_experimental.parquet`, which no release carries.
- `release-check` fails on a label without a configuration, a `current` label without
  structure, a reading-level column pooled across the configurations, and an experimental
  code in a release table.
- `stats` gives reading levels per configuration only, with the JSON's beside the structure's
  for the same `current` labels.

### Changed
- The Kaggle mirror's title is "PlainPairs: prescriber and patient label texts": Kaggle takes
  6 to 50 characters, and `release check` now checks the title and the subtitle (20 to 80)
  against those limits.
- The card and LICENSES.md give the NCI credit line in words. Its placeholder was written as an
  HTML-like tag, which Hugging Face read as a tag, hiding the rest of the card. `release check`
  now fails on a raw HTML tag outside code in the card, LICENSES.md and the Kaggle description,
  and the documents that carried the same placeholder say it in words too.
- The removal route says that opening a request needs a free GitHub account and gives the
  dataset's Community tab on Hugging Face as a second route (card, LICENSES.md,
  `docs/removal.md`, the data card).
- The repository is public for the first release, and `main` takes changes only through pull
  requests that pass the four checks (Python 3.10 to 3.13).
- CI runs the full matrix (Python 3.10 to 3.13) on pull requests again, so that the four
  checks `main` requires report; a push to `main` runs Python 3.12 only.
- The dataset card's `size_categories` is computed from the pack's row count and checked
  (`1M<n<10M` for 1,409,294 rows).
- The card's first-screen box, the README and the data card now cover the cancer information
  text as well: it may be out of date, must never be used to decide about care, and current
  information is on the National Cancer Institute's own site. `release check` fails when the
  first screen leaves the NCI text out.
- The card explains `excluded_otc`: every label in the export typed over the counter that
  carries a guide or an insert (100), record fields only.
- One citation, with the year, in the card, the Kaggle description and `CITATION.cff`
  (`preferred-citation`, the dataset's version); `release check` fails when the card or the
  Kaggle description does not cite the manifest's version.
- The data card records that version 0.1.0 is on Hugging Face as a private dataset; nothing
  is public yet.
- The text switch for the first release: labels `unmarked`, the NCI configuration's kept text
  with its credit line; the Spanish index is marked provisional in the data card.
- The hand topic check is scored: seven heading keys release their mapping rule
  (`rule_status = rule_released`), three are released with similarity scores only
  (`similarity_only`): before taking, avoid and general information.
- Flesch-Kincaid and SMOG are always reported together; the data card states three limits:
  the configurations hold different labels, two measurement bases sit side by side in the same
  tables, and the source's JSON repeats some subsections.
- Codebook version 1 (DRAFT): a development check by hand of every code, each code marked
  trusted or experimental with its error counts, and rule fixes where a clear cause showed
  (risk sizes only, cross-references and doses left out; the month "May" and "may report";
  "inform patients" is not a contact; brand names and pronunciations in brackets; packaging
  counts in "1 in N"). `codes.parquet` now holds only the trusted codes.
- The benchmark design takes the maintainer's defaults: grade 8, 1,000 test and 200
  development items, items from `current` labels only.
- The data card states the two configurations, what the listed-now flags do and do not mean,
  and reading levels per configuration.
- `export_ids.parquet` writes a version too large for a 32-bit integer as null (counted in the
  build summary) instead of stopping the build.
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
