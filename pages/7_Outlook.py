# ==================================================
# OUTLOOK — maturities, ladder, and an explicit illustration.
#
# Reads the Command Center's fd book (cc_books) and asset totals (cc_assets);
# every number is native to the workbook + this run's computed values. FCNR
# (USD) amounts stay in USD with a clear "FX at maturity unknown" note — nothing
# is converted with a guessed rate. The 5-year view is an ILLUSTRATION built on
# flat-rate assumptions the reader sets; it is never a forecast, and never advice.
# ==================================================
import streamlit as st
from datetime import datetime
import pandas as pd
import pytz

from lib import theme
from lib.formatters import format_inr, format_inr_compact, safe_float
import html as _html
from lib.ui import (
    caption as ui_caption,
    empty_state as ui_empty,
    ladder_rows as ui_ladder,
    nav_shell as ui_nav,
    page_header_html as ui_page_header,
    safe_page_link,
    section_header_html as ui_section,
    unavailable as ui_unavailable,
)

theme.inject_css()

IST = pytz.timezone("Asia/Kolkata")
NOW_IST = datetime.now(IST)
TODAY = pd.Timestamp(NOW_IST.date())

ui_nav("outlook")
st.markdown(ui_page_header(
    "Northline · Family desk",
    "What happens next",
    "Cash that is maturing, a five-year illustration of today’s mix versus a 40% equity book, "
    "and a quiet place to test a move. Not investment advice.",
    meta=[
        f"AS OF {NOW_IST.strftime('%d %b %Y, %H:%M IST')}",
        "WORKBOOK DATES ONLY",
        "NO GUESSED FX",
    ],
), unsafe_allow_html=True)

_books = st.session_state.get("cc_books") or {}
_fd = _books.get("fd")
_assets = st.session_state.get("cc_assets") or {}

if _fd is None or _fd.empty or "Maturity Date" not in _fd.columns:
    st.markdown(ui_empty(
        "No FD book in this session yet.",
        "The Command Center builds the fd book when it runs on the workbook.",
        "Open Command Center once, then return here.",
    ), unsafe_allow_html=True)
    st.stop()


# --------------------------------------------------
# 01 — NEXT 90 DAYS: maturity calendar
# --------------------------------------------------
st.markdown(ui_section("Next 90 days · maturity calendar", "workbook dates only"), unsafe_allow_html=True)
_mat = _fd.copy()
_mat["_days"] = pd.to_numeric(_fd["Days to Maturity"], errors="coerce")

def _fd_meta(row):
    """Booked value (this run's mark) vs contractual maturity proceeds.

    FCNR proceeds stay in native USD — never converted at a guessed FX.
    INR booked value is Current Value (INR); proceeds are Maturity Amount (Native).
    """
    cur = str(row.get("Currency") or "").strip().upper()
    proceeds = safe_float(row.get("Maturity Amount (Native)"), None)
    booked = safe_float(row.get("Current Value (INR)"), None)
    if cur == "USD":
        proc = f"{proceeds:,.0f} USD proceeds" if proceeds else "USD proceeds n/a"
        return ("FCNR USD", proc)
    booked_s = format_inr(booked) if booked else "booked n/a"
    if proceeds:
        return ("INR FD", f"{booked_s} booked · {format_inr(proceeds)} proceeds")
    return ("INR FD", f"{booked_s} booked")

def _bucket_rows(days):
    if days < 0:
        label = f"matured {int(abs(days))}d ago"
    elif days == 0:
        label = "matures today"
    elif days < 30:
        label = f"{int(days)}d"
    else:
        label = f"{int(days)}d"
    return label

buckets = [
    ("Due now", _mat[_mat["_days"] < 0]),
    ("Next 30 days", _mat[_mat["_days"].between(0, 30)]),
    ("31–60 days", _mat[_mat["_days"].between(31, 60)]),
    ("61–90 days", _mat[_mat["_days"].between(61, 90)]),
]
nonempty = [b for b in buckets if not b[1].empty]
if nonempty:
    _isd_currency = _fd["Currency"].astype(str).str.strip().str.upper().fillna("INR")
    cards = []
    for label, df in buckets:
        if df.empty:
            continue
        _inr_rows = df[_isd_currency.reindex(df.index) != "USD"]
        _usd_rows = df[_isd_currency.reindex(df.index) == "USD"]
        _cards = []
        if not _inr_rows.empty:
            tot_inr = float(pd.to_numeric(_inr_rows["Current Value (INR)"], errors="coerce").sum() or 0)
            _cards.append((format_inr_compact(tot_inr) if tot_inr else "—",
                           f"{len(_inr_rows)} FD{'s' if len(_inr_rows) > 1 else ''} · booked value"))
        if not _usd_rows.empty:
            _cards.append((f"{len(_usd_rows)} USD FD{'s' if len(_usd_rows) > 1 else ''}", "FCNR·USD"))
        for _val, _sub in _cards:
            cards.append({"label": label, "value": _val, "sub": _sub})
    _bucket_grid = "".join(
        f'<div class="t-kpi"><div class="t-kpi-label">{_c["label"]}</div>'
        f'<div class="t-kpi-value">{_c["value"]}</div>'
        f'<div class="t-kpi-sub">{_c["sub"]}</div></div>' for _c in cards)
    st.markdown(
        f'<div class="t-kpi-grid t-kpi-grid-4">{_bucket_grid}</div>',
        unsafe_allow_html=True)
    rows = []
    for label, df in nonempty:
        for _, r in df.sort_values("_days").iterrows():
            kind, amt = _fd_meta(r)
            rows.append((kind, f"{r.get('Holder Name')} · {_bucket_rows(r['_days'])}", amt))
    list_html = "".join(
        f'<div class="t-list-row"><span class="t-list-name">{_html.escape(str(r[0]))} · {_html.escape(str(r[1]))}</span>'
        f'<span class="t-list-meta">{_html.escape(str(r[2]))}</span></div>' for r in rows)
    st.markdown(f'<div class="t-list">{list_html}</div>', unsafe_allow_html=True)
    st.markdown(ui_caption(
        "Booked value = this run’s mark (Current Value INR). Maturity proceeds = the "
        "contractual amount on the deposit. FCNR proceeds land in USD; the INR figure "
        "depends on the settlement rate, so it is never guessed here."), unsafe_allow_html=True)
