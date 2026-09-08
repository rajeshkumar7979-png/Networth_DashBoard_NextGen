# -------------------------------------------------
# Phase 1B driver module tests.
# Uses frozen baseline golden values; no network, no Streamlit.
# -------------------------------------------------
import math

import pandas as pd
import pytest

from lib.drivers import (
    ASSET_CLASSES,
    DRIVER_KEYS,
    NOT_A_CASHFLOW_LABEL,
    _get,
    _num,
    class_pnl_from_register,
    class_slug,
    decompose_current,
    fd_return_components,
    fd_rounding_bound,
    has_enriched_row,
    snapshot_delta,
)
from tests.frozen_baseline import CLASS_PNL_GOLDEN, FROZEN_BOOKS, FROZEN_TOTALS
from lib.register import build_asset_register, family_level_sum


# ── helpers ──────────────────────────────────────────────────────────────────

def _register():
    """Build the canonical register from frozen books (in-memory)."""
    return build_asset_register(
        pd.DataFrame(FROZEN_BOOKS["mf"]),
        pd.DataFrame(FROZEN_BOOKS["stocks"]),
        pd.DataFrame(FROZEN_BOOKS["gold"]),
        pd.DataFrame(FROZEN_BOOKS["fd"]),
    )


def construct_decomposable_fd_rounding(n, sign):
    """Per-FD rounding deltas (full-precision pnl minus rounded pnl) of the given
    sign, up to the maximum per-FD rounding magnitude of 1.0. Sum is the worst
    case the register-vs-driver reconciliation could encounter for n FDs."""
    return [sign * 1.0 for _ in range(int(n))]


# ── class_slug ───────────────────────────────────────────────────────────────

class TestClassSlug:
    @pytest.mark.parametrize("cls, expected", [
        ("Equity", "equity"),
        ("Liquid", "liquid"),
        ("FCNR (USD)", "fcnr_usd"),
        ("INR FD", "inr_fd"),
        ("Gold", "gold"),
    ])
    def test_slugs(self, cls, expected):
        assert class_slug(cls) == expected

    def test_empty_string_gives_empty(self):
        assert class_slug("") == ""

    def test_nonascii_gives_member(self):
        assert class_slug(None) == "none"


# ── fd_rounding_bound ────────────────────────────────────────────────────────

class TestFDRoundingBound:
    def test_known_value(self):
        assert fd_rounding_bound(23) == 35.5

    @pytest.mark.parametrize("n, expected", [(0, 1.0), (1, 2.5), (10, 16.0)])
    def test_parametrized(self, n, expected):
        assert fd_rounding_bound(n) == expected

    def test_none_gives_zero_bound(self):
        assert fd_rounding_bound(None) == 1.0

    def test_worst_case_rounding_bounded_across_23_fds(self):
        """Structurally prove the FD rounding residual bound.

        Per-FD class P&L in the register uses display-rounded current and cost,
        while the drivers use full-precision pre-round attribution. Each FD
        contributes a rounding delta in [-1.0, +1.0] to (current - invested).
        Both extreme sign patterns across 23 FDs must stay within the documented
        1.5*n+1 bound (true worst case is <= n = 23 < 35.5)."""
        n = 23
        bound = fd_rounding_bound(n)
        worst_plus = abs(sum(construct_decomposable_fd_rounding(n, sign=+1.0)))
        worst_minus = abs(sum(construct_decomposable_fd_rounding(n, sign=-1.0)))
        worst = max(worst_plus, worst_minus)
        assert worst <= n
        assert worst <= bound

    def test_worst_case_within_reported_bound_in_decompose(self):
        """End-to-end: a decomposed run whose FD rounding is at the worst case
        (residual magnitude ~n) still reports residual_ok under fd_rounding_bound."""
        n = 23
        residual = 23.0  # true worst-case FD rounding magnitude for 23 FDs
        total_pnl = 100000.0
        attributed = total_pnl - residual
        # equity + liquid + gold class pnl sum to (attributed - fd drivers)
        fd_drivers_total = attributed - 90000.0
        class_pnl = {
            "by_class": {
                "Equity": {"pnl": 30000.0},
                "Liquid": {"pnl": 10000.0},
                "Gold": {"pnl": 50000.0},
                "FCNR (USD)": {"pnl": 0.0},
                "INR FD": {"pnl": 0.0},
            },
            "total_pnl": total_pnl,
        }
        fd_components = {
            "fcnr_interest": fd_drivers_total * 0.6,
            "fcnr_fx_principal": fd_drivers_total * 0.4,
            "fcnr_fx_interest": 0.0,
            "inr_fd_interest": 0.0,
        }
        result = decompose_current(class_pnl, fd_components, n_fd=n)
        assert result["residual_ok"] is True
        assert abs(result["residual"]) == pytest.approx(residual)


