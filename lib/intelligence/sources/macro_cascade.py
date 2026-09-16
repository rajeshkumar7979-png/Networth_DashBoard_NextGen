# -------------------------------------------------
# Intelligence Data Gateway — macro FX / sovereign-yield cascade.
#
# get_macro_fx_snapshot() serves one deterministic snapshot of three macro
# inputs — the US 10-Year Treasury Yield (FRED DGS10), the India 10-Year
# government bond yield (FRED INDIRLTLT01STM, monthly; no validated Yahoo
# symbol exists, so it uses FRED or the stale cache only) and the USD/INR spot
# rate (FRED DEXINUS) — via a live -> fallback -> stale-cache cascade:
#
#   Plan A (FRED_API):               existing FRED adapter
#                                    (fetches fresh live, or a FRESH disk cache)
#   Plan B (YAHOO_FINANCE_FALLBACK): yfinance live quotes (^TNX / USDINR=X);
#                                    only for series with a validated ticker
#   Plan C (STALE_CACHE):            last successful fetch from the gateway
#                                    cache (cascade keys, then FRED keys)
#
# The India-vs-US 10Y carry spread is exposed as metadata["yield_spread"] — a
# pure calculation over the snapshot's observed records (India 10Y minus US
# 10Y, in pp and bps). It is never a fabricated number: absent either yield it
# is explicitly unavailable.
#
# Provider-neutral, never raises, and never invents data. Every failure
# degrades to an explicit unavailable SourceResult with a scrubbed reason.
# The plan that produced each record is stamped in payload["provenance"] and
# in metadata["plans"] so consumers can always tell the data's provenance.
#
# Page loads never hit the network: load_macro_snapshot() is a network-free
# cache-only read of the last persisted snapshot; the live cascade plans above
# run exclusively through get_macro_fx_snapshot() on an explicit refresh.
# --------------------------------------------------------------------------
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Optional

from lib.intelligence.model import SourceClass, SourceType

from . import httpio as _httpio
from .cache import Cache
from .errors import ProviderUnavailable
from .fred import latest_fred_observation
from .record import (
    SourceRecord,
    SourceResult,
    cached_result,
    make_record_id,
    unavailable_result,
    utc_now,
)

OBSERVED = SourceType.OBSERVED

PROVIDER = "macro_cascade"
# Same refresh horizon as the FRED adapter (twice a day).
CASCADE_CACHE_TTL = 12 * 3600

PROVENANCE_FRED = "FRED_API"
PROVENANCE_YAHOO = "YAHOO_FINANCE_FALLBACK"
PROVENANCE_CACHE = "STALE_CACHE"


def plan_badge(provenance: Optional[str], *, is_stale: bool) -> tuple[str, str]:
    """Command Center badge (label, tone) for one macro record.

    "Stale" is a statement about AGE versus the cascade TTL, never about
    provenance alone: a STALE_CACHE record is served from the last successful
    fetch (that is what every cache-only page load re-stamps), so it badges
    "Cache · fresh" until its cache actually passes the TTL. Provenance only
    selects the provider family; `is_stale` decides fresh vs stale.
    """
    if provenance == PROVENANCE_FRED:
        return "FRED · authoritative", "positive"
    if provenance == PROVENANCE_YAHOO:
        return "Yahoo · fallback", "warning"
    if provenance == PROVENANCE_CACHE:
        return ("Cache · stale", "warning") if is_stale else ("Cache · fresh", "positive")
    return str(provenance or "unknown"), "neutral"

# Canonical, source-neutral entity ids for the three series.
US_10Y = "DGS10"
USD_INR = "DEXINUS"
INDIA_10Y = "IN10Y"

# India 10-Year government benchmark yield: FRED has a monthly OECD series
# (INDIRLTLT01STM). No Yahoo Finance symbol for the India 10Y G-Sec could be
# validated (every candidate returned no data), so India has NO Plan B and
# relies on a FRED refresh or the stale cache — never a fabricated fallback.
INDIA_FRED_SERIES = "INDIRLTLT01STM"
INDIA_YAHOO_TICKER = ""


