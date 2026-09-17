"""Ollama local health check + service-start helpers — fully offline test suite.

No network, no real Ollama server, no credentials. The health check's network
seam is `health.requests.get`; every test replaces it with a fake. This suite
pins that the helpers degrade safely (never raise, never fabricate a "healthy"
result), that auto-start spawns a detached `ollama serve` background process,
and that importing/configuring the AI package never triggers a health probe.
"""
import os

import requests

from lib.intelligence import ai
from lib.intelligence.ai import health


def _fake_response(status_code=200, payload=None, text_raise=False):
    class _Fake:
        def __init__(self, code):
            self.status_code = code

        def json(self):
            if text_raise:
                raise ValueError("not json")
            return payload if payload is not None else {}

    return _Fake(status_code)


def _monkey_get(monkeypatch, result=None, exc=None):
    calls = []

    def fake_get(*a, **k):
        calls.append((a, k))
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(health.requests, "get", fake_get)
    return calls


# ------------------------------------------------------------- health probe ---

def test_health_ok_with_models(monkeypatch):
    calls = _monkey_get(
        monkeypatch,
        _fake_response(payload={"models": [
            {"name": "llama3.2:3b"}, {"name": "llama3.1:8b"},
        ]}))
    result = health.check_ollama_health()
    assert result["ok"] is True
    assert result["count"] == 2
    assert result["models"] == ("llama3.1:8b", "llama3.2:3b")  # sorted
    assert result["error"] is None
    assert result["latency_ms"] >= 0.0
    url = calls[0][0][0]
    assert url == health.OLLAMA_TAGS_URL
    assert calls[0][1]["timeout"] == health.OLLAMA_HEALTH_TIMEOUT_SECONDS


def test_health_ok_with_no_models(monkeypatch):
    _monkey_get(monkeypatch, _fake_response(payload={"models": []}))
    result = health.check_ollama_health()
    assert result["ok"] is True
    assert result["count"] == 0
    assert result["models"] == ()


def test_health_connection_refused_is_not_ok(monkeypatch):
    _monkey_get(monkeypatch, exc=requests.exceptions.ConnectionError("refused"))
    result = health.check_ollama_health()
    assert result["ok"] is False
    assert "Could not reach" in result["error"]
    assert result["count"] == 0


def test_health_timeout_is_not_ok(monkeypatch):
    _monkey_get(monkeypatch, exc=requests.exceptions.Timeout("slow"))
    result = health.check_ollama_health()
    assert result["ok"] is False
    assert "timed out" in result["error"]


def test_health_http_error_is_not_ok(monkeypatch):
    _monkey_get(monkeypatch, _fake_response(status_code=500))
    result = health.check_ollama_health()
    assert result["ok"] is False
    assert "HTTP 500" in result["error"]


def test_health_bad_json_is_not_ok(monkeypatch):
    _monkey_get(monkeypatch, _fake_response(payload=None, text_raise=True))
    result = health.check_ollama_health()
    assert result["ok"] is False
    assert "unreadable" in result["error"]


def test_health_non_object_payload_is_not_ok(monkeypatch):
    _monkey_get(monkeypatch, _fake_response(payload=["not", "a", "dict"]))
    result = health.check_ollama_health()
    assert result["ok"] is False
    assert "non-object" in result["error"]


def test_health_never_raises_on_any_request_exception(monkeypatch):
    _monkey_get(monkeypatch, exc=requests.exceptions.TooManyRedirects("stuck"))
    result = health.check_ollama_health()
    assert result["ok"] is False
    assert isinstance(result["error"], str)


def test_health_respects_custom_timeout_and_url(monkeypatch):
    calls = _monkey_get(monkeypatch, _fake_response(payload={"models": []}))
    health.check_ollama_health(timeout_seconds=9.5, tags_url="http://127.0.0.1:11434/api/tags")
    assert calls[0][1]["timeout"] == 9.5
    assert calls[0][0][0] == "http://127.0.0.1:11434/api/tags"


# ------------------------------------------------------------ launch helpers -

def test_ollama_command_available(monkeypatch):
    monkeypatch.setattr(health.shutil, "which", lambda name: "C:/tools/ollama.exe" if name == "ollama" else None)
    assert health.ollama_command_available() is True
    monkeypatch.setattr(health.shutil, "which", lambda name: None)
    assert health.ollama_command_available() is False


class _FakePopen:
    def __init__(self, args, **kwargs):
        self.args = args
        self.kwargs = kwargs


