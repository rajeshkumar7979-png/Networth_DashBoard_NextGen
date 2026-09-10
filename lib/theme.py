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
/* ============ base ============ */
.stApp { background: #0a0e17; color: #e5e9f0; -webkit-font-smoothing: antialiased; }
html, body, [data-testid="stAppViewContainer"] { background: #0a0e17; }

* { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }

p, span, label, ul, ol, li, .stMarkdown, div[data-testid="stMarkdownContainer"] {
    color: #c2c9d6 !important;
}
a { color: #7fa8f5; text-decoration: none; }
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
section[data-testid="stSidebar"] {
    background-color: #0d1220 !important; border-right: 1px solid #1c2333;
}
section[data-testid="stSidebar"] * { color: #aeb7c8; }
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding-top: 1rem; }
#stSidebarUserContent > div { min-width: 18rem; }

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
}
@media (max-width: 991px) {
    [data-testid="stMainBlockContainer"], .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
}

/* ============ typography scale ============ */
.t-kicker { font-size: 0.66rem; font-weight: 800; letter-spacing: 0.24em; text-transform: uppercase; color: #6b8fd6; margin: 0 0 7px 0; }
.t-title { font-size: 2.05rem; font-weight: 800; color: #f8fafc; letter-spacing: -0.028em; line-height: 1.06; margin: 0; }
.t-sub { font-size: 0.86rem; color: #7c86a0; font-weight: 400; margin: 8px 0 0 0; line-height: 1.5; }
.t-meta-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 12px 0 2px 0; }

/* Section header: label — rule — meta, with guaranteed gaps (never concat).
   A leading index chip (Deep Health step numbers, e.g. 01) is .t-section-index. */
.t-section { margin: 1.9rem 0 0.7rem 0; }
.t-section-title {
    font-size: 0.73rem; font-weight: 800; color: #8b95a8; text-transform: uppercase;
    letter-spacing: 0.11em; display: flex; align-items: center; gap: 12px; margin: 0;
}
.t-section-index {
    font-size: 0.68rem; font-weight: 800; letter-spacing: 0.02em; color: #3b82f6;
    background: rgba(59,130,246,0.12); border: 1px solid rgba(59,130,246,0.22);
    border-radius: 5px; padding: 2px 7px; flex: none; white-space: nowrap;
}
.t-section-lbl { flex: none; white-space: nowrap; }
.t-section-title::after { content: ""; flex: 1; height: 1px; background: #1a2233; }
.t-section-meta {
    font-size: 0.68rem; color: #5b6478; font-weight: 600; letter-spacing: 0.03em;
    text-transform: none; flex: none; white-space: nowrap;
}

/* ============ Streamlit element restyle ============ */
div[data-testid="stMetric"] {
    background: linear-gradient(155deg, #12182a 0%, #0e1420 100%);
    border: 1px solid #1c2333; border-radius: 12px; padding: 12px 15px 10px 15px;
}
div[data-testid="stMetric"]:hover { border-color: #2a3552; }
div[data-testid="stMetricValue"] { font-size: 1.35rem !important; font-weight: 700 !important; color: #f8fafc !important; }
div[data-testid="stMetricLabel"] { color: #6b7688 !important; font-size: 0.66rem !important; font-weight: 600 !important; text-transform: uppercase; letter-spacing: 0.08em; }
div[data-testid="stMetricDelta"] { font-size: 0.75rem !important; }
div[data-testid="stCaptionContainer"] p { font-size: 0.72rem; color: #5b6478; line-height: 1.5; }

.stTabs [data-baseweb="tab-list"] { background-color: #0f1420; gap: 3px; border-radius: 9px; padding: 3px; border: 1px solid #1c2333; width: fit-content; max-width: 100%; overflow-x: auto; }
.stTabs [data-baseweb="tab"] { color: #6b7688 !important; border-radius: 6px; padding: 7px 18px; font-weight: 500; }
.stTabs [aria-selected="true"] { background: linear-gradient(135deg, #1e2942, #17203a) !important; color: #f8fafc !important; font-weight: 600; }

.stDataFrame, [data-testid="stDataFrame"] {
    border: 1px solid #1c2333; border-radius: 10px; overflow: hidden;
}
.stDataFrame *, [data-testid="stDataFrame"] * { font-size: 0.76rem; }
.stDataFrame [data-testid="stDataFrame"] {
    --grid-border-color: #161d2d;
}
.stExpander { border: 1px solid #1c2333 !important; border-radius: 10px !important; background: #0c1220 !important; }
.stExpander summary { font-size: 0.82rem !important; font-weight: 600; color: #c2c9d6; }
div[data-baseweb="select"] > div, div[data-testid="stNumberInput"] input,
div[data-testid="stTextInput"] input, div[data-testid="stSelectbox"] > div > div {
    background-color: #0f1420 !important; border-color: #2a3552 !important; color: #e5e9f0 !important;
}
div[data-testid="stNumberInput"] input { color: #f8fafc !important; font-weight: 600; }
.stButton > button, .stDownloadButton > button {
    background: #141c2e !important; border: 1px solid #2a3552 !important; color: #d7dce6 !important;
    border-radius: 8px; font-weight: 600; font-size: 0.8rem; padding: 0.45rem 0.9rem;
}
.stButton > button[kind="primary"] { background: linear-gradient(135deg,#1e3a8a,#2563eb) !important; border-color:#3b82f6 !important; color:#fff !important; }
.stButton > button:hover, .stDownloadButton > button:hover { border-color: #3b82f6 !important; }
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible,
input:focus-visible, [data-testid="stSelectbox"]:focus-within { outline: 2px solid #3b82f6 !important; outline-offset: 1px; }

.stProgress > div > div > div { background: linear-gradient(90deg,#2563eb,#60a5fa); }

/* Sidebar navigation — quiet grouped hierarchy (PORTFOLIO / DECISION / INTELLIGENCE) */
[data-testid="stSidebarNav"] { padding: 0.5rem 0 0.75rem 0; }
[data-testid="stSidebarNav"] a { display: flex; align-items: center; gap: 10px; padding: 7px 12px !important; margin: 1px 6px; border-radius: 8px; font-size: 0.82rem; font-weight: 500; color: #9aa4b8 !important; }
[data-testid="stSidebarNav"] a:hover { background: #101828; color: #d7dce6 !important; }
[data-testid="stSidebarNav"] a[aria-current="page"] { background: linear-gradient(135deg,#1e2942,#17203a) !important; color: #f8fafc !important; font-weight: 700; }
[data-testid="stSidebarNav"] a[aria-current="page"]::before { content: ""; }
.stSidebarNavSectionLabel, [data-testid="stSidebarNav"] .stSidebarNavSectionLabel {
    font-size: 0.6rem; font-weight: 800; letter-spacing: 0.16em; color: #4b5570;
    text-transform: uppercase; padding: 10px 16px 2px 16px;
}
.stSidebarNavSectionSeparator { border-top: 1px solid #161d2d; margin: 6px 14px; }

/* ============ shared terminal components (t-*) ============ */
.t-kpi-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; margin: 4px 0 6px 0; }
.t-kpi-grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.t-kpi-grid-5 { grid-template-columns: repeat(5, minmax(0, 1fr)); }
@media (max-width: 1200px) { .t-kpi-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 700px)  { .t-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.t-kpi {
    background: linear-gradient(155deg, #12182a 0%, #0e1420 100%);
    border: 1px solid #1c2333; border-radius: 11px; padding: 11px 13px 10px 13px;
    min-height: 78px; display: flex; flex-direction: column; justify-content: space-between;
}
.t-kpi:hover { border-color: #2a3552; }
.t-kpi-label { font-size: 0.64rem; font-weight: 800; color: #6b7688; text-transform: uppercase; letter-spacing: 0.09em; }
.t-kpi-value { font-size: 1.18rem; font-weight: 800; color: #f8fafc; margin-top: 5px; font-variant-numeric: tabular-nums; line-height: 1.1; word-break: break-word; }
.t-kpi-sub { font-size: 0.68rem; color: #7c86a0; margin-top: 4px; font-weight: 500; }
.t-kpi-tone-up .t-kpi-value { color: #4ade80; }
.t-kpi-tone-down .t-kpi-value { color: #f87171; }
.t-kpi-tone-warn .t-kpi-value { color: #fbbf24; }
.t-kpi-tone-accent .t-kpi-value { color: #7fa8f5; }

.t-pill {
    display: inline-flex; align-items: center; gap: 6px; font-size: 0.7rem; font-weight: 700;
    color: #9aa4b8; background: #0f1420; border: 1px solid #262f45; border-radius: 999px; padding: 4px 11px;
}
.t-pill .t-dot { width: 7px; height: 7px; border-radius: 50%; background: #64748b; flex: none; }
.t-pill-ok   .t-dot { background: #22c55e; } .t-pill-ok { color: #86efac; border-color: rgba(34,197,94,0.35); }
.t-pill-cache .t-dot { background: #eab308; } .t-pill-cache { color: #fde68a; border-color: rgba(234,179,8,0.35); }
.t-pill-off  .t-dot { background: #ef4444; } .t-pill-off { color: #fca5a5; border-color: rgba(239,68,68,0.35); }
.t-pill-info .t-dot { background: #60a5fa; } .t-pill-info { color: #93c5fd; border-color: rgba(96,165,250,0.35); }

.t-badge {
    display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 0.64rem;
    font-weight: 800; letter-spacing: 0.04em; background: rgba(100,116,139,0.16); color: #94a3b8; border: 1px solid transparent;
}
.t-badge-pos  { background: rgba(34,197,94,0.14);  color: #4ade80; }
.t-badge-neg  { background: rgba(239,68,68,0.14);  color: #f87171; }
.t-badge-warn { background: rgba(245,158,11,0.14); color: #fbbf24; }
.t-badge-info { background: rgba(59,130,246,0.14); color: #93c5fd; }
.t-badge-live { background: rgba(34,197,94,0.18);  color: #4ade80; border-color: rgba(34,197,94,0.3); }
.t-badge-stale{ background: rgba(245,158,11,0.18); color: #fbbf24; border-color: rgba(245,158,11,0.3); }

/* Fact-kind chips: the provenance taxonomy from lib.intelligence.model */
.t-chip { display: inline-block; padding: 2px 8px; border-radius: 5px; font-size: 0.6rem; font-weight: 800; letter-spacing: 0.07em; }
.t-chip-fact  { background: rgba(59,130,246,0.16);  color: #93c5fd; }
.t-chip-calc  { background: rgba(34,197,94,0.14);  color: #4ade80; }
.t-chip-signal{ background: rgba(245,158,11,0.14); color: #fbbf24; }
.t-chip-ai    { background: rgba(168,85,247,0.16); color: #d8b4fe; }
.t-chip-reco  { background: rgba(239,68,68,0.14);  color: #f87171; }

.t-source { font-size: 0.66rem; color: #5b6478; font-weight: 600; letter-spacing: 0.03em; }
.t-caption { font-size: 0.72rem; color: #5b6478; line-height: 1.5; display: inline-block; }
.t-caption-pos { color: #6ee7a0; }
.t-caption-neg { color: #fca5a5; }
.t-caption-warn { color: #fcd34d; }
.t-footnote { font-size: 0.66rem; color: #4b5570; line-height: 1.45; }
.t-empty {
    border: 1px dashed #262f45; border-radius: 10px; padding: 14px 16px; color: #8b95a8;
    font-size: 0.78rem; background: #0c1220;
}
.t-empty b { color: #c2c9d6; }
.t-empty-hint { margin-top: 6px; font-size: 0.72rem; color: #5b6478; line-height: 1.45; }

.t-card { background: linear-gradient(155deg, #12182a 0%, #0e1420 100%);
    border: 1px solid #1c2333; border-radius: 12px; padding: 12px 14px;
    font-size: 0.8rem; color: #9aa4b8; line-height: 1.55; }
.t-card a { color: #7cb3ff; }
.t-card-title { display: block; font-size: 0.82rem; font-weight: 700; color: #f1f5f9; margin-bottom: 6px; }
.t-list { margin: 0; padding-left: 18px; }
.t-list li { margin: 3px 0; }
.t-list-row { display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
    font-size: 0.78rem; padding: 7px 0; border-bottom: 1px solid #141a28; }
.t-list-name { color: #e5e9f0; font-weight: 600; }
.t-list-meta { color: #9aa4b8; font-variant-numeric: tabular-nums; }

.t-banner { border-radius: 10px; padding: 10px 14px; margin: 8px 0 4px 0; border: 1px solid; font-size: 0.8rem; line-height: 1.4; }
.t-banner-critical { background: #3b1219; border-color: #7f1d1d; color: #fecaca; }
.t-banner-warn { background: #2b2010; border-color: #78350f; color: #fde68a; }
.t-banner-info { background: #0f1a2e; border-color: #1e3a5f; color: #cbd9f5; }
.t-banner-ok { background: #0e2418; border-color: #14532d; color: #bbf7d0; }
.t-banner b { color: inherit; }
.t-banner a { color: inherit; text-decoration: underline; }

/* horizontal stacked allocation bar */
.t-bar-track {
    display: flex; width: 100%; height: 16px; border-radius: 999px; overflow: hidden;
    border: 1px solid #1c2333; background: #0c1220; margin: 6px 0 2px 0;
}
.t-bar-seg { height: 100%; min-width: 0; }

.t-alloc-legend { list-style: none; margin: 6px 0 0 0; padding: 0; }
.t-alloc-legend li { display: flex; justify-content: space-between; gap: 12px; font-size: 0.75rem; color: #9aa4b8; padding: 4px 0; border-bottom: 1px solid #141a28; }
.t-alloc-legend .nm { color: #e5e9f0; font-weight: 600; }
.t-alloc-legend .amt { font-variant-numeric: tabular-nums; color: #c2c9d6; }

/* attention tiles */
.t-attn-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 6px 0 8px 0; }
@media (max-width: 1100px) { .t-attn-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 640px)  { .t-attn-grid { grid-template-columns: 1fr; } }
.t-attn-tile { border-radius: 10px; padding: 10px 12px; border: 1px solid; min-height: 88px; background: #0f1420; }
.t-attn-tag { display: inline-block; font-size: 0.58rem; font-weight: 800; letter-spacing: 0.07em; padding: 2px 7px; border-radius: 4px; margin-bottom: 6px; }
.t-tag-urgent { background: #7f1d1d; color: #fecaca; }
.t-tag-review { background: #78350f; color: #fde68a; }
.t-tag-upcoming { background: #1e3a5f; color: #93c5fd; }
.t-attn-title { font-size: 0.82rem; font-weight: 700; color: #f1f5f9; margin: 0 0 3px 0; line-height: 1.25; }
.t-attn-body { font-size: 0.7rem; color: #9aa4b8; margin: 0; line-height: 1.3; }

/* ============ executive hero ============ */
.t-hero {
    display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 14px;
    background: linear-gradient(140deg, #101627 0%, #0c1220 55%, #0d1220 100%);
    border: 1px solid #1c2333; border-radius: 16px; padding: 22px 26px;
    margin: 12px 0 18px 0;
}
@media (max-width: 900px) { .t-hero { grid-template-columns: 1fr; } }
.t-hero-main { display: flex; flex-direction: column; justify-content: center; }
.t-hero-kicker { font-size: 0.66rem; font-weight: 800; letter-spacing: 0.22em; text-transform: uppercase; color: #6b8fd6; margin: 0 0 8px 0; }
.t-hero-value { font-size: 2.9rem; font-weight: 800; color: #f8fafc; letter-spacing: -0.03em; line-height: 1.04; font-variant-numeric: tabular-nums; word-break: break-word; }
.t-hero-tone-up .t-hero-value { color: #4ade80; }
.t-hero-tone-down .t-hero-value { color: #f87171; }
.t-hero-tone-warn .t-hero-value { color: #fbbf24; }
.t-hero-tone-accent .t-hero-value { color: #7fa8f5; }
.t-hero-delta { margin-top: 8px; font-size: 0.82rem; font-weight: 600; color: #93c5fd; }
.t-hero-sub { margin-top: 5px; font-size: 0.78rem; color: #9aa4b8; }
.t-hero-foot { margin-top: 16px; font-size: 0.7rem; color: #5b6478; line-height: 1.45; }
.t-hero-side { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; align-items: stretch; }
@media (max-width: 560px) { .t-hero-side { grid-template-columns: 1fr; } }
.t-hero-side .t-kpi { min-height: 92px; }

/* ============ watchlist (restrained attention) ============ */
.t-watch-list { display: flex; flex-direction: column; gap: 8px; margin: 6px 0 8px 0; }
.t-watch {
    display: flex; gap: 12px; background: #0f1420; border: 1px solid #1c2333;
    border-radius: 10px; padding: 11px 14px; align-items: flex-start;
}
.t-watch:hover { border-color: #2a3552; }
.t-watch-bar { flex: none; width: 4px; align-self: stretch; border-radius: 999px; }
.t-watch-urgent .t-watch-bar { background: #ef4444; }
.t-watch-warn   .t-watch-bar { background: #f59e0b; }
.t-watch-info   .t-watch-bar { background: #3b82f6; }
.t-watch-main { flex: 1; min-width: 0; }
.t-watch-tag { display: inline-block; font-size: 0.58rem; font-weight: 800; letter-spacing: 0.07em; padding: 1px 7px; border-radius: 4px; margin-bottom: 5px; }
.t-watch-urgent .t-watch-tag { background: rgba(239,68,68,0.16); color: #fca5a5; }
.t-watch-warn   .t-watch-tag { background: rgba(245,158,11,0.16); color: #fde68a; }
.t-watch-info   .t-watch-tag { background: rgba(59,130,246,0.16); color: #93c5fd; }
.t-watch-title { font-size: 0.84rem; font-weight: 700; color: #f1f5f9; margin: 0 0 3px 0; line-height: 1.3; }
.t-watch-title a { color: #f1f5f9; }
.t-watch-title a:hover { color: #7fa8f5; }
.t-watch-body { font-size: 0.74rem; color: #9aa4b8; margin: 0; line-height: 1.4; }
.t-watch-why { margin-top: 6px; font-size: 0.7rem; color: #7c86a0; line-height: 1.4; }
.t-watch-why b { color: #93c5fd; font-weight: 600; }

/* ============ research rows ============ */
.t-research-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 8px 0 4px 0; }
@media (max-width: 1100px) { .t-research-grid { grid-template-columns: 1fr; } }
.t-research {
    background: #0f1420; border: 1px solid #1c2333; border-radius: 11px; padding: 11px 14px;
    min-height: 92px; display: flex; flex-direction: column; justify-content: flex-start;
}
.t-research:hover { border-color: #2a3552; }
.t-research-top { display: flex; gap: 8px; align-items: center; margin-bottom: 5px; }
.t-research-tag { font-size: 0.58rem; font-weight: 800; letter-spacing: 0.06em; padding: 1px 7px; border-radius: 4px; background: rgba(59,130,246,0.14); color: #93c5fd; }
.t-research-meta { margin-left: auto; font-size: 0.64rem; color: #5b6478; font-weight: 500; white-space: nowrap; }
.t-research-title { font-size: 0.84rem; font-weight: 600; color: #eef2f7; line-height: 1.35; margin: 0; }
.t-research-title a { color: #eef2f7; }
.t-research-title a:hover { color: #7fa8f5; }
.t-research-body { margin-top: 5px; font-size: 0.73rem; color: #8b95a8; line-height: 1.45; }

/* ============ unavailable (single deliberate empty state) ============ */
.t-unavailable {
    background: #0c1220; border: 1px dashed #262f45; border-radius: 12px;
    padding: 22px 26px; text-align: center; margin: 8px 0;
}
.t-unavail-mark { font-size: 1.3rem; font-weight: 300; color: #3b485f; letter-spacing: 0.1em; }
.t-unavail-title { font-size: 0.85rem; font-weight: 600; color: #8b95a8; margin-top: 4px; }
.t-unavail-detail { font-size: 0.73rem; color: #5b6478; margin-top: 3px; }

/* ============ evidence trail ============ */
.t-evidence { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.t-evidence-bit {
    font-size: 0.62rem; color: #7c86a0; background: #0f1420; border: 1px solid #1c2333;
    border-radius: 5px; padding: 1px 7px; font-weight: 500;
}

/* ============ legacy classes (consolidated from pages) ============ */
.main-title { font-size: 1.7rem; font-weight: 700; color: #f8fafc; letter-spacing: -0.03em; margin: 0 0 0.05rem 0; padding-top: 0.35rem; position: relative; z-index: 2; }
.sub-title { color: #6b7688; font-size: 0.82rem; margin-bottom: 0.8rem; font-weight: 400; }
.section-header {
    font-size: 0.74rem; font-weight: 800; color: #8b95a8; margin: 1.25rem 0 0.55rem 0;
    text-transform: uppercase; letter-spacing: 0.1em; display: flex; align-items: center; gap: 8px;
}
.section-header::after { content: ""; flex: 1; height: 1px; background: #181f31; }
.caveat { font-size: 0.72rem; color: #5b6478; font-style: italic; }
.recon-pass { color: #22c55e; font-weight: 600; }
.recon-fail { color: #ef4444; font-weight: 600; }
.snap-note { font-size: 0.72rem; color: #6b7688; margin-top: 4px; }

.status-row { display: flex; flex-wrap: wrap; gap: 10px; margin: 6px 0 4px 0; }
.status-pill { font-size: 0.7rem; color: #9aa4b8; background: #0f1420; border: 1px solid #1c2333; border-radius: 999px; padding: 4px 10px; font-weight: 600; }
.status-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; }
.dot-live { background: #22c55e; }
.dot-cache { background: #eab308; }
.dot-off { background: #ef4444; }

.flag-card { border-radius: 8px; padding: 7px 10px; margin-bottom: 0; display: flex; gap: 8px; align-items: flex-start; border: 1px solid; }
.flag-critical { background: rgba(239,68,68,0.08); border-color: rgba(239,68,68,0.28); }
.flag-warning  { background: rgba(245,158,11,0.08); border-color: rgba(245,158,11,0.28); }
.flag-info     { background: rgba(59,130,246,0.08); border-color: rgba(59,130,246,0.28); }
.flag-title { font-weight: 600; font-size: 0.78rem; color: #f1f5f9; margin: 0; line-height: 1.25; }
.flag-body  { font-size: 0.7rem; color: #9aa4b8; margin: 1px 0 0 0; line-height: 1.3; }
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
.attn-body { font-size: 0.7rem; color: #9aa4b8; margin: 0; line-height: 1.3; }

.crit-banner { background: #3b1219; border: 1px solid #7f1d1d; color: #fecaca; border-radius: 10px; padding: 10px 14px; margin: 8px 0 4px 0; font-size: 0.82rem; }
.crit-banner b { color: #fecaca; }

.pulse-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 8px 0 4px 0; }
@media (max-width: 1100px) { .pulse-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.pulse-card { background: linear-gradient(155deg, #12182a 0%, #0e1420 100%); border: 1px solid #1c2333; border-radius: 10px; padding: 12px 14px; min-height: 78px; overflow: hidden; }
.pulse-card:hover { border-color: #2a3552; }
.pulse-label { font-size: 0.65rem; font-weight: 700; color: #6b7688; text-transform: uppercase; letter-spacing: 0.06em; }
.pulse-val { font-size: 1.05rem; font-weight: 700; color: #f8fafc; margin-top: 2px; font-variant-numeric: tabular-nums; }
.pulse-chg-up { color: #22c55e; font-size: 0.78rem; font-weight: 700; }
.pulse-chg-dn { color: #ef4444; font-size: 0.78rem; font-weight: 700; }
.pulse-chg-na { color: #5b6478; font-size: 0.78rem; }

.ticker-wrap { width: 100%; overflow: hidden; background: #0b0f18; border: 1px solid #1c2333; border-radius: 10px; padding: 10px 0; white-space: nowrap; margin: 8px 0 4px 0; }
.ticker-move { display: inline-block; animation: ticker-scroll 50s linear infinite; }
.ticker-wrap:hover .ticker-move { animation-play-state: paused; }
@keyframes ticker-scroll { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
.ticker-item { display: inline-flex; align-items: baseline; gap: 6px; padding: 0 26px; font-size: 0.82rem; font-weight: 600; color: #e5e9f0; }
.ticker-name { color: #8b95a8; font-weight: 600; letter-spacing: 0.02em; }
.ticker-val { color: #f8fafc; font-variant-numeric: tabular-nums; }
.ticker-chg { font-weight: 700; font-variant-numeric: tabular-nums; }
.ticker-up .ticker-chg, .ticker-up .ticker-arrow { color: #22c55e; }
.ticker-down .ticker-chg, .ticker-down .ticker-arrow { color: #ef4444; }
.ticker-arrow { font-size: 0.95rem; font-weight: 800; }
.ticker-na { color: #5b6478; }

.why-box { background: #0f1420; border: 1px solid #1c2333; border-radius: 10px; padding: 10px 14px; margin-top: 8px; }
.why-box li { color: #9aa4b8; font-size: 0.78rem; margin: 3px 0; }

.alloc-legend { list-style: none; margin: 8px 0 0 0; padding: 0; }
.alloc-legend li { display: flex; justify-content: space-between; gap: 12px; font-size: 0.78rem; color: #9aa4b8; padding: 4px 0; border-bottom: 1px solid #141a28; }
.alloc-legend .nm { color: #e5e9f0; font-weight: 600; }
.alloc-legend .amt { font-variant-numeric: tabular-nums; color: #c2c9d6; }

.news-item { padding: 8px 0; border-bottom: 1px solid #1c2333; }
.news-item a { color: #d7dce6 !important; text-decoration: none; font-size: 0.84rem; font-weight: 500; }
.news-item a:hover { color: #7fa8f5 !important; }
.news-meta { font-size: 0.71rem; color: #5b6478; margin-top: 1px; }

/* ============ MF Health consolidated classes ============ */
.mfh-card { background: linear-gradient(155deg, #12182a 0%, #0e1420 100%); border: 1px solid #1c2333; border-radius: 14px; padding: 16px 18px; }
.mfh-kpi-label { font-size: 0.68rem; font-weight: 700; color: #6b7688; text-transform: uppercase; letter-spacing: 0.06em; }
.mfh-kpi-val { font-size: 1.55rem; font-weight: 800; color: #f8fafc; margin: 4px 0 2px 0; }
.mfh-kpi-sub { font-size: 0.72rem; color: #6b7688; }
.mfh-badge { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 0.68rem; font-weight: 700; }
.badge-low    { background: rgba(34,197,94,0.14);  color: #4ade80; }
.badge-mod    { background: rgba(245,158,11,0.14); color: #fbbf24; }
.badge-high   { background: rgba(239,68,68,0.14);  color: #f87171; }
.badge-vhigh  { background: rgba(239,68,68,0.22);  color: #fca5a5; }

.score-circle {
    display: inline-flex; align-items: center; justify-content: center;
    width: 38px; height: 38px; border-radius: 50%; font-weight: 800; font-size: 0.82rem;
    border: 3px solid;
}
.sc-excellent { border-color: #22c55e; color: #4ade80; }
.sc-good      { border-color: #eab308; color: #fbbf24; }
.sc-average   { border-color: #f97316; color: #fb923c; }
.sc-poor      { border-color: #ef4444; color: #f87171; }

.fund-row { border-bottom: 1px solid #1c2333; padding: 10px 4px; }
.fund-name { color: #f1f5f9 !important; font-weight: 600; font-size: 0.86rem; }
.fund-amc  { color: #6b7688 !important; font-size: 0.72rem; }
.cat-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #3b82f6; margin-right: 6px; }

/* horizontal rules — consistent with section-title hairline */
hr, [data-testid="stMarkdownHorizontalBlock"] { border: none !important; height: 1px !important; background: #1a2233 !important; margin: 1.6rem 0 !important; }

/* section wrapper — provides the intended vertical rhythm around .t-section-title */
.t-section { margin: 1.9rem 0 0.7rem 0; }

/* ============ mobility + motion ============ */
@media (max-width: 768px) {
    .block-container { padding-top: 1.8rem !important; padding-left: 0.9rem !important; padding-right: 0.9rem !important; }
    .main-title { font-size: 1.45rem; padding-top: 0.5rem; }
    .sub-title { font-size: 0.75rem; }
    .t-title { font-size: 1.4rem; }
    div[data-testid="stMetricValue"] { font-size: 1.15rem !important; }
    .t-kpi-value { font-size: 1.0rem; }
    .block-container { max-width: 100%; }
}
@media (prefers-reduced-motion: reduce) {
    .ticker-move { animation: none; }
    * { scroll-behavior: auto !important; }
}
"""


def inject_css():
    st.markdown(f"<style>{DESIGN_SYSTEM_CSS}</style>", unsafe_allow_html=True)