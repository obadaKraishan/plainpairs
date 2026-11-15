# Method (DRAFT)

**DRAFT for the maintainer's review.** How the corpus would be built in S2 and checked.

## 1. Source and download
All 14 drug-label bulk parts of one weekly export (`download.json` lists 1,787.53 MiB zipped,
about 1.87 GB, for the 2026-11-13 export), each saved raw once to the external drive, flushed and checked by
SHA-256. The source says a weekly update may change any record, so every export is read in
full, never patched (`docs/automation.md`).

## 2. Parsing
One row per label (`plainpairs.label.parse_label`). The source gives each section as plain
strings without line breaks; the parser cleans them (entities, stray tags, spaces) and keeps
every word, headings included. Tables come as HTML and become plain rows. Records are read one
at a time from the zip archive, which is never unpacked to disk.

## 3. Scope
Prescription-format labels (newer or older format) with a Medication Guide or a patient package
insert (`docs/schema.md`). The format is read from the sections the label has, because most
labels lack the source's product type.

## 4. Duplicates
Three hashes per patient text: exact (after spaces), loose (case, punctuation and symbols
ignored) and core (loose, without the closing lines that name the maker or distributor and
the revision date). The `patient_texts` table groups by the core hash; the other two are
columns, so users can choose. S2 reports how many labels each step merges.

## 5. Alignment of patient segments to prescriber sections
**Step 1, cut the patient text at its standard headings.** The Medication Guide regulation
(21 CFR 208.20) fixes the questions a guide answers, and most guides add storage, ingredients and
"before taking" headings; in the sample, 76% to 89% of guides have each of the five most common
ones. Headings are found by their wording, and a heading quoted in running text ("See 'What is
the most important information…'") is skipped. Patient package inserts follow the same plan less
often (31% to 87% per heading).

**Step 2, a rule from the regulation, checked against the data.** Each heading key gets the
prescriber section(s) it is meant to draw on:

| heading key | prescriber section(s) | share of guide segments whose most similar section is one of these (sample) |
|---|---|---:|
| `what_is` | indications_and_usage | 74% |
| `who_should_not` | contraindications | 69% |
| `how_to_take` | dosage_and_administration | 55% (plus 23% section 17) |
| `storage` | how_supplied_storage | 83% |
| `ingredients` | description | 87% |
| `most_important` | boxed_warning, warnings_and_precautions | 66% (plus 29% section 17) |
| `side_effects` | adverse_reactions, warnings_and_precautions | 58% (plus 39% section 17) |
| `before` | warnings_and_precautions, use_in_specific_populations, drug_interactions | 43% or more (plus 46% section 17) |
| `avoid` | warnings_and_precautions, drug_interactions, patient_counseling_information | 87% or more |
| `general` | none (stock wording) | (section 17, 76%) |

Section 17 (patient counseling information) is a close match for many headings because it is
the prescriber's own summary of what to tell patients, so it is listed with every pair as a
second prescriber text, never as the only one.

**Step 3, a similarity score for every pair.** TF-IDF cosine between the segment and each
prescriber section of the same label, leaving out words found in most of that label's sections
(its own names). The score is kept with the pair. Where the rule and the most similar section
disagree, the pair is flagged, not changed.

**How the alignment is checked.**
- **By hand:** a stratified sample of 200 segments (20 per heading key, from at least 50
  medicines and both formats). A coder (the maintainer) marks for each pair whether the
  prescriber section is where the patient text's content comes from (yes, partly, no) and, if
  not, which section is. The sheet is in S3's hand-coding time (about two hours).
- **Measures:** share of "yes" per heading key, with a Wilson interval; agreement between the
  rule and the similarity choice; for a second coder, Krippendorff's alpha (through the
  reliability module of reliacode once it is released).
- **Release rule:** a heading key whose rule scores under 80% "yes or partly" is released with
  similarity matches only and a flag, and the codebook says so.

## 6. Measures
Computed by stated rules (`docs/codebook-draft.md`). Readability grades are only comparable
within the corpus until S2 fixes sentence splitting on lists: the flattened text joins list
items into long sentences, which raises grades on both sides (`docs/sample.md`).

## 7. What the corpus is not
A record of wording. No measure says what a medicine does, whether it is safe or what anyone
should take. Every release repeats the source's disclaimer and states the export date.
