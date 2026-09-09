# AI Research Provider v1 — grounding and claim validation.
#
# Two deterministic gates run on every AI answer:
#   1. Evidence grounding: every evidence id cited by a finding must exist in
#      the supplied context allow-list, and a 'fact'-kind finding must cite at
#      least one evidence id. Unknown/missing refs downgrade the finding
#      (grounded=False) — it is kept for transparency but never shown as fact.
#   2. Existing intelligence validation: findings are converted to the standard
#      Interpretation/Claim shape and run through provider.validate_claims, so
#      any claim that references an unknown fact id is downgraded too.
# This reuses the existing validation framework — no parallel provenance system.
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable, Optional

from lib.intelligence.model import Briefing, Claim, Interpretation
from lib.intelligence.provider import validate_claims
from lib.intelligence.ai.model import AIAssessment


def known_evidence_ids(brief, extra: Iterable[str] = ()) -> frozenset:
    """Every evidence id the model is allowed to cite for this brief."""
    allowed = set(extra)
    for dev in getattr(brief, "external", ()) or ():
        allowed.add(dev.evidence.id)
    for c in getattr(brief, "conclusions", ()) or ():
        allowed.update(c.evidence_ids)
    return frozenset(allowed)


def ground_assessment(assessment: AIAssessment,
                      allowed_ids: Iterable[str]) -> AIAssessment:
    """Mark findings whose evidence refs cannot be verified as ungrounded.

    Downgrades carry an explicit human-readable reason; nothing is silently
    deleted.
    """
    allowed = frozenset(allowed_ids)
    downgrades = list(assessment.downgrades)
    findings = []
    for index, finding in enumerate(assessment.findings):
        unknown = sorted(
            e for e in finding.evidence_ids if e not in allowed)
        reason = None
        grounded = True
        if unknown:
            grounded = False
            reason = (f"[{index}] {finding.section} cites unknown evidence "
                      f"id(s) {unknown} — downgraded.")
        elif finding.kind == "fact" and not finding.evidence_ids:
            grounded = False
            reason = (f"[{index}] {finding.section} is a fact-kind claim with "
                      "no evidence reference — downgraded.")
        if reason:
            downgrades.append(reason)
        findings.append(replace(finding, grounded=grounded,
                                downgrade_reason=reason))
    return replace(assessment, findings=tuple(findings),
                   downgrades=tuple(downgrades))


def inherit_fact_ids(assessment: AIAssessment, conclusions=()) -> AIAssessment:
    """Attach deterministic fact ids to findings that echo a conclusion.

    A finding matches a conclusion when it cites at least one of the same
    evidence ids. Inherited fact ids make the subsequent validate_claims pass
    meaningful (claims cite deterministically-known facts), and are purely
    derived — the model does not invent them.
    """
    by_evidence: dict = {}
    for c in conclusions or ():
        for ev in getattr(c, "evidence_ids", ()) or ():
            by_evidence.setdefault(ev, set()).update(c.fact_ids or ())
    if not by_evidence:
        return assessment
    findings = []
    for finding in assessment.findings:
        inherited = set()
        for ev in finding.evidence_ids:
            inherited.update(by_evidence.get(ev, ()))
        if inherited:
            merged = tuple(sorted(inherited))
            findings.append(
                replace(finding, fact_ids=merged))
        else:
            findings.append(finding)
    return replace(assessment, findings=tuple(findings))


def build_synthesis(assessment: AIAssessment) -> Interpretation:
    """Convert a grounded assessment into the standard Interpretation shape."""
    if assessment.provider and assessment.model:
        model = f"ai:{assessment.provider}:{assessment.model}"
    elif assessment.provider:
        model = f"ai:{assessment.provider}"
    else:
        model = "ai"
    claims = tuple(
        Claim(text=f"[{f.section}] {f.text}",
              fact_ids=f.fact_ids,
              supported=f.grounded)
        for f in assessment.findings)
    return Interpretation(
        model=model,
        summary=assessment.overall_assessment,
        claims=claims,
        confidence=assessment.confidence,
    )


def validate_assessment_claims(
        assessment: AIAssessment,
        *,
        facts: Iterable = (),
        evidence: Iterable = (),
        now: Optional[datetime] = None) -> AIAssessment:
    """Run the produced Interpretation through the existing validate_claims.

    Claims citing unknown fact ids are downgraded (supported=False) and a
    reason is recorded. facts/evidence are whatever the deterministic layer
    has already built (ExposureFacts + EvidenceBag items).
    """
    synthesis = build_synthesis(assessment)
    briefing = Briefing(
        as_of=now or assessment.created_at,
        facts=tuple(facts),
        evidence=tuple(evidence),
        signals=(),
    )
    unsupported = validate_claims(synthesis, briefing)
    downgrades = list(assessment.downgrades)
    if unsupported:
        blocked = tuple({c.text for c in unsupported})
        claims = tuple(
            c if c not in set(unsupported) else replace(c, supported=False)
            for c in synthesis.claims)
        synthesis = replace(synthesis, claims=claims)
        downgrades.append(
            f"{len(unsupported)} claim(s) failed validate_claims "
            f"(unknown fact ids): {list(blocked)[:2]}…")
    return replace(assessment, synthesis=synthesis, downgrades=tuple(downgrades))


def deterministic_fallback(brief):
    """The unchanged deterministic synthesis is the fallback for the AI layer."""
    return brief.synthesis