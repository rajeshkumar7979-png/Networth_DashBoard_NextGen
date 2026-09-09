# -------------------------------------------------
# Portfolio-Aware Live Research — Google News RSS adapter (provider "gnews").
#
# Controlled, bounded, explicitly-invoked news ingestion. Queries come from the
# planner (derived from CURRENT holdings), so coverage is intentionally
# portfolio-shaped. Records are OBSERVED FACT news evidence (SourceClass C,
# SourceType NEWS) and are NEVER auto-converted into verified portfolio facts.
#
# Identifier labeling: a title word-boundary match against a held identifier
# only LABELS the record's likely affected holdings ("matched_identifiers").
# The "mapped" gate remains assess_relevance (lib.intelligence.sources.mapping),
# which matches exact identifiers of the portfolio index only. No fuzzy identity
# resolution, no invented associations.
#
# Live fetch happens ONLY via fetch_gnews (called by pipeline.run_live_research
# on an explicit user action). Cache reads are network-free. A provider failure
# (timeout, HTTP error, malformed feed) degrades to a stale cached result marked
# is_stale, or to an explicit unavailable result — never a fabricated record.
# -------------------------------------------------
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import feedparser

from lib.config import DATA_DIR
from lib.intelligence.model import SourceClass, SourceType
from lib.intelligence.sources import httpio as _gateway_http
from lib.intelligence.sources.cache import Cache
from lib.intelligence.sources.record import (
    SourceRecord,
    SourceResult,
    cached_result,
    make_record_id,
    unavailable_result,
    utc_now,
)

NEWS_PROVIDER = "gnews"
NEWS_BASE_URL = "https://news.google.com/rss/search"
NEWS_TTL_SECONDS = 30 * 60
NEWS_MAX_PER_QUERY = 8
NEWS_COHORT_CAP = 40
LIVE_CACHE_DIR = Path(DATA_DIR) / "live_research_cache"

_NEWS_PARAMS = {"hl": "en-IN", "gl": "IN", "ceid": "IN:en"}
_QUERY_SCRUB = re.compile(r"\?[^\s\"'<>]+")
_HTML_TAG = re.compile(r"<[^>]+>")


def to_naive_utc(now=None) -> datetime:
    """Deterministic naive-UTC timestamp (matches gateway cache timestamps)."""
    now = now or utc_now()
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc).replace(tzinfo=None)
    return now


def scrub_error(text) -> str:
    """Single scrub choke point for error strings: drop URL query segments."""
    return _QUERY_SCRUB.sub("?[redacted]", str(text or ""))


def _clean_title(title, source):
    title = (title or "").strip()
    source = (source or "").strip()
    if source and title.lower().endswith(f"- {source.lower()}"):
        title = title[: -(len(source) + 2)].strip(" -")
    return title


def _parse_published(entry):
    parsed = getattr(entry, "published_parsed", None)
    if parsed:
        try:
            return datetime(*parsed[:6])
        except (TypeError, ValueError):
            pass
    return None


def _content_id(title) -> str:
    norm = re.sub(r"[^0-9a-z]+", "", (title or "").lower())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:14]


def _identifier_pattern(identifier):
    """Exact word-boundary pattern: identifier letters, internal separators
    (space/dot/dash) made optional. Deterministic -- never fuzzy."""
    chunks = re.findall(r"[0-9A-Za-z]+", str(identifier or ""))
    if not chunks:
        return None
    body = r"[\s.\-]*".join(re.escape(c) for c in chunks)
    return re.compile(rf"(?<![0-9A-Za-z]){body}(?![0-9A-Za-z])", re.IGNORECASE)


def _pick_identifiers(title, identifiers):
    """Identifiers (in caller order) whose exact word-boundary pattern appears
    in the title. Bounded at 4 to keep payloads small."""
    picked = []
    for ident in identifiers:
        pattern = _identifier_pattern(ident)
        if pattern is not None and pattern.search(title or ""):
            picked.append(str(ident).strip())
            if len(picked) >= 4:
                break
    return picked


def _summary_text(entry) -> str:
    text = re.sub(r"\s+", " ", _HTML_TAG.sub(" ", str(entry.get("summary") or "")))
    return text.strip()[:280]


