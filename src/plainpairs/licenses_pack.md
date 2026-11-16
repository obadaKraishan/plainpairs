# What applies to each part of PlainPairs $version

PlainPairs is a research record of wording, not medical information. Each configuration comes
from a different source, with its own terms. Nothing here is endorsed by any source.

## The project's own additions (all configurations)
The measures, codes, flags, alignments, pairs, hashes and other fields this project computes,
and the layout of the tables, are dedicated to the public domain under the Creative Commons CC0
1.0 Universal dedication (https://creativecommons.org/publicdomain/zero/1.0/). Citing the
project is asked, not required. The software that builds them is licensed under the Apache
License 2.0 (https://www.apache.org/licenses/LICENSE-2.0) in the project's repository.

## `current` and `unlisted`: label text from openFDA
- **Source:** the openFDA drug label bulk files, export of $export (https://open.fda.gov).
- **Terms:** "Unless otherwise noted, the content, data, documentation, code, and related
  materials on openFDA is public domain and made available with a Creative Commons CC0 1.0
  Universal dedication." (https://open.fda.gov/terms/).
- **Credit:** Data provided by the U.S. Food and Drug Administration (https://open.fda.gov).
- **Disclaimer:** "Do not rely on openFDA to make decisions regarding medical care. Always speak
  to your health provider about the risks and benefits of FDA-regulated products."
- **Company text:** the companies that market each medicine write its label. Text rows are
  released only for labels that show no copyright mark (the `unmarked` setting); the record
  rows of marked labels stay, without their text. A rights holder may ask for removal
  (README, "Removal").
- **Structure** for `current` labels comes from DailyMed's release of $dailymed_release
  (National Library of Medicine): Courtesy of the National Library of Medicine.

## `nci`: $nci_name
- **Source:** the National Cancer Institute's website (https://www.cancer.gov), pages read on
  $nci_read.
- **Terms:** "Unless otherwise indicated, all text within National Cancer Institute (NCI)
  products is free of copyright and may be reused without our permission. Credit the National
  Cancer Institute as the source." (https://www.cancer.gov/policies/copyright-reuse).
- **Credit:** every row carries a credit line: the summary's title in quotation marks, then
  "was originally published by the National Cancer Institute.", and the page's address.
- **Left out:** images and figures (NCI uses them with permission for its own summaries only),
  tables that NCI credits to other publishers, references, citation marks and the closing
  sections. A row is therefore not an NCI summary and must not be presented as one; the NCI
  logo and NCI's trademarks are not used.

## Removal
A removal request on the project's repository,
https://github.com/obadaKraishan/plainpairs/issues/new/choose (opening one needs a free GitHub
account), or in the dataset's Community tab on Hugging Face,
https://huggingface.co/datasets/obadakr/plainpairs/discussions (with a free Hugging Face
account).
