import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import feedparser
from datetime import datetime, timedelta
import pytz
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import re
import time
from lib.formatters import safe_float, format_inr_indian, format_inr, format_inr_compact
from lib.portfolio import load_excel as load_data
from lib.valuation import _safe_maturity_amount, compute_fd_current_native, compute_fcnr_attribution
from lib.gold import (
    DEBT_LIKE,
    SGB_TICKER_PATTERN,
    is_gold_symbol,
    is_gold_fund,
    infer_category,
)
from lib.scoring import (
    score_allocation,
    score_concentration,
    score_liquidity_nri,
    score_diversification,
    score_performance,
)
from lib.register import (
    ASSET_CLASSES,
    aggregate_by_class,
    aggregate_by_member,
    build_asset_register,
    family_level_sum,
    NonUniqueKeyError,
)
from lib.ledger import net_worth as compute_net_worth
from lib.drivers import (
    DRIVER_KEYS,
    NOT_A_CASHFLOW_LABEL,
    class_pnl_from_register,
    decompose_current,
    snapshot_delta,
)
from lib import snapshot as snapshot_io
from lib.intelligence import exposure as intel_exposure
from lib.intelligence import evidence as intel_evidence
from lib.intelligence import signals as intel_signals
from lib.intelligence import research as intel_research
from lib.intelligence import live as intel_live
from lib.intelligence import ai as intel_ai
from lib.intelligence.portfolio_brain import build_briefing as intel_build_briefing
from lib.intelligence.provider import DeterministicProvider as DeterministicIntelProvider
from lib.intelligence.sources import gateway_status as intel_gateway_status
from lib.intelligence.sources import mapping as intel_mapping
from lib.intelligence.sources import mf as intel_mf
from lib import theme
from lib.ui import (
    page_header_html as ui_page_header,
    section_header_html as ui_section,
    pill as ui_badge,
    status_pill as ui_pill,
    stacked_bar as ui_alloc_bar,
    caption as ui_caption,
    empty_state as ui_empty,
    banner as ui_banner,
    hero_metrics as ui_hero,
    kpi_cards as ui_kpi_cards,
    watchlist as ui_watch,
    research_row as ui_research_row,
    research_grid as ui_research_grid,
    unavailable as ui_unavailable,
    evidence_trail as ui_evidence,
)
IST = pytz.timezone("Asia/Kolkata")
now_ist = datetime.now(IST)
TODAY_NAIVE = pd.Timestamp(now_ist.date())
HISTORY_PATH = "data/history.csv"
AMFI_CACHE_PATH = "data/amfi_nav_cache.json"

# -------------------------------------------------
# THEME — one shared design system (lib.theme + lib.ui). R-1701.
# Collapse Streamlit header so title isn't eaten on mobile Chrome/iOS.
# No page-local <style> blocks.
# -------------------------------------------------
theme.inject_css()

