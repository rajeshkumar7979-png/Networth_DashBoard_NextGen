#!/usr/bin/env python3
"""Daily self-audit for Northline Family Desk.

Runs once per day (GitHub Actions). Detects production issues, applies only
*safe* auto-fixes, and appends a timestamped log under data/audit/.

Safe fixes only:
  - Ensure audit log directory exists
  - Normalize Indian-comma / quoted numeric cells in committed workbook (in place)
  - Ensure portfolio_history.csv has cash_current_inr column header if file exists
  - Never replace critical .py modules with stubs
  - Never invent NAVs, holdings, or history rows

Exit codes:
  0 = clean or only auto-fixed warnings
  1 = residual issues that need human / holdings job attention
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

AUDIT_DIR = ROOT / "data" / "audit"
LATEST_JSON = AUDIT_DIR / "latest.json"
LATEST_MD = AUDIT_DIR / "latest.md"
HISTORY_LOG = AUDIT_DIR / "audit_history.jsonl"

CRITICAL = {
    "lib/mf_holdings.py": 15_000,
    "scripts/update_holdings_cache.py": 12_000,
    "pages/5_MF_Health.py": 8_000,
    "pages/1_Command_Center.py": 1_500,
    "lib/overlap.py": 3_000,
    "lib/history.py": 4_000,
}

LOADER_MARKERS = (
    "_load_github_body",
    "Command Center loader",
    "cc_parts",
    "Command_Center_loaded",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class Audit:
    def __init__(self) -> None:
        self.ts = now_iso()
        self.issues: List[Dict[str, Any]] = []
        self.fixes: List[Dict[str, Any]] = []

    def issue(self, severity: str, code: str, message: str, **extra: Any) -> None:
        row = {"severity": severity, "code": code, "message": message, "at": self.ts}
        row.update(extra)
        self.issues.append(row)

    def fix(self, code: str, message: str, **extra: Any) -> None:
        row = {"code": code, "message": message, "at": self.ts, "fixed": True}
        row.update(extra)
        self.fixes.append(row)

    def summary(self) -> Dict[str, Any]:
        crit = sum(1 for i in self.issues if i["severity"] == "critical")
        warn = sum(1 for i in self.issues if i["severity"] == "warning")
        info = sum(1 for i in self.issues if i["severity"] == "info")
        return {
            "run_at": self.ts,
            "date": today(),
            "counts": {
                "critical": crit,
                "warning": warn,
                "info": info,
                "fixes": len(self.fixes),
            },
            "issues": self.issues,
            "fixes": self.fixes,
            "healthy": crit == 0,
        }


def check_critical_files(audit: Audit) -> None:
    for rel, min_size in CRITICAL.items():
        path = ROOT / rel
        if not path.exists():
            audit.issue("critical", "MISSING_FILE", f"Missing {rel}")
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        size = len(raw.encode("utf-8"))
        effective = min_size
        if rel.endswith("1_Command_Center.py") and any(m in raw for m in LOADER_MARKERS):
            effective = 1_500
        if size < effective:
            audit.issue(
                "critical",
                "TOO_SMALL",
                f"{rel} is {size} bytes (need >= {effective}) — possible truncation; do NOT auto-stub",
                path=rel,
                size=size,
                min_size=effective,
            )
        for marker in ("SEE ARTIFACT", "SEE_ARTIFACT", "PLACEHOLDER_WILL_FAIL_CI"):
            if marker in raw and size < 2000:
                audit.issue(
                    "critical",
                    "PLACEHOLDER",
                    f"{rel} contains placeholder marker with tiny size",
                    path=rel,
                )


def check_workbook(audit: Audit) -> None:
    xlsx = ROOT / "data" / "Networth_Raw_Data.xlsx"
    if not xlsx.exists():
        audit.issue("critical", "NO_BOOK", "data/Networth_Raw_Data.xlsx missing")
        return
    size = xlsx.stat().st_size
    if size < 5_000:
        audit.issue("warning", "BOOK_TINY", f"Workbook only {size} bytes — may be sample without Cash")
    elif size > 20_000:
        audit.issue("info", "BOOK_COMMITTED", f"Committed-size book present ({size} bytes)")
    try:
        import pandas as pd

        xl = pd.ExcelFile(xlsx)
        sheets = {str(s): pd.read_excel(xl, s) for s in xl.sheet_names}
        names = list(sheets)
        if not any("cash" in n.lower() for n in names):
            audit.issue("warning", "NO_CASH_SHEET", f"No Cash sheet in {names}")
        else:
            audit.issue("info", "CASH_SHEET_OK", "Cash sheet present")

        fixed_cells = 0
        if any(k.lower().startswith("fd") or "deposit" in k.lower() for k in names):
            for sname, df in sheets.items():
                if not any(k in sname.lower() for k in ("fd", "deposit", "fcnr")):
                    continue
                changed = False
                for col in df.columns:
                    if df[col].dtype == object:
                        new_vals = []
                        for v in df[col]:
                            if isinstance(v, str) and ("," in v or (v.startswith("'") and v.endswith("'"))):
                                cleaned = v.strip().strip("'\"").replace(",", "")
                                try:
                                    num = float(cleaned)
                                    new_vals.append(num)
                                    fixed_cells += 1
                                    changed = True
                                except ValueError:
                                    new_vals.append(v)
                            else:
                                new_vals.append(v)
                        if changed:
                            df[col] = new_vals
                sheets[sname] = df
        if fixed_cells:
            with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
                for sname, df in sheets.items():
                    df.to_excel(writer, sheet_name=sname[:31], index=False)
            audit.fix(
                "NORMALIZE_INDIAN_COMMAS",
                f"Normalized {fixed_cells} numeric cell(s) in workbook (Indian commas / quotes)",
                cells=fixed_cells,
            )
            audit.issue(
                "warning",
                "HAD_INDIAN_COMMAS",
                f"Found and fixed {fixed_cells} non-plain numeric cell(s) in FD/book",
            )
    except Exception as exc:
        audit.issue("warning", "BOOK_READ_FAIL", f"Could not inspect workbook: {exc}")


def check_history(audit: Audit) -> None:
    path = ROOT / "data" / "portfolio_history.csv"
    if not path.exists():
        audit.issue("warning", "NO_HISTORY", "data/portfolio_history.csv missing")
        return
    try:
        import pandas as pd

        df = pd.read_csv(path)
        if df.empty:
            audit.issue("warning", "HISTORY_EMPTY", "portfolio_history.csv has no rows")
            return
        if "date" not in df.columns:
            audit.issue("critical", "HISTORY_BAD_SCHEMA", "portfolio_history.csv missing date column")
            return
        last = str(df["date"].iloc[-1])
        audit.issue("info", "HISTORY_LAST", f"Last history row date={last} rows={len(df)}")
        try:
            last_d = datetime.strptime(last[:10], "%Y-%m-%d").date()
            age = (datetime.now(timezone.utc).date() - last_d).days
            if age > 2:
                audit.issue(
                    "warning",
                    "HISTORY_STALE",
                    f"History last row is {age} day(s) old ({last}) — holdings job may be failing",
                    age_days=age,
                )
        except ValueError:
            pass
        if "cash_current_inr" not in df.columns:
            df["cash_current_inr"] = ""
            df.to_csv(path, index=False)
            audit.fix(
                "HISTORY_CASH_COLUMN",
                "Added cash_current_inr column header to portfolio_history.csv (values filled by next holdings job)",
            )
            audit.issue(
                "info",
                "HISTORY_CASH_COL_ADDED",
                "cash_current_inr column was missing; header added",
            )
    except Exception as exc:
        audit.issue("warning", "HISTORY_READ_FAIL", str(exc))


def check_holdings_cache(audit: Audit) -> None:
    cache_p = ROOT / "data" / "mf_holdings_cache.json"
    meta_p = ROOT / "data" / "mf_holdings_meta.json"
    amfi_p = ROOT / "data" / "amfi_nav_cache.json"
    if not cache_p.exists():
        audit.issue("warning", "NO_HOLDINGS_CACHE", "mf_holdings_cache.json missing")
    else:
        try:
            data = json.loads(cache_p.read_text(encoding="utf-8"))
            n = len([k for k in data if str(k).isdigit()]) if isinstance(data, dict) else 0
            if n == 0:
                audit.issue("warning", "HOLDINGS_EMPTY", "Holdings cache has no fund entries")
            else:
                audit.issue("info", "HOLDINGS_COUNT", f"Holdings cache has {n} fund key(s)")
        except Exception as exc:
            audit.issue("warning", "HOLDINGS_PARSE", str(exc))
    if meta_p.exists():
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            asofs = sorted(
                {
                    str(v.get("as_of") or "")
                    for v in (meta.values() if isinstance(meta, dict) else [])
                    if isinstance(v, dict) and v.get("as_of")
                }
            )
            if asofs:
                audit.issue("info", "HOLDINGS_ASOF", f"Holdings as_of values: {asofs[-3:]}")
        except Exception:
            pass
    if amfi_p.exists():
        try:
            amfi = json.loads(amfi_p.read_text(encoding="utf-8"))
            saved = (amfi or {}).get("saved_at") if isinstance(amfi, dict) else None
            if saved:
                audit.issue("info", "AMFI_SAVED", f"AMFI cache saved_at={saved}")
                m = re.match(r"(\d{4}-\d{2}-\d{2})", str(saved))
                if m:
                    d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
                    age = (datetime.now(timezone.utc).date() - d).days
                    if age > 7:
                        audit.issue(
                            "warning",
                            "AMFI_STALE",
                            f"AMFI disk cache is {age} day(s) old — Cloud may still live-fetch",
                            age_days=age,
                        )
        except Exception:
            pass


def check_workflow_safety(audit: Audit) -> None:
    wf = ROOT / ".github" / "workflows" / "update-holdings.yml"
    if not wf.exists():
        audit.issue("warning", "NO_HOLDINGS_WORKFLOW", "update-holdings.yml missing")
        return
    text = wf.read_text(encoding="utf-8", errors="replace")
    if "Keeping committed book" not in text and "st_size > 20000" not in text:
        audit.issue(
            "warning",
            "WORKFLOW_OVERWRITE_RISK",
            "Holdings workflow may rebuild sample over a committed full book — protect >20KB books",
        )
    else:
        audit.issue("info", "WORKFLOW_BOOK_GUARD", "Holdings workflow has committed-book size guard")


def run_critical_guard(audit: Audit) -> None:
    script = ROOT / "scripts" / "check_critical_files.py"
    if not script.exists():
        return
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            audit.issue(
                "critical",
                "GUARD_FAIL",
                "check_critical_files.py failed",
                stdout=(proc.stdout or "")[-500],
                stderr=(proc.stderr or "")[-300],
            )
        else:
            audit.issue("info", "GUARD_OK", "check_critical_files.py passed")
    except Exception as exc:
        audit.issue("warning", "GUARD_ERROR", str(exc))


def write_logs(audit: Audit) -> Dict[str, Any]:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    summary = audit.summary()
    LATEST_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        f"# Northline daily self-audit — {summary['run_at']}",
        "",
        f"- Critical: **{summary['counts']['critical']}**",
        f"- Warning: **{summary['counts']['warning']}**",
        f"- Info: **{summary['counts']['info']}**",
        f"- Auto-fixes: **{summary['counts']['fixes']}**",
        f"- Healthy: **{summary['healthy']}**",
        "",
        "## Issues",
    ]
    if not summary["issues"]:
        lines.append("- None")
    for i in summary["issues"]:
        lines.append(f"- `{i['severity']}` **{i['code']}**: {i['message']}")
    lines.append("")
    lines.append("## Fixes applied")
    if not summary["fixes"]:
        lines.append("- None this run")
    for f in summary["fixes"]:
        lines.append(f"- `{f['at']}` **{f['code']}**: {f['message']}")
    lines.append("")
    LATEST_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with HISTORY_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
    return summary


def main() -> int:
    audit = Audit()
    print(f"=== Northline daily self-audit {audit.ts} ===")
    try:
        check_critical_files(audit)
        check_workbook(audit)
        check_history(audit)
        check_holdings_cache(audit)
        check_workflow_safety(audit)
        run_critical_guard(audit)
    except Exception:
        audit.issue("critical", "AUDIT_CRASH", traceback.format_exc()[-500])
    summary = write_logs(audit)
    print(json.dumps(summary["counts"], indent=2))
    for i in summary["issues"]:
        print(f"  [{i['severity']}] {i['code']}: {i['message']}")
    for f in summary["fixes"]:
        print(f"  [fix] {f['code']}: {f['message']}")
    print(f"Wrote {LATEST_JSON} and {LATEST_MD}")
    return 0 if summary["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
