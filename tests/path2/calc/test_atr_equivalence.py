"""calculate_atr 向量化实现与原 pandas 逐行实现逐值等价(atol=1e-12)。"""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from path2.calc.atr import calculate_atr

PKL_DIR = Path("datasets/pkls")


def _reference_atr(highs, lows, closes, period=14):
    """原实现(pandas 逐行),作 golden。"""
    prev_close = closes.shift(1)
    tr = pd.concat([highs - lows, (highs - prev_close).abs(), (lows - prev_close).abs()],
                   axis=1).max(axis=1)
    atr = pd.Series(np.nan, index=closes.index, dtype=float)
    if len(tr) < period:
        return atr
    atr.iloc[period - 1] = tr.iloc[:period].mean()
    for i in range(period, len(tr)):
        atr.iloc[i] = (atr.iloc[i - 1] * (period - 1) + tr.iloc[i]) / period
    return atr


def _real_frames(n=3):
    if not PKL_DIR.exists():
        pytest.skip("datasets/pkls 缺失")
    out = []
    for p in sorted(PKL_DIR.glob("*.pkl"))[:200]:
        df = pd.read_pickle(p)
        if len(df) >= 300:
            out.append(df.iloc[-760:].reset_index(drop=True))
        if len(out) == n:
            break
    if len(out) < n:
        pytest.skip(f"datasets/pkls 中长度达标的样本不足 {n} 个(实得 {len(out)})")
    return out


@pytest.mark.parametrize("period", [14, 20])
def test_equivalent_on_real_data(period):
    for df in _real_frames():
        a = _reference_atr(df["high"], df["low"], df["close"], period)
        b = calculate_atr(df["high"], df["low"], df["close"], period)
        assert b.index.equals(a.index)
        assert np.allclose(a.to_numpy(), b.to_numpy(), rtol=0, atol=1e-12, equal_nan=True)
        assert np.isnan(b.iloc[: period - 1]).all()


def test_short_input_all_nan():
    s = pd.Series([1.0, 2.0, 3.0])
    out = calculate_atr(s + 1, s - 1, s, period=14)
    assert len(out) == 3 and out.isna().all()


def test_nan_inside_matches_reference():
    rng = np.random.default_rng(0)
    c = pd.Series(100 + rng.standard_normal(120).cumsum())
    h, l = c + 1, c - 1
    h.iloc[30] = np.nan                      # 一根缺高价:TR 按 skipna 取余下两项
    a = _reference_atr(h, l, c, 14)
    b = calculate_atr(h, l, c, 14)
    assert np.allclose(a.to_numpy(), b.to_numpy(), rtol=0, atol=1e-12, equal_nan=True)


def test_nan_both_high_low_missing_seed_and_recursion():
    """high/low 同根缺失 → 三项(H-L/|H-Cprev|/|L-Cprev|)全 NaN → TR 本身为 NaN。
    分别在种子窗内(period=14 时 idx=5<14,走 out[period-1] 的 np.nanmean 分支)
    与递推段内(idx=20>=14,走 for 循环里 tr[i] 为 NaN 的传播分支)各触发一次,
    覆盖 path2/calc/atr.py 里此前零覆盖的两条 NaN 支路。"""
    rng = np.random.default_rng(1)
    c = pd.Series(100 + rng.standard_normal(40).cumsum())
    h, l = c + 1, c - 1
    h.iloc[5] = np.nan; l.iloc[5] = np.nan     # 种子窗内(period=14 > 5)
    h.iloc[20] = np.nan; l.iloc[20] = np.nan   # 递推段内(20 >= 14)
    a = _reference_atr(h, l, c, 14)
    b = calculate_atr(h, l, c, 14)
    # 种子窗内的 NaN 应被 nanmean 跳过,idx13(period-1)仍是有限值
    assert np.isfinite(a.iloc[13]) and np.isfinite(b.iloc[13])
    # 递推段内一旦 tr[20] 为 NaN,ATR 自 idx20 起永久 NaN(两实现须逐值一致地传播)
    assert np.isnan(a.iloc[20:]).all() and np.isnan(b.iloc[20:]).all()
    assert np.allclose(a.to_numpy(), b.to_numpy(), rtol=0, atol=1e-12, equal_nan=True)
