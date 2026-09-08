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