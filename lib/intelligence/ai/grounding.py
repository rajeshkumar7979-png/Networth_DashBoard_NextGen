"""Bounded verified context that must travel with the provider prompt.

run_ai_research() previously used facts and evidence only inside
validate_assessment_claims. The model never saw them. This module turns the
same objects into a short, id-bearing block and returns any ids that should
join the citation allow-list.
"""
from __future__ import annotations

_LIMIT = 12
_TEXT_LIMIT = 240


def _clip(value) -> str:
    text = str(value or "").strip().replace("\n", " ")
    if len(text) > _TEXT_LIMIT:
        return text[:_TEXT_LIMIT] + "\u2026"
    return text


def _field(item, *names):
    if item is None:
        return None
    if isinstance(item, dict):
        for name in names:
            if item.get(name) not in (None, ""):
                return item.get(name)
        return None
    for name in names:
        value = getattr(item, name, None)
        if value not in (None, ""):
            return value
    return None


def verified_context_block(facts=(), evidence=(), limit=_LIMIT):
    """Return (block, extra_ids). Empty block when nothing usable is present."""
    lines = []
    ids = []
    for fact in list(facts or [])[:limit]:
        text = _clip(_field(fact, "statement", "text", "title", "label"))
        if not text:
            continue
        fact_id = _field(fact, "id", "fact_id")
        if fact_id:
            ids.append(str(fact_id))
            lines.append("- fact id=%s: %s" % (fact_id, text))
        else:
            lines.append("- fact: %s" % text)
    for item in list(evidence or [])[:limit]:
        headline = _clip(_field(item, "headline", "title", "statement", "text"))
        evidence_id = _field(item, "id")
        source = _field(item, "source")
        if evidence_id:
            ids.append(str(evidence_id))
        if not headline and not evidence_id:
            continue
        bits = []
        if evidence_id:
            bits.append("id=%s" % evidence_id)
        if source:
            bits.append("source=%s" % _clip(source))
        if headline:
            bits.append(headline)
        lines.append("- evidence " + " | ".join(bits))
    if not lines:
        return "", ids
    block = "\n".join([
        "Verified facts and evidence already built by the desk "
        "(restate, do not recompute; cite only listed ids):",
        *lines,
    ])
    return block, ids