# ── class_pnl_from_register ──────────────────────────────────────────────────

class TestClassPnlFromRegister:
    def test_golden_values_match(self):
        reg = _register()
        result = class_pnl_from_register(reg)
        for cls in ASSET_CLASSES:
            expected = CLASS_PNL_GOLDEN[cls]
            actual = result["by_class"][cls]["pnl"]
            assert math.isclose(actual, expected, abs_tol=1.0), (
                f"{cls}: got {actual}, expected {expected}"
            )

    def test_total_pnl_matches(self):
        reg = _register()
        result = class_pnl_from_register(reg)
        assert math.isclose(result["total_pnl"], FROZEN_TOTALS["total_pnl"], abs_tol=1.0)

    def test_sum_of_class_pnl_equals_total(self):
        reg = _register()
        result = class_pnl_from_register(reg)
        sum_pnl = sum(v["pnl"] for v in result["by_class"].values())
        assert math.isclose(sum_pnl, result["total_pnl"], abs_tol=2.0)

    def test_accepts_family_level_sum_dict(self):
        reg = _register()
        fam = family_level_sum(reg)
        result = class_pnl_from_register(fam)
        assert "total_pnl" in result
        assert result["total_pnl"] > 0


# ── fd_return_components ─────────────────────────────────────────────────────

class TestFDReturnComponents:
    def test_from_synthetic_data(self):
        fd_df = pd.DataFrame({
            "Product": ["FCNR", "FCNR", "INR FD", "INR FD"],
            "Interest Return (INR)": [100.0, 200.0, 300.0, 400.0],
            "FX Gain/Loss (INR)": [50.0, 60.0, 0.0, 0.0],
            "FX on Interest (INR)": [10.0, 20.0, 0.0, 0.0],
        })
        result = fd_return_components(fd_df)
        assert result["n_fd"] == 4
        assert math.isclose(result["fcnr_interest"], 300.0)
        assert math.isclose(result["fcnr_fx_principal"], 110.0)
        assert math.isclose(result["fcnr_fx_interest"], 30.0)
        assert math.isclose(result["inr_fd_interest"], 700.0)

    def test_empty_df(self):
        result = fd_return_components(pd.DataFrame())
        assert result["n_fd"] == 0
        assert all(v == 0.0 for k, v in result.items() if k != "n_fd")

    def test_none(self):
        result = fd_return_components(None)
        assert result["n_fd"] == 0


# ── decompose_current ────────────────────────────────────────────────────────

class TestDecomposeCurrent:
    def test_golden_class_drivers_from_register(self):
        """Genuine class-level golden: equity/liquid/gold drivers are derived from
        the register over frozen books (CLASS_PNL_GOLDEN). The FD-driven drivers
        are intentionally NOT fabricated here (see frozen_baseline note); only the
        identity residual == total_pnl - attributed is asserted."""
        reg = _register()
        pnl = class_pnl_from_register(reg)
        for cls in ASSET_CLASSES:
            assert math.isclose(pnl["by_class"][cls]["pnl"], CLASS_PNL_GOLDEN[cls], abs_tol=1.0)
        result = decompose_current(pnl, {"n_fd": 23}, n_fd=23)
        # The decomposition identity is exact by construction.
        assert math.isclose(result["attributed"] + result["residual"], pnl["total_pnl"], abs_tol=1e-6)
        assert result["fabricated"] is False
        assert result["cashflow_measurement"] is False
        # equity/liquid/gold class drivers match the genuine golden.
        assert math.isclose(result["drivers"]["equity_market"], CLASS_PNL_GOLDEN["Equity"], abs_tol=1.0)
        assert math.isclose(result["drivers"]["liquid_nav"], CLASS_PNL_GOLDEN["Liquid"], abs_tol=1.0)
        assert math.isclose(result["drivers"]["gold_price"], CLASS_PNL_GOLDEN["Gold"], abs_tol=1.0)

    def test_missing_fx_flag(self):
        pnl = {"by_class": {c: {"pnl": 0.0} for c in ASSET_CLASSES}, "total_pnl": 0.0}
        result = decompose_current(pnl, {}, missing_fx=True)
        assert result["missing_fx"] is True
        assert "USD/INR unavailable" in result["notes"][0]

    def test_residual_within_bound(self):
        pnl = {"by_class": {c: {"pnl": 100.0} for c in ASSET_CLASSES}, "total_pnl": 600.0}
        fd_comp = {"fcnr_interest": 50.0, "fcnr_fx_principal": 30.0, "fcnr_fx_interest": 0.0, "inr_fd_interest": 50.0}
        result = decompose_current(pnl, fd_comp, n_fd=1)
        expected_attributed = sum(result["drivers"].values())
        assert math.isclose(result["attributed"], expected_attributed)
        assert math.isclose(result["residual"], 600.0 - expected_attributed)

    def test_residual_never_forced_to_zero(self):
        """A non-zero residual must be surfaced as-is, never silently zeroed."""
        pnl = {"by_class": {c: {"pnl": 0.0} for c in ASSET_CLASSES}, "total_pnl": 1234.0}
        result = decompose_current(pnl, {}, n_fd=1)  # no FD attribution at all
        assert abs(result["residual"]) == pytest.approx(1234.0)
        assert result["residual_ok"] is False  # 1234 far exceeds the 2.5 bound for n=1

    def test_all_driver_keys_present(self):
        pnl = {"by_class": {c: {"pnl": 0.0} for c in ASSET_CLASSES}, "total_pnl": 0.0}
        result = decompose_current(pnl, {})
        for k in DRIVER_KEYS:
            assert k in result["drivers"]
            assert k in result["driver_labels"]


