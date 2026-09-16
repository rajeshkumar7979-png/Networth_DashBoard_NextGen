"""AI Research Provider v1 — fully offline/mocked test suite.

No real API key is required anywhere here. The network seam
(lib.intelligence.ai.client.requests.POST on OpenAICompatClient, and the
AIProviderClient protocol in general) is always replaced with mocks, and two
tests additionally assert that page-load paths never touch the network.
The AI pipeline must never mutate financial facts; tests pin that too.
"""
import json
from datetime import datetime, timezone

import pytest
import requests

from lib.intelligence import ai
from lib.intelligence.ai import client as aiclient
from lib.intelligence.model import (
    Briefing,
    Claim,
    Interpretation,
    SourceClass,
    SourceType,
    make_evidence,
    make_fact,
)
from lib.intelligence.research import (
    EvidenceQuality,
    ExternalDevelopment,
    PortfolioChange,
    ResearchBrief,
    ResearchConclusion,
)

NOW = datetime(2026, 9, 8, 10, 30, tzinfo=timezone.utc)
API_KEY = "test-secret-key-12345"

SAMPLE = {
    "overall_assessment": "Equity drove most of the change this run; evidence "
                          "supports the deterministic drivers.",
    "confidence": 0.72,
    "uncertainty": "NAV fixtures may lag; the evidence set is a single "
                   "provider snapshot.",
    "key_findings": [
        {"text": "Equity is the largest positive driver.",
         "evidence_ids": ["ev:test:1"], "kind": "fact"},
        {"text": "Held-fund NAV direction is broadly firm.",
         "evidence_ids": ["amfi:nav:TEST", "ev:test:2"], "kind": "interpretation"},
    ],
    "risks": [
        {"text": "Concentration in fixed income remains elevated.",
         "evidence_ids": ["ev:test:1"], "kind": "interpretation"},
    ],
    "opportunities": [],
    "research_needs": [
        {"text": "Confirm renewal terms on maturing FDs.",
         "evidence_ids": ["ev:test:1"], "kind": "fact"},
    ],
    "invalidation_conditions": ["Market reversal on a later run",
                                "Statutory disclosure corrected"],
    "limitations": ["No transaction history exists", "Single NAV snapshot"],
}


def _ev(eid, source_type=SourceType.NEWS, entity="TEST", payload=None, now=None):
    return make_evidence(
        eid=eid,
        source="test-source",
        source_class=SourceClass.B,
        source_type=source_type,
        entity=entity,
        title=f"headline {eid}",
        now=now if now is not None else NOW,
        payload=payload or {},
    )


def _brief(**overrides) -> ResearchBrief:
    ev1 = _ev("ev:test:1", source_type=SourceType.CALCULATED)
    ev2 = _ev("ev:test:2")
    nav = _ev("amfi:nav:TEST", source_type=SourceType.OBSERVED,
              payload={"nav": 140.5, "as_of_date": "2026-09-06"})
    devs = (
        ExternalDevelopment(
            evidence=ev1,
            quality=EvidenceQuality(
                evidence_id="ev:test:1", score=0.95, source_class="A",
                fresh=True, relevance="mapped", basis="test"),
            category="macro", headline=f"drivers {ev1.id}",
            mapped=True, matched=("TOTAL",)),
        ExternalDevelopment(
            evidence=ev2,
            quality=EvidenceQuality(
                evidence_id="ev:test:2", score=0.7, source_class="C",
                fresh=True, relevance="unmapped", basis="test"),
            category="news", headline=f"headline {ev2.id}",
            mapped=False, matched=()),
        ExternalDevelopment(
            evidence=nav,
            quality=EvidenceQuality(
                evidence_id="amfi:nav:TEST", score=1.0, source_class="A",
                fresh=True, relevance="mapped", basis="test"),
            category="nav", headline="NAV Quant Small Cap",
            mapped=True, matched=("INF966L01689",)),
    )
    risk = ResearchConclusion(
        id="research:risk:test", topic="risk", title="FCNR concentration",
        statement="FCNR concentration is elevated.",
        strength="strong", confidence=0.9,
        fact_ids=("class:fcnr:share_pct",),
        evidence_ids=("ev:test:1",),
        invalidation="Rule no longer fires.",
    )
    change = PortfolioChange(
        kind="pnl_driver", label="Equity market", amount=5000.0,
        cashflow_measurement=False, note="driven by equity holdings")
    synthesis = Interpretation(model="research-deterministic",
                               summary="Deterministic synthesis",
                               claims=(), confidence=0.7)
    base = dict(
        as_of=NOW,
        question="What changed, and where is the evidence thin?",
        totals={"total_assets": 25000000.0, "total_invested": 20000000.0,
                "total_pnl": 5000000.0},
        changes=(change,),
        external=devs,
        risks=(risk,),
        research_needs=(),
        gaps=(),
        conclusions=(risk,),
        synthesis=synthesis,
        synthesis_reason=None,
        evidence_count=3,
        mapped_count=2,
        not_a_cashflow_label="NOT a cash-flow measurement",
    )
    base.update(overrides)
    return ResearchBrief(**base)


def _empty_brief() -> ResearchBrief:
    return _brief(
        changes=(), external=(), risks=(), research_needs=(), gaps=(),
        conclusions=(), evidence_count=0, mapped_count=0,
        totals={"total_assets": 0.0, "total_invested": 0.0, "total_pnl": 0.0},
    )


