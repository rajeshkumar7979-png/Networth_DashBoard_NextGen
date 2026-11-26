"""FRED series client for macro context (Outlook / Intelligence).

Uses FRED_API_KEY from env or Streamlit secrets [fred].FRED_API_KEY.
Never invents observations; returns empty on failure.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

_UA = "NorthlineFamilyDesk/1.0"
_BASE = "https://api.stlouisfed.org/fred"


def read_fred_key() -> str:
    key = str(os.environ.get("FRED_API_KEY") or "").strip()
    if key:
        return key
    try:
        import streamlit as st

        secrets = st.secrets
        for path in (("fred", "FRED_API_KEY"), ("fred", "api_key"), ("FRED_API_KEY",)):
            cur = secrets
            ok = True
            for k in path:
                if not hasattr(cur, "get"):
                    ok = False
                    break
                cur = cur.get(k)
            if ok and cur and not hasattr(cur, "get"):
                return str(cur).strip()
    except Exception:
        pass
    return ""


# Series useful for an NRI India desk (US rates / USD / risk)
DEFAULT_SERIES = (
    ("DGS10", "US 10Y Treasury"),
    ("DFF", "Fed funds effective"),
    ("DTWEXBGS", "USD broad index"),
    ("DCOILWTICO", "WTI crude"),
)


def fetch_series_latest(series_id: str, key: Optional[str] = None) -> Dict[str, Any]:
    """Return {id, title optional, date, value} or empty dict."""
    api_key = (key or read_fred_key()).strip()
    if not api_key or not series_id:
        return {}
    try:
        r = requests.get(
            f"{_BASE}/series/observations",
            params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 5,
            },
            headers={"User-Agent": _UA},
            timeout=20,
        )
        if r.status_code != 200:
            return {"id": series_id, "error": f"http_{r.status_code}"}
        obs = (r.json() or {}).get("observations") or []
        for row in obs:
            val = str(row.get("value") or "").strip()
            if val and val != ".":
                return {
                    "id": series_id,
                    "date": row.get("date"),
                    "value": float(val),
                    "source": "FRED",
                }
    except Exception as exc:
        return {"id": series_id, "error": type(exc).__name__}
    return {"id": series_id, "error": "no_observation"}


def macro_snapshot(series: Optional[List[tuple]] = None) -> List[Dict[str, Any]]:
    """Fetch latest points for the default (or given) series list."""
    rows = []
    key = read_fred_key()
    if not key:
        return [{"error": "FRED_API_KEY not configured"}]
    for sid, title in series or DEFAULT_SERIES:
        point = fetch_series_latest(sid, key=key)
        if point.get("value") is not None:
            point["title"] = title
            rows.append(point)
        elif point.get("error"):
            rows.append({"id": sid, "title": title, "error": point["error"]})
    return rows
