"""
低谷检测器

Trough 是 Peak 的镜像概念，用于检测局部最低点。
用于 V 形反转信号的检测。
"""

from dataclasses import dataclass
from datetime import date
from typing import List

import numpy as np
import pandas as pd


@dataclass
class Trough:
    """
    低谷数据结构

    Attributes:
        index: 在价格序列中的索引
        price: 低谷价格（使用 low）
        date: 低谷日期
        window_start: 检测窗口起始位置
        window_end: 检测窗口结束位置（trough 被确认的日期索引）
    """
    index: int
    price: float
    date: date
    window_start: int = None
    window_end: int = None


class TroughDetector:
    """
    低谷检测器

    检测局部最低点，支持不同的窗口参数。

    参数：
        window: 检测窗口大小
        min_side_bars: 单侧最小 K 线数
        measure: 价格衡量方式 ("low", "close", "body_bottom")
    """

    def __init__(self, window: int = 10, min_side_bars: int = 3, measure: str = "low"):
        if min_side_bars * 2 > window:
            raise ValueError(
                f"min_side_bars ({min_side_bars}) * 2 > window ({window})"
            )
        self.window = window
        self.min_side_bars = min_side_bars
        self.measure = measure

    def _get_prices(self, df: pd.DataFrame) -> np.ndarray:
        """
        根据 measure 获取价格序列

        Args:
            df: OHLCV 数据

        Returns:
            价格序列数组
        """
        if self.measure == "low":
            return df["low"].values
        elif self.measure == "close":
            return df["close"].values
        elif self.measure == "body_bottom":
            return np.minimum(df["open"].values, df["close"].values)
        else:
            # 默认使用 low
            return df["low"].values

    def detect_troughs(self, df: pd.DataFrame) -> List[Trough]:
        """
        检测所有低谷

        Args:
            df: OHLCV 数据

        Returns:
            检测到的低谷列表
        """
        troughs = []

        if len(df) < self.window:
            return troughs

        lows = self._get_prices(df)

        for i in range(self.window, len(df)):
            window_start = i - self.window
            window_lows = lows[window_start:i]

            # 找到窗口内的最低点
            min_low = min(window_lows)
            min_local_idx = list(window_lows).index(min_low)

            # 检查是否在有效范围内（不在前后 min_side_bars 个位置）
            if min_local_idx < self.min_side_bars:
                continue
            if min_local_idx >= len(window_lows) - self.min_side_bars:
                continue

            # 计算全局索引
            trough_global_idx = window_start + min_local_idx

            # 检查是否已经添加过这个低谷
            if any(t.index == trough_global_idx for t in troughs):
                continue

            trough = Trough(
                index=trough_global_idx,
                price=min_low,
                date=df.index[trough_global_idx].date(),
                window_start=window_start,
                window_end=i - 1,  # 窗口最后一个元素的索引（trough 确认日期）
            )
            troughs.append(trough)

        return troughs
