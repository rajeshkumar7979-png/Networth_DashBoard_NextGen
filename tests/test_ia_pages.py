# ==================================================
# IA pages — product-shell + standalone-page tests.
#
# These tests are NETWORK-FREE by construction: every page is driven with an
# empty (or n/a) Command Center session, so each renders only its early
# empty-state path. The live-with-data variants live in
# tests/test_page_smoke.py (smoke-marked; they run the real app.py so
# st.page_link resolves against the st.navigation registry).
#
# Navigation contract (audit fix, pinned here):
#   - lib/ui/nav.py renders navigation with state-preserving st.page_link
#     elements, NOT markdown anchors. Streamlit rewrites every custom <a> in
#     st.markdown(unsafe_allow_html=True) to target="_blank", which opens a
#     fresh browser tab -> fresh websocket session -> all cc_* context lost on
#     every in-app hop. Therefore NO rendered markdown anywhere may contain an
#     href="../" anchor (the old contract) or any other route-relative href.
#     The negative assertion below is the regression guard.
#   - In a standalone AppTest there is no st.navigation registry, so
#     safe_page_link() skips every st.page_link (StreamlitPageNotFoundError is
#     caught and the item renders as its bare label/badge instead). Real
#     page-link resolution is exercised by the smoke suite through app.py.
# ==================================================
from pathlib import Path

import pytest

from lib.ui import PAGE_FILES

ROOT = Path(__file__).resolve().parents[1]


def _all_slugs():
    return sorted(PAGE_FILES.keys())


# slug -> standalone empty-state sentinel that proves the page degraded honestly
# (never fabricated data) when the Command Center has not published a session.
EMPTY_STATE = {
    "holdings": "Open the Command Center first",
    "funds": "Open the Command Center once so your funds",
    "intelligence": "Intelligence hasn't been computed in this session yet.",
    "pulse": "No news in this session yet",
    "outlook": "No FD book in this session yet.",
    "desk": "Nothing to show until the Command Center runs.",
    # Decision Desk is a deterministic sandbox that always renders (inputs start at
    # zero, see test_decision_desk_starts_from_zero_without_command_center); its
    # content sentinel is the first section header.
    "decisions": "Money to move",
}

# pages that can render standalone without live valuation (Command Center
# excluded: it performs live fetches and is exercised by the smoke AppTest).
STANDALONE = [
    ("2_Deep_Health.py", "decisions"),
    ("3_Asset_Detail.py", "holdings"),
    ("4_News.py", "pulse"),
    ("5_MF_Health.py", "funds"),
    ("6_Intelligence.py", "intelligence"),
    ("7_Outlook.py", "outlook"),
    ("8_Desk.py", "desk"),
]


def test_nav_groups_cover_all_pages():
    files = sorted(p.name for p in (ROOT / "pages").glob("*.py"))
    assert len(files) == 8, files
    slugs = _all_slugs()
    assert len(slugs) == 8, slugs
    for slug, file in PAGE_FILES.items():
        # each nav entry attaches to a real, registered page file
        assert (ROOT / "pages" / Path(file).name).exists(), f"{slug} -> {file}"
    # every registered page file (except Command Center, covered by the smoke
    # AppTest) has exactly one nav slug — 8 files, 8 slugs, no strays.
    covered = {Path(PAGE_FILES[s]).name for s in slugs}
    assert {f for f in files if f != "1_Command_Center.py"} <= covered, "unslugged page files"


def test_app_registers_all_nav_pages_with_hidden_position():
    """app.py must own the full navigation registry with url_paths matching the
    nav slugs, and the stock st.navigation widget must be hidden (lib/ui/nav.py
    renders the rail + mobile bar instead)."""
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'position="hidden"' in src, "st.navigation must be position='hidden'"
    for slug, file in PAGE_FILES.items():
        assert f'"{file}"' in src, f"app.py must register {slug} -> {file}"
    assert 'url_path="command"' in src, "Command Center is the default page"


def _main_and_sidebar_md(at):
    main = [m.value for m in at.markdown]
    sidebar = [m.value for m in at.sidebar.markdown]
    return main, sidebar


