"""Holdings ingest: CDN primary, fail-fast 4xx, circuit-breaker. Network-free."""
from __future__ import annotations

import json

import pytest
import requests

from lib import mf_holdings as mh


class _Resp:
    def __init__(self, payload=None, status_code=200, text="", headers=None):
        self._payload = payload
        self.status_code = status_code
        self.text = text if text else (
            json.dumps(payload) if payload is not None else ""
        )
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


@pytest.fixture(autouse=True)
def _reset():
    mh.reset_ingest_state_for_tests()
    yield
    mh.reset_ingest_state_for_tests()


def test_normalize_holding_reads_cdn_pct_nav_and_industry():
    row = {
        "holding_type": "equity",
        "instrument": "HDFC Bank Limited",
        "isin": "INE040A01034",
        "industry": "Banks",
        "quantity": 10,
        "market_value": 112.5,
        "pct_nav": 7.63,
    }
    out = mh._normalize_holding(row, "fund-disclosures")
    assert out["name"] == "HDFC Bank Limited"
    assert out["isin"] == "INE040A01034"
    assert out["weight_pct"] == 7.63
    assert out["sector"] == "Banks"
    assert out["instrument_type"] == "equity"


def test_request_json_does_not_retry_404(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append(url)
        return _Resp(
            payload={"error": {"code": "404", "message": "The deployment could not be found on Vercel."}},
            status_code=404,
            text="The deployment could not be found on Vercel.",
        )

    session = requests.Session()
    monkeypatch.setattr(session, "get", fake_get)
    url = "https://fund-holdings-browser.vercel.app/api/amfi/122639"
    with pytest.raises(RuntimeError, match="HTTP 404"):
        mh._request_json(session, url)
    assert len(calls) == 1
    assert "fund-holdings-browser.vercel.app" in mh._DEAD_HOSTS


def test_vercel_circuit_skips_later_schemes(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append(url)
        return _Resp(status_code=404, text="DEPLOYMENT_NOT_FOUND")

    session = requests.Session()
    monkeypatch.setattr(session, "get", fake_get)
    url = "https://fund-holdings-browser.vercel.app/api/amfi/1"
    with pytest.raises(RuntimeError):
        mh._request_json(session, url)
    with pytest.raises(RuntimeError, match="circuit-open"):
        mh._request_json(session, "https://fund-holdings-browser.vercel.app/api/amfi/2")
    assert len(calls) == 1


def test_fetch_cdn_holdings_uses_latest_as_of_not_stale_row(monkeypatch):
    catalog = {
        "meta": {"commit": "abc123"},
        "lookup": {
            "120828": {
                "amfi_code": "120828",
                "portfolio_id": "100176",
                "as_of": "2026-07-31",
                "latest_as_of": "2026-08-31",
                "portfolio_key": "portfolios/asof/2026-08-31/100176.json",
                "portfolio_url": (
                    "https://cdn.jsdelivr.net/gh/kushagra-agarwal-a/"
                    "fund-holdings-data@abc123/portfolios/asof/2026-08-31/100176.json"
                ),
            }
        },
        "ref": "abc123",
    }
    mh._CDN_CATALOG = catalog
    payload = {
        "meta": {
            "as_of": "2026-08-31",
            "disclosure_type": "monthly",
            "source_file": "Monthly_Portfolio_August26.xlsx",
        },
        "holdings": [
            {
                "instrument": "Reliance Industries",
                "isin": "INE002A01018",
                "pct_nav": 8.1,
                "market_value": 100.0,
            }
        ],
    }
    seen = []

    def fake_multi(session, urls):
        seen.extend(list(urls))
        return payload, {}

    monkeypatch.setattr(mh, "_request_json_multi", fake_multi)
    holdings, meta = mh.fetch_cdn_holdings(requests.Session(), "120828")
    assert len(holdings) == 1
    assert holdings[0]["name"] == "Reliance Industries"
    assert holdings[0]["weight_pct"] == 8.1
    assert meta["as_of"] == "2026-08-31"
    assert meta["source"] == "fund-disclosures"
    assert meta["transport"] == "github-cdn"
    assert "2026-08-31/100176.json" in seen[0]


def test_ingest_prefers_cdn_over_vercel(monkeypatch):
    def cdn(session, code):
        return (
            [{"name": "X", "isin": "INE1", "weight_pct": 50.0, "source": "fund-disclosures"}],
            {"as_of": "2026-08-31", "source": "fund-disclosures", "transport": "github-cdn"},
        )

    def boom(*a, **k):
        raise AssertionError("must not fall through")

    monkeypatch.setattr(mh, "fetch_cdn_holdings", cdn)
    monkeypatch.setattr(mh, "fetch_fund_disclosures", boom)
    monkeypatch.setattr(mh, "fetch_mfdata_fallback", boom)
    holdings, meta = mh.ingest_scheme_holdings(requests.Session(), "122639")
    assert holdings[0]["name"] == "X"
    assert meta["fallback_used"] is False
    assert meta["validation"]["holdings_with_weight"] == 1
