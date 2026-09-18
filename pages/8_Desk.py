# ==================================================
# DESK — operator & transparency view.
#
# Source status (cache-read-only, network-free), the books as-of, exports,
# a live register↔page reconciliation gate, and the methodology/integrity
# notices that explain how this terminal reaches its numbers. Nothing here
# re-values the portfolio; every figure is imported or recomputed purely
# from the Command Center's own session data.
# ==================================================
import streamlit as st
from datetime import datetime
import json
import os
import pandas as pd
import pytz

from lib import theme
from lib.formatters import format_inr_compact
from lib.intelligence.sources import gateway_status
from lib.intelligence import live as intel_live
from lib.register import aggregate_by_class, build_asset_register, family_level_sum
from lib.ui import (
    caption as ui_caption,
    empty_state as ui_empty,
    nav_shell as ui_nav,
    page_header_html as ui_page_header,
    section_header_html as ui_section,
    status_pill as ui_status_pill,
    unavailable as ui_unavailable,
)

theme.inject_css()

IST = pytz.timezone("Asia/Kolkata")
NOW_IST = datetime.now(IST)

ui_nav("desk")
st.markdown(ui_page_header(
    "Northline · Family desk",
    "Sources, exports, how to read this",
    "Tape status, downloads, reconciliation, and the method behind every number. Nothing here re-values the book.",
    meta=[
        f"AS OF {NOW_IST.strftime('%d %b %Y, %H:%M IST')}",
        "CACHE-READ-ONLY",
        "NO VALUATION HERE",
    ],
), unsafe_allow_html=True)

_books = st.session_state.get("cc_books") or {}
_assets = st.session_state.get("cc_assets") or {}
_rates = st.session_state.get("cc_rates") or {}
_snapshot = st.session_state.get("cc_intel_snapshot") or {}

