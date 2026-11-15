# Benchmark design (DRAFT; nothing built)

**DRAFT for the maintainer's review.** This replaces the first sketch (`docs/benchmark-sketch.md`)
as the design. Nothing here is built or run. It is a research benchmark of rewriting text for
a reading level; it never produces, checks or publishes information about medicines.

## 1. The task and its inputs
**Task:** rewrite a passage written for prescribers so that a general reader can follow it, at
a set reading level, for one patient-text heading.

**One item per distinct patient text.** Items come from the `current` configuration only
(section 7). The unit is a distinct Medication Guide or patient
package insert (by core hash, the `patient_texts` table), never a label: a guide shared by 40
labels is one item. For each distinct text, one of its heading segments is drawn with a seed,
balanced across heading keys, so that every key has about the same number of items. Only
segments of two sentences or more are drawn, and only heading keys whose mapping passed the
hand topic check (80% "yes" or "partly", `docs/hand-sheet-guide.md`).

**What the model sees:**
- the heading, with the medicine's name as the label writes it (for example "How should I take
  [product name]?");
- the prescriber section the heading is mapped to (`section_pairs.mapped_present`); where a
  heading maps to two or three sections, the one with the highest similarity to the segment,
  so that the input is one section; cut at 1,200 words, with the cut marked;
- the target: "Write for a reader at about US school grade 8" (section 7).

**What the model never sees:** the official patient segment (the gold), other parts of the
patient text, or any score.

**The gold:** the official segment body of that text (one representative label, the one whose
exact text is most common in the group).

## 2. Splits, held-out items and fresh items
- **Splits by distinct text,** stratified by heading key and by text kind (guide or insert):
  a development split of 200 items and a test split of 1,000 (section 7). Near-duplicate texts (the same
  loose hash, or a trigram Jaccard of 0.8 or more between segments) go to the same split.
- **Held out:** the test split's gold texts are not put in the benchmark's released files; only
  their ids, hashes and dates are. This limits how often input and gold sit side by side in a
  public file. It does not hide them: every label is public at its source (section 4).
- **Fresh items each week,** from the `changes` table of each new export:
  1. labels marked `new_label` or `texts_changed` whose guide or insert has a core hash not
     seen in any earlier build;
  2. of those texts, the heading segments whose body differs materially from every earlier
     version known to the corpus (trigram Jaccard below 0.8 against the previous version's
     segment, which the previous build's text layer holds; openFDA keeps current versions
     only, so these comparisons need the weekly builds to be kept);
  3. each such segment becomes an item dated by the export in which it first appeared, with
     the label's effective date beside it.
  How many fresh items a week yields is not known until two exports have been compared; it is
  measured before any schedule is set.
- **Results are reported by item date:** for each model, the score on items first seen after
  the model's stated training cutoff is reported apart from the score on older items.

## 3. Scores
Every score is computed per item and averaged over items, by heading key and overall.