@dataclass(frozen=True)
class _MacroSeries:
    entity: str          # canonical, source-neutral series id
    fred_series: str     # FRED series id
    yahoo_ticker: str    # Yahoo Finance ticker
    title: str
    units: str


MACRO_SERIES: tuple[_MacroSeries, ...] = (
    _MacroSeries(US_10Y, "DGS10", "^TNX",
                 "US 10-Year Treasury Yield", "percent"),
    _MacroSeries(USD_INR, "DEXINUS", "USDINR=X",
                 "USD/INR Spot Rate", "INR per USD"),
    _MacroSeries(INDIA_10Y, INDIA_FRED_SERIES, INDIA_YAHOO_TICKER,
                 "India 10-Year Government Bond Yield", "percent"),
)


def _cache_key(entity: str) -> str:
    return f"{PROVIDER}:{entity}"


def _to_naive_utc(value: Optional[datetime]) -> datetime:
    """Gateway determinism: normalize aware timestamps (e.g. IST `now`) to
    naive UTC so cache freshness arithmetic never mixes aware and naive."""
    if value is None:
        return utc_now()
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _series_value(records, entity: str) -> Optional[float]:
    """Scalar value for one entity from a snapshot's records, or None."""
    for record in records or ():
        if record.entity != entity:
            continue
        value = (record.payload or {}).get("value")
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return float(value)
    return None


def _yield_spread(records) -> dict:
    """India 10Y minus US 10Y carry indicator (calculated, pp and bps).

    A pure calculation over this snapshot's observed records — never invented:
    without both yields the result is explicitly unavailable. Each contributing
    record keeps its own provenance stamp; the spread itself is a CALCULATED
    fact, decision-support only.
    """
    india = _series_value(records, INDIA_10Y)
    us = _series_value(records, US_10Y)
    if india is None or us is None:
        return {
            "available": False,
            "basis": "requires both India 10Y and US 10Y yields in the snapshot",
        }
    spread_pp = float(india) - float(us)
    return {
        "available": True,
        "india_yield": india,
        "us_yield": us,
        "spread_pp": spread_pp,
        "spread_bps": round(spread_pp * 100.0, 1),
        "basis": "India 10Y yield minus US 10Y yield (calculated from the "
                 "snapshot's observed records)",
    }


def _with_provenance(record: SourceRecord, plan: str) -> SourceRecord:
    """Copy a record, stamping the cascade plan that produced it."""
    return replace(record, payload={**(record.payload or {}), "provenance": plan})


def _pin_identity(record: SourceRecord, spec: _MacroSeries) -> SourceRecord:
    """Ensure a record carries the canonical macro entity/title regardless of
    which provider plan produced it (FRED adapter records keep the FRED series
    id, e.g. INDIRLTLT01STM, instead of the canonical IN10Y)."""
    if record.entity == spec.entity and record.title == spec.title:
        return record
    return replace(record, entity=spec.entity, title=spec.title)


def _fetch_yahoo_value(ticker: str) -> tuple[float, Optional[datetime]]:
    """Live quote via yfinance.fast_info, then a short history as a backup.

    Raises ProviderUnavailable on any failure; an absent or non-finite value is
    a failure — never a fabricated number.
    """
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - yfinance is a dependency
        raise ProviderUnavailable(
            f"yfinance unavailable: {type(exc).__name__}") from exc
    try:
        info = yf.Ticker(ticker).fast_info
        last_price = getattr(info, "last_price", None)
        if isinstance(last_price, (int, float)) and math.isfinite(float(last_price)):
            return float(last_price), None
        hist = yf.Ticker(ticker).history(period="5d")
        close = getattr(hist, "Close", None)
        if close is None or len(close) == 0:
            raise ProviderUnavailable(f"yahoo returned no series data for {ticker}")
        value = float(close.dropna().iloc[-1])
        if not math.isfinite(value):
            raise ProviderUnavailable(f"yahoo returned a non-finite value for {ticker}")
        return value, None
    except ProviderUnavailable:
        raise
    except Exception as exc:
        raise ProviderUnavailable(
            f"yahoo fetch failed for {ticker}: {type(exc).__name__}") from exc


