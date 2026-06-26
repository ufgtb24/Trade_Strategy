"""vol_ratio: 当前 bar volume 相对前 baseline_period 日均量的倍数。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_vol_ratio(volumes: pd.Series, baseline_period: int = 63) -> pd.Series:
    """volume / rolling.mean(volume, baseline_period).shift(1)。

    用 shift(1) 避免 self-leakage(当前 bar 自己不参与基线)。
    前 baseline_period 个 bar 为 NaN(基线不足)。
    零成交量段(停牌)→ baseline 为 0 → 商为 inf;统一规整为 NaN,
    下游只需防 NaN。
    """
    baseline = volumes.rolling(window=baseline_period, min_periods=baseline_period).mean().shift(1)
    return (volumes / baseline).replace([np.inf, -np.inf], np.nan)
