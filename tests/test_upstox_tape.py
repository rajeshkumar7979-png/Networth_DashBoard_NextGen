from lib.upstox_tape import instrument_key, tape_from_payloads


def test_upstox_tape_uses_quote_and_ratios_without_network():
    assert instrument_key("INE092T01019") == "NSE_EQ|INE092T01019"
    tape = tape_from_payloads(
        "INE092T01019",
        quote={"data": {"NSE_EQ:IDFCFIRSTB": {"symbol": "IDFCFIRSTB", "last_price": 80.5, "ohlc": {"close": 79.0}}}},
        ratios={"data": [{"name": "P/E", "company_value": "18.2", "sector_value": "14.1"}, {"name": "ROE", "company_value": "12%", "sector_value": "10%"}]},
        candles={"data": {"candles": [["2026-10-01", 1, 2, 0.5, 70 + i, 1, 0] for i in range(30)]}},
    )
    labels = [r["label"] for r in tape["fundamentals"]["rows"]]
    assert tape["ok"] is True
    assert "Last price" in labels
    assert "Trailing P/E" in labels
    assert "ROE" in labels
    assert tape["source"] == "Upstox Analytics token"
