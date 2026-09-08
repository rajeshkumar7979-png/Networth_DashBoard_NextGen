# -------------------------------------------------
# Portfolio Intelligence foundation — provider + portfolio brain tests.
# Deterministic: verifies the ResearchProvider registry, deterministic synthesis,
# claim validation (fabricated numbers are downgraded, never trusted), the
# "no provider -> Insufficient evidence" default, and the moderation gate.
# -------------------------------------------------
import datetime

from lib.intelligence.evidence import EvidenceBag, insufficient_evidence
from lib.intelligence.model import (
    Claim,
    Interpretation,
    INSUFFICIENT_EVIDENCE,
    Recommendation,
)
from lib.intelligence.portfolio_brain import build_briefing
from lib.intelligence.provider import (
    get_provider,
    known_fact_ids,
    moderate,
    register_provider,
    unregister_provider,
    validate_claims,
)
from lib.intelligence.exposure import Coverage

NOW = datetime.datetime.fromisoformat("2026-09-08T13:38:00")


def _facts():
    from lib.intelligence.model import make_fact

    class _F:
        def __init__(self):
            self.as_of = NOW
            self.total_assets = 100000.0
            self.total_invested = 80000.0
            self.total_pnl = 20000.0
            self.coverage = Coverage(10000, 10000, 0, 5, 0, (), 100.0)
            self.underlying = ()
            self._facts = (
                make_fact("Equity", "share_pct", 40.0, "pct", now=NOW, prefix="class"),
                make_fact("Total assets", "current_inr", 100000.0, "INR", now=NOW, prefix="summary"),
            )

        def all_facts(self):
            return self._facts
    return _F()


def _evidence():
    return EvidenceBag(tuple())


def _signal():
    from lib.intelligence.model import Signal
    return Signal(
        id="sig:fx", rule="fx_attribution_unavailable", label="FCNR FX attribution unavailable",
        level="warn", message="USD/INR live rate missing.",
    )


# ---------------- registry ----------------
def test_deterministic_provider_is_registered():
    assert get_provider("deterministic") is not None
    assert get_provider(None) is None


def test_register_provider_then_get():
    class Fake:
        name = "fake"
    register_provider("fake_test", lambda: Fake())
    try:
        assert isinstance(get_provider("fake_test"), Fake)
    finally:
        unregister_provider("fake_test")


# ---------------- deterministic synthesis ----------------
def test_deterministic_synthesis_cites_signals():
    briefing = build_briefing(facts=_facts(), evidence=_evidence(), signals=(_signal(),))
    assert briefing.synthesis is not None
    assert briefing.synthesis.model == "deterministic"
    assert "FCNR" in briefing.synthesis.summary
    assert briefing.synthesis_reason is None
    assert any("USD/INR" in c.text for c in briefing.synthesis.claims)


def test_synthesis_survives_empty_facts():
    class _Empty:
        as_of = NOW
        def all_facts(self):
            return ()
    briefing = build_briefing(facts=_Empty(), evidence=_evidence())
    assert briefing.synthesis is not None
    assert "Insufficient evidence" in briefing.synthesis.summary


# ---------------- insufficient-evidence default ----------------
def test_no_provider_means_insufficient_evidence():
    briefing = build_briefing(facts=_facts(), provider=None)
    assert briefing.synthesis is None
    assert briefing.synthesis_reason == INSUFFICIENT_EVIDENCE + ": no AI research provider configured."


def test_provider_failure_never_crashes_app():
    class Crash:
        name = "crash"
        def synthesize(self, briefing, question=None):
            raise RuntimeError("boom")
    briefing = build_briefing(facts=_facts(), provider=Crash())
    assert briefing.synthesis is None
    assert "boom" in briefing.synthesis_reason


# ---------------- claim validation ----------------
def test_validate_claims_flags_unknown_fact_ids():
    interpretation = Interpretation(
        model="x",
        summary="s",
        claims=(
            Claim(text="ok", fact_ids=("class:equity:share_pct",)),
            Claim(text="fabricated", fact_ids=("made:up:number",)),
        ),
    )
    unknown = validate_claims(interpretation, build_briefing(facts=_facts()))
    assert [c.text for c in unknown] == ["fabricated"]


def test_unsupported_claims_are_downgraded_in_briefing():
    class Lying:
        name = "lying"
        def synthesize(self, briefing, question=None):
            return Interpretation(
                model="lying",
                summary="s",
                claims=(Claim(text="price is 999", fact_ids=("fake:price:inr",)),),
            )
    briefing = build_briefing(facts=_facts(), provider=Lying())
    assert briefing.synthesis is not None
    assert briefing.synthesis.claims[0].supported is False


# ---------------- moderation gate ----------------
def test_moderate_requires_known_fact_ids():
    briefing = build_briefing(facts=_facts())
    good = Recommendation(
        id="r1", action="REBALANCE", target="Equity",
        rationale="underweight", fact_ids=("class:equity:share_pct",),
    )
    bad = Recommendation(
        id="r2", action="SELL", target="XYZ",
        rationale="fabricated", fact_ids=("fake:ticker:inr",),
    )
    assert moderate(good, briefing) is True
    assert moderate(bad, briefing) is False


def test_known_fact_ids_returns_set():
    assert isinstance(known_fact_ids(build_briefing(facts=_facts())), set)


# ---------------- model hydra: evidence marker for the brain ----------------
def test_insufficient_evidence_helper_is_evidence():
    ev = insufficient_evidence(question="Is my equity too low?", now=NOW)
    assert ev.id == "ev:insufficient"
    assert ev.payload["question"] == "Is my equity too low?"


# note: Briefing round-trips dataclasses without dicts
def test_briefing_fields_are_tuple_frozen():
    briefing = build_briefing(facts=_facts(), evidence=_evidence(), signals=(_signal(),))
    assert isinstance(briefing.signals, tuple)
    assert isinstance(briefing.evidence, tuple)
    assert isinstance(briefing.facts, tuple)