"""Proof file: compare a sample of rows in out/awards.parquet with their award pages on SBIR.gov, field by field.

    python checks/sample.py 25 SEED     # writes checks/sample_<date>.md

The bulk file has no award ID, so each row's page is found with SBIR.gov's own award search (company name and the
start of the title), and the candidate pages are read until one shows the same contract number, tracking number,
award year and amount. About one request a second.
"""
import datetime as dt
import html as H
import re
import sys
import time
import urllib.parse
import urllib.request

import pandas as pd

UA = "sbir-awards-dataset-check (github.com/abigailhaddad/sbir-awards)"
BASE = "https://www.sbir.gov"
STATES = {}  # full name -> two-letter code, as SBIR.gov shows on award pages (checks/states.csv)
# Award pages show agency and branch codes. These are the names SBIR.gov gives each code in the filter list on
# www.sbir.gov/awards, spelled as in the bulk file ("Department of War" on the site is "Department of Defense" there).
AGENCY_CODES = {
    "USDA": "Department of Agriculture", "NIFA": "National Institute of Food and Agriculture",
    "DOC": "Department of Commerce", "NIST": "National Institute of Standards and Technology",
    "NOAA": "National Oceanic and Atmospheric Administration", "DOW": "Department of Defense",
    "DOD": "Department of Defense", "USAF": "Air Force", "ARMY": "Army",
    "DARPA": "Defense Advanced Research Projects Agency", "DHA": "Defense Health Agency",
    "DLA": "Defense Logistics Agency", "DMEA": "Defense Microelectronics Activity",
    "DTRA": "Defense Threat Reduction Agency", "MDA": "Missile Defense Agency",
    "NGA": "National Geospatial-Intelligence Agency", "NAVY": "Navy",
    "CBD": "Office for Chemical and Biological Defense", "OSD": "Office of the Secretary of Defense",
    "SDA": "Space Development Agency", "SOCOM": "Special Operations Command", "SCO": "Strategic Capabilities Office",
    "ED": "Department of Education", "IES": "Institute of Education Sciences", "DOE": "Department of Energy",
    "ARPA-E": "ARPA-E", "HHS": "Department of Health and Human Services", "ACL": "Administration for Community Living",
    "ARPA-H": "Advanced Research Projects Agency for Health", "CDC": "Centers for Disease Control and Prevention",
    "FDA": "Food and Drug Administration", "NIH": "National Institutes of Health",
    "DHS": "Department of Homeland Security", "CWMD": "Countering Weapons of Mass Destruction",
    "DNDO": "Domestic Nuclear Detection Office", "DOI": "Department of the Interior",
    "DOT": "Department of Transportation", "EPA": "Environmental Protection Agency",
    "NASA": "National Aeronautics and Space Administration", "NSF": "National Science Foundation",
    "NRC": "Nuclear Regulatory Commission",
}


CACHE = {}  # url -> page, so a rerun in the same process doesn't refetch


def get(url):
    if url in CACHE:
        return CACHE[url]
    time.sleep(1.1)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        CACHE[url] = r.read().decode("utf-8", "replace")
    return CACHE[url]


def text_of(page):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    t = H.unescape(re.sub(r"<[^>]+>", "\n", t))
    return [x.strip() for x in t.split("\n") if x.strip()]


def after(lines, label):
    """The line after `label`, or None if that line is itself a label (the page leaves empty values out)."""
    for i, x in enumerate(lines):
        if x == label:
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            return None if re.fullmatch(r"[A-Za-z ]+:", nxt) else nxt
    return None


def parse_award(page):
    L = text_of(page)
    i = L.index("Back to Award Search") if "Back to Award Search" in L else 0
    L = L[i:]
    d = {"title": L[1] if len(L) > 1 else None}
    j = L.index("Awardee") if "Awardee" in L else None
    if j is not None:
        d["company"] = L[j + 1]
        k = L.index("Award Year:")
        d["address"] = " | ".join(L[j + 2:k])
    for lab, key in [("Award Year:", "award_year"), ("UEI:", "uei"), ("HUBZone Owned:", "hubzone"),
                     ("Woman Owned:", "woman"), ("Socially and Economically Disadvantaged:", "sed"),
                     ("Contract Number:", "contract"), ("Agency Tracking Number:", "tracking"),
                     ("Solicitation Topic Code:", "topic"), ("Solicitation Number:", "solicitation"),
                     ("Total Award Amount:", "amount")]:
        d[key] = after(L, lab)
    t = L.index("Tagged as:") if "Tagged as:" in L else None
    if t is not None:
        d["program"], d["phase"] = L[t + 1], L[t + 2]
    a = L.index("Awarding Agency") if "Awarding Agency" in L else None
    if a is not None:
        d["agency"] = AGENCY_CODES.get(L[a + 1], L[a + 1])
        b = L[a + 2].replace("Branch:", "").strip() if L[a + 2].startswith("Branch:") else ""
        d["branch"] = AGENCY_CODES.get(b, b)
    if "Abstract" in L and "Award Schedule" in L:
        d["abstract"] = " ".join(L[L.index("Abstract") + 1:L.index("Award Schedule")])
    if "Award Schedule" in L:
        s = L[L.index("Award Schedule") + 1:L.index("Principal Investigator") if "Principal Investigator" in L else None]
        labels = {"Solicitation Year", "Award Year", "Award Start Date", "Award End Date"}
        # each value comes before its label; a missing value means two labels in a row
        pairs = {x: (s[k - 1] if k > 0 and s[k - 1] not in labels else None) for k, x in enumerate(s) if x in labels}
        d["solicitation_year"] = pairs.get("Solicitation Year")
        d["start"] = pairs.get("Award Start Date")
        d["end"] = pairs.get("Award End Date")
    if "Principal Investigator" in L:
        d["pi_name"] = after(L[L.index("Principal Investigator"):], "Name:")
    if "Business Contact" in L:
        d["contact_name"] = after(L[L.index("Business Contact"):], "Name:")
    if "Research Institution" in L:
        d["ri_name"] = after(L[L.index("Research Institution"):], "Name:")
    return d