else:
    st.markdown(ui_caption("Nothing matures in the next 90 days — no calendar to draw."),
                unsafe_allow_html=True)


# --------------------------------------------------
# 02 — 12-MONTH LADDER
# --------------------------------------------------
st.markdown(ui_section("Rolling 12-month ladder", "when each deposit frees cash"), unsafe_allow_html=True)

_ladder = _mat.copy()
_ladder["_mat"] = pd.to_datetime(_ladder["Maturity Date"], errors="coerce")
_ladder = _ladder[_ladder["_mat"].notna()]
_ladder["_ym"] = _ladder["_mat"].dt.to_period("M")
_m12 = TODAY + pd.DateOffset(months=12)
_ladder = _ladder[_ladder["_mat"] <= _m12]

if _ladder.empty:
    st.markdown(ui_caption("No maturities across the next 12 months."), unsafe_allow_html=True)
else:
    _inr = _ladder[_ladder["Currency"].astype(str).str.strip().str.upper().fillna("INR") != "USD"]
    _usd = _ladder[_ladder["Currency"].astype(str).str.strip().str.upper() == "USD"]

    inr_rows = []
    for pm, grp in _inr.groupby("_ym"):
        # Contractual proceeds only — never mix booked Current Value into the
        # "frees cash" ladder (those are different quantities).
        if "Maturity Amount (Native)" in grp.columns:
            _proc = pd.to_numeric(grp["Maturity Amount (Native)"], errors="coerce")
            _total = float(_proc.dropna().sum()) if _proc.notna().any() else 0.0
        else:
            _total = 0.0
        inr_rows.append({"label": str(pm), "value": float(_total or 0)})
    if inr_rows:
        st.markdown(ui_ladder(inr_rows), unsafe_allow_html=True)
    else:
        st.markdown(ui_caption("No INR FDs mature across the next 12 months."), unsafe_allow_html=True)

    if not _usd.empty:
        st.markdown("**FCNR (USD) — separate, because FX at maturity is unknown**")
        for _pm, _grp in _usd.groupby("_ym"):
            _amt = float(pd.to_numeric(_grp["Maturity Amount (Native)"], errors="coerce").dropna().sum() or 0)
            st.markdown(
                f'<div class="t-list-row"><span class="t-list-name">{_html.escape(str(_pm))} · FCNR USD</span>'
                f'<span class="t-list-meta">{_amt:,.0f} USD proceeds</span></div>',
                unsafe_allow_html=True)
    st.markdown(ui_caption(
        "INR bars are contractual maturity proceeds (native INR), not this run’s booked value. "
        "USD FCNR is listed separately as USD proceeds and is never converted at a guessed rate."),
        unsafe_allow_html=True)


# --------------------------------------------------
# 03 — ILLUSTRATIVE 5-YEAR VIEW (explicit assumptions)
# --------------------------------------------------
st.markdown(ui_section("Illustrative 5-year view", "your assumptions, not a forecast"), unsafe_allow_html=True)

_net = _assets.get("total_assets")
if not _net:
    st.markdown(ui_unavailable("Total assets not available",
                               "Publish cc_assets by opening the Command Center once."), unsafe_allow_html=True)
    st.stop()

c1, c2 = st.columns(2)
with c1:
    _rate = st.slider("Assumed flat annual growth (%)", min_value=0.0, max_value=15.0, value=7.0, step=0.5)
with c2:
    _horizon = st.slider("Horizon (years)", min_value=1, max_value=10, value=5)

_proj = _net * (1 + _rate / 100.0) ** _horizon
_gain = _proj - _net

_proj_cards = [
    {"label": "Assumed flat rate", "value": f"{_rate:.1f}% p.a.", "sub": "your input"},
    {"label": f"Projected total · {_horizon}y", "value": format_inr_compact(_proj), "sub": "illustration"},
    {"label": "Implied gain", "value": format_inr_compact(_gain), "sub": "before any costs / taxes / FX"},
]
_proj_grid = "".join(
        f'<div class="t-kpi"><div class="t-kpi-label">{_c["label"]}</div>'
        f'<div class="t-kpi-value">{_c["value"]}</div><div class="t-kpi-sub">{_c["sub"]}</div></div>'
        for _c in _proj_cards)
st.markdown(
    f'<div class="t-kpi-grid t-kpi-grid-4">{_proj_grid}</div>',
    unsafe_allow_html=True)
st.markdown(ui_caption(
    "ILLUSTRATION, NOT A FORECAST: a single flat rate compounds the current total with no "
    "contributions, withdrawals, taxes or currency moves modelled. Markets do not move in "
    "flat lines. Not investment advice."), unsafe_allow_html=True)


# --------------------------------------------------
# HOOK TO DECISION DESK
# --------------------------------------------------
st.markdown("---")
st.markdown("**Money that frees up has a decision to make.**")
with st.container(key="nb_drill_links"):
    safe_page_link("pages/2_Deep_Health.py", label="Open Decision Desk →")
st.caption(f"Outlook as-of {NOW_IST:%d %b %Y, %H:%M IST} · weeks and months from the workbook's own "
           "maturity dates; nothing else is projected.")