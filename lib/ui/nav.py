# -------------------------------------------------
# lib/ui/nav — product shell: desktop left rail + mobile bottom bar.
#
# Pure HTML-string builder (no streamlit/network). Every page renders
# nav_shell(<page-slug>) right after inject_css(); the single stylesheet in
# lib/theme.py owns the .nb-* classes. The Streamlit sidebar is hidden by CSS;
# this custom chrome gives the family-office rail (brand, grouped navigation,
# footer) on desktop and a first-class fixed bottom bar on mobile — the same
# set of links, one DOM, two media-query layouts.
#
# hrefs are ROUTE-RELATIVE, one level up: "../{slug}". Every st.navigation page
# (app.py url_paths) lives exactly one path segment under the deployment base
# path (e.g. "/command", "/holdings", or "/{basePath}/command" under a sub-path
# proxy). From any page, ".." therefore lands in the sibling-page directory, so
# the href resolves to the target page regardless of the base path — fixing the
# old relative "href={slug}" bug where, at "/holdings", clicking "command"
# compounded to "/holdings/command" (404). Same tab, no new tab, browser
# history works, direct URLs work.
#
# NOTE: st.page_link was rejected for this shell after inspection of the
# installed Streamlit frontend: page_link renders inside its own
# [data-testid="stPageLink"] / stElementContainer block and Streamlit elements
# can never nest inside custom HTML containers — so a fixed rail + bottom bar
# built from our own <nav> markup cannot contain real page_link elements
# without a complete layout rewrite. Route-relative anchors deliver the same
# in-app navigation with the design fully preserved. st.navigation url_paths
# (app.py) must match the slugs in NAV_GROUPS.
# -------------------------------------------------
from __future__ import annotations

import html as _html

# (slug, rail-label, short mobile label, glyph)
NAV_GROUPS = [
    ("BOOKS", [
        ("command", "Command Center", "Home", "\u25cf"),
        ("holdings", "Holdings", "Hold", "\u25a3"),
        ("funds", "Funds", "Funds", "\u25d0"),
    ]),
    ("INTELLIGENCE", [
        ("intelligence", "Intelligence", "Intel", "\u2726"),
        ("pulse", "Pulse", "Pulse", "\u2261"),
    ]),
    ("PLANNING", [
        ("outlook", "Outlook", "Plan", "\u25f7"),
        ("decisions", "Decision Desk", "Move", "\u2192"),
    ]),
    ("OPERATIONS", [
        ("desk", "Desk", "Desk", "\u2699"),
    ]),
]


def _link(slug, label, glyph, current, short=False):
    cls = " nb-active" if slug == current else ""
    text = label if not short else _glyph_label(slug)
    return (
        f'<a class="nb-link{cls}" href="../{_html.escape(slug, quote=True)}">'
        f'<span class="nb-glyph">{glyph}</span><span class="nb-item">{_html.escape(text)}</span></a>'
    )


def _glyph_label(slug):
    for _group, items in NAV_GROUPS:
        for _slug, _label, short, _glyph in items:
            if _slug == slug:
                return short
    return slug


def nav_shell(current="command"):
    """Full-shell HTML: desktop rail + mobile top brand + fixed bottom bar."""
    groups_html = []
    for group, items in NAV_GROUPS:
        links = "".join(_link(slug, label, glyph, current) for slug, label, _short, glyph in items)
        groups_html.append(
            f'<div class="nb-group"><div class="nb-group-label">{_html.escape(group)}</div>{links}</div>'
        )
    rail = (
        '<div class="nb-rail">'
        '<div class="nb-brand"><div class="nb-brand-name">NORTHLINE</div>'
        '<div class="nb-brand-sub">Family desk</div></div>'
        '<nav class="nb-groups">' + "".join(groups_html) + "</nav>"
        '<div class="nb-rail-foot">NRI-aware books.<br>Not investment advice.</div>'
        "</div>"
    )
    topbar = (
        '<div class="nb-topbar">'
        '<span class="nb-top-name">NORTHLINE</span>'
        '<span class="nb-top-sub">Family desk</span>'
        "</div>"
    )
    bar_items = []
    for group, items in NAV_GROUPS:
        for slug, _label, short, glyph in items:
            cls = " nb-active" if slug == current else ""
            bar_items.append(
                f'<a class="nb-bar-item{cls}" href="../{_html.escape(slug, quote=True)}">'
                f'<span class="nb-glyph">{glyph}</span><span class="nb-bar-label">{short}</span></a>'
            )
    bar = '<nav class="nb-bar">' + "".join(bar_items) + "</nav>"
    return rail + topbar + bar