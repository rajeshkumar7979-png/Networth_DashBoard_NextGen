# -------------------------------------------------
# Intelligence Data Gateway v1 — offline regression suite.
#
# No network here: FRED/SEC go through the httpio._http_get seam, which these
# tests monkeypatch with canned provider responses. MF adapters are cache-read-
# only and get temp files. Freezes normalization, provenance, freshness,
# failure semantics, entity mapping and the no-fabricated-data rules.
# -------------------------------------------------
from __future__ import annotations

import json

import pytest
import requests

from lib.ledger import net_worth
from lib.intelligence.model import FactKind, SourceClass, SourceType
from lib.intelligence.sources import (
    assess_relevance,
    build_portfolio_index,
    fetch_fred_series,
    fetch_sec_company_facts,
    fetch_sec_submissions,
    gateway_status,
    latest_fred_observation,
    load_mf_holdings_evidence,
    load_mf_nav_evidence,
)
from lib.intelligence.sources import httpio
from lib.intelligence.sources.cache import Cache
from lib.intelligence.sources.errors import ProviderMalformed, ProviderTimeout, ProviderUnavailable
from lib.intelligence.sources.record import (
    SourceRecord,
    cached_result,
    dedupe_records,
    parse_iso,
    utc_now,
)
from lib.intelligence.sources.sec import SEC_DEFAULT_UA, _headers


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        if isinstance(self._data, BaseException):
            raise self._data
        return self._data


def fake_get(routes):
    """Build a httpio._http_get replacement served from a URL->payload map."""
    def _fake(url, params=None, headers=None, timeout=None):
        try:
            return FakeResponse(routes[url])
        except KeyError:
            raise ProviderUnavailable(f"unexpected URL {url}")
    return _fake


FRED_META = {
    "seriess": [{
        "id": "DFF", "title": "Federal Funds Effective Rate",
        "units": "Percent", "frequency": "Daily",
        "seasonal_adjustment": "Not Seasonally Adjusted",
        "observation_start": "1954-07-01", "observation_end": "2026-09-08",
        "last_updated": "2026-09-09T00:00:00+00:00",
    }]
}
FRED_OBS = {
    "realtime_start": "2026-09-09", "realtime_end": "2026-09-09",
    "observation_start": "1954-07-01", "observation_end": "2026-09-08",
    "observations": [
        {"realtime_start": "2026-09-09", "realtime_end": "2026-09-09",
         "date": "2026-09-05", "value": "4.83"},
        {"realtime_start": "2026-09-09", "realtime_end": "2026-09-09",
         "date": "2026-09-06", "value": "."},
        {"realtime_start": "2026-09-09", "realtime_end": "2026-09-09",
         "date": "2026-09-07", "value": "0.00"},
        {"realtime_start": "2026-09-09", "realtime_end": "2026-09-09",
         "date": "2026-09-08", "value": "4.79"},
    ],
}


def _fred_routes():
    return {
        "https://api.stlouisfed.org/fred/series": FRED_META,
        "https://api.stlouisfed.org/fred/series/observations": FRED_OBS,
    }


SEC_SUBMISSIONS = {
    "cik": 320193, "name": "Apple Inc.",
    "filings": {"recent": {
        "accessionNumber": ["000032019326000020"],
        "filingDate": ["2026-07-31"],
        "reportDate": ["2026-07-01"],
        "form": ["10-Q"],
        "primaryDocument": ["aapl-20260731.htm"],
    }},
}
SEC_FACTS = {
    "cik": 320193, "entityName": "Apple Inc.", "sic": "3571",
    "sicDescription": "ELECTRONIC COMPUTERS", "exchange": "NASDAQ",
    "ticker": "AAPL",
    "facts": {
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": []}}},
        "us-gaap": {"Assets": {"units": {"USD": []}}},
    },
}
SEC_URLS = {
    "https://data.sec.gov/submissions/CIK0000320193.json": SEC_SUBMISSIONS,
    "https://data.sec.gov/companyfacts/CIK0000320193.json": SEC_FACTS,
}


