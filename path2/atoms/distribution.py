"""Distribution atom: 高位放量阴线带长上影(单 bar 派发判据)。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

import pandas as pd

from path2 import Event
from path2.stdlib import BarwiseDetector, span_id
from path2.calc.volume import calculate_vol_ratio
from path2.calc.geometry import upper_shadow_ratio


@dataclass(frozen=True)
class Distribution(Event):
    """高位放量阴线带长上影的单 bar 派发事件。start_idx == end_idx;confirm_idx = start_idx(点事件,该根即确认)。

    输出字段(where 可引用):
    - vol_ratio:          当根量比(volume[i] / SMA(volume, vol_baseline_period))
    - upper_shadow_ratio: 上影占比(分母是整根 K 线区间 high - low,非实体)
    """
    class_id = "dist"
    vol_ratio: float = 0.0
    upper_shadow_ratio: float = 0.0


class DistributionDetector(BarwiseDetector):
    """单 bar 派发点事件 detector:高位放量阴线带长上影。

    核心判据(per spec §2.1,三条同时满足才产事件):
      1. vol_ratio ≥ vol_threshold(放量)
      2. close < open(阴线;大涨阳线即使放量也不产)
      3. upper_shadow_ratio ≥ upper_shadow_threshold(上影足够长)
    upper_shadow_ratio 由 path2/calc/geometry.py::upper_shadow_ratio 计算
    (分母 = 整根 K 线区间 high - low,非实体)。
    vol_ratio 在序列前 vol_baseline_period 根热身期为 NaN(直接跳过不产)。

    输出字段详见 Distribution。
    """
    has_debug_hooks: ClassVar[bool] = False

    event_cls = Distribution

    def __init__(self,
                 vol_threshold: float = 3.0,
                 upper_shadow_threshold: float = 0.5,
                 vol_baseline_period: int = 63):
        self.vol_threshold = vol_threshold
        self.upper_shadow_threshold = upper_shadow_threshold
        self.vol_baseline_period = vol_baseline_period
        self._vol_ratio_series: Optional[pd.Series] = None

    def detect(self, df: pd.DataFrame):
        self._vol_ratio_series = calculate_vol_ratio(df['volume'], self.vol_baseline_period)
        yield from super().detect(df)

    def emit(self, df: pd.DataFrame, i: int) -> Optional[Distribution]:
        vr = self._vol_ratio_series.iloc[i]
        if pd.isna(vr) or vr < self.vol_threshold:
            return None
        o = df['open'].iloc[i]
        c = df['close'].iloc[i]
        if c >= o:
            return None
        h = df['high'].iloc[i]
        l = df['low'].iloc[i]
        usr = upper_shadow_ratio(o, h, l, c)
        if usr < self.upper_shadow_threshold:
            return None
        return Distribution(
            event_id=span_id(self.event_cls.class_id, i, i),
            start_idx=i,
            end_idx=i,
            confirm_idx=i,   # 点事件:该根即确认
            vol_ratio=float(vr),
            upper_shadow_ratio=float(usr),
        )
