# Asset Intelligence — wrapper around lib.asset_intelligence
from __future__ import annotations

import time
import pandas as pd
import streamlit as st

from lib.asset_intelligence import build_asset_pack, pack_prompt_extras
from lib.company_tape import fetch_yahoo_equity, format_tape_value, yahoo_ticker
from lib.upstox_tape import fetch_upstox_equity, read_upstox_token
from lib.intelligence import ai as intel_ai
from lib.intelligence.ai.config import load_ai_config, provider_is_configured
from lib.intelligence.ai.health import ollama_failure_hint
from lib.register import canonical_instrument_key
from lib.roster import build_roster, member_filter_options
from lib.theme import inject_css
from lib.ui import caption, empty_state, nav_shell, page_header_html, section_header_html
from lib.ui.asset_board import render_stock_board

inject_css()
nav_shell("asset-intelligence")
st.markdown(page_header_html(
    "Northline · Asset Intelligence", "Issuer and scheme reading",
    "Deterministic flags from the Command Center session and an opt-in tape.",
), unsafe_allow_html=True)

BOOK_KIND = {"MF": "mf", "Stocks": "stocks", "Gold": "gold", "FD": "fd"}


@st.cache_data(ttl=900, show_spinner=False)
def _upstox_tape(isin: str, exchange: str):
    return fetch_upstox_equity(isin, exchange)


@st.cache_data(ttl=21600, show_spinner=False)
def _yahoo_tape(symbol: str, exchange: str):
    return fetch_yahoo_equity(symbol, exchange)


def _raw_records_for(books, kind, key):
    book = (books or {}).get(BOOK_KIND.get(kind))
    if book is None or getattr(book, "empty", True):
        return []
    out = []
    for _, row in book.iterrows():
        rec = row.to_dict()
        if canonical_instrument_key(kind, rec) == key:
            out.append(rec)
    return out


def _flag_frame(items):
    return pd.DataFrame([{"Flag": f.label, "Reading": f.text, "Source": f.source} for f in items])


def _upstox_prompt(tape):
    if not isinstance(tape, dict):
        return ""
    lines = []
    for row in (tape.get("statements") or [])[:6]:
        lines.append("%s %s: %s (%s)" % (row.get("Statement"), row.get("Line"), row.get("Latest"), row.get("Period")))
    for row in (tape.get("shareholding") or [])[:4]:
        lines.append("Holding %s: %s" % (row.get("Holder"), row.get("Percent")))
    for row in (tape.get("news") or [])[:3]:
        lines.append("News: %s" % row.get("Headline"))
    if not lines:
        return ""
    return "\nVerified Upstox facts. Restate these. Do not invent figures.\n" + "\n".join(lines)


books = st.session_state.get("cc_books")
assets = st.session_state.get("cc_assets")
cohort = st.session_state.get("cc_live_cohort")
brief = st.session_state.get("cc_research_brief")
briefing = st.session_state.get("cc_intel_briefing")
roster = None
if isinstance(books, dict):
    try:
        roster = build_roster(mf_valid=books.get("mf"), stocks_valid=books.get("stocks"), gold_valid=books.get("gold"), fd_valid=books.get("fd"))
    except Exception:
        roster = None
if roster is None or len(roster) == 0:
    st.markdown(empty_state("Open the Command Center first", "Asset Intelligence reads the published books."), unsafe_allow_html=True)
    st.stop()

members = member_filter_options(roster)
left, right = st.columns((1, 2))
with left:
    owners = st.multiselect("Member filter", members, default=members)
show = roster[roster["Member"].isin(owners)] if owners else roster
show = show[show["Kind"].isin(["Stocks", "MF"])]
if show.empty:
    st.markdown(empty_state("No stock or fund line in this filter", "Gold and FD have no issuer tape on this page."), unsafe_allow_html=True)
    st.stop()
labels = [f"{r['Kind']} · {r['Name']} · {r['Member']}" for _, r in show.iterrows()]
keys = list(show["Key"].astype(str))
focus = st.session_state.get("ai_focus_key")
default_idx = keys.index(str(focus)) if focus and str(focus) in keys else 0
with right:
    picked = st.selectbox("Instrument", labels, index=default_idx)
