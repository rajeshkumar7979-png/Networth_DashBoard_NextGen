#!/usr/bin/env python3
"""Fail CI if critical modules were replaced by placeholders or stubs."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# path -> minimum acceptable byte size
CRITICAL = {
    "lib/mf_holdings.py": 15_000,
    "scripts/update_holdings_cache.py": 12_000,
    "pages/5_MF_Health.py": 8_000,
    # Command Center may be a thin loader that bootstraps the full body.
    "pages/1_Command_Center.py": 1_500,
    "lib/overlap.py": 3_000,
    "lib/history.py": 4_000,
}

# Thin loader is valid if it clearly bootstraps a real body.
LOADER_MARKERS = (
    "_load_github_body",
    "Command Center loader",
    "cc_parts",
    "Command_Center_loaded",
    "Command_Center_bootstrapped",
)

BAD_MARKERS = (
    "PLACEHOLDER",
    "SEE ARTIFACT",
    "SEE_ARTIFACT",
    "truncated push blocked",
)


def main() -> int:
    failed = False
    for rel, min_size in CRITICAL.items():
        path = ROOT / rel
        if not path.exists():
            print(f"MISSING {rel}")
            failed = True
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        size = len(raw.encode("utf-8"))
        effective_min = min_size
        if rel.endswith("1_Command_Center.py") and any(m in raw for m in LOADER_MARKERS):
            effective_min = 1_500
            if "total_networth" not in raw and "_load_github_body" not in raw and "cc_parts" not in raw:
                print(f"BAD_LOADER {rel}: loader markers present but no body source")
                failed = True
        if size < effective_min:
            print(f"TOO_SMALL {rel}: {size} bytes (need >= {effective_min})")
            failed = True
        for marker in BAD_MARKERS:
            if marker in raw:
                print(f"BAD_MARKER {rel}: contains {marker!r}")
                failed = True
        if not failed:
            print(f"OK {rel}: {size} bytes (min {effective_min})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
