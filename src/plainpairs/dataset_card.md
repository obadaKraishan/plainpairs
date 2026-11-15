---
license: other
license_name: plainpairs-sources
license_link: https://huggingface.co/datasets/obadakr/plainpairs/blob/main/LICENSES.md
language:
- en
- es
pretty_name: PlainPairs
size_categories:
- 100K<n<1M
tags:
- health-literacy
- readability
- plain-language
- medicine-labels
- text-pairs
configs:
$configs
---

# PlainPairs

> **Not medical information.** PlainPairs is a research record of how the text of United
> States medicine labels is worded, for prescribers and for patients. The labels in it may be
> out of date, incomplete or replaced by newer versions. **Never use it to decide anything
> about a medicine.** For that, read the current label that comes with the medicine and talk
> to a doctor or pharmacist. Nothing here says what a medicine does, whether it is safe, or
> who should take it.

Version $version, built from the openFDA drug label export of $export.

## What it is, and who it is for
For every label in a prescription format that carries a Medication Guide or a patient package
insert, PlainPairs holds the label's sections written for prescribers next to its text written
for patients, matched section by section, with reading-level and plain-language measures on
both sides. A separate configuration holds $nci_name, in a health-professional and a patient
version, in English and Spanish. It is for researchers who study health communication,
readability and plain language, and for those who build and test text-simplification tools.

## Load one table
Every table of every configuration is its own config; there is no default, so nothing loads
the configurations together by accident.

```python
from datasets import load_dataset

labels = load_dataset("obadakr/plainpairs", "current_labels", split="train")
guides = load_dataset("obadakr/plainpairs", "current_text_patient", split="train")
nci = load_dataset("obadakr/plainpairs", "nci_summaries", split="train")
```

## Three configurations, never pooled
| configuration | what it holds | labels or summaries |
|---|---|---:|
| `current` | labels that DailyMed serves in the same version as the export; their text structure (paragraphs, list items, headings, tables) comes from DailyMed's XML, and their reading levels are measured on that structure | $n_current_labels labels |
| `unlisted` | every other label, measured from the source's JSON only | $n_unlisted_labels labels |
| `nci` | $nci_name | $n_nci_summaries summaries |

Each configuration has its own record tables (labels, distinct patient texts, section pairs,
trusted codes; or summaries and pairs) and its text tables. **No number in this card or in the
project's documents combines two configurations,** and no file holds rows of two. They hold
different sets of texts, measured in different ways: a difference between them is not a
measured change.

