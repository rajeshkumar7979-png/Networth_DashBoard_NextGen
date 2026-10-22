import numpy as np
import pandas as pd

def safe_float(val, default=0.0):
    """Coerce workbook numbers; handles Indian grouping like 12,00,000.00."""
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        if isinstance(val, str):
            s = val.strip().replace(",", "").replace("₹", "").replace(" ", "")
            if not s or s in {"-", "—", "NA", "N/A"}:
                return default
            val = s
        v = pd.to_numeric(val, errors="coerce")
        return default if pd.isna(v) else float(v)
    except Exception:
        return default

def format_inr_indian(num, decimals=0):
    if num is None or (isinstance(num, float) and np.isnan(num)):
        return "₹0" if decimals == 0 else "₹0.00"
    try:
        n = float(num)
    except Exception:
        return "₹0"
    sign = "-" if n < 0 else ""
    n = abs(n)
    if decimals <= 0:
        int_part = str(int(round(n)))
        frac = ""
    else:
        s = f"{n:.{decimals}f}"
        int_part, frac = s.split(".")
        frac = "." + frac
    if len(int_part) <= 3:
        grouped = int_part
    else:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        groups = []
        while rest:
            groups.append(rest[-2:])
            rest = rest[:-2]
        grouped = ",".join(reversed(groups)) + "," + last3
    return f"{sign}₹{grouped}{frac}"

def format_inr(num):
    return format_inr_indian(num, decimals=0)

def format_inr_compact(num):
    if num is None or (isinstance(num, float) and np.isnan(num)):
        return "₹0"
    try:
        n = float(num)
    except Exception:
        return "₹0"
    sign = "-" if n < 0 else ""
    a = abs(n)
    if a >= 1e7:
        return f"{sign}₹{a/1e7:.2f} Cr"
    if a >= 1e5:
        return f"{sign}₹{a/1e5:.2f} L"
    return format_inr_indian(n, decimals=0)


def format_identity_value(label, value, currency=None):
    """Format a dossier / identity field for display. Never invents a number.

    Money-ish labels become Indian-grouped rupees; ROI / percent labels keep
    two decimals and a % sign; timestamps become 'DD Mon YYYY'; everything
    else is shown as a trimmed string. Missing/NaN → '—'.

    Native-currency amounts pass ``currency`` ('USD' / 'INR'). USD money is
    rendered as Western-grouped dollars, never as rupees — FCNR principal and
    maturity proceeds stay in the deposit's native unit.
    """
    if value is None:
        return "—"
    if isinstance(value, float) and np.isnan(value):
        return "—"
    try:
        if pd.isna(value):
            return "—"
    except Exception:
        pass

    label_l = str(label or "").lower()
    cur = str(currency or "").strip().upper()

    if hasattr(value, "strftime") and not isinstance(value, str):
        try:
            return value.strftime("%d %b %Y")
        except Exception:
            pass

    # ROI / percent
    if "roi" in label_l or "%" in label_l or "percent" in label_l or "pct" in label_l:
        try:
            return f"{float(value):.2f}%"
        except Exception:
            return str(value).strip() or "—"

    moneyish = any(
        k in label_l
        for k in (
            "principal",
            "amount",
            "value",
            "invested",
            "balance",
            "maturity",
            "booked",
            "current",
            "lien",
            "inr",
            "usd",
            "cost",
            "pnl",
            "p&l",
        )
    )
    if moneyish:
        try:
            n = float(value)
        except Exception:
            return str(value).strip() or "—"
        if cur == "USD":
            return f"{n:,.0f} USD"
        return format_inr_indian(n, decimals=0)

    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return "—"
    return text
