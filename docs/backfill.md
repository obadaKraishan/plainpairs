# Backfill estimate

For S2, which reads every label once. Sizes from `download.json` (export of 2026-11-13; sizes
are listed in MiB); speeds from the one part downloaded on 2026-11-15.

## The bulk parts
| part | file | size (MiB) | labels |
|---|---|---:|---:|
| 1 | drug-label-0001-of-0014.json.zip | 130.34 | 20,000 |
| 2 | drug-label-0002-of-0014.json.zip | 143.79 | 20,000 |
| 3 | drug-label-0003-of-0014.json.zip | 136.09 | 20,000 |
| 4 | drug-label-0004-of-0014.json.zip | 137.35 | 20,000 |
| 5 | drug-label-0005-of-0014.json.zip | 125.15 | 20,000 |
| 6 | drug-label-0006-of-0014.json.zip | 137.24 | 20,000 |
| 7 | drug-label-0007-of-0014.json.zip | 140.52 | 20,000 |
| 8 | drug-label-0008-of-0014.json.zip | 137.61 | 20,000 |
| 9 | drug-label-0009-of-0014.json.zip | 126.10 | 20,000 |
| 10 | drug-label-0010-of-0014.json.zip | 133.36 | 20,000 |
| 11 | drug-label-0011-of-0014.json.zip | 140.39 | 20,000 |
| 12 | drug-label-0012-of-0014.json.zip | 135.88 | 20,000 |
| 13 | drug-label-0013-of-0014.json.zip | 126.23 | 20,000 |
| 14 | drug-label-0014-of-0014.json.zip | 37.48 | 4,748 (downloaded in S1) |
| **all** | | **1,787.53 (about 1.87 GB)** | **264,748** |

## Disk, time and requests
| item | estimate | basis |
|---|---|---|
| Download | 13 more parts, 1,750 MiB (about 1.84 GB); with part 14 already on the drive | `download.json` |
| Requests | 14 (`download.json` and 13 parts), one at a time | the parts |
| Download time | about 40 minutes at the 0.8 MB/s part 14 got (39.3 MB in 49 s); less on a faster link | usage log |
| Raw disk | 1.87 GB on the external drive (plenty free: 1.6 TB) | |
| Unpacked | about 9.4 GB if unpacked (part 14 unpacks 5.0 times), but **nothing is unpacked**: the reader streams each archive | part 14 |
| Parse time | about 5 minutes for all 264,748 labels (5.6 s per 4,748) | part 14 |
| Profile time | about 15 to 20 minutes with all measures, on the labels in scope only | part 14 (22 s for 4,748 labels, 787 in scope) |
| Labels in scope | 35,840 with a Medication Guide or a patient package insert, nearly all in a prescription format | API counts |
| Working tables | about 62 KB of text per label in scope (sample), so about 2.2 GB of text, 2.6 GB as JSON lines in `data/interim/`; Parquet with compression perhaps 0.4 to 0.6 GB | part 14; an upper estimate, since this part holds newer, longer labels |

## Recommended route for S2
1. **The maintainer approves the download** (about 1.84 GB, over the 1 GB line), or not.
2. Fetch `download.json` again and the 13 parts with `plainpairs download-part --part N`, one
   after another, each written once to the drive and checked by SHA-256. If the export date has
   moved on since part 14 was fetched, fetch part 14 again too, so all 14 come from one export.
3. Parse and profile all parts from the drive on this laptop: it is CPU work on 1.87 GB, under
   half an hour, with no model calls, so neither Kaggle nor the Batch API is needed.
4. Keep the parsed rows in `data/interim/` (gitignored) and only aggregates in reports.

Not recommended for S2: DailyMed's SPL XML (human prescription labels alone are 6 parts, about
16.8 GB). It keeps the list and heading structure that the JSON flattens, which would help the
readability measures, so S2 tests it on a handful of labels first and decides from that.
