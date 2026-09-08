# -------------------------------------------------
# Portfolio Intelligence foundation — exposure facts tests.
# Deterministic; rebuilds the register from the FROZEN_BOOKS capture (same
# approach as test_register) and pins the intelligence exposure/concentration
# output. Also covers the through-fund look-through with a synthetic holdings
# cache: weights are derived from disclosed market values exactly like
# lib.mf_health.get_holdings_for_funds, and uncovered funds are flagged, never
# zeroed.
# -------------------------------------------------
import datetime

import pandas as pd
import pytest

from lib.intelligence.exposure import (
    build_exposure_facts,
    load_holdings_cache,
    underlying_df,
)
from lib.register import build_asset_register
from tests.frozen_baseline import FROZEN_BOOKS, FROZEN_TOTALS

NOW = datetime.datetime.fromisoformat("2026-09-08T13:38:00")


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


@pytest.fixture(scope="session")
def facts(frozen_books, register):
    return build_exposure_facts(
        register=register,
        mf_valid=frozen_books["mf"],
        stocks_valid=frozen_books["stocks"],
        gold_valid=frozen_books["gold"],
        fd_valid=frozen_books["fd"],
        amfi_codes={},
        holdings_by_scheme={},
        now=NOW,
    )


def fact_by_id(facts, fid):
    for f in facts.all_facts():
        if f.id == fid:
            return f
    return None


# ---------------- totals reconcile to the frozen Command Center baseline ----------------
def test_total_assets_reconcile_to_frozen_baseline(facts):
    assert abs(facts.total_assets - FROZEN_TOTALS["total_networth"]) < 1.0
    assert abs(facts.total_invested - FROZEN_TOTALS["total_invested"]) < 1.0
    assert abs(facts.total_pnl - FROZEN_TOTALS["total_pnl"]) < 1.0


def test_class_facts_cover_the_five_classes(facts):
    classes = {f.entity for f in facts.class_facts if f.metric == "current_inr"}
    assert classes == {"Equity", "Liquid", "FCNR (USD)", "INR FD", "Gold"}


def test_class_shares_sum_to_100(facts):
    shares = [f.value for f in facts.class_facts if f.metric == "share_pct"]
    assert sum(shares) == pytest.approx(100.0, abs=0.6)


def test_instrument_facts_count(facts, register):
    # 3 metrics per register row (current/invested/pnl)
    assert len(facts.instrument_facts) == len(register) * 3


def test_member_facts_present(facts):
    members = {f.entity for f in facts.member_facts}
    assert members == {"Mr. Janak Khandelwal", "Mr. RAJESH KUMAR",
                        "Mrs. KAVITA KHANDELWAL", "Mr. SATYANARAYAN SHARMA"}


# ---------------- fact-kind / provenance contract ----------------
def test_calculated_fact_kinds(facts):
    assert {f.kind.value for f in facts.all_facts()} == {"CALCULATED FACT"}


def test_derived_pnl_facts_are_labeled_not_cashflow(facts):
    pnl_facts = [f for f in facts.instrument_facts if f.metric == "pnl_inr"]
    assert pnl_facts
    assert all("NOT a cash-flow" in (f.provenance.reference or "") for f in pnl_facts)


def test_fact_ids_are_unique_and_deterministic(facts):
    ids = [f.id for f in facts.all_facts()]
    assert len(ids) == len(set(ids))
    second = build_exposure_facts(
        register=pd.DataFrame(),
        now=NOW,
    )
    assert second.all_facts() == ()
    assert {f.id for f in facts.all_facts()} == {f.id for f in facts.all_facts()}


# ---------------- coverage: no disclosures => flagged, never zeroed ----------------
def test_coverage_with_no_disclosures(facts):
    assert facts.coverage.coverage_pct is None
    assert facts.coverage.covered_funds == 0
    assert facts.coverage.covered_value == 0.0
    assert not facts.underlying
    assert not facts.underlying_facts


def test_coverage_missing_names_only_mf(facts, frozen_books):
    assert len(facts.coverage.missing_names) == frozen_books["mf"]["ISIN"].nunique()


