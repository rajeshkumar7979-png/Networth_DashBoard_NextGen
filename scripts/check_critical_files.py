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
    "pages/1_Command_Center.py": 40_000,
    "lib/overlap.py": 3_000,
    "lib/history.py": 4_000,
}

BAD_MARKERS = (
    "PLACEHOLDER",
    "SEE ARTIFACT",
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
        if size < min_size:
            print(f"TOO_SMALL {rel}: {size} bytes (need >= {min_size})")
            failed = True
        for marker in BAD_MARKERS:
            if marker in raw:
                print(f"BAD_MARKER {rel}: contains {marker!r}")
                failed = True
        if not failed:
            print(f"OK {rel}: {size} bytes")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
