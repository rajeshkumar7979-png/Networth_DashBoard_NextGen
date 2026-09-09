# -------------------------------------------------
# Intelligence Data Gateway — record/result model.
#
# Pure module. SourceRecord wraps ONE normalized external data point. It is the
# gateway's output unit and converts into the canonical intelligence Evidence
# via model.make_evidence. SourceResult wraps a whole provider round-trip.
#
# Caching rule: a cache Hit is a stored SourceResult; fields reprinted below.
# -------------------------------------------------
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from lib.intelligence.model import (
    Evidence,
    FactKind,
    SourceClass,
    SourceType,
    make_evidence,
    slugify,
)

OBSERVED = SourceType.OBSERVED
OFFICIAL_FILING = SourceType.OFFICIAL_FILING


def utc_now() -> datetime:
    """Naive UTC timestamp used across the gateway for determinism."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def make_record_id(provider: str, *parts: object) -> str:
    """Deterministic, stable record id: provider + slugified parts.

    Same inputs => same id; distinct observations must never collide.
    """
    out = [slugify(str(provider))]
    for part in parts:
        token = str(part)
        cleaned = re.sub(r"[^0-9A-Za-z._:-]+", "_", token).strip("_")
        out.append(cleaned if len(cleaned) <= 60 else cleaned[:60])
    return ":".join(out)


def _json_safe(value):
    """Recursively make a payload JSON-serializable (datetimes -> iso)."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return to_iso(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def _enum_or(enum_cls, value, default):
    """Map a stored enum value, falling back to `default` for corrupt entries."""
    try:
        return enum_cls(str(value))
    except (ValueError, TypeError):
        return default


def _dict_or(value) -> dict:
    return dict(value) if isinstance(value, dict) else {}


@dataclass(frozen=True)
class SourceRecord:
    """One normalized, immutable, externally-observed data point."""

    id: str
    provider: str
    entity: str
    title: str
    retrieved_at: datetime
    source_class: SourceClass
    source_type: SourceType
    published_at: Optional[datetime] = None
    reference: Optional[str] = None
    confidence: Optional[float] = None
    payload: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "provider": self.provider,
            "entity": self.entity,
            "title": self.title,
            "retrieved_at": to_iso(self.retrieved_at),
            "source_class": self.source_class.value,
            "source_type": self.source_type.value,
            "published_at": to_iso(self.published_at),
            "reference": self.reference,
            "confidence": self.confidence,
            "payload": _json_safe(self.payload),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SourceRecord":
        """Rebuild from a stored dict. Tolerant of corrupt/partial payloads:
        bad enum values default, non-dict payloads become {}, missing datetimes
        fall back to now. Never raises on malformed input."""
        return cls(
            id=str(data.get("id", "")),
            provider=str(data.get("provider", "")),
            entity=str(data.get("entity", "")),
            title=str(data.get("title", "")),
            retrieved_at=parse_iso(data.get("retrieved_at")) or utc_now(),
            source_class=_enum_or(SourceClass, data.get("source_class"), SourceClass.D),
            source_type=_enum_or(SourceType, data.get("source_type"), OBSERVED),
            published_at=parse_iso(data.get("published_at")),
            reference=data.get("reference"),
            confidence=data.get("confidence"),
            payload=_dict_or(data.get("payload")),
        )

    def to_evidence(self) -> Evidence:
        """Convert into canonical intelligence evidence.

        External data is always an observed FACT — never AI, never calculated.
        """
        payload = _json_safe(self.payload)
        payload["provider"] = self.provider
        if self.published_at is not None:
            payload["published_at"] = to_iso(self.published_at)
        return make_evidence(
            eid=self.id,
            source=self.provider,
            source_class=self.source_class,
            source_type=self.source_type,
            entity=self.entity,
            title=self.title,
            now=self.retrieved_at,
            fact_kind=FactKind.FACT,
            reference=self.reference,
            confidence=self.confidence,
            payload=payload,
        )


def dedupe_records(records: Iterable[SourceRecord]) -> tuple[SourceRecord, ...]:
    """Collapse duplicate record ids, preserving first occurrence order."""
    seen: set[str] = set()
    out = []
    for rec in records:
        if rec.id in seen:
            continue
        seen.add(rec.id)
        out.append(rec)
    return tuple(out)


@dataclass(frozen=True)
class SourceResult:
    """Outcome of one provider round-trip (or cache hit)."""

    provider: str
    status: str = "ok"  # "ok" | "unavailable"
    records: tuple[SourceRecord, ...] = ()
    retrieved_at: Optional[datetime] = None
    is_stale: bool = False
    cache_hit: bool = False
    reason: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "status": self.status,
            "record_count": len(self.records),
            "retrieved_at": to_iso(self.retrieved_at),
            "is_stale": self.is_stale,
            "cache_hit": self.cache_hit,
            "reason": self.reason,
            "metadata": _json_safe(self.metadata),
            "records": [r.as_dict() for r in self.records],
        }


def unavailable_result(provider: str, reason: str, **extra) -> SourceResult:
    """A provider failure is NEVER a success with zero records."""
    return SourceResult(
        provider=provider,
        status="unavailable",
        records=(),
        reason=reason,
        metadata=extra,
    )


def cached_result(provider: str, entry: dict, *, default_retrieved=None) -> Optional[SourceResult]:
    """Decode a stored gateway cache entry into a SourceResult.

    The single decode path shared by every provider. A structurally corrupt
    entry (meta/data not objects, records not a list, every record unusable)
    returns None so callers degrade to a live fetch or an explicit
    "unavailable" — a corrupted cache NEVER becomes a fabricated record.
    """
    if not isinstance(entry, dict):
        return None
    body = entry.get("data")
    meta = entry.get("meta") or {}
    if not isinstance(body, dict) or not isinstance(meta, dict):
        return None
    raw_records = body.get("records")
    if raw_records is None:
        raw_records = []
    if not isinstance(raw_records, list):
        return None

    records = []
    for raw in raw_records:
        if not isinstance(raw, dict):
            continue
        try:
            rec = SourceRecord.from_dict(raw)
        except Exception:
            continue
        if not all((rec.id, rec.provider, rec.entity, rec.title)):
            continue
        records.append(rec)
    if raw_records and not records:
        # records existed but none survived decode -> treated as corrupt
        return None

    records = tuple(records)
    retrieved = parse_iso(meta.get("retrieved_at"))
    if retrieved is None and records:
        retrieved = records[0].retrieved_at
    if retrieved is None:
        retrieved = default_retrieved

    metadata = body.get("metadata")
    return SourceResult(
        provider=provider,
        status="ok",
        records=records,
        retrieved_at=retrieved,
        cache_hit=True,
        metadata=_dict_or(metadata),
    )