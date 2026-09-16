# -------------------------------------------------
# macro_cascade — offline fallback-cascade regression suite.
#
# Freezes the Plan A -> Plan B -> Plan C behavior of
# get_macro_fx_snapshot(): FRED first, Yahoo fallback, stale-cache last,
# explicit unavailable (with scrubbed reasons) otherwise. No network and no
# real credentials: every provider seam is injected, and yfinance is never
# imported by these tests.
# -------------------------------------------------
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lib.intelligence.model import SourceClass, SourceType
from lib.intelligence.sources.cache import Cache
from lib.intelligence.sources.errors import ProviderUnavailable
from lib.intelligence.sources.macro_cascade import (
    INDIA_FRED_SERIES,
    INDIA_10Y,
    PROVENANCE_CACHE,
    PROVENANCE_FRED,
    PROVENANCE_YAHOO,
    US_10Y,
    USD_INR,
    get_macro_fx_snapshot,
    load_macro_snapshot,
    plan_badge,
)
from lib.intelligence.sources.record import (
    SourceRecord,
    SourceResult,
    make_record_id,
)

NOW = datetime(2026, 9, 14, 10, 0, 0)
OLD = datetime(2026, 9, 13, 20, 0, 0)  # 14h before NOW -> stale vs the 12h TTL


def _fred_record(series_id, value, *, now=NOW):
    return SourceRecord(
        id=make_record_id("fred", series_id, now.date().isoformat()),
        provider="fred",
        entity=series_id,
        title=f"FRED series {series_id}",
        retrieved_at=now,
        source_class=SourceClass.A,
        source_type=SourceType.OBSERVED,
        published_at=datetime(now.year, now.month, now.day),
        payload={"series_id": series_id, "value": value,
                 "raw_value": str(value), "units": "percent"},
    )


def _fred_ok(values):
    def fetch(series_id, now=None):
        if series_id not in values:
            raise ProviderUnavailable(f"unknown fred series {series_id}")
        return SourceResult(
            provider="fred", status="ok",
            records=(_fred_record(series_id, values[series_id], now=now or NOW),),
            retrieved_at=now or NOW,
        )
    return fetch


def _fred_boom():
    def fetch(series_id, now=None):
        raise ProviderUnavailable(
            "provider unreachable for https://api.stlouisfed.org/fred/series/"
            "observations?api_key=SECRET-QUERY-KEY&series_id=DGS10")
    return fetch


def _yahoo_ok(values_by_ticker):
    def fetch(ticker):
        if ticker not in values_by_ticker:
            raise AssertionError(f"unexpected yahoo ticker: {ticker}")
        return float(values_by_ticker[ticker]), None
    return fetch


def _yahoo_boom():
    def fetch(ticker):
        raise ProviderUnavailable(f"yahoo fetch failed for {ticker}: ConnectionError")
    return fetch


# Three series: US 10Y (FRED DGS10), USD/INR (FRED DEXINUS), India 10Y (FRED
# INDIRLTLT01STM). Yahoo only serves the first two — no valid India 10Y symbol
# exists, so India has no Plan B.
_FRED_DICT = {"DGS10": 4.21, "DEXINUS": 84.55, INDIA_FRED_SERIES: 6.94}
_YAHOO_DICT = {"^TNX": 4.18, "USDINR=X": 84.5}


def test_fred_plan_a_success_never_calls_yahoo(tmp_path):
    def yahoo_must_not_run(ticker):
        raise AssertionError("yahoo fallback must not run when FRED is fresh")

    result = get_macro_fx_snapshot(
        now=NOW,
        fred_fetch=_fred_ok(dict(_FRED_DICT)),
        yahoo_fetch=yahoo_must_not_run,
        cache=Cache(base_dir=tmp_path),
    )
    assert result.status == "ok"
    assert result.is_stale is False
    assert len(result.records) == 3
    by_entity = {r.entity: r for r in result.records}
    assert by_entity[US_10Y].payload["value"] == 4.21
    assert by_entity[US_10Y].payload["provenance"] == PROVENANCE_FRED
    assert by_entity[USD_INR].payload["value"] == 84.55
    assert by_entity[USD_INR].payload["provenance"] == PROVENANCE_FRED
    assert by_entity[INDIA_10Y].payload["value"] == 6.94
    assert by_entity[INDIA_10Y].payload["provenance"] == PROVENANCE_FRED
    assert all(r.provider == "fred" for r in result.records)
    assert result.metadata["plans"] == {
        US_10Y: "FRED_API", USD_INR: "FRED_API", INDIA_10Y: "FRED_API"}


