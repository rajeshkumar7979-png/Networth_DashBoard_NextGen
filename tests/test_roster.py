# -------------------------------------------------
# lib/roster — drill-down roster built over the frozen Phase 1A books.
# The roster is a pure view over book rows: totals must reconcile to the
# register baseline and lookups must be exact-identifier only.
# -------------------------------------------------
import pandas as pd

from lib.roster import build_roster, lookup_roster, instrument_summary, member_filter_options

from tests.frozen_baseline import FROZEN_BOOKS, FROZEN_TOTALS


def _books():
    return {
        "mf_valid": pd.DataFrame(FROZEN_BOOKS["mf"]),
        "stocks_valid": pd.DataFrame(FROZEN_BOOKS["stocks"]),
        "gold_valid": pd.DataFrame(FROZEN_BOOKS["gold"]),
        "fd_valid": pd.DataFrame(FROZEN_BOOKS["fd"]),
    }


def test_roster_row_count_matches_frozen_books():
    roster = build_roster(**_books())
    expected = sum(len(FROZEN_BOOKS[k]) for k in ("mf", "stocks", "gold", "fd"))
    assert len(roster) == expected


def test_roster_reconciles_to_register_totals():
    roster = build_roster(**_books())
    assert len(roster) > 0
    assert abs(roster["Current Value"].sum() - FROZEN_TOTALS["total_networth"]) < 1.0
    assert abs(roster["Invested"].sum() - FROZEN_TOTALS["total_invested"]) < 1.0


def test_roster_pnl_and_return_are_calculated_facts():
    roster = build_roster(**_books())
    for _, row in roster.iterrows():
        assert abs((row["P&L"] - (row["Current Value"] - row["Invested"]))) < 1e-6
        if row["Invested"]:
            assert abs(row["Return %"] - row["P&L"] / row["Invested"] * 100.0) < 1e-6


def test_roster_uses_register_canonical_keys():
    roster = build_roster(**_books())
    fd_rows = roster[roster["Kind"] == "FD"]
    assert len(fd_rows) == len(FROZEN_BOOKS["fd"])
    assert fd_rows["Key"].str.startswith("acct:").all()
    assert fd_rows["Key"].is_unique


def test_roster_class_assignment_matches_register_taxonomy():
    roster = build_roster(**_books())
    assert set(roster["Class"].unique()) <= {
        "Equity", "Liquid", "FCNR (USD)", "INR FD", "Gold"}
    gold = roster[roster["Kind"] == "Gold"]
    assert (gold["Class"] == "Gold").all()
    fd = roster[roster["Kind"] == "FD"]
    assert (fd["Class"].isin(["FCNR (USD)", "INR FD"])).all()


def test_lookup_exact_symbol_returns_all_members():
    roster = build_roster(**_books())
    matches = lookup_roster(roster, "JIOFIN")
    assert len(matches) >= 1
    assert set(matches["Name"]) == {"JIOFIN"}
    assert set(matches["Kind"]) == {"Stocks"}


def test_lookup_case_insensitive_exact_only():
    roster = build_roster(**_books())
    assert len(lookup_roster(roster, "hdfcbank")) == 1
    assert len(lookup_roster(roster, "HDFCBAN")) == 0
    assert len(lookup_roster(roster, "INF179K01XQ")) == 0


def test_lookup_by_isin_and_fund_name():
    roster = build_roster(**_books())
    isin_matches = lookup_roster(roster, "INF179K01XQ0")
    assert len(isin_matches) == 1
    assert isin_matches["Kind"].iloc[0] == "MF"
    name_matches = lookup_roster(roster, "SBI CONTRA DIRECT PLAN GROWTH")
    assert len(name_matches) == 1
    assert name_matches["Kind"].iloc[0] == "MF"


def test_lookup_empty_on_missing_symbol_and_never_fuzzy():
    roster = build_roster(**_books())
    assert len(lookup_roster(roster, "RELIANCE")) == 0
    assert len(lookup_roster(roster, "")) == 0
    assert len(lookup_roster(roster, None)) == 0


def test_roster_handles_empty_books():
    empty = pd.DataFrame(columns=["Key", "Name", "Kind", "Class", "Member",
                                  "Current Value", "Invested", "P&L",
                                  "Return %", "Maturity", "Match Terms"])
    roster = build_roster()
    assert roster is not None and len(roster) == 0
    assert "Maturity" in roster.columns
    assert lookup_roster(empty, "X") is not None
    assert len(lookup_roster(empty, "X")) == 0


def test_instrument_summary_never_invents():
    roster = build_roster(**_books())
    row = roster.iloc[0]
    summary = instrument_summary(row)
    assert summary["Key"] == row["Key"]
    assert summary["Return %"] in ("0.00%", "n/a") or summary["Return %"].endswith("%")


def test_member_filter_options_excludes_non_name_tokens():
    """Regression: the workbook's FD 'Holder Name' column carries non-name
    tokens (numeric principal strings) that must never surface in the member
    filter — they are not family members."""
    roster = pd.DataFrame({
        "Member": ["Mrs. KAVITA KHANDELWAL", "Mr. RAJESH KUMAR", "3562870",
                   "4203971", "475000", None, pd.NaT, "NaT", ""],
    })
    opts = member_filter_options(roster)
    assert opts == ["Mr. RAJESH KUMAR", "Mrs. KAVITA KHANDELWAL"]
    assert all(any(c.isalpha() for c in m) for m in opts)


def test_member_filter_options_on_frozen_books_is_clean_and_sorted():
    roster = build_roster(**_books())
    opts = member_filter_options(roster)
    assert opts == sorted(opts)
    assert set(opts) <= {"Mr. RAJESH KUMAR", "Mrs. KAVITA KHANDELWAL",
                         "Mr. SATYANARAYAN SHARMA", "Mr. Janak Khandelwal"}
    assert set(opts), "filter must not be empty on the frozen books"


def test_member_filter_options_handles_empty_inputs():
    assert member_filter_options(None) == []
    assert member_filter_options(pd.DataFrame(columns=["Member"])) == []


def test_fd_roster_names_are_product_holder_account_never_blank():
    """Workbook FD has no Symbol column. Names must be Product · Holder · Account
    so the dossier selector is never a blank ' · FD'."""
    roster = build_roster(**_books())
    fd = roster[roster["Kind"] == "FD"]
    assert len(fd) == len(FROZEN_BOOKS["fd"])
    names = fd["Name"].astype(str).str.strip()
    assert (names != "").all()
    assert (~names.isin(["—", "-", "FD", "nan", "None"])).all()
    abc = fd[fd["Key"] == "acct:ABC123"]
    assert len(abc) == 1
    assert abc["Name"].iloc[0] == "INR FD · Mrs. KAVITA KHANDELWAL · ABC123"
    fcnr = fd[fd["Key"] == "acct:ABC136"]
    assert len(fcnr) == 1
    assert fcnr["Name"].iloc[0] == "FCNR (USD) · Mr. RAJESH KUMAR · ABC136"


def test_fd_roster_carries_maturity_date_from_the_book():
    roster = build_roster(**_books())
    abc = roster[roster["Key"] == "acct:ABC123"].iloc[0]
    assert str(abc["Maturity"]).startswith("2027-01-16")