# -------------------------------------------------
# RUN CONTROLS & EXPORTS — single shared touch-point band.
# The Excel uploader, the force-recalculate trigger, the snapshot/auto-refresh
# toggles dry-write session keys for the Command Center to read on its next pass
# (cc_uploaded_file / cc_log_snapshot / cc_auto_refresh). Nothing here calls the
# network; the Command Center remains the only page that fetches live evidence.
# -------------------------------------------------
_controls_exp = st.expander("Run controls & exports", expanded=False)
with _controls_exp:
    st.markdown("### Controls")
    st.file_uploader(
        "Upload new Excel",
        type=["xlsx", "xls"],
        key="cc_uploaded_file",
        help="Pick the family workbook (.xlsx/.xls). It dry-writes the session key that the Command Center reads on its next run — nothing is fetched until you run there.",
    )
    if st.button("Force Recalculate", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()
    st.toggle(
        "Log today's snapshot to history", value=bool(st.session_state.get("cc_log_snapshot", True)), key="cc_log_snapshot"
    )
    st.toggle(
        "Auto refresh every 5 minutes", value=bool(st.session_state.get("cc_auto_refresh", True)), key="cc_auto_refresh"
    )
    st.markdown("---")
    st.markdown("### History")
    if st.button("Reset history file", use_container_width=True):
        st.session_state["cc_reset_history"] = True
    st.markdown("---")
    st.markdown("### Restore / merge history CSV")
    st.file_uploader(
        "Restore history CSV",
        type=["csv"],
        key="cc_hist_upload",
        help="Merge an existing history file into the history log. The Command Center applies this on its next run.",
    )
    st.markdown("---")
    st.markdown("### Books")
    st.number_input(
        "Liabilities (session-only, ₹)",
        min_value=0.0,
        value=float(st.session_state.get("cc_liabilities", 0.0) or 0.0),
        step=100000.0,
        key="cc_liabilities",
        help="No liabilities sheet exists in the workbook. This is a session-only estimate used by Command as Net Worth = Total Assets − Liabilities.",
    )
    st.caption("Run controls & exports save to the session only. Nothing is recalculated until the Command Center runs.")

_ready = bool(_books) or bool(_assets)
if not _ready:
    st.markdown(ui_empty(
        "Nothing to show until the Command Center runs.",
        "Desk is a read-only view over the session data the Command Center builds.",
        "Upload a workbook above, open Command Center once, then return here.",
    ), unsafe_allow_html=True)
    st.stop()


# --------------------------------------------------
# 01 — BOOKS AS-OF
# --------------------------------------------------
st.markdown(ui_section("Books as-of", "session snapshot the terminal reads"),
            unsafe_allow_html=True)
_book_cards = []
for _k, _label in (("mf", "Mutual funds"), ("stocks", "Stocks"), ("gold", "Gold"), ("fd", "FDs")):
    _df = _books.get(_k)
    _n = 0 if _df is None else int(len(_df))
    _cur = 0.0
    if _df is not None and not _df.empty and "Current Value" in _df.columns:
        _cur = float(pd.to_numeric(_df["Current Value"], errors="coerce").sum() or 0)
    elif _df is not None and not _df.empty and "Current Value (INR)" in _df.columns:
        _cur = float(pd.to_numeric(_df["Current Value (INR)"], errors="coerce").sum() or 0)
    _book_cards.append({
        "label": _label,
        "value": f"{_n}" if _n else "0",
        "sub": format_inr_compact(_cur) if _cur else "—",
    })
_book_cards.append({
    "label": "Total assets",
    "value": format_inr_compact(_assets.get("total_assets")) if _assets.get("total_assets") else "—",
    "sub": "as computed by Command Center",
})
_book_grid = "".join(
        f'<div class="t-kpi"><div class="t-kpi-label">{_c["label"]}</div>'
        f'<div class="t-kpi-value">{_c["value"]}</div>'
        f'<div class="t-kpi-sub">{_c.get("sub", "")}</div></div>' for _c in _book_cards)
st.markdown(
    f'<div class="t-kpi-grid t-kpi-grid-4">{_book_grid}</div>',
    unsafe_allow_html=True)
if _rates:
    _rd = []
    if _rates.get("usd_inr") is not None:
        _rd.append(f"USD/INR {_rates['usd_inr']:.2f}")
    if _rates.get("gold_10g_inr") is not None:
        _rd.append(f"Gold ₹/10g {_rates['gold_10g_inr']:,.0f}")
    if _rd:
        st.markdown(f'<div class="t-caption">Reference rates this run: {" · ".join(_rd)}.</div>',
                    unsafe_allow_html=True)


# --------------------------------------------------
# 02 — RECONCILIATION (register vs Command Center, live)
# --------------------------------------------------
st.markdown(ui_section("Reconciliation", "canonical register vs page"), unsafe_allow_html=True)
try:
    _reg = build_asset_register(_books.get("mf"), _books.get("stocks"),
                                _books.get("gold"), _books.get("fd"))
    _classes = aggregate_by_class(_reg)
    _family = family_level_sum(_reg)
    _reg_total = float(_family.get("total_assets") or 0.0) if _family is not None else 0.0
    _page_total = float(_assets.get("total_assets") or 0.0)
    _diff = abs(_reg_total - _page_total)
    _ok = _diff <= 1.0
    _mark = f'<span class="{"recon-pass" if _ok else "recon-fail"}">{("✓ PASS" if _ok else "✗ FAIL")}</span>'
    st.markdown(
        f'<div class="t-card">{_mark} — register total {format_inr_compact(_reg_total)} '
        f'vs Command Center total {format_inr_compact(_page_total)} '
        f'(difference {_diff:,.2f} INR, tolerance ₹1). The register is rebuilt purely from the '
        f'same four books; it never changes them.</div>',
        unsafe_allow_html=True)
    if _ok:
        st.markdown(ui_caption(
            "If this ever shows ✗ FAIL, stop and inspect: a register key collision or a books/"
            "assets mismatch means the standalone pages are reading a different picture."),
            unsafe_allow_html=True)
    if _classes is not None and not _classes.empty:
        with st.expander("Class totals (register view)"):
            st.dataframe(_classes, hide_index=True, use_container_width=True)
except Exception as _recon_err:
    st.markdown(ui_unavailable("Reconciliation could not run", str(_recon_err)),
                unsafe_allow_html=True)


# --------------------------------------------------
# 03 — SOURCES (network-free status)
# --------------------------------------------------
st.markdown(ui_section("Sources & freshness", "cache state, never live calls"), unsafe_allow_html=True)
try:
    _gw = gateway_status()
except Exception:
    _gw = []
_gw_rows = _gw or st.session_state.get("cc_intel_gateway_status") or []
if _gw_rows:
    with st.expander("Data gateway cache (FRED / SEC / AMFI NAV)"):
        st.dataframe(pd.DataFrame(_gw_rows), hide_index=True, use_container_width=True,
                     column_config={
                         "provider": st.column_config.TextColumn("Provider"),
                         "key": st.column_config.TextColumn("Cache key"),
                         "last_retrieval": st.column_config.TextColumn("Last retrieval"),
                         "record_count": st.column_config.NumberColumn("Records"),
                         "status": st.column_config.TextColumn("Status"),
                         "reason": st.column_config.TextColumn("Note"),
                     })
    _ok_n = sum(1 for r in _gw_rows if r.get("status") == "ok")
    st.markdown(ui_status_pill(f"{_ok_n}/{len(_gw_rows)} gateway caches usable",
                               "ok" if _ok_n else "cache"), unsafe_allow_html=True)
else:
    st.markdown(ui_caption("No gateway cache written yet — FRED/SEC fetch is on-demand from the "
                           "Command Center's refresh action."))
try:
    _lv_st = intel_live.live_status()
except Exception:
    _lv_st = []
if _lv_st:
    with st.expander("Live research cache (Google News RSS)"):
        st.dataframe(pd.DataFrame(_lv_st), hide_index=True, use_container_width=True)


# --------------------------------------------------
# 04 — EXPORTS (from this session's data)
# --------------------------------------------------
st.markdown(ui_section("Exports", "download current session data"), unsafe_allow_html=True)
_export_parts = []
for _k, _asset_label in (("mf", "MF"), ("stocks", "Stock"), ("gold", "Gold"), ("fd", "FD")):
    _df = _books.get(_k)
    if _df is not None and not _df.empty:
        _copy = _df.copy()
        _copy["Asset"] = _asset_label
        _export_parts.append(_copy)
if _export_parts:
    _hold = pd.concat(_export_parts, ignore_index=True, sort=False)
    st.download_button("Download holdings CSV",
                       data=_hold.to_csv(index=False).encode("utf-8"),
                       file_name="networth_holdings.csv", mime="text/csv")
else:
    st.markdown(ui_caption("No books in this session to export."))

if _snapshot:
    _snap_json = json.dumps(_snapshot, default=str, indent=2)
    st.download_button("Download intelligence snapshot (JSON)",
                       data=_snap_json.encode("utf-8"),
                       file_name="intelligence_snapshot.json", mime="application/json")
else:
    st.markdown(ui_caption("Run Command Center once and the intelligence snapshot export appears here."))

history_path = "data/history.csv"
if os.path.exists(history_path):
    try:
        _hist = pd.read_csv(history_path)
    except Exception:
        _hist = None
    if _hist is not None and not _hist.empty:
        st.download_button("Download history CSV",
                           data=_hist.to_csv(index=False).encode("utf-8"),
                           file_name="networth_history.csv", mime="text/csv")


# --------------------------------------------------
# 05 — HOW TO READ THIS (methodology & integrity)
# --------------------------------------------------
st.markdown(ui_section("How to read this terminal", "method & integrity"), unsafe_allow_html=True)
_stmts = [
    "Net Worth = Total Assets − Liabilities, computed only by lib/ledger; the workbook has no "
    "liabilities sheet, so liabilities are a session-only estimate and default to zero.",
    "Total Assets (INR) is the headline metric. It is the sum of the four data-backed books: "
    "Equity (stocks + non-liquid MF), Liquid MF, FCNR (USD) FD, INR FD, and Gold.",
    "FCNR (USD) deposits use the INR cost basis from the deposit-date FX, and their P&L is split "
    "into interest-at-current-FX and FX-on-principal — the attribution reconciles to the current "
    "value within ₹1 (lib/valuation).",
    "Current-run P&L decomposes into exact valuation drivers (Equity market, Liquid NAV, Gold price, "
    "FCNR interest, FCNR FX, INR FD interest) plus a labelled rounding residual bounded by "
    "1.5·n_fd+1 (lib/drivers).",
    "The invested difference between snapshots is the Invested-Basis Change — NOT a cash-flow "
    "measurement; there is no transaction history, so no deposit/withdrawal/SIP/redemption exists.",
    "No holding, return, valuation, tax outcome or historical event is ever invented. Missing data "
    "renders as 'insufficient evidence' or 'no data', never as a fabricated value.",
    "Intelligence facts carry the FactKind taxonomy (FACT / CALCULATED FACT / SIGNAL / AI "
    "INTERPRETATION / RECOMMENDATION). External data is observed evidence; our math is a "
    "calculated fact; neither is ever mislabeled as AI.",
    "Provider failures degrade to stale/unavailable, never to a successful record with made-up "
    "values. Network calls happen only on explicit actions (e.g. 'Refresh research evidence').",
    "Recommendations here are decision support only — this terminal never trades, and nothing on "
    "any page is an order.",
]
for _s in _stmts:
    st.markdown(f'<div class="t-list-row" style="align-items:flex-start;"><span class="t-list-name">·</span>'
                f'<span class="t-list-meta" style="text-align:left;">{_s}</span></div>',
                unsafe_allow_html=True)

st.markdown(f'<div class="t-footnote" style="margin-top:16px;">Desk as-of '
            f'{NOW_IST:%d %b %Y, %H:%M IST} · read-only render; no network happened on this page.</div>',
            unsafe_allow_html=True)