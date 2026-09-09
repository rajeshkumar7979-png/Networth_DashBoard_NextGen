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


def _ev(eid, source_type=SourceType.NEWS, entity="TEST", payload=None):
    return make_evidence(
        eid=eid,
        source="test-source",
        source_class=SourceClass.B,
        source_type=source_type,
        entity=entity,
        title=f"headline {eid}",
        now=NOW,
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
    assert cfg.provider == "groq"
    assert cfg.model == "openai/gpt-oss-120b"
    assert cfg.base_url == "https://api.groq.com/openai/v1"
    assert cfg.api_key == ""


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
    assert cfg.max_evidence_catalog == 12


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


def test_parse_assessment_missing_overall_is_malformed():
    bad = dict(SAMPLE)
    bad.pop("overall_assessment")
    with pytest.raises(ai.AIOutputError):
        ai.parse_assessment(json.dumps(bad))


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
                      base_url="https://api.groq.com/openai/v1",
                      model="openai/gpt-oss-120b")
    cli = aiclient.OpenAICompatClient(cfg)
    request = ai.AIRequest(
        messages=({"role": "system", "content": "s"},
                  {"role": "user", "content": "u"}),
        json_schema=ai.OUTPUT_SCHEMA, max_tokens=500, temperature=0.0)
    response = cli.complete(request)
    url, kwargs = calls[0]
    assert url == "https://api.groq.com/openai/v1/chat/completions"
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
    assert out.status == "not_configured"
    assert out.fallback_used is True
    assert "AI_API_KEY" in (out.reason or "")
    assert calls == []


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


def test_run_malformed_response_classified():
    client = FakeClient(response_text="certainly not JSON")
    out = ai.run_ai_research(
        brief=_brief(), config=ai.AIConfig(api_key=API_KEY),
        client=client, facts=_facts())
    assert out.status == "malformed"
    assert out.fallback_used is True
    assert out.assessment is None


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