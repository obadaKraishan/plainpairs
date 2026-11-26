# Automation sketch (nothing built)

**A sketch for the release.** A weekly run that reads the newest export, finds new and changed labels,
and delivers the next dataset version as a pull request on the Hugging Face dataset, published
only when the maintainer merges it (the pattern the CommonsWire weekly update uses).

## What the source allows and requires
- The label data are updated weekly (dataset page: "Frequency Weekly"); the export of
  2026-11-13 is dated in `download.json` (`export_date`, `meta.last_updated`).
- Any record may change in any update, so the run downloads **all** parts every week and
  never patches: "you cannot simply download 'new' files to keep your downloaded version up to
  date" (`docs/sources.md`).
- 15 requests a week (`download.json` and 14 parts, about 1.9 GB) is far inside the limits for
  requests without a key (1,000 a day); no key is needed.

## The weekly run
1. **When.** A GitHub Actions schedule a day or two after the usual export day (the next run
   time is set from the `export_date` history at release), plus a manual button.
2. **Check for a new export.** Read `download.json`; if `export_date` equals the last release's,
   stop with nothing to do.
3. **Download.** The 14 parts, one at a time, each streamed and checked against its size; the
   runner's disk (14 GB) holds the 1.9 GB zipped and nothing is unpacked.
4. **Structure from DailyMed** (for the `current` configuration). The full release (6 parts,
   18.1 GB) is read once; each week only DailyMed's update files since the last run are
   fetched. DailyMed's page lists one file per working day for the current week and one file
   per week (Monday to Friday) for the weeks before it, so the update takes the daily files of
   the current week and the weekly file of each earlier week, never both for one day
   (2026-11-26: the weekly file of 2026-11-16 to 20, 466.69 MB, and the daily files of 11-23 to
   11-25). **Coverage rule:** a weekday of the span that no listed file covers and that falls
   before the days the page lists one by one means its weekly file is no longer listed; the
   update then stops before anything is downloaded (`status = stopped`,
   `dailymed_update_files_missing`). A weekday without a file among the daily ones (a holiday,
   or the export day itself) is counted and allowed. A label changed since the last run is read from the update
   that holds its new version; an unchanged label keeps the structure of the last build. The
   zip file metadata (7.65 MB) is read again for the "served" flag. About 0.7 GB a week, read
   in place like the full release. The full release does not fit a standard runner's disk
   (14 GB), so the weekly run starts from the last build's structure table and reads only
   update files; whether the full release must be read again from time to time (DailyMed
   replaces it on its own schedule) is checked against the update files' counts before the run
   is automated.
5. **Parse and build** the three tables (`docs/schema.md`) for labels in scope, with the two
   small listing files read the same day (`plainpairs listed-download`, then
   `plainpairs build --listed --structure`), then the codes (`plainpairs codes --structure`).
6. **Compare with the last release, by set id**, using only the record layer (every text has
   its SHA-256 there, so no text is needed to tell what changed):
   - **new label:** a set id not in the last release;
   - **new version, same texts:** a higher `version` with every section hash unchanged (the
     source often re-issues a label for packaging or listing changes);
   - **changed text:** any prescriber section or patient text whose hash changed, recorded per
     section, so a researcher can ask which sections changed and how often;
   - **patient text added or dropped:** a guide or insert that appears or disappears (a label
     can enter or leave the scope this way);
   - **identity changed:** the `openfda` block appearing or disappearing, a format change, a
     copyright mark appearing or disappearing (which moves text in or out under the switch);
   - **left the scope or withdrawn:** a set id no longer in the corpus, told apart by the
     export's full list of set ids (`export_ids.parquet`): still in the export but out of
     scope, or gone from the source; kept in the release with its last export date, flagged,
     unless the maintainer decides otherwise;
   - **unchanged:** carried over as it is.
   The comparison writes one small table per release (`changes`: set id, old and new version,
   what changed), so the history of wording is itself a dataset. `plainpairs changes --old
   <last build> --new <this build>` does this now; the schema is in `docs/schema.md`.
