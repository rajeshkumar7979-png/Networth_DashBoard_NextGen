# -------------------------------------------------
# Portfolio-Aware Live Research — research planner.
#
# Derives the bounded set of external targets from the CURRENT portfolio:
#   * one query per held stock symbol, ranked by portfolio weight (bounded)
#   * one query per held MF fund, ranked by portfolio weight (bounded; short-name
#     query + full-name identifier)
#   * gold: a sovereign-gold query only when an SGB is actually held, a per-ETF
#     symbol query for each non-SGB gold holding, and one INR gold-price query
#   * asset-class contextual queries, emitted only when the exposure exists:
#       FCNR (USD) book        -> "USD INR forecast RBI policy"
#       gold held              -> "gold price INR forecast"
#       equity share > 30%     -> "Nifty 50 valuation PE ratio"
#   * fixed NRI/tax and macro query sets (reused from lib.news — single source)
#   * FRED DEXINUS (INR per USD) ONLY when a USD-denominated (FCNR) book exists
#
# The portfolio-derived queries are capped at MAX_PORTFOLIO_QUERIES and
# prioritized by portfolio weight (highest current value first). The NRI/tax and
# macro policy sets are added on top and are deliberately NOT crowded out by
# holdings — they are the NRI-specific differentiator (see lib.news).
#
# Deterministic and pure (no network, no pandas). Identifiers are exact strings
# from the holdings; mapping to the portfolio index is still exact-match only.
# -------------------------------------------------
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from lib.intelligence.sources.record import utc_now

MAX_STOCK_QUERIES = 5
MAX_FUND_QUERIES = 5
MAX_PORTFOLIO_QUERIES = 6

FRED_USD_INR_TARGET = "DEXINUS"
_SGB_PREFIX = "SGB"

# Query hygiene: Google News RSS phrase-matches the raw query; underscores,
# plus signs and punctuation tokenize poorly and suppress recall (observed:
# "GOLD_GOLDFEED"/"HDFC_MID_CAP" return zero records, "GOLD GOLDFEED" finds
# stories). Everything below is deterministic and pure.
_MAX_QUERY_LENGTH = 80
_QUERY_UNSAFE = re.compile(r"[^0-9A-Za-z\s]+")
_QUERY_SPACES = re.compile(r"\s+")

# Known Indian fund-houses, longest-first so "Aditya Birla Sun Life" wins over
# "Aditya Birla". Used only to build a human/news-friendly query text; the
# exact fund identifier is carried untouched for mapping.
_FUND_AMCS = tuple(sorted((
    "Aditya Birla Sun Life", "Aditya Birla", "Mahindra Manulife",
    "ICICI Prudential", "Motilal Oswal", "Morgan Stanley", "Parag Parikh",
    "Kotak Mahindra", "Canara Robeco", "JP Morgan", "Goldman Sachs",
    "BNP Paribas", "JM Financial", "WhiteOak Capital", "White Oak",
    "360 ONE", "360 One", "Mirae Asset", "Franklin", "Edelweiss",
    "Sundaram", "Invesco", "Principal", "Reliance", "Tata", "HDFC", "SBI",
    "ICICI", "Axis", "Kotak", "Nippon", "UTI", "DSP", "Quant", "Mirae",
    "IDFC", "PGIM", "HSBC", "Baroda", "IIFL", "Samco", "Shriram", "Navi",
    "Bandhan", "Bajaj", "Union", "JM", "ITI", "Muthoot", "Birla",
), key=len, reverse=True))

# Category keywords -> query label. Search order matters: the most specific
# phrase ("balanced advantage", "money market") precedes the bare words.
_FUND_CATEGORY_WORDS = (
    ("balanced advantage", "balanced advantage"),
    ("money market", "money market"),
    ("corporate bond", "corporate bond"),
    ("short duration", "short duration"), ("short term", "short duration"),
    ("long duration", "long duration"), ("long term", "long duration"),
    ("multi cap", "multi cap"), ("multicap", "multi cap"),
    ("flexi cap", "flexi cap"), ("flexicap", "flexi cap"),
    ("large cap", "large cap"), ("largecap", "large cap"),
    ("mid cap", "mid cap"), ("midcap", "mid cap"),
    ("small cap", "small cap"), ("smallcap", "small cap"),
    ("micro cap", "micro cap"),
    ("gold", "gold"), ("silver", "silver"), ("elss", "ELSS"),
    ("nifty", "index"), ("sensex", "index"), ("index", "index"),
    ("overnight", "overnight"), ("gilt", "gilt"), ("liquid", "liquid"),
    ("hybrid", "hybrid"), ("equity", "equity"), ("banking", "banking"),
    ("dividend", "dividend"), ("value", "value"), ("focused", "focused"),
)

