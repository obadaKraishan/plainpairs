# PlainPairs

PlainPairs is a research corpus of how United States medicine labels are worded for two
readers. For every medicine whose label carries a version written for patients (a Medication
Guide or a patient package insert), it holds the text written for prescribers next to the text
written for patients, matched section by section, with reading-level and plain-language
measures on both sides.

It is built for health literacy, health communication and risk communication research that
studies how official patient information is written: how long it is, how hard it is to read,
how it words numbers and risks, and how it differs from the professional text it comes from.

**Status: in development. Nothing has been released yet.** The plan, the source terms and the
drafts are in [`docs/`](docs/).

## What it holds (planned)
- One row per label, with its identity (set id, version, effective date, product type, route,
  application number, manufacturer, names) and its prescriber sections and patient texts as
  plain text with their headings kept.
- One row per distinct patient text, since many labels from different manufacturers carry the
  same Medication Guide word for word.
- Patient sections matched to the prescriber sections they draw on, with the method and its
  checks described in [`docs/method.md`](docs/method.md).
- Reading-level and plain-language measures for every text, computed by stated rules.
- New and changed labels added every week, with versioned, citable releases.
- Apart from the labels, in its own configuration: text taken from the National Cancer
  Institute's cancer information summaries, in their health-professional and patient versions,
  in English and Spanish, paired by NCI's own links, with images, credited tables, references
  and closing sections left out and a credit line on every row.

## What it is not
- **Not medical information.** PlainPairs is a research record of how label text and cancer
  information text are worded. The labels in it may be out of date, incomplete or replaced by
  newer versions, and the cancer information text may be out of date too. Never use any of it
  to decide anything about a medicine or about care. For a medicine, read the current label
  that comes with it and talk to a doctor, pharmacist or other health care professional;
  current cancer information is on the National Cancer Institute's own site
  (<https://www.cancer.gov>).
- **Not a judgment of any medicine.** The measures describe wording only. Nothing here says what
  a medicine does, whether it is safe or whether anyone should take it.
- **Not about people.** Labels hold no information about patients, and PlainPairs adds none.
- **Not an official product.** PlainPairs is an independent research project. It is not made,
  endorsed or checked by the U.S. Food and Drug Administration, the National Library of Medicine,
  the National Cancer Institute or any company whose labels it holds.

## Source
The labels come from the drug label dataset that the U.S. Food and Drug Administration publishes
through its openFDA program. The companies that market each medicine write its label.
[`docs/sources.md`](docs/sources.md) quotes the terms of use, the disclaimer and the citation the
source asks for, and the open questions about rights in label text. The source's own
disclaimer applies to everything here: "Do not rely on openFDA to make decisions regarding
medical care. Always speak to your health provider about the risks and benefits of
FDA-regulated products."

The cancer information summaries come from the National Cancer Institute's website
(<https://www.cancer.gov>), whose text is free of copyright unless marked otherwise; every row
credits the National Cancer Institute as the source and links the original summary. NCI's
summaries "are not clinical practice guidelines or treatment recommendations".

## Documents
[`docs/`](docs/) holds the data card (`data-card.md`, a draft), the schema and the method
(`schema.md`, `method.md`), the source check (`sources.md`), the prior art (`prior-art.md`),
the counts, the sample and the XML test (`counts.md`, `sample.md`, `xml-test.md`), the hand
sheet guide, the codebook of rule-based codes (`codebook.md`, a draft), the benchmark design
(`benchmark-design.md`, a draft) and a draft of the weekly update.

## License
The software in this repository is licensed under the Apache License, Version 2.0 (see
[`LICENSE`](LICENSE) and [`NOTICE`](NOTICE)). The corpus is distributed separately, as a
Hugging Face dataset; what applies to each of its configurations (the sources' terms, the
credit lines, and the CC0 dedication of the project's own measures) is in that dataset's
`LICENSES.md`, from the first release on.

## Development
```bash
uv sync
uv run pytest --cov=plainpairs
uv run ruff check . && uv run ruff format --check .
```
