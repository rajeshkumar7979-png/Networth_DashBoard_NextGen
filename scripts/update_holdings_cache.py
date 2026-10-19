# scripts/update_holdings_cache.py
"""Refresh complete MF holdings and keep a durable history.

Rules:
- Never replace a good cache entry with an empty response.
- Never invent a filing date.
- Archive each reporting period so a later month does not erase the prior one.
- Write a daily full-book value row (MF units x AMFI NAV + stock marks +
  FD available/principal in INR). Stocks prefer Yahoo LTP, else invested basis.
  USD FCNR is converted with spot USDINR (Frankfurter, fallback 95).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.mf_diff import diff_snapshots  # noqa: E402
from lib.mf_holdings import (  # noqa: E402
    HOLDINGS_CACHE,
    HOLDINGS_META_CACHE,
    build_isin_index,
    fetch_amfi_universe,
    ingest_scheme_holdings,
    load_json,
    save_json_atomic,
)

RAW_XLSX = ROOT / "data" / "Networth_Raw_Data.xlsx"
SNAPSHOT_DIR = ROOT / "data" / "mf_snapshots"
PORTFOLIO_HISTORY = ROOT / "data" / "portfolio_history.csv"

ISIN_ALIASES = {"isin", "isin code", "isin number", "isin no", "isin id"}
FUND_ALIASES = {"fund name", "mutual fund", "scheme name", "scheme", "fund"}
UNITS_ALIASES = {"units", "unit", "balance units"}
INVESTED_ALIASES = {"invested amount", "invested", "cost"}


def _norm_col(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _find_column(columns, aliases):
    normalized = {_norm_col(c): c for c in columns}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    for norm, original in normalized.items():
        if any(alias in norm for alias in aliases):
            return original
    return None


def _num(value: Any) -> Optional[float]:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def load_book_sheets() -> Dict[str, pd.DataFrame]:
    if not RAW_XLSX.exists():
        raise FileNotFoundError(f"Missing {RAW_XLSX}")
    frames = pd.read_excel(RAW_XLSX, sheet_name=None)
    return {str(name).lower().strip(): frame for name, frame in frames.items()}


def pick_sheet(sheets: Dict[str, pd.DataFrame], *names: str) -> pd.DataFrame:
    for name in names:
        if name in sheets and isinstance(sheets[name], pd.DataFrame):
            return sheets[name]
    return pd.DataFrame()


def discover_mf_rows(sheets: Optional[Dict[str, pd.DataFrame]] = None) -> pd.DataFrame:
    sheets = sheets or load_book_sheets()
    candidates: List[pd.DataFrame] = []
    for sheet_name, df in sheets.items():
        if df is None or df.empty:
            continue
        isin_col = _find_column(df.columns, ISIN_ALIASES)
        if not isin_col:
            continue
        fund_col = _find_column(df.columns, FUND_ALIASES)
        units_col = _find_column(df.columns, UNITS_ALIASES)
        invested_col = _find_column(df.columns, INVESTED_ALIASES)
        out = pd.DataFrame({
            "isin": df[isin_col].astype(str).str.strip().str.upper(),
            "fund_name": df[fund_col].astype(str).str.strip() if fund_col else "",
            "units": pd.to_numeric(df[units_col], errors="coerce") if units_col else None,
            "invested": pd.to_numeric(df[invested_col], errors="coerce") if invested_col else None,
            "sheet": sheet_name,
        })
        out = out[out["isin"].str.match(r"^IN[A-Z0-9]{8,}$", na=False)]
        if not out.empty:
            candidates.append(out)
    if not candidates:
        raise RuntimeError("Could not find an ISIN column in any workbook sheet")
    all_rows = pd.concat(candidates, ignore_index=True)
    grouped = (
        all_rows.groupby("isin", as_index=False)
        .agg({
            "fund_name": "first",
            "units": "sum",
            "invested": "sum",
            "sheet": "first",
        })
    )
    return grouped


def sum_stocks_invested(sheets: Dict[str, pd.DataFrame]) -> Tuple[float, int]:
    stocks = pick_sheet(sheets, "stocks", "stock", "equities")
    if stocks.empty:
        return 0.0, 0
    invested_col = _find_column(stocks.columns, INVESTED_ALIASES)
    if not invested_col:
        return 0.0, 0
    series = pd.to_numeric(stocks[invested_col], errors="coerce").fillna(0.0)
    return float(series.sum()), int((series > 0).sum())


def mark_stocks_current(sheets: Dict[str, pd.DataFrame]) -> Tuple[float, float, int, str]:
    """Best-effort Yahoo LTP × qty; fall back to invested basis.

    Returns (current, invested, rows, mark_label).
    """
    stocks = pick_sheet(sheets, "stocks", "stock", "equities")
    invested, rows = sum_stocks_invested(sheets)
    if stocks.empty:
        return 0.0, 0.0, 0, "none"
    symbol_col = _find_column(stocks.columns, {"ticker / symbol", "ticker", "symbol"})
    qty_col = _find_column(stocks.columns, {"quantity", "qty", "units"})
    invested_col = _find_column(stocks.columns, INVESTED_ALIASES)
    exchange_col = _find_column(stocks.columns, {"exchange"})
    if not symbol_col or not qty_col:
        return invested, invested, rows, "invested_basis"
    try:
        import yfinance as yf
    except Exception:
        return invested, invested, rows, "invested_basis"

    current = 0.0
    marked = 0
    for _, row in stocks.iterrows():
        inv = _num(row.get(invested_col)) if invested_col else None
        qty = _num(row.get(qty_col))
        sym = str(row.get(symbol_col) or "").strip().upper()
        if not sym or qty is None:
            if inv is not None:
                current += inv
            continue
        if sym.startswith("SGB") or "-" in sym:
            if inv is not None:
                current += inv
            continue
        ex = str(row.get(exchange_col) or "NSE").strip().upper() if exchange_col else "NSE"
        yahoo = sym if "." in sym else (sym + (".BO" if ex in {"BSE", "BOM"} else ".NS"))
        last = None
        try:
            hist = yf.Ticker(yahoo).history(period="5d")
            if hist is not None and not hist.empty and "Close" in hist.columns:
                last = _num(hist["Close"].dropna().iloc[-1])
        except Exception:
            last = None
        if last is not None:
            current += qty * last
            marked += 1
        elif inv is not None:
            current += inv
    label = "yahoo_ltp+invested_fallback" if marked else "invested_basis"
    return float(current), float(invested), rows, label


def fetch_usd_inr() -> float:
    """Spot USDINR for FCNR INR conversion. Fallback 95 if network fails."""
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest",
            params={"from": "USD", "to": "INR"},
            timeout=15,
        )
        if r.status_code == 200:
            rate = float((r.json().get("rates") or {}).get("INR") or 0)
            if rate > 50:
                return rate
    except Exception:
        pass
    return 95.0


def sum_fd_current(sheets: Dict[str, pd.DataFrame], usd_inr: float | None = None) -> Tuple[float, float, int]:
    """FD current in INR = available (else principal) × FX for USD rows."""
    fd = pick_sheet(sheets, "fd", "fixed deposits", "fixed_deposits")
    if fd.empty:
        return 0.0, 0.0, 0
    principal_col = _find_column(fd.columns, {"principal amount", "principal", "deposit amount"})
    available_col = _find_column(fd.columns, {"available balance", "available", "balance"})
    currency_col = _find_column(fd.columns, {"currency", "ccy"})
    fx = float(usd_inr) if usd_inr else fetch_usd_inr()
    current = 0.0
    principal_total = 0.0
    counted = 0
    for _, row in fd.iterrows():
        principal = _num(row.get(principal_col)) if principal_col else None
        available = _num(row.get(available_col)) if available_col else None
        ccy = str(row.get(currency_col) or "INR").strip().upper() if currency_col else "INR"
        mult = fx if ccy in {"USD", "US$"} else 1.0
        if principal is not None:
            principal_total += principal * mult
        value = available if available not in (None, 0.0) else principal
        if value is None:
            continue
        current += value * mult
        counted += 1
    return float(current), float(principal_total), counted


def choose_scheme(isin: str, fund_name: str, isin_index: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any] | None:
    candidates = isin_index.get(isin.upper(), [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    fn = " ".join(str(fund_name or "").lower().replace("-", " ").split())
    scored = []
    for row in candidates:
        sn = " ".join(str(row.get("scheme_name") or "").lower().replace("-", " ").split())
        score = 0
        if fn and (fn in sn or sn in fn):
            score += 100
        if "direct" in fn and "direct" in sn:
            score += 10
        if "regular" in fn and "regular" in sn:
            score += 10
        if "growth" in fn and "growth" in sn:
            score += 5
        scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def archive_snapshot(scheme_code: str, as_of: str, holdings: list) -> None:
    if not scheme_code or not as_of or not holdings:
        return
    folder = SNAPSHOT_DIR / str(scheme_code)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{as_of}.json"
    save_json_atomic(path, {
        "scheme_code": str(scheme_code),
        "as_of": as_of,
        "archived_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "holdings": holdings,
    })


def write_portfolio_history_row(
    portfolio: pd.DataFrame,
    isin_index: Dict[str, List[Dict[str, Any]]],
    sheets: Dict[str, pd.DataFrame],
) -> None:
    """Durable daily row: MF mark + stock marks + FD current + totals."""
    mf_current = 0.0
    mf_invested = 0.0
    priced = 0
    missing = 0
    for _, row in portfolio.iterrows():
        scheme = choose_scheme(str(row["isin"]), str(row.get("fund_name") or ""), isin_index)
        inv = row.get("invested")
        if pd.notna(inv):
            mf_invested += float(inv)
        units = row.get("units")
        nav = scheme.get("nav") if scheme else None
        if pd.notna(units) and nav:
            mf_current += float(units) * float(nav)
            priced += 1
        else:
            missing += 1

    stocks_current, stocks_invested, stocks_rows, stocks_mark = mark_stocks_current(sheets)
    usd_inr = fetch_usd_inr()
    fd_current, fd_principal, fd_rows = sum_fd_current(sheets, usd_inr=usd_inr)

    total_current = mf_current + stocks_current + fd_current
    total_invested = mf_invested + stocks_invested + fd_principal

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = {
        "date": today,
        "mf_current_inr": round(mf_current, 2),
        "mf_invested_inr": round(mf_invested, 2),
        "schemes_priced": priced,
        "schemes_missing_nav": missing,
        "stocks_current_inr": round(stocks_current, 2),
        "stocks_invested_inr": round(stocks_invested, 2),
        "stocks_rows": stocks_rows,
        "stocks_mark": stocks_mark,
        "fd_current_inr": round(fd_current, 2),
        "fd_principal_inr": round(fd_principal, 2),
        "fd_rows": fd_rows,
        "usd_inr": round(usd_inr, 4),
        "total_assets_inr": round(total_current, 2),
        "total_invested_inr": round(total_invested, 2),
        "note": (
            "Full book snapshot. MF = units x AMFI NAV. "
            f"Stocks = {stocks_mark}. "
            f"FD = available/principal in INR (USD FCNR x USDINR {usd_inr:.2f}). "
            "Not liabilities. Not gold."
        ),
    }
    PORTFOLIO_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    if PORTFOLIO_HISTORY.exists():
        hist = pd.read_csv(PORTFOLIO_HISTORY)
        hist = hist[hist["date"].astype(str) != today]
    else:
        hist = pd.DataFrame()
    hist = pd.concat([hist, pd.DataFrame([row])], ignore_index=True)
    hist.to_csv(PORTFOLIO_HISTORY, index=False)
    print(
        f"History row {today}: MF {row['mf_current_inr']} | "
        f"Stocks {row['stocks_current_inr']} ({stocks_mark}) | FD {row['fd_current_inr']} | "
        f"Total {row['total_assets_inr']} (USDINR {usd_inr:.2f})"
    )


def main() -> int:
    print("=== MF holdings refresh ===")
    sheets = load_book_sheets()
    portfolio = discover_mf_rows(sheets)
    print(f"Unique portfolio ISINs found: {len(portfolio)}")
    session = requests.Session()
    amfi_rows = fetch_amfi_universe(session, force=True)
    isin_index = build_isin_index(amfi_rows)
    print(f"AMFI universe rows: {len(amfi_rows)}")
    write_portfolio_history_row(portfolio, isin_index, sheets)

    cache = load_json(HOLDINGS_CACHE, {})
    meta = load_json(HOLDINGS_META_CACHE, {})
    if not isinstance(cache, dict):
        cache = {}
    if not isinstance(meta, dict):
        meta = {}

    success = failed = unresolved = 0
    for _, row in portfolio.iterrows():
        isin = str(row["isin"]).strip().upper()
        fund_name = str(row.get("fund_name") or "").strip()
        scheme = choose_scheme(isin, fund_name, isin_index)
        if not scheme:
            unresolved += 1
            meta[isin] = {
                "status": "UNRESOLVED_AMFI",
                "isin": isin,
                "fund_name": fund_name,
                "updated_at": pd.Timestamp.utcnow().isoformat(),
            }
            print(f"[UNRESOLVED] {fund_name} | {isin}")
            continue

        scheme_code = str(scheme["scheme_code"])
        display_name = scheme.get("scheme_name") or fund_name
        print(f"[FETCH] {display_name} | {isin} | AMFI {scheme_code}")
        try:
            holdings, source_meta = ingest_scheme_holdings(session, scheme_code)
            if not holdings:
                raise RuntimeError("Source returned empty holdings")
            prior_meta = meta.get(scheme_code) if isinstance(meta.get(scheme_code), dict) else {}
            prior_as_of = str(prior_meta.get("as_of") or "")
            prior_holdings = cache.get(scheme_code) if isinstance(cache.get(scheme_code), list) else []
            new_as_of = str(source_meta.get("as_of") or "")
            if prior_holdings and prior_as_of:
                archive_snapshot(scheme_code, prior_as_of, prior_holdings)
            if new_as_of:
                archive_snapshot(scheme_code, new_as_of, holdings)
            if prior_as_of and new_as_of and prior_as_of != new_as_of:
                change = diff_snapshots(prior_holdings, holdings)
            elif prior_as_of == new_as_of:
                change = {"status": "SAME_PERIOD", "added": [], "exited": [], "changed": []}
            else:
                change = {"status": "NO_PRIOR", "added": [], "exited": [], "changed": []}
            cache[scheme_code] = holdings
            meta[scheme_code] = {
                "status": "OK",
                "isin": isin,
                "fund_name": fund_name,
                "amfi_scheme_code": scheme_code,
                "amfi_scheme_name": display_name,
                "amc": scheme.get("amc"),
                "category": scheme.get("category"),
                **source_meta,
                "validation": source_meta.get("validation", {}),
                "comparison_status": change.get("status"),
                "added_count": len(change.get("added") or []),
                "exited_count": len(change.get("exited") or []),
                "changed_count": len(change.get("changed") or []),
                "prior_as_of": prior_as_of or None,
            }
            success += 1
            print(f"  -> {len(holdings)} holdings | {new_as_of} | {change.get('status')}")
        except Exception as exc:
            failed += 1
            meta[scheme_code] = {
                **(meta.get(scheme_code) if isinstance(meta.get(scheme_code), dict) else {}),
                "status": "ERROR",
                "isin": isin,
                "fund_name": fund_name,
                "amfi_scheme_code": scheme_code,
                "amfi_scheme_name": display_name,
                "error": str(exc),
                "updated_at": pd.Timestamp.utcnow().isoformat(),
                "cache_preserved": scheme_code in cache,
            }
            print(f"  !! FAILED: {exc}")

    save_json_atomic(HOLDINGS_CACHE, cache)
    save_json_atomic(HOLDINGS_META_CACHE, meta)
    print(f"Successful: {success}  Failed: {failed}  Unresolved: {unresolved}")
    if success == 0 and not cache:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
