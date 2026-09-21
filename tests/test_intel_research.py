# -------------------------------------------------
# Portfolio Intelligence Research & Synthesis v1 — offline regression suite.
#
# Hermetic: no network, no committed caches — every external-evidence input is
# passed explicitly. Pins evidence-quality scoring, change-summary semantics,
# portfolio-relevance ranking, conclusion derivation (risks / changes /
# external / research needs), claim validation (fabricated fact ids are
# downgraded, never trusted), synthesizer-failure safety, the network-free
# guarantee, and the no-cash-flow vocabulary rule.
# -------------------------------------------------
from __future__ import annotations

import datetime

import pandas as pd

from lib.intelligence.evidence import EvidenceBag, build_evidence_bag
from lib.intelligence.exposure import Coverage
from lib.intelligence.model import (
    SourceClass,
    SourceType,
    make_evidence,
    make_fact,
    Signal,
)
from lib.intelligence.research import (
    TOPIC_EXTERNAL,
    TOPIC_RESEARCH_NEED,
    TOPIC_RISK,
    build_change_summary,
    build_research_brief,
    classify_external,
    delta_from_history,
    gateway_cached_evidence,
    list_source_results,
    score_evidence,
)
from lib.intelligence.sources.cache import Cache
from lib.intelligence.sources.mapping import PortfolioIndex
from lib.intelligence.sources.record import (
    SourceRecord,
    SourceResult,
    unavailable_result,
)

NOW = datetime.datetime.fromisoformat("2026-09-08T13:38:00")


class _Facts:
    def __init__(self):
        self.as_of = NOW
        self.total_assets = 100000.0
        self.total_invested = 80000.0
        self.total_pnl = 20000.0
        self.coverage = Coverage(10000, 10000, 0, 5, 0, (), 100.0)
        self._facts = (
            make_fact("Equity", "share_pct", 40.0, "pct", now=NOW, prefix="class"),
            make_fact("Gold", "share_pct", 5.0, "pct", now=NOW, prefix="class"),
            make_fact("Total assets", "current_inr", 100000.0, "INR", now=NOW,
                      prefix="summary"),
        )

    def all_facts(self):
        return self._facts


def _amfi_nav_evidence():
    rec = SourceRecord(
        id="amfi:nav:INF966L01689", provider="amfi", entity="INF966L01689",
        title="Quant Small Cap Fund", retrieved_at=NOW,
        source_class=SourceClass.A, source_type=SourceType.OBSERVED,
        published_at=datetime.datetime(2026, 9, 6),
        payload={"isin": "INF966L01689", "scheme_code": "120828",
                 "scheme_name": "Quant Small Cap Fund", "amc": "quant Mutual Fund",
                 "category": "Equity Scheme - Small Cap Fund", "nav": 123.45,
                 "nav_date": "06-09-2026"},
    )
    return rec.to_evidence()


def _fred_evidence():
    rec = SourceRecord(
        id="fred:dff:latest", provider="fred", entity="DFF",
        title="Effective Federal Funds Rate", retrieved_at=NOW,
        source_class=SourceClass.A, source_type=SourceType.OBSERVED,
        published_at=datetime.datetime(2026, 9, 7),
        payload={"value": 4.79, "date": "2026-09-07", "series": "DFF"},
    )
    return rec.to_evidence()


def _drivers():
    return {
        "drivers": {"equity_market": 2000.0, "liquid_nav": 0.0, "gold_price": 500.0,
                    "fcnr_interest": 100.0, "fcnr_fx_principal": 25.0,
                    "inr_fd_interest": 75.0},
        "total_pnl": 2700.0, "attributed": 2700.0, "residual": 0.0,
        "residual_bound": 35.5, "residual_ok": True, "fabricated": False,
        "missing_fx": False, "notes": [], "cashflow_measurement": False,
    }


