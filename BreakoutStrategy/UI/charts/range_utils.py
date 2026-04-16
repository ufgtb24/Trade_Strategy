"""
Chart range specification and data transformations.

本模块统一承载 Dev UI 和 Live UI 的 K 线图范围语义：
- ChartRangeSpec：三层范围（scan / compute / display）的 ideal/actual 双值表达
- trim_df_to_display：按 spec 裁切 df 到显示范围
- adjust_indices：把 breakout/peak 的 index 映射到裁切后的 df 坐标
- _collect_warnings：汇总降级状态供 UI 显示
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd


DISPLAY_MIN_WINDOW = timedelta(days=1095)  # 3 年


@dataclass(frozen=True)
class ChartRangeSpec:
    """K 线图渲染所需的范围契约（frozen，避免下游意外修改）。"""

    scan_start_ideal: date
    scan_end_ideal: date
    scan_start_actual: date
    scan_end_actual: date

    compute_start_ideal: date
    compute_start_actual: date

    display_start: date
    display_end: date

    pkl_start: date
    pkl_end: date

    @property
    def scan_start_degraded(self) -> bool:
        return self.scan_start_actual > self.scan_start_ideal

    @property
    def scan_end_degraded(self) -> bool:
        return self.scan_end_actual < self.scan_end_ideal

    @property
    def compute_buffer_degraded(self) -> bool:
        return self.compute_start_actual > self.compute_start_ideal
