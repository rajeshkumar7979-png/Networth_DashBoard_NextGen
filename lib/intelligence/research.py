# -------------------------------------------------
# Portfolio Intelligence — Research & Synthesis v1.
#
# Answers the research questions a portfolio owner actually asks, deterministically
# and network-free:
#   * What materially changed this run?          -> build_change_summary
#   * Which external developments are relevant?  -> rank_external_developments
#   * What deserves attention? (risks)           -> derive_conclusions (signals)
#   * Where is the evidence thin?                -> evidence gaps
#   * What invalidates each conclusion?          -> ResearchConclusion.invalidation
#   * What are the research opportunities?       -> research_needs (decision-support,
#                                                  never orders)
#
# Architecture principle (SPEC/AGENTS contract):
#   portfolio truth (register/drivers/delta) + external verified evidence
#   (AMFI NAV / MF holdings / news / gateway cache records) -> deterministic
#   signals -> synthesis. Python stays the source of truth for financial facts.
#   Anything unprovable surfaces as Insufficient evidence — never a fabricated
#   number. No AI provider is connected: ResearchSynthesizer is deterministic
#   rule-based; a future AI can be wired through the existing provider registry
#   in lib.intelligence.provider, and its claims are still guarded by
#   validate_claims (unsupported claims are downgraded, never trusted).
#
# Pure module: no streamlit, no network. The gateway caches it reads are
# cache-read-only (section 8 of AGENTS.md).
# -------------------------------------------------
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Optional

from lib.drivers import DRIVER_KEYS, DRIVER_LABELS, NOT_A_CASHFLOW_LABEL, snapshot_delta
from lib.intelligence.evidence import EvidenceBag
from lib.intelligence.model import (
    Claim,
    Evidence,
    Interpretation,
    SourceType,
    slugify,
)
from lib.intelligence.provider import validate_claims
from lib.intelligence.sources.cache import Cache
from lib.intelligence.sources.mapping import assess_relevance
from lib.intelligence.sources.record import cached_result, parse_iso

TOPIC_CHANGE = "change"
TOPIC_RISK = "risk"
TOPIC_EXTERNAL = "external"
TOPIC_RESEARCH_NEED = "research_need"

STRONG = "strong"
MODERATE = "moderate"
WEAK = "weak"
INSUFFICIENT = "insufficient"

# Evidence-quality scoring constants (deterministic).
_BASE_SCORE = 0.50
_CLASS_BONUS = {"A": 0.25, "B": 0.15, "C": 0.00, "D": -0.15}
_MAPPED_BONUS = 0.15
_UNMAPPED_PENALTY = -0.05
_FRESH_DAYS = {SourceType.NEWS: 3, "default": 7}
_FRESH_BONUS = 0.10
_STALE_PENALTY = -0.10

# A change/statement that labels the invested difference must never sound like a
# cash flow, deposit, SIP, redemption or transaction.
CHANGE_EPSILON = 0.005


@dataclass(frozen=True)
class EvidenceQuality:
    """Deterministic 0-1 quality score for one piece of external evidence."""

    evidence_id: str
    score: float
    source_class: str
    fresh: bool
    relevance: str  # "mapped" | "unmapped" | "insufficient"
    basis: str      # human-readable reason for the score


@dataclass(frozen=True)
class ExternalDevelopment:
    evidence: Evidence
    quality: EvidenceQuality
    category: str  # nav | holdings | macro | filing | news | other
    headline: str
    mapped: bool
    matched: tuple[str, ...] = ()


@dataclass(frozen=True)
class PortfolioChange:
    kind: str  # pnl_driver | rounding_residual | total | invested_basis_change |
    #          # market_valuation_change | class_delta | insufficient
    label: str
    amount: Optional[float]
    cashflow_measurement: bool
    note: str


@dataclass(frozen=True)
class ResearchConclusion:
    id: str
    topic: str            # change | risk | external | research_need
    title: str
    statement: str
    strength: str         # strong | moderate | weak | insufficient
    confidence: Optional[float]
    fact_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    invalidation: str


