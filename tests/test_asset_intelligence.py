from lib.asset_intelligence import build_asset_pack
from lib.company_tape import build_equity_tape


def test_stock_pack_flags_tape_and_concentration_without_network():
    info = {
        "sector": "Financial Services",
        "industry": "Credit Services",
        "marketCap": 5e11,
        "trailingPE": 22.0,
        "forwardPE": 18.0,
        "priceToBook": 4.0,
        "trailingEps": 20.0,
        "profitMargins": 0.22,
        "returnOnEquity": 0.18,
        "debtToEquity": 80.0,
        "beta": 1.1,
        "dividendYield": 0.01,
        "currentPrice": 100.0,
        "fiftyTwoWeekHigh": 120.0,
        "fiftyTwoWeekLow": 80.0,
        "longName": "Bajaj Finance Ltd",
    }
    tape = build_equity_tape(info=info, hist=None, ticker="BAJFINANCE.NS", retrieved_at="2026-09-29")
    pack = build_asset_pack(
        row={"Kind": "Stocks", "Name": "Bajaj Finance", "Member": "A", "Key": "BAJFINANCE",
             "Current Value": 50000, "Invested": 40000, "P&L": 10000},
        rec={"Symbol": "BAJFINANCE", "ISIN": "INE296A01024", "Current Value": 50000, "Invested": 40000},
        assets={"total_assets": 1000000, "as_of": "2026-09-29"},
        tape=tape, session_holdings=[], live_cohort=None, research_brief=None,
    )
    labels = {p["Parameter"] for p in pack.parameters}
    assert "Trailing P/E" in labels
    assert "Weight of family assets" in labels
    assert pack.tape_ok is True
    assert any(f.label == "Concentration" for f in pack.green)
    blob = " ".join(f.text for f in pack.green + pack.red + pack.watch)
    assert "XIRR" not in blob
    assert pack.brief is not None
    assert pack.brief.evidence_count >= 1


def test_stock_pack_without_tape_records_gap():
    pack = build_asset_pack(
        row={"Kind": "Stocks", "Name": "ALANKIT", "Member": "A", "Key": "ALANKIT",
             "Current Value": 200000, "Invested": 100000},
        rec={"Symbol": "ALANKIT", "ISIN": "INE914E01040", "Current Value": 200000},
        assets={"total_assets": 1000000}, tape=None,
    )
    assert pack.tape_ok is False
    assert any(f.label == "Company tape" for f in pack.gaps)
    assert any(f.label == "Concentration" and f.tone == "red" for f in pack.red)


def test_mf_pack_uses_row_performance_not_holdings_summary_only():
    pack = build_asset_pack(
        row={"Kind": "MF", "Name": "DSP Nifty Next 50 Index Fund", "Member": "A",
             "Key": "INF740K01QI4", "Class": "Index", "Current Value": 80000},
        rec={"Fund Name": "DSP Nifty Next 50 Index Fund", "ISIN": "INF740K01QI4",
             "Category": "Index", "1Y %": 12.0, "3Y %": 18.0, "5Y %": 15.0,
             "vs Nifty50 1Y": -1.5, "Current Value": 80000, "Invested": 70000},
        assets={"total_assets": 2000000}, session_holdings=[],
    )
    params = {p["Parameter"]: p["Value"] for p in pack.parameters}
    assert params.get("1Y %") == 12.0
    assert any(f.label == "vs Nifty 1Y" for f in pack.watch)
    assert any(f.label == "Look-through" for f in pack.gaps)
    assert pack.brief is not None
