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


def _esc_attr(value):
    if value is None:
        return ""
    return _html.escape(str(value), quote=True)


# ---------------------------------------------------------------------------
# Typography / page shell
# ---------------------------------------------------------------------------
def page_header_html(kicker, title, sub="", meta=()):
    parts = ['<div class="t-pagehead">']
    if kicker:
        parts.append(f'<div class="t-kicker">{_esc(kicker)}</div>')
    parts.append(f'<h1 class="t-title">{_esc(title)}</h1>')
    if sub:
        parts.append(f'<p class="t-sub">{_esc(sub)}</p>')
    if meta:
        pills = "".join(f'<span class="t-meta-pill">{_esc(m)}</span>' for m in meta if m)
        if pills:
            parts.append(f'<div class="t-meta-row">{pills}</div>')
    parts.append("</div>")
    return "".join(parts)


def section_header_html(label, meta="", index=None, desc=""):
    """Section title with a hairline rule and never-concatenated meta.
    A short numeric meta (e.g. step numbering "01") is rendered as a leading
    index chip; any other meta sits on the right, separated by the rule.
    An optional `desc` becomes a muted sentence under the title."""
    if index is None and str(meta).strip().isdigit():
        index, meta = str(meta).strip(), ""
    idx_html = f'<span class="t-section-index">{_esc(index)}</span>' if index else ""
    meta_html = f'<span class="t-section-meta">{_esc(meta)}</span>' if meta else ""
    head = (f'<div class="t-section"><div class="t-section-title">{idx_html}'
            f'<span class="t-section-lbl">{_esc(label)}</span>{meta_html}</div>')
    desc_html = f'<div class="t-section-desc">{_esc(desc)}</div>' if desc else ""
    return head + desc_html + "</div>"


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