@dataclass(frozen=True)
class ResearchBrief:
    as_of: datetime
    question: Optional[str]
    totals: dict
    changes: tuple[PortfolioChange, ...]
    external: tuple[ExternalDevelopment, ...]
    risks: tuple[ResearchConclusion, ...]
    research_needs: tuple[ResearchConclusion, ...]
    gaps: tuple[str, ...]
    conclusions: tuple[ResearchConclusion, ...]
    synthesis: Optional[Interpretation]
    synthesis_reason: Optional[str]
    evidence_count: int
    mapped_count: int
    not_a_cashflow_label: str


def _evidence_age_days(evidence, now):
    """Age of an evidence record in days (published/retrieved), or None."""
    payload = evidence.payload or {}
    stamp = parse_iso(payload.get("published_at")) if payload.get("published_at") else None
    if stamp is None:
        stamp = evidence.provenance.retrieved_at
    if stamp is None:
        return None
    try:
        return max((now - stamp).total_seconds() / 86400.0, 0.0)
    except TypeError:
        return None


def score_evidence(evidence, *, now=None, relevance="unmapped") -> EvidenceQuality:
    """Deterministic 0-1 quality score: source class + exact-match relevance +
    freshness. Explicit basis; never a hidden AI number."""
    now = now or datetime.now()
    cls = evidence.provenance.source_class.value
    score = _BASE_SCORE + _CLASS_BONUS.get(cls, 0.0)
    parts = [f"base 0.50, source class {cls}"]

    if relevance == "mapped":
        score += _MAPPED_BONUS
        parts.append("exact portfolio match +0.15")
    elif relevance == "unmapped":
        score += _UNMAPPED_PENALTY
        parts.append("no exact portfolio match -0.05")
    else:
        parts.append("record carries no identifiers")

    threshold = _FRESH_DAYS.get(evidence.provenance.source_type, _FRESH_DAYS["default"])
    age = _evidence_age_days(evidence, now)
    if age is None:
        fresh = False
        parts.append("age unknown (no date)")
    elif age <= threshold:
        fresh = True
        score += _FRESH_BONUS
        parts.append(f"age {age:.0f}d <= {threshold}d +0.10")
    else:
        fresh = False
        score += _STALE_PENALTY
        parts.append(f"age {age:.0f}d > {threshold}d -0.10")

    score = max(0.0, min(1.0, score))
    return EvidenceQuality(
        evidence_id=evidence.id,
        score=round(score, 3),
        source_class=cls,
        fresh=fresh,
        relevance=relevance,
        basis="; ".join(parts),
    )


def classify_external(evidence) -> str:
    """Coarse category of an external evidence record (deterministic)."""
    src = str(evidence.provenance.source or "").lower()
    if "fund-disclosures" in src or "mfdata" in src:
        return "holdings"
    if "amfi" in src:
        return "nav"
    if "fred" in src:
        return "macro"
    if "sec" in src:
        return "filing"
    if evidence.provenance.source_type == SourceType.NEWS:
        return "news"
    # Gateway Google News cache keys
    if "gnews" in src or "google" in src or "news" in src:
        return "news"
    return "other"


def headline_for(evidence, category, mapped, matched) -> str:
    """One-line, provenance-honest description of an external development."""
    title = evidence.title or evidence.id
    if category in ("holdings", "nav"):
        if mapped:
            return f"{title} — matches {', '.join(sorted(matched))}"
        return title
    if category == "macro":
        return f"{title} (macro — not portfolio-specific)"
    if category == "filing":
        return f"{title} (filing — not portfolio-specific)" if not mapped else title
    return title


def list_source_results(results) -> tuple:
    """Flatten ok SourceResults into canonical Evidence records (exact order)."""
    out = []
    for res in results or ():
        if res is None:
            continue
        if getattr(res, "status", "") != "ok":
            continue
        for rec in getattr(res, "records", ()):
            try:
                out.append(rec.to_evidence())
            except Exception:
                continue
    return tuple(out)


