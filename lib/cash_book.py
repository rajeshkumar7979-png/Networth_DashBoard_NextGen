"""Cash in Hand / savings book helpers."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import pandas as pd

from lib.formatters import safe_float


def build_cash_book(cash_raw) -> pd.DataFrame:
    """Normalize optional Cash in Hand sheet to Owner/Account/Current Value rows."""
    rows = []
    if cash_raw is None or getattr(cash_raw, "empty", True):
        return pd.DataFrame(columns=["Account", "Owner", "Current Value", "Invested", "ROI %", "Currency"])
    for _, row in cash_raw.iterrows():
        try:
            acct = str(
                row.get("Saving Bank Balance")
                or row.get("Account Number")
                or row.get("Account")
                or ""
            ).strip()
            holder = str(row.get("Name") or row.get("Holder Name") or row.get("Owner") or "").strip()
            amount = safe_float(row.get("Amount") or row.get("Balance") or row.get("Available Balance"))
            roi = safe_float(row.get("Rate of Interest") or row.get("ROI % p.a."), default=0.0)
            if amount is None or amount <= 0:
                continue
            if not acct and not holder:
                continue
            rows.append({
                "Account": acct,
                "Owner": holder,
                "Current Value": float(amount),
                "Invested": float(amount),
                "ROI %": float(roi or 0.0),
                "Currency": "INR",
            })
        except Exception:
            continue
    return pd.DataFrame(rows)


def cash_total(cash_df) -> float:
    if cash_df is None or getattr(cash_df, "empty", True):
        return 0.0
    if "Current Value" not in cash_df.columns:
        return 0.0
    return float(pd.to_numeric(cash_df["Current Value"], errors="coerce").fillna(0).sum())


def sum_cash_current(sheets: Optional[Dict[str, Any]] = None) -> Tuple[float, int]:
    """For the daily history job: sum Cash in Hand face value from workbook sheets."""
    if not sheets:
        return 0.0, 0
    key = None
    for name in ("cash in hand", "cash", "savings", "saving bank", "bank balance", "cash_in_hand"):
        if name in sheets and isinstance(sheets[name], pd.DataFrame) and not sheets[name].empty:
            key = name
            break
    if key is None:
        return 0.0, 0
    book = build_cash_book(sheets[key])
    return float(cash_total(book)), int(len(book))
