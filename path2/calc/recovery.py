"""dd_recov: 回撤恢复度,深跌后早期恢复信号。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_dd_recov(closes: pd.Series, lookback: int = 252,
                       best_recovery: float = 0.25) -> pd.Series:
    """drawdown × recovery × (1 - recovery)^(decay_power - 1)

    decay_power = 1 / best_recovery (峰值在 r = best_recovery)。
    recovery = (close - trough) / (peak - trough)。
    peak = rolling max(closes, lookback);trough = peak 之后到当前的 rolling min。
    第一个有效 bar 在 iloc[lookback - 1](前 lookback - 1 个 bar 为 NaN warmup)。
    """
    n = len(closes)
    result = pd.Series(np.nan, index=closes.index, dtype=float)
    decay_power = 1.0 / best_recovery
    for i in range(n):
        if i < lookback - 1:
            continue
        window = closes.iloc[i - lookback + 1: i + 1]
        peak_idx_rel = window.idxmax()
        peak = closes.loc[peak_idx_rel]
        peak_pos = closes.index.get_loc(peak_idx_rel)
        # trough: peak 之后到当前的 rolling min
        if peak_pos >= i:
            result.iloc[i] = 0.0
            continue
        post_peak = closes.iloc[peak_pos: i + 1]
        trough = post_peak.min()
        if peak <= trough:
            result.iloc[i] = 0.0
            continue
        drawdown = (peak - trough) / peak
        current = closes.iloc[i]
        recovery = (current - trough) / (peak - trough)
        recovery = max(0.0, min(1.0, recovery))
        result.iloc[i] = drawdown * recovery * ((1 - recovery) ** (decay_power - 1))
    return result
