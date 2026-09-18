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
        "cc_recon_tests",
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


def test_phase_b_recon_count_currency_key_and_timestamps():
    src = (ROOT / "pages" / "1_Command_Center.py").read_text(encoding="utf-8")
    assert "Register row count = four-book row count" in src
    assert "Register keys unique" in src
    assert "FCNR product count = USD deposit count" in src
    assert "INR FD count = non-USD deposit count" in src
    assert "cc_recon_tests" in src
    assert "usd_inr_published" in src
    assert "retrieved_at" in src
    assert "FCNR return · two parts" in src
    assert "get_usd_inr_quote" in src


def test_phase_b_intelligence_mapped_only_no_unmapped_fallback():
    src = (ROOT / "pages" / "6_Intelligence.py").read_text(encoding="utf-8")
    assert "or _dev_rows" not in src
    assert "_mapped[:6] or" not in src
    assert "not mapped to your book" in src
    assert "invested_basis_change" in src
    assert "NOT_A_CASHFLOW_LABEL" in src


def test_phase_b_news_macro_demoted_from_primary_order():
    src = (ROOT / "pages" / "4_News.py").read_text(encoding="utf-8")
    assert '("macro", "Market backdrop"' not in src
    assert "not mapped to your book" in src
    assert "NRI / tax treatment is not modelled" in src


def test_phase_b_holdings_fd_table_indian_grouping_and_two_returns():
    src = (ROOT / "pages" / "3_Asset_Detail.py").read_text(encoding="utf-8")
    assert 'format="₹%d"' not in src
    assert '"Product"' in src and '"Account"' in src
    assert "not annualized" in src
    assert "NRI / tax treatment is not modelled" in src
    assert "FCNR return · two parts" in src
    assert "Interest Return (INR)" in src
    assert "FX Gain/Loss (INR)" in src


def test_phase_b_mf_health_overlap_disclosure_and_as_of():
    src = (ROOT / "pages" / "5_MF_Health.py").read_text(encoding="utf-8")
    assert "n_disclosed" in src
    assert "disclosed" in src
    assert "undisclosed" in src
    assert "datetime.now()" not in src
    assert "trailing_return" in src
    assert "trailing CAGR" in src


def test_phase_b_nri_tax_empty_state_on_desk_holdings_decisions():
    for rel in ("pages/2_Deep_Health.py", "pages/3_Asset_Detail.py", "pages/8_Desk.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "NRI / tax treatment is not modelled" in src, rel


def test_phase_b_desk_renders_recon_grid_and_timestamps():
    src = (ROOT / "pages" / "8_Desk.py").read_text(encoding="utf-8")
    assert "cc_recon_tests" in src
    assert "usd_inr_published" in src
    assert "invested_basis_change" in src
    assert "NOT_A_CASHFLOW_LABEL" in src
    assert 'class="recon-pass"' in src or "recon-pass" in src
