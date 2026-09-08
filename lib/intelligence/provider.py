# -------------------------------------------------
# Portfolio Intelligence foundation — research-provider abstraction.
# The AI column of a briefing is produced by a ResearchProvider. Deterministic
# rule-based synthesis is always available ("deterministic"); real AI models plug
# in later by registering a provider (config-driven) WITHOUT touching portfolio
# logic. A provider only ever sees a read-only Briefing, and every numeric claim
# it makes must cite fact ids present in that briefing — the validator downgrades
# unsupported claims rather than trusting them.
# -------------------------------------------------
from __future__ import annotations

from typing import Protocol

from lib.intelligence.model import Briefing, Claim, Interpretation, Recommendation

_PROVIDERS = {}


class ResearchProvider(Protocol):
    name: str

    def synthesize(self, briefing, question=None):
        ...

    def moderate(self, recommendation, briefing) -> bool:
        ...


def register_provider(name, factory):
    """Register a provider factory. Factory is called on get_provider()."""
    _PROVIDERS[name] = factory


def unregister_provider(name):
    """Remove a provider (testing/cleanup only)."""
    _PROVIDERS.pop(name, None)


def get_provider(name="deterministic"):
    """Return an instance for `name`, or None if not registered (+None handling)."""
    if name is None:
        return None
    factory = _PROVIDERS.get(name)
    if factory is None:
        return None
    return factory()


def known_fact_ids(briefing):
    return {f.id for f in briefing.facts}


def validate_claims(interpretation, briefing):
    """Return the claims whose fact ids are not present in the briefing.

    A claim referencing an unknown/unsupported number cannot be trusted and is
    marked supported=False (downgrade), never silently accepted.
    """
    known = known_fact_ids(briefing)
    bad = []
    for c in interpretation.claims:
        if c.fact_ids and not set(c.fact_ids).issubset(known):
            bad.append(c)
    return tuple(bad)


def moderate(recommendation: Recommendation, briefing: Briefing) -> bool:
    """A recommendation is only 'evidence-backed' when every cited fact exists."""
    known = known_fact_ids(briefing)
    return set(recommendation.fact_ids).issubset(known)


class DeterministicProvider:
    """Rule-based research provider: summarizes facts+signals into claims.

    Every claim cites the fact ids its signal came from. This is the zero-cost,
    always-on AI column until a real research provider is configured.
    """

    name = "deterministic"

    def synthesize(self, briefing, question=None):
        warns = [s for s in briefing.signals if s.level in ("critical", "warn", "watch")]
        criticals = [s for s in briefing.signals if s.level == "critical"]
        if not briefing.facts:
            return Interpretation(
                model=self.name,
                summary="Insufficient evidence: no portfolio facts available.",
                claims=(),
                confidence=None,
            )
        parts = []
        if criticals:
            parts.append(f"{len(criticals)} critical issue(s): "
                         + "; ".join(s.label for s in criticals[:3]))
        if warns:
            parts.append(f"{len(warns)} watch-level signal(s): "
                         + "; ".join(s.label for s in warns[:4]))
        if not parts:
            parts.append("No elevated portfolio signals in the current run.")
        if question:
            parts.append(f"Prompt recorded: {question}")
        claims = tuple(
            Claim(text=s.message, fact_ids=s.fact_ids, supported=True)
            for s in warns
        )
        return Interpretation(
            model=self.name,
            summary=" ".join(parts),
            claims=claims,
            confidence=0.7,
        )

    def moderate(self, recommendation, briefing) -> bool:
        return moderate(recommendation, briefing)


register_provider("deterministic", DeterministicProvider)