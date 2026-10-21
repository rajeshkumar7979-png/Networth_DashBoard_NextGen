"""MF holdings period status table for production transparency."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from lib.config import DATA_DIR

META_PATH = DATA_DIR / "mf_holdings_meta.json"


def scheme_period_table(meta_path: Path | None = None) -> pd.DataFrame:
    """One row per scheme: as_of, comparison, holding_count, source."""
    path = meta_path or META_PATH
    if not path.exists():
        return pd.DataFrame()
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return pd.DataFrame()
    if not isinstance(meta, dict):
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for code, v in meta.items():
        if not isinstance(v, dict):
            continue
        rows.append({
            "Scheme": str(code),
            "Name": str(v.get("fund_name") or v.get("amfi_scheme_name") or "")[:40],
            "as_of": str(v.get("as_of") or "")[:10],
            "Status": str(v.get("comparison_status") or v.get("status") or ""),
            "Holdings": v.get("holding_count"),
            "Source": str(v.get("source") or ""),
            "+": int(v.get("added_count") or 0),
            "-": int(v.get("exited_count") or 0),
            "~": int(v.get("changed_count") or 0),
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df.sort_values(["as_of", "Scheme"], ascending=[False, True]).reset_index(drop=True)
