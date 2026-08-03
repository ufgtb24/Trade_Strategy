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


def rolling_atr_pct_nanmedian(highs: pd.Series, lows: pd.Series, closes: pd.Series,
                              period: int = 20) -> pd.Series:
    """TR/close 的滚动 nanmedian —— 首次穿越的波动率尺度 M。

    M_t = nanmedian of (TR/close) over [t-period+1 .. t](含 t 当日;买点日 t 收盘
    买入,TR[t] 用 t 的 high/low + t-1 的 close,均已知 → 无前瞻)。前 period-1 个
    为 NaN(样本不足,首穿判定时跳过这些 t)。

    与 calculate_atr 的区别:后者 Wilder RMA(均值类,对一年一次的极端异动不鲁棒,
    会被撑成一把刻度过大的尺子);本函数用 nanmedian(中位数,免疫少数异动)。
    TR 含跳空(|high-prev_close| / |low-prev_close|),与首穿判定 high/low 越线
    含跳空(跳空越过算触)自洽。
    """
    prev_close = closes.shift(1)
    tr = pd.concat([
        highs - lows,
        (highs - prev_close).abs(),
        (lows - prev_close).abs(),
    ], axis=1).max(axis=1)
    tr_pct = tr / closes
    return tr_pct.rolling(period).apply(np.nanmedian, raw=True)
