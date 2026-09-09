# AI Research Provider v1 — structured prompt/context generation.
#
# This module builds the exact payload sent to an external AI provider on an
# EXPLICIT user action. Only the minimum verified context needed for an
# evidence-grounded research summary is included:
#   * deterministic portfolio numbers (totals + change rows) already computed
#     by the Python layer — the model may RESTATE them, never recompute them;
#   * a bounded evidence catalog (headline + source + quality + a small scalar
#     snippet) — NEVER raw disclosures, holdings dumps, or payload blobs;
#   * an explicit allow-list of evidence ids the model may cite.
# Raw portfolio data (positions/account numbers/holder names) is never sent.
#
# The model is told it is a Grounded Analyst: it may interpret the supplied
# context and must express uncertainty; it must not fabricate numbers, must not
# give personalized tax/investment advice beyond caveated guidance, must not
# produce buy/sell/hold/trade instructions, and must only emit the JSON shape
# defined in schema.py.
from __future__ import annotations

import math

from lib.intelligence.ai.schema import OUTPUT_NAME
from lib.intelligence.research import classify_external

DEFAULT_QUESTION = "What changed, and where is the evidence thin?"

_SYSTEM_ROLE = (
    "You are the Grounded Analyst for a family investment intelligence system. "
    "You interpret a verified context pack and answer in a strict JSON schema "
    "only. You never perform financial calculation: every number in your answer "
    "must already appear in the supplied context (restate, do not recompute). "
    "You never fabricate values, transactions, cash flows, XIRR, SIP history, "
    "tax conclusions, or corporate actions. If a number or answer is not "
    "supported by the supplied context, say so explicitly and lower your "
    "confidence. Mark each finding as a deterministic 'fact' (directly "
    "supported by the cited evidence) or an 'interpretation' (your reasoning "
    "over the evidence). Only reference evidence ids from the supplied allow-"
    "list. End-of-answer uncertainty and limitations are mandatory. You never "
    "give buy/sell/hold/trade, execution, or personalized tax/investment "
    "instructions; output is decision-support only. Respond with a single JSON "
    "object matching the schema named " + OUTPUT_NAME + "."
)

# Static per-answer constraints appended inside the user prompt (present in
# every generated context, including the production pipeline path).
_USER_ALLOWED_HINT = (
    "Rules: respond ONLY with the " + OUTPUT_NAME + " JSON object; cite only "
    "ids from the allowed list; kind must be 'fact' (directly supported by "
    "cited evidence) or 'interpretation'; if evidence is thin or a gap is "
    "listed, say so and reduce confidence; confidence is 0..1; do not invent "
    "numbers, cash flows, transactions, returns, SIP history, tax "
    "consequences, or corporate actions; nothing here is trading advice."
)

# Small scalar payload keys allowed into the catalog snippet, per category.
_SNIPPET_KEYS = {
    "nav": ("nav", "nav_date", "as_of", "as_of_date", "currency"),
    "holdings": ("fund_name", "as_of_date", "holdings_count", "scheme_name"),
    "macro": ("value", "date", "series_name", "observation_date"),
    "filing": ("filed_date", "form_type", "cik", "company_name"),
    "news": (),
    "other": (),
}

_SNIPPET_VALUE_MAX = 120


def _inr(value) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(f):
        return "—"
    sign = "-" if f < 0 else ""
    return f"{sign}{abs(f):,.0f}"


def _clean_text(value, limit=200) -> str:
    text = str(value or "").strip()
    return (text[:limit] + "…") if len(text) > limit else text


def _evidence_snippet(evidence) -> str:
    """A bounded, flat snippet for one evidence item — never the raw payload."""
    keys = _SNIPPET_KEYS.get(classify_external(evidence), ())
    parts = []
    for key in keys:
        value = evidence.payload.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, (list, dict)):
            value = f"{len(value)} items"
        text = _clean_text(str(value), _SNIPPET_VALUE_MAX)
        parts.append(f"{key}={text}")
    return " · ".join(parts)


