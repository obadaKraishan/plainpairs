# Facts for a data paper: PlainPairs 0.1.0

Every figure the dataset card and the method give for version 0.1.0, each with the file it comes
from and that file's date. Figures only: nothing here quotes a label or a cancer information
summary. No figure combines two configurations, except the pack's own file totals, which say how
much is in the files and measure nothing.

## Where the figures come from
| key | file | date |
|---|---|---|
| **M** | the pack's `manifest.json` (Hugging Face `obadakr/plainpairs`, tag `v0.1.0`) | built 2026-11-15, from the openFDA drug label export of 2026-11-13 |
| **C** | the dataset card, `README.md` on Hugging Face (`main`, after two card-only fixes; the data files are those of the tag) | 2026-11-16 |
| **D** | [`data-card.md`](data-card.md) | figures from the export of 2026-11-13; file as of 2026-11-16 |
| **K** | [`codebook.md`](codebook.md) (version 1), section "Status: trusted or experimental" | checked 2026-11-15 |
| **A** | [`method.md`](method.md), section 7 (alignment), and the hand sheet's result file `data/interim/sheet/sheet-result-seed20261116.json` (written by `plainpairs sheet-check`; not published) | scored 2026-11-15 |
| **Z** | the Zenodo record of the software and documents, <https://zenodo.org/records/24267451> | published 2026-11-16 |

## 1. The release
| fact | value | from |
|---|---|---|
| version | 0.1.0 | M |
| dataset | <https://huggingface.co/datasets/obadakr/plainpairs>, tag `v0.1.0` | C |
| Kaggle mirror | <https://www.kaggle.com/datasets/obadakraishan/plainpairs> | C |
| software and documents (no data table) | DOI 10.5281/zenodo.24267450 (all versions); version 0.1.0 is 10.5281/zenodo.24267451 | Z |
| Hugging Face configs | 16, one per table, none the default | M, C |
| the pack's files | 16 data files, 1,409,294 rows, 562,978,573 bytes (563.0 MB) | M |
| code version of the rule-based codes | 1 | M |

## 2. Sources and their dates
| source | date | from |
|---|---|---|
| openFDA drug label export | 2026-11-13 | M |
| openFDA NDC directory export (the "listed" flag) | 2026-11-13 | M |
| DailyMed label list read (the "served" flag) | 2026-11-15 | M |
| DailyMed full release of human prescription labels (the structure of `current`) | 2026-11-13 | M |
| National Cancer Institute pages read (every summary in the sitemap, each page once) | 2026-11-15 | M, D |

## 3. Sizes per configuration (M)
| configuration | table | config name | layer | rows | bytes | MB |
|---|---|---|---|---:|---:|---:|
| `current` | `labels` | `current_labels` | record | 19,778 | 20,232,902 | 20.2 |
| `current` | `patient_texts` | `current_patient_texts` | record | 12,857 | 2,481,702 | 2.5 |
| `current` | `section_pairs` | `current_section_pairs` | record | 143,885 | 5,112,444 | 5.1 |
| `current` | `codes` | `current_codes` | record | 221,072 | 2,916,198 | 2.9 |
| `current` | `text_prescriber` | `current_text_prescriber` | text | 260,290 | 242,600,795 | 242.6 |
| `current` | `text_patient` | `current_text_patient` | text | 33,003 | 41,400,336 | 41.4 |
| `unlisted` | `labels` | `unlisted_labels` | record | 15,399 | 11,019,869 | 11.0 |
| `unlisted` | `patient_texts` | `unlisted_patient_texts` | record | 8,559 | 1,263,903 | 1.3 |
| `unlisted` | `section_pairs` | `unlisted_section_pairs` | record | 106,944 | 3,942,169 | 3.9 |
| `unlisted` | `codes` | `unlisted_codes` | record | 171,088 | 1,820,322 | 1.8 |
| `unlisted` | `text_prescriber` | `unlisted_text_prescriber` | text | 196,019 | 184,556,597 | 184.6 |
| `unlisted` | `text_patient` | `unlisted_text_patient` | text | 23,516 | 29,150,934 | 29.2 |
| `nci` | `summaries` | `nci_summaries` | record | 756 | 127,307 | 0.1 |
| `nci` | `pairs` | `nci_pairs` | record | 634 | 49,302 | 0.0 |
| `nci` | `text` | `nci_text` | text | 195,394 | 16,298,819 | 16.3 |
| (a list, not a configuration) | `excluded_otc` | `excluded_otc` | record | 100 | 4,974 | 0.0 |

