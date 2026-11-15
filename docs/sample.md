# The sample: one bulk part (2026-11-15)

**What it is.** Part 14 of the 14 drug-label bulk files of the 2026-11-13 export
(`drug-label-0014-of-0014.json.zip`, 39,297,061 bytes, SHA-256
`087e7a9c7af51c6b12a0e8fd611a27cb8635e1910ad160b89995da9a4b39b1b3`), the smallest part, saved
raw outside the repository. It holds 4,748 labels. Everything below is an aggregate; no label
text is reproduced.

**How the parts are ordered, and what kind of sample this is.** The part's own `meta` block
says `skip: 260000, limit: 4748, total: 264748`: the 14 parts are consecutive slices of one
ordering of all labels, 20,000 to a part, and this one is the last 4,748. That ordering is not
by set id and not by date (neither is sorted within the part), but the last slice is far newer
than the whole: 62.5% of its labels have an effective date in 2026, against 14.4% of all labels,
and 75.9% carry the harmonized `openfda` block, against 32.9% of all labels. The likeliest
reading is that records are added at the end when they are new or changed, so this part
over-represents recently added and updated labels. **It is not a random sample**, and its shares
should not be read as shares of the whole data; S2 reads all 14 parts.

## What the part holds

| | labels | share |
|---|---:|---:|
| all | 4,748 | 100% |
| distinct set ids | 4,748 | 100.0% |
| with the harmonized `openfda` block | 3,602 | 75.9% |
| product type: HUMAN OTC DRUG | 2,137 | 45.0% |
| product type: HUMAN PRESCRIPTION DRUG | 1,456 | 30.7% |
| product type: (none) | 1,146 | 24.1% |
| product type: PLASMA DERIVATIVE | 8 | 0.2% |
| product type: CELLULAR THERAPY | 1 | 0.0% |
| format: Drug Facts (over the counter) | 2,894 | 61.0% |
| format: newer prescription format (has `warnings_and_cautions`) | 1,137 | 23.9% |
| format: older prescription format | 656 | 13.8% |
| format: none of these | 61 | 1.3% |
| with a Medication Guide or a patient package insert | 787 | 16.6% |
| with `medication_guide` (not empty) | 520 | 11.0% |
| with `patient_package_insert` (not empty) | 271 | 5.7% |
| with `instructions_for_use` (not empty) | 133 | 2.8% |
| with `patient_medication_information` (not empty) | 24 | 0.5% |

One record per set id: the part holds only the current version of each label, as the source's
documentation says ("the most recent drug listing information companies have submitted").

**Text shape.** Every section is plain text without line breaks; a heading runs into its body.
Tables come separately as HTML (`*_table` fields: 439 Medication Guide tables in this part). Of
the 1,437 `information_for_patients` strings, 1,030 begin with "17 PATIENT COUNSELING
INFORMATION" (or "17."), the prescriber label's section 17, and most others with "Information for
Patients", the older format's subsection, also written to the prescriber. The
`patient_medication_information` texts (24) open as patient information leaflets, Medication
Guides, consumer information or section 17 text: a mixed field.

## Duplicates among patient texts

Within this part only; duplicates across manufacturers mostly span parts, so S2 measures them on all 14.

| text | labels | distinct (exact) | distinct (case and punctuation ignored) | distinct (closing lines ignored) | texts on 2+ labels | of those, from 2+ makers | largest group | distinct generic-name sets | labels with no generic name |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| instructions_for_use | 133 | 128 | 127 | 127 | 1 | 0 | 6 | 86 | 30 |
| medication_guide | 520 | 498 | 497 | 478 | 21 | 5 | 3 | 197 | 95 |
| patient_medication_information | 24 | 23 | 23 | 23 | 1 | 0 | 2 | 14 | 8 |
| patient_package_insert | 271 | 266 | 265 | 260 | 3 | 3 | 4 | 137 | 49 |

"Closing lines" are the maker, distributor, approval and revision lines when they begin in the last third of the text. Generic names come from the `openfda` block, so labels without it have none.

