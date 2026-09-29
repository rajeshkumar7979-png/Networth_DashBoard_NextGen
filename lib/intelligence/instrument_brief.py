# Instrument-scoped research brief for the Holdings dossier AI button.
from __future__ import annotations

from datetime import datetime

from lib.intelligence.model import (
    Evidence,
    FactKind,
    Provenance,
    SourceClass,
    SourceType,
)
from lib.intelligence.research import (
    EvidenceQuality,
    ExternalDevelopment,
    PortfolioChange,
    ResearchBrief,
    classify_external,
)


def _now(brief) -> datetime:
    return getattr(brief, "as_of", None) or datetime.now()


def _tokens(*parts) -> set:
    out = set()
    for p in parts:
        s = str(p or "").strip().upper()
        if not s or s in {"N/A", "NONE", "—"}:
            continue
        out.add(s)
        for chunk in s.replace("-", " ").replace("/", " ").split():
            if len(chunk) >= 3:
                out.add(chunk)
    return out


def _mentions(dev, tokens):
    if not tokens:
        return False
    blob = " ".join([
        str(getattr(dev, "headline", "") or ""),
        " ".join(getattr(dev, "matched", ()) or ()),
        str(getattr(getattr(dev, "evidence", None), "title", "") or ""),
        str((getattr(getattr(dev, "evidence", None), "payload", None) or {})),
    ]).upper()
    return any(tok in blob for tok in tokens if len(tok) >= 4)


def _synth_evidence(
    eid,
    title,
    source,
    entity,
    now,
    payload,
    source_class=SourceClass.A,
    source_type=SourceType.OBSERVED,
):
    ev = Evidence(
        id=eid,
        provenance=Provenance(
            source=source,
            source_class=source_class,
            source_type=source_type,
            retrieved_at=now,
            entity=entity,
            fact_kind=FactKind.FACT,
            confidence=1.0,
            reference=eid,
        ),
        title=title,
        payload=payload,
    )
    return ExternalDevelopment(
        evidence=ev,
        quality=EvidenceQuality(
            evidence_id=eid,
            score=0.9,
            source_class=source_class.value,
            fresh=True,
            relevance="mapped",
            basis="instrument register / observed tape on this dossier",
        ),
        category=(
            classify_external(ev)
            if source_type != SourceType.OBSERVED
            else "other"
        ),
        headline=title,
        mapped=True,
        matched=(entity,),
    )


