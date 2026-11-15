"""Read SBIR.gov's bulk award files and turn them into one table.

Two files, both linked from https://www.sbir.gov/data-resources:
  CURRENT   award data without abstracts, refreshed by SBIR.gov (UEI included)
  ABSTRACTS award data with abstracts, an older export (no UEI; dates and amounts formatted differently)

The table is CURRENT, row for row. Abstracts are copied in from ABSTRACTS only where a record matches exactly one
ABSTRACTS row on agency, company, contract, tracking number, phase, award year, title and amount (letters and
digits only, case ignored). Nothing is dropped, deduplicated or corrected.
"""
import hashlib
import re

import pandas as pd

CURRENT_URL = "https://data.www.sbir.gov/mod_awarddatapublic_no_abstract/award_data_no_abstract.csv"
ABSTRACTS_URL = "https://data.www.sbir.gov/awarddatapublic/award_data.csv"
AWARDS_PAGE = "https://www.sbir.gov/awards"
UA = "sbir-awards-dataset (github.com/abigailhaddad/sbir-awards)"

# source header -> column name. Every source column must be here; build() stops on a new or missing one.
COLUMNS = {
    "Company": "company",
    "Award Title": "award_title",
    "Agency": "agency",
    "Branch": "branch",
    "Phase": "phase",
    "Program": "program",
    "Agency Tracking Number": "agency_tracking_number",
    "Contract": "contract",
    "Proposal Award Date": "proposal_award_date",
    "Contract End Date": "contract_end_date",
    "Solicitation Number": "solicitation_number",
    "Solicitation Year": "solicitation_year",
    "Solicitation Close Date": "solicitation_close_date",
    "Proposal Receipt Date": "proposal_receipt_date",
    "Date of Notification": "date_of_notification",
    "Topic Code": "topic_code",
    "Award Year": "award_year",
    "Award Amount": "award_amount",
    "UEI": "uei",
    "Duns": "duns",
    "HUBZone Owned": "hubzone_owned",
    "Socially and Economically Disadvantaged": "socially_economically_disadvantaged",
    "Woman Owned": "woman_owned",
    "Number Employees": "number_employees",
    "Company Website": "company_website",
    "Address1": "address1",
    "Address2": "address2",
    "City": "city",
    "State": "state",
    "Zip": "zip",
    "Contact Name": None,
    "Contact Title": None,
    "Contact Phone": None,
    "Contact Email": None,
    "PI Name": "pi_name",
    "PI Title": "pi_title",
    "PI Phone": None,
    "PI Email": None,
    "RI Name": "ri_name",
    "RI POC Name": "ri_poc_name",
    "RI POC Phone": None,
}
# None = left out on purpose: personal phone numbers and email addresses, and the "Contact" name and title. In a
# 2026-11-15 sample of award pages the file's Contact Name never matched the page's Business Contact (it is often
# blank or an agency office such as "NASA SBIR Support Office"), so it is not the firm's contact and would mislead.
# PI and research institution names are kept.
DROPPED = [k for k, v in COLUMNS.items() if v is None]
DATE_COLS = ["proposal_award_date", "contract_end_date", "solicitation_close_date",
             "proposal_receipt_date", "date_of_notification"]
INT_COLS = ["award_year", "solicitation_year", "number_employees"]
FLAG_COLS = ["hubzone_owned", "socially_economically_disadvantaged", "woman_owned"]
# Fields that identify a record for record_id. Contract numbers alone are not unique (NIST, NSF and others reuse
# solicitation-wide numbers), so the id hashes all of these and numbers repeats in file order.
ID_FIELDS = ["agency", "branch", "program", "phase", "company", "award_title", "contract",
             "agency_tracking_number", "award_year", "award_amount", "proposal_award_date", "uei", "duns"]


def read_csv(path_or_buf):
    """Every value as text, nothing turned into NaN, BOM removed."""
    return pd.read_csv(path_or_buf, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def norm(s):
    return s.fillna("").astype(str).str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)


