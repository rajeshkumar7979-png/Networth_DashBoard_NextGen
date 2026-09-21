# -------------------------------------------------
# Canonical Command Center run stamps.
#
# Other pages must not print datetime.now() as if it were the valuation
# clock. Command publishes cc_assets["valued_at"] (full IST ISO) and
# cc_assets["as_of"] (the date used for days-held / days-to-maturity).
# Pages read those. datetime.now is only "page opened".
# Pure: no Streamlit, no network, no re-valuation.
# -------------------------------------------------
from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytz

IST = pytz.timezone("Asia/Kolkata")


def page_opened_ist() -> datetime:
    return datetime.now(IST)


def _assets(session) -> dict:
    raw = (session or {}).get("cc_assets") if session is not None else None
    return raw if isinstance(raw, dict) else {}


def valued_at_iso(session) -> str | None:
    stamp = _assets(session).get("valued_at")
    if stamp:
        return str(stamp)
    return None


def as_of_date_str(session) -> str | None:
    stamp = _assets(session).get("as_of")
    if stamp:
        return str(stamp)
    return None


def as_of_timestamp(session):
    """Calendar date Command used for maturity / holding-period math.

    Returns a naive pandas Timestamp at midnight, or None when Command
    has not published a run. Callers must not fall back to today.
    """
    raw = as_of_date_str(session)
    if raw:
        ts = pd.to_datetime(raw, errors="coerce")
        if pd.notna(ts):
            return pd.Timestamp(ts.date())
    iso = valued_at_iso(session)
    if iso:
        ts = pd.to_datetime(iso, errors="coerce")
        if pd.notna(ts):
            return pd.Timestamp(ts.date())
    return None


def _format_ist(value) -> str | None:
    ts = pd.to_datetime(value, errors="coerce")
    if not pd.notna(ts):
        return None
    if getattr(ts, "tzinfo", None) is None and getattr(ts, "tz", None) is None:
        ts = ts.tz_localize(IST)
    else:
        ts = ts.tz_convert(IST)
    return ts.strftime("%d %b %Y, %H:%M IST")


def header_valued_at(session) -> str:
    """Page-header stamp. Never a fresh now() pretending to be the book."""
    iso = valued_at_iso(session)
    formatted = _format_ist(iso) if iso else None
    if formatted:
        return f"VALUED {formatted}"
    as_of = as_of_date_str(session)
    if as_of:
        return f"VALUED {as_of} (date only)"
    return "NO VALUATION THIS SESSION"


def page_opened_label(now=None) -> str:
    stamp = now or page_opened_ist()
    return f"PAGE OPENED {stamp.strftime('%d %b %Y, %H:%M IST')}"
