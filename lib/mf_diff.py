"""Compare two validated scheme snapshots. Weight change is not a trade."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _key(row: Dict[str, Any]) -> Optional[str]:
    isin = str(row.get("isin") or "").strip().upper()
    if isin and isin not in {"-", "NA", "N/A"}:
        return "ISIN:" + isin
    name = "".join(ch for ch in str(row.get("name") or "").upper() if ch.isalnum())
    return "NAME:" + name if name else None


def _index(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = _key(row)
        if key and key not in out:
            out[key] = row
    return out


def _num(value):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n:
        return None
    return n


def diff_snapshots(prior: List[Dict[str, Any]], current: List[Dict[str, Any]], *, prior_ok=True, current_ok=True) -> Dict[str, Any]:
    """Diff two snapshots. Missing quantity is not treated as zero."""
    if not prior_ok or not current_ok:
        return {"status": "NOT_COMPARABLE", "added": [], "exited": [], "changed": []}
    if not prior:
        return {"status": "NO_PRIOR", "added": [], "exited": [], "changed": []}
    old = _index(prior)
    new = _index(current)
    added, exited, changed = [], [], []
    for key, row in new.items():
        if key not in old:
            added.append({"key": key, "name": row.get("name"), "weight_pct": row.get("weight_pct")})
            continue
        prev = old[key]
        item = {"key": key, "name": row.get("name") or prev.get("name")}
        touched = False
        w0, w1 = _num(prev.get("weight_pct")), _num(row.get("weight_pct"))
        if w0 is not None and w1 is not None and abs(w1 - w0) >= 0.05:
            item["weight_from"] = w0
            item["weight_to"] = w1
            item["weight_note"] = "Weight change is not proof of a purchase or sale."
            touched = True
        q0, q1 = _num(prev.get("quantity")), _num(row.get("quantity"))
        if q0 is not None and q1 is not None and q1 != q0:
            item["quantity_from"] = q0
            item["quantity_to"] = q1
            touched = True
        if touched:
            changed.append(item)
    for key, row in old.items():
        if key not in new:
            exited.append({"key": key, "name": row.get("name"), "weight_pct": row.get("weight_pct")})
    return {
        "status": "VALID",
        "added": added,
        "exited": exited,
        "changed": changed,
        "limitation": "Two snapshots do not prove trades. Price, corporate actions, and reporting differences can move weights.",
    }