def test_yahoo_fallback_when_fred_fails(tmp_path):
    """FRED unavailable -> yfinance fallback for the two series that have a
    validated ticker; India (no Yahoo symbol) degrades to unavailable rather
    than a fabricated record."""
    result = get_macro_fx_snapshot(
        now=NOW,
        fred_fetch=_fred_boom(),
        yahoo_fetch=_yahoo_ok(dict(_YAHOO_DICT)),
        cache=Cache(base_dir=tmp_path),
    )
    assert result.status == "ok"
    assert result.is_stale is False
    assert len(result.records) == 2
    by_entity = {r.entity: r for r in result.records}
    assert by_entity[US_10Y].payload["value"] == 4.18
    assert by_entity[USD_INR].payload["value"] == 84.5
    for record in result.records:
        assert record.provider == "yahoo"
        assert record.payload["provenance"] == "YAHOO_FINANCE_FALLBACK"
    assert by_entity[US_10Y].payload["ticker"] == "^TNX"
    assert by_entity[USD_INR].payload["ticker"] == "USDINR=X"
    assert INDIA_10Y not in by_entity
    assert result.metadata["plans"] == {
        US_10Y: "YAHOO_FINANCE_FALLBACK", USD_INR: "YAHOO_FINANCE_FALLBACK",
        INDIA_10Y: "unavailable"}


def test_defensive_fred_value_error_still_cascades(tmp_path):
    def fd_boom(series_id, now=None):
        raise ValueError("unexpected non-gateway error")

    result = get_macro_fx_snapshot(
        now=NOW,
        fred_fetch=fd_boom,
        yahoo_fetch=_yahoo_ok(dict(_YAHOO_DICT)),
        cache=Cache(base_dir=tmp_path),
    )
    assert result.status == "ok"
    assert all(r.payload["provenance"] == PROVENANCE_YAHOO for r in result.records)
    assert any("ValueError" in f["reason"] for f in result.metadata["failures"])


def test_india_10y_fred_fetch(tmp_path):
    """The India 10-Year G-Sec yield is served from its real FRED series
    (INDIRLTLT01STM) with canonical entity, value and title — critical for the
    FD vs FCNR carry decision."""
    result = get_macro_fx_snapshot(
        now=NOW,
        fred_fetch=_fred_ok(dict(_FRED_DICT)),
        yahoo_fetch=_yahoo_ok(dict(_YAHOO_DICT)),
        cache=Cache(base_dir=tmp_path),
    )
    india = next(r for r in result.records if r.entity == INDIA_10Y)
    assert INDIA_FRED_SERIES == "INDIRLTLT01STM"
    assert india.provider == "fred"
    assert india.payload["series_id"] == INDIA_FRED_SERIES
    assert india.payload["value"] == 6.94
    assert india.payload["provenance"] == PROVENANCE_FRED
    assert india.title == "India 10-Year Government Bond Yield"


def test_india_10y_has_no_yahoo_fallback(tmp_path):
    """No validated Yahoo symbol exists for India 10Y: the cascade must never
    call the Yahoo seam for it (and must not fabricate a record)."""
    india_tickers_seen = []

    def yahoo_spy(ticker):
        india_tickers_seen.append(ticker)
        if ticker not in _YAHOO_DICT:
            raise AssertionError(f"unexpected yahoo ticker: {ticker}")
        return float(_YAHOO_DICT[ticker]), None

    result = get_macro_fx_snapshot(
        now=NOW,
        fred_fetch=_fred_boom(),
        yahoo_fetch=yahoo_spy,
        cache=Cache(base_dir=tmp_path),
    )
    # India resolved to unavailable without ever touching the Yahoo seam.
    assert result.metadata["plans"][INDIA_10Y] == "unavailable"
    assert all(r.entity != INDIA_10Y for r in result.records)
    assert "^INF10YR=IND" not in india_tickers_seen


def test_yield_spread_calculation_in_metadata(tmp_path):
    """India 10Y minus US 10Y carry spread, computed from the snapshot's
    observed records (India yield only): 6.94 - 4.21 = 2.73 pp = 273 bps."""
    result = get_macro_fx_snapshot(
        now=NOW,
        fred_fetch=_fred_ok(dict(_FRED_DICT)),
        yahoo_fetch=_yahoo_boom(),
        cache=Cache(base_dir=tmp_path),
    )
    spread = result.metadata["yield_spread"]
    assert spread["available"] is True
    assert spread["india_yield"] == 6.94
    assert spread["us_yield"] == 4.21
    assert abs(spread["spread_pp"] - 2.73) < 1e-9
    assert spread["spread_bps"] == 273.0
    assert result.records[0].payload["provenance"] == PROVENANCE_FRED


