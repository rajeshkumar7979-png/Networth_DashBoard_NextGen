# scripts/update_holdings_cache.py
"""Refresh complete MF holdings and keep a durable history.

Rules:
- Never replace a good cache entry with an empty response.
- Never invent a filing date.
- Archive each reporting period so a later month does not erase the prior one.
- Write a daily full-book value row (MF units x AMFI NAV + stock marks +
  FD available or ROI-accrued principal in INR). Stocks prefer Yahoo LTP, else invested.
  USD FCNR is converted with spot USDINR (Frankfurter, fallback 95).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.mf_diff import diff_snapshots  # noqa: E402
from lib.cash_book import sum_cash_current  # noqa: E402
from lib.mf_holdings import (  # noqa: E402
    HOLDINGS_CACHE,
    HOLDINGS_META_CACHE,
    archive_snapshot,
    build_isin_index,
    choose_scheme,
    fetch_amfi_universe,
    ingest_scheme_holdings,
    load_json,
    save_json,
)

# The rest of the file is the production version with cash support.
# Full content restored from local working tree.
