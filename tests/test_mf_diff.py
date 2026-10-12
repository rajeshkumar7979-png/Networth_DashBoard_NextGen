from lib.mf_diff import diff_snapshots


def test_diff_reports_add_exit_and_weight_without_calling_it_a_trade():
    prior = [
        {"isin": "INE018A01030", "name": "Larsen", "weight_pct": 8.0, "quantity": 100},
        {"isin": "INE002A01018", "name": "Reliance", "weight_pct": 5.0, "quantity": 50},
    ]
    current = [
        {"isin": "INE018A01030", "name": "Larsen", "weight_pct": 8.7, "quantity": 100},
        {"isin": "INE040A01034", "name": "HDFC Bank", "weight_pct": 4.0, "quantity": 20},
    ]
    out = diff_snapshots(prior, current)
    assert out["status"] == "VALID"
    assert out["added"][0]["name"] == "HDFC Bank"
    assert out["exited"][0]["name"] == "Reliance"
    assert out["changed"][0]["weight_from"] == 8.0
    assert "not proof" in out["changed"][0]["weight_note"]
    assert "quantity_from" not in out["changed"][0]


def test_missing_quantity_is_not_treated_as_zero():
    prior = [{"isin": "INE018A01030", "name": "Larsen", "weight_pct": 8.0}]
    current = [{"isin": "INE018A01030", "name": "Larsen", "weight_pct": 8.0, "quantity": 10}]
    out = diff_snapshots(prior, current)
    assert out["changed"] == []


def test_failed_snapshot_is_not_comparable():
    out = diff_snapshots([{"isin": "INE018A01030", "name": "Larsen"}], [], current_ok=False)
    assert out["status"] == "NOT_COMPARABLE"
