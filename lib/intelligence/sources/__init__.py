# -------------------------------------------------
# Intelligence Data Gateway v1 — provider-neutral external-data gateway.
#
# Importing this package performs NO network I/O. Live fetches happen only
# through the explicit fetch_* functions; gateway_status() reads caches only.
# -------------------------------------------------
from __future__ import annotations

from lib.intelligence.model import (
    FactKind,
    SourceClass,
    SourceType,
    INSUFFICIENT_EVIDENCE,
)
from lib.intelligence.sources.cache import Cache, CacheEntry
from lib.intelligence.sources.errors import (
    GatewayError,
    ProviderConfigMissing,
    ProviderMalformed,
    ProviderTimeout,
    ProviderUnavailable,
)
from lib.intelligence.sources.fred import fetch_fred_series, latest_fred_observation
from lib.intelligence.sources.mapping import (
    MappingResult,
    PortfolioIndex,
    assess_relevance,
    build_portfolio_index,
)
from lib.intelligence.sources.mf import (
    load_mf_holdings_evidence,
    load_mf_nav_evidence,
    mf_status,
)
from lib.intelligence.sources.record import (
    SourceRecord,
    SourceResult,
    dedupe_records,
    make_record_id,
    unavailable_result,
    utc_now,
)
from lib.intelligence.sources.sec import (
    fetch_sec_company_facts,
    fetch_sec_submissions,
)


def gateway_status(*, now=None, cache=None) -> list[dict]:
    """Read-only provider freshness/availability snapshot. No network calls.

    Merges the JSON cache scan (FRED/SEC) with the MF cache status. Safe to
    call on every Command Center page open.
    """
    cache = cache or Cache()
    rows = [entry.as_dict() for entry in cache.scan(now=now)]
    if not any(row["status"] == "ok" for row in rows):
        rows.append({
            "provider": "gateway",
            "key": "intel_gateway_cache",
            "last_retrieval": None,
            "record_count": None,
            "is_stale": False,
            "status": "never_fetched",
            "reason": "no gateway cache written yet; FRED/SEC fetch on demand",
        })
    rows.extend(mf_status(now=now))
    return rows


__all__ = [
    "Cache",
    "CacheEntry",
    "FactKind",
    "GatewayError",
    "INSUFFICIENT_EVIDENCE",
    "MappingResult",
    "PortfolioIndex",
    "ProviderConfigMissing",
    "ProviderMalformed",
    "ProviderTimeout",
    "ProviderUnavailable",
    "SourceClass",
    "SourceRecord",
    "SourceResult",
    "SourceType",
    "assess_relevance",
    "build_portfolio_index",
    "dedupe_records",
    "fetch_fred_series",
    "fetch_sec_company_facts",
    "fetch_sec_submissions",
    "gateway_status",
    "latest_fred_observation",
    "load_mf_holdings_evidence",
    "load_mf_nav_evidence",
    "make_record_id",
    "mf_status",
    "unavailable_result",
    "utc_now",
]