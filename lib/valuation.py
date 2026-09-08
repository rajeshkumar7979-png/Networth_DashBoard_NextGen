# -------------------------------------------------
# Phase 1 — FD valuation + FCNR attribution helpers
# Extracted verbatim from pages/1_Command_Center.py (Phase 0).
# The only intentional calculation change in this phase:
#   `notess` -> `notes` (fixed a NameError on the simple-interest path).
# -------------------------------------------------
from lib.formatters import safe_float


def _safe_maturity_amount(row):
    """
    Robust lookup for bank-supplied maturity / current accrued amount.
    Handles trailing spaces, case differences, and common alternate names.
    Also falls back to Available Balance when it looks like a real accrued value.
    """
    # Build a normalised map of the row's columns once
    col_map = {}
    for c in row.index if hasattr(row, "index") else row.keys():
        key = str(c).strip().lower().replace("_", " ")
        col_map[key] = c

    # Preferred names (highest priority first)
    candidates = [
        "maturity amount",
        "maturity value",
        "maturity amt",
        "maturityamount",
        "current accrued amount",
        "accrued amount",
        "current value",
    ]

    for name in candidates:
        if name in col_map:
            v = safe_float(row.get(col_map[name]))
            if v is not None and v > 0:
                return v

    # Secondary: Available Balance (only if it is meaningfully different from principal
    # or equal to principal — still better than pure simple-interest guess)
    for name in ("available balance", "available balanc", "available amount"):
        if name in col_map:
            v = safe_float(row.get(col_map[name]))
            if v is not None and v > 0:
                return v

    return None


def compute_fd_current_native(principal, roi, dep_date, mat_date, today,
                              maturity_amt=None, available_balance=None):
    """
    Returns (current_value_native, accrued_native, method, notes)

    Priority for this workbook:
    1. Maturity Amount → linear interpolation (best)
    2. Available Balance only if it is meaningfully > principal (real accrued value)
    3. Simple interest from deposit date
    """
    notes = []
    if principal is None or principal <= 0:
        return None, None, "invalid", ["principal missing/zero"]

    days_elapsed = max((today - dep_date).days, 0) if dep_date is not None else 0
    total_tenor_days = None
    if dep_date is not None and mat_date is not None and mat_date > dep_date:
        total_tenor_days = (mat_date - dep_date).days

    # --- 1. Maturity Amount interpolation (preferred) ---
    if maturity_amt is not None and maturity_amt > 0 and total_tenor_days and total_tenor_days > 0:
        frac = min(max(days_elapsed / total_tenor_days, 0.0), 1.0)
        current = principal + (maturity_amt - principal) * frac
        accrued = current - principal
        method = "maturity_interp"
        notes.append(f"interpolated using maturity amount (frac={frac:.3f})")
        if days_elapsed < total_tenor_days:
            current = min(current, maturity_amt)
            accrued = current - principal
        return current, accrued, method, notes

    # --- 2. Available Balance only if it looks like real accrued value ---
    # (skip when it is essentially equal to principal — common in this Excel)
    if available_balance is not None and available_balance > 0:
        if available_balance > principal * 1.001:  # at least 0.1% above principal
            current = float(available_balance)
            accrued = current - principal
            method = "available_balance"
            notes.append("using Available Balance from bank (above principal)")
            return current, accrued, method, notes
        else:
            notes.append("Available Balance ≈ principal — ignored")

    # --- 3. Simple interest fallback ---
    accrued = principal * (roi / 100.0) * (days_elapsed / 365.0)
    current = principal + accrued
    method = "simple_interest"
    notes.append("fallback simple interest from deposit date")
    if total_tenor_days and total_tenor_days > 400 and days_elapsed > 400:
        notes.append("WARNING: long tenor – simple interest may overstate value")
    return current, accrued, method, notes


def compute_fcnr_attribution(principal_native, accrued_native, fx_deposit, fx_today):
    """
    Full FCNR attribution that reconciles exactly.

    Model:
      - Interest is valued at *current* FX
      - FX gain/loss is calculated only on the original principal

    Identity (must hold within ₹1):
      interest_at_current_fx + fx_on_principal
      == current_value_inr - cost_basis_inr
    """
    if fx_today is None or fx_deposit is None or fx_today <= 0 or fx_deposit <= 0:
        return None

    cost_basis_inr     = principal_native * fx_deposit
    current_value_inr  = (principal_native + accrued_native) * fx_today

    interest_at_current_fx = accrued_native * fx_today
    fx_on_principal        = principal_native * (fx_today - fx_deposit)

    total_attribution = interest_at_current_fx + fx_on_principal
    pnl               = current_value_inr - cost_basis_inr
    reconciled        = abs(total_attribution - pnl) < 1.0

    return {
        "cost_basis_inr":          cost_basis_inr,
        "current_value_inr":       current_value_inr,
        "interest_at_current_fx":  interest_at_current_fx,
        "fx_on_principal":         fx_on_principal,
        "fx_on_interest":          0.0,   # kept for column compatibility; always 0 in this model
        "total_attribution":       total_attribution,
        "pnl":                     pnl,
        "reconciled":              reconciled,
    }