"""Funds — quality, overlap, concentration (restored working page)."""
import json
from collections import defaultdict

import numpy as np
import pandas as pd
import streamlit as st

from lib.deploy_meta import mf_period_status
from lib.formatters import format_inr_compact
from lib.mf_health import analyze_fund, get_holdings_for_funds
from lib.mf_holdings import HOLDINGS_META_CACHE
from lib.theme import inject_css
from lib.ui import (
    caption,
    empty_state,
    kpi_cards,
    nav_shell,
    page_header_html,
    pill,
    section_header_html,
)

inject_css()
nav_shell("funds")
st.markdown(
    page_header_html(
        "Northline · Family desk",
        "Quality, overlap, concentration",
        "The mutual-fund book, portfolio-first. Disclosed numbers only.",
        meta=["PORTFOLIO-FIRST", "DISCLOSED NUMBERS ONLY", "COST UNSCORED"],
    ),
    unsafe_allow_html=True,
)

mf_list = st.session_state.get("mf_holdings_for_health", [])
if not mf_list:
    st.markdown(
        empty_state(
            "Nothing to analyze yet",
            "Open the Command Center once so your funds and scheme codes are loaded here.",
            hint="Command Center → run once",
        ),
        unsafe_allow_html=True,
    )
    st.stop()

# Period banner (production transparency)
_period = mf_period_status()
if _period.get("ok"):
    st.caption(_period.get("headline") or "")
    st.caption(
        f"SAME_PERIOD {_period.get('same_period', 0)} · "
        f"new/changed {_period.get('new_period', 0)} · "
        f"errors {_period.get('errors', 0)} · unresolved {_period.get('unresolved', 0)}"
    )
else:
    st.caption(_period.get("reason") or "Holdings meta unavailable")

# Aggregate by scheme code
raw_results = []
for row in mf_list:
    name = row.get("Fund Name") or str(row)
    value = float(row.get("Current Value") or 0)
    weight = float(row.get("Weight %") or 0)
    scheme_code = row.get("Scheme Code")
    raw = analyze_fund(
        name,
        value,
        weight,
        scheme_code,
        cagr_1y=row.get("1Y %"),
        cagr_3y=row.get("3Y %"),
        cagr_5y=row.get("5Y %"),
        latest_nav=row.get("Current NAV"),
    )
    raw["Owner"] = row.get("Owner") or ""
    raw_results.append(raw)

by_code = {}
for r in raw_results:
    code = r.get("scheme_code")
    if not code:
        continue
    prev = by_code.get(code)
    if prev is None:
        r = dict(r)
        r["_positions"] = 1
        by_code[code] = r
        continue
    prev["current_value"] = float(prev.get("current_value") or 0) + float(r.get("current_value") or 0)
    prev["_positions"] = int(prev.get("_positions") or 1) + 1

ok_results = [r for r in by_code.values() if r.get("status") == "ok"]
if not ok_results:
    st.warning("No funds with usable data yet — scheme codes or cached values are missing.")
    st.stop()

total_value = sum(float(r.get("current_value") or 0) for r in ok_results)
n_positions = len(mf_list)
n_schemes = len(ok_results)

for r in ok_results:
    r["weight_pct"] = (float(r["current_value"]) / total_value * 100.0) if total_value else 0.0

rows = []
for r in ok_results:
    m = r.get("metrics") or {}
    rows.append(
        {
            "Fund": r.get("fund_name"),
            "Scheme": r.get("scheme_code"),
            "Value": r.get("current_value"),
            "Weight %": round(r.get("weight_pct") or 0, 2),
            "Positions": r.get("_positions"),
            "1Y": m.get("cagr_1Y"),
            "3Y": m.get("cagr_3Y"),
            "5Y": m.get("cagr_5Y"),
        }
    )
df = pd.DataFrame(rows).sort_values("Weight %", ascending=False)

st.markdown(section_header_html("Health at a glance", "portfolio"), unsafe_allow_html=True)
top5 = float(df.nlargest(5, "Weight %")["Weight %"].sum()) if not df.empty else 0.0
st.markdown(
    kpi_cards(
        [
            {
                "label": "MF book value",
                "value": format_inr_compact(total_value),
                "sub": "sum of positions after scheme merge",
            },
            {
                "label": "Positions / schemes",
                "value": f"{n_positions} / {n_schemes}",
                "sub": "unique schemes after merge",
            },
            {
                "label": "Top 5 weight",
                "value": f"{top5:.1f}%",
                "sub": "concentration in largest schemes",
            },
        ],
        cols=3,
    ),
    unsafe_allow_html=True,
)

st.markdown(section_header_html("Scheme book", "sorted by weight"), unsafe_allow_html=True)
st.dataframe(df, hide_index=True, use_container_width=True)

# Holdings disclosure coverage
codes = [r.get("scheme_code") for r in ok_results if r.get("scheme_code")]
holdings_by_code, _cache = get_holdings_for_funds(codes, force_refresh=False)
n_disclosed = sum(1 for c in codes if holdings_by_code.get(c))
st.markdown(
    caption(
        f"Holdings disclosure: {n_disclosed}/{n_schemes} schemes have cached portfolio lines. "
        "as_of is the AMC filing date (see banner). SAME_PERIOD means the filing month has not "
        "advanced yet — not that holdings never change."
    ),
    unsafe_allow_html=True,
)

if n_disclosed:
    st.markdown(section_header_html("Sample disclosed holdings", "first scheme with cache"), unsafe_allow_html=True)
    for c in codes:
        h = holdings_by_code.get(c) or []
        if not h:
            continue
        sample = pd.DataFrame(h[:25])
        st.caption(f"Scheme {c} · showing up to 25 lines")
        st.dataframe(sample, hide_index=True, use_container_width=True)
        break