def _facts():
    return (
        make_fact("class:equity", "share_pct", 40.0, "pct",
                  now=NOW, fid="class:equity:share_pct"),
        make_fact("class:fcnr", "share_pct", 35.0, "pct",
                  now=NOW, fid="class:fcnr:share_pct"),
    )


class FakeClient:
    provider = "fake"
    model = "fake-model"

    def __init__(self, response_text=None, error=None):
        self.response_text = response_text
        self.error = error
        self.calls = []

    def complete(self, request, api_key=""):
        self.calls.append(api_key)
        if self.error is not None:
            raise self.error
        return ai.AIResponse(
            text=self.response_text, provider=self.provider,
            model=self.model, created_at=None, latency_ms=12.3,
            meta={"format": "json_schema"})


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


# ---------------------------------------------------------------- config ---

def test_load_ai_config_defaults_no_key():
    cfg = ai.load_ai_config({})
    assert cfg.configured is False
    assert cfg.provider == "ollama_local"
    assert cfg.model == "llama3.1:8b"
    assert cfg.base_url == "http://localhost:11434/v1"
    assert cfg.api_key == ""
    assert cfg.structured_output is True


def test_default_model_config_is_valid_and_degrades_to_json_object(monkeypatch):
    """The default model id is a live Ollama local model and "Run AI research" works."""
    assert ai.DEFAULT_MODEL == "llama3.1:8b"
    cfg = ai.AIConfig(api_key="", provider="ollama_local",
                      base_url="http://localhost:11434/v1", model=ai.DEFAULT_MODEL)
    assert cfg.provider == "ollama_local"
    assert cfg.model == ai.DEFAULT_MODEL
    assert cfg.structured_output is True
    # Ollama OpenAI-compat returns json_object on the default; the default
    # model must hit the single 400-degrade and succeed via json_object.
    import lib.intelligence.ai.client as aiclient
    calls = []
    seq = [
        FakeResponse({"error": {"message": "response format json_schema "
                                          "unsupported"}}, status_code=400),
        FakeResponse(_chat_payload("ok")),
    ]

    def fake_post(*a, **k):
        assert k["json"]["model"] == ai.DEFAULT_MODEL
        calls.append(k["json"]["response_format"]["type"])
        return seq.pop(0)

    monkeypatch.setattr(aiclient.requests, "post", fake_post)
    cli = aiclient.OpenAICompatClient(cfg)
    response = cli.complete(ai.AIRequest(
        messages=({"role": "user", "content": "x"},), json_schema=ai.OUTPUT_SCHEMA))
    assert calls == ["json_schema", "json_object"]
    assert response.meta["format"] == "json_object"
    assert response.provider == "ollama_local"
    assert response.model == "fake-model"


def test_load_ai_config_overrides_env():
    cfg = ai.load_ai_config({
        "AI_API_KEY": " K ",
        "AI_PROVIDER": "openai_compat",
        "AI_BASE_URL": "http://localhost:11434/v1",
        "AI_MODEL": "local-model",
        "AI_TIMEOUT_SECONDS": "7",
        "AI_MAX_TOKENS": "512",
        "AI_TEMPERATURE": "0.5",
        "AI_STRUCTURED_OUTPUT": "0",
        "AI_MAX_EVIDENCE_CATALOG": "3",
    })
    assert cfg.api_key == "K"
    assert cfg.provider == "openai_compat"
    assert cfg.base_url == "http://localhost:11434/v1"
    assert cfg.model == "local-model"
    assert cfg.timeout_seconds == 7.0
    assert cfg.max_tokens == 512
    assert cfg.temperature == 0.5
    assert cfg.structured_output is False
    assert cfg.max_evidence_catalog == 3


def test_load_ai_config_ignores_garbage_values():
    cfg = ai.load_ai_config({
        "AI_TIMEOUT_SECONDS": "garbage",
        "AI_MAX_TOKENS": "-",
        "AI_TEMPERATURE": "??",
        "AI_MAX_EVIDENCE_CATALOG": "many",
    })
    assert cfg.timeout_seconds == 30.0
    assert cfg.max_tokens == 1200
    assert cfg.temperature == 0.0
    assert cfg.max_evidence_catalog == 20


def test_load_ai_config_reads_streamlit_secrets(monkeypatch):
    """st.secrets['ai'] wins over the environment inside a Streamlit run."""
    import streamlit as st

    monkeypatch.setattr(st.runtime, "exists", lambda: True)
    monkeypatch.setattr(
        st, "secrets",
        {"ai": {"AI_API_KEY": "  s3cret-from-toml  ", "AI_MODEL": "stealth-model"}})
    cfg = ai.load_ai_config({})
    assert cfg.api_key == "s3cret-from-toml"
    assert cfg.configured is True
    assert cfg.model == "stealth-model"


def test_load_ai_config_ignores_secrets_outside_runtime(monkeypatch):
    """Outside a Streamlit runtime the secrets file must never be consulted."""
    import streamlit as st

    monkeypatch.setattr(st.runtime, "exists", lambda: False)
    monkeypatch.setattr(
        st, "secrets",
        {"ai": {"AI_API_KEY": "ignored-secret"}})
    cfg = ai.load_ai_config({"AI_PROVIDER": "openai_compat"})
    assert cfg.configured is False
    assert cfg.api_key == ""
    assert cfg.provider == "openai_compat"


def test_ai_config_status_never_exposes_key():
    cfg = ai.AIConfig(api_key=API_KEY)
    status = ai.ai_config_status(cfg)
    dumped = json.dumps(status)
    assert API_KEY not in dumped
    assert status["key_masked"] == "***"
    assert status["configured"] is True


