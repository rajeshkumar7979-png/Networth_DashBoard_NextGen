# -------------------------------------------------
# Phase 1B snapshot module tests.
# Uses temp files so data/ is never touched.
# -------------------------------------------------
from pathlib import Path

import pandas as pd
import pytest

from lib.snapshot import (
    BASE_COLS,
    SCHEMA,
    build_snapshot_row,
    clean,
    load_history,
    merge_uploaded,
    upsert_snapshot,
)


# ── build_snapshot_row ───────────────────────────────────────────────────────

class TestBuildSnapshotRow:
    def test_base_columns(self):
        row = build_snapshot_row(date="2026-01-01", net_worth=1000, equity_pct=20.0,
                                 fd_pct=50.0, pnl=50.0, health_score=65.5)
        assert row["date"] == "2026-01-01"
        assert row["net_worth"] == 1000.0
        assert row["equity_pct"] == 20.0
        assert row["fd_pct"] == 50.0
        assert row["pnl"] == 50.0
        assert row["health_score"] == 65.5
        assert row["schema"] == SCHEMA

    def test_enriched_scalars(self):
        row = build_snapshot_row(date="2026-01-01", net_worth=1000, equity_pct=20.0,
                                 fd_pct=50.0, pnl=50.0, health_score=65.0,
                                 total_invested=900.0, usd_inr=94.5)
        assert row["total_invested"] == 900.0
        assert row["usd_inr"] == 94.5

    def test_none_scalars_omitted(self):
        row = build_snapshot_row(date="2026-01-01", net_worth=1000, equity_pct=20.0,
                                 fd_pct=50.0, pnl=50.0, health_score=65.0)
        assert "total_invested" not in row
        assert "usd_inr" not in row

    def test_class_columns(self):
        cur = {"Equity": 100.0, "Liquid": 200.0}
        inv = {"Equity": 80.0, "Liquid": 190.0}
        row = build_snapshot_row(date="2026-01-01", net_worth=1000, equity_pct=10.0,
                                 fd_pct=20.0, pnl=30.0, health_score=70.0,
                                 class_current=cur, class_invested=inv)
        assert row["class_current_equity"] == 100.0
        assert row["class_invested_equity"] == 80.0
        assert row["class_current_liquid"] == 200.0
        # FCNR not provided, should be absent
        assert "class_current_fcnr_usd" not in row

    def test_member_columns(self):
        row = build_snapshot_row(date="2026-01-01", net_worth=1000, equity_pct=10.0,
                                 fd_pct=20.0, pnl=30.0, health_score=70.0,
                                 member_current={"Mr. RAJESH KUMAR": 500.0},
                                 member_invested={"Mr. RAJESH KUMAR": 400.0})
        assert row["member_current_mr_rajesh_kumar"] == 500.0
        assert row["member_invested_mr_rajesh_kumar"] == 400.0


# ── clean ────────────────────────────────────────────────────────────────────

class TestClean:
    def test_empty_df(self):
        result = clean(pd.DataFrame())
        assert result.empty
        assert list(result.columns) == BASE_COLS

    def test_none(self):
        result = clean(None)
        assert result.empty

    def test_filters_bad_dates(self):
        df = pd.DataFrame({"date": ["2026-01-01", "bad-date", "2026-01-03"],
                           "net_worth": [100, 200, 300]})
        result = clean(df)
        assert len(result) == 2

    def test_deduplicates_last_per_date(self):
        df = pd.DataFrame({"date": ["2026-01-01", "2026-01-01"],
                           "net_worth": [100, 200]})
        result = clean(df)
        assert len(result) == 1
        assert result.iloc[0]["net_worth"] == 200.0

    def test_sorted_by_date(self):
        df = pd.DataFrame({"date": ["2026-01-03", "2026-01-01"],
                           "net_worth": [300, 100]})
        result = clean(df)
        assert result.iloc[0]["date"] == "2026-01-01"

    def test_enriched_columns_pass_through(self):
        df = pd.DataFrame({
            "date": ["2026-01-01"], "net_worth": [1000],
            "equity_pct": [20.0], "fd_pct": [50.0],
            "pnl": [50.0], "health_score": [65.0],
            "class_current_equity": [200.0],
        })
        result = clean(df)
        assert "class_current_equity" in result.columns
        assert result.iloc[0]["class_current_equity"] == 200.0


# ── load_history / upsert_snapshot ───────────────────────────────────────────

