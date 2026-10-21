"""Funds — quality, overlap, concentration (Phase 5 institutional view)."""
from __future__ import annotations

from collections import defaultdict

import pandas as pd
import streamlit as st

from lib.deploy_meta import mf_period_status
from lib.mf_period_table import scheme_period_table
from lib.formatters import format_inr_compact
from lib.mf_health import analyze_fund, get_holdings_for_funds
from lib.overlap import (
    CONCENTRATION_THRESHOLD_PCT,
    DIRECT_REGULAR_NOTE,
    LOOKTHROUGH_METHOD,
    OVERLAP_METHOD,
    concentration_flags,
    direct_regular_pairs,
    family_look_through,
    holding_key,
    pairwise_matrix,
)
from lib.theme import inject_css
from lib.ui import (
    caption,
    empty_state,
    kpi_cards,
    nav_shell,
    page_header_html,
    section_header_html,
)

inject_css()
nav_shell("funds")
st.markdown(
    page_header_html(
        "Northline · Family desk",
        "Quality, overlap, concentration",
        "Disclosed AMC portfolios + your scheme weights. Not a recommendation engine.",
        meta=["PORTFOLIO-FIRST", "DISCLOSED NUMBERS ONLY", "ILLUSTRATIVE SCORES"],
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

_period_tbl = scheme_period_table()
if _period_tbl is not None and not _period_tbl.empty:
    with st.expander("Scheme filing status (as_of / SAME_PERIOD / source)", expanded=False):
        st.dataframe(_period_tbl, hide_index=True, use_container_width=True)
        st.caption(
            "SAME_PERIOD = AMC has not published a newer monthly portfolio yet. "
            "+ / - / ~ are holding-line adds, exits, and weight changes vs prior filing."
        )

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

ok_results = list(by_code.values())
n_positions = len(raw_results)
n_schemes = len(ok_results)
total_value = sum(float(r.get("current_value") or 0) for r in ok_results)
for r in ok_results:
    cv = float(r.get("current_value") or 0)
    r["weight_pct"] = (cv / total_value * 100.0) if total_value else 0.0

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
            "Health*": r.get("health_score"),
        }
    )
df = pd.DataFrame(rows).sort_values("Weight %", ascending=False)

