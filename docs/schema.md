# Schema

The tables as `plainpairs build` writes them (Parquet, zstd), from all bulk parts of one
weekly export. Sizes for the export of 2026-11-13 are in [`data-card.md`](data-card.md).

Every row of every label table carries `source`, `export_date`, `set_id` and `version`. A
label's `set_id` is stable across its versions; `version` is the source's version number.

Each release table below lists its columns one per row; the Kaggle mirror's column and file
descriptions are built from these tables (`plainpairs.kaggle_meta`), so a column is described
here once. A name with `<section>` or `<text>` stands for one column per prescriber section or
per patient text (the lists under `labels`).

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

## Columns in every label table (`labels`, `patient_texts`, `section_pairs`, `excluded_otc`, `text_prescriber`, `text_patient`, `codes`)
| column | type | notes |
|---|---|---|
| `source` | string | where the row was read: the openFDA drug label bulk files, with their address |
| `export_date` | string | the date of the source's weekly export the row was built from |
| `set_id` | string | the label's set id, stable across its versions |
| `version` | int | the source's version number of the label |

## `labels` (table A): one row per label in scope
| column | type | notes |
|---|---|---|
| `id` | string | this version's document id |
| `source_part` | int | the bulk part the label was read from |
| `effective_date` | date | the label's effective date; null when the source's value is not a date |
| `effective_time_raw` | string | the effective time as the source gives it |
| `label_format` | string | the label's format by the scope rule above: `plr` or `older` |
| `format_conflicts` | list | signals that point to another format |
| `harmonized` | bool | whether the source's `openfda` block is present |
| `product_type` | string | the product type, from the `openfda` block; empty without it |
| `routes` | list | the routes of administration, from the `openfda` block; empty without it |
| `application_numbers` | list | the application numbers, from the `openfda` block; empty without it |
| `manufacturers` | list | the manufacturer names, from the `openfda` block; empty without it |
| `brand_names` | list | the brand names, from the `openfda` block; empty without it |
| `generic_names` | list | the generic names, from the `openfda` block; empty without it |
| `pharm_classes_epc` | list | the established pharmacologic classes, from the `openfda` block; empty without it |
| `medicine_key` | string | the medicine key (see below); null when the label has none |
| `medicine_key_source` | string | where the key comes from: `openfda`, `shared_text` or `none` (see below) |
| `product_name` | string | the name at the head of the label's structured product data (`spl_product_data_elements`); never merged into the medicine key |
| `product_name_source` | string | `spl_product_data_elements`, or `none` when no name was read |
| `product_name_rule` | string | the rule that ended the name: `restart`, `lowercase` or `ingredient` (`docs/method.md`, section 4) |
| `listed_in_ndc_directory` | bool | the product is in the current NDC directory; null when the build had no directory file |
| `ndc_match` | string | how the label matched the directory: by `set_id`, by `spl_id` (the document id), or `none` |
| `served_by_dailymed` | bool | DailyMed's zip file metadata lists the set id; null when the build had no such file. "Served" says only that DailyMed lists the label; it never means "marketed" |
| `dailymed_version` | int | the version of the label DailyMed serves |
| `configuration` | string | `current`: DailyMed's full release of the same week holds this label in this version, and each of its patient texts with the same words as the JSON; its structure comes from the XML. `unlisted`: every other label, measured from the JSON only. Null when the build had no structure folder (`docs/method.md`, section 6b) |
| `structure_source` | string | `dailymed_xml` for `current`, `json` for `unlisted` |
| `unlisted_reason` | string | for `unlisted` labels: `not_in_release`, `other_version`, `patient_text_missing` (a patient text of the JSON has no section in the XML) or `patient_text_differs`; null for `current` |
| `has_boxed_warning` | bool | the label has a boxed warning |
| `has_medication_guide` | bool | the label has a Medication Guide |
| `has_patient_package_insert` | bool | the label has a patient package insert |
| `has_instructions_for_use` | bool | the label has Instructions for Use |
| `has_other_patient_text` | bool | the label has the mixed `patient_medication_information` field |
| `has_copyright_mark` | bool | any text field of the label shows the copyright sign, the word "copyright" or "all rights reserved" |
| `n_tables` | int | the number of the label's tables in the text layer |
| `tables_sha256` | list | the SHA-256 of each of those tables, in the order the rows are written |
| `p_<section>_sha256` | string | the SHA-256 of the label's `<section>` text, a prescriber section; null when the label lacks it |
| `p_<section>` | struct | the measures of the `<section>` text, from the JSON (see Measures) |
| `t_<text>_sha256` | string | the SHA-256 of the label's `<text>`, a patient text; null when the label lacks it |
| `t_<text>_id` | string | the `patient_texts` id of the label's `<text>` |
| `t_<text>` | struct | the measures of the `<text>`, from the JSON (see Measures) |
| `p_<section>_structured` | struct | the measures of the `<section>` text from structure, for `current` labels only (null for every `unlisted` label); see Measures from structure. The JSON measures stay in `p_<section>` |
| `t_<text>_structured` | struct | the measures of the `<text>` from structure, for `current` labels only (null for every `unlisted` label); see Measures from structure. The JSON measures stay in `t_<text>` |

