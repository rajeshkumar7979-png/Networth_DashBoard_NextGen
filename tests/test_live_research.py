# -------------------------------------------------
# Portfolio-Aware Live Research & News Evidence v1 — offline regression suite.
#
# Hermetic: no network, no committed caches, no real API keys — every provider
# is frozen by monkeypatching the single gateway HTTP seam (httpio._http_get)
# and feedparser.parse on the gnews adapter. Pins: planner derivation, gnews
# normalization, exact word-boundary identifier labeling, observed-fact
# evidence classification, exact-match relevance, content-id dedup, cache
# round-trip + corruption handling, freshness/staleness, failure degradation
# (timeout / HTTP 429 / malformed feed -> stale or unavailable, never
# fabricated), credential scrubbing, explicit-fetch-only network behavior,
# no portfolio-number mutation, no-cash-flow vocabulary, and ResearchBrief
# consumption without any AI involvement.
# -------------------------------------------------
from __future__ import annotations

import datetime
import types

from lib.intelligence import live as intel_live
from lib.intelligence import research
from lib.intelligence.evidence import EvidenceBag
from lib.intelligence.exposure import Coverage
from lib.intelligence.model import (
    FactKind,
    SourceClass,
    SourceType,
    make_fact,
)
from lib.intelligence.sources import httpio
from lib.intelligence.sources.cache import Cache
from lib.intelligence.sources.errors import ProviderTimeout, ProviderUnavailable
from lib.intelligence.sources.mapping import PortfolioIndex, assess_relevance
from lib.intelligence.sources.record import SourceRecord

NOW = datetime.datetime.fromisoformat("2026-09-08T13:38:00")
OLD = NOW - datetime.timedelta(minutes=90)  # older than the 1-hour news TTL


