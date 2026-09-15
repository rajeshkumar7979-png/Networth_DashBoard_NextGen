# AI Research Provider v1 — structured-output parsing and strict local
# validation. Works regardless of whether the provider used Structured Outputs
# (json_schema), json_object mode, or plain text that happened to be JSON.
#
# Robustness rule: structural shape (arrays/objects/kinds) is validated
# strictly — a genuinely broken answer stays malformed. The two scalar string
# fields that providers most often drift on (overall_assessment, uncertainty)
# are recovered best-effort with a labeled downgrade instead of failing the
# whole answer, so an otherwise usable response still surfaces in the UI.
from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from typing import Optional

from lib.intelligence.ai.client import AIOutputError
from lib.intelligence.ai.model import AIAssessment, AIFinding
from lib.intelligence.ai.schema import (
    ALLOWED_KINDS,
    MAX_FINDINGS_PER_SECTION,
    SECTIONS,
)

logger = logging.getLogger(__name__)

# Bounded length for any recovered scalar string field (never an unbounded
# echo of a runaway answer into the UI or the synthesis summary).
MAX_SCALAR_TEXT = 1500

_OVERALL_ASSESSMENT_FALLBACK = (
    "No overall assessment was provided by the model. The deterministic "
    "findings below carry the analysis."
)

_UNCERTAINTY_FALLBACK = "The model did not state an uncertainty level."


