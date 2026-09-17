# -------------------------------------------------
# lib/ui/nav — product shell: desktop rail + mobile bottom bar.
#
# STATE-PRESERVING navigation. Earlier versions rendered raw `<a href="../{slug}">`
# anchors through st.markdown. Streamlit's markdown renderer rewrites every
# synthetic anchor to target="_blank" (a NEW browser tab), and each new tab is a
# fresh websocket session — so every nav click silently dropped the Command
# Center's session context (cc_books, cc_rates, cc_* briefing, ...). That defect
# was proven empirically during the cross-page integrity audit (captured DOM
# `<a href="../command" target="_blank" rel="noopener noreferrer">` and
# window-handles 1 -> 2 on click). This is the single biggest cross-page defect
# in this app and the reason the drill-down pages displayed fallbacks instead of
# the live session.
#
# The shell now renders with st.page_link, which Streamlit routes through the
# SAME websocket session (client-side page swap via preventDefault + internal
# page change in the pages-manager bundle). It is the only supported primitive
# that keeps session state across page navigation.
#
# Northline rail (SPEC §3): an ungrouped private-bank rail —
#   Command · Outlook · Holdings · Funds · Desk
#   ─────────────────────────────────────────
#   Intelligence · Pulse
# Decision Desk is a drill page (reached from Outlook), never a nav item; when
# it is the current page a static "you are here" badge renders in the rail.
# Group caption elements are kept in the DOM (AppTest pins the string) but
# visually suppressed by theme.py, so the rail reads ungrouped.
#
# Rendering model:
#   * Desktop (>=992px): the rail lives in the real st.sidebar, styled by
#     theme.py to the brand rail (width --rail-w, bg-raised, active badge).
#     Streamlit's default sidebar chrome/chevron is hidden by theme CSS so the
#     rail is always expanded.
#   * Mobile (<992px): a fixed bottom bar of exactly five items
#     (Command Outlook Holdings Funds Desk), built from st.page_link elements
#     inside st.container(key="nb_mobile_bar"). The key becomes the CSS class
#     "st-key-nb_mobile_bar" (Streamlit st.container contract), so theme.py can
#     dock it to the bottom of the viewport without owning this DOM. A Pulse
#     link lives top-right in st-container(key="nb_topbar").
#   * The CURRENT page renders as a static .nb-active badge (never a self-link)
#     in both the rail and the bar.
#
# NOTE: this module is no longer pure — it renders Streamlit elements and
# returns None. The slug <-> file mapping in PAGE_FILES must match the st.Page
# paths in app.py exactly.
# -------------------------------------------------
from __future__ import annotations

import html as _html

import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

# (slug, rail label, mobile/top label, glyph). Order is the rail order.
_PRIMARY_ITEMS = [
    ("command", "Command", "Home", "\u25cf"),
    ("outlook", "Outlook", "Plan", "\u25f7"),
    ("holdings", "Holdings", "Hold", "\u25a3"),
    ("funds", "Funds", "Funds", "\u25d0"),
    ("desk", "Desk", "Desk", "\u2699"),
]

_INTEL_ITEMS = [
    ("intelligence", "Intelligence", "Intel", "\u2726"),
    ("pulse", "Pulse", "Pulse", "\u2261"),
]

# Backward-compatible group view of the rail (labels hidden visually by CSS).
NAV_GROUPS = [
    ("BOOKS", _PRIMARY_ITEMS),
    ("INTELLIGENCE", _INTEL_ITEMS),
]

# The five always-visible items on the mobile bottom bar.
_MOBILE_ITEMS = _PRIMARY_ITEMS

# Slug -> st.navigation source file (must match app.py st.Page paths exactly).
PAGE_FILES = {
    "command": "pages/1_Command_Center.py",
    "holdings": "pages/3_Asset_Detail.py",
    "funds": "pages/5_MF_Health.py",
    "intelligence": "pages/6_Intelligence.py",
    "pulse": "pages/4_News.py",
    "outlook": "pages/7_Outlook.py",
    "decisions": "pages/2_Deep_Health.py",
    "desk": "pages/8_Desk.py",
}

_DECISIONS = ("decisions", "Decision Desk", "Move", "\u2192")


