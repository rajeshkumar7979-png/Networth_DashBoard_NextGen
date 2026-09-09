# -------------------------------------------------
# Portfolio-Aware Live Research — read-only evidence cohort.
#
# assemble_cohort() merges, on every page load (network-free), the cached gnews
# query buckets with any FRED/SEC records already in the gateway cache into one
# deduplicated LiveCohort of observed SourceRecords. Duplicate stories collapse
# by deterministic content_id (preferring holdings-first query order). A corrupt
# or unusable cache entry is skipped, never turned into a fabricated record.
#
# development_rows() renders the cohort for the UI with deterministic quality
# (research.score_evidence) and exact-identifier relevance (sources.mapping).
# -------------------------------------------------
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from lib.intelligence.research import classify_external, score_evidence
from lib.intelligence.sources.cache import Cache, default_ttl_seconds
from lib.intelligence.sources.mapping import PortfolioIndex, assess_relevance
from lib.intelligence.sources.record import (
    SourceRecord,
    cached_result,
    parse_iso,
    to_iso,
    utc_now,
)

from .news import (
    LIVE_CACHE_DIR,
    NEWS_COHORT_CAP,
    NEWS_PROVIDER,
    NEWS_TTL_SECONDS,
    news_cache_key,
    to_naive_utc,
)
from .planner import ResearchPlan

GATEWAY_PROVIDERS = ("fred", "sec")


@dataclass(frozen=True)
class LiveCohort:
    """Deduped, read-only set of currently-usable external evidence records."""

    records: tuple[SourceRecord, ...] = ()
    cache_served: tuple[SourceRecord, ...] = ()
    stale_sources: tuple[str, ...] = ()
    generated_at: Optional[datetime] = None

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def has_records(self) -> bool:
        return bool(self.records)

    @property
    def news_records(self) -> tuple[SourceRecord, ...]:
        return tuple(r for r in self.records if r.provider == NEWS_PROVIDER)

    @property
    def gateway_records(self) -> tuple[SourceRecord, ...]:
        return tuple(r for r in self.records if r.provider in GATEWAY_PROVIDERS)

    @property
    def last_retrieved_at(self) -> Optional[datetime]:
        if not self.records:
            return None
        return max(r.retrieved_at for r in self.records)

    def to_evidence(self):
        return tuple(r.to_evidence() for r in self.records)


def _is_usable(record) -> bool:
    return bool(record and all((record.id, record.provider, record.title)))


def _read_gnews_bucket(cache: Cache, query, category, now):
    key = news_cache_key(query, category)
    entry = cache.load(key)
    if entry is None:
        return [], False
    result = cached_result(NEWS_PROVIDER, entry)
    if result is None or result.status != "ok" or not result.records:
        return [], False
    is_old = cache.is_stale(key, NEWS_TTL_SECONDS, now=now)
    return [r for r in result.records if _is_usable(r)], is_old


def _read_gateway_cache(cache: Cache, now):
    records = []
    stale = set()
    if not cache.base_dir.is_dir():
        return records, stale
    for path in sorted(cache.base_dir.glob("*.json")):
        data = cache.load(path.stem)
        if data is None or not isinstance(data, dict):
            continue
        provider = str((data.get("meta") or {}).get("provider") or "misc")
        if provider not in GATEWAY_PROVIDERS:
            continue
        result = cached_result(provider, data)
        if result is None:
            continue
        if cache.is_stale(path.stem, default_ttl_seconds(provider), now=now):
            stale.add(provider)
        records.extend(r for r in result.records if _is_usable(r))
    return records, stale


def assemble_cohort(*, plan: ResearchPlan, now=None, cache=None, gateway_cache_dir=None) -> LiveCohort:
    """Merge gnews cache buckets + gateway cache records. Network-free."""
    now = to_naive_utc(now if now is not None else utc_now())
    cache = cache or Cache(base_dir=LIVE_CACHE_DIR)
    gw_cache = Cache(base_dir=gateway_cache_dir) if gateway_cache_dir is not None else Cache()

    seen_ids = set()
    seen_cid = set()
    records: list[SourceRecord] = []
    served_ids = set()
    stale_sources = set()

    for query in plan.queries:
        bucket, is_old = _read_gnews_bucket(cache, query.query, query.category, now)
        if is_old:
            stale_sources.add(NEWS_PROVIDER)
        for record in bucket:
            if record.id in seen_ids:
                continue
            cid = (record.payload or {}).get("content_id")
            if cid:
                if cid in seen_cid:
                    continue
                seen_cid.add(cid)
            seen_ids.add(record.id)
            records.append(record)
            served_ids.add(record.id)

    gw_records, gw_stale = _read_gateway_cache(gw_cache, now)
    stale_sources.update(gw_stale)
    for record in gw_records:
        if record.id in seen_ids:
            continue
        seen_ids.add(record.id)
        records.append(record)
        served_ids.add(record.id)

    if len(records) > NEWS_COHORT_CAP:
        records = records[:NEWS_COHORT_CAP]

    cache_served = tuple(r for r in records if r.id in served_ids)
    return LiveCohort(
        records=tuple(records),
        cache_served=cache_served,
        stale_sources=tuple(sorted(stale_sources)),
        generated_at=now,
    )