def build_instrument_brief(
    *,
    parent,
    kind,
    name,
    member,
    isin="",
    symbol="",
    current_value=None,
    invested=None,
    pnl=None,
    simple_roi=None,
    lump_sum_ann=None,
    days_held=None,
    qty=None,
    avg_buy=None,
    last_price=None,
    y1=None,
    y3=None,
    y5=None,
    vs_n1=None,
    vs_n3=None,
    vs_n5=None,
    lookthrough=None,
    tape=None,
):
    now = _now(parent) if parent is not None else datetime.now()
    entity = (name or symbol or isin or "instrument").strip()
    tokens = _tokens(name, isin, symbol)

    def _f(v):
        try:
            n = float(v)
            return n if n == n else None
        except (TypeError, ValueError):
            return None

    cur = _f(current_value)
    inv = _f(invested)
    pnl_n = _f(pnl)
    if pnl_n is None and cur is not None and inv is not None:
        pnl_n = cur - inv
    totals = {"total_assets": cur, "total_invested": inv, "total_pnl": pnl_n}
    changes = []
    if pnl_n is not None:
        changes.append(PortfolioChange(
            kind="market_valuation_change",
            label=f"{entity} register P&L",
            amount=pnl_n,
            cashflow_measurement=False,
            note="current minus book cost on this single purchase record — not XIRR",
        ))
    if simple_roi is not None:
        changes.append(PortfolioChange(
            kind="total",
            label=f"{entity} simple ROI %",
            amount=_f(simple_roi),
            cashflow_measurement=False,
            note="(current-invested)/invested; not annualized",
        ))
    external = []
    payload = {
        "instrument": entity,
        "kind": kind,
        "member": member,
        "isin": isin or "",
        "symbol": symbol or "",
        "current_value_inr": cur,
        "invested_inr": inv,
        "pnl_inr": pnl_n,
        "simple_roi_pct": _f(simple_roi),
        "lump_sum_annualized_pct": _f(lump_sum_ann),
        "days_held": days_held,
        "quantity": qty,
        "avg_buy": _f(avg_buy),
        "last_price": _f(last_price),
        "scheme_1y_pct": _f(y1),
        "scheme_3y_pct": _f(y3),
        "scheme_5y_pct": _f(y5),
        "vs_nifty_1y": _f(vs_n1),
        "vs_nifty_3y": _f(vs_n3),
        "vs_nifty_5y": _f(vs_n5),
    }
    payload = {k: v for k, v in payload.items() if v not in (None, "", "n/a")}
    external.append(_synth_evidence(
        eid=f"register:{isin or symbol or entity}",
        title=f"Register line: {entity} ({kind}) · {member}",
        source="command-center-register",
        entity=entity,
        now=now,
        payload=payload,
        source_class=SourceClass.A,
        source_type=SourceType.CALCULATED,
    ))
    if lookthrough:
        names = []
        for row in lookthrough[:12]:
            if isinstance(row, dict):
                label = row.get("Name") or row.get("Fund") or "?"
                weight = row.get("Weight %") or row.get("weight") or ""
                names.append(f"{label} {weight}%")
            else:
                names.append(str(row))
        if names:
            external.append(_synth_evidence(
                eid=f"lookthrough:{isin or entity}",
                title=f"Look-through / disclosed names for {entity}",
                source="mf-holdings-cache",
                entity=entity,
                now=now,
                payload={
                    "fund_name": entity,
                    "holdings_count": len(names),
                    "scheme_name": "; ".join(names)[:400],
                },
                source_class=SourceClass.B,
                source_type=SourceType.OBSERVED,
            ))
    if tape and tape.get("ok"):
        tape_payload = {
            "fund_name": tape.get("name") or entity,
            "as_of_date": tape.get("retrieved_at") or "",
            "scheme_name": tape.get("ticker") or symbol,
        }
        lines = []
        for section in ("fundamentals", "technicals"):
            for row in ((tape.get(section) or {}).get("rows") or []):
                if isinstance(row, dict) and row.get("label"):
                    lines.append(f"{row.get('label')}={row.get('value')}")
        tape_payload["holdings_count"] = len(lines)
        tape_payload["nav"] = "; ".join(lines)[:800]
        external.append(_synth_evidence(
            eid=f"yahoo-tape:{tape.get('ticker') or symbol or entity}",
            title=f"Yahoo tape {tape.get('ticker') or symbol} (opt-in, observed)",
            source="yahoo-finance-yfinance",
            entity=entity,
            now=now,
            payload=tape_payload,
            source_class=SourceClass.C,
            source_type=SourceType.OBSERVED,
        ))
    if parent is not None:
        for dev in getattr(parent, "external", ()) or ():
            if _mentions(dev, tokens):
                external.append(dev)
    gaps = []
    if parent is None:
        gaps.append(
            "Command Center research brief was not in session; "
            "only this line's register is cited."
        )
    if kind == "Stocks" and not (tape and tape.get("ok")):
        gaps.append(
            "Yahoo company tape not loaded this session — "
            "PE/RSI/SMA are absent, not guessed."
        )
    if kind == "MF" and not lookthrough:
        gaps.append(
            "No look-through holdings rows were attached for this scheme "
            "this session."
        )
    conclusions = tuple(getattr(parent, "conclusions", ()) or ()) if parent else ()
    if tokens:
        kept = []
        for c in conclusions:
            blob = f"{c.title} {c.statement}".upper()
            if any(tok in blob for tok in tokens if len(tok) >= 4):
                kept.append(c)
        conclusions = tuple(kept)
    cash_label = "not a cash flow"
    if parent is not None:
        cash_label = getattr(parent, "not_a_cashflow_label", cash_label)
    return ResearchBrief(
        as_of=now,
        question=f"Interpret instrument {entity}",
        totals=totals,
        changes=tuple(changes),
        external=tuple(external),
        risks=tuple(c for c in conclusions if getattr(c, "topic", "") == "risk"),
        research_needs=tuple(
            c for c in conclusions if getattr(c, "topic", "") == "research_need"
        ),
        gaps=tuple(gaps),
        conclusions=conclusions,
        synthesis=None,
        synthesis_reason=None,
        evidence_count=len(external),
        mapped_count=sum(1 for d in external if d.mapped),
        not_a_cashflow_label=cash_label,
    )
