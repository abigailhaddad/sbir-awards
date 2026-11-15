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

Data: U.S. government data from SBIR.gov. Code: MIT.
