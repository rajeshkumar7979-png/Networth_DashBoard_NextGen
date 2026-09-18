# -------------------------------------------------
# lib.formatters — display-only helpers. Never invent a number; missing stays —.
# -------------------------------------------------
from datetime import datetime

import pandas as pd

from lib.formatters import format_identity_value, format_inr_indian


def test_identity_missing_is_em_dash():
    assert format_identity_value("Principal (native)", None) == "—"
    assert format_identity_value("ROI % p.a.", float("nan")) == "—"
    assert format_identity_value("Holder", "") == "—"
    assert format_identity_value("Holder", "nan") == "—"


def test_identity_roi_is_percent_not_rupees():
    assert format_identity_value("ROI % p.a.", 6.6) == "6.60%"
    assert format_identity_value("ROI %", 0) == "0.00%"


def test_identity_inr_money_uses_indian_grouping():
    assert format_identity_value("Booked value (INR)", 52931) == format_inr_indian(52931)
    assert "₹" in format_identity_value("Principal (native)", 50000, currency="INR")


def test_identity_usd_native_is_never_rupees():
    rendered = format_identity_value("Principal (native)", 25000, currency="USD")
    assert rendered == "25,000 USD"
    assert "₹" not in rendered
    proceeds = format_identity_value("Maturity proceeds (native)", 26100.4, currency="USD")
    assert proceeds.endswith("USD")
    assert "₹" not in proceeds


def test_identity_dates_are_human():
    assert format_identity_value("Maturity Date", "2027-01-16") == "16 Jan 2027"
    assert format_identity_value("Maturity Date", datetime(2028, 12, 21)) == "21 Dec 2028"
    assert format_identity_value("Maturity Date", pd.Timestamp("2027-01-16")) == "16 Jan 2027"


def test_identity_passthrough_strings():
    assert format_identity_value("Holder", "Mrs. KAVITA KHANDELWAL") == "Mrs. KAVITA KHANDELWAL"
    assert format_identity_value("Account Number", "ABC123") == "ABC123"
