"""TrendSegment atom: 走势-无关的趋势 segment 流(三态 down/sideways/up + hysteresis)。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Iterator, Literal

import pandas as pd

from path2 import Event
from path2.calc.ma import calculate_ma


@dataclass(frozen=True)
class TrendSegment(Event):
    """走势-无关的连续相同 regime 区段。confirm_idx = end_idx:retrospective,regime 切换才确认完整区段。

    输出字段(where 可引用):
    - regime:   "down" / "sideways" / "up" 三态
    - drawdown: (seg_high - seg_low) / seg_high,区段内价格振幅占比
                (非「相对前高」的绝对跌幅;服务 bottom_burst 谓词 ④)
    """
    regime: Literal["down", "sideways", "up"] = "sideways"
    drawdown: float = 0.0


class TrendSegmentDetector:
    """按 SMA per-bar 相对变化 + hysteresis 切割连续相同 regime 区段。

    核心判据:
      1. ma = SMA(close, ma_period);ma_diff[t] = (ma[t] - ma[t-1]) / ma[t-1]
      2. instant_regime[t] 与 ±sideways_eps 比较得三态
         (> sideways_eps → up;< -sideways_eps → down;否则 sideways)
      3. confirmed_regime 切换需 hysteresis_bars 根 instant 连续一致(平滑短反转)
      4. 连续相同 confirmed_regime 合并为一个 segment,yield TrendSegment
      5. drawdown = (seg_high - seg_low) / seg_high(seg_high ≤ 0 时为 0)

    简化版(取消 slope 计算):per-bar 相对变化直接判态,不算回归斜率。

    输出字段详见 TrendSegment。
    """
    has_debug_hooks: ClassVar[bool] = False

    event_cls = TrendSegment

    def __init__(self,
                 ma_period: int = 20,
                 sideways_eps: float = 0.0005,
                 hysteresis_bars: int = 3):
        self.ma_period = ma_period
        self.sideways_eps = sideways_eps
        self.hysteresis_bars = hysteresis_bars

    def detect(self, df: pd.DataFrame) -> Iterator[TrendSegment]:
        n = len(df)
        if n < self.ma_period + 1:
            return

        closes = df['close']
        ma = calculate_ma(closes, self.ma_period)
        ma_diff = (ma - ma.shift(1)) / ma.shift(1)

        # 1. instant_regime per bar
        instant = ['sideways'] * n
        for i in range(n):
            d = ma_diff.iloc[i]
            if pd.isna(d):
                continue
            if d > self.sideways_eps:
                instant[i] = 'up'
            elif d < -self.sideways_eps:
                instant[i] = 'down'

        # 2. confirmed_regime per bar (with hysteresis)
        confirmed = ['sideways'] * n
        current = 'sideways'
        candidate = None
        candidate_count = 0
        for i in range(n):
            if instant[i] == current:
                candidate = None
                candidate_count = 0
            else:
                if candidate == instant[i]:
                    candidate_count += 1
                else:
                    candidate = instant[i]
                    candidate_count = 1
                if candidate_count >= self.hysteresis_bars:
                    current = candidate
                    candidate = None
                    candidate_count = 0
            confirmed[i] = current

        # 3. 切 segments
        seg_start = 0
        seg_regime = confirmed[0]
        for i in range(1, n):
            if confirmed[i] != seg_regime:
                yield self._make_segment(df, seg_start, i - 1, seg_regime)
                seg_start = i
                seg_regime = confirmed[i]
        # 末段
        yield self._make_segment(df, seg_start, n - 1, seg_regime)

    def _make_segment(self, df: pd.DataFrame, start: int, end: int, regime: str) -> TrendSegment:
        seg_high = float(df['high'].iloc[start: end + 1].max())
        seg_low = float(df['low'].iloc[start: end + 1].min())
        drawdown = (seg_high - seg_low) / seg_high if seg_high > 0 else 0.0
        return TrendSegment(
            start_idx=start,
            end_idx=end,
            confirm_idx=end,   # retrospective:regime 切换才确认完整区段
            regime=regime,
            drawdown=drawdown,
        )
