# scripts/clear_stale_news_cache.py
"""Delete zero-record Google News RSS cache entries left behind by old query
shapes.

The live-research news adapter writes one JSON bucket per (query, category)
under data/live_research_cache/ (gitignored). If a planner change alters how a
query string is built, the OLD query's cache bucket can linger forever holding
zero records. Those records are harmless on their own but are stale dead weight
that masks freshly-fixed queries (e.g. the old "GOLDBEES 73320 32" number-laden
queries produced by the pre-fix gold route). They must never block the current
pipeline, so this script prunes every bucket for a given key prefix whose JSON
content has an empty records list.

A bucket with records (record_count > 0) is NEVER deleted — the script only
removes the 0-record leftovers of retired query shapes. Corrupt/unreadable JSON
is skipped with a warning, never deleted. No network, no credentials.

Run it after any planner change that can alter derived query strings:
    python scripts/clear_stale_news_cache.py
Use --dry-run to preview what would be deleted, and --cache-dir to target a
different cache directory (used by the regression tests).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_LOG = logging.getLogger("clear_stale_news_cache")

# Live news cache buckets live under data/live_research_cache and are named
# gnews_cache_<category>_<query>.json (colons in the cache key become
# underscores). The default target is the legacy gold-route bucket family.
DEFAULT_PREFIX = "gnews_cache_holding_GOLDBEES"


@dataclass(frozen=True)
class CleanupResult:
    deleted: tuple[Path, ...]
    kept: tuple[Path, ...]
    skipped: tuple[tuple[Path, str], ...]

    @property
    def deleted_count(self) -> int:
        return len(self.deleted)


def _record_count(path: Path) -> Optional[int]:
    """Number of records in a news cache bucket; None when unreadable/corrupt.

    The gateway JSON layout is {"meta": ..., "data": {"metadata": ..., "records": [...]}}
    (cache.save wraps a {"metadata", "records"} payload). Tolerate a top-level
    "records" as well so a hand-written bucket still parses.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    body = payload.get("data") if isinstance(payload, dict) else None
    records = None
    if isinstance(body, dict):
        records = body.get("records")
    if records is None and isinstance(payload, dict):
        records = payload.get("records")
    if not isinstance(records, list):
        return None
    return len(records)


def clear_stale_news_cache(cache_dir: Path, *, prefix: str = DEFAULT_PREFIX,
                           dry_run: bool = False) -> CleanupResult:
    """Scan `cache_dir` for `{prefix}*.json` buckets and delete the stale ones.

    A bucket is stale when its cache is fully readable AND holds zero records.
    Corrupt buckets are skipped (never deleted); buckets with records are kept.
    With dry_run=True nothing is removed and every would-be deletion is logged.
    """
    cache_dir = Path(cache_dir)
    deleted: list[Path] = []
    kept: list[Path] = []
    skipped: list[tuple[Path, str]] = []

    if not cache_dir.is_dir():
        _LOG.warning("cache directory not found: %s (nothing to clean)", cache_dir)
        return CleanupResult((), (), ((cache_dir, "directory not found"),))

    for path in sorted(cache_dir.glob(f"{prefix}*.json")):
        count = _record_count(path)
        if count is None:
            skipped.append((path, "unreadable/corrupt JSON — kept"))
            _LOG.warning("kept (unreadable): %s", path)
            continue
        if count > 0:
            kept.append(path)
            _LOG.info("kept (%d records): %s", count, path.name)
            continue
        # record_count == 0: a leftover from a retired query shape.
        if dry_run:
            _LOG.info("would delete (0 records): %s", path)
        else:
            _LOG.info("deleted (0 records): %s", path)
            try:
                path.unlink()
            except OSError as exc:
                skipped.append((path, f"delete failed: {type(exc).__name__}"))
                _LOG.error("delete failed: %s (%s)", path, exc)
                continue
        deleted.append(path)

    return CleanupResult(tuple(deleted), tuple(kept), tuple(skipped))


def _build_parser() -> argparse.ArgumentParser:
    default_dir = Path(__file__).resolve().parents[1] / "data" / "live_research_cache"
    parser = argparse.ArgumentParser(
        description="Delete zero-record Google News RSS cache buckets.")
    parser.add_argument(
        "--cache-dir", type=Path, default=default_dir,
        help="live-research cache directory (default: data/live_research_cache)")
    parser.add_argument(
        "--prefix", default=os.environ.get("STALE_CACHE_PREFIX", DEFAULT_PREFIX),
        help="file prefix to scan (default: gnews_cache_holding_GOLDBEES)")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="list would-be deletions without deleting anything")
    return parser


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s")
    args = _build_parser().parse_args(argv)
    result = clear_stale_news_cache(
        args.cache_dir, prefix=args.prefix, dry_run=args.dry_run)
    action = "would delete" if args.dry_run else "deleted"
    print(f"{action} zero-record buckets: {result.deleted_count}")
    if result.skipped:
        for path, reason in result.skipped:
            print(f"kept {path.name}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())