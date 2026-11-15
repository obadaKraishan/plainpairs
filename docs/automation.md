# Automation sketch (nothing built)

**A sketch for S4.** A weekly run that reads the newest export, finds new and changed labels,
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
   time is set from the `export_date` history in S4), plus a manual button.
2. **Check for a new export.** Read `download.json`; if `export_date` equals the last release's,
   stop with nothing to do.
3. **Download.** The 14 parts, one at a time, each streamed and checked against its size; the
   runner's disk (14 GB) holds the 1.9 GB zipped and nothing is unpacked.
4. **Parse and build** the three tables (`docs/schema.md`) for labels in scope.
5. **Compare with the last release, by set id:**
   - **new:** a set id not in the last release;
   - **changed:** same set id, a higher version or a different core hash of any text;
   - **removed:** a set id that left the source (kept in the release with `last_seen`, as the
     record of what was published, unless the maintainer decides otherwise);
   - **unchanged:** carried over as it is.
6. **Checks before delivery:** counts within expected bounds of the last release (a sudden drop
   of more than a few percent stops the run), every row valid against the models, no duplicate
   keys, measures recomputed for changed rows only, a summary of changes.
7. **Deliver** as a pull request on the Hugging Face dataset, with the change summary in its
   description, from a token that can only open pull requests; the maintainer merges it to
   publish. A failed run opens an issue in this repository.
8. **Kaggle mirror and Zenodo:** by hand, monthly and at minor releases, as for CommonsWire.

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
