# -------------------------------------------------
# Portfolio-Aware Live Research & News Evidence v1.
#
# Importing this package performs NO network I/O. Live retrieval happens only
# through pipeline.run_live_research (explicit user action); every page-load
# entry point (build_live_plan / load_live_cohort / live_status /
# development_rows) is cache-read-only and network-free.
# -------------------------------------------------
from __future__ import annotations

from lib.intelligence.live.news import (
    LIVE_CACHE_DIR,
    NEWS_COHORT_CAP,
    NEWS_MAX_PER_QUERY,
    NEWS_PROVIDER,
    NEWS_TTL_SECONDS,
    fetch_gnews,
    news_cache_key,
    scrub_error,
    to_naive_utc,
)
from lib.intelligence.live.planner import (
    MAX_FUND_QUERIES,
    MAX_STOCK_QUERIES,
    FRED_USD_INR_TARGET,
    NewsQuery,
    ResearchPlan,
    build_live_plan,
)
from lib.intelligence.live.cohort import (
    GATEWAY_PROVIDERS,
    LiveCohort,
    affected_for,
    assemble_cohort,
    development_rows,
    live_status,
)
from lib.intelligence.live.pipeline import (
    LiveResult,
    STATUS_DEGRADED,
    STATUS_OK,
    STATUS_UNAVAILABLE,
    load_live_cohort,
    run_live_research,
    usd_book_present,
)

__all__ = [
    "FRED_USD_INR_TARGET",
    "GATEWAY_PROVIDERS",
    "LIVE_CACHE_DIR",
    "LiveCohort",
    "LiveResult",
    "MAX_FUND_QUERIES",
    "MAX_STOCK_QUERIES",
    "NEWS_COHORT_CAP",
    "NEWS_MAX_PER_QUERY",
    "NEWS_PROVIDER",
    "NEWS_TTL_SECONDS",
    "NewsQuery",
    "ResearchPlan",
    "STATUS_DEGRADED",
    "STATUS_OK",
    "STATUS_UNAVAILABLE",
    "affected_for",
    "assemble_cohort",
    "build_live_plan",
    "development_rows",
    "fetch_gnews",
    "live_status",
    "load_live_cohort",
    "news_cache_key",
    "run_live_research",
    "scrub_error",
    "to_naive_utc",
    "usd_book_present",
]