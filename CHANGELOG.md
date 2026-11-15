# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- The repository: Apache-2.0 license, README, NOTICE and a draft citation file.
- CI: ruff and pytest on Python 3.10 to 3.13, with every action pinned to a commit.
- Runtime dependencies: pydantic (frozen record models) and requests (HTTP).
- Commands: `fetch-page` and `quotes-check` (source pages kept as evidence, quotes checked
  word for word), `counts` (label API counts, resumable), `download-part` (one bulk part,
  200 MB at most).
- A label parser: one row per label with its identity, its prescriber sections and its
  patient texts, cleaned of markup with headings kept, and its tables as plain rows.
- Readability measures (Flesch-Kincaid grade, Flesch reading ease, SMOG) and the standard
  headings of Medication Guides found by their wording.
