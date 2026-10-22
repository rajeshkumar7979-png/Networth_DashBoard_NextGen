"""Materialize durable workbook from the repo — no secrets required.

Priority:
  1. Session upload (portfolio.py) — temporary
  2. data/Networth_Raw_Data.xlsx committed in the repo (preferred)
  3. data/Networth_Raw_Data.xlsx.b64 committed sidecar
  4. Secrets / env (optional)

Workflow when investments or cash change:
  Edit the Excel → upload/replace data/Networth_Raw_Data.xlsx on GitHub → Cloud redeploys.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Optional, Tuple

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PRIVATE_BOOK_PATH = DATA_DIR / ".private_book.xlsx"
COMMITTED_XLSX = DATA_DIR / "Networth_Raw_Data.xlsx"
COMMITTED_B64 = DATA_DIR / "Networth_Raw_Data.xlsx.b64"


def _secrets_book():
    try:
        import streamlit as st
        if not hasattr(st, "secrets"):
            return None
        return st.secrets.get("book")
    except Exception:
        return None


def materialize_private_book() -> Tuple[Optional[Path], str]:
    """Return durable workbook path when available.

    source_label: committed | sidecar | path | b64 | url | none
    """
    status = "using fallback sample"
    book = _secrets_book()

    # 0) Committed plain Excel in data/ (the simple GitHub path you asked for)
    # Prefer files that look complete (with Cash sheet typically >20 KB).
    if COMMITTED_XLSX.exists() and COMMITTED_XLSX.stat().st_size > 20000:
        _set_status(f"committed xlsx ok · {COMMITTED_XLSX.stat().st_size} bytes")
        return COMMITTED_XLSX, "committed"

    # 1) Committed sidecar .b64 (text-safe alternative)
    if COMMITTED_B64.exists() and COMMITTED_B64.stat().st_size > 500:
        try:
            b64 = "".join(COMMITTED_B64.read_text(encoding="utf-8").split())
            data = base64.b64decode(b64, validate=False)
            if len(data) > 500 and data[:2] == b"PK":
                PRIVATE_BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
                PRIVATE_BOOK_PATH.write_bytes(data)
                _set_status(f"committed sidecar ok · {len(data)} bytes")
                return PRIVATE_BOOK_PATH, "sidecar"
            status = f"sidecar present but invalid ({len(data)} bytes)"
        except Exception as exc:
            status = f"sidecar decode failed: {type(exc).__name__}"

    # 2) Explicit path (env / secrets)
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

    # 3) Secrets/env base64
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
                _set_status(f"b64 ok · {len(data)} bytes")
                return PRIVATE_BOOK_PATH, "b64"
            status = f"xlsx_b64 too small ({len(data)} bytes)"
        except Exception as exc:
            status = f"xlsx_b64 decode failed: {type(exc).__name__}"

    # 4) URL
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
                _set_status(f"url ok · {len(data)} bytes")
                return PRIVATE_BOOK_PATH, "url"
            status = f"url too little data ({len(data)} bytes)"
        except Exception as exc:
            status = f"url fetch failed: {type(exc).__name__}"

    # Small committed sample still present → report size so UI is honest
    if COMMITTED_XLSX.exists():
        status = f"committed xlsx is sample-sized ({COMMITTED_XLSX.stat().st_size} bytes) — replace with full book"

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