# Contextual asset-class queries. Emitted only when the exposure is present.
ASSET_CLASS_QUERIES = {
    "fcnr": "USD INR forecast RBI policy",
    "gold": "gold price INR forecast",
    "equity": "Nifty 50 valuation PE ratio",
}
EQUITY_CONTEXT_MIN_PCT = 30.0


@dataclass(frozen=True)
class NewsQuery:
    query: str
    category: str
    kind: str
    identifier: str = ""
    identifier_key: str = ""

    def is_identified(self) -> bool:
        return bool(self.identifier and self.identifier_key)


@dataclass(frozen=True)
class ResearchPlan:
    queries: tuple[NewsQuery, ...] = ()
    fred_targets: tuple[str, ...] = ()
    generated_at: Optional[datetime] = None

    @property
    def query_count(self) -> int:
        return len(self.queries)

    @property
    def fred_count(self) -> int:
        return len(self.fred_targets)


def _to_weight(value) -> float:
    """Finite, non-negative weight; anything else degrades to 0.0."""
    try:
        weight = float(value)
    except (TypeError, ValueError):
        return 0.0
    return weight if weight > 0 and math.isfinite(weight) else 0.0


def _holding_pair(item) -> tuple[str, float]:
    """Accept a plain name or a (name, weight) pair; never raises."""
    if isinstance(item, (tuple, list)) and len(item) == 2:
        return str(item[0]).strip(), _to_weight(item[1])
    return str(item).strip(), 0.0


def rank_by_weight(holdings) -> list[tuple[str, float]]:
    """Deterministically rank holdings by descending portfolio weight.

    Accepts an iterable of names or ``(name, weight)`` pairs. Duplicate names
    are collapsed (keeping the maximum weight, first-seen order as tiebreak),
    blank names are dropped, and ties keep their original relative order, so
    the result is reproducible across runs. Pure; never raises.
    """
    weights: dict[str, float] = {}
    order: list[str] = []
    for item in holdings or ():
        name, weight = _holding_pair(item)
        if not name:
            continue
        if name not in weights:
            weights[name] = weight
            order.append(name)
        elif weight > weights[name]:
            weights[name] = weight
    order.sort(key=lambda name: -weights[name])  # stable: ties keep input order
    return [(name, weights[name]) for name in order]


def _fund_short_query(name: str) -> str:
    return str(name).split(" - ")[0].split(" FUND")[0].strip()


def sanitize_query(text) -> str:
    """Normalize a holding-derived string into a Google-News-safe query.

    Google News RSS phrase-matches the query; underscores, plus signs and
    other punctuation suppress recall (observed: 'GOLD_GOLDFEED' and
    'HDFC_MID_CAP' return zero records while the space-separated forms find
    stories). Collapse every non-alphanumeric run to a single space, squash
    whitespace, and bound the length. Deterministic and pure — case is
    preserved (it is insignificant to the news search but keeps cache keys and
    tests readable).
    """
    value = str(text or "").strip()
    value = _QUERY_UNSAFE.sub(" ", value)
    value = _QUERY_SPACES.sub(" ", value).strip()
    return value[:_MAX_QUERY_LENGTH].strip()


def _split_amc(scheme: str) -> tuple[Optional[str], str]:
    """Return (amc_name, remainder) when the scheme starts with a known AMC."""
    lowered = str(scheme).lower()
    for amc in _FUND_AMCS:
        if lowered.startswith(amc.lower()):
            tail = str(scheme)[len(amc):].strip(" -")
            return amc, tail
    return None, str(scheme)


def _detect_category(text: str) -> Optional[str]:
    # Scheme names hyphenate category words ("Mid-Cap"); normalize any
    # non-alphanumeric run to a space before matching keywords.
    lowered = re.sub(r"[^0-9a-z]+", " ", str(text or "").lower())
    for keyword, label in _FUND_CATEGORY_WORDS:
        normalized = re.sub(r"[^0-9a-z]+", " ", keyword.lower()).strip()
        if normalized and normalized in lowered:
            return label
    return None


def _fund_query(full_name: str) -> str:
    """Derive a compact, news-friendly query for one fund holding.

    Prefers "AMC + category" (e.g. 'HDFC mid cap fund') over the long scheme
    name ("HDFC Mid-Cap Opportunities Fund - Direct - Growth"). When no
    category can be extracted, falls back to the sanitized short scheme name
    ("PARAM MOMENTUM FUND - Direct - Growth" -> "PARAM MOMENTUM"). The exact
    fund name stays available as the query's ``identifier`` for mapping.
    """
    scheme = str(full_name or "").split(" - ")[0].strip()
    if not scheme:
        return ""
    amc, remainder = _split_amc(scheme)
    category = _detect_category(remainder or scheme)
    if category:
        if amc:
            return sanitize_query(f"{amc} {category} fund")
        return sanitize_query(f"{category} fund")
    return sanitize_query(_fund_short_query(full_name))


