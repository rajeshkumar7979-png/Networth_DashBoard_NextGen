# ==================================================
# INTELLIGENCE — read-only synthesis desk (SPEC §4, R-3300+).
#
# Renders, network-free, the intelligence the Command Center already computed
# on its run: the deterministic briefing (facts+signals), the evidence-based
# research brief (changes, risks, research needs, gaps), the portfolio-aware
# live cohort (cached news/gateway records), gateway cache status and a compact
# look-through snapshot. This page NEVER re-computes valuation and NEVER calls
# the network; if the session has no Command Center data yet it says so plainly.
#
# Nothing here is an order. AI never runs on page load.
# ==================================================
import streamlit as st
from datetime import datetime
import html as _html
import pytz
import pandas as pd

from lib import theme
from lib.formatters import format_inr_compact
from lib.intelligence import exposure as intel_exposure
from lib.intelligence import live as intel_live
from lib.intelligence.sources import mapping as intel_mapping
from lib.ui import (
    caption as ui_caption,
    empty_state as ui_empty,
    nav_shell as ui_nav,
    page_header_html as ui_page_header,
    pill as ui_badge,
    research_grid as ui_research_grid,
    research_row as ui_research_row,
    section_header_html as ui_section,
    status_pill as ui_pill,
    unavailable as ui_unavailable,
    watchlist as ui_watch,
)
from lib.register import build_asset_register

theme.inject_css()

IST = pytz.timezone("Asia/Kolkata")
NOW_IST = datetime.now(IST)

ui_nav("intelligence")
st.markdown(ui_page_header(
    "Northline · Family desk",
    "Intelligence",
    "What the evidence says — fixed, evidence-backed signals from this run. Read-only. Nothing here is an order.",
    meta=[
        f"AS OF {NOW_IST.strftime('%d %b %Y, %H:%M IST')}",
        "READ-ONLY SYNTHESIS",
        "NO NETWORK THIS RUN",
    ],
), unsafe_allow_html=True)

_briefing = st.session_state.get("cc_intel_briefing")
_research = st.session_state.get("cc_research_brief")
_snapshot = st.session_state.get("cc_intel_snapshot")
_gw_rows = st.session_state.get("cc_intel_gateway_status") or []
_cohort = st.session_state.get("cc_live_cohort")
_rates = st.session_state.get("cc_rates") or {}
_live_result = st.session_state.get("cc_live_result")

if _briefing is None and _research is None and _snapshot is None:
    st.markdown(ui_empty(
        "Intelligence hasn't been computed in this session yet.",
        "The Command Center builds the briefing, research brief and evidence cohort when it runs.",
        "Open Command Center once, then return to this page — nothing here ever calls the network.",
    ), unsafe_allow_html=True)
    st.stop()


# ==================================================
# A — POSTURE (aggregate readout)
# ==================================================
st.markdown(ui_section("Posture", "evidence & signals"), unsafe_allow_html=True)

# Count signals from the briefing itself (canonical). Snapshot is a compact
# handoff that can lag or omit 'watch' keys — never use it as the raised count.
_all_sigs = list(getattr(_briefing, "signals", ()) or ()) if _briefing is not None else []
_sig_raised = [s for s in _all_sigs if getattr(s, "level", "info") in ("critical", "warn", "watch")]
_sig_info = [s for s in _all_sigs if getattr(s, "level", "info") == "info"]

_posture = []
_coverage_pct = (_snapshot or {}).get("coverage_pct")
_posture.append({
    "label": "Holdings disclosure",
    "value": f"{_coverage_pct:.0f}%" if _coverage_pct is not None else "n/a",
    "sub": "look-through coverage of MF book",
})
if _research is not None:
    _posture.append({
        "label": "Evidence rows",
        "value": f"{_research.evidence_count}",
        "sub": f"{_research.mapped_count} mapped to portfolio",
    })
_posture.append({
    "label": "Signals raised",
    "value": f"{len(_sig_raised)}",
    "sub": "critical / warn / watch — info notes are demoted",
})
_cc_assets = st.session_state.get("cc_assets") or {}
if _cc_assets.get("total_assets"):
    if _cc_assets.get("has_liabilities"):
        _posture.append({
            "label": "Net worth",
            "value": format_inr_compact(_cc_assets.get("net_worth")),
            "sub": f"Total assets {format_inr_compact(_cc_assets.get('total_assets'))} − session liabilities",
        })
    else:
        _posture.append({
            "label": "Total assets",
            "value": format_inr_compact(_cc_assets.get("total_assets")),
            "sub": "Net worth = total assets (no liabilities recorded)",
        })
