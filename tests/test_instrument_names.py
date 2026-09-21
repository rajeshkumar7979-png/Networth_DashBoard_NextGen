# Display names: ISIN-shaped "Company Name" must never be the roster label.
from lib.instrument_names import (
    clean_disclosed_name,
    equity_display_name,
    extract_isin,
    looks_like_isin,
)
from lib.roster import build_roster
import pandas as pd


def test_looks_like_isin_accepts_nse_equity_and_rejects_tickers():
    assert looks_like_isin("INE040A01034")
    assert looks_like_isin("ine031a01017")
    assert not looks_like_isin("HDFCBANK")
    assert not looks_like_isin("HUDCO")
    assert not looks_like_isin("")


def test_extract_isin_picks_first_real_isin():
    assert extract_isin("HUDCO", "INE031A01017") == "INE031A01017"
    assert extract_isin("HDFCBANK") == ""


def test_clean_disclosed_name_strips_filing_junk():
    assert clean_disclosed_name("HDFC Bank Ltd.£") == "HDFC Bank Ltd."
    assert clean_disclosed_name("HDFC Bank Limited (13/11/2026) #") == "HDFC Bank Limited"
    assert clean_disclosed_name("INE040A01034") == ""


def test_equity_display_name_prefers_book_name_then_cache_then_ticker():
    names = {"INE040A01034": "HDFC Bank Ltd."}
    assert equity_display_name("HDFC Bank", "HDFCBANK", "INE040A01034", names=names) == "HDFC Bank"
    assert equity_display_name("INE040A01034", "HDFCBANK", "", names=names) == "HDFC Bank Ltd."
    assert equity_display_name("INE031A01017", "HUDCO", "", names={}) == "HUDCO"


def test_roster_stock_name_is_not_the_isin_from_company_column():
    stocks = pd.DataFrame([{
        "Owner": "Mrs. KAVITA KHANDELWAL",
        "Symbol": "HUDCO",
        "Company Name": "INE031A01017",
        "Invested": 1000.0,
        "Current Value": 1100.0,
    }])
    roster = build_roster(stocks_valid=stocks)
    assert len(roster) == 1
    assert roster.iloc[0]["Name"] != "INE031A01017"
    assert roster.iloc[0]["Name"] in {"HUDCO", "Housing & Urban Development Corporation Ltd."}
    assert "INE031A01017" in set(roster.iloc[0]["Match Terms"])
