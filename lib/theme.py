# -------------------------------------------------
# Design system — single shared dark institutional theme.
# R-1701 (SPEC §17): every page injects this one stylesheet via inject_css().
# No page carries its own <style> block anymore. Component HTML is emitted by
# lib/ui/components.py as declarative strings; the classes they reference live
# here (t-* prefix). Legacy classes (pulse-*, attn-*, mfh-*, section-header,
# etc.) are consolidated here too so existing page markup keeps working
# without duplicated CSS.
#
# Accessibility: high-contrast text tokens, status expressed via label text +
# glyph (never color alone), visible focus rings, reduced-motion respect.
# -------------------------------------------------
import streamlit as st

DESIGN_SYSTEM_CSS = r"""
/* ============ design tokens ============ */
:root {
  --c-bg: #0a0e17; --c-bg-card: #0e1420; --c-bg-surface: #0f1420;
  --c-bg-deep: #0c1220; --c-bg-raised: #0b0f18;
  --c-border: #1c2333; --c-border-hover: #2a3552; --c-border-subtle: #161d2d;
  --c-border-strong: #1a2233;
  --c-text: #f8fafc; --c-text-body: #e5e9f0; --c-text-secondary: #c2c9d6;
  --c-text-muted: #9aa4b8; --c-text-dim: #7c86a0; --c-text-faint: #6b7688;
  --c-text-ghost: #5b6478; --c-text-buried: #4b5570;
  --c-blue: #3b82f6; --c-blue-soft: #7fa8f5; --c-blue-dim: #6b8fd6;
  --c-green: #22c55e; --c-green-soft: #4ade80;
  --c-red: #ef4444; --c-red-soft: #f87171;
  --c-amber: #f59e0b; --c-amber-soft: #fbbf24;
  --c-teal: #06b6d4; --c-purple: #a855f7; --c-slate: #64748b;
  --page-accent: var(--c-blue-soft);
  --rail-w: 230px; --bar-h: 64px;
  --r-sm: 8px; --r-md: 10px; --r-lg: 12px; --r-pill: 999px;
  --sp-xs: 4px; --sp-sm: 8px; --sp-md: 14px; --sp-lg: 22px;
}

/* ============ base ============ */
.stApp { background: var(--c-bg); color: var(--c-text-body); -webkit-font-smoothing: antialiased; }
html, body, [data-testid="stAppViewContainer"] { background: var(--c-bg); }

* { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }

p, span, label, ul, ol, li, .stMarkdown, div[data-testid="stMarkdownContainer"] {
    color: var(--c-text-secondary) !important;
}
a { color: var(--c-blue-soft); text-decoration: none; }
a:hover { color: #a8c3fb; }

/* Header / chrome collapse for the app shell */
header[data-testid="stHeader"] {
    background: transparent !important; height: 0 !important; min-height: 0 !important;
    border: none !important; padding: 0 !important;
}
div[data-testid="stDecoration"] { display: none !important; }
div[data-testid="stToolbar"] { display: none !important; }
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
/* The product rail now lives IN the real Streamlit sidebar (lib/ui/nav.py):
   streamlit's own navigation widget is disabled, and the sidebar is styled to
   the brand rail. It must stay expanded — the collapse chevron is hidden. */
section[data-testid="stSidebarNavigation"] { display: none !important; }
[data-testid="stSidebar"] {
    width: var(--rail-w) !important; background: var(--c-bg-raised);
    border-right: 1px solid var(--c-border-strong);
}
[data-testid="stSidebarContent"] {
    padding: 26px 14px 18px 16px !important; overflow-y: auto;
    scrollbar-width: thin; scrollbar-color: var(--c-border-strong) transparent;
}
[data-testid="stSidebarResizeHandle"] { display: none !important; }
[data-testid="stSidebarCollapseButton"] { display: none !important; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 2px !important; }

/* ============ layout: use the desktop viewport ============ */
[data-testid="stMainBlockContainer"], .block-container {
    max-width: 1640px !important;
    margin-inline: auto;
    padding-top: 1.1rem !important;
    padding-bottom: 2rem;
}
@media (min-width: 992px) {
    [data-testid="stMainBlockContainer"], .block-container {
        padding-left: 2.25rem !important;
        padding-right: 2.25rem !important;
        padding-top: 1.1rem !important;
    }
    .nb-topbar { display: none; }
}
@media (max-width: 991px) {
    [data-testid="stMainBlockContainer"], .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        padding-top: 1.15rem !important;
        padding-bottom: calc(var(--bar-h) + 28px) !important;
    }
    .nb-topbar { display: flex; }
}

/* ============ typography scale ============ */
.t-kicker { font-size: 0.64rem; font-weight: 800; letter-spacing: 0.26em; text-transform: uppercase; color: var(--page-accent); margin: 0 0 9px 0; }
.t-title { font-size: 2.1rem; font-weight: 800; color: var(--c-text); letter-spacing: -0.015em; line-height: 1.05; margin: 0; font-family: Georgia, "Iowan Old Style", "Palatino Linotype", "Book Antiqua", "Times New Roman", serif; }
.t-sub { font-size: 0.86rem; color: var(--c-text-dim); font-weight: 400; margin: 10px 0 0 0; line-height: 1.55; max-width: 64ch; }
.t-meta-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 14px 0 2px 0; }
.t-meta-pill {
    font-size: 0.62rem; font-weight: 700; letter-spacing: 0.05em; color: var(--c-text-faint);
    background: var(--c-bg-surface); border: 1px solid var(--c-border); border-radius: var(--r-pill);
    padding: 3px 9px; font-variant-numeric: tabular-nums;
}
.t-meta-pill b { color: var(--c-text-secondary); font-weight: 700; }
.t-section-desc { font-size: 0.78rem; color: var(--c-text-dim); margin: 7px 0 2px 0; line-height: 1.5; max-width: 72ch; }

/* Section header: label — rule — meta, with guaranteed gaps (never concat).
   A leading index chip (Deep Health step numbers, e.g. 01) is .t-section-index. */
.t-section { margin: 2.1rem 0 0.8rem 0; }
.t-section-title {
    font-size: 0.72rem; font-weight: 800; color: var(--c-text-muted); text-transform: uppercase;
    letter-spacing: 0.12em; display: flex; align-items: center; gap: 12px; margin: 0;
}
.t-section-index {
    font-size: 0.66rem; font-weight: 800; letter-spacing: 0.02em; color: var(--c-blue-soft);
    background: rgba(59,130,246,0.12); border: 1px solid rgba(59,130,246,0.22);
    border-radius: 5px; padding: 2px 7px; flex: none; white-space: nowrap;
    color: var(--page-accent);
    background: color-mix(in srgb, var(--page-accent) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--page-accent) 24%, transparent);
}
.t-section-lbl { flex: none; white-space: nowrap; }
.t-section-title::after { content: ""; flex: 1; height: 1px; background: var(--c-border-strong); }
.t-section-meta {
    font-size: 0.67rem; color: var(--c-text-ghost); font-weight: 600; letter-spacing: 0.03em;
    text-transform: none; flex: none; white-space: nowrap;
}

/* ============ Streamlit element restyle ============ */
div[data-testid="stMetric"] {
    background: var(--c-bg-card);
    border: 1px solid var(--c-border); border-radius: var(--r-md); padding: 12px 15px 10px 15px;
}
div[data-testid="stMetric"]:hover { border-color: var(--c-border-hover); }
div[data-testid="stMetricValue"] { font-size: 1.35rem !important; font-weight: 700 !important; color: var(--c-text) !important; font-variant-numeric: tabular-nums; }
div[data-testid="stMetricLabel"] { color: var(--c-text-faint) !important; font-size: 0.64rem !important; font-weight: 700 !important; text-transform: uppercase; letter-spacing: 0.1em; }
div[data-testid="stMetricDelta"] { font-size: 0.75rem !important; }
div[data-testid="stCaptionContainer"] p { font-size: 0.72rem; color: var(--c-text-ghost); line-height: 1.55; }

.stTabs [data-baseweb="tab-list"] { background-color: var(--c-bg-surface); gap: 3px; border-radius: 9px; padding: 3px; border: 1px solid var(--c-border); width: fit-content; max-width: 100%; overflow-x: auto; }
.stTabs [data-baseweb="tab"] { color: var(--c-text-faint) !important; border-radius: 6px; padding: 8px 18px; font-weight: 500; }
.stTabs [aria-selected="true"] { background: #141d31 !important; color: var(--c-text) !important; font-weight: 600; }

.stDataFrame, [data-testid="stDataFrame"] {
    border: 1px solid var(--c-border); border-radius: 10px; overflow: hidden;
}
.stDataFrame *, [data-testid="stDataFrame"] * { font-size: 0.76rem; }
.stDataFrame [data-testid="stDataFrame"] {
    --grid-border-color: var(--c-border-subtle);
}
.stExpander { border: 1px solid var(--c-border) !important; border-radius: 10px !important; background: var(--c-bg-deep) !important; }
.stExpander summary { font-size: 0.82rem !important; font-weight: 600; color: var(--c-text-secondary); }
div[data-baseweb="select"] > div, div[data-testid="stNumberInput"] input,
div[data-testid="stTextInput"] input, div[data-testid="stSelectbox"] > div > div {
    background-color: var(--c-bg-surface) !important; border-color: var(--c-border-hover) !important; color: var(--c-text-body) !important;
}
div[data-testid="stNumberInput"] input { color: var(--c-text) !important; font-weight: 600; }
.stButton > button, .stDownloadButton > button {
    background: #141c2e !important; border: 1px solid var(--c-border-hover) !important; color: #d7dce6 !important;
    border-radius: 8px; font-weight: 600; font-size: 0.8rem; padding: 0.5rem 1rem;
}
.stButton > button[kind="primary"] { background: #1e3a8a !important; border-color: var(--c-blue) !important; color: #fff !important; }
.stButton > button:hover, .stDownloadButton > button:hover { border-color: var(--c-blue) !important; }
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible,
input:focus-visible, [data-testid="stSelectbox"]:focus-within { outline: 2px solid var(--c-blue) !important; outline-offset: 1px; }

.stProgress > div > div > div { background: var(--c-blue); }

/* checkbox / multiselect / radio restyle for the terminal look */
[data-testid="stCheckbox"] span { font-size: 0.8rem; color: var(--c-text-secondary); }
[data-testid="stRadio"] label > div:first-child { background: var(--c-blue); }
.stMultiSelect [data-baseweb="tag"], [data-baseweb="tag"] {
    background: var(--c-bg-surface) !important; border: 1px solid var(--c-border-hover) !important;
}
[data-testid="stMultiSelect"] [data-baseweb="tag"] span { color: var(--c-text-secondary) !important; }
.stSlider [data-baseweb="slider"] div[role="slider"] { background: var(--c-blue); border-color: var(--c-blue); }

/* ============ product shell ============
   Desktop rail lives in the real Streamlit sidebar (styled above); the mobile
   bottom bar is a real element container pinned by its st-key-nb_mobile_bar
   class. Nav items are st.page_link elements routed inside the same websocket
   session (state-preserving) — except the current page, which renders as a
   static .nb-active badge instead of a self-link. */
.nb-brand { border-left: 2px solid var(--page-accent); padding-left: 12px; }
.nb-brand-name { font-size: 0.9rem; font-weight: 800; letter-spacing: 0.3em; color: var(--c-text); }
.nb-brand-sub { font-size: 0.62rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--c-text-ghost); margin-top: 3px; }
.nb-group-label {
    font-size: 0.56rem; font-weight: 800; letter-spacing: 0.2em; color: var(--c-text-buried);
    text-transform: uppercase; padding: 0 10px 8px 10px; margin-top: 20px;
}
[data-testid="stSidebar"] .nb-group-label:first-of-type { margin-top: 26px; }

/* nav-link look shared by st.page_link anchors and the static active badge */
.nb-link, [data-testid="stPageLink-NavLink"] {
    display: flex !important; align-items: center; gap: 10px; margin: 1px 0 !important;
    padding: 8px 10px !important; border-radius: 7px; font-size: 0.8rem; font-weight: 500;
    color: var(--c-text-muted); border-left: 2px solid transparent; width: 100%;
}
[data-testid="stPageLink-NavLink"]:hover, [data-testid="stPageLink-NavLink"]:focus-visible,
.nb-link:hover { background: var(--c-bg-surface); color: #dce2ec; }
.nb-link.nb-active, .nb-bar-item.nb-active {
    background: var(--c-bg-surface); color: var(--c-text); font-weight: 600;
    border-left: 2px solid var(--page-accent);
}
.nb-glyph { width: 14px; text-align: center; color: var(--c-slate); font-size: 0.74rem; flex: none; }
.nb-active .nb-glyph { color: var(--page-accent); }
[data-testid="stPageLink"] { margin: 0 !important; padding: 0 !important; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] { margin: 0; }
.nb-rail-foot {
    font-size: 0.6rem; line-height: 1.55; color: var(--c-text-buried); letter-spacing: 0.05em;
    padding: 14px 10px 2px 10px; border-top: 1px solid var(--c-border-subtle); margin-top: 10px;
}
/* mobile top brand (only ≤991px; hidden elsewhere) */
.nb-topbar {
    display: none; align-items: baseline; gap: 10px; margin: 2px 0 16px 0;
    padding: 0 0 14px 0; border-bottom: 1px solid var(--c-border-subtle);
    border-left: 2px solid var(--page-accent); padding-left: 12px;
}
.nb-top-name { font-size: 0.8rem; font-weight: 800; letter-spacing: 0.26em; color: var(--c-text); }
.nb-top-sub { font-size: 0.6rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--c-text-ghost); }

/* mobile bottom bar: a real element container docked by its st-key class */
.st-key-nb_mobile_bar { display: none; }
@media (max-width: 991px) {
    section[data-testid="stSidebar"] { display: none !important; }
    .st-key-nb_mobile_bar {
        display: block; position: fixed; left: 0; right: 0; bottom: 0; z-index: 950;
        background: var(--c-bg-raised); border-top: 1px solid var(--c-border-strong);
        padding: 6px 2px calc(8px + env(safe-area-inset-bottom));
    }
    .st-key-nb_mobile_bar [data-testid="stElementContainer"], .st-key-nb_mobile_bar [data-testid="stColumn"] { padding: 0 !important; }
    .st-key-nb_mobile_bar [data-testid="stHorizontalBlock"] { gap: 0 !important; }
    .nb-bar-item {
        flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; align-items: center; gap: 3px;
        padding: 8px 1px 6px; color: var(--c-text-faint); font-size: 0.56rem; letter-spacing: 0.02em; font-weight: 600;
        position: relative;
    }
    .nb-bar-item .nb-glyph { font-size: 1.05rem; color: var(--c-text-dim); }
    .nb-bar-item.nb-active { color: var(--c-text); }
    .nb-bar-item.nb-active .nb-glyph { color: var(--page-accent); }
    .nb-bar-item.nb-active::before {
        content: ""; position: absolute; top: 0; left: 50%; transform: translateX(-50%);
        width: 22px; height: 2px; border-radius: var(--r-pill); background: var(--page-accent);
    }
    .st-key-nb_mobile_bar [data-testid="stPageLink-NavLink"] {
        flex-direction: column !important; justify-content: center; align-items: center; gap: 3px !important;
        margin: 0 !important; padding: 8px 1px 6px !important; border-left: none !important; border-radius: 0 !important;
        background: transparent !important; color: var(--c-text-faint) !important;
        font-size: 0.56rem !important; letter-spacing: 0.02em !important; font-weight: 600 !important;
        position: relative; height: 100%;
    }
    .st-key-nb_mobile_bar [data-testid="stPageLink"] { margin: 0 !important; padding: 0 !important; width: 100%; }
    .st-key-nb_mobile_bar [data-testid="stPageLink-NavLink"]:hover { background: transparent !important; }
}

/* drill row + drill page_links (in-app hooks, same session-preserving primitive) */
.st-key-nb_drill_links { display: flex; flex-wrap: wrap; gap: 6px 14px; margin: 4px 0 2px 0; }
.st-key-nb_drill_links [data-testid="stPageLink"] { margin: 0 !important; padding: 0 !important; }
.st-key-nb_drill_links [data-testid="stPageLink-NavLink"] {
    margin: 0 !important; padding: 0 !important; background: transparent !important;
    color: #93c5fd !important; font-size: 0.76rem !important; font-weight: 600 !important;
    border: none !important; text-decoration: none; width: auto !important; display: inline-flex !important;
}
.st-key-nb_drill_links [data-testid="stPageLink-NavLink"]:hover { color: #bfdbfe !important; text-decoration: underline; }
.st-key-nb_drill_links [data-testid="stPageLink-NavLink"]::before { content: "→ "; color: var(--c-text-ghost); font-weight: 400; }

/* ============ shared terminal components (t-*) ============ */
.t-kpi-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; margin: 4px 0 6px 0; }
.t-kpi-grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.t-kpi-grid-5 { grid-template-columns: repeat(5, minmax(0, 1fr)); }
@media (max-width: 1200px) { .t-kpi-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 700px)  { .t-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.t-kpi {
    background: var(--c-bg-card);
    border: 1px solid var(--c-border); border-radius: var(--r-md); padding: 13px 15px 12px 15px;
    min-height: 82px; display: flex; flex-direction: column; justify-content: space-between;
}
.t-kpi:hover { border-color: var(--c-border-hover); }
.t-kpi-label { font-size: 0.62rem; font-weight: 800; color: var(--c-text-faint); text-transform: uppercase; letter-spacing: 0.1em; }
.t-kpi-value { font-size: 1.2rem; font-weight: 800; color: var(--c-text); margin-top: 6px; font-variant-numeric: tabular-nums; line-height: 1.1; word-break: break-word; }
.t-kpi-sub { font-size: 0.68rem; color: var(--c-text-dim); margin-top: 5px; font-weight: 500; line-height: 1.4; }
.t-kpi-tone-up .t-kpi-value { color: var(--c-green-soft); }
.t-kpi-tone-down .t-kpi-value { color: var(--c-red-soft); }
.t-kpi-tone-warn .t-kpi-value { color: var(--c-amber-soft); }
.t-kpi-tone-accent .t-kpi-value { color: var(--page-accent); }
.t-kpi-foot { font-size: 0.62rem; color: var(--c-text-ghost); margin-top: 6px; font-weight: 600; letter-spacing: 0.02em; }

.t-pill {
    display: inline-flex; align-items: center; gap: 6px; font-size: 0.7rem; font-weight: 700;
    color: var(--c-text-muted); background: var(--c-bg-surface); border: 1px solid #262f45; border-radius: var(--r-pill); padding: 4px 11px;
}
.t-pill .t-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--c-slate); flex: none; }
.t-pill-ok   .t-dot { background: var(--c-green); } .t-pill-ok { color: #86efac; border-color: rgba(34,197,94,0.35); }
.t-pill-cache .t-dot { background: var(--c-amber); } .t-pill-cache { color: #fde68a; border-color: rgba(234,179,8,0.35); }
.t-pill-off  .t-dot { background: var(--c-red); } .t-pill-off { color: #fca5a5; border-color: rgba(239,68,68,0.35); }
.t-pill-info .t-dot { background: #60a5fa; } .t-pill-info { color: #93c5fd; border-color: rgba(96,165,250,0.35); }

.t-badge {
    display: inline-block; padding: 2px 9px; border-radius: var(--r-pill); font-size: 0.64rem;
    font-weight: 800; letter-spacing: 0.04em; background: rgba(100,116,139,0.16); color: #94a3b8; border: 1px solid transparent;
}
.t-badge-pos  { background: rgba(34,197,94,0.14);  color: var(--c-green-soft); }
.t-badge-neg  { background: rgba(239,68,68,0.14);  color: var(--c-red-soft); }
.t-badge-warn { background: rgba(245,158,11,0.14); color: var(--c-amber-soft); }
.t-badge-info { background: rgba(59,130,246,0.14); color: #93c5fd; }
.t-badge-live { background: rgba(34,197,94,0.18);  color: var(--c-green-soft); border-color: rgba(34,197,94,0.3); }
.t-badge-stale{ background: rgba(245,158,11,0.18); color: var(--c-amber-soft); border-color: rgba(245,158,11,0.3); }

/* Fact-kind chips: the provenance taxonomy from lib.intelligence.model */
.t-chip { display: inline-block; padding: 2px 8px; border-radius: 5px; font-size: 0.6rem; font-weight: 800; letter-spacing: 0.07em; }
.t-chip-fact  { background: rgba(59,130,246,0.16);  color: #93c5fd; }
.t-chip-calc  { background: rgba(34,197,94,0.14);  color: #4ade80; }
.t-chip-signal{ background: rgba(245,158,11,0.14); color: #fbbf24; }
.t-chip-ai    { background: rgba(168,85,247,0.16); color: #d8b4fe; }
.t-chip-reco  { background: rgba(239,68,68,0.14);  color: #f87171; }

.t-source { font-size: 0.66rem; color: var(--c-text-ghost); font-weight: 600; letter-spacing: 0.03em; }
.t-caption { font-size: 0.72rem; color: var(--c-text-ghost); line-height: 1.55; display: inline-block; }
.t-caption-pos { color: #6ee7a0; }
.t-caption-neg { color: #fca5a5; }
.t-caption-warn { color: #fcd34d; }
.t-footnote { font-size: 0.66rem; color: var(--c-text-buried); line-height: 1.5; }
.t-empty {
    border: 1px dashed #262f45; border-radius: var(--r-md); padding: 16px 18px; color: var(--c-text-muted);
    font-size: 0.78rem; background: var(--c-bg-deep);
}
.t-empty b { color: var(--c-text-secondary); }
.t-empty-hint { margin-top: 8px; font-size: 0.72rem; color: var(--c-text-ghost); line-height: 1.55; }

.t-card { background: var(--c-bg-card);
    border: 1px solid var(--c-border); border-radius: var(--r-md); padding: 14px 16px;
    font-size: 0.8rem; color: var(--c-text-muted); line-height: 1.55; }
.t-card a { color: #7cb3ff; }
.t-card-summary { font-size: 0.9rem; color: var(--c-text-body); }
.t-card-title { display: block; font-size: 0.8rem; font-weight: 700; color: #f1f5f9; margin-bottom: 6px; }
.t-list { margin: 0; padding-left: 18px; }
.t-list li { margin: 3px 0; }
.t-list-title { font-size: 0.66rem; font-weight: 700; color: var(--c-text-faint); text-transform: uppercase; letter-spacing: 0.1em; }
.t-list-row { display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
    font-size: 0.78rem; padding: 8px 0; border-bottom: 1px solid var(--c-border-subtle); }
.t-list-name { color: var(--c-text-body); font-weight: 600; }
.t-list-meta { color: var(--c-text-muted); font-variant-numeric: tabular-nums; }

.t-banner { border-radius: var(--r-md); padding: 11px 15px; margin: 10px 0 4px 0; border: 1px solid; font-size: 0.8rem; line-height: 1.45; }
.t-banner-critical { background: #3b1219; border-color: #7f1d1d; color: #fecaca; }
.t-banner-warn { background: #2b2010; border-color: #78350f; color: #fde68a; }
.t-banner-info { background: #0f1a2e; border-color: #1e3a5f; color: #cbd9f5; }
.t-banner-ok { background: #0e2418; border-color: #14532d; color: #bbf7d0; }
.t-banner b { color: inherit; }
.t-banner a { color: inherit; text-decoration: underline; }

/* horizontal stacked allocation bar */
.t-bar-track {
    display: flex; width: 100%; height: 18px; border-radius: var(--r-pill); overflow: hidden;
    border: 1px solid var(--c-border); background: var(--c-bg-deep); margin: 8px 0 2px 0;
}
.t-bar-seg { height: 100%; min-width: 0; }

.t-alloc-legend { list-style: none; margin: 8px 0 0 0; padding: 0; }
.t-alloc-legend li { display: flex; justify-content: space-between; gap: 12px; font-size: 0.75rem; color: var(--c-text-muted); padding: 5px 0; border-bottom: 1px solid var(--c-border-subtle); }
.t-alloc-legend .nm { color: var(--c-text-body); font-weight: 600; }
.t-alloc-legend .amt { font-variant-numeric: tabular-nums; color: var(--c-text-secondary); }

/* maturity ladder (Outlook) */
.ladder-row { display: grid; grid-template-columns: 84px 1fr 96px; align-items: center; gap: 12px; padding: 9px 0; border-bottom: 1px solid var(--c-border-subtle); }
@media (max-width: 620px) { .ladder-row { grid-template-columns: 72px 1fr; } .ladder-val { grid-column: 2; text-align: left; } }
.ladder-ym { font-size: 0.72rem; font-weight: 700; color: var(--c-text-muted); letter-spacing: 0.03em; }
.ladder-bar-wrap { height: 18px; background: var(--c-bg-deep); border: 1px solid var(--c-border-strong); border-radius: var(--r-pill); overflow: hidden; }
.ladder-bar { height: 100%; background: var(--c-blue); border-radius: var(--r-pill); min-width: 1px; }
.ladder-val { font-size: 0.78rem; font-weight: 700; color: #f1f5f9; font-variant-numeric: tabular-nums; text-align: right; }
.ladder-meta-row { text-align: right; font-size: 0.64rem; color: var(--c-text-ghost); padding: 2px 0 6px 0; }

/* attention tiles */
.t-attn-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 8px 0 8px 0; }
@media (max-width: 1100px) { .t-attn-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 640px)  { .t-attn-grid { grid-template-columns: 1fr; } }
.t-attn-tile { border-radius: var(--r-md); padding: 12px 14px; border: 1px solid; min-height: 92px; background: var(--c-bg-surface); }
.t-attn-tag { display: inline-block; font-size: 0.58rem; font-weight: 800; letter-spacing: 0.07em; padding: 2px 7px; border-radius: 4px; margin-bottom: 6px; }
.t-tag-urgent { background: #7f1d1d; color: #fecaca; }
.t-tag-review { background: #78350f; color: #fde68a; }
.t-tag-upcoming { background: #1e3a5f; color: #93c5fd; }
.t-attn-title { font-size: 0.82rem; font-weight: 700; color: #f1f5f9; margin: 0 0 3px 0; line-height: 1.25; }
.t-attn-body { font-size: 0.7rem; color: var(--c-text-muted); margin: 0; line-height: 1.35; }

/* ============ executive hero ============ */
.t-hero {
    display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 14px;
    background: var(--c-bg-deep);
    border: 1px solid var(--c-border); border-radius: 16px; padding: 24px 28px;
    margin: 14px 0 20px 0;
}
@media (max-width: 900px) { .t-hero { grid-template-columns: 1fr; } }
.t-hero-main { display: flex; flex-direction: column; justify-content: center; }
.t-hero-kicker { font-size: 0.62rem; font-weight: 800; letter-spacing: 0.24em; text-transform: uppercase; color: var(--page-accent); margin: 0 0 10px 0; }
.t-hero-value { font-size: 3.0rem; font-weight: 800; color: var(--c-text); letter-spacing: -0.03em; line-height: 1.02; font-variant-numeric: tabular-nums; word-break: break-word; }
.t-hero-tone-up .t-hero-value { color: var(--c-green-soft); }
.t-hero-tone-down .t-hero-value { color: var(--c-red-soft); }
.t-hero-tone-warn .t-hero-value { color: var(--c-amber-soft); }
.t-hero-tone-accent .t-hero-value { color: var(--page-accent); }
.t-hero-delta { margin-top: 10px; font-size: 0.8rem; font-weight: 600; color: #93c5fd; }
.t-hero-sub { margin-top: 6px; font-size: 0.78rem; color: var(--c-text-muted); }
.t-hero-foot { margin-top: 18px; font-size: 0.7rem; color: var(--c-text-ghost); line-height: 1.5; }
.t-hero-side { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; align-items: stretch; }
@media (max-width: 560px) { .t-hero-side { grid-template-columns: 1fr; } }
.t-hero-side .t-kpi { min-height: 92px; }
.t-kpi-tall { min-height: 96px; }

/* ============ watchlist (restrained attention) ============ */
.t-watch-list { display: flex; flex-direction: column; gap: 8px; margin: 8px 0 8px 0; }
.t-watch {
    display: flex; gap: 12px; background: var(--c-bg-surface); border: 1px solid var(--c-border);
    border-radius: var(--r-md); padding: 12px 15px; align-items: flex-start;
}
.t-watch:hover { border-color: var(--c-border-hover); }
.t-watch-bar { flex: none; width: 4px; align-self: stretch; border-radius: var(--r-pill); }
.t-watch-urgent .t-watch-bar { background: var(--c-red); }
.t-watch-warn   .t-watch-bar { background: var(--c-amber); }
.t-watch-info   .t-watch-bar { background: var(--c-blue); }
.t-watch-main { flex: 1; min-width: 0; }
.t-watch-tag { display: inline-block; font-size: 0.58rem; font-weight: 800; letter-spacing: 0.07em; padding: 1px 7px; border-radius: 4px; margin-bottom: 5px; }
.t-watch-urgent .t-watch-tag { background: rgba(239,68,68,0.16); color: #fca5a5; }
.t-watch-warn   .t-watch-tag { background: rgba(245,158,11,0.16); color: #fde68a; }
.t-watch-info   .t-watch-tag { background: rgba(59,130,246,0.16); color: #93c5fd; }
.t-watch-title { font-size: 0.84rem; font-weight: 700; color: #f1f5f9; margin: 0 0 3px 0; line-height: 1.3; }
.t-watch-title a { color: #f1f5f9; }
.t-watch-title a:hover { color: var(--c-blue-soft); }
.t-watch-body { font-size: 0.74rem; color: var(--c-text-muted); margin: 0; line-height: 1.45; }
.t-watch-why { margin-top: 6px; font-size: 0.7rem; color: var(--c-text-dim); line-height: 1.45; }
.t-watch-why b { color: #93c5fd; font-weight: 600; }

/* ============ research rows ============ */
.t-research-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 10px 0 4px 0; }
@media (max-width: 1100px) { .t-research-grid { grid-template-columns: 1fr; } }
.t-research {
    background: var(--c-bg-surface); border: 1px solid var(--c-border); border-radius: var(--r-md); padding: 12px 15px;
    min-height: 92px; display: flex; flex-direction: column; justify-content: flex-start;
}
.t-research:hover { border-color: var(--c-border-hover); }
.t-research-top { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.t-research-tag { font-size: 0.58rem; font-weight: 800; letter-spacing: 0.06em; padding: 1px 7px; border-radius: 4px; background: rgba(59,130,246,0.14); color: #93c5fd; }
.t-research-meta { margin-left: auto; font-size: 0.64rem; color: var(--c-text-ghost); font-weight: 500; white-space: nowrap; }
.t-research-title { font-size: 0.84rem; font-weight: 600; color: #eef2f7; line-height: 1.35; margin: 0; }
.t-research-title a { color: #eef2f7; }
.t-research-title a:hover { color: var(--c-blue-soft); }
.t-research-body { margin-top: 6px; font-size: 0.73rem; color: var(--c-text-muted); line-height: 1.5; }

/* ============ unavailable (single deliberate empty state) ============ */
.t-unavailable {
    background: var(--c-bg-deep); border: 1px dashed #262f45; border-radius: var(--r-md);
    padding: 24px 28px; text-align: center; margin: 8px 0;
}
.t-unavail-mark { font-size: 1.3rem; font-weight: 300; color: #3b485f; letter-spacing: 0.1em; }
.t-unavail-title { font-size: 0.85rem; font-weight: 600; color: var(--c-text-muted); margin-top: 4px; }
.t-unavail-detail { font-size: 0.73rem; color: var(--c-text-ghost); margin-top: 3px; }

/* ============ evidence trail ============ */
.t-evidence { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.t-evidence-bit {
    font-size: 0.62rem; color: var(--c-text-dim); background: var(--c-bg-surface); border: 1px solid var(--c-border);
    border-radius: 5px; padding: 1px 7px; font-weight: 500;
}

/* ============ legacy classes (consolidated from pages) ============ */
.main-title { font-size: 1.7rem; font-weight: 700; color: var(--c-text); letter-spacing: -0.012em; margin: 0 0 0.05rem 0; padding-top: 0.35rem; position: relative; z-index: 2; font-family: Georgia, "Iowan Old Style", "Palatino Linotype", "Book Antiqua", "Times New Roman", serif; }
.sub-title { color: var(--c-text-faint); font-size: 0.82rem; margin-bottom: 0.8rem; font-weight: 400; }
.section-header {
    font-size: 0.72rem; font-weight: 800; color: var(--c-text-muted); margin: 1.45rem 0 0.6rem 0;
    text-transform: uppercase; letter-spacing: 0.12em; display: flex; align-items: center; gap: 8px;
}
.section-header::after { content: ""; flex: 1; height: 1px; background: var(--c-border-strong); }
.caveat { font-size: 0.72rem; color: var(--c-text-ghost); font-style: italic; }
.recon-pass { color: var(--c-green); font-weight: 600; }
.recon-fail { color: var(--c-red); font-weight: 600; }
.snap-note { font-size: 0.72rem; color: var(--c-text-faint); margin-top: 4px; }

.status-row { display: flex; flex-wrap: wrap; gap: 10px; margin: 6px 0 4px 0; }
.status-pill { font-size: 0.7rem; color: var(--c-text-muted); background: var(--c-bg-surface); border: 1px solid var(--c-border); border-radius: var(--r-pill); padding: 4px 10px; font-weight: 600; }
.status-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; }
.dot-live { background: var(--c-green); }
.dot-cache { background: var(--c-amber); }
.dot-off { background: var(--c-red); }

.flag-card { border-radius: 8px; padding: 7px 10px; margin-bottom: 0; display: flex; gap: 8px; align-items: flex-start; border: 1px solid; }
.flag-critical { background: rgba(239,68,68,0.08); border-color: rgba(239,68,68,0.28); }
.flag-warning  { background: rgba(245,158,11,0.08); border-color: rgba(245,158,11,0.28); }
.flag-info     { background: rgba(59,130,246,0.08); border-color: rgba(59,130,246,0.28); }
.flag-title { font-weight: 600; font-size: 0.78rem; color: #f1f5f9; margin: 0; line-height: 1.25; }
.flag-body  { font-size: 0.7rem; color: var(--c-text-muted); margin: 1px 0 0 0; line-height: 1.3; }
.flag-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 4px; }
@media (max-width: 900px) { .flag-grid { grid-template-columns: 1fr; } }

.attn-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 6px 0 8px 0; }
@media (max-width: 1100px) { .attn-grid { grid-template-columns: repeat(2, 1fr); } }
.attn-tile { border-radius: 10px; padding: 10px 12px; border: 1px solid; min-height: 88px; }
.attn-tag { display: inline-block; font-size: 0.6rem; font-weight: 800; letter-spacing: 0.06em; padding: 2px 7px; border-radius: 4px; margin-bottom: 6px; }
.tag-urgent { background: #7f1d1d; color: #fecaca; }
.tag-review { background: #78350f; color: #fde68a; }
.tag-upcoming { background: #1e3a5f; color: #93c5fd; }
.attn-title { font-size: 0.82rem; font-weight: 700; color: #f1f5f9; margin: 0 0 3px 0; line-height: 1.25; }
.attn-body { font-size: 0.7rem; color: var(--c-text-muted); margin: 0; line-height: 1.3; }

.crit-banner { background: #3b1219; border: 1px solid #7f1d1d; color: #fecaca; border-radius: 10px; padding: 10px 14px; margin: 8px 0 4px 0; font-size: 0.82rem; }
.crit-banner b { color: #fecaca; }

.pulse-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 8px 0 4px 0; }
@media (max-width: 1100px) { .pulse-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.pulse-card { background: var(--c-bg-card); border: 1px solid var(--c-border); border-radius: var(--r-md); padding: 12px 14px; min-height: 78px; overflow: hidden; }
.pulse-card:hover { border-color: var(--c-border-hover); }
.pulse-label { font-size: 0.65rem; font-weight: 700; color: var(--c-text-faint); text-transform: uppercase; letter-spacing: 0.08em; }
.pulse-val { font-size: 1.05rem; font-weight: 700; color: var(--c-text); margin-top: 2px; font-variant-numeric: tabular-nums; }
.pulse-chg-up { color: var(--c-green); font-size: 0.78rem; font-weight: 700; }
.pulse-chg-dn { color: var(--c-red); font-size: 0.78rem; font-weight: 700; }
.pulse-chg-na { color: var(--c-text-ghost); font-size: 0.78rem; }

.ticker-wrap { width: 100%; overflow: hidden; background: var(--c-bg-raised); border: 1px solid var(--c-border); border-radius: var(--r-md); padding: 10px 0; white-space: nowrap; margin: 8px 0 4px 0; }
.ticker-move { display: inline-block; animation: ticker-scroll 50s linear infinite; }
.ticker-wrap:hover .ticker-move { animation-play-state: paused; }
@keyframes ticker-scroll { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
.ticker-item { display: inline-flex; align-items: baseline; gap: 6px; padding: 0 26px; font-size: 0.82rem; font-weight: 600; color: var(--c-text-body); }
.ticker-name { color: var(--c-text-muted); font-weight: 600; letter-spacing: 0.02em; }
.ticker-val { color: var(--c-text); font-variant-numeric: tabular-nums; }
.ticker-chg { font-weight: 700; font-variant-numeric: tabular-nums; }
.ticker-up .ticker-chg, .ticker-up .ticker-arrow { color: var(--c-green); }
.ticker-down .ticker-chg, .ticker-down .ticker-arrow { color: var(--c-red); }
.ticker-arrow { font-size: 0.95rem; font-weight: 800; }
.ticker-na { color: var(--c-text-ghost); }

.why-box { background: var(--c-bg-surface); border: 1px solid var(--c-border); border-radius: var(--r-md); padding: 10px 14px; margin-top: 8px; }
.why-box li { color: var(--c-text-muted); font-size: 0.78rem; margin: 3px 0; }

.alloc-legend { list-style: none; margin: 8px 0 0 0; padding: 0; }
.alloc-legend li { display: flex; justify-content: space-between; gap: 12px; font-size: 0.78rem; color: var(--c-text-muted); padding: 4px 0; border-bottom: 1px solid var(--c-border-subtle); }
.alloc-legend .nm { color: var(--c-text-body); font-weight: 600; }
.alloc-legend .amt { font-variant-numeric: tabular-nums; color: var(--c-text-secondary); }

.news-item { padding: 8px 0; border-bottom: 1px solid var(--c-border); }
.news-item a { color: #d7dce6 !important; text-decoration: none; font-size: 0.84rem; font-weight: 500; }
.news-item a:hover { color: var(--c-blue-soft) !important; }
.news-meta { font-size: 0.71rem; color: var(--c-text-ghost); margin-top: 1px; }

/* ============ MF Health consolidated classes ============ */
.mfh-card { background: var(--c-bg-card); border: 1px solid var(--c-border); border-radius: 14px; padding: 16px 18px; }
.mfh-kpi-label { font-size: 0.68rem; font-weight: 700; color: var(--c-text-faint); text-transform: uppercase; letter-spacing: 0.08em; }
.mfh-kpi-val { font-size: 1.55rem; font-weight: 800; color: var(--c-text); margin: 4px 0 2px 0; }
.mfh-kpi-sub { font-size: 0.72rem; color: var(--c-text-faint); }
.mfh-badge { display: inline-block; padding: 2px 9px; border-radius: var(--r-pill); font-size: 0.68rem; font-weight: 700; }
.badge-low    { background: rgba(34,197,94,0.14);  color: var(--c-green-soft); }
.badge-mod    { background: rgba(245,158,11,0.14); color: var(--c-amber-soft); }
.badge-high   { background: rgba(239,68,68,0.14);  color: var(--c-red-soft); }
.badge-vhigh  { background: rgba(239,68,68,0.22);  color: #fca5a5; }

.score-circle {
    display: inline-flex; align-items: center; justify-content: center;
    width: 38px; height: 38px; border-radius: 50%; font-weight: 800; font-size: 0.82rem;
    border: 3px solid;
}
.sc-excellent { border-color: var(--c-green); color: var(--c-green-soft); }
.sc-good      { border-color: var(--c-amber); color: var(--c-amber-soft); }
.sc-average   { border-color: #f97316; color: #fb923c; }
.sc-poor      { border-color: var(--c-red); color: var(--c-red-soft); }

.fund-row { border-bottom: 1px solid var(--c-border); padding: 10px 4px; }
.fund-name { color: #f1f5f9 !important; font-weight: 600; font-size: 0.86rem; }
.fund-amc  { color: var(--c-text-faint) !important; font-size: 0.72rem; }
.cat-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--c-blue); margin-right: 6px; }

/* horizontal rules — consistent with section-title hairline */
hr, [data-testid="stMarkdownHorizontalBlock"] { border: none !important; height: 1px !important; background: var(--c-border-strong) !important; margin: 1.8rem 0 !important; }

/* section wrapper — provides the intended vertical rhythm around .t-section-title */
.t-section { margin: 2.1rem 0 0.8rem 0; }

/* ============ data sheet — two-column labelled dossier rows ============ */
.t-sheet { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 26px; margin: 2px 0 6px 0; }
.t-sheet-cell { padding: 9px 0; border-bottom: 1px solid var(--c-border-subtle); min-width: 0; }
.t-sheet-label { font-size: 0.62rem; font-weight: 800; color: var(--c-text-faint); text-transform: uppercase; letter-spacing: 0.1em; }
.t-sheet-value { font-size: 0.84rem; font-weight: 600; color: var(--c-text); margin-top: 3px; font-variant-numeric: tabular-nums; word-break: break-word; }
.t-sheet-value.up   { color: var(--c-green-soft); }
.t-sheet-value.down { color: var(--c-red-soft); }
.t-sheet-value.dim  { color: var(--c-text-muted); font-weight: 500; }
.t-sheet-value.accent { color: var(--page-accent); }

/* ============ mobility + motion ============ */
@media (max-width: 768px) {
    .block-container { padding-top: 1.8rem !important; padding-left: 0.9rem !important; padding-right: 0.9rem !important; }
    .main-title { font-size: 1.45rem; padding-top: 0.5rem; }
    .sub-title { font-size: 0.75rem; }
    .t-title { font-size: 1.42rem; letter-spacing: -0.01em; }
    .t-kicker { font-size: 0.6rem; }
    .t-sub { font-size: 0.82rem; }
    .t-meta-row { margin-top: 12px; }
    div[data-testid="stMetricValue"] { font-size: 1.15rem !important; }
    .t-kpi-value { font-size: 1.08rem; }
    .t-kpi { padding: 11px 12px 10px 12px; }
    .t-hero-value { font-size: 2.2rem; }
    .t-hero-side { margin-top: 4px; }
    .t-section-title { letter-spacing: 0.09em; }
    .t-sheet { grid-template-columns: 1fr; }
    .t-kpi-grid-4, .t-kpi-grid-5 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .block-container { max-width: 100%; }
}
@media (max-width: 620px) {
    .ladder-meta-row { text-align: left; }
}
@media (max-width: 480px) {
    .t-kpi-grid-4, .t-kpi-grid-5 { grid-template-columns: 1fr; }
    .st-key-nb_mobile_bar { padding-bottom: calc(6px + env(safe-area-inset-bottom)); }
    .st-key-nb_mobile_bar .nb-bar-item, .st-key-nb_mobile_bar [data-testid="stPageLink-NavLink"] { padding: 7px 0 6px !important; }
    .t-hero-value { font-size: 2rem; letter-spacing: -0.02em; }
}
@media (prefers-reduced-motion: reduce) {
    .ticker-move { animation: none; }
    * { scroll-behavior: auto !important; }
}
"""


def inject_css():
    st.markdown(f"<style>{DESIGN_SYSTEM_CSS}</style>", unsafe_allow_html=True)