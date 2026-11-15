# Method

How the corpus is built, as the code does it. The numbers for the export of 2026-11-13 are in
[`data-card.md`](data-card.md); the rule-based codes of wording are in
[`codebook.md`](codebook.md) (version 1, a draft), and the wider plan in
[`codebook-draft.md`](codebook-draft.md).

## 1. Source and download
All bulk parts of one weekly export of the openFDA drug label data, as `download.json` lists
them (14 parts for 2026-11-13). `plainpairs download-all`:
- reads the listing, and downloads only the parts not yet on disk, one at a time;
- writes each part once to the external drive, flushed and read back by SHA-256, and records
  its size and hash in the export's `manifest.csv`;
- checks each part's own `meta` block (export date, record count, total) against the
  listing, and reads the listing again at the end; if the export date moved, it stops.

The source says any record may change in any update, so a new export is always read in full.

## 2. Parsing
`plainpairs build` checks every part against its manifest, then reads the labels one at a time
from each zip archive (never unpacked to disk). Each label becomes one row
(`plainpairs.label.parse_label`). Each section is cleaned (entities, stray tags, spaces) with
every word kept, headings included; tables come as HTML and become plain rows.

## 3. Scope
A label is in scope when it is in a prescription format (decided by its sections, see
[`schema.md`](schema.md)) and has a Medication Guide or a patient package insert that is not
empty after cleaning. Instructions for use and `patient_medication_information` are kept as
extra patient texts on labels in scope. The source's `information_for_patients` is section 17
(Patient Counseling Information) or the older format's Information for Patients, both written
to the prescriber, so it is a prescriber section. Drug Facts labels are out; the labels typed
over the counter that carry a guide or an insert are listed apart.

## 4. Identity
- **Label:** `set_id`, stable across versions; the source holds only the current version.
- **Medicine:** the `openfda` block's generic names, when the block exists. Most labels lack
  it. For those, the medicine key is taken from labels that carry an identical patient text
  (by the core hash) and have generic names; otherwise there is none. No name is read from the
  label's own text.
- **Product name** (its own column, never merged into the medicine key): read from
  `spl_product_data_elements`, the label's structured product data, not its prose. That field
  runs the product name, the generic name and the ingredients together with nothing between
  them; the name ends where the first of three rules fires, in this order, within its first
  eight words (`plainpairs.label.split_product_name`): the first word comes back (`restart`),
  a lower-case word follows a word with a capital (`lowercase`), or a word not in capitals
  comes back later in capitals as the ingredient (`ingredient`). The rule used is kept in
  `product_name_rule`; where no rule fires, there is no name. Where a label also has the
  `openfda` block, the name is compared with its brand names (`data-card.md`).
- **Maker:** the `openfda` block's manufacturer names, when the block exists; otherwise none.
  `docs/data-card.md` reports how often names could be found in other fields, as a measure of
  what a later step could use; nothing is taken from them.

## 5. Duplicates
Three hashes per patient text: exact (after spacing), loose (case, punctuation and symbols
ignored) and core (loose, without the closing lines naming the maker or distributor and the
revision date, when those begin in the last third). Table B groups texts by the core hash; it
records how many exact and loose variants each group has and whether its labels name more than
one maker.

## 6. Text structure and measures
The source keeps no line breaks, but it does keep list marks (such as the bullet sign). Two sentence
rules are computed:
- `s1`: sentences end at a full stop, exclamation mark or question mark (abbreviations and
  decimals protected);
