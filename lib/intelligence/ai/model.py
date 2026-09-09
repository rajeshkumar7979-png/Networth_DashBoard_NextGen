# AI Research Provider v1 — output model (provider-neutral dataclasses).
#
# These types describe the *interpretation result* of an AI research call.
# They deliberately reuse the existing intelligence vocabulary (Claim /
# Interpretation / validate_claims) for the final synthesis; they add only
# what a structured AI answer needs: per-finding evidence refs, grounding
# status, and an explicit status envelope so the caller knows exactly why a
# call produced no interpretation.
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from lib.intelligence.model import Interpretation

# AIOutcome.status values.
STATUS_OK = "ok"
STATUS_NOT_CONFIGURED = "not_configured"
STATUS_INSUFFICIENT = "insufficient_evidence"
STATUS_FAILED = "failed"
STATUS_MALFORMED = "malformed"

LABEL_NOT_CONFIGURED = "AI provider not configured"
LABEL_INSUFFICIENT = "Insufficient evidence"
LABEL_FAILED = "AI research unavailable"
LABEL_MALFORMED = "Malformed AI response"


@dataclass(frozen=True)
class AIFinding:
    """One structured finding produced by the model, section-tagged.

    `grounded` is the deterministic verdict about the finding's references:
    every cited evidence id must exist in the supplied context set, and a
    `fact`-kind finding must cite at least one evidence id. It is NEVER set by
    the model — only by lib.intelligence.ai.validator.
    """

    section: str  # key_findings | risks | opportunities | research_needs
    text: str
    evidence_ids: tuple[str, ...] = ()
    kind: str = "interpretation"  # fact | interpretation
    fact_ids: tuple[str, ...] = ()  # inherited from matched deterministic conclusions
    grounded: bool = True
    downgrade_reason: Optional[str] = None


@dataclass(frozen=True)
class AIAssessment:
    """Validated, grounded interpretation from the AI provider."""

    overall_assessment: str
    confidence: Optional[float]
    uncertainty: str
    findings: tuple[AIFinding, ...]
    invalidation_conditions: tuple[str, ...]
    limitations: tuple[str, ...]
    provider: Optional[str]
    model: Optional[str]
    created_at: datetime
    latency_ms: float
    downgrades: tuple[str, ...] = ()
    requested_format: str = "json_schema"
    inference_meta: dict = field(default_factory=dict)
    synthesis: Optional[Interpretation] = None


@dataclass(frozen=True)
class AIOutcome:
    """Envelope for every AI research attempt — success or controlled failure.

    `fallback_used` is True whenever the caller should rely on the
    deterministic ResearchBrief.synthesis instead of this interpretation.
    """

    status: str
    created_at: datetime
    assessment: Optional[AIAssessment] = None
    reason: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    fallback_used: bool = False
    evidence_catalog_count: int = 0
    inference_meta: dict = field(default_factory=dict)

    @property
    def status_label(self) -> str:
        return {
            STATUS_OK: "OK",
            STATUS_NOT_CONFIGURED: LABEL_NOT_CONFIGURED,
            STATUS_INSUFFICIENT: LABEL_INSUFFICIENT,
            STATUS_FAILED: LABEL_FAILED,
            STATUS_MALFORMED: LABEL_MALFORMED,
        }.get(self.status, self.status)