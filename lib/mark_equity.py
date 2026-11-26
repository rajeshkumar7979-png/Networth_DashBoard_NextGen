"""Equity mark helper used by update_holdings_cache."""
from __future__ import annotations
from typing import Dict, Tuple
import pandas as pd
from lib.market_marks import resolve_ltps

def _norm_col(value) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())

def mark_stocks_current(sheets: Dict[str, pd.DataFrame]) -> Tuple[float, float, int, str, float, float, int, int, int]:
    stocks_current = stocks_invested = 0.0
    gold_current = gold_invested = 0.0
    stocks_rows = gold_rows = 0
    marks_used = set()
    live_hits = 0
    live_attempts = 0
    pending = []
    for name, df in sheets.items():
        if df is None or df.empty:
            continue
        if "stock" not in name.lower() and "equity" not in name.lower():
            continue
        ticker_col = qty_col = inv_col = isin_col = None
        for col in df.columns:
            n = _norm_col(col)
            if n in {"ticker / symbol", "ticker", "symbol"}:
                ticker_col = col
            if n in {"quantity", "qty", "units"}:
                qty_col = col
            if n in {"invested amount", "invested", "cost"}:
                inv_col = col
            if n in {"isin", "isin code", "isin number"}:
                isin_col = col
        if not ticker_col:
            continue
        for _, r in df.iterrows():
            ticker = str(r.get(ticker_col) or "").strip().upper()
            if not ticker or ticker in {"NAN", "NONE"}:
                continue
            inv = float(r.get(inv_col) or 0) if inv_col else 0.0
            qty = float(r.get(qty_col) or 0) if qty_col else 0.0
            isin = str(r.get(isin_col) or "").strip().upper() if isin_col else ""
            is_gold = any(k in ticker for k in ("GOLD", "SGB", "GBEES")) or "-GB" in ticker
            pending.append((ticker, isin or None, qty, inv, is_gold))
    ltps = resolve_ltps([t[0] for t in pending], [t[1] for t in pending]) if pending else {}
    for ticker, isin, qty, inv, is_gold in pending:
        live_attempts += 1
        hit = ltps.get(ticker)
        if hit is not None and qty > 0:
            ltp, source = hit
            value = float(ltp) * qty
            marks_used.add("upstox_ltp" if source == "upstox" else "yahoo_ltp")
            live_hits += 1
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
        int(live_hits), int(live_attempts),
    )
