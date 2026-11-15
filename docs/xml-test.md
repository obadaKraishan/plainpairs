# DailyMed XML against the JSON: a test on 20 labels (2026-11-15)

**Question:** what does DailyMed's label XML (Structured Product Labeling) keep that the
openFDA JSON loses, how do the grades differ, and what would moving to XML cost?

**Method.** 20 labels drawn with seed 20261115 from the in-scope labels of the 2026-11-13
export: 5 each of newer-format labels with a Medication Guide, older-format labels with a guide,
newer-format labels with a patient package insert (no guide) and older-format labels with an
insert. One request each to DailyMed's single-label web service
(`/dailymed/services/v2/spls/{SETID}.xml`), after one request for robots.txt (DailyMed has none:
the path returns its HTML home page). 21 requests in all. Each XML section was read by its LOINC
code (FDA's list of SPL section headings) into blocks (titles, paragraphs, list items; tables
counted apart) and measured with a sentence break at the end of every block, against the same
section's JSON text measured by both sentence rules. Aggregates only; no text is kept here.

## Results
- **Coverage:** 13 of the 20 set ids were on DailyMed, each with the same version as the JSON.
  7 answered 404: 2 newer-format guides, 1 older-format guide, 1 newer-format insert and 3
  older-format inserts. **All 7 lack the openFDA `openfda`
  block**, while 9 of the 13 found have it. Their effective dates run from 2011 to 2026. The
  likeliest reading is that labels without the block are mostly for products no longer listed,
  which DailyMed no longer serves as current labels; 20 labels cannot show how often.
- **Same words:** the JSON and the XML hold the same text (median ratio of word counts 1.04 for
  patient texts, 1.00 for prescriber sections, over 139 sections).
- **Lists:** the XML marks 261 list items in the 11 patient texts compared and 342 in the
  prescriber sections; the JSON of the same sections keeps 10 and 9 list marks. Most lists, then,
  are lost in the JSON without a trace; the `s2` rule can only split the lists whose marks were
  typed into the text.
- **Headings:** in the prescriber sections the XML keeps 323 titles and 198 subsections. In the
  patient texts it has only 6 titles: the standard questions of a Medication Guide are styled
  paragraphs, not titles, so they are found by their wording in either format (the JSON gave 46
  standard headings in the same texts).
- **Grades:** with a break at every block, the XML reads lower.

  | | Flesch-Kincaid, JSON `s1` | JSON `s2` | XML blocks | SMOG, JSON `s2` | XML blocks |
  |---|---:|---:|---:|---:|---:|
  | patient texts (11) | 11.99 | 11.91 | 9.38 | 13.05 | 11.09 |
  | prescriber sections (127) | 16.21 | 15.81 | 14.12 | 16.46 | 14.68 |

  The median difference per section between JSON `s2` and XML is 1.71 grades for patient texts
  and 1.31 for prescriber sections.

## What moving to XML would cost
- **Download:** the full release of human prescription labels is 6 parts, 55,148 files, about
  16.8 GB (with images), then about 680 MB a week (the weekly update of 2026-11-02 to 06 held
  1,590 labels). The JSON is 1.87 GB a week for every label. The single-label service would need
  one request per label (35,177), which is not a reasonable load for a weekly run.
- **Coverage:** labels DailyMed no longer serves would have no XML (7 of 20 here).
- **Work:** the SPL reader exists (`plainpairs.dailymed`); joining by set id and version, keeping
  list items as sentences, and carrying the XML's subsections into the alignment would take
  about one session.

## Recommendation
**JSON with XML for structure.** Keep the JSON as the source of record: it covers every label,
holds the same words, carries the identifiers, and is what the weekly run reads. Add the XML
later, where it exists, only for structure (list items and subsection titles), joined by set id
and version, to give a second set of grades and finer alignment. That needs the maintainer's
approval of the 16.8 GB download, and is best done after the hand sheet shows whether the
alignment needs subsections. XML alone is not recommended: it would lose the labels DailyMed no
longer has, and it does not make the patient texts' headings any easier to find.
