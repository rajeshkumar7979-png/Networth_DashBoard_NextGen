"""Publish the committed test book into the Command Center session keys.

Direct /funds, /holdings and /asset-intelligence do not run Command Center, so
those pages otherwise see an empty session. This module fills the same keys
from the workbook plus the already-committed AMFI cache. It does not fetch
NAV, does not reimplement trailing returns, and does not overwrite a book
Command Center has already published.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

SOURCE = "workbook+amfi-cache"


def _num(value):
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text


def load_amfi_cache(path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, {}, {}, None
    if not isinstance(payload, dict):
        return {}, {}, {}, None
    return (
        payload.get("nav") or {},
        payload.get("code") or {},
        payload.get("name") or {},
        payload.get("saved_at"),
    )


def _scheme_code(codes, isin):
    raw = codes.get(isin)
    if raw in (None, "", "-"):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return raw


def build_published_frames(fd, mf, stocks, amfi_navs=None, amfi_codes=None, saved_at=None):
    """Shape raw workbook frames into the columns roster and Funds already read."""
    navs = amfi_navs or {}
    codes = amfi_codes or {}
    mf_rows = []
    for _, row in mf.iterrows():
        isin = _text(row.get("ISIN")).upper()
        units = _num(row.get("Units"))
        invested = _num(row.get("Invested Amount"))
        nav = _num(navs.get(isin))
        current = units * nav if units is not None and nav is not None else invested
        if current is None:
            continue
        mf_rows.append({
            "Owner": _text(row.get("Owner")),
            "Fund Name": _text(row.get("Fund Name")),
            "ISIN": isin,
            "Scheme Code": _scheme_code(codes, isin),
            "Category": "",
            "Purchase Date": row.get("Purchase Date"),
            "Units": units,
            "Current NAV": nav,
            "Invested": invested if invested is not None else current,
            "Current Value": float(current),
            "1Y %": None,
            "3Y %": None,
            "5Y %": None,
        })
    mf_valid = pd.DataFrame(mf_rows)
    total = float(mf_valid["Current Value"].sum()) if not mf_valid.empty else 0.0
    if not mf_valid.empty and total > 0:
        mf_valid["Weight %"] = mf_valid["Current Value"] / total * 100.0
    elif not mf_valid.empty:
        mf_valid["Weight %"] = 0.0

    stock_rows = []
    for _, row in stocks.iterrows():
        symbol = _text(row.get("Ticker / Symbol") or row.get("Symbol")).upper()
        qty = _num(row.get("Quantity"))
        invested = _num(row.get("Invested Amount"))
        if not symbol:
            continue
        current = invested if invested is not None else 0.0
        stock_rows.append({
            "Owner": _text(row.get("Owner")),
            "Symbol": symbol,
            "Company": _text(row.get("Company Name") or row.get("Company")),
            "Exchange": _text(row.get("Exchange")) or "NSE",
            "Quantity": qty,
            "Avg Buy": _num(row.get("Avg Buy Price")),
            "Invested": invested if invested is not None else current,
            "Current Value": current,
        })
    stocks_valid = pd.DataFrame(stock_rows)

    fd_rows = []
    for _, row in fd.iterrows():
        holder = _text(row.get("Holder Name"))
        principal = _num(row.get("Principal Amount"))
        if not holder or principal is None or principal <= 0:
            continue
        available = _num(row.get("Available Balance"))
        current = available if available not in (None, 0.0) else principal
        fd_rows.append({
            "Holder": holder,
            "Account": _text(row.get("Account Number")),
            "Currency": _text(row.get("Currency")) or "INR",
            "Principal": principal,
            "Available": available,
            "Current Value": current,
            "Maturity": row.get("Maturity Date"),
        })
    fd_valid = pd.DataFrame(fd_rows)

    holdings = []
    for _, row in mf_valid.iterrows():
        holdings.append({
            "Owner": row.get("Owner"),
            "Fund Name": row.get("Fund Name"),
            "scheme_code": row.get("Scheme Code"),
            "ISIN": row.get("ISIN"),
            "Units": row.get("Units"),
            "current": row.get("Current Value"),
            "Current Value": row.get("Current Value"),
            "Weight %": row.get("Weight %"),
            "1Y %": None,
            "3Y %": None,
            "5Y %": None,
            "Current NAV": row.get("Current NAV"),
        })

    assets_total = (
        (pd.to_numeric(mf_valid["Current Value"], errors="coerce").fillna(0).sum() if not mf_valid.empty else 0)
        + (pd.to_numeric(stocks_valid["Current Value"], errors="coerce").fillna(0).sum() if not stocks_valid.empty else 0)
        + (pd.to_numeric(fd_valid["Current Value"], errors="coerce").fillna(0).sum() if not fd_valid.empty else 0)
    )
    return {
        "mf": mf_valid,
        "stocks": stocks_valid,
        "gold": pd.DataFrame(),
        "fd": fd_valid,
        "holdings": holdings,
        "assets": {
            "total": float(assets_total),
            "source": SOURCE,
            "as_of": saved_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        },
    }


def ensure_published_book():
    """Fill session keys once. Leave a Command Center publish untouched."""
    import streamlit as st
    from lib.config import AMFI_CACHE_PATH, EXCEL_PATH, resolve_book_path

    books = st.session_state.get("cc_books")
    holdings = st.session_state.get("mf_holdings_for_health")
    if isinstance(books, dict) and books.get("mf") is not None and holdings:
        return False
    book_path = resolve_book_path()
    # Honest book-mode flag for UI banners (sample vs private).
    try:
        resolved = book_path.resolve()
        sample = EXCEL_PATH.resolve()
        st.session_state["book_mode"] = "sample" if resolved == sample else "private"
        st.session_state["book_path_display"] = str(book_path)
    except Exception:
        st.session_state["book_mode"] = "unknown"
    if not book_path.exists():
        return False
    try:
        frames = pd.read_excel(book_path, sheet_name=None)
    except Exception:
        return False
    sheets = {str(name).lower().strip(): frame for name, frame in frames.items()}

    def pick(*names):
        for name in names:
            if name in sheets:
                return sheets[name]
        return pd.DataFrame()

    navs, codes, _names, saved_at = load_amfi_cache(AMFI_CACHE_PATH)
    published = build_published_frames(
        pick("fd", "fixed deposits", "fixed_deposits"),
        pick("mf", "mutual funds", "mutual_funds"),
        pick("stocks", "stock", "equities"),
        navs,
        codes,
        saved_at,
    )
    if not published["holdings"]:
        return False
    st.session_state["cc_books"] = {
        "mf": published["mf"],
        "stocks": published["stocks"],
        "gold": published["gold"],
        "fd": published["fd"],
    }
    st.session_state["cc_assets"] = published["assets"]
    st.session_state["mf_holdings_for_health"] = published["holdings"]
    st.session_state["cc_book_source"] = SOURCE
    label = (
        "Public sample book"
        if "Member A" in str(published["mf"].get("Owner", pd.Series(dtype=str)).head(1).tolist())
        else "Book"
    )
    st.session_state["cc_book_note"] = (
        f"{label} from {book_path.name}. Fund marks use the AMFI cache"
        + (f" saved {saved_at}." if saved_at else ".")
        + " Stock marks are invested amount until Command Center applies a live price."
        + " Trailing 1Y/3Y/5Y are not invented here."
        + " Do not commit a real family book to the public repository."
    )
    return True