def _active_badge(label, glyph, mobile=False):
    """Static markdown badge for the current page (never a self-link)."""
    cls = "nb-bar-item" if mobile else "nb-link"
    return (f'<div class="{cls} nb-active" aria-current="page">'
            f'<span class="nb-glyph">{glyph}</span>'
            f'<span class="nb-item">{_html.escape(label)}</span></div>')


def _group_label(group):
    return f'<div class="nb-group-label">{_html.escape(group)}</div>'


def safe_page_link(page, label, help=None):
    """st.page_link that degrades to a no-op outside a registered navigation.

    Page links resolve only against the pages st.navigation registered in
    app.py. A page executed standalone (e.g. an AppTest harness, or a direct
    `streamlit run pages/...` by accident) has no registered pages, so page_link
    raises StreamlitPageNotFoundError. The shell must not crash in that mode —
    it simply omits the unresolved links. Inside the real app every link
    resolves, because app.py registers exactly the paths in PAGE_FILES.
    """
    try:
        st.page_link(page, label=label, help=help)
    except StreamlitPageNotFoundError:
        pass


def _render_rail_item(slug, label, glyph, current):
    if slug == current:
        st.markdown(_active_badge(label, glyph), unsafe_allow_html=True)
    else:
        safe_page_link(PAGE_FILES[slug], label=f"{glyph}  {label}",
                       help=f"Open {label}")


def nav_shell(current="command"):
    """Render the product shell (desktop rail + mobile bottom bar). Returns None.

    Streamlit pages call this right after inject_css(). Navigation is rendered
    via st.page_link, so navigating keeps the current websocket session (and
    therefore the Command Center context) intact.
    """
    # Mobile top brand + Pulse link (theme hides nb_topbar >=992px).
    with st.container(key="nb_topbar"):
        _top_left, _top_right = st.columns([3, 1], vertical_alignment="center")
        with _top_left:
            st.markdown(
                '<div class="nb-topbar">'
                '<span class="nb-top-name">NORTHLINE</span>'
                '<span class="nb-top-sub">Family desk</span>'
                "</div>",
                unsafe_allow_html=True,
            )
        with _top_right:
            with st.container(key="nb_pulse_link"):
                safe_page_link(PAGE_FILES["pulse"], label="\u2261  Pulse",
                               help="Open Pulse")

    # Mobile bottom bar — exactly five items, pinned by the container key.
    # page_link's icon param only accepts emoji, so the geometric glyphs are
    # carried INSIDE the label text (plain text glyphs matching the badge).
    with st.container(key="nb_mobile_bar"):
        _cols = st.columns(len(_MOBILE_ITEMS))
        for _col, (slug, label, short, glyph) in zip(_cols, _MOBILE_ITEMS):
            if slug == current:
                _col.markdown(_active_badge(short, glyph, mobile=True),
                              unsafe_allow_html=True)
            else:
                safe_page_link(PAGE_FILES[slug], label=f"{glyph}  {short}")

    # Desktop rail — st.sidebar styled by theme.py as the brand rail.
    with st.sidebar:
        st.markdown(
            '<div class="nb-brand"><div class="nb-brand-name">NORTHLINE</div>'
            '<div class="nb-brand-sub">Family desk</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown(_group_label("BOOKS"), unsafe_allow_html=True)
        for slug, label, _short, glyph in _PRIMARY_ITEMS:
            _render_rail_item(slug, label, glyph, current)

        if current == "decisions":
            # Decision Desk is a drill page, never a nav item; a static
            # "you are here" badge keeps the active-page contract honest.
            _slug, label, _short, glyph = _DECISIONS
            st.markdown(_active_badge(label, glyph), unsafe_allow_html=True)

        st.markdown('<div class="nb-divider"></div>', unsafe_allow_html=True)
        st.markdown(_group_label("INTELLIGENCE"), unsafe_allow_html=True)
        for slug, label, _short, glyph in _INTEL_ITEMS:
            _render_rail_item(slug, label, glyph, current)

        st.markdown(
            '<div class="nb-rail-foot">NRI-aware books.<br>Not investment advice.</div>',
            unsafe_allow_html=True,
        )