# -------------------------------------------------
# Intelligence Data Gateway — SEC EDGAR (company filings + summary company facts).
#
# Provider: data.sec.gov JSON APIs only (CIK%010d paths). User-Agent comes from
# the SEC_USER_AGENT env var; the default is an identifiable non-email string
# so SEC's traffic policy is respected without hard-coding a personal contact.
# Normalizes filing metadata only — no financial values are interpreted or
# inferred here.
# -------------------------------------------------
from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Optional

from . import httpio as _http
from .cache import Cache
from .errors import ProviderConfigMissing, ProviderUnavailable
from .record import (
    SourceRecord,
    SourceResult,
    cached_result,
    dedupe_records,
    make_record_id,
    unavailable_result,
    utc_now,
)
from lib.intelligence.model import SourceClass, SourceType

SEC_BASE = "https://data.sec.gov"
SEC_DEFAULT_TTL = 24 * 3600
SEC_DEFAULT_UA = "NetworthDashboard/0.1 (local research dashboard; set SEC_USER_AGENT env to identify)"
SEC_RATE_SLEEP = 0.1

_HEADERS = {
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}


def _user_agent() -> str:
    return os.environ.get("SEC_USER_AGENT", "").strip() or SEC_DEFAULT_UA


def _headers() -> dict:
    return {**_HEADERS, "User-Agent": _user_agent()}


def _cik(value) -> int:
    if isinstance(value, int):
        cik = value
    else:
        text = str(value).strip()
        if not text.isdigit():
            raise ValueError(f"invalid CIK: {text!r}")
        cik = int(text)
    if cik <= 0:
        raise ValueError("CIK must be a positive integer")
    return cik


def _cik_padded(cik: int) -> str:
    return f"{cik:010d}"


def _filing_url(cik: int, accession: str, primary_doc) -> str | None:
    if not primary_doc:
        return None
    return (
        f"{SEC_BASE}/Archives/edgar/data/{cik}/"
        f"{accession.replace('-', '')}/{primary_doc}"
    )


def _at(values: list, idx: int) -> str:
    """Safe per-field access for parallel EDGAR arrays (short arrays stay empty)."""
    if idx < len(values):
        return str(values[idx] or "")
    return ""


def _submission_records(cik: int, name: str, recent: dict, limit: int, now) -> tuple[SourceRecord, ...]:
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accessions = recent.get("accessionNumber") or []
    docs = recent.get("primaryDocument") or []
    reports = recent.get("reportDate") or []
    periods = min(limit, len(forms))
    records = []
    for i in range(periods):
        form = _at(forms, i)
        accession = _at(accessions, i)
        doc = _at(docs, i)
        filing_date = _at(dates, i)
        report_date = _at(reports, i)
        published = None
        if filing_date:
            try:
                published = datetime.strptime(filing_date, "%Y-%m-%d")
            except ValueError:
                pass
        records.append(SourceRecord(
            id=make_record_id("sec", "filing", cik, accession or f"idx{i}", form),
            provider="sec",
            entity=str(name) or f"CIK {cik}",
            title=f"{form} · {filing_date}",
            retrieved_at=now,
            source_class=SourceClass.A,
            source_type=SourceType.OFFICIAL_FILING,
            published_at=published,
            reference=_filing_url(cik, accession, doc),
            payload={
                "cik": cik,
                "cik_padded": _cik_padded(cik),
                "company_name": str(name) or "",
                "form": form,
                "filing_date": filing_date,
                "report_date": report_date,
                "accession_number": accession,
                "primary_document": doc,
            },
        ))
    return dedupe_records(records)


def _facts_summary(cik: int, data: dict, now) -> list[SourceRecord]:
    name = str(data.get("entityName") or f"CIK {cik}")
    facts = data.get("facts") or {}
    taxonomy_counts = {
        str(k): len(v) if isinstance(v, dict) else 0
        for k, v in facts.items()
    }
    record = SourceRecord(
        id=make_record_id("sec", "facts", cik),
        provider="sec",
        entity=name,
        title=f"{name} · XBRL company-facts summary",
        retrieved_at=now,
        source_class=SourceClass.A,
        source_type=SourceType.OFFICIAL_FILING,
        reference=(f"{SEC_BASE}/files/Archives/edgar/data/{cik}/"
                   f"CIK{_cik_padded(cik)}.json"),
        payload={
            "cik": cik,
            "cik_padded": _cik_padded(cik),
            "entity_name": name,
            "sic": data.get("sic"),
            "sic_description": data.get("sicDescription"),
            "exchange": data.get("exchange"),
            "ticker": data.get("ticker"),
            "taxonomy_counts": taxonomy_counts,
            "summary_only": True,
        },
    )
    return [record]