st.markdown(section_header_html("Book at a glance", "portfolio"), unsafe_allow_html=True)
top5 = float(df.nlargest(5, "Weight %")["Weight %"].sum()) if not df.empty else 0.0
st.markdown(
    kpi_cards(
        [
            {
                "label": "MF book value",
                "value": format_inr_compact(total_value),
                "sub": "positions merged by scheme code",
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

st.markdown(section_header_html("Scheme weights", "bar"), unsafe_allow_html=True)
if not df.empty:
    st.bar_chart(df.set_index("Fund")[["Weight %"]].head(15), height=280)

st.markdown(section_header_html("Scheme book", "sorted by weight"), unsafe_allow_html=True)
st.dataframe(df, hide_index=True, use_container_width=True)
st.caption(
    "*Health is an illustrative internal index (returns / concentration heuristics), "
    "not an AMFI or rating-agency score."
)

codes = [str(r.get("scheme_code")) for r in ok_results if r.get("scheme_code")]
holdings_by_code, _cache = get_holdings_for_funds(codes, force_refresh=False)
n_disclosed = sum(1 for c in codes if holdings_by_code.get(c))
st.markdown(
    caption(
        f"Holdings disclosure: {n_disclosed}/{n_schemes} schemes have cached portfolio lines. "
        "Source on HEAD is OpenFin CDN (openfin-cdn). as_of is the AMC filing month. "
        "SAME_PERIOD means that month has not advanced yet."
    ),
    unsafe_allow_html=True,
)

fund_values = {
    str(r.get("scheme_code")): float(r.get("current_value") or 0)
    for r in ok_results
    if r.get("scheme_code")
}
fund_names = {
    str(r.get("scheme_code")): str(r.get("fund_name") or r.get("scheme_code"))
    for r in ok_results
    if r.get("scheme_code")
}

fund_weights = {}
stock_exposure = defaultdict(list)
for code, holdings in (holdings_by_code or {}).items():
    if not holdings:
        continue
    fname = fund_names.get(str(code), str(code))
    fv = fund_values.get(str(code), 0.0)
    wmap = {}
    for h in holdings:
        if not isinstance(h, dict):
            continue
        key = holding_key(h.get("isin"), h.get("name"))
        if not key:
            continue
        try:
            w = float(h.get("weight_pct"))
        except (TypeError, ValueError):
            continue
        if w <= 0:
            continue
        prev = wmap.get(key)
        if prev is None or w > prev:
            wmap[key] = w
        stock_exposure[key].append((fname, w, fv, h.get("name")))
    if wmap:
        fund_weights[fname] = wmap

st.markdown(section_header_html("Pairwise overlap", "Morningstar-style min weights"), unsafe_allow_html=True)
st.caption(OVERLAP_METHOD)
if len(fund_weights) >= 2:
    pairs = pairwise_matrix(fund_weights)
    if pairs:
        pair_df = pd.DataFrame(
            [
                {"Overlap %": round(float(pct), 1), "Fund A": a, "Fund B": b}
                for a, b, pct in pairs
                if pct is not None
            ]
        ).sort_values("Overlap %", ascending=False)
        st.dataframe(pair_df.head(20), hide_index=True, use_container_width=True)
        top_names = list(df["Fund"].head(8))
        top_set = set(top_names)
        matrix_names = [n for n in top_names if n in fund_weights]
        if len(matrix_names) >= 2:
            grid = {a: {b: None for b in matrix_names} for a in matrix_names}
            for a, b, pct in pairs:
                if a in top_set and b in top_set and pct is not None:
                    grid[a][b] = round(float(pct), 1)
                    grid[b][a] = round(float(pct), 1)
            for n in matrix_names:
                grid[n][n] = 100.0
            short = {n: (n[:22] + "…") if len(n) > 22 else n for n in matrix_names}
            mat = pd.DataFrame(grid).rename(index=short, columns=short)
            mat = mat.reindex(index=[short[n] for n in matrix_names], columns=[short[n] for n in matrix_names])
            st.caption("Overlap grid (top schemes by weight)")
            st.dataframe(mat, use_container_width=True)
    else:
        st.caption("No pairwise overlap rows (no common disclosed holdings).")
else:
    st.caption("Need at least two schemes with disclosed holdings for pairwise overlap.")

st.markdown(section_header_html("Family look-through", "top equity exposures"), unsafe_allow_html=True)
st.caption(LOOKTHROUGH_METHOD)
if stock_exposure and total_value > 0:
    look = family_look_through(stock_exposure, total_value)
    if look:
        look_df = pd.DataFrame(
            [
                {
                    "Security": r.get("name"),
                    "Exposure ₹": round(float(r.get("exposure_inr") or 0), 0),
                    "Of MF book %": round(float(r.get("pct_of_mf") or 0), 2),
                    "Funds": r.get("n_funds"),
                }
                for r in look
            ]
        )
        st.dataframe(look_df.head(25), hide_index=True, use_container_width=True)
        flags = concentration_flags(look, threshold_pct=CONCENTRATION_THRESHOLD_PCT)
        if flags:
            st.caption(f"Concentration flags (>{CONCENTRATION_THRESHOLD_PCT}% of MF book)")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Security": r.get("name"),
                            "Of MF book %": round(float(r.get("pct_of_mf") or 0), 2),
                            "Exposure ₹": round(float(r.get("exposure_inr") or 0), 0),
                        }
                        for r in flags
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )
    else:
        st.caption("No look-through rows (weights or holdings missing).")
else:
    st.caption("No disclosed holdings available for look-through.")

name_list = [str(r.get("fund_name") or "") for r in ok_results]
dr_pairs = direct_regular_pairs(name_list)
if dr_pairs:
    st.markdown(section_header_html("Direct vs Regular", "same scheme, two share classes"), unsafe_allow_html=True)
    st.caption(DIRECT_REGULAR_NOTE)
    st.dataframe(
        pd.DataFrame(
            [
                {"Stem": stem, "Direct": ", ".join(d), "Regular": ", ".join(reg)}
                for stem, d, reg in dr_pairs
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )

if n_disclosed:
    st.markdown(section_header_html("Disclosed holdings sample", "largest scheme with cache"), unsafe_allow_html=True)
    best, best_v = None, -1.0
    for c in codes:
        h = holdings_by_code.get(c) or []
        v = fund_values.get(str(c), 0.0)
        if h and v > best_v:
            best, best_v = c, v
    if best:
        h = holdings_by_code.get(best) or []
        st.caption(
            f"{fund_names.get(str(best), best)} · scheme {best} · {len(h)} lines · top 30 by weight"
        )
        hdf = pd.DataFrame(h)
        if "weight_pct" in hdf.columns:
            hdf = hdf.sort_values("weight_pct", ascending=False)
        st.dataframe(hdf.head(30), hide_index=True, use_container_width=True)

st.caption(
    "Northline does not place orders. Overlap and look-through use cached AMC monthly portfolios "
    "(OpenFin CDN). Figures are for monitoring only."
)
