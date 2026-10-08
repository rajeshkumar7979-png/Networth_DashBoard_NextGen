"""Opt-in Upstox market tape. Analytics token only. No holdings call."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pandas as pd

from lib.company_tape import rsi_wilder, sma

SOURCE = "Upstox Analytics token"
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
    try:
        import streamlit as st
        secrets = st.secrets
        for path in (("upstox", "ACCESS_TOKEN"), ("upstox", "ANALYTICS_TOKEN"), ("UPSTOX_ACCESS_TOKEN",)):
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


def _latest(history):
    if not history or not isinstance(history[0], dict):
        return None, None
    return history[0].get("value"), history[0].get("period")


def tape_from_payloads(isin, quote=None, ratios=None, candles=None, retrieved_at=None, income=None, cash_flow=None, balance=None, holdings=None, actions=None, news=None):
    rows = []

    def add(label, value, sub=""):
        if value is None or value == "":
            return
        rows.append({"label": label, "value": value, "sub": sub})

    data = (quote or {}).get("data") if isinstance(quote, dict) else {}
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
    labels = {"P/E": "Trailing P/E", "P/B": "Price / Book", "ROA": "ROA", "ROE": "ROE", "ROCE": "ROCE", "EV/EBITDA": "EV / EBITDA"}
    for item in ((ratios or {}).get("data") or []):
        if not isinstance(item, dict):
            continue
        label = labels.get(str(item.get("name") or "").strip())
        if not label:
            continue
        add(label, _finite(item.get("company_value")), "Upstox")
        sector = _finite(item.get("sector_value"))
        if sector is not None:
            add(label + " sector", sector, "Upstox sector benchmark")
    history = []
    raw = (((candles or {}).get("data") or {}).get("candles")) or []
    closes = [_finite(bar[4]) for bar in raw if isinstance(bar, (list, tuple)) and len(bar) >= 5]
    closes = [c for c in closes if c is not None]
    if closes:
        history = list(reversed(closes))
        series = pd.Series(history)
        add("SMA 20", sma(series, 20), "Upstox daily")
        add("SMA 50", sma(series, 50), "Upstox daily")
        add("SMA 200", sma(series, 200), "Upstox daily")
        add("RSI-14", rsi_wilder(series), "Wilder, Upstox daily")
        add("52-week high", _finite(series.iloc[-252:].max()))
        add("52-week low", _finite(series.iloc[-252:].min()))
    statements = []
    for payload, key, title in ((income, "income_statement", "Income"), (cash_flow, "cash_flow", "Cash flow"), (balance, "balance_sheet", "Balance sheet")):
        body = (payload or {}).get("data") if isinstance(payload, dict) else None
        if not isinstance(body, dict):
            continue
        for block in body.get(key) or []:
            if not isinstance(block, dict):
                continue
            value, period = _latest(block.get("history") or [])
            if value is None:
                continue
            statements.append({"Statement": title, "Line": str(block.get("category") or "").replace("_", " ").title(), "Latest": value, "Period": period or "", "Unit": body.get("units_in") or "crore"})
    shareholding = []
    hold_body = (holdings or {}).get("data") if isinstance(holdings, dict) else None
    hold_rows = hold_body if isinstance(hold_body, list) else (hold_body or {}).get("share_holdings") if isinstance(hold_body, dict) else []
    for item in hold_rows or []:
        if not isinstance(item, dict):
            continue
        value, period = _latest(item.get("history") or [])
        shareholding.append({"Holder": str(item.get("category") or item.get("name") or "").replace("_", " ").title(), "Percent": value if value is not None else item.get("percentage"), "Period": period or ""})
    action_rows = []
    action_body = (actions or {}).get("data") if isinstance(actions, dict) else None
    action_list = action_body if isinstance(action_body, list) else (action_body or {}).get("corporate_actions") if isinstance(action_body, dict) else []
    for item in (action_list or [])[:8]:
        if isinstance(item, dict):
            action_rows.append({"Action": item.get("type") or item.get("name") or "", "Ex date": item.get("ex_date") or item.get("date") or "", "Detail": item.get("amount") or item.get("ratio") or ""})
    news_rows = []
    news_body = (news or {}).get("data") if isinstance(news, dict) else None
    items = news_body if isinstance(news_body, list) else []
    if isinstance(news_body, dict):
        for value in news_body.values():
            if isinstance(value, list):
                items.extend(value)
    for item in items[:6]:
        if isinstance(item, dict) and (item.get("title") or item.get("headline")):
            news_rows.append({"Headline": item.get("title") or item.get("headline"), "Published": item.get("published_at") or "", "Link": item.get("url") or item.get("link") or ""})
    tech = {"SMA 20", "SMA 50", "SMA 200", "RSI-14", "52-week high", "52-week low", "Last price"}
    return {
        "ok": bool(rows or statements or news_rows),
        "source": SOURCE,
        "ticker": isin,
        "name": str(node.get("symbol") or ""),
        "retrieved_at": retrieved_at,
        "history": history,
        "fundamentals": {"rows": [r for r in rows if r["label"] not in tech or r["label"] == "Last price"], "source": SOURCE},
        "technicals": {"rows": [r for r in rows if r["label"] in tech], "source": SOURCE},
        "statements": statements,
        "shareholding": [r for r in shareholding if r.get("Holder")],
        "actions": [r for r in action_rows if r.get("Action")],
        "news": news_rows,
        "error": None if rows else "Upstox returned no usable fields for this ISIN.",
    }


def fetch_upstox_equity(isin: str, exchange: str = "NSE") -> dict:
    token = read_upstox_token()
    key = instrument_key(isin, exchange)
    retrieved = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not token:
        return {"ok": False, "source": SOURCE, "error": "Analytics token is not in Streamlit secrets.", "retrieved_at": retrieved}
    if not key:
        return {"ok": False, "source": SOURCE, "error": "This line has no ISIN, so Upstox cannot be queried.", "retrieved_at": retrieved}
    import requests
    headers = {"Accept": "application/json", "Authorization": "Bearer " + token, "User-Agent": "NorthlineFamilyDesk/1.0"}
    code = isin.strip().upper()
    to_date = datetime.now(timezone.utc).date()
    from_date = to_date - timedelta(days=400)

    def get(url, params=None):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=20)
            return response.json() if response.status_code == 200 else {}
        except Exception:
            return {}

    root = BASE + "/fundamentals/" + code
    return tape_from_payloads(
        isin,
        quote=get(BASE + "/market-quote/quotes", {"instrument_key": key}),
        ratios=get(root + "/key-ratios"),
        candles=get(BASE + "/historical-candle/" + key + "/day/" + to_date.isoformat() + "/" + from_date.isoformat()),
        income=get(root + "/income-statement", {"type": "consolidated", "time_period": "yearly"}),
        cash_flow=get(root + "/cash-flow", {"type": "consolidated"}),
        balance=get(root + "/balance-sheet", {"type": "consolidated"}),
        holdings=get(root + "/share-holdings"),
        actions=get(root + "/corporate-actions"),
        news=get(BASE + "/news", {"category": "instrument_keys", "instrument_keys": key, "page_size": 5}),
        retrieved_at=retrieved,
    )
