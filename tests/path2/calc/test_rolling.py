import pandas as pd
import pytest

from path2.calc.rolling import rolling_range_pct, rolling_std_pct


def test_range_pct_constant_range():
    highs = pd.Series([11.0] * 20)
    lows = pd.Series([10.0] * 20)
    r = rolling_range_pct(highs, lows, period=5)
    # (11-10)/10 = 0.1
    assert r.iloc[10] == pytest.approx(0.1)


def test_std_pct_zero():
    closes = pd.Series([10.0] * 20)
    s = rolling_std_pct(closes, period=5)
    assert s.iloc[10] == pytest.approx(0.0)


def test_range_pct_warmup_nan():
    highs = pd.Series([11.0] * 20)
    lows = pd.Series([10.0] * 20)
    r = rolling_range_pct(highs, lows, period=5)
    assert r.iloc[:4].isna().all()


def test_rolling_range_pct_zero_low_gives_nan():
    # rolling min(lows) 为 0 时,商应为 NaN(不是 inf)
    highs = pd.Series([10.0] * 20)
    lows = pd.Series([0.0] * 5 + [5.0] * 15)
    result = rolling_range_pct(highs, lows, period=5)
    # 前 5 个 bar 的 rolling min(lows) = 0 → NaN
    assert pd.isna(result.iloc[4])
    # 之后 rolling min(lows) > 0 → 有限值
    assert not pd.isna(result.iloc[10])