Prescriber sections: `boxed_warning`, `indications_and_usage`, `dosage_and_administration`,
`contraindications`, `warnings_and_precautions` (the older format's Warnings and Precautions
joined), `adverse_reactions`, `drug_interactions`, `use_in_specific_populations`,
`patient_counseling_information` (the source's `information_for_patients`: section 17, or the
older format's Information for Patients), `description`, `how_supplied_storage`.

Patient texts: `medication_guide`, `patient_package_insert`, `instructions_for_use`,
`patient_medication_information` (a mixed field, flagged as other).

### Fields of a measures struct (`measures`)
A struct per text (`p_<section>`, `t_<text>` and `measures`). Grades use the `s2` sentence rule
unless the name ends in `_s1`, and are computed on the prose with inline tables cut
(`docs/method.md`). In the CSV files each field is a column of its own, named
`<column>.<field>` (`t_medication_guide.flesch_kincaid`).

| column | type | notes |
|---|---|---|
| `words` | int | the words of the prose, inline tables cut |
| `words_with_tables` | int | the words with the inline tables kept |
| `sentences` | int | the sentences, by the `s2` rule |
| `sentences_s1` | int | the sentences, by the `s1` rule |
| `syllables` | int | the syllables |
| `polysyllables` | int | the words of three or more syllables |
| `long_sentence_share` | float | the share of sentences over 20 words |
| `numbers` | int | the numbers written in digits |
| `percentages` | int | the numbers followed by "%" or "percent" |
| `flesch_kincaid` | float | the Flesch-Kincaid grade, by `s2` |
| `flesch_kincaid_s1` | float | the Flesch-Kincaid grade, by `s1` |
| `flesch_reading_ease` | float | the Flesch reading ease (higher is easier) |
| `smog` | float | the SMOG grade, by `s2` |
| `smog_s1` | float | the SMOG grade, by `s1` |
| `smog_short_text` | bool | the text has fewer than 30 sentences, the number SMOG is defined for |
| `headings` | int | numbered headings in a prescriber section; standard headings in a patient text |
| `table_chars_cut` | int | the characters of inline tables cut before measuring |

### Fields of a measures-from-structure struct (`measures_structured`)
A struct per section of a `current` label (`p_<section>_structured`, `t_<text>_structured`
and `measures_structured`; `docs/method.md`, section 6b). The word test comes first; the
measures follow only when the words agree (`exact`, `near` or `json_repeats`). These grades are
on a different basis from the JSON's and are never pooled with them.

| column | type | notes |
|---|---|---|
| `xml_match` | string | the word test against the JSON: `exact`, `near`, `json_repeats`, `not`, `json_missing` or `xml_missing` |
| `xml_dice` | float | the Dice overlap of the XML's and the JSON's words |
| `xml_tokens` | int | the words of the section in the XML, read flat |
| `json_tokens` | int | the words of the section in the JSON |
| `blocks_dice` | float | how much of the JSON's words the measured blocks cover |
| `words` | int | the words of the measured blocks |
| `sentences` | int | the sentences of the measured blocks |
| `syllables` | int | the syllables |
| `polysyllables` | int | the words of three or more syllables |
| `long_sentence_share` | float | the share of sentences over 20 words |
| `numbers` | int | the numbers written in digits |
| `percentages` | int | the numbers followed by "%" or "percent" |
| `flesch_kincaid` | float | the Flesch-Kincaid grade, on structure |
| `flesch_reading_ease` | float | the Flesch reading ease, on structure (higher is easier) |
| `smog` | float | the SMOG grade, on structure |
| `smog_short_text` | bool | fewer than 30 sentences, the number SMOG is defined for |
| `blocks_title` | int | the blocks that are titles |
| `blocks_heading` | int | the blocks that are headings |
| `blocks_paragraph` | int | the blocks that are paragraphs |
| `blocks_item` | int | the blocks that are list items |
| `blocks_cell` | int | the blocks that are table cells of layout tables |
| `blocks_caption` | int | the blocks that are captions |
| `blocks_data_cell` | int | the blocks that are cells of data tables (not measured) |
| `blocks_in_highlights` | int | the blocks inside the Highlights excerpt |
| `subsection_titles` | int | the titles of subsections |
| `sentences_over_20` | int | the sentences over 20 words, on structure |
| `sentences_over_40` | int | the sentences over 40 words, on structure |
| `longest_sentence_words` | int | the words of the longest sentence, on structure |
| `parts` | int | the parts between the XML's own headings |
| `longest_part_words` | int | the words of the longest part |
| `parts_over_250` | int | the parts of more than 250 words |

**Medicine key.** The lower-cased, sorted generic names from the `openfda` block
(`medicine_key_source = openfda`). A label without them takes the key of the labels it shares
an identical patient text with (`shared_text`), when those have one; otherwise it has none
(`none`). No key is ever read from the label's own text.

## `patient_texts` (table B): one row per distinct patient text
| column | type | notes |
|---|---|---|
| `patient_text_id` | string | the text's id: its kind and core hash, as `kind:core hash` |
| `kind` | string | which patient text it is (one of the patient texts under `labels`) |
| `core_hash` | string | the core hash of the text (see the three hashes below) |
| `n_labels` | int | the number of labels that carry the text |
| `n_exact_variants` | int | the number of distinct exact hashes among those labels |
| `n_loose_variants` | int | the number of distinct loose hashes among those labels |
| `set_ids` | list | the set ids of all labels that carry the text |
| `n_manufacturers_known` | int | the number of distinct manufacturers named in those labels' `openfda` blocks |
| `n_labels_without_manufacturer` | int | the number of those labels that name no manufacturer |
| `crosses_makers` | bool | the labels that carry the text name more than one manufacturer |
| `medicine_keys` | list | the medicine keys of those labels |
| `has_copyright_mark_any` | bool | any label that carries the text shows a copyright mark |
| `headings_found` | list | the standard headings found in the text |
| `measures` | struct | the measures of the most common exact variant, from the JSON (see Measures) |
| `configuration` | string | `current` when at least one label carrying the text is `current`, else `unlisted` |
| `n_labels_current` | int | the number of `current` labels that carry the text |
| `measures_structured` | struct | the measures from structure, taken from a `current` label with the most common exact variant when there is one, else from any `current` label; null for texts that are not `current` (in `current` files only) |

The `set_id` and `version` of a row are those of the first label with the most common exact
variant.

Three hashes: exact (after spacing), loose (case, punctuation and symbols ignored) and core
(loose, without the closing lines that name the maker or distributor and the revision date).
Table B groups by the core hash.

## `section_pairs` (table C): one row per segment of a guide or insert
| column | type | notes |
|---|---|---|
| `kind` | string | the patient text the segment is in: `medication_guide` or `patient_package_insert` |
| `patient_text_id` | string | the `patient_texts` id of that text |
| `segment_index` | int | the segment's place in the text, from 0 |
| `heading_key` | string | the standard heading that opens the segment, one of ten |
| `heading_template` | string | the heading with the medicine's name replaced by `[medicine]` |
| `seg_start` | int | the character offset into the patient text where the segment starts |
| `heading_end` | int | the character offset where its heading ends |
| `seg_end` | int | the character offset where the segment ends |
| `measures` | struct | the measures of the segment's body, from the JSON (see Measures) |
| `mapped_sections` | list | the prescriber sections the heading key points to |
| `mapped_present` | list | those of them the label has |
| `best_section` | string | the prescriber section most similar to the segment (TF-IDF cosine) |
| `best_similarity` | float | that section's similarity |
| `mapped_best_similarity` | float | the highest similarity among the mapped sections the label has |
| `best_is_mapped` | bool | the most similar section is one of the mapped sections |
| `section17_similarity` | float | the segment's similarity to `patient_counseling_information` (section 17) |
| `rule_status` | string | `rule_released` when the heading key passed the hand check and keeps its mapping rule, `similarity_only` when it did not (`pending_hand_check` before the check is scored) |
| `configuration` | string | the label's configuration |

Every column before `configuration` is built from the JSON text, as in the build the hand
sheet was drawn from. A heading followed at once by its restatement is one segment
(`docs/method.md`, section 7). The mapping of `general` is this project's choice, not the
regulation's (`plainpairs.align.mapping_source`).

## `excluded_otc`: one row per label typed over the counter that carries a guide or an insert
| column | type | notes |
|---|---|---|
| `product_type` | string | the product type, from the `openfda` block |
| `label_format` | string | the label's format by the scope rule above |
| `has_medication_guide` | bool | the label has a Medication Guide |
| `has_patient_package_insert` | bool | the label has a patient package insert |

## `text_prescriber`, `text_patient` (the text layer): one row per label, section and part
| column | type | notes |
|---|---|---|
| `section` | string | a prescriber section (in `text_prescriber`) or a patient text (in `text_patient`) |
| `part` | string | `text` for the section's prose, `table` for one of its tables |
| `part_index` | int | 0 for the text, 1, 2... for its tables |
| `text` | string | the cleaned text of the part |
| `sha256` | string | the SHA-256 of `text` |
| `has_copyright_mark` | bool | the label's copyright flag |
| `text_has_copyright_mark` | bool | this row's own text shows a copyright mark |

## `codes`: one row per text of the text layer (record layer; `plainpairs codes`)
Codebook version 1, **the trusted codes only** (`docs/codebook.md` gives each code's rule and
check).

| column | type | notes |
|---|---|---|
| `section` | string | the prescriber section or patient text coded |
| `side` | string | `patient` or `prescriber` |
| `patient_text_id` | string | the `patient_texts` id (patient texts only) |
| `code_version` | string | the codebook version |
| `configuration` | string | the label's configuration |
| `structure_source` | string | the label's structure source |
| `words` | int | the words of the text |
| `sentences` | int | the sentences of the text |
| `you_words` | int | the words "you", "your", "yours", "yourself" and "yourselves" |
| `sentences_with_you` | int | the sentences with at least one of those words |
| `command_sentences` | int | the sentences that open with a command (a base-form verb from a fixed list, or "Do not", "Don't" or "Never" with one) |
| `conditional_commands` | int | the sentences with a condition, a comma, then a command |
| `distinct_actions` | int | the number of different verbs that open the text's commands |
| `percentages` | int | the numbers followed by "%" or "percent" |
| `one_in_n` | int | the "1 in N" expressions |
| `frequencies` | int | the expressions of how often (a number of times a day, every so many hours, daily) |
| `doses` | int | the numbers followed by a dose unit (mg, mcg, mL and the like) |
| `contact_sentences` | int | the sentences that name a contact verb and someone to contact |
| `structured_sentences` | int | the sentences measured on structure (`current` labels only; null for `unlisted`; in `current` files only) |
| `structured_sentences_over_20` | int | the sentences over 20 words, on structure (`current` only) |
| `structured_sentences_over_40` | int | the sentences over 40 words, on structure (`current` only) |
| `structured_longest_sentence_words` | int | the words of the longest sentence, on structure (`current` only) |

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

## Text from the National Cancer Institute's cancer information summaries, with parts left out (configuration `nci`; `plainpairs nci-build`)
Three tables. A pair carries each page's address, dates and credit line for both of its pages
(`_a`, `_b`).

### Columns in every `nci` table (`nci_summaries`, `nci_pairs`, `nci_text`)
| column | type | notes |
|---|---|---|
| `configuration` | string | always `nci` |
| `source` | string | where the row was read: the National Cancer Institute's cancer information summaries, with their address |

### Columns of each page (`nci_summaries`, `nci_text`)
| column | type | notes |
|---|---|---|
| `url` | string | NCI's address for the page |
| `date_read` | string | the date the page was read |
| `nci_updated` | string | the date NCI gives for the page's last update |
| `credit_line` | string | the summary's title in quotation marks, then "was originally published by the National Cancer Institute.", then the page's address |

### `nci_summaries` (record layer): one row per summary page
| column | type | notes |
|---|---|---|
| `language` | string | `en` or `es` |
| `version` | string | `health_professional` or `patient` |
| `title` | string | NCI's own title for the summary |
| `topic_id` | string | the smallest address among the pages linked to it |
| `other_version_url` | string | the address of the page's other version, by NCI's own link |
| `other_language_url` | string | the address of the page in the other language, by NCI's own link |
| `text_sha256` | string | the SHA-256 over its kept blocks |
| `n_blocks` | int | the number of kept blocks |
| `references` | int | the references, counted, not kept |
| `left_out` | struct | the blocks left out, counted by kind: `figure`, `navigation`, `key_points`, `reference`, `citation_mark`, `about_this`, `credit_line`, `credited_table` |
| `measures` | struct | `words`, `sentences`, `long_sentence_share`; English `flesch_kincaid` and `smog`; Spanish `szigriszt_pazos` and `inflesz_band`; blocks by kind |
| `codes` | struct | the trusted codes, English only; null for Spanish |

### Fields of the left_out struct (`nci_left_out`)
| column | type | notes |
|---|---|---|
| `figure` | int | the figures left out |
| `navigation` | int | the navigation blocks left out |
| `key_points` | int | the key-point blocks left out |
| `reference` | int | the references left out |
| `citation_mark` | int | the citation marks left out |
| `about_this` | int | the blocks of the closing "About This" sections left out |
| `credit_line` | int | the credit lines left out of the text (each row carries its own) |
| `credited_table` | int | the tables NCI credits to other publishers, left out whole |

### Fields of the NCI measures struct (`nci_measures`)
| column | type | notes |
|---|---|---|
| `words` | int | the words of the kept prose |
| `sentences` | int | the sentences |
| `long_sentence_share` | float | the share of sentences over 20 words |
| `flesch_kincaid` | float | the Flesch-Kincaid grade (English only) |
| `smog` | float | the SMOG grade (English only) |
| `szigriszt_pazos` | float | the Szigriszt-Pazos perspicuity index (Spanish only; higher is easier; provisional) |
| `inflesz_band` | string | the index's band on the INFLESZ scale (Spanish only) |
| `blocks_heading` | int | the kept headings |
| `blocks_paragraph` | int | the kept paragraphs |
| `blocks_item` | int | the kept list items |
| `blocks_cell` | int | the kept table cells |
| `blocks_data_cell` | int | the kept cells of data tables |
| `blocks_caption` | int | the kept captions |

### Fields of the NCI codes struct (`nci_codes`)
The trusted codes on the English text, as in the label `codes` tables (`docs/codebook.md`).

| column | type | notes |
|---|---|---|
| `you_words` | int | the words "you", "your", "yours", "yourself" and "yourselves" |
| `sentences_with_you` | int | the sentences with at least one of those words |
| `command_sentences` | int | the sentences that open with a command |
| `conditional_commands` | int | the sentences with a condition, a comma, then a command |
| `distinct_actions` | int | the number of different verbs that open the text's commands |
| `percentages` | int | the numbers followed by "%" or "percent" |
| `one_in_n` | int | the "1 in N" expressions |
| `frequencies` | int | the expressions of how often |
| `doses` | int | the numbers followed by a dose unit |
| `contact_sentences` | int | the sentences that name a contact verb and someone to contact |
| `sentences_over_20` | int | the sentences over 20 words |
| `sentences_over_40` | int | the sentences over 40 words |
| `longest_sentence_words` | int | the words of the longest sentence |

### `nci_pairs` (record layer): one row per pair found by NCI's own links
| column | type | notes |
|---|---|---|
| `pair_kind` | string | `version`: the health-professional and the patient summary in one language, `url_a` the professional one; `language`: one version in English and Spanish, `url_a` the English one |
| `language` | string | for a version pair, the language the pair shares |
| `version` | string | for a language pair, the version the pair shares |
| `url_a` | string | the address of the first page of the pair |
| `url_b` | string | the address of the second page of the pair |
| `linked_from` | string | which page links to the other: `both`, `a_only` or `b_only` |
| `topic_id` | string | the topic both pages belong to |
| `date_read_a` | string | the date the first page was read |
| `date_read_b` | string | the date the second page was read |
| `nci_updated_a` | string | the date NCI gives for the first page's last update |
| `nci_updated_b` | string | the date NCI gives for the second page's last update |
| `credit_line_a` | string | the first page's credit line |
| `credit_line_b` | string | the second page's credit line |

### `nci_text` (text layer): one row per kept block
| column | type | notes |
|---|---|---|
| `block_index` | int | the block's place in the page, from 0 |
| `kind` | string | `heading`, `paragraph`, `item`, `cell`, `data_cell` or `caption` |
| `level` | int | a heading's level (0 for other blocks) |
| `table` | int | the number of the table a cell belongs to (0 outside a table) |
| `text` | string | the block's text |
| `sha256` | string | the SHA-256 of `text` |

Released with its credit line under the switch for this configuration (`docs/data-card.md`);
never a left-out block.

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

**The NCI configuration.** When the `nci` tables are present it also fails when a table lacks
its columns, holds a row of another configuration, or has a row without its address, date
read, NCI update date or credit line (or a credit line that does not name NCI and end with the
page's address); when `nci_text` holds a block of a left-out or unknown kind, or a block that
carries a credit or permission line; and when a summary's text hash does not match its blocks.