def _to_records(query, category, entries, *, identifiers=(), now=None, limit=NEWS_MAX_PER_QUERY):
    """Normalize raw feed entries into SourceRecords. Pure restructure."""
    now = to_naive_utc(now)
    ident_keys = {str(i).strip(): key for i, key in (identifiers or ()) if str(i).strip()}
    records = []
    seen_cid = set()
    for entry in entries or ():
        raw = str(entry.get("title") or "").strip()
        if not raw:
            continue
        src = entry.get("source") or {}
        source_name = src.get("title") if isinstance(src, dict) else ""
        title = _clean_title(raw, source_name)
        cid = _content_id(title)
        if not cid or cid in seen_cid:
            continue
        seen_cid.add(cid)
        published_dt = _parse_published(entry)
        matched = _pick_identifiers(title, list(ident_keys))
        payload = {
            "query": query,
            "category": category,
            "content_id": cid,
            "source_name": source_name,
            "summary": _summary_text(entry),
        }
        if published_dt is not None:
            payload["published"] = str(entry.get("published") or entry.get("updated") or "")
            payload["published_dt"] = published_dt.isoformat()
        for ident in matched:
            key = ident_keys[ident]
            payload.setdefault(key, ident)
        payload["matched_identifiers"] = matched
        records.append(SourceRecord(
            id=make_record_id(NEWS_PROVIDER, category, query, cid),
            provider=NEWS_PROVIDER,
            entity=query,
            title=title,
            retrieved_at=now,
            source_class=SourceClass.C,
            source_type=SourceType.NEWS,
            published_at=published_dt,
            reference=entry.get("link") or None,
            payload=payload,
        ))
    records.sort(key=lambda r: r.published_at or datetime.min, reverse=True)
    return tuple(records[: max(0, int(limit))])


def news_cache_key(query, category) -> str:
    """Deterministic cache-file key for one query+category bucket."""
    return make_record_id(NEWS_PROVIDER, "cache", category, query)


def fetch_gnews(query, category, *, identifiers=(), now=None, limit=NEWS_MAX_PER_QUERY,
                cache=None, params=None, parse=None) -> SourceResult:
    """Fetch (or serve cached) news for one query. Explicit call only.

    Degrades: fresh cache -> cache hit; live failure with a cache -> stale-served
    records (is_stale=True); live failure without a cache -> unavailable. Never
    raises and never fabricates records.
    """
    now = to_naive_utc(now)
    cache = cache or Cache(base_dir=LIVE_CACHE_DIR)
    key = news_cache_key(query, category)

    entry = cache.load(key)
    decoded = cached_result(NEWS_PROVIDER, entry) if entry is not None else None
    if decoded is not None and cache.is_fresh(key, NEWS_TTL_SECONDS, now=now):
        return decoded

    try:
        qparams = dict(params or _NEWS_PARAMS)
        qparams["q"] = query
        response = _gateway_http._http_get(NEWS_BASE_URL, params=qparams)
        feed = (parse or feedparser.parse)(response.text)
        entries = getattr(feed, "entries", None) or []
        records = _to_records(query, category, entries, identifiers=identifiers,
                              now=now, limit=limit)
        result = SourceResult(
            provider=NEWS_PROVIDER,
            status="ok",
            records=records,
            retrieved_at=now,
            metadata={"query": query, "category": category},
        )
        cache.save(
            key,
            {"metadata": result.metadata, "records": [r.as_dict() for r in records]},
            provider=NEWS_PROVIDER,
            retrieved_at=now,
        )
        return result
    except Exception as exc:
        reason = scrub_error(f"live refresh failed: {type(exc).__name__}: {exc}")
        if decoded is not None:
            return SourceResult(
                provider=NEWS_PROVIDER,
                status="ok",
                records=decoded.records,
                retrieved_at=decoded.retrieved_at,
                is_stale=True,
                cache_hit=False,
                reason=f"stale cache served; {reason}",
                metadata={"query": query, "category": category},
            )
        return unavailable_result(NEWS_PROVIDER, f"{reason} (query: {query})")