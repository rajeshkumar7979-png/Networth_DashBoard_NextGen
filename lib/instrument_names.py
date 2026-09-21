# -------------------------------------------------
# Instrument display names.
#
# The family workbook's Stocks "Company Name" column is often an ISIN
# (INE…), not a legal name. We never invent a name:
#   1. a non-ISIN Company Name from the book wins
#   2. else the most common disclosed name for that ISIN in the committed
#      MF holdings cache (statutory filings, same ISIN)
#   3. else the ticker
# Missing stays the ticker. No fuzzy match, no network.
# -------------------------------------------------
from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from lib.config import DATA_DIR

ISIN_RE = re.compile(r"^IN[A-Z0-9]{9}[0-9]$")
_JUNK_SUFFIX = re.compile(r"[\s£*^#]+$")
_PAREN_TAIL = re.compile(r"\s+\([^)]*\)\s*$")


def looks_like_isin(value) -> bool:
    s = str(value or "").strip().upper()
    return bool(ISIN_RE.match(s))


def extract_isin(*values) -> str:
    for value in values:
        s = str(value or "").strip().upper()
        if ISIN_RE.match(s):
            return s
    return ""


def clean_disclosed_name(name: str) -> str:
    s = str(name or "").strip()
    s = _JUNK_SUFFIX.sub("", s)
    s = _PAREN_TAIL.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(" -")
    if not s or looks_like_isin(s):
        return ""
    return s


def _pick_name(counter: Counter) -> str:
    if not counter:
        return ""
    return counter.most_common(1)[0][0]


@lru_cache(maxsize=1)
def isin_name_index(path: str | None = None) -> dict:
    p = Path(path) if path else DATA_DIR / "mf_holdings_cache.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    buckets: dict[str, Counter] = {}
    holds_iter = data.values() if isinstance(data, dict) else []
    for holds in holds_iter:
        if not isinstance(holds, list):
            continue
        for row in holds:
            if not isinstance(row, dict):
                continue
            isin = extract_isin(row.get("isin"))
            name = clean_disclosed_name(row.get("name") or "")
            if isin and name:
                buckets.setdefault(isin, Counter())[name] += 1
    return {k: _pick_name(v) for k, v in buckets.items()}


def equity_display_name(company_name="", symbol="", isin="", names=None) -> str:
    """Human label for a direct equity line. Never returns an ISIN if a
    ticker or disclosed name exists."""
    raw = str(company_name or "").strip()
    if raw and not looks_like_isin(raw):
        return raw
    code = extract_isin(isin, raw)
    index = names if names is not None else isin_name_index()
    if code and index.get(code):
        return index[code]
    tick = str(symbol or "").strip()
    if tick and not looks_like_isin(tick):
        return tick
    return raw or tick or code or ""
