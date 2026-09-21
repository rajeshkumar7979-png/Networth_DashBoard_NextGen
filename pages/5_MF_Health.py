import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from collections import defaultdict
import json
import time
from lib.mf_health import analyze_fund, get_holdings_for_funds
from lib.mf_holdings import HOLDINGS_META_CACHE
from lib.theme import inject_css, PLOTLY_LAYOUT
from lib.formatters import format_inr_compact
from lib.overlap import (
    CONCENTRATION_THRESHOLD_PCT,
    DIRECT_REGULAR_NOTE,
    LOOKTHROUGH_METHOD,
    OVERLAP_METHOD,
    concentration_flags,
    direct_regular_pairs,
    family_look_through,
    pairwise_matrix,
    pairwise_overlap_pct,
)
from lib.returns import (
    LUMP_SUM_ANN_LABEL,
    MULTI_CASHFLOW_XIRR_GAP,
    SIMPLE_ROI_LABEL,
    TRAILING_CAGR_LABEL,
)
from lib.ui import (
    page_header_html,
    section_header_html,
    pill,
    kpi_cards,
    empty_state,
    caption,
    banner,
    footnote,
    nav_shell,
)

# ==================================================
# INSTITUTIONAL DARK THEME — one shared stylesheet (lib.theme)
# ==================================================
inject_css()

nav_shell("funds")
st.markdown(page_header_html(
    "Northline · Family desk",
    "Quality, overlap, concentration",
    "The mutual-fund book, portfolio-first. Every pillar traces to a disclosed or observed number; "
    "cost stays un-scored (no free expense-ratio source).",
    meta=[
        "PORTFOLIO-FIRST",
        "DISCLOSED NUMBERS ONLY",
        "COST UNSCORED",
    ],
), unsafe_allow_html=True)

mf_list = st.session_state.get("mf_holdings_for_health", [])
if not mf_list:
    st.markdown(empty_state(
        "Nothing to analyze yet",
        "Open the Command Center once so your funds and scheme codes are loaded here.",
        hint="Command Center → Intelligence → Refresh holdings",
    ), unsafe_allow_html=True)
    st.stop()