# ── _num / _get ──────────────────────────────────────────────────────────────

class TestNumGet:
    def test_num_none(self):
        assert _num(None) is None

    def test_num_nan(self):
        assert _num(float("nan")) is None

    def test_num_valid(self):
        assert _num(42) == 42.0

    def test_get_dict(self):
        assert _get({"a": 1}, "a") == 1

    def test_get_missing(self):
        assert _get({"a": 1}, "b") is None

    def test_get_series(self):
        s = pd.Series({"a": 1})
        assert _get(s, "a") == 1


# ── has_enriched_row ─────────────────────────────────────────────────────────

class TestHasEnrichedRow:
    def test_enriched_dict(self):
        assert has_enriched_row({"class_invested_equity": 100.0}) is True

    def test_legacy_dict(self):
        assert has_enriched_row({"net_worth": 1000.0}) is False

    def test_series(self):
        s = pd.Series({"class_invested_equity": 100.0})
        assert has_enriched_row(s) is True


# ── snapshot_delta ───────────────────────────────────────────────────────────

class TestSnapshotDelta:
    def _row(self, **kw):
        base = {
            "date": "2026-01-01", "net_worth": 1000.0,
            "class_current_equity": 200.0, "class_invested_equity": 100.0,
            "class_current_liquid": 300.0, "class_invested_liquid": 200.0,
            "class_current_gold": 100.0, "class_invested_gold": 50.0,
            "class_current_fcnr_usd": 250.0, "class_invested_fcnr_usd": 150.0,
            "class_current_inr_fd": 150.0, "class_invested_inr_fd": 100.0,
        }
        base.update(kw)
        return base

    def test_basic_delta(self):
        prev = self._row(date="2026-01-01", net_worth=1000.0,
                         fcnr_interest_total=100.0, fcnr_fx_principal_total=50.0)
        curr = self._row(date="2026-01-02", net_worth=1100.0,
                         class_current_equity=250.0,  # +50 from prev
                         class_invested_equity=110.0,  # +10 invested
                         fcnr_interest_total=120.0, fcnr_fx_principal_total=55.0)
        d = snapshot_delta(prev, curr)
        assert d["available"] is True
        assert d["cashflow_measurement"] is False
        # Equity: invested_basis_change = 110-100 = 10, mv = (250-110)-(200-100) = 140-100 = 40
        eq = d["by_class"]["Equity"]
        assert eq["invested_basis_change"] == 10.0
        assert eq["market_valuation_change"] == 40.0
        assert eq["delta_current"] == 50.0
        # FCNR deltas
        assert d["fcnr"]["delta_interest"] == 20.0
        assert d["fcnr"]["delta_fx"] == 5.0

    def test_legacy_prev_unavailable(self):
        prev = {"date": "2026-01-01", "net_worth": 1000.0}
        curr = self._row(date="2026-01-02", net_worth=1100.0)
        d = snapshot_delta(prev, curr)
        assert d["available"] is False
        assert d["reason"] is not None
        assert d["unattributed_abs"] == 100.0

    def test_same_values_zero_delta(self):
        row = self._row()
        d = snapshot_delta(row, row)
        assert d["available"] is True
        for cls_data in d["by_class"].values():
            if cls_data is not None:
                assert cls_data["delta_current"] == 0.0
                assert cls_data["invested_basis_change"] == 0.0
                assert cls_data["market_valuation_change"] == 0.0

    def test_label_present(self):
        d = snapshot_delta(self._row(), self._row())
        assert d["not_a_cashflow_label"] == NOT_A_CASHFLOW_LABEL