# ---------------- through-fund look-through with synthetic disclosures ----------------
def test_look_through_derives_weights_and_flags_uncovered():
    mf = pd.DataFrame([
        {"Owner": "X", "Fund Name": "Fund One", "ISIN": "ISO1", "Current Value": 5000.0,
         "Invested": 4000.0, "Category": "Mid Cap"},
        {"Owner": "X", "Fund Name": "Fund Two", "ISIN": "ISO2", "Current Value": 5000.0,
         "Invested": 4000.0, "Category": "Liquid"},
    ])
    register = build_asset_register(mf, pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    amfi_codes = {"ISO1": "999999"}
    holdings_by_scheme = {
        "999999": [
            {"name": "Security A", "isin": "INA", "market_value": 40.0},
            {"name": "Security B", "isin": "INB", "market_value": 60.0},
        ]
    }
    facts = build_exposure_facts(
        register=register, mf_valid=mf,
        amfi_codes=amfi_codes, holdings_by_scheme=holdings_by_scheme,
        now=NOW,
    )
    # Funds total 10_000; covered 5_000/5_000 -> coverage 50%
    assert facts.coverage.covered_value == pytest.approx(5000.0)
    assert facts.coverage.uncovered_value == pytest.approx(5000.0)
    assert facts.coverage.coverage_pct == pytest.approx(50.0)
    assert facts.coverage.missing_funds == 1
    assert facts.coverage.missing_names == ("Fund Two",)

    # A -> 40% of 5000 = 2000, B -> 60% of 5000 = 3000
    a = next(u for u in facts.underlying if u.name == "Security A")
    b = next(u for u in facts.underlying if u.name == "Security B")
    assert a.value_inr == pytest.approx(2000.0)
    assert b.value_inr == pytest.approx(3000.0)
    assert a.pct_of_assets == pytest.approx(20.0)
    assert b.pct_of_assets == pytest.approx(30.0)
    assert a.weight_basis == "market_value_derived"
    assert facts.weight_basis == frozenset({"market_value_derived"})


def test_look_through_aggregates_across_funds():
    mf = pd.DataFrame([
        {"Owner": "X", "Fund Name": "Fund One", "ISIN": "ISO1", "Current Value": 5000.0,
         "Invested": 4000.0, "Category": "Mid Cap"},
        {"Owner": "Y", "Fund Name": "Fund Three", "ISIN": "ISO3", "Current Value": 5000.0,
         "Invested": 4000.0, "Category": "Mid Cap"},
    ])
    register = build_asset_register(mf, pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    amfi_codes = {"ISO1": "S1", "ISO3": "S3"}
    holdings_by_scheme = {
        "S1": [{"name": "Security A", "isin": "INA", "weight_pct": 80.0},
               {"name": "Security Z", "isin": "INZ", "weight_pct": 20.0}],
        "S3": [{"name": "Security A", "isin": "INA", "weight_pct": 100.0}],
    }
    facts = build_exposure_facts(
        register=register, mf_valid=mf,
        amfi_codes=amfi_codes, holdings_by_scheme=holdings_by_scheme,
        now=NOW,
    )
    a = next(u for u in facts.underlying if u.name == "Security A")
    assert a.value_inr == pytest.approx(4000.0 + 5000.0)  # held by both funds
    assert a.schemes == ("S1", "S3")
    assert facts.weight_basis == frozenset({"weight_pct"})


def test_missing_scheme_code_counts_as_uncovered():
    mf = pd.DataFrame([
        {"Owner": "X", "Fund Name": "Fund One", "ISIN": "ISO1", "Current Value": 5000.0,
         "Invested": 4000.0, "Category": "Mid Cap"},
    ])
    register = build_asset_register(mf, pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    facts = build_exposure_facts(
        register=register, mf_valid=mf,
        amfi_codes={}, holdings_by_scheme={}, now=NOW,
    )
    assert facts.coverage.missing_funds == 1
    assert facts.coverage.covered_value == 0.0
    assert facts.coverage.coverage_pct is None


# ---------------- concentration measures ----------------
def test_instrument_concentration_reconcilable(facts, register):
    f = fact_by_id(facts, "concentration:cr5_instrument:pct")
    expected = register["Current Value"].nlargest(5).sum() / FROZEN_TOTALS["total_networth"] * 100
    assert f.value == pytest.approx(expected, abs=0.1)


def test_underlying_concentration_absent_without_disclosures(facts):
    assert fact_by_id(facts, "concentration:cr5_underlying:pct") is None
    assert fact_by_id(facts, "concentration:hhi_underlying") is None


def test_concentration_facts_are_pct_or_hhi(facts):
    for f in facts.concentration_facts:
        assert f.unit in ("pct", "hhi")


# ---------------- helpers ----------------
def test_underlying_df_returns_frame(facts):
    df = underlying_df(facts)
    assert list(df.columns) == ["name", "isin", "instrument_type", "value_inr",
                                "pct_of_assets", "schemes", "confidence"]


def test_load_holdings_cache_missing_file(tmp_path):
    absent = tmp_path / "never.json"
    assert load_holdings_cache(str(absent)) == {}


def test_load_holdings_cache_parses_dict(tmp_path):
    p = tmp_path / "cache.json"
    p.write_text('{"120": [{"name": "A", "market_value": 1.0}]}', encoding="utf-8")
    cache = load_holdings_cache(str(p))
    assert cache["120"][0]["name"] == "A"


def test_empty_register_yields_zero_facts():
    facts = build_exposure_facts(register=pd.DataFrame(), now=NOW)
    assert facts.total_assets == 0.0
    assert facts.all_facts() == ()
    assert not facts.class_facts