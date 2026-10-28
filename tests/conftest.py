from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
# Golden tests MUST use the public sample workbook, never the family book.
# The committed family Networth_Raw_Data.xlsx changes with real holdings and
# would break row-count / principal goldens on every cash or FD update.
SAMPLE_XLSX = ROOT / "data" / "_test_sample_book.xlsx"
SAMPLE_CSV_DIR = ROOT / "data" / "sample_book"

GOLDENS = {
    "fd_rows": 23,
    "usd_fd_rows": 14,
    "blank_currency_rows": 0,
    "fd_usd_principal": 109132.34,
    "fd_inr_principal": 3562870.00,
    "mf_rows": 25,
    "mf_invested": 7168423.41,
    "stocks_rows": 36,
    "stocks_invested": 1458796.97,
    "gold_stock_symbols": ["SGBSEP31II-GB", "SGBMR29XII-GB", "GOLDBEES"],
}


def _ensure_test_sample() -> Path:
    """Build a stable sample xlsx from data/sample_book CSVs for CI goldens."""
    if SAMPLE_XLSX.exists() and SAMPLE_XLSX.stat().st_size > 2000:
        return SAMPLE_XLSX
    SAMPLE_XLSX.parent.mkdir(parents=True, exist_ok=True)
    fd = pd.read_csv(SAMPLE_CSV_DIR / "fd.csv")
    mf = pd.read_csv(SAMPLE_CSV_DIR / "mf.csv")
    stocks = pd.read_csv(SAMPLE_CSV_DIR / "stocks.csv")
    with pd.ExcelWriter(SAMPLE_XLSX, engine="openpyxl") as writer:
        fd.to_excel(writer, sheet_name="FD", index=False)
        mf.to_excel(writer, sheet_name="MF", index=False)
        stocks.to_excel(writer, sheet_name="Stocks", index=False)
    return SAMPLE_XLSX


WORKBOOK_PATH = _ensure_test_sample()


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