def status_dots(items):
    """items: list of dict(label, on). Word + 6px dot; never colour alone."""
    bits = []
    for it in items:
        on = bool(it.get("on"))
        cls = "t-sdot-on" if on else "t-sdot-off"
        bits.append(
            f'<span class="t-sdot {cls}"><span class="t-sdot-mark"></span>'
            f'{_esc(it.get("label", ""))}</span>'
        )
    return f'<div class="t-sdot-row">{"".join(bits)}</div>'


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
        foot_html = f'<div class="t-kpi-foot">{_esc(c.get("foot", ""))}</div>' if c.get("foot") else ""
        items.append(
            f'<div class="t-kpi {tone_cls}">'
            f'<div class="t-kpi-label">{_esc(c.get("label", ""))}</div>'
            f'<div class="t-kpi-value">{_esc(c.get("value", ""))}</div>'
            f'{sub_html}{foot_html}'
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
            f'<div class="t-bar-seg" style="width:{pct:.2f}%;background:{p.get("color", "#c5cedb")}" '
            f'title="{_esc_attr(p.get("label", ""))}: {v:,.0f}"></div>'
        )
    bar = f'<div class="t-bar-track" style="height:{int(height)}px">{"".join(segs)}</div>'
    legend = []
    for p, v in norm:
        if v <= 0:
            continue
        pct = v / denominator * 100.0
        legend.append(
            f'<li><span class="nm">'
            f'<span style="color:{p.get("color", "#c5cedb")}">●</span> '
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
            tag_cls, lvl_cls = "t-tag-urgent", "t-attn-urgent"
            default_tag = "URGENT"
        elif level == "warning":
            tag_cls, lvl_cls = "t-tag-review", "t-attn-warn"
            default_tag = "REVIEW"
        else:
            tag_cls, lvl_cls = "t-tag-upcoming", "t-attn-info"
            default_tag = "NOTE"
        tag = t.get("tag") or default_tag
        items.append(
            f'<div class="t-attn-tile {lvl_cls}">'
            f'<span class="t-attn-tag {tag_cls}">{_esc(tag)}</span>'
            f'<p class="t-attn-title">{_esc(t.get("title", ""))}</p>'
            f'<p class="t-attn-body">{_esc(t.get("body", ""))}</p></div>'
        )
    return f'<div class="t-attn-grid">{"".join(items)}</div>'


def watchlist(items):
    """Restrained hierarchical attention list. level: critical | warning | info.
    Each row carries a small tag (HIGH PRIORITY / WATCH / NOTE), a title
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


def briefing_hero(kicker, value, meta_bits, stance, ring_html, strip_html, kpis_html=""):
    """Northline combined briefing card: family net worth + ring + five-sleeve strip.
    meta_bits: list of dict(text, tone=None) rendered as 'Invested · P&L · %'.
    kpis_html: optional KPI grid that sits beside the ring on desktop and
    hides on the iPhone briefing so the hero stays a single centred number."""
    metas = []
    for i, bit in enumerate(meta_bits or ()):
        if i:
            metas.append('<span class="t-brief-sep">·</span>')
        tone = (bit or {}).get("tone") or ""
        cls = f" t-signed-{tone}" if tone in ("up", "down") else ""
        metas.append(f'<span class="t-brief-bit{cls}">{_esc((bit or {}).get("text", ""))}</span>')
    stance_html = (
        f'<div class="t-stance-mini">{_esc(stance)}</div>' if stance else ""
    )
    kpis_block = f'<div class="t-brief-kpis">{kpis_html}</div>' if kpis_html else ""
    return (
        '<div class="t-brief">'
        '<div class="t-brief-top">'
        '<div class="t-brief-main">'
        f'<div class="t-brief-kicker">{_esc(kicker)}</div>'
        f'<div class="t-brief-value">{_esc(value)}</div>'
        f'<div class="t-brief-meta">{"".join(metas)}</div>'
        f'{stance_html}'
        '</div>'
        f'<div class="t-brief-ring">{ring_html}</div>'
        f'{kpis_block}'
        '</div>'
        '<div class="t-brief-alloc">'
        '<div class="t-brief-alloc-lbl">Asset allocation</div>'
        f'<div class="t-brief-strip">{strip_html}</div>'
        '</div>'
        '</div>'
    )


def news_strip(items):
    """Editorial pulse list. items: dict(title, meta, href, sentiment)."""
    rows = []
    for it in items or ():
        sent = str(it.get("sentiment") or "neutral")
        if sent in ("green", "positive", "up"):
            dot = "up"
        elif sent in ("red", "negative", "down"):
            dot = "down"
        else:
            dot = "neutral"
        href = str(it.get("href") or it.get("link") or "").strip()
        title = _esc(it.get("title") or "")
        meta = _esc(it.get("meta") or "")
        inner = (
            f'<span class="t-news-dot t-news-dot-{dot}"></span>'
            f'<span class="t-news-copy"><span class="t-news-title">{title}</span>'
            f'<span class="t-news-meta">{meta}</span></span>'
        )
        if href:
            row = (f'<li class="t-news-row"><a href="{_esc_attr(href)}" '
                   f'target="_blank" rel="noopener noreferrer">{inner}</a></li>')
        else:
            row = f'<li class="t-news-row"><div class="t-news-plain">{inner}</div></li>'
        rows.append(row)
    if not rows:
        return '<div class="t-empty">No headlines this run.</div>'
    return f'<ul class="t-news-strip">{"".join(rows)}</ul>'


def due_list(rows):
    """Cash-coming-due rows. rows: dict(name, meta, amount)."""
    if not rows:
        return '<div class="t-empty">No deposits mature in the next 90 days.</div>'
    items = []
    for r in rows:
        items.append(
            '<li class="t-due-row">'
            f'<span class="t-due-name">{_esc(r.get("name", ""))}</span>'
            f'<span class="t-due-meta">{_esc(r.get("meta", ""))}</span>'
            f'<span class="t-due-amt">{_esc(r.get("amount", ""))}</span>'
            '</li>'
        )
    return f'<ul class="t-due-list">{"".join(items)}</ul>'


# ---------------------------------------------------------------------------
# Research rows — compact headline cards with evidence meta
# ---------------------------------------------------------------------------
def research_row(title, meta="", body="", tag="", href="", tone="", badge=""):
    safe_title = _esc(title)
    if href:
        safe_title = f'<a href="{_esc_attr(href)}" target="_blank" rel="noopener">{safe_title}</a>'
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


# ---------------------------------------------------------------------------
# Data sheet — two-column labelled dossier rows (Asset Detail, Deep Health)
# ---------------------------------------------------------------------------
def data_sheet(rows):
    """rows: list of dict(label, value, tone=None). tone: up|down|dim|accent.
    Two-column labelled rows; long values wrap, labels are the uppercase set."""
    cells = []
    for r in rows:
        label = _esc(r.get("label", ""))
        tone_cls = {"up": "up", "down": "down", "dim": "dim", "accent": "accent"}.get(r.get("tone"), "")
        val = f'<div class="t-sheet-value {tone_cls}">{_esc(r.get("value", ""))}</div>'
        cells.append(
            f'<div class="t-sheet-cell"><div class="t-sheet-label">{label}</div>{val}</div>'
        )
    if not cells:
        return '<div class="t-empty">No details to display.</div>'
    return f'<div class="t-sheet">{"".join(cells)}</div>'


# ---------------------------------------------------------------------------
# Outlook ladder — vertical month bars (Outlook)
# ---------------------------------------------------------------------------
def ladder_rows(rows):
    """rows: list of dict(label, value, meta=""). Bar widths are derived from the
    given values only (max value scales to 100%); missing values never render."""
    numeric = []
    for r in rows:
        try:
            numeric.append((r, max(0.0, float(r.get("value") or 0.0))))
        except (TypeError, ValueError):
            continue
    peak = max((v for _, v in numeric), default=0.0)
    if peak <= 0:
        return '<div class="t-empty">Nothing matures in this window.</div>'
    out = []
    for r, v in numeric:
        width = max(1.0, v / peak * 100) if v > 0 else 0.0
        meta = f'<div class="ladder-meta">{_esc(r.get("meta", ""))}</div>' if r.get("meta") else ""
        out.append(
            f'<div class="ladder-row"><div class="ladder-ym">{_esc(r.get("label", ""))}</div>'
            f'<div class="ladder-bar-wrap"><div class="ladder-bar" style="width:{width:.1f}%"></div></div>'
            f'<div class="ladder-val">{_fmt_compact(r.get("value"))}</div></div>'
            + (f'<div class="ladder-meta-row">{meta}</div>' if meta else "")
        )
    return '<div class="ladder">' + "".join(out) + "</div>"


def _fmt_compact(value):
    """INR compact formatting; delegates to the app's shared formatter so ladder
    values display identically everywhere (₹2.34 Cr)."""
    from lib.formatters import format_inr_compact
    try:
        return format_inr_compact(float(value))
    except (TypeError, ValueError):
        return "" if value in (None, "") else str(value)


# ---------------------------------------------------------------------------
# Northline briefing extras — health ring, five-sleeve strip, stance pill
# ---------------------------------------------------------------------------
def score_ring(score, label="HEALTH", sub="", size=96, stroke=7):
    """Radial health ring with the numeric score in the centre (Newsreader).
    score: number 0..100. The ring stroke colour is chosen by score band:
    ok (>=75) / warn (55-74) / urgent (<55)."""
    try:
        s = max(0.0, min(100.0, float(score)))
    except (TypeError, ValueError):
        s = 0.0
    band = "t-ring-ok" if s >= 75 else ("t-ring-warn" if s >= 55 else "t-ring-urgent")
    radius = (size - stroke) / 2.0
    circ = round(2 * 3.141592653589793 * radius, 3)
    filled = round(circ * s / 100.0, 3)
    sub_html = f'<div class="t-ring-sub">{_esc(sub)}</div>' if sub else ""
    return (
        f'<div class="t-ring-wrap {band}" style="width:{size}px;height:{size}px">'
        f'<svg class="t-ring" width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
        f'role="img" aria-label="{_esc_attr(label)} score {s:.0f}">'
        f'<circle class="t-ring-track" cx="{size/2}" cy="{size/2}" r="{radius}" '
        f'stroke-width="{stroke}"></circle>'
        f'<circle class="t-ring-progress" cx="{size/2}" cy="{size/2}" r="{radius}" '
        f'stroke-width="{stroke}" stroke-dasharray="{filled} {circ - filled}"></circle></svg>'
        f'<div class="t-ring-center"><div class="t-ring-score">{s:.0f}</div>'
        f'<div class="t-ring-label">{_esc(label)}</div>{sub_html}</div></div>'
    )


def weight_strip(parts, total=None):
    """Five-sleeve allocation strip for the Northline briefing.
    parts: list of dict(label, value, color). Renders one segmented bar plus a
    five-column legend. Percentages derive from the given values; absent
    sleeves simply do not render. Colours default to SLEEVE_COLORS-by-label."""
    from lib.theme import SLEEVE_COLORS
    labelled = {k.lower(): v for k, v in SLEEVE_COLORS.items()}
    norm = []
    for p in parts:
        try:
            v = max(0.0, float(p.get("value") or 0.0))
        except (TypeError, ValueError):
            continue
        label = str(p.get("label") or "")
        color = p.get("color") or labelled.get(label.lower(), "#c5cedb")
        norm.append((label, v, color))
    denominator = float(total) if total is not None else sum(v for _, v, _ in norm)
    if denominator <= 0:
        return '<div class="t-empty">No allocation to display.</div>'
    segs = []
    legend = []
    for label, v, color in norm:
        if v <= 0:
            continue
        pct = v / denominator * 100.0
        if pct >= 11:
            inlabel = (
                f'<span class="t-strip-in"><span class="t-strip-in-name">{_esc(label)}</span>'
                f'<span class="t-strip-in-pct">{pct:.0f}%</span></span>'
            )
        elif pct >= 7:
            inlabel = f'<span class="t-strip-in"><span class="t-strip-in-pct">{pct:.0f}%</span></span>'
        else:
            inlabel = ""
        segs.append(
            f'<div class="t-strip-seg" style="flex:0 0 {pct:.2f}%;background:{color}" '
            f'title="{_esc_attr(label)}: {v:,.0f}">{inlabel}</div>'
        )
        legend.append(
            f'<div class="t-sleeve">'
            f'<div class="t-sleeve-name"><span class="t-sleeve-dot" style="background:{color}"></span>{_esc(label)}</div>'
            f'<div class="t-sleeve-pct">{pct:.1f}%</div>'
            f'<div class="t-sleeve-val">{_fmt_compact(v)}</div></div>'
        )
    bar = f'<div class="t-strip-bar">{"".join(segs)}</div>'
    legend_html = f'<div class="t-strip-legend">{"".join(legend)}</div>' if legend else ""
    return f'<div class="t-strip">{bar}{legend_html}</div>'


def stance_pill(text, tone=""):
    """A single serene stance sentence as a wide pill. tone: ok | warn | crit."""
    cls = f" t-stance-{tone}" if tone else ""
    return f'<div class="t-stance{cls}">{text}</div>'


def dots(done, total, tone="neutral"):
    """Small step dots for a bounded progress context (e.g. 3 of 6 stages)."""
    t = int(total or 0)
    d = max(0, min(t, int(done or 0)))
    dots_html = "".join(
        f'<span class="t-dot{" t-dot-on" if i < d else ""}"></span>' for i in range(t)
    )
    return f'<span class="t-dots">{dots_html}</span>'
