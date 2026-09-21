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

import logging
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
    _FALLBACK_PROVIDER,
    GROQ_BASE_URL,
    GROQ_MODEL,
    GROQ_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_LOCAL_PROVIDER,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
    load_ai_config,
    provider_is_configured,
    redact,
)
from lib.intelligence.ai.health import check_ollama_health, ollama_failure_hint
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

logger = logging.getLogger(__name__)

# Bounded raw-response excerpt for the DEBUG log — never the full reply, and
# always redacted so a stray key echo can never reach the logs (§8).
_RAW_EXCERPT_LIMIT = 1500


def _log_excerpt(text: str, config) -> str:
    excerpt = redact(str(text or ""), config.api_key)
    if len(excerpt) > _RAW_EXCERPT_LIMIT:
        excerpt = excerpt[:_RAW_EXCERPT_LIMIT] + "…"
    return excerpt


def _has_research_content(brief) -> bool:
    return bool(
        (getattr(brief, "changes", ()) or ())
        or (getattr(brief, "external", ()) or ())
        or (getattr(brief, "risks", ()) or ())
        or (getattr(brief, "research_needs", ()) or ())
        or (getattr(brief, "gaps", ()) or ())
        or getattr(brief, "evidence_count", 0)
    )


def _fallback_config(primary_config: AIConfig) -> Optional[AIConfig]:
    """Build an AIConfig for the wired fallback, if one exists.

    Groq/openai_compat → keyless Ollama. Ollama → Groq only when a key is
    already on the primary config (Streamlit secrets / AI_API_KEY). Returns
    None when there is nowhere to cascade.
    """
    if primary_config.provider == OLLAMA_LOCAL_PROVIDER and primary_config.api_key.strip():
        return AIConfig(
            api_key=primary_config.api_key,
            provider=GROQ_PROVIDER,
            base_url=GROQ_BASE_URL,
            model=GROQ_MODEL,
            timeout_seconds=min(float(primary_config.timeout_seconds or 60), 60.0),
            max_tokens=primary_config.max_tokens,
            temperature=primary_config.temperature,
            structured_output=primary_config.structured_output,
            max_evidence_catalog=primary_config.max_evidence_catalog,
        )
    fallback_name = _FALLBACK_PROVIDER.get(primary_config.provider)
    if not fallback_name or fallback_name == primary_config.provider:
        return None
    return AIConfig(
        api_key="",  # keyless local server
        provider=fallback_name,
        base_url=OLLAMA_BASE_URL,
        model=OLLAMA_MODEL,
        timeout_seconds=OLLAMA_TIMEOUT_SECONDS,
        max_tokens=primary_config.max_tokens,
        temperature=primary_config.temperature,
        structured_output=primary_config.structured_output,
        max_evidence_catalog=primary_config.max_evidence_catalog,
    )


def _clean_reason(exc, config: AIConfig, *, rewrite_local: bool = False) -> str:
    raw = redact(str(exc), getattr(config, "api_key", None))
    lowered = raw.lower()
    urllib_blob = (
        "httpconnectionpool" in lowered
        or "max retries" in lowered
        or "errno 111" in lowered
        or "connection refused" in lowered
    )
    if rewrite_local and getattr(config, "provider", "") == OLLAMA_LOCAL_PROVIDER:
        hint = ollama_failure_hint(raw)
        if hint and "taking too long" in hint.lower():
            return hint
        if hint or urllib_blob:
            return (
                "Ollama is not running on this host. "
                "Add Streamlit secret [ai] AI_API_KEY (Groq) to interpret here. "
                "The deterministic dossier is unchanged."
            )
    if urllib_blob:
        return (
            "AI provider is unreachable from this host. "
            "The deterministic dossier is unchanged."
        )
    return raw


def _ollama_is_up() -> bool:
    probe = check_ollama_health()
    return bool(probe.get("ok"))


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

    Cascade: when the primary provider fails with a retriable network error
    (timeout / connection refused) and no explicit client was injected, the
    pipeline tries the wired fallback provider (Groq → Ollama local → "AI
    unavailable"). An explicit ``client=`` override disables the cascade so
    callers own the full failure path.
    """
    if now is None:
        now = getattr(brief, "as_of", None) or datetime.now()
    config = config if config is not None else load_ai_config()

    if not provider_is_configured(config):
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
    response = None
    cli = client

    # Local Ollama is keyless, so provider_is_configured is True even on a
    # host with nothing listening on :11434 (Streamlit Cloud). Probe first
    # on the default path so we never wait 180s or dump urllib internals.
    if client is None and config.provider == OLLAMA_LOCAL_PROVIDER and not _ollama_is_up():
        fb_cfg = _fallback_config(config)
        if fb_cfg is not None:
            try:
                fb_cli = build_client(fb_cfg)
                response = fb_cli.complete(request, api_key=fb_cfg.api_key)
            except Exception as exc:
                return AIOutcome(
                    status=STATUS_FAILED,
                    created_at=now,
                    reason=_clean_reason(exc, fb_cfg, rewrite_local=False),
                    provider=fb_cfg.provider,
                    model=fb_cfg.model,
                    fallback_used=True,
                )
        if response is None:
            return AIOutcome(
                status=STATUS_FAILED,
                created_at=now,
                reason=_clean_reason(
                    "Could not reach the Ollama server on localhost:11434.",
                    config,
                    rewrite_local=True,
                ),
                provider=config.provider,
                model=config.model,
                fallback_used=True,
            )

    if response is None:
        cli = client if client is not None else build_client(config)

    # --- primary provider --------------------------------------------------
    try:
        if response is None:
            response = cli.complete(request, api_key=config.api_key)
    except (AIProviderTimeout, AIProviderUnavailable) as exc:
        # Retriable network error: try the wired fallback when no explicit
        # client was injected (the CC button path uses client=None).
        if client is None:
            fb_cfg = _fallback_config(config)
            if fb_cfg is not None:
                logger.debug(
                    "AI research cascading %s -> %s after retriable "
                    "failure", config.provider, fb_cfg.provider)
                try:
                    fb_cli = build_client(fb_cfg)
                    response = fb_cli.complete(request, api_key=fb_cfg.api_key)
                except Exception:  # fallback also failed — fall through
                    pass
        if response is None:
            return AIOutcome(
                status=STATUS_FAILED,
                created_at=now,
                reason=_clean_reason(exc, config, rewrite_local=(client is None)),
                provider=config.provider,
                model=config.model,
                fallback_used=True,
            )
    except AIProviderError as exc:
        return AIOutcome(
            status=STATUS_FAILED,
            created_at=now,
            reason=_clean_reason(exc, config, rewrite_local=(client is None)),
            provider=config.provider,
            model=config.model,
            fallback_used=True,
        )
    except Exception as exc:  # defensive: never let an AI hiccup break the page
        return AIOutcome(
            status=STATUS_FAILED,
            created_at=now,
            reason=_clean_reason(
                f"Unexpected AI provider failure: "
                f"{type(exc).__name__}: {exc}",
                config,
                rewrite_local=(client is None),
            ),
            provider=getattr(cli, "provider", config.provider),
            model=getattr(cli, "model", config.model),
            fallback_used=True,
        )

    latency_ms = (time.perf_counter() - start) * 1000.0
    mode = (response.meta or {}).get("format", "json_object")

    logger.debug(
        "AI research raw response (provider=%s model=%s mode=%s len=%d): %s",
        response.provider, response.model, mode, len(response.text),
        _log_excerpt(response.text, config))

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
        logger.debug(
            "AI research parse failed (provider=%s model=%s): %s",
            response.provider, response.model, redact(str(exc), config.api_key))
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