class TestLoadAndUpsert:
    def test_load_missing_file(self):
        result = load_history(Path("nonexistent_file.csv"))
        assert result.empty

    def test_upsert_creates_file(self, tmp_path):
        csv_path = tmp_path / "test_history.csv"
        row = build_snapshot_row(date="2026-01-01", net_worth=1000, equity_pct=20.0,
                                 fd_pct=50.0, pnl=50.0, health_score=65.0)
        result = upsert_snapshot(row, csv_path)
        assert len(result) == 1
        assert csv_path.exists()

    def test_upsert_replaces_same_date(self, tmp_path):
        csv_path = tmp_path / "test_history.csv"
        row1 = build_snapshot_row(date="2026-01-01", net_worth=1000, equity_pct=20.0,
                                  fd_pct=50.0, pnl=50.0, health_score=65.0)
        row2 = build_snapshot_row(date="2026-01-01", net_worth=1100, equity_pct=22.0,
                                  fd_pct=48.0, pnl=55.0, health_score=66.0)
        upsert_snapshot(row1, csv_path)
        result = upsert_snapshot(row2, csv_path)
        assert len(result) == 1
        assert result.iloc[0]["net_worth"] == 1100.0

    def test_upsert_preserves_other_dates(self, tmp_path):
        csv_path = tmp_path / "test_history.csv"
        row1 = build_snapshot_row(date="2026-01-01", net_worth=1000, equity_pct=20.0,
                                  fd_pct=50.0, pnl=50.0, health_score=65.0)
        row2 = build_snapshot_row(date="2026-01-02", net_worth=1100, equity_pct=22.0,
                                  fd_pct=48.0, pnl=55.0, health_score=66.0)
        upsert_snapshot(row1, csv_path)
        result = upsert_snapshot(row2, csv_path)
        assert len(result) == 2


# ── merge_uploaded ───────────────────────────────────────────────────────────

class TestMergeUploaded:
    def test_merge_valid(self, tmp_path):
        csv_path = tmp_path / "test_history.csv"
        row = build_snapshot_row(date="2026-01-01", net_worth=1000, equity_pct=20.0,
                                 fd_pct=50.0, pnl=50.0, health_score=65.0)
        upsert_snapshot(row, csv_path)
        incoming = pd.DataFrame({"date": ["2026-01-02"], "net_worth": [1200]})
        result = merge_uploaded(incoming, csv_path)
        assert len(result) == 2

    def test_merge_missing_columns(self, tmp_path):
        csv_path = tmp_path / "test_history.csv"
        incoming = pd.DataFrame({"date": ["2026-01-01"]})
        with pytest.raises(ValueError, match="at least date and net_worth"):
            merge_uploaded(incoming, csv_path)


# ── _slugify ─────────────────────────────────────────────────────────────────

class TestSlugify:
    def test_basic(self):
        from lib.snapshot import _slugify
        assert _slugify("Mr. RAJESH KUMAR") == "mr_rajesh_kumar"

    def test_empty(self):
        from lib.snapshot import _slugify
        assert _slugify("") == "member"


# ── member slug collisions ───────────────────────────────────────────────────

class TestMemberSlugCollision:
    def _row(self, member_current, member_invested):
        return build_snapshot_row(
            date="2026-01-01", net_worth=1000, equity_pct=20.0,
            fd_pct=50.0, pnl=50.0, health_score=65.0,
            member_current=member_current, member_invested=member_invested,
        )

    def test_distinct_members_keep_readable_slugs(self):
        row = self._row({"Mr. Janak Khandelwal": 100.0},
                        {"Mr. Janak Khandelwal": 90.0})
        assert "member_current_mr_janak_khandelwal" in row
        assert "member_invested_mr_janak_khandelwal" in row

    def test_collision_preserves_both_members(self):
        """A-B and A B collide on the readable slug; both must survive."""
        member_current = {"A-B": 100.0, "A B": 200.0}
        member_invested = {"A-B": 90.0, "A B": 180.0}
        row = self._row(member_current, member_invested)
        # Both a_member_current_* keys are present with their own values.
        cur_keys = [k for k in row if k.startswith("member_current_")]
        assert len(cur_keys) == 2, cur_keys
        # Values survive (not overwritten): one of them is 200.0, the other 100.0.
        cur_vals = {row[k] for k in cur_keys}
        assert cur_vals == {100.0, 200.0}
        inv_keys = [k for k in row if k.startswith("member_invested_")]
        assert len(inv_keys) == 2, inv_keys
        inv_vals = {row[k] for k in inv_keys}
        assert inv_vals == {90.0, 180.0}
        # current and invested disambiguate consistently (same slug per member).
        for cur_k, inv_k in zip(sorted(cur_keys), sorted(inv_keys)):
            assert cur_k.replace("member_current_", "") == inv_k.replace("member_invested_", "")

    def test_deterministic_output(self):
        """Same inputs produce the same column names every run."""
        member_current = {"A-B": 1.0, "A B": 2.0}
        r1 = self._row(member_current, {k: v for k, v in member_current.items()})
        r2 = self._row(member_current, {k: v for k, v in member_current.items()})
        cur_keys1 = {k: v for k, v in r1.items() if k.startswith("member_current_")}
        cur_keys2 = {k: v for k, v in r2.items() if k.startswith("member_current_")}
        assert cur_keys1 == cur_keys2

    def test_case_only_collision_preserves_both(self):
        row = self._row({"Mr. Rajesh Kumar": 300.0, "Mr. RAJESH KUMAR": 400.0},
                        {"Mr. Rajesh Kumar": 280.0, "Mr. RAJESH KUMAR": 380.0})
        cur_vals = {row[k] for k in row if k.startswith("member_current_")}
        assert cur_vals == {300.0, 400.0}
