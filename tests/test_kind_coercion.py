"""AI kind coercion — production parse recovers unknown kinds instead of hard-failing."""
import json
from lib.intelligence import ai


def _sample():
    return {
        "overall_assessment": "Test assessment with enough text to pass minimum length checks for the parser.",
        "confidence": 0.5,
        "uncertainty": "Limited evidence in this unit test fixture.",
        "key_findings": [
            {"text": "A grounded finding for the unit test.", "evidence_ids": ["ev:test:1"], "kind": "fact"}
        ],
        "risks": [
            {"text": "A risk finding for the unit test.", "evidence_ids": ["ev:test:1"], "kind": "fact"}
        ],
        "opportunities": [],
        "research_needs": [],
    }


def test_parse_assessment_bad_kind_is_coerced():
    bad = json.loads(json.dumps(_sample()))
    bad["risks"][0]["kind"] = "recommendation"
    assessment = ai.parse_assessment(json.dumps(bad))
    assert any(f.kind == "interpretation" for f in assessment.findings)
    assert any("kind" in d and "coerced" in d.lower() for d in assessment.downgrades)
