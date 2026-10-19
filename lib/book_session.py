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
            "Invested": invested,
            "Current Value": current,
        })
    mf_valid = pd.DataFrame(mf_rows)

    stock_rows = []
    for _, row in stocks.iterrows():
        invested = _num(row.get("Invested Amount"))
        if invested is None:
            continue
        stock_rows.append({
            "Owner": _text(row.get("Owner")),
            "Ticker / Symbol": _text(row.get("Ticker / Symbol") or row.get("Symbol")),
            "Company Name": _text(row.get("Company Name")),
            "Exchange": _text(row.get("Exchange")),
            "Quantity": _num(row.get("Quantity")),
            "Avg Buy Price": _num(row.get("Avg Buy Price")),
            "Invested": invested,
            "Current Value": invested,
        })
    stocks_valid = pd.DataFrame(stock_rows)

    fd_rows = []
    for _, row in fd.iterrows():
        principal = _num(row.get("Principal Amount") or row.get("Principal"))
        available = _num(row.get("Available Balance") or row.get("Available"))
        if principal is None and available is None:
            continue
        value = available if available not in (None, 0.0) else principal
        fd_rows.append({
            "Account Number": _text(row.get("Account Number")),
            "Holder Name": _text(row.get("Holder Name") or row.get("Holder")),
            "Currency": _text(row.get("Currency") or "INR") or "INR",
            "Principal Amount": principal,
            "Available Balance": available,
            "Current Value": value,
            "ROI % p.a.": _num(row.get("ROI % p.a.")),
            "Deposit Date": row.get("Deposit Date"),
            "Maturity Date": row.get("Maturity Date"),
        })
    fd_valid = pd.DataFrame(fd_rows)

    holdings = []
    for _, row in mf_valid.iterrows():
        holdings.append({
            "isin": row.get("ISIN"),
            "fund_name": row.get("Fund Name"),
            "scheme_code": row.get("Scheme Code"),
            "units": row.get("Units"),
            "invested": row.get("Invested"),
            "current": row.get("Current Value"),
            "owner": row.get("Owner"),
        })

    assets_total = float(
        (pd.to_numeric(mf_valid["Current Value"], errors="coerce").fillna(0).sum() if not mf_valid.empty else 0)
        + (pd.to_numeric(stocks_valid["Current Value"], errors="coerce").fillna(0).sum() if not stocks_valid.empty else 0)
        + (pd.to_numeric(fd_valid["Current Value"], errors="coerce").fillna(0).sum() if not fd_valid.empty else 0)
    )
    invested = float(
        (pd.to_numeric(mf_valid["Invested"], errors="coerce").fillna(0).sum() if not mf_valid.empty else 0)
        + (pd.to_numeric(stocks_valid["Invested"], errors="coerce").fillna(0).sum() if not stocks_valid.empty else 0)
        + (pd.to_numeric(fd_valid["Principal Amount"], errors="coerce").fillna(0).sum() if not fd_valid.empty else 0)
    )
    assets = {
        "total_assets": assets_total,
        "total_invested": invested,
        "total_pnl": assets_total - invested,
        "as_of": str(saved_at or datetime.now(timezone.utc).date()),
        "valued_at": str(saved_at or ""),
        "source": SOURCE,
    }
    return {
        "mf": mf_valid,
        "stocks": stocks_valid,
        "gold": None,
        "fd": fd_valid,
        "holdings": holdings,
        "assets": assets,
    }


def ensure_published_book():
    """Fill session keys once. Leave a Command Center publish untouched."""
    import streamlit as st
    from lib.config import AMFI_CACHE_PATH, resolve_book_path

    books = st.session_state.get("cc_books")
    holdings = st.session_state.get("mf_holdings_for_health")
    if isinstance(books, dict) and books.get("mf") is not None and holdings:
        return False
    book_path = resolve_book_path()
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
    label = "Public sample book" if "Member A" in str(published["mf"].get("Owner", pd.Series(dtype=str)).head(1).tolist()) else "Book"
    st.session_state["cc_book_note"] = (
        f"{label} from {book_path.name}. Fund marks use the AMFI cache"
        + (f" saved {saved_at}." if saved_at else ".")
        + " Stock marks are invested amount until Command Center applies a live price."
        + " Trailing 1Y/3Y/5Y are not invented here."
        + " Do not commit a real family book to the public repository."
    )
    return True
