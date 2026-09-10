# -------------------------------------------------
# lib/roster — canonical family asset roster for drill-down surfaces.
#
# Pure. Reuses lib.register for canonical keys and class assignment — it never
# re-values and never re-implements book semantics. The roster is the full list
# a user can drill into; lookup_roster is exact-identifier matching only
# (lib.intelligence.sources.mapping rule: never infer identity by fuzzy match).
#
# If two members hold the same instrument (e.g. a Symbol held by two Owners),
# both roster rows are returned — positions are never merged, ever.
# -------------------------------------------------
from __future__ import annotations

import pandas as pd

from lib.register import canonical_instrument_key, assign_asset_class
from lib.formatters import safe_float


def _s(row, column):
    value = row.get(column)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _name_of(row, kind):
    if kind == "MF":
        return _s(row, "Fund Name") or _s(row, "ISIN")
    if kind == "Stocks":
        return _s(row, "Company Name") or _s(row, "Symbol")
    return _s(row, "Symbol")


def _member_of(row, kind):
    if kind == "FD":
        return _s(row, "Holder Name")
    return _s(row, "Owner")


def _current_of(row, kind):
    if kind == "FD":
        return safe_float(row.get("Current Value (INR)"))
    return safe_float(row.get("Current Value"))


def _invested_of(row, kind):
    if kind == "FD":
        return safe_float(row.get("Principal (INR, at deposit FX)"))
    return safe_float(row.get("Invested"))


def _match_terms(row, kind, key, name):
    terms = {_s(row, "Symbol").upper(), key.upper(), name.upper()}
    if kind == "MF":
        terms.add(_s(row, "ISIN").upper())
    elif kind == "FD":
        terms.add(_s(row, "Account Number").upper())
    for word in name.upper().replace("-", " ").split():
        if len(word) >= 3:
            terms.add(word)
    return sorted(t for t in terms if t)


def build_roster(mf_valid=None, stocks_valid=None, gold_valid=None, fd_valid=None):
    """Build the drill-down roster DataFrame from the validated Command Center
    books. Rows mirror the register: one row per book holding.

    The caller must pass the already-routed books (mf / stocks / gold / fd),
    exactly as they are handed to lib.register.build_asset_register — this
    module never re-routes gold or re-classifies funds."""
    rows = []
    for name, book in (("mf", mf_valid), ("stocks", stocks_valid),
                       ("gold", gold_valid), ("fd", fd_valid)):
        if book is None or book.empty:
            continue
        for _, row in book.iterrows():
            record = row.to_dict()
            kind = {"mf": "MF", "stocks": "Stocks", "gold": "Gold", "fd": "FD"}[name]
            key = canonical_instrument_key(kind, record)
            if not key:
                continue
            current = _current_of(record, kind)
            invested = _invested_of(record, kind)
            if current is None or not pd.notna(current):
                continue
            invested = invested if (invested is not None and pd.notna(invested)) else 0.0
            name_ = _name_of(record, kind)
            pnl = current - invested
            pct = (pnl / invested * 100.0) if invested else None
            rows.append({
                "Key": key,
                "Name": name_,
                "Kind": kind,
                "Class": assign_asset_class(kind, record),
                "Member": _member_of(record, kind),
                "Current Value": float(current),
                "Invested": float(invested),
                "P&L": float(pnl),
                "Return %": pct,
                "Match Terms": _match_terms(record, kind, key, name_),
            })
    if not rows:
        return pd.DataFrame(columns=["Key", "Name", "Kind", "Class", "Member",
                                     "Current Value", "Invested", "P&L", "Return %",
                                     "Match Terms"])
    return pd.DataFrame(rows)


def lookup_roster(roster, token):
    """Exact-identifier lookup over Key / Match Terms. No fuzzy matching.

    Returns a new DataFrame with the matching row(s). A symbol held by multiple
    members returns all those rows; empty when there is no exact hit."""
    if roster is None or len(roster) == 0 or not token:
        return roster.iloc[0:0] if roster is not None else None
    query = str(token).strip().upper()
    if not query:
        return roster.iloc[0:0]
    mask = (
        roster["Key"].astype(str).str.upper().eq(query)
        | roster["Match Terms"].apply(lambda terms: query in set(terms))
    )
    return roster[mask]


def instrument_summary(row):
    """Human summary for a roster row — used by dossier rendering. Pure."""
    pct = row.get("Return %")
    return {
        "Key": row.get("Key"),
        "Name": row.get("Name"),
        "Kind": row.get("Kind"),
        "Class": row.get("Class"),
        "Member": row.get("Member"),
        "Current Value": row.get("Current Value"),
        "Invested": row.get("Invested"),
        "P&L": row.get("P&L"),
        "Return %": f"{pct:.2f}%" if pct is not None else "n/a",
    }