raw_results = []
for row in mf_list:
    name = row.get("Fund Name") or str(row)
    value = float(row.get("Current Value") or 0)
    weight = float(row.get("Weight %") or 0)
    scheme_code = row.get("Scheme Code")
    raw = analyze_fund(
        name, value, weight, scheme_code,
        cagr_1y=row.get("1Y %"), cagr_3y=row.get("3Y %"), cagr_5y=row.get("5Y %"),
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
        _holder = r.get("holder_name") or r.get("Holder Name") or r.get("Owner") or "family"
        r = dict(r)
        r["_holders"] = {_holder}
        r["_positions"] = 1
        by_code[code] = r
        continue
    prev["current_value"] = float(prev.get("current_value") or 0) + float(r.get("current_value") or 0)
    _holder = r.get("holder_name") or r.get("Holder Name") or r.get("Owner") or "family"
    prev.setdefault("_holders", set()).add(_holder)
    prev["_positions"] = int(prev.get("_positions") or 1) + 1
    if not prev.get("fund_name"):
        prev["fund_name"] = r.get("fund_name")

ok_results = [r for r in by_code.values() if r["status"] == "ok"]
if not ok_results:
    st.markdown(banner("No funds with usable data yet — scheme codes or cached values are missing.", "warning"),
                unsafe_allow_html=True)
    st.stop()

total_value = sum(r["current_value"] for r in ok_results)
n_positions = len(mf_list)
n_schemes = len(ok_results)
# Combined scheme weight vs the MF book (not the larger member's original weight).
for r in ok_results:
    r["weight_pct"] = (float(r["current_value"]) / total_value * 100.0) if total_value else 0.0

# ==================================================
# CATEGORY (reuse Command Center's category text via fund name heuristics
# already stored — fall back to generic label; never invented AUM/expense data)
# ==================================================
import re
CATEGORY_RULES = [
    ("Liquid", r"liquid"), ("Small Cap", r"small\s*cap"), ("Mid Cap", r"mid\s*cap"),
    ("Large Cap", r"large\s*cap|bluechip"), ("Flexi Cap", r"flexi\s*cap|multi\s*cap"),
    ("Index", r"index|next\s*50|nifty\s*50\b"), ("Hybrid", r"hybrid|balanced"),
    ("Contra/Value", r"contra|value\s*discovery"),
    ("Thematic", r"infra|defence|bharat\s*22|fof|reform"),
]
def infer_category(name):
    n = (name or "").lower()
    for label, pat in CATEGORY_RULES:
        if re.search(pat, n):
            return label
    return "Other Equity"

def infer_amc(name):
    n = (name or "").strip()
    for amc in ["HDFC", "ICICI Prudential", "ICICI", "SBI", "DSP", "Nippon India", "Mirae Asset",
                "Invesco India", "Invesco", "Quant", "UTI", "Kotak", "Parag Parikh", "Axis",
                "ITI", "Edelweiss"]:
        if n.upper().startswith(amc.upper()):
            return amc
    return n.split()[0] if n else "—"

# ==================================================
# PILLAR SCORING — every pillar traces to a real number; nothing fabricated.
# Cost is explicitly N/A (no free expense-ratio source found).
# ==================================================
def consistency_score(m):
    vals = [m.get("cagr_1Y"), m.get("cagr_3Y"), m.get("cagr_5Y")]
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return None  # missing history is excluded from the denominator, not a free 10
    spread = (max(vals) - min(vals))
    return float(np.clip(20 - spread * 40, 0, 20))

def performance_score(m):
    c3 = m.get("cagr_3Y")
    if c3 is None:
        return None
    if c3 > 0.18: return 25.0
    if c3 > 0.12: return 20.0
    if c3 > 0.08: return 14.0
    if c3 > 0.04: return 8.0
    return 3.0

def concentration_score(weight_pct):
    # Smaller position in YOUR portfolio = lower single-fund concentration risk
    if weight_pct <= 5: return 15.0
    if weight_pct <= 15: return 11.0
    if weight_pct <= 25: return 6.0
    return 2.0

def risk_adjusted_score(m):
    c3, dd = m.get("cagr_3Y"), m.get("max_drawdown")
    if c3 is None or dd is None or dd == 0:
        return None
    calmar = c3 / abs(dd)
    return float(np.clip(calmar * 8, 0, 10))

def overlap_pillar_score(overlap_pct):
    if overlap_pct is None:
        return None  # unknown — excluded from total, not guessed
    return float(np.clip(20 - overlap_pct * 0.4, 0, 20))

# ==================================================
# HOLDINGS OVERLAP (best-effort; honest empty state if unavailable)
# ==================================================
codes = [r["scheme_code"] for r in ok_results]
holdings_by_code, cache = get_holdings_for_funds(codes, force_refresh=False)

def _is_equity_holding(h):
    """Only real equity positions belong in the stock-overlap analysis."""
    typ = str(h.get("instrument_type") or "").strip().lower()
    if typ:
        return typ in {"equity", "stock", "listed_equity", "equity_share"}
    # Conservative fallback when an old cache has no instrument_type.
    name = str(h.get("name") or "").lower()
    blocked = ("bond", "debenture", "certificate of deposit", "treasury",
               "t-bill", "g-sec", "government security", "commercial paper",
               "money market", "cash", "liquid fund", "etf", "fund of fund")
    return not any(x in name for x in blocked)

def _holding_key(h):
    isin = str(h.get("isin") or "").strip().upper()
    if isin and isin != "-":
        return "ISIN:" + isin
    name = re.sub(r"[^A-Z0-9]", "", str(h.get("name") or "").upper())
    return "NAME:" + name if name else None

# security key -> [(fund_name, weight_in_fund, fund_value, display_name)]
stock_exposure = defaultdict(list)
for r in ok_results:
    code = r["scheme_code"]
    for h in holdings_by_code.get(code, []):
        if not _is_equity_holding(h):
            continue
        key = _holding_key(h)
        weight = h.get("weight")
        if not key or not isinstance(weight, (int, float)) or weight <= 0:
            continue
        stock_exposure[key].append((
            r["fund_name"], float(weight), float(r["current_value"]),
            str(h.get("name") or "—")
        ))

fund_weights = {}
for r in ok_results:
    wmap = {}
    for h in holdings_by_code.get(r["scheme_code"], []):
        if not _is_equity_holding(h):
            continue
        key = _holding_key(h)
        weight = h.get("weight")
        if key and isinstance(weight, (int, float)) and weight > 0:
            wmap[key] = float(weight)
    if wmap:
        fund_weights[r["fund_name"]] = wmap

look_through_rows = family_look_through(stock_exposure, total_value)
concentrated = concentration_flags(look_through_rows)
share_class_pairs = direct_regular_pairs([r["fund_name"] for r in ok_results])
pairwise_rows = pairwise_matrix(fund_weights)

overlap_available = any(len({x[0] for x in apps}) > 1 for apps in stock_exposure.values())
n_disclosed = sum(1 for r in ok_results if holdings_by_code.get(r["scheme_code"]))

# Per-fund overlap = percentage of that fund's disclosed portfolio invested in
# stocks that are also held by at least one other fund in this portfolio.
per_fund_overlap_pct = {}
for r in ok_results:
    code = r["scheme_code"]
    hlist = holdings_by_code.get(code, [])
    if not hlist:
        per_fund_overlap_pct[code] = None
        continue
    overlapped_keys = {k for k, apps in stock_exposure.items()
                       if len({x[0] for x in apps}) > 1}
    overlap_weight = 0.0
    seen_keys = set()
    for h in hlist:
        if not _is_equity_holding(h):
            continue
        key = _holding_key(h)
        weight = h.get("weight")
        if key in overlapped_keys and key not in seen_keys and isinstance(weight, (int, float)):
            overlap_weight += float(weight)
            seen_keys.add(key)
    per_fund_overlap_pct[code] = overlap_weight

# Portfolio overlap is based on YOUR actual MF allocation, not the average of fund percentages.
# This prevents a small liquid fund and a large equity fund from having equal influence.
overlap_user_value = 0.0
if overlap_available and total_value > 0:
    for key, apps in stock_exposure.items():
        if len({x[0] for x in apps}) < 2:
            continue
        for fund_name, weight, fund_value, _display_name in apps:
            overlap_user_value += fund_value * (weight / 100.0)
    portfolio_overlap_pct = float(np.clip(overlap_user_value / total_value * 100.0, 0, 100))
else:
    portfolio_overlap_pct = None

def overlap_badge(pct):
    if pct is None:
        return "—", ""
    if pct < 10: return "Low", "badge-low"
    if pct < 30: return "Moderate", "badge-mod"
    if pct < 45: return "High", "badge-high"
    return "Very High", "badge-vhigh"

# ==================================================
# ASSEMBLE PER-FUND SCORES
# ==================================================
rows = []
for r in ok_results:
    m = r["metrics"]
    code = r["scheme_code"]
    ov_pct = per_fund_overlap_pct.get(code)
    perf = performance_score(m)
    cons = consistency_score(m)
    conc = concentration_score(r["weight_pct"])
    risk = risk_adjusted_score(m)
    ov_score = overlap_pillar_score(ov_pct)

    scored = []
    max_parts = []
    for part, cap in ((perf, 25), (cons, 20), (conc, 15), (risk, 10), (ov_score, 20)):
        if part is None:
            continue
        scored.append(part)
        max_parts.append(cap)
    denom = sum(max_parts)
    total_100 = (sum(scored) / denom * 100) if denom else 0

    label, cls = overlap_badge(ov_pct)
    rows.append({
        "Fund": r["fund_name"], "AMC": infer_amc(r["fund_name"]),
        "Category": infer_category(r["fund_name"]),
        "1Y": m.get("cagr_1Y"), "3Y": m.get("cagr_3Y"), "5Y": m.get("cagr_5Y"),
        "Weight %": r["weight_pct"], "Value": r["current_value"],
        "Score": round(total_100), "OverlapPct": ov_pct,
        "OverlapLabel": label, "OverlapCls": cls,
        "_perf": perf, "_cons": cons, "_conc": conc, "_risk": risk, "_ov": ov_score,
    })
df = pd.DataFrame(rows).sort_values("Weight %", ascending=False)

overall_health = round(df["Score"].mean())
top5_weight = df.nlargest(5, "Weight %")["Weight %"].sum()
n_families = int(df["AMC"].nunique())

def score_bucket(s):
    if s >= 80: return "Excellent", "sc-excellent"
    if s >= 60: return "Good", "sc-good"
    if s >= 40: return "Average", "sc-average"
    return "Poor", "sc-poor"

def conc_bucket(top5):
    if top5 < 35: return "Low", "#4ade80"
    if top5 < 55: return "Moderate", "#fbbf24"
    return "High", "#f87171"

conc_label, conc_color = conc_bucket(top5_weight)

# ==================================================
# HEALTH AT A GLANCE (portfolio-first)
# ==================================================
st.markdown(section_header_html("Health at a glance", "portfolio"), unsafe_allow_html=True)

def _holdings_as_of_label():
    """Use committed holdings-meta as_of when present. Never invent today's date."""
    try:
        if not HOLDINGS_META_CACHE.exists():
            return None, None
        meta = json.loads(HOLDINGS_META_CACHE.read_text(encoding="utf-8"))
        dates = sorted({
            str(v.get("as_of"))[:10] for v in meta.values()
            if isinstance(v, dict) and v.get("as_of")
        })
        pulled = sorted({
            str(v.get("retrieved_at"))[:10] for v in meta.values()
            if isinstance(v, dict) and v.get("retrieved_at")
        })
        as_of = dates[-1] if dates else None
        if dates and dates[0] != dates[-1]:
            as_of = f"{dates[0]} to {dates[-1]}"
        retrieved = pulled[-1] if pulled else None
        return as_of, retrieved
    except Exception:
        return None, None


_as_of, _retrieved = _holdings_as_of_label()
_as_of_pill = (f"Holdings disclosed as of {_as_of}" if _as_of
               else "Holdings as-of unknown (no meta cache)")
_pulled_pill = (f"Last pulled {_retrieved}" if _retrieved else None)

b_label, _ = score_bucket(overall_health)
ov_txt = f"{portfolio_overlap_pct:.0f}%" if portfolio_overlap_pct is not None else "N/A"
ov_lbl, ov_cls = overlap_badge(portfolio_overlap_pct)
_ov_tone = {"": "", "badge-low": "up", "badge-mod": "", "badge-high": "warn", "badge-vhigh": "warn"}.get(ov_cls, "")
_conc_tone = {"Low": "up", "Moderate": "warn", "High": "down"}.get(conc_label, "")
k_cards = [
    {"label": "MF book value", "value": format_inr_compact(total_value),
     "sub": "sum of positions; unique schemes after merge"},
    {"label": "Positions / schemes", "value": f"{n_positions} / {n_schemes}",
     "sub": f"{n_families} fund families (AMCs)"},
    {"label": "Illustrative health index", "value": f"{overall_health}/100",
     "sub": "rescaled over scored pillars · cost excluded · missing ≠ 0",
     "tone": "up" if b_label == "Excellent" else ("warn" if b_label == "Good" else "down")},
    {"label": "Portfolio Overlap", "value": ov_txt, "sub": ov_lbl, "tone": _ov_tone},
    {"label": "Concentration Risk", "value": conc_label, "sub": f"Top 5 schemes: {top5_weight:.1f}% of MF book",
     "tone": _conc_tone},
]
st.markdown(kpi_cards(k_cards, cols=5), unsafe_allow_html=True)
st.markdown(
    '<div class="t-meta-row">'
    + pill(_as_of_pill, "info")
    + (pill(_pulled_pill, "neutral") if _pulled_pill else "")
    + pill(f"{n_positions} positions · {n_schemes} unique schemes · {n_families} AMCs", "neutral")
    + pill(f"overlap coverage {n_disclosed}/{n_schemes} schemes disclosed", "neutral")
    + pill("score /100 rescaled over scored pillars — cost excluded (no expense-ratio source)", "stale")
    + '</div>',
    unsafe_allow_html=True,
)
st.markdown(caption(
    f"Overlap coverage: {n_disclosed}/{n_schemes} schemes have disclosed holdings. "
    "Funds without disclosure sit in the portfolio-overlap denominator as unique "
    "(zero overlapped rupees). 1Y / 3Y / 5Y are trailing CAGR via "
    "trailing_return(hist, years) with years × 365.25 from the latest NAV — "
    "not the roster Return %. "
    "as_of is the AMC statutory filing date, not when this desk last pulled. "
    "SEBI monthly books are due by the 10th of the next month; this page never invents a later book."
), unsafe_allow_html=True)

# ==================================================
# BREAKDOWN RADAR + OVERLAP DONUT + TOP OVERLAPPED STOCKS
# ==================================================
c1, c2, c3 = st.columns([1.1, 0.9, 1.3])

with c1:
    st.markdown(section_header_html("Health breakdown", meta="pillar averages across funds"),
                unsafe_allow_html=True)
    pillars = ["Performance\n(25)", "Consistency\n(20)", "Concentration\n(15)", "Risk Adjusted\n(10)"]
    vals = [df["_perf"].mean(), df["_cons"].mean(), df["_conc"].mean(), df["_risk"].mean()]
    if df["_ov"].notna().any():
        pillars.append("Overlap\n(20)")
        vals.append(df["_ov"].mean())
    fig = go.Figure(go.Scatterpolar(r=vals + [vals[0]], theta=pillars + [pillars[0]],
                                     fill="toself", line_color="#22c55e", fillcolor="rgba(34,197,94,0.18)"))
    fig.update_layout(
        polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(visible=True, showticklabels=False, gridcolor="#1c2333"),
                   angularaxis=dict(gridcolor="#1c2333", color="#8b95a8")),
        showlegend=False, height=280, margin=dict(t=20, b=20, l=40, r=40),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    if not df["_ov"].notna().any():
        st.markdown(caption("Overlap pillar excluded — holdings data unavailable this run."), unsafe_allow_html=True)
    st.markdown(caption("Cost pillar not shown — no free source for per-fund expense ratio."), unsafe_allow_html=True)

with c2:
    st.markdown(section_header_html("Portfolio overlap", meta="across disclosed holdings"),
                unsafe_allow_html=True)
    if portfolio_overlap_pct is not None:
        fig2 = go.Figure(go.Pie(
            values=[portfolio_overlap_pct, 100 - portfolio_overlap_pct],
            labels=["Overlapped exposure", "Unique exposure"], hole=0.68,
            marker_colors=["#eab308", "#22c55e"], textinfo="none",
        ))
        fig2.update_layout(
            height=230, showlegend=True, legend=dict(orientation="h", y=-0.15, font=dict(size=10, color="#c2c9d6")),
            margin=dict(t=10, b=10, l=10, r=10), paper_bgcolor="rgba(0,0,0,0)",
            annotations=[dict(text=f"{portfolio_overlap_pct:.0f}%<br>Overlap", x=0.5, y=0.5,
                               font_size=15, showarrow=False, font_color="#f8fafc")],
        )
        st.plotly_chart(fig2, width="stretch", config={"displayModeBar": False})
    else:
        st.markdown(empty_state(
            "No holdings data cached",
            "Holdings come from the holdings refresh on the Command Center.",
            hint="Command Center → Intelligence → Refresh holdings",
        ), unsafe_allow_html=True)

with c3:
    st.markdown(section_header_html("Top overlapped stocks · equity only",
                                    meta=f"{df['AMC'].nunique()} fund families · disclosed holdings"),
                unsafe_allow_html=True)
    if overlap_available:
        rows2 = []
        for key, apps in stock_exposure.items():
            fund_count = len({x[0] for x in apps})
            if fund_count < 2:
                continue
            total_exp = sum(fv * (w / 100.0) for _, w, fv, _ in apps)
            display_name = max(apps, key=lambda x: x[1])[3]
            rows2.append({"Stock": display_name, "In Funds": fund_count,
                          "Total Exposure": total_exp, "% of MF Portfolio": total_exp / total_value * 100})
        if rows2:
            top_df = pd.DataFrame(rows2).sort_values(
                ["In Funds", "Total Exposure"], ascending=[False, False]
            ).head(5)
            for _, rr in top_df.iterrows():
                st.markdown(
                    f"<div class='t-list-row'>"
                    f"<span class='t-list-name'>{rr['Stock']}</span>"
                    f"<span class='t-list-meta'>{int(rr['In Funds'])} funds · {format_inr_compact(rr['Total Exposure'])} · {rr['% of MF Portfolio']:.1f}%</span>"
                    f"</div>", unsafe_allow_html=True)
        else:
            st.markdown(caption("No stock appears in more than one fund yet."), unsafe_allow_html=True)
    else:
        st.markdown(caption("Holdings data unavailable — cache is empty and mfdata.in hasn't returned data. "
                       "As a manual check meanwhile, try overlapiq.in with your fund list."), unsafe_allow_html=True)
    force = st.button("Refresh holdings now (once an hour)", width="stretch")
    if force:
        last = float(st.session_state.get("mf_holdings_refresh_ts") or 0)
        if time.time() - last < 3600:
            st.warning("Holdings refresh is capped at once an hour so we do not lock the statutory feed.")
        else:
            st.session_state["mf_holdings_refresh_ts"] = time.time()
            get_holdings_for_funds(codes, force_refresh=True)
            st.rerun()

# ==================================================
# BOOKS AT A GLANCE — category / AMC / look-through / pairwise
# All figures are disclosed or observed. Empty when the cache has no data.
# ==================================================
def _plot(fig, height=280, legend=False):
    layout = dict(PLOTLY_LAYOUT)
    layout.update(height=height, showlegend=legend, margin=dict(t=24, b=24, l=16, r=16))
    fig.update_layout(**layout)
    return fig


st.markdown(section_header_html("Books at a glance", "category · AMC · look-through"),
            unsafe_allow_html=True)
st.markdown(caption(LOOKTHROUGH_METHOD), unsafe_allow_html=True)

g1, g2 = st.columns(2)
with g1:
    cat_sum = df.groupby("Category", as_index=False)["Value"].sum().sort_values("Value", ascending=False)
    if not cat_sum.empty:
        fig_cat = go.Figure(go.Pie(
            labels=cat_sum["Category"], values=cat_sum["Value"], hole=0.58,
            textinfo="label+percent", textposition="inside",
        ))
        fig_cat.update_layout(title=dict(text="Category mix · by current value", font=dict(size=13)))
        st.plotly_chart(_plot(fig_cat, legend=True), width="stretch", config={"displayModeBar": False})
        st.markdown(caption("Category is inferred from the fund name / AMFI title — a proxy, not SEBI official."),
                    unsafe_allow_html=True)
    else:
        st.markdown(caption("No category mix to draw."), unsafe_allow_html=True)
with g2:
    amc_sum = df.groupby("AMC", as_index=False)["Value"].sum().sort_values("Value", ascending=False)
    if not amc_sum.empty:
        fig_amc = go.Figure(go.Pie(
            labels=amc_sum["AMC"], values=amc_sum["Value"], hole=0.58,
            textinfo="label+percent", textposition="inside",
        ))
        fig_amc.update_layout(title=dict(text="AMC mix · by current value", font=dict(size=13)))
        st.plotly_chart(_plot(fig_amc, legend=True), width="stretch", config={"displayModeBar": False})
    else:
        st.markdown(caption("No AMC mix to draw."), unsafe_allow_html=True)

g3, g4 = st.columns(2)
with g3:
    st.markdown(section_header_html("3Y trailing CAGR vs Nifty50", "scheme path, not your XIRR"),
                unsafe_allow_html=True)
    perf = df.dropna(subset=["3Y"]).copy()
    nifty_3y_pct = next(
        (row.get("vs Nifty50 3Y") for row in mf_list if row.get("vs Nifty50 3Y") is not None),
        None,
    )
    if not perf.empty:
        perf = perf.sort_values("3Y", ascending=True)
        fig_bar = go.Figure(go.Bar(
            x=perf["3Y"] * 100.0, y=perf["Fund"], orientation="h",
            marker_color="#8fa4c4", name="Fund 3Y",
        ))
        if nifty_3y_pct is not None:
            fig_bar.add_vline(
                x=float(nifty_3y_pct), line_dash="dot", line_color="#d4a054",
                annotation_text=f"Nifty50 3Y {float(nifty_3y_pct):.1f}%",
                annotation_position="top",
            )
        fig_bar.update_layout(xaxis_title="Trailing 3Y CAGR %")
        st.plotly_chart(_plot(fig_bar, height=max(280, 22 * len(perf))), width="stretch",
                        config={"displayModeBar": False})
        st.markdown(caption(
            TRAILING_CAGR_LABEL + " Nifty50 is a broad equity bar, not each fund's official benchmark. "
            "'—' funds have too little NAV history or are debt-like."),
            unsafe_allow_html=True)
    else:
        st.markdown(caption("No 3Y trailing CAGR in this run — open Command Center so scheme history is computed."),
                    unsafe_allow_html=True)
with g4:
    st.markdown(section_header_html("Look-through · top companies", "family rupees through funds"),
                unsafe_allow_html=True)
    if look_through_rows:
        top_lt = look_through_rows[:8]
        fig_lt = go.Figure(go.Bar(
            x=[r["exposure_inr"] for r in top_lt],
            y=[r["name"][:28] for r in top_lt],
            orientation="h", marker_color="#5b9eaa",
            customdata=[[r["n_funds"], r["pct_of_mf"]] for r in top_lt],
            hovertemplate="%{y}<br>₹%{x:,.0f}<br>%{customdata[0]} funds · %{customdata[1]:.1f}% of MF book<extra></extra>",
        ))
        fig_lt.update_layout(yaxis=dict(autorange="reversed"), xaxis_title="Family exposure (INR)")
        st.plotly_chart(_plot(fig_lt, height=max(280, 24 * len(top_lt))), width="stretch",
                        config={"displayModeBar": False})
        st.markdown(caption(
            f"Top {len(top_lt)} of {len(look_through_rows)} disclosed names. "
            "Bar = family rupees through funds; hover % is of the MF book, not total assets. "
            "A stock in several funds is one family exposure, not several."),
            unsafe_allow_html=True)
    else:
        st.markdown(caption("No look-through yet — holdings cache empty for these scheme codes."),
                    unsafe_allow_html=True)

st.markdown(section_header_html("Pairwise fund overlap", "min-weight, disclosed equity"),
            unsafe_allow_html=True)
st.markdown(caption(OVERLAP_METHOD), unsafe_allow_html=True)
if len(fund_weights) >= 2:
    labels = sorted(fund_weights)
    short = [(n if len(n) <= 22 else n[:21] + "…") for n in labels]
    z = []
    for a in labels:
        row = []
        for b in labels:
            if a == b:
                row.append(100.0)
            else:
                pct = pairwise_overlap_pct(fund_weights[a], fund_weights[b])
                row.append(pct if pct is not None else 0.0)
        z.append(row)
    fig_hm = go.Figure(go.Heatmap(
        z=z, x=short, y=short, colorscale="Tealgrn", zmin=0, zmax=60,
        hovertemplate="%{y} × %{x}<br>%{z:.1f}% of disclosed fund weights<extra></extra>",
        colorbar=dict(title="%"),
    ))
    st.plotly_chart(_plot(fig_hm, height=max(320, 18 * len(labels)), legend=False),
                    width="stretch", config={"displayModeBar": False})
    if pairwise_rows:
        hottest = sorted(pairwise_rows, key=lambda t: -t[2])[:5]
        for a, b, pct in hottest:
            st.markdown(
                f"<div class='t-list-row'><span class='t-list-name'>{a[:32]} × {b[:32]}</span>"
                f"<span class='t-list-meta'>{pct:.1f}% common disclosed weight</span></div>",
                unsafe_allow_html=True)
    st.markdown(caption(
        "Read as exposure, not an order. Two funds sharing ~N% of holdings may still "
        "earn their keep if style or AMC differs."),
        unsafe_allow_html=True)
else:
    st.markdown(caption("Need at least two disclosed equity funds to draw pairwise overlap."),
                unsafe_allow_html=True)

st.markdown(section_header_html("Single-stock concentration",
                                f"flag ≥ {CONCENTRATION_THRESHOLD_PCT:.0f}% of the MF book"),
            unsafe_allow_html=True)
if concentrated:
    for r in concentrated[:8]:
        st.markdown(
            f"<div class='t-list-row'><span class='t-list-name'>{r['name']}</span>"
            f"<span class='t-list-meta'>{r['n_funds']} funds · {format_inr_compact(r['exposure_inr'])} · "
            f"{r['pct_of_mf']:.1f}% of MF book</span></div>",
            unsafe_allow_html=True)
    st.markdown(caption(
        "Threshold is a fact flag on this family's MF book, not a sell rule. "
        "Direct stock holdings in the Stocks sleeve are a separate line — they are not added here."),
        unsafe_allow_html=True)
else:
    st.markdown(caption(
        f"No disclosed name is ≥ {CONCENTRATION_THRESHOLD_PCT:.0f}% of the MF book this run, "
        "or look-through coverage is empty."),
        unsafe_allow_html=True)

if share_class_pairs:
    st.markdown(section_header_html("Direct and Regular of the same scheme", "cost fact"),
                unsafe_allow_html=True)
    for stem, direct, regular in share_class_pairs:
        st.markdown(
            f"<div class='t-list-row'><span class='t-list-name'>{stem}</span>"
            f"<span class='t-list-meta'>Direct {len(direct)} · Regular {len(regular)}</span></div>",
            unsafe_allow_html=True)
    st.markdown(caption(DIRECT_REGULAR_NOTE), unsafe_allow_html=True)

sector_inr = defaultdict(float)
for r in ok_results:
    for h in holdings_by_code.get(r["scheme_code"], []):
        sec = str(h.get("sector") or "").strip()
        w = h.get("weight")
        if not sec or not isinstance(w, (int, float)) or w <= 0:
            continue
        sector_inr[sec] += float(r["current_value"]) * float(w) / 100.0
if sector_inr:
    st.markdown(section_header_html("Look-through sector mix", "only where the disclosure carries a sector tag"),
                unsafe_allow_html=True)
    items = sorted(sector_inr.items(), key=lambda kv: -kv[1])
    fig_sec = go.Figure(go.Pie(
        labels=[k for k, _ in items], values=[v for _, v in items], hole=0.58,
        textinfo="label+percent",
    ))
    st.plotly_chart(_plot(fig_sec, legend=True), width="stretch", config={"displayModeBar": False})
else:
    st.markdown(caption(
        "This holdings cache does not carry sector tags on the disclosed names — "
        "sector mix is no data, not zero."),
        unsafe_allow_html=True)

with st.expander("What these return numbers mean"):
    st.markdown(caption(SIMPLE_ROI_LABEL), unsafe_allow_html=True)
    st.markdown(caption(LUMP_SUM_ANN_LABEL), unsafe_allow_html=True)
    st.markdown(caption(TRAILING_CAGR_LABEL), unsafe_allow_html=True)
    st.markdown(caption(MULTI_CASHFLOW_XIRR_GAP), unsafe_allow_html=True)
    st.markdown(caption(
        "Rolling N-year CAGR is the scheme NAV measured on many end-dates. "
        "It is not computed here because this page does not keep a NAV series in session. "
        "Trailing 1Y / 3Y / 5Y above is the latest window of that path."),
        unsafe_allow_html=True)

# ==================================================
# SEARCHABLE / FILTERABLE FUND TABLE
# ==================================================
st.markdown(section_header_html("Fund details — secondary analysis",
                                meta="searchable · category/AMC filter · list or family view"),
            unsafe_allow_html=True)

_exp, _btn = st.columns([5, 1])
with _btn:
    st.download_button("Export CSV",
                       df.drop(columns=[c for c in df.columns if c.startswith("_")]).to_csv(index=False),
                       "mf_health.csv", "text/csv")

fc1, fc2, fc3, fc4 = st.columns([2, 1, 1, 1])
with fc1:
    search = st.text_input("Search fund / AMC / Category", "", label_visibility="collapsed",
                            placeholder="Search fund / AMC / Category")
with fc2:
    cat_filter = st.selectbox("Category", ["All Categories"] + sorted(df["Category"].unique().tolist()))
with fc3:
    amc_filter = st.selectbox("AMC", ["All AMCs"] + sorted(df["AMC"].unique().tolist()))
with fc4:
    view = st.radio("View", ["List View", "Family View"], horizontal=True, label_visibility="collapsed")

fdf = df.copy()
if search:
    s = search.lower()
    fdf = fdf[fdf["Fund"].str.lower().str.contains(s) | fdf["AMC"].str.lower().str.contains(s)
              | fdf["Category"].str.lower().str.contains(s)]
if cat_filter != "All Categories":
    fdf = fdf[fdf["Category"] == cat_filter]
if amc_filter != "All AMCs":
    fdf = fdf[fdf["AMC"] == amc_filter]

def render_table(data):
    def fmt(v):
        return f"{v*100:.1f}%" if v is not None else "—"

    disp = pd.DataFrame({
        "Fund": data["Fund"],
        "AMC": data["AMC"].map(lambda a: f"{a} Mutual Fund"),
        "Category": data["Category"],
        "1Y": data["1Y"].map(fmt),
        "3Y": data["3Y"].map(fmt),
        "5Y": data["5Y"].map(fmt),
        "Health Score": data["Score"],
        "Overlap": [
            (f"{lbl} · {pct:.1f}%" if pct is not None else "—")
            for lbl, pct in zip(data["OverlapLabel"], data["OverlapPct"])
        ],
    })
    st.dataframe(
        disp,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Health Score": st.column_config.ProgressColumn(
                "Health Score", min_value=0, max_value=100, format="%d",
            ),
        },
    )