def _build_yahoo_record(spec: _MacroSeries, value: float,
                        published: Optional[datetime], now: datetime) -> SourceRecord:
    return SourceRecord(
        id=make_record_id("yahoo", spec.fred_series, now.date().isoformat()),
        provider="yahoo",
        entity=spec.entity,
        title=spec.title,
        retrieved_at=now,
        source_class=SourceClass.C,
        source_type=OBSERVED,
        published_at=published,
        payload={
            "series_id": spec.fred_series,
            "ticker": spec.yahoo_ticker,
            "value": value,
            "units": spec.units,
            "provenance": PROVENANCE_YAHOO,
        },
    )


def _persist_yahoo(cache: Cache, spec: _MacroSeries, record: SourceRecord,
                   now: datetime) -> None:
    """Best-effort cascade cache write so a later Plan C can serve this data."""
    try:
        cache.save(
            _cache_key(spec.entity),
            {"metadata": {"series_id": spec.fred_series, "title": spec.title},
             "records": [record.as_dict()]},
            provider=PROVIDER,
            retrieved_at=now,
        )
    except Exception:
        pass  # a cache write failure must never fail the snapshot


def _read_cached(cache: Cache, spec: _MacroSeries, now: datetime):
    """Plan C: last successful fetch from the gateway cache.

    Cascade keys first (our own writes), then the FRED adapter's keys. A
    corrupted entry is skipped; the record is always re-stamped STALE_CACHE.
    """
    for key in (_cache_key(spec.entity), f"fred:{spec.fred_series}"):
        entry = cache.load(key)
        if entry is None:
            continue
        provider = PROVIDER if key.startswith(f"{PROVIDER}:") else "fred"
        result = cached_result(provider, entry)
        if result is None or result.status != "ok" or not result.records:
            continue
        record = _pin_identity(
            _with_provenance(result.records[-1], PROVENANCE_CACHE), spec)
        stale = not cache.is_fresh(key, CASCADE_CACHE_TTL, now=now)
        return record, stale
    return None


def _fred_latest(series_id: str, now=None) -> SourceResult:
    return latest_fred_observation(series_id, now=now)


def _snapshot_one(spec: _MacroSeries, *, now: datetime, cache: Cache,
                  fred_fetch, yahoo_fetch, failures: list) -> tuple[Optional[SourceRecord], bool]:
    """One series through Plan A -> Plan B -> Plan C. Returns (record, stale).

    Plan A only accepts FRESH observations; a stale-too cache from the FRED
    adapter does not pass for live data — the cascade keeps downgrading until
    it finds fresh data or exhausts every plan.
    """
    fred_result = None
    try:
        fred_result = fred_fetch(spec.fred_series, now=now)
    except Exception as exc:  # defensive: even a raw failure degrades cleanly
        failures.append((spec.entity, "fred", _httpio._sanitize_error(
            f"{type(exc).__name__}: {exc}")))
    if (fred_result is not None and fred_result.status == "ok"
            and fred_result.records and not fred_result.is_stale):
        record = _pin_identity(
            _with_provenance(fred_result.records[-1], PROVENANCE_FRED), spec)
        return record, False
    if fred_result is not None and fred_result.records:
        failures.append((spec.entity, "fred",
                         "live refresh failed; only stale FRED cache available"))
    elif fred_result is not None:
        failures.append((spec.entity, "fred", _httpio._sanitize_error(
            fred_result.reason or "unavailable")))

    if not spec.yahoo_ticker:
        failures.append((spec.entity, "yahoo",
                         "no Yahoo fallback available for this series"))
    else:
        try:
            value, published = yahoo_fetch(spec.yahoo_ticker)
        except Exception as exc:
            failures.append((spec.entity, "yahoo", _httpio._sanitize_error(
                f"{type(exc).__name__}: {exc}")))
        else:
            record = _pin_identity(_build_yahoo_record(spec, value, published, now), spec)
            _persist_yahoo(cache, spec, record, now)
            return record, False

    cached = _read_cached(cache, spec, now)
    if cached is not None:
        return cached
    return None, False


