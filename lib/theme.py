# -------------------------------------------------
# Design system — single shared dark institutional theme.
# R-1701 (SPEC §17): every page injects this one stylesheet via inject_css().
# No page carries its own <style> block anymore. Component HTML is emitted by
# lib/ui/components.py as declarative strings; the classes they reference live
# here (t-* prefix). Legacy classes (pulse-*, attn-*, mfh-*, section-header,
# etc.) are consolidated here too so existing page markup keeps working
# without duplicated CSS.
#
# Northline Family Desk — private-bank briefing palette.
# Backgrounds: near-black; surfaces: layered slate; text: silver-white.
# Accent is silver (never blue). Status tones are restrained and semantic.
# Numerals set in Newsreader (tabular) for the executive look.
#
# Accessibility: high-contrast text tokens, status expressed via label text +
# glyph (never color alone), visible focus rings, reduced-motion respect.
# -------------------------------------------------
import streamlit as st

# Sleeve colours for the five-sleeve allocation strip (SPEC §3 composition).
SLEEVE_ORDER = ("Equity", "Liquid MF", "INR FD", "FCNR", "Gold")
SLEEVE_COLORS = {
    "Equity": "#8fa4c4",
    "Liquid MF": "#4aa88a",
    "INR FD": "#6b8cce",
    "FCNR": "#5b9eaa",
    "Gold": "#b8a07a",
}

# Default Plotly theming so every figure on every page shares the surface
# language (paper/plot backgrounds, grid, font, and accent).
PLOTLY_LAYOUT = {
    "paper_bgcolor": "#101218",
    "plot_bgcolor": "#101218",
    "font": {"color": "#8b93a4", "family": "IBM Plex Sans, Segoe UI, sans-serif", "size": 12},
    "xaxis": {"gridcolor": "#222632", "linecolor": "#2e3444", "zerolinecolor": "#2e3444"},
    "yaxis": {"gridcolor": "#222632", "linecolor": "#2e3444", "zerolinecolor": "#2e3444"},
    "colorway": ["#8fa4c4", "#4aa88a", "#6b8cce", "#5b9eaa", "#b8a07a", "#8b93a4"],
    "margin": {"l": 8, "r": 8, "t": 8, "b": 8},
    "showlegend": False,
}