if view == "List View":
    render_table(fdf)
else:
    for amc, grp in fdf.groupby("AMC"):
        with st.expander(f"{amc} Mutual Fund · {len(grp)} fund(s) · avg score {grp['Score'].mean():.0f}"):
            render_table(grp)

st.markdown("---")
lc1, lc2, lc3 = st.columns(3)
lc1.markdown("**How we calculate the illustrative health index**")
lc1.markdown(caption(
    "Each scheme: Performance 25 + Consistency 20 + Concentration 15 + Risk Adjusted 10 "
    "+ Overlap 20 when disclosures exist. The sum is rescaled to /100 over that scheme’s "
    "available denominator (70 without overlap, 90 with). Cost / expense ratio is not a "
    "pillar and is never filled with zero — there is no free source. Portfolio score is "
    "the unweighted mean of scheme scores."), unsafe_allow_html=True)
lc2.markdown("**Overlap Impact**")
lc2.markdown(caption(
    "Per-fund overlap = sum of that fund's disclosed equity weights that also appear "
    "in another family fund (denominator = that fund's disclosed portfolio weights). "
    "Portfolio overlap = overlapped ₹ / total MF book; undisclosed funds sit in the "
    "denominator as unique. Shown only when holdings data is available. Math unchanged."),
             unsafe_allow_html=True)
lc3.markdown("**Score scale**")
lc3.markdown(caption("80–100 Excellent · 60–79 Good · 40–59 Average · 0–39 Poor — text labels are the signal; colour only repeats them."),
             unsafe_allow_html=True)

st.markdown(footnote("Mutual fund investments are subject to market risks. Past performance is not indicative of future returns."),
            unsafe_allow_html=True)
