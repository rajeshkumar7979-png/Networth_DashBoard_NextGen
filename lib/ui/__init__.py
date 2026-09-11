# -------------------------------------------------
# lib/ui — shared presentation components (R-1701).
# Pure HTML-string builders; no streamlit, no network, no financial math.
# -------------------------------------------------
from __future__ import annotations

from lib.ui.components import (
    attention_tiles,
    banner,
    caption,
    empty_state,
    evidence_meta,
    evidence_trail,
    fact_kind_chip,
    footnote,
    hero_metrics,
    kpi_cards,
    page_header_html,
    pill,
    research_grid,
    research_row,
    section_header_html,
    sentiment_mark,
    source_tag,
    stacked_bar,
    status_pill,
    tone_for,
    unavailable,
    watchlist,
)
from lib.ui.nav import NAV_GROUPS, nav_shell

__all__ = [
    "NAV_GROUPS",
    "attention_tiles",
    "banner",
    "caption",
    "empty_state",
    "evidence_meta",
    "evidence_trail",
    "fact_kind_chip",
    "footnote",
    "hero_metrics",
    "kpi_cards",
    "nav_shell",
    "page_header_html",
    "pill",
    "research_grid",
    "research_row",
    "section_header_html",
    "sentiment_mark",
    "source_tag",
    "stacked_bar",
    "status_pill",
    "tone_for",
    "unavailable",
    "watchlist",
]