"""
超大成交量检测器

检测条件（任一满足）：
1. 成交量是过去 126 个交易日内的最大值
2. 成交量超过 N 日均量的 X 倍（默认 3 倍 MA20）
"""

from typing import List

import numpy as np
import pandas as pd

from ..models import AbsoluteSignal, SignalType
from .base import SignalDetector


class HighVolumeDetector(SignalDetector):
    """
    超大成交量检测器

    参数：
        lookback_days: 回看窗口，用于判断是否为窗口内最大（默认 126，约半年）
        volume_ma_period: 均量计算周期（默认 20）
        volume_multiplier: 均量倍数阈值（默认 3.0）
    """

    def __init__(
        self,
        lookback_days: int = 126,
        volume_ma_period: int = 20,
        volume_multiplier: float = 3.0,
    ):
        self.lookback_days = lookback_days
        self.volume_ma_period = volume_ma_period
        self.volume_multiplier = volume_multiplier

    def detect(self, df: pd.DataFrame, symbol: str) -> List[AbsoluteSignal]:
        """
        检测超大成交量信号

        Args:
            df: OHLCV 数据
            symbol: 股票代码

        Returns:
            检测到的 HIGH_VOLUME 信号列表
        """
        signals = []

        if len(df) < self.volume_ma_period:
            return signals

        volumes = df["volume"].values
        closes = df["close"].values

        # 计算移动平均成交量
        ma_volume = pd.Series(volumes).rolling(window=self.volume_ma_period).mean().values

        # 从有足够数据的位置开始检测
        start_idx = max(self.lookback_days, self.volume_ma_period)

        for i in range(start_idx, len(df)):
            current_volume = volumes[i]
            current_ma = ma_volume[i]

            # 条件 1: 是否为 lookback_days 内最大
            lookback_start = max(0, i - self.lookback_days + 1)
            is_max_126d = current_volume >= np.max(volumes[lookback_start : i + 1])

            # 条件 2: 是否超过均量倍数
            volume_ratio = current_volume / current_ma if current_ma > 0 else 0
            is_multiplier_triggered = volume_ratio >= self.volume_multiplier

            # 任一条件满足则触发
            if is_max_126d or is_multiplier_triggered:
                signal = AbsoluteSignal(
                    symbol=symbol,
                    date=df.index[i].date(),
                    signal_type=SignalType.HIGH_VOLUME,
                    price=float(closes[i]),
                    details={
                        "volume": float(current_volume),
                        "volume_ratio": round(float(volume_ratio), 2),
                        "is_max_126d": bool(is_max_126d),
                        "is_multiplier_triggered": bool(is_multiplier_triggered),
                    },
                )
                signals.append(signal)

        return signals