@pytest.fixture()
def fred_env(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    yield


@pytest.fixture()
def cache_dir(tmp_path):
    return Cache(base_dir=tmp_path / "gateway_cache")


# ------------------------------------------------- record layer
def test_record_roundtrip_is_json_safe():
    rec = SourceRecord(
        id="fred:dff:2026_09_08", provider="fred", entity="DFF",
        title="Federal Funds Effective Rate", retrieved_at=utc_now(),
        source_class=SourceClass.A, source_type=SourceType.OBSERVED,
        published_at=parse_iso("2026-09-08"),
        reference="https://fred.stlouisfed.org/series/DFF",
        payload={"value": 4.79, "date": "2026-09-08"},
    )
    as_dict = rec.as_dict()
    json.dumps(as_dict)
    back = SourceRecord.from_dict(as_dict)
    assert back.id == rec.id and back.entity == rec.entity
    assert back.published_at == rec.published_at
    assert back.source_class == SourceClass.A and back.source_type == SourceType.OBSERVED


def test_record_to_evidence_is_observed_fact():
    rec = SourceRecord(
        id="fred:dff:2026_09_08", provider="fred", entity="DFF",
        title="Federal Funds Effective Rate", retrieved_at=parse_iso("2026-09-08T10:00:00"),
        source_class=SourceClass.B, source_type=SourceType.OBSERVED,
        payload={"value": 5.0},
    )
    evidence = rec.to_evidence()
    assert evidence.provenance.fact_kind == FactKind.FACT
    assert evidence.provenance.source_type == SourceType.OBSERVED
    assert evidence.provenance.source == "fred"
    assert evidence.payload["value"] == 5.0
    assert evidence.provenance.retrieved_at == rec.retrieved_at
    assert isinstance(json.dumps(evidence.payload), str)


def test_record_id_deterministic_and_unique():
    from lib.intelligence.sources.record import make_record_id
    assert make_record_id("fred", "DFF", "2026-09-08") == make_record_id("fred", "DFF", "2026-09-08")
    assert make_record_id("fred", "DFF", "2026-09-08") != make_record_id("fred", "DFF", "2026-09-09")


def test_dedupe_records_collapses_duplicate_ids():
    now = utc_now()
    rec = SourceRecord(
        id="x:1", provider="p", entity="e", title="t", retrieved_at=now,
        source_class=SourceClass.D, source_type=SourceType.OBSERVED,
    )
    assert len(dedupe_records([rec, rec])) == 1


# ------------------------------------------------- httpio seam
def test_http_timeout_maps_to_timeout(monkeypatch):
    def _boom(*a, **k):
        raise requests.exceptions.Timeout("slow")
    monkeypatch.setattr(httpio.requests, "get", _boom)
    with pytest.raises(ProviderTimeout):
        httpio._http_get("https://example.test/x")


def test_http_status_maps_to_unavailable(monkeypatch):
    class R:
        status_code = 500
        def json(self):
            return {}
    monkeypatch.setattr(httpio.requests, "get", lambda *a, **k: R())
    with pytest.raises(ProviderUnavailable):
        httpio._http_get("https://example.test/x")


def test_http_connection_error_maps_to_unavailable(monkeypatch):
    def _conn(*a, **k):
        raise requests.exceptions.ConnectionError("connection refused")
    monkeypatch.setattr(httpio.requests, "get", _conn)
    with pytest.raises(ProviderUnavailable):
        httpio._http_get("https://example.test/x")


def test_http_error_message_does_not_leak_query_params(monkeypatch):
    def _conn(url, *a, **k):
        raise requests.exceptions.ConnectionError(f"boom {url}?api_key=TOP-SECRET-VALUE")
    monkeypatch.setattr(httpio.requests, "get", _conn)
    with pytest.raises(ProviderUnavailable) as exc_info:
        httpio._http_get("https://api.example.test/x", params={"api_key": "TOP-SECRET-VALUE"})
    assert "TOP-SECRET-VALUE" not in str(exc_info.value)
    assert "api.example.test" in str(exc_info.value)


def test_response_json_malformed_maps_to_malformed():
    with pytest.raises(ProviderMalformed):
        httpio._response_json(FakeResponse(ValueError("bad json")))
    with pytest.raises(ProviderMalformed):
        httpio._response_json(FakeResponse([1, 2]))


# ------------------------------------------------- FRED
def test_fred_normalizes_observations(monkeypatch, fred_env, cache_dir):
    monkeypatch.setattr(httpio, "_http_get", fake_get(_fred_routes()))
    result = fetch_fred_series("DFF", cache=cache_dir)
    assert result.status == "ok" and result.cache_hit is False
    assert len(result.records) == 3          # the "." missing point is skipped
    assert [r.payload["value"] for r in result.records] == [4.83, 0.00, 4.79]
    assert any(r.payload["value"] == 0.0 for r in result.records)  # real zero kept
    assert all(r.source_class == SourceClass.A for r in result.records)
    assert all(r.source_type == SourceType.OBSERVED for r in result.records)
    first = result.records[0]
    assert first.entity == "DFF" and first.published_at is not None
    assert result.metadata.get("title") == "Federal Funds Effective Rate"


def test_fred_no_computed_deltas(monkeypatch, fred_env, cache_dir):
    monkeypatch.setattr(httpio, "_http_get", fake_get(_fred_routes()))
    result = fetch_fred_series("DFF", cache=cache_dir)
    raw = json.dumps([r.to_evidence().payload for r in result.records]).lower()
    assert "pct_change" not in raw
    assert "delta" not in raw
    assert "return" not in raw


def test_fred_missing_key_unavailable_without_network(monkeypatch, cache_dir):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    calls = []
    def _never(url, params=None, headers=None, timeout=None):
        calls.append(url)
        return FakeResponse({})
    monkeypatch.setattr(httpio, "_http_get", _never)
    result = fetch_fred_series("DFF", cache=cache_dir)
    assert result.status == "unavailable" and result.records == ()
    assert calls == []


def test_fred_fresh_cache_served_without_network(monkeypatch, fred_env, cache_dir):
    monkeypatch.setattr(httpio, "_http_get", fake_get(_fred_routes()))
    first = fetch_fred_series("DFF", cache=cache_dir)
    assert first.cache_hit is False
    calls = []
    def _boom(url, params=None, headers=None, timeout=None):
        calls.append(url)
        raise ProviderUnavailable("network down")
    monkeypatch.setattr(httpio, "_http_get", _boom)
    second = fetch_fred_series("DFF", cache=cache_dir)
    assert second.cache_hit is True and second.status == "ok"
    assert len(second.records) == 3 and calls == []


def test_fred_stale_cache_served_when_refresh_fails(monkeypatch, fred_env, cache_dir):
    monkeypatch.setattr(httpio, "_http_get", fake_get(_fred_routes()))
    fetch_fred_series("DFF", cache=cache_dir)
    def _boom(url, params=None, headers=None, timeout=None):
        raise ProviderUnavailable("network down")
    monkeypatch.setattr(httpio, "_http_get", _boom)
    stale = fetch_fred_series("DFF", cache=cache_dir, force_refresh=True)
    assert stale.status == "ok"
    assert stale.is_stale is True and stale.cache_hit is False
    assert len(stale.records) == 3
    assert "stale" in (stale.reason or "")


def test_fred_no_cache_and_failure_is_unavailable(monkeypatch, fred_env, cache_dir):
    def _boom(url, params=None, headers=None, timeout=None):
        raise ProviderUnavailable("network down")
    monkeypatch.setattr(httpio, "_http_get", _boom)
    result = fetch_fred_series("DFF", cache=cache_dir, force_refresh=True)
    assert result.status == "unavailable" and result.records == ()


def test_fred_malformed_body_is_unavailable(monkeypatch, fred_env, cache_dir):
    def _malformed(url, params=None, headers=None, timeout=None):
        return FakeResponse(ValueError("broken"))
    monkeypatch.setattr(httpio, "_http_get", _malformed)
    result = fetch_fred_series("DFF", cache=cache_dir)
    assert result.status == "unavailable" and result.records == ()


def test_fred_cache_never_stores_credentials(monkeypatch, fred_env, cache_dir):
    monkeypatch.setattr(httpio, "_http_get", fake_get(_fred_routes()))
    fetch_fred_series("DFF", cache=cache_dir)
    path = cache_dir._path("fred:DFF")
    text = path.read_text(encoding="utf-8")
    assert "test-key" not in text and "api_key" not in text


def test_fred_latest_observation_tail(monkeypatch, fred_env, cache_dir):
    monkeypatch.setattr(httpio, "_http_get", fake_get(_fred_routes()))
    result = latest_fred_observation("DFF", cache=cache_dir)
    assert len(result.records) == 1 and result.records[0].payload["value"] == 4.79


def test_record_from_dict_tolerant_of_weird_payload(fred_env):
    rec = SourceRecord.from_dict({
        "id": 123,
        "source_class": "Z",
        "source_type": None,
        "retrieved_at": "not-a-date",
        "payload": ["junk"],
    })
    assert rec.id == "123"
    assert rec.payload == {}
    assert rec.source_class == SourceClass.D
    assert rec.source_type == SourceType.OBSERVED
    assert rec.retrieved_at is not None


def test_cached_result_corrupt_entries_return_none():
    assert cached_result("fred", None) is None
    assert cached_result("fred", {"data": ["nope"], "meta": {}}) is None
    assert cached_result("fred", {"data": {"records": "garbage"}, "meta": {}}) is None
    assert cached_result("fred", {"data": {"records": [{"id": 1, "payload": ["x"]}]}, "meta": {}}) is None
    now = utc_now()
    rec = SourceRecord(
        id="r:1", provider="p", entity="e", title="t", retrieved_at=now,
        source_class=SourceClass.A, source_type=SourceType.OBSERVED,
    )
    ok = cached_result("p", {"data": {"records": [rec.as_dict()]}, "meta": {"retrieved_at": now.isoformat()}})
    assert ok is not None and len(ok.records) == 1 and ok.cache_hit is True
    empty = cached_result("p", {"data": {"records": []}, "meta": {}})
    assert empty is not None and empty.records == () and empty.status == "ok"


def test_fred_corrupt_cache_not_served_as_fact(monkeypatch, fred_env, cache_dir):
    cache_dir.save("fred:DFF", {"records": "structurally corrupt"}, provider="fred")
    calls = []
    def _boom(url, params=None, headers=None, timeout=None):
        calls.append(url)
        raise ProviderUnavailable("network down")
    monkeypatch.setattr(httpio, "_http_get", _boom)
    result = fetch_fred_series("DFF", cache=cache_dir)
    assert result.status == "unavailable" and result.records == ()
    assert calls, "corrupt-but-fresh cache must not skip the live refresh"


def test_fred_junk_records_cache_degrades_not_fabricates(monkeypatch, fred_env, cache_dir):
    cache_dir.save("fred:DFF", {"records": [{"id": 1, "payload": {"value": 42}}]}, provider="fred")
    def _boom(url, params=None, headers=None, timeout=None):
        raise ProviderUnavailable("network down")
    monkeypatch.setattr(httpio, "_http_get", _boom)
    result = fetch_fred_series("DFF", cache=cache_dir)
    assert result.status == "unavailable" and result.records == ()


# ------------------------------------------------- SEC
def test_sec_normalizes_filings(monkeypatch, fred_env, cache_dir):
    monkeypatch.setattr(httpio, "_http_get", fake_get(SEC_URLS))
    result = fetch_sec_submissions(320193, cache=cache_dir, rate_sleep=0)
    assert result.status == "ok"
    assert len(result.records) == 1
    rec = result.records[0]
    assert rec.source_class == SourceClass.A
    assert rec.source_type == SourceType.OFFICIAL_FILING
    assert rec.payload["form"] == "10-Q"
    assert rec.reference == ("https://data.sec.gov/Archives/edgar/data/320193/"
                             "000032019326000020/aapl-20260731.htm")
    assert rec.published_at is not None
    assert result.metadata.get("company_name") == "Apple Inc."


def test_sec_user_agent_never_personal_email(fred_env):
    ua = _headers()["User-Agent"]
    assert "@" not in ua
    assert ua == SEC_DEFAULT_UA


def test_sec_user_agent_from_env(fred_env, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "my-org research dashboard")
    assert _headers()["User-Agent"] == "my-org research dashboard"


def test_sec_malformed_body_is_unavailable(monkeypatch, fred_env, cache_dir):
    def _malformed(url, params=None, headers=None, timeout=None):
        return FakeResponse(ValueError("broken"))
    monkeypatch.setattr(httpio, "_http_get", _malformed)
    result = fetch_sec_submissions(320193, cache=cache_dir, rate_sleep=0)
    assert result.status == "unavailable" and result.records == ()


def test_sec_facts_summary_never_financial_values(monkeypatch, fred_env, cache_dir):
    monkeypatch.setattr(httpio, "_http_get", fake_get(SEC_URLS))
    result = fetch_sec_company_facts(320193, cache=cache_dir, rate_sleep=0)
    assert result.status == "ok"
    assert len(result.records) == 1
    payload = result.records[0].payload
    assert payload["summary_only"] is True
    assert payload["taxonomy_counts"] == {"dei": 1, "us-gaap": 1}
    assert payload["ticker"] == "AAPL"
    serialized = json.dumps(payload)
    # raw fact labels / unit sheets from the underlying XBRL never leak in
    assert "label" not in serialized
    assert "units" not in serialized
    assert "shares" not in serialized


def test_sec_company_facts_url_fallback(monkeypatch, fred_env, cache_dir):
    fallback_url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    monkeypatch.setattr(httpio, "_http_get", fake_get({fallback_url: SEC_FACTS}))
    result = fetch_sec_company_facts(320193, cache=cache_dir, rate_sleep=0)
    assert result.status == "ok" and len(result.records) == 1
    assert result.records[0].payload["summary_only"] is True


def test_sec_cik_must_be_valid(fred_env, cache_dir):
    with pytest.raises(ValueError):
        fetch_sec_submissions("not-a-cik", cache=cache_dir)


def test_sec_short_arrays_stay_aligned(monkeypatch, fred_env, cache_dir):
    short = {
        "cik": 320193, "name": "Apple Inc.",
        "filings": {"recent": {
            "accessionNumber": ["000032019326000020"],
            "filingDate": ["2026-07-31", "2026-08-15"],
            "reportDate": ["2026-07-01", "2026-08-01"],
            "form": ["10-Q", "8-K"],
            "primaryDocument": ["aapl-20260731.htm", "aapl-20260815.htm"],
        }},
    }
    monkeypatch.setattr(httpio, "_http_get", fake_get({
        "https://data.sec.gov/submissions/CIK0000320193.json": short,
    }))
    result = fetch_sec_submissions(320193, cache=cache_dir, rate_sleep=0)
    assert result.status == "ok" and len(result.records) == 2
    assert any("idx1" in r.id for r in result.records)  # missing accession -> indexed id
    assert result.records[0].payload["filing_date"] == "2026-07-31"


def test_sec_fresh_cache_served_without_network(monkeypatch, fred_env, cache_dir):
    monkeypatch.setattr(httpio, "_http_get", fake_get(SEC_URLS))
    first = fetch_sec_submissions(320193, cache=cache_dir, rate_sleep=0)
    assert first.cache_hit is False
    calls = []
    def _boom(url, params=None, headers=None, timeout=None):
        calls.append(url)
        raise ProviderUnavailable("down")
    monkeypatch.setattr(httpio, "_http_get", _boom)
    second = fetch_sec_submissions(320193, cache=cache_dir, rate_sleep=0)
    assert second.cache_hit is True and len(second.records) == 1 and calls == []


# ------------------------------------------------- MF cache readers
def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_mf_nav_from_universe_cache(tmp_path):
    universe = _write(tmp_path, "universe.json", {
        "fetched_at": "2026-09-07T04:38:49+00:00",
        "rows": [
            {"scheme_code": "120828", "isin_primary": "INF966L01689", "isin_secondary": "",
             "scheme_name": "Quant Small Cap Fund", "amc": "quant Mutual Fund",
             "category": "Open Ended Schemes", "nav": 123.45, "nav_date": "06-09-2026"},
        ],
    })
    result = load_mf_nav_evidence(universe_cache_path=universe,
                                  amfi_cache_path=tmp_path / "missing.json")
    assert result.status == "ok"
    rec = result.records[0]
    assert rec.entity == "INF966L01689"
    assert rec.provider == "amfi" and rec.source_class == SourceClass.A
    assert rec.source_type == SourceType.OBSERVED
    assert rec.published_at is not None and rec.payload["nav"] == 123.45
    assert rec.reference.startswith("AMFI")


def test_mf_nav_fallback_to_amfi_cache(tmp_path):
    empty = _write(tmp_path, "empty.json", {"rows": []})
    amfi = _write(tmp_path, "amfi.json", {
        "saved_at": "2026-08-20 08:02",
        "nav": {"INF966L01689": 120.0, "INF209KA12Z1": None},
        "code": {"INF966L01689": "120828"},
        "name": {"INF966L01689": "Quant Small Cap Fund"},
    })
    result = load_mf_nav_evidence(universe_cache_path=empty, amfi_cache_path=amfi)
    assert result.status == "ok"
    assert len(result.records) == 1
    assert result.records[0].payload["nav"] == 120.0
    assert result.records[0].entity == "INF966L01689"
    assert all(rec.payload["nav"] is not None for rec in result.records)


def test_mf_nav_no_cache_is_unavailable(tmp_path):
    result = load_mf_nav_evidence(
        universe_cache_path=tmp_path / "nope.json", amfi_cache_path=tmp_path / "nope2.json")
    assert result.status == "unavailable" and result.records == ()


def test_mf_nav_universe_filtered_to_portfolio_isins(tmp_path):
    universe = _write(tmp_path, "universe.json", {
        "fetched_at": "2026-09-07T04:38:49+00:00",
        "rows": [
            {"scheme_code": "120828", "isin_primary": "INF966L01689", "isin_secondary": "",
             "scheme_name": "Quant Small Cap Fund", "amc": "quant Mutual Fund",
             "category": "Open Ended Schemes", "nav": 123.45, "nav_date": "06-09-2026"},
            {"scheme_code": "119598", "isin_primary": "INF209KA12Z1", "isin_secondary": "",
             "scheme_name": "HDFC Top 100", "amc": "HDFC AMC",
             "category": "Open Ended Schemes", "nav": 55.5, "nav_date": "06-09-2026"},
        ],
    })
    result = load_mf_nav_evidence(universe_cache_path=universe,
                                  amfi_cache_path=tmp_path / "missing.json",
                                  only_isins=["INF966L01689"])
    assert result.status == "ok"
    assert [r.entity for r in result.records] == ["INF966L01689"]


def test_mf_nav_fallback_filtered_to_portfolio_isins(tmp_path):
    empty = _write(tmp_path, "empty.json", {"rows": []})
    amfi = _write(tmp_path, "amfi.json", {
        "saved_at": "2026-08-20 08:02",
        "nav": {"INF966L01689": 120.0, "INF209KA12Z1": 55.5},
        "code": {"INF966L01689": "120828", "INF209KA12Z1": "119598"},
        "name": {"INF966L01689": "Quant Small Cap Fund", "INF209KA12Z1": "HDFC Top 100"},
    })
    result = load_mf_nav_evidence(universe_cache_path=empty, amfi_cache_path=amfi,
                                  only_isins=["INF209KA12Z1"])
    assert result.status == "ok"
    assert [r.entity for r in result.records] == ["INF209KA12Z1"]


def test_mf_holdings_primary_source(tmp_path):
    holdings = _write(tmp_path, "holdings.json", {
        "120828": [{"name": "HDFC Bank", "isin": "INE040A01034",
                    "weight_pct": None, "market_value": 312000, "quantity": 200,
                    "instrument_type": "Equity"}],
    })
    meta = _write(tmp_path, "meta.json", {
        "120828": {"fund_name": "Quant Small Cap Fund", "fallback_used": False,
                   "endpoint": "https://fund-holdings-browser.vercel.app/api/amfi/120828",
                   "as_of": "2026-07-31", "retrieved_at": "2026-09-07T04:38:50+00:00"},
    })
    result = load_mf_holdings_evidence(holdings_cache_path=holdings, holdings_meta_path=meta)
    assert result.status == "ok"
    rec = result.records[0]
    assert rec.provider == "fund-disclosures"
    assert rec.source_class == SourceClass.C
    assert rec.source_type == SourceType.OFFICIAL_FILING
    assert rec.payload["secondary_source"] is False


def test_mf_holdings_secondary_source_tagged(tmp_path):
    holdings = _write(tmp_path, "holdings.json", {
        "120828": [{"name": "HDFC Bank", "isin": "INE040A01034",
                    "weight_pct": 2.5, "market_value": 100}],
    })
    meta = _write(tmp_path, "meta.json", {
        "120828": {"fallback_used": True, "source_endpoint": "https://mfdata.in/...",
                   "retrieved_at": "2026-09-07T04:38:50+00:00"},
    })
    result = load_mf_holdings_evidence(holdings_cache_path=holdings, holdings_meta_path=meta)
    rec = result.records[0]
    assert rec.provider == "mfdata"
    assert rec.payload["secondary_source"] is True


def test_mf_holdings_missing_file_is_unavailable(tmp_path):
    result = load_mf_holdings_evidence(holdings_cache_path=tmp_path / "no.json",
                                       holdings_meta_path=tmp_path / "no2.json")
    assert result.status == "unavailable" and result.records == ()


# ------------------------------------------------- mapping
def test_mapping_mapped_unmapped_insufficient():
    import pandas as pd
    register = pd.DataFrame({
        "Key": ["mf:XXX", "st:INFY"],
        "Instrument": ["INF966L01689", "INFY"],
        "Source": ["MF", "Stocks"],
    })
    index = build_portfolio_index(register)

    rec = SourceRecord(
        id="mf:x", provider="amfi", entity="INF966L01689", title="t",
        retrieved_at=utc_now(), source_class=SourceClass.A,
        source_type=SourceType.OBSERVED, payload={"isin": "INF966L01689"},
    )
    assert assess_relevance(rec, index).status == "mapped"

    fred_rec = SourceRecord(
        id="fred:dff:2026_09_08", provider="fred", entity="DFF", title="t",
        retrieved_at=utc_now(), source_class=SourceClass.A,
        source_type=SourceType.OBSERVED, payload={"value": 4.79},
    )
    assert assess_relevance(fred_rec, index).status == "unmapped"

    bare = SourceRecord(
        id="x:1", provider="p", entity="", title="t", retrieved_at=utc_now(),
        source_class=SourceClass.D, source_type=SourceType.OBSERVED, payload={},
    )
    assert assess_relevance(bare, index).status == "insufficient"


def test_mapping_exact_match_only_no_fuzzy():
    import pandas as pd
    register = pd.DataFrame({"Key": ["k"], "Instrument": ["INF966L01689"], "Source": ["MF"]})
    index = build_portfolio_index(register)
    near_miss = SourceRecord(
        id="mf:y", provider="amfi", entity="INF966L01680", title="t",
        retrieved_at=utc_now(), source_class=SourceClass.A,
        source_type=SourceType.OBSERVED, payload={"isin": "INF966L01680"},
    )
    assert assess_relevance(near_miss, index).status == "unmapped"


def test_mapping_index_via_amfi_codes():
    index = build_portfolio_index(amfi_codes={"INF966L01689": "120828"})
    assert "120828" in index.scheme_codes
    rec = SourceRecord(
        id="m", provider="amfi", entity="120828", title="t", retrieved_at=utc_now(),
        source_class=SourceClass.A, source_type=SourceType.OBSERVED,
        payload={"scheme_code": "120828", "isin": ""},
    )
    assert assess_relevance(rec, index).status == "mapped"


def test_mapping_broad_code_key_is_not_an_identifier():
    index = build_portfolio_index()
    rec = SourceRecord(
        id="x", provider="p", entity="", title="t", retrieved_at=utc_now(),
        source_class=SourceClass.D, source_type=SourceType.OBSERVED,
        payload={"code": "INFY"},
    )
    # bare "code" was dropped from the identifier set: it must not map anything
    assert assess_relevance(rec, index).status == "insufficient"


# ------------------------------------------------- gateway status
def test_gateway_status_never_uses_network(monkeypatch, fred_env):
    calls = []
    def _boom(url, params=None, headers=None, timeout=None):
        calls.append(url)
        raise AssertionError("network must not fire")
    monkeypatch.setattr(httpio, "_http_get", _boom)
    rows = gateway_status()  # default cache dir + committed MF caches (file IO only)
    assert isinstance(rows, list) and rows
    assert calls == []


def test_import_sources_package_is_network_free(monkeypatch, fred_env):
    import importlib
    calls = []
    def _boom(url, *a, **k):
        calls.append(url)
        raise AssertionError("network during import")
    monkeypatch.setattr(httpio.requests, "get", _boom)
    for name in ("record", "cache", "errors", "httpio", "fred", "sec", "mf", "mapping"):
        importlib.reload(importlib.import_module(f"lib.intelligence.sources.{name}"))
    importlib.reload(importlib.import_module("lib.intelligence.sources"))
    assert calls == []


def test_gateway_status_never_fetched_row(tmp_path):
    rows = gateway_status(cache=Cache(base_dir=tmp_path / "empty"))
    required = {"provider", "key", "last_retrieval", "record_count", "is_stale", "status"}
    assert rows and all(required <= set(r) for r in rows)
    assert any(row["status"] == "never_fetched" for row in rows)


def test_gateway_status_surfaces_cache_entries(tmp_path, monkeypatch, fred_env):
    cache = Cache(base_dir=tmp_path / "gw")
    monkeypatch.setattr(httpio, "_http_get", fake_get(_fred_routes()))
    fetch_fred_series("DFF", cache=cache)
    rows = gateway_status(cache=cache)
    assert any(r["provider"] == "fred" and r["key"] == "fred:DFF" and r["status"] == "ok" for r in rows)
    assert any(r["provider"] == "mf" for r in rows)


# ------------------------------------------------- financial core untouched
def test_gateway_does_not_change_financial_semantics():
    assert net_worth(100.0, None)["net_worth"] == 100.0
    assert net_worth(100.0, 25.0)["net_worth"] == 75.0