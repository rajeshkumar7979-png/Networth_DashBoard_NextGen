# -------------------------------------------------
# lib/ui — shared presentation components (R-1701).
#
# Pure HTML-string builders. No streamlit, no network, no data math here: these
# helpers only render strings. Page code calls them with already-computed
# values; the exact figures always come from engines (register/drivers/valuation)
# or observed evidence — never from a helper.
#
# Every component maps to a class in lib.theme.DESIGN_SYSTEM_CSS (one shared
# stylesheet per page). No page may carry its own <style> block.
# -------------------------------------------------
from __future__ import annotations

import html as _html

from lib.intelligence.model import FactKind


def _esc(value):
    if value is None:
        return ""
    return _html.escape(str(value), quote=False)


# ---------------------------------------------------------------------------
# Typography / page shell
# ---------------------------------------------------------------------------
def page_header_html(kicker, title, sub=""):
    parts = ["<div>"]
    if kicker:
        parts.append(f'<div class="t-kicker">{_esc(kicker)}</div>')
    parts.append(f'<div class="t-title">{_esc(title)}</div>')
    if sub:
        parts.append(f'<div class="t-sub">{_esc(sub)}</div>')
    parts.append("</div>")
    return "".join(parts)


def section_header_html(label, meta="", index=None):
    """Section title with a hairline rule and never-concatenated meta.
    A short numeric meta (e.g. step numbering "01") is rendered as a leading
    index chip; any other meta sits on the right, separated by the rule."""
    if index is None and str(meta).strip().isdigit():
        index, meta = str(meta).strip(), ""
    idx_html = f'<span class="t-section-index">{_esc(index)}</span>' if index else ""
    meta_html = f'<span class="t-section-meta">{_esc(meta)}</span>' if meta else ""
    return (f'<div class="t-section-title">{idx_html}'
            f'<span class="t-section-lbl">{_esc(label)}</span>{meta_html}</div>')


def caption(text, tone=""):
    cls = f" t-caption-{tone}" if tone else ""
    return f'<span class="t-caption{cls}">{_esc(text)}</span>'


def footnote(text):
    return f'<div class="t-footnote">{_esc(text)}</div>'


# ---------------------------------------------------------------------------
# Status & classification
# ---------------------------------------------------------------------------
def status_pill(text, state="neutral"):
    """state: ok | cache | off | info | neutral"""
    return f'<span class="t-pill t-pill-{state}"><span class="t-dot"></span>{_esc(text)}</span>'


def pill(text, tone="neutral"):
    tone_map = {"positive": "pos", "negative": "neg", "warning": "warn",
                "info": "info", "live": "live", "stale": "stale", "neutral": ""}
    cls = tone_map.get(tone, "")
    return f'<span class="t-badge{(" t-badge-" + cls) if cls else ""}">{_esc(text)}</span>'


def fact_kind_chip(kind):
    """Chip for the FactKind taxonomy (FACT / CALCULATED FACT / SIGNAL /
    AI INTERPRETATION / RECOMMENDATION) plus the short source-type words."""
    label = getattr(kind, "value", kind)
    norm = str(label).upper().strip()
    mapping = {
        FactKind.FACT.value: "fact",
        FactKind.CALCULATED_FACT.value: "calc",
        FactKind.SIGNAL.value: "signal",
        FactKind.AI_INTERPRETATION.value: "ai",
        FactKind.RECOMMENDATION.value: "reco",
    }
    for key, cls in mapping.items():
        if norm == str(key).upper():
            return f'<span class="t-chip t-chip-{cls}">{_esc(label)}</span>'
    keywords = {
        "CALCULATED": "calc", "FACT": "fact", "SIGNAL": "signal",
        "INTERPRETATION": "ai", "RECOMMENDATION": "reco", "NEWS": "fact",
    }
    for word, cls in keywords.items():
        if word in norm:
            return f'<span class="t-chip t-chip-{cls}">{_esc(label)}</span>'
    return f'<span class="t-chip t-chip-fact">{_esc(label)}</span>'


def source_tag(text):
    return f'<span class="t-source">{_esc(text)}</span>'


def sentiment_mark(sentiment):
    """Non-color status: glyph + word, colour only as reinforcement (R-1705)."""
    if sentiment in ("red", "negative"):
        return '<span class="t-badge t-badge-neg">▼ NEGATIVE</span>'
    if sentiment in ("green", "positive"):
        return '<span class="t-badge t-badge-pos">▲ POSITIVE</span>'
    return '<span class="t-badge">• NEUTRAL</span>'


