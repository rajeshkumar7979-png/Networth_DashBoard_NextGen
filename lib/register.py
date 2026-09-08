# -------------------------------------------------
# Phase 1A — family asset register.
# Pure aggregation over the four validated books produced by Command Center.
# No external data, no network, no streamlit, no re-valuation.
# The register never changes book values: it is a canonical ledger view that
# reconciles to the existing Command Center totals within the ₹1 tolerance.
#
# Taxonomy (matches Command Center slices):
#   Equity         = stocks (non-gold) + non-DEBT_LIKE mutual funds
#   Liquid         = DEBT_LIKE mutual funds
#   FCNR (USD)     = USD fixed deposits
#   INR FD         = INR / blank-currency fixed deposits
#   Gold           = SGB + gold ETFs (Stocks sheet) + gold FoFs (MF sheet)
# No-data classes are flagged, never summed as assets.
# -------------------------------------------------
import pandas as pd

from lib.gold import DEBT_LIKE

ASSET_CLASSES = ["Equity", "Liquid", "FCNR (USD)", "INR FD", "Gold"]
NO_DATA_CLASSES = ["Retirement", "Real Estate", "Savings/Cash", "Liabilities"]
DATA_BACKED_CLASSES = list(ASSET_CLASSES)

# Pages / tests that consume register rows should use these column names.
REGISTER_COLUMNS = ["Member", "Asset Class", "Instrument", "Current Value", "Invested", "Source", "Key"]

_BAD_ACCOUNT = {"", "nan", "none", "nat", "-"}


class NonUniqueKeyError(Exception):
    """Two distinct FD records mapped to the same canonical instrument key.

    The Command Center routes identical fingerprints through its own dedup, so a
    collision reaching the register means two genuinely distinct records would
    silently collapse into one. We STOP with an explicit data-quality error
    rather than merging, disambiguating, or inventing a key.
    """


