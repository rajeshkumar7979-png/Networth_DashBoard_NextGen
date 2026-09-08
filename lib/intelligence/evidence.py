# -------------------------------------------------
# Portfolio Intelligence foundation — evidence/provenance layer.
# Wraps existing producers (lib.news items, holdings coverage meta, lib.drivers
# output, snapshot history rows) into typed Evidence records. Pure module: does
# not import streamlit, does not make network calls; it only restructures data
# the caller already fetched. Anything unsupported is surfaced as
# INSUFFICIENT_EVIDENCE rather than a guessed number.
# -------------------------------------------------
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from lib.intelligence.model import (
    FactKind,
    INSUFFICIENT_EVIDENCE,
    SourceClass,
    SourceType,
    make_evidence,
)

NEWS_SOURCE = "google-news-rss (lib.news)"
HOLDINGS_SOURCE = "data/mf_holdings_cache.json (fund-disclosures/mfdata.in)"
HOLDINGS_REFERENCE = "statutory monthly portfolio disclosures via aggregator cache"
DRIVERS_SOURCE = "lib.drivers.decompose_current"
HISTORY_SOURCE = "data/history.csv (lib.snapshot)"

EVIDENCE_DRIVERS = "ev:drivers"
EVIDENCE_HOLDINGS_COVERAGE = "ev:holdings_coverage"
EVIDENCE_HISTORY = "ev:history"


@dataclass(frozen=True)
class EvidenceBag:
    items: tuple = ()

    def ids(self):
        return tuple(e.id for e in self.items)

    def as_dict(self):
        out = []
        for e in self.items:
            p = e.provenance
            out.append({
                "id": e.id,
                "title": e.title,
                "payload": e.payload,
                "provenance": {
                    "source": p.source,
                    "source_class": p.source_class.value,
                    "source_type": p.source_type.value,
                    "retrieved_at": p.retrieved_at.isoformat(),
                    "entity": p.entity,
                    "fact_kind": p.fact_kind.value,
                    "confidence": p.confidence,
                    "reference": p.reference,
                    "derived_from": list(p.derived_from),
                },
            })
        return out

    def to_json(self, path=None):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2), encoding="utf-8")
        return path


def news_evidence(news_items, now):
    """News items fetched by lib.news.get_portfolio_news -> typed Evidence.

    Each item already carries category/query/source/published and an optional
    deterministic 'sentiment' added by the caller. Confidence is None: a
    headline is context, not a measurable number.
    """
    items = []
    for i, item in enumerate(news_items or ()):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        items.append(make_evidence(
            f"ev:news:{i}",
            source=NEWS_SOURCE,
            source_class=SourceClass.C,
            source_type=SourceType.NEWS,
            entity=str(item.get("query") or "news"),
            title=title,
            now=now,
            fact_kind=FactKind.FACT,
            reference=item.get("link") or item.get("url") or None,
            confidence=None,
            payload={k: item.get(k) for k in
                     ("category", "query", "source", "published", "sentiment", "published_dt")
                     if k in item},
        ))
    return tuple(items)


def holdings_coverage_evidence(coverage, now):
    """One evidence record summarising how much of the fund book is disclosed."""
    c = coverage
    pct = c.coverage_pct
    pct_txt = f"{pct:.0f}%" if pct is not None else "n/a (no disclosures)"
    return make_evidence(
        EVIDENCE_HOLDINGS_COVERAGE,
        source=HOLDINGS_SOURCE,
        source_class=SourceClass.C,
        source_type=SourceType.OFFICIAL_FILING,
        entity="mf-holdings",
        title=f"Holdings disclosure coverage {pct_txt}",
        now=now,
        fact_kind=FactKind.CALCULATED_FACT,
        reference=HOLDINGS_REFERENCE,
        confidence=(0.9 if pct is not None and pct >= 70 else (0.4 if pct is not None else None)),
        payload={
            "fund_value_total": c.fund_value_total,
            "covered_value": c.covered_value,
            "uncovered_value": c.uncovered_value,
            "covered_funds": c.covered_funds,
            "missing_funds": c.missing_funds,
            "coverage_pct": pct,
            "missing_fund_names": list(c.missing_names),
        },
    )


def drivers_evidence(drivers, now):
    """Phase 1B P&L driver reconciliation -> typed Evidence (deterministic)."""
    if not drivers:
        return None
    return make_evidence(
        EVIDENCE_DRIVERS,
        source=DRIVERS_SOURCE,
        source_class=SourceClass.A,
        source_type=SourceType.CALCULATED,
        entity="portfolio",
        title="Current-run P&L driver reconciliation",
        now=now,
        fact_kind=FactKind.CALCULATED_FACT,
        reference="cc_drivers (decompose_current over the canonical register)",
        confidence=0.9 if drivers.get("residual_ok") else 0.6,
        payload={
            "missing_fx": bool(drivers.get("missing_fx")),
            "residual_ok": bool(drivers.get("residual_ok")),
            "attributed": drivers.get("attributed"),
            "total_pnl": drivers.get("total_pnl"),
            "residual": drivers.get("residual"),
        },
    )


def history_evidence(history_df, now):
    """Latest immutable snapshot row -> typed Evidence."""
    latest = None
    if history_df is not None and not history_df.empty and "date" in history_df.columns:
        latest = history_df.sort_values("date").iloc[-1].to_dict()
    if not latest:
        return None
    payload = {k: latest.get(k) for k in
               ("date", "net_worth", "equity_pct", "fd_pct", "pnl", "health_score",
                "drivers_recon_ok", "usd_inr", "snapshot_ts")
               if k in latest}
    return make_evidence(
        EVIDENCE_HISTORY,
        source=HISTORY_SOURCE,
        source_class=SourceClass.A,
        source_type=SourceType.CALCULATED,
        entity="portfolio",
        title=f"History snapshot {payload.get('date', '?')}",
        now=now,
        fact_kind=FactKind.CALCULATED_FACT,
        reference="lib.snapshot.build_snapshot_row / upsert_snapshot",
        confidence=0.9,
        payload=payload,
    )


def insufficient_evidence(question="", now=None, reason=INSUFFICIENT_EVIDENCE):
    """Marker evidence: the answer is not knowable from available data."""
    if now is None:
        now = datetime.now()
    return make_evidence(
        "ev:insufficient",
        source="lib.intelligence.evidence",
        source_class=SourceClass.D,
        source_type=SourceType.CALCULATED,
        entity="portfolio",
        title=reason,
        now=now,
        fact_kind=FactKind.FACT,
        reference=None,
        confidence=None,
        payload={"question": question, "reason": reason},
    )


def build_evidence_bag(*, news_items=None, coverage=None, drivers=None,
                       history_df=None, now=None, question=""):
    """Assemble the evidence for the current portfolio run. Pure restructure."""
    if now is None:
        now = datetime.now()
    items = []
    items.extend(news_evidence(news_items, now))
    if coverage is not None:
        items.append(holdings_coverage_evidence(coverage, now))
    d_ev = drivers_evidence(drivers, now)
    if d_ev is not None:
        items.append(d_ev)
    h_ev = history_evidence(history_df, now)
    if h_ev is not None:
        items.append(h_ev)
    return EvidenceBag(tuple(items))