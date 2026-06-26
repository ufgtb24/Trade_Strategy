"""ATR 计算 (Wilder RMA)。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_atr(highs: pd.Series, lows: pd.Series, closes: pd.Series,
                  period: int = 14) -> pd.Series:
    """Wilder RMA 平滑的 ATR。

    返回与输入同长 Series(前 period-1 为 NaN,第 period 个为算术均;之后为 Wilder 递推)。
    TR_i = max(H_i - L_i, |H_i - C_{i-1}|, |L_i - C_{i-1}|)
    ATR_i = (ATR_{i-1} * (period - 1) + TR_i) / period
    """
    prev_close = closes.shift(1)
    tr = pd.concat([
        highs - lows,
        (highs - prev_close).abs(),
        (lows - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = pd.Series(np.nan, index=closes.index, dtype=float)
    if len(tr) < period:
        return atr
    atr.iloc[period - 1] = tr.iloc[:period].mean()
    for i in range(period, len(tr)):
        atr.iloc[i] = (atr.iloc[i - 1] * (period - 1) + tr.iloc[i]) / period
    return atr
