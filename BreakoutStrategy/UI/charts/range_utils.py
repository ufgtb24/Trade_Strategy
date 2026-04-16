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


def trim_df_to_display(df: pd.DataFrame, spec: ChartRangeSpec) -> tuple[pd.DataFrame, int]:
    """
    裁切 df 到 display_start 之后。返回 (display_df, index_offset)。

    如果 display_start 早于 df.index[0]，不裁切（offset=0）。
    """
    start_dt = pd.to_datetime(spec.display_start)
    mask = df.index >= start_dt
    if not mask.any():
        return df, 0
    first_idx = int(mask.argmax())
    if first_idx == 0:
        return df, 0
    return df.iloc[first_idx:].copy(), first_idx


def adjust_indices(items: list, offset: int) -> list:
    """
    把 breakout/peak 的 index 映射到裁切后的 df 坐标。

    - offset=0：返回原列表（不拷贝）
    - item.index < offset：跳过（位于裁切区之前）
    - 否则：浅拷贝 + index -= offset；若对象有 broken_peaks 属性，递归调整
    """
    if offset == 0:
        return items

    result = []
    for item in items:
        if item.index < offset:
            continue
        new_item = item.__class__.__new__(item.__class__)
        new_item.__dict__.update(item.__dict__)
        new_item.index = item.index - offset
        if hasattr(new_item, "broken_peaks") and new_item.broken_peaks:
            new_item.broken_peaks = adjust_indices(new_item.broken_peaks, offset)
        result.append(new_item)
    return result