def _history():
    rows = [
        {"date": "2026-09-07", "net_worth": 100000.0,
         "class_current_equity": 40000.0, "class_invested_equity": 30000.0,
         "class_current_liquid": 20000.0, "class_invested_liquid": 20000.0,
         "class_current_fcnr_usd": 20000.0, "class_invested_fcnr_usd": 18000.0,
         "class_current_gold": 10000.0, "class_invested_gold": 9000.0,
         "class_current_inr_fd": 10000.0, "class_invested_inr_fd": 10000.0},
        {"date": "2026-09-08", "net_worth": 102000.0,
         "class_current_equity": 42000.0, "class_invested_equity": 30000.0,
         "class_current_liquid": 20000.0, "class_invested_liquid": 20000.0,
         "class_current_fcnr_usd": 20000.0, "class_invested_fcnr_usd": 18000.0,
         "class_current_gold": 10000.0, "class_invested_gold": 9000.0,
         "class_current_inr_fd": 10000.0, "class_invested_inr_fd": 10000.0},
    ]
    return pd.DataFrame(rows)


def _signals():
    return (
        Signal(
            id="sig:concentration", rule="concentration_top_instruments",
            label="Instrument concentration", level="warn",
            message="Top 5 instruments are 62.0% of assets.",
            fact_ids=("class:equity:share_pct",),
            invalidation="Top-5 instrument share falls below 60%.", confidence=0.8,
        ),
        Signal(
            id="sig:matured_fd", rule="matured_fd",
            label="Matured FD proceeds uncollected", level="critical",
            message="1 FD(s) from Mrs. KAVITA KHANDELWAL have matured — likely "
                    "earning the default rate.",
            invalidation="Workbook updated after proceeds are collected or reinvested.",
            confidence=0.9,
        ),
    )


def _index():
    return PortfolioIndex(isins=frozenset({"INF966L01689"}))


def _full_brief(**overrides):
    facts = _Facts()
    bag = build_evidence_bag(coverage=facts.coverage, drivers=_drivers(),
                             history_df=_history(), now=NOW)
    delta = delta_from_history(_history())
    kwargs = dict(facts=facts, evidence=bag, signals=_signals(),
                  drivers=_drivers(), delta=delta, portfolio_index=_index(),
                  nav_evidence=(_amfi_nav_evidence(),), holdings_evidence=(),
                  gateway_evidence=(_fred_evidence(),), now=NOW)
    kwargs.update(overrides)
    return build_research_brief(**kwargs)


FORBIDDEN_CASHFLOW_WORDS = {
    "sip", "withdrawal", "deposit", "redemption", "xirr", "cash flow",
    " buy ", " sell ",
}


# ---------------- evidence quality scoring ----------------
def test_score_evidence_mapped_authoritative_fresh_scores_high():
    q = score_evidence(_amfi_nav_evidence(), now=NOW, relevance="mapped")
    assert 0.0 <= q.score <= 1.0
    assert q.score >= 0.8
    assert q.fresh is True
    assert q.relevance == "mapped"
    assert q.basis


def test_score_evidence_ordering_and_penalties():
    authoritative_stale = SourceRecord(
        id="a:1", provider="fred", entity="DFF", title="t",
        retrieved_at=datetime.datetime(2026, 8, 30),
        source_class=SourceClass.A, source_type=SourceType.OBSERVED,
        payload={"value": 1}).to_evidence()
    experimental_fresh = SourceRecord(
        id="d:1", provider="x", entity="x", title="t", retrieved_at=NOW,
        source_class=SourceClass.D, source_type=SourceType.OBSERVED,
        payload={"value": 1}).to_evidence()
    q_stale = score_evidence(authoritative_stale, now=NOW, relevance="unmapped")
    q_fresh = score_evidence(experimental_fresh, now=NOW, relevance="unmapped")
    q_mapped = score_evidence(_amfi_nav_evidence(), now=NOW, relevance="mapped")
    q_unmapped = score_evidence(_amfi_nav_evidence(), now=NOW, relevance="unmapped")
    q_insufficient = score_evidence(_amfi_nav_evidence(), now=NOW, relevance="insufficient")
    assert q_stale.score > q_fresh.score  # authoritative beats experimental
    assert q_mapped.score > q_unmapped.score
    assert q_insufficient.score > q_unmapped.score  # no identifier is not a demerit
    assert q_stale.fresh is False
    assert q_fresh.fresh is True