## Length and reading level, in the 787 labels with a Medication Guide or a patient package insert

Words, Flesch-Kincaid grade (FK) and SMOG grade per text: median, with the 25th and 75th percentiles.

| side | section | texts | words | FK grade | SMOG grade |
|---|---|---:|---:|---:|---:|
| patient | medication_guide | 520 | 1,628 (1,144 to 2,049) | 11.68 (10.76 to 12.43) | 13.39 (12.88 to 14.24) |
| patient | patient_package_insert | 271 | 1,314 (989 to 1,567) | 10.54 (9.61 to 11.38) | 12.86 (12.16 to 13.6) |
| patient | instructions_for_use | 75 | 795 (551 to 1,806) | 8.28 (7.61 to 10.15) | 10.86 (10.2 to 12.12) |
| patient | patient_medication_information | 5 | 645 (543 to 1,636) | 12.56 (12.14 to 15.83) | 14.32 (14.32 to 16.3) |
| prescriber | adverse_reactions | 783 | 1,025 (588 to 1,607) | 20.59 (18.52 to 23.77) | 20.56 (18.64 to 22.98) |
| prescriber | boxed_warning | 442 | 237 (127 to 370) | 15.93 (14.52 to 18.26) | 16.95 (15.9 to 19.06) |
| prescriber | contraindications | 782 | 63 (38 to 114) | 18.58 (16.35 to 21.48) | 17.16 (15.25 to 19.43) |
| prescriber | description | 783 | 160 (132 to 208) | 15.97 (14.53 to 17.46) | 16.93 (15.9 to 18.27) |
| prescriber | dosage_and_administration | 785 | 684 (373 to 1,101) | 15.31 (13.43 to 17.18) | 16.26 (14.71 to 17.87) |
| prescriber | drug_interactions | 712 | 468 (209 to 825) | 18.5 (17.19 to 20.06) | 18.88 (17.74 to 20.08) |
| prescriber | how_supplied_storage | 782 | 114 (79 to 174) | 11.42 (9.56 to 14.49) | 12.49 (11.21 to 14.55) |
| prescriber | indications_and_usage | 787 | 129 (75 to 230) | 19.29 (16.81 to 24.01) | 19.45 (17.63 to 22.92) |
| prescriber | patient_counseling_information | 728 | 466 (285 to 668) | 16.12 (14.55 to 17.51) | 16.91 (15.62 to 17.96) |
| prescriber | use_in_specific_populations | 649 | 1,192 (828 to 1,536) | 17.04 (16.13 to 17.52) | 17.86 (17.2 to 18.32) |
| prescriber | warnings_and_precautions | 779 | 1,755 (970 to 2,736) | 17.24 (16.22 to 18.14) | 17.92 (16.94 to 18.64) |

The share of patient texts above an 8th-grade level that this sample first gave is withdrawn:
the grades it rested on are inflated where lists lost their marks (see below and
`docs/xml-test.md`), so no share above a grade is stated until the structure question is
settled.

**Read these grades with care.** The source text has lost its line breaks, so a bulleted list
without full stops is read as one long sentence, which raises both grades; Medication Guides are
full of such lists. The grades are useful to compare texts measured the same way (patient texts
are about five grades below the prescriber sections they come from), not as the grade a reader
would meet on the printed page. S2 tests sentence splitting on list items (or the SPL XML, which
keeps the list structure) before any grade is released.

## Headings inside Medication Guides

Standard headings found by their wording in 520 Medication Guides, with the medicine's name taken out (the most common wording of each). The patient package insert column applies the same headings to the 271 inserts, many of which follow the same plan.