@pytest.mark.parametrize("page_name,slug", STANDALONE)
def test_pages_render_empty_state_without_network(page_name, slug):
    """Each standalone page must not raise with no Command Center session, must
    render its navigation chrome (active badge + group labels of the rail), and
    must NOT emit any in-app route-relative anchor (audit fix: markdown anchors
    open a new browser tab and drop the session)."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "pages" / page_name))
    at.run(timeout=180)
    assert not at.exception, f"{page_name} raised: {at.exception}"
    main, sidebar = _main_and_sidebar_md(at)
    all_md = main + sidebar
    # active badge: the current slug is highlighted (mobile bar + rail)
    assert any("aria-current=\"page\"" in r for r in all_md), (
        f"{page_name} missing active nav badge"
    )
    # rail renders its group labels in the sidebar
    assert any("nb-group-label" in r for r in sidebar), f"{page_name} missing rail group labels"
    # NO in-app anchors anywhere (audit regression guard)
    for label, r in [("main", main), ("sidebar", sidebar)]:
        assert not any('href="../' in x for x in r), (
            f"{page_name} emits route-relative {label} anchors (would open new sessions)"
        )
    # honest no-data degradation
    assert any(EMPTY_STATE[slug] in r for r in main), (
        f"{page_name} missing empty-state sentinel {EMPTY_STATE[slug]!r}"
    )


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
    main, _sidebar = _main_and_sidebar_md(at)
    assert any("No news in this session yet" in r for r in main), \
        "Pulse must show its empty state without a session feed"
    assert not any('href="../' in r for r in main), "Pulse must not emit in-app anchors"


def test_decision_desk_starts_from_zero_without_command_center():
    """Decision Desk must not fabricate portfolio figures when the Command
    Center has not run — all monetary/allocation inputs start at zero (fix:
    default weights/monetary fields were hard-coded to 17/18/16/42/6 and a
    25.2Cr net worth, implying data that does not exist in an empty session)."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "pages" / "2_Deep_Health.py"))
    at.run(timeout=180)
    assert not at.exception, f"Decision Desk raised: {at.exception}"
    values = [n.value for n in at.number_input]
    assert values, "Decision Desk should expose its numeric inputs"
    assert all(v == 0 for v in values), (
        f"Decision Desk must start from 0.0 without a Command Center run, got {values}"
    )


def test_holdings_roster_builds_from_session_books_without_fallback():
    """Regression (audit fix): Holdings rebuilds its drill-down roster from the
    Command Center's published books via
    build_roster(mf_valid=..., stocks_valid=..., ...). The call-site must map the
    cc_books dict keys ("mf"/"stocks"/"gold"/"fd") onto those kwarg names —
    build_roster(**cc_books) raises TypeError (the signature is mf_valid/fd_valid),
    which the removed workbook _fallback_roster silently masked. Seeded with a
    minimal session, the roster must render and never fall back to no-data."""
    import pandas as pd
    from streamlit.testing.v1 import AppTest

    mf = pd.DataFrame([{
        "Owner": "Mrs. KAVITA KHANDELWAL", "Fund Name": "Franklin India Liquid Fund",
        "ISIN": "INF205K01734", "Category": "Liquid", "Symbol": "INF205K01734",
        "Current Value": 1000.0, "Invested": 950.0,
    }])
    stocks = pd.DataFrame([{
        "Owner": "Mr. RAJESH KUMAR", "Company Name": "Reliance Industries",
        "Symbol": "RELIANCE", "Exchange": "NSE",
        "Current Value": 200000.0, "Invested": 150000.0,
    }])
    gold = pd.DataFrame([{
        "Owner": "Mr. RAJESH KUMAR", "Symbol": "SGBSEP31II-GB",
        "Company Name": "SOVEREIGN GOLD BOND SEP31 II",
        "Current Value": 150000.0, "Invested": 100000.0,
    }])
    fd = pd.DataFrame([{
        "Account Number": "ABC123", "Holder Name": "Mr. RAJESH KUMAR",
        "Currency": "INR", "Product": "FD", "Deposit Date": "2024-01-01",
        "ROI %": 7.0, "Maturity Date": "2027-01-01", "Principal Amount": 100000.0,
        "Current Value (INR)": 110000.0, "Principal (INR, at deposit FX)": 100000.0,
    }])
    at = AppTest.from_file(str(ROOT / "pages" / "3_Asset_Detail.py"))
    at.session_state["cc_books"] = {"mf": mf, "stocks": stocks, "gold": gold, "fd": fd}
    at.run(timeout=180)
    assert not at.exception, f"Holdings raised: {at.exception}"
    main = [m.value for m in at.markdown]
    assert not any("No holdings to drill into" in r for r in main), (
        "Holdings must render its roster from the seeded session books "
        "(call-site kwarg regression)"
    )
    assert any("Command Center session data" in r for r in main), \
        "Holdings must credit the Command Center session"