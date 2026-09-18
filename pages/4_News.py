import html
import streamlit as st

from lib.news import get_sentiment, time_ago
from lib.theme import inject_css
from lib.ui import (page_header_html, section_header_html, pill, sentiment_mark, empty_state,
                    research_row, research_grid, footnote, nav_shell, kpi_cards)

inject_css()

nav_shell("pulse")
st.markdown(page_header_html(
    "Northline · Family desk",
    "Holdings + NRI / tax",
    "An editorial feed of what is moving around your portfolio. Headlines are observations, never verified portfolio facts.",
    meta=[
        "EDITORIAL FEED",
        "OBSERVATIONS, NOT VERIFIED FACTS",
        "PORTFOLIO + NRI / TAX",
    ],
), unsafe_allow_html=True)

_rates = st.session_state.get("cc_rates") or {}
if _rates.get("usd_inr") is not None or _rates.get("gold_10g_inr") is not None:
    _rate_cards = []
    if _rates.get("usd_inr") is not None:
        _fx_sub = _rates.get("usd_inr_source") or "Frankfurter"
        if _rates.get("usd_inr_published"):
            _fx_sub += f" · published {_rates['usd_inr_published']}"
        _rate_cards.append({"label": "USD/INR", "value": f"{_rates['usd_inr']:.2f}",
                            "sub": _fx_sub, "tone": "accent"})
    if _rates.get("gold_10g_inr") is not None:
        _g_sub = _rates.get("gold_source") or "India spot reference"
        if _rates.get("retrieved_at"):
            _g_sub = f"{_g_sub} · retrieved {_rates['retrieved_at']}"
        _rate_cards.append({"label": "Gold ₹/10g", "value": f"{_rates['gold_10g_inr']:,.0f}",
                            "sub": _g_sub, "tone": "accent"})
    if _rate_cards:
        st.markdown(kpi_cards(_rate_cards, cols=4), unsafe_allow_html=True)

CATEGORY_LABELS = {"holding": "Holding", "nri_tax": "NRI / Tax", "macro": "Market"}
ORDER = [
    ("holding", "Your holdings", "portfolio-relevant first"),
    ("nri_tax", "NRI / tax", "regulatory"),
]

_sess_items = st.session_state.get("cc_news_items_full")
news_items = list(_sess_items) if _sess_items else None

# Dedupe by normalized title (exact string, case-insensitive).
seen, items = set(), []
for item in news_items or []:
    _t = str(item.get("title", "")).strip().lower()
    if not _t or _t in seen:
        continue
    seen.add(_t)
    items.append(item)

if not items:
    st.markdown(empty_state(
        "No news in this session yet",
        "The Command Center gathers the feed when it runs; this page never calls "
        "the network itself.",
        hint="Open Command Center, or press 'Refresh research evidence' there.",
    ), unsafe_allow_html=True)
    st.stop()

st.markdown(
    '<div class="t-meta-row">'
    + pill(f"{len(items)} items", "info")
    + pill("from last Command Center run", "stale")
    + '</div>',
    unsafe_allow_html=True,
)

for cat, label, meta in ORDER:
    group = [i for i in items if i.get("category") == cat]
    if not group:
        if cat == "nri_tax":
            st.markdown(section_header_html(label, meta), unsafe_allow_html=True)
            st.markdown(empty_state(
                "No NRI / tax headlines this run",
                "NRI / tax treatment is not modelled in the books. This feed is observations, "
                "not tax advice. Missing stays missing — never filled with zero.",
            ), unsafe_allow_html=True)
        continue
    st.markdown(section_header_html(label, meta), unsafe_allow_html=True)
    cards = []
    for item in group:
        _title = str(item.get("title", ""))
        _link = html.escape(str(item.get("link") or ""), quote=True)
        _age = time_ago(item.get("published_dt"))
        _query = str(item.get("query", "") or "")
        _sub = str(item.get("source", "") or "")
        _meta = " · ".join(x for x in [_sub, _age, _query] if x)
        cards.append(research_row(
            title=_title,
            meta=_meta,
            tag=CATEGORY_LABELS.get(item.get("category", ""), ""),
            href=_link,
            badge=sentiment_mark(get_sentiment(item.get("title", ""))),
        ))
    st.markdown(research_grid(cards), unsafe_allow_html=True)

_macro = [i for i in items if i.get("category") == "macro"]
if _macro:
    with st.expander(f"Market backdrop · not mapped to your book ({len(_macro)})", expanded=False):
        st.caption("General market context — not mapped to a holding or NRI/tax identifier. "
                   "Fetched with the rest of the tape; demoted here so it does not look like book news.")
        cards = []
        for item in _macro:
            _title = str(item.get("title", ""))
            _link = html.escape(str(item.get("link") or ""), quote=True)
            _age = time_ago(item.get("published_dt"))
            _query = str(item.get("query", "") or "")
            _sub = str(item.get("source", "") or "")
            _meta = " · ".join(x for x in [_sub, _age, _query] if x)
            cards.append(research_row(
                title=_title,
                meta=_meta,
                tag=CATEGORY_LABELS.get(item.get("category", ""), ""),
                href=_link,
                badge=sentiment_mark(get_sentiment(item.get("title", ""))),
            ))
        st.markdown(research_grid(cards), unsafe_allow_html=True)

st.markdown("---")
st.markdown(footnote(
    "Feed: Google News RSS gathered by the Command Center's refresh action, on the holdings "
    "and NRI/tax/market terms. Sentiment is a keyword heuristic (▲ Positive / ▼ Negative / "
    "• Neutral) — a tone, not an investment conclusion. The Command Center maps these stories "
    "to portfolio identifiers by exact match only."), unsafe_allow_html=True)
st.caption("Pulse re-renders this session's Command Center feed; it never fetches news itself — "
           "a network call happens only on 'Refresh research evidence'.")