class _FeedEntry(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


def _ok_response(text="<rss/>"):
    return types.SimpleNamespace(text=text)


def _entries_feed(entries):
    return types.SimpleNamespace(entries=entries)


def _feed_entry(title, source="MoneyControl", summary="some copy",
                link="https://example.com/story", published_parsed=(2026, 9, 8, 10, 30, 0, 0, 0, 0)):
    return _FeedEntry(
        title=title,
        source={"title": source},
        summary=summary,
        link=link,
        published=datetime.date(*published_parsed[:3]).isoformat(),
        published_parsed=published_parsed,
    )


def _news_record(query, category, title, *, content_id=None, symbol=None,
                 fund_name=None, retrieved_at=NOW, published_at=NOW):
    from lib.intelligence.live import news as live_news
    cid = content_id or live_news._content_id(title)
    payload = {
        "query": query,
        "category": category,
        "content_id": cid,
        "source_name": "MoneyControl",
        "summary": "summary",
        "matched_identifiers": [],
    }
    if symbol:
        payload["symbol"] = symbol
        payload["matched_identifiers"] = [symbol]
    if fund_name:
        payload["fund_name"] = fund_name
        payload["matched_identifiers"] = [fund_name]
    return SourceRecord(
        id=live_news.make_record_id("gnews", category, query, cid),
        provider="gnews",
        entity=query,
        title=title,
        retrieved_at=retrieved_at,
        source_class=SourceClass.C,
        source_type=SourceType.NEWS,
        published_at=published_at,
        reference="https://example.com/story",
        payload=payload,
    )


def _seed(cache: Cache, record: SourceRecord):
    from lib.intelligence.live import news as live_news
    query = record.payload.get("query") or "unused"
    category = record.payload.get("category") or "holding"
    cache.save(live_news.news_cache_key(query, category),
               {"metadata": {}, "records": [record.as_dict()]},
               provider="gnews", retrieved_at=record.retrieved_at)


def _plan_for(record: SourceRecord):
    from lib.intelligence.live.planner import NewsQuery, ResearchPlan
    query = record.payload.get("query") or "unused"
    category = record.payload.get("category") or "holding"
    return ResearchPlan(
        queries=(NewsQuery(query=query, category=category, kind=category),),
        generated_at=NOW)


class _Facts:
    def __init__(self, usd=False):
        self.as_of = NOW
        self.total_assets = 100000.0
        self.total_invested = 80000.0
        self.total_pnl = 20000.0
        self.coverage = Coverage(10000, 10000, 0, 5, 0, (), 100.0)
        self._facts = [make_fact("Equity", "share_pct", 40.0, "pct", now=NOW, prefix="class")]
        if usd:
            self._facts.append(make_fact("FCNR (USD)", "current_inr", 5000.0, "INR",
                                         now=NOW, prefix="class"))
        self.class_facts = tuple(self._facts)

    def all_facts(self):
        return tuple(self._facts)


FORBIDDEN_CASHFLOW_WORDS = {
    "sip", "withdrawal", "deposit", "redemption", "xirr", "cash flow",
    " buy ", " sell ",
}


# ---------------- planner ----------------
def test_build_live_plan_derives_queries_from_holdings():
    plan = intel_live.build_live_plan(
        stock_symbols=["ETERNAL", "BLS"],
        fund_names=["PARAM MOMENTUM FUND - Direct - Growth"],
        gold_symbols=["GOLDBEES", "SGBSEP31II-GB"],
        has_usd_book=False, now=NOW)
    queries = plan.queries
    categories = {q.category for q in queries}
    assert categories == {"holding", "nri_tax", "macro"}
    assert plan.fred_targets == ()
    named = {q.query: q for q in queries}
    assert named["ETERNAL"].kind == "holding"
    assert named["ETERNAL"].identifier == "ETERNAL"
    assert named["ETERNAL"].identifier_key == "symbol"
    assert named["Sovereign Gold Bond"].kind == "gold"
    assert named["Sovereign Gold Bond"].identifier == ""
    assert "GOLDBEES" in named and named["GOLDBEES"].identifier == "GOLDBEES"
    assert "SGBSEP31II-GB" not in named  # SGB tickers stay on generic gold queries
    assert named["PARAM MOMENTUM"].kind == "fund"
    assert named["PARAM MOMENTUM"].identifier == "PARAM MOMENTUM FUND - Direct - Growth"
    assert named["PARAM MOMENTUM"].identifier_key == "fund_name"
    assert plan.query_count == len(queries)


def test_build_live_plan_has_usd_book_controls_fred():
    assert intel_live.build_live_plan(has_usd_book=False, now=NOW).fred_targets == ()
    plan = intel_live.build_live_plan(has_usd_book=True, now=NOW)
    assert plan.fred_targets == (intel_live.FRED_USD_INR_TARGET,)


def test_derives_queries_from_top_holdings():
    plan = intel_live.build_live_plan(
        stock_symbols=[("SMALLCO", 5.0), ("BIGCO", 100.0), ("MIDCO", 40.0)],
        fund_names=[("PARAM MOMENTUM FUND - Direct - Growth", 200.0)],
        gold_symbols=["GOLDBEES"],
        has_usd_book=True,
        equity_pct=55.0,
        asset_class_weights={"gold": 10.0, "fcnr": 3.0},
        now=NOW)
    portfolio = [q for q in plan.queries
                 if q.category == "holding" or q.kind == "asset_class"]
    assert len(portfolio) == intel_live.MAX_PORTFOLIO_QUERIES  # bounded, by weight
    queries = [q.query for q in portfolio]
    assert queries[0] == "PARAM MOMENTUM"          # highest portfolio weight first
    assert queries.index("BIGCO") < queries.index("MIDCO")
    assert "SMALLCO" not in queries                # lowest weight crowded out
    assert "Nifty 50 valuation PE ratio" in queries
    assert "gold price INR forecast" in queries
    equity = next(q for q in portfolio if q.query == "Nifty 50 valuation PE ratio")
    assert equity.category == "macro" and equity.kind == "asset_class"
    assert plan.fred_targets == (intel_live.FRED_USD_INR_TARGET,)

    # equity contextual query is gated on a >30% equity share
    low = intel_live.build_live_plan(equity_pct=20.0, now=NOW)
    assert "Nifty 50 valuation PE ratio" not in {q.query for q in low.queries}


def test_fcnr_contextual_query_when_usd_book():
    plan = intel_live.build_live_plan(
        stock_symbols=[("TINY", 1.0)], has_usd_book=True,
        asset_class_weights={"fcnr": 50.0}, now=NOW)
    named = {q.query: q for q in plan.queries}
    assert "USD INR forecast RBI policy" in named
    assert named["USD INR forecast RBI policy"].kind == "asset_class"
    assert named["USD INR forecast RBI policy"].category == "macro"


def test_rank_by_weight_is_stable_and_pure():
    holdings = [("A", 10.0), ("B", 10.0), ("C", 5.0), "D", ("A", 20.0), ("", 99.0)]
    ranked = intel_live.rank_by_weight(holdings)
    assert ranked == [("A", 20.0), ("B", 10.0), ("C", 5.0), ("D", 0.0)]
    assert intel_live.rank_by_weight([]) == []


# ---------------- query sanitization + zero-record fallback ----------------
def test_sanitize_query_strips_news_breaking_characters():
    # underscores/special chars suppress Google News recall (0-record queries)
    assert intel_live.sanitize_query("GOLD_GOLDFEED") == "GOLD GOLDFEED"
    assert intel_live.sanitize_query("HDFC_MID_CAP") == "HDFC MID CAP"
    assert intel_live.sanitize_query("SGBSEP31II-GB") == "SGBSEP31II GB"
    assert intel_live.sanitize_query("ICICI+Prudential, (Direct)") == \
        "ICICI Prudential Direct"
    assert intel_live.sanitize_query("   A   B   ") == "A B"
    assert intel_live.sanitize_query("...") == ""
    assert intel_live.sanitize_query("") == ""


def test_fund_query_uses_amc_and_category_not_scheme_name():
    plan = intel_live.build_live_plan(
        fund_names=[
            "HDFC Mid-Cap Opportunities Fund - Direct - Growth",
            "GOLD GOLDFEED FUND - Direct - Growth",
            "PARAM MOMENTUM FUND - Direct - Growth",
        ],
        now=NOW)
    named = {q.query: q for q in plan.queries}
    assert named["HDFC mid cap fund"].kind == "fund"
    assert named["HDFC mid cap fund"].identifier == \
        "HDFC Mid-Cap Opportunities Fund - Direct - Growth"
    assert named["HDFC mid cap fund"].identifier_key == "fund_name"
    assert named["gold fund"].identifier == "GOLD GOLDFEED FUND - Direct - Growth"
    # no category keyword -> sanitized short scheme name, exact identifier kept
    assert named["PARAM MOMENTUM"].kind == "fund"
    assert named["PARAM MOMENTUM"].identifier == "PARAM MOMENTUM FUND - Direct - Growth"


def test_simplify_query_falls_back_to_higher_recall_forms():
    assert intel_live.simplify_query("GOLDBEES") == "gold price India"
    assert intel_live.simplify_query("Sovereign Gold Bond") == "gold price India"
    assert intel_live.simplify_query("gold price INR forecast") == "gold price India"
    assert intel_live.simplify_query("Nifty 50 valuation PE ratio") == "Nifty 50 valuation"
    assert intel_live.simplify_query("HDFC") == "HDFC"  # already minimal
    assert intel_live.simplify_query("!!!") == ""


def test_run_live_research_falls_back_when_query_zero_records(monkeypatch, tmp_path, caplog):
    """A 0-record query is retried with a simplified form; the miss is logged."""
    import logging

    def _http_get(url, **kwargs):
        query = (kwargs.get("params") or {}).get("q", "")
        return _ok_response(query)  # echo the query so the parse seam can branch

    monkeypatch.setattr(httpio, "_http_get", _http_get)

    def _fake_parse(text):
        if text == "gold price India":
            return _entries_feed([
                _feed_entry("Gold prices climb to a record in India",
                            published_parsed=(2026, 9, 8, 11, 0, 0, 0, 0, 0))])
        return _entries_feed([])

    with caplog.at_level(logging.INFO, logger="lib.intelligence.live.pipeline"):
        result = intel_live.run_live_research(
            gold_symbols=["GOLDBEES"], facts=_Facts(), now=NOW,
            news_cache=Cache(tmp_path / "news"),
            gateway_cache=Cache(tmp_path / "gw"),
            parse=_fake_parse)
    assert result.status == intel_live.STATUS_OK
    fallback = [r for r in result.cohort.records
                if (r.payload or {}).get("query") == "gold price India"]
    assert fallback, "the simplified fallback query must join the cohort"
    assert any("0 records" in (r.getMessage() or "") for r in caplog.records)
    assert "gold price India" in caplog.text


# ---------------- gnews normalization + cache ----------------
def test_fetch_gnews_normalizes_feed_records(monkeypatch, tmp_path):
    entry = _feed_entry("ETERNAL beats Q2 estimates - MoneyControl")
    monkeypatch.setattr(httpio, "_http_get", lambda url, **kwargs: _ok_response())
    monkeypatch.setattr("lib.intelligence.live.news.feedparser.parse",
                        lambda text: _entries_feed([entry]))
    result = intel_live.fetch_gnews("ETERNAL", "holding",
                                    identifiers=[("ETERNAL", "symbol")],
                                    now=NOW, cache=Cache(tmp_path))
    assert result.status == "ok"
    assert len(result.records) == 1
    rec = result.records[0]
    assert rec.provider == "gnews"
    assert " - MoneyControl" not in rec.title
    assert rec.published_at is not None
    assert rec.reference == "https://example.com/story"
    assert rec.payload["query"] == "ETERNAL"
    assert rec.payload["category"] == "holding"
    assert rec.payload["content_id"]
    assert rec.payload["source_name"] == "MoneyControl"


def test_fetch_gnews_second_call_is_cache_hit(monkeypatch, tmp_path):
    entry = _feed_entry("ETERNAL beats Q2 estimates")
    calls = []

    def _http_get(url, **kwargs):
        calls.append(url)
        return _ok_response()

    monkeypatch.setattr(httpio, "_http_get", _http_get)
    monkeypatch.setattr("lib.intelligence.live.news.feedparser.parse",
                        lambda text: _entries_feed([entry]))
    cache = Cache(tmp_path)
    first = intel_live.fetch_gnews("ETERNAL", "holding", now=NOW, cache=cache)
    second = intel_live.fetch_gnews("ETERNAL", "holding", now=NOW, cache=cache)
    assert len(calls) == 1
    assert second.cache_hit is True
    assert second.records[0].id == first.records[0].id


def test_respects_hourly_rate_limit(monkeypatch, tmp_path):
    entry = _feed_entry("ETERNAL beats Q2 estimates")
    calls = []

    def _http_get(url, **kwargs):
        calls.append(url)
        return _ok_response()

    monkeypatch.setattr(httpio, "_http_get", _http_get)
    monkeypatch.setattr("lib.intelligence.live.news.feedparser.parse",
                        lambda text: _entries_feed([entry]))
    cache = Cache(tmp_path)
    intel_live.fetch_gnews("ETERNAL", "holding", now=NOW, cache=cache)
    assert len(calls) == 1

    inside = intel_live.fetch_gnews(
        "ETERNAL", "holding",
        now=NOW + datetime.timedelta(minutes=45), cache=cache)
    assert len(calls) == 1  # < 1 hour old -> served from cache, no network call
    assert inside.cache_hit is True
    assert inside.reason == "Cache fresh (45 min old) - skipping network call"

    outside = intel_live.fetch_gnews(
        "ETERNAL", "holding",
        now=NOW + datetime.timedelta(minutes=61), cache=cache)
    assert len(calls) == 2  # past the hourly window -> live refresh permitted
    assert outside.cache_hit is False
    assert outside.records[0].retrieved_at == NOW + datetime.timedelta(minutes=61)


# ---------------- identifier labeling ----------------
def test_gnews_identifier_labeling_exact_containment(monkeypatch, tmp_path):
    entry = _feed_entry("ETERNAL profit jumps 10% after strong Q2")
    monkeypatch.setattr(httpio, "_http_get", lambda url, **kwargs: _ok_response())
    monkeypatch.setattr("lib.intelligence.live.news.feedparser.parse",
                        lambda text: _entries_feed([entry]))
    result = intel_live.fetch_gnews("ETERNAL", "holding",
                                    identifiers=[("ETERNAL", "symbol"), ("RELIANCE", "symbol")],
                                    now=NOW, cache=Cache(tmp_path))
    rec = result.records[0]
    assert rec.payload["symbol"] == "ETERNAL"
    assert "RELIANCE" not in rec.payload
    assert rec.payload["matched_identifiers"] == ["ETERNAL"]


def test_gnews_identifier_does_not_false_match(monkeypatch, tmp_path):
    cases = ["ETERNALGLOBE doubles output", "theETERNAL stock drops"]
    for title in cases:
        monkeypatch.setattr("lib.intelligence.live.news.feedparser.parse",
                            lambda text, e=[_feed_entry(title)]: _entries_feed(e))
        result = intel_live.fetch_gnews(title, "holding",
                                        identifiers=[("ETERNAL", "symbol")],
                                        now=NOW, cache=Cache(tmp_path))
        assert result.records[0].payload["matched_identifiers"] == []
    fund = _feed_entry("PARAM MOMENTUM FUND declares dividend")
    monkeypatch.setattr("lib.intelligence.live.news.feedparser.parse",
                        lambda text: _entries_feed([fund]))
    result = intel_live.fetch_gnews("PARAM MOMENTUM", "holding",
                                    identifiers=[("PARAM MOMENTUM FUND", "fund_name")],
                                    now=NOW, cache=Cache(tmp_path))
    assert result.records[0].payload["matched_identifiers"] == ["PARAM MOMENTUM FUND"]


# ---------------- evidence classification ----------------
def test_gnews_record_is_observed_fact_evidence():
    rec = _news_record("ETERNAL", "holding", "ETERNAL jumps", symbol="ETERNAL")
    ev = rec.to_evidence()
    assert ev.provenance.fact_kind == FactKind.FACT
    assert ev.provenance.source_type == SourceType.NEWS
    assert ev.provenance.source_class == SourceClass.C
    assert ev.provenance.source == "gnews"
    assert ev.payload["provider"] == "gnews"


def test_exact_match_relevance_mapping_only():
    index = PortfolioIndex(symbols=frozenset({"ETERNAL"}))
    mapped = _news_record("ETERNAL", "holding", "ETERNAL jumps", symbol="ETERNAL")
    unmapped = _news_record("RELIANCE", "holding", "RELIANCE climbs", symbol="RELIANCE")
    bare = _news_record("Sovereign Gold Bond", "holding", "sgb rally")
    assert assess_relevance(mapped, index).status == "mapped"
    assert assess_relevance(unmapped, index).status == "unmapped"
    # a bare gnews record always carries an entity (the query), so without an
    # exact identifier hit it is unmapped, never "insufficient"
    assert assess_relevance(bare, index).status == "unmapped"


def test_unmapped_news_is_not_promoted(tmp_path):
    bare = _news_record("Sovereign Gold Bond", "holding", "gold rallies on Fed")
    cache = Cache(tmp_path)
    _seed(cache, bare)
    cohort = intel_live.assemble_cohort(plan=_plan_for(bare), cache=cache, now=NOW)
    rows = intel_live.development_rows(
        cohort, index=PortfolioIndex(symbols=frozenset({"ETERNAL"})), now=NOW)
    assert rows[0]["Relevance"] == "unmapped"
    assert rows[0]["Affected"] == "\u2014"


# ---------------- cohort assembly ----------------
def test_duplicate_stories_deduped_by_content_id(tmp_path):
    from lib.intelligence.live import news as live_news
    title = "ETERNAL hits record high"
    shared_cid = live_news._content_id(title)
    r1 = _news_record("ETERNAL", "holding", title, content_id=shared_cid, symbol="ETERNAL")
    r2 = _news_record("Nifty 50", "macro", title, content_id=shared_cid)
    cache = Cache(tmp_path)
    cache.save(live_news.news_cache_key("ETERNAL", "holding"),
               {"metadata": {}, "records": [r1.as_dict()]}, provider="gnews", retrieved_at=NOW)
    cache.save(live_news.news_cache_key("Nifty 50", "macro"),
               {"metadata": {}, "records": [r2.as_dict()]}, provider="gnews", retrieved_at=NOW)
    plan = intel_live.build_live_plan(stock_symbols=["ETERNAL"], now=NOW)
    cohort = intel_live.assemble_cohort(plan=plan, now=NOW, cache=cache,
                                        gateway_cache_dir=tmp_path / "gw")
    assert cohort.record_count == 1
    assert cohort.records[0].payload["symbol"] == "ETERNAL"  # holdings-first wins


def test_cache_roundtrip_and_corruption_skipped(tmp_path):
    cache = Cache(tmp_path)
    rec = _news_record("ETERNAL", "holding", "ETERNAL steady", symbol="ETERNAL")
    _seed(cache, rec)
    plan = intel_live.build_live_plan(stock_symbols=["ETERNAL"], now=NOW)
    cohort = intel_live.assemble_cohort(plan=plan, now=NOW, cache=cache,
                                        gateway_cache_dir=tmp_path / "gw")
    assert cohort.record_count == 1
    assert cohort.records[0].id == rec.id
    cache._path(intel_live.news_cache_key("ETERNAL", "holding")).write_text(
        "{definitely not json", encoding="utf-8")
    corrupt = intel_live.assemble_cohort(plan=plan, now=NOW, cache=cache,
                                         gateway_cache_dir=tmp_path / "gw")
    assert corrupt.record_count == 0  # corrupt bucket skipped, never fabricated
    rows = intel_live.live_status(cache=cache, now=NOW)
    assert any(r["status"] == "corrupt" for r in rows)


def test_freshness_and_staleness(tmp_path):
    fresh = _news_record("ETERNAL", "holding", "fresh headline", symbol="ETERNAL",
                         published_at=NOW)
    cache = Cache(tmp_path)
    _seed(cache, fresh)
    # simulate an old bucket file: the record itself is new but retrieval is stale
    cache.save(intel_live.news_cache_key("ETERNAL", "holding"),
               {"metadata": {}, "records": [fresh.as_dict()]}, provider="gnews",
               retrieved_at=OLD)
    plan = intel_live.build_live_plan(stock_symbols=["ETERNAL"], now=NOW)
    cohort = intel_live.assemble_cohort(plan=plan, now=NOW, cache=cache)
    assert cohort.stale_sources == ("gnews",)
    rows = intel_live.live_status(cache=cache, now=NOW)
    assert all(r["is_stale"] for r in rows if r["status"] == "ok")
    dev = intel_live.development_rows(
        cohort, index=PortfolioIndex(symbols=frozenset({"ETERNAL"})), now=NOW)[0]
    assert dev["Relevance"] == "mapped"
    assert dev["Quality"] >= 0.6  # exact map + fresh published headline

    aged = _news_record("ETERNAL", "holding", "aged headline", symbol="ETERNAL",
                        published_at=NOW - datetime.timedelta(days=10))
    _seed(cache, aged)
    aged_cohort = intel_live.assemble_cohort(plan=plan, now=NOW, cache=cache)
    aged_dev = intel_live.development_rows(
        aged_cohort, index=PortfolioIndex(symbols=frozenset({"ETERNAL"})), now=NOW)
    aged_row = next(r for r in aged_dev if r["Development"] == "aged headline")
    assert aged_row["Quality"] < 0.6  # stale published age penalized


# ---------------- failure degradation ----------------
def test_fetch_failure_degrades_to_stale_cache_or_unavailable(monkeypatch, tmp_path):
    cache = Cache(tmp_path)
    rec = _news_record("ETERNAL", "holding", "stale but valuable", symbol="ETERNAL")
    _seed(cache, rec)
    cache.save(intel_live.news_cache_key("ETERNAL", "holding"),
               {"metadata": {}, "records": [rec.as_dict()]}, provider="gnews",
               retrieved_at=OLD)

    def _boom(url, **kwargs):
        raise ProviderTimeout("provider timed out for " + url)

    monkeypatch.setattr(httpio, "_http_get", _boom)

    no_cache = intel_live.fetch_gnews("RELIANCE", "holding", now=NOW, cache=Cache(tmp_path))
    assert no_cache.status == "unavailable"
    assert no_cache.records == ()

    stale = intel_live.fetch_gnews("ETERNAL", "holding", now=NOW, cache=cache)
    assert stale.status == "ok"
    assert stale.is_stale is True
    assert len(stale.records) >= 1
    assert "stale cache" in (stale.reason or "")


def test_rate_limit_429_degrades(monkeypatch, tmp_path):
    def _http_get(url, **kwargs):
        raise ProviderUnavailable(f"provider returned HTTP 429 for {url}")

    monkeypatch.setattr(httpio, "_http_get", _http_get)
    result = intel_live.fetch_gnews("ETERNAL", "holding", now=NOW, cache=Cache(tmp_path))
    assert result.status == "unavailable"
    assert result.records == ()
    assert "429" in (result.reason or "")


def test_malformed_feed_degrades_gracefully(monkeypatch, tmp_path):
    monkeypatch.setattr(httpio, "_http_get", lambda url, **kwargs: _ok_response())
    monkeypatch.setattr("lib.intelligence.live.news.feedparser.parse",
                        lambda text: _entries_feed([]))
    result = intel_live.fetch_gnews("ETERNAL", "holding", now=NOW, cache=Cache(tmp_path))
    assert result.status == "ok"
    assert result.records == ()


def test_no_credentials_leak_in_failures(monkeypatch, tmp_path):
    monkeypatch.setenv("FRED_API_KEY", "SK-FAKE-123")

    def _http_get(url, **kwargs):
        if "stlouisfed" in url:
            raise ProviderUnavailable(
                "provider returned HTTP 500 for " + url + "?series_id=DEXINUS&api_key=SK-FAKE-123")
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(httpio, "_http_get", _http_get)
    plan = intel_live.build_live_plan(has_usd_book=True, now=NOW)
    result = intel_live.run_live_research(plan=plan, now=NOW,
                                          news_cache=Cache(tmp_path / "news"),
                                          gateway_cache=Cache(tmp_path / "gw"))
    assert result.status == intel_live.STATUS_UNAVAILABLE
    assert result.failures
    for source, reason in result.failures:
        assert "SK-FAKE-123" not in (reason or "")
        assert "api_key=" not in (reason or "")
    assert any("DEXINUS" in source for source, _ in result.failures)


# ---------------- explicit pipeline + no mutation ----------------
def test_run_live_research_explicit_and_no_mutation(monkeypatch, tmp_path):
    entries = [_feed_entry("ETERNAL beats Q2 estimates - MoneyControl")]
    monkeypatch.setattr(httpio, "_http_get", lambda url, **kwargs: _ok_response())
    monkeypatch.setattr("lib.intelligence.live.news.feedparser.parse",
                        lambda text: _entries_feed(entries))
    facts = _Facts(usd=False)
    result = intel_live.run_live_research(stock_symbols=["ETERNAL"], fund_names=[],
                                          gold_symbols=[], facts=facts, now=NOW,
                                          news_cache=Cache(tmp_path / "news"),
                                          gateway_cache=Cache(tmp_path / "gw"))
    assert result.status == intel_live.STATUS_OK
    assert result.cohort.news_records
    assert result.failures == ()
    for ev in result.to_evidence():
        assert ev.provenance.fact_kind == FactKind.FACT
        assert ev.provenance.source_type == SourceType.NEWS
    brief = research.build_research_brief(
        facts=facts, evidence=EvidenceBag(result.to_evidence()), signals=(),
        nav_evidence=(), holdings_evidence=(), gateway_evidence=(), now=NOW)
    assert brief.totals["total_assets"] == 100000.0  # never mutated
    assert brief.totals["total_pnl"] == 20000.0


# ---------------- network-free page-load paths ----------------
def test_network_free_page_load_paths(monkeypatch, tmp_path):
    def _boom(*args, **kwargs):
        raise AssertionError("network call attempted on page load")

    monkeypatch.setattr(httpio, "_http_get", _boom)
    news_cache = Cache(tmp_path / "news")
    gw_cache = Cache(tmp_path / "gw")

    news_rec = _news_record("ETERNAL", "holding", "ETERNAL up", symbol="ETERNAL")
    _seed(news_cache, news_rec)
    fred_rec = SourceRecord(
        id="fred:dexinus:2026-09-07", provider="fred", entity="DEXINUS",
        title="Foreign Exchange Rate: India", retrieved_at=NOW,
        source_class=SourceClass.A, source_type=SourceType.OBSERVED,
        published_at=datetime.datetime(2026, 9, 7),
        payload={"series_id": "DEXINUS", "value": 94.0, "date": "2026-09-07"})
    gw_cache.save("fred:dexinus", {"metadata": {}, "records": [fred_rec.as_dict()]},
                  provider="fred", retrieved_at=NOW)

    plan = intel_live.build_live_plan(stock_symbols=["ETERNAL"], now=NOW)
    cohort = intel_live.load_live_cohort(plan=plan, now=NOW, news_cache=news_cache,
                                         gateway_cache_dir=gw_cache.base_dir)
    assert cohort.record_count == 2
    assert {r.provider for r in cohort.records} == {"gnews", "fred"}
    rows = intel_live.live_status(cache=news_cache, now=NOW)
    assert rows and all(r["status"] == "ok" for r in rows)
    dev = intel_live.development_rows(
        cohort, index=PortfolioIndex(symbols=frozenset({"ETERNAL"})), now=NOW)
    assert any(r["Development"] == "ETERNAL up" and r["Relevance"] == "mapped" for r in dev)


# ---------------- ResearchBrief consumption ----------------
def test_research_brief_consumes_cohort_evidence_no_ai():
    mapped = _news_record("ETERNAL", "holding", "ETERNAL jumps", symbol="ETERNAL")
    macro = _news_record("Nifty 50", "macro", "Sensex closes higher")
    cohort_evidence = tuple(r.to_evidence() for r in (mapped, macro))
    brief = research.build_research_brief(
        facts=_Facts(), evidence=EvidenceBag(cohort_evidence),
        signals=(), nav_evidence=(), holdings_evidence=(),
        gateway_evidence=cohort_evidence, now=NOW,
        portfolio_index=PortfolioIndex(symbols=frozenset({"ETERNAL"})))
    assert brief.evidence_count >= 2
    assert brief.mapped_count >= 1
    assert any(d.category == "news" and d.mapped for d in brief.external)
    assert not any("No news evidence" in g for g in brief.gaps)
    assert brief.synthesis is not None
    assert brief.synthesis.model == "research-deterministic"
    body = " ".join(
        [c.label + " " + (c.note or "") for c in brief.changes]
        + [c.statement + " " + (c.invalidation or "") for c in brief.conclusions]
        + [c.title for c in brief.research_needs]
        + list(brief.gaps)
    ).lower()
    for word in FORBIDDEN_CASHFLOW_WORDS:
        assert word not in body


def test_usd_book_present_detection():
    assert intel_live.usd_book_present(None) is False
    assert intel_live.usd_book_present(_Facts(usd=False)) is False
    assert intel_live.usd_book_present(_Facts(usd=True)) is True