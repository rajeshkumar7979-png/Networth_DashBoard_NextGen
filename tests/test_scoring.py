import pandas as pd
import pytest

from lib.scoring import (
    score_allocation,
    score_concentration,
    score_diversification,
    score_liquidity_nri,
    score_performance,
)

WEIGHTS = {"Allocation": 0.26, "Concentration": 0.20, "Liquidity": 0.20, "Diversification": 0.14, "Performance": 0.20}


def test_score_allocation():
    assert score_allocation(50) == pytest.approx(100.0)
    assert score_allocation(50, target=50) == pytest.approx(100.0)
    assert score_allocation(60, target=50) == pytest.approx(100 - 10 * 1.6)
    assert score_allocation(30, target=50) == pytest.approx(100 - 20 * 1.6)
    assert score_allocation(100) == pytest.approx(20.0)  # 100 - 50*1.6 (no floor beyond 0)
    assert score_allocation(0) == pytest.approx(20.0)
    assert 0 <= score_allocation(200, target=50) <= 100


def test_score_concentration():
    assert score_concentration(0) == 100
    assert score_concentration(35) == 100
    assert score_concentration(80) == 0
    assert score_concentration(100) == 0
    assert score_concentration(57.5) == pytest.approx(100 - (57.5 - 35) / 45 * 100)


def test_score_liquidity_nri():
    assert score_liquidity_nri(12) == 100
    assert score_liquidity_nri(35) == 100
    assert score_liquidity_nri(10) == pytest.approx(100 - (12 - 10) * 5)
    assert score_liquidity_nri(40) == pytest.approx(100 - (40 - 35) * 1.5)
    assert score_liquidity_nri(0) == pytest.approx(40.0)  # 100 - 12*5 (no floor beyond 0)
    assert score_liquidity_nri(100) == pytest.approx(2.5)  # 100 - 65*1.5


DIVERSIFIED = pd.DataFrame({
    "Category": ["Liquid", "Liquid", "Flexi Cap", "Gold", "Small Cap"],
    "Current Value": [100, 100, 200, 300, 300],
    "Fund": ["a", "b", "c", "d", "e"],
})


def test_score_diversification():
    assert 0 <= score_diversification(DIVERSIFIED) <= 100
    assert score_diversification(pd.DataFrame(columns=["Category", "Current Value"])) == 50
    zero = DIVERSIFIED.assign(**{"Current Value": 0.0})
    assert score_diversification(zero) == 50
    # A single category is undiversified (bounded towards 0).
    single = pd.DataFrame({"Category": ["Liquid"], "Current Value": [1000.0]})
    assert score_diversification(single) == pytest.approx(0.0)


PERFORMANCE = pd.DataFrame({
    "Fund": ["a", "b", "c", "d"],
    "1Y %": [5.0, 12.0, -3.0, 20.0],
    "vs Nifty50 1Y": [8.0, 8.0, 8.0, 8.0],
    "Current Value": [100.0, 400.0, 200.0, 100.0],
})


def test_score_performance_value_weighted():
    beat = (PERFORMANCE["1Y %"] > PERFORMANCE["vs Nifty50 1Y"]).astype(float)
    w = PERFORMANCE["Current Value"]
    expected = float((beat * w).sum() / w.sum() * 100.0)
    assert score_performance(PERFORMANCE) == pytest.approx(expected)


def test_score_performance_fallbacks():
    assert score_performance(None) == 60.0
    assert score_performance(pd.DataFrame(columns=["Fund"])) == 60.0
    missing = PERFORMANCE.drop(columns=["vs Nifty50 1Y"])
    assert score_performance(missing) == 60.0
    no_value = PERFORMANCE.drop(columns=["Current Value"])
    # equal-weight beat rate: 2 of 4 funds beat (12%, 20%) -> 50
    assert score_performance(no_value) == pytest.approx(50.0)


def test_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)