def test_redact_removes_secret():
    text = f"boom failed with {API_KEY} and Bearer {API_KEY}"
    assert API_KEY not in ai.redact(text, API_KEY)
    assert "Bearer ***" in ai.redact(text, API_KEY)


# --------------------------------------------------------------- prompts ---

def test_build_context_allowlist_and_catalog():
    brief = _brief()
    ctx = ai.build_context(brief=brief)
    allowed = ctx["allowed_evidence_ids"]
    assert "ev:test:1" in allowed
    assert "amfi:nav:TEST" in allowed
    assert len(ctx["catalog"]) == 3
    ids = {item["id"] for item in ctx["catalog"]}
    assert ids == {"ev:test:1", "ev:test:2", "amfi:nav:TEST"}
    assert "25000000" in ctx["user"] or "25,000,000" in ctx["user"]
    assert "Total assets (INR)" in ctx["user"]
    assert "Allowed evidence ids" in ctx["user"]


def test_build_context_never_dumps_raw_payload():
    blob = "X" * 5000
    brief = _brief()
    devs = list(brief.external)
    devs[0] = ExternalDevelopment(
        evidence=_ev("ev:test:1", source_type=SourceType.CALCULATED,
                     payload={"secret_blob": blob}),
        quality=devs[0].quality,
        category=devs[0].category, headline=devs[0].headline,
        mapped=devs[0].mapped, matched=devs[0].matched)
    ctx = ai.build_context(brief=_brief(external=tuple(devs)))
    assert blob not in ctx["user"]
    for item in ctx["catalog"]:
        assert len(item["snippet"]) <= 300


def test_build_context_ranks_mapped_then_quality_then_recency():
    """Catalog order reflects (a) mapped-first, (b) quality desc, (c) recency."""
    old = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
    new = datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc)

    def dev(eid, mapped, score, ts, category="news"):
        return ExternalDevelopment(
            evidence=_ev(eid, now=ts),
            quality=EvidenceQuality(
                evidence_id=eid, score=score, source_class="C", fresh=True,
                relevance="mapped" if mapped else "unmapped", basis="test"),
            category=category, headline=f"headline {eid}",
            mapped=mapped, matched=("TEST",) if mapped else ())

    # Deliberately scrambled: a newer-but-unmapped quality-0.99 record must
    # fall behind mapped records even at lower quality, and a tie on quality
    # must resolve by recency.
    brief = _brief(external=(
        dev("mapped-old", True, 0.90, old),
        dev("mapped-new", True, 0.90, new),
        dev("news-high", False, 0.99, new, category="news"),
    ), evidence_count=3, mapped_count=2)
    ctx = ai.build_context(brief=brief, max_evidence=20)
    ids = [item["id"] for item in ctx["catalog"]]
    assert ids == ["mapped-new", "mapped-old", "news-high"]


def test_build_context_caps_catalog_and_allowlist_when_100_plus():
    """With 100+ developments only the top-20 are sent; the allow-list stays
    bounded to the catalog plus conclusion-cited ids, and the prompt notes the
    truncation — the token budget can never blow up like the 46k-token error."""
    devs = []
    for i in range(120):
        eid = f"ev:synth:{i:04d}"
        mapped = i % 3 == 0
        ts = datetime(2026, 9, min(1 + i % 7, 8), (i * 7) % 24,
                      tzinfo=timezone.utc)
        devs.append(ExternalDevelopment(
            evidence=_ev(eid, now=ts),
            quality=EvidenceQuality(
                evidence_id=eid, score=round(0.5 + (i % 20) / 20.0, 3),
                source_class="C", fresh=i < 60,
                relevance="mapped" if mapped else "unmapped", basis="test"),
            category="nav" if i % 2 else "news", headline=f"synth {i}",
            mapped=mapped, matched=("TEST",) if mapped else ()))
    brief = _brief(
        external=tuple(devs), evidence_count=120, mapped_count=sum(
            d.mapped for d in devs))
    ctx = ai.build_context(brief=brief, max_evidence=20)

    assert ctx["truncated"] is True
    assert ctx["total_available"] == 120
    assert len(ctx["catalog"]) == 20
    # Every catalogued record is a mapped one (mapped-first ranking).
    assert all(item["mapped"] for item in ctx["catalog"])
    assert "top-20 most relevant developments out of 120 total records" \
        in ctx["system"]
    assert "top 20 of 120" in ctx["user"]
    assert "lower-ranked records" in ctx["user"]

    # Allow-list == catalog ids ∪ conclusion-cited ids; no full 120-id dump.
    catalog_ids = {item["id"] for item in ctx["catalog"]}
    conclusion_ids = {eid for c in brief.conclusions for eid in c.evidence_ids}
    assert ctx["allowed_evidence_ids"] == (catalog_ids | conclusion_ids)
    assert len(ctx["allowed_evidence_ids"]) <= 21
    # Sanity token bound (chars/4): far below the 46k-token failure threshold.
    assert len(ctx["user"]) < 40_000


def test_build_messages_shape():
    sys_msg, user_msg = ai.build_messages(brief=_brief())
    assert sys_msg["role"] == "system"
    assert user_msg["role"] == "user"
    assert "Grounded Analyst" in sys_msg["content"]
    assert "evidence_ids" in sys_msg["content"] or "evidence" in user_msg["content"]
    assert "Rules:" in user_msg["content"]