- `s2` (the one reported): `s1`, plus breaks at list marks, before numbered headings ("5.1
  ...") and around runs of capitals that read as headings.

Before measuring, the tables the source repeats inline in a section's text are cut from it
(`plainpairs.text.strip_tables`). Per text and per section: words (with and without tables),
sentences, syllables, words of three or more syllables, the share of sentences over 20 words,
numbers and percentages written in digits, Flesch-Kincaid grade, Flesch reading ease and SMOG
grade (by both rules), and the headings found. Grades are comparable within the corpus, between
texts measured the same way; they are not the grade a reader meets on the printed page, which
keeps a layout the source has lost.

## 6b. Structure from DailyMed's XML, and the two configurations
The JSON flattens each section into one string, so a list reads as one long sentence and a
heading runs into its body. DailyMed publishes the same labels as SPL XML, which keeps the
structure. The corpus uses it where it can, and says so on every label.

- **The release.** `plainpairs xml-download` reads DailyMed's "Download All Drug Labels" page
  and downloads the full release of human prescription labels part by part (6 parts of
  2026-11-13, 18,063,809,249 bytes), resuming a cut-off part, checking each against the page's
  MD5 and writing it once with its SHA-256 in a manifest. The parts are read where they lie:
  each holds one zip per label with one XML document and its images; only the XML is opened
  (in memory), and the images are counted by type, never read.
- **The join.** `plainpairs structure` reads every document's set id and version (55,148
  documents, 52,840 set ids; 2,302 set ids appear in two or three versions). A corpus label
  matches when the release holds its set id in the same version as the export.
- **The same words?** For each matched label and section, the XML's words, read flat (every
  text node of the section, a space between each, as the JSON flattens it), are compared with
  the JSON text after the same cleaning: lower-case letters and digits as tokens; `exact` is
  the same tokens in the same order, `near` a Dice overlap of the token bags of 0.98 or more.
  A third class, `json_repeats`, holds the XML's words with the subsections that carry their
  parent's section code read a second time: the JSON repeats such subsections, so its text is
  longer than the label's (1.6% to 3.3% of prescriber sections, 2 Medication Guides).
