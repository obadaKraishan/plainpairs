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
| `product_name`, `product_name_source`, `product_name_rule` | string | the name at the head of the label's structured product data (`spl_product_data_elements`); the source is `spl_product_data_elements` or `none`; the rule is `restart`, `lowercase` or `ingredient` (`docs/method.md`, section 4). Never merged into the medicine key |
| `listed_in_ndc_directory`, `ndc_match` | bool, string | in the current NDC directory, matched by `set_id` or by `spl_id` (the document id), or `none`; null when the build had no directory file |
| `served_by_dailymed`, `dailymed_version` | bool, int | DailyMed's zip file metadata lists the set id, and the version it serves; null when the build had no such file. "Served" says only that DailyMed lists the label; it never means "marketed" |
| `configuration` | string | `current`: DailyMed's full release of the same week holds this label in this version, and each of its patient texts with the same words as the JSON; its structure comes from the XML. `unlisted`: every other label, measured from the JSON only. Null when the build had no structure folder (`docs/method.md`, section 6b) |
| `structure_source` | string | `dailymed_xml` for `current`, `json` for `unlisted` |
| `unlisted_reason` | string | for `unlisted` labels: `not_in_release`, `other_version`, `patient_text_missing` (a patient text of the JSON has no section in the XML) or `patient_text_differs`; null for `current` |
| `has_boxed_warning`, `has_medication_guide`, `has_patient_package_insert`, `has_instructions_for_use`, `has_other_patient_text` | bool | presence of each text |
| `has_copyright_mark` | bool | any text field of the label shows the copyright sign, the word "copyright" or "all rights reserved" |
| `n_tables`, `tables_sha256` | int, list | the label's tables in the text layer, and the hash of each |
| `p_<section>_sha256`, `p_<section>` | string, struct | for each of the 11 prescriber sections: the text's hash and its measures |
| `t_<text>_sha256`, `t_<text>_id`, `t_<text>` | string, string, struct | for each of the 4 patient texts: hash, its `patient_texts` id, measures |
| `p_<section>_structured`, `t_<text>_structured` | struct | measures from structure, for `current` labels only (null for every `unlisted` label); see below. The JSON measures stay in `p_<section>` and `t_<text>` for every label |

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