Per configuration: `current` 6 files, 690,885 rows, 314.7 MB; `unlisted` 6 files, 521,525
rows, 231.8 MB; `nci` 3 files, 196,784 rows, 16.5 MB (M).

## 4. The export and the scope (D, "Honest sizes", export of 2026-11-13)
| fact | value |
|---|---:|
| labels in the export | 264,748 |
| labels in a prescription format with a Medication Guide or a patient package insert | 35,177 |
| of those, newer format / older format | 25,796 / 9,381 |
| of those, with the source's `openfda` block | 15,022 (42.7%) |
| with a Medication Guide / a patient package insert / both | 22,872 / 12,519 / 214 |
| with instructions for use / with the mixed "other" patient field | 2,059 / 146 |
| distinct Medication Guides (exact / loose / core) | 15,308 / 14,820 / 12,006 |
| distinct patient package inserts (exact / loose / core) | 9,168 / 8,990 / 7,769 |
| patient text groups (all four kinds) | 21,416 |
| distinct medicine keys | 1,713 or more (a lower bound) |
| labels with no medicine key | 16,122 |
| labels with a product name read from their product data / distinct product names | 34,406 / 3,676 |
| product names that agree with a brand name of the `openfda` block | 14,339 of 14,818 (96.8%) |
| labels in the NDC directory / served by DailyMed / on neither list | 15,022 / 19,847 / 15,318 |
| `current` labels / `unlisted` labels | 19,778 / 15,399 |
| `unlisted`: not in DailyMed's release / there only in another version / no patient text in the XML / patient text with other words | 15,122 / 268 / 8 / 1 |
| distinct guides with at least one `current` label | 7,182 of 12,006 |
| distinct inserts with at least one `current` label | 4,576 of 7,769 |
| labels typed over the counter with a guide or insert (`excluded_otc`; all such labels in the export): Drug Facts format / newer prescription format | 100: 92 / 8 |

## 5. The switch (M, D)
| fact | value | from |
|---|---|---|
| labels | `unmarked`: text only for labels with no company copyright mark | M |
| NCI | `kept_text_with_credit`: the kept text, a credit line on every row | M |
| labels showing a copyright sign, "copyright" or "all rights reserved" | 3,781 of 35,177 (10.7%) | D |
| label text rows held back (marked labels) | 68,156 | M |
| text rows taken down (labels / NCI) | 0 / 0 | M |
| entries on the takedown list (set ids / addresses) | 0 / 0 | M |
| text-layer rows before the switch, prescriber / patient: all | 512,274 / 68,710 | D |
| the same, only where no mark is found | 456,309 / 56,519 | D |
| texts under `unmarked`: prescriber sections / patient texts | 316,405 of 354,564 / 33,034 of 37,596 | D |
| distinct guides / inserts with at least one unmarked label | 10,650 of 12,006 / 6,173 of 7,769 | D |
| experimental code columns left out of the release | 17 | M |

## 6. Reading levels, per configuration and basis (C, D; export of 2026-11-13)
Over distinct texts, each shared text once. Flesch-Kincaid and SMOG are always given together.

| | `current`, from structure | `current`, the same texts, from the JSON | `unlisted`, from the JSON |
|---|---:|---:|---:|
| Medication Guides (texts) | 7,182 | 7,182 | 4,824 |
| median Flesch-Kincaid grade (middle half) | 8.67 (7.88 to 9.48) | 10.86 (9.68 to 11.87) | 10.70 (9.42 to 11.79) |
| above grade 8 by Flesch-Kincaid | 71.9% | 95.0% | 93.1% |
| median SMOG grade / above grade 8 | 11.10 / 99.2% | 12.94 / 99.5% | 12.85 / 99.5% |
| median share of sentences over 20 words | 11% | 22% | 21% |
| patient package inserts (texts) | 4,576 | 4,576 | 3,193 |
| median Flesch-Kincaid grade | 8.58 | 10.03 | 9.72 |
| above grade 8 by Flesch-Kincaid | 66.9% | 91.4% | 87.6% |
| median SMOG grade / above grade 8 | 11.21 / 99.5% | 12.46 / 99.6% | 12.20 / 99.7% |