if _rates.get("usd_inr") is not None:
    _posture.append({
        "label": "USD/INR",
        "value": f"{_rates['usd_inr']:.2f}",
        "sub": "this run's reference rate",
    })
if _rates.get("gold_10g_inr") is not None:
    _posture.append({
        "label": "Gold ₹/10g",
        "value": f"{_rates['gold_10g_inr']:,.0f}",
        "sub": "India spot",
    })
if _cohort is not None and _cohort.has_records:
    _posture.append({
        "label": "Live cohort",
        "value": f"{_cohort.record_count}",
        "sub": "cached news / gateway records",
    })
if _posture:
    _posture_grid = "".join(
        f'<div class="t-kpi"><div class="t-kpi-label">{_p["label"]}</div>'
        f'<div class="t-kpi-value">{_p["value"]}</div>'
        f'<div class="t-kpi-sub">{_p.get("sub", "")}</div></div>' for _p in _posture)
    st.markdown(f'<div class="t-kpi-grid t-kpi-grid-4">{_posture_grid}</div>',
                unsafe_allow_html=True)


# ==================================================
# B — WHAT MATTERS NOW (raised signals only; info notes demoted)
# ==================================================
st.markdown(ui_section("What matters now", "raised signals only"), unsafe_allow_html=True)

if _sig_raised:
    _watch = []
    for _s in _sig_raised:
        _lv = {"critical": "critical", "warn": "warning", "watch": "warning"}.get(
            getattr(_s, "level", "info"), "warning")
        _until = getattr(_s, "invalidation", "") or "the rule no longer fires"
        _watch.append({
            "level": _lv,
            "title": _s.label,
            "body": _s.message,
            "what": f"Still in force until: {_until}",
        })
    st.markdown(ui_watch(_watch), unsafe_allow_html=True)
else:
    st.markdown(ui_empty(
        "No signals raised this run.",
        "Info-level notes and research questions are listed below — they are not raised signals.",
    ), unsafe_allow_html=True)

_risk_rows = []
_sig_titles = {str(getattr(s, "label", "")).strip().lower() for s in _sig_raised}
if _research is not None:
    for _c in _research.risks:
        if str(_c.title or "").strip().lower() in _sig_titles:
            continue
        if str(getattr(_c, "strength", "")).lower() == "insufficient":
            continue
        _badge = ui_badge(f"STRENGTH {_c.strength.upper()}", "warning")
        _until = _c.invalidation or "the evidence changes"
        _risk_rows.append(ui_research_row(
            title=_c.title,
            badge=_badge,
            meta=f"{len(_c.evidence_ids)} evidence · still in force until: {_until}",
            body=_c.statement,
            tag="RISK",
        ))
    if _research.gaps:
        _gaps = [g for g in _research.gaps if g]
        if _gaps:
            st.caption("Insufficient evidence (never invented): " + " · ".join(_gaps[:6]))

if _risk_rows:
    with st.expander(f"Further research risks ({len(_risk_rows)}) — not counted as raised signals",
                     expanded=False):
        st.markdown(ui_research_grid(_risk_rows), unsafe_allow_html=True)

if _sig_info:
    with st.expander(f"Standing notes ({len(_sig_info)}) — info, not raised", expanded=False):
        for _s in _sig_info:
            _until = getattr(_s, "invalidation", "") or ""
            _meta = f"Still in force until: {_until}" if _until else "info"
            st.markdown(ui_research_row(
                title=_s.label, body=_s.message, meta=_meta, tag="NOTE",
            ), unsafe_allow_html=True)

_questions = []
if _research is not None:
    _questions = list(_research.research_needs)[:4]
if _questions:
    st.markdown("**Decision-support questions** — things worth asking before you move money. Not signals.")
    _q_rows = [ui_research_row(
        title=_q.title,
        badge=ui_badge("QUESTIONS", "info"),
        meta=f"strength {_q.strength} · {len(_q.evidence_ids)} evidence",
        body=_q.statement,
        tag="THINK",
    ) for _q in _questions]
    st.markdown(ui_research_grid(_q_rows), unsafe_allow_html=True)
    st.caption("These are questions, not orders. A decision stays yours.")


