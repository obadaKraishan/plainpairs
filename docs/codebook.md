# Codebook, version 1 (DRAFT)

**DRAFT for the maintainer's review.** These are rule-based codes of wording. Each one is a
fixed rule over one cleaned text (a Medication Guide, a patient package insert, instructions for
use, or one section of the prescribing information), written to the record layer as counts
(`plainpairs codes`; code version `1`). The rules live in `src/plainpairs/codes.py`, with tests
on invented sentences in `tests/test_codes.py`. Version 1 fixes the rules where the development
check below showed a clear cause, and gives every code a status.

**What these codes are, and are not.**

- They describe **wording only**. None of them judges whether a statement is right, complete,
  current or safe, and none says anything about a medicine.
- They are **PEMAT-informed text items**, not PEMAT scores. The Patient Education Materials
  Assessment Tool for printable materials (PEMAT-P) rates understandability (items 1 to 19)
  and actionability (items 20 to 26) by hand, and several of its items rate layout and visual
  aids (items 12 and 15 to 19, and item 26), which this corpus cannot see. Where a code below
  relates to a PEMAT-P item, the item is named by its number and topic only, described in this
  project's words, and nothing from the instrument is reprinted. Source: Shoemaker SJ, Wolf MS,
  Brach C. *The Patient Education Materials Assessment Tool (PEMAT) and User's Guide.*
  Rockville, MD: Agency for Healthcare Research and Quality; November 2013 (updated August
  2014). AHRQ Publication No. 14-0002-EF.
- A rule's count is evidence about a text, not a grade of it. Shares are reported over
  distinct patient texts (each shared text once) and over labels for prescriber sections.

**Sentences** are cut by the corpus's sentence rule `s2` (`docs/method.md`) for every label.
Where the source lost a list's marks, a list reads as one long sentence; every sentence-level
code below inherits that. For `current` labels the length codes are also read from the
structure of DailyMed's XML (`structured_*` columns), where every list item, paragraph and cell
ends a sentence and headings are not sentences.

## Status: trusted or experimental
**This is a development check, not a validation.** The maintainer's project carried it out on
its own: one reader, no second coder, no agreement statistic, judging each item against the
code's own definition (not against PEMAT). It tells where a rule fails often enough to be
withheld; it does not show that a trusted code measures what PEMAT-P means by its item.

- **How the items were drawn.** With fixed seeds, from distinct guides and inserts (one per
  text) and from prescriber sections, half each. For the five codes doubted in version 0
  (explained terms, long sentences and sections, vague words, whom to call with a "when", risk
  statements with a number): 20 hits and 20 misses each. For the other codes: 10 and 10.
