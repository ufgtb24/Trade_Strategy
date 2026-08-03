import numpy as np
import pandas as pd
import pytest

from path2.calc.atr import rolling_atr_pct_nanmedian


def _s(vals):
    return pd.Series(vals, dtype=float)


def test_rolling_atr_pct_nanmedian_constant_window():
    """恒定 TR/close=0.03、period=3 → 从第 3 个起 M=0.03(中位数=均值);前 2 个 NaN。"""
    # close 恒 100,high-low 恒 3(无跳空 → TR=high-low=3),TR/close=0.03
    highs = _s([103.0] * 6); lows = _s([100.0] * 6); closes = _s([100.0] * 6)
    m = rolling_atr_pct_nanmedian(highs, lows, closes, period=3)
    assert np.isnan(m.iloc[0]) and np.isnan(m.iloc[1])
    for i in range(2, 6):
        assert m.iloc[i] == pytest.approx(0.03)


def test_rolling_atr_pct_nanmedian_robust_to_outlier():
    """中位数扛异动:window 内一个 30% 异动不拉高 M(均值会被拉到 ~4%)。"""
    # 平时 TR/close=0.02,第 4 根跳空使 TR/close=0.30;period=5
    closes = _s([100.0] * 6)
    highs = _s([102.0, 102.0, 102.0, 130.0, 102.0, 102.0])
    lows = _s([100.0] * 6)
    m = rolling_atr_pct_nanmedian(highs, lows, closes, period=5)
    # [0..4] 窗(含异动 0.30)中位数 = 排序 [0.02,0.02,0.02,0.02,0.30] 中间 = 0.02
    assert m.iloc[4] == pytest.approx(0.02)
    # 均值法会是 (0.02*4+0.30)/5=0.076;中位数 0.02 → 证明鲁棒
    assert m.iloc[4] < 0.03


def test_rolling_atr_pct_nanmedian_too_short_all_nan():
    """len < period → 全 NaN。"""
    m = rolling_atr_pct_nanmedian(_s([102.0, 101.0]), _s([100.0, 100.0]), _s([100.0, 100.0]), period=5)
    assert m.isna().all()
