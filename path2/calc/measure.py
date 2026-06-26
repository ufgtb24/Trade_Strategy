"""单 bar / 向量价格度量(纯数值,无 Event/Detector)。bo 的 peak/breakout 与 tb 的 anchor/破位共用。"""
from __future__ import annotations

import pandas as pd

VALID_MEASURES = ("high", "close", "body_top", "low")


def measure_at(df: pd.DataFrame, i: int, measure: str) -> float:
    """单 bar 度量:high / close / body_top(实体上界) / low。"""
    if measure == "high":
        return float(df['high'].iloc[i])
    if measure == "close":
        return float(df['close'].iloc[i])
    if measure == "body_top":
        return float(max(df['open'].iloc[i], df['close'].iloc[i]))
    if measure == "low":
        return float(df['low'].iloc[i])
    raise ValueError(f"unknown measure: {measure!r}")


def measure_series(df: pd.DataFrame, measure: str) -> pd.Series:
    """向量度量序列:服务窗口扫描(避免逐 bar 函数调用)。"""
    if measure == "high":
        return df['high']
    if measure == "close":
        return df['close']
    if measure == "body_top":
        return pd.concat([df['open'], df['close']], axis=1).max(axis=1)
    if measure == "low":
        return df['low']
    raise ValueError(f"unknown measure: {measure!r}")
