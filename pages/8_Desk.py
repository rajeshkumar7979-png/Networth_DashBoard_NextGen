"""Desk — operator controls and session transparency."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from lib.formatters import format_inr_compact
from lib.history import render_portfolio_history
from lib.theme import inject_css
from lib.ui import (
    empty_state as ui_empty,
    kpi_cards as ui_kpi_cards,
    nav_shell as ui_nav,
    page_header_html as ui_page_header,
    section_header_html as ui_section,
)
from lib.drivers import LIFETIME_PNL_CAPTION, NOT_A_CASHFLOW_LABEL, PERIOD_DELTA_CAPTION

inject_css()
ui_nav("desk")
st.markdown(
    ui_page_header(
        "Northline · Family desk",
        "Operator desk",
        "Upload workbook, then open Command Center to recompute. Numbers come from Command session.",
    ),
    unsafe_allow_html=True,
)

_books = st.session_state.get("cc_books") or {}
_assets = st.session_state.get("cc_assets") or {}

_controls_exp = st.expander("Run controls & exports", expanded=True)
with _controls_exp:
    st.markdown("### Controls")
    _mode = st.session_state.get("book_mode") or "unknown"
    _priv = st.session_state.get("book_private_status") or ""
    if _mode == "committed" or str(_mode).startswith("private"):
        st.success(
            f"Durable book active ({_mode}). "
            f"{_priv or ''} "
            "Edit `data/Networth_Raw_Data.xlsx` on GitHub when holdings change — no re-upload needed after reboot."
        )
    elif _mode == "upload":
        st.info("Using a session upload (temporary until reboot).")
    else:
        st.caption(f"Book mode: {_mode}. Prefer committing the Excel to data/Networth_Raw_Data.xlsx on GitHub.")
    st.file_uploader(
        "Upload Excel (optional override — lost on reboot)",
        type=["xlsx", "xls"],
        key="cc_uploaded_file",
        help="Optional. Permanent book = data/Networth_Raw_Data.xlsx on GitHub.",
    )
    _up = st.session_state.get("cc_uploaded_file")
    if _up is not None:
        try:
            _bytes = _up.getvalue()
            if _bytes:
                st.session_state["cc_uploaded_bytes"] = _bytes
                st.session_state["cc_uploaded_name"] = getattr(_up, "name", "upload.xlsx")
                st.session_state["book_mode"] = "upload"
                st.success(
                    f"Loaded {st.session_state['cc_uploaded_name']} ({len(_bytes):,} bytes). "
                    "Open Command Center now to recompute (includes Cash in Hand if present)."
                )
        except Exception as _exc:
            st.warning(f"Upload could not be buffered: {_exc}")
    elif st.session_state.get("cc_uploaded_bytes"):
        st.info(
            f"Session still holds uploaded book: {st.session_state.get('cc_uploaded_name') or 'workbook'}. "
            "Open Command Center to recompute."
        )
    if st.button("Force Recalculate", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()
    st.toggle(
        "Log today's snapshot to history",
        value=bool(st.session_state.get("cc_log_snapshot", True)),
        key="cc_log_snapshot",
    )
    st.toggle(
        "Auto refresh every 5 minutes",
        value=bool(st.session_state.get("cc_auto_refresh", True)),
        key="cc_auto_refresh",
    )
    st.markdown("---")
    st.markdown("### History")
    if st.button("Reset history file", use_container_width=True):
        st.session_state["cc_reset_history"] = True
    st.file_uploader(
        "Restore history CSV",
        type=["csv"],
        key="cc_hist_upload",
        help="Merge history on next Command Center run.",
    )
    st.markdown("---")
    st.markdown("### Books")
    st.number_input(
        "Liabilities (session-only, ₹)",
        min_value=0.0,
        value=float(st.session_state.get("cc_liabilities", 0.0) or 0.0),
        step=100000.0,
        key="cc_liabilities",
        help="Session-only estimate. Net Worth = Total Assets − Liabilities.",
    )
    st.caption("Controls save to session only. Command Center performs the recompute.")

_ready = bool(_books) or bool(_assets)
if not _ready:
    st.markdown(
        ui_empty(
            "Nothing to show until the Command Center runs.",
            "Upload a workbook above, open Command Center once, then return here.",
            "Desk → upload → Command",
        ),
        unsafe_allow_html=True,
    )
    st.stop()

st.markdown(ui_section("Books as-of", "session snapshot"), unsafe_allow_html=True)
_book_cards = []
for _k, _label in (
    ("mf", "Mutual funds"),
    ("stocks", "Stocks"),
    ("gold", "Gold"),
    ("fd", "FDs"),
    ("cash", "Cash"),
):
    _df = _books.get(_k)
    _n = 0 if _df is None else int(len(_df))
    _cur = 0.0
    if _df is not None and not getattr(_df, "empty", True):
        for _col in ("Current Value", "Current Value (INR)", "Current"):
            if _col in _df.columns:
                try:
                    _cur = float(pd.to_numeric(_df[_col], errors="coerce").fillna(0).sum())
                    break
                except Exception:
                    pass
    _book_cards.append(
        {
            "label": _label,
            "value": format_inr_compact(_cur) if _cur else str(_n),
            "sub": f"{_n} rows" if _n else "empty",
        }
    )
st.markdown(ui_kpi_cards(_book_cards, cols=5), unsafe_allow_html=True)

st.markdown(
    ui_section("Committed portfolio history", "daily job → portfolio_history.csv"),
    unsafe_allow_html=True,
)
try:
    render_portfolio_history(st)
except Exception as _hist_exc:
    st.caption(f"Portfolio history unavailable: {_hist_exc}")

st.markdown(ui_section("Sources & freshness", "session"), unsafe_allow_html=True)
st.caption(str(st.session_state.get("cc_book_note") or "—"))
st.caption(
    f"Book mode: {st.session_state.get('book_mode') or 'unknown'} · "
    f"path {st.session_state.get('book_path_display') or '—'}"
)

st.markdown(ui_section("Exports", "session CSV"), unsafe_allow_html=True)
for _k, _label in (("mf", "MF"), ("stocks", "Stocks"), ("gold", "Gold"), ("fd", "FD"), ("cash", "Cash")):
    _df = _books.get(_k)
    if _df is None or getattr(_df, "empty", True):
        continue
    st.download_button(
        f"Download {_label} CSV",
        data=_df.to_csv(index=False).encode("utf-8"),
        file_name=f"northline_{_k}.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.markdown(ui_section("Daily self-audit", "GitHub Actions · data/audit"), unsafe_allow_html=True)
_audit_md = Path(__file__).resolve().parents[1] / "data" / "audit" / "latest.md"
_audit_json = _audit_md.with_suffix(".json")
if _audit_md.exists():
    try:
        _txt = _audit_md.read_text(encoding="utf-8")
        st.markdown(_txt)
    except Exception as _ae:
        st.caption(f"Audit log unreadable: {_ae}")
    if _audit_json.exists():
        st.download_button(
            "Download latest audit JSON",
            data=_audit_json.read_bytes(),
            file_name="northline_audit_latest.json",
            mime="application/json",
            use_container_width=True,
        )
else:
    st.caption(
        "No audit log yet. GitHub Action **Daily Self Audit** runs once daily (~05:15 UTC) "
        "and writes data/audit/latest.md. You can also run it manually from the Actions tab."
    )

st.caption(LIFETIME_PNL_CAPTION)
st.caption(PERIOD_DELTA_CAPTION)
st.caption(NOT_A_CASHFLOW_LABEL)
