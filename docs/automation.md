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
4. **Structure from DailyMed** (for the `current` configuration). The full release (6 parts,
   18.1 GB) is read once; each week only DailyMed's update files since the last run are
   fetched: the weekly update zip (2026-11-02 to 06: 1,590 labels of every kind, 679.93 MB as
   listed) or, to match the export day exactly, the daily update zips up to it (38 to 226 MB a
   day in the week of 2026-11-09). A label changed since the last run is read from the update
   that holds its new version; an unchanged label keeps the structure of the last build. The
   zip file metadata (7.65 MB) is read again for the "served" flag. About 0.7 GB a week, read
   in place like the full release. The full release does not fit a standard runner's disk
   (14 GB), so the weekly run starts from the last build's structure table and reads only
   update files; whether the full release must be read again from time to time (DailyMed
   replaces it on its own schedule) is checked against the update files' counts in S4.
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