7. **Checks before delivery:** counts within expected bounds of the last release (a sudden drop
   of more than a few percent stops the run), every row valid against the models, no duplicate
   keys, measures recomputed for changed rows only, a summary of changes.
8. **Deliver** as a pull request on the Hugging Face dataset, with the change summary in its
   description, from a token that can only open pull requests; the maintainer merges it to
   publish. A failed run opens an issue in this repository.
9. **Kaggle mirror and Zenodo:** by hand, monthly and at minor releases, as for CommonsWire.

## Versions over time
The source keeps only the current version of each label, so the weekly releases become the
record of how label wording changes (for example under a final Patient Medication Information
rule). Each release lists the export date it was built from, and the `labels` table keeps
`first_seen` and `last_seen` per version.

## Guards
- `RELEASE_APPROVED` in the repository root before the first publication; a `DELIVERY_ENABLED`
  switch in the workflow, off until the maintainer turns it on.
- Actions pinned to commit SHAs; the token scoped to the one dataset and to pull requests.
- No model calls in the weekly run.

## The route (2026-11-15)
`plainpairs update` does the weekly run (`--from-pack` starts it from the published version:
the record layer is public data, and the structure of every unchanged `current` label is read
back from its measures). The workflow `.github/workflows/weekly-update.yml` runs it on GitHub
Actions; it is **switched off** (no schedule, no delivery) until the repository is public.

| | needs |
|---|---|
| disk | about 6 to 8 GB: openFDA's 14 parts (1.9 GB), DailyMed's daily updates for the week (about 0.7 GB), the last pack (0.56 GB) and two builds; a standard runner has 14 GB free |
| memory | the build's workers (about 120 MB each) and the pack writer, which holds one text table at a time (about 2 GB); a standard public runner has 16 GB, a private one 7 GB |
| time | two builds, the codes and the pack: about 20 minutes on this project's laptop with six workers; an estimated 50 to 60 minutes on a four-core public runner, 90 on a two-core private one (not yet measured on a runner) |
| minutes | free once the repository is public; while it is private, about 90 billed minutes a run, about 390 a month, which this account's private quota cannot carry |
| secrets | `HF_TOKEN` in the environment `release`, able to open pull requests on `obadakr/plainpairs` only, for the delivery job |

So: **a standard runner can do it**, once the repository is public. Until then the weekly run
is done from the maintainer's Mac with the same command (`plainpairs update --work ...`), and
delivered with the publish script's `update` step. The first real run waits for openFDA's next
export after 2026-11-13 (none was listed on 2026-11-15).

## Text from NCI's cancer information summaries (configuration `nci`)
NCI updates its summaries one at a time, each with its own "Updated" date, and its sitemap's
dates are a site-wide publishing date, not a change date (752 of 757 summary pages carried one
day in October 2026). So a change cannot be seen without reading the pages.

- **Cadence: every three months**, not weekly. A full reading on 2026-11-15 took 760 requests
  (robots.txt, the reuse policy, the sitemap index and the page sitemap, then 756 summary pages),
  149.3 MB and 65 minutes at one request every 5 seconds, with every answer 200. NCI's own
  update dates on that day: only 6 of the 756 summaries were updated in the past 12 months
  (the latest on 2026-10-15); 449 carry a date in 2025 and 196 in 2024. Read every three
  months, the cost is about 3,040 requests and 600 MB a year. If NCI's update rate returns to
  that of 2025, monthly reading (about 9,100 requests a year) is the next step.
- **Each reading:** read the sitemap; read every summary page once; build the three `nci` tables;
  compare each page's `text_sha256` and `nci_updated` with the last build; record the pages that
  changed, appeared or left; deliver with the label release.
- **In a GitHub Actions run** the pages are read and parsed in memory and not kept; the saved
  copies on the maintainer's drive stay the evidence of the first reading.