def _safe_str(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _normalize_account(value):
    acct = _safe_str(value)
    return "" if acct.lower() in _BAD_ACCOUNT else acct


def _to_number(value):
    num = pd.to_numeric(value, errors="coerce")
    return None if num is None or pd.isna(num) else float(num)


def assign_asset_class(kind, row):
    """Return the canonical asset class for a book row.

    kind is one of "MF" / "Stocks" / "Gold" / "FD".
    Mirrors the Command Center slice definitions so register totals equal the
    existing class totals (Equity/Liquid/FCNR/INR FD/Gold) within ₹1.
    """
    if kind == "MF":
        category = _safe_str(row.get("Category"))
        return "Liquid" if category in DEBT_LIKE else "Equity"
    if kind == "Stocks":
        return "Equity"
    if kind == "Gold":
        return "Gold"
    if kind == "FD":
        product = _safe_str(row.get("Product"))
        if product == "FCNR":
            return "FCNR (USD)"
        if product:
            return "INR FD"
        currency = _safe_str(row.get("Currency")).upper()
        return "FCNR (USD)" if currency == "USD" else "INR FD"
    raise ValueError(f"unknown book kind: {kind!r}")


def _fd_fingerprint(row):
    holder = _safe_str(row.get("Holder Name"))
    currency = _safe_str(row.get("Currency")).upper()
    product = _safe_str(row.get("Product")) or ("FCNR" if currency == "USD" else "INR FD")
    principal = _to_number(row.get("Principal (Native)"))
    roi = _to_number(row.get("ROI %"))
    maturity = _safe_str(row.get("Maturity Date"))
    principal_s = f"{principal:.2f}" if principal is not None else "NA"
    roi_s = f"{roi:.4f}" if roi is not None else "NA"
    return f"{holder}|{currency}|{product}|{principal_s}|{roi_s}|{maturity}"


def canonical_instrument_key(kind, row):
    """Return the canonical instrument key for a register row.

    FD accounts are canonical keys; a fingerprint fallback is used only for
    missing Account Number and only if it is unique (see build_asset_register,
    which raises NonUniqueKeyError instead of collapsing two distinct records).
    """
    if kind == "MF":
        return _safe_str(row.get("ISIN"))
    if kind in ("Stocks", "Gold"):
        return _safe_str(row.get("Symbol"))
    if kind == "FD":
        acct = _normalize_account(row.get("Account Number"))
        if acct:
            return f"acct:{acct}"
        return f"fp:{_fd_fingerprint(row)}"
    raise ValueError(f"unknown book kind: {kind!r}")


def _fd_record(row):
    key = canonical_instrument_key("FD", row)
    member = _safe_str(row.get("Holder Name"))
    current = _to_number(row.get("Current Value (INR)"))
    invested = _to_number(row.get("Principal (INR, at deposit FX)"))
    return {
        "Member": member,
        "Asset Class": assign_asset_class("FD", row),
        "Instrument": key,
        "Current Value": current,
        "Invested": invested,
        "Source": "FD",
        "Key": key,
    }


def _book_rows(records):
    rows = []
    for rec in records:
        current = rec.get("Current Value")
        if current is None or not pd.notna(current):
            continue
        rec["Current Value"] = float(current)
        if rec.get("Invested") is None or not pd.notna(rec.get("Invested")):
            rec["Invested"] = 0.0
        else:
            rec["Invested"] = float(rec["Invested"])
        rows.append(rec)
    return rows


def build_asset_register(mf_valid, stocks_valid, gold_valid, fd_valid):
    """Build the family asset register from the four validated Command Center books.

    One row per validated book holding (MF rows are already Owner+ISIN
    aggregated by Command Center; gold is already Owner+Symbol aggregated).
    FD rows are keyed by Account Number unless missing, in which case a unique
    fingerprint is required — a collision raises NonUniqueKeyError.
    """
    records = []

    if mf_valid is not None and not mf_valid.empty:
        for _, row in mf_valid.iterrows():
            records.append({
                "Member": _safe_str(row.get("Owner")),
                "Asset Class": assign_asset_class("MF", row),
                "Instrument": canonical_instrument_key("MF", row),
                "Current Value": _to_number(row.get("Current Value")),
                "Invested": _to_number(row.get("Invested")),
                "Source": "MF",
                "Key": canonical_instrument_key("MF", row),
            })

    if stocks_valid is not None and not stocks_valid.empty:
        for _, row in stocks_valid.iterrows():
            records.append({
                "Member": _safe_str(row.get("Owner")),
                "Asset Class": assign_asset_class("Stocks", row),
                "Instrument": canonical_instrument_key("Stocks", row),
                "Current Value": _to_number(row.get("Current Value")),
                "Invested": _to_number(row.get("Invested")),
                "Source": "Stocks",
                "Key": canonical_instrument_key("Stocks", row),
            })

    if gold_valid is not None and not gold_valid.empty:
        for _, row in gold_valid.iterrows():
            records.append({
                "Member": _safe_str(row.get("Owner")),
                "Asset Class": assign_asset_class("Gold", row),
                "Instrument": canonical_instrument_key("Gold", row),
                "Current Value": _to_number(row.get("Current Value")),
                "Invested": _to_number(row.get("Invested")),
                "Source": "Gold",
                "Key": canonical_instrument_key("Gold", row),
            })

    if fd_valid is not None and not fd_valid.empty:
        seen_fd_keys = {}
        for _, row in fd_valid.iterrows():
            rec = _fd_record(row)
            key = rec["Key"]
            if key in seen_fd_keys:
                raise NonUniqueKeyError(
                    "Two distinct FD records map to the same instrument key "
                    f"{key!r}. Records: {seen_fd_keys[key]!r} and {rec['Member']!r} "
                    f"(principal={rec['Invested']!r}, account={_safe_str(row.get('Account Number'))!r}). "
                    "Refusing to merge or invent a key — fix the source data (e.g. missing Account Number)."
                )
            seen_fd_keys[key] = rec["Member"]
            records.append(rec)

    register = pd.DataFrame(_book_rows(records), columns=REGISTER_COLUMNS)
    return register


def aggregate_by_class(register):
    """Per-class current/invested totals, including flagged no-data classes.

    No-data classes (Retirement, Real Estate, Savings/Cash, Liabilities) are
    present with Data Backed = False and never receive a numeric asset value;
    they are never summed into assets (see family_level_sum).
    """
    if register is None or len(register) == 0:
        rows = [{"Asset Class": c, "Current Value": None, "Invested": None, "Data Backed": False}
                for c in ASSET_CLASSES + NO_DATA_CLASSES]
        return pd.DataFrame(rows, columns=["Asset Class", "Current Value", "Invested", "Data Backed"])

    data = register.groupby("Asset Class", as_index=False)[["Current Value", "Invested"]].sum()
    data["Data Backed"] = data["Asset Class"].isin(DATA_BACKED_CLASSES)
    data = data[~data["Asset Class"].isin(NO_DATA_CLASSES)]

    out = []
    for cls in ASSET_CLASSES + NO_DATA_CLASSES:
        match = data[data["Asset Class"] == cls]
        if cls in DATA_BACKED_CLASSES and not match.empty:
            out.append({"Asset Class": cls, "Current Value": float(match["Current Value"].iloc[0]),
                        "Invested": float(match["Invested"].iloc[0]), "Data Backed": True})
        elif cls in DATA_BACKED_CLASSES:
            out.append({"Asset Class": cls, "Current Value": 0.0, "Invested": 0.0, "Data Backed": True})
        else:
            out.append({"Asset Class": cls, "Current Value": None, "Invested": None, "Data Backed": False})
    return pd.DataFrame(out, columns=["Asset Class", "Current Value", "Invested", "Data Backed"])


def aggregate_by_member(register):
    """Per-member (raw Owner/Holder string) current/invested totals, descending."""
    if register is None or len(register) == 0:
        return pd.DataFrame(columns=["Member", "Current Value", "Invested"])
    return (
        register.groupby("Member", as_index=False)[["Current Value", "Invested"]]
        .sum()
        .sort_values("Current Value", ascending=False)
        .reset_index(drop=True)
    )


def family_level_sum(register):
    """Family-level totals over the data-backed register.

    Only data-backed classes count as assets; no-data classes are never summed.
    Returns total_assets (current), total_invested, and by_class / by_member
    summaries.
    """
    if register is None or len(register) == 0:
        return {
            "total_assets": 0.0,
            "total_invested": 0.0,
            "by_class": {},
            "by_member": {},
        }
    by_class = aggregate_by_class(register)
    class_dict = {
        r["Asset Class"]: {"current": r["Current Value"], "invested": r["Invested"]}
        for _, r in by_class.iterrows()
        if r["Data Backed"]
    }
    total_assets = sum(
        float(v["current"]) for v in class_dict.values()
        if v.get("current") is not None and pd.notna(v.get("current"))
    )
    by_member = aggregate_by_member(register)
    member_dict = {
        r["Member"]: {"current": r["Current Value"], "invested": r["Invested"]}
        for _, r in by_member.iterrows()
    }
    total_invested = 0.0
    for v in class_dict.values():
        inv = v.get("invested")
        if inv is not None and pd.notna(inv):
            total_invested += float(inv)
    return {
        "total_assets": total_assets,
        "total_invested": total_invested,
        "by_class": class_dict,
        "by_member": member_dict,
    }