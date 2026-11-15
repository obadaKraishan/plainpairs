# Method

How the corpus is built, as the code does it. The numbers for the export of 2026-11-13 are in
[`data-card.md`](data-card.md); the codebook for later, rule-based content codes is still a
draft ([`codebook-draft.md`](codebook-draft.md)).

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

## 7. Alignment of patient segments to prescriber sections
- **Cut:** each guide or insert is cut at its standard headings (the questions of 21 CFR 208.20
  and the common additions), found by their wording; a heading cited in running text ("See
  'What is the most important...'") is skipped.
- **Map:** each heading key is mapped to the prescriber sections the regulation points it to
  (`plainpairs.align.MAPPING`): what it is to Indications and usage; who should not take it to
  Contraindications; how to take it to Dosage and administration; storage to How supplied;
  ingredients to Description; most important information to the Boxed warning and Warnings
  and precautions; side effects to Adverse reactions and Warnings and precautions; before
  taking to Warnings and precautions, Use in specific populations and Drug interactions; avoid
  to Warnings and precautions, Drug interactions and section 17; general information (no section
  in the regulation) to section 17.
- **Score:** each segment is compared with every prescriber section of its label by the cosine
  of TF-IDF weighted word counts. Document frequencies come from the whole corpus, and the words
  found in more than half of one label's sections and segments (its own names) are left out for
  that label. The pair keeps the mapped sections present, the most similar section, both
  similarities and whether they agree.
- **Check:** a blind hand sheet of 100 segments, 10 per heading key, drawn with a seed (one per
  distinct patient text and, where possible, a new medicine each time). It asks one question:
  does this prescriber section cover the same topic as this patient segment (yes, partly, no).
  It never asks whether the content is medically right. A heading's rule is released when 80%
  of its rows are "yes" or "partly"; otherwise its pairs are released with similarity scores
  only, and flagged (`docs/hand-sheet-guide.md`).

## 8. Copyright marks and the text switch
Every label's text fields are scanned for the copyright sign, the word "copyright" and "all
rights reserved". The flag is kept on the label and on each of its text rows. The text layer is
released only as the switch allows: all, unmarked only, or none; the maintainer decides before
any release.

## 9. Checks before release
`plainpairs release-check` (rules in [`schema.md`](schema.md)) and `plainpairs text`, which
rebuilds the text layer from the record layer and the bulk files of the same export date and
confirms every row by its hash.

## 10. What the corpus is not
A record of wording. No measure says what a medicine does, whether it is safe or what anyone
should take. Every release repeats the source's disclaimer and states the export date.
