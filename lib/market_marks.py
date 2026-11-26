"""Live equity LTP: Upstox (token) then Yahoo (UA) then none."""
from __future__ import annotations

import gzip
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

_UA = "NorthlineFamilyDesk/1.0"
_UPSTOX_BASE = "https://api.upstox.com/v2"
_INSTRUMENT_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
_CACHE = Path(__file__).resolve().parents[1] / "data" / "cache" / "upstox_nse_eq_map.json"


def read_upstox_token_env() -> str:
    tok = str(os.environ.get("UPSTOX_ACCESS_TOKEN") or "").strip()
    if tok:
        return tok
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
    return ""


def _load_nse_eq_map() -> Dict[str, str]:
    if _CACHE.exists() and time.time() - _CACHE.stat().st_mtime < 86400:
        try:
            data = json.loads(_CACHE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                return {str(k).upper(): str(v) for k, v in data.items()}
        except Exception:
            pass
    try:
        r = requests.get(_INSTRUMENT_URL, timeout=60, headers={"User-Agent": _UA})
        r.raise_for_status()
        rows = json.loads(gzip.decompress(r.content))
    except Exception as exc:
        print(f"Upstox instrument map fetch failed: {exc}")
        return {}
    out: Dict[str, str] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or str(row.get("segment") or "") != "NSE_EQ":
            continue
        sym = str(row.get("trading_symbol") or "").strip().upper()
        key = str(row.get("instrument_key") or "").strip()
        if sym and key and sym not in out:
            out[sym] = key
        isin = str(row.get("isin") or "").strip().upper()
        if isin and key and f"ISIN:{isin}" not in out:
            out[f"ISIN:{isin}"] = key
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(out), encoding="utf-8")
        tmp.replace(_CACHE)
    except Exception:
        pass
    return out


def _yahoo_ltp(symbol: str) -> Optional[float]:
    sym = symbol.strip().upper()
    if not sym:
        return None
    if sym.endswith(".NS") or sym.endswith(".BO") or "-" in sym:
        candidates = [sym]
    else:
        candidates = [f"{sym}.NS", f"{sym}.BO", sym]
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NorthlineFamilyDesk/1.0)"}
    for cand in candidates:
        try:
            r = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{cand}",
                params={"interval": "1d", "range": "5d"},
                timeout=15,
                headers=headers,
            )
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


def resolve_ltps(
    symbols: List[str],
    isins: Optional[List[Optional[str]]] = None,
) -> Dict[str, Tuple[float, str]]:
    result: Dict[str, Tuple[float, str]] = {}
    if not symbols:
        return result
    syms = [str(s or "").strip().upper() for s in symbols]
    isin_list = isins or [None] * len(syms)
    token = read_upstox_token_env()
    key_by_sym: Dict[str, str] = {}
    if token:
        eq_map = _load_nse_eq_map()
        for i, sym in enumerate(syms):
            if not sym:
                continue
            isin = str(isin_list[i] or "").strip().upper() if i < len(isin_list) else ""
            if isin and f"ISIN:{isin}" in eq_map:
                key = eq_map[f"ISIN:{isin}"]
            elif isin:
                key = f"NSE_EQ|{isin}"
            elif sym in eq_map:
                key = eq_map[sym]
            else:
                key = ""
            if key:
                key_by_sym[sym] = key
        headers = {
            "Accept": "application/json",
            "Authorization": "Bearer " + token,
            "User-Agent": _UA,
        }
        keys = list(dict.fromkeys(key_by_sym.values()))
        prices_by_key: Dict[str, float] = {}
        for i in range(0, len(keys), 40):
            chunk = keys[i : i + 40]
            try:
                r = requests.get(
                    _UPSTOX_BASE + "/market-quote/ltp",
                    params={"instrument_key": ",".join(chunk)},
                    headers=headers,
                    timeout=25,
                )
                if r.status_code != 200:
                    print(f"Upstox LTP HTTP {r.status_code}")
                    continue
                data = (r.json() or {}).get("data") or {}
                if not isinstance(data, dict):
                    continue
                rev = {v: k for k, v in key_by_sym.items()}
                for resp_key, node in data.items():
                    if not isinstance(node, dict):
                        continue
                    price = node.get("last_price")
                    if price is None:
                        continue
                    ik = str(node.get("instrument_key") or "").strip()
                    sym = rev.get(ik)
                    if not sym and ":" in str(resp_key):
                        sym = str(resp_key).split(":")[-1].upper()
                    if sym:
                        result[sym] = (float(price), "upstox")
                    if ik:
                        prices_by_key[ik] = float(price)
                for sym, key in key_by_sym.items():
                    if sym not in result and key in prices_by_key:
                        result[sym] = (prices_by_key[key], "upstox")
            except Exception as exc:
                print(f"Upstox LTP batch error: {exc}")
    for sym in syms:
        if not sym or sym in result:
            continue
        px = _yahoo_ltp(sym)
        if px is not None:
            result[sym] = (px, "yahoo")
    return result


def ltp_one(symbol: str, isin: Optional[str] = None) -> Tuple[Optional[float], str]:
    got = resolve_ltps([symbol], [isin])
    sym = str(symbol or "").strip().upper()
    if sym in got:
        return got[sym]
    return None, "none"