def gateway_cached_evidence(*, now=None, cache_dir=None) -> tuple:
    """Read any on-demand gateway cache (FRED/SEC) written by an earlier fetch.

    Cache-read-only: no network. A corrupt/unusable cache entry is skipped, never
    turned into a fabricated record.
    """
    now = now or datetime.now()
    cache = Cache(base_dir=cache_dir) if cache_dir else Cache()
    if not cache.base_dir.is_dir():
        return ()
    out = []
    for path in sorted(cache.base_dir.glob("*.json")):
        try:
            data = cache.load(path.stem)
        except Exception:
            continue
        provider = str(((data or {}).get("meta") or {}).get("provider") or "misc")
        result = cached_result(provider, data)
        if result is None:
            continue
        for rec in result.records:
            try:
                out.append(rec.to_evidence())
            except Exception:
                continue
    return tuple(out)


def delta_from_history(history_df):
    """snapshot_delta between the two latest history rows, or None when not
    comparable (missing / single-row / legacy). Never invents.

    Also accepts data/portfolio_history.csv rows (total_assets_inr schema).
    Those lack class_invested_* so snapshot_delta marks available=False —
    still useful for a honest totals-moved note without inventing drivers.
    """
    if history_df is None or getattr(history_df, "empty", True):
        try:
            from lib.history import load_portfolio_history
            history_df = load_portfolio_history()
        except Exception:
            history_df = None
    if history_df is None or getattr(history_df, "empty", True):
        return None
    try:
        if "date" not in history_df.columns:
            return None
        df = history_df.sort_values("date")
        if len(df) < 2:
            return None
        prev = df.iloc[-2].to_dict()
        curr = df.iloc[-1].to_dict()
        for row in (prev, curr):
            if row.get("net_worth") is None and row.get("total_assets_inr") is not None:
                try:
                    row["net_worth"] = float(row["total_assets_inr"])
                except (TypeError, ValueError):
                    pass
        return snapshot_delta(prev, curr)
    except Exception:
        return None


def build_change_summary(drivers=None, delta=None) -> tuple:
    """What materially changed this run. Invested-basis differences are called
    exactly what they are (NOT a cash flow); the label travels on every row."""
    changes = []
    if drivers:
        drv = drivers.get("drivers") or {}
        for key in DRIVER_KEYS:
            value = drv.get(key)
            if value is None:
                continue
            amount = float(value)
            if abs(amount) > CHANGE_EPSILON:
                changes.append(PortfolioChange(
                    kind="pnl_driver",
                    label=DRIVER_LABELS.get(key, key),
                    amount=amount,
                    cashflow_measurement=bool(drivers.get("cashflow_measurement", False)),
                    note="current-run P&L attributed to valuation",
                ))
        residual = drivers.get("residual")
        if residual is not None and abs(float(residual)) > CHANGE_EPSILON:
            bound = drivers.get("residual_bound")
            changes.append(PortfolioChange(
                kind="rounding_residual",
                label="FD rounding residual (labeled)",
                amount=float(residual),
                cashflow_measurement=False,
                note=(f"within documented bound {bound:.2f}, "
                      f"residual_ok={bool(drivers.get('residual_ok'))}")
                if bound is not None
                else f"residual_ok={bool(drivers.get('residual_ok'))}",
            ))
        if drivers.get("missing_fx"):
            changes.append(PortfolioChange(
                kind="insufficient",
                label="FCNR interest/FX split",
                amount=None,
                cashflow_measurement=False,
                note="USD/INR unavailable this run — FCNR interest vs FX on "
                     "principal is not split (never guessed)",
            ))
        total_pnl = drivers.get("total_pnl")
        if total_pnl is not None:
            changes.append(PortfolioChange(
                kind="total",
                label="Total current-run P&L",
                amount=float(total_pnl),
                cashflow_measurement=False,
                note=f"attributed {drivers.get('attributed')} + labeled residual "
                     f"{drivers.get('residual')}",
            ))

    if delta is not None:
        if delta.get("available"):
            t = delta.get("totals") or {}
            invested = t.get("invested_basis_change")
            market = t.get("market_valuation_change")
            if invested is not None:
                changes.append(PortfolioChange(
                    kind="invested_basis_change",
                    label="Invested-Basis Change",
                    amount=float(invested),
                    cashflow_measurement=False,
                    note=NOT_A_CASHFLOW_LABEL + " (delta between snapshots)",
                ))
            if market is not None:
                changes.append(PortfolioChange(
                    kind="market_valuation_change",
                    label="Market/Valuation Change",
                    amount=float(market),
                    cashflow_measurement=False,
                    note="change in current-minus-invested between snapshots",
                ))
            by_class = delta.get("by_class") or {}
            rows = [(cls, v) for cls, v in by_class.items() if v is not None]
            for cls, v in sorted(rows, key=lambda kv: -abs(kv[1]["delta_current"]))[:3]:
                changes.append(PortfolioChange(
                    kind="class_delta",
                    label=f"{cls} delta",
                    amount=float(v["delta_current"]),
                    cashflow_measurement=False,
                    note=(f"invested-basis {v['invested_basis_change']:+,.0f} + market "
                          f"{v['market_valuation_change']:+,.0f} ({NOT_A_CASHFLOW_LABEL})"),
                ))
            unattributed = delta.get("unattributed_abs")
            if unattributed is not None and abs(float(unattributed)) > CHANGE_EPSILON:
                changes.append(PortfolioChange(
                    kind="insufficient",
                    label="Unattributed snapshot delta",
                    amount=float(unattributed),
                    cashflow_measurement=False,
                    note="net-worth delta not explained by the enriched decomposition",
                ))
        else:
            changes.append(PortfolioChange(
                kind="insufficient",
                label="Snapshot delta (unattributed)",
                amount=delta.get("unattributed_abs"),
                cashflow_measurement=False,
                note=delta.get("reason")
                or "Prior snapshot is legacy (pre-Phase 1B) without a class breakdown.",
            ))
    return tuple(changes)


