import pytest

from tests.conftest import GOLDENS


@pytest.mark.parametrize("sheet,column,expected", [
    ("FD", "Principal Amount", GOLDENS["fd_inr_principal"] + GOLDENS["fd_usd_principal"]),
    ("MF", "Invested Amount", GOLDENS["mf_invested"]),
    ("Stocks", "Invested Amount", GOLDENS["stocks_invested"]),
])
def test_sheet_total_invested(raw_sheets, sheet, column, expected):
    actual = float(raw_sheets[sheet][column].sum())
    assert actual == pytest.approx(expected, abs=0.01)


def test_fd_usd_principal_total(fd_df):
    usd = float(fd_df.loc[fd_df["Currency"] == "USD", "Principal Amount"].sum())
    assert usd == pytest.approx(GOLDENS["fd_usd_principal"], abs=0.01)


def test_fd_inr_and_blank_principal_total(fd_df):
    total = float(fd_df["Principal Amount"].sum())
    usd = float(fd_df.loc[fd_df["Currency"] == "USD", "Principal Amount"].sum())
    assert (total - usd) == pytest.approx(GOLDENS["fd_inr_principal"], abs=0.01)


def test_mf_invested_total(mf_df):
    assert float(mf_df["Invested Amount"].sum()) == pytest.approx(GOLDENS["mf_invested"], abs=0.01)


def test_stocks_invested_total(stocks_df):
    assert float(stocks_df["Invested Amount"].sum()) == pytest.approx(GOLDENS["stocks_invested"], abs=0.01)