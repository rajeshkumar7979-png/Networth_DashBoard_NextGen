# -------------------------------------------------
# Portfolio Intelligence foundation — evidence/provenance tests.
# Deterministic; verifies the typed Evidence model, serialization round-trip,
# provenance classification over news/holdings/drivers/history, and the
# INSUFFICIENT_EVIDENCE marker.
# -------------------------------------------------
import datetime

import pandas as pd

from lib.intelligence.evidence import (
    EvidenceBag,
    build_evidence_bag,
    insufficient_evidence,
    news_evidence,
    holdings_coverage_evidence,
    drivers_evidence,
    history_evidence,
)
from lib.intelligence.model import (
    FactKind,
    INSUFFICIENT_EVIDENCE,
    SourceClass,
    SourceType,
)
from lib.intelligence.exposure import Coverage

NOW = datetime.datetime.fromisoformat("2026-09-08T13:38:00")


def _coverage(pct=100.0):
    return Coverage(
        fund_value_total=10000.0,
        covered_value=10000.0 if pct == 100.0 else pct * 100.0,
        uncovered_value=10000.0 - (10000.0 if pct == 100.0 else pct * 100.0),
        covered_funds=5,
        missing_funds=1,
        missing_names=("Fund X",),
        coverage_pct=pct,
    )


def test_coverage_evidence_classification():
    ev = holdings_coverage_evidence(_coverage(80.0), NOW)
    assert ev.id == "ev:holdings_coverage"
    assert ev.provenance.source_type is SourceType.OFFICIAL_FILING
    assert ev.provenance.source_class is SourceClass.C
    assert ev.provenance.fact_kind is FactKind.CALCULATED_FACT
    assert ev.provenance.confidence == 0.9
    assert ev.payload["coverage_pct"] == 80.0


def test_coverage_evidence_low_confidence_when_partial():
    ev = holdings_coverage_evidence(_coverage(50.0), NOW)
    assert ev.provenance.confidence == 0.4


def test_drivers_evidence_marks_missing_fx():
    ev = drivers_evidence({"missing_fx": True, "residual_ok": True,
                           "attributed": 100.0, "total_pnl": 100.0, "residual": 0.0}, NOW)
    assert ev.id == "ev:drivers"
    assert ev.payload["missing_fx"] is True
    assert ev.provenance.source_type is SourceType.CALCULATED
    assert ev.provenance.source_class is SourceClass.A
    assert ev.provenance.confidence == 0.9


def test_drivers_evidence_none_when_missing():
    assert drivers_evidence(None, NOW) is None


def test_history_evidence_takes_latest_row():
    df = pd.DataFrame([
        {"date": "2026-09-07", "net_worth": 25000000.0, "pnl": 2800000.0,
         "health_score": 60.0, "equity_pct": 18.0, "fd_pct": 58.0},
        {"date": "2026-09-08", "net_worth": 25342848.0, "pnl": 2981658.0,
         "health_score": 65.0, "equity_pct": 18.2, "fd_pct": 57.9},
    ])
    ev = history_evidence(df, NOW)
    assert ev.id == "ev:history"
    assert ev.payload["date"] == "2026-09-08"
    assert ev.payload["net_worth"] == 25342848.0


def test_history_evidence_none_when_empty():
    assert history_evidence(pd.DataFrame(), NOW) is None


def test_news_evidence_carries_query_and_sentiment():
    items = [{"title": "Nifty falls on global cues", "link": "https://x/1",
              "query": "Nifty 50", "category": "macro", "source": "X", "sentiment": "red"}]
    evs = news_evidence(items, NOW)
    assert len(evs) == 1
    assert evs[0].id == "ev:news:0"
    assert evs[0].provenance.source_type is SourceType.NEWS
    assert evs[0].provenance.source_class is SourceClass.C
    assert evs[0].provenance.confidence is None
    assert evs[0].payload["sentiment"] == "red"
    assert evs[0].payload["query"] == "Nifty 50"


def test_insufficient_evidence_marker():
    ev = insufficient_evidence(question="any", now=NOW)
    assert ev.title == INSUFFICIENT_EVIDENCE
    assert ev.provenance.confidence is None
    assert ev.payload["question"] == "any"


def test_build_evidence_bag_assembles_and_serializes(tmp_path):
    bag = build_evidence_bag(
        news_items=[{"title": "Gold price India", "query": "gold price India",
                     "category": "macro", "link": "https://g", "published": "", "sentiment": "neutral"}],
        coverage=_coverage(80.0),
        drivers={"missing_fx": False, "residual_ok": True, "attributed": 1.0,
                 "total_pnl": 1.0, "residual": 0.0},
        history_df=pd.DataFrame([{"date": "2026-09-08", "net_worth": 1.0}]),
        now=NOW,
    )
    assert isinstance(bag, EvidenceBag)
    ids = bag.ids()
    assert "ev:news:0" in ids
    assert "ev:holdings_coverage" in ids
    assert "ev:drivers" in ids

    d = bag.as_dict()
    assert len(d) == len(ids)
    provenance = d[0]["provenance"]
    assert provenance["retrieved_at"] == NOW.isoformat()
    assert provenance["fact_kind"] == "FACT"

    path = tmp_path / "evidence.json"
    bag.to_json(str(path))
    assert path.exists()

    empty = build_evidence_bag(now=NOW)
    assert empty.items == ()