def tone_for(value):
    """up | down | warn | neutral for a signed figure."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "neutral"
    if v > 0:
        return "up"
    if v < 0:
        return "down"
    return "neutral"


# ---------------------------------------------------------------------------
# KPI strip
# ---------------------------------------------------------------------------
def kpi_cards(cards, cols=None):
    """cards: list of dict(label, value, sub=None, tone=None).
    tone: up | down | warn | accent | neutral. Renders to the t-kpi-grid.
    Optional cols (e.g. 4) selects a fixed-column modifier so heterogeneous
    grids (8-card market pulse) stay on balanced rows instead of a 6+2 break."""
    items = []
    for c in cards:
        tone_cls = {"up": "t-kpi-tone-up", "down": "t-kpi-tone-down",
                    "warn": "t-kpi-tone-warn", "accent": "t-kpi-tone-accent"}.get(
                        c.get("tone"), "")
        sub_html = f'<div class="t-kpi-sub">{_esc(c.get("sub", ""))}</div>' if c.get("sub") else ""
        items.append(
            f'<div class="t-kpi {tone_cls}">'
            f'<div class="t-kpi-label">{_esc(c.get("label", ""))}</div>'
            f'<div class="t-kpi-value">{_esc(c.get("value", ""))}</div>'
            f'{sub_html}'
            f'</div>'
        )
    grid_cls = f" t-kpi-grid-{int(cols)}" if cols else ""
    return f'<div class="t-kpi-grid{grid_cls}">{"".join(items)}</div>'


# ---------------------------------------------------------------------------
# Allocation bar
# ---------------------------------------------------------------------------
def stacked_bar(parts, total=None, height=16):
    """parts: list of dict(label, value, color). One horizontal bar plus an
    itemised table. Percentages are derived from the given values; the bar
    never invents a bucket (missing classes simply do not render)."""
    norm = [(p, max(0.0, float(p.get("value") or 0.0))) for p in parts]
    denominator = float(total) if total is not None else sum(v for _, v in norm)
    if denominator <= 0:
        return '<div class="t-empty">No allocation to display.</div>'
    segs = []
    for p, v in norm:
        if v <= 0:
            continue
        pct = v / denominator * 100.0
        segs.append(
            f'<div class="t-bar-seg" style="width:{pct:.2f}%;background:{p.get("color", "#3b82f6")}" '
            f'title="{_esc(p.get("label", ""))}: {v:,.0f}"></div>'
        )
    bar = f'<div class="t-bar-track" style="height:{int(height)}px">{"".join(segs)}</div>'
    legend = []
    for p, v in norm:
        if v <= 0:
            continue
        pct = v / denominator * 100.0
        legend.append(
            f'<li><span class="nm">'
            f'<span style="color:{p.get("color", "#3b82f6")}">●</span> '
            f'{_esc(p.get("label", ""))}</span>'
            f'<span class="amt">{pct:.1f}% · {v:,.0f}</span></li>'
        )
    legend_html = f'<ul class="t-alloc-legend">{"".join(legend)}</ul>' if legend else ""
    return bar + legend_html


# ---------------------------------------------------------------------------
# Attention
# ---------------------------------------------------------------------------
def attention_tiles(tiles):
    """tiles: list of dict(tag, level, title, body). level: critical|warning|info."""
    items = []
    for t in tiles:
        level = t.get("level", "info")
        if level == "critical":
            tag_cls, border = "t-tag-urgent", "#7f1d1d"
        elif level == "warning":
            tag_cls, border = "t-tag-review", "#78350f"
        else:
            tag_cls, border = "t-tag-upcoming", "#1e3a5f"
        tag = t.get("tag") or {"critical": "URGENT", "warning": "REVIEW", "info": "WATCH"}[level]
        items.append(
            f'<div class="t-attn-tile" style="border-color:{border}">'
            f'<span class="t-attn-tag {tag_cls}">{_esc(tag)}</span>'
            f'<p class="t-attn-title">{_esc(t.get("title", ""))}</p>'
            f'<p class="t-attn-body">{_esc(t.get("body", ""))}</p></div>'
        )
    return f'<div class="t-attn-grid">{"".join(items)}</div>'


def watchlist(items):
    """Restrained hierarchical attention list. level: critical | warning | info.
    Each row carries a small tag (HIGH PRIORITY / WATCH / INFORMATION), a title
    and a 'why it matters' body — evidence first, not alarm styling."""
    label = {"critical": "HIGH PRIORITY", "warning": "WATCH", "info": "INFORMATION"}
    cls = {"critical": "urgent", "warning": "warn", "info": "info"}
    rows = []
    for level in ("critical", "warning", "info"):
        for it in (i for i in items if (i.get("level") or "info") == level):
            why = ""
            if it.get("what"):
                why = f'<div class="t-watch-why"><b>Why it matters</b> — {_esc(it["what"])}</div>'
            rows.append(
                f'<div class="t-watch t-watch-{cls[level]}">'
                f'<div class="t-watch-bar"></div>'
                f'<div class="t-watch-main">'
                f'<div class="t-watch-tag">{label[level]}</div>'
                f'<div class="t-watch-title">{_esc(it.get("title", ""))}</div>'
                f'<div class="t-watch-body">{_esc(it.get("body", ""))}</div>'
                f'{why}</div></div>'
            )
    if not rows:
        return '<div class="t-empty">Nothing flagged right now.</div>'
    return f'<div class="t-watch-list">{"".join(rows)}</div>'


# ---------------------------------------------------------------------------
# Executive hero — one dominant number + supporting metrics
# ---------------------------------------------------------------------------
def hero_metrics(primary, supporting=(), foot=""):
    """primary: dict(label, value, sub, delta). supporting: list of dicts for
    kpi_cards(). One dominant card on the left, supporting cards on the right."""
    tone_cls = {"up": "t-hero-tone-up", "down": "t-hero-tone-down",
                "warn": "t-hero-tone-warn", "accent": "t-hero-tone-accent"}.get(
                    primary.get("tone"), "")
    main = ['<div class="t-hero-main">',
            f'<div class="t-hero-kicker">{_esc(primary.get("label", ""))}</div>',
            f'<div class="t-hero-value {tone_cls}">{_esc(primary.get("value", ""))}</div>']
    if primary.get("delta"):
        main.append(f'<div class="t-hero-delta">{_esc(primary["delta"])}</div>')
    if primary.get("sub"):
        main.append(f'<div class="t-hero-sub">{_esc(primary["sub"])}</div>')
    if foot:
        main.append(f'<div class="t-hero-foot">{_esc(foot)}</div>')
    main.append('</div>')

    side = []
    for c in supporting:
        tone_c = {"up": "t-kpi-tone-up", "down": "t-kpi-tone-down",
                  "warn": "t-kpi-tone-warn", "accent": "t-kpi-tone-accent"}.get(c.get("tone"), "")
        sub = f'<div class="t-kpi-sub">{_esc(c.get("sub", ""))}</div>' if c.get("sub") else ""
        side.append(
            f'<div class="t-kpi {tone_c}">'
            f'<div class="t-kpi-label">{_esc(c.get("label", ""))}</div>'
            f'<div class="t-kpi-value">{_esc(c.get("value", ""))}</div>{sub}</div>'
        )
    side_html = f'<div class="t-hero-side">{"".join(side)}</div>' if side else ""
    return f'<div class="t-hero">{"".join(main)}{side_html}</div>'


# ---------------------------------------------------------------------------
# Research rows — compact headline cards with evidence meta
# ---------------------------------------------------------------------------
def research_row(title, meta="", body="", tag="", href="", tone="", badge=""):
    safe_title = _esc(title)
    if href:
        safe_title = f'<a href="{href}" target="_blank" rel="noopener">{safe_title}</a>'
    top = ""
    if tag or meta or badge:
        top = ('<div class="t-research-top">'
               + (f'<span class="t-research-tag">{_esc(tag)}</span>' if tag else "")
               + (badge if badge else "")
               + (f'<span class="t-research-meta">{_esc(meta)}</span>' if meta else "")
               + '</div>')
    body_html = f'<div class="t-research-body">{_esc(body)}</div>' if body else ""
    return (f'<div class="t-research">{top}'
            f'<div class="t-research-title">{safe_title}</div>'
            f'{body_html}</div>')


def research_grid(rows):
    """rows: list of HTML strings from research_row(). Two-column layout."""
    return f'<div class="t-research-grid">{"".join(rows)}</div>'


def unavailable(primary, detail=""):
    """One deliberate, calm 'not available' state (replaces repeated n/a blocks)."""
    detail_html = f'<div class="t-unavail-detail">{_esc(detail)}</div>' if detail else ""
    return (f'<div class="t-unavailable"><div class="t-unavail-mark">—</div>'
            f'<div class="t-unavail-title">{_esc(primary)}</div>{detail_html}</div>')


def evidence_trail(bits):
    """Compact single-line provenance trail; bits are pre-formatted short strings."""
    joined = "".join(f"<span class='t-evidence-bit'>{_esc(str(b))}</span>" for b in bits if str(b))
    return f'<div class="t-evidence">{joined}</div>'


def banner(text, kind="critical"):
    return f'<div class="t-banner t-banner-{kind}">{text}</div>'


def empty_state(primary, secondary="", hint=""):
    """Calm blocked/empty state: bold primary, optional reason, optional
    how-to-proceed hint rendered as a distinct muted line below."""
    parts = [f"<b>{_esc(primary)}</b>"]
    if secondary:
        parts.append(_esc(secondary))
    hint_html = f'<div class="t-empty-hint">{_esc(hint)}</div>' if hint else ""
    return f'<div class="t-empty">{" ".join(parts)}{hint_html}</div>'


# ---------------------------------------------------------------------------
# Evidence / provenance line
# ---------------------------------------------------------------------------
def evidence_meta(source, retrieved_at="", class_label="", method=""):
    bits = [
        f"SOURCE {_esc(source)}" if source else "",
        _esc(retrieved_at) if retrieved_at else "",
        f"CLASS {_esc(class_label)}" if class_label else "",
        _esc(method) if method else "",
    ]
    return source_tag(" · ".join(b for b in bits if b))