import pytest

from lib.ledger import net_worth


def test_zero_liability_equals_total_assets_exactly():
    # Net Worth = Total Assets - Total Liabilities; zero liabilities -> parity.
    for assets in (0.0, 25342848.288211264, 12345.678):
        out = net_worth(assets)
        assert out["net_worth"] == assets
        assert out["total_assets"] == assets
        assert out["total_liabilities"] == 0.0
        assert out["has_liabilities"] is False
        # exact within the pinned ₹0.01 parity tolerance
        assert abs(out["net_worth"] - assets) < 0.01


def test_explicit_zero_liabilities_matches_none():
    a = net_worth(1000000.0)
    b = net_worth(1000000.0, 0)
    c = net_worth(1000000.0, 0.0)
    assert a == b == c
    assert b["net_worth"] == 1000000.0
    assert b["has_liabilities"] is False


def test_liabilities_subtracted_exactly():
    out = net_worth(25342848.288211264, 5000000.0)
    assert out["net_worth"] == pytest.approx(20342848.288211264, abs=0.01)
    assert out["total_liabilities"] == 5000000.0
    assert out["total_assets"] == 25342848.288211264
    assert out["has_liabilities"] is True


def test_has_liabilities_only_when_positive():
    assert net_worth(100, 0.0001)["has_liabilities"] is True
    assert net_worth(100, 0.0)["has_liabilities"] is False
    assert net_worth(100)["has_liabilities"] is False


def test_assets_required_finite():
    with pytest.raises(ValueError):
        net_worth(None)
    with pytest.raises(ValueError):
        net_worth(float("nan"))
    with pytest.raises(ValueError):
        net_worth(float("inf"))


def test_liabilities_must_be_finite_and_non_negative():
    with pytest.raises(ValueError):
        net_worth(100, -1.0)
    with pytest.raises(ValueError):
        net_worth(100, float("nan"))
    with pytest.raises(ValueError):
        net_worth(100, float("inf"))