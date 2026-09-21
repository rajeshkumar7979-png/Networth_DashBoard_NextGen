# -------------------------------------------------
# Phase 1B - financial drivers + snapshot delta decomposition.
# Pure module: no streamlit, no network, no re-valuation.
#
# Semantics: the workbook has NO cash-flow/transaction ledger. The class
# invested difference between two snapshots is the "Invested-Basis Change" -
# explicitly NOT a cash-flow measurement - and no deposits/withdrawals/SIPs/
# redemptions/switches/dividends/bonuses are ever inferred. Every output that
# involves it carries cashflow_measurement=False and the label below.
#
# Drivers: P&L attribution (valuation) only. Bank/rounded books produce a
# labeled residual bounded by 1.5*n_fd + 1 (per-FD rounding of current and cost
# to whole rupees, plus the FX-on-interest fold-in).
# -------------------------------------------------
import re

import pandas as pd

from lib.register import ASSET_CLASSES, family_level_sum

NOT_A_CASHFLOW_LABEL = "NOT a cash-flow measurement; transaction history unavailable."

DRIVER_KEYS = [
    "equity_market",
    "liquid_nav",
    "gold_price",
    "fcnr_interest",
    "fcnr_fx_principal",
    "inr_fd_interest",
]

DRIVER_LABELS = {
    "equity_market": "Equity (stocks + non-liquid MF) P&L",
    "liquid_nav": "Liquid funds P&L",
    "gold_price": "Gold (SGB + ETF + FoF) P&L",
    "fcnr_interest": "FCNR interest (at current FX)",
    "fcnr_fx_principal": "FCNR FX on principal",
    "inr_fd_interest": "INR FD interest",
}

DRIVER_SUBS = {
    "equity_market": "current − invested",
    "liquid_nav": "current − invested",
    "gold_price": "current − invested",
    "fcnr_interest": "accrued USD × today's FX",
    "fcnr_fx_principal": "principal × FX move",
    "inr_fd_interest": "accrued contractual interest",
}

LIFETIME_PNL_CAPTION = (
    "These rupees are this mark's P&L (current − invested) split by source. "
    "They are not cash received and not the move since the last snapshot."
)
PERIOD_DELTA_CAPTION = (
    "Difference versus the previous history snapshot. "
    + NOT_A_CASHFLOW_LABEL
)

LIFETIME_CHANGE_KINDS = frozenset({"pnl_driver"})
PERIOD_CHANGE_KINDS = frozenset({
    "invested_basis_change", "market_valuation_change", "class_delta",
})


def split_change_rows(changes):
    """Separate lifetime P&L drivers from snapshot-to-snapshot deltas.

    build_change_summary emits both in one tuple. Mixing them under
    'what changed this run' is the labelling bug — the numbers are right,
    the heading is not.
    """
    lifetime, period, other = [], [], []
    for row in changes or ():
        kind = getattr(row, "kind", "")
        if kind in LIFETIME_CHANGE_KINDS:
            lifetime.append(row)
        elif kind in PERIOD_CHANGE_KINDS:
            period.append(row)
        else:
            other.append(row)
    return lifetime, period, other


def driver_sub_for(change) -> str:
    label = getattr(change, "label", "") or ""
    for key, text in DRIVER_LABELS.items():
        if label == text:
            return DRIVER_SUBS.get(key, "current − invested")
    return "current − invested"



def class_slug(cls):
    """Canonical column-safe slug for an asset class (e.g. 'FCNR (USD)' -> 'fcnr_usd')."""
    return re.sub(r"[^0-9a-z]+", "_", str(cls).lower()).strip("_")


def fd_rounding_bound(n):
    """Documented residual bound for rounded bank values: each FD contributes up
    to ~₹0.5 on current and ~₹0.5 on cost (independent whole-rupee rounding)."""
    n = int(n) if n is not None else 0
    return 1.5 * n + 1.0


