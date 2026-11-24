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


def fetch_usd_inr() -> Tuple[float, str]:
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest",
            params={"from": "USD", "to": "INR"},
            timeout=20,
        )
        r.raise_for_status()
        rate = float(r.json()["rates"]["INR"])
        if rate > 50:
            return rate, "frankfurter"
    except Exception as exc:
        print(f"USDINR fetch failed: {exc}")
    return 95.0, "fallback_95"


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


def mark_stocks_current(sheets: Dict[str, pd.DataFrame]) -> Tuple[float, float, int, str, float, float, int, int, int]:
    stocks_current = stocks_invested = 0.0
    gold_current = gold_invested = 0.0
    stocks_rows = gold_rows = 0
    marks_used = set()
    yahoo_hits = 0
    yahoo_attempts = 0
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
            yahoo_attempts += 1
            ltp = _yahoo_ltp(ticker)
            if ltp is not None and qty > 0:
                value = ltp * qty
                marks_used.add("yahoo_ltp")
                yahoo_hits += 1
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
        int(yahoo_hits), int(yahoo_attempts),
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
        yahoo_hits, yahoo_attempts,
    ) = mark_stocks_current(sheets)
    usd_inr, fx_source = fetch_usd_inr()
    fd_current, fd_principal, fd_rows = sum_fd_current(sheets, usd_inr=usd_inr)
    cash_current, _cash_rows = sum_cash_current(sheets)
    cash_current = float(cash_current or 0.0)

    sheet_names = {str(k).strip().lower() for k in sheets.keys()}
    has_cash_sheet = any("cash" in n for n in sheet_names)
    try:
        book_bytes = RAW_XLSX.stat().st_size if RAW_XLSX.exists() else 0
    except OSError:
        book_bytes = 0
    if book_bytes < 20000 and not has_cash_sheet:
        book_mode = "sample"
    elif has_cash_sheet:
        book_mode = "committed_with_cash"
    else:
        book_mode = "committed"

    quality_flags = []
    if stocks_mark == "invested_fallback" or (yahoo_attempts > 0 and yahoo_hits == 0):
        quality_flags.append("EQUITY_COST_ONLY")
    if yahoo_attempts > 0 and 0 < yahoo_hits < yahoo_attempts:
        quality_flags.append("EQUITY_PARTIAL_MARK")
    if not has_cash_sheet:
        quality_flags.append("NO_CASH_SHEET")
    if str(fx_source).startswith("fallback"):
        quality_flags.append("FX_FALLBACK")
    if book_mode == "sample":
        quality_flags.append("SAMPLE_BOOK")
    data_quality = "+".join(quality_flags) if quality_flags else "OK"
    if "EQUITY_COST_ONLY" in quality_flags:
        print(
            f"WARNING: equity mark is cost-only "
            f"(yahoo_hits={yahoo_hits}/{yahoo_attempts}). "
            "Stock P&L in history is not mark-to-market."
        )

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
        "stocks_yahoo_hits": yahoo_hits,
        "stocks_yahoo_attempts": yahoo_attempts,
        "gold_current_inr": round(gold_current, 2),
        "gold_invested_inr": round(gold_invested, 2),
        "gold_rows": gold_rows,
        "fd_current_inr": round(fd_current, 2),
        "fd_principal_inr": round(fd_principal, 2),
        "fd_rows": fd_rows,
        "cash_current_inr": round(cash_current, 2),
        "usd_inr": round(usd_inr, 4),
        "fx_source": fx_source,
        "book_mode": book_mode,
        "data_quality": data_quality,
        "total_assets_inr": round(total_current, 2),
        "total_invested_inr": round(total_invested, 2),
        "note": (
            f"book_mode={book_mode}. data_quality={data_quality}. "
            "MF = units x AMFI NAV. "
            f"Equity stocks = {stocks_mark} (yahoo {yahoo_hits}/{yahoo_attempts}). "
            f"Gold (SGB/ETF) = invested or mark. "
            f"FD = available or ROI-accrued principal in INR "
            f"(USD FCNR x USDINR {usd_inr:.2f} via {fx_source}). "
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


def _prior_snapshot_path(scheme_code: str, current_as_of: str) -> Optional[Path]:
    """Newest archived snapshot for scheme with as_of strictly before current."""
    folder = SNAPSHOT_DIR / str(scheme_code)
    if not folder.exists():
        return None
    current = str(current_as_of or "")[:10]
    candidates = []
    for path in folder.glob("*.json"):
        stamp = path.stem[:10]
        if len(stamp) >= 10 and stamp < current:
            candidates.append((stamp, path))
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1][1]


