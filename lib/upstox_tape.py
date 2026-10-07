"""Opt-in Upstox market tape for a direct equity line.

Reads the access token from Streamlit secrets or UPSTOX_ACCESS_TOKEN.
Never writes the token. Uses the ISIN already on the book:
  instrument key NSE_EQ|{ISIN}
  quote:        GET /v2/market-quote/quotes
  ratios:       GET /v2/fundamentals/{isin}/key-ratios
  daily bars:   GET /v2/historical-candle/{key}/day/{to}/{from}
Missing fields stay missing. This does not value mutual funds.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pandas as pd

from lib.company_tape import rsi_wilder, sma

SOURCE = "Upstox market data"
BASE = "https://api.upstox.com/v2"


def _finite(value):
    if value is None or value == "":
        return None
    text = str(value).replace("%", "").replace(",", "").strip()
    try:
        n = float(text)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    return n


def instrument_key(isin: str, exchange: str = "NSE") -> str:
    code = str(isin or "").strip().upper()
    if not code or len(code) < 10:
        return ""
    segment = "BSE_EQ" if str(exchange or "").upper() in {"BSE", "BOM"} else "NSE_EQ"
    return segment + "|" + code


def read_upstox_token() -> str:
    """Secret only. Returns empty when unset. Never logs the value."""
    try:
        import streamlit as st
        secrets = st.secrets
        for path in (
            ("upstox", "ACCESS_TOKEN"),
            ("upstox", "access_token"),
            ("UPSTOX_ACCESS_TOKEN",),
        ):
            cur = secrets
            ok = True
            for key in path:
                if not hasattr(cur, "get"):
                    ok = False
                    break
                cur = cur.get(key)
            if ok and cur and not hasattr(cur, "get"):
                return str(cur).strip()
    except Exception:
        pass
    return str(os.environ.get("UPSTOX_ACCESS_TOKEN") or "").strip()


def tape_from_payloads(isin, quote=None, ratios=None, candles=None, retrieved_at=None):
    """Pure builder. quote/ratios/candles are already-parsed API bodies."""
    rows = []

    def add(label, value, sub=""):
        if value is None or value == "":
            return
        rows.append({"label": label, "value": value, "sub": sub})

    quote = quote or {}
    data = (quote.get("data") or {}) if isinstance(quote, dict) else {}
    node = next(iter(data.values()), {}) if isinstance(data, dict) and data else {}
    last = _finite(node.get("last_price"))
    ohlc = node.get("ohlc") or {}
    add("Last price", last, "Upstox")
    add("Day open", _finite(ohlc.get("open")), "Upstox")
    add("Day high", _finite(ohlc.get("high")), "Upstox")
    add("Day low", _finite(ohlc.get("low")), "Upstox")
    prev = _finite(ohlc.get("close"))
    add("Previous close", prev, "Upstox")
    if last is not None and prev:
        add("Day change", (last / prev - 1.0) * 100.0, "%")

    ratio_rows = ratios.get("data") if isinstance(ratios, dict) else None
    labels = {
        "P/E": "Trailing P/E",
        "P/B": "Price / Book",
        "ROA": "ROA",
        "ROE": "ROE",
        "ROCE": "ROCE",
        "EV/EBITDA": "EV / EBITDA",
    }
    for item in ratio_rows or []:
        if not isinstance(item, dict):
            continue
        label = labels.get(str(item.get("name") or "").strip())
        if not label:
            continue
        add(label, _finite(item.get("company_value")), "Upstox")
        sector = _finite(item.get("sector_value"))
        if sector is not None:
            add(label + " sector", sector, "Upstox sector benchmark")

    frame = pd.DataFrame()
    if isinstance(candles, dict):
        raw = ((candles.get("data") or {}).get("candles")) or []
        closes = []
        for bar in raw:
            if isinstance(bar, (list, tuple)) and len(bar) >= 5:
                closes.append(_finite(bar[4]))
        closes = [c for c in closes if c is not None]
        if closes:
            frame = pd.DataFrame({"Close": list(reversed(closes))})
            series = frame["Close"]
            add("SMA 20", sma(series, 20), "Upstox daily")
            add("SMA 50", sma(series, 50), "Upstox daily")
            add("SMA 200", sma(series, 200), "Upstox daily")
            add("RSI-14", rsi_wilder(series), "Wilder, Upstox daily")
            add("52-week high", _finite(series.iloc[-252:].max()) if len(series) else None)
            add("52-week low", _finite(series.iloc[-252:].min()) if len(series) else None)
    return {
        "ok": bool(rows),
        "source": SOURCE,
        "ticker": isin,
        "name": str(node.get("symbol") or ""),
        "retrieved_at": retrieved_at,
        "fundamentals": {"rows": [r for r in rows if "SMA" not in r["label"] and r["label"] != "RSI-14"], "source": SOURCE},
        "technicals": {"rows": [r for r in rows if "SMA" in r["label"] or r["label"] in {"RSI-14", "52-week high", "52-week low", "Last price"}], "source": SOURCE},
        "error": None if rows else "Upstox returned no usable fields for this ISIN.",
    }


def fetch_upstox_equity(isin: str, exchange: str = "NSE") -> dict:
    """Network seam. Call only from an explicit button."""
    token = read_upstox_token()
    key = instrument_key(isin, exchange)
    retrieved = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not token:
        return {"ok": False, "source": SOURCE, "error": "Upstox token is not in Streamlit secrets.", "retrieved_at": retrieved}
    if not key:
        return {"ok": False, "source": SOURCE, "error": "This line has no ISIN, so Upstox cannot be queried.", "retrieved_at": retrieved}
    import requests
    headers = {"Accept": "application/json", "Authorization": "Bearer " + token}
    to_date = datetime.now(timezone.utc).date()
    from_date = to_date - timedelta(days=400)

    def get(url, params=None):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=20)
            if response.status_code != 200:
                return {}
            return response.json()
        except Exception:
            return {}

    quote = get(BASE + "/market-quote/quotes", {"instrument_key": key})
    ratios = get(BASE + "/fundamentals/" + isin.strip().upper() + "/key-ratios")
    candles = get(
        BASE + "/historical-candle/" + key + "/day/" + to_date.isoformat() + "/" + from_date.isoformat()
    )
    tape = tape_from_payloads(isin, quote, ratios, candles, retrieved)
    if not tape.get("ok") and not tape.get("error"):
        tape["error"] = "Upstox returned no usable fields for this ISIN."
    return tape
