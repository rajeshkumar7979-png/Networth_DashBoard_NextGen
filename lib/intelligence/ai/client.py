# AI Research Provider v1 — provider-neutral client interface + one reference
# implementation over the OpenAI-compatible chat/completions API (used by Groq,
# OpenAI, OpenRouter, Together, LM Studio, vLLM, ...).
#
# The intelligence engine depends ONLY on `AIProviderClient`; the model behind
# it can be swapped by registering a different factory. Network calls happen
# only inside `complete()` — never during import or page load.
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol

import requests

from lib.intelligence.ai.config import AIConfig, AI_HTTP_USER_AGENT, _KEYLESS_PROVIDERS, redact
from lib.intelligence.ai.schema import OUTPUT_SCHEMA, OUTPUT_NAME

# Requests-style timeout tuple: (connect, read).
CONNECT_TIMEOUT_SECONDS = 5.0

_LOG = logging.getLogger(__name__)

# Phrase markers (case-insensitive) that identify a discontinued/retired model
# id rejection so we can give the user an actionable AI_MODEL error instead of
# wasting a json_schema -> json_object degrade retry on a dead model.
_DISCONTINUED_MODEL_MARKERS = (
    "model discontinued",
    "model not found",
    "model is no longer supported",
    "model does not exist",
)

# Whole-word markers that also identify a discontinued/retired model, needed
# when the provider embeds the model id between the words — e.g. Groq's
# "Model retired-model-123 discontinued": the id 'retired-model-123' sits
# between "model" and "discontinued", so no contiguous phrase marker matches.
_DISCONTINUED_MODEL_TOKENS = frozenset((
    "discontinued",
    "retired",
))


class AIProviderTimeout(Exception):
    """The provider did not answer within the configured timeout."""


class AIProviderUnavailable(Exception):
    """Transport-level failure (DNS, connection, server error)."""


class AIProviderError(Exception):
    """The provider was reached but rejected the request (HTTP status)."""


class AIOutputError(Exception):
    """The model's text was not a usable structured answer (parse went on)."""


@dataclass(frozen=True)
class AIRequest:
    messages: tuple[dict, ...]
    json_schema: Optional[dict] = None
    max_tokens: int = 1200
    temperature: float = 0.0
    json_mode: str = "auto"  # auto -> try json_schema, degrade to json_object


@dataclass(frozen=True)
class AIResponse:
    text: str
    provider: str
    model: str
    created_at: Optional[datetime]
    latency_ms: float
    meta: dict = field(default_factory=dict)


class AIProviderClient(Protocol):
    """Anything that turns an AIRequest into an AIResponse is a provider.

    Implementations MUST NOT leak the API key into exceptions or AIResponse
    metadata (redact() is available for that reason).
    """

    provider: str
    model: str

    def complete(self, request: AIRequest, api_key: str) -> AIResponse: ...


_REGISTRY: dict[str, callable] = {}


def register_ai_provider(name: str, factory) -> None:
    """Register a client factory: factory(config: AIConfig) -> AIProviderClient."""
    _REGISTRY[name] = factory


def unregister_ai_provider(name: str) -> None:
    _REGISTRY.pop(name, None)


def get_ai_client(config: AIConfig):
    """Build a client for the configured provider via the registry."""
    factory = _REGISTRY.get(config.provider)
    if factory is None:
        raise AIProviderError(
            f"No AI provider registered for '{config.provider}' "
            f"(AI_PROVIDER env).")
    return factory(config)


def build_client(config: AIConfig):
    """Public entry point used by the engine and the Command Center."""
    return get_ai_client(config)


def _safe_error_message(response, secret: Optional[str]) -> str:
    """Extract a scrubbed provider error without ever embedding the key."""
    message = f"HTTP {response.status_code} from AI provider"
    try:
        data = response.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict) and err.get("message"):
                message = str(err["message"])
            elif isinstance(err, str):
                message = err
    except (ValueError, TypeError):
        pass
    return redact(message, secret)


def _is_discontinued_model_error(message: str) -> bool:
    """True when the provider rejected the request because the model id is no
    longer served (discontinued/retired), regardless of the HTTP status code."""
    lowered = str(message or "").lower()
    if any(marker in lowered for marker in _DISCONTINUED_MODEL_MARKERS):
        return True
    # Fall back to word-boundary tokens for id-embedded phrasings like
    # "Model retired-model-123 discontinued": neither contiguous marker matches
    # because the model id sits between the words. Treat every non-alphanumeric
    # run as a word separator and look for the standalone token.
    tokens = set("".join(ch if ch.isalnum() else " "
                         for ch in lowered).split())
    return bool(set(_DISCONTINUED_MODEL_TOKENS) & tokens)


