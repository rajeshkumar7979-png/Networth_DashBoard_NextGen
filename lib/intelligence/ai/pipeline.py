# AI Research Provider v1 — orchestration pipeline.
#
# run_ai_research() is the single entry point invoked by the Command Center on
# an EXPLICIT user action (a button press). It is never called during page
# load. It owns every failure path:
#   not configured  -> AIOutcome(status="not_configured")  [no network]
#   empty evidence  -> AIOutcome(status="insufficient_evidence")  [no network]
#   provider errors -> AIOutcome(status="failed")   [timeout/unavailable/HTTP]
#   malformed text  -> AIOutcome(status="malformed")
# In every non-ok outcome, `fallback_used` is True and the caller keeps using
# the unchanged deterministic ResearchBrief.synthesis.
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from lib.intelligence.ai.client import (
    AIOutputError,
    AIProviderError,
    AIProviderTimeout,
    AIProviderUnavailable,
    AIRequest,
    build_client,
)
from lib.intelligence.ai.config import (
    ENV_AI_API_KEY,
    AIConfig,
    load_ai_config,
    redact,
)
from lib.intelligence.ai.model import (
    STATUS_FAILED,
    STATUS_INSUFFICIENT,
    STATUS_MALFORMED,
    STATUS_NOT_CONFIGURED,
    STATUS_OK,
    AIOutcome,
)
from lib.intelligence.ai.parse import parse_assessment
from lib.intelligence.ai.prompts import build_context
from lib.intelligence.ai.schema import OUTPUT_SCHEMA
from lib.intelligence.ai.validator import (
    ground_assessment,
    inherit_fact_ids,
    known_evidence_ids,
    validate_assessment_claims,
)


def _has_research_content(brief) -> bool:
    return bool(
        (getattr(brief, "changes", ()) or ())
        or (getattr(brief, "external", ()) or ())
        or (getattr(brief, "risks", ()) or ())
        or (getattr(brief, "research_needs", ()) or ())
        or (getattr(brief, "gaps", ()) or ())
        or getattr(brief, "evidence_count", 0)
    )


def run_ai_research(
        *,
        brief,
        config: Optional[AIConfig] = None,
        client=None,
        facts=(),
        evidence=(),
        question: Optional[str] = None,
        now: Optional[datetime] = None) -> AIOutcome:
    """Explicitly invoke the AI research provider for one ResearchBrief.

    `facts`/`evidence` are the deterministic facts and evidence the page has
    already built (exposure facts + EvidenceBag items); they are used only to
    construct the Briefing for validate_claims — never sent to the provider.
    """
    if now is None:
        now = getattr(brief, "as_of", None) or datetime.now()
    config = config if config is not None else load_ai_config()

    if not config.configured:
        return AIOutcome(
            status=STATUS_NOT_CONFIGURED,
            created_at=now,
            reason=f"{ENV_AI_API_KEY} is not set. Set it to enable the AI "
                   "research provider (the deterministic Research Brief is "
                   "unaffected).",
            provider=config.provider,
            model=config.model,
            fallback_used=True,
        )

    if not _has_research_content(brief):
        return AIOutcome(
            status=STATUS_INSUFFICIENT,
            created_at=now,
            reason="No portfolio evidence or research conclusions this run — "
                   "refusing to send an empty prompt to an external AI "
                   "provider.",
            provider=config.provider,
            model=config.model,
            fallback_used=True,
        )

    cli = client if client is not None else build_client(config)
    ctx = build_context(brief=brief, question=question,
                        max_evidence=config.max_evidence_catalog)
    messages = (
        {"role": "system", "content": ctx["system"]},
        {"role": "user", "content": ctx["user"]},
    )
    request = AIRequest(
        messages=messages,
        json_schema=OUTPUT_SCHEMA,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
    )

    start = time.perf_counter()
    try:
        response = cli.complete(request, api_key=config.api_key)
    except (AIProviderTimeout, AIProviderUnavailable, AIProviderError) as exc:
        return AIOutcome(
            status=STATUS_FAILED,
            created_at=now,
            reason=redact(str(exc), config.api_key),
            provider=config.provider,
            model=config.model,
            fallback_used=True,
        )
    except Exception as exc:  # defensive: never let an AI hiccup break the page
        return AIOutcome(
            status=STATUS_FAILED,
            created_at=now,
            reason=redact(
                f"Unexpected AI provider failure: "
                f"{type(exc).__name__}: {exc}", config.api_key),
            provider=getattr(cli, "provider", config.provider),
            model=getattr(cli, "model", config.model),
            fallback_used=True,
        )

    latency_ms = (time.perf_counter() - start) * 1000.0
    mode = (response.meta or {}).get("format", "json_object")

    try:
        assessment = parse_assessment(
            response.text,
            provider=response.provider,
            model=response.model,
            now=now,
            latency_ms=latency_ms,
            requested_format=mode,
        )
    except AIOutputError as exc:
        return AIOutcome(
            status=STATUS_MALFORMED,
            created_at=now,
            reason=redact(str(exc), config.api_key),
            provider=response.provider,
            model=response.model,
            fallback_used=True,
        )

    allowed = known_evidence_ids(brief)
    assessment = ground_assessment(assessment, allowed)
    assessment = inherit_fact_ids(assessment, getattr(brief, "conclusions", ()) or ())
    assessment = validate_assessment_claims(
        assessment, facts=facts or (), evidence=evidence or (), now=now)

    return AIOutcome(
        status=STATUS_OK,
        created_at=now,
        assessment=assessment,
        provider=assessment.provider,
        model=assessment.model,
        fallback_used=False,
        evidence_catalog_count=len(ctx["catalog"]),
        inference_meta=dict(response.meta or {}),
    )