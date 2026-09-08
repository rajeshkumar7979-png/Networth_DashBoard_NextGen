# -------------------------------------------------
# NRI-aware health score factors.
# Extracted verbatim from pages/1_Command_Center.py (Phase 0).
# No calculation changes in this phase.
# -------------------------------------------------
import pandas as pd


def score_allocation(equity_pct, target=50):
    # Softer resident-60% target: NRI books often run lower equity by design
    return max(0, 100 - abs(equity_pct - target) * 1.6)


def score_concentration(top5_pct):
    if top5_pct <= 35: return 100
    if top5_pct >= 80: return 0
    return 100 - (top5_pct - 35) / 45 * 100


def score_liquidity_nri(true_liquid_pct):
    # Adequate deployable liquidity for NRI: ~12–35% of NW in liquid MF + near maturities
    if 12 <= true_liquid_pct <= 35: return 100
    if true_liquid_pct < 12: return max(0, 100 - (12 - true_liquid_pct) * 5)
    return max(0, 100 - (true_liquid_pct - 35) * 1.5)


def score_diversification(mf_df):
    if mf_df.empty:
        return 50
    cat = mf_df.groupby("Category")["Current Value"].sum()
    if cat.sum() == 0:
        return 50
    hhi = ((cat / cat.sum()) ** 2).sum()
    return min(100, max(0, (1 - hhi) * 100 / 0.85))


def score_performance(mf_df):
    """
    Phase 2B — value-weighted beat rate vs Nifty50 1Y.
    A ₹50L fund that beats the index counts far more than a ₹50k fund.
    Falls back to equal-weight if Current Value is missing.
    """
    if mf_df is None or mf_df.empty:
        return 60.0
    need = ["1Y %", "vs Nifty50 1Y"]
    if not all(c in mf_df.columns for c in need):
        return 60.0
    valid = mf_df.dropna(subset=need).copy()
    if valid.empty:
        return 60.0
    beat = (valid["1Y %"] > valid["vs Nifty50 1Y"]).astype(float)
    if "Current Value" in valid.columns:
        w = pd.to_numeric(valid["Current Value"], errors="coerce").fillna(0.0)
        wsum = float(w.sum())
        if wsum > 0:
            return float((beat * w).sum() / wsum * 100.0)
    return float(beat.mean() * 100.0)