def _strength(confidence):
    if confidence is None:
        return INSUFFICIENT
    if confidence >= 0.8:
        return STRONG
    if confidence >= 0.6:
        return MODERATE
    if confidence >= 0.4:
        return WEAK
    return INSUFFICIENT


def derive_conclusions(*, facts, signals, changes, external_developments, gaps) -> tuple:
    """Deterministic conclusions: risks from elevated signals, change highlights,
    mapped external highlights, and explicit research needs where evidence is
    thin. Every conclusion carries an invalidation condition."""
    conclusions = []
    seen = set()

    def add(topic, title, statement, *, confidence, fact_ids=(), evidence_ids=(),
            invalidation="", cid=None):
        cid = cid or f"research:{topic}:{len(conclusions)}"
        if cid in seen:
            return
        seen.add(cid)
        conclusions.append(ResearchConclusion(
            id=cid,
            topic=topic,
            title=title,
            statement=statement,
            strength=_strength(confidence),
            confidence=confidence,
            fact_ids=tuple(fact_ids),
            evidence_ids=tuple(evidence_ids),
            invalidation=invalidation,
        ))

    for s in signals or ():
        if s.level not in ("critical", "warn", "watch"):
            continue
        add(
            TOPIC_RISK,
            title=s.label,
            statement=s.message,
            confidence=s.confidence if s.confidence is not None else 0.5,
            fact_ids=s.fact_ids,
            evidence_ids=s.evidence_ids,
            invalidation=s.invalidation or "Rule no longer fires.",
            cid=f"research:risk:{s.id}",
        )

    for c in sorted(changes, key=lambda ch: -abs(ch.amount) if ch.amount is not None else 0.0)[:3]:
        if c.kind in ("insufficient", "total") or c.amount is None:
            continue
        add(
            TOPIC_CHANGE,
            title=c.label,
            statement=f"{c.label} moved {c.amount:,.0f} INR this run — {c.note}.",
            confidence=0.85,
            invalidation="Attribution changes on a later run."
            if c.kind != "invested_basis_change"
            else "Invested basis is revised or the next snapshot replaces it.",
            cid=f"research:change:{c.kind}",
        )

    for d in [d for d in external_developments if d.mapped][:3]:
        add(
            TOPIC_EXTERNAL,
            title=d.headline,
            statement=(f"{d.headline} (source {d.evidence.provenance.source}, "
                       f"quality {d.quality.score:.2f})."),
            confidence=0.7 if d.quality.score >= 0.6 else 0.5,
            evidence_ids=(d.evidence.id,),
            invalidation="Source record is superseded or no longer relevant.",
            cid=f"research:external:{d.evidence.id}",
        )

    for s in signals or ():
        if s.id == "sig:matured_fd" and s.level == "critical":
            add(
                TOPIC_RESEARCH_NEED,
                title="Matured FD deployment",
                statement="Verify the prevailing renewal/default rate for matured "
                          "FD proceeds before any redeployment.",
                confidence=0.6 if (s.evidence_ids or s.fact_ids) else None,
                fact_ids=s.fact_ids,
                evidence_ids=s.evidence_ids,
                invalidation="Proceeds are collected or reinvested (workbook updated).",
                cid="research:need:matured_fd",
            )

    for gap in (gaps or ())[:5]:
        add(
            TOPIC_RESEARCH_NEED,
            title="Insufficient evidence",
            statement=gap,
            confidence=None,
            invalidation="The missing source becomes available on a later run.",
            cid=f"research:need:gap:{slugify(gap)[:48]}",
        )

    return tuple(conclusions)