## What "listed" means, and what it does not
Every label carries two flags, read on the days the two lists were read (the NDC directory of
$ndc, DailyMed's label list of $dailymed_list):

- `listed_in_ndc_directory`: the product is in FDA's current NDC directory. This week it equals
  the source's `openfda` block, because openFDA fills that block from the directory.
- `served_by_dailymed`: DailyMed lists the label. **This does not mean the product is
  marketed.**

A label on neither list may be for a product no longer marketed, or one these lists do not
cover. The source keeps the latest version of each label it holds, whether or not the product
is still sold, so this is not a list of medicines on the market.

## Reading levels
Grades are computed by stated formulas, always **Flesch-Kincaid and SMOG together**, per
configuration and per basis; neither alone is the corpus's reading level. Over distinct texts,
export of $export:

| | Flesch-Kincaid (median) | SMOG (median) | above grade 8, FK / SMOG |
|---|---:|---:|---:|
| Medication Guides, `current`, from structure | 8.67 | 11.10 | 71.9% / 99.2% |
| the same guides, from the JSON | 10.86 | 12.94 | 95.0% / 99.5% |
| Medication Guides, `unlisted`, from the JSON | 10.70 | 12.85 | 93.1% / 99.5% |
| patient package inserts, `current`, from structure | 8.58 | 11.21 | 66.9% / 99.5% |
| NCI patient summaries (English) | 8.65 | 11.11 | 83% / 100% |
| NCI health-professional summaries (English) | 13.49 | 15.08 | 100% / 100% |

The JSON loses list items and headings, so its grades run higher than the structure's on the
same texts; the two bases sit in separate columns (`t_<text>` and `t_<text>_structured`).

**Spanish (provisional).** Spanish NCI summaries are measured with the Szigriszt-Pazos
perspicuity index on the INFLESZ scale (higher is easier): health-professional summaries 47.29
("somewhat difficult"), patient summaries 57.82 ("normal"). Its syllable rule was tested on 46
words only, and a silent h is read as a consonant, so a few words count one syllable too many.
It is an ease score, not a school grade, and it is never set beside an English grade.

## Codes of wording
The `codes` tables hold **trusted codes only**: direct address, commands, distinct actions,
percentages, "1 in N", frequencies, doses, whom to call, and (for `current`) long sentences
measured on structure. Each code was checked by hand on 10 to 20 hits and misses by **one
reader, as a development check, not a validation**; a code was trusted when at least 90% of
its hits and of its misses were right. Experimental codes are not released.

## Alignment
Each segment of a guide or insert (one per standard heading) is matched to the prescriber
sections its heading points to. A blind hand check of **100 pairs by one coder** asked only
whether the two passages are on the same topic. Seven heading keys passed (80% "yes" or
"partly") and keep their mapping rule (`rule_status = rule_released`): how to take, ingredients,
most important information, side effects, storage, what it is, who should not take it. Three
did not and carry similarity scores only (`similarity_only`): before taking, what to avoid,
general information.

## Sources, terms and credit
**openFDA** (the labels; export of $export). Its terms: "Unless otherwise noted, the content,
data, documentation, code, and related materials on openFDA is public domain and made available
with a Creative Commons CC0 1.0 Universal dedication." Credit, as the source asks: **Data
provided by the U.S. Food and Drug Administration (https://open.fda.gov).** Its disclaimer
applies to everything here: "Do not rely on openFDA to make decisions regarding medical care.
Always speak to your health provider about the risks and benefits of FDA-regulated products."
The companies that market each medicine write its label; some labels carry a company's
copyright mark.

**DailyMed** (National Library of Medicine) is the source of the text structure of `current`
labels (its full release of human prescription labels of $dailymed_release) and of the
"served" flag. Courtesy of the National Library of Medicine.

**The National Cancer Institute** (the `nci` configuration; pages read on $nci_read). Its terms:
"Unless otherwise indicated, all text within National Cancer Institute (NCI) products is free
of copyright and may be reused without our permission. Credit the National Cancer Institute as
the source." Every row carries the credit line '"<title>" was originally published by the
National Cancer Institute.' with the page's address. Images, figures, tables that NCI credits
to other publishers, references and the closing sections are left out, so a row here is not
an NCI summary and must never be presented as one.

Not made, endorsed or checked by the U.S. Food and Drug Administration, the National Library of
Medicine, the National Cancer Institute or any company whose labels it holds. What applies to
each configuration is in [LICENSES.md](LICENSES.md).

## The text switch, and rebuilding the text
- **Labels:** text is released only for labels that show no company copyright mark
  (`unmarked`); $held_marked text rows of marked labels are held back. Their record rows stay,
  and anyone can rebuild their text from the source's own files with the project's
  `plainpairs text` command, by set id and hash.
- **NCI:** the kept text is released, each row with its credit line. `plainpairs nci-text`
  rebuilds it from NCI's own pages; pages NCI has updated since will differ.

## Removal
A company, or anyone else, may ask that a text be taken out: open a removal request on the
project's repository (https://github.com/obadaKraishan/plainpairs/issues/new/choose) with the
set id or the page address, who is asking, and why. The text row is removed in the next
version, the record row stays, and the request is answered within 14 days.

## Limits
- The two label configurations hold different labels: `unlisted` labels are mostly ones
  DailyMed's current release no longer carries, older on average, with no structure.
- Two measurement bases sit side by side in the label tables; use one configuration and one
  basis at a time.
- The source's JSON repeats subsections that carry their parent's section code (in 1.6% to
  3.3% of prescriber sections); their JSON word counts are too high, and the section pairs,
  built from the JSON, carry the repeat too.

## How to cite
Kraishan, O. PlainPairs: a research corpus pairing the prescriber and patient texts of US
medicine labels, version $version. https://huggingface.co/datasets/obadakr/plainpairs. Please
also give the sources' credit lines above.

## Files
$files_table

The manifest (`manifest.json`) gives every file's rows, size and SHA-256, the date of each
source and the switch setting.