def amount_key(s):
    """'171,433' and '171433.0000' -> '171433'. Blank -> ''."""
    v = pd.to_numeric(s.fillna("").astype(str).str.replace(",", "", regex=False), errors="coerce").round(0)
    return v.map(lambda x: "" if pd.isna(x) else str(int(x)))


def match_key(df, agency="Agency", company="Company", contract="Contract", tracking="Agency Tracking Number",
              phase="Phase", year="Award Year", title="Award Title", amount="Award Amount"):
    # "Phase II – Direct to Phase II" in the current file is "Phase II" in the older one.
    ph = df[phase].str.replace(r"\s*[–-]\s*Direct to Phase II$", "", regex=True)
    return (df[agency].str.replace("Department of Interior", "Department of the Interior", regex=False) + "|"
            + norm(df[company]) + "|" + norm(df[contract]) + "|" + norm(df[tracking]) + "|" + ph + "|"
            + df[year] + "|" + norm(df[title]) + "|" + amount_key(df[amount]))


def check_header(df):
    got, want = list(df.columns), list(COLUMNS)
    if got != want:
        raise SystemExit(f"STOP: SBIR.gov changed the file's columns.\n  new: {sorted(set(got) - set(want))}\n"
                         f"  gone: {sorted(set(want) - set(got))}\n  order same: {sorted(got) == sorted(want)}")


def record_ids(df):
    base = df[ID_FIELDS].astype(str).agg("\x1f".join, axis=1).map(
        lambda s: hashlib.sha1(s.encode()).hexdigest()[:12])
    n = base.groupby(base).cumcount() + 1
    return base.where(n == 1, base + "-" + n.astype(str))


def build(current, abstracts=None):
    """current, abstracts: DataFrames from read_csv. Returns (table, report dict)."""
    check_header(current)
    raw = current
    df = pd.DataFrame({new: raw[old] for old, new in COLUMNS.items() if new})
    for c in df.columns:
        df[c] = df[c].str.strip()
    report = {"source_rows": len(raw), "dropped_columns": DROPPED}

    for c in DATE_COLS:
        bad = df[c].ne("") & ~df[c].str.fullmatch(r"\d{4}-\d{2}-\d{2}")
        if bad.any():
            raise SystemExit(f"STOP: {bad.sum()} {c} values are not YYYY-MM-DD, e.g. {df.loc[bad, c].head(3).tolist()}")
    for c in INT_COLS:
        bad = df[c].ne("") & ~df[c].str.fullmatch(r"\d+")
        if bad.any():
            raise SystemExit(f"STOP: {bad.sum()} {c} values are not whole numbers, e.g. {df.loc[bad, c].head(3).tolist()}")
    bad = df.award_amount.ne("") & pd.to_numeric(df.award_amount, errors="coerce").isna()
    if bad.any():
        raise SystemExit(f"STOP: {bad.sum()} award amounts are not numbers")
    for c in FLAG_COLS:
        extra = set(df[c]) - {"Y", "N", "U", ""}
        if extra:
            raise SystemExit(f"STOP: {c} has new values {extra}")

    # duplicates: flagged, never dropped
    exact = raw.duplicated(keep=False)
    dup_key = (df.agency + "|" + norm(df.company) + "|" + df.phase + "|" + df.award_year + "|"
               + norm(df.award_title) + "|" + amount_key(df.award_amount))
    df["exact_duplicate"] = exact.values
    df["possible_duplicate_count"] = dup_key.map(dup_key.value_counts()).astype("int32").values
    report["exact_duplicate_rows"] = int(exact.sum())
    report["exact_duplicate_extra_rows"] = int(raw.duplicated().sum())
    report["possible_duplicate_rows"] = int((df.possible_duplicate_count > 1).sum())
    report["possible_duplicate_groups"] = int(dup_key[df.possible_duplicate_count > 1].nunique())

    # abstracts
    df["abstract"] = ""
    if abstracts is not None:
        ak = match_key(abstracts)
        unique = ~ak.duplicated(keep=False)
        lookup = pd.Series(abstracts.loc[unique, "Abstract"].str.strip().values, index=ak[unique].values)
        ck = match_key(raw)
        hit = ck.map(lookup)
        df["abstract"] = hit.fillna("").values
        report["abstract_file_rows"] = len(abstracts)
        report["abstract_file_max_award_year"] = int(pd.to_numeric(abstracts["Award Year"], errors="coerce").max())
        report["abstract_matched"] = int(hit.notna().sum())
        report["abstract_nonblank"] = int(df.abstract.ne("").sum())
        report["abstract_file_rows_unmatched"] = int((~ak.isin(set(ck))).sum())
        report["abstract_file_replacement_chars"] = int(abstracts["Abstract"].str.contains("�").sum())

    df.insert(0, "record_id", record_ids(df))
    assert df.record_id.is_unique

    out = df.copy()
    for c in DATE_COLS:
        out[c] = pd.to_datetime(out[c].replace("", None), format="%Y-%m-%d", errors="raise").dt.date
    for c in INT_COLS:
        out[c] = pd.to_numeric(out[c].replace("", None)).astype("Int64")
    out["award_amount"] = pd.to_numeric(out["award_amount"].replace("", None)).astype("float64")
    report["rows"] = len(out)
    return out, report


