import pandas as pd

from lib.company_tape import (
    build_equity_tape,
    fundamentals_from_info,
    metric_tone,
    rsi_wilder,
    sma,
    tape_prompt_lines,
    tape_table_rows,
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
    assert "SMA 200" not in labels
    rsi = next(r["value"] for r in tech["rows"] if r["label"] == "RSI-14")
    assert 70.0 <= rsi <= 100.0


def test_fetch_yahoo_equity_is_the_only_network_seam():
    import inspect
    import lib.company_tape as tape

    src = inspect.getsource(tape)
    assert "yf.Ticker" in inspect.getsource(tape.fetch_yahoo_equity)
    assert src.count("yf.Ticker") == 1
    assert "requests." not in src


def test_metric_tone_rules_are_conservative():
    assert metric_tone("RSI-14", 75) == "elevated"
    assert metric_tone("RSI-14", 20) == "watch"
    assert metric_tone("RSI-14", 50) == "ok"
    assert metric_tone("Profit margin", -1.0) == "elevated"
    assert metric_tone("vs SMA 50", -3.0) == "watch"
    assert metric_tone("Sector", "Industrials") == "neutral"


def test_tape_table_and_prompt_lines():
    rows = [{"label": "Trailing P/E", "value": 13.6, "sub": "Yahoo ratio"}]
    table = tape_table_rows(rows)
    assert table[0]["Metric"] == "Trailing P/E"
    assert table[0]["Flag"] == "neutral"
    tape = {
        "ok": True,
        "name": "Bharat Electronics",
        "ticker": "BEL.NS",
        "fundamentals": {"rows": rows},
        "technicals": {"rows": [{"label": "RSI-14", "value": 72.0, "sub": "Wilder"}]},
        "retrieved_at": "2026-09-22 00:00 UTC",
    }
    lines = tape_prompt_lines(tape)
    assert any("Bharat Electronics" in x for x in lines)
    assert any("RSI-14" in x and "elevated" in x for x in lines)
    assert tape_prompt_lines(None) == []
    assert tape_prompt_lines({"ok": False}) == []
