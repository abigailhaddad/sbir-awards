# NIH awards: SBIR.gov compared with NIH RePORTER, 2026-11-15

A second, independent source for one agency. NIH is the largest civilian SBIR/STTR funder (37,061 of the 219,780
rows), and NIH RePORTER (api.reporter.nih.gov) publishes every NIH grant with its grant number, so the two can be
matched record by record, not just by total.

- SBIR.gov side: rows in `out/awards.parquet` with branch "National Institutes of Health", by `award_year`.
- RePORTER side: pulled 2026-11-15 with `checks/nih_reporter_pull.py 2015 2025` (21,888 records, saved as
  `nih_reporter_2026-11-15.csv.gz`), activity codes R41, R42, R43, R44, U43, U44, SB1, UT1, UT2. Kept: NIH
  institutes only (CDC centers, NIOSH and FDA dropped) and award types 1, 2, 4, 6, 7, 9. Left out: type 5 (the
  second and later budget years of an award already counted) and type 3 (supplements). By fiscal year.
- Matched on the full grant number: SBIR.gov `contract` = RePORTER `project_num` (e.g. `1R43CA125917-01`).

Run `python checks/nih_compare.py checks/nih_reporter_2026-11-15.csv.gz` to rebuild the table.

Every row on both sides falls in exactly one column (the script asserts it):
SBIR.gov = same number same year + SBIR.gov repeat number + SBIR.gov other FY + SBIR.gov only;
RePORTER = same number same year + RePORTER repeat number + RePORTER other year + RePORTER only.

| year | reporter | sbir_gov | same_number_same_year | sbir_gov_repeat_number | sbir_gov_other_fy | reporter_repeat_number | reporter_other_year | reporter_only | reporter_only_type_6_7 | sbir_gov_only | sbir_gov_only_contract_numbers | sbir_gov_only_supplements |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2015 | 1113 | 1200 | 1081 | 5 | 8 | 0 | 3 | 29 | 8 | 106 | 101 | 1 |
| 2016 | 1237 | 1304 | 1187 | 20 | 14 | 0 | 4 | 46 | 16 | 83 | 71 | 1 |
| 2017 | 1317 | 1371 | 1268 | 10 | 17 | 0 | 2 | 47 | 17 | 76 | 70 | 0 |
| 2018 | 1451 | 1516 | 1426 | 1 | 4 | 2 | 1 | 22 | 11 | 85 | 78 | 1 |
| 2019 | 1502 | 1595 | 1485 | 0 | 1 | 0 | 2 | 15 | 14 | 109 | 102 | 2 |
| 2020 | 1267 | 1352 | 1250 | 1 | 4 | 0 | 1 | 16 | 11 | 97 | 90 | 0 |
| 2021 | 1249 | 1313 | 1226 | 0 | 6 | 0 | 2 | 21 | 11 | 81 | 75 | 2 |
| 2022 | 1258 | 1327 | 1243 | 0 | 2 | 1 | 1 | 13 | 10 | 82 | 77 | 1 |
| 2023 | 1290 | 1339 | 1266 | 0 | 2 | 0 | 5 | 19 | 15 | 71 | 71 | 0 |
| 2024 | 1109 | 1181 | 1093 | 0 | 2 | 0 | 0 | 16 | 14 | 86 | 86 | 0 |
| 2025 | 1060 | 1103 | 1051 | 0 | 0 | 0 | 4 | 5 | 3 | 52 | 50 | 0 |

What the gaps are:

- SBIR.gov only: almost all are NIH contracts (numbers like `75N91019C00047`, `HHSN...` or `2612...`), which
  RePORTER, a grants database, doesn't list under these activity codes. The rest are a few supplements (`3R44...`)
  and a handful of grant numbers RePORTER doesn't return for 2015-2025.
- RePORTER only: mostly type 6 and 7 records (a grant moved to a new organization or grantee). SBIR.gov lists the
  award under its original number.
- Other year / repeat number: the same grant number in a different fiscal year on the other side (most within
  one year), or the same grant number on more than one SBIR.gov row (2015-2017 mostly).
- So for 2015-2025, 13,576 NIH grant awards appear in both under the same number and year; SBIR.gov has 928
  awards RePORTER doesn't (871 of them contracts), and RePORTER has 249 grants SBIR.gov doesn't (130 of them
  type 6 or 7).

Amounts are not compared as totals: SBIR.gov's `award_amount` is the total award, RePORTER's `award_amount` is that
fiscal year's funding. For awards matched on number and year, the amounts are equal for 85% of Phase I awards
(7,435 of 8,764; SBIR.gov is higher for 1,305, multi-year Phase I) and for 14% of Phase II (577 of 4,210; SBIR.gov
higher for 3,629), which is what you'd expect from a total compared with a first year.