def test_yield_spread_unavailable_when_india_yield_missing(tmp_path):
    """No India yield -> the spread is explicitly unavailable, never zero
    or invented (critical whenever only ONE series is missing)."""
    cache = Cache(base_dir=tmp_path)
    for series_id, value in (("DGS10", 4.05), ("DEXINUS", 85.1)):
        record = _fred_record(series_id, value, now=OLD)
        cache.save(
            f"fred:{series_id}",
            {"metadata": {}, "records": [record.as_dict()]},
            provider="fred", retrieved_at=OLD,
        )
    result = get_macro_fx_snapshot(
        now=NOW, fred_fetch=_fred_boom(), yahoo_fetch=_yahoo_boom(),
        cache=cache,
    )
    spread = result.metadata["yield_spread"]
    assert spread["available"] is False
    assert "India" in spread["basis"]
    assert "spread_pp" not in spread


def test_stale_cache_fallback_when_fred_and_yahoo_fail(tmp_path):
    cache = Cache(base_dir=tmp_path)
    for series_id, value in (("DGS10", 4.05), ("DEXINUS", 85.1),
                             (INDIA_FRED_SERIES, 6.9)):
        record = _fred_record(series_id, value, now=OLD)
        cache.save(
            f"fred:{series_id}",
            {"metadata": {}, "records": [record.as_dict()]},
            provider="fred", retrieved_at=OLD,
        )

    result = get_macro_fx_snapshot(
        now=NOW,
        fred_fetch=_fred_boom(),
        yahoo_fetch=_yahoo_boom(),
        cache=cache,
    )
    assert result.status == "ok"
    assert result.is_stale is True
    assert len(result.records) == 3
    by_entity = {r.entity: r for r in result.records}
    for entity in (US_10Y, USD_INR, INDIA_10Y):
        assert by_entity[entity].payload["provenance"] == PROVENANCE_CACHE
    # Exact seeded values survive the cascade — nothing is invented.
    assert by_entity[US_10Y].payload["value"] == 4.05
    assert by_entity[USD_INR].payload["value"] == 85.1
    assert by_entity[INDIA_10Y].payload["value"] == 6.9


def test_all_plans_fail_returns_scrubbed_unavailable(tmp_path):
    result = get_macro_fx_snapshot(
        now=NOW,
        fred_fetch=_fred_boom(),
        yahoo_fetch=_yahoo_boom(),
        cache=Cache(base_dir=tmp_path),
    )
    assert result.status == "unavailable"
    assert result.records == ()
    assert result.reason
    # The FRED failure reason embeds a query-string API key; it must stay scrubbed.
    assert "SECRET-QUERY-KEY" not in result.reason
    assert "api_key=" not in result.reason
    assert "yahoo" in result.reason.lower()
    assert result.metadata["plans"] == {
        US_10Y: "unavailable", USD_INR: "unavailable", INDIA_10Y: "unavailable"}


def test_yahoo_results_persisted_for_future_cache_fallback(tmp_path):
    cache = Cache(base_dir=tmp_path)
    result = get_macro_fx_snapshot(
        now=NOW,
        fred_fetch=_fred_boom(),
        yahoo_fetch=_yahoo_ok(dict(_YAHOO_DICT)),
        cache=cache,
    )
    assert result.status == "ok"
    assert cache.load("macro_cascade:DGS10") is not None
    assert cache.load("macro_cascade:DEXINUS") is not None
    # India has no Yahoo path, so nothing is persisted for it here.
    assert cache.load(f"macro_cascade:{INDIA_10Y}") is None


def test_load_macro_snapshot_reads_cache_network_free(tmp_path):
    """load_macro_snapshot is a cache-only read: it takes no fetch seams, so it
    can never touch the network; it re-stamps STALE_CACHE and preserves the
    exact persisted values."""
    cache = Cache(base_dir=tmp_path)
    for series_id, value in (("DGS10", 4.05), ("DEXINUS", 85.1),
                             (INDIA_FRED_SERIES, 6.9)):
        record = _fred_record(series_id, value, now=OLD)
        cache.save(
            f"fred:{series_id}",
            {"metadata": {}, "records": [record.as_dict()]},
            provider="fred", retrieved_at=OLD,
        )

    result = load_macro_snapshot(now=NOW, cache=cache)
    assert result.status == "ok"
    assert result.metadata["readonly"] is True
    assert result.metadata["cascade"] == "cache-only read (no network)"
    assert result.is_stale is True  # OLD is 14h before NOW -> past the 12h TTL
    assert len(result.records) == 3
    by_entity = {r.entity: r for r in result.records}
    assert by_entity[US_10Y].payload["provenance"] == PROVENANCE_CACHE
    assert by_entity[US_10Y].payload["value"] == 4.05
    assert by_entity[USD_INR].payload["value"] == 85.1
    assert by_entity[INDIA_10Y].payload["value"] == 6.9
    assert result.metadata["plans"] == {
        US_10Y: "STALE_CACHE", USD_INR: "STALE_CACHE", INDIA_10Y: "STALE_CACHE"}
    assert all(r.retrieved_at == OLD for r in result.records)


