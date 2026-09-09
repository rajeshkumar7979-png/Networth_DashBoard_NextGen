# -------------------------------------------------
# Intelligence Data Gateway — Indian mutual funds (AMFI / fund-disclosures /
# mfdata cache readers). CACHE-READ-ONLY: this adapter normalizes what the
# existing ingestion pipeline already fetched and baked into data/
# amfi_scheme_universe.json / amfi_nav_cache.json / mf_holdings_cache.json.
# It NEVER triggers a network call, so the Command Center can surface status
# without touching the outside world.
# -------------------------------------------------
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lib.config import AMFI_CACHE_PATH
from lib.mf_holdings import (
    AMFI_UNIVERSE_CACHE,
    HOLDINGS_CACHE,
    HOLDINGS_META_CACHE,
    load_json,
)

from .record import (
    SourceRecord,
    SourceResult,
    make_record_id,
    parse_iso,
    unavailable_result,
    utc_now,
)
from lib.intelligence.model import SourceClass, SourceType


def _parse_mf_date(value):
    if not value:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            continue
    parsed = parse_iso(str(value))
    return parsed


def load_mf_nav_evidence(*, universe_cache_path=None, amfi_cache_path=None,
                         limit: int = 500, now=None) -> SourceResult:
    """NAV records from the AMFI universe cache (preferred) or the NAV disk
    cache fallback. Missing data stays missing — never a fabricated zero."""
    now = now or utc_now()
    universe_path = Path(universe_cache_path) if universe_cache_path else AMFI_UNIVERSE_CACHE
    universe = load_json(universe_path, {})
    rows = universe.get("rows") if isinstance(universe, dict) else []
    if isinstance(rows, list) and rows:
        fetched_at = parse_iso(universe.get("fetched_at"))
        records = []
        for row in rows:
            if len(records) >= limit:
                break
            isin = str(row.get("isin_primary") or row.get("isin_secondary") or "").strip().upper()
            nav = row.get("nav")
            if not isin or nav is None:
                continue
            records.append(SourceRecord(
                id=make_record_id("amfi", "nav", isin),
                provider="amfi",
                entity=isin,
                title=str(row.get("scheme_name") or f"NAV {isin}"),
                retrieved_at=fetched_at or now,
                source_class=SourceClass.A,
                source_type=SourceType.OBSERVED,
                published_at=_parse_mf_date(row.get("nav_date")),
                reference="AMFI NAVAll (amfi_scheme_universe cache)",
                payload={
                    "isin": isin,
                    "scheme_code": str(row.get("scheme_code") or ""),
                    "scheme_name": str(row.get("scheme_name") or ""),
                    "amc": str(row.get("amc") or ""),
                    "category": str(row.get("category") or ""),
                    "nav": nav,
                    "nav_date": str(row.get("nav_date") or ""),
                },
            ))
        if records:
            return SourceResult(
                provider="amfi",
                status="ok",
                records=records,
                retrieved_at=fetched_at or now,
                metadata={
                    "cache": "amfi_scheme_universe",
                    "fetched_at": fetched_at.isoformat() if fetched_at else None,
                },
            )

    amfi_path = Path(amfi_cache_path) if amfi_cache_path else AMFI_CACHE_PATH
    cached = load_json(amfi_path, {})
    nav = cached.get("nav") or {}
    code = cached.get("code") or {}
    name = cached.get("name") or {}
    saved_at = parse_iso(cached.get("saved_at")) or now
    if isinstance(nav, dict) and nav:
        records = []
        for isin, nav_value in nav.items():
            if len(records) >= limit:
                break
            if nav_value is None:
                continue
            records.append(SourceRecord(
                id=make_record_id("amfi", "nav", str(isin)),
                provider="amfi",
                entity=str(isin),
                title=str(name.get(isin) or f"NAV {isin}"),
                retrieved_at=saved_at,
                source_class=SourceClass.A,
                source_type=SourceType.OBSERVED,
                reference="AMFI NAVAll (amfi_nav_cache.json)",
                payload={
                    "isin": str(isin),
                    "scheme_code": str(code.get(isin) or ""),
                    "scheme_name": str(name.get(isin) or ""),
                    "nav": nav_value,
                    "nav_date": str(cached.get("saved_at") or ""),
                },
            ))
        if records:
            return SourceResult(
                provider="amfi",
                status="ok",
                records=records,
                retrieved_at=saved_at,
                metadata={"cache": "amfi_nav_cache", "saved_at": cached.get("saved_at")},
            )

    return unavailable_result(
        "amfi",
        "no MF NAV cache available (amfi_scheme_universe.json or amfi_nav_cache.json)",
    )


