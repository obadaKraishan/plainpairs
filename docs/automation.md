# Automation

A weekly run reads the newest export, finds new and changed labels, builds the next dataset
version and delivers it as a **draft pull request** on the Hugging Face dataset, which is
published only when the maintainer reads it and merges it (the pattern of the CommonsWire
weekly update). It runs on GitHub Actions: `.github/workflows/weekly-update.yml`, with the stop
issue in `.github/workflows/failure-issue.yml`. Version 0.2.0 was the first weekly update, built
and delivered from the maintainer's Mac; the workflow builds 0.2.1 and every version after it.

## What the source allows and requires
- The label data are updated weekly (dataset page: "Frequency Weekly"); the export of
  2026-11-13 is dated in `download.json` (`export_date`, `meta.last_updated`).
- Any record may change in any update, so the run downloads **all** parts every week and
  never patches: "you cannot simply download 'new' files to keep your downloaded version up to
  date" (`docs/sources.md`).
- 15 requests a week (`download.json` and 14 parts, about 1.9 GB) is far inside the limits for
  requests without a key (1,000 a day); no key is needed.

## The weekly run
1. **When.** A GitHub Actions schedule, Mondays at 07:23 UTC, plus a button to run it by hand.
   openFDA now lists a new export most days (2026-11-26 and 2026-11-27), so each run takes the
   newest.
2. **Check for a new export.** Read `download.json`; if `export_date` equals the last release's,
   stop with nothing to do.
3. **Download.** The 14 parts, one at a time, each streamed and checked against its size; the
   runner's disk holds the 1.9 GB zipped and nothing is unpacked (a standard runner had 87 GB
   free at the start on 2026-11-27, and 82 GB at the lowest).
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
   in place like the full release (the first run, on 2026-11-27, read one daily file of
   129 MB). The weekly run never reads the full release: it rebuilds the last version's structure
   from the published `current` tables (their measures from structure) and reads only update
   files. Whether
   the full release must be read again from time to time (DailyMed replaces it on its own
   schedule) is still open; each run's report gives the update files and their label counts.
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
     scope, or gone from the source. Such a label is counted, and it is not in the new
     version's tables (its rows stay in the earlier versions);
   - **unchanged:** carried over as it is.
   The comparison writes one small table per release (`changes`: set id, old and new version,
   what changed), so the history of wording is itself a dataset. `plainpairs changes --old
   <last build> --new <this build>` does this now; the schema is in `docs/schema.md`.
7. **Checks before delivery:** DailyMed's coverage (a weekday its listed files no longer cover
   stops the run before any download); the release check of the build (`docs/schema.md`,
   "Release rules"); the pack check, with the easy-access layer row for row; Hugging Face's card
   validator; open removal requests and open pull requests on the dataset. Not built: a limit on
   how far the counts may fall from one version to the next.
8. **Deliver** as a draft pull request on the Hugging Face dataset, with the run's report (counts
   only) as its description, from a token that can read the dataset and open pull requests on
   it, nothing more; then the pull request is checked signed out by hash. The maintainer reads
   it and merges it to publish. A run that stops or fails opens an issue in this repository.
9. **Kaggle mirror and Zenodo:** by hand, monthly and at minor releases, as for CommonsWire.

## Versions over time
The source keeps only the current version of each label, so the weekly releases become the
record of how label wording changes (for example under a final Patient Medication Information
rule). Each version names the export it was built from (`export_date` in every row, and the
manifest's `sources`), and each update counts what changed against the version before it (the
run's report, in the pull request's description). The tables hold no first-seen or last-seen
dates: a label's history is read across versions.

## Guards
- A weekly version reaches the dataset only as a draft pull request, which the maintainer
  publishes and merges; the workflow's token cannot write to `main` or tag.
- `DELIVERY_ENABLED` in the workflow, and the schedule with it; a removal request or a pull
  request still open on the dataset stops the next delivery.
- Actions pinned to commit SHAs; `HF_TOKEN` read in one step only.
- No model calls in the weekly run.

