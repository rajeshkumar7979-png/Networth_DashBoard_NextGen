from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from lib.config import DATA_DIR, HISTORY_PATH, TODAY_STR

COLS = ["date", "net_worth", "equity_pct", "fd_pct", "pnl", "health_score"]
PORTFOLIO_HISTORY_PATH = DATA_DIR / "portfolio_history.csv"

PORTFOLIO_COLS = [
    "date",
    "mf_current_inr",
    "mf_invested_inr",
    "schemes_priced",
    "schemes_missing_nav",
    "stocks_current_inr",
    "stocks_invested_inr",
    "fd_current_inr",
    "fd_principal_inr",
    "total_assets_inr",
    "total_invested_inr",
    "note",
]


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=COLS)
    df = df.copy()
    df["date"] = df["date"].astype(str)
    df = df[df["date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]
    for c in COLS[1:]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["net_worth"])
    return df.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)


def load_history() -> pd.DataFrame:
    _ensure_dir()
    if not HISTORY_PATH.exists():
        return pd.DataFrame(columns=COLS)
    try:
        return _clean(pd.read_csv(HISTORY_PATH))
    except Exception:
        return pd.DataFrame(columns=COLS)


def load_portfolio_history(path: Path | None = None) -> pd.DataFrame:
    """Durable daily book snapshot written by the holdings refresh job."""
    target = path or PORTFOLIO_HISTORY_PATH
    if not target.exists():
        return pd.DataFrame(columns=PORTFOLIO_COLS)
    try:
        df = pd.read_csv(target)
    except Exception:
        return pd.DataFrame(columns=PORTFOLIO_COLS)
    if df is None or df.empty:
        return pd.DataFrame(columns=PORTFOLIO_COLS)
    df = df.copy()
    df["date"] = df["date"].astype(str)
    df = df[df["date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]
    for col in PORTFOLIO_COLS:
        if col in ("date", "note"):
            continue
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)


def portfolio_history_delta(df: pd.DataFrame | None = None) -> dict:
    """Latest vs prior totals from the committed portfolio history."""
    hist = df if df is not None else load_portfolio_history()
    if hist is None or hist.empty or "total_assets_inr" not in hist.columns:
        return {"ok": False, "reason": "No portfolio history rows yet."}
    usable = hist.dropna(subset=["total_assets_inr"])
    if usable.empty:
        # Fall back to MF-only rows from before full-book columns existed.
        if "mf_current_inr" not in hist.columns:
            return {"ok": False, "reason": "No valued history rows yet."}
        usable = hist.dropna(subset=["mf_current_inr"])
        if usable.empty:
            return {"ok": False, "reason": "No valued history rows yet."}
        latest = usable.iloc[-1]
        prior = usable.iloc[-2] if len(usable) >= 2 else None
        out = {
            "ok": True,
            "date": str(latest["date"]),
            "total_assets": float(latest["mf_current_inr"] or 0),
            "mf_current": float(latest["mf_current_inr"] or 0),
            "scope": "mf_only",
        }
        if prior is not None:
            out["prior_date"] = str(prior["date"])
            out["prior_total"] = float(prior["mf_current_inr"] or 0)
            out["delta"] = out["total_assets"] - out["prior_total"]
        return out
    latest = usable.iloc[-1]
    prior = usable.iloc[-2] if len(usable) >= 2 else None
    out = {
        "ok": True,
        "date": str(latest["date"]),
        "total_assets": float(latest.get("total_assets_inr") or 0),
        "total_invested": float(latest["total_invested_inr"]) if pd.notna(latest.get("total_invested_inr")) else None,
        "mf_current": float(latest["mf_current_inr"]) if pd.notna(latest.get("mf_current_inr")) else None,
        "stocks_current": float(latest["stocks_current_inr"]) if pd.notna(latest.get("stocks_current_inr")) else None,
        "fd_current": float(latest["fd_current_inr"]) if pd.notna(latest.get("fd_current_inr")) else None,
        "scope": "full_book",
    }
    if prior is not None and pd.notna(prior.get("total_assets_inr")):
        out["prior_date"] = str(prior["date"])
        out["prior_total"] = float(prior["total_assets_inr"] or 0)
        out["delta"] = out["total_assets"] - out["prior_total"]
    return out


def render_portfolio_history(st_module=None) -> pd.DataFrame:
    """Show the committed daily book trend (MF + stocks + FD when present)."""
    ui = st_module or st
    hist = load_portfolio_history()
    if hist.empty:
        ui.caption("No committed portfolio_history.csv rows yet. The daily holdings job writes them.")
        return hist
    delta = portfolio_history_delta(hist)
    if delta.get("ok"):
        bits = [f"Latest {delta['date']}: ₹{delta['total_assets']:,.0f}"]
        if delta.get("delta") is not None and delta.get("prior_date"):
            sign = "+" if delta["delta"] >= 0 else ""
            bits.append(f"vs {delta['prior_date']} {sign}₹{delta['delta']:,.0f}")
        if delta.get("scope") == "mf_only":
            bits.append("(MF-only rows; full-book columns start after the history upgrade)")
        ui.caption(" · ".join(bits))
    chart_cols = [c for c in (
        "total_assets_inr", "mf_current_inr", "stocks_current_inr", "fd_current_inr",
    ) if c in hist.columns and hist[c].notna().any()]
    if chart_cols:
        plot = hist.set_index("date")[chart_cols].copy()
        plot = plot.rename(columns={
            "total_assets_inr": "Total assets",
            "mf_current_inr": "MF",
            "stocks_current_inr": "Stocks",
            "fd_current_inr": "FD",
        })
        ui.line_chart(plot, height=260)
    show_cols = [c for c in PORTFOLIO_COLS if c in hist.columns]
    ui.dataframe(hist[show_cols].tail(14), hide_index=True, use_container_width=True)
    ui.caption(
        "Source: data/portfolio_history.csv committed by GitHub Actions. "
        "MF = units × AMFI NAV. Stocks = invested basis in the daily job. "
        "FD = available or principal. Not a full P&L ledger."
    )
    return hist


def log_snapshot(
    net_worth: float,
    equity_pct: float,
    fd_pct: float,
    pnl: float,
    health_score: float,
) -> pd.DataFrame:
    """Upsert today's row. Still uses local file — ephemeral on Streamlit Cloud.
    Swap body later for Google Sheet / Supabase without changing callers.
    """
    _ensure_dir()
    row = {
        "date": TODAY_STR,
        "net_worth": float(net_worth),
        "equity_pct": float(equity_pct),
        "fd_pct": float(fd_pct),
        "pnl": float(pnl),
        "health_score": round(float(health_score), 1),
    }
    hist = load_history()
    hist = hist[hist["date"] != TODAY_STR]
    hist = pd.concat([hist, pd.DataFrame([row])], ignore_index=True)
    hist = _clean(hist)
    try:
        hist.to_csv(HISTORY_PATH, index=False)
    except Exception as e:
        st.warning(f"Could not write history: {e}")
    return hist


def merge_uploaded(csv_file) -> pd.DataFrame:
    incoming = pd.read_csv(csv_file)
    if "date" not in incoming.columns or "net_worth" not in incoming.columns:
        raise ValueError("CSV must have at least date and net_worth columns.")
    existing = load_history()
    merged = pd.concat([existing, incoming], ignore_index=True)
    merged = _clean(merged)
    merged.to_csv(HISTORY_PATH, index=False)
    return merged
