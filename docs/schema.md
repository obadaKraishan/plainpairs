# Schema (DRAFT)

**DRAFT for the maintainer's review; nothing here is final.** Numbers come from the label API on
2026-11-15 (`docs/counts.md`) and from one bulk part (`docs/sample.md`).

## The decision: the unit
| option | one row per | rows, as far as S1 can tell | good for | weak for |
|---|---|---|---|---|
| **A** | label, with both sides | 35,840 labels with a Medication Guide or a patient package insert (23,224 and 12,837; 221 have both) | tracing any text to its label, set id and version; weekly changes; everything keyed by set id | many rows repeat the same patient text (generic copies), which inflates counts if read as "documents" |
| **B** | distinct patient text, listing the labels that carry it | between the number of medicines and the number of labels; in the sample, 478 distinct Medication Guides (closing lines ignored) among 520 labels, but duplicates mostly span parts, so S2 counts it on all labels | readability and content studies, where a text shared by 40 generic labels should count once | the prescriber side varies within a group (each manufacturer has its own prescriber label), so B holds no single prescriber text |
| **C** | aligned pair of sections (a patient segment and the prescriber section(s) it draws on) | about 270,000 (7.8 segments per guide and 7.0 per insert in the sample, times the label counts) | section-level comparison; the benchmark | depends on the alignment rule; needs its own quality check |

**Proposal: all three, as three tables of one release, with A as the backbone.**
- `labels` (A): one row per label in scope, both sides, identity, measures per text.
- `patient_texts` (B): one row per distinct patient text (by the hash that ignores case,
  punctuation and closing lines), its measures, and the list of set ids that carry it.
- `section_pairs` (C): one row per patient segment, with its heading key, the matched
  prescriber section(s), the rule that matched them and a similarity score.

## The decision: the scope
| question | numbers | proposal |
|---|---|---|
| Prescription only, or Drug Facts too? | Drug Facts labels are themselves written for consumers and have no prescriber text to pair with: 49,694 labels are typed over the counter (among the third with a product type). Only 100 typed over-the-counter labels have a Medication Guide or an insert. In the sample, 783 of the 787 labels with either are in a prescription format. | **Prescription formats only**: the newer format (with a "Warnings and Precautions" section) and the older one. Drug Facts out; their 100 or so labels with a guide or insert listed separately. |
| Product type or format? | 59% of labels with a Medication Guide and 57% of those with either text have no `openfda` block, so no product type; in the sample nearly all of them are prescription-format labels | **Decide by format**, which every label has; keep product type as a column where it exists. |
| Which fields count as a patient version? | `spl_medguide` 23,224; `spl_patient_package_insert` 12,837; `instructions_for_use` 6,503 (of the typed ones, 1,647 prescription and 1,380 over the counter); `patient_medication_information` 1,380; `information_for_patients` 67,916 | **Medication Guide and patient package insert** define the scope. Instructions for use are kept as a third patient text when the label has one (they are written for patients but cover handling, not the medicine). `patient_medication_information` is kept as a flagged "other patient text" (a mixed field, `docs/sources.md` section 7). `information_for_patients` is **not** a patient version: it holds section 17 (Patient Counseling Information) or the older "Information for Patients", both written to the prescriber, and goes on the prescriber side. |
| Labels with a guide but no `spl_medguide` field | 775 labels have "medication guide" in `spl_unclassified_section` and 1,147 in `information_for_patients`, with no `spl_medguide` (some are only the line "Dispense with Medication Guide") | S2 checks a sample by hand before deciding whether any of these hold a full guide. |

## Table `labels` (A)
| column | type | notes |
|---|---|---|
| `set_id` | string | stable across versions; the key |
| `id` | string | this version's document id |
| `version` | integer | |
| `effective_date` | date | null when the source date is not a date (a few lie in the future) |
| `label_format` | `plr` / `older` | the scope rule |
| `harmonized` | boolean | whether the source's `openfda` block exists |
| `product_type`, `routes`, `application_numbers`, `manufacturers`, `brand_names`, `generic_names`, `pharm_classes_epc` | string / list | from the `openfda` block; empty when it is missing |
| `prescriber.<section>` | string | `boxed_warning`, `indications_and_usage`, `dosage_and_administration`, `contraindications`, `warnings_and_precautions`, `adverse_reactions`, `drug_interactions`, `use_in_specific_populations`, `patient_counseling_information`, `description`, `how_supplied_storage`; headings kept |
| `patient.<text>` | string | `medication_guide`, `patient_package_insert`, `instructions_for_use`, `patient_medication_information` |
| `tables` | list of (section, text) | HTML tables as plain rows |
| `measures.<side>.<text>` | struct | words, sentences, Flesch-Kincaid, SMOG, flags (`docs/codebook-draft.md`) |
| `patient_text_id` | string | links to `patient_texts` |
| `source_fields` | list | the source fields this row was read from |
| `source_export_date` | date | the bulk export the row came from |

## Table `patient_texts` (B)
`patient_text_id` (the hash), `kind`, `text`, `measures`, `set_ids` (list), `n_labels`,
`n_manufacturers`, `generic_names` (union), `first_seen`, `last_seen`.

## Table `section_pairs` (C)
`set_id`, `kind` (guide or insert), `segment_index`, `heading_key` (one of the ten standard
keys, or `preamble`, or `other`), `heading` (as written), `patient_text`, `prescriber_sections`
(list of section names), `match_rule` (`regulation` or `similarity`), `similarity`,
`measures.patient`, `measures.prescriber`.

## Records, frozen and strict
The S1 parser already builds `labels` rows as frozen pydantic models that refuse unknown
fields (`src/plainpairs/schema.py`). Released files are Parquet by export date, as in the
CommonsWire layout.