## The workflow (2026-11-27)
One job, `update`, builds, checks and delivers, because jobs share no disk. It runs in the
environment `release` (deployments from `main` only), which holds the secret `HF_TOKEN`: a
fine-grained Hugging Face token for `obadakr/plainpairs` only, with read access and "Open pull
requests", and no write. Its steps:

1. check out the repository (no saved credentials), set up uv and Python 3.12 (no cache) and
   install the locked project;
2. count what must stop a delivery: open removal requests on the repository (issues labelled
   `takedown`) and open pull requests on the dataset. With delivery on, either one stops the
   run before it builds anything;
3. download the published version anonymously, only the ten files `--from-pack` reads (the
   manifest, each configuration's labels, patient texts and section pairs, and the NCI tables:
   58 MB for 0.2.0), and name the next version (`python -m plainpairs.weekly next-version`:
   the last number raised, 0.2.0 to 0.2.1);
4. `plainpairs update --from-pack` with four workers and the caps of 120 calls and 4 GB,
   counted from the step's start;
5. if the update is ready: `release build` and `release check` (the pack on its own, with its
   easy-access layer row for row), then Hugging Face's own card validator;
6. the run's report (`python -m plainpairs.weekly report`): counts, dates, names and hashes only,
   from named fields of `summary.json`, the manifest and the usage log. It is the job summary,
   the stop issue's body and the pull request's description;
7. **deliver** (delivery on, the update ready): the only step that reads `HF_TOKEN`, in its own
   `env`. `hf auth whoami`, then `hf upload ... --create-pr`, which opens a draft pull request
   titled "PlainPairs VERSION" with the report as its description;
8. **check** the pull request signed out (no token in the step, an empty `HF_HOME`):
   `python -m plainpairs.weekly pr-check` finds the open pull request by its title and compares
   every file of `refs/pr/N` with the pack by hash (data and easy-access files by LFS SHA-256
   and size or by git blob id; README, LICENSES and the manifest by blob id), and fails on any
   file the pack does not have.

A second job, `report`, runs when the first fails or stops: it calls `failure-issue.yml`, which
opens an issue titled "Weekly update stopped", or comments on the one already open, with the
report (counts only). While delivery is off, it writes the would-be issue to the job summary.

**Measured.** The first run by hand, with delivery off (2026-11-27, run 46011002223), took
1 h 2 min 39 s on a standard runner, 3,273 s of it in the update: 19 calls and 2,048,518,491
bytes, inside the caps of 120 calls and 4 GB. Free space on the runner was 87 GB at the start,
84 GB after the update and 82 GB after the pack. It built 0.2.1 from the export of 2026-11-27
(3 labels with record fields changed only), and every check passed: the release check (0
problems), the pack check and the card validator. The two delivery steps were skipped and no
issue was opened.

**Switched on and off.** The schedule (Mondays, 07:23 UTC) and `DELIVERY_ENABLED: "true"` change
together, in one pull request (a test checks it). They were switched on on 2026-11-27; the first
scheduled run is on Monday, 2026-11-30. Setting `DELIVERY_ENABLED` back to "false"
makes every run a dry run: it builds and checks, uploads nothing and opens no issue. A run can
always be started by hand from the Actions tab.

**Versions.** Weekly versions (0.2.1, 0.2.2, ...) are not tagged (the token cannot tag): each is
the dataset commit titled "PlainPairs 0.2.N (#K)", and its manifest names it. Minor versions
(0.2.0, 0.3.0) are built and tagged by hand from the Mac with the publish script, with a GitHub
release and a Zenodo record. The Kaggle mirror is not updated from here: it gets a new version
by hand, about monthly.

**Never.** No job runs on pull requests, so a fork's pull request never reaches the workflow or
its secret. Every action is pinned to a full commit SHA. Nothing is uploaded as an artifact.
Logs, the job summary, the issue and the pull request's description hold no label or summary
text. The workflow uses no model and no paid service.

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
