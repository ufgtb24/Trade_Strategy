import numpy as np
import pandas as pd
import pytest

from path2.calc.ma import (
    calculate_ma,
    calculate_ma_pos,
    calculate_ma_z_atr,
    calculate_ma_curve,
    calculate_ma_slope,
)


def test_ma_simple():
    closes = pd.Series([1.0, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    ma = calculate_ma(closes, period=3)
    assert ma.iloc[:2].isna().all()
    assert ma.iloc[2] == pytest.approx(2.0)
    assert ma.iloc[9] == pytest.approx(9.0)


def test_ma_pos():
    closes = pd.Series([10.0] * 10 + [11.0] * 10)
    ma_pos = calculate_ma_pos(closes, period=10)
    # at idx 15, MA10 window = closes[6..15] = 4*10 + 6*11, mean = 10.6
    ma_15 = (10 * 4 + 11 * 6) / 10
    assert ma_pos.iloc[15] == pytest.approx((11.0 - ma_15) / ma_15, rel=1e-3)


def test_ma_z_atr():
    closes = pd.Series(np.linspace(10, 12, 20))
    atr = pd.Series([0.5] * 20)
    z = calculate_ma_z_atr(closes, atr, period=5)
    # 仅 sanity check:无 NaN(对应 period+1 之后)
    assert not z.iloc[6:].isna().any()


def test_ma_curve_positive_when_accelerating_up():
    # 加速上行:MA 二阶差分应为正
    closes = pd.Series([10 + i * i * 0.01 for i in range(50)])
    curve = calculate_ma_curve(closes, period=10, stride=5)
    assert curve.iloc[40] > 0


def test_ma_slope_normalized():
    # 每 bar MA 涨 1%:slope ≈ 0.01 (per-bar)
    ma = pd.Series([100 * (1.01 ** i) for i in range(40)])
    slope = calculate_ma_slope(ma, lookback=20)
    # (ma[20] - ma[0]) / ma[0] / 20 ≈ (1.01^20 - 1) / 20 ≈ 0.01
    assert slope.iloc[20] == pytest.approx(0.01, abs=2e-3)
