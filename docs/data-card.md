# PlainPairs data card (DRAFT)

**DRAFT for the maintainer's review. Nothing has been released.** Sizes are those of the build
from the openFDA drug label export of 2026-11-13.

## What it is
A research record of how United States medicine labels are worded for two readers. For every
label in a prescription format that carries a Medication Guide or a patient package insert, it
holds the label's sections written for prescribers next to its texts written for patients,
matched section by section, with reading-level and plain-language measures on both sides.

## What it is not
- **Not medical information.** A record of wording. The labels may be out of date, incomplete
  or replaced, and the cancer information text may be out of date too; never use any of it to
  decide anything about a medicine or about care. Read the label that comes with the medicine
  and ask a doctor or pharmacist; current cancer information is on the National Cancer
  Institute's own site (https://www.cancer.gov).
- **Not a judgment of any medicine.** The measures describe wording only.
- **Not about people.** Labels hold no information about patients, and nothing is added.
- **Not a list of medicines on the market.** The source keeps the latest version of each label
  it holds, whether or not the product is still listed. On the days the two lists were read
  (the NDC directory of 2026-11-13, DailyMed's label list of 2026-11-15), 15,022 of the 35,177
  labels (42.7%) were for products in the current NDC directory, DailyMed served 19,847
  (56.4%), and 15,318 (43.5%) were on neither list. Every label carries both flags
  (`listed_in_ndc_directory`, `served_by_dailymed`). What they do and do not mean:
  - the NDC flag equals the source's `openfda` block this week (every label with the block is
    in the directory, none without it), because openFDA fills the block from the directory;
    it is kept because the two could part when refreshed on different days;
  - "served by DailyMed" means only that DailyMed lists the label. It does not mean the product
    is marketed, and this card never says so;
  - a label on neither list may be for a product no longer marketed, or one these lists do not
    cover.
- **Not official.** Not made, endorsed or checked by the U.S. Food and Drug Administration, the
  National Library of Medicine or any company whose labels it describes.

