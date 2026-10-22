"""Materialize durable workbook — committed sidecar first, then secrets/env.

Priority:
  1. Session upload (portfolio.py)
  2. data/Networth_Raw_Data.xlsx.b64 committed in the repo (simple, survives reboot)
  3. Secrets / env (optional override)
  4. data/Networth_Raw_Data.xlsx plain file if present

To update the book: replace data/Networth_Raw_Data.xlsx.b64 (or the .xlsx)
on GitHub and let Streamlit Cloud redeploy. No Streamlit secrets required.
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
    """Ensure a durable workbook exists on disk.

    Returns (path_or_None, source_label).
    source_label: sidecar | path | b64 | url | none
    Writes st.session_state["book_private_status"] with a human reason.
    """
    status = "no private book configured"
    book = _secrets_book()

    # 0) Committed sidecar data/Networth_Raw_Data.xlsx.b64 (simple durable path)
    sidecar = DATA_DIR / "Networth_Raw_Data.xlsx.b64"
    if sidecar.exists() and sidecar.stat().st_size > 500:
        try:
            b64 = "".join(sidecar.read_text(encoding="utf-8").split())
            data = base64.b64decode(b64, validate=False)
            if len(data) > 500 and data[:2] == b"PK":  # xlsx zip magic
                PRIVATE_BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
                PRIVATE_BOOK_PATH.write_bytes(data)
                _set_status(f"committed sidecar ok · {len(data)} bytes")
                return PRIVATE_BOOK_PATH, "sidecar"
            status = f"sidecar present but invalid ({len(data)} bytes)"
        except Exception as exc:
            status = f"sidecar decode failed: {type(exc).__name__}"

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

    # 2) Base64 payload from secrets/env
    b64 = (os.environ.get("NORTHLINE_BOOK_B64") or "").strip()
    if not b64 and book is not None and hasattr(book, "get"):
        b64 = str(book.get("xlsx_b64") or book.get("content_b64") or "").strip()
    if b64:
        try:
            if "," in b64 and b64.lower().startswith("data:"):
                b64 = b64.split(",", 1)[1]
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
        status = "no sidecar and no [book] secrets"

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
