from lib.book_session import build_published_frames
import pandas as pd


def test_published_frames_use_cache_nav_and_scheme_code():
    mf = pd.DataFrame([{
        "Owner": "A",
        "Fund Name": "DSP Nifty Next 50",
        "ISIN": "INF740K01GX9",
        "Units": 10,
        "Invested Amount": 1000,
        "Purchase Date": "2024-01-01",
        "Currency": "INR",
    }])
    stocks = pd.DataFrame([{
        "Owner": "A",
        "Ticker / Symbol": "ALANKIT",
        "Company Name": "INE914E01040",
        "Exchange": "NSE",
        "Quantity": 2,
        "Avg Buy Price": 10,
        "Invested Amount": 20,
    }])
    fd = pd.DataFrame([{
        "Account Number": "ABC1",
        "Holder Name": "A",
        "Currency": "INR",
        "Principal Amount": 50,
        "Available Balance": 40,
        "Maturity Date": "2027-01-01",
    }])
    published = build_published_frames(
        fd, mf, stocks,
        amfi_navs={"INF740K01GX9": 12.5},
        amfi_codes={"INF740K01GX9": "119551"},
        saved_at="2026-08-20 08:02",
    )
    holding = published["holdings"][0]
    assert holding["Scheme Code"] == 119551
    assert holding["Current Value"] == 125.0
    assert holding["1Y %"] is None
    assert published["stocks"].iloc[0]["Symbol"] == "ALANKIT"
    assert published["stocks"].iloc[0]["Current Value"] == 20
    assert published["fd"].iloc[0]["Current Value (INR)"] == 40
    assert published["assets"]["source"] == "workbook+amfi-cache"
    assert published["assets"]["as_of"] == "2026-08-20 08:02"
