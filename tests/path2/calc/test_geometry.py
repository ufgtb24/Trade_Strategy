import pytest

from path2.calc.geometry import upper_shadow_ratio, lower_shadow_ratio, body_pct


def test_upper_shadow_long():
    # open=10, close=10.5, high=12, low=9.8 → upper = (12 - 10.5) / (12 - 9.8) ≈ 0.68
    assert upper_shadow_ratio(10, 12, 9.8, 10.5) == pytest.approx((12 - 10.5) / (12 - 9.8))


def test_lower_shadow_long():
    # open=10, close=10.5, high=10.6, low=9 → lower = (10 - 9) / (10.6 - 9) ≈ 0.625
    assert lower_shadow_ratio(10, 10.6, 9, 10.5) == pytest.approx((10 - 9) / (10.6 - 9))


def test_body_pct():
    # |close - open| / (high - low)
    assert body_pct(10, 12, 9, 11) == pytest.approx(1.0 / 3.0)


def test_zero_range_no_div():
    assert upper_shadow_ratio(10, 10, 10, 10) == 0.0
    assert lower_shadow_ratio(10, 10, 10, 10) == 0.0
    assert body_pct(10, 10, 10, 10) == 0.0