def to_naive_ts(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    ts = pd.Timestamp(x)
    return ts.tz_localize(None) if ts.tzinfo is not None else ts

# -------------------------------------------------
# DATA SOURCES
# -------------------------------------------------
def _parse_amfi_text(text: str):
    # AMFI format (2024+): SchemeCode;ISIN_G;ISIN_D;Name;Plan;Option;NAV;Date  (8 cols)
    # Older format:         SchemeCode;ISIN_G;ISIN_D;Name;NAV;Date                 (6 cols)
    # Prefer index 6 (new), fall back to index 4 (old).
    nav_dict, code_dict, name_dict = {}, {}, {}
    for line in text.splitlines():
        parts = line.split(";")
        if len(parts) < 5 or not parts[0].strip().isdigit():
            continue
        code = parts[0].strip()
        isin_g, isin_d = parts[1].strip(), parts[2].strip()
        name = parts[3].strip()
        nav = None
        for idx in (6, 4):
            if len(parts) > idx:
                try:
                    nav = float(parts[idx].strip())
                    break
                except Exception:
                    continue
        if nav is None:
            continue
        for isin in (isin_g, isin_d):
            if isin and isin != "-" and len(isin) > 8:
                nav_dict[isin] = nav
                code_dict[isin] = code
                name_dict[isin] = name
    return nav_dict, code_dict, name_dict

def _save_amfi_cache(nav_dict, code_dict, name_dict):
    try:
        os.makedirs("data", exist_ok=True)
        import json
        payload = {
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "nav": nav_dict,
            "code": code_dict,
            "name": name_dict,
        }
        with open(AMFI_CACHE_PATH, "w") as f:
            json.dump(payload, f)
    except Exception:
        pass

def _load_amfi_cache():
    try:
        import json
        if not os.path.exists(AMFI_CACHE_PATH):
            return None
        with open(AMFI_CACHE_PATH) as f:
            payload = json.load(f)
        nav = payload.get("nav") or {}
        if not nav:
            return None
        return nav, payload.get("code") or {}, payload.get("name") or {}, payload.get("saved_at", "unknown")
    except Exception:
        return None

@st.cache_data(ttl=3600)
def get_amfi_data():
    # NAV updates once a day. Live fetch + disk fallback so a blocked cloud IP
    # still serves yesterday's file instead of zeroing every fund.
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/plain,*/*",
    }
    urls = [
        "https://www.amfiindia.com/spages/NAVAll.txt",
        "https://portal.amfiindia.com/spages/NAVAll.txt",
    ]
    for attempt in range(2):
        for url in urls:
            try:
                r = requests.get(url, headers=headers, timeout=20)
                r.raise_for_status()
                if len(r.text) < 1000:
                    continue
                nav_dict, code_dict, name_dict = _parse_amfi_text(r.text)
                if nav_dict:
                    _save_amfi_cache(nav_dict, code_dict, name_dict)
                    return nav_dict, code_dict, name_dict, None  # None = live
            except Exception:
                continue
        if attempt == 0:
            time.sleep(1.5)
    cached = _load_amfi_cache()
    if cached:
        nav_dict, code_dict, name_dict, saved_at = cached
        return nav_dict, code_dict, name_dict, saved_at  # disk fallback
    return {}, {}, {}, None

@st.cache_data(ttl=21600, show_spinner=False)
def get_mf_nav_history(scheme_code: str):
    try:
        r = requests.get(f"https://api.mfapi.in/mf/{scheme_code}", timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return None
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
        df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
        df = df.dropna().sort_values("date")
        return df if not df.empty else None
    except Exception:
        return None

@st.cache_data(ttl=3600)
def get_nifty_history():
    try:
        hist = yf.Ticker("^NSEI").history(period="5y")
        if hist.empty:
            return None
        df = hist[["Close"]].rename(columns={"Close": "nav"}).reset_index().rename(columns={"Date": "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        return df
    except Exception:
        return None

TROY_OZ_G = 31.1034768  # grams per troy ounce

@st.cache_data(ttl=900, show_spinner=False)
def get_market_pulse_yf(ticker: str):
    """Last close + day change. Ignores absurd gaps (halved contract, empty sessions)."""
    try:
        hist = yf.Ticker(ticker).history(period="15d")
        if hist.empty:
            return None
        closes = hist["Close"].dropna()
        if len(closes) < 1:
            return None
        latest = float(closes.iloc[-1])
        change_pct = None
        if len(closes) >= 2:
            prev = float(closes.iloc[-2])
            if prev > 0:
                raw = (latest / prev - 1) * 100
                if abs(raw) <= 20:
                    change_pct = raw
                elif len(closes) >= 3:
                    prev2 = float(closes.iloc[-3])
                    if prev2 > 0:
                        change_pct = (latest / prev2 - 1) * 100
                        if abs(change_pct) > 20:
                            change_pct = None
        return {"value": latest, "change_pct": change_pct}
    except Exception:
        return None

@st.cache_data(ttl=86400, show_spinner=False)
def get_ath_pct(ticker: str):
    """% below all-time high (daily close). Free Yahoo history."""
    try:
        hist = yf.Ticker(ticker).history(period="max")
        if hist.empty:
            return None
        closes = hist["Close"].dropna()
        if closes.empty:
            return None
        ath = float(closes.max())
        latest = float(closes.iloc[-1])
        if ath <= 0:
            return None
        return (latest / ath - 1) * 100
    except Exception:
        return None

@st.cache_data(ttl=900, show_spinner=False)
def get_india_gold_10g():
    """INR per 10g pure gold from goldprice.dev XAU-INR spot (free, no key)."""
    try:
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        r = requests.get(
            "https://api.goldprice.dev/v1/prices?symbol=XAU-INR-SPOT",
            headers=headers, timeout=12,
        )
        r.raise_for_status()
        price_oz = float(r.json()["symbols"][0]["price"])
        per_10g = price_oz / TROY_OZ_G * 10.0
        # day change: compare vs Yahoo GC=F move as proxy when prior INR not stored
        chg = None
        y = get_market_pulse_yf("GC=F")
        if y:
            chg = y["change_pct"]
        return {"value": per_10g, "change_pct": chg}
    except Exception:
        # fallback: COMEX oz * USDINR → INR/10g
        try:
            g = get_market_pulse_yf("GC=F")
            fx = get_market_pulse_yf("INR=X")
            if g and fx:
                per_10g = g["value"] / TROY_OZ_G * 10.0 * fx["value"]
                return {"value": per_10g, "change_pct": g["change_pct"]}
        except Exception:
            pass
        return None

@st.cache_data(ttl=900, show_spinner=False)
def get_india_silver_kg():
    """INR per kg silver via COMEX SI=F * USD/INR."""
    try:
        s = get_market_pulse_yf("SI=F")
        fx = get_market_pulse_yf("INR=X")
        if not s or not fx:
            return None
        per_kg = s["value"] / TROY_OZ_G * 1000.0 * fx["value"]
        return {"value": per_kg, "change_pct": s["change_pct"]}
    except Exception:
        return None

def build_market_pulse_rows():
    """India indices, INR metals, global, FX — with ATH% where Yahoo max history is free."""
    rows = []
    # (label, fetcher, fmt, yf_ticker_for_ath or None)
    specs = [
        ("NIFTY 50", lambda: get_market_pulse_yf("^NSEI"), "{:,.2f}", "^NSEI"),
        ("SENSEX", lambda: get_market_pulse_yf("^BSESN"), "{:,.2f}", "^BSESN"),
        ("GOLD ₹/10g", lambda: get_india_gold_10g(), "{:,.0f}", "GC=F"),
        ("SILVER ₹/kg", lambda: get_india_silver_kg(), "{:,.0f}", "SI=F"),
        ("BRENT OIL", lambda: get_market_pulse_yf("BZ=F"), "{:,.2f}", "BZ=F"),
        ("S&P 500", lambda: get_market_pulse_yf("^GSPC"), "{:,.2f}", "^GSPC"),
        ("NASDAQ", lambda: get_market_pulse_yf("^IXIC"), "{:,.2f}", "^IXIC"),
        ("USD/INR", lambda: get_market_pulse_yf("INR=X"), "{:,.2f}", None),
    ]
    for label, fetcher, fmt, ath_ticker in specs:
        d = fetcher()
        ath = get_ath_pct(ath_ticker) if ath_ticker else None
        if d and d.get("value") is not None:
            rows.append({"Market": label, "Value": d["value"], "Chg %": d.get("change_pct"), "ATH %": ath, "fmt": fmt})
        else:
            rows.append({"Market": label, "Value": None, "Chg %": None, "ATH %": ath, "fmt": fmt})
    return rows


def style_money_df(df, pnl_cols=("P&L", "Return %", "FX Gain/Loss (INR)")):
    """Color positive/negative P&L columns for holdings tables."""
    if df is None or df.empty:
        return df
    cols = [c for c in pnl_cols if c in df.columns]
    if not cols:
        return df
    def _clr(v):
        try:
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return ""
            return "color: #22c55e" if float(v) >= 0 else "color: #ef4444"
        except Exception:
            return ""
    try:
        return df.style.map(_clr, subset=cols)
    except Exception:
        return df

def trailing_return(hist_df, years):
    if hist_df is None or hist_df.empty:
        return None
    latest_date, latest_nav = hist_df["date"].iloc[-1], hist_df["nav"].iloc[-1]
    target_date = latest_date - pd.Timedelta(days=int(years * 365.25))
    past = hist_df[hist_df["date"] <= target_date]
    if past.empty or latest_nav <= 0:
        return None
    past_nav = past.iloc[-1]["nav"]
    return None if past_nav <= 0 else ((latest_nav / past_nav) ** (1 / years) - 1) * 100

@st.cache_data(ttl=300)
def get_usd_inr():
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=INR", timeout=8)
        return float(r.json()["rates"]["INR"])
    except Exception:
        return None  # FIXED: no more silent 95.5 fallback — see integrity check below

# NEW — Phase 2 (FCNR audit): historical FX rate as of a specific deposit
# date, so a USD FD's INR cost basis reflects the rate on the day it was
# actually funded, not today's rate. Without this, "Principal (INR)" was
# silently computed with today's FX for BOTH the cost basis and the current
# value, which mathematically erases any FX gain/loss from the P&L — a real
# NRI's rupee depreciation gain over a multi-year FCNR deposit was invisible.
@st.cache_data(ttl=86400, show_spinner=False)
def get_historical_usd_inr(date_str: str):
    try:
        r = requests.get(f"https://api.frankfurter.app/{date_str}?from=USD&to=INR", timeout=8)
        r.raise_for_status()
        rates = r.json().get("rates", {})
        return rates.get("INR")
    except Exception:
        return None

@st.cache_data(ttl=300, show_spinner=False)
def get_groww_ltp(nse_symbol: str):
    """Live LTP from Groww free NSE CASH endpoint (equities + SGBs)."""
    if not nse_symbol:
        return None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        r = requests.get(
            f"https://groww.in/v1/api/stocks_data/v1/tr_live_prices/exchange/NSE/segment/CASH/{nse_symbol}/latest",
            headers=headers, timeout=10,
        )
        r.raise_for_status()
        ltp = r.json().get("ltp")
        if ltp is not None and float(ltp) > 0:
            return float(ltp)
    except Exception:
        pass
    return None

@st.cache_data(ttl=300)
def get_stock_price(symbol: str):
    if not symbol:
        return None
    # Prefer Groww live LTP; fall back to Yahoo last close
    price = get_groww_ltp(symbol)
    if price is not None:
        return price
    try:
        t = yf.Ticker(f"{symbol}.NS")
        hist = t.history(period="2d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None

@st.cache_data(ttl=300, show_spinner=False)
def get_sgb_price(raw_ticker: str):
    # Strip data-entry "-GB" suffix; Yahoo lacks most SGB series — Groww has live NSE LTP
    nse_symbol = re.sub(r"-GB$", "", raw_ticker.strip(), flags=re.IGNORECASE)
    price = get_groww_ltp(nse_symbol)
    if price is not None:
        return price
    try:
        t = yf.Ticker(f"{nse_symbol}.NS")
        hist = t.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None


# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.markdown("### Controls")
    uploaded = st.file_uploader("Upload new Excel", type=["xlsx", "xls"])
    if st.button("Force Recalculate", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()
    log_snapshot = st.toggle("Log today's snapshot to history", value=True,
                              help="Free-tier Streamlit storage isn't guaranteed to survive a redeploy — download history periodically.")
    auto_refresh = st.toggle(
        "Auto-refresh every 5 min",
        value=True,
        help="Reloads the whole page every 5 minutes so prices/NAVs stay fresh. Turn off on mobile if it interrupts reading.",
    )
    if st.button("Reset history file", use_container_width=True,
                 help="Deletes corrupted or unwanted history.csv rows."):
        try:
            if os.path.exists(HISTORY_PATH):
                os.remove(HISTORY_PATH)
            st.success("History cleared.")
        except Exception as e:
            st.error(f"Could not clear history: {e}")

    st.markdown("##### Restore history")
    hist_upload = st.file_uploader(
        "Upload previous history CSV to merge",
        type=["csv"],
        help="After a Streamlit Cloud restart, upload a previously downloaded networth_history.csv to restore older days.",
        key="hist_csv_upload",
    )
    if hist_upload is not None:
        try:
            os.makedirs("data", exist_ok=True)
            incoming = pd.read_csv(hist_upload)
            if "date" not in incoming.columns or "net_worth" not in incoming.columns:
                st.error("CSV must have at least date and net_worth columns.")
            else:
                if os.path.exists(HISTORY_PATH):
                    existing = pd.read_csv(HISTORY_PATH)
                    merged = pd.concat([existing, incoming], ignore_index=True)
                else:
                    merged = incoming
                merged["date"] = merged["date"].astype(str)
                merged = merged[merged["date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]
                for col in ["net_worth", "equity_pct", "fd_pct", "pnl", "health_score"]:
                    if col in merged.columns:
                        merged[col] = pd.to_numeric(merged[col], errors="coerce")
                merged = merged.dropna(subset=["net_worth"])
                # Keep latest row per date
                merged = merged.sort_values("date").drop_duplicates(subset=["date"], keep="last")
                merged.to_csv(HISTORY_PATH, index=False)
                st.success(f"Merged history — {len(merged)} day(s) on disk.")
        except Exception as e:
            st.error(f"Could not merge history: {e}")

    st.markdown("---")
    st.caption("AMFI · Groww · Yahoo · goldprice.dev · Frankfurter · Google News")
    st.caption(f"IST {now_ist.strftime('%d %b %Y, %H:%M')}")

# Auto-refresh: full page reload (no extra package). Only when toggle is on.
if auto_refresh:
    import streamlit.components.v1 as components
    components.html(
        """
        <script>
        // Reload parent Streamlit page after 5 minutes
        setTimeout(function () {
            window.parent.location.reload();
        }, 300000);
        </script>
        """,
        height=0,
    )

# -------------------------------------------------
# LOAD + PROCESS
# -------------------------------------------------
fd_raw, mf_raw, stocks_raw = load_data(uploaded)
usd_inr = get_usd_inr()
amfi_navs, amfi_codes, amfi_names, amfi_cache_date = get_amfi_data()
nifty_hist = get_nifty_history()
nifty_1y, nifty_3y, nifty_5y = trailing_return(nifty_hist, 1), trailing_return(nifty_hist, 3), trailing_return(nifty_hist, 5)

# ---- Data integrity log, built up as we go (Phase 3) ----
integrity_issues = []  # each: (severity, message)
if usd_inr is None:
    integrity_issues.append(("CRITICAL", "USD/INR live rate fetch failed this run — all USD FD conversions below are unavailable until it recovers, not silently defaulted to a guessed rate."))
    usd_inr = None

mf_txns = []
for _, row in mf_raw.iterrows():
    try:
        isin = str(row.get("ISIN", "") or "").strip()
        owner = str(row.get("Owner", "") or "").strip()
        fund_name = str(row.get("Fund Name", "") or "").strip()
        units = safe_float(row.get("Units"))
        invested = safe_float(row.get("Invested Amount", row.get("Invested")))
        pdate = to_naive_ts(row.get("Purchase Date"))
        if units <= 0 or not isin:
            continue
        mf_txns.append({"Owner": owner, "ISIN": isin, "Fund Name": fund_name, "Units": units,
                         "Invested": invested, "Purchase Date": pdate})
    except Exception:
        continue

mf_txns_df = pd.DataFrame(mf_txns)
if not mf_txns_df.empty:
    # Aggregate by Owner+ISIN only so name variants (spaces/dashes) of the same
    # fund collapse into one row (fixes split HDFC Liquid / Gold FoF lines).
    def _pick_name(s):
        return max(s.astype(str), key=len)  # longest name is usually the cleanest
    mf_agg = (
        mf_txns_df.groupby(["Owner", "ISIN"], as_index=False)
        .agg({"Units": "sum", "Invested": "sum", "Purchase Date": "min", "Fund Name": _pick_name})
    )
else:
    mf_agg = pd.DataFrame(columns=["Owner", "ISIN", "Fund Name", "Units", "Invested", "Purchase Date"])

mf_rows, gold_rows_from_mf, mf_failed = [], [], 0
for _, row in mf_agg.iterrows():
    try:
        isin, units, invested, pdate = row["ISIN"], row["Units"], row["Invested"], row["Purchase Date"]
        fund_name = str(row["Fund Name"] or "")
        nav = amfi_navs.get(isin)  # None = unknown; do NOT default to 0.0
        if nav is None:
            mf_failed += 1
            integrity_issues.append(("HIGH", f"{fund_name[:40]}: no live NAV found for ISIN {isin} — excluded from totals."))
        if units < 0:
            integrity_issues.append(("HIGH", f"{fund_name[:40]} ({row['Owner']}): negative net units ({units:.2f}) after aggregation — check for a sell exceeding recorded buys."))
        if nav is not None:
            current_value = units * nav
            pnl = current_value - invested
            ret = (pnl / invested * 100) if invested > 0 else 0.0
        else:
            current_value = pnl = ret = None
        amfi_official = amfi_names.get(isin) if isinstance(amfi_names, dict) else None
        category = infer_category(fund_name, amfi_official)

        # Route pure gold FoFs/ETFs out of Mutual Funds into the unified Gold book
        if is_gold_fund(fund_name):
            # Short display symbol for the Gold table (keep it readable)
            sym = "GOLD-FoF"
            if "HDFC" in fund_name.upper():
                sym = "HDFC-GOLD-FoF"
            elif "ICICI" in fund_name.upper():
                sym = "ICICI-GOLD-FoF"
            elif "NIPPON" in fund_name.upper() or "RELIANCE" in fund_name.upper():
                sym = "NIPPON-GOLD-FoF"
            gold_rows_from_mf.append({
                "Owner": row["Owner"], "Symbol": sym, "Quantity": round(units, 3),
                "Invested": invested, "Current Price": nav, "Current Value": current_value,
                "P&L": pnl, "Return %": ret, "Source": "MF",
            })
            continue  # do not also put in mf_rows

        days_held = (TODAY_NAIVE - pdate).days if pdate is not None else None
        fund_return_ann = ((current_value / invested) ** (365.25 / days_held) - 1) * 100 if (current_value is not None and days_held and days_held >= 30 and invested > 0) else None
        code = amfi_codes.get(isin)
        r1y = r3y = r5y = b1y = b3y = b5y = None
        if category not in DEBT_LIKE and code:
            fund_hist = get_mf_nav_history(code)
            r1y, r3y, r5y = trailing_return(fund_hist, 1), trailing_return(fund_hist, 3), trailing_return(fund_hist, 5)
            b1y, b3y, b5y = nifty_1y, nifty_3y, nifty_5y
        mf_rows.append({
            "Owner": row["Owner"], "ISIN": isin, "Fund Name": fund_name[:42], "Category": category,
            "Units": round(units, 3), "Invested": invested, "Current NAV": nav, "Current Value": current_value,
            "P&L": pnl, "Return %": ret, "Ann. Return %": fund_return_ann,
            "1Y %": r1y, "3Y %": r3y, "5Y %": r5y, "vs Nifty50 1Y": b1y, "vs Nifty50 3Y": b3y, "vs Nifty50 5Y": b5y,
            "Purchase Date": pdate,
        })
    except Exception:
        mf_failed += 1
mf = pd.DataFrame(mf_rows)

# Gold book: SGB + gold ETFs (from Stocks sheet) + gold FoFs (from MF sheet above).
# All gold exposure lives in exactly one place.
stock_rows, gold_rows = [], []
for _, row in stocks_raw.iterrows():
    try:
        symbol = str(row.get("Symbol", row.get("Ticker / Symbol", "")) or "").strip().upper()
        qty = safe_float(row.get("Quantity"))
        invested = safe_float(row.get("Invested Amount"))
        if qty <= 0:
            continue
        is_gold = is_gold_symbol(symbol)
        if is_gold and SGB_TICKER_PATTERN.match(symbol):
            price = get_sgb_price(symbol)
        else:
            price = get_stock_price(symbol) if symbol else None
        used_fallback = False
        if price is None:
            price = safe_float(row.get("Current Price", row.get("Current Price (CMP)")))
            used_fallback = True
            if price == 0:
                price = safe_float(row.get("Purchase Price", row.get("Avg Buy Price")))
        if used_fallback:
            integrity_issues.append(("MEDIUM", f"{symbol}: live price unavailable, used stale price from the raw file instead."))
        if price and price > 0:
            current_value = qty * price
            pnl = current_value - invested
            ret = (pnl / invested * 100) if invested > 0 else 0.0
        else:
            current_value = pnl = ret = None
            price = None
            integrity_issues.append(("HIGH", f"{symbol}: no valid price from any source — excluded from totals."))
        # Only flag extreme P&L when it looks like a possible data error (very large
        # multiple). Long-held winners at low cost basis are normal and noisy here.
        if invested > 0 and pnl is not None and abs(pnl) > invested * 10:
            integrity_issues.append(("MEDIUM", f"{symbol}: P&L is {pnl/invested*100:.0f}% of invested amount — unusually large; confirm quantity/price if this was a recent buy."))
        row_dict = {"Owner": str(row.get("Owner", "") or ""), "Symbol": symbol, "Quantity": qty,
                    "Invested": invested, "Current Price": price, "Current Value": current_value,
                    "P&L": pnl, "Return %": ret, "Source": "Stocks"}
        if is_gold:
            gold_rows.append(row_dict)
        else:
            stock_rows.append(row_dict)
    except Exception:
        continue

# Merge gold from Stocks sheet + gold FoFs routed out of MF, then collapse
# any remaining same-owner/same-symbol splits (e.g. FoF name variants).
gold_rows.extend(gold_rows_from_mf)
stocks = pd.DataFrame(stock_rows)
gold = pd.DataFrame(gold_rows)
if not gold.empty and {"Owner", "Symbol", "Quantity", "Invested", "Current Value"}.issubset(gold.columns):
    g_sum = gold.groupby(["Owner", "Symbol"], as_index=False).agg({
        "Quantity": "sum",
        "Invested": "sum",
        "Current Value": "sum",
        "Source": "first",
    })
    g_sum["Current Price"] = g_sum.apply(
        lambda r: (r["Current Value"] / r["Quantity"]) if r["Quantity"] and r["Quantity"] > 0 and pd.notna(r["Current Value"]) else None,
        axis=1,
    )
    g_sum["P&L"] = g_sum["Current Value"] - g_sum["Invested"]
    g_sum["Return %"] = g_sum.apply(
        lambda r: (r["P&L"] / r["Invested"] * 100) if r["Invested"] and r["Invested"] > 0 and pd.notna(r["P&L"]) else None,
        axis=1,
    )
    gold = g_sum

# ---- FD: Phase-1 corrected valuation + full FCNR attribution ----
fd_rows = []
seen_accounts = set()
seen_fingerprints = set()  # catches exact clones when Account Number is blank/missing
fd_attrib = {"fcnr_interest": 0.0, "fcnr_fx_principal": 0.0, "fcnr_fx_interest": 0.0, "inr_fd_interest": 0.0}
for _, row in fd_raw.iterrows():
    try:
        holder = str(row.get("Holder Name", "") or "").strip()
        account = str(row.get("Account Number", "") or "").strip()
        if account.lower() in ("nan", "none", "nat", "-"):
            account = ""
        principal_native = safe_float(row.get("Principal Amount"))
        if (not holder or holder.lower() in ["nan", "nat", "none"] or principal_native <= 0 or "total" in holder.lower()):
            continue

        currency = str(row.get("Currency", "INR") or "INR").upper().strip()
        if currency not in ["INR", "USD"]:
            integrity_issues.append(("HIGH", f"FD {account or 'no-acct'} ({holder}): unrecognized currency '{currency}' — treated as INR."))
            currency = "INR"

        mat_date = to_naive_ts(row.get("Maturity Date"))
        dep_date = to_naive_ts(row.get("Deposit Date"))
        roi = safe_float(row.get("ROI % p.a.", row.get("ROI_Percent_pa", 6.5)))
        maturity_amt = _safe_maturity_amount(row)

        # Also try to read Available Balance directly
        available_balance = None
        for col in row.index if hasattr(row, "index") else []:
            if str(col).strip().lower().replace("_", " ") in (
                "available balance", "available balanc", "available amount"
            ):
                available_balance = safe_float(row.get(col))
                break

        # Dedup key: prefer real account number; otherwise fingerprint of the deposit itself
        if account:
            dedup_key = f"acct:{account}"
        else:
            mat_s = mat_date.strftime("%Y-%m-%d") if mat_date is not None else ""
            dep_s = dep_date.strftime("%Y-%m-%d") if dep_date is not None else ""
            dedup_key = f"fp:{holder}|{currency}|{principal_native:.2f}|{roi:.4f}|{mat_s}|{dep_s}"

        if dedup_key in seen_accounts or dedup_key in seen_fingerprints:
            integrity_issues.append((
                "CRITICAL",
                f"Duplicate FD skipped — {holder} {currency} {principal_native:,.2f} "
                f"({'acct ' + account if account else 'no account #, identical principal/dates/ROI'}). "
                f"Fix the Excel so this row is not counted twice."
            ))
            continue  # do NOT double-count
        if account:
            seen_accounts.add(dedup_key)
        else:
            seen_fingerprints.add(dedup_key)

        if mat_date is not None and dep_date is not None and mat_date < dep_date:
            integrity_issues.append(("HIGH", f"FD {account or 'no-acct'} ({holder}): maturity date is before deposit date — dates likely swapped in source data."))
        days_to_mat = (mat_date - TODAY_NAIVE).days if mat_date is not None else None
        days_elapsed = (TODAY_NAIVE - dep_date).days if dep_date is not None else 0
        if roi <= 0 or roi > 15:
            integrity_issues.append(("MEDIUM", f"FD {account or 'no-acct'} ({holder}): ROI {roi}% p.a. is outside a normal FD range — verify."))

        # ----- Phase-1 valuation -----
        current_value_native, accrued_native, val_method, val_notes = compute_fd_current_native(
            principal_native, roi, dep_date, mat_date, TODAY_NAIVE,
            maturity_amt=maturity_amt,
            available_balance=available_balance,
        )
        if current_value_native is None:
            continue

        if val_method == "simple_interest" and maturity_amt is None and available_balance is None:
            integrity_issues.append((
                "MEDIUM",
                f"FD {account or 'no-acct'} ({holder}): no Maturity Amount / Available Balance in Excel — using simple interest from deposit date."
            ))
        if "WARNING: long tenor" in " ".join(val_notes):
            integrity_issues.append((
                "HIGH",
                f"FD {account or 'no-acct'} ({holder}): deposit→maturity span is very long; simple-interest fallback may overstate value. "
                f"Prefer supplying Maturity Amount or Available Balance."
            ))

        # ----- FX setup -----
        fx_today = usd_inr if currency == "USD" else 1.0
        fx_deposit = 1.0
        if currency == "USD" and dep_date is not None and usd_inr is not None:
            fx_deposit = get_historical_usd_inr(dep_date.strftime("%Y-%m-%d")) or usd_inr
        elif currency == "USD":
            fx_deposit = usd_inr or 1.0

        product = "FCNR" if currency == "USD" else "INR FD"

        # ----- Phase-1 FCNR attribution (full reconciliation) -----
        if currency == "USD" and fx_today is not None and fx_deposit is not None:
            attr = compute_fcnr_attribution(principal_native, accrued_native, fx_deposit, fx_today)
            if attr is None:
                principal_inr_at_cost = None
                current_value_inr = None
                interest_return_inr = None
                fx_gain_inr = 0.0
                fx_on_interest_inr = 0.0
            else:
                principal_inr_at_cost = attr["cost_basis_inr"]
                current_value_inr = attr["current_value_inr"]
                # Keep old column name "Interest Return (INR)" for compatibility,
                # but now it is interest converted at *current* FX (correct).
                interest_return_inr = attr["interest_at_current_fx"]
                # Old column "FX Gain/Loss (INR)" now = FX on principal only
                # (we also expose FX on interest separately).
                fx_gain_inr = attr["fx_on_principal"]
                fx_on_interest_inr = attr["fx_on_interest"]
                # Phase 1B: full-precision, pre-round accumulators for driver recon.
                if product == "FCNR":
                    fd_attrib["fcnr_interest"] += attr["interest_at_current_fx"]
                    fd_attrib["fcnr_fx_principal"] += attr["fx_on_principal"]
                    fd_attrib["fcnr_fx_interest"] += attr["fx_on_interest"]
                else:
                    fd_attrib["inr_fd_interest"] += attr["interest_at_current_fx"]
                if not attr["reconciled"]:
                    integrity_issues.append((
                        "HIGH",
                        f"FCNR {account or 'no-acct'} ({holder}): attribution does not reconcile "
                        f"(diff ₹{abs(attr['total_attribution'] - attr['pnl']):.0f}). Check FX rates."
                    ))
        else:
            # INR FD path (unchanged economics)
            principal_inr_at_cost = principal_native
            current_value_inr = current_value_native
            interest_return_inr = accrued_native
            fx_gain_inr = 0.0
            fx_on_interest_inr = 0.0
            fd_attrib["inr_fd_interest"] += interest_return_inr

        fd_rows.append({
            "Holder Name": holder,
            "Account Number": account,
            "Currency": currency,
            "Product": product,
            "Principal (Native)": round(principal_native, 2),
            "Principal (INR, at deposit FX)": round(principal_inr_at_cost, 0) if principal_inr_at_cost is not None else None,
            "ROI %": roi,
            "Days to Maturity": days_to_mat,
            "Current Value (Native)": round(current_value_native, 2),
            "Current Value (INR)": round(current_value_inr, 0) if current_value_inr is not None else None,
            # Compatibility columns (names kept so downstream tables keep working)
            "Interest Return (INR)": round(interest_return_inr, 0) if interest_return_inr is not None else None,
            "FX Gain/Loss (INR)": round(fx_gain_inr, 0),          # now = FX on principal only
            # New transparency columns (safe to ignore if UI doesn't show them yet)
            "FX on Interest (INR)": round(fx_on_interest_inr, 0),
            "Valuation Method": val_method,
            "Maturity Amount (Native)": round(maturity_amt, 2) if maturity_amt is not None else None,
            "Maturity Date": mat_date.strftime("%Y-%m-%d") if mat_date is not None else "",
        })
    except Exception:
        continue

fd = pd.DataFrame(fd_rows)
fd_fx_unavailable = fd["Current Value (INR)"].isna().sum() if not fd.empty else 0
if fd_fx_unavailable:
    integrity_issues.append(("CRITICAL", f"{fd_fx_unavailable} USD FD(s) excluded from INR totals — live FX rate unavailable this run."))
# -------------------------------------------------
# AGGREGATES — only rows with a real current value count toward totals
# -------------------------------------------------
mf_valid = mf.dropna(subset=["Current Value"]) if not mf.empty else mf
stocks_valid = stocks.dropna(subset=["Current Value"]) if not stocks.empty else stocks
gold_valid = gold.dropna(subset=["Current Value"]) if not gold.empty else gold
fd_valid = fd.dropna(subset=["Current Value (INR)"]) if not fd.empty else fd

# PHASE 1A — canonical family asset register (built from the four books above; no re-valuation).
# Stops loudly on an FD instrument-key collision rather than inventing/merging keys.
try:
    register = build_asset_register(mf_valid, stocks_valid, gold_valid, fd_valid)
    register_classes = aggregate_by_class(register)
    register_members = aggregate_by_member(register)
    family_sum = family_level_sum(register)
    register_error = None
except NonUniqueKeyError as e:
    register = register_classes = register_members = family_sum = None
    register_error = str(e)
    integrity_issues.append(("CRITICAL", f"Asset register halted: {register_error} Please add account numbers to the conflicting FD deposits."))

total_mf = mf_valid["Current Value"].sum() if not mf_valid.empty else 0
total_stocks = stocks_valid["Current Value"].sum() if not stocks_valid.empty else 0
total_gold = gold_valid["Current Value"].sum() if not gold_valid.empty else 0
total_fd = fd_valid["Current Value (INR)"].sum() if not fd_valid.empty else 0
total_networth = total_mf + total_stocks + total_gold + total_fd
total_fd_invested = fd_valid["Principal (INR, at deposit FX)"].sum() if not fd_valid.empty else 0
total_invested = ((mf_valid["Invested"].sum() if not mf_valid.empty else 0)
                  + (stocks_valid["Invested"].sum() if not stocks_valid.empty else 0)
                  + (gold_valid["Invested"].sum() if not gold_valid.empty else 0)
                  + total_fd_invested)
total_pnl = total_networth - total_invested

# --- NRI split: equity (ex-liquid MF) vs liquid MF vs INR FD vs FCNR vs gold ---
if not mf_valid.empty and "Category" in mf_valid.columns:
    _liq_mask = mf_valid["Category"].isin(DEBT_LIKE)
    total_liquid_mf = float(mf_valid.loc[_liq_mask, "Current Value"].sum() or 0)
    total_equity_mf = float(mf_valid.loc[~_liq_mask, "Current Value"].sum() or 0)
else:
    total_liquid_mf, total_equity_mf = 0.0, float(total_mf or 0)
total_equity = total_equity_mf + total_stocks
if not fd_valid.empty and "Product" in fd_valid.columns:
    total_fcnr = float(fd_valid.loc[fd_valid["Product"] == "FCNR", "Current Value (INR)"].sum() or 0)
    total_inr_fd = float(fd_valid.loc[fd_valid["Product"] == "INR FD", "Current Value (INR)"].sum() or 0)
elif not fd_valid.empty and "Currency" in fd_valid.columns:
    total_fcnr = float(fd_valid.loc[fd_valid["Currency"] == "USD", "Current Value (INR)"].sum() or 0)
    total_inr_fd = float(fd_valid.loc[fd_valid["Currency"] != "USD", "Current Value (INR)"].sum() or 0)
else:
    total_fcnr, total_inr_fd = 0.0, float(total_fd or 0)

# Near-term maturities (≤90d) count toward usable liquidity for an NRI
if not fd_valid.empty and "Days to Maturity" in fd_valid.columns:
    _near = fd_valid[fd_valid["Days to Maturity"].between(0, 90)]
    total_near_fd = float(_near["Current Value (INR)"].sum() or 0) if not _near.empty else 0.0
else:
    total_near_fd = 0.0
total_true_liquid = total_liquid_mf + total_near_fd

def _pct(part):
    return (part / total_networth * 100) if total_networth else 0.0

equity_pct = _pct(total_equity)          # stocks + non-liquid MF only
liquid_mf_pct = _pct(total_liquid_mf)
inr_fd_pct = _pct(total_inr_fd)
fcnr_pct = _pct(total_fcnr)
gold_pct = _pct(total_gold)
# Backward-compatible: all deposits as share of NW (history still uses this key)
fd_pct = _pct(total_fd)
true_liquid_pct = _pct(total_true_liquid)
# Deep Health defaults
st.session_state["cc_equity_pct"] = float(equity_pct)
st.session_state["cc_liquid_pct"] = float(liquid_mf_pct)
st.session_state["cc_inr_fd_pct"] = float(inr_fd_pct)
st.session_state["cc_fcnr_pct"] = float(fcnr_pct)
st.session_state["cc_gold_pct"] = float(gold_pct)
st.session_state["cc_net_worth"] = float(total_networth)

# PHASE 1B — current P&L drivers (pure decomposition over the canonical register +
# full-precision FD attribution). Additive; no financial value is changed.
cc_drivers = None
if register is not None:
    _fd_comp = dict(fd_attrib)
    _fd_comp["n_fd"] = int(len(fd_valid)) if fd_valid is not None and not fd_valid.empty else 0
    cc_drivers = decompose_current(
        class_pnl_from_register(family_sum),
        _fd_comp,
        n_fd=_fd_comp["n_fd"],
        missing_fx=(usd_inr is None),
    )
    st.session_state["cc_drivers"] = cc_drivers

# Phase 2A — family-level concentration (same fund/stock across members counted once)
if not mf_valid.empty and total_mf > 0 and "ISIN" in mf_valid.columns:
    _mf_by_isin = (
        mf_valid.dropna(subset=["Current Value"])
        .groupby("ISIN", as_index=False)["Current Value"]
        .sum()
    )
    top5_mf_pct = float(_mf_by_isin.nlargest(5, "Current Value")["Current Value"].sum() / total_mf * 100)
elif not mf_valid.empty and total_mf > 0:
    top5_mf_pct = float(mf_valid.nlargest(5, "Current Value")["Current Value"].sum() / total_mf * 100)
else:
    top5_mf_pct = 0.0

if not stocks_valid.empty and total_stocks > 0 and "Symbol" in stocks_valid.columns:
    _stk_by_sym = (
        stocks_valid.dropna(subset=["Current Value"])
        .groupby("Symbol", as_index=False)["Current Value"]
        .sum()
    )
    top5_stock_pct = float(_stk_by_sym.nlargest(5, "Current Value")["Current Value"].sum() / total_stocks * 100)
elif not stocks_valid.empty and total_stocks > 0:
    top5_stock_pct = float(stocks_valid.nlargest(5, "Current Value")["Current Value"].sum() / total_stocks * 100)
else:
    top5_stock_pct = 0.0
total_fx_gain = fd_valid["FX Gain/Loss (INR)"].sum() if not fd_valid.empty else 0
total_fcnr_interest = 0.0
if not fd_valid.empty and "Product" in fd_valid.columns and "Interest Return (INR)" in fd_valid.columns:
    total_fcnr_interest = float(fd_valid.loc[fd_valid["Product"] == "FCNR", "Interest Return (INR)"].sum() or 0)

# -------------------------------------------------
# HEALTH SCORE — NRI-aware
# Liquidity scores *true* liquidity (liquid MF + FDs ≤90d), not all FCNR as locked cash.
# Allocation still tracks equity share but narrative treats FCNR as intentional USD book.
# (score_* factor functions now live in lib/scoring.py)
# -------------------------------------------------
alloc_score = score_allocation(equity_pct)
conc_score = min(score_concentration(top5_mf_pct), score_concentration(top5_stock_pct) if not stocks_valid.empty else 100)
liq_score = score_liquidity_nri(true_liquid_pct)
div_score = score_diversification(mf_valid)
perf_score = score_performance(mf_valid)
WEIGHTS = {"Allocation": 0.26, "Concentration": 0.20, "Liquidity": 0.20, "Diversification": 0.14, "Performance": 0.20}
factor_scores = {"Allocation": alloc_score, "Concentration": conc_score, "Liquidity": liq_score, "Diversification": div_score, "Performance": perf_score}
health_score = sum(factor_scores[k] * WEIGHTS[k] for k in WEIGHTS)
health_label = "Healthy" if health_score >= 75 else ("Adequate" if health_score >= 55 else "Needs Attention")

# -------------------------------------------------
# RECONCILIATION TESTS (Phase 4) — shown, not hidden, pass or fail
# -------------------------------------------------
recon_tests = []
owner_sum = 0
owner_map = {}
for df_, col, key in [(mf_valid, "Current Value", "Owner"), (stocks_valid, "Current Value", "Owner"),
                       (gold_valid, "Current Value", "Owner"), (fd_valid, "Current Value (INR)", "Holder Name")]:
    if not df_.empty and key in df_.columns:
        for owner, val in df_.groupby(key)[col].sum().items():
            owner_map[owner] = owner_map.get(owner, 0) + val
owner_sum = sum(owner_map.values())
recon_tests.append(("Sum of owner totals = total net worth", abs(owner_sum - total_networth) < 1, f"{format_inr(owner_sum)} vs {format_inr(total_networth)}"))
# Equity (ex-liquid) + liquid MF + INR FD + FCNR + gold should ≈ 100%
alloc_sum = equity_pct + liquid_mf_pct + inr_fd_pct + fcnr_pct + gold_pct
recon_tests.append(("NRI allocation slices sum to 100%", abs(alloc_sum - 100) < 0.6, f"{alloc_sum:.2f}%"))
recon_tests.append(("Portfolio total = MF + Stocks + Gold + FD", abs((total_mf + total_stocks + total_gold + total_fd) - total_networth) < 1, "by construction"))
recon_tests.append((
    "FCNR + INR FD = total deposits",
    abs((total_fcnr + total_inr_fd) - total_fd) < 1,
    f"FCNR {format_inr(total_fcnr)} + INR FD {format_inr(total_inr_fd)}",
))
_gold_leaked_stocks = any(is_gold_symbol(s) for s in stocks["Symbol"]) if not stocks.empty else False
_gold_leaked_mf = any(is_gold_fund(n) for n in mf["Fund Name"]) if not mf.empty else False
recon_tests.append((
    "Gold instruments only in Gold (not Stocks/MF)",
    (not _gold_leaked_stocks) and (not _gold_leaked_mf),
    f"{len(gold)} gold holding(s) · leaked stocks={_gold_leaked_stocks} mf={_gold_leaked_mf}",
))

# PHASE 1A — asset register reconciliation: register (canonical) vs Command Center (page) totals.
if register is not None:
    recon_tests.append((
        "Asset register total = portfolio total",
        abs(family_sum["total_assets"] - total_networth) < 1,
        f"{format_inr(family_sum['total_assets'])} vs {format_inr(total_networth)}",
    ))
    recon_tests.append((
        "Asset register invested = invested capital",
        abs(family_sum["total_invested"] - total_invested) < 1,
        f"{format_inr(family_sum['total_invested'])} vs {format_inr(total_invested)}",
    ))
    for _cls, _page_total in [("Equity", total_equity), ("Liquid", total_liquid_mf),
                              ("FCNR (USD)", total_fcnr), ("INR FD", total_inr_fd),
                              ("Gold", total_gold)]:
        _reg_val = family_sum["by_class"].get(_cls, {}).get("current", 0.0) or 0.0
        recon_tests.append((
            f"Asset register {_cls.lower()} = Command Center {_cls.lower()} total",
            abs(_reg_val - _page_total) < 1,
            f"{format_inr(_reg_val)} vs {format_inr(_page_total)}",
        ))
    # PHASE 1B — driver-level reconciliation entries.
    if cc_drivers is not None:
        _drv_sum = float(sum(cc_drivers["drivers"].values()))
        _fd_drv = float(cc_drivers["drivers"]["fcnr_interest"]
                        + cc_drivers["drivers"]["fcnr_fx_principal"]
                        + cc_drivers["drivers"]["inr_fd_interest"])
        _fd_cls = float(total_fd - total_fd_invested)
        _bound = cc_drivers["residual_bound"] or 0.0
        recon_tests.append((
            "Register class P&L sums to Total P&L",
            abs(cc_drivers["attributed"] - total_pnl) <= _bound,
            f"{format_inr(cc_drivers['attributed'])} vs {format_inr(total_pnl)} (bound \u20B9{_bound:.1f})",
        ))
        recon_tests.append((
            "FD drivers reconcile to FD class P&L (rounding-bound)",
            abs(_fd_drv - _fd_cls) <= _bound,
            f"{format_inr(_fd_drv)} vs {format_inr(_fd_cls)} (bound \u20B9{_bound:.1f})",
        ))
        recon_tests.append((
            "Total drivers reconcile to Total P&L (rounding-bound)",
            abs(_drv_sum - total_pnl) <= _bound and cc_drivers["residual_ok"],
            f"{format_inr(_drv_sum)} vs {format_inr(total_pnl)} (bound \u20B9{_bound:.1f})",
        ))

# -------------------------------------------------
# RED FLAGS
# -------------------------------------------------
flags = []
if equity_pct < 35:
    gap_to_40 = max(0, 0.40 * total_networth - total_equity)
    gap_to_50 = max(0, 0.50 * total_networth - total_equity)
    flags.append((
        "critical" if equity_pct < 20 else "warning",
        "Equity allocation (NRI view)",
        f"Equity (stocks + non-liquid MF) is {equity_pct:.1f}% of NW. "
        f"FCNR {fcnr_pct:.1f}% · INR FD {inr_fd_pct:.1f}% · Liquid MF {liquid_mf_pct:.1f}%. "
        f"~{format_inr(gap_to_40)} more equity → 40%; ~{format_inr(gap_to_50)} → 50%. "
        f"FCNR is intentional USD book (interest + FX), not generic cash.",
    ))
if fcnr_pct >= 15:
    flags.append((
        "info",
        "FCNR / USD deposit book",
        f"FCNR is {fcnr_pct:.1f}% of NW ({format_inr(total_fcnr)}). "
        f"Return = interest (~{format_inr(total_fcnr_interest)}) + FX vs deposit-date USD/INR (~{format_inr(total_fx_gain)}).",
    ))
if 3 <= gold_pct <= 15:
    flags.append(("info", "Gold allocation healthy",
                   f"Gold (SGB + ETFs + FoFs) is {gold_pct:.1f}% of net worth — a reasonable diversifier."))
elif gold_pct > 15:
    flags.append(("info", "Gold allocation is notable", f"Gold (SGB + ETFs + FoFs) is {gold_pct:.1f}% of net worth."))
if top5_mf_pct > 60:
    flags.append(("warning", "Mutual fund concentration", f"Top 5 funds are {top5_mf_pct:.1f}% of your MF portfolio."))
if not stocks_valid.empty and top5_stock_pct > 65:
    flags.append(("warning", "Stock concentration", f"Top 5 stocks are {top5_stock_pct:.1f}% of your equity holdings."))
if not mf_valid.empty:
    persistent = mf_valid.dropna(subset=["1Y %", "3Y %", "vs Nifty50 1Y", "vs Nifty50 3Y"])
    persistent = persistent[(persistent["1Y %"] < persistent["vs Nifty50 1Y"] - 2) & (persistent["3Y %"] < persistent["vs Nifty50 3Y"] - 2)]
    for _, r in persistent.sort_values("1Y %").head(3).iterrows():
        flags.append(("warning", f"{r['Fund Name']}: persistent underperformance",
                       f"Trailing both 1Y ({r['1Y %']:.1f}% vs Nifty50 {r['vs Nifty50 1Y']:.1f}%) and 3Y ({r['3Y %']:.1f}% vs Nifty50 {r['vs Nifty50 3Y']:.1f}%)."))
    losers = mf_valid[mf_valid["Return %"] < -10]
    for _, r in losers.sort_values("Return %").head(3).iterrows():
        pnl_abs = abs(r["P&L"]) if pd.notna(r.get("P&L")) else 0
        flags.append(("critical", f"{r['Fund Name'][:28]} down {abs(r['Return %']):.1f}%",
                       f"Loss {format_inr(pnl_abs)} · currently a loss position."))
if not stocks_valid.empty:
    losers_s = stocks_valid[stocks_valid["Return %"] < -15]
    # Per-owner equity book for context
    owner_eq = stocks_valid.groupby("Owner")["Current Value"].sum().to_dict() if "Owner" in stocks_valid.columns else {}
    for _, r in losers_s.sort_values("Return %").head(3).iterrows():
        pnl_abs = abs(r["P&L"]) if pd.notna(r.get("P&L")) else 0
        own = r.get("Owner", "")
        book = owner_eq.get(own, 0) or 0
        pct_book = (pnl_abs / book * 100) if book > 0 else 0
        flags.append(("critical", f"{r['Symbol']} down {abs(r['Return %']):.1f}%",
                       f"Loss {format_inr(pnl_abs)}"
                       + (f" · {pct_book:.0f}% of {own.split()[-1]}'s stock book" if own and book else "")
                       + "."))
if not fd.empty:
    overdue = fd[fd["Days to Maturity"] < 0]
    for _, r in overdue.iterrows():
        cv = r['Current Value (INR)']
        flags.append(("critical", f"{r['Holder Name']}'s FD matured {abs(int(r['Days to Maturity']))}d ago, uncollected",
                       f"{format_inr(cv) if pd.notna(cv) else r['Current Value (Native)']} — likely earning the bank's default rate instead of {r['ROI %']:.2f}%."))
    soon = fd[fd["Days to Maturity"].between(0, 14)]
    # Rough liquid-MF stock for context on near-maturity FDs
    liq_cv = 0.0
    if not mf_valid.empty and "Category" in mf_valid.columns:
        liq_cv = float(mf_valid[mf_valid["Category"] == "Liquid"]["Current Value"].sum() or 0)
    for _, r in soon.iterrows():
        cv = r['Current Value (INR)']
        body = f"{format_inr(cv) if pd.notna(cv) else r['Current Value (Native)']} — decide reinvest vs deploy elsewhere."
        if liq_cv > 0:
            body += f" Liquid MFs already hold ~{format_inr(liq_cv)}."
        flags.append(("info", f"{r['Holder Name']}'s FD matures in {int(r['Days to Maturity'])}d", body))
critical_integrity = [i for i in integrity_issues if i[0] == "CRITICAL"]
for _, msg in critical_integrity:
    flags.append(("critical", "Data integrity issue", msg))
severity_rank = {"critical": 0, "warning": 1, "info": 2}
flags.sort(key=lambda f: severity_rank[f[0]])

# -------------------------------------------------
# NEWS
# -------------------------------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_news_for(names, max_items=10):
    """Pull recent Google News RSS for each name; dedupe by title."""
    items, seen = [], set()
    cutoff = datetime.now() - timedelta(days=45)
    for name in names[:12]:
        if not name or not str(name).strip():
            continue
        try:
            q = requests.utils.quote(str(name).strip())
            url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
            feed = feedparser.parse(url)
            for entry in feed.entries[:2]:
                title = (entry.title or "").strip()
                if not title or title in seen:
                    continue
                pub = datetime(*entry.published_parsed[:6]) if hasattr(entry, "published_parsed") and entry.published_parsed else None
                if pub and pub < cutoff:
                    continue
                seen.add(title)
                items.append({
                    "title": title, "link": entry.link,
                    "source": entry.get("source", {}).get("title", "") if hasattr(entry, "source") else "",
                    "published": entry.get("published", ""), "pub_dt": pub or datetime.min,
                    "query": str(name).strip(),
                })
        except Exception:
            continue
    items.sort(key=lambda x: x["pub_dt"], reverse=True)
    return items[:max_items]

# -------------------------------------------------
# HISTORY — FIXED: full precision kept in the CSV/download, rounded only
# for on-screen display (Phase 7)
# -------------------------------------------------
def _build_history_row():
    """Build an enriched snapshot row for today (Phase 1B)."""
    _family = family_sum if family_sum is not None else {"by_class": {}, "by_member": {}}
    _class_cur = {_cls: (_family["by_class"].get(_cls) or {}).get("current", 0.0)
                  for _cls in ASSET_CLASSES}
    _class_inv = {_cls: (_family["by_class"].get(_cls) or {}).get("invested", 0.0)
                  for _cls in ASSET_CLASSES}
    _mem_cur = {m: v["current"] for m, v in (_family.get("by_member") or {}).items()}
    _mem_inv = {m: v["invested"] for m, v in (_family.get("by_member") or {}).items()}
    return snapshot_io.build_snapshot_row(
        date=now_ist.strftime("%Y-%m-%d"),
        net_worth=total_networth,
        equity_pct=float(equity_pct),
        fd_pct=float(fd_pct),
        pnl=total_pnl,
        health_score=health_score,
        total_invested=total_invested,
        usd_inr=usd_inr,
        amfi_cache_date=str(amfi_cache_date) if amfi_cache_date else None,
        snapshot_ts=now_ist.strftime("%Y-%m-%d %H:%M:%S"),
        fcnr_interest_total=(cc_drivers or {}).get("drivers", {}).get("fcnr_interest"),
        fcnr_fx_principal_total=(cc_drivers or {}).get("drivers", {}).get("fcnr_fx_principal"),
        inr_fd_interest_total=(cc_drivers or {}).get("drivers", {}).get("inr_fd_interest"),
        drivers_recon_ok=bool(cc_drivers and cc_drivers["residual_ok"]),
        class_current=_class_cur,
        class_invested=_class_inv,
        member_current=_mem_cur,
        member_invested=_mem_inv,
    )


def log_history_snapshot():
    return snapshot_io.upsert_snapshot(_build_history_row(), HISTORY_PATH)


history_df = log_history_snapshot() if log_snapshot else snapshot_io.load_history(HISTORY_PATH)
history_df = snapshot_io.clean(history_df)
# rewrite cleaned history so bad rows don't keep coming back
if log_snapshot and not history_df.empty:
    try:
        history_df.to_csv(HISTORY_PATH, index=False)
    except Exception:
        pass

# Quick exports (sidebar)
with st.sidebar:
    st.markdown("### Quick actions")
    if history_df is not None and not history_df.empty:
        st.download_button(
            "Download history CSV",
            data=history_df.to_csv(index=False).encode("utf-8"),
            file_name="networth_history.csv",
            mime="text/csv",
            use_container_width=True,
        )
    # Holdings export
    _parts = []
    if not mf_valid.empty:
        _m = mf_valid.copy(); _m["Asset"] = "MF"; _parts.append(_m)
    if not stocks_valid.empty:
        _s = stocks_valid.copy(); _s["Asset"] = "Stock"; _parts.append(_s)
    if not gold_valid.empty:
        _g = gold_valid.copy(); _g["Asset"] = "Gold"; _parts.append(_g)
    if _parts:
        _hold = pd.concat(_parts, ignore_index=True, sort=False)
        st.download_button(
            "Download holdings CSV",
            data=_hold.to_csv(index=False).encode("utf-8"),
            file_name="networth_holdings.csv",
            mime="text/csv",
            use_container_width=True,
        )
    st.markdown("---")
    st.caption("AMFI · Groww · Yahoo · goldprice.dev · Frankfurter")

# ==================================================
# HEADER — command center
# ==================================================
st.markdown(ui_page_header(
    "Portfolio intelligence terminal",
    "Command Center",
    f"Last updated {now_ist.strftime('%d %b %Y, %H:%M IST')} · all amounts in INR unless noted",
), unsafe_allow_html=True)

# Data status pills
amfi_dot = "dot-off" if len(amfi_navs) == 0 else ("dot-cache" if amfi_cache_date else "dot-live")
amfi_lbl = "AMFI offline" if len(amfi_navs) == 0 else ("AMFI cache" if amfi_cache_date else "AMFI live")
stocks_ok = (not stocks.empty and stocks["Current Price"].notna().any()) if not stocks.empty else False
gold_ok = (not gold.empty and gold["Current Price"].notna().any()) if not gold.empty else False
fx_ok = usd_inr is not None
st.markdown(
    '<div class="t-meta-row">'
    + ui_pill(f"{amfi_lbl} · {len(amfi_navs)} schemes",
              "off" if len(amfi_navs) == 0 else ("cache" if amfi_cache_date else "ok"))
    + ui_pill(f"Stocks {'live' if stocks_ok else 'n/a'}", "ok" if stocks_ok else "off")
    + ui_pill(f"Gold {'live' if gold_ok else 'n/a'}", "ok" if gold_ok else "off")
    + ui_pill(f"USD/INR {'live' if fx_ok else 'n/a'}", "ok" if fx_ok else "off")
    + ui_pill("Market pulse", "info")
    + '</div>',
    unsafe_allow_html=True,
)

if len(amfi_navs) == 0:
    st.markdown(ui_banner(
        "<b>AMFI data failed to load</b> this run and no disk cache found — "
        "mutual fund values below are excluded.", "critical"), unsafe_allow_html=True)
elif amfi_cache_date:
    st.markdown(ui_banner(
        f"<b>AMFI live fetch failed</b> — using disk cache from {amfi_cache_date} · "
        f"{len(amfi_navs)} NAVs.", "warn"), unsafe_allow_html=True)
elif mf_failed > 0:
    st.markdown(ui_banner(
        f"{mf_failed} fund(s) missing a live NAV · {len(amfi_navs)} AMFI NAVs OK.",
        "warn"), unsafe_allow_html=True)

# Optional vs prior history day (used by the hero cards below)
_prev_nw = _prev_eq = None
if history_df is not None and not history_df.empty and "net_worth" in history_df.columns:
    try:
        _hist_sorted = history_df.sort_values("date")
        if len(_hist_sorted) >= 2:
            _prev_nw = float(_hist_sorted["net_worth"].iloc[-2])
            _prev_eq = float(_hist_sorted["equity_pct"].iloc[-2]) if "equity_pct" in _hist_sorted.columns else None
        elif len(_hist_sorted) == 1 and str(_hist_sorted["date"].iloc[-1]) != now_ist.strftime("%Y-%m-%d"):
            _prev_nw = float(_hist_sorted["net_worth"].iloc[-1])
    except Exception:
        pass
_nw_delta = None
if _prev_nw and _prev_nw > 0:
    _nw_delta = f"{(total_networth - _prev_nw) / _prev_nw * 100:+.2f}% vs prior snapshot"

# Net-worth semantics: Total Assets − Liabilities (session-only liabilities input).
_liab_value = float(st.session_state.get("cc_liabilities", 0.0) or 0.0)
_ledger = compute_net_worth(total_networth, _liab_value)

# HERO — executive snapshot: one dominant net-worth number + supporting metrics
st.markdown(ui_hero(
    {"label": "Net Worth", "value": format_inr_compact(_ledger["net_worth"]),
     "tone": "accent",
     "delta": _nw_delta or "current value this run",
     "sub": ("Total Assets − Liabilities" if _ledger["has_liabilities"]
             else "= Total Assets (no liabilities recorded)")},
    [
        {"label": "Total Assets (INR)", "value": format_inr_compact(total_networth),
         "sub": "MF + stocks + gold + FD"},
        {"label": "Invested Basis", "value": format_inr_compact(total_invested),
         "sub": "book cost at purchase / deposit FX"},
        {"label": "Total P&L", "value": format_inr_compact(total_pnl),
         "tone": "up" if total_pnl >= 0 else "down",
         "sub": f"{total_pnl / total_invested * 100:.1f}% overall" if total_invested else "—"},
        {"label": "Equity (ex-liquid)", "value": f"{equity_pct:.1f}%",
         "tone": "warn" if equity_pct < 35 else "neutral",
         "sub": "NRI view · stocks + non-liquid MF"},
        {"label": "Health Score", "value": f"{health_score:.0f} / 100",
         "tone": "warn" if health_score < 55 else ("neutral" if health_score < 75 else "up"),
         "sub": health_label},
    ],
    foot=("Net Worth = Total Assets − Liabilities. No liabilities sheet exists in the "
          "source workbook — the field below is a session-only estimate."),
), unsafe_allow_html=True)

_LIAB_HELP = ("No liabilities data exists in the source workbook — this is a "
              "session-only estimate. Net Worth = Total Assets − Liabilities.")
_lcols = st.columns([2, 6])
with _lcols[0]:
    st.number_input(
        "Liabilities (session-only, ₹)",
        min_value=0.0,
        value=_liab_value,
        step=100000.0,
        key="cc_liabilities",
        help=_LIAB_HELP,
    )
with _lcols[1]:
    if _ledger["has_liabilities"]:
        st.markdown(
            ui_caption(f"Net Worth = Total Assets {format_inr_compact(_ledger['total_assets'])} "
                       f"− Liabilities {format_inr_compact(_ledger['total_liabilities'])}. "
                       "Liabilities are an estimator, never a book."),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            ui_caption("Net Worth = Total Assets (no liabilities recorded) — the workbook "
                       "has no liabilities sheet, so this input is an estimate."),
            unsafe_allow_html=True,
        )

# ==================================================
# PORTFOLIO POSTURE — allocation readout
# ==================================================
st.markdown(ui_section("Portfolio posture"), unsafe_allow_html=True)
st.markdown(ui_alloc_bar([
    {"label": "Equity (stocks + non-liquid MF)", "value": total_equity, "color": "#f59e0b"},
    {"label": "Liquid MF", "value": total_liquid_mf, "color": "#22c55e"},
    {"label": "INR FD", "value": total_inr_fd, "color": "#3b82f6"},
    {"label": "FCNR (USD)", "value": total_fcnr, "color": "#06b6d4"},
    {"label": "Gold", "value": total_gold, "color": "#eab308"},
], total=total_networth), unsafe_allow_html=True)
_posture_bits = []
if equity_pct < 25:
    _posture_bits.append(f"equity-light posture ({equity_pct:.1f}%)")
elif equity_pct < 40:
    _posture_bits.append(f"moderate equity posture ({equity_pct:.1f}%)")
else:
    _posture_bits.append(f"equity-oriented posture ({equity_pct:.1f}%)")
if fcnr_pct > 0:
    _posture_bits.append(f"USD book {fcnr_pct:.1f}% of assets")
if gold_pct > 0:
    _posture_bits.append(f"gold diversifier {gold_pct:.1f}%")
_posture_bits.append(f"health {health_score:.0f}/100 ({health_label.lower()})")
st.markdown(
    f'<div class="t-caption">{" · ".join(_posture_bits)} — a descriptive readout, not advice.</div>',
    unsafe_allow_html=True,
)

# ==================================================
# WHAT CHANGED — P&L drivers (valuation attribution only)
# ==================================================
st.markdown(ui_section("What changed · current P&L drivers"), unsafe_allow_html=True)
if cc_drivers is not None:
    _drv_rows = []
    _fcnr_drivers = {"fcnr_interest", "fcnr_fx_principal"}
    for _k in DRIVER_KEYS:
        # When USD/INR is unavailable, FCNR interest / FX-on-principal slices are
        # genuinely not measurable this run -> show n/a, never a fabricated 0.00.
        if cc_drivers["missing_fx"] and _k in _fcnr_drivers:
            _drv_rows.append({
                "Driver": cc_drivers["driver_labels"].get(_k, _k),
                "Amount (INR)": "n/a",
                "% of P&L": "n/a",
            })
            continue
        _dv = float(cc_drivers["drivers"].get(_k, 0.0))
        _pct = (_dv / cc_drivers["total_pnl"] * 100) if cc_drivers["total_pnl"] else None
        _drv_rows.append({
            "Driver": cc_drivers["driver_labels"].get(_k, _k),
            "Amount (INR)": round(_dv, 2),
            "% of P&L": round(_pct, 2) if _pct is not None else None,
        })
    if cc_drivers["residual_bound"]:
        _drv_rows.append({
            "Driver": f"Rounded residual (documented bound \u20B9{cc_drivers['residual_bound']:.1f})",
            "Amount (INR)": round(cc_drivers["residual"], 2),
            "% of P&L": None,
        })
    st.dataframe(pd.DataFrame(_drv_rows), hide_index=True, use_container_width=True)
    _dnote = (
        f"Attributed {format_inr(cc_drivers['attributed'])} of "
        f"Total P&L {format_inr(cc_drivers['total_pnl'])}. "
    )
    if cc_drivers["missing_fx"]:
        _dnote += "USD/INR unavailable this run \u2014 FCNR interest/FX slices are n/a (never guessed). "
    if not cc_drivers["residual_ok"]:
        _dnote += "Residual exceeds the documented rounding bound \u2014 review source data. "
    _dnote += "Valuation attribution only, not cash-flow events."
    st.markdown(
        f'<div class="t-caption">{_dnote} {NOT_A_CASHFLOW_LABEL}</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(ui_empty(
        "P&L drivers unavailable",
        "The register did not build this run — see data integrity below.",
    ), unsafe_allow_html=True)

# ==================================================
# FCNR RETURN ATTRIBUTION — interest + FX split (what changed · USD book)
# ==================================================
if not fd_valid.empty and (fd_valid["Currency"] == "USD").any():
    st.markdown(ui_section("FCNR return · USD FD attribution (interest + FX)"),
                unsafe_allow_html=True)
    st.caption(
        "NRI FCNR-style USD deposits: INR return = interest accrued on principal + FX from USD/INR move "
        "since each deposit's own date (cost basis at deposit-date FX, mark-to-market at today's FX)."
    )
    usd_fd = fd_valid[fd_valid["Currency"] == "USD"]
    st.markdown(ui_kpi_cards([
        {"label": "FCNR interest (INR)", "value": format_inr(usd_fd["Interest Return (INR)"].sum()),
         "tone": "up", "sub": "interest accrued at current FX"},
        {"label": "FCNR FX gain/(loss) (INR)", "value": format_inr(total_fx_gain),
         "tone": "up" if total_fx_gain >= 0 else "down", "sub": "FX on principal vs deposit date"},
        {"label": "Total FCNR return (INR)", "value": format_inr(usd_fd["Interest Return (INR)"].sum() + total_fx_gain),
         "tone": "accent", "sub": "interest + FX"},
    ]), unsafe_allow_html=True)

# ==================================================
# WHAT NEEDS MY ATTENTION — tagged tiles
# ==================================================
st.markdown(ui_section("What needs my attention"), unsafe_allow_html=True)
if not flags:
    st.markdown(ui_empty("Nothing flagged right now.", "No warning or review items on this run."),
                unsafe_allow_html=True)
else:
    _tiles = []
    for level, title, body in flags[:8]:
        _tiles.append({"level": level, "title": title, "body": body})
    st.markdown(ui_watch(_tiles), unsafe_allow_html=True)

# Critical integrity banner (also surfaced as a flag tile above)
crit = [m for sev, m in integrity_issues if sev == "CRITICAL"]
if crit:
    bullets = "".join(f"<div>• {c}</div>" for c in crit[:6])
    st.markdown(ui_banner(f"<b>Critical data issues</b>{bullets}", "critical"),
                unsafe_allow_html=True)

# ==================================================
# MARKET PULSE — card grid (Phase A)
# ==================================================
st.markdown(ui_section("Market pulse"), unsafe_allow_html=True)
pulse_rows = build_market_pulse_rows()
pulse_cards = []
for row in pulse_rows:
    if row["Value"] is None:
        val = "—"
        chg = None
        sub = "no quote this run"
    else:
        val = row["fmt"].format(row["Value"])
        chg = row["Chg %"]
        sub = None
        if chg is not None:
            sub = f"{'▲' if chg >= 0 else '▼'} {chg:+.2f}%"
    ath = row.get("ATH %")
    if ath is not None:
        sub = f"{sub + ' · ' if sub else ''}{ath:.1f}% from ATH"
    pulse_cards.append({
        "label": row["Market"],
        "value": val,
        "sub": sub or "",
        "tone": "up" if (chg is not None and chg >= 0)
                else ("down" if (chg is not None and chg < 0) else ""),
    })
st.markdown(ui_kpi_cards(pulse_cards, cols=4), unsafe_allow_html=True)
st.caption("Free delayed sources · Gold ₹/10g & Silver ₹/kg (INR) · day change vs prior close · ATH from Yahoo daily history")

# ==================================================
# COMPUTE — news + portfolio intelligence + research + gateway
# Build-only band: these blocks fetch/read data and set session state but
# render nothing at this position. The executive bands below render from them.
# ==================================================
from lib.news import get_portfolio_news, group_by_asset

_stock_syms = []
if not stocks_valid.empty and "Symbol" in stocks_valid.columns:
    _stock_syms = stocks_valid["Symbol"].dropna().astype(str).head(6).tolist()
_fund_names = []
if not mf_valid.empty and "Fund Name" in mf_valid.columns:
    _fund_names = mf_valid["Fund Name"].dropna().astype(str).head(3).tolist()
_gold_syms = []
if not gold_valid.empty and "Symbol" in gold_valid.columns:
    _gold_syms = gold_valid["Symbol"].dropna().astype(str).head(3).tolist()

st.session_state["stock_syms"] = _stock_syms
st.session_state["fund_names"] = _fund_names
st.session_state["gold_syms"] = _gold_syms

try:
    news_items = get_portfolio_news(
        stock_symbols=_stock_syms,
        fund_names=_fund_names,
        gold_symbols=_gold_syms,
    )
except Exception:
    news_items = []

groups = []
if news_items:
    groups = group_by_asset(news_items, max_groups=9, min_nri_tax_groups=1, min_macro_groups=1)



# ==================================================
# PORTFOLIO INTELLIGENCE (foundation, Phase 1C)
# Read-only deterministic roll-up over facts the page already computed: the
# canonical register, the four books, the MF holdings disclosure cache, the P&L
# drivers, snapshot history and the news feed. Nothing here is invented — a
# missing input surfaces as "Insufficient evidence". Synthesis is rule-based
# (DeterministicProvider); no external AI is connected. Pure modules in
# lib/intelligence; the page only feeds and renders.
# ==================================================
_intel_briefing = None
try:
    if register is not None:
        _intel_facts = intel_exposure.build_exposure_facts(
            register=register,
            mf_valid=mf_valid if "mf_valid" in dir() else None,
            stocks_valid=stocks_valid if "stocks_valid" in dir() else None,
            gold_valid=gold_valid if "gold_valid" in dir() else None,
            fd_valid=fd_valid if "fd_valid" in dir() else None,
            amfi_codes=amfi_codes,
            holdings_by_scheme=intel_exposure.load_holdings_cache(),
            now=now_ist,
        )
        _intel_evidence = intel_evidence.build_evidence_bag(
            news_items=news_items if "news_items" in dir() else None,
            coverage=_intel_facts.coverage,
            drivers=cc_drivers,
            history_df=history_df if "history_df" in dir() else None,
            now=now_ist,
        )
        _intel_fd = fd if "fd" in dir() and fd is not None and not fd.empty else None
        _intel_signals = intel_signals.evaluate_signals(
            _intel_facts, _intel_evidence,
            mf_valid=mf_valid if "mf_valid" in dir() else None,
            fd_df=_intel_fd,
            now=now_ist,
        )
        _intel_briefing = intel_build_briefing(
            facts=_intel_facts,
            evidence=_intel_evidence,
            signals=_intel_signals,
            question="What deserves attention this week?",
            provider=DeterministicIntelProvider(),
        )
        st.session_state["cc_intel_briefing"] = _intel_briefing
except Exception as _intel_err:
    _intel_briefing = None
    st.caption(f"Portfolio Intelligence unavailable this run: {_intel_err}")



# ==================================================
# RESEARCH & SYNTHESIS (evidence-based research brief, v1)
# Answers: what changed, which external developments map to the portfolio, what
# deserves attention, what invalidates a conclusion, and where evidence is thin.
# Deterministic and network-free: reuses the facts/evidence/signals the briefing
# already built plus cache-read-only NAV/holdings/gateway records and the
# snapshot delta. Synthesis is rule-based; no AI provider is connected.
# Nothing here is an order.
# ==================================================
_research_brief = None
try:
    if _intel_briefing is not None:
        _pm_index = intel_mapping.build_portfolio_index(
            register=register,
            mf_valid=mf_valid if "mf_valid" in dir() else None,
            stocks_valid=stocks_valid if "stocks_valid" in dir() else None,
            gold_valid=gold_valid if "gold_valid" in dir() else None,
            fd_valid=fd_valid if "fd_valid" in dir() else None,
            amfi_codes=amfi_codes,
        )
        _nav_evs = intel_research.list_source_results(
            (intel_mf.load_mf_nav_evidence(limit=2000, only_isins=_pm_index.isins or None,
                                           now=now_ist),))
        _hold_evs = intel_research.list_source_results(
            (intel_mf.load_mf_holdings_evidence(now=now_ist),))
        # ---- portfolio-aware live research cohort (network-free) ----
        # Deriving the plan and reading cached gnews/gateway records is safe on
        # every page load; live retrieval happens ONLY via the explicit refresh
        # button in the "Current External Developments" expander below. News is
        # OBSERVED FACT evidence labeled with exact-identifier relevance and can
        # never alter any number on this page.
        _live_plan = intel_live.build_live_plan(
            stock_symbols=list(_stock_syms or ()),
            fund_names=list(_fund_names or ()),
            gold_symbols=list(_gold_syms or ()),
            has_usd_book=bool(intel_live.usd_book_present(_intel_facts)),
            now=now_ist,
        )
        _live_cohort = intel_live.load_live_cohort(plan=_live_plan, now=now_ist)
        _cohort_evs = _live_cohort.to_evidence() if _live_cohort.has_records else ()
        # The cache-backed cohort replaces the generic page-news feed items in the
        # base evidence AND becomes the gateway-scored external developments, so
        # deterministic research ranks portfolio-mapped stories first.
        _research_evidence = intel_evidence.EvidenceBag(
            items=tuple(e for e in _intel_evidence.items
                        if not e.id.startswith("ev:news:")) + _cohort_evs)
        _gateway_evidence = _cohort_evs if _cohort_evs else \
            intel_research.gateway_cached_evidence(now=now_ist)
        _delta = intel_research.delta_from_history(
            history_df if "history_df" in dir() else None)
        _research_brief = intel_research.build_research_brief(
            facts=_intel_facts,
            evidence=_research_evidence,
            signals=_intel_signals,
            drivers=cc_drivers if "cc_drivers" in dir() else None,
            delta=_delta,
            portfolio_index=_pm_index,
            nav_evidence=_nav_evs,
            holdings_evidence=_hold_evs,
            gateway_evidence=_gateway_evidence,
            question="What changed, and where is the evidence thin?",
            now=now_ist,
        )
        st.session_state["cc_research_brief"] = _research_brief
except Exception as _research_err:
    _research_brief = None
    st.caption(f"Research & Synthesis unavailable this run: {_research_err}")



# PHASE 1B — delta decomposition between the two most recent snapshots.
# Shows per-class Invested-Basis Change vs Market/Valuation Change. A legacy
# (pre-Phase 1B) prior snapshot cannot be decomposed and is flagged.
st.markdown(ui_section("Snapshot delta \u00b7 change since prior snapshot"), unsafe_allow_html=True)
if len(history_df) >= 2:
    _hist_sorted = history_df.sort_values("date").reset_index(drop=True)
    _delta = snapshot_delta(_hist_sorted.iloc[-2], _hist_sorted.iloc[-1])
    if _delta["available"]:
        _delta_rows = []
        for _cls in ASSET_CLASSES:
            _d = _delta["by_class"].get(_cls)
            if _d is None:
                _delta_rows.append({"Asset Class": _cls, "\u0394 Current Value": None,
                                    "Invested-Basis Change (not cash flow)": None, "Market/Valuation Change": None})
            else:
                _delta_rows.append({"Asset Class": _cls,
                                    "\u0394 Current Value": round(_d["delta_current"], 2),
                                    "Invested-Basis Change (not cash flow)": round(_d["invested_basis_change"], 2),
                                    "Market/Valuation Change": round(_d["market_valuation_change"], 2)})
        _dt = _delta["totals"]
        _delta_rows.append({"Asset Class": "TOTAL",
                            "\u0394 Current Value": round(_dt["delta_current"], 2),
                            "Invested-Basis Change (not cash flow)": round(_dt["invested_basis_change"], 2),
                            "Market/Valuation Change": round(_dt["market_valuation_change"], 2)})
        st.dataframe(pd.DataFrame(_delta_rows), hide_index=True, use_container_width=True)
        _dcap = [NOT_A_CASHFLOW_LABEL]
        if _delta["unattributed_abs"] > 1e-6:
            _dcap.append(f"Unattributed / unavailable: \u20B9{_delta['unattributed_abs']:.2f}")
        if _delta["fcnr"] is not None:
            _dcap.append(
                f"FCNR \u0394 interest {format_inr(_delta['fcnr']['delta_interest'])} \u00b7 "
                f"\u0394 FX on principal {format_inr(_delta['fcnr']['delta_fx'])}"
            )
        st.caption(" \u00b7 ".join(_dcap))
    else:
        st.caption(f"{_delta['reason']} (|\u0394| \u2248 \u20B9{_delta['unattributed_abs']:,.0f})")
else:
    st.caption("Add a second snapshot (next day\u2019s run) to see the \u0394 Current Value decomposition.")


# ==================================================
# CURRENT EXTERNAL DEVELOPMENTS — portfolio-aware live research
# Cache-read-only cohort; live retrieval happens ONLY via the explicit refresh
# button. Records stay OBSERVED FACT evidence labelled by exact-identifier
# relevance and never change the numbers computed above.
# ==================================================
st.markdown(ui_section("Current external developments · portfolio-aware"),
            unsafe_allow_html=True)
if "_live_cohort" not in dir() or _live_cohort is None:
    st.markdown(ui_empty(
        "No live research cohort", "The research layer did not build this run."),
        unsafe_allow_html=True)
else:
    try:
        _live_caption = (f"**{_live_cohort.record_count} cached record(s)** "
                         f"({len(_live_cohort.news_records)} news · "
                         f"{len(_live_cohort.gateway_records)} gateway)")
        if _live_cohort.last_retrieved_at is not None:
            _live_caption += f" · last retrieved {_live_cohort.last_retrieved_at:%d %b %Y %H:%M} UTC"
        if _live_cohort.stale_sources:
            _live_caption += (f" · stale sources: {', '.join(_live_cohort.stale_sources)} "
                              "(refresh to update)")
        st.caption(_live_caption)
        _row_a, _row_b = st.columns([1, 3])
        with _row_a:
            if st.button("Refresh research evidence (on demand)",
                         key="cc_live_refresh"):
                with st.spinner("Fetching live research evidence…"):
                    st.session_state["cc_live_result"] = intel_live.run_live_research(
                        facts=_intel_facts, now=now_ist, plan=_live_plan,
                    )
                    st.session_state["cc_live_refreshed_at"] = now_ist
                st.rerun()
        with _row_b:
            _live_result = st.session_state.get("cc_live_result")
            if _live_result is not None and _live_result.refreshed_at is not None:
                st.caption(f"Last explicit refresh: {_live_result.refreshed_at:%d %b %Y %H:%M} UTC · "
                           f"status: {_live_result.status} · "
                           f"{len(_live_result.failures)} failure(s)")
                if _live_result.failures:
                    with st.expander(f"Refresh failures ({len(_live_result.failures)})"):
                        for _src, _reason in _live_result.failures:
                            st.caption(f"· {_src}: {_reason}")
        _dev_rows = intel_live.development_rows(_live_cohort, index=_pm_index, now=now_ist)
        if _dev_rows:
            _dev_cards = []
            for _d in _dev_rows[:8]:
                _mapped = str(_d.get("Relevance", "no")).strip().lower() != "no"
                _dev_cards.append(ui_research_row(
                    title=str(_d.get("Development", "")),
                    meta=str(_d.get("Published") or ""),
                    body=str(_d.get("Category") or ""),
                    tag="MAPPED" if _mapped else "CONTEXT",
                    href=str(_d.get("Link") or ""),
                ))
            st.markdown(ui_research_grid(_dev_cards), unsafe_allow_html=True)
            with st.expander(f"Full developments table ({len(_dev_rows)} rows)"):
                st.dataframe(
                    pd.DataFrame(_dev_rows[:20]), hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Development": st.column_config.TextColumn(width="large"),
                        "Affected": st.column_config.TextColumn(width="small"),
                        "Category": st.column_config.TextColumn(width="small"),
                        "Source": st.column_config.TextColumn(width="small"),
                        "Published": st.column_config.TextColumn(width="small"),
                        "Quality": st.column_config.NumberColumn(format="%.2f"),
                        "Relevance": st.column_config.TextColumn(width="small"),
                        "Link": st.column_config.TextColumn(width="small"),
                    })
            st.caption("Relevance uses exact identifier matching only "
                       "(lib.intelligence.sources.mapping), never fuzzy. Quality = "
                       "deterministic evidence score (mapped first, fresh above stale). "
                       "All records are OBSERVED FACT evidence from Google News RSS and "
                       "the FRED/SEC gateway cache — they never alter the numbers above.")
            if "groups" in dir() and groups:
                _news_chips = "".join(ui_badge(
                    ("NEGATIVE" if g["sentiment"] == "red"
                     else ("POSITIVE" if g["sentiment"] == "green" else "NEUTRAL"))
                    + " · " + g["asset"],
                    "negative" if g["sentiment"] == "red"
                    else ("positive" if g["sentiment"] == "green" else "neutral"))
                    for g in groups)
                st.markdown(f'<div class="t-caption">News by asset: {_news_chips}</div>',
                            unsafe_allow_html=True)
            st.page_link("pages/4_News.py", label="Open Intel & News →", icon="📰")
        else:
            st.caption("No cached news/gateway records yet — press 'Refresh research "
                       "evidence' to fetch. A network call happens only on that explicit "
                       "action, never on page open.")
        _st_rows = intel_live.live_status(now=now_ist)
        if _st_rows:
            with st.expander("Live research cache status"):
                st.dataframe(pd.DataFrame(_st_rows), hide_index=True,
                             use_container_width=True)
    except Exception as _live_render_err:
        st.caption(f"Live research panel unavailable: {_live_render_err}")

st.markdown("---")


# ==================================================
# RESEARCH & SYNTHESIS — executive readout (deterministic, network-free)
# ==================================================
st.markdown(ui_section("Research & Synthesis · decision readout"),
            unsafe_allow_html=True)
if _research_brief is not None:
    try:
        _rb = _research_brief
        st.markdown(
            f"**Research brief {_rb.as_of.strftime('%d %b %Y %H:%M')}** — "
            f"{len(_rb.changes)} change row(s) · {_rb.mapped_count} mapped external "
            f"record(s) · {len(_rb.risks)} risk(s) · {len(_rb.gaps)} evidence gap(s).")
        if _rb.synthesis is not None:
            st.markdown(f"**Synthesis ({_rb.synthesis.model})** — {_rb.synthesis.summary}")

        if _rb.changes:
            st.markdown("**What changed this run**")
            _ch = pd.DataFrame([
                {
                    "Kind": c.kind.replace("_", " "),
                    "Item": c.label,
                    "Amount (INR)": f"{c.amount:,.0f}" if c.amount is not None else "—",
                    "Note": c.note,
                }
                for c in _rb.changes
            ])
            st.dataframe(_ch, hide_index=True, use_container_width=True,
                         column_config={"Note": st.column_config.TextColumn(width="large")})
            st.caption(_rb.not_a_cashflow_label)

        if _rb.risks:
            st.markdown("**Risks that deserve attention**")
            _risk_items = [{
                "level": "warning" if r.strength in ("weak", "moderate") else "critical",
                "title": r.title,
                "body": r.statement,
                "what": "invalidated by: " + r.invalidation,
            } for r in _rb.risks[:5]]
            st.markdown(ui_watch(_risk_items), unsafe_allow_html=True)

        if _rb.research_needs:
            st.markdown("**Research needs (decision-support, not orders)**")
            _needs = [ui_research_row(
                title=n.title,
                meta=f"strength {n.strength}",
                body=n.statement,
            ) for n in _rb.research_needs[:5]]
            st.markdown(ui_research_grid(_needs), unsafe_allow_html=True)

        if _rb.gaps:
            st.markdown("**Where evidence is insufficient**")
            st.markdown(ui_evidence(list(_rb.gaps[:6])), unsafe_allow_html=True)

        if _rb.synthesis is not None and _rb.synthesis.claims:
            st.markdown(f"**Claims ({_rb.synthesis.model})**")
            for _c in _rb.synthesis.claims:
                st.caption(("✓ " if _c.supported else "⚠ ") + _c.text)
        if _rb.synthesis_reason:
            st.caption(f"Reason: {_rb.synthesis_reason}")
        st.caption("Synthesis is deterministic rule-based (no AI provider connected). "
                   "Every number comes from this page's own calc or cached statutory "
                   "disclosures; decision-support only — nothing here is an order.")
    except Exception as _research_render_err:
        st.caption(f"Research & Synthesis render skipped: {_research_render_err}")
else:
    st.markdown(ui_unavailable(
        "Research brief unavailable", "The research layer did not build this run."),
        unsafe_allow_html=True)

st.markdown("---")


# ==================================================
# AI RESEARCH (explicit opt-in only — NEVER called during page load).
# Provider-neutral: talks to lib.intelligence.ai, model is switchable via env.
# Deterministic facts + the existing ResearchBrief stay the source of truth.
# ==================================================
if _research_brief is not None:
    with st.expander("AI Research · provider-grounded interpretation (opt-in)"):
        try:
            _ai_cfg = intel_ai.ai_config_status()
            st.caption(
                f"Provider: **{_ai_cfg['provider']}** · Model: **{_ai_cfg['model']}** · "
                f"Structured output: {'on' if _ai_cfg['structured_output'] else 'off'} · "
                f"Configured: **{'yes' if _ai_cfg['configured'] else 'no'}**")
            if _ai_cfg["configured"]:
                st.caption(
                    "Pressing the button sends ONLY a minimal evidence-grounded context "
                    "(deterministic totals and change summaries, a bounded evidence "
                    "catalog, and the allow-list of evidence ids) to the configured "
                    "provider. Raw positions, account numbers, holder names and "
                    "credentials are never sent. The deterministic Research Brief above "
                    "is unaffected either way.")
            else:
                st.warning(
                    "No AI API key configured. Set `AI_API_KEY` in the environment/"
                    "secrets (optionally `AI_PROVIDER`, `AI_MODEL`, `AI_BASE_URL`, "
                    "`AI_TIMEOUT_SECONDS`) to enable the AI research provider. Until "
                    "then the deterministic Research Brief is the only synthesis — "
                    "unchanged.")
            _ai_fp = (
                tuple(sorted(_research_brief.totals.items())),
                _research_brief.evidence_count,
                _research_brief.mapped_count,
                len(_research_brief.changes),
                len(_research_brief.external),
                len(_research_brief.gaps),
            )
            if st.session_state.get("cc_ai_outcome_for") != _ai_fp:
                st.session_state.pop("cc_ai_outcome", None)
            if st.button("Run AI research (explicit call to the configured provider)",
                         key="cc_ai_run",
                         disabled=not _ai_cfg["configured"]):
                with st.spinner("Running AI research…"):
                    st.session_state["cc_ai_outcome"] = intel_ai.run_ai_research(
                        brief=_research_brief,
                        facts=_intel_facts.all_facts()
                            if _intel_facts is not None else (),
                        evidence=tuple(_intel_evidence.items)
                            if _intel_evidence is not None else (),
                        now=now_ist)
                    st.session_state["cc_ai_outcome_for"] = _ai_fp
            _ai_outcome = st.session_state.get("cc_ai_outcome")
            if _ai_outcome is None:
                st.caption("Not run yet — press the button to invoke the AI provider "
                           "explicitly. Nothing is sent to any external provider "
                           "during normal page loads.")
            elif _ai_outcome.status == intel_ai.STATUS_OK and _ai_outcome.assessment is not None:
                _a = _ai_outcome.assessment
                st.markdown(ui_section(
                    f"AI interpretation · {_a.provider} / {_a.model} ({_a.requested_format} transport)"))
                st.caption(
                    f"Confidence **{(_a.confidence or 0.0):.2f}** · "
                    f"{_a.latency_ms:.0f} ms · {_a.created_at:%d %b %Y %H:%M} · "
                    f"{len(_a.findings)} finding(s), "
                    f"{sum(1 for f in _a.findings if f.grounded)} evidence-grounded")
                if _a.overall_assessment:
                    st.markdown(_a.overall_assessment)
                if _a.uncertainty:
                    st.caption(f"Uncertainty: {_a.uncertainty}")
                for _section in ("key_findings", "risks", "opportunities", "research_needs"):
                    _findings = [f for f in _a.findings if f.section == _section]
                    if not _findings:
                        continue
                    st.markdown(f"**{_section.replace('_', ' ').title()}**")
                    for _f in _findings:
                        _mark = "✓" if _f.grounded else "⚠"
                        st.markdown(f"{_mark} **[{_f.kind}]** {_f.text}")
                        if _f.evidence_ids:
                            st.caption("evidence: " + ", ".join(_f.evidence_ids))
                        if _f.downgrade_reason:
                            st.caption(f"downgraded: {_f.downgrade_reason}")
                if _a.invalidation_conditions:
                    st.markdown("**Invalidated by**")
                    for _cond in _a.invalidation_conditions:
                        st.caption("↻ " + _cond)
                if _a.limitations:
                    st.markdown("**Limitations**")
                    for _lim in _a.limitations:
                        st.caption("· " + _lim)
                if _a.downgrades:
                    st.markdown("**Grounding / validation notes**")
                    for _dg in _a.downgrades:
                        st.caption("× " + _dg)
                st.caption(
                    "AI INTERPRETATION only — every deterministic number above "
                    "(and in the Research Brief) remains authoritative. Nothing "
                    "here is financial advice, a recommendation to trade, or an "
                    "order; gold/SGB/FD amounts are restated, never recomputed by "
                    "the model.")
            else:
                st.warning(f"{_ai_outcome.status_label}: {_ai_outcome.reason}")
                st.caption("Falling back to the deterministic Research Brief "
                           "synthesis — unchanged.")
        except Exception as _ai_err:
            st.caption(f"AI Research section unavailable: {_ai_err}")


# ==================================================
# DEEPER ANALYTICS — compact drill-down (tabs)
# ==================================================
st.markdown(ui_section("Deeper analytics"), unsafe_allow_html=True)
_t_h, _t_hist, _t_hold, _t_struct, _t_intel = st.tabs(
    ["Health & allocation", "History", "Holdings", "Structure", "Intelligence"])

with _t_h:

    # ==================================================
    # DETAILED POSTURE — health factors + allocation
    # ==================================================
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(ui_section("Portfolio health breakdown"), unsafe_allow_html=True)
        bd = pd.DataFrame({"Factor": list(factor_scores.keys()), "Score": list(factor_scores.values())})
        fig_h = go.Figure(go.Bar(x=bd["Score"], y=bd["Factor"], orientation="h",
            marker_color=["#ef4444" if s < 55 else ("#f59e0b" if s < 75 else "#22c55e") for s in bd["Score"]],
            text=[f"{s:.0f}" for s in bd["Score"]], textposition="outside"))
        fig_h.update_layout(height=210, margin=dict(t=5, b=5, l=5, r=25), xaxis=dict(range=[0, 105], showgrid=False),
                             paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#c2c9d6")
        st.plotly_chart(fig_h, use_container_width=True, key="chart_health")

        _why = []
        if factor_scores.get("Liquidity", 100) < 50:
            _why.append(
                f"Deployable liquidity is {true_liquid_pct:.1f}% of NW "
                f"(liquid MF + deposits maturing ≤90d). Long FCNR is not treated as cash."
            )
        if factor_scores.get("Allocation", 100) < 40:
            _gap40 = max(0, 0.40 * total_networth - total_equity)
            _why.append(
                f"Equity (ex-liquid) is {equity_pct:.1f}% of NW — NRI books often run lower by design; "
                f"~{format_inr(_gap40)} more equity would reach 40%."
            )
        if factor_scores.get("Concentration", 100) < 60:
            _why.append("Top holdings concentration is elevated.")
        if factor_scores.get("Performance", 100) < 55:
            _why.append("Trailing fund performance vs Nifty50 is mixed.")
        if fcnr_pct > 0:
            _why.append(
                f"FCNR is {fcnr_pct:.1f}% of NW — USD principal + interest + INR FX vs deposit-date rate "
                f"(not the same as resident INR FD)."
            )
        if inr_fd_pct > 0:
            _why.append(f"INR FDs are {inr_fd_pct:.1f}% of NW (domestic fixed income).")
        if gold_pct > 0:
            _why.append(f"Gold is {gold_pct:.1f}% of NW (SGB + ETFs + FoFs) — diversifier, not equity.")
        if not _why:
            _why.append("No single factor is dragging hard — score is moderate overall.")
        _why_html = "".join(f"<li>{x}</li>" for x in _why)
        st.markdown(
            f'<div class="t-card"><span class="t-card-title">'
            f'Why score is {health_score:.0f}? (NRI view)</span>'
            f'<ul class="t-list" style="margin-top:6px">{_why_html}</ul></div>',
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(ui_section("Asset allocation · NRI books"), unsafe_allow_html=True)
        alloc_df = pd.DataFrame({
            "Asset": ["Equity (stocks + non-liquid MF)", "Liquid MF", "INR FD", "FCNR (USD)", "Gold"],
            "Value": [total_equity, total_liquid_mf, total_inr_fd, total_fcnr, total_gold],
        })
        alloc_df = alloc_df[alloc_df["Value"] > 0].reset_index(drop=True)
        colors = ["#f59e0b", "#22c55e", "#3b82f6", "#06b6d4", "#eab308"]
        fig = px.pie(alloc_df, values="Value", names="Asset", hole=0.62, color_discrete_sequence=colors)
        fig.update_traces(textposition="inside", textinfo="percent", textfont_size=12)
        fig.update_layout(margin=dict(t=5, b=5, l=5, r=5), height=200, showlegend=False,
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#c2c9d6",
                           annotations=[dict(text=f"{format_inr_compact(total_networth)}<br>Net Worth",
                                             x=0.5, y=0.5, font_size=13, showarrow=False, font_color="#e5e9f0")])
        st.plotly_chart(fig, use_container_width=True, key="chart_alloc")
        legend_items = "".join(
            f'<li><span class="nm"><span style="color:{col}">●</span> {asset}</span>'
            f'<span class="amt">{((val / total_networth * 100) if total_networth else 0):.1f}% · {format_inr(val)}</span></li>'
            for asset, val, col in zip(alloc_df["Asset"], alloc_df["Value"], colors)
        )
        st.markdown(f'<ul class="t-alloc-legend">{legend_items}</ul>', unsafe_allow_html=True)

with _t_hold:
    st.markdown(ui_section("Mutual funds"), unsafe_allow_html=True)
    if not mf.empty:
        st.caption(
            f"{len(mf)} consolidated holdings — "
            f"'vs Nifty50' is a broad equity bar only (not each fund's official benchmark). "
            f"Mid/small/flexi/contra can look better or worse vs Nifty50 for the wrong reason. "
            f"'—' means insufficient history or debt-like category."
        )
        _mf_view = mf[["Owner", "Fund Name", "Category", "Current Value", "P&L", "Return %",
                        "1Y %", "3Y %", "5Y %", "vs Nifty50 1Y", "vs Nifty50 3Y", "vs Nifty50 5Y"]]
        st.dataframe(
            style_money_df(_mf_view),
            column_config={
                "Current Value": st.column_config.NumberColumn(format="₹%d"),
                "P&L": st.column_config.NumberColumn(format="₹%d"),
                "Return %": st.column_config.NumberColumn(format="%.1f%%"),
                "1Y %": st.column_config.NumberColumn(format="%.1f%%"),
                "3Y %": st.column_config.NumberColumn(format="%.1f%%"),
                "5Y %": st.column_config.NumberColumn(format="%.1f%%"),
                "vs Nifty50 1Y": st.column_config.NumberColumn(format="%.1f%%"),
                "vs Nifty50 3Y": st.column_config.NumberColumn(format="%.1f%%"),
                "vs Nifty50 5Y": st.column_config.NumberColumn(format="%.1f%%"),
            }, use_container_width=True, height=380)

    st.markdown(ui_section("Stocks"), unsafe_allow_html=True)
    if not stocks.empty:
        st.dataframe(
            style_money_df(stocks[["Owner", "Symbol", "Quantity", "Invested", "Current Price", "Current Value", "P&L", "Return %"]]),
            column_config={
                "Quantity": st.column_config.NumberColumn(format="%d"),
                "Invested": st.column_config.NumberColumn(format="₹%d"),
                "Current Value": st.column_config.NumberColumn(format="₹%d"),
                "P&L": st.column_config.NumberColumn(format="₹%d"),
                "Return %": st.column_config.NumberColumn(format="%.1f%%"),
                "Current Price": st.column_config.NumberColumn(format="₹%.2f"),
            }, use_container_width=True, height=380)
        st.caption("Fundamental red flags (P/E, debt/equity, promoter pledging) need paid/structured data — not shown here to avoid false precision.")

    st.markdown(ui_section("FCNR & INR FDs"), unsafe_allow_html=True)
    if not fd.empty:
        st.caption(
            "NRI view: USD rows are labeled FCNR (interest + FX vs deposit-date rate). "
            "INR rows are domestic FDs. Native currency and INR shown side by side — "
            "a FCNR is never displayed as though it were an INR deposit. Sorted by days to maturity."
        )
        _fd_cols = [c for c in [
            "Holder Name", "Product", "Currency", "Principal (Native)", "Principal (INR, at deposit FX)",
            "ROI %", "Days to Maturity", "Current Value (Native)", "Current Value (INR)",
            "Interest Return (INR)", "FX Gain/Loss (INR)", "Maturity Date",
        ] if c in fd.columns]
        _fd_view = fd[_fd_cols].copy()
        if "Days to Maturity" in _fd_view.columns:
            _fd_view = _fd_view.sort_values("Days to Maturity", ascending=True, na_position="last")
        st.dataframe(
            style_money_df(_fd_view, pnl_cols=("FX Gain/Loss (INR)", "Interest Return (INR)")),
            column_config={
                "Holder Name": st.column_config.TextColumn("Holder", width="medium"),
                "Product": st.column_config.TextColumn("Product", width="small"),
                "Currency": st.column_config.TextColumn("Ccy", width="small"),
                "Principal (Native)": st.column_config.NumberColumn("Principal", format="%.2f"),
                "Principal (INR, at deposit FX)": st.column_config.NumberColumn("Principal INR", format="%.0f"),
                "ROI %": st.column_config.NumberColumn("ROI %", format="%.2f%%", width="small"),
                "Days to Maturity": st.column_config.NumberColumn("Days left", width="small"),
                "Current Value (Native)": st.column_config.NumberColumn("Value (native)", format="%.2f"),
                "Current Value (INR)": st.column_config.NumberColumn("Value (INR)", format="%.0f"),
                "Interest Return (INR)": st.column_config.NumberColumn("Interest", format="%.0f"),
                "FX Gain/Loss (INR)": st.column_config.NumberColumn("FX P&L", format="%.0f"),
                "Maturity Date": st.column_config.TextColumn("Matures", width="small"),
            },
            use_container_width=True,
            hide_index=True,
        )

    st.markdown(ui_section("Gold"), unsafe_allow_html=True)
    if not gold.empty:
        st.caption(
            "Unified Gold book: Sovereign Gold Bonds (SGB…-GB), gold ETFs (e.g. GOLDBEES), and Gold ETF FoFs. "
            "Same rows as the Gold snapshot above — excluded from Stocks and Mutual Funds so gold appears in one book only. "
            "SGB maturity/interest are not invented — source file does not carry them."
        )
        _g_tab_cols = [c for c in ["Owner", "Symbol", "Quantity", "Invested", "Current Price", "Current Value", "P&L", "Return %"] if c in gold.columns]
        _g_tab = gold[_g_tab_cols]
        _g_tab_h = min(400, 48 + 28 * max(len(_g_tab), 1))
        st.dataframe(
            style_money_df(_g_tab),
            column_config={
                "Quantity": st.column_config.NumberColumn(format="%g"),
                "Invested": st.column_config.NumberColumn(format="₹%d"),
                "Current Value": st.column_config.NumberColumn(format="₹%d"),
                "P&L": st.column_config.NumberColumn(format="₹%d"),
                "Return %": st.column_config.NumberColumn(format="%.1f%%"),
                "Current Price": st.column_config.NumberColumn(format="₹%.2f"),
            }, use_container_width=True, height=_g_tab_h, hide_index=True)
        st.markdown(
            f'<div class="t-caption">Total Gold {format_inr(total_gold)} · {gold_pct:.1f}% of net worth</div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("No gold holdings identified in the current data.")


with _t_struct:
    # ==================================================
    # BY FAMILY MEMBER + CATEGORY MIX
    # ==================================================
    c3, c4 = st.columns(2)
    with c3:
        st.markdown(ui_section("By family member"), unsafe_allow_html=True)
        if register is not None and register_members is not None and not register_members.empty:
            owner_df = register_members.rename(columns={"Member": "Owner", "Current Value": "Value"})[["Owner", "Value"]]
        elif owner_map:
            owner_df = pd.DataFrame([{"Owner": k, "Value": v} for k, v in owner_map.items()])
        else:
            owner_df = pd.DataFrame(columns=["Owner", "Value"])
        if not owner_df.empty:
            fig2 = px.bar(owner_df, x="Owner", y="Value", text_auto=".2s", color_discrete_sequence=["#3b82f6"])
            fig2.update_layout(margin=dict(t=5, b=5, l=5, r=5), height=240, showlegend=False,
                                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#c2c9d6")
            st.plotly_chart(fig2, use_container_width=True, key="chart_owner")
    with c4:
        st.markdown(ui_section("Category mix (MF) · overlap proxy"), unsafe_allow_html=True)
        if not mf_valid.empty:
            cat_df = mf_valid.groupby("Category")["Current Value"].sum().reset_index().sort_values("Current Value", ascending=False)
            fig3 = px.bar(cat_df, x="Current Value", y="Category", orientation="h", color_discrete_sequence=["#22c55e"])
            fig3.update_layout(margin=dict(t=5, b=5, l=5, r=5), height=240, showlegend=False,
                                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#c2c9d6")
            st.plotly_chart(fig3, use_container_width=True, key="chart_cat")
            st.markdown(ui_caption("Category-level concentration, not real stock-level overlap — genuine holdings-level overlap needs paid portfolio-disclosure data with no free equivalent."), unsafe_allow_html=True)


    # ==================================================
    # TOP 5 STOCK CONCENTRATION + HOLDINGS SNAPSHOT
    # ==================================================
    snap_l, snap_r = st.columns([1, 1])
    with snap_l:
        st.markdown(ui_section("Top 5 stock concentration"), unsafe_allow_html=True)
        if not stocks_valid.empty and total_stocks > 0:
            top5 = stocks_valid.nlargest(5, "Current Value")[["Symbol", "Current Value"]].copy()
            top5_sum = top5["Current Value"].sum()
            other_val = max(total_stocks - top5_sum, 0)
            pie_df = pd.concat([
                top5.rename(columns={"Symbol": "Name", "Current Value": "Value"}),
                pd.DataFrame([{"Name": "Others", "Value": other_val}]),
            ], ignore_index=True)
            fig_t5 = px.pie(pie_df, values="Value", names="Name", hole=0.55,
                            color_discrete_sequence=["#3b82f6", "#f59e0b", "#a855f7", "#ef4444", "#22c55e", "#64748b"])
            fig_t5.update_traces(textposition="inside", textinfo="percent", textfont_size=11)
            fig_t5.update_layout(margin=dict(t=5, b=5, l=5, r=5), height=220, showlegend=True,
                                 legend=dict(orientation="h", y=-0.15, font=dict(size=10)),
                                 paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#c2c9d6",
                                 annotations=[dict(text=f"{top5_stock_pct:.0f}%<br>Top 5", x=0.5, y=0.5,
                                                   font_size=14, showarrow=False, font_color="#e5e9f0")])
            st.plotly_chart(fig_t5, use_container_width=True, key="chart_top5")
        else:
            st.caption("No stock holdings for concentration chart.")

    with snap_r:
        st.markdown(ui_section("Holdings snapshot · Gold"), unsafe_allow_html=True)
        if not gold_valid.empty:
            _g_cols = [c for c in ["Owner", "Symbol", "Quantity", "Invested", "Current Price", "Current Value", "P&L", "Return %"] if c in gold_valid.columns]
            _g = gold_valid[_g_cols].copy()
            _g_height = min(360, 48 + 28 * max(len(_g), 1))
            st.dataframe(
                style_money_df(_g),
                column_config={
                    "Quantity": st.column_config.NumberColumn(format="%g"),
                    "Invested": st.column_config.NumberColumn(format="₹%d"),
                    "Current Value": st.column_config.NumberColumn(format="₹%d"),
                    "P&L": st.column_config.NumberColumn(format="₹%d"),
                    "Return %": st.column_config.NumberColumn(format="%.1f%%"),
                    "Current Price": st.column_config.NumberColumn(format="₹%.2f"),
                },
                use_container_width=True, height=_g_height, hide_index=True,
            )
            st.markdown(
                f'<div class="t-caption">Total Gold {format_inr(total_gold)} · {gold_pct:.1f}% of net worth · SGB/ETF via Groww/Yahoo · FoFs via AMFI</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("No gold holdings identified.")


with _t_intel:
    st.caption("Intelligence layers are read-only: deterministic signals, "
               "coverage and gateway cache status. No AI provider is "
               "connected or triggered on page load.")

    if _intel_briefing is not None:
        with st.expander("Portfolio Intelligence · signals, coverage & look-through"):
            try:
                _sig_rows = [
                    {
                        "Level": s.level,
                        "Rule": s.label,
                        "What we know": s.message,
                        "Invalidated by": s.invalidation,
                    }
                    for s in _intel_briefing.signals
                    if s.level != "info"
                ]
                if _sig_rows:
                    _sig_df = pd.DataFrame(_sig_rows)
                    st.dataframe(
                        _sig_df,
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "Level": st.column_config.TextColumn("Level", width="small"),
                            "Rule": st.column_config.TextColumn("Rule", width="medium"),
                            "What we know": st.column_config.TextColumn("What we know", width="large"),
                            "Invalidated by": st.column_config.TextColumn("Invalidated by", width="large"),
                        },
                    )
                else:
                    st.caption("No elevated signal this run — the rules see nothing abnormal.")
                st.caption("Signal rules are deterministic (lib.intelligence.signals); levels only "
                           "ever reach info when their fact is missing (insufficient evidence).")

                _cov = _intel_facts.coverage
                _cov_pct = f"{_cov.coverage_pct:.0f}%" if _cov.coverage_pct is not None else "n/a"
                st.markdown(
                    f"**Holdings disclosure coverage {_cov_pct}** — "
                    f"{_cov.covered_funds} of {_cov.covered_funds + _cov.missing_funds} fund(s) "
                    f"disclose holdings; look-through uses disclosed market values ("
                    f"{'market-value-derived' if 'market_value_derived' in _intel_facts.weight_basis else 'published weights'}).",
                    unsafe_allow_html=False,
                )
                if _cov.missing_funds:
                    st.caption("No disclosure (insufficient evidence): " + ", ".join(list(_cov.missing_names)[:5]))

                _uds = intel_exposure.underlying_df(_intel_facts)
                if not _uds.empty:
                    _top = _uds.sort_values("value_inr", ascending=False).head(5)
                    st.markdown(f"**Top underlying positions (through funds, top {len(_top)})**")
                    st.dataframe(
                        _top[["name", "value_inr", "pct_of_assets", "schemes", "confidence"]],
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "name": st.column_config.TextColumn("Security"),
                            "value_inr": st.column_config.NumberColumn("Value (INR)", format="₹%d"),
                            "pct_of_assets": st.column_config.NumberColumn("% of assets", format="%.1f%%"),
                            "schemes": st.column_config.TextColumn("Via funds"),
                            "confidence": st.column_config.NumberColumn("Confidence", format="%.2f"),
                        },
                    )

                _synth = _intel_briefing.synthesis
                if _synth is not None:
                    st.markdown(f"**Synthesis ({_synth.model})** — {_synth.summary}")
                    if _synth.claims:
                        for _c in _synth.claims:
                            st.caption(("✓ " if _c.supported else "⚠ ") + _c.text)
                if _intel_briefing.synthesis_reason:
                    st.caption(f"Reason: {_intel_briefing.synthesis_reason}")
                st.caption("Decision-support only: the numbers above come from this page's own "
                           "calc (register/drivers/snapshots) and statutory disclosure caches. "
                           "No AI provider is connected; nothing here is an order.")
            except Exception as _intel_render_err:
                st.caption(f"Portfolio Intelligence render skipped: {_intel_render_err}")


    # ---- Intelligence data gateway: read-only provider status (no network) ----
    try:
        _gw_rows = intel_gateway_status()
        st.session_state["cc_intel_gateway_status"] = _gw_rows
        if _gw_rows:
            with st.expander("Portfolio Intelligence · data gateway (external-provider status)"):
                st.dataframe(pd.DataFrame(_gw_rows), hide_index=True, use_container_width=True)
                st.caption("Read-only cache status; no external call happens on page open. "
                           "FRED/SEC/MF evidence is normalized to observed FACT evidence by "
                           "lib.intelligence.sources and never alters the numbers above.")
    except Exception as _gw_err:
        st.session_state["cc_intel_gateway_status"] = []
        st.caption(f"Data gateway status unavailable: {_gw_err}")


# ==================================================
# VERIFICATION — reconciliation + data integrity + asset register
# Total is only ever "verified" when the register agrees with the page and the
# drivers explain the P&L within the documented rounding bound.
# ==================================================
st.markdown(ui_section("Verification · reconciliation & data conditions"),
            unsafe_allow_html=True)
for name, passed, detail in recon_tests:
    mark = ui_badge("✓ PASS", "positive") if passed else ui_badge("✗ FAIL", "negative")
    st.markdown(f"{mark} — {name} ({detail})", unsafe_allow_html=True)

if integrity_issues:
    sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    integrity_issues.sort(key=lambda x: sev_order.get(x[0], 9))
    with st.expander(f"Data integrity check — {len(integrity_issues)} issue(s) found"):
        for sev, msg in integrity_issues:
            st.markdown(f"**{sev}** — {msg}")

# PHASE 1A — additive asset-register view by canonical class.
# Display-only; totals mirror the reconciliation entries above. No re-valuation here.
if register_classes is not None and not register_classes.empty:
    with st.expander("Asset register · by canonical class"):
        _class_view = register_classes.copy()
        _class_view["Current (INR)"] = _class_view.apply(
            lambda r: pd.NA if not r["Data Backed"] else r["Current Value"], axis=1
        )
        _class_view["Invested (INR)"] = _class_view.apply(
            lambda r: pd.NA if not r["Data Backed"] else r["Invested"], axis=1
        )
        st.dataframe(
            _class_view[["Asset Class", "Current (INR)", "Invested (INR)", "Data Backed"]],
            hide_index=True, use_container_width=True,
            column_config={
                "Current (INR)": st.column_config.NumberColumn(
                    "Current (INR)", format="₹ %,d",
                ),
                "Invested (INR)": st.column_config.NumberColumn(
                    "Invested (INR)", format="₹ %,d",
                ),
            },
        )
        st.caption("No-data classes (Retirement / Real Estate / Savings/Cash / Liabilities) have no workbook source and are never summed.")


st.markdown("---")
src = "AMFI live" if (len(amfi_navs) and not amfi_cache_date) else (f"AMFI cache {amfi_cache_date}" if amfi_cache_date else "AMFI offline")
_usd_lbl = ("%.2f" % usd_inr) if usd_inr else "n/a"
_footer = (
    "INR · USD "
    + _usd_lbl
    + " · "
    + now_ist.strftime("%d %b %Y %H:%M IST")
    + " · "
    + src
    + " (%d schemes) · Stocks/Gold ETF: Groww+Yahoo · Gold FoF: AMFI · Gold Rs/10g: goldprice.dev" % len(amfi_navs)
)
st.caption(_footer)

# ----- Pass matured FD amount to Deep Health -----
# Sums the INR current value of any FD that is already overdue (Days to
# Maturity < 0) or maturing within the next 14 days, so Deep Health's
# "Amount available" field is pre-filled with money that actually needs a
# decision right now. Falls back to 0 (no pre-fill) if fd/fd_valid aren't
# available or nothing qualifies.
try:
    if "fd" in dir() and fd is not None and not fd.empty and "Days to Maturity" in fd.columns:
        actionable = fd[fd["Days to Maturity"] <= 14]
        if not actionable.empty and "Current Value (INR)" in actionable.columns:
            matured_total = float(actionable["Current Value (INR)"].dropna().sum())
            if matured_total > 0:
                st.session_state["matured_fd_amount"] = matured_total
except Exception:
    pass
# ----- Read-only handoff to MF Health (does not change mf_valid or returns) -----
try:
    if "mf_valid" in dir() and mf_valid is not None and not mf_valid.empty:
        total = float(mf_valid["Current Value"].sum()) if "Current Value" in mf_valid.columns else 0.0
        records = []
        for _, row in mf_valid.iterrows():
            name = str(row["Fund Name"]) if "Fund Name" in mf_valid.columns else ""
            value = float(row["Current Value"]) if "Current Value" in mf_valid.columns else 0.0
            weight = (value / total * 100.0) if total > 0 else 0.0
            scheme_code = None
            if "amfi_codes" in dir() and amfi_codes and "ISIN" in mf_valid.columns:
                isin = str(row.get("ISIN", "")).strip()
                if isin and isin in amfi_codes:
                    try:
                        scheme_code = int(amfi_codes[isin])
                    except Exception:
                        scheme_code = amfi_codes[isin]
            records.append({
                "Fund Name": name,
                "Current Value": value,
                "Weight %": weight,
                "Scheme Code": scheme_code,
            })
        st.session_state["mf_holdings_for_health"] = records
except Exception:
    pass

# ----- Read-only handoffs for Asset Detail (drill-down dossier) -----
# Books / totals / live cohort are exported as session data so the detail page
# renders the exact same numbers this page computed — never re-valued there.
try:
    st.session_state["cc_books"] = {
        "mf": mf_valid if "mf_valid" in dir() else None,
        "stocks": stocks_valid if "stocks_valid" in dir() else None,
        "gold": gold_valid if "gold_valid" in dir() else None,
        "fd": fd_valid if "fd_valid" in dir() else None,
    }
    st.session_state["cc_assets"] = {
        "total_assets": float(total_networth),
        "total_invested": float(total_invested),
        "total_pnl": float(total_pnl),
        "equity_pct": float(equity_pct),
        "fcnr_pct": float(fcnr_pct),
        "inr_fd_pct": float(inr_fd_pct),
        "liquid_mf_pct": float(liquid_mf_pct),
        "gold_pct": float(gold_pct),
        "health_score": float(health_score),
    }
    st.session_state["cc_live_cohort"] = (
        _live_cohort if "_live_cohort" in dir() and _live_cohort is not None else None
    )
except Exception:
    pass
try:
    if news_items:
        st.session_state["cc_news_items"] = [
            {"title": g["asset"], "sentiment": g["sentiment"], "count": len(g["items"])}
            for g in groups
        ]
        st.session_state["cc_news_items_full"] = list(news_items)
except Exception:
    pass