def simplify_query(query: str, kind: str = "") -> str:
    """Zero-record fallback: a simpler, higher-recall version of a news query.

    Used when a planned query returns no records: commodity holdings collapse
    to their price headline ('GOLD...' -> 'gold price India'), and any
    multi-word query shrinks to its first three words. Returns '' when the
    query is already minimal. Deterministic and pure.
    """
    base = sanitize_query(query)
    if not base:
        return ""
    lowered = base.lower()
    for token in ("gold", "silver"):
        if token in lowered:
            return f"{token} price India"
    words = base.split()
    if len(words) > 3:
        return " ".join(words[:3])
    return base


def build_live_plan(*, stock_symbols=(), fund_names=(), gold_symbols=(),
                    has_usd_book: bool = False, equity_pct=None,
                    asset_class_weights=None, now=None) -> ResearchPlan:
    """Build the bounded research plan from the current portfolio.

    ``stock_symbols``/``fund_names`` accept either plain names or
    ``(name, weight)`` pairs; when weights are supplied the highest-value
    holdings win the ``MAX_PORTFOLIO_QUERIES`` slots. ``equity_pct`` enables the
    equity contextual query above ``EQUITY_CONTEXT_MIN_PCT``. ``asset_class_weights``
    (keys ``fcnr``/``gold``/``equity``) is the priority weight for the asset-class
    queries; it defaults to 0.0 (stable, insertion-ordered) when omitted.
    """
    now = now or utc_now()
    queries: list[NewsQuery] = []
    seen: set[tuple[str, str]] = set()

    def add(query, category, kind, identifier="", identifier_key=""):
        key = (str(query or "").strip().lower(), category)
        if not key[0] or key in seen:
            return
        seen.add(key)
        queries.append(NewsQuery(
            query=str(query).strip(),
            category=category,
            kind=kind,
            identifier=identifier,
            identifier_key=identifier_key,
        ))

    weights = dict(asset_class_weights or {})
    gold_weight = _to_weight(weights.get("gold"))
    fcnr_weight = _to_weight(weights.get("fcnr"))
    equity_weight = _to_weight(equity_pct) if "equity" not in weights \
        else _to_weight(weights.get("equity"))

    # (priority, insertion_index, kwargs) — insertion index keeps ties stable.
    candidates: list[tuple[float, int, dict]] = []

    def candidate(weight, query, category, kind, identifier="", identifier_key=""):
        candidates.append((_to_weight(weight), len(candidates), {
            "query": query, "category": category, "kind": kind,
            "identifier": identifier, "identifier_key": identifier_key,
        }))

    for name, weight in rank_by_weight(stock_symbols)[:MAX_STOCK_QUERIES]:
        query = sanitize_query(name)
        if not query:
            continue
        candidate(weight, query, "holding", "holding",
                  identifier=name, identifier_key="symbol")

    for full, weight in rank_by_weight(fund_names)[:MAX_FUND_QUERIES]:
        short = _fund_query(full)
        if short:
            candidate(weight, short, "holding", "fund",
                      identifier=full, identifier_key="fund_name")

    gold_symbols = [str(s).strip() for s in (gold_symbols or ()) if str(s).strip()]
    if gold_symbols:
        sgb = [s for s in gold_symbols if s.upper().startswith(_SGB_PREFIX)]
        etfs = [s for s in gold_symbols if not s.upper().startswith(_SGB_PREFIX)]
        if sgb:
            candidate(gold_weight, sanitize_query("Sovereign Gold Bond"),
                      "holding", "gold")
        for symbol in etfs:
            query = sanitize_query(symbol)
            if not query:
                continue
            candidate(gold_weight, query, "holding", "gold",
                      identifier=symbol, identifier_key="symbol")
        candidate(gold_weight, ASSET_CLASS_QUERIES["gold"], "macro", "asset_class")

    if has_usd_book:
        candidate(fcnr_weight, ASSET_CLASS_QUERIES["fcnr"], "macro", "asset_class")
    if equity_pct is not None and _to_weight(equity_pct) > EQUITY_CONTEXT_MIN_PCT:
        candidate(equity_weight, ASSET_CLASS_QUERIES["equity"], "macro", "asset_class")

    # Highest portfolio weight first; ties keep insertion order (stable sort).
    candidates.sort(key=lambda item: -item[0])
    selected = 0
    for _weight, _idx, kwargs in candidates:
        if selected >= MAX_PORTFOLIO_QUERIES:
            break
        before = len(queries)
        add(**kwargs)
        if len(queries) > before:
            selected += 1

    from lib.news import MACRO_QUERIES, NRI_TAX_QUERIES  # lazy: single source of truth

    for query in NRI_TAX_QUERIES:
        add(query, "nri_tax", "nri_tax")
    for query in MACRO_QUERIES:
        add(query, "macro", "macro")

    fred_targets = (FRED_USD_INR_TARGET,) if has_usd_book else ()
    return ResearchPlan(queries=tuple(queries), fred_targets=fred_targets, generated_at=now)
