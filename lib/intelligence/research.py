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
    Briefing,
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
    comparable (missing / single-row / legacy). Never invents."""
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
    trusted. A future real-AI synthesizer would implement the same protocol and
    still sit behind the same validator.
    """

    name = "research-deterministic"

    def synthesize(self, research, question=None):
        if not research.conclusions and not research.changes:
            return Interpretation(
                model=self.name,
                summary="Insufficient evidence: no research conclusions this run.",
                claims=(),
                confidence=None,
            )
        parts = []
        n_drv = sum(1 for c in research.changes if c.kind == "pnl_driver")
        if n_drv:
            parts.append(f"{n_drv} P&L driver(s) from {len(research.changes)} change row(s)")
        else:
            parts.append(f"{len(research.changes)} portfolio change row(s)")
        parts.append(f"{len(research.external)} external record(s) reviewed, "
                     f"{research.mapped_count} mapped to held entities")
        parts.append(f"{len(research.risks)} risk(s) at watch or above, "
                     f"{len(research.gaps)} evidence gap(s)")
        if question:
            parts.append(f"Prompt recorded: {question}")
        claims = tuple(
            Claim(text=f"[{c.topic}] {c.title}: {c.statement}", fact_ids=c.fact_ids, supported=True)
            for c in research.conclusions
        )
        confidences = [c.confidence for c in research.conclusions if c.confidence is not None]
        confidence = round(sum(confidences) / len(confidences), 3) if confidences else None
        return Interpretation(
            model=self.name,
            summary=" ".join(parts),
            claims=claims,
            confidence=confidence,
        )


def build_research_brief(*, facts, evidence=None, signals=None, drivers=None,
                         delta=None, portfolio_index=None, nav_evidence=None,
                         holdings_evidence=None, gateway_evidence=None,
                         question=None, now=None, synthesizer=None) -> ResearchBrief:
    """Assemble the evidence-based research brief.

    facts:                 ExposureFacts (see lib.intelligence.exposure)
    evidence:              EvidenceBag from build_evidence_bag (news/coverage/drivers/history)
    signals:               evaluate_signals output
    drivers:               decompose_current output (cc_drivers)
    delta:                 snapshot_delta output (from delta_from_history)
    portfolio_index:       build_portfolio_index output (exact-match relevance)
    nav/holdings/gateway_evidence: pre-built Evidence tuples; when None the
                   committed caches + gateway cache dir are read (still no network).

    Synthesizer failure never takes down the app: synthesis=None + reason.
    """
    now = now or getattr(facts, "as_of", None) or datetime.now()
    bag = evidence if evidence is not None else EvidenceBag(tuple())
    base_ev = tuple(getattr(bag, "items", ()) or ())

    ext = list(nav_evidence or ())
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
    if not any(e.provenance.source_type == SourceType.NEWS for e in base_ev):
        gaps.append("No news evidence this run (news feed unavailable).")
    cov = facts.coverage.coverage_pct
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
        gaps.append("No comparable prior snapshot (history.csv) available to "
                    "measure what changed.")
    elif not delta.get("available"):
        gaps.append(delta.get("reason")
                    or "Prior snapshot is legacy without a class breakdown.")
    if not ext_sorted:
        gaps.append("No external provider records available this run "
                    "(AMFI NAV / holdings / gateway caches empty).")
    unmapped_by_cat = {}
    for d in ext_sorted:
        if not d.mapped and d.category in ("filing", "macro"):
            unmapped_by_cat[d.category] = unmapped_by_cat.get(d.category, 0) + 1
    for cat, n in sorted(unmapped_by_cat.items()):
        gaps.append(f"{n} unmapped {cat} record(s) — not portfolio-specific; no exact identifier match.")

    conclusions = derive_conclusions(
        facts=facts,
        signals=signals,
        changes=changes,
        external_developments=ext_sorted,
        gaps=gaps,
    )

    all_facts = tuple(facts.all_facts())

    def _dedupe_evidence(items):
        seen = set()
        out = []
        for e in items:
            if e.id not in seen:
                seen.add(e.id)
                out.append(e)
        return tuple(out)

    all_evidence = _dedupe_evidence(base_ev + tuple(d.evidence for d in ext_sorted))
    validation_briefing = Briefing(
        as_of=now,
        facts=all_facts,
        evidence=all_evidence,
        signals=tuple(signals or ()),
    )

    brief = ResearchBrief(
        as_of=now,
        question=question,
        totals={
            "total_assets": float(getattr(facts, "total_assets", 0.0) or 0.0),
            "total_invested": float(getattr(facts, "total_invested", 0.0) or 0.0),
            "total_pnl": float(getattr(facts, "total_pnl", 0.0) or 0.0),
        },
        changes=changes,
        external=ext_sorted,
        risks=tuple(c for c in conclusions if c.topic == TOPIC_RISK),
        research_needs=tuple(c for c in conclusions if c.topic == TOPIC_RESEARCH_NEED),
        gaps=tuple(gaps),
        conclusions=conclusions,
        synthesis=None,
        synthesis_reason=None,
        evidence_count=len(all_evidence),
        mapped_count=mapped_count,
        not_a_cashflow_label=NOT_A_CASHFLOW_LABEL,
    )

    synth = None
    reason = None
    try:
        synth = (synthesizer or ResearchSynthesizer()).synthesize(brief, question=question)
    except Exception as exc:
        synth = None
        reason = f"Research synthesizer unavailable: {type(exc).__name__}: {exc}"
    if synth is not None:
        unsupported = validate_claims(synth, validation_briefing)
        if unsupported:
            unsup = set(unsupported)
            claims = tuple(c if c not in unsup else replace(c, supported=False)
                           for c in synth.claims)
            synth = replace(synth, claims=claims)

    return replace(brief, synthesis=synth, synthesis_reason=reason)