def class_pnl_from_register(register):
    """Per-class current/invested/P&L from the canonical register (exact floats)."""
    fam = (
        register
        if isinstance(register, dict) and "by_class" in register
        else family_level_sum(register)
    )
    by_class = {}
    for cls in ASSET_CLASSES:
        v = fam["by_class"].get(cls) or {}
        cur = float(v.get("current") or 0.0)
        inv = float(v.get("invested") or 0.0)
        by_class[cls] = {"current": cur, "invested": inv, "pnl": cur - inv}
    total_assets = float(fam["total_assets"])
    total_invested = float(fam["total_invested"])
    return {
        "by_class": by_class,
        "total_assets": total_assets,
        "total_invested": total_invested,
        "total_pnl": total_assets - total_invested,
    }


def fd_return_components(fd_df):
    """Sum per-FD attribution columns ('Interest Return (INR)', 'FX Gain/Loss
    (INR)', 'FX on Interest (INR)') split by Product (FCNR vs INR FD). Used for
    recover-then-decompose paths (tests); the page prefers full-precision
    accumulators. Also reports n_fd for the rounding bound."""
    out = {"fcnr_interest": 0.0, "fcnr_fx_principal": 0.0, "fcnr_fx_interest": 0.0, "inr_fd_interest": 0.0, "n_fd": 0}
    if fd_df is None or getattr(fd_df, "empty", True):
        return out
    if "Product" in fd_df.columns:
        is_fcnr = fd_df["Product"] == "FCNR"
    else:
        is_fcnr = pd.Series(False, index=fd_df.index)
    if "Interest Return (INR)" in fd_df.columns:
        out["fcnr_interest"] = float(fd_df.loc[is_fcnr, "Interest Return (INR)"].sum() or 0.0)
        out["inr_fd_interest"] = float(fd_df.loc[~is_fcnr, "Interest Return (INR)"].sum() or 0.0)
    if "FX Gain/Loss (INR)" in fd_df.columns:
        out["fcnr_fx_principal"] = float(fd_df.loc[is_fcnr, "FX Gain/Loss (INR)"].sum() or 0.0)
    if "FX on Interest (INR)" in fd_df.columns:
        out["fcnr_fx_interest"] = float(fd_df.loc[is_fcnr, "FX on Interest (INR)"].sum() or 0.0)
    out["n_fd"] = len(fd_df)
    return out


def decompose_current(class_pnl, fd_components, n_fd=None, missing_fx=False):
    """Split current-run P&L into six drivers plus a labeled rounding residual.

    Identity: sum(drivers) + residual == total_pnl. residual_ok means the
    residual (rounded-book vs full-precision accumulation) is within the
    documented 1.5*n_fd + 1 bound. FX-independent slices are never invented.
    """
    drivers = {
        "equity_market": float(class_pnl["by_class"]["Equity"]["pnl"]),
        "liquid_nav": float(class_pnl["by_class"]["Liquid"]["pnl"]),
        "gold_price": float(class_pnl["by_class"]["Gold"]["pnl"]),
        "fcnr_interest": float(fd_components.get("fcnr_interest") or 0.0),
        "fcnr_fx_principal": float(
            (fd_components.get("fcnr_fx_principal") or 0.0)
            + (fd_components.get("fcnr_fx_interest") or 0.0)
        ),
        "inr_fd_interest": float(fd_components.get("inr_fd_interest") or 0.0),
    }
    attributed = float(sum(drivers.values()))
    total_pnl = float(class_pnl["total_pnl"])
    residual = total_pnl - attributed
    n = n_fd if n_fd is not None else fd_components.get("n_fd")
    bound = fd_rounding_bound(n) if n is not None else None
    notes = []
    if missing_fx:
        notes.append("USD/INR unavailable this run - FCNR interest/FX slices are n/a (0.0), never guessed.")
    return {
        "drivers": drivers,
        "driver_labels": dict(DRIVER_LABELS),
        "total_pnl": total_pnl,
        "attributed": attributed,
        "residual": residual,
        "residual_bound": bound,
        "residual_ok": bound is None or abs(residual) <= bound,
        "fabricated": False,
        "missing_fx": bool(missing_fx),
        "notes": notes,
        "cashflow_measurement": False,
    }


