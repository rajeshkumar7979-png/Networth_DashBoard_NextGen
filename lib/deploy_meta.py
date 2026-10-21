"""Deploy identity and MF period status for production transparency."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BUILD_SHA_PATH = ROOT / "data" / "BUILD_SHA.txt"
HOLDINGS_META = ROOT / "data" / "mf_holdings_meta.json"


def short_sha(value: str | None, n: int = 8) -> str:
    if not value:
        return "unknown"
    v = str(value).strip()
    return v[:n] if v else "unknown"


def resolve_build_sha() -> str:
    """Best-effort deploy identity for the footer.

    Order: env NORTHLINE_BUILD_SHA → git rev-parse → data/BUILD_SHA.txt.
    """
    env = (os.environ.get("NORTHLINE_BUILD_SHA") or "").strip()
    if env:
        return short_sha(env)
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return short_sha(out.decode("utf-8", errors="replace"))
    except Exception:
        pass
    if BUILD_SHA_PATH.exists():
        try:
            return short_sha(BUILD_SHA_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return "unknown"


def render_build_footer(st_module) -> None:
    """Global footer: build SHA + production honesty lines."""
    sha = resolve_build_sha()
    st_module.caption(
        f"Build {sha} · Command Center is live truth · "
        f"History is the durable trend · Read-only desk — no orders"
    )
    st_module.caption(
        "Health scores are illustrative NRI allocation/liquidity indices, not rating-agency scores. "
        "MF holdings source: OpenFin CDN (monthly AMC filings). "
        "Public deploy uses the sample book unless a private path is configured."
    )


def mf_period_status(meta_path: Path | None = None) -> dict[str, Any]:
    """Summarise committed holdings meta for the Funds banner."""
    path = meta_path or HOLDINGS_META
    empty = {
        "ok": False,
        "reason": "No holdings meta cache",
        "as_of_dates": [],
        "latest_as_of": None,
        "scheme_count": 0,
        "same_period": 0,
        "new_period": 0,
        "changed": 0,
        "errors": 0,
        "unresolved": 0,
    }
    if not path.exists():
        return empty
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {**empty, "reason": "Holdings meta unreadable"}
    if not isinstance(meta, dict):
        return {**empty, "reason": "Holdings meta not a dict"}

    as_ofs: list[str] = []
    same = new = changed = errors = unresolved = schemes = 0
    for _k, v in meta.items():
        if not isinstance(v, dict):
            continue
        status = str(v.get("status") or "").upper()
        if status == "UNRESOLVED_AMFI":
            unresolved += 1
            continue
        if status == "ERROR":
            errors += 1
            continue
        schemes += 1
        as_of = str(v.get("as_of") or "")[:10]
        if as_of:
            as_ofs.append(as_of)
        cmp_st = str(v.get("comparison_status") or "").upper()
        if cmp_st == "SAME_PERIOD":
            same += 1
        elif cmp_st in {"NEW_PERIOD", "CHANGED", "DIFF"} or (
            int(v.get("added_count") or 0)
            + int(v.get("exited_count") or 0)
            + int(v.get("changed_count") or 0)
        ) > 0 and cmp_st not in {"SAME_PERIOD", "NO_PRIOR", ""}:
            new += 1
            changed += int(v.get("added_count") or 0)
            changed += int(v.get("exited_count") or 0)
            changed += int(v.get("changed_count") or 0)
        elif cmp_st == "NO_PRIOR":
            pass

    dates = sorted(set(as_ofs))
    latest = dates[-1] if dates else None
    multi = len(dates) > 1
    if not schemes and not unresolved and not errors:
        return {**empty, "reason": "Holdings meta empty"}

    if multi:
        headline = f"Multiple filing periods in cache: {dates[0]} … {dates[-1]}"
        tone = "warn"
    elif latest and same == schemes and schemes > 0:
        headline = f"All {schemes} schemes still on as_of {latest} (SAME_PERIOD) — waiting on next AMC filing"
        tone = "info"
    elif latest and new > 0:
        headline = f"New/changed period detected for {new} scheme(s); latest as_of {latest}"
        tone = "up"
    elif latest:
        headline = f"Holdings as_of {latest} · {schemes} schemes"
        tone = "info"
    else:
        headline = "Holdings as_of unknown"
        tone = "warn"

    return {
        "ok": True,
        "reason": None,
        "as_of_dates": dates,
        "latest_as_of": latest,
        "scheme_count": schemes,
        "same_period": same,
        "new_period": new,
        "changed": changed,
        "errors": errors,
        "unresolved": unresolved,
        "headline": headline,
        "tone": tone,
    }
