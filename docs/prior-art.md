# Prior art

Checked on 2026-11-15, in a bounded search of about an hour: dataset cards, README files,
abstracts and API metadata only (nothing was downloaded). Sizes and licenses are as the cards
state them; where a card is unclear, the row says so. "Cannot" means what a health
communication researcher cannot do with the resource as published.

**Answer first.** No public resource pairs each US label's prescriber text with its official
patient text (Medication Guide or patient package insert), aligns them by section, measures
both sides and stays current. The closest is a 2023 study that built the same pairing from one
2019 snapshot and released no data.

## Copies of the label data
| resource | holds | size | license | living or frozen | cannot |
|---|---|---|---|---|---|
| Kaggle "openFDA Drug Labeling" (ddrbcn) | the openFDA label bulk files as served, with the data dictionary | 1.74 GB, 13 files | CC0-1.0 | frozen (April 2025) | no pairing, alignment or measures; 19 months old |
| Kaggle "openFDA Human OTC Drug Labels" (cahyaasrini) | over-the-counter labels with a category column | 1,338 products | CC0-1.0 | frozen (2021) | no prescription labels, so no Medication Guides |
| Kaggle "DailyMed Label Sections & Change History" (anurmi) | label sections and changes between versions | 4.2 MB, coverage not stated | CC0-1.0 | frozen (2025) | no patient/prescriber pairing; unknown coverage |
| Kaggle "Drug Labels & Side Effects" (pratyushpuri) | synthetic records with invented names | 1,393 rows | Apache-2.0 | frozen (2025) | not official text |
| Hugging Face `tirandazdylan/drug-labels-snapshot` | one label per drug, prescriber and Drug Facts sections | 138 labels | CC0-1.0 | frozen (2026-10) | no patient fields |
| Hugging Face `Oduwo/drug_label_approved_openfda` | instruction and answer pairs generated from labels | 10k to 100k rows | Apache-2.0 | frozen (2026-05) | generated text, no patient side |
| Hugging Face `reapxdev/openfda-scraper` | rows sampled across openFDA endpoints | 21,384 rows | CC-BY-4.0 | 2026-08 | mixed endpoints, no pairing |
| Hugging Face `um-ids/dailymed-annotations` | indications text | not stated | CC-BY-4.0 | frozen (2023) | indications only |
| GitHub `tatonetti-lab/onsides` | adverse effects extracted from labels | not checked | MIT | living | prescriber side only |
| GitHub SPL and openFDA parsers (`MaastrichtU-IDS/extract-dailymed-spl`, `pharmaDB/spl_parser`, `coderxio/dailymed-api`, `arshaver/pySPL` and others) | code | none | MIT, Apache-2.0 and others | various | tools, not corpora; none pairs the two readers |
| Meyer et al. 2023, "Neural text generation in regulatory medical writing", *Frontiers in Pharmacology* (doi 10.3389/fphar.2023.1086913) | 5,357 prescription labels from the September 2019 DailyMed edition, 1,437 with a Medication Guide, aligned to its questions in three ways; ROUGE only | 1,437 pairs | article CC BY 4.0; no data or code released | frozen (2019) | no released corpus, no readability measures, no patient package inserts, not updated |

## Studies of Medication Guide and leaflet readability
| study | measures | sample | data released | cannot |
|---|---|---|---|---|
| Wolf et al. 2006, *Patient Educ Couns* | Lexile, SAM; interviews | all 40 Medication Guides then issued | no | small, old, no pairing |
| Wolf et al. 2012, *J Gen Intern Med* | SAM, Lexile; comprehension test with 449 adults | 185 Medication Guides | no | largest US sample found; hand-scored; no prescriber side |
| Candelario et al. 2017, *J Am Pharm Assoc* | completeness against core domains; Flesch, Flesch-Kincaid | 33 Medication Guides | no | compares with Wikipedia, not with the prescriber text |
| Chan et al. 2018, *Pharmacoepidemiol Drug Saf* | Lexile, Fog, Flesch-Kincaid, PEMAT-P | 27 risk-program patient materials (Medication Guides excluded) | no | no Medication Guides |
| Jones et al. 2021, *Ther Innov Regul Sci* | length, Flesch, Flesch-Kincaid, Fry, Fog | 53 Medication Guides of new molecular entities | no | small; no sections or prescriber side |
| Lau and Smith 2023; Lau et al. 2025 (dermatology) | readability, by section in 2025 | one drug class each; counts not in the abstracts | no | one class |
| Sridharan and Sivaramakrishnan 2024, *Expert Rev Clin Pharmacol* | grade level before and after model rewrites to grade 6 | recent Medication Guides and safety communications; count not in the abstract | no | proof of concept; no reference corpus |
| Moore et al. 2023, *Med Mycol* | Flesch, Flesch-Kincaid, Fog, SMOG for professional vs patient texts | 16 antifungals in four regions | no | one of few professional/patient comparisons; tiny |
| Noble et al. 2022, *Epilepsia* (UK) | four formulas, user tests | 140 leaflets | no | not US; no professional side |
| Jones et al. 2024, *Health Promot Int* | perceived ease of reading (survey) | 5,204 adults | no | perception only |
| Pires et al. 2015, *Rev Saude Publica* | review of leaflet readability studies | 22 studies | n/a | notes the small samples and the limits of formulas |

