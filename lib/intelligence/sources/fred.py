# -------------------------------------------------
# Intelligence Data Gateway — FRED (Federal Reserve Economic Data).
#
# Provider: config-driven (FRED_API_KEY from Streamlit-native secrets
# `st.secrets["fred"]["FRED_API_KEY"]` inside a running Streamlit script, else
# the FRED_API_KEY env var; never hard-coded, never logged, never stored in
# cache). Normalizes raw observations only: missing "." points are skipped,
# real zero values are kept, and NO computed deltas or derived macro signals
# are produced here.
# -------------------------------------------------
from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime
from typing import Optional

from . import httpio as _http
from .cache import Cache
from .errors import ProviderConfigMissing
from .record import (
    SourceRecord,
    SourceResult,
    cached_result,
    dedupe_records,
    make_record_id,
    unavailable_result,
    utc_now,
)
from lib.intelligence.model import SourceClass, SourceType

FRED_BASE = "https://api.stlouisfed.org/fred"
FRED_DEFAULT_TTL = 12 * 3600

_MISSING = {"", ".", "n/a"}


def _streamlit_fred_key() -> Optional[str]:
    """Read `[fred]` FRED_API_KEY from Streamlit's native secrets.

    Returns None (never raises) outside a running Streamlit script run, when no
    `[fred]` section exists, or when the value is missing/empty — the caller
    then falls back to the environment. Scripts and pytest never touch the
    secrets file. The key is never echoed anywhere by this module.
    """
    try:
        import streamlit as st
    except ImportError:  # scripts, pytest, plain module imports
        return None
    runtime = getattr(st, "runtime", None)
    try:
        if runtime is None or not runtime.exists():
            return None
        section = st.secrets.get("fred", {})
    except Exception:
        return None
    # Streamlit returns an AttrDict (a Mapping, not a dict subclass).
    if not isinstance(section, Mapping):
        return None
    value = section.get("FRED_API_KEY")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _api_key() -> str:
    key = _streamlit_fred_key()
    if not key:
        key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise ProviderConfigMissing(
            "FRED_API_KEY is not set (expected in `st.secrets['fred']` or the "
            "`FRED_API_KEY` environment variable); FRED is unavailable")
    return key


def _series_meta(series_id: str) -> dict:
    key = _api_key()
    response = _http._http_get(
        f"{FRED_BASE}/series",
        params={"series_id": series_id, "api_key": key, "file_type": "json"},
    )
    data = _http._response_json(response)
    seriess = data.get("seriess") or []
    if not seriess:
        return {}
    raw = seriess[0]
    return {
        "title": raw.get("title"),
        "units": raw.get("units"),
        "frequency": raw.get("frequency"),
        "seasonal_adjustment": raw.get("seasonal_adjustment"),
        "observation_start": raw.get("observation_start"),
        "observation_end": raw.get("observation_end"),
        "last_updated": raw.get("last_updated"),
    }


def _observations(series_id: str, max_observations: int) -> list[dict]:
    key = _api_key()
    # NOTE: FRED applies `limit` to the sorted window, so sort_order="asc" with
    # a limit returns the OLDEST N observations (not the latest N). We ask for
    # desc to get the most recent window, then _normalize sorts back ascending.
    response = _http._http_get(
        f"{FRED_BASE}/series/observations",
        params={
            "series_id": series_id,
            "api_key": key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": int(max_observations),
        },
    )
    data = _http._response_json(response)
    observations = data.get("observations") or []
    if not isinstance(observations, list):
        return []
    return [o for o in observations if isinstance(o, dict)]


