import os
import sys

import pandas as pd
import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, os.path.join(HERE, "..", "checks"))
import sbir  # noqa: E402

F = os.path.join(HERE, "fixtures")


@pytest.fixture(scope="module")
def built():
    cur = sbir.read_csv(os.path.join(F, "current.csv"))
    ab = sbir.read_csv(os.path.join(F, "abstracts.csv"))
    return cur, ab, *sbir.build(cur, ab)


def test_rows_kept_in_order(built):
    cur, _, df, report = built
    assert len(df) == len(cur) == report["rows"] == report["source_rows"]
    assert df.company.tolist() == cur.Company.str.strip().tolist()


def test_contact_phone_and_email_dropped(built):
    _, _, df, report = built
    assert not [c for c in df.columns if "phone" in c or "email" in c]
    assert len(report["dropped_columns"]) == 7 and "contact_name" not in df.columns


def test_exact_duplicates_flagged_not_dropped(built):
    _, _, df, report = built
    gse = df[df.company == "GSE INC"]
    assert len(gse) == 2 and gse.exact_duplicate.all()
    assert gse.record_id.str.endswith("-2").sum() == 1
    assert report["exact_duplicate_rows"] == 2
    assert df.record_id.is_unique


def test_possible_duplicates_counted(built):
    _, _, df, _ = built
    # GSE INC rows repeat exactly, so they count as possible duplicates too
    assert (df[df.company == "GSE INC"].possible_duplicate_count == 2).all()
    # Icucom: same amount, year, contract; title spelled MODELLING / Modeling. Not flagged: titles must match
    # letter for letter (case and punctuation ignored).
    ic = df[df.company == "Icucom Corp"]
    assert len(ic) == 2 and (ic.possible_duplicate_count == 1).all()


def test_types(built):
    _, _, df, _ = built
    assert str(df.award_year.dtype) == "Int64"
    assert df.award_amount.dtype == "float64"
    assert df.award_amount.isna().sum() == 1  # the blank-amount row stays blank, not 0
    first = df.iloc[0]
    assert str(first.proposal_award_date) == "2026-09-01" and first.award_amount == 189993.0


def test_abstracts_matched(built):
    _, ab, df, report = built
    assert report["abstract_nonblank"] >= 5
    row = df[df.abstract != ""].iloc[0]
    assert row.abstract in set(ab.Abstract.str.strip())
    assert df.iloc[0].abstract == ""  # a 2026 award: not in the older abstracts file


def test_amount_key_formats():
    s = pd.Series(["171,433", "171433.0000", "", "99.5"])
    assert sbir.amount_key(s).tolist() == ["171433", "171433", "", "100"]


def test_header_change_stops():
    cur = sbir.read_csv(os.path.join(F, "current.csv")).rename(columns={"UEI": "Unique Entity ID"})
    with pytest.raises(SystemExit):
        sbir.build(cur)


def test_bad_date_stops():
    cur = sbir.read_csv(os.path.join(F, "current.csv"))
    cur.loc[0, "Proposal Award Date"] = "09/01/2026"
    with pytest.raises(SystemExit):
        sbir.build(cur)


def test_facets_parse():
    html = open(os.path.join(F, "awards_page.html"), encoding="utf-8").read()
    f = sbir.facet_counts(html)
    assert f["total"] == 219780
    assert f["program"] == {"SBIR": 197888, "STTR": 21892}
    assert f["phase"] == {"Phase I": 151616, "Phase II": 68164}
    assert f["agency"]["Department of War"] == 105822
    assert f["branch"]["Air Force"] == 35612
    assert f["year"]["1983"] == 785
    assert sum(f["year"].values()) == 219780


def test_compare_ignores_case_and_reports_diffs():
    facets = {"total": 3, "agency": {"Department Of Agriculture": 2, "NASA": 1}}
    ours = {"total": 3, "agency": {"Department of Agriculture": 2, "NASA": 1}}
    assert sbir.compare(facets, ours, kinds=("agency",)) == []
    ours["agency"]["NASA"] = 0
    assert sbir.compare(facets, ours, kinds=("agency",)) == [("agency", "nasa", 1, 0)]


def test_award_page_parse():
    import sample
    p = sample.parse_award(open(os.path.join(F, "award_218508.html"), encoding="utf-8").read())
    assert p["title"] == "CRAZY TRAIN" and p["company"] == "UMBRA LAB, INC"
    assert p["amount"] == "$59,999,818" and p["contract"] == "FA2401-25-9-0013"
    assert p["phase"] == "Phase II" and p["agency"] == "Department of Defense" and p["branch"] == "Air Force"
    assert p["start"] == "September 30, 2025"
