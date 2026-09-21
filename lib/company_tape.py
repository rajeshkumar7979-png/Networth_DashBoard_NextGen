# -------------------------------------------------
# Company tape for a direct equity line.
#
# Fundamentals are Yahoo-published fields (observed). Technicals are
# calculated from Yahoo daily closes (SMA, Wilder RSI-14, 52-week range).
# Missing fields stay missing. Nothing here is a buy/sell signal.
# Pure except fetch_yahoo_equity(), which is the only network seam.
# -------------------------------------------------
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

YAHOO_SOURCE = "Yahoo Finance (yfinance)"
RSI_PERIOD = 14
TECHNICAL_NOTE = (
    "Technicals are calculated from Yahoo daily closes (Wilder RSI-14, SMA). "
    "They describe the tape, not an order."
)
FUNDAMENTAL_NOTE = (
    "Ratios are Yahoo's published figures for this ticker, not a DCF and "
    "not NSE/BSE official. Missing stays missing — never a guessed PE."
)


def _finite(value):
    if value is None or value == "" or value == "None":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    return n


def yahoo_ticker(symbol: str, exchange: str = "NSE") -> str:
    raw = str(symbol or "").strip().upper()
    if not raw:
        return ""
    if "." in raw:
        return raw
    ex = str(exchange or "NSE").strip().upper()
    if ex in {"BSE", "BOM"}:
        return raw + ".BO"
    return raw + ".NS"


def rsi_wilder(close: pd.Series, period: int = RSI_PERIOD):
    """Wilder RSI. Returns None when the series is too short."""
    if close is None or len(close.dropna()) < period + 1:
        return None
    delta = close.astype(float).diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    last_gain = _finite(avg_gain.iloc[-1])
    last_loss = _finite(avg_loss.iloc[-1])
    if last_gain is None or last_loss is None:
        return None
    if last_loss == 0:
        return 100.0 if last_gain > 0 else None
    rs = last_gain / last_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def sma(close: pd.Series, window: int):
    if close is None or len(close.dropna()) < window:
        return None
    return _finite(close.astype(float).rolling(window).mean().iloc[-1])


def _pct_field(info: dict, key: str):
    n = _finite((info or {}).get(key))
    if n is None:
        return None
    # Yahoo stores 0.012 for 1.2%. Values already > 1.5 are treated as percent.
    return n * 100.0 if abs(n) <= 1.5 else n


def fundamentals_from_info(info: dict) -> dict:
    info = info or {}
    rows = []

    def add(label, value, sub=""):
        if value is None or value == "":
            return
        rows.append({"label": label, "value": value, "sub": sub})

    add("Sector", str(info.get("sector") or "").strip() or None)
    add("Industry", str(info.get("industry") or "").strip() or None)
    cap = _finite(info.get("marketCap"))
    add("Market cap", cap, "INR" if cap and cap > 1e6 else "")
    add("Trailing P/E", _finite(info.get("trailingPE")), "Yahoo ratio")
    add("Forward P/E", _finite(info.get("forwardPE")), "Yahoo ratio")
    add("Price / Book", _finite(info.get("priceToBook")), "Yahoo ratio")
    add("Book value / share", _finite(info.get("bookValue")))
    add("Trailing EPS", _finite(info.get("trailingEps")))
    add("Profit margin", _pct_field(info, "profitMargins"), "%")
    add("ROE", _pct_field(info, "returnOnEquity"), "%")
    add("Dividend yield", _pct_field(info, "dividendYield"), "%")
    add("Beta", _finite(info.get("beta")))
    add("Debt / Equity", _finite(info.get("debtToEquity")))
    return {"rows": rows, "source": YAHOO_SOURCE, "note": FUNDAMENTAL_NOTE}


def technicals_from_history(hist: pd.DataFrame, info: dict | None = None) -> dict:
    info = info or {}
    rows = []
    as_of = None
    close = None
    if hist is not None and not getattr(hist, "empty", True) and "Close" in hist.columns:
        close = hist["Close"].dropna()
        if len(close):
            last_idx = close.index[-1]
            try:
                as_of = pd.Timestamp(last_idx).strftime("%Y-%m-%d")
            except Exception:
                as_of = str(last_idx)
    last = _finite(close.iloc[-1]) if close is not None and len(close) else _finite(
        (info or {}).get("currentPrice") or (info or {}).get("regularMarketPrice")
    )
    sma20 = sma(close, 20) if close is not None else None
    sma50 = sma(close, 50) if close is not None else None
    sma200 = sma(close, 200) if close is not None else None
    rsi = rsi_wilder(close) if close is not None else None
    high_52 = _finite((info or {}).get("fiftyTwoWeekHigh"))
    low_52 = _finite((info or {}).get("fiftyTwoWeekLow"))
    if close is not None and len(close) >= 60:
        window = close.iloc[-252:] if len(close) >= 252 else close
        high_52 = high_52 or _finite(window.max())
        low_52 = low_52 or _finite(window.min())

    def add(label, value, sub=""):
        if value is None:
            return
        rows.append({"label": label, "value": value, "sub": sub})

    add("Last close", last, as_of or "Yahoo")
    add("SMA 20", sma20, "daily")
    add("SMA 50", sma50, "daily")
    add("SMA 200", sma200, "daily")
    add("RSI-14", rsi, "Wilder, daily closes")
    if last is not None and sma50:
        add("vs SMA 50", (last / sma50 - 1.0) * 100.0, "%")
    add("52-week high", high_52)
    add("52-week low", low_52)
    if last is not None and high_52 and low_52 and high_52 > low_52:
        add("In 52-week range", (last - low_52) / (high_52 - low_52) * 100.0, "% from low")
    return {
        "rows": rows,
        "as_of": as_of,
        "source": YAHOO_SOURCE,
        "note": TECHNICAL_NOTE,
        "bars": int(len(close)) if close is not None else 0,
    }


def build_equity_tape(info=None, hist=None, ticker="", retrieved_at=None) -> dict:
    funda = fundamentals_from_info(info or {})
    tech = technicals_from_history(hist if hist is not None else pd.DataFrame(), info or {})
    return {
        "ticker": ticker,
        "name": str((info or {}).get("longName") or (info or {}).get("shortName") or "").strip(),
        "retrieved_at": retrieved_at,
        "fundamentals": funda,
        "technicals": tech,
        "ok": bool(funda["rows"] or tech["rows"]),
        "source": YAHOO_SOURCE,
    }


def fetch_yahoo_equity(symbol: str, exchange: str = "NSE") -> dict:
    """Network seam. Callers must invoke on an explicit user action / cache."""
    import yfinance as yf

    ticker = yahoo_ticker(symbol, exchange)
    if not ticker:
        return build_equity_tape(ticker=ticker)
    retrieved = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    info = {}
    hist = pd.DataFrame()
    try:
        t = yf.Ticker(ticker)
        try:
            info = dict(t.info or {})
        except Exception:
            info = {}
        try:
            hist = t.history(period="1y")
            if hist is None:
                hist = pd.DataFrame()
        except Exception:
            hist = pd.DataFrame()
    except Exception:
        return {
            **build_equity_tape(ticker=ticker, retrieved_at=retrieved),
            "ok": False,
            "error": "Yahoo tape unavailable this run.",
        }
    tape = build_equity_tape(info, hist, ticker, retrieved)
    if not tape["ok"]:
        tape["error"] = "Yahoo returned no usable fields for this ticker this run."
    return tape
