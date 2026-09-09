# -------------------------------------------------
# Intelligence Data Gateway — JSON file cache.
#
# Deterministic keys, atomic writes, retrieval timestamps, stale detection.
# NO database. Cached files live under data/intel_gateway_cache/ (gitignored)
# and are plain JSON; a malformed cache entry degrades to "no cache", never to
# a fabricated record.
# -------------------------------------------------
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from lib.config import DATA_DIR
from .record import parse_iso, to_iso, utc_now

DEFAULT_CACHE_DIR = Path(DATA_DIR) / "intel_gateway_cache"

DEFAULT_TTL_SECONDS = {
    "fred": 12 * 3600,          # twice a day
    "sec": 24 * 3600,           # once a day
    "mf_nav": 7 * 24 * 3600,    # NAV universe refreshes weekly
    "mf_holdings": 35 * 24 * 3600,  # fund disclosures are monthly
}


def default_ttl_seconds(provider: str) -> int:
    return DEFAULT_TTL_SECONDS.get(provider, 24 * 3600)


@dataclass(frozen=True)
class CacheEntry:
    """One scan line: provider, key, freshness and status of a cached file."""

    provider: str
    key: str
    retrieved_at: Optional[datetime]
    record_count: Optional[int]
    is_stale: bool
    status: str
    reason: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "key": self.key,
            "last_retrieval": to_iso(self.retrieved_at),
            "record_count": self.record_count,
            "is_stale": self.is_stale,
            "status": self.status,
            "reason": self.reason,
        }


def _safe_key(key: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "._-" else "_" for c in key)
    return cleaned.strip("_")[:120] or "entry"


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".gateway-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=1, sort_keys=True)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json_fallback(path: Path) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        return None
    return None


class Cache:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else DEFAULT_CACHE_DIR

    def _path(self, key: str) -> Path:
        return self.base_dir / f"{_safe_key(key)}.json"

    def load(self, key: str) -> Optional[dict]:
        """Raw stored entry (meta + data), or None when absent/not usable."""
        return _read_json_fallback(self._path(key))

    def save(self, key: str, data: dict, *, provider: str, retrieved_at=None) -> None:
        if not isinstance(data, dict):
            raise ValueError("cache data must be a dict")
        retrieved_at = retrieved_at or utc_now()
        payload = {
            "meta": {
                "provider": provider,
                "key": key,
                "retrieved_at": to_iso(retrieved_at),
            },
            "data": data,
        }
        _atomic_write_json(self._path(key), payload)

    def retrieved_at(self, key: str) -> Optional[datetime]:
        entry = self.load(key)
        if not entry or not isinstance(entry, dict):
            return None
        return parse_iso((entry.get("meta") or {}).get("retrieved_at"))

    def is_fresh(self, key: str, ttl_seconds: int, now=None) -> bool:
        fetched = self.retrieved_at(key)
        if fetched is None:
            return False
        now = now or utc_now()
        age = (now - fetched).total_seconds()
        return age >= 0 and age < ttl_seconds

    def is_stale(self, key: str, ttl_seconds: int, now=None) -> bool:
        fetched = self.retrieved_at(key)
        if fetched is None:
            return False
        now = now or utc_now()
        return (now - fetched).total_seconds() >= ttl_seconds

    def scan(self, now=None) -> list[CacheEntry]:
        """Read every cached file and report freshness/status. No network."""
        now = now or utc_now()
        if not self.base_dir.is_dir():
            return []
        entries: list[CacheEntry] = []
        for path in sorted(self.base_dir.glob("*.json")):
            try:
                data = _read_json_fallback(path) or {}
                meta = data.get("meta") or {}
                body = data.get("data") or {}
                provider = str(meta.get("provider") or "misc")
                key = str(meta.get("key") or path.stem)
                fetched = parse_iso(meta.get("retrieved_at"))
                records = body.get("records") or []
                count = len(records) if isinstance(records, list) else None
                status = str(meta.get("status") or "ok")
                stale = fetched is not None and (now - fetched).total_seconds() >= default_ttl_seconds(provider)
                entries.append(CacheEntry(
                    provider=provider,
                    key=key,
                    retrieved_at=fetched,
                    record_count=count,
                    is_stale=stale,
                    status=status,
                ))
            except Exception:
                continue
        return entries