# PlainPairs

[![arXiv](https://img.shields.io/badge/arXiv-2611.21160-b31b1b.svg)](https://arxiv.org/abs/2611.21160)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24267450.svg)](https://doi.org/10.5281/zenodo.24267450)

PlainPairs is a research corpus of how United States medicine labels are worded for two
readers. For every medicine whose label carries a version written for patients (a Medication
Guide or a patient package insert), it holds the text written for prescribers next to the text
written for patients, matched section by section, with reading-level and plain-language
measures on both sides.

It is built for health literacy, health communication and risk communication research that
studies how official patient information is written: how long it is, how hard it is to read,
how it words numbers and risks, and how it differs from the professional text it comes from.

**Status: version 0.2.1, released on 2026-11-27,** the first version built and delivered by
the weekly workflow (from the openFDA export of 2026-11-27), after version 0.2.0 (tag `v0.2.0`,
the same day, from the export of 2026-11-26). The corpus is on Hugging Face,
[`obadakr/plainpairs`](https://huggingface.co/datasets/obadakr/plainpairs) (version 0.2.1 is the
dataset commit "PlainPairs 0.2.1 (#2)", since weekly versions are not tagged; its card starts
with "Start here": which file to open, a CSV and an Excel workbook for readers who do not use
Parquet, and how to load each table), with a mirror on Kaggle (version 0.2.0),
[`obadakraishan/plainpairs`](https://www.kaggle.com/datasets/obadakraishan/plainpairs). Every
Monday a workflow builds the next weekly version (0.2.1, 0.2.2, ...) from the newest export and
opens it as a draft pull request on the dataset, which the maintainer reads and merges
([`docs/automation.md`](docs/automation.md)); the Kaggle mirror is updated about monthly. The
method, the source terms and the drafts are in [`docs/`](docs/).

## What it holds
- One row per label, with its identity (set id, version, effective date, product type, route,
  application number, manufacturer, names) and its prescriber sections and patient texts as
  plain text with their headings kept.
- One row per distinct patient text, since many labels from different manufacturers carry the
  same Medication Guide word for word.
- Patient sections matched to the prescriber sections they draw on, with the method and its
  checks described in [`docs/method.md`](docs/method.md).
- Reading-level and plain-language measures for every text, computed by stated rules.
- New and changed labels added every week, with versioned, citable releases (the weekly
  update is not yet switched on).
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
(`benchmark-design.md`, a draft), a draft of the weekly update, the removal route
(`removal.md`) and the figures of each release for a data paper (`paper-facts.md`).

## How to cite
If you use PlainPairs, please cite the paper:

> Kraishan, O. (2026). PlainPairs: A Corpus Pairing the Prescriber and Patient Texts of U.S.
> Prescription Medicine Labels. arXiv:2611.21160. <https://arxiv.org/abs/2611.21160>
> (doi:10.48550/arXiv.2611.21160)

```bibtex
@misc{kraishan2026plainpairs,
  author        = {Kraishan, Obada},
  title         = {{PlainPairs}: A Corpus Pairing the Prescriber and Patient Texts of {U.S.} Prescription Medicine Labels},
  year          = {2026},
  eprint        = {2611.21160},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  doi           = {10.48550/arXiv.2611.21160},
  url           = {https://arxiv.org/abs/2611.21160}
}
```

To name the exact data you used, also give the dataset and its version:

> Kraishan, O. (2026). PlainPairs: a research corpus pairing the prescriber and patient texts of
> US medicine labels (Version 0.2.0) [Data set]. Hugging Face.
> <https://huggingface.co/datasets/obadakr/plainpairs>

That is version 0.2.0; the dataset's card gives the citation of each version. Please also give
the sources' credit lines (in the card and in `LICENSES.md`). The software and
documents are archived on Zenodo, with no data table:
<https://doi.org/10.5281/zenodo.24267450>. This DOI stands for all versions and resolves to the
latest; version 0.2.0 is <https://doi.org/10.5281/zenodo.24576965> and version 0.1.0
<https://doi.org/10.5281/zenodo.24267451>. GitHub's "Cite this
repository" reads `CITATION.cff`.

## License
The software in this repository is licensed under the Apache License, Version 2.0 (see
[`LICENSE`](LICENSE) and [`NOTICE`](NOTICE)). The corpus is distributed separately, as a
Hugging Face dataset; what applies to each of its configurations (the sources' terms, the
credit lines, and the CC0 dedication of the project's own measures) is in that dataset's
`LICENSES.md`.

## Development
```bash
uv sync
uv run pytest --cov=plainpairs
uv run ruff check . && uv run ruff format --check .
```
