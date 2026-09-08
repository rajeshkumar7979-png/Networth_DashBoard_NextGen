from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

APP = Path(__file__).resolve().parents[1] / "app.py"


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