| score | how it is computed | needs a model as judge? |
|---|---|---|
| **Reading level reached** | Flesch-Kincaid grade and SMOG of the output, by the corpus's own rules (sentence rule `s2`); the score is the absolute distance from the target grade, and the share of outputs within one grade of it. The gold's own grade is reported beside it, never used as the target, because official texts mostly sit above the usual plain-language targets | no |
| **Numbers kept** | the numbers in the gold segment (digits and number words, with their units normalized: "twice a day" and "2 times a day" are one), and the share the output keeps; numbers in the output that are in neither the input nor the gold are counted as **added numbers** | no |
| **Key facts kept** | version 1, by rule: the key phrases the gold took from the input (content words and two- and three-word phrases found in both the input and the gold, after a stop list), and the share the output keeps. Version 2, only if version 1 proves too blunt: a judge model that matches facts, used only after it agrees with hand scores on at least 100 items (Krippendorff's alpha of 0.67 or more), with an Apache-2.0 or MIT model | version 1 no; version 2 yes |
| **Nothing added** | version 1, by rule: added numbers, and named terms (content words or phrases) in the output that are in neither the input nor the gold, per 100 output words. Whether an added sentence is a claim the input does not support needs a judge (an entailment model) and is version 2 only, under the same agreement test | version 1 no; version 2 yes |
| Closeness to the gold (secondary) | an overlap measure such as ROUGE-L; reported, never ranked on, since good rewrites differ from the official wording | no |
| Copying (a flag, not a score) | the longest word span the output shares with the gold that is not in the input; a span of 25 words or more is flagged as likely recall of the official text | no |

## 4. Training data: what is known, and how the design limits it
- **Known:** every label in the corpus is public at its source, openFDA's bulk files have been
  downloadable for years, the label pages are on DailyMed, and frozen copies of label text are
  shared in public datasets (`docs/prior-art.md`). Any model trained on a web crawl has likely
  seen many gold texts, often many times, since generic labels repeat one wording.
- **What the design does about it:**
  - fresh weekly items, dated by first appearance, with results split by item date against
    each model's training cutoff (section 2);
  - one item per distinct text, so a wording repeated across 40 labels counts once;
  - the copying flag (section 3), reported per model;
  - a canary string in every released benchmark file, so the files can be found and left out of
    training sets;
  - test golds kept out of the benchmark's own files.
- **What it cannot do:** prove that a model has not seen a text. The dated split is the
  evidence; scores on older items are reported as possibly inflated by memory.

## 5. Outputs mistaken for advice
**The risk:** an output is a patient-style passage about a real medicine. It can read like an
official leaflet while it leaves out a warning, changes a number or adds a claim. If it is
shown on a page or shared, someone could take it as information about their medicine.

**What prevents it:**
- model outputs are **never published as text**: only scores and the counts behind them. Any
  example output shown in documentation is for an invented medicine;
- the task is framed as rewriting a passage for a reading level, not as advising anyone;
- every benchmark page, file and card carries this wording:

  > PlainPairs is a research benchmark of how text is rewritten for a reading level. The texts
  > models write in it are unchecked machine output, not medical information, and they may be
  > wrong, incomplete or out of date. Never use them to decide anything about a medicine. For
  > information about a medicine, read its official label or ask a pharmacist or doctor.

- the official labels' own disclaimers stay with the items, and the corpus's statement that
  labels in it may be out of date applies to every item.

## 6. Running it on Kaggle Community Benchmarks
- **Items** live in a Kaggle dataset (ids, hashes, dates, inputs; the test split's golds only
  where the release terms allow text, section 7). The benchmark's tasks read it.
- **Tasks:** one task per target grade, written with Kaggle's benchmarks library. Each task
  sends one prompt per item to the model under test and scores the reply in plain Python with
  the rules of section 3 (the corpus's own readability code), so version 1 needs no judge and
  no second model.
- **Model calls per run** (one model, one target grade):

  | design | items | calls |
  |---|---:|---:|
  | test split, version 1 (no judge) | 1,000 | 1,000 |
  | the same, both targets (grades 6 and 8) | 1,000 | 2,000 |
  | version 2, one judge call per item | 1,000 | 2,000 (1,000 under test, 1,000 judge) |
  | a weekly fresh set, version 1 | measured first (section 2) | one per fresh item |

  Each call sends about 1,700 tokens (the instructions and a section of up to 1,200 words) and
  returns about 350 (a 250-word segment), so 1,000 calls are about 1.7 million tokens in and
  0.35 million out per model and target. A pilot of 20 items on one model comes first, to
  measure tokens, time and quota before any full run.
- **Private first:** tasks stay private until the maintainer approves them, as with every
  release.

## 7. The maintainer's choices (2026-11-15)
The defaults for version 1, as decided. Nothing is built yet.

| choice | decided |
|---|---|
| the unit | one heading segment per distinct text |
| the target grade | grade 8 |
| the splits | 1,000 test items and 200 development items |
| which heading keys enter | only keys that pass the hand topic check (80% "yes" or "partly"): on the maintainer's sheet of 2026-11-15, how to take, ingredients, most important, side effects, storage, what is and who should not take it; not before taking, avoid or general information |
| the input cap | 1,200 words, one section per item (section 1) |
| the scores | rule-based scores only in version 1; a judge waits for version 2 and its agreement test |
| where items come from | **the `current` configuration only**: labels DailyMed serves in the same version as the export, whose structure comes from DailyMed's XML (`docs/method.md`, section 6b). Labels of the `unlisted` configuration are never items |
| which models | chosen at build time, within the free quota |

Still open, for the build session: whether the development split's texts are released (this
follows the corpus's text switch: all, unmarked, none), and the fresh-item threshold and
cadence (trigram Jaccard 0.8; weekly or monthly), which waits until two exports have been
compared.

With one target grade, a version 1 run is 1,000 calls per model (section 6). The reading level
reached is scored by the corpus's own rules; since items come from `current`, the gold's own
grade beside it is the grade measured on its structure (`docs/method.md`). That is not the
basis the output is measured on (plain text, sentence rule `s2`), so the gold's grade is shown
beside the score and never compared with the output's.
