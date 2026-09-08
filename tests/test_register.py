import pandas as pd
import pytest

from lib.gold import DEBT_LIKE
from lib.register import (
    ASSET_CLASSES,
    DATA_BACKED_CLASSES,
    NO_DATA_CLASSES,
    REGISTER_COLUMNS,
    NonUniqueKeyError,
    aggregate_by_class,
    aggregate_by_member,
    assign_asset_class,
    build_asset_register,
    canonical_instrument_key,
    family_level_sum,
)
from tests.frozen_baseline import (
    FROZEN_BOOKS,
    FROZEN_MEMBER_CURRENT,
    FROZEN_MEMBER_INVESTED,
    FROZEN_ROWS,
    FROZEN_TOTALS,
)

# Canonical class current-value totals from the live Command Center capture run.
CLASS_CURRENT_GOLDEN = {
    "Equity": FROZEN_TOTALS["total_equity"],
    "Liquid": FROZEN_TOTALS["total_liquid_mf"],
    "FCNR (USD)": FROZEN_TOTALS["total_fcnr"],
    "INR FD": FROZEN_TOTALS["total_inr_fd"],
    "Gold": FROZEN_TOTALS["total_gold"],
}

# Per-class invested totals derived from the frozen capture books (pinned, since the
# frozen Invested columns are themselves golden constants as of the capture run).
CLASS_INVESTED_GOLDEN = {
    "Equity": 3633811.92,
    "Liquid": 4438182.6257,
    "FCNR (USD)": 9974895.0,
    "INR FD": 3562870.0,
    "Gold": 751431.1539,
}


@pytest.fixture(scope="session")
def frozen_books():
    return {
        "mf": pd.DataFrame(FROZEN_BOOKS["mf"]),
        "stocks": pd.DataFrame(FROZEN_BOOKS["stocks"]),
        "gold": pd.DataFrame(FROZEN_BOOKS["gold"]),
        "fd": pd.DataFrame(FROZEN_BOOKS["fd"]),
    }


@pytest.fixture(scope="session")
def register(frozen_books):
    return build_asset_register(
        frozen_books["mf"], frozen_books["stocks"], frozen_books["gold"], frozen_books["fd"]
    )


# ---------------- structure ----------------
def test_register_columns_and_no_null_members(register):
    assert list(register.columns) == REGISTER_COLUMNS
    assert not register.empty
    for col in ("Member", "Asset Class", "Instrument", "Current Value", "Invested"):
        assert register[col].notna().all(), f"{col} contains nulls"
    assert (register["Current Value"] >= 0).all()


def test_register_row_counts_by_book(register):
    source_map = {"mf": "MF", "stocks": "Stocks", "gold": "Gold", "fd": "FD"}
    for source, count in FROZEN_ROWS.items():
        if source == "register_total":
            assert len(register) == count
        else:
            assert len(register[register["Source"] == source_map[source]]) == count


def test_register_appears_in_every_data_backed_class(register):
    assert set(ASSET_CLASSES) == set(DATA_BACKED_CLASSES)
    assert set(register["Asset Class"]) == set(ASSET_CLASSES)


def test_register_members_are_raw_strings(register):
    assert set(register["Member"]) == set(FROZEN_MEMBER_CURRENT.keys())
    assert FROZEN_MEMBER_CURRENT.keys() == {
        "Mr. Janak Khandelwal", "Mr. RAJESH KUMAR", "Mrs. KAVITA KHANDELWAL", "Mr. SATYANARAYAN SHARMA",
    }


# ---------------- frozen current-value goldens (reconcile to Command Center ≤ ₹1) ----------------
def test_register_current_total_reconciles(register):
    total = family_level_sum(register)["total_assets"]
    assert abs(total - FROZEN_TOTALS["total_networth"]) < 1.0


def test_class_current_totals_reconcile_to_command_center(register):
    by_class = {r["Asset Class"]: r["Current Value"] for _, r in aggregate_by_class(register).iterrows()}
    for cls, golden in CLASS_CURRENT_GOLDEN.items():
        assert abs(by_class[cls] - golden) < 1.0, f"{cls}: {by_class[cls]} vs {golden}"
    total = sum(by_class[c] for c in DATA_BACKED_CLASSES)
    assert abs(total - FROZEN_TOTALS["total_networth"]) < 1.0