def ws(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return "" if s in ("N/A", "$") else s


def money(x):
    return f"${x:,.0f}" if pd.notna(x) else ""


def longdate(d):
    return d.strftime("%B %-d, %Y") if pd.notna(d) and d is not None else None


def yn(v):
    return {"Y": "Yes", "N": "No", "U": "Unknown"}.get(v, v)


def find_page(row):
    words = re.sub(r"[^A-Za-z0-9 ]", " ", row.award_title).split()
    kw = ""
    for w in words:
        if len(kw) + len(w) + 1 > 45:
            break
        kw = (kw + " " + w).strip()
    co = re.sub(r"[^A-Za-z0-9 &]", " ", row.company)[:40].strip()
    tried = []
    for params in ({"company_name": co, "keywords": kw}, {"keywords": kw}, {"company_name": co}):
        url = BASE + "/awards?" + urllib.parse.urlencode(params)
        ids = list(dict.fromkeys(re.findall(r'href="/awards/(\d+)"', get(url))))
        for aid in ids[:10]:
            if aid in tried:
                continue
            tried.append(aid)
            p = parse_award(get(f"{BASE}/awards/{aid}"))
            if (ws(p.get("contract")) == ws(row.contract) and ws(p.get("tracking")) == ws(row.agency_tracking_number)
                    and ws(p.get("award_year")) == str(row.award_year)
                    and ws(p.get("amount")).replace("$", "").replace(",", "") ==
                    (f"{row.award_amount:.0f}" if pd.notna(row.award_amount) else "")):
                return aid, p, url
            if len(tried) >= 12:
                return None, None, url
    return None, None, url


def compare(row, p):
    """(field, ours, sbir.gov page, same?)"""
    st = STATES.get(row.state, row.state)
    out = [
        ("title", ws(row.award_title), ws(p.get("title"))),
        ("company", ws(row.company), ws(p.get("company"))),
        ("city, state, zip", f"{row.city}, {st}, {row.zip}".upper(), None),
        ("award year", str(row.award_year), ws(p.get("award_year"))),
        ("UEI", row.uei, ws(p.get("uei"))),
        ("HUBZone", yn(row.hubzone_owned), ws(p.get("hubzone"))),
        ("woman owned", yn(row.woman_owned), ws(p.get("woman"))),
        ("socially/economically disadvantaged", yn(row.socially_economically_disadvantaged), ws(p.get("sed"))),
        ("program", row.program, ws(p.get("program"))),
        ("phase", row.phase, ws(p.get("phase"))),
        ("agency / branch", f"{row.agency} / {row.branch}", f"{ws(p.get('agency'))} / {ws(p.get('branch'))}"),
        ("amount", money(row.award_amount), ws(p.get("amount"))),
        ("contract", row.contract, ws(p.get("contract"))),
        ("tracking number", row.agency_tracking_number, ws(p.get("tracking"))),
        ("topic code", row.topic_code, ws(p.get("topic"))),
        ("solicitation number", row.solicitation_number, ws(p.get("solicitation"))),
        ("solicitation year", "" if pd.isna(row.solicitation_year) else str(row.solicitation_year),
         ws(p.get("solicitation_year"))),
        ("start (proposal_award_date)", longdate(row.proposal_award_date) or "", ws(p.get("start"))),
        ("end (contract_end_date)", longdate(row.contract_end_date) or "", ws(p.get("end"))),
        ("PI name", ws(row.pi_name), ws(p.get("pi_name"))),
        ("abstract (first 80 chars)", ws(row.abstract)[:80], ws(p.get("abstract"))[:80] if row.abstract else "(not compared: blank here)"),
    ]
    addr = ws(p.get("address")).upper()
    res = []
    for f, a, b in out:
        if f == "city, state, zip":
            b = addr
            same = ws(f"{row.city}, {st}, {row.zip}").upper() in addr
        elif f.startswith("abstract") and not row.abstract:
            same = None
        else:
            same = ws(a).upper() == ws(b).upper()
        res.append((f, a, b, same))
    return res


def main():
    n, seed = int(sys.argv[1]), int(sys.argv[2])
    df = pd.read_parquet("out/awards.parquet")
    st = pd.read_csv("checks/states.csv", dtype=str)
    STATES.update(dict(zip(st.name, st.code)))
    picks = [(i, "random") for i in df.sample(n, random_state=seed).index]
    amt = df.award_amount
    edge = {
        "largest amount": amt.idxmax(),
        "oldest: earliest proposal_award_date": df.proposal_award_date.dropna().sort_values().index[0],
        "oldest award year (1983), first in file": df.index[df.award_year == df.award_year.min()][0],
        "newest: latest proposal_award_date": df.proposal_award_date.dropna().sort_values().index[-1],
        "newest award year, first in file": df.index[df.award_year == df.award_year.max()][0],
        "missing UEI (has DUNS)": df[(df.uei == "") & (df.duns != "")].sample(1, random_state=seed).index[0],
        "missing UEI and DUNS": df[(df.uei == "") & (df.duns == "")].sample(1, random_state=seed).index[0],
        "blank amount": df[amt.isna()].index[0],
        "zero amount": df[amt == 0].sample(1, random_state=seed).index[0],
    }
    ex = df[df.exact_duplicate].sort_values(["company", "record_id"]).index[:2]
    edge["exact duplicate (1 of a pair)"], edge["exact duplicate (2 of a pair)"] = ex[0], ex[1]
    pd_rows = df[(df.possible_duplicate_count == 2) & ~df.exact_duplicate]
    g = pd_rows.sample(1, random_state=seed)
    key = ["agency", "company", "phase", "award_year", "award_title", "award_amount"]
    pair = pd_rows.merge(g[key], on=key, how="inner")
    pair_idx = df.index[df.record_id.isin(pair.record_id)]
    edge["possible duplicate (1 of a pair)"], edge["possible duplicate (2 of a pair)"] = pair_idx[0], pair_idx[1]
    picks += [(i, k) for k, i in edge.items()]

    day = dt.date.today().isoformat()
    lines = [f"# Field-by-field sample, {day}", "",
             f"Rows from `out/awards.parquet` (built from SBIR.gov's file last modified Sun, 01 Nov 2026) compared "
             f"with each award's page on www.sbir.gov, read {day}. {n} random rows (pandas `sample`, seed {seed}) "
             f"and {len(edge)} edge cases. Pages were found with SBIR.gov's award search; the search URL is listed "
             "for each. A row counts as found only when the page shows the same contract number, tracking number, "
             "award year and amount.", "",
             "Dates on the page are shown as SBIR.gov writes them; ours are converted to the same form. "
             "Flags: our Y/N/U shown as Yes/No/Unknown.", ""]
    summary = []
    for idx, why in picks:
        row = df.loc[idx]
        try:
            aid, p, surl = find_page(row)
        except Exception as e:  # network trouble: say so in the file, don't hide it
            aid, p, surl = None, None, f"error: {e}"
        lines += [f"## {why}: {ws(row.award_title)[:90]}", "",
                  f"record_id `{row.record_id}`, source row {idx + 2} of the CSV (header is row 1). Search: {surl}", ""]
        if not aid:
            lines += ["**No page found** with the same contract, tracking number, year and amount.", ""]
            summary.append((why, row.record_id, None, "not found", ""))
            continue
        lines += [f"Award page: {BASE}/awards/{aid}", "", "| field | ours | sbir.gov page | same |", "|---|---|---|---|"]
        res = compare(row, p)
        bad = []
        for f, a, b, same in res:
            mark = "yes" if same else ("n/a" if same is None else "**NO**")
            if same is False:
                bad.append(f)
            lines.append(f"| {f} | {str(a).replace('|', '/')} | {str(b).replace('|', '/')} | {mark} |")
        lines.append("")
        summary.append((why, row.record_id, aid, "all match" if not bad else "differs: " + ", ".join(bad), ""))
        print(why, aid, bad, flush=True)
    head = ["## Summary", "", "| case | record_id | award page | result |", "|---|---|---|---|"]
    for why, rid, aid, res, _ in summary:
        head.append(f"| {why} | `{rid}` | {BASE + '/awards/' + aid if aid else ''} | {res} |")
    head.append("")
    i = next(k for k, x in enumerate(lines) if x.startswith("## "))
    out = lines[:i] + head + lines[i:]
    with open(f"checks/sample_{day}.md", "w") as fh:
        fh.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
