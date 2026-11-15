# Codebook, version 0 (DRAFT)

**DRAFT for the maintainer's review.** These are the first rule-based codes of wording. Each
one is a fixed rule over one cleaned text (a Medication Guide, a patient package insert,
instructions for use, or one section of the prescribing information), written to the record
layer as counts in the `codes` table (`plainpairs codes`; code version `0`). The rules live in
`src/plainpairs/codes.py`, with tests on invented sentences in `tests/test_codes.py`.

**What these codes are, and are not.**

- They describe **wording only**. None of them judges whether a statement is right, complete,
  current or safe, and none says anything about a medicine.
- They are **PEMAT-informed text items**, not PEMAT scores. The Patient Education Materials
  Assessment Tool for printable materials (PEMAT-P) rates understandability (items 1 to 19)
  and actionability (items 20 to 26) by hand, and several of its items rate layout and visual
  aids (items 12 and 15 to 19, and item 26), which this corpus cannot see: the source keeps no
  layout, no images and no line breaks. Where a code below relates to a PEMAT-P item, the item
  is named by its number and topic only, described in this project's words, and nothing from
  the instrument is reprinted. Source: Shoemaker SJ, Wolf MS, Brach C. *The Patient Education
  Materials Assessment Tool (PEMAT) and User's Guide.* Rockville, MD: Agency for Healthcare
  Research and Quality; November 2013 (updated August 2014). AHRQ Publication No. 14-0002-EF.
- A rule's count is evidence about a text, not a grade of it. Shares are reported over
  distinct patient texts (each shared text once) and over labels for prescriber sections.

**Sentences** are cut by the corpus's sentence rule `s2` (`docs/method.md`): at sentence marks,
at list marks the source kept, before numbered headings and around runs of capitals. Where
the source lost a list's marks, a list reads as one long sentence; every sentence-level code
below inherits that.

## The codes

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
| Long sections (patient texts) | `sections`, `longest_section_words`, `sections_over_250` | words between two standard headings (the segments of `section_pairs`); sections of more than 250 words | PEMAT-P item 8 (organization: information in short sections) | **paragraphs**: the source keeps no line breaks, so paragraphs cannot be seen at all. This code measures sections between headings instead; a paragraph code waits for the SPL XML's structure |
| Whom to call, and when | `contact_sentences`, `contact_sentences_with_when` | a sentence with a contact verb ("call", "contact", "tell", "talk to", "ask", "notify", "inform", "report", "go to", "get help", "seek care") and someone to contact ("doctor", "healthcare provider", "pharmacist", "nurse", "prescriber", "poison control", "911", "emergency", "hospital", "FDA"); "with when" if it also holds a condition or timing word ("if", "when", "right away", "immediately", "before", "within" and the like) | PEMAT-P item 20 (an action named); the CDC Clear Communication Index's call-to-action area | whether the condition is clear or the contact reachable; contact details given in a table |

## What version 0 does not code yet
- **Active voice** (PEMAT-P item 5): needs a parser.
- **Calculations asked of the reader** (PEMAT-P item 7): needs judgment; doses are a pointer.
- **Purpose, distracting information, logical order** (PEMAT-P items 1, 2 and 10): judgment.
- **A summary** (PEMAT-P item 11): the "most important information" heading coming first is
  a rule the build can already give from `section_pairs`; not yet reported as a code.
- **Layout, visual cues and visual aids** (PEMAT-P items 12, 15 to 19 and 26): not visible in
  this source.

## Before any of these is released
- Each code is checked by hand on a sample of real texts (counts of hits and misses per code),
  and its limits are restated with the numbers.
- The word lists are released with the code; changing a list changes the code version.
