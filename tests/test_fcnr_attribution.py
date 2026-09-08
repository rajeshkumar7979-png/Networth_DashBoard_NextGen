import pandas as pd
import pytest

from lib.formatters import safe_float
from lib.valuation import compute_fcnr_attribution, compute_fd_current_native, _safe_maturity_amount

TODAY = pd.Timestamp("2026-09-08")
FX_DEPOSIT, FX_TODAY = 83.0, 84.0


def _to_naive_ts(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    ts = pd.Timestamp(x)
    return ts.tz_localize(None) if ts.tzinfo is not None else ts


def _usd_fd_params(row):
    principal = safe_float(row.get("Principal Amount"))
    dep, mat = _to_naive_ts(row.get("Deposit Date")), _to_naive_ts(row.get("Maturity Date"))
    roi = safe_float(row.get("ROI % p.a.", row.get("ROI_Percent_pa", 6.5)))
    available_balance = None
    for col in row.index if hasattr(row, "index") else []:
        if str(col).strip().lower().replace("_", " ") in (
            "available balance", "available balanc", "available amount"
        ):
            available_balance = safe_float(row.get(col))
            break
    return dict(principal=principal, roi=roi, dep_date=dep, mat_date=mat, today=TODAY,
                maturity_amt=_safe_maturity_amount(row), available_balance=available_balance)


# ---------------- attribution math ----------------
@pytest.mark.parametrize("principal,accrued,fx_deposit,fx_today", [
    (10000, 500, 83.0, 84.0),
    (10000, 500, 83.0, 83.0),
    (109132.34, 2103.44, 75.2, 84.7),
    (7467.76, 232.11, 82.4, 86.1),
    (12345.67, 0.0, 90.0, 90.0),
    (10000, 500, 80.0, 84.0),
])
def test_fcnr_attribution_fields_and_identity(principal, accrued, fx_deposit, fx_today):
    attr = compute_fcnr_attribution(principal, accrued, fx_deposit, fx_today)
    assert attr is not None
    assert attr["cost_basis_inr"] == pytest.approx(principal * fx_deposit, abs=1e-9)
    assert attr["current_value_inr"] == pytest.approx((principal + accrued) * fx_today, abs=1e-9)
    assert attr["interest_at_current_fx"] == pytest.approx(accrued * fx_today, abs=1e-9)
    assert attr["fx_on_principal"] == pytest.approx(principal * (fx_today - fx_deposit), abs=1e-9)
    assert attr["fx_on_interest"] == 0.0
    assert attr["total_attribution"] == pytest.approx(
        attr["interest_at_current_fx"] + attr["fx_on_principal"], abs=1e-9
    )
    assert attr["pnl"] == pytest.approx(
        attr["current_value_inr"] - attr["cost_basis_inr"], abs=1e-9
    )
    # The NRI identity must reconcile strictly within ₹1.
    assert abs(attr["total_attribution"] - attr["pnl"]) < 1.0
    assert attr["reconciled"] is True


def test_fcnr_identity_property_sweep():
    # Identity holds for any valid FX pair / principal / accrual combination.
    for principal in (1000.0, 50000.0, 2342229.0 / 83.0):
        for accrued in (0.0, 100.0, 3500.0):
            for fx_deposit in (74.0, 80.5, 86.0):
                for fx_today in (75.0, 83.0, 95.0):
                    attr = compute_fcnr_attribution(principal, accrued, fx_deposit, fx_today)
                    assert abs(attr["total_attribution"] - attr["pnl"]) < 1.0


@pytest.mark.parametrize("principal,accrued,fx_deposit,fx_today", [
    (10000, 500, None, 84.0),
    (10000, 500, 83.0, None),
    (10000, 500, 0.0, 84.0),
    (10000, 500, 83.0, 0.0),
    (10000, 500, -1.0, 84.0),
])
def test_fcnr_invalid_fx_returns_none(principal, accrued, fx_deposit, fx_today):
    assert compute_fcnr_attribution(principal, accrued, fx_deposit, fx_today) is None


# ---------------- workbook FCNR sweep (all 14 USD rows) ----------------
def test_workbook_usd_fd_rows_recount(fd_df):
    usd = fd_df[fd_df["Currency"] == "USD"]
    assert len(usd) == 14
    for _, row in usd.iterrows():
        params = _usd_fd_params(row)
        current, accrued, method, _ = compute_fd_current_native(**params)
        assert current is not None


@pytest.mark.parametrize("usd_row_index", list(range(7, 16)) + list(range(18, 23)))
def test_workbook_usd_fd_identity_within_rupee(fd_df, usd_row_index):
    row = fd_df.iloc[usd_row_index]
    assert str(row.get("Currency", "")).strip().upper() == "USD"
    params = _usd_fd_params(row)
    _, accrued, _, _ = compute_fd_current_native(**params)
    attr = compute_fcnr_attribution(params["principal"], accrued, FX_DEPOSIT, FX_TODAY)
    assert attr is not None
    assert abs(attr["total_attribution"] - attr["pnl"]) < 1.0
    assert attr["reconciled"] is True