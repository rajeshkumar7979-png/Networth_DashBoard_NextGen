# Asset Intelligence — wrapper around lib.asset_intelligence
from __future__ import annotations

import time
import pandas as pd
import streamlit as st

from lib.asset_intelligence import build_asset_pack, pack_prompt_extras
from lib.company_tape import fetch_yahoo_equity, format_tape_value, yahoo_ticker
from lib.intelligence import ai as intel_ai
from lib.intelligence.ai.config import load_ai_config, provider_is_configured
from lib.intelligence.ai.health import ollama_failure_hint
from lib.register import canonical_instrument_key
from lib.roster import build_roster, member_filter_options
from lib.theme import inject_css
from lib.ui import caption, empty_state, nav_shell, page_header_html, section_header_html

inject_css()
nav_shell("asset-intelligence")
st.markdown(page_header_html(
    "Northline · Asset Intelligence", "Issuer and scheme reading",
    "Deterministic flags from the Command Center session and an opt-in tape.",
), unsafe_allow_html=True)

BOOK_KIND = {"MF": "mf", "Stocks": "stocks", "Gold": "gold", "FD": "fd"}


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


books = st.session_state.get("cc_books")
assets = st.session_state.get("cc_assets")
cohort = st.session_state.get("cc_live_cohort")
brief = st.session_state.get("cc_research_brief")
briefing = st.session_state.get("cc_intel_briefing")

roster = None
if isinstance(books, dict):
    try:
        roster = build_roster(mf_valid=books.get("mf"), stocks_valid=books.get("stocks"),
                             gold_valid=books.get("gold"), fd_valid=books.get("fd"))
    except Exception:
        roster = None

if roster is None or len(roster) == 0:
    st.markdown(empty_state(
        "Open the Command Center first",
        "Asset Intelligence reads the published books. It does not load the workbook again.",
    ), unsafe_allow_html=True)
    st.stop()

members = member_filter_options(roster)
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
picked = st.selectbox("Instrument", labels, index=default_idx)
row = show.iloc[labels.index(picked)].to_dict()
recs = _raw_records_for(books, str(row.get("Kind")), str(row.get("Key")))
rec = recs[0] if recs else {}

tape = None
if str(row.get("Kind")) == "Stocks":
    symbol = str(rec.get("Symbol") or row.get("Key") or "").strip()
    exchange = str(rec.get("Exchange") or "NSE").strip() or "NSE"
    tape_key = f"ai_tape_{row['Key']}"
    if st.button(f"Load company tape for {symbol or 'this stock'} (Yahoo, opt-in)", key=tape_key):
        with st.spinner(f"Fetching {yahoo_ticker(symbol, exchange)}…"):
            st.session_state[tape_key + "_data"] = _yahoo_tape(symbol, exchange)
    tape = st.session_state.get(tape_key + "_data")

pack = build_asset_pack(
    row=row, rec=rec, books=books, assets=assets, research_brief=brief,
    live_cohort=cohort, tape=tape if isinstance(tape, dict) else None,
    session_holdings=st.session_state.get("mf_holdings_for_health"),
)

st.markdown(section_header_html(pack.name or "Instrument", pack.kind), unsafe_allow_html=True)
st.markdown(caption(
    f"{pack.member or '—'} · ISIN {pack.isin or '—'} · symbol {pack.symbol or '—'}. "
    + (" · ".join(pack.freshness) if pack.freshness else "No freshness stamp this session.")
), unsafe_allow_html=True)

if pack.parameters:
    st.markdown(section_header_html("Verified parameters", "observed / published"), unsafe_allow_html=True)
    view = []
    for item in pack.parameters:
        val = item.get("Value")
        label = str(item.get("Parameter") or "")
        shown = format_tape_value(label, val, str(item.get("Unit") or "")) if not isinstance(val, str) else val
        view.append({"Parameter": label, "Value": shown, "Source": item.get("Source")})
    st.dataframe(pd.DataFrame(view), hide_index=True, use_container_width=True)

