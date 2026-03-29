"""
波动率分析器

负责分析波动率的变化趋势:
- ATR 序列计算
- 波动率收敛检测
- 收敛分数计算
"""
from datetime import date
from typing import List, TYPE_CHECKING

import numpy as np
import pandas as pd

from ..config import VolatilityConfig
from .results import VolatilityResult

if TYPE_CHECKING:
    pass


class VolatilityAnalyzer:
    """
    波动率分析器

    职责:
    - 计算 ATR 序列
    - 检测波动率收敛
    - 评估收敛分数

    收敛分数公式:
        score = 斜率分数(0.5) + ATR比率分数(0.3) + 稳定性分数(0.2)
    """

    def __init__(self, config: VolatilityConfig):
        """
        初始化分析器

        Args:
            config: 波动率配置
        """
        self.config = config

    def analyze(self, df: pd.DataFrame, initial_atr: float,
                as_of_date: date) -> VolatilityResult:
        """
        分析波动率状态

        Args:
            df: OHLCV DataFrame
            initial_atr: 突破时的 ATR
            as_of_date: 分析日期

        Returns:
            VolatilityResult
        """
        if len(df) < self.config.atr_period:
            return VolatilityResult(
                current_atr=initial_atr,
                atr_ratio=1.0,
                convergence_score=0.0,
                volatility_state="stable"
            )

        # 计算 ATR 序列
        atr_series = self._calculate_atr_series(df, self.config.atr_period)
        current_atr = float(atr_series.iloc[-1]) if len(atr_series) > 0 else initial_atr

        # ATR 比率
        atr_ratio = current_atr / initial_atr if initial_atr > 0 else 1.0

        # 收敛分数
        convergence_score = self._calculate_convergence_score(
            atr_series.tolist(), initial_atr
        )

        # 波动状态
        volatility_state = self._determine_volatility_state(atr_ratio, convergence_score)

        return VolatilityResult(
            current_atr=current_atr,
            atr_ratio=atr_ratio,
            convergence_score=convergence_score,
            volatility_state=volatility_state
        )

    def _calculate_atr_series(self, df: pd.DataFrame, period: int) -> pd.Series:
        """
        计算 ATR 序列

        Args:
            df: OHLCV DataFrame
            period: ATR 周期

        Returns:
            ATR Series
        """
        high = df['high']
        low = df['low']
        close = df['close']

        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # ATR (Simple Moving Average)
        atr = tr.rolling(window=period).mean()

        return atr.dropna()

    def _calculate_convergence_score(self, atr_series: List[float],
                                     initial_atr: float) -> float:
        """
        计算收敛分数

        公式: score = 斜率分数(0.5) + ATR比率分数(0.3) + 稳定性分数(0.2)

        Args:
            atr_series: ATR 值列表
            initial_atr: 初始 ATR

        Returns:
            收敛分数 (0-1)
        """
        if len(atr_series) < 5:
            return 0.0

        # 取最近 N 天
        lookback = min(self.config.lookback_days, len(atr_series))
        recent = atr_series[-lookback:]
        current_atr = recent[-1]

        # 1. 斜率分数: 线性回归斜率，负值得分
        slope = self._linear_regression_slope(recent)
        mean_val = np.mean(recent)
        normalized_slope = slope / mean_val if mean_val > 0 else 0

        if slope < 0:
            # 斜率为负，波动率在下降
            slope_score = min(abs(normalized_slope) / 0.05, 1.0) * 0.5
        else:
            slope_score = 0

        # 2. ATR 比率分数: 当前/初始 越小越好
        atr_ratio = current_atr / initial_atr if initial_atr > 0 else 1.0

        if atr_ratio <= self.config.contraction_threshold:
            ratio_score = 0.3
        elif atr_ratio <= 1.0:
            # 线性插值
            ratio_score = 0.3 * (1.0 - atr_ratio) / (1.0 - self.config.contraction_threshold)
        else:
            ratio_score = 0

        # 3. 稳定性分数: 变异系数 (CV) 越小越好
        last_5 = recent[-5:] if len(recent) >= 5 else recent
        mean_last = np.mean(last_5)
        cv = np.std(last_5) / mean_last if mean_last > 0 else 1.0
        stability_score = max(0, 0.2 * (1 - cv / 0.3))

        return slope_score + ratio_score + stability_score

    def _linear_regression_slope(self, values: List[float]) -> float:
        """
        计算线性回归斜率

        Args:
            values: 值列表

        Returns:
            斜率
        """
        n = len(values)
        if n < 2:
            return 0.0

        x = np.arange(n)
        y = np.array(values)

        x_mean = np.mean(x)
        y_mean = np.mean(y)

        numerator = np.sum((x - x_mean) * (y - y_mean))
        denominator = np.sum((x - x_mean) ** 2)

        return float(numerator / denominator) if denominator > 0 else 0.0

    def _determine_volatility_state(self, atr_ratio: float,
                                    convergence_score: float) -> str:
        """
        判断波动率状态

        Args:
            atr_ratio: ATR 比率
            convergence_score: 收敛分数

        Returns:
            状态字符串
        """
        if convergence_score >= 0.5 and atr_ratio < 1.0:
            return "contracting"
        elif convergence_score < 0.3 or atr_ratio > 1.2:
            return "expanding"
        else:
            return "stable"
