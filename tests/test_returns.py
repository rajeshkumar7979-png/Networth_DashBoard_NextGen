"""Honest return helpers — lump-sum annualized ≠ trailing CAGR ≠ XIRR."""
from datetime import date

import pandas as pd
import pytest

from lib.returns import (
    LUMP_SUM_ANN_LABEL,
    MULTI_CASHFLOW_XIRR_GAP,
    SIMPLE_ROI_LABEL,
    holding_period_days,
    lump_sum_annualized_pct,
    rolling_cagr_pct,
    simple_roi_pct,
    trailing_cagr_pct,
)


def test_simple_roi_is_not_annualized():
    assert simple_roi_pct(110, 100) == pytest.approx(10.0)
    assert simple_roi_pct(80, 100) == pytest.approx(-20.0)
    assert simple_roi_pct(100, 0) is None
    assert simple_roi_pct(None, 100) is None


def test_lump_sum_annualized_one_year_is_the_roi():
    assert lump_sum_annualized_pct(110, 100, 365) == pytest.approx(10.014, abs=0.02)
    assert lump_sum_annualized_pct(110, 100, 29) is None  # too young
    assert lump_sum_annualized_pct(110, 100, None) is None
    assert lump_sum_annualized_pct(0, 100, 365) is None


def test_lump_sum_annualized_two_years_compounds():
    # 21% over ~2 years is about 10% a year, not 10.5%.
    got = lump_sum_annualized_pct(121, 100, 730)
    assert got == pytest.approx(10.0, abs=0.05)


def test_holding_period_days_rejects_inverted_dates():
    assert holding_period_days(date(2024, 1, 1), date(2025, 1, 1)) == 366
    assert holding_period_days(date(2025, 1, 1), date(2024, 1, 1)) is None
    assert holding_period_days(None, date(2025, 1, 1)) is None


def test_trailing_cagr_matches_command_window():
    # 100 → 121 over exactly 2 × 365.25 days.
    start = pd.Timestamp("2023-01-01")
    end = start + pd.Timedelta(days=int(2 * 365.25))
    hist = pd.DataFrame({"date": [start, end], "nav": [100.0, 121.0]})
    assert trailing_cagr_pct(hist, 2) == pytest.approx(10.0, abs=0.05)
    assert trailing_cagr_pct(hist, 5) is None  # window longer than history
    assert trailing_cagr_pct(pd.DataFrame(), 1) is None


def test_rolling_cagr_empty_when_history_is_short():
    hist = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=8, freq="D"),
        "nav": [100 + i for i in range(8)],
    })
    assert rolling_cagr_pct(hist, 1) == []


def test_rolling_cagr_returns_windows_not_zeros():
    days = pd.date_range("2020-01-01", periods=800, freq="D")
    nav = [100.0 * (1.10 ** (i / 365.25)) for i in range(800)]
    hist = pd.DataFrame({"date": days, "nav": nav})
    series = rolling_cagr_pct(hist, 1, step_days=60)
    assert series, "a year of 10% growth must produce at least one 1Y window"
    for _, cagr in series:
        assert cagr == pytest.approx(10.0, abs=0.2)


def test_labels_do_not_sell_simple_roi_as_xirr():
    assert "Not a multi-cashflow XIRR" in SIMPLE_ROI_LABEL
    assert "one buy" in LUMP_SUM_ANN_LABEL
    assert "SIPs are not invented" in LUMP_SUM_ANN_LABEL
    assert "Not in the workbook" in MULTI_CASHFLOW_XIRR_GAP