## The source, its credit line and its disclaimer
The openFDA drug label bulk files (<https://open.fda.gov/data/spl/>; license page: "Public
Domain and CC0"), export of 2026-11-13. The companies that market each medicine write its
label. The source asks for this credit, though it does not require it:

> Data provided by the U.S. Food and Drug Administration (https://open.fda.gov)

and states:

> Do not rely on openFDA to make decisions regarding medical care. Always speak to your health
> provider about the risks and benefits of FDA-regulated products.

## Honest sizes (export of 2026-11-13)
| | count |
|---|---:|
| labels in the export | 264,748 |
| labels in a prescription format with a guide or an insert (table A) | 35,177 |
| of those, newer format / older format | 25,796 / 9,381 |
| of those, with the source's `openfda` block | 15,022 (42.7%) |
| with a Medication Guide / a patient package insert / both | 22,872 / 12,519 / 214 |
| with instructions for use / with the mixed "other" patient field | 2,059 / 146 |
| distinct Medication Guides (exact / loose / core) | 15,308 / 14,820 / 12,006 |
| distinct patient package inserts (exact / loose / core) | 9,168 / 8,990 / 7,769 |
| patient text groups in table B (all four kinds) | 21,416 |
| distinct medicine keys (from the `openfda` block, and through shared texts) | 1,713 or more |
| labels with no medicine key | 16,122 |
| labels with a product name read from their product data / distinct product names | 34,406 / 3,676 |
| labels in the current NDC directory / served by DailyMed / on neither list | 15,022 / 19,847 / 15,318 |
| configuration `current` (structure from DailyMed's XML) / `unlisted` (JSON only) | 19,778 / 15,399 |
| distinct guides / inserts in `current` (at least one current label) | 7,182 of 12,006 / 4,576 of 7,769 |
| section pairs in table C | 250,829 |
| … whose heading key passed the hand topic check (`rule_status = rule_released`) / did not (`similarity_only`) | 7 keys / 3 keys (before taking, avoid, general information) |
| labels typed over the counter with a guide or insert (listed apart, not in scope; all such labels in the export, 92 in the Drug Facts format and 8 in the newer prescription format) | 100 |

"Distinct medicines" are distinct sets of generic names from the source's `openfda` block,
which most labels lack. A label without it borrows the key of labels that carry the same
patient text (the same core hash: identical once case, punctuation and the closing lines that
name the maker are set aside); 16,122 labels have neither, so the count of medicines is a
lower bound. No medicine key is read from the label text.

Product names are a separate column, read from each label's structured product data
(`spl_product_data_elements`), not from its prose, and never merged into the medicine key.
Where a label also has the `openfda` block, the name read agrees with one of its brand names for
14,339 of 14,818 labels (96.8%). The 3,676 distinct product names (case ignored) are therefore
reported beside the 1,713 or more distinct medicines: a product name is not a medicine.

## Two layers and the switch
- **Record layer**, always releasable: `labels`, `patient_texts`, `section_pairs`,
  `excluded_otc`, and `codes` (the trusted rule-based codes only; `docs/codebook.md`).
  Identifiers, dates, formats, hashes, headings found, lengths, reading levels per
  configuration, counts, alignment keys and scores. No label text.
- **Text layer**: `text_prescriber` and `text_patient`, the cleaned texts keyed by label and
  section, each row with the label's `has_copyright_mark`.

3,781 of the 35,177 labels (10.7%) show a copyright sign, the word
"copyright" or "all rights reserved" somewhere in their text. The switch decides what text a
release carries. **For the first release the maintainer chose `unmarked`:** 68,156 text rows of
marked labels are held back; their record rows stay, and their text can be rebuilt from the
source with `plainpairs text`. The NCI configuration's kept text is released with its credit
line.

Rows of the text layer (a section's text and each of its tables are separate rows):

| setting | prescriber rows | patient rows |
|---|---:|---:|
| all | 512,274 | 68,710 |
| only where no mark is found | 456,309 | 56,519 |
| none | 0 | 0 |

Counted as texts rather than rows, the middle setting releases 316,405 of 354,564 prescriber
sections and 33,034 of 37,596 patient texts; 10,650 of the 12,006 distinct Medication Guides
and 6,173 of the 7,769 distinct patient package inserts have at least one unmarked label.

Whatever the setting, `plainpairs text` rebuilds the text layer from the record layer and the
source's own bulk files of the same export date, and confirms every row by its hash.

## Configurations
The release has three configurations. Two hold the labels, and no reading level is ever
computed across both; the third, `nci`, holds text from the National Cancer Institute's cancer information summaries, with parts left out (below):

- **`current`** (19,778 labels): DailyMed's full release of human prescription labels of the
  same week (2026-11-13) holds the label in the same version, and each of its patient texts
  with the same words as the source's JSON. The text's structure (paragraphs, list items,
  headings, tables) comes from that XML, and its reading levels are measured on the structure.
  Benchmark items come from this configuration only.
- **`unlisted`** (15,399 labels): every other label, measured from the JSON only and flagged
  so (`structure_source = json`). 15,122 are not in DailyMed's release, 268 are there only in
  another version, 8 lack a patient text in the XML and 1 has a patient text whose words
  differ.

The two are not the same as the lists above: the configuration rests on DailyMed's release of
the same week as the export, the "served" flag on its list of two days later.

## Reading levels
Grades are computed by stated formulas and are comparable only within one configuration and
one basis. Flesch-Kincaid and SMOG are always given together: neither alone is this corpus's
reading level, and they differ most just where readers ask (at grade 8). Over distinct texts
(each shared text once), export and release of 2026-11-13:

| | `current`, from structure | `current`, same texts, from the JSON | `unlisted`, from the JSON |
|---|---:|---:|---:|
| Medication Guides | 7,182 texts | 7,182 | 4,824 |
| median Flesch-Kincaid grade (middle half) | 8.67 (7.88 to 9.48) | 10.86 (9.68 to 11.87) | 10.70 (9.42 to 11.79) |
| above grade 8 by Flesch-Kincaid | 71.9% | 95.0% | 93.1% |
| median SMOG grade / above grade 8 | 11.10 / 99.2% | 12.94 / 99.5% | 12.85 / 99.5% |
| median share of sentences over 20 words | 11% | 22% | 21% |
| patient package inserts | 4,576 texts | 4,576 | 3,193 |
| median Flesch-Kincaid grade | 8.58 | 10.03 | 9.72 |
| above grade 8 by Flesch-Kincaid | 66.9% | 91.4% | 87.6% |
| median SMOG grade / above grade 8 | 11.21 / 99.5% | 12.46 / 99.6% | 12.20 / 99.7% |

**What may be said.** On `current` labels, reading levels may be reported as measured on the
label's structure, with both formulas: by Flesch-Kincaid most Medication Guides (72%) and
patient package inserts (67%) are above grade 8, and by SMOG nearly all are (99%). On
`unlisted` labels only grades from the flattened JSON exist; they are reported apart, flagged,
and run higher than the structure's on the same texts (guides: Flesch-Kincaid 10.86 against
8.67, SMOG 12.94 against 11.10), because lists that lost their marks read as long sentences.
No figure combines the two configurations.

## Text from the National Cancer Institute's cancer information summaries, with parts left out (configuration `nci`)
A third configuration, apart from the labels and never pooled with them in any number: text
taken from the National Cancer Institute's cancer information summaries, which NCI writes in a
version for health professionals and a version for patients, in English and Spanish. Read from
NCI's pages on 2026-11-15 (every summary in its sitemap, each page once). It is not the
summaries themselves: images, figures, tables credited to other publishers, references and the
closing sections are left out, so a record here must never be presented as an NCI summary
(NCI allows that name only for a whole, regularly updated summary).

| | English | Spanish |
|---|---:|---:|
| health-professional summaries | 242 | 220 |
| patient summaries | 147 | 147 |
| version pairs (professional and patient, by NCI's links) | 131 | 136 |
| language pairs (English and Spanish, by NCI's links) | 220 professional, 147 patient | |
| summaries without the other version | 111 professional, 16 patient | 84 professional, 11 patient |

Every pair comes from a link on NCI's own pages, and in every pair both pages link each other;
no other rule was needed. NCI's update dates run from 2013 to 2026-10-15; 645 of the 756 fall
in 2024 or 2025.

**Left out, and counted:** 1,562 images and figures, 763 tables credited to other publishers,
68,229 references (counted; their text is not kept), 88,795 citation marks, the key-point boxes
of patient summaries, the navigation, and the closing sections (purpose, reviewers, levels of
evidence, permission, citation, disclaimer).

**The release switch for this configuration:** the kept text may be released with its credit
line on every row ('"<title>" was originally published by the National Cancer Institute.' and
the page's address); nothing that is left out is ever kept. NCI also suggests linking to its
pages rather than copying them, so `plainpairs nci-text` rebuilds the text from NCI's pages
with the addresses and hashes of `nci_summaries`.

**Reading levels** (each summary once; English with both formulas, always together):

| | English Flesch-Kincaid | English SMOG | Spanish Szigriszt-Pazos (higher is easier) |
|---|---:|---:|---:|
| health-professional summaries (median) | 13.49 | 15.08 | 47.29 ("somewhat difficult") |
| patient summaries (median) | 8.65 | 11.11 | 57.82 ("normal") |
| above grade 8, patient summaries | 83% | 100% | |

In each of the 131 English version pairs the patient version reads lower on both formulas
(median differences: Flesch-Kincaid 4.84 grades, SMOG 3.90 grades), and it is less than half as
long (median 0.47 of the professional version's words). The Spanish index is a Spanish measure
of ease on the INFLESZ scale, validated on texts written for patients; it is not a school
grade and is never set beside an English grade. It is **provisional**: its syllable rule was
tested on 46 words, and a silent h is read as a consonant, so a few words count one syllable
too many. These figures describe NCI's summaries only:
they are a different kind of text from the labels and are never compared with the labels'
figures as if they were one corpus.

## Limits
- **The two configurations hold different labels.** `unlisted` labels are mostly labels that
  DailyMed's current release no longer carries; they are older on average and have no
  structure. A difference between the configurations is a difference between two sets of
  labels as well as between two ways of measuring, so the two are never compared as if they
  were one corpus measured twice.
- **Two bases sit side by side in the same tables.** Every label keeps its grades from the
  JSON (`p_<section>`, `t_<text>`), and `current` labels also have grades from structure
  (`p_<section>_structured`, `t_<text>_structured`). The column names and `structure_source`
  keep them apart; a reader who averages a column across configurations, or mixes the two
  kinds of column, gets a number that means nothing. Use one configuration and one basis at a
  time.
- **The source's JSON repeats some text.** When a subsection carries the same section code as
  the section around it, the JSON holds that subsection's words twice. This happens in 1.6% to
  3.3% of prescriber sections (and 2 Medication Guides) of labels DailyMed also holds; their
  JSON word counts are too high, and the section pairs, which are built from the JSON, carry
  the repeat too. The structure's measures do not.
## History
The source holds only the current version of each label. This corpus's history therefore
starts with its first release: each weekly release records the export date it was built from,
and labels that change or leave the source can be followed from then on. Older versions exist
on DailyMed's labeling archives but are not part of this corpus.

The record matters now because a proposed rule (88 FR 35694, 2023) would replace Medication
Guides and patient package inserts with a one-page Patient Medication Information, phased in
over five years once final (a final rule is planned for December 2026 and not yet published).
A weekly record would show the old texts giving way to the new ones.

## How to cite
A draft citation is in `CITATION.cff`; the DOI is added at the first release. Please also cite
the source with its credit line above. The nearest earlier work: Meyer et al. (2023), Neural text
generation in regulatory medical writing, *Frontiers in Pharmacology*
(doi:10.3389/fphar.2023.1086913), and the CLARA-MeD corpus (Campillos-Llanos et al., 2022).

## Takedown
A company or anyone else who believes a text should not be in a release can ask for its
removal through the repository's issue tracker (a takedown form will be added before the
first release); the record layer keeps the label's identifiers and measures.