def test_class_current_equals_slice_definitions(frozen_books, register):
    mf, st, go, fd = frozen_books["mf"], frozen_books["stocks"], frozen_books["gold"], frozen_books["fd"]
    by_class = {r["Asset Class"]: r["Current Value"] for _, r in aggregate_by_class(register).iterrows()}
    liq_mask = mf["Category"].isin(DEBT_LIKE)
    assert abs(by_class["Equity"] - (mf.loc[~liq_mask, "Current Value"].sum() + st["Current Value"].sum())) < 1.0
    assert abs(by_class["Liquid"] - mf.loc[liq_mask, "Current Value"].sum()) < 1.0
    assert abs(by_class["FCNR (USD)"] - fd.loc[fd["Product"] == "FCNR", "Current Value (INR)"].sum()) < 1.0
    assert abs(by_class["INR FD"] - fd.loc[fd["Product"] != "FCNR", "Current Value (INR)"].sum()) < 1.0
    assert abs(by_class["Gold"] - go["Current Value"].sum()) < 1.0


def test_member_current_totals_reconcile_to_command_center(register):
    by_member = {r["Member"]: r["Current Value"] for _, r in aggregate_by_member(register).iterrows()}
    assert by_member.keys() == FROZEN_MEMBER_CURRENT.keys()
    for member, golden in FROZEN_MEMBER_CURRENT.items():
        assert abs(by_member[member] - golden) < 1.0, f"{member}: {by_member[member]} vs {golden}"
    member_sum = sum(by_member.values())
    assert abs(member_sum - FROZEN_TOTALS["total_networth"]) < 1.0


# ---------------- invested goldens ----------------
def test_register_invested_total_reconciles(register):
    assert abs(family_level_sum(register)["total_invested"] - FROZEN_TOTALS["total_invested"]) < 1.0


def test_class_invested_totals_are_frozen(register):
    by_class = {r["Asset Class"]: r["Invested"] for _, r in aggregate_by_class(register).iterrows()}
    for cls, golden in CLASS_INVESTED_GOLDEN.items():
        assert abs(by_class[cls] - golden) < 0.01, f"{cls}: {by_class[cls]} vs {golden}"
    total = sum(by_class[c] for c in DATA_BACKED_CLASSES)
    assert abs(total - FROZEN_TOTALS["total_invested"]) < 1.0


def test_fd_invested_reconciles_to_deposit_cost_basis(register):
    fd_rows = register[register["Source"] == "FD"]
    assert abs(fd_rows["Invested"].sum() - FROZEN_TOTALS["total_fd_invested"]) < 1.0


def test_member_invested_totals_reconcile(register):
    by_member = {r["Member"]: r["Invested"] for _, r in aggregate_by_member(register).iterrows()}
    assert by_member.keys() == FROZEN_MEMBER_INVESTED.keys()
    for member, golden in FROZEN_MEMBER_INVESTED.items():
        assert abs(by_member[member] - golden) < 1.0, f"{member}: {by_member[member]} vs {golden}"


# ---------------- no-data classes ----------------
def test_no_data_classes_flagged_and_never_numeric(register):
    by_class = aggregate_by_class(register)
    no_data = by_class[by_class["Asset Class"].isin(NO_DATA_CLASSES)]
    assert len(no_data) == len(NO_DATA_CLASSES)
    assert not no_data["Data Backed"].any()
    assert no_data["Current Value"].isna().all()
    assert no_data["Invested"].isna().all()
    family = family_level_sum(register)
    assert set(family["by_class"].keys()) == set(DATA_BACKED_CLASSES)
    for cls in NO_DATA_CLASSES:
        assert cls not in family["by_class"]


# ---------------- canonical keys / FD collision safety ----------------
def test_register_canonical_records_unique(register):
    dup = register.duplicated(subset=["Member", "Asset Class", "Instrument"])
    assert not dup.any(), f"collapsed records: {register[dup][['Member', 'Asset Class', 'Instrument']]}"


def test_workbook_fd_keys_all_account_backed_and_unique(register):
    fd_rows = register[register["Source"] == "FD"]
    assert len(fd_rows) == 23
    assert fd_rows["Instrument"].str.startswith("acct:").all()
    assert fd_rows["Instrument"].is_unique
    assert fd_rows["Member"].nunique() == 3  # KAVITA, SHARMA, RAJESH


