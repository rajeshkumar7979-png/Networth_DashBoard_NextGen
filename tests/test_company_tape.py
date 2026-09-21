import pandas as pd

from lib.company_tape import (
    build_equity_tape,
    fundamentals_from_info,
    rsi_wilder,
    sma,
    technicals_from_history,
    yahoo_ticker,
)


def test_yahoo_ticker_ns_default_and_keeps_suffix():
    assert yahoo_ticker("BEL", "NSE") == "BEL.NS"
    assert yahoo_ticker("bel", "nse") == "BEL.NS"
    assert yahoo_ticker("BEL.NS") == "BEL.NS"
    assert yahoo_ticker("RELIANCE", "BSE") == "RELIANCE.BO"
    assert yahoo_ticker("") == ""


def test_rsi_wilder_none_on_short_series():
    s = pd.Series([10.0, 11.0, 12.0])
    assert rsi_wilder(s) is None


def test_rsi_wilder_is_bounded_on_a_trend():
    # Strictly rising closes → RSI should sit near the top of 0–100.
    s = pd.Series([float(i) for i in range(1, 40)])
    val = rsi_wilder(s)
    assert val is not None
    assert 70.0 <= val <= 100.0


def test_sma_needs_full_window():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert sma(s, 5) == 3.0
    assert sma(s, 6) is None


def test_fundamentals_skip_missing_never_zero():
    out = fundamentals_from_info({"trailingPE": None, "sector": "Industrials", "profitMargins": 0.12})
    labels = [r["label"] for r in out["rows"]]
    assert "Sector" in labels
    assert "Trailing P/E" not in labels
    margin = next(r for r in out["rows"] if r["label"] == "Profit margin")
    assert abs(margin["value"] - 12.0) < 1e-9


def test_build_tape_ok_false_when_empty():
    tape = build_equity_tape({}, pd.DataFrame(), ticker="BEL.NS")
    assert tape["ok"] is False
    assert tape["fundamentals"]["rows"] == []


def test_technicals_from_synthetic_history():
    idx = pd.date_range("2025-01-01", periods=80, freq="B")
    close = pd.Series(range(80), index=idx, dtype=float) + 100.0
    hist = pd.DataFrame({"Close": close})
    tech = technicals_from_history(hist, {})
    labels = [r["label"] for r in tech["rows"]]
    assert "Last close" in labels
    assert "SMA 20" in labels
    assert "SMA 50" in labels
    assert "RSI-14" in labels
    assert "SMA 200" not in labels  # series too short
    rsi = next(r["value"] for r in tech["rows"] if r["label"] == "RSI-14")
    assert 70.0 <= rsi <= 100.0


def test_fetch_yahoo_equity_is_the_only_network_seam():
    import inspect
    import lib.company_tape as tape

    src = inspect.getsource(tape)
    assert "yf.Ticker" in inspect.getsource(tape.fetch_yahoo_equity)
    assert src.count("yf.Ticker") == 1
    assert "requests." not in src
