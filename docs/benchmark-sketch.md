# Benchmark sketch (phase 2; nothing built)

**A sketch for discussion, not a plan.** Planned for S5, on Kaggle Community Benchmarks.

## Task
Given a prescriber section (or the prescriber sections a heading draws on, from `section_pairs`)
and a heading key, write the patient segment for that heading at a set reading level (for
example grade 6 or grade 8). The model sees the prescriber text only, never the patient text.

## Gold text
The official patient segment of the same label: the Medication Guide or patient package insert
section aligned to the prescriber section(s) (`docs/method.md`, section 5). Only pairs whose
alignment passed the hand check are used, one per distinct patient text (the `patient_texts`
grouping), so a guide shared by 40 generic labels is one item, not 40.

## Scores
1. **Reading level reached:** Flesch-Kincaid and SMOG of the answer against the target (the
   absolute difference), with the same rules as the corpus.
2. **Facts kept:** of the facts in the gold segment, the share the answer keeps. The
   first version uses checkable facts only: numbers (doses, frequencies, ages, percentages),
   named side effects and conditions, and instructions (imperatives), matched by rule after
   normalization. A judge model would come later and only after it agrees with hand scores.
3. **Numbers kept:** the share of numbers in the prescriber text that the gold keeps, and whether
   the answer keeps the same ones; a number the gold does not have and the answer adds is counted
   as an addition, not a reward.
4. **Additions:** statements in the answer that are in neither the prescriber text nor the gold
   (a rule flags new numbers and new named conditions).
5. **Closeness to the gold** (secondary): ROUGE-L or a similar overlap, reported but not
   ranked on, since many good rewrites differ from the official wording.

## Fresh items every week
The source changes every week: new labels and new versions of old ones. A weekly set of items
from labels whose patient text is new or changed since the last release (by core hash) gives
test items that could not have been in a model's training data before their effective date.
Results are reported by item date, so a model's score on items dated after its training
cutoff can be told apart from its score on older ones.

## What could go wrong
- **Texts seen in training.** Labels have been public for years and are in web crawls and the
  frozen copies listed in `docs/prior-art.md`. Old items measure memory as much as rewriting;
  the dated weekly items are the answer, together with a canary string in every released file.
- **Outputs taken for advice.** A model's patient-style text about a real medicine can read like
  an official leaflet. Generated answers are never published as text, only as scores; the
  benchmark's pages say plainly that outputs are not medical information; items keep the
  official disclaimer.
- **The gold is not ideal.** Official patient texts score above grade 8 in nearly every case
  (`docs/sample.md`), so a model that writes plainer text than the gold should not be penalized
  for it; that is why the reading-level score is against the target, not against the gold.
- **Alignment errors** put the wrong gold next to a prompt; only hand-checked heading keys are
  used.
- **Generic copies** would weight a few medicines heavily; items are drawn per distinct text and
  balanced by heading key.
- **Rights.** The benchmark redistributes label text, so it waits for the same terms decision as
  the corpus.