def test_build_context_rules_hint_is_inline():
    ctx = ai.build_context(brief=_brief())
    assert "Rules:" in ctx["user"]
    sys_msg, user_msg = ai.build_messages(brief=_brief())
    assert "Rules:" in user_msg["content"]
    assert "Rules:" not in sys_msg["content"]


# ----------------------------------------------------------------- parse ---

def test_extract_json_object_plain_and_fenced():
    assert ai.extract_json_object('{"a": 1}') == {"a": 1}
    fenced = '```json\n{"a": 1}\n```'
    assert ai.extract_json_object(fenced) == {"a": 1}
    trailing = 'Here is the answer:\n{"a": {"b": [1, 2]}}\n\nhope this helps'
    assert ai.extract_json_object(trailing) == {"a": {"b": [1, 2]}}


def test_extract_json_object_rejects_non_json():
    with pytest.raises(ai.AIOutputError):
        ai.extract_json_object("no json here")
    with pytest.raises(ai.AIOutputError):
        ai.extract_json_object("[]")


def test_parse_assessment_valid_and_confidence_clamped():
    text = json.dumps(SAMPLE)
    assessment = ai.parse_assessment(text, provider="groq", model="m",
                                     now=NOW, latency_ms=5.0)
    assert assessment.overall_assessment == SAMPLE["overall_assessment"]
    assert assessment.confidence == 0.72
    assert len(assessment.findings) == 4  # 2 findings + 1 risk + 1 need
    assert assessment.invalidation_conditions
    assert assessment.model == "m"
    assert assessment.latency_ms == 5.0

    over = dict(SAMPLE, confidence=1.4)
    assert ai.parse_assessment(json.dumps(over)).confidence == 1.0
    under = dict(SAMPLE, confidence=-0.5)
    assert ai.parse_assessment(json.dumps(under)).confidence == 0.0


def test_parse_assessment_missing_overall_recovers():
    """Missing overall_assessment degrades gracefully, never 'Malformed'."""
    bad = dict(SAMPLE)
    bad.pop("overall_assessment")
    assessment = ai.parse_assessment(json.dumps(bad))
    assert assessment.overall_assessment.strip()
    assert any("overall_assessment" in d for d in assessment.downgrades)


def test_parse_assessment_overall_as_object_recovers():
    """gpt-oss drift: a summary object with a text key is unpacked."""
    bad = json.loads(json.dumps(SAMPLE))
    bad["overall_assessment"] = {"summary": "Equity was the dominant driver."}
    assessment = ai.parse_assessment(json.dumps(bad))
    assert assessment.overall_assessment == "Equity was the dominant driver."
    assert any("overall_assessment" in d for d in assessment.downgrades)
    assert any("'summary'" in d for d in assessment.downgrades)


def test_parse_assessment_overall_as_list_and_boolean_recovers():
    bad = json.loads(json.dumps(SAMPLE))
    bad["overall_assessment"] = ["first sentence", "second sentence"]
    assessment = ai.parse_assessment(json.dumps(bad))
    assert assessment.overall_assessment == "first sentence second sentence"
    assert any("joined" in d for d in assessment.downgrades)

    bad2 = json.loads(json.dumps(SAMPLE))
    bad2["overall_assessment"] = True
    assessment2 = ai.parse_assessment(json.dumps(bad2))
    assert assessment2.overall_assessment == "Yes"
    assert any("boolean" in d for d in assessment2.downgrades)


def test_parse_assessment_uncertainty_nonstring_recovers():
    bad = json.loads(json.dumps(SAMPLE))
    bad["uncertainty"] = {"level": "low"}
    assessment = ai.parse_assessment(json.dumps(bad))
    assert assessment.uncertainty.strip()
    assert any("uncertainty" in d for d in assessment.downgrades)


def test_parse_assessment_scalar_values_are_bounded():
    bad = json.loads(json.dumps(SAMPLE))
    bad["overall_assessment"] = "x" * 5000
    assessment = ai.parse_assessment(json.dumps(bad))
    assert len(assessment.overall_assessment) <= ai.parse.MAX_SCALAR_TEXT + 1
    assert any("truncated" in d.lower() for d in assessment.downgrades)


def test_parse_assessment_nonfinite_confidence_is_malformed():
    bad = json.dumps(dict(SAMPLE, confidence=float("nan")))
    with pytest.raises(ai.AIOutputError):
        ai.parse_assessment(bad)


def test_parse_assessment_bad_kind_is_malformed():
    bad = json.loads(json.dumps(SAMPLE))
    bad["risks"][0]["kind"] = "recommendation"
    with pytest.raises(ai.AIOutputError):
        ai.parse_assessment(json.dumps(bad))


def test_parse_assessment_wrong_shape_is_malformed():
    bad = json.loads(json.dumps(SAMPLE))
    bad["research_needs"] = "not a list"
    with pytest.raises(ai.AIOutputError):
        ai.parse_assessment(json.dumps(bad))


def test_parse_assessment_truncates_oversized_findings():
    rows = [
        {"text": f"finding {i}", "evidence_ids": ["ev:test:1"], "kind": "fact"}
        for i in range(30)
    ]
    big = dict(SAMPLE, key_findings=rows, risks=[], opportunities=[], research_needs=[])
    assessment = ai.parse_assessment(json.dumps(big))
    assert len(assessment.findings) <= 8 * 4
    assert any("Truncated" in d for d in assessment.downgrades)


# ---------------------------------------------------------------- client ---