# ---------------- external classification ----------------
def test_classify_external_categories():
    assert classify_external(_amfi_nav_evidence()) == "nav"
    assert classify_external(_fred_evidence()) == "macro"
    holdings = make_evidence(
        "h:1", "fund-disclosures", SourceClass.C, SourceType.OFFICIAL_FILING,
        "INE040A01034", "120828 · HDFC Bank", NOW,
        payload={"scheme_code": "120828"})
    assert classify_external(holdings) == "holdings"
    news = make_evidence(
        "n:1", "google-news-rss (lib.news)", SourceClass.C, SourceType.NEWS,
        "Nifty 50", "headline", NOW, payload={"category": "macro"})
    assert classify_external(news) == "news"
    other = make_evidence("o:1", "somewhere", SourceClass.D, SourceType.OBSERVED,
                          "e", "t", NOW)
    assert classify_external(other) == "other"


# ---------------- source result flattening ----------------
def test_list_source_results_ok_and_unavailable():
    rec = SourceRecord(
        id="amfi:nav:INF966L01689", provider="amfi", entity="INF966L01689",
        title="Quant Small Cap Fund", retrieved_at=NOW,
        source_class=SourceClass.A, source_type=SourceType.OBSERVED,
        payload={"nav": 123.45})
    ok = SourceResult(provider="amfi", status="ok", records=(rec,), retrieved_at=NOW)
    broken = unavailable_result("fred", "no cache")
    evs = list_source_results((ok, broken, None))
    assert len(evs) == 1
    assert evs[0].id == rec.id


# ---------------- gateway cached evidence ----------------
def test_gateway_cached_evidence_reads_and_skips_corrupt(tmp_path):
    rec = SourceRecord(id="fred:dff:1", provider="fred", entity="DFF",
                       title="Effective Federal Funds Rate", retrieved_at=NOW,
                       source_class=SourceClass.A, source_type=SourceType.OBSERVED,
                       payload={"value": 4.79, "series": "DFF"})
    cache = Cache(base_dir=tmp_path)
    cache.save("fred_test", {"records": [rec.as_dict()], "metadata": {"series": "DFF"}},
               provider="fred", retrieved_at=NOW)
    (tmp_path / "corrupt.json").write_text("{not json", encoding="utf-8")

    evs = gateway_cached_evidence(now=NOW, cache_dir=tmp_path)
    assert len(evs) == 1
    assert evs[0].provenance.source == "fred"
    assert evs[0].payload["value"] == 4.79


def test_gateway_cached_evidence_empty_dir_returns_empty(tmp_path):
    assert gateway_cached_evidence(now=NOW, cache_dir=tmp_path) == ()


# ---------------- snapshot delta ----------------
def test_delta_from_history_enriched_and_edge_cases():
    delta = delta_from_history(_history())
    assert delta is not None and delta["available"] is True
    assert delta["totals"]["invested_basis_change"] == 0.0
    assert delta["totals"]["market_valuation_change"] == 2000.0
    assert delta["totals"]["delta_current"] == 2000.0
    assert delta_from_history(_history().head(1)) is None
    assert delta_from_history(pd.DataFrame()) is None
    assert delta_from_history(None) is None
    assert delta_from_history(pd.DataFrame({"date": ["2026-09-08"]})) is None


# ---------------- change summary ----------------
def test_build_change_summary_drivers_only():
    changes = build_change_summary(drivers=_drivers(), delta=None)
    labels = [c.label for c in changes]
    assert "Equity (stocks + non-liquid MF) P&L" in labels
    assert any(c.kind == "total" and c.amount == 2700.0 for c in changes)
    assert all(not c.cashflow_measurement for c in changes)

    fx = _drivers()
    fx["missing_fx"] = True
    fx_changes = build_change_summary(drivers=fx)
    assert any(c.kind == "insufficient" and "USD/INR" in c.note for c in fx_changes)

    resid = _drivers()
    resid["residual"] = 3.2
    r_changes = build_change_summary(drivers=resid)
    assert any(c.kind == "rounding_residual" and c.amount == 3.2 for c in r_changes)


def test_build_change_summary_with_delta():
    delta = delta_from_history(_history())
    changes = build_change_summary(drivers=_drivers(), delta=delta)
    kinds = [c.kind for c in changes]
    assert "invested_basis_change" in kinds
    assert "market_valuation_change" in kinds
    assert "class_delta" in kinds
    ib = next(c for c in changes if c.kind == "invested_basis_change")
    assert ib.amount == 0.0
    assert "NOT a cash-flow measurement" in ib.note


def test_build_change_summary_legacy_delta():
    legacy = {"available": False, "unattributed_abs": 5000.0,
              "reason": "Prior snapshot is legacy (pre-Phase 1B) without a class breakdown."}
    changes = build_change_summary(drivers=None, delta=legacy)
    assert any(c.kind == "insufficient" and "legacy" in c.note.lower() for c in changes)


