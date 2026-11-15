# Codebook (DRAFT)

The codes built so far, with their rules and limits, are in `docs/codebook.md` (version 0).
This file stays as the wider plan.

**DRAFT for the maintainer's review. No text is coded in this session.** Each measure has a
definition in this project's own words, its source, the level it applies to (whole text,
segment, aligned pair) and a first view of how it could be computed:

- **rule**: a stated, deterministic rule over the text (a formula, a pattern, a word list);
- **rule + check**: a rule whose output needs a hand check on a sample before release;
- **judgment**: needs a trained coder (or, later and only after a reliability check against hand
  codes, a model).

PEMAT and Clear Communication Index items are **described, not reprinted**: AHRQ's terms for
PEMAT could not be read (`docs/sources.md`, section 6), and CDC's terms allow reprinting its
materials only without changes to their substance, with credit, a non-endorsement disclaimer and
a note that they are free on CDC's site. Each PEMAT or CCI-based code below names the area it
comes from; it is an adaptation, not the instrument.

## 1. Readability formulas
| measure | definition (own words) | source | level | how |
|---|---|---|---|---|
| Flesch-Kincaid grade | US school grade from mean sentence length in words and mean syllables per word | Kincaid JP, Fishburne RP, Rogers RL, Chissom BS. *Derivation of new readability formulas for Navy enlisted personnel.* Research Branch Report 8-75, Naval Technical Training Command, 1975 | text, segment | rule (built in S1) |
| Flesch reading ease | a 0 to 100 score from the same two quantities; higher is easier | Flesch R. A new readability yardstick. *J Appl Psychol.* 1948;32(3):221-233 | text, segment | rule (built) |
| SMOG grade | grade from the number of words of three or more syllables per 30 sentences | McLaughlin GH. SMOG grading: a new readability formula. *J Reading.* 1969;12(8):639-646 | text (30 sentences or more; shorter texts flagged) | rule (built) |
| Gunning fog index | grade from sentence length and the share of words of three or more syllables | Gunning R. *The Technique of Clear Writing.* McGraw-Hill; 1952 | text | rule |
| Coleman-Liau index | grade from letters per 100 words and sentences per 100 words; needs no syllable count | Coleman M, Liau TL. A computer readability formula designed for machine scoring. *J Appl Psychol.* 1975;60(2):283-284 | text | rule |
| New Dale-Chall | grade from sentence length and the share of words not on a list of familiar words | Chall JS, Dale E. *Readability Revisited: The New Dale-Chall Readability Formula.* Brookline Books; 1995 | text | rule, but the word list's license must be checked first |

Two cautions for every formula: label text has lost its line breaks, so lists read as long
sentences (S2 fixes sentence splitting before release); and formulas measure surface features,
not understanding, which is why the judgment codes below exist.

