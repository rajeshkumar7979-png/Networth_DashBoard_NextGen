# -------------------------------------------------
# Portfolio Intelligence foundation — exposure & concentration facts.
# Pure deterministic roll-up over the canonical register + the four Command
# Center books + the MF holdings disclosure cache. Never invents a number:
# missing disclosures are flagged as uncovered (insufficient evidence), and
# weights are only derived from disclosed market values when a disclosure does
# not publish weight_pct (documented in each underlying's confidence).
# No pandas-free guarantee: pandas is required to consume the register/books.
# -------------------------------------------------
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from lib.config import DATA_DIR
from lib.intelligence.model import (
    Fact,
    make_fact,
    slugify,
)
from lib.register import aggregate_by_class, aggregate_by_member, family_level_sum

REGISTER_SOURCE = "command_center books + lib.register"
HOLDINGS_SOURCE = "data/mf_holdings_cache.json (fund-disclosures/mfdata.in)"
HOLDINGS_REFERENCE = "statutory monthly portfolio disclosures via aggregator cache"

NOT_A_CASHFLOW_LABEL = (
    "NOT a cash-flow measurement; transaction history unavailable."
)


@dataclass(frozen=True)
class Coverage:
    fund_value_total: float
    covered_value: float
    uncovered_value: float
    covered_funds: int
    missing_funds: int
    missing_names: tuple[str, ...]
    coverage_pct: Optional[float]


@dataclass(frozen=True)
class UnderlyingExposure:
    name: str
    isin: Optional[str]
    instrument_type: Optional[str]
    sector: Optional[str]
    value_inr: float
    pct_of_assets: Optional[float]
    schemes: tuple[str, ...]
    weight_basis: str  # "weight_pct" | "market_value_derived"
    confidence: Optional[float]


@dataclass(frozen=True)
class ExposureFacts:
    as_of: datetime
    total_assets: float
    total_invested: float
    total_pnl: float
    class_facts: tuple[Fact, ...]
    member_facts: tuple[Fact, ...]
    instrument_facts: tuple[Fact, ...]
    concentration_facts: tuple[Fact, ...]
    underlying_facts: tuple[Fact, ...]
    underlying: tuple[UnderlyingExposure, ...]
    coverage: Coverage
    weight_basis: frozenset[str]

    def all_facts(self):
        if not hasattr(self, "_all"):
            object.__setattr__(
                self, "_all",
                self.class_facts + self.member_facts + self.instrument_facts
                + self.concentration_facts + self.underlying_facts,
            )
        return self._all


