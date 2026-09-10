import html
import streamlit as st

from lib.news import get_portfolio_news, get_sentiment, time_ago
from lib.theme import inject_css
from lib.ui import (page_header_html, section_header_html, pill, sentiment_mark, empty_state,
                    research_row, research_grid, footnote)

inject_css()

st.markdown(page_header_html(
    "Research & market intelligence",
    "News",
    "Relevance-first briefing · your holdings first, then NRI/tax and market context · "
    "headlines are observations, not verified portfolio facts",
), unsafe_allow_html=True)
st.page_link("pages/1_Command_Center.py", label="Command Center", icon="📊")

CATEGORY_LABELS = {"holding": "Holding", "nri_tax": "NRI / Tax", "macro": "Market"}
ORDER = [
    ("holding", "Your holdings", "portfolio-relevant first"),
    ("nri_tax", "NRI / tax", "regulatory"),
    ("macro", "Market backdrop", "context"),
]

_sess_items = st.session_state.get("cc_news_items_full")
news_items = list(_sess_items) if _sess_items else None
source_is_session = bool(news_items)

if not news_items:
    try:
        news_items = get_portfolio_news(
            stock_symbols=st.session_state.get("stock_syms", []),
            fund_names=st.session_state.get("fund_names", []),
            gold_symbols=st.session_state.get("gold_syms", []),
        )
    except Exception:
        news_items = []

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
        "No recent news found this run",
        "Refresh research evidence in the Command Center or come back later.",
    ), unsafe_allow_html=True)
    st.stop()

st.markdown(
    '<div class="t-meta-row">'
    + pill(f"{len(items)} items", "info")
    + pill("from Command Center run" if source_is_session else "live fetch",
           "stale" if source_is_session else "live")
    + '</div>',
    unsafe_allow_html=True,
)

for cat, label, meta in ORDER:
    group = [i for i in items if i.get("category") == cat]
    if not group:
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

st.markdown("---")
st.markdown(footnote(
    "Feed: Google News RSS queried on the holdings and NRI/tax/market terms. "
    "Sentiment is a keyword heuristic (▲ Positive / ▼ Negative / • Neutral) — a tone, "
    "not an investment conclusion. The Command Center maps these stories to portfolio "
    "identifiers by exact match only."), unsafe_allow_html=True)