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


# --- the count check's three outcomes (src/check.py) ---------------------------------------------------------

def _page(name):
    return open(os.path.join(F, name), encoding="utf-8").read()


def _ours_matching(html):
    """Counts shaped like table_counts() that agree with the page: labels shown without a number are absent."""
    f = sbir.facet_counts(html)
    return {k: (v if k == "total" else {a: n for a, n in v.items() if n is not None}) for k, v in f.items()}


def test_facets_missing_count_is_none_not_zero():
    f = sbir.facet_counts(_page("awards_page.html"))
    assert f["agency"]["Small Business Administration"] is None  # shown on 2026-11-15 with no "(n)"
    assert not sbir.shows_no_counts(f)


def test_page_with_no_counts_detected():
    # www.sbir.gov/awards on 2026-11-16: every label, no "(n)", no "Showing 1-N of N results"
    f = sbir.facet_counts(_page("awards_page_no_counts.html"))
    assert f["total"] is None
    assert sum(len(v) for k, v in f.items() if k != "total") == 150
    assert all(n is None for k, v in f.items() if k != "total" for n in v.values())
    assert sbir.shows_no_counts(f)


def test_no_counts_needs_both_total_and_labels_missing():
    assert not sbir.shows_no_counts({"total": 5, "agency": {"NASA": None}})
    assert not sbir.shows_no_counts({"total": None, "agency": {"NASA": None, "DOE": 3}})
    assert sbir.shows_no_counts({"total": None, "agency": {"NASA": None}})


def test_compare_label_without_count():
    facets = {"total": 3, "agency": {"NASA": 3, "SBA": None}}
    assert sbir.compare(facets, {"total": 3, "agency": {"NASA": 3}}, kinds=("agency",)) == []
    assert sbir.compare(facets, {"total": 4, "agency": {"NASA": 3, "SBA": 1}}, kinds=("agency",)) == [
        ("total", "", 3, 4), ("agency", "sba", None, 1)]


def test_check_no_counts_skips_upload(tmp_path):
    import check
    html = _page("awards_page_no_counts.html")
    out, issue = tmp_path / "gh_output", tmp_path / "out" / "issue.md"
    ours = {"total": 219780, "agency": {"NASA": 1}}
    assert check.run(html, ours, "2026-11-16", checks_dir=tmp_path, issue_path=str(issue),
                     github_output=str(out)) == "no_counts"  # returns: no exception, exit 0
    assert out.read_text() == "verified=false\n"
    text = issue.read_text()
    assert "2026-11-16" in text and "shows no counts" in text and "did not upload" in text
    assert "Facet labels on the page: 150" in text and "with a count: 0" in text
    assert "\"No results found\": yes" in text and "219,780 rows" in text
    assert (tmp_path / "facets_2026-11-16.json").exists()


def test_check_counts_equal_uploads(tmp_path):
    import check
    html = _page("awards_page.html")
    out = tmp_path / "gh_output"
    assert check.run(html, _ours_matching(html), "2026-11-15", checks_dir=tmp_path,
                     issue_path=str(tmp_path / "issue.md"), github_output=str(out)) == "match"
    assert out.read_text() == "verified=true\n"
    assert not (tmp_path / "issue.md").exists()


def test_check_counts_differ_fails(tmp_path):
    import check
    html = _page("awards_page.html")
    ours = _ours_matching(html)
    ours["year"]["1983"] += 1
    out = tmp_path / "gh_output"
    with pytest.raises(SystemExit) as e:
        check.run(html, ours, "2026-11-15", checks_dir=tmp_path, issue_path=str(tmp_path / "issue.md"),
                  github_output=str(out))
    assert "1 counts differ" in str(e.value)
    assert out.read_text() == "verified=false\n"
    assert not (tmp_path / "issue.md").exists()