Across the US studies: 27 to 185 documents, scored once, with nothing released. None compares
the prescriber and patient texts of the same label section by section across all labels.

## Plain-language and simplification corpora
| resource | holds | size | license | living or frozen | cannot |
|---|---|---|---|---|---|
| PLABA (Attal et al. 2023, *Sci Data*) | PubMed abstracts with plain-language adaptations written for the corpus | 750 abstracts, 7,643 sentence pairs | CC0 (OSF) | frozen (2023) | simple side written for the corpus; no medicine labels |
| Med-EASi (Basu et al. 2023) | short expert and simple medical text pairs with edit annotations | 1,979 pairs per the card (the split files add up to 1,894) | card: none; code MIT | frozen (2023) | sources not named; short snippets |
| SimpleDC (Rahman et al. 2024) | digestive-cancer web pages simplified by nurses | 1,183 sentence pairs | CC BY-NC-ND 4.0 | frozen (2024) | complex side is already for patients; no derivatives |
| CELLS (Guo et al. 2024) | journal abstracts with author lay summaries | 62,886 pairs | code MIT; data rights not stated | frozen (2024) | research summaries, not medicine information |
| Cochrane plain-language summaries (Devaraj et al. 2021) | review abstracts and their plain-language summaries | about 4,459 pairs | CC-BY-4.0 (repository) | frozen (2022) | evidence summaries, not labels; paragraph level |
| eLife and PLOS lay summaries (Goldsack et al. 2022) | articles with lay summaries | about 32,000 | CC-BY-4.0 | frozen | research articles |
| MSD Manual pairs (Cao et al. 2020) | professional and consumer versions of one publisher's manual | 675 aligned test pairs, many unaligned sentences | no license file | frozen (2020) | publisher text, not official; mostly unaligned |
| CLARA-MeD (Campillos-Llanos et al. 2022), Spanish | professional and lay pairs, including 10,211 official product-characteristics/leaflet pairs from the Spanish medicines agency and NCI cancer summaries | 24,298 document pairs; 3,800 aligned sentence pairs | non-commercial (CC BY-NC; the variant differs between sources) | frozen (2022) | Spanish only; non-commercial; no US labels; no measures shipped |
| CLEAR (Grabar and Cardon 2018), French | encyclopedia, drug information and Cochrane comparable corpora | 663 aligned sentence pairs | not checked | frozen | French; mostly unaligned |

## Readability benchmarks for language models
| resource | measures | size | license | cannot |
|---|---|---|---|---|
| RephQA (Qiu et al. 2025) | Flesch-Kincaid grade and share of professional terms in answers to public-health questions | 533 question-answer pairs | paper CC BY 4.0; data release unclear | answers questions; does not rewrite official text against a reference |
| MedReadCtrl (Tran et al. 2025) | readability-controlled generation for grades 1 to 12 on 9 existing datasets | no new corpus | no license file | no labels or leaflets; no official patient reference |
| HealthBench (Arora et al. 2025) | physician-written rubrics, including a communication axis and "expertise-tailored communication" | 5,000 conversations | MIT | rubric grading of chat answers, not reading level against an official text |

## The Patient Medication Information rule
A proposed rule (88 FR 35694, 2023) would replace Medication Guides and patient package inserts
with a one-page Patient Medication Information; a final rule is planned for December 2026 and
not yet published (`docs/sources.md`, section 7). If it is finalized, its five-year rollout
would make the weekly update the only open record of the change from the old texts to the new.
The 1,380 labels with the source field `patient_medication_information` are not that format:
they use an older section code for assorted patient texts.

## Searches
"medication guide", "patient package insert" and "drug label simplification" on Kaggle, Hugging
Face, GitHub, Zenodo (through a web search limited to zenodo.org) and Harvard Dataverse found no
dataset of paired label texts. Kaggle and Hugging Face match only unrelated sets or the copies
above; GitHub shows the source's field names in API wrappers and retrieval tools only; Dataverse
returned unrelated studies. Two small Zenodo records came up and were not opened: an Irish
leaflet-readability set (14698163) and a statin label/leaflet comparison (1464311).

## Is a paired corpus still new?
Yes, for US medicines. What exists is of three kinds: raw or partial copies of the label data
(the largest, a frozen 1.7 GB Kaggle copy, holds the patient fields but leaves them unpaired and
unmeasured); simplification corpora whose plain side was written for the corpus or is a research
summary; and readability studies of 27 to 185 Medication Guides with nothing released. The
nearest neighbors are one study that paired 1,437 labels from a 2019 snapshot without releasing
data, and a Spanish corpus of official professional and leaflet texts that is frozen and
non-commercial. The text itself is public, so what would be new is the pairing kept current
every week, the section alignment, measures on both sides, and a benchmark scored against the
official patient text.
