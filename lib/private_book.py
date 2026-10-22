"""Materialize a durable private workbook from Streamlit secrets / env.

Priority for the live book (highest first):
  1. Session upload bytes (cc_uploaded_bytes) — handled in portfolio.py
  2. Secrets / env materialized private file
  3. Committed sample data/Networth_Raw_Data.xlsx

Streamlit secrets (Cloud → Settings → Secrets):

  [book]
  # Preferred: full Excel as base64 (survives every reboot)
  xlsx_b64 = "UEsDBBQAAAAI..."

  # Or a Cloud-reachable path / private URL
  # path = "/mount/private_Networth_Raw_Data.xlsx"
  # url  = "https://..."

Env alternatives: NORTHLINE_BOOK_PATH, NORTHLINE_BOOK_B64, NORTHLINE_BOOK_URL.

Never commit a real family workbook to the public repo.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Optional, Tuple

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PRIVATE_BOOK_PATH = DATA_DIR / ".private_book.xlsx"


def _secrets_book():
    try:
        import streamlit as st
        if not hasattr(st, "secrets"):
            return None
        book = st.secrets.get("book")
        if book is None:
            return None
        return book
    except Exception:
        return None


def materialize_private_book() -> Tuple[Optional[Path], str]:
    """Ensure a durable private workbook exists on disk when configured.

    Returns (path_or_None, source_label).
    source_label: path | b64 | url | none
    Also writes st.session_state["book_private_status"] with a human reason.
    """
    status = "no private book configured"
    book = _secrets_book()

    # 1) Explicit path (env first, then secrets)
    for raw in (
        (os.environ.get("NORTHLINE_BOOK_PATH") or "").strip(),
        (str(book.get("path") or "").strip() if book is not None and hasattr(book, "get") else ""),
    ):
        if not raw:
            continue
        p = Path(raw)
        if p.exists() and p.stat().st_size > 100:
            _set_status(f"path ok · {p} · {p.stat().st_size} bytes")
            return p, "path"
        status = f"path set but not readable on Cloud: {raw}"

    # 2) Base64 payload
    b64 = (os.environ.get("NORTHLINE_BOOK_B64") or "").strip()
    if not b64 and book is not None and hasattr(book, "get"):
        b64 = str(book.get("xlsx_b64") or book.get("content_b64") or "").strip()
    if b64:
        try:
            if "," in b64 and b64.lower().startswith("data:"):
                b64 = b64.split(",", 1)[1]
            # strip whitespace/newlines that secrets UI sometimes injects
            b64 = "".join(b64.split())
            data = base64.b64decode(b64, validate=False)
            if len(data) > 500:
                PRIVATE_BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
                PRIVATE_BOOK_PATH.write_bytes(data)
                _set_status(f"b64 ok · materialized {len(data)} bytes")
                return PRIVATE_BOOK_PATH, "b64"
            status = f"xlsx_b64 present but decoded size too small ({len(data)} bytes)"
        except Exception as exc:
            status = f"xlsx_b64 present but decode failed: {type(exc).__name__}"

    # 3) Remote URL
    url = (os.environ.get("NORTHLINE_BOOK_URL") or "").strip()
    if not url and book is not None and hasattr(book, "get"):
        url = str(book.get("url") or "").strip()
    if url:
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=45) as resp:
                data = resp.read()
            if len(data) > 500:
                PRIVATE_BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
                PRIVATE_BOOK_PATH.write_bytes(data)
                _set_status(f"url ok · fetched {len(data)} bytes")
                return PRIVATE_BOOK_PATH, "url"
            status = f"url returned too little data ({len(data)} bytes)"
        except Exception as exc:
            status = f"url fetch failed: {type(exc).__name__}"

    if book is None and not any(
        (os.environ.get(k) or "").strip()
        for k in ("NORTHLINE_BOOK_PATH", "NORTHLINE_BOOK_B64", "NORTHLINE_BOOK_URL")
    ):
        status = "no [book] section in secrets and no NORTHLINE_BOOK_* env"

    _set_status(status)
    return None, "none"


def _set_status(msg: str) -> None:
    try:
        import streamlit as st
        st.session_state["book_private_status"] = msg
    except Exception:
        pass


def private_book_status() -> str:
    try:
        import streamlit as st
        return str(st.session_state.get("book_private_status") or "")
    except Exception:
        return ""
