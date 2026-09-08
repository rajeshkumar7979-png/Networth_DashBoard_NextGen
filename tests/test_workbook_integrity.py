import re

import numpy as np
import pandas as pd

from lib.formatters import safe_float
from tests.conftest import GOLDENS

FD_COLUMNS = [
    "Account Number", "Holder Name", "Deposit Date", "Maturity Date", "Currency",
    "Principal Amount", "Lien Amount", "Available Balance", "Maturity Amount",
    "ROI % p.a.", "Tenor Years", "Tenor Months",
]
MF_COLUMNS = [
    "Owner", "Folio Number", "Fund Name", "ISIN", "Purchase Date", "Units",
    "Purchase NAV", "Invested Amount", "Currency",
]
STOCKS_COLUMNS = [
    "Owner", "Ticker / Symbol", "Company Name", "Exchange", "Purchase Date",
    "Quantity", "Avg Buy Price", "Invested Amount",
]
ISIN_RE = re.compile(r"^IN[A-Z0-9]{9}[0-9]$")


def test_sheet_names(raw_sheets):
    assert set(raw_sheets.keys()) == {"FD", "MF", "Stocks"}


def test_fd_shape(fd_df):
    assert len(fd_df) == GOLDENS["fd_rows"]
    assert list(fd_df.columns) == FD_COLUMNS


def test_fd_currency_counts(fd_df):
    ccy = fd_df["Currency"]
    assert int((ccy == "USD").sum()) == GOLDENS["usd_fd_rows"]
    assert int(ccy.isna().sum()) == GOLDENS["blank_currency_rows"]
    assert int((ccy == "INR").sum()) == GOLDENS["fd_rows"] - GOLDENS["usd_fd_rows"] - GOLDENS["blank_currency_rows"]


def test_fd_data_rows_are_well_formed(fd_df):
    # Rows 0..22 are real deposits; rows 23..32 are blank/subtotal rows the app skips.
    for i in range(0, 23):
        row = fd_df.iloc[i]
        assert row["Holder Name"] and str(row["Holder Name"]).strip().lower() not in ("nan", "nat", "none")
        assert safe_float(row["Principal Amount"]) > 0
        assert pd.notna(row["Deposit Date"]) and pd.notna(row["Maturity Date"])
    for i in range(23, GOLDENS["fd_rows"]):
        assert safe_float(fd_df.iloc[i]["Principal Amount"]) == 0.0


def test_mf_shape(mf_df):
    assert len(mf_df) == GOLDENS["mf_rows"]
    assert list(mf_df.columns) == MF_COLUMNS


def test_mf_rows_well_formed(mf_df):
    assert int((mf_df["Units"] > 0).sum()) == GOLDENS["mf_rows"]
    assert int(mf_df["ISIN"].notna().sum()) == GOLDENS["mf_rows"]
    for isin in mf_df["ISIN"].astype(str):
        assert ISIN_RE.match(isin), f"bad ISIN {isin!r}"


def test_stocks_shape(stocks_df):
    assert len(stocks_df) == GOLDENS["stocks_rows"]
    assert list(stocks_df.columns) == STOCKS_COLUMNS


def test_stocks_rows_well_formed(stocks_df):
    assert int((stocks_df["Quantity"] > 0).sum()) == GOLDENS["stocks_rows"]
    assert set(stocks_df["Exchange"].dropna().unique()) == {"NSE"}
    assert all(str(s).strip() for s in stocks_df["Ticker / Symbol"])


def test_workbook_sums_are_finite(raw_sheets):
    for sheet in raw_sheets.values():
        for col in sheet.columns:
            nums = pd.to_numeric(sheet[col], errors="coerce").dropna()
            if len(nums):
                assert np.isfinite(nums).all(), f"{sheet.name}.{col} has non-finite values"