class ResearchSynthesizer:
    """Deterministic rule-based synthesis over a ResearchBrief.

    The production default AI column for the research layer: composes the brief's
    structured conclusions into claims + a summary. Claims cite fact ids; the
    caller runs validate_claims so an unsupported claim is downgraded, never
    trusted. No LLM is called.
    """

    name = "research-deterministic"

    def synthesize(self, research: ResearchBrief, *, question=None) -> Interpretation:
        claims = []
        for c in research.conclusions:
            claims.append(Claim(
                id=c.id,
                text=c.statement,
                supported=c.strength != INSUFFICIENT,
                fact_ids=c.fact_ids,
                evidence_ids=c.evidence_ids,
            ))
        lines = []
        if research.risks:
            lines.append(f"{len(research.risks)} risk(s) at watch or above.")
        if research.changes:
            lines.append(f"{len(research.changes)} P&L driver(s) from change rows.")
        mapped = [d for d in research.external if d.mapped]
        if mapped:
            lines.append(f"{len(mapped)} external record(s) mapped to held entities.")
        if research.gaps:
            lines.append(f"{len(research.gaps)} evidence gap(s).")
        if question:
            lines.insert(0, f"Prompt recorded: {question}")
        summary = " ".join(lines) if lines else "No material findings this run."
        return Interpretation(
            provider=self.name,
            summary=summary,
            claims=tuple(claims),
            question=question or research.question,
            reason=f"{research.evidence_count} evidence · "
                   f"{research.mapped_count} mapped to held entities",
        )