for title, items, hint in (
    ("Green flags", pack.green, "Conservative observed band — not a buy."),
    ("Red flags", pack.red, "Elevated observed band — not a sell."),
    ("Watch items", pack.watch, "Needs attention, still not an order."),
    ("Data gaps", pack.gaps, "Missing stays missing."),
):
    st.markdown(section_header_html(title, hint), unsafe_allow_html=True)
    if not items:
        st.markdown(caption("None on verified inputs this session."), unsafe_allow_html=True)
        continue
    st.dataframe(pd.DataFrame([{"Flag": f.label, "Reading": f.text, "Source": f.source} for f in items]), hide_index=True, use_container_width=True)

if pack.lookthrough:
    st.markdown(section_header_html("Look-through", "statutory cache"), unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(pack.lookthrough), hide_index=True, use_container_width=True)
if pack.family_overlap:
    st.markdown(section_header_html("Family-fund overlap", "same ISIN"), unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(pack.family_overlap), hide_index=True, use_container_width=True)

st.markdown(section_header_html("Mapped external developments", "exact identifier"), unsafe_allow_html=True)
if pack.developments:
    cols = [c for c in ("Development", "Source", "Published", "Category", "Relevance", "Link") if c in pack.developments[0]]
    st.dataframe(pd.DataFrame(pack.developments)[cols], hide_index=True, use_container_width=True,
                 column_config={"Link": st.column_config.LinkColumn("Link")})
else:
    st.markdown(caption("No cohort item exact-matches this instrument. Refresh research evidence on Command Center."), unsafe_allow_html=True)

st.markdown(section_header_html("AI reading of this pack", "opt-in · never on load"), unsafe_allow_html=True)
try:
    ai_cfg = load_ai_config()
    ai_ready = provider_is_configured(ai_cfg)
except Exception:
    ai_cfg = None
    ai_ready = False
st.markdown(caption("AI restates the deterministic pack. Flags above stay if the provider fails."), unsafe_allow_html=True)
run_ai = st.button("Interpret this Asset Intelligence pack", key=f"ai_pack_{pack.key}")
out_key = f"ai_pack_out_{pack.key}"
if run_ai:
    if pack.brief is None:
        st.warning("No instrument brief could be built. Open Command Center first.")
    else:
        store = st.session_state.setdefault("asset_intel_ai_hour", {})
        ck = "|".join(("asset-intel-v1", pack.key, str(getattr(pack.brief, "evidence_count", 0)), str(getattr(ai_cfg, "provider", "") or "")))
        hit = store.get(ck) if isinstance(store, dict) else None
        reuse = isinstance(hit, dict) and (time.time() - float(hit.get("ts") or 0) < 3600)
        if reuse:
            out = hit["out"]
            st.markdown(caption("Reusing the last hour's pack reading."), unsafe_allow_html=True)
        else:
            with st.spinner("AI is reading the Asset Intelligence pack…"):
                out = intel_ai.run_ai_research(
                    brief=pack.brief,
                    facts=getattr(briefing, "facts", ()) or (),
                    evidence=getattr(briefing, "evidence", ()) or (),
                    question=pack_prompt_extras(pack),
                )
            stt = str(getattr(out, "status", "") or "")
            if stt == "ok" or (stt == "failed" and getattr(out, "provider", "") == "groq"):
                store[ck] = {"ts": time.time(), "out": out}
        st.session_state[out_key] = out

stored = st.session_state.get(out_key)
if stored is not None:
    status = getattr(stored, "status", "")
    if status == "ok" and getattr(stored, "assessment", None) is not None:
        ass = stored.assessment
        st.markdown(caption(str(getattr(ass, "overall_assessment", "") or "")), unsafe_allow_html=True)
        if getattr(ass, "uncertainty", None):
            st.markdown(caption("What could change: " + str(ass.uncertainty)), unsafe_allow_html=True)
        for finding in (getattr(ass, "findings", None) or [])[:8]:
            st.markdown(caption("· " + str(getattr(finding, "text", finding))), unsafe_allow_html=True)
        st.markdown(caption("Decision-support only. Not an order."), unsafe_allow_html=True)
    else:
        reason = str(getattr(stored, "reason", "") or "").strip()
        hint = ollama_failure_hint(reason) if reason else ""
        line = f"AI did not produce a grounded reading — {status or 'unavailable'}."
        if hint:
            line += " " + hint
        elif reason:
            line += " " + reason
        if not ai_ready:
            line += " Configure Groq in Streamlit secrets if you want a reading."
        line += " Deterministic flags above are unchanged."
        st.markdown(caption(line), unsafe_allow_html=True)
