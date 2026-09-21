# AI Research Provider v1 — Ollama local health check + service start helpers.
#
# Used by the Command Center only on EXPLICIT user actions (the connection
# check button and the Run AI research button). Nothing here runs during page
# load, so ordinary page loads stay network-free. The single transport is
# `requests.get` on the root health endpoint; tests monkeypatch
# `health.requests.get`. `redact()` is applied to any error text the caller may
# surface so a stray token can never reach the UI (§8).
from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Optional

import requests

from lib.intelligence.ai.config import redact

# Ollama's root HTTP endpoint (the OpenAI-compatible path lives under /v1; the
# health/tags endpoint is served from the root, NOT under /v1).
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"

# Health probes are quick liveness checks — they must never wait for a model
# to load, so a short timeout is correct (the real inference timeout is
# `timeout_seconds` in AIConfig / config.py, default 180 s).
OLLAMA_HEALTH_TIMEOUT_SECONDS = 3.0

OLLAMA_NOT_RUNNING_HINT = "Ollama is not running. Start it with: ollama serve"

OLLAMA_TIMEOUT_HINT = (
    "Ollama is taking too long. This is normal on first run. Try: "
    "(a) Wait 2-3 minutes, (b) Use a smaller model like llama3.2:3b (set "
    "AI_MODEL), (c) Check if your PC has enough RAM (need 8GB+)."
)

OLLAMA_FIRST_RUN_SPINNER = "AI is thinking... (this may take 2-3 minutes on first run)"

# Windows creation flags for a detached background process (ollama serve).
_CREATE_NEW_PROCESS_GROUP = 0x00000200 if os.name == "nt" else 0
_DETACHED_PROCESS = 0x00000008 if os.name == "nt" else 0


def _health_outcome(ok: bool, error: Optional[str] = None,
                    models: tuple = (), latency_ms: float = 0.0) -> dict:
    return {
        "ok": ok,
        "error": error,
        "models": tuple(sorted(models)),
        "count": len(models),
        "latency_ms": round(latency_ms, 1),
    }


def check_ollama_health(timeout_seconds: Optional[float] = None,
                        tags_url: Optional[str] = None) -> dict:
    """Probe the local Ollama server; return a plain health dict.

    Never raises: a dead/missing/slow server degrades to ``{"ok": False}``
    with a scrubbed error, never to an exception and never to a fabricated
    "healthy" result.
    """
    url = tags_url or OLLAMA_TAGS_URL
    timeout = timeout_seconds if timeout_seconds is not None \
        else OLLAMA_HEALTH_TIMEOUT_SECONDS
    start = time.perf_counter()
    try:
        response = requests.get(url, timeout=timeout)
    except requests.exceptions.Timeout:
        return _health_outcome(
            False, f"Ollama health check timed out after {timeout:.0f}s.")
    except requests.exceptions.RequestException:
        return _health_outcome(
            False, "Could not reach the Ollama server on localhost:11434.")
    latency_ms = (time.perf_counter() - start) * 1000.0
    if response.status_code != 200:
        return _health_outcome(
            False, f"Ollama health check returned HTTP {response.status_code}.",
            latency_ms=latency_ms)
    try:
        data = response.json()
    except (ValueError, TypeError):
        return _health_outcome(
            False, "Ollama health check returned unreadable data.",
            latency_ms=latency_ms)
    if not isinstance(data, dict):
        return _health_outcome(
            False, "Ollama health check returned a non-object payload.",
            latency_ms=latency_ms)
    models = data.get("models") or ()
    names = tuple(
        m.get("name", "") for m in models
        if isinstance(m, dict) and m.get("name"))
    return _health_outcome(True, None, names, latency_ms)


def ollama_command_available() -> bool:
    """True when the `ollama` executable is reachable on PATH."""
    return shutil.which("ollama") is not None


def start_ollama_service() -> tuple:
    """Launch `ollama serve` as a detached background process.

    Returns ``(ok, message)``. A missing executable or a failed spawn is a
    controlled failure message, never an exception; error text is scrubbed.
    """
    exe = shutil.which("ollama")
    if not exe:
        return False, (
            "Could not find the `ollama` executable on PATH. Install it from "
            "https://ollama.com, then retry.")
    try:
        kwargs: dict = {}
        if os.name == "nt":
            kwargs["creationflags"] = (
                _CREATE_NEW_PROCESS_GROUP | _DETACHED_PROCESS)
        subprocess.Popen(
            [exe, "serve"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs,
        )
        return True, (
            "Ollama server starting in the background. Wait a few seconds for "
            "it to bind localhost:11434, then run AI research again.")
    except Exception as exc:
        return False, redact(f"Could not start Ollama: {exc}", None)


def ollama_failure_hint(reason: Optional[str]) -> Optional[str]:
    """Targeted guidance for a failed local-Ollama run.

    A timeout gets the first-run guidance message; any other failure gets the
    explicit "not running / start it" hint. Never fabricated: unknown/empty
    reasons return None so the caller renders its normal failure text.
    """
    if not reason:
        return None
    lowered = str(reason).lower()
    if "timed out" in lowered or "timeout" in lowered:
        return OLLAMA_TIMEOUT_HINT
    markers = (
        "localhost:11434",
        "127.0.0.1:11434",
        "connection refused",
        "httpconnectionpool",
        "errno 111",
        "max retries",
        "could not reach the ollama",
        "failed to establish a new connection",
    )
    if any(m in lowered for m in markers):
        return OLLAMA_NOT_RUNNING_HINT
    return None
