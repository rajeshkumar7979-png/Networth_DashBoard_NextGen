# -------------------------------------------------
# Portfolio-Aware Live Research — explicit-fetch pipeline.
#
# run_live_research() is the ONLY network entry point. It is invoked solely by
# an explicit user action ("Refresh research evidence"). It fetches each planned
# gnews query plus the FRED USD/INR series when a USD book is present, and
# assembles the resulting cohort. Every per-provider failure degrades to an
# unavailable/stale result and is recorded, never re-raised; a provider failure
# can never become a financial fact.
#
# load_live_cohort() and live_status() are network-free cache reads used on
# ordinary page loads.
# -------------------------------------------------
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from lib.intelligence.sources.cache import Cache
from lib.intelligence.sources.fred import fetch_fred_series
from lib.intelligence.sources.record import SourceResult, unavailable_result, utc_now

from .cohort import LiveCohort, assemble_cohort
from .news import LIVE_CACHE_DIR, NEWS_PROVIDER, fetch_gnews, scrub_error, to_naive_utc
from .planner import NewsQuery, ResearchPlan, build_live_plan, simplify_query

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_UNAVAILABLE = "unavailable"


def usd_book_present(facts) -> bool:
    """True when the exposure facts carry a nonzero FCNR/USD class value."""
    if facts is None:
        return False
    try:
        class_facts = getattr(facts, "class_facts", ()) or ()
    except Exception:
        return False
    for fact in class_facts:
        entity = str(getattr(fact, "entity", "") or "").lower()
        if ("fcnr" in entity or "usd" in entity) and float(fact.value) > 0.0:
            return True
    return False


@dataclass(frozen=True)
class LiveResult:
    """Outcome of one explicit live-research refresh."""

    plan: ResearchPlan
    results: tuple[SourceResult, ...]
    cohort: LiveCohort
    failures: tuple[tuple[str, str], ...] = ()
    status: str = STATUS_UNAVAILABLE
    refreshed_at: Optional[datetime] = None

    def to_evidence(self):
        return self.cohort.to_evidence()

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "refreshed_at": self.refreshed_at.isoformat() if self.refreshed_at else None,
            "record_count": self.cohort.record_count,
            "stale_sources": list(self.cohort.stale_sources),
            "failures": [{"source": src, "reason": reason} for src, reason in self.failures],
            "query_count": self.plan.query_count,
            "fred_count": self.plan.fred_count,
        }


def run_live_research(*, stock_symbols=(), fund_names=(), gold_symbols=(),
                      facts=None, now=None, plan=None, news_cache=None,
                      gateway_cache=None, parse=None) -> LiveResult:
    """Explicit fetch of the planned live-research evidence. Never raises."""
    now = to_naive_utc(now if now is not None else utc_now())
    plan = plan or build_live_plan(
        stock_symbols=stock_symbols,
        fund_names=fund_names,
        gold_symbols=gold_symbols,
        has_usd_book=usd_book_present(facts),
        now=now,
    )
    news_cache = news_cache or Cache(base_dir=LIVE_CACHE_DIR)
    gateway_cache = gateway_cache if gateway_cache is not None else Cache()

    results: list[SourceResult] = []
    failures: list[tuple[str, str]] = []
    effective_queries = list(plan.queries)

    def fetch_news(query, category, identifiers, *, is_fallback: bool) -> SourceResult:
        try:
            result = fetch_gnews(
                query, category,
                identifiers=identifiers,
                now=now,
                cache=news_cache,
                parse=parse,
            )
        except Exception as exc:  # defensive: fetch_gnews already guards, never raise
            result = unavailable_result(NEWS_PROVIDER, scrub_error(
                f"refresh failed: {type(exc).__name__}: {exc}"))
        if is_fallback:
            logger.debug("gnews fallback fetch (query=%r category=%r) status=%s "
                         "records=%d", query, category, result.status,
                         len(result.records))
        return result

    for query in plan.queries:
        identifiers = [(query.identifier, query.identifier_key)] if query.is_identified() else []
        result = fetch_news(query.query, query.category, identifiers, is_fallback=False)
        results.append(result)
        if result.status != "ok":
            failures.append((query.query, scrub_error(result.reason or "unavailable")))
            continue
        if result.records:
            continue
        # Zero records: retry once with a simplified, higher-recall query and
        # log the miss for debugging. The fallback bucket joins the cohort.
        simplified = simplify_query(query.query, kind=query.kind)
        if not simplified or simplified.lower() == query.query.lower():
            logger.info(
                "gnews query returned 0 records (query=%r category=%r kind=%r) "
                "- no simpler form available", query.query, query.category,
                query.kind)
            continue
        logger.info(
            "gnews query returned 0 records (query=%r category=%r kind=%r) - "
            "retrying simplified: %r", query.query, query.category, query.kind,
            simplified)
        fb = fetch_news(simplified, query.category, identifiers, is_fallback=True)
        results.append(fb)
        if fb.status == "ok":
            if not fb.records:
                logger.info(
                    "gnews simplified query also returned 0 records "
                    "(query=%r)", simplified)
            effective_queries.append(NewsQuery(
                query=simplified,
                category=query.category,
                kind=query.kind,
                identifier=query.identifier,
                identifier_key=query.identifier_key,
            ))

    for series in plan.fred_targets:
        try:
            result = fetch_fred_series(series, cache=gateway_cache, force_refresh=True, now=now)
        except Exception as exc:  # defensive; fred module guards internally
            result = unavailable_result("fred", scrub_error(
                f"refresh failed: {type(exc).__name__}: {exc}"))
        results.append(result)
        if result.status != "ok":
            failures.append((f"fred:{series}", scrub_error(result.reason or "unavailable")))

    gateway_used = gateway_cache if gateway_cache.base_dir != Cache().base_dir else None
    cohort = assemble_cohort(
        plan=ResearchPlan(queries=tuple(effective_queries),
                          fred_targets=plan.fred_targets,
                          generated_at=plan.generated_at),
        now=now,
        cache=news_cache,
        gateway_cache_dir=gateway_used.base_dir if gateway_used is not None else None,
    )

    if cohort.has_records:
        status = STATUS_OK if not cohort.stale_sources else STATUS_DEGRADED
    else:
        status = STATUS_DEGRADED if cohort.stale_sources else STATUS_UNAVAILABLE

    return LiveResult(
        plan=plan,
        results=tuple(results),
        cohort=cohort,
        failures=tuple(failures),
        status=status,
        refreshed_at=now,
    )


def load_live_cohort(*, plan=None, stock_symbols=(), fund_names=(), gold_symbols=(),
                     facts=None, has_usd_book: Optional[bool] = None, now=None,
                     news_cache=None, gateway_cache_dir=None) -> LiveCohort:
    """Network-free cohort for ordinary page loads (cache-read-only).

    When a plan is not supplied one is derived; has_usd_book overrides the
    facts-based detection so callers can decide once and reuse.
    """
    now = to_naive_utc(now if now is not None else utc_now())
    if plan is None:
        if has_usd_book is None:
            has_usd_book = usd_book_present(facts)
        plan = build_live_plan(
            stock_symbols=stock_symbols,
            fund_names=fund_names,
            gold_symbols=gold_symbols,
            has_usd_book=bool(has_usd_book),
            now=now,
        )
    news_cache = news_cache or Cache(base_dir=LIVE_CACHE_DIR)
    return assemble_cohort(plan=plan, now=now, cache=news_cache,
                           gateway_cache_dir=gateway_cache_dir)