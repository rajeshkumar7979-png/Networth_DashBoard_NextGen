"""
Book workbook loader. Supports optional Cash in Hand sheet.
"""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from lib.config import resolve_book_path


def _workbook_from_session_or_upload(uploaded_file=None):
    """Prefer live upload, then durable session bytes, then resolved book path.

    Streamlit UploadedFile handles can go stale after multipage navigation;
    Desk stores raw bytes under cc_uploaded_bytes so Command can always re-open.
    """
    if uploaded_file is not None:
        try:
            data = uploaded_file.getvalue()
            if data:
                st.session_state["cc_uploaded_bytes"] = data
                st.session_state["cc_uploaded_name"] = getattr(uploaded_file, "name", "upload.xlsx")
                st.session_state["book_mode"] = "upload"
                return pd.ExcelFile(io.BytesIO(data))
        except Exception:
            pass
    raw = st.session_state.get("cc_uploaded_bytes")
    if isinstance(raw, (bytes, bytearray)) and raw:
        st.session_state["book_mode"] = "upload"
        return pd.ExcelFile(io.BytesIO(raw))
    path = resolve_book_path()
    try:
        return pd.ExcelFile(path)
    except Exception:
        st.error(f"Could not load book at {path}")
        st.stop()


def load_excel(uploaded_file=None):
    """Return (fd, mf, stocks). Optional cash sheet is stashed in session.

    Cash is normalized later by Command Center via lib.cash_book using
    st.session_state["cc_cash_raw"]. Returning three frames keeps older
    Command Center unpacks working.
    """
    xls = _workbook_from_session_or_upload(uploaded_file)
    sheet_map = {s.lower().strip(): s for s in xls.sheet_names}

    def find_sheet(*names):
        for n in names:
            if n in sheet_map:
                return sheet_map[n]
        return None

    def read_required(*names):
        key = find_sheet(*names)
        if key is None:
            return pd.read_excel(xls, list(xls.sheet_names)[0])
        return pd.read_excel(xls, key)

    def read_optional(*names):
        key = find_sheet(*names)
        if key is None:
            return pd.DataFrame()
        return pd.read_excel(xls, key)

    fd = read_required("fd", "fixed deposits", "fixed_deposits")
    mf = read_required("mf", "mutual funds", "mutual_funds")
    stocks = read_required("stocks", "stock", "equities")
    cash = read_optional(
        "cash in hand",
        "cash",
        "savings",
        "saving bank",
        "bank balance",
        "cash_in_hand",
    )
    try:
        st.session_state["cc_cash_raw"] = cash
    except Exception:
        pass
    return fd, mf, stocks
