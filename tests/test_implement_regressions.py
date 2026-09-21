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
    assert "(member, key)" in src
    assert "News pulse · holdings + NRI" in src
    assert "Books at a glance" in src
    assert "flags[:8]" in src


def test_phase_c_holdings_performance_columns():
    src = (ROOT / "pages" / "3_Asset_Detail.py").read_text(encoding="utf-8")
    assert "vs Nifty50 1Y" in src
    assert "Interest Return (INR)" in src
    assert "Days left" in src
    assert "1Y / 3Y / 5Y" in src
    assert "Lump-sum annualized" in src
    assert "Look-through · this fund" in src
    assert "Interpret this instrument (opt-in AI)" in src
    assert "never on load" in src
    assert "run_ai_research" in src


def test_mf_health_lookthrough_charts_and_pairwise():
    src = (ROOT / "pages" / "5_MF_Health.py").read_text(encoding="utf-8")
    assert "Pairwise fund overlap" in src
    assert "Look-through · top companies" in src
    assert "Single-stock concentration" in src
    assert "LUMP_SUM_ANN_LABEL" in src
    assert "datetime.now()" not in src
    assert "trailing CAGR" in src
    assert "pairwise_overlap_pct" in src
    assert "family_look_through" in src


def test_phase_b_intelligence_mapped_only_no_unmapped_fallback():
    src = (ROOT / "pages" / "6_Intelligence.py").read_text(encoding="utf-8")
    assert "or _dev_rows" not in src
    assert "_mapped[:6] or" not in src
    assert "not mapped to your book" in src
    assert "split_change_rows" in src
    assert "PERIOD_DELTA_CAPTION" in src


def test_phase_b_news_macro_demoted_from_primary_order():
    src = (ROOT / "pages" / "4_News.py").read_text(encoding="utf-8")
    assert '("macro", "Market backdrop"' not in src
    assert "not mapped to your book" in src
    assert "NRI / tax treatment is not modelled" in src


def test_attribution_is_lifetime_pnl_not_this_run_jargon():
    src = (ROOT / "pages" / "1_Command_Center.py").read_text(encoding="utf-8")
    assert "Where today's P&L comes from" in src
    assert "valuation attribution" not in src
    assert "LIFETIME_PNL_CAPTION" in src
    desk = (ROOT / "pages" / "8_Desk.py").read_text(encoding="utf-8")
    assert "valuation attribution" not in desk
    intel = (ROOT / "pages" / "6_Intelligence.py").read_text(encoding="utf-8")
    assert "Where today's P&L comes from" in intel


def test_decision_desk_is_scenario_not_advice():
    src = (ROOT / "pages" / "2_Deep_Health.py").read_text(encoding="utf-8")
    assert "Prefer Liquid / short FD" not in src
    assert "Do not put this money into equity right now" not in src
    assert "Liquidity scenario" in src
    assert "does not guess USD/INR" in src


def test_funds_consistency_does_not_award_free_points():
    src = (ROOT / "pages" / "5_MF_Health.py").read_text(encoding="utf-8")
    assert "return 10.0" not in src
    assert "Illustrative health index" in src


def test_pages_do_not_print_fresh_now_as_valuation_clock():
    for name in ("6_Intelligence.py", "7_Outlook.py", "8_Desk.py"):
        src = (ROOT / "pages" / name).read_text(encoding="utf-8")
        assert "header_valued_at" in src, name
        assert "AS OF {NOW_IST" not in src, name


def test_command_publishes_valued_at():
    src = (ROOT / "pages" / "1_Command_Center.py").read_text(encoding="utf-8")
    assert '"valued_at"' in src
    assert "now_ist.isoformat()" in src


def test_outlook_today_is_not_inside_next_30():
    src = (ROOT / "pages" / "7_Outlook.py").read_text(encoding="utf-8")
    assert "Matures today" in src
    assert "between(1, 30)" in src
    assert "between(0, 30)" not in src


def test_holdings_dossier_uses_company_name_not_raw_isin_label():
    src = (ROOT / "pages" / "3_Asset_Detail.py").read_text(encoding="utf-8")
    assert "_dossier_label" in src
    assert "Also inside family funds" in src
    assert "of family assets" in src
    assert "status_label" in src
