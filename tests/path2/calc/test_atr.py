from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from path2.calc.atr import calculate_atr, prev_bar_atr_pct


def test_atr_basic_shape():
    n = 30
    highs = pd.Series(np.linspace(10, 12, n) + 0.5)
    lows = pd.Series(np.linspace(10, 12, n) - 0.5)
    closes = pd.Series(np.linspace(10, 12, n))
    atr = calculate_atr(highs, lows, closes, period=14)
    assert len(atr) == n
    assert atr.iloc[:13].isna().all()
    assert not atr.iloc[14:].isna().any()


def test_atr_constant_tr():
    n = 30
    highs = pd.Series([11.0] * n)
    lows = pd.Series([10.0] * n)
    closes = pd.Series([10.5] * n)
    atr = calculate_atr(highs, lows, closes, period=14)
    assert atr.iloc[20] == pytest.approx(1.0, rel=1e-6)


def test_atr_zero_when_no_range():
    n = 20
    highs = pd.Series([10.0] * n)
    lows = pd.Series([10.0] * n)
    closes = pd.Series([10.0] * n)
    atr = calculate_atr(highs, lows, closes, period=14)
    assert atr.iloc[15] == 0.0


# ---------------------------------------------------------------------------
# prev_bar_atr_pct:与 feature-study 抽取里「买点前一根 atr/close」的标量算式逐位对拍。
# ---------------------------------------------------------------------------

_FIXTURE_CSV = Path(__file__).resolve().parents[1] / "fixtures" / "aapl_vol_slice.csv"


def _scalar_prev_bar_atr_pct(highs, lows, closes, period):
    """标量直白版:逐个 entry_idx 取前一根 atr/close;entry_idx<1、分母<=0、
    或任一端非有限 → NaN。"""
    atr = calculate_atr(highs, lows, closes, period).to_numpy(float)
    close = closes.to_numpy(float)
    out = []
    for entry_idx in range(len(close)):
        if entry_idx < 1:
            out.append(np.nan)
            continue
        denom = close[entry_idx - 1]
        numer = atr[entry_idx - 1]
        out.append(numer / denom
                   if denom > 0 and np.isfinite(denom) and np.isfinite(numer)
                   else np.nan)
    return np.array(out, dtype=float)


def _dirty_ohlc(n, seed):
    """随机 OHLC,注入 NaN / 0 / 负数 / inf 收盘与 NaN 高低价,覆盖全部 NaN 分支。"""
    rng = np.random.default_rng(seed)
    close = 20.0 * np.exp(np.cumsum(rng.normal(0, 0.03, n)))
    high = close * (1 + np.abs(rng.normal(0, 0.02, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.02, n)))
    close[[25, 26]] = 0.0
    close[40] = -3.0
    close[55] = np.nan
    close[70] = np.inf
    high[80] = np.nan
    low[81] = np.nan
    return pd.Series(high), pd.Series(low), pd.Series(close)


@pytest.mark.parametrize("period", [14, 5])
def test_prev_bar_atr_pct_matches_scalar_formula(period):
    h, l, c = _dirty_ohlc(120, seed=period)
    got = prev_bar_atr_pct(h, l, c, period)
    ref = _scalar_prev_bar_atr_pct(h, l, c, period)
    assert got.dtype == np.float64 and len(got) == len(c)
    np.testing.assert_array_equal(got, ref)   # 非 NaN 位精确相等,NaN 位置一致
    assert np.isnan(got[0])
    assert np.isfinite(got).sum() > 50


def test_prev_bar_atr_pct_real_prices_and_short_input():
    """真实价格 fixture 默认 period=14 逐位相等;长度 0 / 不足 period 时全 NaN。"""
    df = pd.read_csv(_FIXTURE_CSV)
    h, l, c = df["high"], df["low"], df["close"]
    np.testing.assert_array_equal(prev_bar_atr_pct(h, l, c),
                                  _scalar_prev_bar_atr_pct(h, l, c, 14))
    empty = pd.Series([], dtype=float)
    assert len(prev_bar_atr_pct(empty, empty, empty)) == 0
    short = prev_bar_atr_pct(h.iloc[:10], l.iloc[:10], c.iloc[:10])
    assert len(short) == 10 and np.isnan(short).all()
