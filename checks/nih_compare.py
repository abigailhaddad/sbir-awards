"""Compare SBIR.gov's NIH awards (out/awards.parquet) with NIH RePORTER (checks/nih_reporter_*.csv.gz).

    python checks/nih_compare.py checks/nih_reporter_2026-11-15.csv.gz

RePORTER side: SBIR/STTR activity codes, NIH institutes only (CDC and FDA centers dropped), award types that start
or move an award (1 new, 2 renewal, 4 extension, 6 and 7 change of organization or grantee, 9 change of institute);
type 5 (later years of a multi-year award) and type 3 (supplements) left out. Matched to SBIR.gov on the full grant
number (SBIR.gov `contract`, RePORTER `project_num`).
"""
import sys

import pandas as pd

KEEP_TYPES = {"1", "2", "4N", "4C", "6", "7", "9"}
NOT_NIH = {"NIOSH", "FDA", "NCEZID", "NCIPC", "NCIRD", "NCCDPHP", "NCHHSTP", "CGH", "NCBDDD", "GHC", "COTPER", "NCEH"}

r = pd.read_csv(sys.argv[1], dtype=str, keep_default_na=False)
r = r[~r.ic.isin(NOT_NIH) & r.award_type.isin(KEEP_TYPES)].copy()
r["k"] = r.project_num.str.strip()
d = pd.read_parquet("out/awards.parquet", columns=["branch", "award_year", "contract"])
n = d[d.branch == "National Institutes of Health"].copy()
n["k"] = n.contract.str.strip()
n["kind"] = "contract number"  # anything not shaped like an NIH grant number (75N..., HHSN..., 2612...)
n.loc[n.k.str.match(r"^\d[A-Z]\d\d[A-Z]{2}\d{6}"), "kind"] = "grant"
n.loc[n.k.str.match(r"^3"), "kind"] = "supplement (type 3)"
rk, nk = set(r.k), set(n.k)
rows = []
# sbir_gov = same_number_same_year + sbir_gov_repeat_number + sbir_gov_other_fy + sbir_gov_only
# reporter = same_number_same_year + reporter_repeat_number + reporter_other_year + reporter_only
for fy in sorted(set(r.fiscal_year.astype(int))):
    a, b = r[r.fiscal_year == str(fy)], n[n.award_year == fy]
    only_s = b[~b.k.isin(rk)]
    same = set(a.k) & set(b.k)
    bm, am = b[b.k.isin(rk)], a[a.k.isin(nk)]
    rows.append({"year": fy, "reporter": len(a), "sbir_gov": len(b),
                 "same_number_same_year": len(same),
                 "sbir_gov_repeat_number": int(bm.k.isin(same).sum() - len(same)),
                 "sbir_gov_other_fy": int((~bm.k.isin(same)).sum()),
                 "reporter_repeat_number": int(am.k.isin(same).sum() - len(same)),
                 "reporter_other_year": int((~am.k.isin(same)).sum()),
                 "reporter_only": int((~a.k.isin(nk)).sum()),
                 "reporter_only_type_6_7": int((~a.k.isin(nk) & a.award_type.isin({"6", "7"})).sum()),
                 "sbir_gov_only": len(only_s),
                 "sbir_gov_only_contract_numbers": int((only_s.kind == "contract number").sum()),
                 "sbir_gov_only_supplements": int((only_s.kind == "supplement (type 3)").sum())})
t = pd.DataFrame(rows)
assert (t.sbir_gov == t.same_number_same_year + t.sbir_gov_repeat_number + t.sbir_gov_other_fy + t.sbir_gov_only).all()
assert (t.reporter == t.same_number_same_year + t.reporter_repeat_number + t.reporter_other_year + t.reporter_only).all()
print("| " + " | ".join(t.columns) + " |")
print("|" + "---|" * len(t.columns))
for row in t.itertuples(index=False):
    print("| " + " | ".join(str(v) for v in row) + " |")