def get_macro_fx_snapshot(*, now=None, cache=None, fred_fetch=None,
                          yahoo_fetch=None) -> SourceResult:
    """Deterministic snapshot of the US 10Y yield + India 10Y yield +
    USD/INR spot rate.

    Cascade per series: FRED (fresh) -> Yahoo live -> gateway disk cache. The
    returned SourceResult carries one SourceRecord per series; each record's
    payload["provenance"] is one of FRED_API / YAHOO_FINANCE_FALLBACK /
    STALE_CACHE, also summarized in metadata["plans"]. metadata["yield_spread"]
    holds the calculated India 10Y minus US 10Y carry spread (or an explicit
    "available: false" when either yield is absent). When every plan fails
    for every series the result is an unavailable SourceResult with a scrubbed
    reason — never invented data.
    """
    now = _to_naive_utc(now or utc_now())
    cache = cache or Cache()
    fred_fetch = fred_fetch or _fred_latest
    yahoo_fetch = yahoo_fetch or _fetch_yahoo_value

    records: list[SourceRecord] = []
    stale_flags: list[bool] = []
    failures: list[tuple[str, str, str]] = []
    plans: dict[str, str] = {}

    for spec in MACRO_SERIES:
        record, stale = _snapshot_one(
            spec, now=now, cache=cache, fred_fetch=fred_fetch,
            yahoo_fetch=yahoo_fetch, failures=failures)
        if record is None:
            plans[spec.entity] = "unavailable"
            continue
        records.append(record)
        stale_flags.append(stale)
        plans[spec.entity] = (record.payload or {}).get("provenance", "unknown")

    if not records:
        reason = _httpio._sanitize_error(
            "all macro providers failed (" + "; ".join(
                f"{entity}[{provider}] {why}" for entity, provider, why in failures)
            + ")" if failures else "all macro providers failed")
        return unavailable_result(
            PROVIDER, reason, plans=plans, cascade="fred -> yahoo -> cache")

    return SourceResult(
        provider=PROVIDER,
        status="ok",
        records=tuple(records),
        retrieved_at=now,
        is_stale=any(stale_flags),
        metadata={
            "cascade": "fred -> yahoo -> cache",
            "plans": plans,
            "failures": [{"entity": entity, "provider": provider, "reason": reason}
                         for entity, provider, reason in failures],
            "yield_spread": _yield_spread(records),
        },
    )


def load_macro_snapshot(*, now=None, cache=None) -> SourceResult:
    """Network-free read of the last persisted macro snapshot.

    Mirrors the live-research split: deriving the plan and reading caches is
    safe on every page load; the live plans (FRED/Yahoo) run ONLY through
    get_macro_fx_snapshot() on an explicit refresh. Returns one SourceRecord
    per series read from the cascade cache (then FRED keys), each re-stamped
    STALE_CACHE with a stale flag per the cascade TTL. Absent or corrupt
    caches degrade to an unavailable result — never invented data.
    """
    now = _to_naive_utc(now)
    cache = cache or Cache()

    records: list[SourceRecord] = []
    plans: dict[str, str] = {}
    stale_seen = False
    for spec in MACRO_SERIES:
        cached = _read_cached(cache, spec, now)
        if cached is None:
            plans[spec.entity] = "unavailable"
            continue
        record, stale = cached
        records.append(record)
        plans[spec.entity] = (record.payload or {}).get("provenance", PROVENANCE_CACHE)
        stale_seen = stale_seen or stale

    if not records:
        return unavailable_result(
            PROVIDER,
            "no cached macro indicators (cascade fetch happens only on an "
            "explicit refresh)",
            plans=plans,
            cascade="cache-only read (no network)",
        )
    return SourceResult(
        provider=PROVIDER,
        status="ok",
        records=tuple(records),
        retrieved_at=now,
        is_stale=stale_seen,
        metadata={
            "readonly": True,
            "cascade": "cache-only read (no network)",
            "plans": plans,
            "yield_spread": _yield_spread(records),
        },
    )