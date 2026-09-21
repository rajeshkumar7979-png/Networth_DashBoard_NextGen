# lib/mf_holdings.py
"""Mutual-fund holdings ingestion for Networth_DashBoard.

Phase 1 source hierarchy:
1) OpenFin GitHub/jsDelivr CDN (same AMC statutory filings the dead
   fund-holdings-browser Vercel API used to serve)
2) fund-disclosures Vercel API (kept as a one-shot probe; circuit-opens on
   DEPLOYMENT_NOT_FOUND so a gone host cannot burn the refresh job)
3) mfdata.in family holdings API (fallback; circuit-opens on repeated 5xx)

The module deliberately stores COMPLETE holdings returned by the source.
It never truncates the portfolio to top-N rows. It never invents a filing
date the source did not publish.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import requests

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

AMFI_NAV_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
FUND_DISCLOSURES_API = "https://fund-holdings-browser.vercel.app/api/amfi/{scheme_code}"
MFDATA_BASE = "https://mfdata.in"

# Public AMC-statutory holdings store. Vercel API is gone (DEPLOYMENT_NOT_FOUND);
# the parser project now publishes JSON to this GitHub repo and jsDelivr.
CDN_OWNER = "kushagra-agarwal-a"
CDN_REPO = "fund-holdings-data"
CDN_JSDELIVR = "https://cdn.jsdelivr.net/gh/{owner}/{repo}@{ref}/{path}"
CDN_GITHUB_RAW = "https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"

AMFI_UNIVERSE_CACHE = DATA_DIR / "amfi_scheme_universe.json"
HOLDINGS_CACHE = DATA_DIR / "mf_holdings_cache.json"
HOLDINGS_META_CACHE = DATA_DIR / "mf_holdings_meta.json"

HOLDINGS_USER_AGENT = (
    "NorthlineFamilyDesk/1.0 "
    "(+https://github.com/rajeshkumar7979-png/Networth_DashBoard_NextGen)"
)

JSON_TIMEOUT = (6, 20)
TEXT_TIMEOUT = (10, 45)
TIMEOUT = JSON_TIMEOUT  # back-compat alias
RETRIES = 3
_NO_RETRY_STATUS = frozenset({400, 401, 403, 404, 405, 410, 418, 422})
_HOST_TRIP_AFTER = 2

_DEAD_HOSTS: Dict[str, str] = {}
_HOST_FAILS: Dict[str, int] = {}
_CDN_CATALOG: Optional[Dict[str, Any]] = None


def reset_ingest_state_for_tests() -> None:
    """Clear circuit-breaker / catalog caches. Tests only."""
    global _CDN_CATALOG
    _DEAD_HOSTS.clear()
    _HOST_FAILS.clear()
    _CDN_CATALOG = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": HOLDINGS_USER_AGENT,
        "Accept": "application/json,text/plain,*/*",
    })
    return session


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()


def _compact_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", "")
    s = s.replace("₹", "").replace("INR", "")
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _first(row: Dict[str, Any], aliases: Iterable[str]) -> Any:
    compact = {_compact_key(k): v for k, v in row.items()}
    for alias in aliases:
        key = _compact_key(alias)
        if key in compact and compact[key] not in (None, ""):
            return compact[key]
    return None


def _host(url: str) -> str:
    return (urlparse(url).netloc or "").lower()


def _headers() -> Dict[str, str]:
    return {
        "User-Agent": HOLDINGS_USER_AGENT,
        "Accept": "application/json,text/plain,*/*",
    }


def _trip_host(url: str, reason: str) -> None:
    host = _host(url)
    if host:
        _DEAD_HOSTS[host] = reason


def _note_transport_fail(url: str, reason: str) -> None:
    host = _host(url)
    if not host:
        return
    _HOST_FAILS[host] = _HOST_FAILS.get(host, 0) + 1
    if "vercel.app" in host or host.endswith("mfdata.in"):
        if _HOST_FAILS[host] >= _HOST_TRIP_AFTER:
            _trip_host(url, reason)


def _maybe_trip_from_response(url: str, status: int, body: str) -> None:
    blob = (body or "").lower()
    host = _host(url)
    if "vercel.app" in host and (
        status in (404, 410)
        or "deployment could not be found" in blob
        or "deployment_not_found" in blob
    ):
        _trip_host(url, f"HTTP {status}")


def _request_json(
    session: requests.Session,
    url: str,
    *,
    params: Optional[dict] = None,
    timeout: Tuple[int, int] = JSON_TIMEOUT,
) -> Tuple[Any, Dict[str, str]]:
    host = _host(url)
    if host in _DEAD_HOSTS:
        raise RuntimeError(f"GET skipped: {url}: host circuit-open ({_DEAD_HOSTS[host]})")

    last_error: Optional[Exception] = None
    for attempt in range(RETRIES):
        try:
            r = session.get(url, params=params, timeout=timeout, headers=_headers())
            body_head = (r.text or "")[:240]
            if r.status_code == 429:
                retry_after = _to_float(r.headers.get("Retry-After")) or (2 ** attempt)
                time.sleep(min(retry_after, 20))
                last_error = RuntimeError(f"HTTP 429 for {url}")
                continue
            if r.status_code in _NO_RETRY_STATUS:
                _maybe_trip_from_response(url, r.status_code, body_head)
                raise RuntimeError(f"GET failed: {url}: HTTP {r.status_code}")
            if r.status_code >= 500:
                _maybe_trip_from_response(url, r.status_code, body_head)
                last_error = RuntimeError(f"GET failed: {url}: HTTP {r.status_code}")
                _note_transport_fail(url, f"HTTP {r.status_code}")
                if attempt < RETRIES - 1 and host not in _DEAD_HOSTS:
                    time.sleep(min(1.5 * (2 ** attempt), 8))
                    continue
                raise last_error
            r.raise_for_status()
            return r.json(), {k.lower(): v for k, v in r.headers.items()}
        except RuntimeError:
            raise
        except Exception as exc:  # network/API failures are expected; preserve old cache
            last_error = exc
            _note_transport_fail(url, type(exc).__name__)
            if attempt < RETRIES - 1 and _host(url) not in _DEAD_HOSTS:
                time.sleep(min(1.5 * (2 ** attempt), 8))
    raise RuntimeError(f"GET failed: {url}: {last_error}")


def _request_json_multi(
    session: requests.Session, urls: Iterable[str],
) -> Tuple[Any, Dict[str, str]]:
    errors: List[str] = []
    seen = set()
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        try:
            return _request_json(session, url)
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError(" | ".join(errors) if errors else "no URLs")


def _request_text(session: requests.Session, url: str) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(RETRIES):
        try:
            r = session.get(url, timeout=TEXT_TIMEOUT, headers=_headers())
            if r.status_code == 429:
                time.sleep(min(2 ** attempt, 20))
                continue
            if r.status_code in _NO_RETRY_STATUS:
                raise RuntimeError(f"GET failed: {url}: HTTP {r.status_code}")
            r.raise_for_status()
            return r.text
        except RuntimeError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt < RETRIES - 1:
                time.sleep(min(1.5 * (2 ** attempt), 8))
    raise RuntimeError(f"GET failed: {url}: {last_error}")


def _cdn_url(ref: str, path: str, *, raw: bool = False) -> str:
    template = CDN_GITHUB_RAW if raw else CDN_JSDELIVR
    return template.format(owner=CDN_OWNER, repo=CDN_REPO, ref=ref, path=path)


def fetch_cdn_catalog(session: requests.Session, *, force: bool = False) -> Dict[str, Any]:
    """Load the OpenFin AMFI lookup (one GET per process). Pin to meta.commit."""
    global _CDN_CATALOG
    if _CDN_CATALOG is not None and not force:
        return _CDN_CATALOG

    meta_payload, _ = _request_json_multi(session, [
        _cdn_url("main", "meta.json"),
        _cdn_url("main", "meta.json", raw=True),
    ])
    meta = meta_payload if isinstance(meta_payload, dict) else {}
    ref = str(meta.get("commit") or "main").strip() or "main"
    lookup, _ = _request_json_multi(session, [
        _cdn_url(ref, "catalog/amfi-lookup.json"),
        _cdn_url(ref, "catalog/amfi-lookup.json", raw=True),
        _cdn_url("main", "catalog/amfi-lookup.json"),
        _cdn_url("main", "catalog/amfi-lookup.json", raw=True),
    ])
    if not isinstance(lookup, dict) or not lookup:
        raise RuntimeError("CDN catalog is empty or not an object")
    _CDN_CATALOG = {"meta": meta, "lookup": lookup, "ref": ref}
    return _CDN_CATALOG


def parse_amfi_navall(text: str) -> List[Dict[str, Any]]:
    """Parse AMFI's current NAVAll.txt into scheme metadata.

    AMFI's feed is semicolon-delimited and carries AMC/category as section
    headers. We only keep rows beginning with a numeric scheme code.
    """
    rows: List[Dict[str, Any]] = []
    current_amc = ""
    current_category = ""

    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line:
            continue

        parts = [p.strip() for p in line.split(";")]
        if len(parts) >= 6 and parts[0].isdigit():
            code = parts[0]
            isin1 = parts[1] if parts[1] and parts[1] != "-" else ""
            isin2 = parts[2] if parts[2] and parts[2] != "-" else ""
            name = parts[3]
            nav = _to_float(parts[4])
            nav_date = parts[5]
            rows.append({
                "scheme_code": code,
                "isin_primary": isin1,
                "isin_secondary": isin2,
                "scheme_name": name,
                "nav": nav,
                "nav_date": nav_date,
                "amc": current_amc,
                "category": current_category,
            })
            continue

        # Category/section lines normally contain "Schemes(" and no semicolons.
        if ";" not in line and ("Schemes(" in line or line.startswith("Open Ended") or line.startswith("Close Ended")):
            current_category = line
        elif ";" not in line:
            current_amc = line

    return rows


def fetch_amfi_universe(session: requests.Session, *, force: bool = False) -> List[Dict[str, Any]]:
    if AMFI_UNIVERSE_CACHE.exists() and not force:
        try:
            payload = json.loads(AMFI_UNIVERSE_CACHE.read_text(encoding="utf-8"))
            if payload.get("rows"):
                return payload["rows"]
        except Exception:
            pass

    text = _request_text(session, AMFI_NAV_URL)
    rows = parse_amfi_navall(text)
    if not rows:
        raise RuntimeError("AMFI NAVAll returned no parseable scheme rows")

    AMFI_UNIVERSE_CACHE.write_text(
        json.dumps({"fetched_at": _now_iso(), "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return rows


def build_isin_index(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    index: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        for key in ("isin_primary", "isin_secondary"):
            isin = str(row.get(key) or "").strip().upper()
            if isin and isin != "-":
                index.setdefault(isin, []).append(row)
    return index


def _extract_candidate_lists(payload: Any) -> List[Any]:
    """Find likely holdings arrays in a flexible API response."""
    if isinstance(payload, list):
        return [payload]
    if not isinstance(payload, dict):
        return []

    candidates: List[Any] = []
    for key in ("holdings", "portfolio", "equity", "debt", "other", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            candidates.append(value)
        elif isinstance(value, dict):
            candidates.extend(_extract_candidate_lists(value))

    data = payload.get("data")
    if isinstance(data, list):
        candidates.append(data)
    elif isinstance(data, dict):
        candidates.extend(_extract_candidate_lists(data))

    return candidates


def _normalize_holding(row: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
    name = _first(row, [
        "name", "security_name", "security", "stock_name", "instrument",
        "scrip_name", "company",
    ])
    isin = _first(row, ["isin", "isin_code", "security_isin"])
    if not name and not isin:
        return None

    weight = _first(row, [
        "weight_pct", "weight", "pct_nav", "% of nav", "nav_pct",
        "percentage", "exposure_pct",
    ])
    market_value = _first(row, ["market_value_cr", "market_value_lakh", "market_value", "value_cr", "value"])
    quantity = _first(row, ["quantity", "qty", "units"])

    normalized = {
        "name": str(name).strip() if name is not None else "",
        "isin": str(isin).strip().upper() if isin is not None and str(isin).strip() != "-" else "",
        "weight_pct": _to_float(weight),
        "market_value": _to_float(market_value),
        "quantity": _to_float(quantity),
        "sector": _first(row, ["sector", "industry", "industry_sector"]),
        "instrument_type": _first(row, [
            "instrument_type", "holding_type", "asset_type", "type",
        ]),
        "market_cap": _first(row, ["market_cap", "market_cap_category", "cap"]),
        "credit_rating": _first(row, ["credit_rating", "rating"]),
        "maturity_date": _first(row, ["maturity_date", "maturity"]),
        "coupon_rate": _to_float(_first(row, ["coupon_rate", "coupon"])),
        "source": source,
    }

    # Preserve any useful extra fields without retaining the whole raw response.
    for label in ("change_mom", "change_qoq", "portfolio_date", "as_of"):
        value = _first(row, [label])
        if value not in (None, ""):
            normalized[label] = value

    return normalized


def _dedupe_holdings(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        key = row.get("isin") or _norm(row.get("name"))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _parse_fund_disclosures(payload: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    meta: Dict[str, Any] = {}
    if isinstance(payload, dict):
        raw_meta = payload.get("meta")
        if isinstance(raw_meta, dict):
            meta.update(raw_meta)
        for key in ("as_of", "portfolio_date", "filing_date", "scheme_code", "amfi_code"):
            if key in payload and payload[key] not in (None, ""):
                meta[key] = payload[key]
        scheme = payload.get("scheme")
        if isinstance(scheme, dict):
            for key in ("amfi_code", "name", "amc_name", "parent_name", "isin"):
                if scheme.get(key) not in (None, "") and key not in meta:
                    meta[f"scheme_{key}"] = scheme[key]

    raw_rows: List[Any] = []
    for candidate in _extract_candidate_lists(payload):
        raw_rows.extend(candidate)

    normalized = []
    for row in raw_rows:
        if isinstance(row, dict):
            item = _normalize_holding(row, "fund-disclosures")
            if item:
                normalized.append(item)

    return _dedupe_holdings(normalized), meta


def fetch_cdn_holdings(
    session: requests.Session, scheme_code: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    catalog = fetch_cdn_catalog(session)
    lookup = catalog.get("lookup") or {}
    row = lookup.get(str(scheme_code))
    if not isinstance(row, dict):
        raise RuntimeError(f"CDN catalog has no AMFI {scheme_code}")

    ref = str(catalog.get("ref") or "main")
    as_of = str(row.get("latest_as_of") or row.get("as_of") or "").strip()
    portfolio_id = str(row.get("portfolio_id") or row.get("parent_amfi") or "").strip()
    portfolio_url = str(row.get("portfolio_url") or "").strip()
    portfolio_key = str(row.get("portfolio_key") or "").strip()
    if not portfolio_key and as_of and portfolio_id:
        portfolio_key = f"portfolios/asof/{as_of}/{portfolio_id}.json"
    if not portfolio_url:
        if not portfolio_key:
            raise RuntimeError(
                f"CDN catalog row for AMFI {scheme_code} has no portfolio path"
            )
        portfolio_url = _cdn_url(ref, portfolio_key)

    urls = [portfolio_url]
    if portfolio_key:
        raw = _cdn_url(ref, portfolio_key, raw=True)
        if raw not in urls:
            urls.append(raw)

    payload, headers = _request_json_multi(session, urls)
    holdings, meta = _parse_fund_disclosures(payload)
    if as_of and not meta.get("as_of"):
        meta["as_of"] = as_of
    meta["source"] = "fund-disclosures"
    meta["transport"] = "github-cdn"
    meta["endpoint"] = portfolio_url
    meta["retrieved_at"] = _now_iso()
    meta["catalog_commit"] = ref
    meta["amfi_code"] = str(scheme_code)
    if portfolio_id:
        meta["portfolio_id"] = portfolio_id
    meta["http_request_id"] = headers.get("x-request-id")
    if not holdings:
        raise RuntimeError(f"CDN returned no holdings for AMFI {scheme_code}")
    return holdings, meta


def fetch_fund_disclosures(session: requests.Session, scheme_code: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    url = FUND_DISCLOSURES_API.format(scheme_code=scheme_code)
    payload, headers = _request_json(session, url)
    holdings, meta = _parse_fund_disclosures(payload)
    meta["source"] = "fund-disclosures"
    meta["endpoint"] = url
    meta["retrieved_at"] = _now_iso()
    meta["http_request_id"] = headers.get("x-request-id")
    if not holdings:
        raise RuntimeError(f"fund-disclosures returned no holdings for AMFI {scheme_code}")
    return holdings, meta


def _parse_mfdata_holdings(payload: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    meta: Dict[str, Any] = {}
    if not isinstance(payload, dict):
        return [], meta
    data = payload.get("data", payload)
    if isinstance(data, dict):
        for key in ("family_id", "month", "scheme_code", "scheme_name"):
            if key in data:
                meta[key] = data[key]
        rows: List[Any] = []
        for key in ("equity", "debt", "other", "holdings"):
            if isinstance(data.get(key), list):
                rows.extend(data[key])
    elif isinstance(data, list):
        rows = data
    else:
        rows = []

    normalized = []
    for row in rows:
        if isinstance(row, dict):
            item = _normalize_holding(row, "mfdata")
            if item:
                normalized.append(item)
    return _dedupe_holdings(normalized), meta


def fetch_mfdata_fallback(session: requests.Session, scheme_code: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    details_url = f"{MFDATA_BASE}/api/v1/schemes/{scheme_code}"
    details, _ = _request_json(session, details_url)
    data = details.get("data", {}) if isinstance(details, dict) else {}
    family_id = data.get("family_id") or data.get("familyId")
    if not family_id:
        raise RuntimeError(f"mfdata has no family_id for AMFI {scheme_code}")

    holdings_url = f"{MFDATA_BASE}/api/v1/families/{family_id}/holdings"
    payload, _ = _request_json(session, holdings_url)
    holdings, meta = _parse_mfdata_holdings(payload)
    meta.update({
        "source": "mfdata",
        "endpoint": holdings_url,
        "retrieved_at": _now_iso(),
        "family_id": family_id,
    })
    if not holdings:
        raise RuntimeError(f"mfdata returned no holdings for family {family_id}")
    return holdings, meta


def validate_holdings(holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
    weights = [h["weight_pct"] for h in holdings if isinstance(h.get("weight_pct"), (int, float))]
    weight_sum = sum(weights) if weights else None
    return {
        "holding_count": len(holdings),
        "holdings_with_weight": len(weights),
        "weight_sum_pct": round(weight_sum, 4) if weight_sum is not None else None,
        "weight_check": (
            "PASS" if weight_sum is not None and 97 <= weight_sum <= 103 else
            "WARN" if weight_sum is not None and 90 <= weight_sum <= 110 else
            "NOT_AVAILABLE"
        ),
        "has_isin": sum(1 for h in holdings if h.get("isin")),
        "has_market_value": sum(1 for h in holdings if h.get("market_value") is not None),
    }


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json_atomic(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def ingest_scheme_holdings(session: requests.Session, scheme_code: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Try the GitHub/jsDelivr statutory CDN first, then Vercel, then mfdata."""
    errors: List[str] = []

    try:
        holdings, meta = fetch_cdn_holdings(session, scheme_code)
        meta["validation"] = validate_holdings(holdings)
        meta["fallback_used"] = False
        return holdings, meta
    except Exception as exc:
        errors.append(f"cdn: {exc}")

    try:
        holdings, meta = fetch_fund_disclosures(session, scheme_code)
        meta["validation"] = validate_holdings(holdings)
        meta["fallback_used"] = True
        meta["primary_error"] = errors[-1]
        return holdings, meta
    except Exception as exc:
        errors.append(f"fund-disclosures: {exc}")

    try:
        holdings, meta = fetch_mfdata_fallback(session, scheme_code)
        meta["validation"] = validate_holdings(holdings)
        meta["fallback_used"] = True
        meta["primary_error"] = errors[-1]
        return holdings, meta
    except Exception as exc:
        errors.append(f"mfdata: {exc}")

    raise RuntimeError(" | ".join(errors))