def _chat_payload(content, model="fake-model", created=1750000000):
    return {
        "id": "req_1",
        "model": model,
        "created": created,
        "choices": [{"message": {"content": content}}],
        "usage": {"total_tokens": 100},
    }


def test_openai_compat_client_builds_structured_request(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(_chat_payload("{}"))

    monkeypatch.setattr(aiclient.requests, "post", fake_post)
    cfg = ai.AIConfig(api_key=API_KEY, provider="groq",
                      base_url="http://localhost:11434/v1",
                      model="openai/gpt-oss-120b")
    cli = aiclient.OpenAICompatClient(cfg)
    request = ai.AIRequest(
        messages=({"role": "system", "content": "s"},
                  {"role": "user", "content": "u"}),
        json_schema=ai.OUTPUT_SCHEMA, max_tokens=500, temperature=0.0)
    response = cli.complete(request)
    url, kwargs = calls[0]
    assert url == "http://localhost:11434/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == f"Bearer {API_KEY}"
    body = kwargs["json"]
    assert body["model"] == "openai/gpt-oss-120b"
    response_format = body["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "ai_research_interpretation"
    assert response_format["json_schema"]["strict"] is True
    assert body["messages"] == [{"role": "system", "content": "s"},
                                {"role": "user", "content": "u"}]
    assert response.model == "fake-model"
    assert response.meta["format"] == "json_schema"


def test_openai_compat_timeout_raises(monkeypatch):
    def boom(*a, **k):
        raise requests.exceptions.Timeout("deadline")

    monkeypatch.setattr(aiclient.requests, "post", boom)
    cli = aiclient.OpenAICompatClient(ai.AIConfig(api_key=API_KEY))
    with pytest.raises(ai.AIProviderTimeout):
        cli.complete(ai.AIRequest(messages=({"role": "user", "content": "x"},)))


def test_openai_compat_unreachable_scrubs_key(monkeypatch):
    def boom(*a, **k):
        raise requests.exceptions.ConnectionError(
            f"cannot reach host?api_key={API_KEY}")

    monkeypatch.setattr(aiclient.requests, "post", boom)
    cli = aiclient.OpenAICompatClient(ai.AIConfig(api_key=API_KEY))
    with pytest.raises(ai.AIProviderUnavailable) as exc:
        cli.complete(ai.AIRequest(messages=({"role": "user", "content": "x"},)))
    assert API_KEY not in str(exc.value)
    assert "Bearer" not in str(exc.value)


def test_openai_compat_degrades_json_schema_to_json_object_on_400(monkeypatch):
    calls = []
    seq = [
        FakeResponse({"error": {"message": "model does not support response "
                                          "format json_schema"}}, status_code=400),
        FakeResponse(_chat_payload("{}")),
    ]

    def fake_post(*a, **k):
        calls.append(k["json"]["response_format"]["type"])
        return seq.pop(0)

    monkeypatch.setattr(aiclient.requests, "post", fake_post)
    cli = aiclient.OpenAICompatClient(ai.AIConfig(api_key=API_KEY))
    response = cli.complete(ai.AIRequest(
        messages=({"role": "user", "content": "x"},), json_schema=ai.OUTPUT_SCHEMA))
    assert calls == ["json_schema", "json_object"]
    assert response.meta["format"] == "json_object"


def test_openai_compat_double_400_raises(monkeypatch):
    def fake_post(*a, **k):
        return FakeResponse({"error": {"message": "400 again"}}, status_code=400)

    monkeypatch.setattr(aiclient.requests, "post", fake_post)
    cli = aiclient.OpenAICompatClient(ai.AIConfig(api_key=API_KEY))
    with pytest.raises(ai.AIProviderError) as exc:
        cli.complete(ai.AIRequest(
            messages=({"role": "user", "content": "x"},), json_schema=ai.OUTPUT_SCHEMA))
    assert API_KEY not in str(exc.value)


def test_openai_compat_404_discontinued_model_raises_clear_error(monkeypatch, caplog):
    """A 404 'model discontinued' payload must raise the actionable AI_MODEL
    error immediately (no json_schema -> json_object degrade retry is wasted),
    log a warning pointing at .streamlit/secrets.toml, and never leak the key."""
    calls = []

    def fake_post(*a, **k):
        calls.append(k["json"]["model"])
        return FakeResponse(
            {"error": {"message": "Model retired-model-123 discontinued"}},
            status_code=404)

    monkeypatch.setattr(aiclient.requests, "post", fake_post)
    cli = aiclient.OpenAICompatClient(
        ai.AIConfig(api_key=API_KEY, provider="groq", model="retired-model-123"))
    with caplog.at_level("WARNING", logger="lib.intelligence.ai.client"):
        with pytest.raises(ai.AIProviderError) as exc:
            cli.complete(ai.AIRequest(
                messages=({"role": "user", "content": "x"},),
                json_schema=ai.OUTPUT_SCHEMA))
    assert calls == ["retired-model-123"]  # failed fast, never degraded
    text = str(exc.value)
    assert "retired-model-123" in text
    assert "no longer supported" in text
    assert "update AI_MODEL" in text
    assert "https://console.groq.com/docs/models" in text
    assert API_KEY not in text
    assert "update AI_MODEL in .streamlit/secrets.toml" in caplog.text
    assert API_KEY not in caplog.text


def test_openai_compat_missing_content_raises(monkeypatch):
    bad = {"choices": [{"message": {}}]}
    monkeypatch.setattr(aiclient.requests, "post",
                        lambda *a, **k: FakeResponse(bad))
    cli = aiclient.OpenAICompatClient(ai.AIConfig(api_key=API_KEY))
    with pytest.raises(ai.AIProviderError):
        cli.complete(ai.AIRequest(messages=({"role": "user", "content": "x"},)))


def test_client_registry_and_unknown_provider():
    class MemClient:
        provider = "mem"
        model = "m"
        def complete(self, request, api_key=""):
            return ai.AIResponse(text="{}", provider="mem", model="m",
                                 created_at=None, latency_ms=0.0)

    ai.register_ai_provider("mem", lambda cfg: MemClient())
    try:
        cli = ai.build_client(ai.AIConfig(api_key="k", provider="mem"))
        assert cli.model == "m"
        with pytest.raises(ai.AIProviderError):
            ai.build_client(ai.AIConfig(api_key="k", provider="nope"))
    finally:
        ai.unregister_ai_provider("mem")


def test_ollama_local_is_keyless_and_registered():
    cfg = ai.AIConfig(api_key="", provider=ai.OLLAMA_LOCAL_PROVIDER,
                      base_url=ai.OLLAMA_BASE_URL, model=ai.OLLAMA_MODEL,
                      timeout_seconds=ai.OLLAMA_TIMEOUT_SECONDS)
    assert ai.provider_is_configured(cfg) is True
    assert ai.ai_config_status(cfg)["configured"] is True
    assert cfg.timeout_seconds == 120.0
    cli = ai.build_client(cfg)
    assert cli.provider == ai.OLLAMA_LOCAL_PROVIDER


def test_ollama_local_client_allows_empty_key(monkeypatch):
    monkeypatch.setattr(aiclient.requests, "post",
                        lambda url, **kwargs: FakeResponse(_chat_payload("{}")))
    cfg = ai.AIConfig(api_key="", provider=ai.OLLAMA_LOCAL_PROVIDER,
                      base_url=ai.OLLAMA_BASE_URL, model=ai.OLLAMA_MODEL,
                      timeout_seconds=ai.OLLAMA_TIMEOUT_SECONDS)
    cli = aiclient.OpenAICompatClient(cfg)
    resp = cli.complete(ai.AIRequest(messages=({"role": "user", "content": "x"},)))
    assert resp.provider == ai.OLLAMA_LOCAL_PROVIDER


# -------------------------------------------------------------- grounding ---

def test_known_evidence_ids_from_brief():
    assert ai.known_evidence_ids(_brief()) == frozenset(
        {"ev:test:1", "ev:test:2", "amfi:nav:TEST"})


def test_ground_assessment_downgrades_unknown_evidence():
    assessment = ai.parse_assessment(json.dumps(SAMPLE))
    known = frozenset({"ev:test:1", "amfi:nav:TEST", "ev:test:2"})
    assessment = ai.ground_assessment(assessment, known)
    assert all(f.grounded for f in assessment.findings)

    # now introduce a fabricated evidence id
    assessment = ai.parse_assessment(json.dumps(SAMPLE))
    known = frozenset({"ev:test:1"})
    assessment = ai.ground_assessment(assessment, known)
    bad = [f for f in assessment.findings if not f.grounded]
    assert bad
    assert any("unknown evidence" in (f.downgrade_reason or "") for f in bad)


def test_ground_assessment_fact_without_evidence_downgraded():
    text = json.loads(json.dumps(SAMPLE))
    text["key_findings"][0]["evidence_ids"] = []
    assessment = ai.parse_assessment(json.dumps(text))
    assessment = ai.ground_assessment(assessment, frozenset())
    fact_findings = [f for f in assessment.findings if f.kind == "fact"]
    failed = [f for f in fact_findings if not f.grounded]
    assert failed
    assert any("no evidence reference" in (f.downgrade_reason or "")
               for f in failed)


def test_inherit_fact_ids_matches_by_evidence():
    assessment = ai.parse_assessment(json.dumps(SAMPLE))
    risk = _brief().risks[0]
    assessment = ai.inherit_fact_ids(assessment, [risk])
    matching = [f for f in assessment.findings if "ev:test:1" in f.evidence_ids]
    assert matching
    assert all("class:fcnr:share_pct" in f.fact_ids for f in matching)


def test_validate_assessment_claims_downgrades_unknown_fact(monkeypatch):
    text = json.loads(json.dumps(SAMPLE))
    text["risks"] = [{"text": "claims a made-up fact", "evidence_ids": ["ev:test:1"],
                      "kind": "fact"}]
    assessment = ai.parse_assessment(json.dumps(text))
    brief = ai.inherit_fact_ids(assessment, [_brief().risks[0]])
    # force an inherited fact_id that is NOT in the facts we supply -> validate
    assessment = ai.validate_assessment_claims(brief, facts=_facts())
    synthesis = assessment.synthesis
    assert synthesis is not None
    all_supported = all(c.supported for c in synthesis.claims)
    if all_supported:
        # no inherited ids collided; add a bogus inheritance to prove the gate
        from dataclasses import replace

        bogus = replace(assessment, findings=(
            replace(assessment.findings[0], fact_ids=("made:up:fact",)),))
        bogus = ai.validate_assessment_claims(
            bogus, facts=_facts())
        assert not all(c.supported for c in bogus.synthesis.claims)
        assert any("validate_claims" in d for d in bogus.downgrades)
    else:
        assert any("validate_claims" in d for d in assessment.downgrades)


# --------------------------------------------------------------- pipeline ---

def test_run_not_configured_no_network(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise AssertionError("network call while not configured")

    monkeypatch.setattr(aiclient.requests, "post", boom)
    out = ai.run_ai_research(
        brief=_brief(), config=ai.AIConfig(api_key=""),
        facts=_facts())
    assert out.status == "failed"
    assert out.fallback_used is True
    assert "network call while not configured" in (out.reason or "")
    assert len(calls) == 1


def test_run_insufficient_evidence_no_network(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise AssertionError("network call on empty brief")

    monkeypatch.setattr(aiclient.requests, "post", boom)
    out = ai.run_ai_research(
        brief=_empty_brief(),
        config=ai.AIConfig(api_key=API_KEY), facts=_facts())
    assert out.status == "insufficient_evidence"
    assert out.fallback_used is True
    assert calls == []


def test_run_ok_with_mock_client():
    client = FakeClient(response_text=json.dumps(SAMPLE))
    out = ai.run_ai_research(
        brief=_brief(), config=ai.AIConfig(api_key=API_KEY),
        client=client, facts=_facts())
    assert out.status == "ok"
    assert out.fallback_used is False
    assert client.calls == [API_KEY]
    assessment = out.assessment
    assert assessment.provider == "fake"
    assert assessment.model == "fake-model"
    assert assessment.synthesis is not None
    assert assessment.synthesis.model == "ai:fake:fake-model"
    supported = [c for c in assessment.synthesis.claims if c.supported]
    assert any("Equity" in c.text for c in supported)
    # findings that cite only known evidence remain grounded
    assert all(f.grounded for f in assessment.findings)


def test_run_timeout_falls_back():
    client = FakeClient(error=ai.AIProviderTimeout("timed out at 30s"))
    out = ai.run_ai_research(
        brief=_brief(), config=ai.AIConfig(api_key=API_KEY),
        client=client, facts=_facts())
    assert out.status == "failed"
    assert out.fallback_used is True
    assert "timed out" in (out.reason or "")


def test_run_provider_error_scrubs_key():
    client = FakeClient(
        error=ai.AIProviderUnavailable(f"transport broke {API_KEY}"))
    out = ai.run_ai_research(
        brief=_brief(), config=ai.AIConfig(api_key=API_KEY),
        client=client, facts=_facts())
    assert out.status == "failed"
    assert API_KEY not in (out.reason or "")


class _LocalFakeClient:
    provider = ai.OLLAMA_LOCAL_PROVIDER
    model = "llama3.1:8b"

    def __init__(self, response_text=None, error=None):
        self.response_text = response_text
        self.error = error

    def complete(self, request, api_key=""):
        if self.error is not None:
            raise self.error
        return ai.AIResponse(
            text=self.response_text, provider=self.provider, model=self.model,
            created_at=None, latency_ms=5.0, meta={"format": "json_schema"})


def test_ai_research_cascades_to_ollama_on_groq_timeout(monkeypatch):
    from lib.intelligence.ai import pipeline as ai_pipe

    built = []

    def _build(cfg):
        built.append(cfg.provider)
        if cfg.provider == "groq":
            return _LocalFakeClient(
                error=ai.AIProviderTimeout("groq timed out after 30s"))
        if cfg.provider == ai.OLLAMA_LOCAL_PROVIDER:
            return _LocalFakeClient(response_text=json.dumps(SAMPLE))
        raise AssertionError(f"unexpected provider {cfg.provider}")

    monkeypatch.setattr(ai_pipe, "build_client", _build)
    out = ai_pipe.run_ai_research(
        brief=_brief(),
        config=ai.AIConfig(api_key=API_KEY, provider="groq",
                           model="openai/gpt-oss-120b"),
        client=None, facts=_facts(), now=NOW)
    assert out.status == "ok"
    assert built == ["groq", ai.OLLAMA_LOCAL_PROVIDER]  # Groq -> Ollama cascade
    assert out.assessment.provider == ai.OLLAMA_LOCAL_PROVIDER
    assert out.fallback_used is False  # the fallback itself succeeded


def test_ai_research_cascade_fails_when_ollama_unavailable(monkeypatch):
    from lib.intelligence.ai import pipeline as ai_pipe

    def _build(cfg):
        if cfg.provider == "groq":
            return _LocalFakeClient(
                error=ai.AIProviderTimeout("groq timed out after 30s"))
        return _LocalFakeClient(
            error=ai.AIProviderUnavailable("ollama refused connection"))

    monkeypatch.setattr(ai_pipe, "build_client", _build)
    out = ai_pipe.run_ai_research(
        brief=_brief(), config=ai.AIConfig(api_key=API_KEY, provider="groq"),
        client=None, facts=_facts(), now=NOW)
    assert out.status == "failed"  # Groq -> Ollama -> AI unavailable
    assert out.fallback_used is True
    assert "timed out" in (out.reason or "")


def test_ai_research_ollama_primary_is_keyless(monkeypatch):
    from lib.intelligence.ai import pipeline as ai_pipe

    monkeypatch.setattr(
        ai_pipe, "build_client",
        lambda cfg: _LocalFakeClient(response_text=json.dumps(SAMPLE)))
    cfg = ai.AIConfig(api_key="", provider=ai.OLLAMA_LOCAL_PROVIDER,
                      base_url=ai.OLLAMA_BASE_URL, model=ai.OLLAMA_MODEL,
                      timeout_seconds=ai.OLLAMA_TIMEOUT_SECONDS)
    out = ai_pipe.run_ai_research(brief=_brief(), config=cfg,
                                  client=None, facts=_facts(), now=NOW)
    assert out.status == "ok"
    assert out.provider == ai.OLLAMA_LOCAL_PROVIDER


def test_run_malformed_response_classified():
    client = FakeClient(response_text="certainly not JSON")
    out = ai.run_ai_research(
        brief=_brief(), config=ai.AIConfig(api_key=API_KEY),
        client=client, facts=_facts())
    assert out.status == "malformed"
    assert out.fallback_used is True
    assert out.assessment is None


def test_run_malformed_overall_recovers_to_ok():
    """The reported defect: overall_assessment arrives as an object. The
    pipeline must NOT return 'Malformed response' — it recovers text and marks
    the coercion in the downgrades the UI surfaces."""
    text = json.loads(json.dumps(SAMPLE))
    text["overall_assessment"] = {"summary": "Recovered summary from object form."}
    client = FakeClient(response_text=json.dumps(text))
    out = ai.run_ai_research(
        brief=_brief(), config=ai.AIConfig(api_key=API_KEY),
        client=client, facts=_facts())
    assert out.status == "ok"
    assert out.fallback_used is False
    assert out.assessment.overall_assessment == "Recovered summary from object form."
    assert any("overall_assessment" in d for d in out.assessment.downgrades)
    assert out.assessment.synthesis is not None


def test_run_logs_raw_response_redacted(caplog):
    """Diagnostic DEBUG logging captures the raw answer before validation and
    never leaks the API key into the logs (not shown in the UI)."""
    import logging

    text = json.loads(json.dumps(SAMPLE))
    text["overall_assessment"] = {"summary": f"summary echoing {API_KEY}"}
    client = FakeClient(response_text=json.dumps(text))
    with caplog.at_level(logging.DEBUG,
                        logger="lib.intelligence.ai.pipeline"):
        out = ai.run_ai_research(
            brief=_brief(), config=ai.AIConfig(api_key=API_KEY),
            client=client, facts=_facts())
    assert out.status == "ok"
    pipeline_records = [
        r for r in caplog.records
        if r.name == "lib.intelligence.ai.pipeline"
    ]
    raw = [r for r in pipeline_records if "raw response" in r.getMessage()]
    assert raw, "pipeline must log the raw response excerpt at DEBUG"
    assert API_KEY not in caplog.text
    assert "Bearer" not in caplog.text


def test_run_unknown_evidence_downgraded_in_outcome():
    text = json.loads(json.dumps(SAMPLE))
    text["risks"][0]["evidence_ids"] = ["invented:ev:id"]
    client = FakeClient(response_text=json.dumps(text))
    out = ai.run_ai_research(
        brief=_brief(), config=ai.AIConfig(api_key=API_KEY),
        client=client, facts=_facts())
    assert out.status == "ok"
    bad = [f for f in out.assessment.findings if not f.grounded]
    assert bad
    assert any("unknown evidence" in (f.downgrade_reason or "") for f in bad)
    assert any("invented:ev:id" not in s for s in out.assessment.overall_assessment)


def test_run_does_not_mutate_financials_or_caches(tmp_path, monkeypatch):
    import os

    brief = _brief()
    snapshot = (brief.totals.copy(), brief.evidence_count, brief.mapped_count,
                tuple(brief.changes))
    facts = _facts()
    cache_dir = tmp_path / "data" / "intel_gateway_cache"
    cache_dir.mkdir(parents=True)
    before = set(os.listdir(cache_dir))

    client = FakeClient(response_text=json.dumps(SAMPLE))
    out = ai.run_ai_research(
        brief=brief, config=ai.AIConfig(api_key=API_KEY),
        client=client, facts=facts, evidence=(_ev("ev:test:1"),))
    assert out.status == "ok"

    assert brief.totals == snapshot[0]
    assert brief.evidence_count == snapshot[1]
    assert brief.mapped_count == snapshot[2]
    assert tuple(brief.changes) == snapshot[3]
    assert [f.id for f in facts] == ["class:equity:share_pct", "class:fcnr:share_pct"]
    assert set(os.listdir(cache_dir)) == before


def test_page_load_paths_never_call_network(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise AssertionError("unexpected network call")

    monkeypatch.setattr(aiclient.requests, "post", boom)
    monkeypatch.setattr(aiclient.requests, "get", boom)

    cfg = ai.load_ai_config({"AI_API_KEY": "x"})
    status = ai.ai_config_status(cfg)
    assert status["configured"] is True
    ai.build_context(brief=_brief())
    ai.build_messages(brief=_brief())
    out2 = ai.run_ai_research(brief=_empty_brief(),
                              config=ai.AIConfig(api_key="x"))
    assert out2.status == "insufficient_evidence"
    assert calls == []


def test_validate_claims_wiring_uses_existing_framework():
    from lib.intelligence import provider as intel_provider

    claim = Claim(text="x", fact_ids=("class:equity:share_pct",))
    interp = Interpretation(model="ai:test", summary="s", claims=(claim,))
    briefing = Briefing(as_of=NOW, facts=_facts(), evidence=(), signals=())
    unsupported = intel_provider.validate_claims(interp, briefing)
    assert unsupported == ()

    lying = Claim(text="x", fact_ids=("bogus:number:inr",))
    interp = Interpretation(model="ai:test", summary="s", claims=(lying,))
    assert intel_provider.validate_claims(interp, briefing) == (lying,)