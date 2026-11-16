# sbir-awards

Every SBIR and STTR award in SBIR.gov's bulk award download, as one Parquet file on Hugging Face:
https://huggingface.co/datasets/abigailhaddad/sbir-awards. Not affiliated with SBA or SBIR.gov.

Read the [dataset card](https://huggingface.co/datasets/abigailhaddad/sbir-awards) before using it. It gives the
as-of date, what was left out and why, and the caveats (amounts are total award amounts, recent years are
incomplete, the ownership flags disagree with SBIR.gov's own site for some awards).

## Where the data comes from

SBIR.gov publishes two bulk files on its [data resources page](https://www.sbir.gov/data-resources):

- [award data without abstracts](https://data.www.sbir.gov/mod_awarddatapublic_no_abstract/award_data_no_abstract.csv)
  (about 90 MB). SBIR.gov refreshes it; the copy used on 2026-11-15 was last modified 2026-11-01. This is the table.
- [award data with abstracts](https://data.www.sbir.gov/awarddatapublic/award_data.csv) (about 370 MB), an older
  export whose newest awards are from early 2024. Abstracts are copied from it where a record matches exactly.

SBIR.gov's awards API was down for maintenance on 2026-11-15 (it returns 403 Forbidden and the API page says so),
so it isn't used. www.sbir.gov's robots.txt doesn't disallow `/awards` or `/data-resources`; the files are on
a separate host (data.www.sbir.gov, an S3 bucket with no robots.txt) linked from that page.

## Checks

- `src/check.py` compares the table's counts with the ones SBIR.gov shows on www.sbir.gov/awards: total, and by
  agency, phase, program and award year. They matched exactly on 2026-11-15 (219,780 rows). The refresh stops
  before uploading if they don't.
- `checks/nih_compare_2026-11-15.md`: NIH's SBIR/STTR awards matched grant by grant against NIH RePORTER, a
  separate database, for 2015-2025. Every row on each side lands in a named category (matched, other year,
  contract, grantee change and so on); 57 SBIR.gov rows over 11 years are grant numbers
  not in the RePORTER pull (8 of them supplements, which the pull leaves out).
- `checks/sample_2026-11-15.md`: 25 random awards and 13 edge cases compared field by field with their SBIR.gov
  award pages.

## Run it

    pip install -r requirements-dev.txt
    python -m pytest tests
    python src/build.py          # downloads both files (about 460 MB, held in memory), writes out/
    python src/check.py          # compares counts with www.sbir.gov/awards
    HF_TOKEN=... python src/publish.py
    python checks/sample.py 25 SEED                                  # field-by-field sample, about 10 minutes
    python checks/nih_reporter_pull.py 2015 2025 > reporter.csv      # then gzip it and run checks/nih_compare.py

## Refresh

`.github/workflows/refresh.yml` runs every Monday: build, compare counts, upload if SBIR.gov's file has changed.

**It needs a repository secret named `HF_TOKEN`** (a Hugging Face token with write access to
abigailhaddad/sbir-awards). Until it's added, the upload step prints a notice and skips, and the dataset stays as
it was first published.

If SBIR.gov updates its site counts before its bulk file (or the other way around), the count check fails and
nothing is uploaded that week. That's on purpose: look at `checks/facets_<date>.json` from a local run to see which
counts moved.

If the awards page shows no counts at all (no "Showing 1-N of N results" line and no number after any label, as on
2026-11-16), the check has nothing to compare against. It never reads a missing count as 0. The run skips the
upload and the SQLite step, stays green, and opens a GitHub issue (or comments on the open one) with what it saw.

Data: U.S. government data from SBIR.gov. Code: MIT.

## Data dictionary

[`docs/data_dictionary.md`](docs/data_dictionary.md) lists every column of the table with its type, a description, the share of rows that have a value, and an example. Types, counts and examples are read from the published parquet files; descriptions are in [`docs/tables.toml`](docs/tables.toml), written from the code that builds each column and SBIR.gov's [award data dictionary](https://www.sbir.gov/data-resources/data-dictionary/award). Regenerate it with

    python src/data_docs.py fetch data   # download the current files from Hugging Face
    python src/data_docs.py write data   # write docs/data_dictionary.md

`src/build.py` puts the same section on the Hugging Face dataset card (`out/README.md`). Both stop with an error if a parquet column has no description in `docs/tables.toml` or a described column is gone, and the weekly workflow runs that check too.

## SQLite download

The weekly workflow builds `sbir-awards.sqlite` from the files on Hugging Face (table `awards`, plus `_source`, which records the Hugging Face commit) and attaches it (about 430 MiB) to the GitHub release [`latest-data`](https://github.com/abigailhaddad/sbir-awards/releases/tag/latest-data). The release is replaced whenever the Hugging Face commit changes. To build it yourself:

    python src/build_sqlite.py data sbir-awards.sqlite
