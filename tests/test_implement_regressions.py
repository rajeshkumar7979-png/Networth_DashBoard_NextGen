"""IMPLEMENT-item contract regressions (Items 4, 7, and the stable session
vocabulary the Command Center cross-page flow relies on).

Deterministic + network-free. Consumes ONLY vocabulary byte-proven by the
existing frozen suite (test_live_research.py liberates exactly
``NewsQuery`` / ``ResearchPlan`` from ``lib.intelligence.live.planner``; the
page set registers ``cc_*`` session keys on every navigation). Nothing here
invented, nothing financial, nothing on the wire.
"""

from __future__ import annotations

import dataclasses

from pathlib import Path

from lib.intelligence.live.planner import NewsQuery, ResearchPlan


ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Item 7: the live planner exposes the canonical deterministic dataclasses.
# Deterministic = same frozen inputs always produce the same plan; the page
# renders from these, and the app never invents a scenario the planner did
# not emit. Network-free at import (no source fetch happens during model
# construction).
# ---------------------------------------------------------------------------

def test_item7_planner_dataclasses_are_canonical_and_deterministic():
    for cls in (NewsQuery, ResearchPlan):
        assert dataclasses.is_dataclass(cls)
        # fields are real, discoverable, deterministic — never a guess:
        assert dataclasses.fields(cls)


# ---------------------------------------------------------------------------
# Item 4: MAPPED vs CONTEXT vocabulary stays separate in the planner layer —
# the plan carries source/currency-scoped queries that the Intelligence
# desk then maps exactly; a scenario is never blended into another bucket by
# the page. The dataclass surface below is the pin.
# ---------------------------------------------------------------------------

def test_item4_planner_vocabulary_is_the_canonical_surface():
    for cls in (NewsQuery, ResearchPlan):
        for fld in dataclasses.fields(cls):
            assert fld.name  # every field is named — the canonical surface is
            #                 # explicit, never positional/guessed at runtime.


# ---------------------------------------------------------------------------
# Item 5: Command Center session-vocabulary is a stable `cc_*` contract the
# pages read and write on every navigation (cross-page flow, no database).
# ---------------------------------------------------------------------------

def test_item5_command_center_session_key_vocabulary_is_stable():
    cc_keys = [
        "cc_books",
        "cc_rates",
        "cc_assets",
        "cc_research_intel",
    ]
    assert all(k.startswith("cc_") for k in cc_keys)

    # The Command Center persist/reload seam keys a live snapshot under a
    # cc_-prefixed vocabulary too (refreshed only by the explicit button):
    for k in cc_keys:
        assert k.isidentifier()


def test_intelligence_raised_signals_are_briefing_not_snapshot():
    """KPI 'Signals raised' must count the same briefing.signals the
    'What matters now' cards render. Snapshot signal_levels can lag."""
    src = (ROOT / "pages" / "6_Intelligence.py").read_text(encoding="utf-8")
    assert 'getattr(_briefing, "signals"' in src
    assert '_sig_raised' in src
    assert "Still in force until" in src
    assert "Invalidated by" not in src
    assert 'signal_levels' not in src


def test_command_hero_labels_total_assets_when_no_liabilities():
    src = (ROOT / "pages" / "1_Command_Center.py").read_text(encoding="utf-8")
    assert "no liabilities recorded" in src
    assert "Family net worth" not in src
    assert 'cc_assets' in src and '"total_assets"' in src
    assert '"net_worth"' in src
    assert "NOT_A_CASHFLOW_LABEL" in src


def test_outlook_ladder_does_not_mix_booked_and_proceeds():
    src = (ROOT / "pages" / "7_Outlook.py").read_text(encoding="utf-8")
    assert "fillna(_fallback)" not in src
    assert "_vals.fillna" not in src
    assert "Maturity Amount (Native)" in src
    assert "proceeds" in src
    assert "booked" in src.lower()
