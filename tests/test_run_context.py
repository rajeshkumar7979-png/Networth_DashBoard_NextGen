from datetime import datetime

import pandas as pd
import pytz

from lib.run_context import (
    as_of_timestamp,
    header_valued_at,
    valued_at_iso,
)

IST = pytz.timezone("Asia/Kolkata")


def test_header_without_command_does_not_invent_now():
    assert header_valued_at({}) == "NO VALUATION THIS SESSION"
    assert header_valued_at(None) == "NO VALUATION THIS SESSION"
    assert valued_at_iso({}) is None
    assert as_of_timestamp({}) is None


def test_header_uses_command_valued_at_not_page_open():
    valued = IST.localize(datetime(2026, 9, 21, 8, 15, 0)).isoformat()
    session = {"cc_assets": {"valued_at": valued, "as_of": "2026-09-21"}}
    stamp = header_valued_at(session)
    assert stamp.startswith("VALUED ")
    assert "21 Sep 2026" in stamp
    assert "08:15" in stamp
    assert as_of_timestamp(session) == pd.Timestamp("2026-09-21")
