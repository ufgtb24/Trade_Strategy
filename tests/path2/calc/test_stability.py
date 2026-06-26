import pandas as pd
import pytest

from path2.calc.stability import calculate_stability


def test_stability_all_above_peak():
    lows = pd.Series([10.5] * 20)  # 全程不跌破 peak=10
    s = calculate_stability(lows, peak_idx=5, peak_price=10.0, lookforward=10)
    assert s == pytest.approx(1.0)


def test_stability_all_below_peak():
    lows = pd.Series([9.0] * 20)
    s = calculate_stability(lows, peak_idx=5, peak_price=10.0, lookforward=10)
    assert s == pytest.approx(0.0)


def test_stability_half():
    lows = pd.Series([9.0] * 5 + [11.0] * 5 + [9.0] * 5 + [11.0] * 5)
    s = calculate_stability(lows, peak_idx=0, peak_price=10.0, lookforward=10)
    # 0..9 (10 bar):lows = [9,9,9,9,9,11,11,11,11,11];不跌破比例 = 5/10 = 0.5
    assert s == pytest.approx(0.5)
