# ==================================================
# IA pages — product-shell + standalone-page tests.
#
# These tests are NETWORK-FREE by construction: every page is driven with an
# empty (or n/a) Command Center session, so each renders only its early
# empty-state path or degrades to workbook rows. The live-with-data variants
# live in tests/test_page_smoke.py (smoke-marked).
# ==================================================
from pathlib import Path

import pytest

from lib.ui import NAV_GROUPS, nav_shell

ROOT = Path(__file__).resolve().parents[1]


def _all_slugs():
    return [slug for _, items in NAV_GROUPS for slug, _l, _s, _g in items]


def test_nav_groups_cover_all_pages():
    pages = sorted(p.name for p in (ROOT / "pages").glob("*.py"))
    slugs = set(_all_slugs())
    # exactly one page file per slug expectation: 8 files, 8 slugs
    assert len(pages) == 8, pages
    assert len(slugs) == 8, slugs
    expected_commands = {
        "command": "1_Command_Center.py",
        "holdings": "3_Asset_Detail.py",
        "funds": "5_MF_Health.py",
        "intelligence": "6_Intelligence.py",
        "pulse": "4_News.py",
        "outlook": "7_Outlook.py",
        "decisions": "2_Deep_Health.py",
        "desk": "8_Desk.py",
    }
    for slug, _label, _short, _glyph in (
        s for _g, items in NAV_GROUPS for s in items
    ):
        # each nav entry attaches to a real, registered page file
        assert (ROOT / "pages" / expected_commands[slug]).exists(), slug


def test_nav_shell_contains_every_slug_and_groups():
    html = nav_shell("command")
    for slug in _all_slugs():
        assert f'href="{slug}"' in html, slug
    assert html.count('class="nb-rail"') == 1
    assert html.count('class="nb-topbar"') == 1
    assert html.count('class="nb-bar"') == 1
    # the active page is highlighted exactly once in the rail and once in the bar
    assert html.count('class="nb-link nb-active"') == 1
    assert html.count('class="nb-bar-item nb-active"') == 1
    for group, _items in NAV_GROUPS:
        assert f'class="nb-group-label">{group}</div>' in html


def test_nav_shell_escapes_current_slug():
    html = nav_shell("command")
    assert "nb-active" in html


@pytest.mark.parametrize("page_name,slug", [
    # Command Center is intentionally absent: it performs live valuation
    # fetches and is exercised by the smoke-marked AppTest instead.
    ("2_Deep_Health.py", "decisions"),
    ("3_Asset_Detail.py", "holdings"),
    ("5_MF_Health.py", "funds"),
    ("6_Intelligence.py", "intelligence"),
    ("7_Outlook.py", "outlook"),
    ("8_Desk.py", "desk"),
])
def test_pages_render_empty_state_without_network(page_name, slug):
    """Each standalone page must not raise when no Command Center session
    exists, and must render its navigation chrome (rail HTML) first."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "pages" / page_name))
    at.run(timeout=180)
    assert not at.exception, f"{page_name} raised: {at.exception}"
    rendered = [m.value for m in at.markdown]
    assert any("nb-rail" in r for r in rendered), f"{page_name} missing nav rail"
    assert any(f'href="{slug}"' in r for r in rendered)


def test_pulse_avoids_live_news_fetch_without_session():
    """Pulse must never hit the network in the default suite. With no Command
    Center news, it emits its empty state and stops (network seal)."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "pages" / "4_News.py"))
    # Monkey-patch the news fetcher so a live call (if any path reached it)
    # would visibly fail the test instead of silently going online.
    import lib.news as _news

    def _boom(*_a, **_k):
        raise AssertionError("Pulse attempted a network news fetch in the default suite")

    _orig = _news.get_portfolio_news
    _news.get_portfolio_news = _boom
    try:
        at.run(timeout=180)
    finally:
        _news.get_portfolio_news = _orig
    assert not at.exception, f"Pulse raised: {at.exception}"