def _normalize(series_id: str, meta: dict, observations: list[dict], now) -> tuple[SourceRecord, ...]:
    records = []
    for obs in observations:
        value = obs.get("value")
        raw = str(value).strip()
        if raw.lower() in _MISSING:
            continue
        try:
            parsed = float(raw)
        except (TypeError, ValueError):
            continue
        date_str = str(obs.get("date") or "")
        published = None
        if date_str:
            try:
                published = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                pass
        records.append(SourceRecord(
            id=make_record_id("fred", series_id, date_str),
            provider="fred",
            entity=series_id,
            title=str(meta.get("title") or f"FRED series {series_id}"),
            retrieved_at=now,
            source_class=SourceClass.A,
            source_type=SourceType.OBSERVED,
            published_at=published,
            reference=(
                f"https://fred.stlouisfed.org/series/{series_id}"
                if date_str
                else None
            ),
            payload={
                "series_id": series_id,
                "date": date_str,
                "value": parsed,
                "raw_value": raw,
                "units": meta.get("units"),
                "frequency": meta.get("frequency"),
                "seasonal_adjustment": meta.get("seasonal_adjustment"),
                "observation_end": meta.get("observation_end"),
            },
        ))
    # FRED is queried newest-first (sort_order=desc&limit=N) so we always hold
    # the most recent N observations, never the oldest N. Normalize back to
    # ascending so records[-1] is genuinely the latest observation.
    records = list(dedupe_records(records))
    records.sort(key=lambda r: (r.published_at is None, r.published_at or datetime.min))
    return tuple(records)


def _fetch_live(series_id: str, max_observations: int):
    meta = _series_meta(series_id)
    observations = _observations(series_id, max_observations)
    now = utc_now()
    records = _normalize(series_id, meta, observations, now)
    return SourceResult(
        provider="fred",
        status="ok",
        records=records,
        retrieved_at=now,
        metadata={
            "title": meta.get("title"),
            "units": meta.get("units"),
            "frequency": meta.get("frequency"),
            "observation_start": meta.get("observation_start"),
            "observation_end": meta.get("observation_end"),
            "last_updated": meta.get("last_updated"),
        },
    ), records


def _record_from_cache(entry: dict) -> Optional[SourceResult]:
    """Decode a stored FRED cache entry; None when corrupt (never raises)."""
    return cached_result("fred", entry)


def fetch_fred_series(series_id: str, *, cache=None, max_observations: int = 100,
                      ttl_seconds: int = FRED_DEFAULT_TTL, force_refresh: bool = False,
                      now=None) -> SourceResult:
    """Fetch (or serve cached) observations for a FRED series.

    never re-raises provider errors: network/config/malformed failures degrade
    to an unavailable SourceResult, or a stale cache hit when one exists.
    """
    cache = cache or Cache()
    if not ttl_seconds:
        ttl_seconds = FRED_DEFAULT_TTL
    key = f"fred:{series_id}"

    cached = cache.load(key)
    decoded = _record_from_cache(cached) if cached is not None else None
    fresh = decoded is not None and cache.is_fresh(key, ttl_seconds, now=now)
    if fresh and not force_refresh:
        return decoded

    try:
        result, records = _fetch_live(series_id, max_observations)
    except ProviderConfigMissing as exc:
        if decoded is not None:
            return SourceResult(
                provider="fred",
                status="ok",
                records=decoded.records,
                retrieved_at=decoded.retrieved_at,
                is_stale=True,
                cache_hit=False,
                reason=f"stale cache served; {exc}",
                metadata=decoded.metadata,
            )
        return unavailable_result("fred", str(exc))
    except Exception as exc:
        if decoded is not None:
            return SourceResult(
                provider="fred",
                status="ok",
                records=decoded.records,
                retrieved_at=decoded.retrieved_at,
                is_stale=True,
                cache_hit=False,
                reason=f"stale cache served; live refresh failed ({type(exc).__name__})",
                metadata=decoded.metadata,
            )
        return unavailable_result("fred", f"refresh failed: {type(exc).__name__}: {exc}")

    cache.save(
        key,
        {
            "metadata": result.metadata,
            "records": [r.as_dict() for r in records],
        },
        provider="fred",
        retrieved_at=result.retrieved_at,
    )
    return result


def latest_fred_observation(series_id: str, **kwargs) -> SourceResult:
    """Latest single observation for a series (maps to fetch_fred_series)."""
    result = fetch_fred_series(series_id, max_observations=kwargs.pop("max_observations", 120), **kwargs)
    if result.status != "ok" or not result.records:
        return result
    return SourceResult(
        provider="fred",
        status="ok",
        records=(result.records[-1],),
        retrieved_at=result.retrieved_at,
        is_stale=result.is_stale,
        cache_hit=result.cache_hit,
        reason=result.reason,
        metadata=result.metadata,
    )