# ---------------- full research brief ----------------
def test_build_research_brief_full():
    brief = _full_brief()
    assert brief.totals["total_assets"] == 100000.0
    assert brief.totals["total_pnl"] == 20000.0
    assert brief.changes
    assert brief.external and brief.external[0].mapped
    assert brief.risks
    assert brief.research_needs
    assert brief.gaps
    assert any("unmapped macro" in g for g in brief.gaps)
    assert brief.synthesis is not None
    assert brief.synthesis.model == "research-deterministic"
    assert brief.synthesis.confidence is not None
    assert brief.synthesis_reason is None
    assert all(c.supported for c in brief.synthesis.claims)
    assert any(c.topic == TOPIC_EXTERNAL for c in brief.conclusions)
    assert any(c.topic == TOPIC_RISK for c in brief.conclusions)
    assert any(c.topic == TOPIC_RESEARCH_NEED for c in brief.conclusions)
    # mapped development is ranked first and cited by an external conclusion
    assert brief.external[0].evidence.id == "amfi:nav:INF966L01689"


def test_rank_external_mapped_first_and_matched():
    brief = _full_brief()
    assert brief.mapped_count == 1
    assert brief.external[0].headline.endswith("matches INF966L01689")


def test_every_conclusion_has_invalidation_and_strength():
    brief = _full_brief()
    assert all(c.invalidation.strip() for c in brief.conclusions)
    assert all(c.strength in ("strong", "moderate", "weak", "insufficient")
               for c in brief.conclusions)


def test_research_brief_downgrades_unsupported_claims():
    lying = Signal(id="sig:lying", rule="lying", label="Lying signal", level="warn",
                   message="Makes up a number.", fact_ids=("fake:made:up",),
                   confidence=0.9)
    brief = build_research_brief(facts=_Facts(), evidence=EvidenceBag(()),
                                 signals=(lying,), nav_evidence=(), holdings_evidence=(),
                                 gateway_evidence=(), now=NOW)
    assert brief.risks
    risk_claims = [c for c in brief.synthesis.claims if c.text.startswith("[risk]")]
    assert any(not c.supported for c in risk_claims)


def test_research_synthesizer_failure_does_not_raise():
    class Crash:
        name = "crash"

        def synthesize(self, research, question=None):
            raise RuntimeError("boom")

    brief = build_research_brief(facts=_Facts(), evidence=EvidenceBag(()), signals=(),
                                 nav_evidence=(), holdings_evidence=(),
                                 gateway_evidence=(), synthesizer=Crash(), now=NOW)
    assert brief.synthesis is None
    assert "boom" in (brief.synthesis_reason or "")


def test_no_cashflow_vocabulary_across_brief():
    brief = _full_brief()
    text = " ".join(
        [c.label + " " + (c.note or "") for c in brief.changes]
        + [c.statement + " " + (c.invalidation or "") for c in brief.conclusions]
        + [c.title for c in brief.research_needs]
        + list(brief.gaps)
    ).lower()
    for word in FORBIDDEN_CASHFLOW_WORDS:
        assert word not in text, f"forbidden word '{word}' leaked into research text"


def test_research_brief_network_free(monkeypatch):
    import lib.intelligence.sources.httpio as httpio

    def _boom(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(httpio, "_http_get", _boom)
    monkeypatch.setattr(httpio, "_response_json", _boom)
    brief = build_research_brief(facts=_Facts(), evidence=EvidenceBag(()), signals=(),
                                 drivers=_drivers(), delta=None, portfolio_index=None,
                                 nav_evidence=(), holdings_evidence=(),
                                 gateway_evidence=(), now=NOW)
    assert brief.synthesis is not None
    assert any("No comparable prior snapshot" in g for g in brief.gaps)
    assert any("No external provider records" in g for g in brief.gaps)


def test_research_brief_without_evidence_is_still_usable():
    brief = build_research_brief(facts=_Facts(), evidence=EvidenceBag(()), signals=(),
                                 nav_evidence=(), holdings_evidence=(),
                                 gateway_evidence=(), now=NOW)
    assert brief.synthesis is not None
    assert brief.evidence_count == 0
    assert brief.mapped_count == 0