DESIGN_SYSTEM_CSS = r"""
/* ============ type ============ */
@import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600;6..72,700;6..72,800&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

/* ============ design tokens ============ */
:root {
  --c-bg: #08090c; --c-bg-card: #101218; --c-bg-surface: #101218;
  --c-bg-deep: #0c0d12; --c-bg-raised: #161922;
  --c-border: #222632; --c-border-hover: #2e3444; --c-border-subtle: #191c24;
  --c-border-strong: #2e3444;
  --c-text: #eceef2; --c-text-body: #eceef2; --c-text-secondary: #8b93a4;
  --c-text-muted: #8b93a4; --c-text-dim: #8b93a4; --c-text-faint: #5c6578;
  --c-text-ghost: #5c6578; --c-text-buried: #5c6578;
  --c-accent: #c5cedb; --c-accent-fg: #0b0c10; --c-accent-dim: #8fa0b8;
  --c-up: #3cba8c; --c-up-soft: #3cba8c; --c-down: #e15d5d; --c-down-soft: #e15d5d;
  --c-warn: #d4a054; --c-warn-soft: #d4a054; --c-info: #6b9ad4; --c-info-soft: #6b9ad4;
  --c-urgent: #c45c5c;
  --c-eq: #8fa4c4; --c-liq: #4aa88a; --c-inrfd: #6b8cce; --c-fcnr: #5b9eaa; --c-gold: #b8a07a;
  --f-serif: 'Newsreader', Georgia, 'Iowan Old Style', 'Times New Roman', serif;
  --f-sans: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --f-mono: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --rail-w: 220px; --bar-h: 72px;
  --r-sm: 8px; --r-md: 12px; --r-lg: 16px; --r-pill: 999px;
  --sp-xs: 4px; --sp-sm: 8px; --sp-md: 16px; --sp-lg: 32px;
}

/* ============ base ============ */
.stApp { background: var(--c-bg); color: var(--c-text-body); -webkit-font-smoothing: antialiased; }
html, body, [data-testid="stAppViewContainer"] { background: var(--c-bg); }

* { font-family: var(--f-sans); }

p, span, label, ul, ol, li, .stMarkdown, div[data-testid="stMarkdownContainer"] {
    color: var(--c-text-secondary) !important;
}
a { color: var(--c-info-soft); text-decoration: none; }
a:hover { color: var(--c-info); text-decoration: underline; }

/* Header / chrome collapse for the app shell */
header[data-testid="stHeader"] {
    background: transparent !important; height: 0 !important; min-height: 0 !important;
    border: none !important; padding: 0 !important; display: none !important;
}
div[data-testid="stDecoration"] { display: none !important; }
div[data-testid="stToolbar"] { display: none !important; }
#MainMenu { visibility: hidden; display: none !important; }
footer { visibility: hidden; display: none !important; }
.stDeployButton, .stAppDeployButton, [data-testid="stStatusWidget"] { display: none !important; }
[class^="viewerBadge_"], [class*="viewerBadge_"], div[class*="viewerBadge"] { display: none !important; }
[data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"],
button[kind="headerNoPadding"], [data-testid="stBaseButton-headerNoPadding"] { display: none !important; }

html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    overflow-x: hidden !important;
    max-width: 100vw;
    -webkit-text-size-adjust: 100%;
    text-size-adjust: 100%;
}
.stApp { background: var(--c-bg); color: var(--c-text-body); -webkit-font-smoothing: antialiased; }
/* The product rail now lives IN the real Streamlit sidebar (lib/ui/nav.py):
   Streamlit's own navigation widget is disabled, and the sidebar is styled to
   the brand rail. It must stay expanded — the collapse chevron is hidden. */
section[data-testid="stSidebarNavigation"] { display: none !important; }
[data-testid="stSidebar"] {
    width: var(--rail-w) !important; background: var(--c-bg-deep);
    border-right: 1px solid var(--c-border);
}
[data-testid="stSidebarContent"] {
    padding: 26px 14px 18px 16px !important; overflow-y: auto;
    scrollbar-width: thin; scrollbar-color: var(--c-border-strong) transparent;
}
[data-testid="stSidebarResizeHandle"] { display: none !important; }
[data-testid="stSidebarCollapseButton"] { display: none !important; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 2px !important; }

/* ============ layout: fixed-width editorial column ============ */
[data-testid="stMainBlockContainer"], .block-container {
    max-width: 1280px !important;
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
    .st-key-nb_topbar { display: none !important; }
}
@media (max-width: 991px) {
    [data-testid="stMainBlockContainer"], .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        padding-top: 0.85rem !important;
        padding-bottom: calc(var(--bar-h) + env(safe-area-inset-bottom, 0px) + 28px) !important;
    }
    .nb-topbar { display: flex; }
    .st-key-nb_topbar { display: flex !important; }
    section[data-testid="stSidebar"],
    [data-testid="stSidebar"],
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapsedControl"] { display: none !important; visibility: hidden !important; }
}

/* ============ typography scale ============ */
.t-kicker { font-size: 11px; font-weight: 600; letter-spacing: 0.16em; text-transform: uppercase; color: var(--c-text-faint); margin: 0 0 6px 0; }
.t-title { font-size: 1.85rem; font-weight: 500; color: var(--c-text); letter-spacing: -0.03em; line-height: 1.05; margin: 0; font-family: var(--f-serif); text-wrap: balance; }
.t-sub { font-size: 0.875rem; color: var(--c-text-muted); font-weight: 400; margin: 8px 0 0 0; line-height: 1.5; max-width: 40rem; }
.t-pagehead { margin: 0 0 1.5rem 0; }
.t-meta-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 14px 0 2px 0; }
.t-meta-pill {
    font-size: 0.62rem; font-weight: 700; letter-spacing: 0.05em; color: var(--c-text-faint);
    background: var(--c-bg-surface); border: 1px solid var(--c-border); border-radius: var(--r-pill);
    padding: 3px 9px; font-variant-numeric: tabular-nums;
}
.t-meta-pill b { color: var(--c-text-secondary); font-weight: 700; }
.t-section-desc { font-size: 0.78rem; color: var(--c-text-dim); margin: 7px 0 2px 0; line-height: 1.5; }

/* Section header: label — rule — meta, with guaranteed gaps (never concat).
   A leading index chip (legacy step numbers, e.g. 01) is .t-section-index. */
.t-section { margin: 2.1rem 0 0.8rem 0; }
.t-section-title {
    font-size: 0.72rem; font-weight: 700; color: var(--c-text-muted); text-transform: uppercase;
    letter-spacing: 0.12em; display: flex; align-items: center; gap: 12px; margin: 0;
}
.t-section-index {
    font-size: 0.66rem; font-weight: 700; letter-spacing: 0.02em; color: var(--c-accent);
    background: color-mix(in srgb, var(--c-accent) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--c-accent) 24%, transparent);
    border-radius: 5px; padding: 2px 7px; flex: none; white-space: nowrap;
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
div[data-testid="stMetricValue"] { font-size: 1.35rem !important; font-weight: 700 !important; color: var(--c-text) !important; font-variant-numeric: tabular-nums; font-family: var(--f-serif); }
div[data-testid="stMetricLabel"] { color: var(--c-text-faint) !important; font-size: 0.64rem !important; font-weight: 700 !important; text-transform: uppercase; letter-spacing: 0.1em; }
div[data-testid="stMetricDelta"] { font-size: 0.75rem !important; }
div[data-testid="stCaptionContainer"] p { font-size: 0.72rem; color: var(--c-text-ghost); line-height: 1.55; }

.stTabs [data-baseweb="tab-list"] { background-color: var(--c-bg-surface); gap: 3px; border-radius: 9px; padding: 3px; border: 1px solid var(--c-border); width: fit-content; max-width: 100%; overflow-x: auto; }
.stTabs [data-baseweb="tab"] { color: var(--c-text-faint) !important; border-radius: 6px; padding: 8px 18px; font-weight: 500; }
.stTabs [aria-selected="true"] { background: var(--c-bg-raised) !important; color: var(--c-text) !important; font-weight: 600; }

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
div[data-testid="stNumberInput"] input { color: var(--c-text) !important; font-weight: 600; font-variant-numeric: tabular-nums; }
.stButton > button, .stDownloadButton > button {
    background: var(--c-bg-raised) !important; border: 1px solid var(--c-border-hover) !important; color: var(--c-text-secondary) !important;
    border-radius: 8px; font-weight: 600; font-size: 0.8rem; padding: 0.5rem 1rem;
}
.stButton > button[kind="primary"] { background: var(--c-accent) !important; border-color: var(--c-accent) !important; color: var(--c-accent-fg) !important; }
.stButton > button:hover, .stDownloadButton > button:hover { border-color: var(--c-accent) !important; }
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible,
input:focus-visible, [data-testid="stSelectbox"]:focus-within { outline: 2px solid var(--c-info) !important; outline-offset: 1px; }

.stProgress > div > div > div { background: var(--c-accent); }

/* checkbox / multiselect / radio restyle for the terminal look */
[data-testid="stCheckbox"] span { font-size: 0.8rem; color: var(--c-text-secondary); }
[data-testid="stRadio"] label > div:first-child { background: var(--c-accent); }
.stMultiSelect [data-baseweb="tag"], [data-baseweb="tag"] {
    background: var(--c-bg-surface) !important; border: 1px solid var(--c-border-hover) !important;
}
[data-testid="stMultiSelect"] [data-baseweb="tag"] span { color: var(--c-text-secondary) !important; }
.stSlider [data-baseweb="slider"] div[role="slider"] { background: var(--c-accent); border-color: var(--c-accent); }

/* ============ product shell ============
   Desktop rail lives in the real Streamlit sidebar (styled above); the mobile
   bottom bar is a real element container pinned by its st-key-nb_mobile_bar
   class; the phone top bar is st-key-nb_topbar. Nav items are st.page_link
   elements routed inside the same websocket session (state-preserving) —
   except the current page, which renders as a static .nb-active badge. */
.nb-brand { padding: 0 4px 8px 4px; }
.nb-brand-kicker { font-size: 11px; font-weight: 600; letter-spacing: 0.18em; text-transform: uppercase; color: var(--c-text-faint); }
.nb-brand-name { font-family: var(--f-serif); font-size: 1.25rem; font-weight: 500; letter-spacing: -0.03em; color: var(--c-text); line-height: 1.15; margin-top: 2px; }
.nb-brand-sub { font-size: 0.62rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--c-text-faint); margin-top: 3px; }
/* Group captions are DOM members (tests pin the string) but visually silent. */
.nb-group-label { display: none; }

[data-testid="stSidebar"] .nb-divider {
    height: 1px; background: var(--c-border-strong); margin: 18px 6px 10px 6px; border: none;
}

/* nav-link look shared by st.page_link anchors and the static active badge */
.nb-link, [data-testid="stPageLink-NavLink"] {
    display: flex !important; align-items: center; gap: 12px; margin: 1px 0 !important;
    padding: 0 12px !important; height: 44px; border-radius: 12px; font-size: 0.875rem; font-weight: 500;
    color: var(--c-text-muted); border-left: none; width: 100%;
}
[data-testid="stPageLink-NavLink"]:hover, [data-testid="stPageLink-NavLink"]:focus-visible,
.nb-link:hover { background: var(--c-bg-surface); color: var(--c-text); }
.nb-link.nb-active, .nb-bar-item.nb-active {
    background: var(--c-bg-raised); color: var(--c-text); font-weight: 500;
    border-left: none;
}
.nb-glyph { width: 14px; text-align: center; color: var(--c-text-faint); font-size: 0.74rem; flex: none; }
.nb-active .nb-glyph { color: var(--c-accent); }
[data-testid="stPageLink"] { margin: 0 !important; padding: 0 !important; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] { margin: 0; }
.nb-rail-foot {
    font-size: 11px; line-height: 1.55; color: var(--c-text-faint);
    padding: 18px 10px 2px 10px; border-top: 1px solid var(--c-border); margin-top: 14px;
}
/* mobile top brand (only ≤991px; hidden elsewhere) */
.nb-topbar { display: none; align-items: baseline; gap: 10px; }
.st-key-nb_topbar { display: none; align-items: center; justify-content: space-between; margin: 2px 0 12px 0; padding: 0 0 10px 0; }
.st-key-nb_topbar .nb-topbar {
    display: flex; flex-direction: column; align-items: flex-start; gap: 0; flex: 1; min-width: 0;
}
.nb-top-kicker { font-size: 10px; font-weight: 600; letter-spacing: 0.16em; text-transform: uppercase; color: var(--c-text-faint); display: block; }
.nb-top-name { font-family: var(--f-serif); font-size: 1.15rem; font-weight: 500; letter-spacing: -0.03em; color: var(--c-text); display: block; line-height: 1.1; }
.nb-top-sub { font-size: 0.6rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--c-text-faint); }
.st-key-nb_topbar .st-key-nb_pulse_link { margin-left: auto; }
.st-key-nb_topbar [data-testid="stPageLink-NavLink"] {
    background: var(--c-bg-surface) !important; border: 1px solid var(--c-border) !important; color: var(--c-text-muted) !important;
    font-size: 11px !important; font-weight: 500 !important; letter-spacing: 0.04em;
    display: inline-flex !important; align-items: center; justify-content: center; gap: 0;
    height: 40px !important; padding: 0 12px !important; border-radius: 12px !important; width: auto !important;
}

/* iPhone topbar: brand | Pulse as a single row, never stacked columns */
@media (max-width: 991px) {
    .st-key-nb_topbar {
        display: flex !important;
        width: 100%;
    }
    .st-key-nb_topbar [data-testid="stVerticalBlock"] {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: center !important;
        justify-content: space-between !important;
        gap: 8px !important;
        width: 100% !important;
    }
    .st-key-nb_topbar [data-testid="stVerticalBlock"] > div:first-child { flex: 1 1 auto; min-width: 0; }
    .st-key-nb_topbar [data-testid="stVerticalBlock"] > div:last-child { flex: 0 0 auto; }
}

/* mobile bottom bar: sibling page_links, flex-row nowrap. NEVER rely on
   st.columns — Streamlit stacks those below ~640px on iPhone Chrome. */
.st-key-nb_mobile_bar { display: none !important; }
@media (max-width: 991px) {
    section[data-testid="stSidebar"], [data-testid="stSidebar"] { display: none !important; }
    .st-key-nb_mobile_bar {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: stretch !important;
        justify-content: space-between !important;
        position: fixed !important;
        left: 0 !important; right: 0 !important; bottom: 0 !important;
        z-index: 9999 !important;
        width: 100% !important;
        max-width: 100vw !important;
        min-height: var(--bar-h);
        margin: 0 !important;
        padding: 4px 2px calc(8px + env(safe-area-inset-bottom, 0px)) !important;
        background: color-mix(in srgb, var(--c-bg-raised) 92%, transparent);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border-top: 1px solid var(--c-border-strong);
        box-sizing: border-box;
    }
    .st-key-nb_mobile_bar [data-testid="stVerticalBlock"] {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: stretch !important;
        justify-content: space-between !important;
        gap: 0 !important;
        width: 100% !important;
        flex: 1 1 auto !important;
    }
    .st-key-nb_mobile_bar [data-testid="stHorizontalBlock"] {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        gap: 0 !important;
        width: 100% !important;
    }
    .st-key-nb_mobile_bar > div,
    .st-key-nb_mobile_bar [data-testid="stVerticalBlock"] > div,
    .st-key-nb_mobile_bar [data-testid="stElementContainer"],
    .st-key-nb_mobile_bar [data-testid="column"],
    .st-key-nb_mobile_bar [data-testid="stColumn"] {
        flex: 1 1 0 !important;
        min-width: 0 !important;
        width: auto !important;
        max-width: none !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    .st-key-nb_mobile_bar [data-testid="stPageLink"],
    .st-key-nb_mobile_bar [data-testid="stMarkdown"] {
        width: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    .nb-bar-item {
        flex: 1 1 0; min-width: 0; min-height: 52px;
        display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px;
        padding: 8px 1px 6px; color: var(--c-text-faint) !important;
        font-size: 10px; letter-spacing: 0.02em; font-weight: 600;
        position: relative;
    }
    .nb-bar-item .nb-glyph { font-size: 1.05rem; color: var(--c-text-dim) !important; }
    .nb-bar-item .nb-item { color: inherit !important; font-size: 10px; }
    .nb-bar-item.nb-active { color: var(--c-text) !important; background: transparent; }
    .nb-bar-item.nb-active .nb-glyph { color: var(--c-warn) !important; }
    .nb-bar-item.nb-active::before {
        content: ""; position: absolute; top: 0; left: 50%; transform: translateX(-50%);
        width: 22px; height: 2px; border-radius: var(--r-pill); background: var(--c-warn);
    }
    .st-key-nb_mobile_bar [data-testid="stPageLink-NavLink"] {
        flex-direction: column !important; justify-content: center; align-items: center; gap: 3px !important;
        margin: 0 !important; padding: 8px 2px 6px !important;
        border-left: none !important; border-radius: 0 !important;
        background: transparent !important; color: var(--c-text-faint) !important;
        font-size: 10px !important; letter-spacing: 0.02em !important; font-weight: 600 !important;
        position: relative; height: 52px !important; min-height: 52px !important;
        width: 100% !important; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        -webkit-tap-highlight-color: transparent;
    }
    .st-key-nb_mobile_bar [data-testid="stPageLink-NavLink"]:hover { background: transparent !important; }
}

/* drill row hidden from the first screen — nav already reaches every page */
.st-key-nb_drill_links { display: none !important; }


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
.t-kpi-label { font-size: 0.62rem; font-weight: 700; color: var(--c-text-faint); text-transform: uppercase; letter-spacing: 0.1em; }
.t-kpi-value { font-size: 1.2rem; font-weight: 700; color: var(--c-text); margin-top: 6px; font-variant-numeric: tabular-nums; line-height: 1.1; word-break: break-word; font-family: var(--f-serif); }
.t-kpi-sub { font-size: 0.68rem; color: var(--c-text-dim); margin-top: 5px; font-weight: 500; line-height: 1.4; }
.t-kpi-tone-up .t-kpi-value { color: var(--c-text); }
.t-kpi-tone-down .t-kpi-value { color: var(--c-text); }
.t-kpi-tone-warn .t-kpi-value { color: var(--c-text); }
.t-kpi-tone-accent .t-kpi-value { color: var(--c-text); }
.t-kpi-tone-up .t-kpi-sub { color: var(--c-up); }
.t-kpi-tone-down .t-kpi-sub { color: var(--c-down); }
.t-kpi-tone-warn .t-kpi-sub { color: var(--c-warn); }
.t-kpi-foot { font-size: 0.62rem; color: var(--c-text-ghost); margin-top: 6px; font-weight: 600; letter-spacing: 0.02em; }

.t-pill {
    display: inline-flex; align-items: center; gap: 6px; font-size: 0.7rem; font-weight: 700;
    color: var(--c-text-muted); background: var(--c-bg-surface); border: 1px solid var(--c-border); border-radius: var(--r-pill); padding: 4px 11px;
}
.t-pill .t-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--c-text-ghost); flex: none; }
.t-pill-ok   .t-dot { background: var(--c-up); } .t-pill-ok { color: var(--c-up-soft); border-color: color-mix(in srgb, var(--c-up) 40%, transparent); }
.t-pill-cache .t-dot { background: var(--c-warn); } .t-pill-cache { color: var(--c-warn-soft); border-color: color-mix(in srgb, var(--c-warn) 40%, transparent); }
.t-pill-off  .t-dot { background: var(--c-down); } .t-pill-off { color: var(--c-down-soft); border-color: color-mix(in srgb, var(--c-down) 40%, transparent); }
.t-pill-info .t-dot { background: var(--c-info); } .t-pill-info { color: var(--c-info-soft); border-color: color-mix(in srgb, var(--c-info) 40%, transparent); }

.t-badge {
    display: inline-block; padding: 2px 9px; border-radius: var(--r-pill); font-size: 0.64rem;
    font-weight: 800; letter-spacing: 0.04em; background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); color: var(--c-text-muted); border: 1px solid transparent;
}
.t-badge-pos  { background: color-mix(in srgb, var(--c-up) 16%, transparent);  color: var(--c-up-soft); }
.t-badge-neg  { background: color-mix(in srgb, var(--c-down) 16%, transparent);  color: var(--c-down-soft); }
.t-badge-warn { background: color-mix(in srgb, var(--c-warn) 16%, transparent); color: var(--c-warn-soft); }
.t-badge-info { background: color-mix(in srgb, var(--c-info) 16%, transparent); color: var(--c-info-soft); }
.t-badge-live { background: color-mix(in srgb, var(--c-up) 20%, transparent);  color: var(--c-up-soft); border-color: color-mix(in srgb, var(--c-up) 32%, transparent); }
.t-badge-stale{ background: color-mix(in srgb, var(--c-warn) 20%, transparent); color: var(--c-warn-soft); border-color: color-mix(in srgb, var(--c-warn) 32%, transparent); }

/* Fact-kind chips: the provenance taxonomy from lib.intelligence.model */
.t-chip { display: inline-block; padding: 2px 8px; border-radius: 5px; font-size: 0.6rem; font-weight: 800; letter-spacing: 0.07em; }
.t-chip-fact  { background: color-mix(in srgb, var(--c-info) 18%, transparent);  color: var(--c-info-soft); }
.t-chip-calc  { background: color-mix(in srgb, var(--c-up) 16%, transparent);  color: var(--c-up-soft); }
.t-chip-signal{ background: color-mix(in srgb, var(--c-warn) 16%, transparent); color: var(--c-warn-soft); }
.t-chip-ai    { background: rgba(168,85,247,0.16); color: #d8b4fe; }
.t-chip-reco  { background: color-mix(in srgb, var(--c-down) 16%, transparent);  color: var(--c-down-soft); }

.t-source { font-size: 0.66rem; color: var(--c-text-ghost); font-weight: 600; letter-spacing: 0.03em; }
.t-caption { font-size: 0.72rem; color: var(--c-text-ghost); line-height: 1.55; display: inline-block; }
.t-caption-pos { color: var(--c-up-soft); }
.t-caption-neg { color: var(--c-down-soft); }
.t-caption-warn { color: var(--c-warn-soft); }
.t-footnote { font-size: 0.66rem; color: var(--c-text-buried); line-height: 1.5; }
.t-empty {
    border: 1px dashed var(--c-border-strong); border-radius: var(--r-md); padding: 16px 18px; color: var(--c-text-muted);
    font-size: 0.78rem; background: var(--c-bg-deep);
}
.t-empty b { color: var(--c-text-secondary); }
.t-empty-hint { margin-top: 8px; font-size: 0.72rem; color: var(--c-text-ghost); line-height: 1.55; }

.t-card { background: var(--c-bg-card);
    border: 1px solid var(--c-border); border-radius: var(--r-md); padding: 14px 16px;
    font-size: 0.8rem; color: var(--c-text-muted); line-height: 1.55; }
.t-card a { color: var(--c-info-soft); }
.t-card-summary { font-size: 0.9rem; color: var(--c-text-body); }
.t-card-title { display: block; font-size: 0.8rem; font-weight: 700; color: var(--c-text); margin-bottom: 6px; }
.t-list { margin: 0; padding-left: 18px; }
.t-list li { margin: 3px 0; }
.t-list-title { font-size: 0.66rem; font-weight: 700; color: var(--c-text-faint); text-transform: uppercase; letter-spacing: 0.1em; }
.t-list-row { display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
    font-size: 0.78rem; padding: 8px 0; border-bottom: 1px solid var(--c-border-subtle); }
.t-list-name { color: var(--c-text-body); font-weight: 600; }
.t-list-meta { color: var(--c-text-muted); font-variant-numeric: tabular-nums; }

.t-banner { border-radius: var(--r-md); padding: 11px 15px; margin: 10px 0 4px 0; border: 1px solid; font-size: 0.8rem; line-height: 1.45; }
.t-banner-critical { background: color-mix(in srgb, var(--c-urgent) 14%, transparent); border-color: color-mix(in srgb, var(--c-urgent) 45%, transparent); color: var(--c-down-soft); }
.t-banner-warn { background: color-mix(in srgb, var(--c-warn) 12%, transparent); border-color: color-mix(in srgb, var(--c-warn) 40%, transparent); color: var(--c-warn-soft); }
.t-banner-info { background: color-mix(in srgb, var(--c-info) 12%, transparent); border-color: color-mix(in srgb, var(--c-info) 40%, transparent); color: var(--c-info-soft); }
.t-banner-ok { background: color-mix(in srgb, var(--c-up) 12%, transparent); border-color: color-mix(in srgb, var(--c-up) 40%, transparent); color: var(--c-up-soft); }
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
.ladder-bar { height: 100%; background: var(--c-accent); border-radius: var(--r-pill); min-width: 1px; }
.ladder-val { font-size: 0.78rem; font-weight: 700; color: var(--c-text); font-variant-numeric: tabular-nums; text-align: right; }
.ladder-meta-row { text-align: right; font-size: 0.64rem; color: var(--c-text-ghost); padding: 2px 0 6px 0; }

/* attention tiles */
.t-attn-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 8px 0 8px 0; }
@media (max-width: 1100px) { .t-attn-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) { .t-attn-grid { grid-template-columns: 1fr; } }
.t-attn-tile { border-radius: var(--r-md); padding: 14px 14px 12px 14px; border: 1px solid var(--c-border); min-height: 0; background: var(--c-bg-surface); }
.t-attn-urgent { border-color: color-mix(in srgb, var(--c-urgent) 40%, var(--c-border)); }
.t-attn-warn { border-color: color-mix(in srgb, var(--c-warn) 35%, var(--c-border)); }
.t-attn-info { border-color: var(--c-border); }
.t-attn-tag { display: inline-block; font-size: 0.58rem; font-weight: 800; letter-spacing: 0.07em; padding: 2px 7px; border-radius: 4px; margin-bottom: 8px; }
.t-tag-urgent { background: color-mix(in srgb, var(--c-urgent) 22%, transparent); color: var(--c-down-soft); }
.t-tag-review { background: color-mix(in srgb, var(--c-warn) 20%, transparent); color: var(--c-warn-soft); }
.t-tag-upcoming { background: color-mix(in srgb, var(--c-info) 20%, transparent); color: var(--c-info-soft); }
.t-attn-title { font-size: 0.95rem; font-weight: 600; color: var(--c-text) !important; margin: 0 0 6px 0; line-height: 1.25; }
.t-attn-body { font-size: 0.78rem; color: var(--c-text-muted) !important; margin: 0; line-height: 1.45; }

/* ============ executive hero ============ */
.t-hero {
    display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 14px;
    background: var(--c-bg-deep);
    border: 1px solid var(--c-border); border-radius: 16px; padding: 24px 28px;
    margin: 14px 0 20px 0;
}
@media (max-width: 900px) { .t-hero { grid-template-columns: 1fr; } }
.t-hero-main { display: flex; flex-direction: column; justify-content: center; }
.t-hero-kicker { font-size: 0.62rem; font-weight: 700; letter-spacing: 0.24em; text-transform: uppercase; color: var(--c-accent); margin: 0 0 10px 0; }
.t-hero-value { font-size: 3.0rem; font-weight: 700; color: var(--c-text); letter-spacing: -0.03em; line-height: 1.02; font-variant-numeric: tabular-nums; word-break: break-word; font-family: var(--f-serif); }
.t-hero-tone-up .t-hero-value { color: var(--c-up); }
.t-hero-tone-down .t-hero-value { color: var(--c-down); }
.t-hero-tone-warn .t-hero-value { color: var(--c-warn); }
.t-hero-tone-accent .t-hero-value { color: var(--c-text); }
.t-hero-delta { margin-top: 10px; font-size: 0.8rem; font-weight: 600; color: var(--c-info-soft); }
.t-hero-sub { margin-top: 6px; font-size: 0.78rem; color: var(--c-text-muted); }
.t-hero-foot { margin-top: 18px; font-size: 0.7rem; color: var(--c-text-ghost); line-height: 1.5; }
.t-hero-side { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; align-items: stretch; }
@media (max-width: 560px) { .t-hero-side { grid-template-columns: 1fr; } }
.t-hero-side .t-kpi { min-height: 92px; }
.t-kpi-tall { min-height: 96px; }

/* ============ five-sleeve strip (allocation) ============ */
.t-strip { margin: 0; }
.t-strip-bar {
    display: flex; height: 44px; border-radius: 10px; overflow: hidden;
    background: var(--c-bg-deep); border: 1px solid var(--c-border);
}
.t-strip-seg {
    height: 100%; min-width: 0; display: flex; align-items: center; justify-content: center;
    overflow: hidden;
}
.t-strip-in {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    line-height: 1.15; text-align: center; padding: 0 4px; pointer-events: none;
}
.t-strip-in-name {
    font-size: 11px; font-weight: 700; color: #0c0d12 !important; letter-spacing: 0.01em;
    white-space: nowrap;
}
.t-strip-in-pct {
    font-size: 11px; font-weight: 600; color: rgba(12,13,18,0.78) !important;
    font-variant-numeric: tabular-nums; font-family: var(--f-mono);
}
.t-strip-legend { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px 16px; margin-top: 12px; }
.t-sleeve { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.t-sleeve-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; flex: none; }
.t-sleeve-name { color: var(--c-text-muted) !important; font-size: 11px; font-weight: 500; display: flex; align-items: center; gap: 6px; }
.t-sleeve-pct { color: var(--c-text) !important; font-weight: 500; font-size: 0.875rem; font-variant-numeric: tabular-nums; font-family: var(--f-mono); }
.t-sleeve-val { color: var(--c-text-faint) !important; font-size: 11px; font-variant-numeric: tabular-nums; font-family: var(--f-mono); }
@media (min-width: 900px) {
    /* Desktop: labels live in the bar; keep the legend as a compact value row. */
    .t-strip-legend { margin-top: 10px; }
}
@media (max-width: 899px) {
    .t-strip-bar { height: 10px; border-radius: var(--r-pill); }
    .t-strip-in { display: none; }
    .t-strip-legend {
        display: flex; flex-wrap: nowrap; overflow-x: auto; gap: 8px;
        grid-template-columns: none; -webkit-overflow-scrolling: touch;
        padding-bottom: 4px; margin-top: 14px; scrollbar-width: none;
    }
    .t-strip-legend::-webkit-scrollbar { display: none; }
    .t-sleeve {
        flex: 0 0 auto; flex-direction: row; align-items: center; gap: 8px;
        border: 1px solid var(--c-border); background: var(--c-bg-surface);
        border-radius: var(--r-pill); padding: 8px 12px;
    }
    .t-sleeve-pct { font-size: 12px; }
    .t-sleeve-val { display: none; }
}

/* ============ health ring ============ */
.t-ring-wrap { position: relative; width: 112px; height: 112px; flex: none; filter: drop-shadow(0 0 14px rgba(212,160,84,0.22)); }
.t-ring { transform: rotate(-90deg); }
.t-ring-track { fill: none; stroke: var(--c-border); stroke-width: 8; }
.t-ring-progress { fill: none; stroke: #d4a054; stroke-width: 8; stroke-linecap: round; }
.t-ring-ok .t-ring-progress { stroke: #d4a054; }
.t-ring-warn .t-ring-progress { stroke: #d4a054; }
.t-ring-urgent .t-ring-progress { stroke: var(--c-down); }
.t-ring-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.t-ring-score { font-family: var(--f-serif); font-size: 1.55rem; font-weight: 500; color: var(--c-text) !important; line-height: 1; font-variant-numeric: tabular-nums; }
.t-ring-label { font-size: 9px; letter-spacing: 0.08em; color: var(--c-text-faint) !important; font-weight: 600; margin-top: 3px; text-transform: uppercase; }
.t-ring-sub { font-size: 9px; letter-spacing: 0.08em; color: var(--c-text-faint) !important; text-transform: uppercase; }

/* ============ stance pill ============ */
.t-stance { display: inline-flex; align-items: center; gap: 8px; font-size: 0.8rem; color: var(--c-text-muted); background: var(--c-bg-surface); border: 1px solid var(--c-border); border-radius: var(--r-pill); padding: 8px 16px; font-weight: 500; line-height: 1.4; }
.t-stance b { color: var(--c-text); font-weight: 600; }
.t-stance-ok   { border-color: color-mix(in srgb, var(--c-up) 45%, transparent); }
.t-stance-warn { border-color: color-mix(in srgb, var(--c-warn) 45%, transparent); }
.t-stance-crit { border-color: color-mix(in srgb, var(--c-urgent) 45%, transparent); }

/* ============ dots (mini step indicator) ============ */
.t-dots { display: inline-flex; gap: 5px; align-items: center; }
.t-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--c-border-strong); }
.t-dot-on { background: var(--c-accent); }

/* watchlist (restrained attention) */
.t-watch-list { display: flex; flex-direction: column; gap: 8px; margin: 8px 0 8px 0; }
.t-watch {
    display: flex; gap: 12px; background: var(--c-bg-surface); border: 1px solid var(--c-border);
    border-radius: var(--r-md); padding: 12px 15px; align-items: flex-start;
}
.t-watch:hover { border-color: var(--c-border-hover); }
.t-watch-bar { flex: none; width: 4px; align-self: stretch; border-radius: var(--r-pill); }
.t-watch-urgent .t-watch-bar { background: var(--c-urgent); }
.t-watch-warn   .t-watch-bar { background: var(--c-warn); }
.t-watch-info   .t-watch-bar { background: var(--c-info); }
.t-watch-main { flex: 1; min-width: 0; }
.t-watch-tag { display: inline-block; font-size: 0.58rem; font-weight: 800; letter-spacing: 0.07em; padding: 1px 7px; border-radius: 4px; margin-bottom: 5px; }
.t-watch-urgent .t-watch-tag { background: color-mix(in srgb, var(--c-urgent) 18%, transparent); color: var(--c-down-soft); }
.t-watch-warn   .t-watch-tag { background: color-mix(in srgb, var(--c-warn) 18%, transparent); color: var(--c-warn-soft); }
.t-watch-info   .t-watch-tag { background: color-mix(in srgb, var(--c-info) 18%, transparent); color: var(--c-info-soft); }
.t-watch-title { font-size: 0.84rem; font-weight: 700; color: var(--c-text); margin: 0 0 3px 0; line-height: 1.3; }
.t-watch-title a { color: var(--c-text); }
.t-watch-title a:hover { color: var(--c-info-soft); }
.t-watch-body { font-size: 0.74rem; color: var(--c-text-muted); margin: 0; line-height: 1.45; }
.t-watch-why { margin-top: 6px; font-size: 0.7rem; color: var(--c-text-dim); line-height: 1.45; }
.t-watch-why b { color: var(--c-info-soft); font-weight: 600; }

/* ============ research rows ============ */
.t-research-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 10px 0 4px 0; }
@media (max-width: 1100px) { .t-research-grid { grid-template-columns: 1fr; } }
.t-research {
    background: var(--c-bg-surface); border: 1px solid var(--c-border); border-radius: var(--r-md); padding: 12px 15px;
    min-height: 92px; display: flex; flex-direction: column; justify-content: flex-start;
}
.t-research:hover { border-color: var(--c-border-hover); }
.t-research-top { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.t-research-tag { font-size: 0.58rem; font-weight: 800; letter-spacing: 0.06em; padding: 1px 7px; border-radius: 4px; background: color-mix(in srgb, var(--c-info) 16%, transparent); color: var(--c-info-soft); }
.t-research-meta { margin-left: auto; font-size: 0.64rem; color: var(--c-text-ghost); font-weight: 500; white-space: nowrap; }
.t-research-title { font-size: 0.84rem; font-weight: 600; color: var(--c-text); line-height: 1.35; margin: 0; }
.t-research-title a { color: var(--c-text); }
.t-research-title a:hover { color: var(--c-info-soft); }
.t-research-body { margin-top: 6px; font-size: 0.73rem; color: var(--c-text-muted); line-height: 1.5; }

/* ============ unavailable (single deliberate empty state) ============ */
.t-unavailable {
    background: var(--c-bg-deep); border: 1px dashed var(--c-border-strong); border-radius: var(--r-md);
    padding: 24px 28px; text-align: center; margin: 8px 0;
}
.t-unavail-mark { font-size: 1.3rem; font-weight: 300; color: var(--c-text-ghost); letter-spacing: 0.1em; }
.t-unavail-title { font-size: 0.85rem; font-weight: 600; color: var(--c-text-muted); margin-top: 4px; }
.t-unavail-detail { font-size: 0.73rem; color: var(--c-text-ghost); margin-top: 3px; }

/* ============ evidence trail ============ */
.t-evidence { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.t-evidence-bit {
    font-size: 0.62rem; color: var(--c-text-dim); background: var(--c-bg-surface); border: 1px solid var(--c-border);
    border-radius: 5px; padding: 1px 7px; font-weight: 500;
}

/* ============ legacy classes (consolidated from pages) ============ */
.main-title { font-size: 1.7rem; font-weight: 700; color: var(--c-text); letter-spacing: -0.012em; margin: 0 0 0.05rem 0; padding-top: 0.35rem; position: relative; z-index: 2; font-family: var(--f-serif); }
.sub-title { color: var(--c-text-faint); font-size: 0.82rem; margin-bottom: 0.8rem; font-weight: 400; }
.section-header {
    font-size: 0.72rem; font-weight: 700; color: var(--c-text-muted); margin: 1.45rem 0 0.6rem 0;
    text-transform: uppercase; letter-spacing: 0.12em; display: flex; align-items: center; gap: 8px;
}
.section-header::after { content: ""; flex: 1; height: 1px; background: var(--c-border-strong); }
.caveat { font-size: 0.72rem; color: var(--c-text-ghost); font-style: italic; }
.recon-pass { color: var(--c-up); font-weight: 600; }
.recon-fail { color: var(--c-down); font-weight: 600; }
.snap-note { font-size: 0.72rem; color: var(--c-text-faint); margin-top: 4px; }

.status-row { display: flex; flex-wrap: wrap; gap: 10px; margin: 6px 0 4px 0; }
.status-pill { font-size: 0.7rem; color: var(--c-text-muted); background: var(--c-bg-surface); border: 1px solid var(--c-border); border-radius: var(--r-pill); padding: 4px 10px; font-weight: 600; }
.status-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; }
.dot-live { background: var(--c-up); }
.dot-cache { background: var(--c-warn); }
.dot-off { background: var(--c-down); }

.flag-card { border-radius: 8px; padding: 7px 10px; margin-bottom: 0; display: flex; gap: 8px; align-items: flex-start; border: 1px solid; }
.flag-critical { background: color-mix(in srgb, var(--c-urgent) 9%, transparent); border-color: color-mix(in srgb, var(--c-urgent) 30%, transparent); }
.flag-warning  { background: color-mix(in srgb, var(--c-warn) 9%, transparent); border-color: color-mix(in srgb, var(--c-warn) 30%, transparent); }
.flag-info     { background: color-mix(in srgb, var(--c-info) 9%, transparent); border-color: color-mix(in srgb, var(--c-info) 30%, transparent); }
.flag-title { font-weight: 600; font-size: 0.78rem; color: var(--c-text); margin: 0; line-height: 1.25; }
.flag-body  { font-size: 0.7rem; color: var(--c-text-muted); margin: 1px 0 0 0; line-height: 1.3; }
.flag-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 4px; }
@media (max-width: 900px) { .flag-grid { grid-template-columns: 1fr; } }

.attn-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 6px 0 8px 0; }
@media (max-width: 1100px) { .attn-grid { grid-template-columns: repeat(2, 1fr); } }
.attn-tile { border-radius: 10px; padding: 10px 12px; border: 1px solid; min-height: 88px; }
.attn-tag { display: inline-block; font-size: 0.6rem; font-weight: 800; letter-spacing: 0.06em; padding: 2px 7px; border-radius: 4px; margin-bottom: 6px; }
.tag-urgent { background: color-mix(in srgb, var(--c-urgent) 22%, transparent); color: var(--c-down-soft); }
.tag-review { background: color-mix(in srgb, var(--c-warn) 20%, transparent); color: var(--c-warn-soft); }
.tag-upcoming { background: color-mix(in srgb, var(--c-info) 20%, transparent); color: var(--c-info-soft); }
.attn-title { font-size: 0.82rem; font-weight: 700; color: var(--c-text); margin: 0 0 3px 0; line-height: 1.25; }
.attn-body { font-size: 0.7rem; color: var(--c-text-muted); margin: 0; line-height: 1.3; }

.crit-banner { background: color-mix(in srgb, var(--c-urgent) 14%, transparent); border: 1px solid color-mix(in srgb, var(--c-urgent) 40%, transparent); color: var(--c-down-soft); border-radius: 10px; padding: 10px 14px; margin: 8px 0 4px 0; font-size: 0.82rem; }
.crit-banner b { color: var(--c-down-soft); }

.pulse-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 8px 0 4px 0; }
@media (max-width: 1100px) { .pulse-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 360px) { .pulse-grid { grid-template-columns: 1fr; } }
.pulse-card { background: var(--c-bg-card); border: 1px solid var(--c-border); border-radius: var(--r-md); padding: 12px 14px; min-height: 78px; overflow: hidden; }
.pulse-card:hover { border-color: var(--c-border-hover); }
.pulse-label { font-size: 0.65rem; font-weight: 700; color: var(--c-text-faint); text-transform: uppercase; letter-spacing: 0.08em; }
.pulse-val { font-size: 1.05rem; font-weight: 700; color: var(--c-text); margin-top: 2px; font-variant-numeric: tabular-nums; }
.pulse-chg-up { color: var(--c-up); font-size: 0.78rem; font-weight: 700; }
.pulse-chg-dn { color: var(--c-down); font-size: 0.78rem; font-weight: 700; }
.pulse-chg-na { color: var(--c-text-ghost); font-size: 0.78rem; }

.ticker-wrap { width: 100%; overflow: hidden; background: var(--c-bg-raised); border: 1px solid var(--c-border); border-radius: var(--r-md); padding: 10px 0; white-space: nowrap; margin: 8px 0 4px 0; }
.ticker-move { display: inline-block; animation: ticker-scroll 50s linear infinite; }
.ticker-wrap:hover .ticker-move { animation-play-state: paused; }
@keyframes ticker-scroll { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
.ticker-item { display: inline-flex; align-items: baseline; gap: 6px; padding: 0 26px; font-size: 0.82rem; font-weight: 600; color: var(--c-text-body); }
.ticker-name { color: var(--c-text-muted); font-weight: 600; letter-spacing: 0.02em; }
.ticker-val { color: var(--c-text); font-variant-numeric: tabular-nums; }
.ticker-chg { font-weight: 700; font-variant-numeric: tabular-nums; }
.ticker-up .ticker-chg, .ticker-up .ticker-arrow { color: var(--c-up); }
.ticker-down .ticker-chg, .ticker-down .ticker-arrow { color: var(--c-down); }
.ticker-arrow { font-size: 0.95rem; font-weight: 800; }
.ticker-na { color: var(--c-text-ghost); }

.why-box { background: var(--c-bg-surface); border: 1px solid var(--c-border); border-radius: var(--r-md); padding: 10px 14px; margin-top: 8px; }
.why-box li { color: var(--c-text-muted); font-size: 0.78rem; margin: 3px 0; }

.alloc-legend { list-style: none; margin: 8px 0 0 0; padding: 0; }
.alloc-legend li { display: flex; justify-content: space-between; gap: 12px; font-size: 0.78rem; color: var(--c-text-muted); padding: 4px 0; border-bottom: 1px solid var(--c-border-subtle); }
.alloc-legend .nm { color: var(--c-text-body); font-weight: 600; }
.alloc-legend .amt { font-variant-numeric: tabular-nums; color: var(--c-text-secondary); }

.news-item { padding: 8px 0; border-bottom: 1px solid var(--c-border); }
.news-item a { color: var(--c-text) !important; text-decoration: none; font-size: 0.84rem; font-weight: 500; }
.news-item a:hover { color: var(--c-info-soft) !important; }
.news-meta { font-size: 0.71rem; color: var(--c-text-ghost); margin-top: 1px; }

/* ============ MF Health consolidated classes ============ */
.mfh-card { background: var(--c-bg-card); border: 1px solid var(--c-border); border-radius: 14px; padding: 16px 18px; }
.mfh-kpi-label { font-size: 0.68rem; font-weight: 700; color: var(--c-text-faint); text-transform: uppercase; letter-spacing: 0.08em; }
.mfh-kpi-val { font-size: 1.55rem; font-weight: 700; color: var(--c-text); margin: 4px 0 2px 0; font-variant-numeric: tabular-nums; font-family: var(--f-serif); }
.mfh-kpi-sub { font-size: 0.72rem; color: var(--c-text-faint); }
.mfh-badge { display: inline-block; padding: 2px 9px; border-radius: var(--r-pill); font-size: 0.68rem; font-weight: 700; }
.badge-low    { background: color-mix(in srgb, var(--c-up) 16%, transparent);  color: var(--c-up-soft); }
.badge-mod    { background: color-mix(in srgb, var(--c-warn) 16%, transparent); color: var(--c-warn-soft); }
.badge-high   { background: color-mix(in srgb, var(--c-down) 16%, transparent);  color: var(--c-down-soft); }
.badge-vhigh  { background: color-mix(in srgb, var(--c-urgent) 24%, transparent);  color: var(--c-down-soft); }

.score-circle {
    display: inline-flex; align-items: center; justify-content: center;
    width: 38px; height: 38px; border-radius: 50%; font-weight: 800; font-size: 0.82rem;
    border: 3px solid;
}
.sc-excellent { border-color: var(--c-up); color: var(--c-up-soft); }
.sc-good      { border-color: var(--c-warn); color: var(--c-warn-soft); }
.sc-average   { border-color: var(--c-warn); color: var(--c-warn-soft); }
.sc-poor      { border-color: var(--c-down); color: var(--c-down-soft); }

.fund-row { border-bottom: 1px solid var(--c-border); padding: 10px 4px; }
.fund-name { color: var(--c-text) !important; font-weight: 600; font-size: 0.86rem; }
.fund-amc  { color: var(--c-text-faint) !important; font-size: 0.72rem; }
.cat-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--c-info); margin-right: 6px; }

/* horizontal rules — consistent with section-title hairline */
hr, [data-testid="stMarkdownHorizontalBlock"] { border: none !important; height: 1px !important; background: var(--c-border-strong) !important; margin: 1.8rem 0 !important; }

/* section wrapper — provides the intended vertical rhythm around .t-section-title */
.t-section { margin: 2.1rem 0 0.8rem 0; }

/* ============ data sheet — two-column labelled dossier rows ============ */
.t-sheet { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 26px; margin: 2px 0 6px 0; }
.t-sheet-cell { padding: 9px 0; border-bottom: 1px solid var(--c-border-subtle); min-width: 0; }
.t-sheet-label { font-size: 0.62rem; font-weight: 800; color: var(--c-text-faint); text-transform: uppercase; letter-spacing: 0.1em; }
.t-sheet-value { font-size: 0.84rem; font-weight: 600; color: var(--c-text); margin-top: 3px; font-variant-numeric: tabular-nums; word-break: break-word; }
.t-sheet-value.up   { color: var(--c-up); }
.t-sheet-value.down { color: var(--c-down); }
.t-sheet-value.dim  { color: var(--c-text-muted); font-weight: 500; }
.t-sheet-value.accent { color: var(--c-text); }

/* ============ briefing hero (Command) ============ */
.t-brief {
    background: var(--c-bg-surface);
    border: 1px solid var(--c-border);
    border-radius: var(--r-lg);
    padding: 20px;
    margin: 0 0 20px 0;
}
@media (min-width: 768px) { .t-brief { padding: 24px 28px; } }
.t-brief-top {
    display: grid;
    grid-template-columns: minmax(160px, 1.1fr) auto minmax(0, 1.5fr);
    align-items: center;
    gap: 20px 28px;
}
.t-brief-kicker { font-size: 11px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: var(--c-text-faint) !important; }
.t-brief-value { font-family: var(--f-serif); font-size: 3.25rem; font-weight: 500; color: var(--c-text) !important; letter-spacing: -0.03em; line-height: 0.95; font-variant-numeric: tabular-nums; margin-top: 8px; }
@media (min-width: 768px) { .t-brief-value { font-size: 4rem; } }
.t-brief-meta { margin-top: 12px; font-size: 0.875rem; color: var(--c-text-muted) !important; display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
.t-brief-sep { color: var(--c-border-strong) !important; }
.t-signed-up { color: var(--c-up) !important; font-variant-numeric: tabular-nums; }
.t-signed-down { color: var(--c-down) !important; font-variant-numeric: tabular-nums; }
.t-stance-mini {
    display: inline-flex; align-items: center; margin-top: 12px;
    border: 1px solid var(--c-border); background: var(--c-bg-deep);
    border-radius: var(--r-pill); padding: 4px 12px;
    font-size: 11px; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: var(--c-text-muted) !important;
}
.t-brief-ring { display: flex; align-items: center; justify-content: center; }
.t-brief-kpis { min-width: 0; }
.t-brief-kpis .t-kpi-grid { margin: 0; }
.t-brief-kpis .t-kpi { min-height: 88px; padding: 12px 14px; }
.t-brief-kpis .t-kpi-value { color: #d4b07a !important; font-size: 1.15rem; }
.t-brief-alloc { margin-top: 22px; }
.t-brief-alloc-lbl {
    font-size: 11px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase;
    color: var(--c-text-faint) !important; margin: 0 0 10px 0;
}
.t-brief-strip { margin-top: 0; }
.t-brief-copy { max-width: 40rem; font-size: 0.875rem; line-height: 1.5; color: var(--c-text-muted) !important; margin: 4px 0 20px 0; }

@media (max-width: 1099px) {
    .t-brief-top { grid-template-columns: minmax(0, 1fr) auto; }
    .t-brief-kpis { grid-column: 1 / -1; }
}
@media (max-width: 767px) {
    .t-pagehead { text-align: center; }
    .t-kicker { text-align: center; }
    .t-sub { margin-inline: auto; }
    .t-sdot-row { justify-content: center; }
    .t-brief {
        background: transparent; border: none; padding: 4px 0 8px; margin-bottom: 8px;
    }
    .t-brief-top {
        grid-template-columns: 1fr;
        justify-items: center;
        text-align: center;
        gap: 18px;
    }
    .t-brief-main { display: flex; flex-direction: column; align-items: center; }
    .t-brief-value { font-size: 3.35rem; }
    .t-brief-meta { justify-content: center; }
    .t-brief-kpis { display: block; width: 100%; }
    .t-brief-kpis .t-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .t-brief-copy { text-align: center; margin-inline: auto; }
    .t-brief-alloc { width: 100%; }
}

/* status dots (AMFI / Stocks / Gold / FX) */
.t-sdot-row { display: flex; flex-wrap: wrap; gap: 6px; }
.t-sdot { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--c-border); background: var(--c-bg-surface); border-radius: var(--r-pill); padding: 4px 10px; font-size: 11px; color: var(--c-text-muted); }
.t-sdot-mark { width: 6px; height: 6px; border-radius: 50%; background: var(--c-down); flex: none; }
.t-sdot-on .t-sdot-mark { background: var(--c-up); }

/* cash due list */
.t-due-card { background: var(--c-bg-surface); border: 1px solid var(--c-border); border-radius: var(--r-md); padding: 16px; }
.t-due-sum { font-size: 0.875rem; color: var(--c-text-muted); margin: 0 0 8px 0; }
.t-due-list { list-style: none; margin: 0; padding: 0; }
.t-due-row { display: grid; grid-template-columns: 1fr auto; grid-template-rows: auto auto; column-gap: 12px; padding: 10px 0; border-top: 1px solid var(--c-border); }
.t-due-row:first-child { border-top: none; padding-top: 0; }
.t-due-name { font-size: 0.875rem; color: var(--c-text); }
.t-due-meta { grid-column: 1; font-size: 11px; color: var(--c-text-faint); }
.t-due-amt { grid-row: 1 / span 2; align-self: center; font-size: 0.875rem; font-variant-numeric: tabular-nums; font-family: var(--f-mono); color: var(--c-text); }

/* news strip */
.t-news-strip { list-style: none; margin: 0; padding: 0; border: 1px solid var(--c-border); border-radius: var(--r-md); background: var(--c-bg-surface); overflow: hidden; }
.t-news-row { border-top: 1px solid var(--c-border); }
.t-news-row:first-child { border-top: none; }
.t-news-row a, .t-news-plain { display: flex; gap: 12px; padding: 12px 16px; text-decoration: none; color: inherit; }
.t-news-row a:hover { background: var(--c-bg-raised); }
.t-news-dot { width: 8px; height: 8px; border-radius: 50%; flex: none; margin-top: 6px; background: var(--c-text-faint); }
.t-news-dot-up { background: var(--c-up); }
.t-news-dot-down { background: var(--c-down); }
.t-news-copy { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.t-news-title { font-size: 0.875rem; color: var(--c-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.t-news-meta { font-size: 11px; color: var(--c-text-faint); }

/* processed news sentiment chips (Command — original grouping) */
.t-sent-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin: 8px 0 4px 0; }
@media (max-width: 900px) { .t-sent-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 480px) { .t-sent-grid { grid-template-columns: 1fr; } }
.t-sent-chip { display: flex; align-items: baseline; gap: 8px; min-width: 0;
    background: var(--c-bg-surface); border: 1px solid var(--c-border);
    border-radius: var(--r-md); padding: 10px 12px; }
.t-sent-name { font-weight: 600; font-size: 0.82rem; color: var(--c-text) !important;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.t-sent-lbl { font-size: 0.72rem; color: var(--c-text-muted) !important; margin-left: auto; flex: none; }
.t-sent-up .t-sent-lbl { color: var(--c-up) !important; }
.t-sent-down .t-sent-lbl { color: var(--c-down) !important; }

.js-plotly-plot, .plotly { max-width: 100% !important; }

.t-chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 8px 0 16px; }
@media (max-width: 767px) { .t-chart-grid { grid-template-columns: 1fr; } }
.t-ov-note { font-size: 0.78rem; color: var(--c-text-muted) !important; margin: 4px 0 10px; }

@media (min-width: 992px) {
    .t-title { font-size: 2.15rem; }
}

/* ============ mobility + motion ============ */
@media (max-width: 768px) {
    .block-container { padding-top: 0.6rem !important; padding-left: 1rem !important; padding-right: 1rem !important; max-width: 100%; }
    .main-title { font-size: 1.45rem; padding-top: 0.5rem; }
    .sub-title { font-size: 0.75rem; }
    .t-title { font-size: 1.45rem; letter-spacing: -0.03em; }
    .t-kicker { font-size: 11px; }
    .t-sub { font-size: 0.8rem; }
    .t-meta-row { margin-top: 12px; justify-content: center; }
    div[data-testid="stMetricValue"] { font-size: 1.15rem !important; }
    .t-kpi-value { font-size: 1.2rem; }
    .t-kpi { padding: 16px; }
    .t-hero-value { font-size: 3.25rem; }
    .t-hero-side { margin-top: 4px; }
    .t-section-title { letter-spacing: 0.1em; }
    .t-sheet { grid-template-columns: 1fr; }
    .t-kpi-grid-4, .t-kpi-grid-5 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 620px) {
    .ladder-meta-row { text-align: left; }
}
@media (max-width: 480px) {
    .st-key-nb_mobile_bar { padding-bottom: calc(8px + env(safe-area-inset-bottom, 0px)) !important; }
    .st-key-nb_mobile_bar .nb-bar-item, .st-key-nb_mobile_bar [data-testid="stPageLink-NavLink"] { padding: 8px 0 8px !important; font-size: 10px !important; }
    .t-hero-value { font-size: 3.25rem; letter-spacing: -0.03em; }
    .t-brief-value { font-size: 3.1rem; }
}
@media (prefers-reduced-motion: reduce) {
    .ticker-move { animation: none; }
    * { scroll-behavior: auto !important; }
}
"""


def inject_css():
    st.markdown(f"<style>{DESIGN_SYSTEM_CSS}</style>", unsafe_allow_html=True)