**Measures from structure** (a struct per section of a `current` label; `docs/method.md`,
section 6b): `xml_match` (`exact`, `near`, `json_repeats`, `not`, `json_missing`,
`xml_missing`), `xml_dice`, `xml_tokens`, `json_tokens` (the word test against the JSON),
`blocks_dice` (how much of the JSON's words the measured blocks cover), then, when the words
agree (`exact`, `near` or `json_repeats`): `words`, `sentences`, `syllables`, `polysyllables`,
`long_sentence_share`, `numbers`, `percentages`, `flesch_kincaid`, `flesch_reading_ease`,
`smog`, `smog_short_text`, the blocks by kind (`blocks_title`, `blocks_heading`,
`blocks_paragraph`, `blocks_item`, `blocks_cell`, `blocks_caption`, `blocks_data_cell`,
`blocks_in_highlights`), `subsection_titles`, and the length codes from structure
(`sentences_over_20`, `sentences_over_40`, `longest_sentence_words`, `parts`,
`longest_part_words`, `parts_over_250`). These grades are on a different basis from the JSON's
and are never pooled with them.

**Medicine key.** The lower-cased, sorted generic names from the `openfda` block
(`medicine_key_source = openfda`). A label without them takes the key of the labels it shares
an identical patient text with (`shared_text`), when those have one; otherwise it has none
(`none`). No key is ever read from the label's own text.

## `patient_texts` (table B): one row per distinct patient text
`patient_text_id` (`<kind>:<core hash>`), `kind`, `core_hash`, `n_labels`, `n_exact_variants`,
`n_loose_variants`, `set_ids` (all labels that carry it), `n_manufacturers_known`,
`n_labels_without_manufacturer`, `crosses_makers`, `medicine_keys`, `has_copyright_mark_any`,
`headings_found`, `measures` (of the most common exact variant), and the `set_id` and `version`
of that variant's first label. `configuration` is `current` when at least one label carrying
the text is `current` (`n_labels_current` says how many); `measures_structured` is then taken
from a current label with the most common exact variant when there is one, else from any
current label; it is null for texts that are not `current`.

Three hashes: exact (after spacing), loose (case, punctuation and symbols ignored) and core
(loose, without the closing lines that name the maker or distributor and the revision date).
Table B groups by the core hash.

## `section_pairs` (table C): one row per segment of a guide or insert
`kind`, `patient_text_id`, `segment_index`, `heading_key` (one of ten), `heading_template` (the
heading with the medicine's name replaced by `[medicine]`), `seg_start`, `heading_end`,
`seg_end` (character offsets into the patient text), `measures` (of the segment's body),
`mapped_sections`, `mapped_present`, `best_section`, `best_similarity`,
`mapped_best_similarity`, `best_is_mapped`, `section17_similarity`, `rule_status`
(`pending_hand_check` until the hand sheet is scored), and last `configuration` (the label's).
Every column before `configuration` is built from the JSON text, as in the build the hand
sheet was drawn from. A heading followed at once by its
restatement is one segment (`docs/method.md`, section 7). The mapping of `general` is this
project's choice, not the regulation's (`plainpairs.align.mapping_source`).

## `excluded_otc`
`product_type`, `label_format`, `has_medication_guide`, `has_patient_package_insert`.

## `text_prescriber`, `text_patient` (the text layer)
`section` (a prescriber section or a patient text), `part` (`text` or `table`), `part_index`
(0 for the text, 1, 2... for its tables), `text`, `sha256`, `has_copyright_mark` (the label's
flag), `text_has_copyright_mark` (this row's own text).

## `codes`: one row per text of the text layer (record layer; `plainpairs codes`)
Codebook version 1. `source`, `export_date`, `set_id`, `version`, `section`, `side` (`patient`
or `prescriber`), `patient_text_id` (patient texts only), `code_version`, `configuration` and
`structure_source` (the label's), the counts `words` and `sentences`, then **the trusted codes
only**: `you_words`, `sentences_with_you`, `command_sentences`, `conditional_commands`,
`distinct_actions`, `percentages`, `one_in_n`, `frequencies`, `doses`, `contact_sentences`, and
for `current` labels the length codes from structure: `structured_sentences`,
`structured_sentences_over_20`, `structured_sentences_over_40`,
`structured_longest_sentence_words` (null for `unlisted`).

## `codes_experimental` (not a release table)
The same ids, then the experimental codes: `risk_sentences`, `risk_sentences_with_number`,
`vague_core`, `vague_extended`, `explained_in_brackets`, `explained_called`,
`abbreviations_in_brackets`, `sentences_over_20`, `sentences_over_40`,
`longest_sentence_words`, `sections`, `longest_section_words`, `sections_over_250`,
`contact_sentences_with_when`, `structured_parts`, `structured_longest_part_words`,
`structured_parts_over_250`. Row for row with `codes`. Status, reasons and error counts:
`docs/codebook.md`.

## The structure folder (`plainpairs structure`; not release tables)
- `index`: one row per document of DailyMed's release: `release_date`, `part`, `member`,
  `xml_name`, `set_id`, `version`, `document_id`, `effective_time`, `document_type`,
  `in_corpus`, `corpus_version`, `version_match`, `fields` (the sections read), `parse_error`.
- `blocks`: the structure of each matched label, one row per block: `set_id`, `version`,
  `section`, `block_index`, `kind` (`title`, `heading`, `paragraph`, `item`, `cell`, `caption`,
  `data_cell`), `depth`, `list_depth`, `table`, `highlights`, `text`. It holds label text, so it
  is kept with the text layer, never in the record layer.
- `structure`: one row per matched label and section: `set_id`, `version`, `section`, `side`,
  `structured` (the struct above). Counts only.

## `export_ids.parquet` (next to the build)
`export_date`, `set_id`, `version` of every label in the export, in scope or not (a version
too large for a 32-bit integer is null; the build summary counts them). Not a release table;
`plainpairs changes` reads it to tell a label that left the scope from one withdrawn.

## `changes`: one row per label that differs between two builds (`plainpairs changes`)
`old_export_date`, `new_export_date`, `set_id`, `change` (`new_label`, `gone`, `left_scope`,
`withdrawn`, `new_version_same_texts`, `texts_changed`, `record_only`), `old_version`,
`new_version`, `sections_changed`, `patient_texts_added`, `patient_texts_dropped` (section
names), and the flags `block_changed`, `format_changed`, `mark_changed`,
`ndc_listing_changed`, `dailymed_listing_changed`. Ids, versions, names and flags only.

## Release rules (`plainpairs release-check`)
It fails when: the labels read differ from the manifest's listed records; a table's rows differ
from the build summary, or its columns from the schema; a record-layer table has a `text` column
or a string longer than 300 characters; a text row lacks a mark flag; the switch would release a
marked text; an id is duplicated (`set_id`; `patient_text_id`; set id, kind and segment; set id,
section, part and index); a label in `labels` is out of scope; a row lacks its source, export
date or set id, or holds another export date; a text does not match its hash, or the hashes in
`labels` do not match the text layer. When a `codes` table is present it also fails if its
columns differ from the schema, a text appears twice, a row is for a label not in `labels`, or
a string is longer than 300 characters.

**The two configurations.** It also fails when no label has a configuration (a build without
the structure folder), when a label's configuration is missing or unknown, when a `current`
label lacks measures from structure for one of its patient texts (a current label without
structure), when a reading-level column is pooled across the configurations (an `unlisted`
label, or a patient text that is not `current`, carrying measures from structure; a row of
`patient_texts` or `section_pairs` that does not say its configuration; a section pair whose
configuration differs from its label's), and when a code marked experimental in
`docs/codebook.md` is a column of `codes`, a release table.
