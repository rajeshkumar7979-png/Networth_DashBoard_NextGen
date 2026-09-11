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
from lib.ui import (
    caption as ui_caption,
    empty_state as ui_empty,
    nav_shell as ui_nav,
    page_header_html as ui_page_header,
    section_header_html as ui_section,
    unavailable as ui_unavailable,
)

theme.inject_css()

IST = pytz.timezone("Asia/Kolkata")
NOW_IST = datetime.now(IST)
TODAY = pd.Timestamp(NOW_IST.date())

st.markdown(ui_nav("outlook"), unsafe_allow_html=True)
st.markdown(ui_page_header(
    "Northline · Family desk",
    "Outlook",
    "What happens next — the maturity calendar, a 12-month ladder and an illustrative "
    "5-year view you can poke at. No forecasts; only workbook dates and your assumptions.",
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
    cur = str(row.get("Currency") or "").strip().upper()
    amt_native = safe_float(row.get("Maturity Amount (Native)"), None)
    if cur == "USD":
        return ("FCNR USD", f"{amt_native:,.0f} USD" if amt_native else "USD (amount n/a)")
    val_inr = safe_float(row.get("Current Value (INR)"), None)
    return ("INR FD", format_inr(val_inr) if val_inr else "amount n/a")

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
    cards = []
    for label, df in buckets:
        if df.empty:
            continue
        tot_inr = float(pd.to_numeric(df["Current Value (INR)"], errors="coerce").sum() or 0)
        cards.append({
            "label": label,
            "value": format_inr_compact(tot_inr) if tot_inr else "—",
            "sub": f"{len(df)} FD{'s' if len(df) > 1 else ''}",
        })
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
        f'<div class="t-list-row"><span class="t-list-name">{r[0]} · {r[1]}</span>'
        f'<span class="t-list-meta">{r[2]}</span></div>' for r in rows)
    st.markdown(f'<div class="t-list">{list_html}</div>', unsafe_allow_html=True)
    st.markdown(ui_caption(
        "FCNR proceeds land in USD; the INR figure depends on the settlement rate, so it is "
        "not shown here. Values use this run's computed current value."), unsafe_allow_html=True)
else:
    st.markdown(ui_caption("Nothing matures in the next 90 days — no calendar to draw."))


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
    st.markdown(ui_caption("No maturities across the next 12 months."))
else:
    _inr = _ladder[_ladder["Currency"].astype(str).str.strip().str.upper().fillna("INR") != "USD"]
    _usd = _ladder[_ladder["Currency"].astype(str).str.strip().str.upper() == "USD"]

    inr_totals = {}
    for pm, grp in _inr.groupby("_ym"):
        inr_totals[str(pm)] = float(pd.to_numeric(
            grp["Current Value (INR)"], errors="coerce")
            .fillna(pd.to_numeric(grp.get("Maturity Amount (Native)"), errors="coerce"))
            .sum() or 0)
    if inr_totals:
        mx = max(inr_totals.values()) or 1
        labels = sorted(inr_totals)
        html = ""
        for ym in labels:
            val = inr_totals[ym]
            width = max(1.0, val / mx * 100)
            html += (
                f'<div class="ladder-row"><div class="ladder-ym">{ym}</div>'
                f'<div class="ladder-bar-wrap"><div class="ladder-bar" style="width:{width:.1f}%"></div></div>'
                f'<div class="ladder-val">{format_inr_compact(val)}</div></div>'
            )
        st.markdown(html, unsafe_allow_html=True)
    else:
        st.markdown(ui_caption("No INR FDs mature across the next 12 months."))

    if not _usd.empty:
        st.markdown("**FCNR (USD) — separate, because FX at maturity is unknown**")
        for _pm, _grp in _usd.groupby("_ym"):
            _amt = float(pd.to_numeric(_grp["Maturity Amount (Native)"], errors="coerce").dropna().sum() or 0)
            _grp2 = pd.to_numeric(_grp["Maturity Amount (Native)"], errors="coerce")
            st.markdown(
                f'<div class="t-list-row"><span class="t-list-name">{_pm} · FCNR USD</span>'
                f'<span class="t-list-meta">{_amt:,.0f} USD</span></div>',
                unsafe_allow_html=True)
        st.markdown(ui_caption("Ladder bar widths use INR amounts only; USD is listed separately, "
                               "never silently converted at a guessed rate."), unsafe_allow_html=True)


# --------------------------------------------------
# 03 — ILLUSTRATIVE 5-YEAR VIEW (explicit assumptions)
# --------------------------------------------------
st.markdown(ui_section("Illustrative 5-year view", "your assumptions, not a forecast"), unsafe_allow_html=True)

_net = _assets.get("total_assets")
if not _net:
    st.markdown(ui_unavailable("Net worth not available",
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
st.markdown('<a class="t-drill" href="decisions" style="font-size:0.95rem;">Open Decision Desk →</a>',
            unsafe_allow_html=True)
st.caption(f"Outlook as-of {NOW_IST:%d %b %Y, %H:%M IST} · weeks and months from the workbook's own "
           "maturity dates; nothing else is projected.")