def _num(value):
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else (row[key] if key in row.index else None)


def has_enriched_row(row):
    """True when the row carries the Phase 1B class-invested breakdown."""
    try:
        return _num(_get(row, "class_invested_equity")) is not None
    except Exception:
        return False


def snapshot_delta(prev_row, curr_row):
    """Decompose the change between two snapshots into per-class Invested-Basis
    Change and Market/Valuation Change.

    invested_basis_change  = class_invested_now  - class_invested_prev   (NOT cash flow)
    market_valuation_change = (current_now - invested_now) - (current_prev - invested_prev)
    delta_current          = current_now - current_prev == ib_change + mv_change  (exact)

    Legacy pre-Phase 1B rows cannot be decomposed: available=False and the whole
    |Delta net worth| is counted as unattributed.
    """
    prev = dict(prev_row)
    curr = dict(curr_row)
    date_prev = str(prev.get("date", "") or "")
    date_curr = str(curr.get("date", "") or "")
    available = has_enriched_row(prev) and has_enriched_row(curr)

    by_class = {}
    for cls in ASSET_CLASSES:
        slug = class_slug(cls)
        c_now = _num(curr.get(f"class_current_{slug}"))
        i_now = _num(curr.get(f"class_invested_{slug}"))
        c_prev = _num(prev.get(f"class_current_{slug}"))
        i_prev = _num(prev.get(f"class_invested_{slug}"))
        if None in (c_now, i_now, c_prev, i_prev):
            by_class[cls] = None
            continue
        invested_basis_change = i_now - i_prev
        market_valuation_change = (c_now - i_now) - (c_prev - i_prev)
        by_class[cls] = {
            "delta_current": c_now - c_prev,
            "invested_basis_change": invested_basis_change,
            "market_valuation_change": market_valuation_change,
        }

    if available:
        invested_total = sum(x["invested_basis_change"] for x in by_class.values() if x is not None)
        market_total = sum(x["market_valuation_change"] for x in by_class.values() if x is not None)
        delta_total = invested_total + market_total
    else:
        invested_total = market_total = None
        nw_prev = _num(prev.get("net_worth"))
        nw_cur = _num(curr.get("net_worth"))
        delta_total = (nw_cur - nw_prev) if None not in (nw_prev, nw_cur) else None

    if available:
        nw_prev = _num(prev.get("net_worth"))
        nw_cur = _num(curr.get("net_worth"))
        if None not in (nw_prev, nw_cur) and delta_total is not None:
            unattributed_abs = abs(delta_total - (nw_cur - nw_prev))
        else:
            unattributed_abs = 0.0
        reason = None
    else:
        unattributed_abs = abs(delta_total) if delta_total is not None else 0.0
        reason = (
            "Prior snapshot is legacy (pre-Phase 1B) without a class breakdown - "
            "enriched snapshots decompose from now on."
        )

    fcnr = None
    if available:
        pair = {"delta_interest": None, "delta_fx": None}
        ok = True
        for key, out in (("fcnr_interest_total", "delta_interest"),
                         ("fcnr_fx_principal_total", "delta_fx")):
            a = _num(curr.get(key))
            b = _num(prev.get(key))
            if a is None or b is None:
                ok = False
                break
            pair[out] = a - b
        fcnr = pair if ok else None

    return {
        "available": available,
        "date_prev": date_prev,
        "date_curr": date_curr,
        "by_class": by_class,
        "totals": {
            "delta_current": delta_total,
            "invested_basis_change": invested_total,
            "market_valuation_change": market_total,
        },
        "fcnr": fcnr,
        "unattributed_abs": unattributed_abs,
        "reason": reason,
        "cashflow_measurement": False,
        "not_a_cashflow_label": NOT_A_CASHFLOW_LABEL,
    }