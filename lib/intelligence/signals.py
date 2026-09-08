# -------------------------------------------------
# Portfolio Intelligence foundation — deterministic rule-based signals.
# Pure module. Signals are data, not paragraphs: each one names the facts and
# evidence it was derived from and states what would invalidate it. Rules reuse
# existing Command Center / lib.scoring thresholds rather than inventing new
# ones, but they ONLY reason over facts fed in — anything missing yields the
# signal level "info" ("insufficient evidence"), never a fabricated warning.
# -------------------------------------------------
from __future__ import annotations

from lib.intelligence.evidence import (
    EVIDENCE_DRIVERS,
    EVIDENCE_HOLDINGS_COVERAGE,
)
from lib.intelligence.model import Signal

CONCENTRATION_CR5 = "concentration:cr5_instrument:pct"
CLASS_EQUITY_SHARE = "class:equity:share_pct"
CLASS_FCNR_SHARE = "class:fcnr_usd:share_pct"
CLASS_GOLD_SHARE = "class:gold:share_pct"


def _value(facts, fid):
    for f in facts.all_facts():
        if f.id == fid:
            return f.value
    return None


def _hnum(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fd_rows(fd_df):
    rows = []
    if fd_df is None or fd_df.empty or "Days to Maturity" not in fd_df.columns:
        return rows
    for _, row in fd_df.iterrows():
        d = _hnum(row.get("Days to Maturity"))
        if d is None:
            continue
        rows.append((d, row))
    return rows


def evaluate_signals(facts, evidence=None, *, drivers=None, mf_valid=None,
                     fd_df=None, now=None):
    """Evaluate the deterministic rule set over exposure facts + evidence."""
    ev = evidence or ()
    ev_ids = set()
    for bag in (ev,):
        if hasattr(bag, "items"):
            ev_ids.update(e.id for e in bag.items)

    signals = []

    cr5 = _value(facts, CONCENTRATION_CR5)
    if cr5 is None:
        signals.append(Signal(
            id="sig:concentration",
            rule="concentration_top_instruments",
            label="Instrument concentration",
            level="info",
            message="Insufficient evidence: no instrument-level current values.",
            fact_ids=(CONCENTRATION_CR5,),
            invalidation="Portfolio register populated.",
        ))
    elif cr5 > 60:
        signals.append(Signal(
            id="sig:concentration",
            rule="concentration_top_instruments",
            label="Instrument concentration",
            level="warn",
            message=f"Top 5 instruments are {cr5:.1f}% of assets.",
            fact_ids=(CONCENTRATION_CR5,),
            invalidation="Top-5 instrument share falls below 60%.",
            confidence=0.8,
        ))
    elif cr5 > 35:
        signals.append(Signal(
            id="sig:concentration",
            rule="concentration_top_instruments",
            label="Instrument concentration",
            level="watch",
            message=f"Top 5 instruments are {cr5:.1f}% of assets.",
            fact_ids=(CONCENTRATION_CR5,),
            invalidation="Top-5 instrument share falls below 35%.",
            confidence=0.8,
        ))
    else:
        signals.append(Signal(
            id="sig:concentration",
            rule="concentration_top_instruments",
            label="Instrument concentration",
            level="info",
            message=f"Top 5 instruments are {cr5:.1f}% of assets.",
            fact_ids=(CONCENTRATION_CR5,),
            invalidation="Top-5 instrument share rises above 35%.",
            confidence=0.8,
        ))

    eq = _value(facts, CLASS_EQUITY_SHARE)
    if eq is None:
        signals.append(Signal(
            id="sig:equity",
            rule="equity_allocation_low",
            label="Equity allocation",
            level="info",
            message="Insufficient evidence: no equity share.",
            fact_ids=(CLASS_EQUITY_SHARE,),
            invalidation="Register available.",
        ))
    elif eq < 20:
        signals.append(Signal(
            id="sig:equity",
            rule="equity_allocation_low",
            label="Equity allocation (NRI view)",
            level="critical",
            message=f"Equity is {eq:.1f}% of assets — well below the 35-50% "
                    f"working band.",
            fact_ids=(CLASS_EQUITY_SHARE,),
            invalidation="Equity share reaches 20% of assets.",
            confidence=0.9,
        ))
    elif eq < 35:
        signals.append(Signal(
            id="sig:equity",
            rule="equity_allocation_low",
            label="Equity allocation (NRI view)",
            level="warn",
            message=f"Equity is {eq:.1f}% of assets (working band 35-50%).",
            fact_ids=(CLASS_EQUITY_SHARE,),
            invalidation="Equity share reaches 35% of assets.",
            confidence=0.9,
        ))
    elif eq > 65:
        signals.append(Signal(
            id="sig:equity",
            rule="equity_allocation_high",
            label="Equity allocation",
            level="watch",
            message=f"Equity is {eq:.1f}% of assets — optionality is low.",
            fact_ids=(CLASS_EQUITY_SHARE,),
            invalidation="Equity share falls below 65% of assets.",
            confidence=0.9,
        ))
    else:
        signals.append(Signal(
            id="sig:equity",
            rule="equity_allocation_ok",
            label="Equity allocation",
            level="info",
            message=f"Equity is {eq:.1f}% of assets.",
            fact_ids=(CLASS_EQUITY_SHARE,),
            invalidation="Equity share leaves the 35-65% band.",
            confidence=0.9,
        ))

    missing_fx = None
    if drivers is not None:
        missing_fx = bool(drivers.get("missing_fx"))
    elif EVIDENCE_DRIVERS in ev_ids:
        for e in (ev.items if hasattr(ev, "items") else ()):
            if e.id == EVIDENCE_DRIVERS:
                missing_fx = bool((e.payload or {}).get("missing_fx"))
                break
    if missing_fx:
        signals.append(Signal(
            id="sig:fx",
            rule="fx_attribution_unavailable",
            label="FCNR FX attribution unavailable",
            level="warn",
            message="USD/INR live rate missing this run: FCNR interest vs FX "
                    "on principal cannot be split.",
            evidence_ids=(EVIDENCE_DRIVERS,) if EVIDENCE_DRIVERS in ev_ids else (),
            invalidation="A live USD/INR rate is retrieved on a later run.",
            confidence=0.7,
        ))

    cov = facts.coverage.coverage_pct
    if cov is None:
        signals.append(Signal(
            id="sig:coverage",
            rule="holdings_coverage_low",
            label="Holdings disclosure coverage",
            level="warn",
            message="No MF portfolio disclosures available — stock-level "
                    "look-through is blocked (insufficient evidence).",
            evidence_ids=(EVIDENCE_HOLDINGS_COVERAGE,) if EVIDENCE_HOLDINGS_COVERAGE in ev_ids else (),
            invalidation="scripts/update_holdings_cache.py refreshes disclosures.",
            confidence=0.7,
        ))
    elif cov < 70:
        signals.append(Signal(
            id="sig:coverage",
            rule="holdings_coverage_low",
            label="Holdings disclosure coverage",
            level="warn",
            message=f"Only {cov:.0f}% of the fund book has disclosure data "
                    f"({facts.coverage.missing_funds} fund(s) uncovered).",
            evidence_ids=(EVIDENCE_HOLDINGS_COVERAGE,) if EVIDENCE_HOLDINGS_COVERAGE in ev_ids else (),
            invalidation="Holdings cache refresh raises coverage to >=70%.",
            confidence=0.7,
        ))
    elif cov >= 90:
        signals.append(Signal(
            id="sig:coverage",
            rule="holdings_coverage_ok",
            label="Holdings disclosure coverage",
            level="info",
            message=f"{cov:.0f}% of the fund book has disclosure data.",
            evidence_ids=(EVIDENCE_HOLDINGS_COVERAGE,) if EVIDENCE_HOLDINGS_COVERAGE in ev_ids else (),
            invalidation="Coverage drops below 90%.",
            confidence=0.7,
        ))
    else:
        signals.append(Signal(
            id="sig:coverage",
            rule="holdings_coverage_partial",
            label="Holdings disclosure coverage",
            level="watch",
            message=f"{cov:.0f}% of the fund book has disclosure data "
                    f"({facts.coverage.missing_funds} fund(s) uncovered).",
            evidence_ids=(EVIDENCE_HOLDINGS_COVERAGE,) if EVIDENCE_HOLDINGS_COVERAGE in ev_ids else (),
            invalidation="Coverage reaches 90%.",
            confidence=0.7,
        ))

    fcnr = _value(facts, CLASS_FCNR_SHARE)
    if fcnr is not None and fcnr >= 40:
        signals.append(Signal(
            id="sig:fcnr",
            rule="fcnr_share_high",
            label="FCNR / USD book",
            level="watch",
            message=f"FCNR is {fcnr:.1f}% of assets — a large USD concentration.",
            fact_ids=(CLASS_FCNR_SHARE,),
            invalidation="FCNR share falls below 40% of assets.",
            confidence=0.8,
        ))

    gold = _value(facts, CLASS_GOLD_SHARE)
    if gold is not None and gold > 25:
        signals.append(Signal(
            id="sig:gold",
            rule="gold_allocation_high",
            label="Gold allocation",
            level="watch",
            message=f"Gold (SGB + ETFs + FoFs) is {gold:.1f}% of assets.",
            fact_ids=(CLASS_GOLD_SHARE,),
            invalidation="Gold share falls below 25% of assets.",
            confidence=0.8,
        ))

    overlap = [u for u in facts.underlying if len(u.schemes) > 1]
    if overlap:
        worst = max(overlap, key=lambda u: u.pct_of_assets or 0.0)
        uf = [f.id for f in facts.underlying_facts
              if f.metric == "value_inr" and f.entity == worst.name][:1]
        if (worst.pct_of_assets or 0.0) >= 10:
            signals.append(Signal(
                id="sig:overlap",
                rule="fund_overlap",
                label="Cross-fund concentration of a single security",
                level="watch",
                message=f"{worst.name} is held by {len(worst.schemes)} funds and is "
                        f"{worst.pct_of_assets:.1f}% of assets.",
                fact_ids=tuple(uf),
                invalidation="Position drops below 10% of assets or disclosure refresh changes overlap.",
                confidence=0.7,
            ))

    fd_rows = _fd_rows(fd_df)
    overdue = [r for d, r in fd_rows if d < 0]
    if overdue:
        vals = [_hnum(r.get("Current Value (INR)")) for r in overdue]
        total = sum(v for v in vals if v is not None)
        names = ", ".join(sorted({str(r.get("Holder Name")) for r in overdue}))
        signals.append(Signal(
            id="sig:matured_fd",
            rule="matured_fd",
            label="Matured FD proceeds uncollected",
            level="critical",
            message=f"{len(overdue)} FD(s) from {names} have matured — "
                    f"~{total:,.0f} INR likely earning the default rate.",
            invalidation="Workbook updated after proceeds are collected or reinvested.",
            confidence=0.9,
        ))
    soon = [r for d, r in fd_rows if 0 <= d <= 14]
    if soon:
        names = ", ".join(sorted({str(r.get("Holder Name")) for r in soon}))
        signals.append(Signal(
            id="sig:near_fd",
            rule="near_maturity_fd",
            label="FDs maturing within 14 days",
            level="info",
            message=f"{len(soon)} FD(s) from {names} mature within two weeks.",
            invalidation="Maturities are reinvested or lapse.",
            confidence=0.9,
        ))

    under = _underperformers(mf_valid)
    if under:
        names = ", ".join(n[:24] for n in under[:3])
        signals.append(Signal(
            id="sig:underperformers",
            rule="persistent_underperformers",
            label="Persistent underperformers",
            level="warn",
            message=f"{len(under)} fund(s) trailing Nifty50 on both 1Y and 3Y: "
                    f"{names}.",
            invalidation="Fund returns recover above the trailing Nifty50 by 2ppt.",
            confidence=0.8,
        ))

    return tuple(signals)


def _underperformers(mf_valid):
    if mf_valid is None or mf_valid.empty:
        return []
    need = {"1Y %", "3Y %", "vs Nifty50 1Y", "vs Nifty50 3Y"}
    if not need.issubset(set(mf_valid.columns)):
        return []
    df = mf_valid.dropna(subset=list(need))
    mask = (df["1Y %"] < df["vs Nifty50 1Y"] - 2) & (df["3Y %"] < df["vs Nifty50 3Y"] - 2)
    return (df.loc[mask, ["Fund Name", "1Y %"]].dropna()
            .sort_values("1Y %")["Fund Name"].head(3).tolist())