def affected_for(record, index: Optional[PortfolioIndex] = None) -> list:
    """Identifiers this record was labeled with, or exact matches vs the index."""
    matched = list((record.payload or {}).get("matched_identifiers") or [])
    if not matched and index is not None and not index.is_empty:
        result = assess_relevance(record, index)
        matched = list(result.matched or [])
    return [str(m).upper() for m in matched]


def development_rows(cohort: LiveCohort, index: Optional[PortfolioIndex] = None,
                     now=None) -> list[dict]:
    """UI rows for the Current External Developments table.

    Deterministic: exact-match relevance + score_evidence quality. Mapped rows
    sort first, then by quality. Never mutates the cohort or portfolio books.
    """
    now = to_naive_utc(now if now is not None else utc_now())
    index = index if index is not None else PortfolioIndex()
    rows = []
    for record in cohort.records:
        evidence = record.to_evidence()
        relevance = assess_relevance(record, index).status if not index.is_empty else "unmapped"
        quality = score_evidence(evidence, now=now, relevance=relevance)
        category = classify_external(evidence)
        if category == "news":
            category = (record.payload or {}).get("category") or "news"
        matched = affected_for(record, index)
        published = record.published_at
        rows.append({
            "Development": record.title,
            "Affected": ", ".join(sorted(matched)) if matched else "\u2014",
            "Category": category,
            "Source": (record.payload or {}).get("source_name") or record.provider,
            "Published": published.strftime("%d %b %H:%M") if published else "\u2014",
            "Quality": quality.score,
            "Relevance": relevance,
            "Link": record.reference or "",
        })
    rows.sort(key=lambda row: (0 if row["Relevance"] == "mapped" else 1, -row["Quality"]))
    return rows


def live_status(*, cache=None, now=None) -> list[dict]:
    """Read-only status of the live-research cache files. No network."""
    now = to_naive_utc(now if now is not None else utc_now())
    cache = cache or Cache(base_dir=LIVE_CACHE_DIR)
    rows = []
    if not cache.base_dir.is_dir():
        return rows
    for path in sorted(cache.base_dir.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as handle:
                entry = json.load(handle)
        except (OSError, ValueError):
            rows.append({
                "provider": NEWS_PROVIDER, "key": path.stem,
                "last_retrieval": to_iso(None), "record_count": None,
                "is_stale": False, "status": "corrupt",
                "reason": "unreadable cache file",
            })
            continue
        if not isinstance(entry, dict):
            rows.append({
                "provider": NEWS_PROVIDER, "key": path.stem,
                "last_retrieval": to_iso(None), "record_count": None,
                "is_stale": False, "status": "corrupt",
                "reason": "cache entry is not a JSON object",
            })
            continue
        meta = entry.get("meta") or {}
        body = entry.get("data") or {}
        provider = str(meta.get("provider") or NEWS_PROVIDER)
        key = str(meta.get("key") or path.stem)
        fetched = parse_iso(meta.get("retrieved_at"))
        raw_records = body.get("records") if isinstance(body, dict) else None
        count = len(raw_records) if isinstance(raw_records, list) else None
        if fetched is None or count is None:
            rows.append({
                "provider": provider, "key": key, "last_retrieval": to_iso(fetched),
                "record_count": count, "is_stale": False, "status": "corrupt",
                "reason": "cache entry missing retrieval time or record list",
            })
            continue
        is_old = (now - fetched).total_seconds() >= NEWS_TTL_SECONDS
        rows.append({
            "provider": provider, "key": key, "last_retrieval": to_iso(fetched),
            "record_count": count, "is_stale": is_old, "status": "ok",
        })
    return rows