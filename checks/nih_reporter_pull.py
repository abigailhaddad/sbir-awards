"""Second, independent check: NIH SBIR/STTR awards by fiscal year from NIH RePORTER (api.reporter.nih.gov).

    python checks/nih_reporter_pull.py 2015 2025 > checks/nih_reporter_YYYY-MM-DD.csv

Writes one row per RePORTER project record (fiscal year, activity code, award type, IC, amount).
One request a second. Only the SBIR/STTR activity codes are asked for.
"""
import csv, json, sys, time, urllib.request

CODES = ["R41", "R42", "R43", "R44", "U43", "U44", "SB1", "UT1", "UT2"]
URL = "https://api.reporter.nih.gov/v2/projects/search"
UA = "sbir-awards-dataset-check (github.com/abigailhaddad/sbir-awards)"


def page(fy, offset):
    body = {"criteria": {"fiscal_years": [fy], "activity_codes": CODES},
            "offset": offset, "limit": 500,
            "include_fields": ["ApplId", "FiscalYear", "ProjectNum", "ActivityCode", "AwardType",
                               "AwardAmount", "AgencyIcAdmin", "AwardNoticeDate"]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as e:
            print(f"retry {fy} {offset}: {e}", file=sys.stderr)
            time.sleep(10)
    raise SystemExit(f"failed {fy} {offset}")


def main():
    y0, y1 = int(sys.argv[1]), int(sys.argv[2])
    w = csv.writer(sys.stdout)
    w.writerow(["fiscal_year", "appl_id", "project_num", "activity_code", "award_type", "ic", "award_amount", "award_notice_date"])
    for fy in range(y0, y1 + 1):
        offset, total = 0, None
        while total is None or offset < total:
            d = page(fy, offset)
            total = d["meta"]["total"]
            for r in d["results"]:
                ic = (r.get("agency_ic_admin") or {}).get("abbreviation", "")
                w.writerow([r["fiscal_year"], r["appl_id"], r["project_num"], r["activity_code"],
                            r.get("award_type") or "", ic, r.get("award_amount") or "", r.get("award_notice_date") or ""])
            offset += 500
            time.sleep(1)
        print(f"FY{fy}: {total}", file=sys.stderr)


if __name__ == "__main__":
    main()
