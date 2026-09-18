# -------------------------------------------------
# lib/ui — shared presentation components are pure HTML-string builders.
# No streamlit, no data math, no network. Tests pin the contract pages rely on.
# -------------------------------------------------
from lib.ui import (
    kpi_cards,
    section_header_html,
    status_pill,
    stacked_bar,
    fact_kind_chip,
    sentiment_mark,
    attention_tiles,
    empty_state,
    pill,
    caption,
    page_header_html,
    tone_for,
    hero_metrics,
    watchlist,
    research_row,
    research_grid,
    unavailable,
    evidence_trail,
    briefing_hero,
    weight_strip,
    score_ring,
)
from lib.intelligence.model import FactKind


def test_kpi_cards_renders_values():
    html = kpi_cards([
        {"label": "Total Assets", "value": "₹ 2.53 Cr", "sub": "as of today"},
        {"label": "P&L", "value": "₹ 29.8 L", "tone": "up"},
    ])
    assert "t-kpi-grid" in html
    assert "₹ 2.53 Cr" in html
    assert "t-kpi-tone-up" in html
    assert "Total Assets" in html


def test_kpi_cards_cols_modifier():
    base = kpi_cards([{"label": "A", "value": "1"}] * 8)
    four = kpi_cards([{"label": "A", "value": "1"}] * 8, cols=4)
    assert "t-kpi-grid-4" in four
    assert "t-kpi-grid-4" not in base
    assert "t-kpi-grid" in base and "t-kpi-grid" in four


def test_kpi_cards_escapes_html():
    html = kpi_cards([{"label": "<script>", "value": "x & y"}])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_fact_kind_chips_map_to_provenance_taxonomy():
    assert "t-chip-fact" in fact_kind_chip(FactKind.FACT)
    assert "t-chip-calc" in fact_kind_chip(FactKind.CALCULATED_FACT)
    assert "t-chip-signal" in fact_kind_chip(FactKind.SIGNAL)
    assert "t-chip-ai" in fact_kind_chip(FactKind.AI_INTERPRETATION)
    assert "t-chip-reco" in fact_kind_chip(FactKind.RECOMMENDATION)
    assert "CALCULATED FACT" in fact_kind_chip(FactKind.CALCULATED_FACT)


def test_sentiment_mark_is_not_color_alone():
    assert "▼ NEGATIVE" in sentiment_mark("red")
    assert "▲ POSITIVE" in sentiment_mark("green")
    assert "• NEUTRAL" in sentiment_mark("neutral")
    assert "t-badge-neg" in sentiment_mark("red")


def test_stacked_bar_never_invents_buckets():
    html = stacked_bar([{"label": "Equity", "value": 100, "color": "#3b82f6"}], total=100)
    assert "t-bar-track" in html
    assert "Equity" in html
    empty = stacked_bar([{"label": "A", "value": 0, "color": "#000"}], total=0)
    assert "No allocation" in empty


def test_status_pill_and_pill():
    assert "t-pill-ok" in status_pill("Live", "ok")
    assert "t-badge-neg" in pill("NEGATIVE", "negative")
    assert "t-badge" in pill("NEUTRAL")


def test_attention_and_empty():
    tiles = attention_tiles([{"tag": "URGENT", "level": "critical", "title": "X",
                              "body": "Y"}])
    assert "t-attn-grid" in tiles and "t-tag-urgent" in tiles
    assert "<b>No data</b>" in empty_state("No data", "insufficient evidence")


def test_empty_state_hint():
    html = empty_state("No data", "reason here", hint="Go to Command Center → Refresh")
    assert "t-empty-hint" in html
    assert "Go to Command Center → Refresh" in html
    # hint is escaped; backward compatible with 2-arg calls
    esc = empty_state("A", "B", hint="<next>")
    assert "<next>" not in esc and "&lt;next&gt;" in esc
    assert "t-empty-hint" not in empty_state("No data", "reason here")


def test_section_and_page_header():
    assert "t-section-title" in section_header_html("WHAT CHANGED")
    assert "t-section-meta" in section_header_html("WHAT CHANGED", "6 drivers")
    html = page_header_html("PORTFOLIO INTELLIGENCE TERMINAL", "Command Center")
    assert "t-kicker" in html and "t-title" in html


def test_caption_escapes():
    assert "&lt;b&gt;" in caption("<b>")


def test_tone_for():
    assert tone_for(5) == "up"
    assert tone_for(-5) == "down"
    assert tone_for(0) == "neutral"
    assert tone_for("n/a") == "neutral"


