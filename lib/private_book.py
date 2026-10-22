"""Materialize a durable private workbook from Streamlit secrets / env.

Priority for the live book (highest first):
  1. Session upload bytes (cc_uploaded_bytes) — handled in portfolio.py
  2. Secrets / env materialized private file
  3. Committed sample data/Networth_Raw_Data.xlsx

Streamlit secrets examples:

  [book]
  path = "/mount/private_Networth_Raw_Data.xlsx"

  [book]
  # Excel file base64-encoded (no newlines required). Survives Cloud reboot.
  xlsx_b64 = "UEsDB..."

  [book]
  url = "https://example.com/private/Networth_Raw_Data.xlsx"

Env:
  NORTHLINE_BOOK_PATH=/path/to/file.xlsx
  NORTHLINE_BOOK_B64=...
  NORTHLINE_BOOK_URL=...
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Optional, Tuple

from lib.config import DATA_DIR, EXCEL_PATH

PRIVATE_BOOK_PATH = DATA_DIR / ".private_book.xlsx"


def _secrets_book():
    try:
        import streamlit as st
        book = st.secrets.get("book") if hasattr(st, "secrets") else None
        if book is None:
            return None
        return book
    except Exception:
        return None


def materialize_private_book() -> Tuple[Optional[Path], str]:
    """Ensure a durable private workbook exists on disk when configured.

    Returns (path_or_None, source_label).
    source_label: path | b64 | url | none
    """
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
            return p, "path"

    # 2) Base64 payload
    b64 = (os.environ.get("NORTHLINE_BOOK_B64") or "").strip()
    if not b64 and book is not None and hasattr(book, "get"):
        b64 = str(book.get("xlsx_b64") or book.get("content_b64") or "").strip()
    if b64:
        try:
            if "," in b64 and b64.lower().startswith("data:"):
                b64 = b64.split(",", 1)[1]
            data = base64.b64decode(b64, validate=False)
            if len(data) > 100:
                PRIVATE_BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
                PRIVATE_BOOK_PATH.write_bytes(data)
                return PRIVATE_BOOK_PATH, "b64"
        except Exception:
            pass

    # 3) Remote URL (private link you control)
    url = (os.environ.get("NORTHLINE_BOOK_URL") or "").strip()
    if not url and book is not None and hasattr(book, "get"):
        url = str(book.get("url") or "").strip()
    if url.startswith("http"):
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "NorthlineBook/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            if len(data) > 100:
                PRIVATE_BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
                PRIVATE_BOOK_PATH.write_bytes(data)
                return PRIVATE_BOOK_PATH, "url"
        except Exception:
            pass

    if PRIVATE_BOOK_PATH.exists() and PRIVATE_BOOK_PATH.stat().st_size > 100:
        return PRIVATE_BOOK_PATH, "cached"

    return None, "none"


def resolve_book_path_with_private() -> Tuple[Path, str]:
    """Path + mode label for UI: private | sample."""
    private, src = materialize_private_book()
    if private is not None:
        return private, f"private:{src}"
    return EXCEL_PATH, "sample"
