"""计算 nl_description 所需的盘整阶段描述字段。

输入：原始 OHLCV df + 突破点 bo_index + 盘整起点 pk_index
输出：dict[str, int | float | None] — 5 个无量纲字段 + pivot_close 归一化基准（共 6 项），无法计算时返回 None
"""

from typing import Optional

import numpy as np
import pandas as pd

ATR_PERIOD = 14
PRE_CONSOL_VOLUME_LOOKBACK = 60
WEEKS_52_BARS = 252  # 美股交易日


def compute_consolidation_fields(
    df: pd.DataFrame, bo_index: int, pk_index: int,
) -> dict[str, int | float | None]:
    """计算盘整阶段 5 字段 + pivot_close 归一化基准（共 6 项）。

    Args:
        df: OHLCV DataFrame，列名小写（open/high/low/close/volume）
        bo_index: 突破日 index
        pk_index: 盘整起点（前一个 peak）index

    Returns:
        6 项字典，元素为 int / float 或 None（数据不足时）；
        pivot_close 为盘整起点收盘价，用于 prompt 中 OHLC 归一化。
    """
    result = {
        "consolidation_length_bars": _length_bars(bo_index, pk_index),
        "consolidation_height_pct": _height_pct(df, bo_index, pk_index),
        "consolidation_position_vs_52w_high": _position_vs_52w_high(df, bo_index, pk_index),
        "consolidation_volume_ratio": _volume_ratio(df, bo_index, pk_index),
        "consolidation_tightness_atr": _tightness_atr(df, bo_index, pk_index),
        "pivot_close": float(df.iloc[pk_index]["close"]),  # 盘整起点收盘价，用于 prompt 归一化
    }
    return result


def _length_bars(bo_index: int, pk_index: int) -> int:
    return int(bo_index - pk_index)


def _height_pct(df: pd.DataFrame, bo_index: int, pk_index: int) -> Optional[float]:
    consol = df.iloc[pk_index:bo_index]
    if len(consol) < 2:
        return None
    high = consol["high"].max()
    low = consol["low"].min()
    if low <= 0:
        return None
    return float((high - low) / low * 100)


def _position_vs_52w_high(
    df: pd.DataFrame, bo_index: int, pk_index: int,
) -> Optional[float]:
    """盘整中位价对 52 周高的距离百分比（负值 = 距离高点；正值 = 突破高点）。"""
    if bo_index < WEEKS_52_BARS:
        return None
    consol = df.iloc[pk_index:bo_index]
    if len(consol) < 2:
        return None
    consol_mid = float((consol["high"].max() + consol["low"].min()) / 2)
    high_52w = float(df.iloc[bo_index - WEEKS_52_BARS:bo_index]["high"].max())
    if high_52w <= 0:
        return None
    return (consol_mid - high_52w) / high_52w * 100


def _volume_ratio(
    df: pd.DataFrame, bo_index: int, pk_index: int,
) -> Optional[float]:
    """盘整期均量 / 盘整前 60 bars 均量。"""
    if pk_index < PRE_CONSOL_VOLUME_LOOKBACK:
        return None
    consol = df.iloc[pk_index:bo_index]
    pre = df.iloc[pk_index - PRE_CONSOL_VOLUME_LOOKBACK:pk_index]
    if len(consol) < 2:  # pre 已由前 guard 保证 60 bars
        return None
    consol_vol = float(consol["volume"].mean())
    pre_vol = float(pre["volume"].mean())
    if pre_vol <= 0:
        return None
    return consol_vol / pre_vol


def _tightness_atr(
    df: pd.DataFrame, bo_index: int, pk_index: int,
) -> Optional[float]:
    """盘整 height / ATR(14) at breakout day。

    ATR 计算需要前一日收盘价，因此取 bo_index-ATR_PERIOD-1 到 bo_index 共 15 行，
    shift(1) 后取最后 ATR_PERIOD 行的 True Range 均值。
    """
    if bo_index < ATR_PERIOD + 1:
        return None
    consol = df.iloc[pk_index:bo_index]
    if len(consol) < 2:
        return None
    height = float(consol["high"].max() - consol["low"].min())

    # 取 ATR_PERIOD+1 行以确保 shift(1) 有前置收盘价
    atr_window = df.iloc[bo_index - ATR_PERIOD - 1:bo_index].copy()
    prev_close = atr_window["close"].shift(1)
    tr = np.maximum.reduce([
        (atr_window["high"] - atr_window["low"]).values,
        np.abs(atr_window["high"].values - prev_close.values),
        np.abs(atr_window["low"].values - prev_close.values),
    ])
    # 去掉第一行（prev_close 为 NaN），取最后 ATR_PERIOD 行
    tr = tr[1:]
    atr = float(np.nanmean(tr))
    if atr <= 0:
        return None
    return height / atr