def _changes_block(brief) -> str:
    if not brief.changes:
        return "(no change rows this run)"
    lines = []
    for c in brief.changes:
        amount = _inr(c.amount) if c.amount is not None else "n/a"
        lines.append(f"- {c.kind.replace('_', ' ')}: {c.label} — {amount} INR. {c.note}")
    return "\n".join(lines)


def _conclusions_block(title, conclusions) -> str:
    if not conclusions:
        return "(none)"
    lines = []
    for c in conclusions:
        lines.append(f"- [{c.strength}] {c.title}: {c.statement} "
                     f"(invalidated by: {c.invalidation or 'n/a'})")
    return f"{title}:\n" + "\n".join(lines)


def _catalog_block(catalog) -> str:
    if not catalog:
        return "(no external evidence records this run)"
    lines = []
    for item in catalog:
        snippet = f" — {item['snippet']}" if item["snippet"] else ""
        lines.append(
            f"- id={item['id']} | category={item['category']} | "
            f"mapped={'yes' if item['mapped'] else 'no'} | "
            f"source={item['source']} | quality={item['quality']:.2f} | "
            f"headline={item['headline']}{snippet}")
    return "\n".join(lines)


def build_context(*, brief, question=None, max_evidence=None) -> dict:
    """Assemble the complete AI context pack into a plain dict.

    Returns keys: system, user, question, allowed_evidence_ids (frozenset),
    catalog (list of dicts with id/category/mapped/source/quality/headline/
    snippet).
    """
    question = (question or DEFAULT_QUESTION).strip() or DEFAULT_QUESTION
    limit = max_evidence or 12

    catalog = []
    for dev in (brief.external or ())[:limit]:
        evidence = dev.evidence
        provenance = evidence.provenance
        snippet = _evidence_snippet(evidence)
        catalog.append({
            "id": evidence.id,
            "category": dev.category,
            "mapped": dev.mapped,
            "source": provenance.source,
            "quality": dev.quality.score,
            "headline": _clean_text(dev.headline, 200),
            "snippet": snippet,
        })

    allowed = set()
    for dev in brief.external or ():
        allowed.add(dev.evidence.id)
    for c in brief.conclusions or ():
        allowed.update(c.evidence_ids)

    totals = getattr(brief, "totals", None) or {}
    total_assets = _inr(totals.get("total_assets") if totals else None)
    total_invested = _inr(totals.get("total_invested") if totals else None)
    total_pnl = _inr(totals.get("total_pnl") if totals else None)

    as_of_line = ""
    if brief.as_of is not None:
        as_of_line = brief.as_of.strftime("%d %b %Y %H:%M %Z")

    user = "\n".join([
        "Portfolio research brief (deterministic, verified context only).",
        f"As of: {as_of_line}",
        "",
        "Verified deterministic totals (already computed — restate, never recompute):",
        f"  Total assets (INR): {total_assets}",
        f"  Total invested (INR): {total_invested}",
        f"  Total P&L (INR): {total_pnl}",
        "",
        "What changed this run (label — amount INR. note):",
        _changes_block(brief),
        "",
        _conclusions_block("Deterministic risks", brief.risks or ()),
        "",
        _conclusions_block("Deterministic research needs", brief.research_needs or ()),
        "",
        "Evidence gaps (explicit insufficiencies):",
        "\n".join(f"- {g}" for g in (brief.gaps or ())) or "(none)",
        "",
        "External evidence catalog (only these records are citable):",
        _catalog_block(catalog),
        "",
        "Allowed evidence ids (cite ONLY these):",
        ", ".join(sorted(allowed)) if allowed else "(none — the evidence base is empty)",
        "",
        "Research question: " + question,
        "",
        _USER_ALLOWED_HINT,
    ])

    return {
        "system": _SYSTEM_ROLE,
        "user": user,
        "question": question,
        "allowed_evidence_ids": frozenset(allowed),
        "catalog": catalog,
        "allowed_ids_text": _USER_ALLOWED_HINT,
    }


def build_messages(*, brief, question=None, max_evidence=None) -> tuple:
    """Return (system_message, user_message) ready for a chat/completions call."""
    ctx = build_context(brief=brief, question=question, max_evidence=max_evidence)
    system = {"role": "system", "content": ctx["system"]}
    user = {"role": "user", "content": ctx["user"]}
    return system, user