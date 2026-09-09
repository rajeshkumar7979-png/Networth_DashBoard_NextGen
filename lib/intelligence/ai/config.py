# AI Research Provider v1 — environment-driven configuration.
#
# All provider credentials come from the environment / secrets. Nothing is
# hard-coded; nothing is ever written to logs, caches, the UI, or error
# messages. `redact()` is the single choke point used to scrub an API key from
# any text we surface.
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

ENV_AI_API_KEY = "AI_API_KEY"
ENV_AI_PROVIDER = "AI_PROVIDER"
ENV_AI_BASE_URL = "AI_BASE_URL"
ENV_AI_MODEL = "AI_MODEL"
ENV_AI_TIMEOUT_SECONDS = "AI_TIMEOUT_SECONDS"
ENV_AI_MAX_TOKENS = "AI_MAX_TOKENS"
ENV_AI_TEMPERATURE = "AI_TEMPERATURE"
ENV_AI_STRUCTURED_OUTPUT = "AI_STRUCTURED_OUTPUT"
ENV_AI_MAX_EVIDENCE_CATALOG = "AI_MAX_EVIDENCE_CATALOG"

# Default provider: Groq — genuine free/developer tier (no credit card), a
# stable OpenAI-compatible chat/completions API, and strict Structured Outputs
# (json_schema) on openai/gpt-oss-120b. The AB layer is provider-neutral:
# these values are only defaults and can be overridden for any OpenAI-compatible
# endpoint (OpenAI, Groq, OpenRouter, Together, LM Studio, vLLM, ...).
DEFAULT_PROVIDER = "groq"
DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_TOKENS = 1200
DEFAULT_TEMPERATURE = 0.0
DEFAULT_STRUCTURED_OUTPUT = True
DEFAULT_MAX_EVIDENCE_CATALOG = 12


@dataclass(frozen=True)
class AIConfig:
    api_key: str = ""
    provider: str = DEFAULT_PROVIDER
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
    structured_output: bool = DEFAULT_STRUCTURED_OUTPUT
    max_evidence_catalog: int = DEFAULT_MAX_EVIDENCE_CATALOG

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())


def _env_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _env_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _env_bool(value, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def load_ai_config(env=None) -> AIConfig:
    """Build AIConfig from an environment mapping (defaults to os.environ)."""
    env = dict(os.environ if env is None else env)
    return AIConfig(
        api_key=str(env.get(ENV_AI_API_KEY, "") or "").strip(),
        provider=str(env.get(ENV_AI_PROVIDER, "") or "").strip() or DEFAULT_PROVIDER,
        base_url=str(env.get(ENV_AI_BASE_URL, "") or "").strip() or DEFAULT_BASE_URL,
        model=str(env.get(ENV_AI_MODEL, "") or "").strip() or DEFAULT_MODEL,
        timeout_seconds=_env_float(
            env.get(ENV_AI_TIMEOUT_SECONDS), DEFAULT_TIMEOUT_SECONDS),
        max_tokens=_env_int(env.get(ENV_AI_MAX_TOKENS), DEFAULT_MAX_TOKENS),
        temperature=_env_float(env.get(ENV_AI_TEMPERATURE), DEFAULT_TEMPERATURE),
        structured_output=_env_bool(
            env.get(ENV_AI_STRUCTURED_OUTPUT), DEFAULT_STRUCTURED_OUTPUT),
        max_evidence_catalog=_env_int(
            env.get(ENV_AI_MAX_EVIDENCE_CATALOG), DEFAULT_MAX_EVIDENCE_CATALOG),
    )


def redact(text: str, secret: Optional[str]) -> str:
    """Replace a secret (API key) with '***' anywhere it appears in text."""
    if not text:
        return text
    if secret:
        text = str(text).replace(str(secret), "***")
    # Belt-and-braces: also scrub any "Bearer <token>" pairing that survived.
    import re

    return re.sub(r"(Bearer\s+)[A-Za-z0-9._~\-]+", r"\1***", str(text))


def ai_config_status(config: Optional[AIConfig] = None) -> dict:
    """Read-only provider metadata for the UI. Never includes the key."""
    cfg = config if config is not None else load_ai_config()
    return {
        "configured": cfg.configured,
        "provider": cfg.provider,
        "model": cfg.model,
        "base_url": cfg.base_url,
        "timeout_seconds": cfg.timeout_seconds,
        "structured_output": cfg.structured_output,
        "max_evidence_catalog": cfg.max_evidence_catalog,
        "key_masked": "***" if cfg.configured else "",
    }