# -------------------------------------------------
# scripts/clear_stale_news_cache — zero-record news-cache cleanup regression.
#
# The live-research news adapter writes one JSON bucket per (query, category);
# a retired query shape can leave a permanent 0-record bucket behind, blocking
# nothing but misleading anyone reading the cache. This suite pins the exact
# rule: buckets with zero records are deleted, buckets WITH records and
# corrupt buckets are never touched. No network, no credentials.
# -------------------------------------------------
from __future__ import annotations

import json
from pathlib import Path

from scripts.clear_stale_news_cache import clear_stale_news_cache


def _write_bucket(cache_dir: Path, name: str, records: list) -> Path:
    path = cache_dir / name
    path.write_text(json.dumps({
        "meta": {"provider": "gnews", "key": f"gnews:cache:holding:{name.split('_', 3)[-1]}",
                 "retrieved_at": "2026-09-14T05:30:00"},
        "data": {"metadata": {"query": name, "category": "holding"},
                 "records": records},
    }), encoding="utf-8")
    return path


def _news_record() -> dict:
    return {
        "id": "gnews:cache:holding:some:query:abc123",
        "provider": "gnews",
        "entity": "some query",
        "title": "some headline",
        "retrieved_at": "2026-09-14T05:30:00",
        "published_at": "2026-09-14T05:00:00",
        "payload": {"query": "some query", "category": "holding"},
    }


def test_deletes_zero_record_buckets_keeps_full_and_corrupt(tmp_path):
    zero = tmp_path / "gnews_cache_holding_GOLDBEES_73320_32.json"
    full = tmp_path / "gnews_cache_holding_GOLDBEES.json"
    other = tmp_path / "gnews_cache_holding_SGBSEP31.json"
    corrupt = tmp_path / "gnews_cache_holding_GOLDBEES_old.json"
    _write_bucket(tmp_path, zero.name, [])
    _write_bucket(tmp_path, full.name, [_news_record()])
    _write_bucket(tmp_path, other.name, [])  # different holding -> untouched
    corrupt.write_text("{not json", encoding="utf-8")

    result = clear_stale_news_cache(tmp_path)

    assert result.deleted == (zero,)
    assert not zero.exists()
    assert full.exists()
    assert other.exists()
    assert corrupt.exists()
    assert result.kept == (full,)
    assert result.skipped == ((corrupt, "unreadable/corrupt JSON — kept"),)


def test_dry_run_deletes_nothing(tmp_path):
    zero = tmp_path / "gnews_cache_holding_GOLDBEES_73320_32.json"
    _write_bucket(tmp_path, zero.name, [])

    result = clear_stale_news_cache(tmp_path, dry_run=True)

    assert result.deleted == (zero,)
    assert zero.exists()  # nothing was removed


def test_missing_directory_is_safe(tmp_path):
    missing = tmp_path / "does_not_exist"
    result = clear_stale_news_cache(missing)
    assert result.deleted == ()
    assert result.skipped == ((missing, "directory not found"),)


def test_non_zero_record_bucket_never_deleted(tmp_path):
    full = tmp_path / "gnews_cache_holding_GOLDBEES.json"
    _write_bucket(tmp_path, full.name, [_news_record(), _news_record()])

    result = clear_stale_news_cache(tmp_path)

    assert result.deleted == ()
    assert result.kept == (full,)
    assert full.exists()