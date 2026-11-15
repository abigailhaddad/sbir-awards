"""Completeness check: compare out/awards.parquet with the counts SBIR.gov shows on https://www.sbir.gov/awards.

    python src/check.py            # exits 1 if the total or any agency, phase, program or year count differs

Writes checks/facets_<date>.json (SBIR.gov's counts, ours, and the differences). One request.
"""
import datetime as dt
import json
import os
import sys
import urllib.request

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import sbir


def main():
    req = urllib.request.Request(sbir.AWARDS_PAGE, headers={"User-Agent": sbir.UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        html = r.read().decode("utf-8", "replace")
    facets = sbir.facet_counts(html)
    df = pd.read_parquet("out/awards.parquet")
    for c in ["agency", "branch", "phase", "program", "state", "hubzone_owned", "woman_owned"]:
        df[c] = df[c].fillna("")
    ours = sbir.table_counts(df)
    diffs = sbir.compare(facets, ours)
    info = sbir.compare(facets, ours, kinds=("branch", "state", "demographic"))
    day = dt.date.today().isoformat()
    os.makedirs("checks", exist_ok=True)
    with open(f"checks/facets_{day}.json", "w") as fh:
        json.dump({"read_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                   "page": sbir.AWARDS_PAGE, "sbir_gov": facets, "ours": ours,
                   "differences_checked": diffs, "differences_not_checked": info}, fh, indent=1)
    print(f"SBIR.gov total {facets.get('total')}, ours {ours['total']}")
    for d in info:
        print("  (not checked)", d)
    if diffs:
        for d in diffs:
            print("  DIFFERS", d)
        sys.exit(f"STOP: {len(diffs)} counts differ from SBIR.gov")
    print("total, agency, phase, program and year counts all match SBIR.gov")


if __name__ == "__main__":
    main()
