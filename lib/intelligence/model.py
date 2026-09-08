# -------------------------------------------------
# Portfolio Intelligence foundation — shared domain model.
# Pure module: no pandas, no streamlit, no network.
# Every financial number an AI/human reasoner may touch is carried by a Fact
# whose Provenance records its source, retrieval time, entity, confidence and
# whether it is a deterministic calculation or an observed value. Anything that
# is not provable this way is "insufficient evidence", never a fact.
# -------------------------------------------------
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

INSUFFICIENT_EVIDENCE = "Insufficient evidence"

# Constrained decision-support vocabulary for future recommendations.
SUPPORTED_RECOMMENDATION_ACTIONS = (
    "HOLD",
    "RESEARCH",
    "REBALANCE",
    "REDUCE",
    "TOP_UP",
    "MOVE_TO_CASH",
    "EXIT",
)


class FactKind(str, Enum):
    """Taxonomy every output must carry.

    FACT                 observed/declared directly from a data source
    CALCULATED FACT      produced by deterministic computation over facts
    SIGNAL               rule applied over facts + evidence
    AI INTERPRETATION    an AI model's interpretation of facts+evidence
    RECOMMENDATION       decision-support advice (never an order)
    """

    FACT = "FACT"
    CALCULATED_FACT = "CALCULATED FACT"
    SIGNAL = "SIGNAL"
    AI_INTERPRETATION = "AI INTERPRETATION"
    RECOMMENDATION = "RECOMMENDATION"


class SourceClass(str, Enum):
    """A = authoritative (data of record, or deterministic compute over it)
    B = reputable secondary, C = aggregator/convenience, D = experimental."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"


class SourceType(str, Enum):
    CALCULATED = "calculated"
    OBSERVED = "observed"
    OFFICIAL_FILING = "official-filing"
    NEWS = "news"
    AI_INFERRED = "ai-inferred"


def slugify(name):
    s = re.sub(r"[^0-9a-z]+", "_", str(name).lower()).strip("_")
    return s or "item"


@dataclass(frozen=True)
class Provenance:
    source: str
    source_class: SourceClass
    source_type: SourceType
    retrieved_at: datetime
    entity: str
    fact_kind: FactKind
    confidence: Optional[float] = None
    reference: Optional[str] = None
    derived_from: tuple[str, ...] = ()


@dataclass(frozen=True)
class Fact:
    id: str
    kind: FactKind
    entity: str
    metric: str
    value: float
    unit: str
    provenance: Provenance
    label: Optional[str] = None


@dataclass(frozen=True)
class Evidence:
    id: str
    provenance: Provenance
    title: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Signal:
    id: str
    rule: str
    label: str
    level: str  # critical | warn | watch | info
    message: str
    fact_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    invalidation: str = ""
    direction: Optional[str] = None
    confidence: Optional[float] = None


@dataclass(frozen=True)
class Claim:
    text: str
    fact_ids: tuple[str, ...] = ()
    supported: bool = True


@dataclass(frozen=True)
class Interpretation:
    model: str
    summary: str
    claims: tuple[Claim, ...] = ()
    confidence: Optional[float] = None


@dataclass(frozen=True)
class Recommendation:
    id: str
    action: str
    target: str
    rationale: str
    fact_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()
    confidence: Optional[float] = None
    invalidation: str = ""
    hypothesis: bool = False


@dataclass(frozen=True)
class Briefing:
    as_of: datetime
    facts: tuple[Fact, ...]
    evidence: tuple[Evidence, ...]
    signals: tuple[Signal, ...]
    synthesis: Optional[Interpretation] = None
    synthesis_reason: Optional[str] = None
    recommendations: tuple[Recommendation, ...] = ()


def make_fact(entity, metric, value, unit, *, now, fact_kind=FactKind.CALCULATED_FACT,
              source="lib.intelligence", source_class=SourceClass.A,
              source_type=SourceType.CALCULATED, reference=None, confidence=None,
              derived_from=(), label=None, prefix="", fid=None):
    """Build a fact with a deterministic, human-debuggable id."""
    if fid is not None:
        fact_id = fid
    else:
        base = slugify(entity)
        if prefix:
            base = f"{prefix}:{base}"
        fact_id = f"{base}:{slugify(metric)}"
    return Fact(
        id=fact_id,
        kind=fact_kind,
        entity=entity,
        metric=metric,
        value=float(value),
        unit=unit,
        provenance=Provenance(
            source=source,
            source_class=source_class,
            source_type=source_type,
            retrieved_at=now,
            entity=entity,
            fact_kind=fact_kind,
            confidence=confidence,
            reference=reference,
            derived_from=tuple(derived_from),
        ),
        label=label,
    )


def make_evidence(eid, source, source_class, source_type, entity, title, now,
                  fact_kind=FactKind.FACT, reference=None, confidence=None, payload=None):
    return Evidence(
        id=eid,
        provenance=Provenance(
            source=source,
            source_class=source_class,
            source_type=source_type,
            retrieved_at=now,
            entity=entity,
            fact_kind=fact_kind,
            confidence=confidence,
            reference=reference,
        ),
        title=title,
        payload=dict(payload or {}),
    )