def build_research_brief(*, facts, evidence=None, signals=None, drivers=None,
                         delta=None, portfolio_index=None, nav_evidence=None,
                         holdings_evidence=None, gateway_evidence=None,
                         question=None, now=None) -> ResearchBrief:
    """Assemble a ResearchBrief from portfolio truth + external verified evidence.

    Network-free. Missing inputs become gaps, never fabricated findings.
    """
    now = now or datetime.now()
    base_ev = tuple(evidence.items) if evidence is not None else ()
    all_evidence = list(base_ev)

    # External developments: NAV / holdings filings / gateway caches
    ext = []
    ext.extend(nav_evidence or ())
    if nav_evidence is None:
        from lib.intelligence.sources import load_mf_nav_evidence
        ext.extend(list_source_results((load_mf_nav_evidence(limit=2000, now=now),)))
    ext.extend(holdings_evidence or ())
    if holdings_evidence is None:
        from lib.intelligence.sources import load_mf_holdings_evidence
        ext.extend(list_source_results((load_mf_holdings_evidence(now=now),)))
    ext.extend(gateway_evidence or ())
    if gateway_evidence is None:
        ext.extend(gateway_cached_evidence(now=now))

    scored = []
    for ev in ext:
        res = None
        if portfolio_index is not None and not portfolio_index.is_empty:
            res = assess_relevance(ev, portfolio_index)
        relevance = res.status if res is not None else "unmapped"
        matched = res.matched if res is not None else ()
        q = score_evidence(ev, now=now, relevance=relevance)
        category = classify_external(ev)
        mapped = relevance == "mapped"
        scored.append(ExternalDevelopment(
            evidence=ev,
            quality=q,
            category=category,
            headline=headline_for(ev, category, mapped, matched),
            mapped=mapped,
            matched=matched,
        ))

    def _sort_key(d):
        order = 0 if d.mapped else (1 if d.category in ("news", "macro") else 2)
        return (order, -d.quality.score)

    ext_sorted = tuple(sorted(scored, key=_sort_key))
    mapped_count = sum(1 for d in ext_sorted if d.mapped)

    changes = build_change_summary(drivers=drivers, delta=delta)

    gaps = []
    _has_news_base = any(
        getattr(getattr(e, "provenance", None), "source_type", None) == SourceType.NEWS
        for e in base_ev
    )
    _has_news_ext = any(d.category in ("news", "macro") for d in ext_sorted)
    if not _has_news_base and not _has_news_ext:
        gaps.append("No news evidence this run (news feed unavailable).")
    elif not _has_news_base and _has_news_ext:
        # Gateway/cache news present; not a feed outage.
        pass
    coverage = getattr(facts, "coverage", None)
    cov = getattr(coverage, "coverage_pct", None) if coverage is not None else None
    if cov is None:
        gaps.append("No MF portfolio disclosures available — stock-level look-through blocked.")
    elif cov < 70:
        gaps.append(
            f"MF holdings disclosure coverage is {cov:.0f}% "
            f"({facts.coverage.missing_funds} fund(s) uncovered).")
    if drivers is not None and drivers.get("missing_fx"):
        gaps.append("USD/INR live rate missing — FCNR interest vs FX on principal "
                    "not split this run.")
    if delta is None:
        gaps.append(
            "No comparable prior snapshot for day-over-day change "
            "(need 2+ rows in data/portfolio_history.csv or history.csv)."
        )
    elif not delta.get("available"):
        gaps.append(delta.get("reason")
                    or "Prior snapshot is legacy without a class breakdown — "
                       "totals can still be compared; per-class drivers need enriched rows.")

    unmapped_by_cat = {}
    for d in ext_sorted:
        if not d.mapped and d.category in ("filing", "macro"):
            unmapped_by_cat[d.category] = unmapped_by_cat.get(d.category, 0) + 1
    for cat, n in sorted(unmapped_by_cat.items()):
        gaps.append(f"{n} unmapped {cat} record(s) — not portfolio-specific; no exact identifier match.")

    conclusions = derive_conclusions(
        facts=facts,
        signals=signals or (),
        changes=changes,
        external_developments=ext_sorted,
        gaps=gaps,
    )
    risks = tuple(c for c in conclusions if c.topic == TOPIC_RISK)
    research_needs = tuple(c for c in conclusions if c.topic == TOPIC_RESEARCH_NEED)

    totals = {
        "net_worth": getattr(getattr(facts, "totals", None), "net_worth", None),
        "total_assets": getattr(getattr(facts, "totals", None), "total_assets", None),
        "evidence_count": len(all_evidence) + len(ext),
        "mapped_count": mapped_count,
    }

    brief = ResearchBrief(
        as_of=now,
        question=question,
        totals=totals,
        changes=changes,
        external=ext_sorted,
        risks=risks,
        research_needs=research_needs,
        gaps=tuple(gaps),
        conclusions=conclusions,
        synthesis=None,
        synthesis_reason=None,
        evidence_count=len(all_evidence) + len(ext),
        mapped_count=mapped_count,
        not_a_cashflow_label=NOT_A_CASHFLOW_LABEL,
    )

    try:
        synth = ResearchSynthesizer().synthesize(brief, question=question)
        # Guard: drop unsupported claims
        guarded = validate_claims(synth, facts=facts, evidence=EvidenceBag(items=tuple(all_evidence)))
        brief = replace(brief, synthesis=guarded, synthesis_reason=synth.reason)
    except Exception as exc:
        brief = replace(brief, synthesis=None, synthesis_reason=str(exc))

    return brief