## 7. The `nci` configuration (D, M)
| | English | Spanish | from |
|---|---:|---:|---|
| health-professional summaries | 242 | 220 | D, M |
| patient summaries | 147 | 147 | D, M |
| version pairs (professional and patient, by NCI's links) | 131 | 136 | D |
| language pairs (English and Spanish, by NCI's links) | 220 professional, 147 patient | | D |
| summaries without the other version | 111 professional, 16 patient | 84 professional, 11 patient | D |

- Rows of `nci_pairs`: 634, the 131 + 136 version pairs and the 220 + 147 language pairs (M, D).
- NCI's update dates run from 2013 to 2026-10-15; 645 of the 756 summaries fall in 2024 or 2025
  (D).
- Left out, and counted: 1,562 images and figures, 763 tables credited to other publishers,
  68,229 references, 88,795 citation marks, plus the key-point boxes, the navigation and the
  closing sections (D).
- Reading levels, each summary once (D, C):

| | English Flesch-Kincaid | English SMOG | Spanish Szigriszt-Pazos, INFLESZ scale (higher is easier; provisional) |
|---|---:|---:|---:|
| health-professional summaries (median) | 13.49 | 15.08 | 47.29 ("somewhat difficult") |
| patient summaries (median) | 8.65 | 11.11 | 57.82 ("normal") |
| above grade 8, patient summaries | 83% | 100% | |
| above grade 8, health-professional summaries | 100% | 100% | |

- In each of the 131 English version pairs the patient version reads lower on both formulas:
  median differences of 4.84 grades (Flesch-Kincaid) and 3.90 grades (SMOG); it is a median of
  0.47 of the professional version's words (D).
- The Spanish syllable rule was tested on 46 words (D).

## 8. The trusted codes, and how they were checked (K, C)
A development check by one reader, not a validation, with no second coder and no agreement
statistic. Items were drawn with fixed seeds from distinct guides and inserts and from prescriber
sections, half each: 20 hits and 20 misses for the five codes first doubted, 10 and 10 for the
others. A code is trusted when at least 90% of its hits and at least 90% of its misses are
right.

| trusted code | hits right | misses right |
|---|---:|---:|
| direct address | 10/10 | 10/10 |
| instructions as commands | 10/10 | 10/10 |
| distinct actions | (counts the verbs of the command code) | |
| percentages | 10/10 | 10/10 |
| "1 in N" | 9/10, then 9/9 after the fix | 10/10 |
| frequencies | 9/10 | 10/10 |
| doses | 10/10 | 10/10 |
| whom to call | 36/40, then 36/36 after the fix | |
| long sentences, from structure (`current` only) | 19/20 | 20/20 |

Experimental codes, not released (hits right; misses right): whom to call with a "when" (20/20;
18/20, then 14/16), risk statements with a number (version 1, fresh draw 14/20; 20/20), vague
frequency words (15/20, then 15/18; 20/20), a term with its explanation (version 1, fresh draw
12/20; 18/20), long sentences from the JSON (8/20; 20/20), long sections from the JSON (8/20, 4
unclear; 20/20), long parts from structure (16/20, 2 unclear; 19/20) (K).

## 9. The alignment sheet, per heading key (A, C)
A blind hand sheet of 100 segments, 10 per heading key, drawn with seed 20261116; one coder
judged only whether the two passages are on the same topic. A heading key keeps its mapping
rule (`rule_status = rule_released`) when at least 80% of its rows are "yes" or "partly".

| heading key | yes | partly | no | yes or partly | 95% interval (Wilson) | `rule_status` |
|---|---:|---:|---:|---:|---|---|
| how to take | 9 | 1 | 0 | 100% | 72% to 100% | `rule_released` |
| ingredients | 9 | 1 | 0 | 100% | 72% to 100% | `rule_released` |
| most important information | 7 | 3 | 0 | 100% | 72% to 100% | `rule_released` |
| side effects | 9 | 1 | 0 | 100% | 72% to 100% | `rule_released` |
| storage | 6 | 3 | 1 | 90% | 60% to 98% | `rule_released` |
| what it is | 7 | 3 | 0 | 100% | 72% to 100% | `rule_released` |
| who should not take it | 9 | 1 | 0 | 100% | 72% to 100% | `rule_released` |
| before taking | 0 | 7 | 3 | 70% | 40% to 89% | `similarity_only` |
| what to avoid | 1 | 4 | 5 | 50% | 24% to 76% | `similarity_only` |
| general information | 0 | 4 | 6 | 40% | 17% to 69% | `similarity_only` |

Section pairs per configuration: `current` 143,885, `unlisted` 106,944 (M).

## 10. Limits (C, D)
- The two label configurations hold different labels: `unlisted` labels are mostly ones
  DailyMed's current release no longer carries, older on average, with no structure.
- Two measurement bases sit side by side in the label tables (`p_<section>` and `t_<text>`
  from the JSON; `p_<section>_structured` and `t_<text>_structured` from structure, `current`
  only).
- The source's JSON repeats subsections that carry their parent's section code in 1.6% to 3.3%
  of prescriber sections, and in 2 Medication Guides, of labels DailyMed also holds; their JSON
  word counts are too high, and the section pairs carry the repeat too.
- The count of medicines is a lower bound (1,713 or more; 16,122 labels have no medicine key).
- The Spanish index is provisional (its syllable rule was tested on 46 words) and is never set
  beside an English grade.
- The code check and the alignment check were each done by one reader; ten rows per heading key
  give wide intervals.

## Version 0.2.0 (the first weekly update; separate from the figures above)
The paper describes version 0.1.0, so every section above keeps 0.1.0's figures. Version 0.2.0's
come from **M2**, its `manifest.json` (Hugging Face `obadakr/plainpairs`, tag `v0.2.0`, built
2026-11-27), and **U**, the update's `summary.json` (counts only).

| figure | value | from |
|---|---|---|
| version | 0.2.0 (tag `v0.2.0`) | M2 |
| openFDA drug label export | 2026-11-26 (14 parts, 265,067 labels listed) | M2, U |
| openFDA NDC directory export / DailyMed's label list read | 2026-11-26 / 2026-11-27 | M2 |
| DailyMed: full release / update files through | 2026-11-13 / 2026-11-25 (one weekly file, three daily files) | M2, U |
| NCI pages read | 2026-11-15 (carried over from 0.1.0, the same SHA-256) | M2, U |
| files, rows, Parquet | 16 configs, 1,410,823 rows, 563.7 MB | M2 |
| `current`: labels / rows / MB | 19,820 / 692,539 / 315.6 | M2 |
| `unlisted`: labels / rows / MB | 15,396 / 521,401 / 231.6 | M2 |
| `nci`: summary pages / rows / MB | 756 / 196,784 / 16.5 | M2 |
| `excluded_otc` | 99 labels | M2 |
| text rows held back (a copyright mark) | 68,198 | M2 |
| against 0.1.0: new labels / left scope / withdrawn | 41 / 2 / 0 | U |
| against 0.1.0: changed texts / new versions with the same texts / record fields only | 126 / 125 / 181 | U |
| moved `unlisted` to `current` / `current` to `unlisted` | 7 / 0 | U |
| structure rows carried / read from the update files | 218,832 / 2,721 | U |
| easy-access files | 21 files, 789.8 MB | M2 |

Reading levels of 0.2.0 (M2, `facts.reading_levels`; the card's table, computed from the
version's own files; medians over distinct texts, shares above grade 8):

| | Flesch-Kincaid | SMOG | above grade 8, FK / SMOG | texts with a grade |
|---|---:|---:|---:|---:|
| Medication Guides, `current`, from structure | 8.67 | 11.10 | 71.9% / 99.2% | 7,105 |
| the same guides, from the JSON | 10.86 | 12.94 | 95.0% / 99.5% | 7,150 |
| Medication Guides, `unlisted`, from the JSON | 10.70 | 12.85 | 93.1% / 99.5% | 4,808 |
| patient package inserts, `current`, from structure | 8.58 | 11.21 | 66.8% / 99.5% | 4,551 |
| NCI patient summaries (English) | 8.65 | 11.11 | 83% / 100% | 147 |
| NCI health-professional summaries (English) | 13.49 | 15.08 | 100% / 100% | 242 |