row = show.iloc[labels.index(picked)].to_dict()
recs = _raw_records_for(books, str(row.get("Kind")), str(row.get("Key")))
rec = recs[0] if recs else {}
tape = None
if str(row.get("Kind")) == "Stocks":
    symbol = str(rec.get("Symbol") or row.get("Key") or "").strip()
    exchange = str(rec.get("Exchange") or "NSE").strip() or "NSE"
    isin = str(rec.get("ISIN") or row.get("Key") or "").strip()
    tape_key = f"ai_tape_{row['Key']}"
    has_token = bool(read_upstox_token())
    c1, c2 = st.columns(2)
    with c1:
        load_upstox = st.button(f"Load Upstox tape for {symbol or 'this stock'}", key=tape_key + "_upstox", disabled=not has_token)
    with c2:
        load_yahoo = st.button(f"Yahoo fallback ({yahoo_ticker(symbol, exchange)})", key=tape_key)
    if load_upstox:
        with st.spinner("Fetching Upstox quote, ratios, statements and news…"):
            st.session_state[tape_key + "_data"] = _upstox_tape(isin, exchange)
    if load_yahoo:
        with st.spinner(f"Fetching {yahoo_ticker(symbol, exchange)}…"):
            st.session_state[tape_key + "_data"] = _yahoo_tape(symbol, exchange)
    tape = st.session_state.get(tape_key + "_data")
    if isinstance(tape, dict) and tape.get("error"):
        st.markdown(caption(str(tape.get("error"))), unsafe_allow_html=True)

pack = build_asset_pack(
    row=row, rec=rec, books=books, assets=assets, research_brief=brief,
    live_cohort=cohort, tape=tape if isinstance(tape, dict) else None,
    session_holdings=st.session_state.get("mf_holdings_for_health"),
)
stock_board = str(row.get("Kind")) == "Stocks" and isinstance(tape, dict) and tape.get("ok")
if stock_board:
    render_stock_board(st, pack, tape, rec)
else:
    st.markdown(section_header_html(pack.name or "Instrument", pack.kind), unsafe_allow_html=True)
    st.markdown(caption(f"{pack.member or '—'} · ISIN {pack.isin or '—'} · symbol {pack.symbol or '—'}."), unsafe_allow_html=True)
    if pack.parameters:
        view = []
        for item in pack.parameters:
            val = item.get("Value")
            label = str(item.get("Parameter") or "")
            shown = format_tape_value(label, val, str(item.get("Unit") or "")) if not isinstance(val, str) else val
            view.append({"Parameter": label, "Value": shown, "Source": item.get("Source")})
        st.dataframe(pd.DataFrame(view), hide_index=True, use_container_width=True)
    if pack.lookthrough:
        st.dataframe(pd.DataFrame(pack.lookthrough), hide_index=True, use_container_width=True)
    row1_l, row1_r = st.columns(2)
    with row1_l:
        if pack.green:
            st.dataframe(_flag_frame(pack.green), hide_index=True, use_container_width=True)
    with row1_r:
        if pack.gaps:
            st.dataframe(_flag_frame(pack.gaps), hide_index=True, use_container_width=True)

st.markdown(section_header_html("AI reading of this pack", "opt-in · never on load"), unsafe_allow_html=True)
try:
    ai_cfg = load_ai_config()
    ai_ready = provider_is_configured(ai_cfg)
except Exception:
    ai_cfg = None
    ai_ready = False
run_ai = st.button("Interpret this Asset Intelligence pack", key=f"ai_pack_{pack.key}")
out_key = f"ai_pack_out_{pack.key}"
if run_ai:
    if pack.brief is None:
        st.warning("No instrument brief could be built. Open Command Center first.")
    else:
        store = st.session_state.setdefault("asset_intel_ai_hour", {})
        ck = "|".join(("asset-intel-v4", pack.key, str((tape or {}).get("retrieved_at") or ""), str(getattr(ai_cfg, "provider", "") or "")))
        hit = store.get(ck) if isinstance(store, dict) else None
        reuse = isinstance(hit, dict) and (time.time() - float(hit.get("ts") or 0) < 3600)
        if reuse:
            out = hit["out"]
        else:
            question = pack_prompt_extras(pack) + _upstox_prompt(tape) + "\nRestate the verified figures. Do not recommend adding, selling, or rebalancing."
            with st.spinner("AI is reading the Asset Intelligence pack…"):
                out = intel_ai.run_ai_research(brief=pack.brief, facts=getattr(briefing, "facts", ()) or (), evidence=getattr(briefing, "evidence", ()) or (), question=question)
            if str(getattr(out, "status", "") or "") == "ok":
                store[ck] = {"ts": time.time(), "out": out}
        st.session_state[out_key] = out
stored = st.session_state.get(out_key)
if stored is not None and getattr(stored, "status", "") == "ok" and getattr(stored, "assessment", None) is not None:
    ass = stored.assessment
    st.markdown(caption(str(getattr(ass, "overall_assessment", "") or "")), unsafe_allow_html=True)
    for finding in (getattr(ass, "findings", None) or [])[:8]:
        st.markdown(caption("· " + str(getattr(finding, "text", finding))), unsafe_allow_html=True)
    st.markdown(caption("Decision-support only. Not an order."), unsafe_allow_html=True)
elif stored is not None:
    reason = str(getattr(stored, "reason", "") or "").strip()
    line = "AI did not produce a grounded reading."
    if reason:
        line += " " + reason
    if not ai_ready:
        line += " Configure Groq in Streamlit secrets if you want a reading."
    st.markdown(caption(line), unsafe_allow_html=True)
