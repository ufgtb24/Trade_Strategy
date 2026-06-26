"""滚动窗口振幅 / 标准差占比。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rolling_range_pct(highs: pd.Series, lows: pd.Series, period: int) -> pd.Series:
    """(rolling max(highs) - rolling min(lows)) / rolling min(lows),over period。

    rolling min 为 0 时(停牌段 / 异常)→ inf;统一规整为 NaN,下游只需防 NaN。
    """
    rmax = highs.rolling(window=period, min_periods=period).max()
    rmin = lows.rolling(window=period, min_periods=period).min()
    return ((rmax - rmin) / rmin).replace([np.inf, -np.inf], np.nan)


def rolling_std_pct(closes: pd.Series, period: int) -> pd.Series:
    """rolling std(closes, period) / closes。"""
    std = closes.rolling(window=period, min_periods=period).std()
    return std / closes