def test_distinct_accounts_never_collapse_regardless_of_fingerprint():
    # Mirrors the real workbook: ABC162/164/166 are 3 separate USD deposits with
    # identical fingerprint (holder/ccy/product/principal/ROI/maturity) but distinct
    # account numbers. Three cross-check rows must survive as 3 register records.
    cols = ["Holder Name", "Account Number", "Currency", "Product", "Principal (Native)",
            "ROI %", "Maturity Date", "Principal (INR, at deposit FX)", "Current Value (INR)"]
    rows = [
        ["Mr. RAJESH KUMAR", "ABC162", "USD", "FCNR", 7000.0, 6.25, "2029-08-01", 667730.0, 666157.0],
        ["Mr. RAJESH KUMAR", "ABC164", "USD", "FCNR", 7000.0, 6.25, "2029-08-01", 667730.0, 666157.0],
        ["Mr. RAJESH KUMAR", "ABC166", "USD", "FCNR", 7000.0, 6.25, "2029-08-01", 667730.0, 666157.0],
    ]
    fd = pd.DataFrame(rows, columns=cols)
    register = build_asset_register(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), fd)
    assert len(register[register["Source"] == "FD"]) == 3
    assert register["Instrument"].is_unique


def test_fd_fallback_collision_raises_non_unique_key_error():
    cols = ["Holder Name", "Account Number", "Currency", "Product", "Principal (Native)",
            "ROI %", "Maturity Date", "Principal (INR, at deposit FX)", "Current Value (INR)"]
    rows = [
        ["Mr. RAJESH KUMAR", "", "USD", "FCNR", 7000.0, 6.25, "2029-08-01", 667730.0, 666157.0],
        ["Mr. RAJESH KUMAR", None, "USD", "FCNR", 7000.0, 6.25, "2029-08-01", 667730.0, 666200.0],
    ]
    fd = pd.DataFrame(rows, columns=cols)
    with pytest.raises(NonUniqueKeyError):
        build_asset_register(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), fd)


def test_fd_missing_account_accepts_unique_fallback():
    cols = ["Holder Name", "Account Number", "Currency", "Product", "Principal (Native)",
            "ROI %", "Maturity Date", "Principal (INR, at deposit FX)", "Current Value (INR)"]
    rows = [
        ["Mr. RAJESH KUMAR", "nan", "USD", "FCNR", 7000.0, 6.25, "2029-08-01", 667730.0, 666157.0],
        ["Mr. RAJESH KUMAR", "nat", "USD", "FCNR", 9000.0, 6.25, "2029-08-01", 858610.0, 858000.0],
    ]
    fd = pd.DataFrame(rows, columns=cols)
    register = build_asset_register(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), fd)
    fd_rows = register[register["Source"] == "FD"]
    assert len(fd_rows) == 2
    assert fd_rows["Instrument"].is_unique
    assert fd_rows["Instrument"].str.startswith("fp:").all()


# ---------------- pure classification helpers ----------------
def test_assign_asset_class_by_kind():
    assert assign_asset_class("MF", {"Category": "Liquid"}) == "Liquid"
    assert assign_asset_class("MF", {"Category": "Mid Cap"}) == "Equity"
    assert assign_asset_class("MF", {"Category": "Flexi Cap"}) == "Equity"
    assert assign_asset_class("MF", {}) == "Equity"  # unknown category -> equity default
    assert assign_asset_class("Stocks", {}) == "Equity"
    assert assign_asset_class("Gold", {}) == "Gold"
    assert assign_asset_class("FD", {"Product": "FCNR"}) == "FCNR (USD)"
    assert assign_asset_class("FD", {"Product": "INR FD"}) == "INR FD"
    assert assign_asset_class("FD", {"Currency": "USD"}) == "FCNR (USD)"
    assert assign_asset_class("FD", {"Currency": "INR"}) == "INR FD"
    assert assign_asset_class("FD", {"Currency": None}) == "INR FD"
    with pytest.raises(ValueError):
        assign_asset_class("Bogus", {})


def test_canonical_instrument_key_by_kind():
    assert canonical_instrument_key("MF", {"ISIN": "INF123"}) == "INF123"
    assert canonical_instrument_key("Stocks", {"Symbol": "SBIN"}) == "SBIN"
    assert canonical_instrument_key("Gold", {"Symbol": "GOLDBEES"}) == "GOLDBEES"
    assert canonical_instrument_key("FD", {"Account Number": "ABC1", "Holder Name": "X"}) == "acct:ABC1"
    assert canonical_instrument_key("FD", {"Account Number": "nan", "Holder Name": "X",
                                           "Currency": "INR", "Product": "INR FD",
                                           "Principal (Native)": 1000.0, "ROI %": 6.5,
                                           "Maturity Date": "2027-01-01"}).startswith("fp:")
    with pytest.raises(ValueError):
        canonical_instrument_key("Bogus", {})