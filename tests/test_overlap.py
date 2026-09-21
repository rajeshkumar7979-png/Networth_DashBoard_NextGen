"""Look-through overlap — pairwise min-weight, family rupees, Direct vs Regular."""
import pytest

from lib.overlap import (
    CONCENTRATION_THRESHOLD_PCT,
    concentration_flags,
    direct_regular_pairs,
    family_look_through,
    holding_key,
    pairwise_matrix,
    pairwise_overlap_pct,
    scheme_stem,
)


def test_holding_key_prefers_isin_over_name():
    assert holding_key("INE002A01018", "Reliance") == "ISIN:INE002A01018"
    assert holding_key("", "Reliance Industries") == "NAME:RELIANCEINDUSTRIES"
    assert holding_key(None, None) is None


def test_pairwise_overlap_is_sum_of_mins():
    a = {"ISIN:A": 10.0, "ISIN:B": 20.0, "ISIN:C": 5.0}
    b = {"ISIN:A": 8.0, "ISIN:B": 4.0, "ISIN:Z": 50.0}
    # min(10,8)+min(20,4) = 12
    assert pairwise_overlap_pct(a, b) == pytest.approx(12.0)
    assert pairwise_overlap_pct(a, {}) is None
    assert pairwise_overlap_pct(a, {"ISIN:Z": 1.0}) == pytest.approx(0.0)


def test_pairwise_matrix_skips_empty_and_is_upper_triangle():
    funds = {
        "Fund A": {"ISIN:X": 40.0, "ISIN:Y": 10.0},
        "Fund B": {"ISIN:X": 25.0, "ISIN:Z": 10.0},
        "Fund C": {},  # undisclosed — omitted
    }
    rows = pairwise_matrix(funds)
    assert len(rows) == 1
    a, b, pct = rows[0]
    assert (a, b) == ("Fund A", "Fund B")
    assert pct == pytest.approx(25.0)


def test_family_look_through_weights_by_family_rupees():
    # Stock S is 10% of a ₹1L fund and 50% of a ₹20k fund → ₹10k + ₹10k.
    exposure = {
        "ISIN:S": [
            ("Fund A", 10.0, 100_000.0, "Stock S"),
            ("Fund B", 50.0, 20_000.0, "Stock S"),
        ],
        "ISIN:T": [
            ("Fund A", 5.0, 100_000.0, "Stock T"),
        ],
    }
    rows = family_look_through(exposure, 120_000.0)
    s = next(r for r in rows if r["name"] == "Stock S")
    t = next(r for r in rows if r["name"] == "Stock T")
    assert s["exposure_inr"] == pytest.approx(20_000.0)
    assert s["n_funds"] == 2
    assert t["pct_of_mf"] == pytest.approx(5000.0 / 120_000.0 * 100.0)
    assert family_look_through({}, 120_000.0) == []
    assert family_look_through(exposure, 0) == []


def test_concentration_flags_use_mf_book_threshold():
    rows = [
        {"name": "Big", "pct_of_mf": 6.2, "n_funds": 3, "exposure_inr": 1},
        {"name": "Small", "pct_of_mf": 1.0, "n_funds": 2, "exposure_inr": 1},
    ]
    flagged = concentration_flags(rows, threshold_pct=CONCENTRATION_THRESHOLD_PCT)
    assert [r["name"] for r in flagged] == ["Big"]


def test_direct_regular_pairs_same_stem_only():
    names = [
        "HDFC Large Cap Fund Direct Growth",
        "HDFC Large Cap Fund Growth - Regular",
        "Axis Large Cap Fund Direct Growth",
        "SBI Contra Direct Plan Growth",
    ]
    pairs = direct_regular_pairs(names)
    assert len(pairs) == 1
    stem, direct, regular = pairs[0]
    assert stem == scheme_stem("HDFC Large Cap Fund Direct Growth")
    assert "HDFC Large Cap Fund Direct Growth" in direct
    assert "HDFC Large Cap Fund Growth - Regular" in regular
    assert scheme_stem("HDFC Large Cap Fund Direct Growth") == scheme_stem(
        "HDFC Large Cap Fund Growth - Regular"
    )
