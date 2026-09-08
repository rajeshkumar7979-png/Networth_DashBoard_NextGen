import pandas as pd
import pytest

from lib.formatters import safe_float
from lib.valuation import _safe_maturity_amount, compute_fd_current_native

TODAY = pd.Timestamp("2026-09-08")


def _to_naive_ts(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    ts = pd.Timestamp(x)
    return ts.tz_localize(None) if ts.tzinfo is not None else ts


def _page_fd_params(row):
    """Replicates pages/1_Command_Center.py FD extraction (lines ~969-990)."""
    holder = str(row.get("Holder Name", "") or "").strip()
    principal = safe_float(row.get("Principal Amount"))
    if (not holder or holder.lower() in ["nan", "nat", "none"] or principal <= 0 or "total" in holder.lower()):
        return None
    dep, mat = _to_naive_ts(row.get("Deposit Date")), _to_naive_ts(row.get("Maturity Date"))
    roi = safe_float(row.get("ROI % p.a.", row.get("ROI_Percent_pa", 6.5)))
    maturity_amt = _safe_maturity_amount(row)
    available_balance = None
    for col in row.index if hasattr(row, "index") else []:
        if str(col).strip().lower().replace("_", " ") in (
            "available balance", "available balanc", "available amount"
        ):
            available_balance = safe_float(row.get(col))
            break
    return dict(principal=principal, roi=roi, dep_date=dep, mat_date=mat, today=TODAY,
                maturity_amt=maturity_amt, available_balance=available_balance)


# ---------------- branch-level unit tests (fabricated, today-fixed) ----------------
def test_maturity_interp_interpolates_between_principal_and_maturity():
    current, accrued, method, notes = compute_fd_current_native(
        100000, 6.5, pd.Timestamp("2025-01-01"), pd.Timestamp("2030-01-01"), TODAY,
        maturity_amt=130000,
    )
    days = (TODAY - pd.Timestamp("2025-01-01")).days
    tenor = (pd.Timestamp("2030-01-01") - pd.Timestamp("2025-01-01")).days
    frac = days / tenor
    expected = 100000 + (130000 - 100000) * frac
    assert method == "maturity_interp"
    assert current == pytest.approx(expected, abs=1e-6)
    assert accrued == pytest.approx(current - 100000, abs=1e-6)
    assert current < 130000


def test_maturity_interp_caps_at_maturity_after_tenor():
    current, accrued, method, _ = compute_fd_current_native(
        100000, 5.5, pd.Timestamp("2020-01-01"), pd.Timestamp("2025-01-01"), TODAY,
        maturity_amt=125000,
    )
    assert method == "maturity_interp"
    assert current == pytest.approx(125000, abs=1e-6)
    assert accrued == pytest.approx(25000, abs=1e-6)


def test_available_balance_used_when_meaningfully_above_principal():
    current, accrued, method, notes = compute_fd_current_native(
        100000, 6.5, pd.Timestamp("2025-01-01"), pd.Timestamp("2030-01-01"), TODAY,
        available_balance=100400,
    )
    assert method == "available_balance"
    assert current == pytest.approx(100400, abs=1e-6)
    assert accrued == pytest.approx(400, abs=1e-6)
    assert "using Available Balance from bank (above principal)" in notes


def test_available_balance_ignored_when_approx_equal_to_principal():
    # Balance ≈ principal (< 0.1% above) is ignored and we fall to simple interest.
    current, accrued, method, notes = compute_fd_current_native(
        100000, 6.5, pd.Timestamp("2025-01-01"), pd.Timestamp("2030-01-01"), TODAY,
        available_balance=100000,
    )
    assert method == "simple_interest"
    assert "Available Balance ≈ principal — ignored" in notes


def test_simple_interest_fallback_formula():
    # Regression for the fixed `notess` bug: this path used to raise NameError.
    current, accrued, method, notes = compute_fd_current_native(
        100000, 6.5, pd.Timestamp("2025-01-01"), pd.Timestamp("2030-01-01"), TODAY,
    )
    days = (TODAY - pd.Timestamp("2025-01-01")).days
    expected_accrued = 100000 * (6.5 / 100.0) * (days / 365.0)
    assert method == "simple_interest"
    assert accrued == pytest.approx(expected_accrued, abs=1e-6)
    assert current == pytest.approx(100000 + expected_accrued, abs=1e-6)


def test_simple_interest_long_tenor_warning():
    _, _, method, notes = compute_fd_current_native(
        100000, 6.5, pd.Timestamp("2015-01-01"), pd.Timestamp("2035-01-01"), TODAY,
    )
    assert method == "simple_interest"
    assert any("long tenor" in n for n in notes)


def test_invalid_principal_returns_invalid_tuple():
    for principal in (None, 0, -1):
        current, accrued, method, notes = compute_fd_current_native(
            principal, 6.5, pd.Timestamp("2025-01-01"), pd.Timestamp("2030-01-01"), TODAY,
        )
        assert (current, accrued) == (None, None)
        assert method == "invalid"
        assert notes


def test_zero_roi_yields_zero_accrual():
    current, accrued, method, _ = compute_fd_current_native(
        100000, 0.0, pd.Timestamp("2025-01-01"), pd.Timestamp("2030-01-01"), TODAY,
    )
    assert method == "simple_interest"
    assert accrued == pytest.approx(0.0, abs=1e-9)
    assert current == pytest.approx(100000, abs=1e-9)


# ---------------- workbook sweep (today-fixed golden regression) ----------------
# Captured from the committed sample workbook with TODAY = 2026-09-08 using the
# app-identical extraction path. Rows 23-32 are blank/subtotal rows (skipped).
FD_GOLDEN = [
    (0, "maturity_interp", 50000.0, 52931.37),
    (1, "maturity_interp", 44009.0, 51356.75),
    (2, "maturity_interp", 72029.0, 76878.14),
    (3, "maturity_interp", 54960.0, 58369.11),
    (4, "maturity_interp", 200000.0, 212788.36),
    (5, "maturity_interp", 300000.0, 332584.61),
    (6, "maturity_interp", 77621.0, 83438.41),
    (7, "maturity_interp", 7467.76, 7708.19),
    (8, "maturity_interp", 7324.09, 7658.76),
    (9, "maturity_interp", 7695.16, 7713.97),
    (10, "maturity_interp", 9530.31, 10315.25),
    (11, "maturity_interp", 6732.37, 7375.71),
    (12, "maturity_interp", 11600.12, 11604.75),
    (13, "maturity_interp", 7537.41, 7915.51),
    (14, "maturity_interp", 7725.96, 8052.8),
    (15, "maturity_interp", 7828.35, 7961.34),
    (16, "maturity_interp", 422022.0, 443363.12),
    (17, "maturity_interp", 2342229.0, 2764936.12),
    (18, "maturity_interp", 7690.81, 7765.18),
    (19, "maturity_interp", 7000.0, 7050.02),
    (20, "maturity_interp", 7000.0, 7050.02),
    (21, "maturity_interp", 7000.0, 7050.02),
    (22, "maturity_interp", 7000.0, 7050.02),
]


def test_workbook_fd_rows_process_exactly(fd_df):
    collected = []
    for idx, row in fd_df.iterrows():
        params = _page_fd_params(row)
        if params is None:
            collected.append((idx, "SKIPPED", None, None))
            continue
        current, accrued, method, _ = compute_fd_current_native(**params)
        assert current is not None
        collected.append((idx, method, params["principal"], current))
    assert len([c for c in collected if c[1] != "SKIPPED"]) == 23
    assert len([c for c in collected if c[1] == "SKIPPED"]) == 10


@pytest.mark.parametrize("idx,method,principal,golden_current", FD_GOLDEN)
def test_workbook_fd_row_valuation(fd_df, idx, method, principal, golden_current):
    row = fd_df.iloc[idx]
    params = _page_fd_params(row)
    assert params is not None
    assert params["principal"] == pytest.approx(principal, abs=1e-6)
    current, accrued, actual_method, notes = compute_fd_current_native(**params)
    assert actual_method == method
    assert current == pytest.approx(golden_current, abs=0.01)
    assert accrued == pytest.approx(current - params["principal"], abs=1e-6)
    assert isinstance(notes, list) and notes