def archive_scheme_snapshot(scheme_code: str, as_of: str, holdings: list, meta_extra: dict | None = None) -> Path:
    as_of_s = str(as_of or "unknown")[:10]
    folder = SNAPSHOT_DIR / str(scheme_code)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{as_of_s}.json"
    payload = {
        "scheme_code": str(scheme_code),
        "as_of": as_of_s,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "holdings": holdings,
    }
    if meta_extra:
        payload.update({k: v for k, v in meta_extra.items() if k not in payload})
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def compare_to_prior(scheme_code: str, as_of: str, holdings: list) -> dict:
    """Diff current holdings vs last archived prior as_of. Safe if no prior."""
    prior_path = _prior_snapshot_path(scheme_code, as_of)
    if prior_path is None:
        return {
            "comparison_status": "NO_PRIOR",
            "prior_as_of": None,
            "added_count": 0,
            "exited_count": 0,
            "changed_count": 0,
        }
    try:
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
        prior_rows = prior.get("holdings") or []
        prior_as_of = str(prior.get("as_of") or prior_path.stem)[:10]
    except Exception:
        return {
            "comparison_status": "NOT_COMPARABLE",
            "prior_as_of": None,
            "added_count": 0,
            "exited_count": 0,
            "changed_count": 0,
        }
    diff = diff_snapshots(prior_rows, holdings)
    status = diff.get("status") or "VALID"
    added = diff.get("added") or []
    exited = diff.get("exited") or []
    changed = diff.get("changed") or []
    if status == "NO_PRIOR":
        cmp_status = "NO_PRIOR"
    elif status == "NOT_COMPARABLE":
        cmp_status = "NOT_COMPARABLE"
    elif not added and not exited and not changed:
        if prior_as_of == str(as_of)[:10]:
            cmp_status = "SAME_PERIOD"
        else:
            cmp_status = "NEW_PERIOD"
    else:
        cmp_status = "CHANGED" if prior_as_of == str(as_of)[:10] else "NEW_PERIOD"
    return {
        "comparison_status": cmp_status,
        "prior_as_of": prior_as_of,
        "added_count": len(added),
        "exited_count": len(exited),
        "changed_count": len(changed),
        "diff_limitation": diff.get("limitation"),
    }


def refresh_amfi_nav_cache(amfi_rows: list) -> None:
    """Rewrite data/amfi_nav_cache.json from a live NAVAll parse so Cloud is not stuck on Aug cache."""
    from lib.config import AMFI_CACHE_PATH

    nav, code, name = {}, {}, {}
    for row in amfi_rows or []:
        if not isinstance(row, dict):
            continue
        scheme_code = str(row.get("scheme_code") or "").strip()
        scheme_name = str(row.get("scheme_name") or "").strip()
        nav_v = row.get("nav")
        for key in ("isin_primary", "isin_secondary"):
            isin = str(row.get(key) or "").strip().upper()
            if not isin or isin in {"-", "NA", "N/A"}:
                continue
            if nav_v is not None:
                try:
                    nav[isin] = float(nav_v)
                except (TypeError, ValueError):
                    pass
            if scheme_code:
                code[isin] = scheme_code
            if scheme_name:
                name[isin] = scheme_name
    payload = {
        "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "nav": nav,
        "code": code,
        "name": name,
        "source": "AMFI NAVAll via holdings job",
        "row_count": len(amfi_rows or []),
    }
    AMFI_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = AMFI_CACHE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(AMFI_CACHE_PATH)
    print(f"AMFI nav cache refreshed: {len(nav)} ISINs -> {AMFI_CACHE_PATH}")


