# -------------------------------------------------
# lib/ui — shared presentation components (R-1701).
# The t-* builders in components.py are pure HTML-string functions (no
# streamlit, no network, no financial math). nav.py is the one exception: the
# product shell renders streamlit elements (st.page_link) to keep navigation
# inside the same session — see lib/ui/nav.py for why anchors were removed.
# -------------------------------------------------
from __future__ import annotations

from lib.ui.components import (
    attention_tiles,
    banner,
    caption,
    data_sheet,
    dots,
    empty_state,
    evidence_meta,
    evidence_trail,
    fact_kind_chip,
    footnote,
    hero_metrics,
    kpi_cards,
    ladder_rows,
    page_header_html,
    pill,
    research_grid,
    research_row,
    score_ring,
    section_header_html,
    sentiment_mark,
    source_tag,
    stacked_bar,
    stance_pill,
    status_pill,
    tone_for,
    unavailable,
    watchlist,
    weight_strip,
)
from lib.ui.nav import NAV_GROUPS, PAGE_FILES, nav_shell, safe_page_link

__all__ = [
    "NAV_GROUPS",
    "PAGE_FILES",
    "attention_tiles",
    "banner",
    "caption",
    "data_sheet",
    "dots",
    "empty_state",
    "evidence_meta",
    "evidence_trail",
    "fact_kind_chip",
    "footnote",
    "hero_metrics",
    "kpi_cards",
    "ladder_rows",
    "nav_shell",
    "page_header_html",
    "pill",
    "research_grid",
    "research_row",
    "safe_page_link",
    "score_ring",
    "section_header_html",
    "sentiment_mark",
    "source_tag",
    "stacked_bar",
    "stance_pill",
    "status_pill",
    "tone_for",
    "unavailable",
    "watchlist",
    "weight_strip",
]