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
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_col(columns, aliases):
    normalized = {
        " ".join(str(c or "").strip().lower().replace("_", " ").split()): c
        for c in columns
    }
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    for norm, original in normalized.items():
        if any(alias in norm for alias in aliases):
            return original
    return None


def resolve_book_path():
    """Prefer a private path from secrets/env; else the public sample workbook."""
    import os
    from pathlib import Path

    try:
        import streamlit as st
        secret = (st.secrets.get("NORTHLINE_BOOK_PATH") if hasattr(st, "secrets") else None)
    except Exception:
        secret = None
    env = os.environ.get("NORTHLINE_BOOK_PATH")
    for candidate in (secret, env):
        if candidate:
            p = Path(str(candidate))
            if p.exists():
                return p
    root = Path(__file__).resolve().parents[1]
    return root / "data" / "Networth_Raw_Data.xlsx"


def _load_amfi_nav_map():
    """ISIN → nav from the committed AMFI universe cache (no network)."""
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "data" / "amfi_scheme_universe.json"
    if not path.exists():
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        nav = _num(row.get("nav"))
        if nav is None:
            continue
        for key in ("isin", "isin1", "isin2"):
            isin = str(row.get(key) or "").strip().upper()
            if isin.startswith("IN") and isin not in out:
                out[isin] = nav
    return out


def _amfi_saved_at():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "data" / "amfi_scheme_universe.json"
    if not path.exists():
        return None
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date().isoformat()
    except Exception:
        return None


def build_published_books(book_path):
    frames = pd.read_excel(book_path, sheet_name=None)
    sheets = {str(k).lower().strip(): v for k, v in frames.items()}

    mf_raw = sheets.get("mf", pd.DataFrame())
    stocks_raw = sheets.get("stocks", pd.DataFrame())
    fd_raw = sheets.get("fd", pd.DataFrame())

    nav_map = _load_amfi_nav_map()

    # MF
    mf = mf_raw.copy() if not mf_raw.empty else pd.DataFrame()
    if not mf.empty:
        isin_col = _find_col(mf.columns, {"isin", "isin code"})
        units_col = _find_col(mf.columns, {"units", "unit", "balance units"})
        inv_col = _find_col(mf.columns, {"invested amount", "invested", "cost"})
        owner_col = _find_col(mf.columns, {"owner", "holder", "member"})
        fund_col = _find_col(mf.columns, {"fund name", "scheme name", "scheme", "fund"})
        if isin_col and units_col:
            current = []
            for _, row in mf.iterrows():
                isin = str(row.get(isin_col) or "").strip().upper()
                units = _num(row.get(units_col))
                nav = nav_map.get(isin)
                if units is not None and nav is not None:
                    current.append(units * nav)
                else:
                    current.append(_num(row.get(inv_col)) if inv_col else None)
            mf = mf.copy()
            mf["Current Value"] = current
            if inv_col and "Invested" not in mf.columns:
                mf["Invested"] = pd.to_numeric(mf[inv_col], errors="coerce")
            if owner_col and "Owner" not in mf.columns:
                mf["Owner"] = mf[owner_col]
            if fund_col and "Fund Name" not in mf.columns:
                mf["Fund Name"] = mf[fund_col]
            if isin_col and "ISIN" not in mf.columns:
                mf["ISIN"] = mf[isin_col].astype(str).str.strip().str.upper()

    # Stocks — invested as current until CC applies live marks; gold symbols split later by CC
    stocks = stocks_raw.copy() if not stocks_raw.empty else pd.DataFrame()
    gold = pd.DataFrame()
    if not stocks.empty:
        inv_col = _find_col(stocks.columns, {"invested amount", "invested", "cost"})
        owner_col = _find_col(stocks.columns, {"owner", "holder", "member"})
        sym_col = _find_col(stocks.columns, {"ticker / symbol", "ticker", "symbol"})
        if inv_col:
            stocks = stocks.copy()
            stocks["Invested"] = pd.to_numeric(stocks[inv_col], errors="coerce")
            stocks["Current Value"] = stocks["Invested"]
        if owner_col and "Owner" not in stocks.columns:
            stocks["Owner"] = stocks[owner_col]
        if sym_col and "Symbol" not in stocks.columns:
            stocks["Symbol"] = stocks[sym_col]

    # FD — principal / available; USD left native (CC applies FX)
    fd = fd_raw.copy() if not fd_raw.empty else pd.DataFrame()
    if not fd.empty:
        prin_col = _find_col(fd.columns, {"principal amount", "principal", "deposit amount"})
        avail_col = _find_col(fd.columns, {"available balance", "available", "balance"})
        ccy_col = _find_col(fd.columns, {"currency", "ccy"})
        holder_col = _find_col(fd.columns, {"holder name", "holder", "owner"})
        if prin_col:
            fd = fd.copy()
            fd["Principal"] = pd.to_numeric(fd[prin_col], errors="coerce")
            if avail_col:
                fd["Available"] = pd.to_numeric(fd[avail_col], errors="coerce")
            else:
                fd["Available"] = fd["Principal"]
            fd["Current Value"] = fd["Available"].where(fd["Available"].fillna(0) > 0, fd["Principal"])
        if ccy_col and "Currency" not in fd.columns:
            fd["Currency"] = fd[ccy_col]
        if holder_col and "Holder" not in fd.columns:
            fd["Holder"] = fd[holder_col]

    assets = {
        "mf": float(pd.to_numeric(mf.get("Current Value"), errors="coerce").fillna(0).sum()) if not mf.empty else 0.0,
        "stocks": float(pd.to_numeric(stocks.get("Current Value"), errors="coerce").fillna(0).sum()) if not stocks.empty else 0.0,
        "gold": 0.0,
        "fd": float(pd.to_numeric(fd.get("Current Value"), errors="coerce").fillna(0).sum()) if not fd.empty else 0.0,
    }
    holdings = []
    if not mf.empty and "ISIN" in mf.columns:
        for _, row in mf.iterrows():
            holdings.append({
                "isin": str(row.get("ISIN") or ""),
                "fund_name": str(row.get("Fund Name") or ""),
                "units": _num(row.get("Units")),
                "invested": _num(row.get("Invested")),
                "current": _num(row.get("Current Value")),
            })

    return {
        "mf": mf,
        "stocks": stocks,
        "gold": gold,
        "fd": fd,
        "assets": assets,
        "holdings": holdings,
    }


def ensure_session_books(st) -> bool:
    """If Command Center has not published books, load the workbook into session.

    Returns True when a book is available in session after this call.
    """
    if st.session_state.get("cc_books"):
        return True
    book_path = resolve_book_path()
    if not book_path.exists():
        st.session_state["cc_book_note"] = f"Workbook not found at {book_path}"
        return False
    try:
        published = build_published_books(book_path)
    except Exception as exc:
        st.session_state["cc_book_note"] = f"Could not load book: {exc}"
        return False
    saved_at = _amfi_saved_at()
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