- **What counts as right.** A hit is right when the unit is what the code says it is (a real
  sentence over 40 words; a number that gives a risk's size). A miss is right when the code
  was right to leave it out (for the length codes: the unit is not part of a longer sentence).
- **The rule.** A code is **trusted** when at least 90% of its hits and at least 90% of its
  misses are right on the check, after any fix; otherwise **experimental**. Only trusted codes
  are candidates for a release: they are the columns of `codes.parquet`. Experimental codes
  are kept in `codes_experimental.parquet`, which no release carries, and `release-check`
  fails if one appears in a release table.
- **After a fix.** Where the fix changed which units are hits (risk statements, explained
  terms), a fresh draw was read; where it only removed known false hits (vague words, whom to
  call, "1 in N"), the first draw was judged again under the new rule.

| code | columns | status | hits right | misses right | why |
|---|---|---|---:|---:|---|
| Direct address | `you_words`, `sentences_with_you` | trusted | 10/10 | 10/10 | the words are what they are; one hit spoke to the prescriber, a stated limit |
| Instructions as commands | `command_sentences`, `conditional_commands` | trusted | 10/10 | 10/10 | |
| Distinct actions | `distinct_actions` | trusted | (the command check) | | counts the verbs the command code finds |
| Percentages | `percentages` | trusted | 10/10 | 10/10 | four hits were product strengths, a stated limit |
| "1 in N" | `one_in_n` | trusted | 9/10, then 9/9 | 10/10 | version 1 leaves out packaging counts ("30 in 1") |
| Frequencies | `frequencies` | trusted | 9/10 | 10/10 | the miss: "daily" in a dose multiple |
| Doses | `doses` | trusted | 10/10 | 10/10 | strengths in product names count, a stated limit |
| Whom to call | `contact_sentences` | trusted | 36/40, then 36/36 | | version 1: "inform patients", "tell you" and the like are not the reader contacting anyone |
| ... with a "when" | `contact_sentences_with_when` | experimental | 20/20 | 18/20, then 14/16 | a condition given as an object ("report such symptoms to ...") is not seen |
| Risk statements with a number | `risk_sentences`, `risk_sentences_with_number` | experimental | 2/20; version 1, fresh draw: 14/20 | 20/20; 20/20 | version 1 counts only numbers that give a risk's size and leaves out cross-references and doses; still caught: product strengths, dose multiples, shares of patients that are not risks |
| Vague frequency words | `vague_core`, `vague_extended` | experimental | 15/20, then 15/18 | 20/20 | version 1 leaves out the month "May" and "may report"; "can" and "may" of ability or permission remain |
| Term with its explanation | `explained_in_brackets`, `explained_called`, `abbreviations_in_brackets` | experimental | 9/20; version 1, fresh draw: 12/20 (patient texts 10/10, prescriber sections 2/10) | 12/20; 18/20 | version 1 leaves out "BRAND (generic)", pronunciations and asides, and counts a one-word term after its plain description ("trouble sleeping (insomnia)"). In prescriber sections most brackets are qualifiers or lists of terms |
| Long sentences (JSON) | `sentences_over_20`, `sentences_over_40`, `longest_sentence_words` | experimental | 8/20 (patient texts 0/10) | 20/20 | in patient texts every hit was list items, headings or typed marks run together |
| Long sections (JSON, patient texts) | `sections`, `longest_section_words`, `sections_over_250` | experimental | 8/20 (4 unclear) | 20/20 | sections over 250 words often hold subheadings that are not standard headings |
| Long sentences (structure, `current`) | `structured_sentences`, `structured_sentences_over_20`, `structured_sentences_over_40`, `structured_longest_sentence_words` | trusted | 19/20 | 20/20 (none part of a longer sentence) | one hit was a semicolon list; 5 of the 20 short units were labels or address lines, which lower the shares a little |
| Long parts (structure, `current`) | `structured_parts`, `structured_longest_part_words`, `structured_parts_over_250` | experimental | 16/20 (2 unclear) | 19/20 | headings set without bold are not seen; one bold lead-in was read as a heading |

`words` and `sentences` (rule `s2`) are counts the shares are taken over, not codes.

## The rules

| code | columns in `codes` | rule (in short) | relates to | what it cannot see |
|---|---|---|---|---|
| Direct address | `you_words`, `sentences_with_you` | the words "you", "your", "yours", "yourself", "yourselves" | PEMAT-P item 21 (actionability: speaking to the reader directly when describing actions) | whether the reader addressed is the patient, a caregiver or a prescriber; "you" in a quoted heading counts too |
| Instructions as commands | `command_sentences`, `conditional_commands` | a sentence that opens with a base-form verb from a fixed list of 151 (after list marks, quote marks and "Step 1:"), or with "Do not", "Don't" or "Never" and such a verb; a verb followed by "in", "of", "with", "is" and the like is read as a noun ("Use in children") and not counted. `conditional_commands`: "If ..., call ..." (a condition, a comma, then a command) | PEMAT-P item 20 (actionability: at least one action named) | verbs outside the list; commands in the middle of a sentence ("you should take"); a sentence that opens with a verb used as a noun the list does not catch |
| Distinct actions | `distinct_actions` | the number of different verbs that open the text's commands; a ban counts apart ("take" and "not take" are two) | PEMAT-P item 22 (actionability: actions broken into explicit steps), as a rough count only | whether steps are in order, numbered or complete |
| Percentages | `percentages` | a number followed by "%" or "percent" | PEMAT-P item 6 (use of numbers: numbers clear and easy to read) | what the number is a share of |
| "1 in N" | `one_in_n` | "1 in 10", "one in ten", "3 out of every 100" and the like | PEMAT-P item 6 | other natural frequencies written in words ("most people") |
| Frequencies | `frequencies` | "twice a day", "3 times a week", "every 12 hours", "each morning", "daily", "q12h" | PEMAT-P item 6 | schedules written as tables or in words the pattern does not list |
| Doses | `doses` | a number followed by a unit: mg, mcg, g, mL, units, IU, mEq, mmol, mg/kg, mg/m2, mcg/kg | PEMAT-P item 7 (use of numbers: no calculation asked of the reader), as context only | whether the reader must calculate anything; strengths in product names count too |
| Risk statements with a number | `risk_sentences`, `risk_sentences_with_number` | a sentence with a risk word ("risk", "chance", "side effect", "adverse reaction", "reaction", "may cause", "can cause", "occur", "incidence", "common", "rare", "likely"); of those, the ones that hold a digit, "%" or a number word | PEMAT-P item 6; the risk-communication literature in `docs/codebook-draft.md` (section 3) | risk statements without those words ("had headache"); a number that is not the risk's size (a dose in the same sentence) |
| Vague frequency words | `vague_core`, `vague_extended` | core: "common", "commonly", "rare", "rarely", "may", "can", "some"; extended: "might", "could", "sometimes", "often", "usually", "uncommon", "frequent(ly)", "occasional(ly)", "likely", "unlikely", "possible", "possibly"; reported per 1,000 words | no PEMAT-P item directly; nearest is item 6 | the sense of each word: "can" may mean ability, "may" permission, "some" an amount; the month "May" counts |
| Term followed by its explanation | `explained_in_brackets`, `explained_called`, `abbreviations_in_brackets` | a bracket of two or more words, at least half of them in lower case, with no digit, not opening with "see", "such as", "for example", "including" and the like; or "called", "also called", "known as", "also known as" (not "call your doctor"). An abbreviation in brackets ("(ALT)") is counted apart | PEMAT-P item 4 (word choice and style: medical terms used only where needed, and explained) | whether the term needed explaining, or whether the explanation is right or plain; explanations after "which means", a dash or a comma; brand names in brackets written in lower case |
| Long sentences | `sentences_over_20`, `sentences_over_40`, `longest_sentence_words` | sentences of more than 20 and more than 40 words (by `s2`), and the longest | PEMAT-P item 3 (word choice and style: common, everyday language), loosely; federal plain-language guidance on sentence length | lists that lost their marks read as long sentences |
| Long sections (patient texts) | `sections`, `longest_section_words`, `sections_over_250` | words between two standard headings (the segments of `section_pairs`); sections of more than 250 words | PEMAT-P item 8 (organization: information in short sections) | **paragraphs**: the JSON keeps no line breaks. For `current` labels the structure gives parts between the XML's own headings (`structured_parts`), still experimental |
| Whom to call, and when | `contact_sentences`, `contact_sentences_with_when` | a sentence with a contact verb ("call", "contact", "tell", "talk to", "ask", "notify", "inform", "report", "go to", "get help", "seek care") and someone to contact ("doctor", "healthcare provider", "pharmacist", "nurse", "prescriber", "poison control", "911", "emergency", "hospital", "FDA"); "with when" if it also holds a condition or timing word ("if", "when", "right away", "immediately", "before", "within" and the like) | PEMAT-P item 20 (an action named); the CDC Clear Communication Index's call-to-action area | whether the condition is clear or the contact reachable; contact details given in a table |

Version 1 changes to the rules (each with a test on invented text):

- **"1 in N":** a phrase whose second number is not larger than the first ("30 in 1") is a
  packaging count and is left out.
- **Risk statements with a number:** cross-references ("[see Warnings (5.1)]", "(5.1, 6)")
  are removed before a sentence is read, so a section number no longer makes a risk sentence
  or a number; a number counts only when it gives a risk's size: a percentage, "1 in N" or
  "N of M", a rate ("per 1,000"), a count of people ("12 patients"), or a multiple ("twice as
  likely"); doses are removed first.
- **Vague words:** "may" or "can" followed by a digit (the month, "May 2024") or by "report"
  is left out.
- **Whom to call:** a contact verb followed by "patients", "caregivers", "families", "them" or
  "you" (not "your") is someone else being told, not the reader contacting anyone.
- **Brackets:** a bracket right after a trademark sign or a capitalized word names a product;
  a bracket of short syllables with an apostrophe or hyphen is a pronunciation; a bracket that
  opens with a qualifier ("sometimes", "particularly", "approximately" and the like) or a
  command verb is an aside. A one-word lower-case term in brackets after at least two words in
  lower case is a term after its plain description, and counts.

Invented examples: "Zorvan may cause a rash in about 1 in 100 people" is a risk sentence with
a number; "Zorvan may cause a rash [see Warnings (5.1)]" is a risk sentence without one;
"ZORVAN® (zorvanide)" is a product name, not an explanation; "trouble sleeping (insomnia)"
counts as an explained term.

## What version 1 does not code yet
- **Active voice** (PEMAT-P item 5): needs a parser.
- **Calculations asked of the reader** (PEMAT-P item 7): needs judgment; doses are a pointer.
- **Purpose, distracting information, logical order** (PEMAT-P items 1, 2 and 10): judgment.
- **A summary** (PEMAT-P item 11): the "most important information" heading coming first is
  a rule the build can already give from `section_pairs`; not yet reported as a code.
- **Layout, visual cues and visual aids** (PEMAT-P items 12, 15 to 19 and 26): not visible in
  this source.

## Before any of these is released
- Only trusted codes are candidates, and the maintainer decides which go out.
- The word lists are released with the code; changing a list changes the code version.
- A trusted code's limits are stated with it, with the counts above.
- An experimental code becomes a candidate only after a new check by these rules, on a fresh
  draw, finds it at 90% or more.
