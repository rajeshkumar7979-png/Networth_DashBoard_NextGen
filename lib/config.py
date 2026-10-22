from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytz

IST = pytz.timezone("Asia/Kolkata")
NOW_IST = datetime.now(IST)
TODAY_STR = NOW_IST.strftime("%Y-%m-%d")

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
HISTORY_PATH = DATA_DIR / "history.csv"
AMFI_CACHE_PATH = DATA_DIR / "amfi_nav_cache.json"
SAMPLE_BOOK_DIR = DATA_DIR / "sample_book"
EXCEL_PATH = DATA_DIR / "Networth_Raw_Data.xlsx"


def resolve_book_path() -> Path:
    """Private durable book first, then committed public sample.

    Streamlit secrets (any one of):
        [book]
        path = "/mount/private_Networth_Raw_Data.xlsx"
        xlsx_b64 = "<base64 of xlsx>"
        url = "https://..."

    Env: NORTHLINE_BOOK_PATH, NORTHLINE_BOOK_B64, NORTHLINE_BOOK_URL.
    """
    try:
        from lib.private_book import materialize_private_book
        private, _src = materialize_private_book()
        if private is not None:
            return private
    except Exception:
        pass

    candidates = []
    env_path = (os.environ.get("NORTHLINE_BOOK_PATH") or "").strip()
    if env_path:
        candidates.append(Path(env_path))
    try:
        import streamlit as st
        book = st.secrets.get("book") if hasattr(st, "secrets") else None
        if book is not None and hasattr(book, "get"):
            secret_path = str(book.get("path") or "").strip()
            if secret_path:
                candidates.append(Path(secret_path))
    except Exception:
        pass
    candidates.append(EXCEL_PATH)
    for path in candidates:
        if path and path.exists():
            return path
    return EXCEL_PATH