def _from_cache_entry(entry: dict) -> Optional[SourceResult]:
    """Decode a stored SEC cache entry; None when corrupt (never raises)."""
    provider = "sec"
    return cached_result(provider, entry)


def _cached_or_unavailable(cache: Cache, key: str, exc: Exception,
                           decoded: Optional[SourceResult]) -> SourceResult:
    if decoded is not None:
        return SourceResult(
            provider=decoded.provider,
            status="ok",
            records=decoded.records,
            retrieved_at=decoded.retrieved_at,
            is_stale=True,
            cache_hit=False,
            reason=f"stale cache served; live refresh failed ({type(exc).__name__})",
            metadata=decoded.metadata,
        )
    return unavailable_result(key.split(":", 1)[0], f"refresh failed: {type(exc).__name__}: {exc}")


def _fetch_sec_data(url: str, params=None, rate_sleep: float = SEC_RATE_SLEEP):
    if rate_sleep and rate_sleep > 0:
        time.sleep(rate_sleep)
    response = _http._http_get(url, params=params, headers=_headers(), timeout=(10, 30))
    return _http._response_json(response)


def _fetch_company_facts_data(cik: int, rate_sleep: float):
    """companyfacts has two documented paths; some networks only serve one."""
    candidates = (
        f"{SEC_BASE}/companyfacts/CIK{_cik_padded(cik)}.json",
        f"{SEC_BASE}/api/xbrl/companyfacts/CIK{_cik_padded(cik)}.json",
    )
    last_error: Exception | None = None
    for url in candidates:
        try:
            return url, _fetch_sec_data(url, rate_sleep=rate_sleep)
        except ProviderUnavailable as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ProviderUnavailable("companyfacts unavailable")


def fetch_sec_submissions(cik, *, cache=None, limit: int = 10,
                          ttl_seconds: int = SEC_DEFAULT_TTL, force_refresh: bool = False,
                          rate_sleep: float = SEC_RATE_SLEEP, now=None) -> SourceResult:
    """Normalize a company's recent SEC filings. Never re-raises provider errors."""
    cache = cache or Cache()
    if not ttl_seconds:
        ttl_seconds = SEC_DEFAULT_TTL
    cik = _cik(cik)
    key = f"sec:submissions:{cik}"

    cached = cache.load(key)
    decoded = _from_cache_entry(cached) if cached is not None else None
    fresh = decoded is not None and cache.is_fresh(key, ttl_seconds, now=now)
    if fresh and not force_refresh:
        return decoded

    try:
        url = f"{SEC_BASE}/submissions/CIK{_cik_padded(cik)}.json"
        data = _fetch_sec_data(url, rate_sleep=rate_sleep)
        name = str(data.get("name") or f"CIK {cik}")
        recent = data.get("filings") or {}
        recent = recent.get("recent") or {}
        now = utc_now()
        records = _submission_records(cik, name, recent, int(limit), now)
        result = SourceResult(
            provider="sec",
            status="ok",
            records=records,
            retrieved_at=now,
            metadata={"company_name": name, "cik": cik},
        )
        cache.save(
            key,
            {"metadata": result.metadata, "records": [r.as_dict() for r in records]},
            provider="sec",
            retrieved_at=result.retrieved_at,
        )
        return result
    except (ValueError, ProviderConfigMissing):
        raise
    except Exception as exc:
        return _cached_or_unavailable(cache, key, exc, decoded)


def fetch_sec_company_facts(cik, *, cache=None, ttl_seconds: int = SEC_DEFAULT_TTL,
                            force_refresh: bool = False, rate_sleep: float = SEC_RATE_SLEEP,
                            now=None) -> SourceResult:
    """Summary-only company-facts availability. Never returns financial values."""
    cache = cache or Cache()
    if not ttl_seconds:
        ttl_seconds = SEC_DEFAULT_TTL
    cik = _cik(cik)
    key = f"sec:facts:{cik}"

    cached = cache.load(key)
    decoded = _from_cache_entry(cached) if cached is not None else None
    fresh = decoded is not None and cache.is_fresh(key, ttl_seconds, now=now)
    if fresh and not force_refresh:
        return decoded

    try:
        _url, data = _fetch_company_facts_data(cik, rate_sleep)
        now = utc_now()
        records = _facts_summary(cik, data, now)
        result = SourceResult(
            provider="sec",
            status="ok",
            records=records,
            retrieved_at=now,
            metadata={"entity_name": records[0].entity, "cik": cik},
        )
        cache.save(
            key,
            {"metadata": result.metadata, "records": [r.as_dict() for r in records]},
            provider="sec",
            retrieved_at=result.retrieved_at,
        )
        return result
    except (ValueError, ProviderConfigMissing):
        raise
    except Exception as exc:
        return _cached_or_unavailable(cache, key, exc, decoded)