def extract_json_object(text: str) -> dict:
    """Recover a JSON object from model output, tolerating fences/trailing text.

    Raises AIOutputError if no valid object can be recovered.
    """
    if not text or not str(text).strip():
        raise AIOutputError("Empty model response.")

    candidate = str(text).strip()

    # 1) Direct parse.
    try:
        value = json.loads(candidate)
        if isinstance(value, dict):
            return value
    except (ValueError, TypeError):
        pass

    # 2) Code fence (```json ... ```).
    if candidate.startswith("```"):
        body = candidate.strip("`")
        for splitter in ("json", "JSON"):
            if body.startswith(splitter):
                body = body[len(splitter):].lstrip("\r\n \t")
                break
        _, _, body = body.partition("{")
        if body:
            body = "{" + body
        try:
            value = json.loads(body)
            if isinstance(value, dict):
                return value
        except (ValueError, TypeError):
            pass

    # 3) Balanced-brace scan over the whole string.
    start = candidate.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(candidate)):
            ch = candidate[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(candidate[start:i + 1])
                        if isinstance(value, dict):
                            return value
                    except (ValueError, TypeError):
                        pass
                    break
        start = candidate.find("{", start + 1)

    raise AIOutputError("Model response is not a recoverable JSON object: "
                        f"prefix={candidate[:60]!r}…")


def _as_str(value, field: str) -> str:
    if not isinstance(value, str):
        raise AIOutputError(f"Field '{field}' must be a string.")
    return value.strip()


def _clip_scalar(text: str, field: str, downgrades: list) -> str:
    if len(text) > MAX_SCALAR_TEXT:
        downgrades.append(
            f"Field '{field}' was truncated to {MAX_SCALAR_TEXT} characters.")
        return text[:MAX_SCALAR_TEXT] + "…"
    return text


def _coerce_scalar_text(value, field: str, fallback: str, downgrades: list) -> str:
    """Recover a plain string for a scalar field the model emitted wrongly.

    Structured-output drift occasionally makes a provider return a JSON
    object, list, boolean, or null where the schema demands a plain string
    (that is the observed defect behind "overall_assessment must be a
    string"). Instead of failing the whole answer we coerce the value to a
    bounded plain string and record a downgrade, which the UI surfaces under
    "Grounding / validation notes".
    """
    if isinstance(value, str):
        text = value.strip()
        if not text:
            downgrades.append(
                f"Field '{field}' was empty; used a fallback statement.")
            return fallback
        return _clip_scalar(text, field, downgrades)
    if value is None:
        downgrades.append(
            f"Field '{field}' was missing; used a fallback statement.")
        return fallback
    logger.debug("Coercing AI scalar field '%s' from %s",
                 field, type(value).__name__)
    if isinstance(value, bool):
        downgrades.append(f"Field '{field}' was boolean; coerced to text.")
        return "Yes" if value else "No"
    if isinstance(value, dict):
        for key in ("text", "summary", "overall_assessment", "assessment",
                    "statement", "content", "value"):
            inner = value.get(key)
            if isinstance(inner, str) and inner.strip():
                downgrades.append(
                    f"Field '{field}' was an object; used its '{key}' value.")
                return _clip_scalar(inner.strip(), field, downgrades)
        downgrades.append(
            f"Field '{field}' was an object without a usable text key; "
            "JSON-serialized (truncated).")
        serialized = json.dumps(value, ensure_ascii=False, default=str)
        return _clip_scalar(serialized, field, downgrades)
    if isinstance(value, list):
        parts = [p.strip() for p in value if isinstance(p, str) and p.strip()]
        if parts:
            downgrades.append(
                f"Field '{field}' was a list; joined its string items.")
            return _clip_scalar(" ".join(parts), field, downgrades)
        downgrades.append(
            f"Field '{field}' was a list of non-strings; used a fallback "
            "statement.")
        return fallback
    downgrades.append(
        f"Field '{field}' was {type(value).__name__}; coerced to text.")
    return _clip_scalar(str(value), field, downgrades)


def _as_str_list(value, field: str):
    if value is None:
        return ()
    if not isinstance(value, list):
        raise AIOutputError(f"Field '{field}' must be a list of strings.")
    out = []
    for item in value:
        if not isinstance(item, str):
            raise AIOutputError(f"Field '{field}' contains a non-string item.")
        text = item.strip()
        if text:
            out.append(text)
    return tuple(out)


def _confidence(value, field: str = "confidence") -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AIOutputError(f"Field '{field}' must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise AIOutputError(f"Field '{field}' must be finite.")
    return max(0.0, min(1.0, number))


def _findings(data: dict, downgrades: list) -> tuple:
    findings = []
    for section in SECTIONS:
        rows = data.get(section)
        if rows is None:
            continue
        if not isinstance(rows, list):
            raise AIOutputError(f"Field '{section}' must be a list.")
        for index, row in enumerate(rows[:MAX_FINDINGS_PER_SECTION]):
            if not isinstance(row, dict):
                raise AIOutputError(f"Field '{section}[{index}]' must be an object.")
            text = _as_str(row.get("text"), f"{section}[{index}].text")
            if not text:
                raise AIOutputError(f"Field '{section}[{index}].text' is empty.")
            kind = row.get("kind") or "interpretation"
            if kind not in ALLOWED_KINDS:
                raise AIOutputError(
                    f"Field '{section}[{index}].kind' must be one of "
                    f"{ALLOWED_KINDS}.")
            evidence_ids = row.get("evidence_ids") or []
            if not isinstance(evidence_ids, list) or any(
                    not isinstance(e, str) for e in evidence_ids):
                raise AIOutputError(
                    f"Field '{section}[{index}].evidence_ids' must be a list of "
                    "strings.")
            findings.append(AIFinding(
                section=section,
                text=text,
                evidence_ids=tuple(e.strip() for e in evidence_ids if e.strip()),
                kind=kind,
            ))
        if len(rows) > MAX_FINDINGS_PER_SECTION:
            excess = len(rows) - MAX_FINDINGS_PER_SECTION
            downgrades.append(
                f"Truncated {excess} finding(s) in '{section}' beyond the "
                "per-section cap.")
    return tuple(findings)


def parse_assessment(
        text: str,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        now: Optional[datetime] = None,
        latency_ms: float = 0.0,
        requested_format: str = "json_schema") -> AIAssessment:
    """Validate a model answer against OUTPUT_SCHEMA and build an AIAssessment.

    Structural violations raise AIOutputError so the pipeline can classify the
    attempt as malformed rather than trust a partially-usable answer.
    """
    data = extract_json_object(text)
    if not isinstance(data, dict):
        raise AIOutputError("Model response is not a JSON object.")

    downgrades = []
    overall = _coerce_scalar_text(
        data.get("overall_assessment"), "overall_assessment",
        _OVERALL_ASSESSMENT_FALLBACK, downgrades)
    confidence = _confidence(data.get("confidence"))
    uncertainty = _coerce_scalar_text(
        data.get("uncertainty"), "uncertainty",
        _UNCERTAINTY_FALLBACK, downgrades)

    findings = _findings(data, downgrades)

    invalidation = _as_str_list(data.get("invalidation_conditions"),
                                "invalidation_conditions")
    limitations = _as_str_list(data.get("limitations"), "limitations")

    return AIAssessment(
        overall_assessment=overall,
        confidence=confidence,
        uncertainty=uncertainty,
        findings=findings,
        invalidation_conditions=invalidation,
        limitations=limitations,
        provider=provider,
        model=model,
        created_at=now or datetime.now(),
        latency_ms=latency_ms,
        downgrades=tuple(downgrades),
        requested_format=requested_format,
    )