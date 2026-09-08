from pathlib import Path

import pandas as pd
import pytest

WORKBOOK_PATH = Path(__file__).resolve().parents[1] / "data" / "Networth_Raw_Data.xlsx"

GOLDENS = {
    "fd_rows": 33,
    "usd_fd_rows": 14,
    "blank_currency_rows": 10,
    "fd_usd_principal": 109132.34,
    "fd_inr_principal": 3562870.00,
    "mf_rows": 26,
    "mf_invested": 7388311.90,
    "stocks_rows": 36,
    "stocks_invested": 1435113.80,
    "gold_stock_symbols": ["SGBSEP31II-GB", "SGBMR29XII-GB", "GOLDBEES"],
}


@pytest.fixture(scope="session")
def workbook_path():
    assert WORKBOOK_PATH.exists(), f"Sample workbook missing: {WORKBOOK_PATH}"
    return WORKBOOK_PATH


@pytest.fixture(scope="session")
def raw_sheets(workbook_path):
    return pd.read_excel(workbook_path, sheet_name=None)


@pytest.fixture(scope="session")
def fd_df(raw_sheets):
    return raw_sheets["FD"]


@pytest.fixture(scope="session")
def mf_df(raw_sheets):
    return raw_sheets["MF"]


@pytest.fixture(scope="session")
def stocks_df(raw_sheets):
    return raw_sheets["Stocks"]