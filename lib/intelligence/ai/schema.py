# AI Research Provider v1 — strict output schema.
#
# This schema has two jobs:
#   1. Requested from the provider in Structured Outputs mode
#      (response_format {"type": "json_schema", "json_schema": {...}, "strict": true})
#      where the provider supports it.
#   2. Enforced locally regardless of provider mode, so a json_object or plain
#      response is validated by the exact same rules (parse.py).
#
# The schema is deliberately small: overall assessment + typed findings that
# carry evidence refs + confidence/uncertainty + invalidation/limitations.
# It mirrors the existing ResearchBrief shape (changes/risks/research_needs)
# instead of inventing a parallel taxonomy.
OUTPUT_NAME = "ai_research_interpretation"

ITEM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "text": {"type": "string", "minLength": 1},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "kind": {"type": "string", "enum": ["fact", "interpretation"]},
    },
    "required": ["text", "evidence_ids", "kind"],
}

STRING_ARRAY_SCHEMA = {"type": "array", "items": {"type": "string"}}

OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "overall_assessment": {"type": "string", "minLength": 1},
        "confidence": {"type": "number"},
        "uncertainty": {"type": "string"},
        "key_findings": {"type": "array", "items": ITEM_SCHEMA},
        "risks": {"type": "array", "items": ITEM_SCHEMA},
        "opportunities": {"type": "array", "items": ITEM_SCHEMA},
        "research_needs": {"type": "array", "items": ITEM_SCHEMA},
        "invalidation_conditions": STRING_ARRAY_SCHEMA,
        "limitations": STRING_ARRAY_SCHEMA,
    },
    "required": [
        "overall_assessment",
        "confidence",
        "uncertainty",
        "key_findings",
        "risks",
        "opportunities",
        "research_needs",
        "invalidation_conditions",
        "limitations",
    ],
}

# Findings are grouped into these sections (keys of OUTPUT_SCHEMA, minus scalars).
SECTIONS = ("key_findings", "risks", "opportunities", "research_needs")

ALLOWED_KINDS = ("fact", "interpretation")

# Per-section cap applied during local parsing so a runaway model answer can
# never flood the UI or the cache.
MAX_FINDINGS_PER_SECTION = 8