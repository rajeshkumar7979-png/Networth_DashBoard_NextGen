# -------------------------------------------------
# Phase 1A — ledger semantics.
# Net Worth = Total Assets - Total Liabilities.
#
# The Command Center metric previously labelled "Net Worth (INR)" actually holds
# TOTAL ASSETS (the workbook carries no liabilities sheet). This module is the
# single source of the corrected semantics; the page keeps the unchanged
# underlying value and renames the label, then computes Net Worth here.
# -------------------------------------------------
import math


def net_worth(assets_total, liabilities_total=None):
    """Net worth from total assets and (optional) total liabilities.

    Zero / None liabilities produce net_worth == assets_total EXACTLY (parity is
    pinned by tests to ₹0.01, and arithmetic here is plain subtraction so it is
    exact at full float precision).
    """
    if assets_total is None or not math.isfinite(float(assets_total)):
        raise ValueError("assets_total must be a finite number")
    assets = float(assets_total)

    if liabilities_total is None:
        liabilities = 0.0
    else:
        if not math.isfinite(float(liabilities_total)):
            raise ValueError("liabilities_total must be a finite number")
        liabilities = float(liabilities_total)
        if liabilities < 0:
            raise ValueError("liabilities_total cannot be negative")

    return {
        "total_assets": assets,
        "total_liabilities": liabilities,
        "net_worth": assets - liabilities,
        "has_liabilities": liabilities > 0,
    }