def load_mf_holdings_evidence(*, holdings_cache_path=None, holdings_meta_path=None,
                              now=None) -> SourceResult:
    """Holdings records from the existing fund-disclosures / mfdata.in cache,
    preserving the primary-vs-secondary provenance in the record payload."""
    now = now or utc_now()
    holdings_path = Path(holdings_cache_path) if holdings_cache_path else HOLDINGS_CACHE
    meta_path = Path(holdings_meta_path) if holdings_meta_path else HOLDINGS_META_CACHE
    if not holdings_path.exists():
        return unavailable_result("mf", "no MF holdings cache file present at " + str(holdings_path))

    holdings = load_json(holdings_path, {})
    meta = load_json(meta_path, {})
    if not isinstance(holdings, dict):
        return unavailable_result("mf", "MF holdings cache is malformed (not an object)")

    records = []
    for scheme_code in sorted(holdings):
        scheme_meta = meta.get(str(scheme_code)) or {}
        if not isinstance(scheme_meta, dict):
            scheme_meta = {}
        fallback = bool(scheme_meta.get("fallback_used"))
        provider = "mfdata" if fallback else "fund-disclosures"
        retrieved = parse_iso(scheme_meta.get("retrieved_at")) or now
        items = holdings[scheme_code] or []
        for holding in items:
            if not isinstance(holding, dict):
                continue
            isin = str(holding.get("isin") or "").strip().upper()
            holding_name = str(holding.get("name") or "")
            entity = isin or holding_name or f"holding-{len(records)}"
            records.append(SourceRecord(
                id=make_record_id("mf", "holding", scheme_code, isin or holding_name),
                provider=provider,
                entity=entity,
                title=f"{scheme_code} · {holding_name or isin}",
                retrieved_at=retrieved,
                source_class=SourceClass.C,
                source_type=SourceType.OFFICIAL_FILING,
                reference=str(scheme_meta.get("endpoint") or ""),
                payload={
                    "scheme_code": str(scheme_code),
                    "fund_name": str(scheme_meta.get("fund_name") or ""),
                    "holding": holding_name,
                    "isin": isin,
                    "weight_pct": holding.get("weight_pct"),
                    "market_value": holding.get("market_value"),
                    "quantity": holding.get("quantity"),
                    "sector": holding.get("sector"),
                    "instrument_type": holding.get("instrument_type"),
                    "as_of": str(scheme_meta.get("as_of") or ""),
                    "data_source": str(holding.get("source") or ""),
                    "secondary_source": fallback,
                    "source_endpoint": str(scheme_meta.get("endpoint") or ""),
                },
            ))

    return SourceResult(
        provider="mf",
        status="ok",
        records=records,
        retrieved_at=now,
        metadata={
            "cache": "mf_holdings_cache",
            "schemes": len(holdings),
            "secondary_fallback_used": any(
                bool((meta.get(str(k)) or {}).get("fallback_used"))
                for k in holdings
            ),
        },
    )


def mf_status(now=None) -> list[dict]:
    """Cache-only availability snapshot for the Command Center diagnostic."""
    rows = []
    universe = load_json(AMFI_UNIVERSE_CACHE, {})
    if isinstance(universe, dict) and isinstance(universe.get("rows"), list) and universe.get("rows"):
        fetched = parse_iso(universe.get("fetched_at"))
        rows.append({
            "provider": "mf",
            "key": "amfi_scheme_universe",
            "last_retrieval": fetched.isoformat() if fetched else None,
            "record_count": len(universe["rows"]),
            "is_stale": False,
            "status": "ok",
        })
    holdings = load_json(HOLDINGS_CACHE, {})
    meta = load_json(HOLDINGS_META_CACHE, {})
    if isinstance(holdings, dict) and holdings:
        fallback = any(bool((meta.get(str(k)) or {}).get("fallback_used")) for k in holdings)
        retrieved = None
        for k in holdings:
            m = meta.get(str(k)) or {}
            r = parse_iso(m.get("retrieved_at"))
            if r:
                retrieved = max(retrieved, r) if retrieved else r
        rows.append({
            "provider": "mf_fund_disclosures" if not fallback else "mf_mfdata",
            "key": "mf_holdings_cache",
            "last_retrieval": retrieved.isoformat() if retrieved else None,
            "record_count": sum(len(v) for v in holdings.values() if isinstance(v, list)),
            "is_stale": False,
            "status": "ok",
            "reason": "secondary source (mfdata.in) in use" if fallback else None,
        })
    return rows