def test_start_ollama_service_spawns_detached(monkeypatch):
    monkeypatch.setattr(health.shutil, "which",
                        lambda name: "C:/tools/ollama.exe" if name == "ollama" else None)
    spawned = []

    def fake_popen(args, **kwargs):
        spawned.append((args, kwargs))
        return _FakePopen(args, **kwargs)

    monkeypatch.setattr(health.subprocess, "Popen", fake_popen)
    ok, message = health.start_ollama_service()
    assert ok is True
    assert "background" in message
    assert len(spawned) == 1
    args, kwargs = spawned[0]
    assert args == ["C:/tools/ollama.exe", "serve"]
    assert kwargs["stdin"] == health.subprocess.DEVNULL
    assert kwargs["stdout"] == health.subprocess.DEVNULL
    assert kwargs["stderr"] == health.subprocess.DEVNULL
    if os.name == "nt":
        assert kwargs["creationflags"] & health._DETACHED_PROCESS
        assert kwargs["creationflags"] & health._CREATE_NEW_PROCESS_GROUP


def test_start_ollama_service_missing_executable(monkeypatch):
    monkeypatch.setattr(health.shutil, "which", lambda name: None)
    spawned = []

    def fake_popen(*a, **k):
        spawned.append(a)

    monkeypatch.setattr(health.subprocess, "Popen", fake_popen)
    ok, message = health.start_ollama_service()
    assert ok is False
    assert "executable on PATH" in message
    assert spawned == []


def test_start_ollama_service_spawn_failure_is_controlled(monkeypatch):
    monkeypatch.setattr(health.shutil, "which",
                        lambda name: "ollama" if name == "ollama" else None)

    def boom(*a, **k):
        raise OSError("spawn refused")

    monkeypatch.setattr(health.subprocess, "Popen", boom)
    ok, message = health.start_ollama_service()
    assert ok is False
    assert "Could not start Ollama" in message


# ------------------------------------------------------------ failure hints ---

def test_failure_hint_timeout_guidance():
    hint = health.ollama_failure_hint("AI provider timed out after 180s (ollama_local).")
    assert hint == health.OLLAMA_TIMEOUT_HINT
    assert "(a) Wait 2-3 minutes" in hint
    assert "(b) Use a smaller model like llama3.2:3b" in hint
    assert "(c) Check if your PC has enough RAM (need 8GB+)" in hint


def test_failure_hint_not_running():
    assert health.ollama_failure_hint(
        "AI provider unreachable: could not connect to localhost:11434") \
        == health.OLLAMA_NOT_RUNNING_HINT


def test_failure_hint_unknown_reason_returns_none():
    assert health.ollama_failure_hint("model not found") is None
    assert health.ollama_failure_hint("") is None
    assert health.ollama_failure_hint(None) is None


# -------------------------------------------------------------- constants & net-free load ---

def test_constants_match_requirements():
    assert health.OLLAMA_TAGS_URL == "http://localhost:11434/api/tags"
    assert health.OLLAMA_HEALTH_TIMEOUT_SECONDS == 3.0
    assert health.OLLAMA_NOT_RUNNING_HINT == "Ollama is not running. Start it with: ollama serve"
    assert "may take 2-3 minutes on first run" in ai.OLLAMA_FIRST_RUN_SPINNER
    assert ai.OLLAMA_FIRST_RUN_SPINNER.startswith("AI is thinking")
    assert health.OLLAMA_FIRST_RUN_SPINNER == ai.OLLAMA_FIRST_RUN_SPINNER


def test_import_and_config_never_probe_health(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("health probe during import/config")

    monkeypatch.setattr(health.requests, "get", boom)
    cfg = ai.load_ai_config({})
    status = ai.ai_config_status(cfg)
    assert status["timeout_seconds"] == 180.0
    assert ai.check_ollama_health is health.check_ollama_health


def test_health_exports_available_on_package():
    assert ai.OLLAMA_NOT_RUNNING_HINT == health.OLLAMA_NOT_RUNNING_HINT
    assert ai.OLLAMA_TIMEOUT_HINT == health.OLLAMA_TIMEOUT_HINT
    assert ai.check_ollama_health is health.check_ollama_health
    assert ai.ollama_command_available is health.ollama_command_available
    assert ai.start_ollama_service is health.start_ollama_service
    assert ai.ollama_failure_hint is health.ollama_failure_hint