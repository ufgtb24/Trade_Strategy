"""
大阳线检测器

基于波动率标准化检测大阳线：
日内涨幅 >= sigma_threshold * daily_volatility

其中 daily_volatility = annual_volatility / sqrt(252)
"""

import math
from typing import List

import numpy as np
import pandas as pd

from ..models import AbsoluteSignal, SignalType
from .base import SignalDetector


class BigYangDetector(SignalDetector):
    """
    大阳线检测器

    参数：
        volatility_lookback: 波动率计算回看周期（默认 252 天）
        sigma_threshold: 波动率倍数阈值（默认 2.5）
    """

    def __init__(
        self,
        volatility_lookback: int = 252,
        sigma_threshold: float = 2.5,
    ):
        self.volatility_lookback = volatility_lookback
        self.sigma_threshold = sigma_threshold
        self.skipped_symbols: List[str] = []

    def reset_skipped(self):
        """重置跳过列表（每次批量扫描前调用）"""
        self.skipped_symbols = []

    def detect(self, df: pd.DataFrame, symbol: str, end_index: int = None) -> List[AbsoluteSignal]:
        """
        检测大阳线信号

        Args:
            df: OHLCV 数据
            symbol: 股票代码
            end_index: 检测结束索引（不含），默认检测到 df 末尾

        Returns:
            检测到的 BIG_YANG 信号列表
        """
        signals = []

        # 至少需要 20 天数据来计算波动率
        min_lookback = 20
        if len(df) < min_lookback:
            return signals

        closes = df["close"].values
        opens = df["open"].values

        # 检查数据有效性
        if np.any(closes[:-1] <= 0):
            print(f"[Warning] {symbol}: invalid close price <= 0, skipping")
            self.skipped_symbols.append(symbol)
            return signals

        # 计算日收益率
        daily_returns = np.diff(closes) / closes[:-1]

        # 从有足够数据的位置开始检测
        start_idx = min(self.volatility_lookback, len(df) - 1)
        start_idx = max(start_idx, min_lookback)

        # 确定检测结束位置
        actual_end = end_index if end_index is not None else len(df)

        for i in range(start_idx, actual_end):
            # 计算年化波动率（使用过去 lookback 天的数据）
            lookback = min(self.volatility_lookback, i)
            if lookback < min_lookback:
                continue

            returns_window = daily_returns[i - lookback : i]
            annual_volatility = np.std(returns_window) * math.sqrt(252)

            if annual_volatility <= 0:
                continue

            # 计算日波动率
            daily_vol = annual_volatility / math.sqrt(252)

            # 计算日内涨幅
            open_price = opens[i]
            close_price = closes[i]

            if open_price <= 0:
                continue

            intraday_change = (close_price - open_price) / open_price

            # 只检测阳线
            if intraday_change <= 0:
                continue

            # 计算 sigma 倍数
            sigma = intraday_change / daily_vol

            if sigma >= self.sigma_threshold:
                signal = AbsoluteSignal(
                    symbol=symbol,
                    date=df.index[i].date(),
                    signal_type=SignalType.BIG_YANG,
                    price=float(close_price),
                    details={
                        "change_pct": round(float(intraday_change) * 100, 2),
                        "sigma": round(float(sigma), 2),
                        "annual_volatility": round(float(annual_volatility) * 100, 2),
                    },
                )
                signals.append(signal)

        return signals