def test_section_header_index_chip_never_concats():
    html = section_header_html("DECISION", "01")
    assert "t-section-index" in html and ">01</span>" in html
    assert "t-section-meta" not in html
    assert "DECISION" in html
    assert "01DECISION" not in html
    meta = section_header_html("WHAT CHANGED", "6 drivers")
    assert "t-section-meta" in meta and "6 drivers" in meta and "t-section-index" not in meta


def test_hero_metrics_dominant_number():
    html = hero_metrics(
        {"label": "NET WORTH", "value": "₹ 2.53 Cr", "delta": "▲ 0.4% today",
         "tone": "up"},
        [{"label": "Total Assets", "value": "₹ 2.53 Cr"},
         {"label": "Liabilities", "value": "₹ 0"}],
        foot="Net Worth = Total Assets − Liabilities",
    )
    assert "t-hero" in html and "t-hero-main" in html and "t-hero-side" in html
    assert "t-hero-value" in html and "₹ 2.53 Cr" in html
    assert "t-hero-tone-up" in html and "t-hero-foot" in html


def test_watchlist_orders_by_level_and_never_alarm_only():
    items = [
        {"level": "info", "title": "I watch", "body": "b"},
        {"level": "critical", "title": "C high", "body": "b", "what": "why"},
        {"level": "warning", "title": "W medium", "body": "b"},
    ]
    html = watchlist(items)
    assert html.index("HIGH PRIORITY") < html.index("WATCH") < html.index("INFORMATION")
    assert "t-watch-urgent" in html and "t-watch-why" in html and "Why it matters" in html
    assert watchlist([]) == '<div class="t-empty">Nothing flagged right now.</div>'


def test_research_row_and_grid_escape():
    html = research_row("<b>x</b>", meta="2h ago", body="body <i>y</i>", tag="MAPPED")
    assert "t-research" in html and "t-research-tag" in html and "&lt;b&gt;x&lt;/b&gt;" in html
    assert "<b>x</b>" not in html and "body &lt;i&gt;y&lt;/i&gt;" in html
    grid = research_grid([html, research_row("T")])
    assert "t-research-grid" in grid
    assert grid.count('class="t-research"') == 2


def test_research_row_badge_passthrough():
    html = research_row("Q", tag="Holding", badge='<span class="t-badge t-badge-pos">▲ POSITIVE</span>')
    assert "t-research-top" in html
    assert 't-badge-pos' in html and "▲ POSITIVE" in html
    assert not research_row("Q").__contains__("t-research-top")


def test_unavailable_and_evidence_trail():
    assert "t-unavailable" in unavailable("No holdings data", "insufficient evidence")
    trail = evidence_trail(["SOURCE FRED", "", "retrieved 2h ago"])
    assert "t-evidence-bit" in trail and "SOURCE FRED" in trail and "retrieved 2h ago" in trail


def test_briefing_hero_carries_kpis_and_alloc_label():
    html = briefing_hero(
        "Family net worth", "₹2.54 Cr",
        [{"text": "Invested ₹2.24 Cr"}, {"text": "+₹30.81 L", "tone": "up"}],
        "Defensive stance",
        '<div class="t-ring-wrap"></div>',
        '<div class="t-strip"></div>',
        '<div class="t-kpi-grid t-kpi-grid-4"></div>',
    )
    assert "t-brief-kpis" in html and "t-brief-alloc-lbl" in html
    assert "Asset allocation" in html
    assert "₹2.54 Cr" in html and "Defensive stance" in html
    six = briefing_hero("K", "V", [], "", "", "")
    assert "t-brief-kpis" not in six


def test_weight_strip_in_bar_labels_for_wide_sleeves():
    html = weight_strip([
        {"label": "Equity", "value": 45},
        {"label": "Liquid MF", "value": 20},
        {"label": "INR FD", "value": 18},
        {"label": "FCNR", "value": 12},
        {"label": "Gold", "value": 5},
    ], total=100)
    assert "t-strip-in" in html and "t-strip-in-name" in html
    assert "Equity" in html and "FCNR" in html
    # Gold at 5% is too thin for an in-bar name, but still in the legend.
    assert html.count('class="t-sleeve"') == 5


def test_score_ring_bands():
    ok = score_ring(80, label="HEALTH")
    warn = score_ring(65, label="ADEQUATE")
    urgent = score_ring(40, label="WEAK")
    assert "t-ring-ok" in ok and "t-ring-warn" in warn and "t-ring-urgent" in urgent
    assert "65" in warn