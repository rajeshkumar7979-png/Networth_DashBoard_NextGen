# -------------------------------------------------
# Phase 1B - enriched ledger snapshots.
# Pure module (path-based) so tests exercise history.csv round-trips without
# touching data/. Read by column name; legacy 6-column rows stay legacy and are
# never back-filled. The base columns keep their historical names/types; enriched
# columns are additive on top ("schema 1b").
#
# Persistence semantics: historical rows are append-only/immutable; today's row
# is upserted (same-date replace). This module never rewrites older dates.
# -------------------------------------------------
import hashlib
import re
from pathlib import Path

import pandas as pd

from lib.drivers import class_slug
from lib.register import ASSET_CLASSES

BASE_COLS = ["date", "net_worth", "equity_pct", "fd_pct", "pnl", "health_score"]

SCHEMA = "1b"


def _slugify(name):
    s = re.sub(r"[^0-9a-z]+", "_", str(name).lower()).strip("_")
    return s or "member"


def _member_slug_map(names):
    """Map each distinct member name to a collision-safe column slug.

    Readable slugs are preserved for non-colliding names (backward compatible
    with existing history). When two distinct members lower-case/collapse to the
    same slug, a deterministic short hash of the raw name is appended to keep the
    columns unique. Never silently overwrites one member's snapshot data.
    """
    names = [n for n in names if n is not None]
    base = {n: _slugify(n) for n in names}
    counts = {}
    for slug in base.values():
        counts[slug] = counts.get(slug, 0) + 1
    out = {}
    for n in names:
        slug = base[n]
        if counts[slug] == 1:
            out[n] = slug
        else:
            digest = hashlib.sha1(str(n).encode("utf-8")).hexdigest()[:8]
            out[n] = f"{slug}_{digest}"
    return out


def build_snapshot_row(*, date, net_worth, equity_pct, fd_pct, pnl, health_score,
                       total_invested=None, usd_inr=None, amfi_cache_date=None,
                       snapshot_ts=None, fcnr_interest_total=None,
                       fcnr_fx_principal_total=None, inr_fd_interest_total=None,
                       drivers_recon_ok=None, class_current=None, class_invested=None,
                       member_current=None, member_invested=None):
    """Build an enriched snapshot row dict (base columns first, then additive
    enriched columns). None values are omitted so legacy consumers keep working."""
    row = {
        "date": str(date),
        "net_worth": float(net_worth),
        "equity_pct": float(equity_pct),
        "fd_pct": float(fd_pct),
        "pnl": float(pnl),
        "health_score": round(float(health_score), 1),
        "schema": SCHEMA,
    }
    scalars = {
        "total_invested": (total_invested, float),
        "usd_inr": (usd_inr, float),
        "amfi_cache_date": (amfi_cache_date, str),
        "snapshot_ts": (snapshot_ts, str),
        "fcnr_interest_total": (fcnr_interest_total, float),
        "fcnr_fx_principal_total": (fcnr_fx_principal_total, float),
        "inr_fd_interest_total": (inr_fd_interest_total, float),
        "drivers_recon_ok": (drivers_recon_ok, bool),
    }
    for key, (val, cast) in scalars.items():
        if val is not None:
            row[key] = cast(val)

    if class_current or class_invested:
        for cls in ASSET_CLASSES:
            slug = class_slug(cls)
            if class_current and cls in class_current and class_current[cls] is not None:
                row[f"class_current_{slug}"] = float(class_current[cls])
            if class_invested and cls in class_invested and class_invested[cls] is not None:
                row[f"class_invested_{slug}"] = float(class_invested[cls])

    member_keys = None
    if member_current or member_invested:
        _all = list(member_current or {}) + list(member_invested or {})
        member_keys = _member_slug_map(_all)

    if member_current:
        for member, val in member_current.items():
            if val is not None:
                row[f"member_current_{member_keys[member]}"] = float(val)
    if member_invested:
        for member, val in member_invested.items():
            if val is not None:
                row[f"member_invested_{member_keys[member]}"] = float(val)
    return row


def clean(df):
    """Base-column coercion + date filtering + sort + keep-last-per-date.
    Enriched/additive columns pass through by name, never positionally."""
    if df is None or df.empty:
        return pd.DataFrame(columns=BASE_COLS)
    df = df.copy()
    df["date"] = df["date"].astype(str)
    df = df[df["date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]
    for col in BASE_COLS[1:]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["net_worth"])
    return df.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)


def load_history(path):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=BASE_COLS)
    try:
        return clean(pd.read_csv(path))
    except Exception:
        return pd.DataFrame(columns=BASE_COLS)


def upsert_snapshot(row, path):
    """Persist today's row. Historical rows are append-only/immutable; the row for
    today's date is upserted (same-date replace). Older dates are never rewritten."""
    path = Path(path)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    hist = load_history(path)
    hist = hist[hist["date"] != str(row["date"])]
    hist = pd.concat([hist, pd.DataFrame([row])], ignore_index=True)
    hist = clean(hist)
    hist.to_csv(path, index=False)
    return hist


def merge_uploaded(incoming_df, path):
    """Merge an uploaded history CSV (needs at least date + net_worth) with the
    stored one, keep-last-per-date, and write back."""
    if "date" not in incoming_df.columns or "net_worth" not in incoming_df.columns:
        raise ValueError("CSV must have at least date and net_worth columns.")
    path = Path(path)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_history(path)
    merged = clean(pd.concat([existing, incoming_df], ignore_index=True))
    merged.to_csv(path, index=False)
    return merged