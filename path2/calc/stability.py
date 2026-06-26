"""peak 起 N 日 low 不跌破 peak_price 的比例(含 peak bar)。"""
from __future__ import annotations

import pandas as pd


def calculate_stability(lows: pd.Series, peak_idx: int, peak_price: float,
                        lookforward: int = 10) -> float:
    """peak 起 lookforward 个 bar(含 peak bar)中 low ≥ peak_price 的比例(0~1)。

    若 peak_idx + lookforward 越界,只统计可用 bar;若可用 0 则返 1.0(无信息=保守满分)。
    """
    end = min(peak_idx + lookforward, len(lows))
    window = lows.iloc[peak_idx: end]
    if len(window) == 0:
        return 1.0
    return float((window >= peak_price).mean())
