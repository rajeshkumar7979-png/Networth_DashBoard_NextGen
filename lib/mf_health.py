import requests
import pandas as pd
import streamlit as st
from datetime import timedelta, datetime
import re
import os
import json

HOLDINGS_CACHE_PATH = "data/mf_holdings_cache.json"


# ---------- NAV history (fallback only — used only when Command Center didn't ----------
# ---------- already compute returns for this fund, e.g. Liquid/debt-like funds) ----------
@st.cache_data(ttl=21600, show_spinner=False)
def get_nav_history(scheme_code: int):
    """Same source + same permissive parse as Command Center's get_mf_nav_history."""
    try:
        r = requests.get(f"https://api.mfapi.in/mf/{int(scheme_code)}", timeout=12)
        r.raise_for_status()
        payload = r.json()
        data = payload.get("data") or []
        if not data:
            return pd.DataFrame(), payload.get("meta", {})
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
        df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
        df = df.dropna().sort_values("date")
        if df.empty:
            return pd.DataFrame(), payload.get("meta", {})
        return df, payload.get("meta", {})
    except Exception:
        return pd.DataFrame(), {}


def calc_cagr(start_nav, end_nav, years):
    if start_nav <= 0 or years <= 0:
        return None
    return (end_nav / start_nav) ** (1 / years) - 1


def max_drawdown(nav_series):
    if len(nav_series) < 5:
        return None
    peak = nav_series.cummax()
    dd = (nav_series - peak) / peak
    val = float(dd.min())
    if val < -0.80:
        return None  # treat as bad data rather than display a false extreme
    return val


def compute_metrics(nav_df: pd.DataFrame):
    if nav_df.empty or len(nav_df) < 10:
        return {}
    nav_df = nav_df.sort_values("date")
    latest = nav_df.iloc[-1]
    end_nav, end_date = latest["nav"], latest["date"]
    metrics = {"latest_nav": end_nav, "latest_date": end_date.strftime("%Y-%m-%d")}
    for years, label in [(1, "1Y"), (3, "3Y"), (5, "5Y")]:
        target = end_date - timedelta(days=int(365.25 * years))
        past = nav_df[nav_df["date"] <= target]
        metrics[f"cagr_{label}"] = calc_cagr(past.iloc[-1]["nav"], end_nav, years) if not past.empty else None
    metrics["max_drawdown"] = max_drawdown(nav_df["nav"])
    return metrics


def simple_health_score(metrics, weight_pct=0):
    score = 55
    cagr3 = metrics.get("cagr_3Y")
    if cagr3 is not None:
        if cagr3 > 0.15:
            score += 15
        elif cagr3 > 0.10:
            score += 8
        elif cagr3 < 0.05:
            score -= 12
    dd = metrics.get("max_drawdown")
    if dd is not None:
        if dd < -0.40:
            score -= 20
        elif dd < -0.30:
            score -= 12
        elif dd > -0.18:
            score += 6
    if weight_pct > 25:
        score -= 15
    elif weight_pct > 15:
        score -= 8
    return max(0, min(100, int(score)))