| heading (most common wording) | Medication Guides | share | patient package inserts | share |
|---|---:|---:|---:|---:|
| What should I avoid while [medicine]? | 271 | 52.1% | 86 | 31.7% |
| Before taking [medicine], tell your healthcare provider | 458 | 88.1% | 202 | 74.5% |
| General information about the safe and effective use of [medicine]. | 379 | 72.9% | 155 | 57.2% |
| How should I take [medicine]? | 376 | 72.3% | 218 | 80.4% |
| What are the ingredients in [medicine]? | 388 | 74.6% | 210 | 77.5% |
| What is the most important information I should know about [medicine]? | 441 | 84.8% | 83 | 30.6% |
| What are the possible side effects of [medicine]? | 409 | 78.7% | 210 | 77.5% |
| How should I store [medicine]? | 373 | 71.7% | 180 | 66.4% |
| What are [medicine]? | 442 | 85.0% | 231 | 85.2% |
| Who should not take [medicine]? | 262 | 50.4% | 128 | 47.2% |

Standard headings per guide: 0: 13, 1: 52, 2: 8, 4: 1, 5: 13, 6: 51, 7: 29, 8: 115, 9: 147, 10: 91. Of the 65 guides with none or one, 56 are full length (3,000 characters or more) and 59 contain no question mark at all. A later count in the same part found that heading phrases written without a question mark are rare (at most 2% for any heading key; for example 11 of 1,053 "most important information"), so these guides do not use the standard headings at all; they are short class-wide texts or follow another plan. The patterns are not widened.

## Which prescriber section each heading draws on (a first proposal)

For each heading segment of a Medication Guide, the prescriber section of the same label whose words it shares most (TF-IDF cosine, leaving out words found in most of the label's sections, such as its own names). Shares of segments; the median similarity of the best match.

| heading | segments | most similar section (share) | second | third | median similarity |
|---|---:|---|---|---|---:|
| avoid | 271 | patient_counseling_information (73%) | warnings_and_precautions (14%) | contraindications (4%) | 0.09 |
| before | 518 | patient_counseling_information (46%) | warnings_and_precautions (35%) | drug_interactions (8%) | 0.17 |
| general | 379 | patient_counseling_information (76%) | how_supplied_storage (8%) | warnings_and_precautions (7%) | 0.06 |
| how_to_take | 379 | dosage_and_administration (55%) | patient_counseling_information (23%) | how_supplied_storage (7%) | 0.13 |
| ingredients | 389 | description (87%) | patient_counseling_information (9%) | how_supplied_storage (2%) | 0.43 |
| most_important | 442 | boxed_warning (38%) | patient_counseling_information (29%) | warnings_and_precautions (28%) | 0.23 |
| side_effects | 410 | patient_counseling_information (39%) | warnings_and_precautions (30%) | adverse_reactions (28%) | 0.19 |
| storage | 374 | how_supplied_storage (83%) | patient_counseling_information (7%) | boxed_warning (2%) | 0.14 |
| what_is | 495 | indications_and_usage (74%) | contraindications (8%) | warnings_and_precautions (5%) | 0.31 |
| who_should_not | 262 | contraindications (69%) | warnings_and_precautions (9%) | patient_counseling_information (9%) | 0.21 |

Read with the regulation in mind, the proposal is: "What is" with indications and usage, "Who
should not" with contraindications, "How should I take" with dosage and administration,
storage with how supplied, ingredients with the description, and "most important information"
with the boxed warning and warnings and precautions. Section 17 (patient counseling) is the
closest match for "avoid", "general information" and part of "side effects", which fits its
role as the prescriber's summary of what to tell patients. `docs/method.md` turns this into the
alignment rule and its check.

## Copyright marks

Labels whose text has the copyright sign, the word "copyright" or "all rights reserved", among the 787 labels with a Medication Guide or a patient package insert: 89 (11.3%), found in 38 Medication Guides, 35 patient package inserts, 26 instructions for use, 43 patient counseling sections and 5 how-supplied sections. Over all 4,748 labels: 83 in a patient text and 94 in a prescriber section.

## Older versions

The source holds one version per label (above). Older versions can come from DailyMed's labeling archives and its `/spls/{SETID}/history` service (version lists per set id), from its monthly and weekly update files kept from now on, and, for the future, from this corpus's own weekly snapshots. S1 fetched none of them.
