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
    "gold_current_inr",
    "gold_invested_inr",
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
    # Drop accidental re-header rows and non-dates
    df["date"] = df["date"].astype(str).str.strip()
    df = df[df["date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]
    for col in list(df.columns):
        if col in ("date", "note", "stocks_mark"):
            continue
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)


def row_data_quality(row: pd.Series) -> str:
    """Label rows so NAV-parse gaps are not mistaken for real zero value."""
    priced = row.get("schemes_priced")
    missing = row.get("schemes_missing_nav")
    mf = row.get("mf_current_inr")
    try:
        priced_n = int(priced) if pd.notna(priced) else 0
    except (TypeError, ValueError):
        priced_n = 0
    try:
        missing_n = int(missing) if pd.notna(missing) else 0
    except (TypeError, ValueError):
        missing_n = 0
    mf_n = float(mf) if pd.notna(mf) else None
    if priced_n == 0 and missing_n > 0 and (mf_n is None or mf_n == 0.0):
        return "NAV_PARSE_GAP"
    if missing_n > 0 and priced_n > 0:
        return "PARTIAL_NAV"
    if row.get("total_assets_inr") is None or (isinstance(row.get("total_assets_inr"), float) and pd.isna(row.get("total_assets_inr"))):
        if mf_n is not None:
            return "MF_ONLY"
        return "INCOMPLETE"
    return "OK"


def portfolio_history_delta(df: pd.DataFrame | None = None) -> dict:
    """Latest vs prior *trusted* totals (skips NAV_PARSE_GAP rows)."""
    hist = df if df is not None else load_portfolio_history()
    if hist is None or hist.empty:
        return {"ok": False, "reason": "No portfolio history rows yet."}
    hist = hist.copy()
    hist["_quality"] = hist.apply(row_data_quality, axis=1)
    trusted = hist[hist["_quality"].isin({"OK", "PARTIAL_NAV", "MF_ONLY"})].copy()
    if trusted.empty:
        return {"ok": False, "reason": "No trusted history rows yet (only NAV-gap zeros)."}

    if "total_assets_inr" in trusted.columns and trusted["total_assets_inr"].notna().any():
        usable = trusted.dropna(subset=["total_assets_inr"])
        scope = "full_book"
        value_col = "total_assets_inr"
    else:
        usable = trusted.dropna(subset=["mf_current_inr"])
        scope = "mf_only"
        value_col = "mf_current_inr"
    if usable.empty:
        return {"ok": False, "reason": "No valued trusted history rows yet."}

    latest = usable.iloc[-1]
    prior = usable.iloc[-2] if len(usable) >= 2 else None
    out = {
        "ok": True,
        "date": str(latest["date"]),
        "total_assets": float(latest[value_col] or 0),
        "mf_current": float(latest["mf_current_inr"]) if pd.notna(latest.get("mf_current_inr")) else None,
        "stocks_current": float(latest["stocks_current_inr"]) if pd.notna(latest.get("stocks_current_inr")) else None,
        "fd_current": float(latest["fd_current_inr"]) if pd.notna(latest.get("fd_current_inr")) else None,
        "total_invested": float(latest["total_invested_inr"]) if pd.notna(latest.get("total_invested_inr")) else None,
        "scope": scope,
        "quality": row_data_quality(latest),
    }
    if prior is not None and pd.notna(prior.get(value_col)):
        out["prior_date"] = str(prior["date"])
        out["prior_total"] = float(prior[value_col] or 0)
        out["delta"] = out["total_assets"] - out["prior_total"]
    return out


def render_portfolio_history(st_module=None) -> pd.DataFrame:
    """Show the committed daily book trend; never chart NAV-gap zeros as real value."""
    ui = st_module or st
    hist = load_portfolio_history()
    if hist.empty:
        ui.caption("No committed portfolio_history.csv rows yet. The daily holdings job writes them.")
        return hist

    hist = hist.copy()
    hist["data_quality"] = hist.apply(row_data_quality, axis=1)
    gap_n = int((hist["data_quality"] == "NAV_PARSE_GAP").sum())

    delta = portfolio_history_delta(hist)
    if delta.get("ok"):
        bits = [f"Latest trusted {delta['date']}: ₹{delta['total_assets']:,.0f}"]
        if delta.get("delta") is not None and delta.get("prior_date"):
            sign = "+" if delta["delta"] >= 0 else ""
            bits.append(f"vs trusted {delta['prior_date']} {sign}₹{delta['delta']:,.0f}")
        if delta.get("scope") == "mf_only":
            bits.append("(MF-only trusted rows)")
        ui.caption(" · ".join(bits))
    else:
        ui.caption(delta.get("reason") or "No trusted history yet.")

    if gap_n:
        ui.caption(
            f"{gap_n} day(s) labelled NAV_PARSE_GAP (MF marked 0 because AMFI parse failed). "
            "Those days are kept in the audit table but excluded from the trend chart."
        )

    chart_src = hist[hist["data_quality"] != "NAV_PARSE_GAP"].copy()
    chart_cols = [c for c in (
        "total_assets_inr", "mf_current_inr", "stocks_current_inr", "gold_current_inr", "fd_current_inr",
    ) if c in chart_src.columns and chart_src[c].notna().any()]
    if chart_cols and not chart_src.empty:
        plot = chart_src.set_index("date")[chart_cols].copy()
        plot = plot.rename(columns={
            "total_assets_inr": "Total assets",
            "mf_current_inr": "MF",
            "stocks_current_inr": "Equity stocks",
            "gold_current_inr": "Gold",
            "fd_current_inr": "FD",
        })
        ui.line_chart(plot, height=260)
    else:
        ui.caption("No trusted rows to chart yet.")

    # Day-over-day on trusted full-book rows only
    trusted = hist[hist["data_quality"].isin({"OK", "PARTIAL_NAV"})].copy()
    if len(trusted) >= 2 and "total_assets_inr" in trusted.columns:
        trusted = trusted.dropna(subset=["total_assets_inr"]).sort_values("date")
        if len(trusted) >= 2:
            dod = trusted[["date", "total_assets_inr", "mf_current_inr", "stocks_current_inr", "gold_current_inr", "fd_current_inr"]].copy()
            for col in ("total_assets_inr", "mf_current_inr", "stocks_current_inr", "gold_current_inr", "fd_current_inr"):
                if col in dod.columns:
                    dod[f"d_{col}"] = dod[col].diff()
            view = pd.DataFrame({
                "Date": dod["date"],
                "Total ₹": dod["total_assets_inr"].round(0),
                "Δ Total": dod["d_total_assets_inr"].round(0),
                "MF ₹": dod.get("mf_current_inr"),
                "Δ MF": dod.get("d_mf_current_inr"),
                "Stocks ₹": dod.get("stocks_current_inr"),
                "Gold ₹": dod.get("gold_current_inr"),
                "FD ₹": dod.get("fd_current_inr"),
            })
            ui.caption("Day-over-day (trusted full-book rows only — NAV_PARSE_GAP excluded)")
            ui.dataframe(view.tail(10), hide_index=True, use_container_width=True)

    show_cols = [c for c in (["data_quality"] + PORTFOLIO_COLS) if c in hist.columns or c == "data_quality"]
    ui.caption("Audit table (includes gap days for forensics)")
    ui.dataframe(hist[show_cols].tail(14), hide_index=True, use_container_width=True)
    ui.caption(
        "Source: data/portfolio_history.csv committed by GitHub Actions daily job. "
        "MF = units × AMFI NAV. Equity stocks = Yahoo LTP or invested fallback. "
        "Gold = SGB/gold ETF (gold_current_inr). FD = available or ROI-accrued principal (USD × USDINR). "
        "NAV_PARSE_GAP = parser wrote zeros that day — not a real crash; excluded from charts and Δ. "
        "Command Center remains live truth; history is the durable trend."
    )
    return hist


def log_snapshot(
    net_worth: float,
    equity_pct: float,
    fd_pct: float,
    pnl: float,
    health_score: float,
) -> pd.DataFrame:
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
