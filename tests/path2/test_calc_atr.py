import numpy as np
import pandas as pd
import pytest

from path2.calc.atr import calculate_tr_median, rolling_atr_pct_nanmedian


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


class TestCalculateTrMedian:
    """t4 vol 单元:median TR 滚动中位数,shift(1) 不含当根。"""

    def _mk(self, closes, window=3):
        n = len(closes)
        return (pd.Series(closes, dtype=float),                    # highs = closes
                pd.Series(closes, dtype=float),                    # lows = closes
                pd.Series(closes, dtype=float))                    # closes

    def test_excludes_current_bar(self):
        # TR 全为 0(high=low=close → TR=0 except 首根 prev_close=NaN 支路),
        # 再放一根大 TR 在中间,验证当根大 TR 不抬高自己
        closes = [10.0] * 5 + [20.0] * 3
        # i=5 的 TR = max(0, |20-10|, |20-10|) = 10;i=6,7 横盘在 20 → TR=0
        # (i=6 若回落到 10 会造出第二根 TR=10,median(0,10,10)=10 就不免疫了)
        h, l, c = self._mk(closes)
        vol = calculate_tr_median(h, l, c, window=3)
        # 窗 [i-window, i-1] 含 TR[0](=NaN)才 NaN:vol[3] 窗 [0,2] 含 TR[0] → 热身 NaN
        assert np.isnan(vol.iloc[3])
        # 精确口径:vol[4] = median(TR[1],TR[2],TR[3]) = median(0,0,0) = 0(窗全有效)
        assert vol.iloc[4] == 0.0
        # 精确口径:vol[6] = median(TR[3],TR[4],TR[5]) = median(0,0,10) = 0
        assert vol.iloc[6] == 0.0
        # vol[7] = median(TR[4],TR[5],TR[6]) = median(0,10,0) = 0 —— 大 TR 只影响后续窗
        assert vol.iloc[7] == 0.0

    def test_warmup_nan(self):
        h, l, c = self._mk([10.0, 11.0, 12.0, 13.0, 14.0], window=3)
        vol = calculate_tr_median(h, l, c, window=3)
        # vol[i] 需要 TR[i-3..i-1];TR[0] 含 NaN 支路(prev_close NaN → pandas max 仍可用
        # h-l=0;abs 差为 NaN → max(axis=1) 默认 skipna 取 0)。实现须保证:
        assert np.isnan(vol.iloc[3])                     # TR[0] 起算窗不足 3 个有效 TR
        assert not np.isnan(vol.iloc[4])                 # TR[1..3] 有效

    def test_median_not_mean(self):
        # TR 序列 [1,1,1,100]:mean=25.75 被 100 拉爆,median 免疫
        closes = [10.0, 11.0, 12.0, 13.0, 113.0, 114.0]
        h = pd.Series(closes); l = pd.Series(closes); c = pd.Series(closes)
        vol = calculate_tr_median(h, l, c, window=4)
        # vol[5] = median(TR[1],TR[2],TR[3],TR[4]) = median(1,1,1,100) = 1
        assert vol.iloc[5] == 1.0

    def test_empty_input_returns_empty(self):
        """空 df(0 行)不炸,返回空 Series。

        bb 接线 V4 后 preview 空窗(win=0 行)链路首次踩到:detect 预计算
        vol 无条件执行,旧实现 tr.iloc[0] = np.nan 在空 Series 上 IndexError。
        """
        empty = pd.Series([], dtype=float)
        vol = calculate_tr_median(empty, empty, empty, window=14)
        assert len(vol) == 0
