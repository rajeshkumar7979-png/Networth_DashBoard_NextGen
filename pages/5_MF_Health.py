import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from collections import defaultdict
from datetime import datetime
from lib.mf_health import analyze_fund, get_holdings_for_funds
from lib.theme import inject_css
from lib.ui import (
    page_header_html,
    section_header_html,
    pill,
    kpi_cards,
    empty_state,
    caption,
    banner,
    footnote,
)

st.set_page_config(page_title="MF Health", page_icon="🛡️", layout="wide")

# ==================================================
# INSTITUTIONAL DARK THEME — one shared stylesheet (lib.theme)
# ==================================================
inject_css()

# ==================================================
# LOAD FUNDS FROM COMMAND CENTER (unchanged data path)
# ==================================================
st.page_link("pages/1_Command_Center.py", label="← Command Center", icon="📊")

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
    raw_results.append(analyze_fund(
        name, value, weight, scheme_code,
        cagr_1y=row.get("1Y %"), cagr_3y=row.get("3Y %"), cagr_5y=row.get("5Y %"),
        latest_nav=row.get("Current NAV"),
    ))

by_code = {}
for r in raw_results:
    code = r.get("scheme_code")
    if not code:
        continue
    prev = by_code.get(code)
    if prev is None or r.get("weight_pct", 0) > prev.get("weight_pct", 0):
        by_code[code] = r

ok_results = [r for r in by_code.values() if r["status"] == "ok"]
if not ok_results:
    st.markdown(banner("No funds with usable data yet — scheme codes or cached values are missing.", "warning"),
                unsafe_allow_html=True)
    st.stop()

total_value = sum(r["current_value"] for r in ok_results)

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
        return 10.0  # neutral — not enough history to judge either way
    spread = (max(vals) - min(vals))
    return float(np.clip(20 - spread * 40, 0, 20))

def performance_score(m):
    c3 = m.get("cagr_3Y")
    if c3 is None:
        return 12.5
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
        return 5.0
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

overlap_available = any(len({x[0] for x in apps}) > 1 for apps in stock_exposure.values())

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

    parts = [perf, cons, conc, risk] + ([ov_score] if ov_score is not None else [])
    max_parts = [25, 20, 15, 10] + ([20] if ov_score is not None else [])
    total_100 = sum(parts) / sum(max_parts) * 100

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
# HEADER — portfolio health first
# ==================================================
st.markdown(page_header_html(
    "Mutual fund portfolio health",
    "MF Health",
    "Portfolio-level health first — score, overlap, concentration — then fund-level "
    "detail · every pillar traces to a disclosed or observed number",
), unsafe_allow_html=True)

c_title, c_export = st.columns([5, 1])
with c_export:
    st.download_button("⬇ Export", df.drop(columns=[c for c in df.columns if c.startswith("_")]).to_csv(index=False),
                        "mf_health.csv", "text/csv", width="stretch")

st.markdown(
    '<div class="t-meta-row">'
    + pill(f"{len(df)} funds", "info")
    + pill(f"{df['AMC'].nunique()} fund families", "neutral")
    + pill("cost not scored — no free expense-ratio source", "stale")
    + '</div>',
    unsafe_allow_html=True,
)
st.caption(f"Data as of {datetime.now().strftime('%d %b %Y')} · Based on {len(df)} unique funds "
           f"· loaded from the Command Center run")
st.markdown("---")

st.markdown(section_header_html("Health at a glance", "portfolio"), unsafe_allow_html=True)

b_label, _ = score_bucket(overall_health)
ov_txt = f"{portfolio_overlap_pct:.0f}%" if portfolio_overlap_pct is not None else "N/A"
ov_lbl, ov_cls = overlap_badge(portfolio_overlap_pct)
_ov_tone = {"": "", "badge-low": "up", "badge-mod": "", "badge-high": "warn", "badge-vhigh": "warn"}.get(ov_cls, "")
_conc_tone = {"Low": "up", "Moderate": "warn", "High": "down"}.get(conc_label, "")
k_cards = [
    {"label": "MF Portfolio Value", "value": f"₹{total_value/1e7:.2f} Cr", "sub": "of total net worth"},
    {"label": "No. of Funds", "value": f"{len(df)}", "sub": f"{df['AMC'].nunique()} fund families"},
    {"label": "MF Health Score", "value": f"{overall_health}/100", "sub": b_label,
     "tone": "up" if b_label == "Excellent" else ("warn" if b_label == "Good" else "down")},
    {"label": "Portfolio Overlap", "value": ov_txt, "sub": ov_lbl, "tone": _ov_tone},
    {"label": "Concentration Risk", "value": conc_label, "sub": f"Top 5 funds: {top5_weight:.1f}%",
     "tone": _conc_tone},
]
st.markdown(kpi_cards(k_cards, cols=5), unsafe_allow_html=True)

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
                    f"<span class='t-list-meta'>{rr['In Funds']} funds · ₹{rr['Total Exposure']/1e5:.1f}L · {rr['% of MF Portfolio']:.1f}%</span>"
                    f"</div>", unsafe_allow_html=True)
        else:
            st.markdown(caption("No stock appears in more than one fund yet."), unsafe_allow_html=True)
    else:
        st.markdown(caption("Holdings data unavailable — cache is empty and mfdata.in hasn't returned data. "
                       "As a manual check meanwhile, try overlapiq.in with your fund list."), unsafe_allow_html=True)
    force = st.button("🔄 Refresh holdings now (may be slow)", width="stretch")
    if force:
        get_holdings_for_funds(codes, force_refresh=True)
        st.rerun()

# ==================================================
# SEARCHABLE / FILTERABLE FUND TABLE
# ==================================================
st.markdown(section_header_html("Fund details — secondary analysis",
                                meta="searchable · category/AMC filter · list or family view"),
            unsafe_allow_html=True)

fc1, fc2, fc3, fc4 = st.columns([2, 1, 1, 1])
with fc1:
    search = st.text_input("🔍 Search fund / AMC / Category", "", label_visibility="collapsed",
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
lc1.markdown("**How we calculate MF Health Score**")
lc1.markdown(caption("Performance (25) · Consistency (20) · Overlap (20, when available) · Concentration (15) · Risk Adjusted (10). "
                     "Cost (expense ratio) is not scored — no free per-fund data source found."), unsafe_allow_html=True)
lc2.markdown("**Overlap Impact**")
lc2.markdown(caption("Share of a fund's disclosed holdings that also appear in your other funds. Shown only when holdings data is available."),
             unsafe_allow_html=True)
lc3.markdown("**Score scale**")
lc3.markdown(caption("80–100 Excellent · 60–79 Good · 40–59 Average · 0–39 Poor — text labels are the signal; colour only repeats them."),
             unsafe_allow_html=True)

st.markdown(footnote("Mutual fund investments are subject to market risks. Past performance is not indicative of future returns."),
            unsafe_allow_html=True)
