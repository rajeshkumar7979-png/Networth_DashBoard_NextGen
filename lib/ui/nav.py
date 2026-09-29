from __future__ import annotations

import html as _html

import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

_PRIMARY_ITEMS = [
    ("command", "Command", "Command", "\u25cf"),
    ("outlook", "Outlook", "Outlook", "\u25f7"),
    ("holdings", "Holdings", "Holdings", "\u25a3"),
    ("funds", "Funds", "Funds", "\u25d0"),
    ("desk", "Desk", "Desk", "\u2699"),
]

_INTEL_ITEMS = [
    ("intelligence", "Intelligence", "Intel", "\u2726"),
    ("pulse", "Pulse", "Pulse", "\u2261"),
    ("asset-intelligence", "Asset Intel", "Asset", "\u25c8"),
]

NAV_GROUPS = [
    ("BOOKS", _PRIMARY_ITEMS),
    ("INTELLIGENCE", _INTEL_ITEMS),
]

_MOBILE_ITEMS = _PRIMARY_ITEMS

PAGE_FILES = {
    "command": "pages/1_Command_Center.py",
    "holdings": "pages/3_Asset_Detail.py",
    "funds": "pages/5_MF_Health.py",
    "intelligence": "pages/6_Intelligence.py",
    "pulse": "pages/4_News.py",
    "outlook": "pages/7_Outlook.py",
    "decisions": "pages/2_Deep_Health.py",
    "desk": "pages/8_Desk.py",
    "asset-intelligence": "pages/9_Asset_Intelligence.py",
}

_DECISIONS = ("decisions", "Decision Desk", "Move", "\u2192")


def _active_badge(label, glyph, mobile=False):
    cls = "nb-bar-item" if mobile else "nb-link"
    return (f'<div class="{cls} nb-active" aria-current="page">'
            f'<span class="nb-glyph">{glyph}</span>'
            f'<span class="nb-item">{_html.escape(label)}</span></div>')


def _group_label(group):
    return f'<div class="nb-group-label">{_html.escape(group)}</div>'


def safe_page_link(page, label, help=None, icon=None, use_container_width=None):
    try:
        kwargs = {"label": label}
        if help:
            kwargs["help"] = help
        if icon:
            kwargs["icon"] = icon
        if use_container_width is not None:
            kwargs["use_container_width"] = use_container_width
        st.page_link(page, **kwargs)
    except TypeError:
        try:
            st.page_link(page, label=label, help=help)
        except StreamlitPageNotFoundError:
            pass
    except StreamlitPageNotFoundError:
        pass


def _render_rail_item(slug, label, glyph, current):
    if slug == current:
        st.markdown(_active_badge(label, glyph), unsafe_allow_html=True)
    else:
        safe_page_link(PAGE_FILES[slug], label=f"{glyph}  {label}", help=f"Open {label}")


def nav_shell(current="command"):
    with st.container(key="nb_topbar"):
        st.markdown(
            '<div class="nb-topbar">'
            '<span class="nb-top-kicker">Northline</span>'
            '<span class="nb-top-name">Family desk</span>'
            "</div>",
            unsafe_allow_html=True,
        )
        with st.container(key="nb_pulse_link"):
            safe_page_link(PAGE_FILES["pulse"], label="Pulse", help="Open Pulse")

    with st.container(key="nb_mobile_bar"):
        for slug, label, short, glyph in _MOBILE_ITEMS:
            if slug == current:
                st.markdown(_active_badge(short, glyph, mobile=True), unsafe_allow_html=True)
            else:
                safe_page_link(PAGE_FILES[slug], label=f"{glyph}  {short}",
                               help=f"Open {label}", use_container_width=True)

    with st.sidebar:
        st.markdown(
            '<div class="nb-brand"><div class="nb-brand-kicker">Northline</div>'
            '<div class="nb-brand-name">Family desk</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown(_group_label("BOOKS"), unsafe_allow_html=True)
        for slug, label, _short, glyph in _PRIMARY_ITEMS:
            _render_rail_item(slug, label, glyph, current)

        if current == "decisions":
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
