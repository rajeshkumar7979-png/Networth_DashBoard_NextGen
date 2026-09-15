from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

APP = Path(__file__).resolve().parents[1] / "app.py"


def _rendered(at):
    """Full rendered markdown of a page: main element tree + the sidebar rail."""
    main = [m.value for m in at.markdown]
    sidebar = [m.value for m in at.sidebar.markdown]
    return main, sidebar


def _assert_nav_chrome(at, label):
    """Every page, when driven from the real app.py (st.navigation registered),
    must render the shared rail with the current page's active badge, in the
    real sidebar — and must NOT emit any in-app route-relative anchor anywhere.

    Audit gate: Streamlit rewrites st.markdown anchors to target="_blank"
    (new tab = fresh websocket session = all cc_* state lost). In-app
    navigation is st.page_link (same-session client route), so no rendered
    markdown may contain href="../" — the regression guard for the exact
    defect this audit fixed.
    """
    main, sidebar = _rendered(at)
    all_md = main + sidebar
    assert any("aria-current=\"page\"" in r for r in all_md), (
        f"{label} missing active nav badge"
    )
    assert any("nb-group-label" in r for r in sidebar), f"{label} missing rail group labels"
    assert any("nb-brand" in r for r in sidebar), f"{label} missing brand rail"
    for source, r in (("main", main), ("sidebar", sidebar)):
        assert not any('href="../' in x for x in r), (
            f"{label} emits route-relative {source} anchors (would drop the session)"
        )


@pytest.mark.skipif(not APP.exists(), reason="app.py missing")
def test_command_center_renders_without_exception():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP))
    at.run(timeout=240)
    assert not at.exception, f"unexpected exception: {at.exception}"
    assert "cc_equity_pct" in at.session_state, "Command Center did not populate session state"
    # Phase 1A twin-run gate: on this live run the canonical asset register (built from
    # the page's own books) must reconcile to the page totals within the ₹1 tolerance.
    rendered = [m.value for m in at.markdown]
    assert any("Asset register total = portfolio total" in r for r in rendered), "register reconciliation missing"
    assert any("Asset register invested = invested capital" in r for r in rendered), "register reconciliation missing"
    assert not any("✗ FAIL" in r for r in rendered), "reconciliation FAILED on live run:\n" + "\n".join(
        r for r in rendered if "✗ FAIL" in r
    )
    # Phase 1B gate: P&L drivers section, three recon entries, cashflow label.
    assert any("Register class P&L sums to Total P&L" in r for r in rendered), "driver recon missing"
    assert any("FD drivers reconcile to FD class P&L" in r for r in rendered), "FD driver recon missing"
    assert any("Total drivers reconcile to Total P&L" in r for r in rendered), "total driver recon missing"
    assert any("NOT a cash-flow measurement" in r for r in rendered), "cashflow label missing"
    # Phase 1B delta block present.
    assert any("Snapshot delta" in r or "snapshot delta" in r for r in rendered), "delta section missing"
    # Level-structure gate (executive-brief hierarchy restructure): the three
    # information-hierarchy sections must render as literal markdown. Empirical note:
    # AppTest's at.markdown DOES surface st.markdown calls made inside expanders; only
    # expander labels and st.caption are not surfaced, hence the session-state gate below
    # for the research brief (whose full readout lives inside the Level-5 expander).
    assert any("What deserves attention" in r for r in rendered), "attention section missing"
    assert any("What changed this run" in r for r in rendered), "changed section missing"
    assert any("Research brief · synthesis" in r for r in rendered), "research brief section missing"
    # Navigation contract (audit fix): CC must render the rail in the sidebar and
    # emit no in-app ../ anchors (its drill row is now st.page_link, so its five
    # drill hooks stay inside the session) — see _assert_nav_chrome.
    _assert_nav_chrome(at, "Command Center")
    # Research & Synthesis + portfolio-aware live-research panel actually rendered.
    # cc_research_brief is set only on success inside the research try-block (which
    # derives the live plan + cached cohort), so a None here means the block was
    # silently swallowed by its except.
    if "cc_research_brief" in at.session_state:
        research_brief = at.session_state["cc_research_brief"]
    else:
        research_brief = None
    assert research_brief is not None, "research brief missing"
    if "cc_ai_outcome" in at.session_state:
        ai_outcome = at.session_state["cc_ai_outcome"]
    else:
        ai_outcome = None
    assert ai_outcome is None, "AI research must not auto-run on page load"


def test_all_pages_render_after_command_center_run():
    """Owning the full product shell: after one Command Center run, every page
    in the custom navigation must render without exception from the same
    session (no page re-runs that computation or the network), carry the shared
    rail with its own active badge, and show CONTENT (never an empty state) —
    the cross-page session flow must actually deliver data."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP))
    at.run(timeout=300)
    assert not at.exception, f"Command Center raised: {at.exception}"
    assert "cc_books" in at.session_state, "Command Center did not publish books"

    orders = [
        ("pages/2_Deep_Health.py", "decisions", "Decision Desk"),
        ("pages/3_Asset_Detail.py", "holdings", "Holdings"),
        ("pages/4_News.py", "pulse", "Pulse"),
        ("pages/5_MF_Health.py", "funds", "Funds"),
        ("pages/6_Intelligence.py", "intelligence", "Intelligence"),
        ("pages/7_Outlook.py", "outlook", "Outlook"),
        ("pages/8_Desk.py", "desk", "Desk"),
    ]
    for page, slug, label in orders:
        at.switch_page(page).run(timeout=180)
        assert not at.exception, f"{label} ({page}) raised: {at.exception}"
        main, sidebar = _rendered(at)
        _assert_nav_chrome(at, label)
        assert any("Northline · Family desk" in r for r in main), f"{label} missing page header"
        # Desktop reconciliation gate (register rebuilt from the same books): with the
        # Command Center's session state present the gate must run and PASS (fix: the
        # register total key is total_assets, not "Current Value"). Match the CSS class
        # token, not the literal "✗ FAIL", because the page's own explanatory caption
        # quotes that phrase.
        if slug == "desk":
            assert any('class="recon-pass"' in r for r in main), \
                "Desk reconciliation must PASS after a Command Center run"
            assert any("register total" in r for r in main), "Desk reconciliation block missing"
            assert not any('class="recon-fail"' in r for r in main), "Desk reconciliation FAILED on live run"
        # Cross-page session flow: each page must be fed real data from the
        # Command Center run — never the honest no-data empty state.
        if slug == "holdings":
            assert not any("No holdings to drill into" in r for r in main), (
                "Holdings must be populated after a Command Center run (fallback roster removed)"
            )
            assert any("Command Center session data" in r for r in main), (
                "Holdings must state its source is the Command Center session"
            )
        elif slug == "funds":
            assert not any("Open the Command Center once so your funds" in r for r in main), (
                "Funds must analyze the session MF book after a Command Center run"
            )
        elif slug == "intelligence":
            assert not any("Intelligence hasn't been computed in this session yet." in r for r in main), (
                "Intelligence must render the computed briefing after a Command Center run"
            )
        elif slug == "pulse":
            assert not any("No news in this session yet" in r for r in main), (
                "Pulse must render the session news feed after a Command Center run"
            )
        elif slug == "outlook":
            assert not any("No FD book in this session yet." in r for r in main), (
                "Outlook must render the maturity ladder after a Command Center run"
            )
        elif slug == "decisions":
            values = [n.value for n in at.number_input]
            assert any(v and v > 0 for v in values), (
                "Decision Desk must arrive pre-filled from the Command Center run"
            )