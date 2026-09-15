# AI Research Provider v1 — configuration from Streamlit native secrets or the
# environment.
#
# Inside a running Streamlit script, values are first looked up in the [ai]
# table of .streamlit/secrets.toml (st.secrets["ai"]); everything else falls
# back to OS environment variables. Nothing is hard-coded; nothing is ever
# written to logs, caches, the UI, or error messages. `redact()` is the single
# choke point used to scrub an API key from any text we surface.
from __future__ import annotations

import os
from collections.abc import Mapping
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

# All keys handled by load_ai_config(). The same names are expected inside the
# `[ai]` section of Streamlit's native secrets (st.secrets["ai"][KEY]).
_AI_ENV_KEYS = (
    ENV_AI_API_KEY,
    ENV_AI_PROVIDER,
    ENV_AI_BASE_URL,
    ENV_AI_MODEL,
    ENV_AI_TIMEOUT_SECONDS,
    ENV_AI_MAX_TOKENS,
    ENV_AI_TEMPERATURE,
    ENV_AI_STRUCTURED_OUTPUT,
    ENV_AI_MAX_EVIDENCE_CATALOG,
)

# Default provider: Groq — genuine free/developer tier (no credit card) and a
# stable OpenAI-compatible chat/completions API. Default model is Groq's current
# stable workhorse llama-3.3-70b-versatile (131k context, 32k max output; the
# previous default mixtral-8x7b-32768 and llama-3.1-70b-versatile have been
# discontinued by Groq). Note: Groq's `json_schema` Structured Outputs (strict
# mode) are supported only on a few models (openai/gpt-oss-20b, gpt-oss-120b,
# qwen3.8-27b); llama-3.3-70b-versatile accepts JSON Object mode but not
# json_schema, so the client's existing single 400-degrade retry runs it in
# `json_object` mode instead (the prompts already spell out the JSON shape, so
# the tolerant parser still recovers the fields).
# openai/gpt-oss-120b remains selectable via AI_MODEL when true json_schema is
# wanted (its scalar fields can drift and return objects — parse.py recovers
# those). The AI layer is provider-neutral: these values are only defaults and
# can be overridden for any OpenAI-compatible endpoint (OpenAI, Groq,
# OpenRouter, Together, LM Studio, vLLM, ...).
DEFAULT_PROVIDER = "groq"
DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_TOKENS = 1200
DEFAULT_TEMPERATURE = 0.0
DEFAULT_STRUCTURED_OUTPUT = True
DEFAULT_MAX_EVIDENCE_CATALOG = 20

# Ollama local fallback — a local inference server that needs no API key.
OLLAMA_LOCAL_PROVIDER = "ollama_local"
OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_MODEL = "llama3.1:8b"
OLLAMA_TIMEOUT_SECONDS = 120.0

# Providers that require no API key (local inference servers).
_KEYLESS_PROVIDERS = frozenset({OLLAMA_LOCAL_PROVIDER})

# Cascade: when the primary provider fails with a retriable network error
# (timeout, connection refused) and no explicit client was injected, try the
# fallback. Only wired for Groq → Ollama; other providers have no fallback.
_FALLBACK_PROVIDER: dict[str, str] = {
    "groq": OLLAMA_LOCAL_PROVIDER,
    "openai_compat": OLLAMA_LOCAL_PROVIDER,
}


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


def provider_requires_key(provider: str) -> bool:
    """True when the provider needs an API key; False for keyless local servers."""
    return provider not in _KEYLESS_PROVIDERS


def provider_is_configured(config: AIConfig) -> bool:
    """True when the config is usable — key present, or keyless local provider."""
    if config.api_key.strip():
        return True
    return not provider_requires_key(config.provider)


def _streamlit_secret(key_name: str) -> Optional[str]:
    """Read one `[ai]` value from Streamlit's native secrets.

    Returns None (never raises) when not running inside a Streamlit script run,
    when no `[ai]` section exists, or when the value is missing/empty — the
    caller then falls back to the environment. The secret value itself is never
    echoed anywhere by this module.
    """
    try:
        import streamlit as st
    except ImportError:  # scripts, pytest, plain module imports
        return None
    runtime = getattr(st, "runtime", None)
    try:
        if runtime is None or not runtime.exists():
            return None
        section = st.secrets.get("ai", {})
    except Exception:
        return None
    # Streamlit returns an AttrDict (a Mapping, not a dict subclass).
    if not isinstance(section, Mapping):
        return None
    value = section.get(key_name)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_ai_config(env=None) -> AIConfig:
    """Build AIConfig from an environment mapping (defaults to os.environ).

    Precedence inside a running Streamlit script run:
        st.secrets["ai"][KEY]  >  explicit `env` mapping  >  os.environ.
    Outside a Streamlit runtime, secrets are never read (no accidental key use
    in scripts/tests, and no error when Streamlit is not installed).
    """
    env = dict(os.environ if env is None else env)
    for _key in _AI_ENV_KEYS:
        _secret = _streamlit_secret(_key)
        if _secret is not None:
            env[_key] = _secret
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
    is_configured = provider_is_configured(cfg)
    return {
        "configured": is_configured,
        "provider": cfg.provider,
        "model": cfg.model,
        "base_url": cfg.base_url,
        "timeout_seconds": cfg.timeout_seconds,
        "structured_output": cfg.structured_output,
        "max_evidence_catalog": cfg.max_evidence_catalog,
        "key_masked": "***" if cfg.api_key.strip() else "",
    }