# ==================================================
# C — WHAT CHANGED THIS RUN (P&L delta view)
# ==================================================
if _research is not None and _research.changes:
    st.markdown(ui_section("What changed this run", "deterministic delta vs prior snapshot"),
                unsafe_allow_html=True)
    _chg_cards = []
    for _c in _research.changes:
        _amt = _c.amount
        _val = format_inr_compact(_amt) if _amt is not None else "—"
        _tone = "up" if (_amt or 0) > 0 else ("down" if (_amt or 0) < 0 else "neutral")
        _note = _c.note or ""
        if _c.kind == "invested_basis_change" and _c.cashflow_measurement is False:
            _note = "NOT a cash-flow measurement; transaction history unavailable."
        _chg_cards.append({
            "label": _c.label,
            "value": _val,
            "sub": _note,
            "tone": "neutral",
        })
    _changes_grid = "".join(
        f'<div class="t-kpi t-kpi-tall t-kpi-tone-{_c.get("tone", "neutral")}">'
        f'<div class="t-kpi-label">{_c["label"]}</div>'
        f'<div class="t-kpi-value">{_c["value"]}</div>'
        f'<div class="t-kpi-sub">{_c.get("sub", "")}</div></div>' for _c in _chg_cards[:8])
    st.markdown(f'<div class="t-kpi-grid">{_changes_grid}</div>',
                unsafe_allow_html=True)
    st.caption("The invested difference between snapshots is the Invested-Basis Change — "
               "there is no transaction history, so nothing on this page is a flow.")


# ==================================================
# D — PORTFOLIO-LINKED DEVELOPMENTS (cached cohort, exact-match only)
# ==================================================
st.markdown(ui_section("External developments · portfolio-aware", "eligibility by exact match"),
            unsafe_allow_html=True)
_dev_rows = []
try:
    _index = None
    if "cc_books" in st.session_state:
        _books = st.session_state["cc_books"]
        _reg = build_asset_register(_books.get("mf"), _books.get("stocks"),
                                    _books.get("gold"), _books.get("fd"))
        if _reg is not None and len(_reg):
            _index = intel_mapping.build_portfolio_index(
                register=_reg, mf_valid=_books.get("mf"), stocks_valid=_books.get("stocks"),
                gold_valid=_books.get("gold"), fd_valid=_books.get("fd"))
    if _cohort is not None:
        _dev_rows = intel_live.development_rows(_cohort, index=_index, now=NOW_IST)
except Exception:
    _dev_rows = []

if _dev_rows:
    _mapped = [d for d in _dev_rows if d.get("Relevance") == "mapped"]
    _shown = _mapped[:6] or _dev_rows[:6]
    _cards = [ui_research_row(
        title=str(_d.get("Development", "")),
        meta=str(_d.get("Published") or ""),
        body=f'{_d.get("Category")} · {_d.get("Source")}'
             + (f' · affects {_d.get("Affected")}' if _d.get("Affected") != "—" else ""),
        tag="MAPPED" if _d.get("Relevance") == "mapped" else "CONTEXT",
        href=str(_d.get("Link") or ""),
    ) for _d in _shown]
    st.markdown(ui_research_grid(_cards), unsafe_allow_html=True)
    with st.expander(f"Full developments table ({len(_dev_rows)} rows)"):
        import pandas as pd
        st.dataframe(pd.DataFrame(_dev_rows[:20]), hide_index=True, use_container_width=True)
    st.caption("Relevance uses exact identifier matching only — never fuzzy. Records are "
               "observed news / gateway facts; they never alter any number here.")
    if _live_result is not None and _live_result.refreshed_at is not None:
        st.markdown(ui_pill(
            f"last refreshed {_live_result.refreshed_at:%d %b %Y %H:%M} UTC · {_live_result.status}",
            "ok" if _live_result.status == "ok" else "cache"), unsafe_allow_html=True)
else:
    st.markdown(ui_caption(
        "No cached cohort yet. Press 'Refresh research evidence' below — that is the "
        "only moment a network call happens. Nothing else on this page ever hits the "
        "network, re-computes valuation or runs AI."), unsafe_allow_html=True)
    with st.expander("Fetch live research evidence (explicit press only)"):
        st.markdown(ui_caption(
            "No network call happens when this page loads. The single moment a network "
            "call happens is pressing this button."), unsafe_allow_html=True)
        _btn_done = st.button(
            "Refresh research evidence", type="primary", use_container_width=True,
            help="Explicit user action: the only moment this app ever calls the network.")
        if _btn_done:
            _sym_stocks = _books.get("stocks") or () if "cc_books" in dir() else ()
            _sym_funds = _books.get("mf") or () if "cc_books" in dir() else ()
            _sym_gold = _books.get("gold") or () if "cc_books" in dir() else ()
            try:
                with st.spinner("Fetching live research evidence…"):
                    _new_live = intel_live.run_live_research(
                        stock_symbols=_sym_stocks, fund_names=_sym_funds,
                        gold_symbols=_sym_gold, now=NOW_IST)
                st.session_state["cc_live_result"] = _new_live
                st.session_state["cc_live_cohort"] = _new_live.cohort
                st.rerun()
            except Exception as _renew_exc:
                st.warning(f"Refresh unavailable: {_renew_exc}")
    with st.expander("Macro posture (cached gateway facts, network-free)"):
        _macro_gw = _rates.get("usd_inr") or _rates.get("gold_10g_inr")
        if _macro_gw is not None:
            _sub = (f"USD/INR {_rates['usd_inr']:.2f}" if _rates.get("usd_inr")
                    else f"Gold ₹{_rates['gold_10g_inr']:,.0f}/10g")
            st.markdown(ui_pill("cached macro evidence", "ok"), unsafe_allow_html=True)
            st.caption(f"Cached reference rate this run — {_sub}. Read from disk, never fetched here.")
        else:
            st.markdown(ui_pill("no cached macro evidence", "cache"), unsafe_allow_html=True)
            st.caption("Run Command Center once to populate the cached macro posture.")
    with st.expander("AI opt-in interpretation"):
        st.markdown(ui_caption(
            "AI here is strictly opt-in and never runs on page load. If enabled, "
            "interpretation happens only on explicit AI actions in the Command Center."),
            unsafe_allow_html=True)
        _ai_opt_in = st.checkbox(
            "Opt in to AI interpretation", value=False,
            help="Network-free toggle: enabling it never fetches anything and never calls an AI provider here.",
            key="cc_ai_opt_in_intel")
        if _ai_opt_in:
            st.caption("Opt-in recorded. AI interpretation still runs only via the Command Center's "
                       "explicit AI action — never on this page load.")


