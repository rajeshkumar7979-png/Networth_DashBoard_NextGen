# scripts/update_holdings_cache.py
"""Refresh complete MF holdings and keep a durable history.

Rules:
- Never replace a good cache entry with an empty response.
- Never invent a filing date.
- Archive each reporting period so a later month does not erase the prior one.
- Write a daily full-book value row (MF units x AMFI NAV + stock marks +
  FD available or ROI-accrued principal in INR). Stocks prefer Yahoo LTP, else invested.
  USD FCNR is converted with spot USDINR (Frankfurter, fallback 95).
  Cash from Cash in Hand sheet is included in total_assets_inr.
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
from lib.cash_book import sum_cash_current  # noqa: E402
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


def _to_float(value: Any) -> float:
    """Parse numbers that may use Indian commas (12,00,000.00) or dashes."""
    if value is None:
        return 0.0
    try:
        if isinstance(value, (int, float)):
            return float(value)
    except (TypeError, ValueError):
        pass
    s = str(value).strip().strip("'\"").replace(",", "")
    if not s or s in {"-", "—", "NA", "N/A", "nan", "None"}:
        return 0.0
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def _pick_col(df: pd.DataFrame, aliases: set) -> Optional[str]:
    for col in df.columns:
        if _norm_col(col) in aliases:
            return col
    return None


def load_book_sheets() -> Dict[str, pd.DataFrame]:
    if not RAW_XLSX.exists():
        raise FileNotFoundError(f"Missing workbook: {RAW_XLSX}")
    xl = pd.ExcelFile(RAW_XLSX)
    out = {}
    for name in xl.sheet_names:
        out[str(name).strip()] = pd.read_excel(xl, name)
    return out


def discover_mf_rows(sheets: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for sheet_name, df in sheets.items():
        if df is None or df.empty:
            continue
        isin_col = _pick_col(df, ISIN_ALIASES)
        fund_col = _pick_col(df, FUND_ALIASES)
        units_col = _pick_col(df, UNITS_ALIASES)
        inv_col = _pick_col(df, INVESTED_ALIASES)
        if not isin_col:
            continue
        for _, r in df.iterrows():
            isin = str(r.get(isin_col) or "").strip().upper()
            if not isin or isin in {"NAN", "NONE", "-"}:
                continue
            rows.append({
                "isin": isin,
                "fund_name": str(r.get(fund_col) or "") if fund_col else "",
                "units": r.get(units_col) if units_col else None,
                "invested": r.get(inv_col) if inv_col else None,
                "sheet": sheet_name,
            })
    if not rows:
        return pd.DataFrame(columns=["isin", "fund_name", "units", "invested", "sheet"])
    return pd.DataFrame(rows).drop_duplicates(subset=["isin"], keep="first")


def fetch_usd_inr() -> float:
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest",
            params={"from": "USD", "to": "INR"},
            timeout=20,
        )
        r.raise_for_status()
        rate = float(r.json()["rates"]["INR"])
        if rate > 50:
            return rate
    except Exception as exc:
        print(f"USDINR fetch failed: {exc}")
    return 95.0


def _yahoo_ltp(symbol: str) -> Optional[float]:
    sym = symbol.strip().upper()
    if not sym:
        return None
    if not sym.endswith(".NS") and not sym.endswith(".BO") and "-" not in sym:
        candidates = [f"{sym}.NS", f"{sym}.BO", sym]
    else:
        candidates = [sym]
    for cand in candidates:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{cand}"
            r = requests.get(url, params={"interval": "1d", "range": "5d"}, timeout=15)
            if r.status_code != 200:
                continue
            result = (r.json().get("chart") or {}).get("result") or []
            if not result:
                continue
            meta = result[0].get("meta") or {}
            price = meta.get("regularMarketPrice") or meta.get("previousClose")
            if price is not None:
                return float(price)
        except Exception:
            continue
    return None


def mark_stocks_current(sheets: Dict[str, pd.DataFrame]) -> Tuple[float, float, int, str, float, float, int]:
    stocks_current = stocks_invested = 0.0
    gold_current = gold_invested = 0.0
    stocks_rows = gold_rows = 0
    marks_used = set()
    for name, df in sheets.items():
        if df is None or df.empty:
            continue
        if "stock" not in name.lower() and "equity" not in name.lower():
            continue
        ticker_col = None
        qty_col = None
        inv_col = None
        for col in df.columns:
            n = _norm_col(col)
            if n in {"ticker / symbol", "ticker", "symbol"}:
                ticker_col = col
            if n in {"quantity", "qty", "units"}:
                qty_col = col
            if n in {"invested amount", "invested", "cost"}:
                inv_col = col
        if not ticker_col:
            continue
        for _, r in df.iterrows():
            ticker = str(r.get(ticker_col) or "").strip().upper()
            if not ticker or ticker in {"NAN", "NONE"}:
                continue
            inv = float(r.get(inv_col) or 0) if inv_col else 0.0
            qty = float(r.get(qty_col) or 0) if qty_col else 0.0
            is_gold = any(k in ticker for k in ("GOLD", "SGB", "GBEES")) or "-GB" in ticker
            ltp = _yahoo_ltp(ticker)
            if ltp is not None and qty > 0:
                value = ltp * qty
                marks_used.add("yahoo_ltp")
            else:
                value = inv
                marks_used.add("invested_fallback")
            if is_gold:
                gold_current += value
                gold_invested += inv
                gold_rows += 1
            else:
                stocks_current += value
                stocks_invested += inv
                stocks_rows += 1
    mark = "+".join(sorted(marks_used)) if marks_used else "none"
    return (
        float(stocks_current), float(stocks_invested), stocks_rows, mark,
        float(gold_current), float(gold_invested), gold_rows,
    )


def sum_fd_current(sheets: Dict[str, pd.DataFrame], usd_inr: float = 95.0) -> Tuple[float, float, int]:
    total_cur = total_prin = 0.0
    rows = 0
    for name, df in sheets.items():
        if df is None or df.empty:
            continue
        if not any(k in name.lower() for k in ("fd", "deposit", "fcnr")):
            continue
        cur_col = prin_col = ccy_col = None
        for col in df.columns:
            n = _norm_col(col)
            if n in {"available balance", "current value", "current value (inr)", "maturity amount"}:
                cur_col = col
            if n in {"principal amount", "principal", "deposit amount"}:
                prin_col = col
            if n in {"currency", "ccy"}:
                ccy_col = col
        if not prin_col and not cur_col:
            continue
        for _, r in df.iterrows():
            prin = _to_float(r.get(prin_col)) if prin_col else 0.0
            cur = _to_float(r.get(cur_col)) if cur_col else 0.0
            if prin <= 0 and cur <= 0:
                continue
            ccy = str(r.get(ccy_col) or "INR").strip().upper() if ccy_col else "INR"
            mult = float(usd_inr) if ccy in {"USD", "US$"} else 1.0
            base = cur if cur > 0 else prin
            total_cur += base * mult
            total_prin += prin * mult
            rows += 1
    return float(total_cur), float(total_prin), rows


def choose_scheme(isin: str, fund_name: str, isin_index: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    candidates = isin_index.get(isin.upper()) or []
    if not candidates:
        return {}
    if len(candidates) == 1:
        return candidates[0]
    name = (fund_name or "").lower()
    for c in candidates:
        cn = str(c.get("scheme_name") or c.get("name") or "").lower()
        if name and name in cn:
            return c
    return candidates[0]


def write_portfolio_history_row(portfolio, isin_index, sheets):
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

    (
        stocks_current, stocks_invested, stocks_rows, stocks_mark,
        gold_current, gold_invested, gold_rows,
    ) = mark_stocks_current(sheets)
    usd_inr = fetch_usd_inr()
    fd_current, fd_principal, fd_rows = sum_fd_current(sheets, usd_inr=usd_inr)
    cash_current, _cash_rows = sum_cash_current(sheets)
    cash_current = float(cash_current or 0.0)

    total_current = mf_current + stocks_current + gold_current + fd_current + cash_current
    total_invested = mf_invested + stocks_invested + gold_invested + fd_principal + cash_current

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
        "gold_current_inr": round(gold_current, 2),
        "gold_invested_inr": round(gold_invested, 2),
        "gold_rows": gold_rows,
        "fd_current_inr": round(fd_current, 2),
        "fd_principal_inr": round(fd_principal, 2),
        "fd_rows": fd_rows,
        "cash_current_inr": round(cash_current, 2),
        "usd_inr": round(usd_inr, 4),
        "total_assets_inr": round(total_current, 2),
        "total_invested_inr": round(total_invested, 2),
        "note": (
            "Full book snapshot. MF = units x AMFI NAV. "
            f"Equity stocks = {stocks_mark}. "
            f"Gold (SGB/ETF) = invested or mark. "
            f"FD = available or ROI-accrued principal in INR (USD FCNR x USDINR {usd_inr:.2f}). "
            f"Cash = bank balances from Cash in Hand sheet ({cash_current:,.0f}). "
            "Not liabilities. Gold FoF inside MF still counted under MF."
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
        f"Stocks {row['stocks_current_inr']} | Gold {row['gold_current_inr']} | "
        f"FD {row['fd_current_inr']} | Cash {row['cash_current_inr']} | Total {row['total_assets_inr']}"
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
        isin = str(row["isin"])
        fund_name = str(row.get("fund_name") or "")
        scheme = choose_scheme(isin, fund_name, isin_index)
        code = scheme.get("scheme_code") or scheme.get("code")
        if not code:
            unresolved += 1
            print(f"UNRESOLVED {isin} {fund_name}")
            continue
        try:
            holdings, info = ingest_scheme_holdings(session, str(code))
            if not holdings:
                failed += 1
                print(f"EMPTY {code} {isin}")
                continue
            as_of = (info or {}).get("as_of") or (info or {}).get("portfolio_date")
            key = str(code)
            if holdings:
                cache[key] = {
                    "scheme_code": key,
                    "isin": isin,
                    "fund_name": fund_name or scheme.get("scheme_name"),
                    "as_of": as_of,
                    "holdings": holdings,
                    "source": (info or {}).get("source"),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
                meta[key] = {
                    "scheme_code": key,
                    "isin": isin,
                    "as_of": as_of,
                    "count": len(holdings),
                    "source": (info or {}).get("source"),
                }
                success += 1
                print(f"OK {code} {isin} rows={len(holdings)} as_of={as_of}")
            else:
                failed += 1
        except Exception as exc:
            failed += 1
            print(f"FAIL {code} {isin}: {exc}")

    save_json_atomic(HOLDINGS_CACHE, cache)
    save_json_atomic(HOLDINGS_META_CACHE, meta)
    print(f"Done success={success} failed={failed} unresolved={unresolved} cache_size={len(cache)}")
    return 0 if success > 0 or len(cache) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
