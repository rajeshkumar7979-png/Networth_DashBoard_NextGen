# -------------------------------------------------
# Honest holding-level returns. Pure. No network. No Streamlit.
#
# The workbook stores one purchase record per line (date, units, invested).
# It is NOT a transaction ledger. These four numbers answer four different
# questions and must never be labelled as each other:
#
#   simple ROI %     — how much the line is up/down vs book cost
#   lump-sum ann. %  — that ROI, annualized, *if* there was one buy
#   trailing CAGR %  — how the *scheme/index NAV* moved over N years
#   rolling CAGR %   — the same NAV path, many trailing windows
#
# True multi-cashflow XIRR needs SIP/sell/dividend dates. Reconstructing
# those from NAV is forbidden (SPEC R-403). Missing stays missing.
# -------------------------------------------------
from __future__ import annotations

from datetime import date, datetime

import pandas as pd

SIMPLE_ROI_LABEL = (
    "Simple ROI % = (current − invested) / invested from the single purchase "
    "record. Not annualized. Not a multi-cashflow XIRR."
)
LUMP_SUM_ANN_LABEL = (
    "Lump-sum annualized % = (current / invested) ** (365.25 / days held) − 1. "
    "Equals XIRR only if there was one buy on Purchase Date and no SIP, sell, "
    "or dividend. The workbook has no transaction history — SIPs are not invented."
)
TRAILING_CAGR_LABEL = (
    "Trailing CAGR is the scheme (or index) NAV path over the last N years "
    "(N × 365.25 from the latest NAV). It is the fund's ride, not yours."
)
ROLLING_CAGR_LABEL = (
    "Rolling N-year CAGR is the same NAV path measured on many end-dates. "
    "It is a scheme statistic. It is not your personal return."
)
MULTI_CASHFLOW_XIRR_GAP = (
    "True XIRR (SIPs, sells, dividends) needs a transaction file. "
    "Not in the workbook. Shown as no data — never reconstructed from NAV."
)

_MIN_DAYS_FOR_ANN = 30


def _finite(value):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    return n


def _as_timestamp(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return pd.Timestamp(value).normalize()
    if isinstance(value, date) and not isinstance(value, datetime):
        return pd.Timestamp(value)
    ts = pd.to_datetime(value, errors="coerce")
    if ts is None or pd.isna(ts):
        return None
    return pd.Timestamp(ts).normalize()


def holding_period_days(purchase, as_of):
    """Calendar days from purchase date to as-of. None if either date is missing."""
    start = _as_timestamp(purchase)
    end = _as_timestamp(as_of)
    if start is None or end is None:
        return None
    days = int((end - start).days)
    if days < 0:
        return None
    return days


def simple_roi_pct(current, invested):
    """(current − invested) / invested × 100. None when invested is missing/≤0."""
    cur = _finite(current)
    inv = _finite(invested)
    if cur is None or inv is None or inv <= 0:
        return None
    return (cur - inv) / inv * 100.0


def lump_sum_annualized_pct(current, invested, days_held, min_days=_MIN_DAYS_FOR_ANN):
    """Annualize a single buy. None when the holding is too young or inputs fail.

    This is the XIRR of exactly two cashflows: −invested at purchase, +current
    today. It is *not* true XIRR if the line was built by SIPs.
    """
    cur = _finite(current)
    inv = _finite(invested)
    days = _finite(days_held)
    if cur is None or inv is None or days is None:
        return None
    if inv <= 0 or cur <= 0 or days < min_days:
        return None
    return ((cur / inv) ** (365.25 / days) - 1.0) * 100.0


def trailing_cagr_pct(hist_df, years):
    """NAV trailing CAGR over `years`, matching Command Center trailing_return.

    hist_df needs columns date, nav, sorted ascending. Returns percent, or None
    when the window is shorter than the requested years.
    """
    years = _finite(years)
    if years is None or years <= 0:
        return None
    if hist_df is None or getattr(hist_df, "empty", True):
        return None
    if "date" not in hist_df.columns or "nav" not in hist_df.columns:
        return None
    frame = hist_df[["date", "nav"]].dropna().sort_values("date")
    if frame.empty:
        return None
    latest_date, latest_nav = frame["date"].iloc[-1], _finite(frame["nav"].iloc[-1])
    if latest_nav is None or latest_nav <= 0:
        return None
    target = latest_date - pd.Timedelta(days=int(years * 365.25))
    past = frame[frame["date"] <= target]
    if past.empty:
        return None
    past_nav = _finite(past["nav"].iloc[-1])
    if past_nav is None or past_nav <= 0:
        return None
    return ((latest_nav / past_nav) ** (1.0 / years) - 1.0) * 100.0


def rolling_cagr_pct(hist_df, window_years, step_days=21):
    """List of (end_date, cagr_pct) for each window of `window_years`.

    Empty list — never zeros — when history is too short. step_days=21 ≈ one
    trading month so a 5-year series stays bounded.
    """
    years = _finite(window_years)
    if years is None or years <= 0:
        return []
    if hist_df is None or getattr(hist_df, "empty", True):
        return []
    if "date" not in hist_df.columns or "nav" not in hist_df.columns:
        return []
    frame = hist_df[["date", "nav"]].dropna().sort_values("date").reset_index(drop=True)
    if len(frame) < 10:
        return []
    window = pd.Timedelta(days=int(years * 365.25))
    step = max(int(step_days or 21), 1)
    out = []
    for i in range(len(frame) - 1, -1, -step):
        end = frame.iloc[i]
        end_nav = _finite(end["nav"])
        if end_nav is None or end_nav <= 0:
            continue
        target = end["date"] - window
        past = frame[frame["date"] <= target]
        if past.empty:
            break
        past_nav = _finite(past["nav"].iloc[-1])
        if past_nav is None or past_nav <= 0:
            continue
        cagr = ((end_nav / past_nav) ** (1.0 / years) - 1.0) * 100.0
        out.append((pd.Timestamp(end["date"]), cagr))
    out.reverse()
    return out