class OpenAICompatClient:
    """Reference OpenAI-compatible /chat/completions client.

    Structured Outputs are requested with response_format json_schema when
    config.structured_output is enabled; a single 400 fallback retries with the
    older json_object mode (e.g. Llama models on Groq do not accept json_schema).
    """

    def __init__(self, config: AIConfig):
        self._config = config

    @property
    def provider(self) -> str:
        return self._config.provider

    @property
    def model(self) -> str:
        return self._config.model

    def _body(self, request: AIRequest, mode: Optional[str]) -> dict:
        body = {
            "model": self._config.model,
            "messages": [dict(m) for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if mode == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": OUTPUT_NAME,
                    "strict": True,
                    "schema": request.json_schema or OUTPUT_SCHEMA,
                },
            }
        elif mode == "json_object":
            body["response_format"] = {"type": "json_object"}
        return body

    def complete(self, request: AIRequest, api_key: str = "") -> AIResponse:
        key = api_key or self._config.api_key
        if not key and self.provider not in _KEYLESS_PROVIDERS:
            raise AIProviderError("AI API key is empty.")
        url = self._config.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": AI_HTTP_USER_AGENT,
            "Accept": "application/json",
        }
        want_schema = bool(request.json_schema) and self._config.structured_output
        modes = ("json_schema", "json_object") if want_schema else ("json_object",)
        start = time.perf_counter()
        for attempt, mode in enumerate(modes):
            try:
                response = requests.post(
                    url, json=self._body(request, mode), headers=headers,
                    timeout=(CONNECT_TIMEOUT_SECONDS, self._config.timeout_seconds))
            except requests.exceptions.Timeout as exc:
                raise AIProviderTimeout(
                    f"AI provider timed out after {self._config.timeout_seconds:.0f}s "
                    f"({self._config.provider}/{self._config.model}).") from exc
            except requests.exceptions.RequestException as exc:
                raise AIProviderUnavailable(
                    redact(f"AI provider unreachable ({self._config.provider}): {exc}",
                           key)) from exc
            latency_ms = (time.perf_counter() - start) * 1000.0
            if response.status_code == 200:
                return self._parse_response(response, mode, latency_ms, key)
            message = _safe_error_message(response, key)
            if _is_discontinued_model_error(message):
                # Model retired/renamed: a json_schema -> json_object degrade
                # retry cannot help, so fail fast with an actionable message.
                _LOG.warning(
                    "AI model '%s' is no longer supported by provider '%s' — "
                    "update AI_MODEL in .streamlit/secrets.toml "
                    "(see https://console.groq.com/docs/models).",
                    self._config.model, self._config.provider)
                raise AIProviderError(
                    f"AI model {self._config.model} is no longer supported. "
                    "Please update AI_MODEL in your secrets file. "
                    "See https://console.groq.com/docs/models for current "
                    "models.")
            if attempt + 1 < len(modes) and response.status_code == 400:
                # json_schema unsupported on this model -> degrade to json_object.
                continue
            raise AIProviderError(message)

        raise AIProviderError(
            f"AI provider rejected the request ({self._config.provider}).")

    def _parse_response(self, response, mode: str, latency_ms: float,
                        key: str) -> AIResponse:
        try:
            data = response.json()
        except (ValueError, TypeError) as exc:
            raise AIProviderError(
                redact(f"AI provider returned malformed JSON "
                       f"({self._config.provider}).", key)) from exc
        if not isinstance(data, dict):
            raise AIProviderError("AI provider returned a non-object payload.")
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(
                f"No assistant message content in AI provider response "
                f"({self._config.provider}).") from exc
        if not isinstance(content, str):
            raise AIProviderError("AI provider content is not text.")
        model = data.get("model") or self._config.model
        created = data.get("created")
        created_at = None
        if isinstance(created, (int, float)) and created > 0:
            created_at = (datetime.fromtimestamp(created)
                          .replace(microsecond=0))
        meta = {
            "request_id": data.get("id"),
            "usage": data.get("usage"),
            "format": mode,
        }
        return AIResponse(
            text=content,
            provider=self._config.provider,
            model=str(model),
            created_at=created_at,
            latency_ms=round(latency_ms, 3),
            meta=meta,
        )


# Reference client is registered under its generic name and under the default
# provider name, so AI_PROVIDER=groq (or =openai_compat) resolves here by default.
register_ai_provider("openai_compat", OpenAICompatClient)
register_ai_provider("groq", OpenAICompatClient)

# Ollama local uses the same OpenAI-compatible transport (localhost:11434/v1).
from lib.intelligence.ai.config import OLLAMA_LOCAL_PROVIDER  # noqa: E402
register_ai_provider(OLLAMA_LOCAL_PROVIDER, OpenAICompatClient)