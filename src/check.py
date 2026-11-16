"""Completeness check: compare out/awards.parquet with the counts SBIR.gov shows on https://www.sbir.gov/awards.

    python src/check.py            # exits 1 if the total or any agency, phase, program or year count differs

Writes checks/facets_<date>.json (SBIR.gov's counts, ours, and the differences). One request.

Three outcomes:
  match      every checked count agrees: verified=true, the workflow uploads.
  differ     counts are on the page and some differ: exits 1, the run fails, nothing is uploaded.
  no counts  the page shows no counts at all (no total, no "(n)" on any label): nothing to compare against.
             Exits 0 with verified=false, so the workflow skips the upload without failing, and writes
             out/no_counts_issue.md for the workflow to post as a GitHub issue. A missing count is never read
             as 0.
In GitHub Actions `verified=true|false` goes to $GITHUB_OUTPUT; the upload and SQLite steps run only on true.
"""
import datetime as dt
import json
import os
import sys
import urllib.request

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import sbir

NO_COUNTS_MSG = "SBIR.gov's awards page shows no counts; could not verify; not uploading."


def fetch_page():
    req = urllib.request.Request(sbir.AWARDS_PAGE, headers={"User-Agent": sbir.UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", "replace")


def set_output(verified, github_output):
    if github_output:
        with open(github_output, "a") as fh:
            fh.write(f"verified={'true' if verified else 'false'}\n")


def run(html, ours, day, checks_dir="checks", issue_path="out/no_counts_issue.md", github_output=None):
    """Compare and record. Returns "match" or "no_counts"; exits 1 (SystemExit) if counts differ."""
    facets = sbir.facet_counts(html)
    os.makedirs(checks_dir, exist_ok=True)
    record = {"read_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "page": sbir.AWARDS_PAGE, "sbir_gov": facets, "ours": ours}

    if sbir.shows_no_counts(facets):
        record["result"] = "no_counts"
        with open(os.path.join(checks_dir, f"facets_{day}.json"), "w") as fh:
            json.dump(record, fh, indent=1)
        os.makedirs(os.path.dirname(issue_path) or ".", exist_ok=True)
        with open(issue_path, "w") as fh:
            fh.write(sbir.no_counts_report(facets, html, day, ours["total"]))
        print(f"::warning::{NO_COUNTS_MSG}")
        print(NO_COUNTS_MSG)
        print(f"our table: {ours['total']} rows; SBIR.gov total: not shown")
        set_output(False, github_output)
        return "no_counts"

    diffs = sbir.compare(facets, ours)
    info = sbir.compare(facets, ours, kinds=("branch", "state", "demographic"))
    record.update(result="differ" if diffs else "match", differences_checked=diffs, differences_not_checked=info)
    with open(os.path.join(checks_dir, f"facets_{day}.json"), "w") as fh:
        json.dump(record, fh, indent=1)
    print(f"SBIR.gov total {facets.get('total')}, ours {ours['total']}")
    for d in info:
        print("  (not checked)", d)
    if diffs:
        for d in diffs:
            print("  DIFFERS", d)
        set_output(False, github_output)
        sys.exit(f"STOP: {len(diffs)} counts differ from SBIR.gov")
    print("total, agency, phase, program and year counts all match SBIR.gov")
    set_output(True, github_output)
    return "match"


def main():
    html = fetch_page()
    df = pd.read_parquet("out/awards.parquet")
    for c in ["agency", "branch", "phase", "program", "state", "hubzone_owned", "woman_owned"]:
        df[c] = df[c].fillna("")
    run(html, sbir.table_counts(df), dt.date.today().isoformat(), github_output=os.environ.get("GITHUB_OUTPUT"))


if __name__ == "__main__":
    main()