def write_holdings_change_summary(meta: dict) -> None:
    """Compact summary of AMC filing changes for UI / audit."""
    out = ROOT / "data" / "holdings_change_summary.json"
    by_status = {}
    changed_funds = []
    for code, v in (meta or {}).items():
        if not isinstance(v, dict):
            continue
        st = str(v.get("comparison_status") or "UNKNOWN")
        by_status[st] = by_status.get(st, 0) + 1
        if st in {"NEW_PERIOD", "CHANGED"} or (
            int(v.get("added_count") or 0)
            + int(v.get("exited_count") or 0)
            + int(v.get("changed_count") or 0)
        ) > 0:
            changed_funds.append({
                "scheme_code": code,
                "fund_name": v.get("fund_name") or v.get("amfi_scheme_name"),
                "as_of": v.get("as_of"),
                "prior_as_of": v.get("prior_as_of"),
                "status": st,
                "added": v.get("added_count"),
                "exited": v.get("exited_count"),
                "changed": v.get("changed_count"),
            })
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "by_status": by_status,
        "changed_funds": sorted(changed_funds, key=lambda x: str(x.get("fund_name") or "")),
        "note": "NEW_PERIOD = new AMC filing month vs prior archive; CHANGED = same as_of with composition moves.",
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Holdings change summary: {by_status} -> {out}")


def main() -> int:
    sheets = load_book_sheets()
    portfolio = discover_mf_rows(sheets)
    print(f"MF rows discovered: {len(portfolio)}")

    amfi_rows = fetch_amfi_universe()
    print(f"AMFI universe rows: {len(amfi_rows or [])}")
    try:
        refresh_amfi_nav_cache(amfi_rows)
    except Exception as exc:
        print(f"AMFI nav cache refresh skipped: {exc}")

    isin_index = build_isin_index(amfi_rows)
    cache = load_json(HOLDINGS_CACHE) or {}
    meta = load_json(HOLDINGS_META_CACHE) or {}

    for _, row in portfolio.iterrows():
        isin = str(row["isin"]).upper()
        fund_name = str(row.get("fund_name") or "")
        scheme = choose_scheme(isin, fund_name, isin_index)
        scheme_code = str(scheme.get("scheme_code") or "").strip()
        if not scheme_code:
            print(f"No AMFI scheme for {isin} {fund_name[:40]}")
            continue

        result = ingest_scheme_holdings(scheme_code, fund_name=fund_name, amfi_row=scheme)
        holdings = (result or {}).get("holdings") or []
        as_of = (result or {}).get("as_of") or ""
        source = (result or {}).get("source") or ""

        if holdings:
            cache[scheme_code] = holdings
            prior_cmp = compare_to_prior(scheme_code, as_of, holdings)
            try:
                archive_scheme_snapshot(
                    scheme_code,
                    as_of,
                    holdings,
                    meta_extra={
                        "fund_name": fund_name,
                        "source": source,
                        **{k: v for k, v in prior_cmp.items() if k != "diff_limitation"},
                    },
                )
            except Exception as exc:
                print(f"Archive failed for {scheme_code}: {exc}")
            meta[scheme_code] = {
                "as_of": as_of,
                "source": source,
                "fund_name": fund_name,
                "amfi_scheme_name": scheme.get("scheme_name"),
                "holding_count": len(holdings),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                **prior_cmp,
            }
            print(
                f"{scheme_code} {fund_name[:36]:36} as_of={as_of} "
                f"n={len(holdings)} src={source} cmp={prior_cmp.get('comparison_status')}"
            )
        else:
            print(f"Empty holdings for {scheme_code} {fund_name[:40]} — keeping prior cache")

    save_json_atomic(HOLDINGS_CACHE, cache)
    save_json_atomic(HOLDINGS_META_CACHE, meta)
    try:
        write_holdings_change_summary(meta)
    except Exception as exc:
        print(f"Change summary skipped: {exc}")

    try:
        write_portfolio_history_row(portfolio, isin_index, sheets)
    except Exception as exc:
        print(f"History row failed: {exc}")
        return 1

    print("Holdings refresh complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
