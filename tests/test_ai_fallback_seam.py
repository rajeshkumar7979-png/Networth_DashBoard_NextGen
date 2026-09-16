"""Deterministic, keyless, network-free pins for the AI model-catalog fallback seam.

These mirror the *provider discovery contract* in ``scripts/list_groq_models.py``
with zero network and zero credentials so the deterministic suite can pin the
degrade behavior permanently (AGENTS §6). The seam under test is the pure
``resolve_ai_model`` seam in ``lib/intelligence/ai/config.py`` — a function of
(model-id, catalog) only; it never touches the API key. The ``smoke``-marked
tests here are the keyless degrade half of ``scripts/list_groq_models.py``'s
exit-code contract and stay network-free by construction.
"""

from __future__ import annotations

from lib.intelligence.ai.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    load_ai_config,
    redact,
    resolve_ai_model,
)

_CATALOG = [
    "gemma2-9b-it",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]
_MATCH = "llama-3.3-70b-versatile"


def test_resolve_keeps_configured_model_when_present() -> None:
    warnings, chosen = resolve_ai_model(_MATCH, _CATALOG)
    assert chosen == _MATCH
    assert warnings == []


def test_resolve_falls_back_to_first_available_with_warning() -> None:
    warnings, chosen = resolve_ai_model("llama-3.3-40b-does-not-exist", _CATALOG)
    assert chosen == "gemma2-9b-it"
    assert len(warnings) == 1
    assert "does-not-exist" in warnings[0]
    assert "gemma2-9b-it" in warnings[0]


def test_resolve_empty_catalog_never_fabricates_a_model() -> None:
    warnings, chosen = resolve_ai_model("anything", [])
    assert chosen == "anything"
    assert len(warnings) == 1
    assert "no discovered" in warnings[0].lower()


def test_resolve_none_uses_catalog_head_silently() -> None:
    warnings, chosen = resolve_ai_model(None, _CATALOG)
    assert chosen == "gemma2-9b-it"
    assert warnings == []


def test_seam_never_needs_a_key() -> None:
    # load_ai_config() without a key must still import; the provider degrades
    # to keyless-local, and resolve_ai_model never reads the key.
    cfg = load_ai_config({"AI_API_KEY": ""})
    assert cfg.provider == "ollama_local"
    assert cfg.base_url == DEFAULT_BASE_URL
    assert cfg.model == DEFAULT_MODEL


def test_redact_scrubs_key_even_from_word_boundaries() -> None:
    secret = "gsk_fake" + ("x" * 40)
    scrubbed = redact("payload " + secret + " tail", secret)
    assert secret not in scrubbed