# ==================================================
# E — RESEARCH SYNTHESIS
# ==================================================
_synth = None
if _research is not None:
    _synth = _research.synthesis
if _synth is not None:
    st.markdown(ui_section("Research synthesis", str(_synth.model)), unsafe_allow_html=True)
    st.markdown(f'<div class="t-card t-card-summary">{_html.escape(str(_synth.summary))}</div>',
                unsafe_allow_html=True)
    if _synth.claims:
        for _cl in _synth.claims:
            st.caption(("✓ " if _cl.supported else "⚠ ") + _cl.text)
else:
    st.markdown(ui_unavailable(
        "Synthesis not computed",
        "The Command Center's research layer must run before a synthesis exists."),
        unsafe_allow_html=True)


# ==================================================
# F — EVIDENCE & PROVENANCE (sources you can check)
# ==================================================
st.markdown(ui_section("Evidence & provenance", "what stands behind each claim"),
            unsafe_allow_html=True)

_gw = []
for _r in (_gw_rows or []):
    _ok = _r.get("status")
    _gw.append((_ok, str(_r.get("provider") or _r.get("source") or "gateway"),
                f'{_r.get("key") or ""} · {_r.get("retrieved_at") or "—"}'
                + (f' · {_r.get("record_count")} records' if _r.get("record_count") is not None else "")))
if _gw:
    _pills = "".join(
        ui_pill(_lbl, "ok" if _s == "ok" else "off") + " "
        for _s, _p, _lbl in _gw[:8]
    )
    st.markdown(f'<div class="t-caption">Data gateway cache: {_pills}</div>', unsafe_allow_html=True)

_live_st_rows = []
try:
    _live_st_rows = intel_live.live_status(now=NOW_IST)
except Exception:
    _live_st_rows = []
if _live_st_rows:
    with st.expander("Live research cache status"):
        st.dataframe(pd.DataFrame(_live_st_rows), hide_index=True, use_container_width=True)

_top_uds = (_snapshot or {}).get("underlyings") or []
if _top_uds:
    with st.expander("Top look-through positions (through funds)"):
        import pandas as pd
        st.dataframe(pd.DataFrame(_top_uds), hide_index=True, use_container_width=True,
                     column_config={
                         "name": st.column_config.TextColumn("Security"),
                         "value_inr": st.column_config.NumberColumn("Value (INR)", format="₹%d"),
                         "pct": st.column_config.NumberColumn("% of assets", format="%.1f%%"),
                         "schemes": st.column_config.TextColumn("Via"),
                         "confidence": st.column_config.NumberColumn("Confidence", format="%.2f"),
                     })

_meta_bits = [
    "read-only render — never re-computes valuation",
    "no AI runs on page load",
    "facts = deterministic calc ± observed evidence (FactKind)",
    "decision-support only; nothing here is an order",
]
st.markdown(f'<div class="t-footnote" style="margin-top:14px;">{" · ".join(_meta_bits)}</div>',
            unsafe_allow_html=True)
st.caption(f"Intelligence as-of {NOW_IST:%d %b %Y, %H:%M IST} · "
           "sources: AMFI NAV / holdings disclosures, Groww, Yahoo, goldprice.dev, Frankfurter, "
           "Google News RSS, FRED, SEC — via the read-only gateway cache.")