## 2. Plain-language features
| measure | definition | source | level | how |
|---|---|---|---|---|
| Sentence length | words per sentence (mean, share over 20 words) | Federal plain language guidelines (plainlanguage.gov, 2011) | text, segment | rule |
| Long words | share of words of three or more syllables | as SMOG | text, segment | rule |
| Direct address | "you" and "your" per 100 words | plain language guidelines; PEMAT understandability (word choice and style) | text, segment | rule |
| Imperatives | share of sentences that start with a verb in the base form ("Take", "Tell", "Do not") | PEMAT actionability (actions stated) | segment | rule + check (needs a part-of-speech tagger) |
| Passive voice | share of clauses in the passive | PEMAT understandability (active voice) | text, segment | rule + check (needs a parser) |
| Medical terms | share of words not in a lay health vocabulary, and whether each is explained nearby (a gloss in parentheses or "which means") | Zeng QT, Tse T. Exploring and developing consumer health vocabularies. *J Am Med Inform Assoc.* 2006;13(1):24-29; PEMAT understandability (medical terms defined) | segment | rule + check (the vocabulary's license must be checked) |
| Headings | number of headings; share written as questions; share of the ten standard headings present | 21 CFR 208.20 (the Medication Guide format); PEMAT understandability (organization) | text | rule (built in S1) |
| Segment length | words per heading segment | PEMAT understandability (information in short sections) | segment | rule |
| Summary first | whether the "most important information" segment comes first | 21 CFR 208.20; PEMAT understandability (a summary) | text | rule |

## 3. Numbers and risk
| measure | definition | source | level | how |
|---|---|---|---|---|
| Number formats | counts of percentages, decimals, fractions, ranges and natural frequencies ("1 in 100", "3 out of 1,000") | Gigerenzer G, Gaissmaier W, Kurz-Milcke E, Schwartz LM, Woloshin S. Helping doctors and patients make sense of health statistics. *Psychol Sci Public Interest.* 2007;8(2):53-96 | segment, pair | rule |
| Relative and absolute risk | statements of relative change ("2 times", "50% higher") with and without a base rate nearby | Gigerenzer et al. 2007; Fagerlin A, Zikmund-Fisher BJ, Ubel PA. Helping patients decide: ten steps to better risk communication. *J Natl Cancer Inst.* 2011;103(19):1436-1443 | segment | rule + check |
| Verbal frequency words | "very common", "common", "uncommon", "rare", "very rare", "may", "can", "sometimes" and the like, with or without a number | Berry DC, Knapp P, Raynor DK. Provision of information about drug side-effects to patients. *Lancet.* 2002;359(9309):853-854; Knapp P, Raynor DK, Berry DC. Comparison of two methods of presenting risk information to patients about the side effects of medicines. *Qual Saf Health Care.* 2004;13(3):176-180 | segment | rule |
| Numbers kept | of the numbers in the prescriber section, the share that appear in the aligned patient segment (as written or converted) | this project; Schwartz LM, Woloshin S, Welch HG. Using a drug facts box to communicate drug benefits and harms: two randomized trials. *Ann Intern Med.* 2009;150(8):516-527 (on giving patients the numbers) | pair | rule + check |
| Calculations asked | whether the reader must calculate (a dose by weight, a schedule) | PEMAT understandability and actionability (calculations) | segment | judgment, with a rule to find candidates |
| Precision | level of precision of risk statements (exact number, rounded, category, word only) | Zikmund-Fisher BJ. The right tool is what they need, not what we have: a taxonomy of appropriate levels of precision in patient risk communication. *Med Care Res Rev.* 2013;70(1 Suppl):37S-49S | segment | rule + check |

## 4. Hedging and certainty
| measure | definition | source | level | how |
|---|---|---|---|---|
| Hedges | modal verbs and hedging words ("may", "might", "could", "possible", "possibly", "likely", "appears") per 100 words | Hyland K. Writing without conviction? Hedging in science research articles. *Appl Linguist.* 1996;17(4):433-454; Hyland K. *Hedging in Scientific Research Articles.* John Benjamins; 1998 | text, segment, pair (patient minus prescriber) | rule (a fixed word list, released with the code) |
| Boosters | certainty words ("will", "always", "never", "must", "proven") per 100 words | Hyland 1998 | text, segment | rule |
| Hedge shift | change in hedges per 100 words from the prescriber section to the aligned patient segment | this project | pair | rule |

## 5. Codes adapted from PEMAT (print) and the Clear Communication Index
Named by area; the items themselves are not reprinted. Formatting and visual items do not
apply to this text, which has lost its layout and images.

| area | what is coded (own words) | source | how |
|---|---|---|---|
| PEMAT understandability: content | the purpose is clear; no distracting information | Shoemaker SJ, Wolf MS, Brach C. Development of the Patient Education Materials Assessment Tool (PEMAT). *Patient Educ Couns.* 2014;96(3):395-403 | judgment |
| PEMAT understandability: word choice and style | common words; terms explained; active voice | Shoemaker et al. 2014 | rule + check (section 2) |
| PEMAT understandability: use of numbers | numbers clear; no calculation needed | Shoemaker et al. 2014 | rule + check (section 3) |
| PEMAT understandability: organization | short sections; informative headings; logical order; a summary | Shoemaker et al. 2014 | rule for sections and headings, judgment for order |
| PEMAT actionability | at least one action named; addressed to the reader; steps broken down; tools (a chart, a checklist); calculation help | Shoemaker et al. 2014 | rule + check for the first three, judgment for the rest |
| CCI main message and call to action | one main message, stated early; a call to action | Baur C, Prue C. The CDC Clear Communication Index is a new evidence-based tool to prepare and review health information. *Health Promot Pract.* 2014;15(5):629-637 | judgment |
| CCI language | everyday words; active voice; terms the audience knows | Baur and Prue 2014 | rule + check (section 2) |
| CCI information design | the most important information first; headings and lists | Baur and Prue 2014 | rule (headings, order) |
| CCI state of the science | what is known and not known is said | Baur and Prue 2014 | judgment |
| CCI behavioral recommendations | the recommended behavior, why, and how | Baur and Prue 2014 | judgment, with imperatives as candidates |
| CCI numbers | numbers the audience uses; no calculations asked | Baur and Prue 2014 | rule + check (section 3) |
| CCI risk | the nature of the risk; benefits and risks together; probability in numbers | Baur and Prue 2014 | rule + check for numbers, judgment for the rest |

## 6. First view: what rules can do
- **Rules alone (S2):** the six formulas (once sentence splitting handles lists), sentence and
  word lengths, direct address, headings and summary position, number formats, verbal frequency
  words, hedges and boosters, numbers kept per pair. About half of the codes above.
- **Rules plus a hand check (S2 and S3):** imperatives, passive voice, medical terms explained,
  relative versus absolute risk, precision, numbers kept after conversion.
- **Judgment (S3 hand sheet, about two hours):** purpose and main message, logical order, state
  of the science, behavioral recommendations, calculations asked, tools. These are the codes the
  field scores by hand today; a model-assisted version would come only after a reliability
  check against the hand codes, with an Apache-2.0 or MIT model.
