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
  or replaced; never use them to decide anything about a medicine. Read the label that comes
  with the medicine and ask a doctor or pharmacist.
- **Not a judgment of any medicine.** The measures describe wording only.
- **Not about people.** Labels hold no information about patients, and nothing is added.
- **Not a list of medicines on the market.** The source keeps the latest version of each label
  it holds, and many may be for products no longer listed: in a test of 20 labels, DailyMed's
  service for current labels did not have 7, and all 7 lacked the source's `openfda` block
  (which 57% of the labels here lack).
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
| distinct medicine keys (from the `openfda` block, and through shared texts) | 1,713 |
| labels with no medicine key | 16,122 |
| section pairs in table C | 259,911 |
| labels typed over the counter with a guide or insert (listed apart, not in scope) | 100 |

"Distinct medicines" are distinct sets of generic names from the source's `openfda` block,
which most labels lack. A label without it borrows the key of labels that carry the same
patient text (the same core hash: identical once case, punctuation and the closing lines that
name the maker are set aside); 16,122 labels have neither, so the count of medicines is a
lower bound. No name is read from the label text.

## Two layers and the switch
- **Record layer**, always releasable: `labels`, `patient_texts`, `section_pairs` and
  `excluded_otc`. Identifiers, dates, formats, hashes, headings found, lengths, reading levels,
  counts, alignment keys and scores. No label text.
- **Text layer**: `text_prescriber` and `text_patient`, the cleaned texts keyed by label and
  section, each row with the label's `has_copyright_mark`.

3,781 of the 35,177 labels (10.7%) show a copyright sign, the word
"copyright" or "all rights reserved" somewhere in their text. The switch decides what text a
release carries:

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

## Reading levels
Grades are computed by stated formulas (Flesch-Kincaid, Flesch reading ease, SMOG) on prose
with the inline tables cut, with a sentence rule that breaks at list marks and headings. They
are comparable within this corpus, not the grade of the printed page. No reading-level figure
is given here yet: the source's JSON loses the structure of lists and subsections, which raises
the grades, and a test against the structured SPL XML (`docs/xml-test.md`) shows by how much.
Figures will be stated once the corpus measures text with its structure.

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
