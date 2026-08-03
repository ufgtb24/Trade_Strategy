"""Platform atom: 窄幅震荡 segment(走势-无关的"平台段")。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Iterator

import numpy as np
import pandas as pd

from path2 import Event
from path2.stdlib import span_id
from path2.calc.atr import calculate_atr


@dataclass(frozen=True)
class Platform(Event):
    """窄幅震荡平台段。confirm_idx = end_idx:retrospective,价格走出平台才确认。

    输出字段(where 可引用):
    - atr_pct_mean: 区段内 ATR/close 均值(相对波动率,非绝对 ATR)
    - range_pct:    扩窗结束时的 (max_high - min_low) / min_low(区段最终振幅占比)
    """
    class_id = "platform"
    atr_pct_mean: float = 0.0
    range_pct: float = 0.0


class PlatformDetector:
    """非重叠贪心扫窗产出窄幅震荡平台段。

    核心判据:
      1. 以固定 window 为初始宽度扫起始位置 i
      2. 初始窗 (max_high - min_low) / min_low ≤ range_thr → 候选;
         不满足则 i += 1 步进重试
      3. 右扩:逐根加入直到加入新 bar 后 range_pct > range_thr 或序列末尾
      4. yield Platform(start..end);下一次从 i = end + 1 开始(非重叠贪心,
         已产 Platform 尾端吃掉的区域不再重扫)
      5. window_min ≤ 0 时跳过该起始位(低价股/极端数据保护)

    atr_pct_mean = mean(ATR / close) over [start, end]
    (NaN 或 close ≤ 0 的 bar 跳过;全跳过则为 0)。

    输出字段详见 Platform。
    """
    has_debug_hooks: ClassVar[bool] = False

    event_cls = Platform

    def __init__(self,
                 window: int = 10,
                 range_thr: float = 0.05,
                 atr_period: int = 14):
        self.window = window
        self.range_thr = range_thr
        self.atr_period = atr_period

    def detect(self, df: pd.DataFrame) -> Iterator[Platform]:
        n = len(df)
        if n < self.window:
            return

        highs = df['high']
        lows = df['low']
        closes = df['close']
        atr = calculate_atr(highs, lows, closes, self.atr_period)

        i = 0
        while i + self.window <= n:
            start = i
            # 初始窗口
            window_max = highs.iloc[start: start + self.window].max()
            window_min = lows.iloc[start: start + self.window].min()
            if window_min <= 0:
                i += 1
                continue
            range_pct = (window_max - window_min) / window_min
            if range_pct > self.range_thr:
                i += 1
                continue

            # 右扩
            end = start + self.window - 1
            while end + 1 < n:
                next_high = highs.iloc[end + 1]
                next_low = lows.iloc[end + 1]
                new_max = max(window_max, next_high)
                new_min = min(window_min, next_low)
                if new_min <= 0:
                    break
                new_range = (new_max - new_min) / new_min
                if new_range > self.range_thr:
                    break
                window_max = new_max
                window_min = new_min
                end += 1
                range_pct = new_range

            # yield
            atr_slice = atr.iloc[start: end + 1]
            close_slice = closes.iloc[start: end + 1]
            valid_atr = [(a / c) for a, c in zip(atr_slice, close_slice)
                         if not pd.isna(a) and c > 0]
            atr_pct_mean = float(np.mean(valid_atr)) if valid_atr else 0.0
            yield Platform(
                event_id=span_id(self.event_cls.class_id, start, end),
                start_idx=start,
                end_idx=end,
                confirm_idx=end,   # retrospective:走出平台才确认
                atr_pct_mean=atr_pct_mean,
                range_pct=float(range_pct),
            )
            i = end + 1
