import pytest

from lib.gold import is_gold_fund, is_gold_symbol
from tests.conftest import GOLDENS


def test_workbook_gold_symbols_rout_out_of_stocks(stocks_df):
    symbols = [str(s).strip().upper() for s in stocks_df["Ticker / Symbol"].astype(str)]
    gold = [s for s in symbols if is_gold_symbol(s)]
    assert set(gold) == set(GOLDENS["gold_stock_symbols"])
    assert len(gold) == 3
    non_gold = [s for s in symbols if s not in gold]
    assert len(non_gold) == GOLDENS["stocks_rows"] - 3
    assert not any(is_gold_symbol(s) for s in non_gold)


def test_workbook_gold_fofs_routed_out_of_mf(mf_df):
    names = [str(n).strip() for n in mf_df["Fund Name"].astype(str) if str(n).strip()]
    gold_funds = [n for n in names if is_gold_fund(n)]
    assert set(gold_funds) == {"HDFC Gold ETF Fund of Fund", "ICICI Prudential Gold ETF FoF Growth"}
    assert not any(is_gold_fund(n) for n in names if n not in gold_funds)


def test_gold_non_leak_invariant(stocks_df, mf_df):
    # A gold instrument may never appear in the Stocks or MF book.
    stocks_gold = {s for s in stocks_df["Ticker / Symbol"].astype(str) if is_gold_symbol(s)}
    mf_gold = {n for n in mf_df["Fund Name"].astype(str) if is_gold_fund(n)}
    assert stocks_gold == set(GOLDENS["gold_stock_symbols"])
    assert mf_gold == {"HDFC Gold ETF Fund of Fund", "ICICI Prudential Gold ETF FoF Growth"}


@pytest.mark.parametrize("symbol,expected", [
    ("SGBSEP31II-GB", True),
    ("SGBMR29XII-GB", True),
    ("sgbsep31ii-gb", True),
    ("GOLDBEES", True),
    ("HDFCGOLD", True),  # ends with "GOLD" -> classified gold by current rules
    ("SBIN", False),
    ("RELIANCE", False),
    ("", False),
    (None, False),
])
def test_is_gold_symbol_classifier(symbol, expected):
    assert is_gold_symbol(symbol) is expected


@pytest.mark.parametrize("name,expected", [
    ("HDFC Gold Fund", False),  # current regex requires gold+{etf|fof|fund of fund}
    ("HDFC Gold ETF Fund of Fund", True),
    ("ICICI Prudential Gold ETF FoF", True),
    ("HDFC Liquid Fund", False),
    ("Kotak Hybrid Equity Fund", False),
    ("", False),
    (None, False),
])
def test_is_gold_fund_classifier(name, expected):
    assert is_gold_fund(name) is expected