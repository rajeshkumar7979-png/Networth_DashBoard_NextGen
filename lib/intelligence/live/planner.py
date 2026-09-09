# -------------------------------------------------
# Portfolio-Aware Live Research — research planner.
#
# Derives the bounded set of external targets from the CURRENT portfolio:
#   * one query per held stock symbol (bounded)
#   * one query per held MF fund (bounded, short-name query + full-name identifier)
#   * gold: generic sovereign-gold/gold-ETF coverage plus a per-ETF symbol query
#   * fixed NRI/tax and macro query sets (reused from lib.news — single source)
#   * FRED DEXINUS (INR per USD) ONLY when a USD-denominated (FCNR) book exists
#
# Deterministic and pure (no network, no pandas). Identifiers are exact strings
# from the holdings; mapping to the portfolio index is still exact-match only.
# -------------------------------------------------
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from lib.intelligence.sources.record import utc_now

MAX_STOCK_QUERIES = 6
MAX_FUND_QUERIES = 3

FRED_USD_INR_TARGET = "DEXINUS"
_SGB_PREFIX = "SGB"


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


def _fund_short_query(name: str) -> str:
    return str(name).split(" - ")[0].split(" FUND")[0].strip()


def build_live_plan(*, stock_symbols=(), fund_names=(), gold_symbols=(),
                    has_usd_book: bool = False, now=None) -> ResearchPlan:
    now = now or utc_now()
    queries = []
    seen = set()

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

    for sym in (stock_symbols or ())[:MAX_STOCK_QUERIES]:
        symbol = str(sym).strip()
        if symbol:
            add(symbol, "holding", "holding", identifier=symbol, identifier_key="symbol")

    for name in (fund_names or ())[:MAX_FUND_QUERIES]:
        full = str(name).strip()
        if not full:
            continue
        short = _fund_short_query(full)
        if short:
            add(short, "holding", "fund", identifier=full, identifier_key="fund_name")

    gold_symbols = [str(s).strip() for s in (gold_symbols or ()) if str(s).strip()]
    if gold_symbols:
        add("Sovereign Gold Bond", "holding", "gold")
        add("Gold ETF India", "holding", "gold")
    for symbol in gold_symbols:
        if not symbol.upper().startswith(_SGB_PREFIX):
            add(symbol, "holding", "gold", identifier=symbol, identifier_key="symbol")

    from lib.news import MACRO_QUERIES, NRI_TAX_QUERIES  # lazy: single source of truth

    for query in NRI_TAX_QUERIES:
        add(query, "nri_tax", "nri_tax")
    for query in MACRO_QUERIES:
        add(query, "macro", "macro")

    fred_targets = (FRED_USD_INR_TARGET,) if has_usd_book else ()
    return ResearchPlan(queries=tuple(queries), fred_targets=fred_targets, generated_at=now)