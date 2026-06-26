"""MA 全家:rolling mean / position / ATR-normalized z / curvature / per-bar slope。"""
from __future__ import annotations

import pandas as pd


def calculate_ma(closes: pd.Series, period: int) -> pd.Series:
    """Simple MA(rolling mean)。前 period-1 为 NaN。"""
    return closes.rolling(window=period, min_periods=period).mean()


def calculate_ma_pos(closes: pd.Series, period: int) -> pd.Series:
    """(close - MA) / MA。前 period-1 为 NaN。"""
    ma = calculate_ma(closes, period)
    return (closes - ma) / ma


def calculate_ma_z_atr(closes: pd.Series, atr: pd.Series, period: int) -> pd.Series:
    """(close - MA) / atr.shift(1)。ATR 取前一日值避免 self-leakage。"""
    ma = calculate_ma(closes, period)
    return (closes - ma) / atr.shift(1)


def calculate_ma_curve(closes: pd.Series, period: int, stride: int = 5) -> pd.Series:
    """MA 二阶差分,归一化为 (d2 / MA[t]) * period^2。"""
    ma = calculate_ma(closes, period)
    d2 = ma - 2 * ma.shift(stride) + ma.shift(2 * stride)
    return (d2 / ma) * (period ** 2)


def calculate_ma_slope(ma_series: pd.Series, lookback: int = 20) -> pd.Series:
    """per-bar normalized slope: (MA[t] - MA[t-lookback]) / MA[t-lookback] / lookback。"""
    prev = ma_series.shift(lookback)
    return (ma_series - prev) / prev / lookback
