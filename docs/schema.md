# Schema

The tables as `plainpairs build` writes them (Parquet, zstd), from all bulk parts of one
weekly export. Sizes for the export of 2026-11-13 are in [`data-card.md`](data-card.md).

Every row of every table carries `source`, `export_date`, `set_id` and `version`. A
label's `set_id` is stable across its versions; `version` is the source's version number.

## Two layers
- **Record layer** (always releasable; no label text): `labels`, `patient_texts`,
  `section_pairs`, `excluded_otc`. Identifiers, dates, formats, hashes, headings found,
  lengths, reading levels, counts, alignment keys and scores.
- **Text layer** (released only as the switch allows): `text_prescriber`, `text_patient`.
  The cleaned texts, one row per label and section, with the label's copyright flag.

The switch has three settings: `all` (needs an explicit allow when marked texts are present),
`unmarked` (only rows of labels whose text shows no copyright mark) and `none`.
`plainpairs release-check` refuses a release that breaks any rule below; `plainpairs text`
rebuilds the text layer from the record layer and the source's bulk files and confirms every
row by its SHA-256.

## Scope
A label is in the tables when it is in a prescription format and has a Medication Guide or a
patient package insert. The format is read from the sections the label has, in this order:
- `plr` (the newer prescription format): it has Warnings and Precautions, Use in Specific
  Populations, or Dosage Forms and Strengths;
- `otc_drug_facts`: it has a Drug Facts section (Purpose, When using, Stop use, Do not use, Ask
  a doctor) or the source types it as an over-the-counter drug;
- `older` (the older prescription format): it has Indications and Usage, Contraindications,
  Warnings, Precautions, Adverse Reactions or Clinical Pharmacology;
- `unknown`: none of these.

Only `plr` and `older` are in scope. Labels typed as over-the-counter drugs that carry a guide
or an insert are listed in `excluded_otc` and are not in any other table.

## `labels` (table A): one row per label in scope
| column | type | notes |
|---|---|---|
| `source`, `export_date`, `set_id`, `version` | string, string, string, int | every table |
| `id` | string | this version's document id |
| `source_part` | int | the bulk part the label was read from |
| `effective_date`, `effective_time_raw` | date, string | the date is null when the source's value is not a date |
| `label_format`, `format_conflicts` | string, list | the scope rule above; signals that point two ways |
| `harmonized` | bool | whether the source's `openfda` block is present |
| `product_type`, `routes`, `application_numbers`, `manufacturers`, `brand_names`, `generic_names`, `pharm_classes_epc` | string, lists | from the `openfda` block; empty without it |
| `medicine_key`, `medicine_key_source` | string | see below |
| `has_boxed_warning`, `has_medication_guide`, `has_patient_package_insert`, `has_instructions_for_use`, `has_other_patient_text` | bool | presence of each text |
| `has_copyright_mark` | bool | any text field of the label shows the copyright sign, the word "copyright" or "all rights reserved" |
| `n_tables`, `tables_sha256` | int, list | the label's tables in the text layer, and the hash of each |
| `p_<section>_sha256`, `p_<section>` | string, struct | for each of the 11 prescriber sections: the text's hash and its measures |
| `t_<text>_sha256`, `t_<text>_id`, `t_<text>` | string, string, struct | for each of the 4 patient texts: hash, its `patient_texts` id, measures |

Prescriber sections: `boxed_warning`, `indications_and_usage`, `dosage_and_administration`,
`contraindications`, `warnings_and_precautions` (the older format's Warnings and Precautions
joined), `adverse_reactions`, `drug_interactions`, `use_in_specific_populations`,
`patient_counseling_information` (the source's `information_for_patients`: section 17, or the
older format's Information for Patients), `description`, `how_supplied_storage`.

Patient texts: `medication_guide`, `patient_package_insert`, `instructions_for_use`,
`patient_medication_information` (a mixed field, flagged as other).

**Measures** (a struct per text): `words`, `words_with_tables`, `sentences`, `sentences_s1`,
`syllables`, `polysyllables`, `long_sentence_share` (sentences over 20 words), `numbers`,
`percentages`, `flesch_kincaid`, `flesch_kincaid_s1`, `flesch_reading_ease`, `smog`,
`smog_s1`, `smog_short_text`, `headings` (numbered headings in a prescriber section; standard
headings in a patient text), `table_chars_cut`. Grades use the `s2` sentence rule unless the
name ends in `_s1`, and are computed on the prose with inline tables cut (`docs/method.md`).

**Medicine key.** The lower-cased, sorted generic names from the `openfda` block
(`medicine_key_source = openfda`). A label without them takes the key of the labels it shares
an identical patient text with (`shared_text`), when those have one; otherwise it has none
(`none`). No key is ever read from the label's own text.

## `patient_texts` (table B): one row per distinct patient text
`patient_text_id` (`<kind>:<core hash>`), `kind`, `core_hash`, `n_labels`, `n_exact_variants`,
`n_loose_variants`, `set_ids` (all labels that carry it), `n_manufacturers_known`,
`n_labels_without_manufacturer`, `crosses_makers`, `medicine_keys`, `has_copyright_mark_any`,
`headings_found`, `measures` (of the most common exact variant), and the `set_id` and `version`
of that variant's first label.

Three hashes: exact (after spacing), loose (case, punctuation and symbols ignored) and core
(loose, without the closing lines that name the maker or distributor and the revision date).
Table B groups by the core hash.

## `section_pairs` (table C): one row per segment of a guide or insert
`kind`, `patient_text_id`, `segment_index`, `heading_key` (one of ten), `heading_template` (the
heading with the medicine's name replaced by `[medicine]`), `seg_start`, `heading_end`,
`seg_end` (character offsets into the patient text), `measures` (of the segment's body),
`mapped_sections`, `mapped_present`, `best_section`, `best_similarity`,
`mapped_best_similarity`, `best_is_mapped`, `section17_similarity`, `rule_status`
(`pending_hand_check` until the hand sheet is scored).

## `excluded_otc`
`product_type`, `label_format`, `has_medication_guide`, `has_patient_package_insert`.

## `text_prescriber`, `text_patient` (the text layer)
`section` (a prescriber section or a patient text), `part` (`text` or `table`), `part_index`
(0 for the text, 1, 2... for its tables), `text`, `sha256`, `has_copyright_mark` (the label's
flag), `text_has_copyright_mark` (this row's own text).

## Release rules (`plainpairs release-check`)
It fails when: the labels read differ from the manifest's listed records; a table's rows differ
from the build summary, or its columns from the schema; a record-layer table has a `text` column
or a string longer than 300 characters; a text row lacks a mark flag; the switch would release a
marked text; an id is duplicated (`set_id`; `patient_text_id`; set id, kind and segment; set id,
section, part and index); a label in `labels` is out of scope; a row lacks its source, export
date or set id, or holds another export date; a text does not match its hash, or the hashes in
`labels` do not match the text layer.
