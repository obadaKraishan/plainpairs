# What the label API counts (2026-11-15)

Counts from the openFDA drug label API, asked without an API key on 2026-11-15 (68 calls; the
data were last updated on 2026-11-13). Each line gives the search used. The raw answers are kept
outside the repository; `plainpairs counts` asks the same questions again.

Field names: MG = `spl_medguide` (Medication Guide), PPI = `spl_patient_package_insert`
(patient package insert), IFU = `instructions_for_use`, IFP = `information_for_patients`,
PMI = `patient_medication_information`.

## Totals

| labels | count | share of all |
|---|---:|---:|
| all labels | 264,748 | 100.0% |
| with MG | 23,224 | 8.8% |
| with PPI | 12,837 | 4.8% |
| with MG or PPI | 35,840 | 13.5% |
| with MG and PPI | 221 | 0.1% |
| with IFU | 6,503 | 2.5% |
| with IFP | 67,916 | 25.7% |
| with PMI | 1,380 | 0.5% |
| with a boxed warning | 33,421 | 12.6% |
| with a boxed warning, among MG or PPI | 20,684 | 7.8% |
| MG or PPI, in the newer format (`warnings_and_cautions`) | 25,522 | 9.6% |
| MG or PPI, in the older format (`warnings`) | 10,024 | 3.8% |
| without the harmonized `openfda` block (no product type) | 177,516 | 67.1% |
| IFP containing the phrase "patient counseling information" | 39,223 | 14.8% |
| no MG field, but "medication guide" in `spl_unclassified_section` | 775 | 0.3% |
| no MG field, but "medication guide" in IFP | 1,147 | 0.4% |

These match a first count taken earlier the same day: 264,748 labels, 23,224 with MG, 12,837 with PPI, 35,840 with either, 67,916 with IFP and 1,380 with PMI.

## The five patient fields, alone and together

Each label counted once, by exactly which of the five fields it has (labels with none: 188,148).

| fields present (and no other of the five) | labels |
|---|---:|
| IFP | 35,277 |
| MG+IFP | 19,326 |
| PPI+IFP | 10,054 |
| IFU | 3,878 |
| MG | 2,675 |
| PPI | 1,323 |
| PPI+IFU+IFP | 1,101 |
| MG+IFU+IFP | 868 |
| IFP+PMI | 541 |
| PMI | 524 |
| IFU+IFP | 423 |
| MG+PPI+IFP | 156 |
| IFU+PMI | 81 |
| MG+PMI | 72 |
| PPI+IFP+PMI | 71 |
| MG+PPI | 43 |
| PPI+IFU | 41 |
| IFU+IFP+PMI | 36 |
| MG+IFU | 33 |
| MG+IFP+PMI | 25 |
| MG+PPI+IFU+IFP | 22 |
| PPI+IFU+IFP+PMI | 15 |
| PPI+PMI | 10 |
| MG+IFU+PMI | 3 |
| MG+IFU+IFP+PMI | 1 |
| PPI+IFU+PMI | 1 |

Not shown: the seven combinations with no label.

## Product type

Product type comes from the harmonized `openfda` block, which 177,516 labels (67.1%) lack. Counts below are among labels that have it.

| among | labels with a product type | HUMAN PRESCRIPTION DRUG | HUMAN OTC DRUG | PLASMA DERIVATIVE | CELLULAR THERAPY |
|---|---:|---:|---:|---:|---:|
| all | 87,232 | 37,430 | 49,694 | 90 | 18 |
| MG | 9,616 | 9,587 | 20 | 0 | 9 |
| PPI | 5,731 | 5,612 | 80 | 34 | 5 |
| MG|PPI | 15,296 | 15,148 | 100 | 34 | 14 |
| IFU | 3,047 | 1,647 | 1,380 | 20 | 0 |
| IFP | 27,973 | 27,717 | 153 | 85 | 18 |
| PMI | 519 | 506 | 13 | 0 | 0 |

## Distinct values among labels with a patient field

From `count=<field>`, which returns at most 1,000 values; "1,000 or more" means the limit was reached. These fields also come from the `openfda` block, so they cover only the harmonized labels (the third column). Exact counts need the bulk files (S2).

| among | field | distinct values | labels with the field |
|---|---|---:|---:|
| MG | generic name | 878 | 9,642 |
| PPI | generic name | 967 | 5,754 |
| MG|PPI | generic name | 1,000 or more | 14,592 |
| IFU | generic name | 1,000 or more | 2,670 |
| PMI | generic name | 180 | 522 |
| MG|PPI | brand name | 1,000 or more | 12,765 |
| MG|PPI | application number | 1,000 or more | 9,525 |
| MG|PPI | manufacturer | 1,000 or more | 15,133 |
| PMI | manufacturer | 164 | 519 |
| MG|PPI | route | 35 | 15,170 |

`set_id` cannot be counted this way (the API returns no values for it); distinct set ids come from the bulk files.

## Labels by the year of their effective date

From `count=effective_time` (daily counts, complete: they add up to the totals). A few dates lie in the future (2027, 2029), as the source has them.

| year | all labels | MG or PPI | PMI |
|---|---:|---:|---:|
| before 2009 | 568 | 95 | 2 |
| 2009 | 1,349 | 144 | 1 |
| 2010 | 4,555 | 475 | 0 |
| 2011 | 4,754 | 499 | 0 |
| 2012 | 5,561 | 623 | 9 |
| 2013 | 5,156 | 499 | 8 |
| 2014 | 4,671 | 460 | 14 |
| 2015 | 5,487 | 502 | 34 |
| 2016 | 7,959 | 1,113 | 71 |
| 2017 | 12,374 | 1,674 | 104 |
| 2018 | 14,027 | 2,422 | 94 |
| 2019 | 12,252 | 1,829 | 91 |
| 2020 | 22,707 | 1,567 | 97 |
| 2021 | 15,605 | 1,665 | 56 |
| 2022 | 16,089 | 1,901 | 71 |
| 2023 | 20,340 | 2,761 | 107 |
| 2024 | 36,459 | 4,854 | 184 |
| 2025 | 36,657 | 5,128 | 200 |
| 2026 | 38,176 | 7,629 | 237 |
| after 2026 | 2 | 0 | 0 |
