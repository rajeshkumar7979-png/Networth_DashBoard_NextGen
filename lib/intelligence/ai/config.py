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
# stable OpenAI-compatible chat/completions API. Groq retired the Llama 3.x
# chat ids (llama-3.3-70b-versatile, llama-3.1-70b-versatile, mixtral-8x7b-32768).
# Current default is openai/gpt-oss-20b (json_object; json_schema is accepted on
# gpt-oss-20b / gpt-oss-120b / qwen/qwen3.8-27b). The client's 400-degrade retry
# still falls back to json_object. openai/gpt-oss-120b remains selectable via
# AI_MODEL when a larger model is wanted (scalar fields can drift to objects —
# parse.py recovers those). The AI layer is provider-neutral: these values are
# only defaults and can be overridden for any OpenAI-compatible endpoint.
DEFAULT_PROVIDER = "ollama_local"
DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.1:8b"
# Local inference (Ollama) is slow on first run (model load/download): the
# timeout defaults to 180 s (3 minutes), not 30 s, so a cold local model has
# time to answer before the request is abandoned.
DEFAULT_TIMEOUT_SECONDS = 180.0
DEFAULT_MAX_TOKENS = 1200
DEFAULT_TEMPERATURE = 0.0
DEFAULT_STRUCTURED_OUTPUT = True
DEFAULT_MAX_EVIDENCE_CATALOG = 20

# Ollama local fallback — a local inference server that needs no API key.
OLLAMA_LOCAL_PROVIDER = "ollama_local"
OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_MODEL = "llama3.1:8b"
OLLAMA_TIMEOUT_SECONDS = 180.0

GROQ_PROVIDER = "groq"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "openai/gpt-oss-20b"
# Ids Groq has already 404'd. load_ai_config remaps these to GROQ_MODEL so an
# old secrets.toml (or the TOML we previously handed the operator) still talks.
GROQ_RETIRED_MODELS = frozenset({
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
})
AI_HTTP_USER_AGENT = "NorthlineFamilyDesk/1.0"

# Providers that require no API key (local inference servers).
_KEYLESS_PROVIDERS = frozenset({OLLAMA_LOCAL_PROVIDER})

# Cascade: when the primary provider fails with a retriable network error
# (timeout, connection refused) and no explicit client was injected, try the
# fallback. Groq → Ollama (keyless). Ollama → Groq only when an API key is
# present (handled in pipeline._fallback_config).
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
    api_key = str(env.get(ENV_AI_API_KEY, "") or "").strip()
    explicit_provider = str(env.get(ENV_AI_PROVIDER, "") or "").strip()
    explicit_base = str(env.get(ENV_AI_BASE_URL, "") or "").strip()
    explicit_model = str(env.get(ENV_AI_MODEL, "") or "").strip()
    # A key with no explicit provider is Groq — Streamlit Cloud has no Ollama.
    # Local Ollama stays the default only when no key is configured.
    default_max_tokens = DEFAULT_MAX_TOKENS
    if explicit_provider:
        provider = explicit_provider
    elif api_key:
        provider = GROQ_PROVIDER
    else:
        provider = DEFAULT_PROVIDER
    if provider == GROQ_PROVIDER:
        base_url = explicit_base or GROQ_BASE_URL
        model = explicit_model or GROQ_MODEL
        default_timeout = 60.0
        default_max_tokens = 2048
    elif provider == OLLAMA_LOCAL_PROVIDER:
        base_url = explicit_base or OLLAMA_BASE_URL
        model = explicit_model or OLLAMA_MODEL
        default_timeout = OLLAMA_TIMEOUT_SECONDS
    else:
        base_url = explicit_base or DEFAULT_BASE_URL
        model = explicit_model or DEFAULT_MODEL
        default_timeout = DEFAULT_TIMEOUT_SECONDS
    if provider == GROQ_PROVIDER and model in GROQ_RETIRED_MODELS:
        model = GROQ_MODEL
    return AIConfig(
        api_key=api_key,
        provider=provider,
        base_url=base_url,
        model=model,
        timeout_seconds=_env_float(
            env.get(ENV_AI_TIMEOUT_SECONDS), default_timeout),
        max_tokens=_env_int(env.get(ENV_AI_MAX_TOKENS), default_max_tokens),
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


def resolve_ai_model(model_or_none: Optional[str], available: list[str]) -> tuple[list, str]:
    """Return ``(warnings, chosen)`` for a model vs a live/known model catalog.

    Deterministic, network-free fallback seam: when ``model_or_none`` is
    configured but absent from ``available`` (e.g. the provider discontinued
    it, or discovery returned a catalog the pin is not in), the call resolves
    to the first available model id and returns an explanatory warning line.
    When ``model_or_none`` is empty/None, the catalog head is chosen without
    a warning. ``available`` must already be keyless/redact-scrubbed by the
    caller (discovery seam); this function never touches the key.

    Never fabricates: an empty ``available`` yields ``("", original or "")``
    with a warning, so the caller can degrade to "model unavailable" instead
    of inventing an id.
    """
    warnings: list[bool] = []
    original = (model_or_none or "").strip()
    if not available:
        warnings.append(
            "no discovered model catalog is available; "
            "cannot verify the configured AI model"
        )
        return warnings, original
    if not original:
        return warnings, available[0]
    if original in available:
        return warnings, original
    warnings.append(
        f"configured AI model {original!r} is not in the available catalog "
        f"({len(available)} models); falling back to first available "
        f"{available[0]!r}"
    )
    return warnings, available[0]


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