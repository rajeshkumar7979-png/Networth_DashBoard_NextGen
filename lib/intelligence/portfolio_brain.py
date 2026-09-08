# -------------------------------------------------
# Portfolio Intelligence foundation — portfolio brain.
# Thin orchestrator: facts (exposure) + evidence (provenance) + signals are
# assembled into a read-only Briefing whose AI column (synthesis) is produced by
# a ResearchProvider. The default provider is deterministic rule-based synthesis
# — immediate value with zero AI cost. Until a real AI provider is configured and
# registered, synthesis is never "expert opinion"; unsupported claims are
# downgraded and the reason is recorded. Decision-support only: a Briefing
# contains recommendations, never orders.
# -------------------------------------------------
from __future__ import annotations

from datetime import datetime

from lib.intelligence.model import Briefing, INSUFFICIENT_EVIDENCE
from lib.intelligence.provider import (
    DeterministicProvider,
    validate_claims,
)


def build_briefing(*, facts, evidence=None, signals=None, question=None,
                   provider="auto", now=None):
    """Assemble a Briefing from exposure facts + evidence + signals.

    provider:
      "auto"      -> registered provider, falling back to deterministic
      DeterministicProvider-ish instance -> used as-is
      None        -> no AI synthesis at all; synthesis_reason records why
    """
    if now is None:
        now = getattr(facts, "as_of", None) or datetime.now()
    all_facts = facts.all_facts() if hasattr(facts, "all_facts") else tuple(facts)
    all_evidence = tuple(evidence.items) if evidence is not None else ()
    all_signals = tuple(signals) if signals is not None else ()

    as_of = now
    facts_tuple = tuple(all_facts)
    evidence_tuple = tuple(all_evidence)
    signals_tuple = tuple(all_signals)

    if provider is None:
        return Briefing(
            as_of=as_of,
            facts=facts_tuple,
            evidence=evidence_tuple,
            signals=signals_tuple,
            synthesis=None,
            synthesis_reason=INSUFFICIENT_EVIDENCE
            + ": no AI research provider configured.",
        )

    if provider == "auto":
        from lib.intelligence.provider import get_provider
        instance = get_provider() or DeterministicProvider()
    else:
        instance = provider

    reason = None
    try:
        interpretation = instance.synthesize(
            Briefing(as_of=as_of, facts=facts_tuple, evidence=evidence_tuple,
                     signals=signals_tuple),
            question=question,
        )
    except Exception as exc:  # provider failure must never take down the app
        interpretation = None
        reason = f"Research provider unavailable: {type(exc).__name__}: {exc}"
    if interpretation is not None:
        unsupported = validate_claims(interpretation, Briefing(
            as_of=as_of, facts=facts_tuple, evidence=evidence_tuple, signals=signals_tuple))
        if unsupported:
            from dataclasses import replace
            unsup = set(unsupported)
            claims = tuple(
                c if c not in unsup else replace(c, supported=False)
                for c in interpretation.claims
            )
            interpretation = replace(interpretation, claims=claims)
        reason = None
    elif reason is None:
        reason = INSUFFICIENT_EVIDENCE + " (no usable synthesis from provider)."

    return Briefing(
        as_of=as_of,
        facts=facts_tuple,
        evidence=evidence_tuple,
        signals=signals_tuple,
        synthesis=interpretation,
        synthesis_reason=reason,
    )