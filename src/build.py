"""Download SBIR.gov's two bulk award files, build out/awards.parquet, out/report.json and out/README.md.

    python src/build.py                       # downloads both files (about 460 MB, not kept on disk)
    python src/build.py CURRENT.csv ABS.csv   # local copies instead
"""
import datetime as dt
import io
import json
import os
import sys
import urllib.request

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import sbir

OUT = "out"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": sbir.UA})
    with urllib.request.urlopen(req, timeout=600) as r:
        last_modified = r.headers.get("Last-Modified", "")
        data = r.read()
    print(f"{url}: {len(data):,} bytes, Last-Modified {last_modified}")
    return io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig", errors="replace"), last_modified


def head_date(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": sbir.UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.headers.get("Last-Modified", "")


def main():
    if len(sys.argv) == 3:
        cur = sbir.read_csv(sys.argv[1])
        ab = pd.read_parquet(sys.argv[2]) if sys.argv[2].endswith(".parquet") else sbir.read_csv(sys.argv[2])
        cur_lm, ab_lm = head_date(sbir.CURRENT_URL), head_date(sbir.ABSTRACTS_URL)
    else:
        f, cur_lm = fetch(sbir.CURRENT_URL)
        cur = sbir.read_csv(f)
        f, ab_lm = fetch(sbir.ABSTRACTS_URL)
        ab = sbir.read_csv(f)
    df, report = sbir.build(cur, ab)
    report["built_utc"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    report["current_file_last_modified"] = cur_lm
    report["abstract_file_last_modified"] = ab_lm
    report["award_year_min"] = int(df.award_year.min())
    report["award_year_max"] = int(df.award_year.max())
    report["by_year"] = {str(k): int(v) for k, v in df.award_year.value_counts().sort_index().items()}
    report["blank_uei"] = int((df.uei == "").sum())
    report["blank_uei_and_duns"] = int(((df.uei == "") & (df.duns == "")).sum())
    report["blank_amount"] = int(df.award_amount.isna().sum())
    report["zero_amount"] = int((df.award_amount == 0).sum())
    report["blank_proposal_award_date"] = int(df.proposal_award_date.isna().sum())
    report["total_amount"] = float(df.award_amount.sum())
    old = df.award_year <= report["abstract_file_max_award_year"] - 1
    report["abstract_old_rows"] = int(old.sum())
    report["abstract_old_missing"] = int((old & df.abstract.eq("")).sum())
    report["abstract_new_rows"] = int((~old).sum())
    report["abstract_new_with"] = int((~old & df.abstract.ne("")).sum())
    os.makedirs(OUT, exist_ok=True)
    # small row groups, so the explorer can read one record's abstract without the whole column
    # Written with DuckDB: pyarrow writes an empty dictionary page for a column chunk that is all null (whole row
    # groups have no proposal_award_date), and the DuckDB-WASM the explorer uses refuses to read that.
    import duckdb
    con = duckdb.connect()
    con.register("awards", df)
    con.execute(f"COPY (SELECT * FROM awards) TO '{OUT}/awards.parquet' "
                "(FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 20000)")
    con.close()
    with open(f"{OUT}/report.json", "w") as fh:
        json.dump(report, fh, indent=1)
    with open(f"{OUT}/README.md", "w") as fh:
        fh.write(card(report))
    print(json.dumps({k: v for k, v in report.items() if k != "by_year"}, indent=1))


def card(r):
    lm = r["current_file_last_modified"]
    return f"""---
license: other
license_name: us-government-data
pretty_name: SBIR and STTR awards
tags:
- government
- contracting
- sbir
size_categories:
- 100K<n<1M
---

# SBIR and STTR awards from SBIR.gov

Every award in SBIR.gov's bulk award download: {r['rows']:,} Small Business Innovation Research (SBIR) and Small
Business Technology Transfer (STTR) awards, award years {r['award_year_min']} to {r['award_year_max']}. Not
affiliated with SBA or SBIR.gov.

As of: built {r['built_utc']} UTC from SBIR.gov's file last modified {lm}. SBIR.gov refreshes that file on its
own schedule, so the newest awards are missing until it does, and recent award years
fill in for months afterward: award year {r['award_year_max']} has {r['by_year'].get(str(r['award_year_max']), 0):,}
records so far.

Code, checks and the field-by-field sample: https://github.com/abigailhaddad/sbir-awards

## Files

`awards.parquet`: one row per row of SBIR.gov's
[award data without abstracts](https://data.www.sbir.gov/mod_awarddatapublic_no_abstract/award_data_no_abstract.csv),
in the same order, with snake_case column names. Values are as published, with leading and trailing spaces
removed; dates are parsed (all non-blank dates in the file are YYYY-MM-DD) and amounts and years are numbers.

Added columns:

- `record_id`: a hash of the identifying fields, for linking. SBIR.gov's file has no award ID. Exact repeats get
  `-2`, `-3`.
- `abstract`: copied from SBIR.gov's older [award data with abstracts](https://data.www.sbir.gov/awarddatapublic/award_data.csv)
  file (Last-Modified {r['abstract_file_last_modified']}; its newest award year is {r['abstract_file_max_award_year']})
  when a record matches exactly one row there on agency, company, contract, tracking number, phase, award year,
  title and amount. {r['abstract_nonblank']:,} rows have one. Of the {r['abstract_old_rows']:,} awards from before
  {r['abstract_file_max_award_year']}, {r['abstract_old_missing']:,} have no abstract here (a title, amount or tracking
  number differs between the two exports, or the abstract is blank there); of the {r['abstract_new_rows']:,} from
  {r['abstract_file_max_award_year']} on, {r['abstract_new_with']:,} have one.
  SBIR.gov's award pages show the abstract for every award.
- `exact_duplicate`: true for the {r['exact_duplicate_rows']} rows that repeat another row in every column.
- `possible_duplicate_count`: how many rows share this row's agency, company, phase, award year, title and amount
  ({r['possible_duplicate_rows']:,} rows in {r['possible_duplicate_groups']:,} groups have 2 or more). SBIR.gov's
  own count includes them, and for the two pairs checked by hand each row has its own award page. Some are the same award entered twice (one sampled
  pair is the same contract listed once as SBIR and once as STTR); some may be separate awards with the same
  title and amount. Nothing was dropped: the row count matches SBIR.gov's own count only with them in.

Left out on purpose: `{"`, `".join(r['dropped_columns'])}`. The phone and email columns are personal contact
details. The "Contact" name and title are out because they aren't what they look like: in a first sample run of 30
awards, the file's Contact Name never matched the Business Contact on the award page; it is often blank or an agency office ("NASA
SBIR Support Office", "AFWERX"). Principal investigator and research institution names are kept. SBIR.gov's award
pages show the rest.

## Checks

- Completeness: the row count and the counts by agency, phase, program and award year match the counts SBIR.gov
  shows on https://www.sbir.gov/awards exactly (see `checks/` in the repo; the refresh stops if they don't).
  SBIR.gov calls the Department of Defense "Department of War" on the site and "Department of Defense" in the
  file. Its HUBZone and woman-owned filter counts don't match the Y counts in the file's flag columns; see
  caveats.
- A second, independent source: NIH's awards matched grant number by grant number against NIH RePORTER for
  2015-2025 (`checks/nih_compare_2026-11-15.md`). 13,576 appear in both under the same number and year. SBIR.gov
  has 928 more, 871 of them NIH contracts, which RePORTER doesn't list; RePORTER has 249 more, 130 of them grants
  moved to a new organization, which SBIR.gov lists under the original number.
- 25 random awards plus edge cases compared field by field with their SBIR.gov award pages (`checks/sample_*.md`).

## Caveats

- `award_amount` is SBIR.gov's "Total Award Amount", not obligations. {r['zero_amount']:,} rows are 0 and
  {r['blank_amount']} are blank.
- `award_year` is the only date on every row. `proposal_award_date` is blank on {r['blank_proposal_award_date']:,}
  rows, and some dates are impossible as published (years like 1905 or 5025).
- {r['blank_uei']:,} rows have no UEI (UEIs replaced DUNS in 2022; older awards have only DUNS);
  {r['blank_uei_and_duns']:,} have neither.
- `hubzone_owned`, `woman_owned`, `socially_economically_disadvantaged` are Y, N or U (unknown) as SBIR.gov
  publishes them in the file. They don't always agree with SBIR.gov's own award pages: in a sample of 38 awards,
  3 differed (one Y in the file was No on the page, one N was Yes, one N was N/A), and the site's HUBZone and
  woman-owned filter counts (4,397 and 16,293 on 2026-11-15) differ from the Y counts in the file. Check the award
  page before relying on a flag for one firm.
- `contract` is not unique: some agencies list one solicitation-wide number for many awards.
- Agency and branch are SBIR.gov's labels. `branch` is blank for agencies with no sub-units listed.

Data: U.S. government data from SBIR.gov. Code: MIT.
"""


if __name__ == "__main__":
    main()