def facet_counts(html):
    """Counts SBIR.gov shows on https://www.sbir.gov/awards (unfiltered): total, and by agency, branch, phase,
    program, year, state, demographic. Returns {"total": n, "agency": {label: n}, ...}."""
    import html as h
    m = re.search(r"Showing 1-\d+ of (\d+) results", html)
    out = {"total": int(m.group(1)) if m else None}
    for m in re.finditer(r'<label[^>]*for="edit-(agency|phase|program|demographic|year|state)-[^"]*"[^>]*>(.*?)</label>',
                         html, re.S):
        kind, text = m.group(1), re.sub(r"\s+", " ", h.unescape(re.sub("<[^>]+>", "", m.group(2)))).strip()
        sub = text.startswith("⮡")
        text = text.lstrip("⮡ ").strip()
        mm = re.fullmatch(r"(.*?) \((\d+)\)", text)
        label, n = (mm.group(1), int(mm.group(2))) if mm else (text, 0)
        key = "branch" if (kind == "agency" and sub) else kind
        out.setdefault(key, {})[label] = n
    return out


def table_counts(df):
    """The same breakdowns from our table, labelled the way the facets are."""
    def vc(s):
        return {str(k): int(v) for k, v in s.value_counts().items()}
    phase = df.phase.str.replace(r"\s*[–-]\s*Direct to Phase II$", "", regex=True)
    return {"total": len(df), "agency": vc(df.agency.replace("Department of Defense", "Department of War")),
            "branch": vc(df.branch[df.branch.ne("")]), "phase": vc(phase), "program": vc(df.program),
            "year": vc(df.award_year.astype(str)), "state": vc(df.state[df.state.ne("")]),
            "demographic": {"HUBZone Owned": int((df.hubzone_owned == "Y").sum()),
                            "Woman Owned": int((df.woman_owned == "Y").sum())}}


def compare(facets, ours, kinds=("agency", "phase", "program", "year")):
    """List of (kind, label, sbir_gov, ours) where they differ. Facet labels with no count are skipped
    (SBIR.gov shows some empty agencies with no number)."""
    diffs = []
    if facets.get("total") != ours["total"]:
        diffs.append(("total", "", facets.get("total"), ours["total"]))
    for k in kinds:
        # SBIR.gov writes "Department Of Agriculture" on the site; compare labels ignoring case
        f = {a.casefold(): n for a, n in facets.get(k, {}).items()}
        o = {a.casefold(): n for a, n in ours.get(k, {}).items()}
        for label in sorted(set(f) | set(o)):
            fv, ov = f.get(label, 0), o.get(label, 0)
            if fv != ov:
                diffs.append((k, label, fv, ov))
    return diffs