- **Blocks.** For the matched sections, `plainpairs.spl` reads the structure into blocks:
  titles; headings (a line wholly in bold or underline, of 30 words or fewer, that does not end
  as a sentence ends; a bold question opening a paragraph is split off; bold list items and
  bold "See ..." lines are not headings); paragraphs; list items (and pieces of a line after a
  typed list mark); cells of tables that hold prose; captions; and cells of data tables (short
  cells, the same rule as the JSON's table cut). A line break ends a line. A newer-format
  section's Highlights excerpt is read too, as the JSON keeps it in the same field.
- **Sentences from structure.** Every paragraph, item, prose cell and caption is cut into
  sentences by rule `s1`, and every block ends a sentence; titles, headings and data cells are
  not sentences and are not measured. The same formulas as section 6 are then applied.
- **The two configurations** (`labels.configuration`):
  - `current`: the release holds the label in the same version, and each of its patient texts
    has a section in the XML whose words are the JSON's (`exact`, `near` or `json_repeats`).
    Its measures from structure are in their own columns (`p_<section>_structured`,
    `t_<text>_structured`); its JSON measures stay in `p_<section>` and `t_<text>`. 19,778
    labels.
  - `unlisted`: every other label, measured from the JSON only (`structure_source = json`),
    with the reason in `unlisted_reason`: not in the release (15,122), in it only in another
    version (268), a patient text the XML lacks (8), a patient text whose words differ (1).
    15,399 labels.

  A reading level is never computed over both configurations at once: every aggregate is
  given per configuration, and for `current` the JSON's figure for the same labels is given
  beside the structure's. Flesch-Kincaid and SMOG are always reported together, per
  configuration and per basis; neither alone is a headline. `release-check` fails when a row does not say its configuration or
  when measures from structure sit on an `unlisted` row.

## 7. Alignment of patient segments to prescriber sections
- **Cut:** each guide or insert is cut at its standard headings (the questions of 21 CFR 208.20
  and the common additions), found by their wording; a heading cited in running text ("See
  'What is the most important...'") is skipped. A heading followed at once by another form of
  the same heading (the question, then "Before taking ..., tell your healthcare provider"; or
  the same question twice), with nothing but spaces, list marks or punctuation between them,
  is one heading: the first is kept and the restatement opens its body. A letter or a digit
  between them is a body, so the two stay apart. The build counts the merges.
- **Map:** each heading key is mapped to the prescriber sections the regulation points it to
  (`plainpairs.align.MAPPING`): what it is to Indications and usage; who should not take it to
  Contraindications; how to take it to Dosage and administration; storage to How supplied;
  ingredients to Description; most important information to the Boxed warning and Warnings
  and precautions; side effects to Adverse reactions and Warnings and precautions; before
  taking to Warnings and precautions, Use in specific populations and Drug interactions; avoid
  to Warnings and precautions, Drug interactions and section 17; general information to
  section 17. The regulation names no section for general information: that mapping is a
  choice of this project (`plainpairs.align.MAPPED_BY_PROJECT`), and every alignment figure
  for it says so.
- **Score:** each segment is compared with every prescriber section of its label by the cosine
  of TF-IDF weighted word counts. Document frequencies come from the whole corpus, and the words
  found in more than half of one label's sections and segments (its own names) are left out for
  that label. The pair keeps the mapped sections present, the most similar section, both
  similarities and whether they agree.
- **Check:** a blind hand sheet of 100 segments, 10 per heading key, drawn with a seed: only
  segments of at least two sentences and 20 words, never two rows from the same distinct
  patient text, and, where possible, a new medicine each time. It asks one question:
  does this prescriber section cover the same topic as this patient segment (yes, partly, no).
  It never asks whether the content is medically right. A heading's rule is released when 80%
  of its rows are "yes" or "partly"; otherwise its pairs are released with similarity scores
  only, and flagged (`docs/hand-sheet-guide.md`).

## 8. Listed now
Two small official lists say whether a label's product is still listed, each read on the day
its file was made (`plainpairs listed-download`, then `plainpairs build --listed`):
- **The NDC directory** (openFDA's `drug/ndc` bulk file): `listed_in_ndc_directory` is true when
  the label's set id is a directory entry's `openfda.spl_set_id`, or else its document id an
  entry's `spl_id` (`ndc_match` says which).
- **DailyMed's zip file metadata** (`dm_spl_zip_files_meta_data.zip`): `served_by_dailymed` is
  true when DailyMed lists the set id; `dailymed_version` is the version it serves. Only the set
  id and the version are read.

The flags describe the lists, not the medicines. A label on neither list may be for a product
no longer marketed, or one these lists do not cover. The NDC flag equals the `openfda` block
this week (all 15,022 labels with the block are in the directory, none without it), because
openFDA fills that block from the NDC directory; the two could part when they are refreshed on
different days, so the flag is kept. "Served by DailyMed" says that DailyMed lists the label,
nothing more: it is never read as "marketed". The configuration (section 6b) rests on
DailyMed's full release of the same week, not on the list, and the two disagree for a few
hundred labels (`docs/data-card.md`).

## 9. Rule-based codes of wording
`plainpairs codes` reads the text layer and writes counts per text for each code of
[`codebook.md`](codebook.md) (version 1): the trusted codes to the `codes` table, the
experimental ones to `codes_experimental`, which no release carries. With `--structure` it adds,
for `current` labels, the length codes read from structure. Each code's status comes from a
development check by hand (20 hits and 20 misses for the codes first doubted, 10 and 10 for the
others), which the codebook reports with its error counts; it is not a validation. The codes
have their own version, so they can change without a new build.

## 10. What changed since the last export
`plainpairs changes --old <older build> --new <newer build>` compares two builds' record layers
and writes the `changes` table: one row per label that is new, gone (left the scope, or
withdrawn when the newer export's set ids show it is no longer in the export at all), a new
version with the same texts, changed texts (by section, with patient texts added or dropped),
or a change of the `openfda` block, the format, the copyright mark or a listing. The build
writes every set id of its export (`export_ids.parquet`) for this. A release keeps labels that
left and flags them; nothing is deleted.

## 11. Copyright marks and the text switch
Every label's text fields are scanned for the copyright sign, the word "copyright" and "all
rights reserved". The flag is kept on the label and on each of its text rows. The text layer is
released only as the switch allows: all, unmarked only, or none; the maintainer decides before
any release.

## 12. Checks before release
`plainpairs release-check` (rules in [`schema.md`](schema.md); it also checks the `codes` table
when there is one, the two configurations, pooled reading-level columns and experimental codes)
and `plainpairs text`, which
rebuilds the text layer from the record layer and the bulk files of the same export date and
confirms every row by its hash.

## 13. What the corpus is not
A record of wording. No measure says what a medicine does, whether it is safe or what anyone
should take. Every release repeats the source's disclaimer and states the export date.