def _hnum(value):
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _sstr(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _pct(part, total):
    return (part / total * 100.0) if total and total > 0 else None


def load_holdings_cache(path=None):
    """Read the MF holdings disclosure cache (dict scheme_code -> holdings list)."""
    path = Path(path) if path is not None else DATA_DIR / "mf_holdings_cache.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _normalize_holdings(holdings):
    cleaned = []
    if not isinstance(holdings, list):
        return cleaned, False
    used_derived = False
    for h in holdings:
        if not isinstance(h, dict):
            continue
        name = _sstr(h.get("name") or h.get("stock_name") or h.get("instrument")
                     or h.get("security") or h.get("security_name"))
        if not name:
            continue
        weight = _hnum(h.get("weight_pct"))
        weight_explicit = weight is not None
        if weight is None:
            weight = _hnum(h.get("weight"))
            weight_explicit = weight is not None
        market_value = _hnum(h.get("market_value"))
        cleaned.append({
            "name": name,
            "weight": weight,
            "market_value": market_value,
            "weight_explicit": weight_explicit,
            "isin": _sstr(h.get("isin")) or None,
            "sector": _sstr(h.get("sector")) or None,
            "instrument_type": _sstr(h.get("instrument_type")) or None,
        })
    total_mv = sum(c["market_value"] for c in cleaned
                   if c["market_value"] is not None and c["market_value"] > 0)
    if total_mv > 0:
        for c in cleaned:
            if c["weight"] is None and c["market_value"] is not None:
                c["weight"] = c["market_value"] / total_mv * 100.0
                c["weight_explicit"] = False
                used_derived = True
    return [c for c in cleaned if c["weight"] is not None and c["weight"] >= 0], used_derived


def _scheme_code(amfi_codes, isin):
    if not amfi_codes or not isin:
        return None
    code = amfi_codes.get(isin)
    if code is None:
        return None
    try:
        return str(int(code))
    except (TypeError, ValueError):
        return str(code).strip()


def _concentration_facts(register_current, total_assets, underlying, now):
    facts = []
    values = sorted((float(v) for v in register_current if v is not None and pd.notna(v)), reverse=True)
    for n in (5, 10):
        share = _pct(sum(values[:n]), total_assets)
        if share is not None:
            facts.append(make_fact(
                f"Top {n} instruments", f"cr{n}_instrument", share, "pct", now=now,
                source=REGISTER_SOURCE, reference="canonical asset register",
                fid=f"concentration:cr{n}_instrument:pct",
            ))
    hhi = _pct(sum((v / total_assets) ** 2 for v in values), 1) if total_assets > 0 else None
    if hhi is not None:
        facts.append(make_fact(
            "Instrument HHI", "hhi_instrument", hhi / 100.0, "hhi", now=now,
            source=REGISTER_SOURCE, reference="canonical asset register",
            fid="concentration:hhi_instrument",
        ))
    if underlying:
        uv = sorted((u.value_inr for u in underlying), reverse=True)
        top5 = _pct(sum(uv[:5]), total_assets)
        if top5 is not None:
            facts.append(make_fact(
                "Top 5 underlying securities", "cr5_underlying", top5, "pct", now=now,
                source=HOLDINGS_SOURCE, reference=HOLDINGS_REFERENCE,
                fid="concentration:cr5_underlying:pct",
            ))
        uhhi = _pct(sum((v / total_assets) ** 2 for v in uv), 1) if total_assets > 0 else None
        if uhhi is not None:
            facts.append(make_fact(
                "Underlying HHI", "hhi_underlying", uhhi / 100.0, "hhi", now=now,
                source=HOLDINGS_SOURCE, reference=HOLDINGS_REFERENCE,
                fid="concentration:hhi_underlying",
            ))
    return tuple(facts)


def build_exposure_facts(*, register, mf_valid=None, stocks_valid=None, gold_valid=None,
                         fd_valid=None, amfi_codes=None, holdings_by_scheme=None,
                         now=None):
    """Roll the canonical register + books + holdings disclosures up into facts.

    register must be the output of lib.register.build_asset_register. The four
    books are only used for the through-fund look-through (ISIN -> holdings).
    """
    if now is None:
        now = datetime.now()
    holdings_by_scheme = holdings_by_scheme or {}

    family = family_level_sum(register)
    total_assets = float(family["total_assets"] or 0.0)
    total_invested = float(family["total_invested"] or 0.0)
    total_pnl = total_assets - total_invested

    class_facts = []
    for _, row in aggregate_by_class(register).iterrows():
        cls = row["Asset Class"]
        if not row["Data Backed"]:
            continue
        cur = float(row["Current Value"]) if pd.notna(row["Current Value"]) else 0.0
        inv = float(row["Invested"]) if pd.notna(row["Invested"]) else 0.0
        class_facts.append(make_fact(
            cls, "current_inr", cur, "INR", now=now,
            source=REGISTER_SOURCE, reference="lib.register.aggregate_by_class",
            prefix="class",
        ))
        class_facts.append(make_fact(
            cls, "invested_inr", inv, "INR", now=now,
            source=REGISTER_SOURCE, reference="lib.register.aggregate_by_class",
            prefix="class",
        ))
        share = _pct(cur, total_assets)
        if share is not None:
            class_facts.append(make_fact(
                cls, "share_pct", share, "pct", now=now,
                source=REGISTER_SOURCE, reference="= current / total assets",
                prefix="class", confidence=0.9,
            ))

    member_facts = []
    for _, row in aggregate_by_member(register).iterrows():
        member = row["Member"]
        cur = float(row["Current Value"]) if pd.notna(row["Current Value"]) else 0.0
        inv = float(row["Invested"]) if pd.notna(row["Invested"]) else 0.0
        member_facts.append(make_fact(
            member, "current_inr", cur, "INR", now=now,
            source=REGISTER_SOURCE, reference="lib.register.aggregate_by_member",
            prefix="member", label="current holdings",
        ))
        member_facts.append(make_fact(
            member, "invested_inr", inv, "INR", now=now,
            source=REGISTER_SOURCE, reference="lib.register.aggregate_by_member",
            prefix="member", label="invested basis", confidence=0.9,
        ))

    instrument_facts = []
    register_current = []
    key_occurrences = {}
    for _, row in register.iterrows():
        key = _sstr(row.get("Key")) or _sstr(row.get("Instrument"))
        slug = slugify(key) or "unknown"
        key_occurrences[slug] = key_occurrences.get(slug, 0) + 1
        occ = key_occurrences[slug]
        entity = key if occ == 1 else f"{key} (#{occ})"
        fid_key = slug if occ == 1 else f"{slug}#{occ}"
        cur = float(row["Current Value"]) if pd.notna(row["Current Value"]) else 0.0
        inv = float(row["Invested"]) if pd.notna(row["Invested"]) else 0.0
        register_current.append(cur)
        instrument_facts.append(make_fact(
            entity, "current_inr", cur, "INR", now=now,
            source=REGISTER_SOURCE, reference=f"register row ({_sstr(row.get('Source'))})",
            fid=f"instrument:{fid_key}:current_inr",
        ))
        instrument_facts.append(make_fact(
            entity, "invested_inr", inv, "INR", now=now,
            source=REGISTER_SOURCE, reference=f"register row ({_sstr(row.get('Source'))})",
            fid=f"instrument:{fid_key}:invested_inr",
        ))
        instrument_facts.append(make_fact(
            entity, "pnl_inr", cur - inv, "INR", now=now,
            source=REGISTER_SOURCE, reference="current - invested basis "
            f"({NOT_A_CASHFLOW_LABEL})", fid=f"instrument:{fid_key}:pnl_inr", confidence=0.9,
        ))

    # ---- through-fund look-through (ISIN -> scheme -> disclosed holdings) ----
    fund_by_isin = {}
    fund_name_by_isin = {}
    if mf_valid is not None and not mf_valid.empty \
            and "ISIN" in mf_valid.columns and "Current Value" in mf_valid.columns:
        for _, row in mf_valid.iterrows():
            isin = _sstr(row.get("ISIN"))
            val = _hnum(row.get("Current Value")) or 0.0
            if isin:
                fund_by_isin[isin] = fund_by_isin.get(isin, 0.0) + val
                if isin not in fund_name_by_isin:
                    fund_name_by_isin[isin] = _sstr(row.get("Fund Name"))

    exposed = {}
    covered_value = 0.0
    covered_funds = 0
    missing_names = []
    weight_basis = set()
    for isin in sorted(fund_by_isin):
        code = _scheme_code(amfi_codes, isin)
        holdings = None
        if code is not None:
            holdings = holdings_by_scheme.get(code)
            if holdings is None:
                holdings = holdings_by_scheme.get(int(code)) if code.isdigit() else None
        if not holdings:
            missing_names.append(fund_name_by_isin.get(isin, isin) or isin)
            continue
        cleaned, used_derived = _normalize_holdings(holdings)
        if not cleaned:
            missing_names.append(fund_name_by_isin.get(isin, isin) or isin)
            continue
        covered_funds += 1
        covered_value += fund_by_isin[isin]
        basis = "market_value_derived" if used_derived else "weight_pct"
        weight_basis.add(basis)
        fund_value = fund_by_isin[isin]
        for h in cleaned:
            key = h["isin"] or slugify(h["name"])
            entry = exposed.setdefault(key, {
                "name": h["name"],
                "isin": h["isin"],
                "instrument_type": h["instrument_type"],
                "sector": h["sector"],
                "value": 0.0,
                "schemes": set(),
                "basis": basis,
            })
            entry["value"] += fund_value * h["weight"] / 100.0
            entry["schemes"].add(code)

    uncovered_value = sum(fund_by_isin.values()) - covered_value
    fund_value_total = sum(fund_by_isin.values())
    # 0 covered with money on the line => no disclosure data at all, not a 0% rate.
    coverage_pct = _pct(covered_value, fund_value_total) if covered_value > 0 else None
    coverage = Coverage(
        fund_value_total=fund_value_total,
        covered_value=covered_value,
        uncovered_value=max(uncovered_value, 0.0),
        covered_funds=covered_funds,
        missing_funds=len(missing_names),
        missing_names=tuple(sorted(missing_names)),
        coverage_pct=coverage_pct,
    )

    under_base_conf = 0.5 if coverage_pct is not None and coverage_pct < 70 else 0.8
    underlying = []
    underlying_facts = []
    for key in sorted(exposed, key=lambda k: -exposed[k]["value"]):
        e = exposed[key]
        pct = _pct(e["value"], total_assets)
        conf = under_base_conf
        if e["basis"] == "weight_pct":
            conf = min(0.9, under_base_conf + 0.1)
        u = UnderlyingExposure(
            name=e["name"],
            isin=e["isin"],
            instrument_type=e["instrument_type"],
            sector=e["sector"],
            value_inr=e["value"],
            pct_of_assets=pct,
            schemes=tuple(sorted(e["schemes"])),
            weight_basis=e["basis"],
            confidence=conf,
        )
        underlying.append(u)
        underlying_facts.append(make_fact(
            e["name"], "value_inr", e["value"], "INR", now=now,
            source=HOLDINGS_SOURCE, reference=HOLDINGS_REFERENCE,
            prefix="underlying", confidence=conf,
        ))
        underlying_facts.append(make_fact(
            e["name"], "share_pct", pct if pct is not None else 0.0, "pct", now=now,
            source=HOLDINGS_SOURCE, reference=HOLDINGS_REFERENCE,
            prefix="underlying", confidence=conf,
        ))

    concentration_facts = _concentration_facts(register_current, total_assets, underlying, now)

    return ExposureFacts(
        as_of=now,
        total_assets=total_assets,
        total_invested=total_invested,
        total_pnl=total_pnl,
        class_facts=tuple(class_facts),
        member_facts=tuple(member_facts),
        instrument_facts=tuple(instrument_facts),
        concentration_facts=concentration_facts,
        underlying_facts=tuple(underlying_facts),
        underlying=tuple(underlying),
        coverage=coverage,
        weight_basis=frozenset(weight_basis),
    )


def underlying_df(facts):
    """Compact DataFrame of the underlying look-through for display/testing."""
    cols = ["name", "isin", "instrument_type", "value_inr", "pct_of_assets", "schemes", "confidence"]
    rows = [
        {
            "name": u.name,
            "isin": u.isin,
            "instrument_type": u.instrument_type or "",
            "value_inr": round(u.value_inr, 2),
            "pct_of_assets": round(u.pct_of_assets, 4) if u.pct_of_assets is not None else None,
            "schemes": ",".join(u.schemes),
            "confidence": u.confidence,
        }
        for u in facts.underlying
    ]
    return pd.DataFrame(rows, columns=cols)


def class_share_df(facts):
    rows = [
        {"asset_class": f.entity, "current_inr": f.value}
        for f in facts.class_facts if f.metric == "current_inr"
    ]
    df = pd.DataFrame(rows, columns=["asset_class", "current_inr"])
    if df.empty:
        return df
    total = float(df["current_inr"].sum())
    df["share_pct"] = df["current_inr"] / total * 100
    return df.sort_values("share_pct", ascending=False).reset_index(drop=True)