def test_load_macro_snapshot_empty_degrades_to_unavailable(tmp_path):
    result = load_macro_snapshot(now=NOW, cache=Cache(base_dir=tmp_path))
    assert result.status == "unavailable"
    assert result.records == ()
    assert result.reason
    assert result.metadata["plans"] == {
        US_10Y: "unavailable", USD_INR: "unavailable", INDIA_10Y: "unavailable"}


def test_aware_now_is_normalized_before_cache_freshness(tmp_path):
    """CC passes IST-aware `now`; freshness math must not crash on mixing aware
    and naive datetimes before the cascade degrades to cache."""
    cache = Cache(base_dir=tmp_path)
    for series_id, value in (("DGS10", 4.05), ("DEXINUS", 85.1),
                             (INDIA_FRED_SERIES, 6.9)):
        record = _fred_record(series_id, value, now=NOW)
        cache.save(
            f"fred:{series_id}",
            {"metadata": {}, "records": [record.as_dict()]},
            provider="fred", retrieved_at=NOW,
        )
    # 16:30 IST == 11:00 UTC, i.e. 1h after the seeded 10:00 UTC cache write
    # (age 1h < 12h TTL). Without naive-UTC normalization mixing aware IST with
    # the naive cache timestamp would crash inside cache.is_fresh.
    aware_now = datetime(2026, 9, 14, 16, 30,
                         tzinfo=timezone(timedelta(hours=5, minutes=30)))

    result = get_macro_fx_snapshot(
        now=aware_now, fred_fetch=_fred_boom(), yahoo_fetch=_yahoo_boom(),
        cache=cache)
    assert result.status == "ok"
    assert result.is_stale is False
    assert all(r.payload["provenance"] == PROVENANCE_CACHE for r in result.records)


def test_plan_badge_staleness_is_age_not_provenance():
    """The Command Center badges STALE_CACHE records by AGE vs the 12h TTL, not
    by provenance: a cache-only page load always re-stamps STALE_CACHE, so a
    recent cache must badge "fresh", never "stale"."""
    assert plan_badge(PROVENANCE_CACHE, is_stale=False) == ("Cache · fresh", "positive")
    assert plan_badge(PROVENANCE_CACHE, is_stale=True) == ("Cache · stale", "warning")
    assert plan_badge(PROVENANCE_FRED, is_stale=False) == ("FRED · authoritative", "positive")
    assert plan_badge(PROVENANCE_FRED, is_stale=True) == ("FRED · authoritative", "positive")
    assert plan_badge(PROVENANCE_YAHOO, is_stale=False) == ("Yahoo · fallback", "warning")
    assert plan_badge(PROVENANCE_YAHOO, is_stale=True) == ("Yahoo · fallback", "warning")
    assert plan_badge(None, is_stale=False) == ("unknown", "neutral")


def test_load_macro_snapshot_recent_cache_badges_fresh(tmp_path):
    """The exact reported scenario: a cache written 1 minute before NOW (well
    under the 12-hour TTL) reads back is_stale=False and must badge
    "Cache · fresh" — never the misleading "Cache · stale"."""
    cache = Cache(base_dir=tmp_path)
    recent = NOW - timedelta(minutes=1)  # 08:13 -> 08:14 IST analogue
    for series_id, value in (("DGS10", 4.05), ("DEXINUS", 85.1),
                             (INDIA_FRED_SERIES, 6.9)):
        record = _fred_record(series_id, value, now=recent)
        cache.save(
            f"fred:{series_id}",
            {"metadata": {}, "records": [record.as_dict()]},
            provider="fred", retrieved_at=recent,
        )

    result = load_macro_snapshot(now=NOW, cache=cache)
    assert result.status == "ok"
    assert result.is_stale is False
    assert result.metadata["plans"] == {
        US_10Y: PROVENANCE_CACHE, USD_INR: PROVENANCE_CACHE, INDIA_10Y: PROVENANCE_CACHE}
    for record in result.records:
        assert record.payload["provenance"] == PROVENANCE_CACHE
        assert plan_badge(record.payload["provenance"],
                          is_stale=result.is_stale) == ("Cache · fresh", "positive")