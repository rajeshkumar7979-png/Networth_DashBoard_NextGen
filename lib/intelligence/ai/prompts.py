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

from lib.intelligence.ai.config import DEFAULT_MAX_EVIDENCE_CATALOG
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
    "object matching the schema named " + OUTPUT_NAME + " with EXACTLY these "
    "fields: overall_assessment — ONE plain string (1-3 sentences, never a "
    "nested object); confidence — a number between 0 and 1; uncertainty — ONE "
    "plain string; invalidation_conditions and limitations — arrays of plain "
    "strings; key_findings, risks, opportunities and research_needs — arrays "
    "of objects with text (string), evidence_ids (array of strings) and kind "
    "('fact' or 'interpretation')."
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


def _recency_ts(dev) -> float:
    """Newest-first recency key from the evidence's retrieved-at stamp."""
    prov = getattr(getattr(dev, "evidence", None), "provenance", None)
    ts = getattr(prov, "retrieved_at", None)
    if ts is None:
        return float("-inf")
    try:
        return ts.timestamp()
    except (OverflowError, OSError, ValueError):
        return float("-inf")


def _rank_developments(brief) -> tuple:
    """Rank external developments before the prompt is built:
    (a) portfolio-mapped developments first,
    (b) deterministic evidence-quality score descending,
    (c) most-recently retrieved evidence first.
    The ranked tuple is sliced to max_evidence so the prompt only ever carries
    the top-N records — never the full cached universe (which can run to
    thousands of records and overflow the model's token budget).
    """
    devs = list(getattr(brief, "external", ()) or ())

    def key(d):
        score = getattr(getattr(d, "quality", None), "score", None) or 0.0
        return (0 if bool(getattr(d, "mapped", False)) else 1,
                -float(score),
                -_recency_ts(d))

    return tuple(sorted(devs, key=key))


def build_context(*, brief, question=None, max_evidence=None) -> dict:
    """Assemble the complete AI context pack into a plain dict.

    The evidence catalog and citable-id allow-list are capped at max_evidence
    (default DEFAULT_MAX_EVIDENCE_CATALOG) after a deterministic ranking —
    portfolio-mapped first, quality descending, recency descending — so the
    prompt never carries the full cached evidence universe.

    Returns keys: system, user, question, allowed_evidence_ids (frozenset),
    catalog (list of dicts with id/category/mapped/source/quality/headline/
    snippet), total_available, truncated.
    """
    question = (question or DEFAULT_QUESTION).strip() or DEFAULT_QUESTION
    limit = max_evidence or DEFAULT_MAX_EVIDENCE_CATALOG

    # Pre-filter: rank mapped-first, quality-desc, recency-desc, then cap at
    # the catalog limit. With thousands of persisted records the prompt only
    # ever carries the top-N; the allow-list is bounded to exactly those plus
    # conclusion-cited ids (previously ALL external ids were listed, which blew
    # past the model's token budget on a 46k-token "request too large" error).
    all_devs = _rank_developments(brief)
    total_available = len(all_devs)
    selected = all_devs[:limit]
    truncated = total_available > limit

    catalog = []
    for dev in selected:
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
    for dev in selected:
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

    if total_available:
        scope = (f"You are analyzing the top-{len(selected)} most relevant "
                 f"developments out of {total_available} total records")
        if truncated:
            scope += (f". {total_available - len(selected)} lower-ranked "
                      "records were excluded; cite only the catalog above.")
        else:
            scope += "."
        system = _SYSTEM_ROLE + "\n\n" + scope
    else:
        system = _SYSTEM_ROLE

    if truncated:
        _catalog_heading = (
            f"External evidence catalog (only these records are citable"
            f" — top {len(selected)} of {total_available}; "
            "lower-ranked records truncated):")
    else:
        _catalog_heading = "External evidence catalog (only these records are citable):"

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
        _catalog_heading,
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
        "system": system,
        "user": user,
        "question": question,
        "allowed_evidence_ids": frozenset(allowed),
        "catalog": catalog,
        "allowed_ids_text": _USER_ALLOWED_HINT,
        "total_available": total_available,
        "truncated": truncated,
    }


def build_messages(*, brief, question=None, max_evidence=None) -> tuple:
    """Return (system_message, user_message) ready for a chat/completions call."""
    ctx = build_context(brief=brief, question=question, max_evidence=max_evidence)
    system = {"role": "system", "content": ctx["system"]}
    user = {"role": "user", "content": ctx["user"]}
    return system, user