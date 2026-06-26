import numpy as np
import pandas as pd
import pytest

from path2.calc.recovery import calculate_dd_recov


def test_dd_recov_no_drawdown_is_zero():
    closes = pd.Series(np.linspace(10, 20, 300))
    dd = calculate_dd_recov(closes, lookback=252)
    # 全程上涨,峰=最新,trough=最新,drawdown=0
    assert dd.iloc[280] == pytest.approx(0.0)


def test_dd_recov_peak_at_best_recovery():
    # 构造:从 10 → 20(peak)→ 10(trough)→ 15(recovery=0.5)
    closes = pd.Series([10.0] * 50 + list(np.linspace(10, 20, 50)) + list(np.linspace(20, 10, 50)) + list(np.linspace(10, 15, 152)))
    dd = calculate_dd_recov(closes, lookback=252, best_recovery=0.25)
    # 末点 recovery = 0.5,峰值在 r=0.25;非 NaN
    assert not pd.isna(dd.iloc[-1])
    assert dd.iloc[-1] > 0


def test_dd_recov_warmup_nan():
    closes = pd.Series(np.linspace(10, 20, 100))
    dd = calculate_dd_recov(closes, lookback=252)
    # lookback 不足 → NaN(严格断言,防止"always 0.0"回归被掩盖)
    assert dd.iloc[:99].isna().all()


def test_dd_recov_first_valid_at_lookback_minus_1():
    # 第一个有效 bar 在 iloc[lookback - 1],前 lookback - 1 为 NaN
    closes = pd.Series(np.linspace(10, 20, 300))
    dd = calculate_dd_recov(closes, lookback=252)
    assert dd.iloc[:251].isna().all()
    # iloc[251] = iloc[lookback - 1] 应为非 NaN
    assert not pd.isna(dd.iloc[251])
