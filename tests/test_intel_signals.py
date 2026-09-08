# -------------------------------------------------
# Portfolio Intelligence foundation — signal rule tests.
# Deterministic: rules over a real ExposureFacts object built from a synthetic
# portfolio. Covers concentration breaches, equity allocation bands, FX
# unavailability gating, holdings coverage levels, matured/near FDs, and the
# persistent-underperformer rule.
# -------------------------------------------------
import datetime

import pandas as pd

from lib.intelligence.evidence import build_evidence_bag
from lib.intelligence.exposure import build_exposure_facts
from lib.intelligence.model import Signal
from lib.intelligence import signals
from lib.register import build_asset_register

NOW = datetime.datetime.fromisoformat("2026-09-08T13:38:00")


def _mk(*, equity_mf=(20000,), liquid_mf=(5000,), stocks=(5000, 5000, 5000, 5000),
        gold=(3000, 3000), fcnr=(6000, 6000), inr=(6000, 6000),
        uncovered_fund_value=0, missing_fx=False):
    """Synthetic portfolio -> (ExposureFacts, EvidenceBag).

    Every fund ISIN is ISO<n> and resolved to scheme S<n>; whether the cache has
    holdings depends on uncovered_fund_value: an extra uncovered fund is present
    exactly when uncovered_fund_value > 0.
    """
    mf_rows = []
    amfi_codes = {}
    fund_i = 0
    for v in equity_mf:
        fund_i += 1
        mf_rows.append({"Owner": "A", "Fund Name": f"Equity Fund {fund_i}",
                        "ISIN": f"ISO{fund_i}", "Current Value": v, "Invested": v * 0.8,
                        "Category": "Mid Cap"})
        amfi_codes[f"ISO{fund_i}"] = f"S{fund_i}"
    for v in liquid_mf:
        fund_i += 1
        mf_rows.append({"Owner": "A", "Fund Name": f"Liquid Fund {fund_i}",
                        "ISIN": f"ISO{fund_i}", "Current Value": v, "Invested": v * 0.99,
                        "Category": "Liquid"})
        amfi_codes[f"ISO{fund_i}"] = f"S{fund_i}"

    if uncovered_fund_value > 0:
        fund_i += 1
        mf_rows.append({"Owner": "A", "Fund Name": "Undisclosed Fund",
                        "ISIN": "ISOUX", "Current Value": uncovered_fund_value,
                        "Invested": uncovered_fund_value * 0.9, "Category": "Flexi Cap"})

    mf = pd.DataFrame(mf_rows)
    stk_rows = [{"Owner": "A", "Symbol": f"STK{i}", "Current Value": v, "Invested": v * 0.7}
                for i, v in enumerate(stocks, start=1)]
    stocks_df = pd.DataFrame(stk_rows)
    gold_df = pd.DataFrame([{"Owner": "A", "Symbol": f"GOLD{i}", "Current Value": v, "Invested": v * 0.8}
                            for i, v in enumerate(gold, start=1)])
    fd_rows = [
        {"Holder Name": "A", "Account Number": f"FC{i}", "Currency": "USD", "Product": "FCNR",
         "Principal (Native)": 100.0, "ROI %": 5.0, "Maturity Date": "2028-01-01",
         "Principal (INR, at deposit FX)": v, "Current Value (INR)": v}
        for i, v in enumerate(fcnr, start=1)
    ] + [
        {"Holder Name": "A", "Account Number": f"IN{i}", "Currency": "INR", "Product": "INR FD",
         "Principal (Native)": 100.0, "ROI %": 6.0, "Maturity Date": "2027-06-01",
         "Principal (INR, at deposit FX)": v, "Current Value (INR)": v}
        for i, v in enumerate(inr, start=1)
    ]
    fd_df = pd.DataFrame(fd_rows)

    register = build_asset_register(mf, stocks_df, gold_df, fd_df)

    holdings_by_scheme = {}
    if uncovered_fund_value == 0:
        # every fund is disclosed
        for i in range(1, fund_i + 1):
            holdings_by_scheme[f"S{i}"] = [
                {"name": f"Security {i}", "isin": f"INA{i}", "weight_pct": 100.0},
            ]

    facts = build_exposure_facts(
        register=register, mf_valid=mf, stocks_valid=stocks_df, gold_valid=gold_df,
        fd_valid=fd_df, amfi_codes=amfi_codes, holdings_by_scheme=holdings_by_scheme,
        now=NOW,
    )
    drivers = {"missing_fx": missing_fx, "residual_ok": True}
    evidence = build_evidence_bag(coverage=facts.coverage, drivers=drivers, now=NOW)
    return facts, evidence


def _by_rule(sigs, rule):
    return [s for s in sigs if s.rule == rule]


def test_signals_are_signal_objects():
    facts, evidence = _mk()
    sigs = signals.evaluate_signals(facts, evidence)
    assert sigs
    assert all(isinstance(s, Signal) for s in sigs)
    assert len({s.id for s in sigs}) == len(sigs)


def test_concentration_thresholds():
    facts_high, _ = _mk(equity_mf=(60000,), liquid_mf=(2000,), stocks=(2000, 2000, 2000, 2000),
                        gold=(2000, 2000), fcnr=(2000, 2000), inr=(2000, 2000))
    sigs = signals.evaluate_signals(facts_high)
    s = _by_rule(sigs, "concentration_top_instruments")[0]
    assert s.level == "warn"
    assert "concentration:cr5_instrument:pct" in s.fact_ids

    facts_mix, _ = _mk(equity_mf=(60000, 4000), liquid_mf=(4000,), stocks=(4000, 4000, 4000, 4000),
                       gold=(3000, 3000), fcnr=(4000, 4000), inr=(4000, 4000))
    sigs_mix = signals.evaluate_signals(facts_mix)
    s_mix = _by_rule(sigs_mix, "concentration_top_instruments")[0]
    assert s_mix.level in ("watch", "warn")


