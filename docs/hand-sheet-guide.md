# Hand sheet guide: does the prescriber section cover the same topic?

One page, for the person filling in the topic-check sheet.

## What each row shows
- **Patient text:** one segment of a Medication Guide or patient package insert, starting with
  its heading (for example "How should I take [the medicine]?").
- **Prescriber section:** the name of one section of the same label's prescribing information,
  and its first 300 words.
- **Same topic?** Your answer, from the list: **yes**, **partly** or **no**.
- **Note:** optional, for anything you want to remember (a few words are enough).

## The one question
> Does this prescriber section cover the same topic as this patient segment?

- **yes:** the section is about what the segment is about (the same subject: what the medicine
  is for, who should not take it, how to take it, how to store it, what is in it, its warnings,
  its side effects).
- **partly:** the section covers part of the segment's topic, or the topic sits in one part of a
  long section (look at the first 300 words shown, and answer from them).
- **no:** the section is about something else.

## What not to judge
- **Never judge the medicine.** Not whether the text is medically right, complete, up to date
  or safe, and not whether the patient text is a good rewrite. Only whether the two are about
  the same topic.
- Not the wording, the reading level or the length.
- Not whether a better section exists elsewhere in the label. Answer for the section shown.

## How to work
- About 100 rows; plan on one to two hours, in one or two sittings.
- Answer in the order shown. The order is random, and nothing on the sheet says how the rows
  were chosen or what any program thought of them; please keep it that way (do not look the
  labels up while answering).
- If a cell is cut ("[... first 300 of N words]"), judge from what is shown.
- If you cannot tell, choose **partly** and write a note.
- Save the file under its own name when you are done (Excel, Google Sheets or Numbers all
  work), and send it back with its key file unchanged.

## What happens with the answers
`plainpairs sheet-check` reads the filled sheet with its key and reports, per heading, the
share of rows answered yes or partly, with a 95% interval. A heading whose rule reaches 80% is
released with the rule; below that, its pairs are released with their similarity scores only,
and flagged.