def test_equity_allocation_bands():
    facts_critical, _ = _mk(equity_mf=(2000,), stocks=(2000,), liquid_mf=(20000,),
                            gold=(15000, 15000), fcnr=(18000, 18000), inr=(18000, 18000))
    sigs = signals.evaluate_signals(facts_critical)
    s = _by_rule(sigs, "equity_allocation_low")[0]
    assert s.level == "critical"
    assert s.fact_ids == ("class:equity:share_pct",)

    facts_ok, _ = _mk(equity_mf=(40000, 10000), liquid_mf=(10000,), stocks=(10000, 10000, 10000, 10000),
                      gold=(6000, 6000), fcnr=(8000, 8000), inr=(8000, 8000))
    sigs_ok = signals.evaluate_signals(facts_ok)
    assert _by_rule(sigs_ok, "equity_allocation_ok")[0].level == "info"


def test_fx_signal_when_missing_fx():
    facts, evidence = _mk(missing_fx=True)
    sigs = signals.evaluate_signals(facts, evidence)
    s = _by_rule(sigs, "fx_attribution_unavailable")[0]
    assert s.level == "warn"
    assert s.evidence_ids == ("ev:drivers",)


def test_fx_signal_absent_when_rate_present():
    facts, evidence = _mk(missing_fx=False)
    sigs = signals.evaluate_signals(facts, evidence)
    assert not _by_rule(sigs, "fx_attribution_unavailable")


def test_coverage_warn_when_no_disclosures():
    facts, evidence = _mk()
    facts = _drop_holdings(facts)
    sigs = signals.evaluate_signals(facts, evidence)
    s = _by_rule(sigs, "holdings_coverage_low")[0]
    assert s.level == "warn"
    assert s.evidence_ids == ("ev:holdings_coverage",)


def test_coverage_warn_when_uncovered_fund_present():
    facts, evidence = _mk(uncovered_fund_value=100000)
    sigs = signals.evaluate_signals(facts, evidence)
    assert _by_rule(sigs, "holdings_coverage_low")[0].level == "warn"


def test_coverage_info_when_fully_disclosed():
    facts, evidence = _mk()
    sigs = signals.evaluate_signals(facts, evidence)
    assert _by_rule(sigs, "holdings_coverage_ok")[0].level == "info"


def test_overlap_signal_when_security_cross_fund():
    from dataclasses import replace
    from lib.intelligence.exposure import UnderlyingExposure

    facts, evidence = _mk()
    u = UnderlyingExposure(
        name="Security X", isin="INX", instrument_type="equity", sector=None,
        value_inr=30000.0, pct_of_assets=30.0, schemes=("S1", "S2"),
        weight_basis="weight_pct", confidence=0.9,
    )
    facts = replace(facts, underlying=(u,))
    sigs = signals.evaluate_signals(facts, evidence)
    s = _by_rule(sigs, "fund_overlap")
    assert s and s[0].level == "watch"


def test_matured_fd_signal_critical():
    facts, evidence = _mk()
    fd_rows = pd.DataFrame([
        {"Holder Name": "B", "Days to Maturity": -30.0, "Current Value (INR)": 1000000.0},
    ])
    sigs = signals.evaluate_signals(facts, evidence, fd_df=fd_rows)
    s = _by_rule(sigs, "matured_fd")[0]
    assert s.level == "critical"
    assert s.invalidation  # stated so a human can remove the signal once resolved


def test_near_maturity_fd_signal_info():
    facts, evidence = _mk()
    fd_rows = pd.DataFrame([
        {"Holder Name": "B", "Days to Maturity": 10.0, "Current Value (INR)": 500000.0},
    ])
    sigs = signals.evaluate_signals(facts, evidence, fd_df=fd_rows)
    assert _by_rule(sigs, "near_maturity_fd")[0].level == "info"


def test_underperformers_rule_uses_mf_returns():
    facts, evidence = _mk()
    mf = pd.DataFrame([
        {"Fund Name": "Bad Fund", "1Y %": 3.0, "3Y %": 4.0,
         "vs Nifty50 1Y": 12.0, "vs Nifty50 3Y": 14.0},
        {"Fund Name": "Good Fund", "1Y %": 15.0, "3Y %": 18.0,
         "vs Nifty50 1Y": 12.0, "vs Nifty50 3Y": 14.0},
    ])
    sigs = signals.evaluate_signals(facts, evidence, mf_valid=mf)
    s = _by_rule(sigs, "persistent_underperformers")
    assert s and "Bad Fund" in s[0].message
    assert s[0].level == "warn"


def test_evidence_is_optional():
    facts, _ = _mk()
    sigs = signals.evaluate_signals(facts)
    assert sigs  # runs without evidence; info signals still emitted


def _drop_holdings(facts):
    from dataclasses import replace
    from lib.intelligence.exposure import Coverage
    return replace(facts, coverage=Coverage(
        fund_value_total=25000.0, covered_value=0.0, uncovered_value=25000.0,
        covered_funds=0, missing_funds=5,
        missing_names=("Equity Fund 1", "Equity Fund 2"),
        coverage_pct=None,
    ))