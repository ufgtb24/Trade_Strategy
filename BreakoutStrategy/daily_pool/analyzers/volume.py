"""
成交量分析器

负责分析成交量的变化:
- 基准成交量计算
- 放量检测
- 成交量趋势判断
"""
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

from ..config import VolumeConfig
from .results import VolumeResult

if TYPE_CHECKING:
    pass


class VolumeAnalyzer:
    """
    成交量分析器

    职责:
    - 计算基准成交量 (MA)
    - 检测放量
    - 判断成交量趋势

    放量判定:
        当前成交量 / 基准成交量 >= expansion_threshold
    """

    def __init__(self, config: VolumeConfig):
        """
        初始化分析器

        Args:
            config: 成交量配置
        """
        self.config = config

    def analyze(self, df: pd.DataFrame, as_of_date: date) -> VolumeResult:
        """
        分析成交量

        Args:
            df: OHLCV DataFrame
            as_of_date: 分析日期

        Returns:
            VolumeResult
        """
        if len(df) == 0 or 'volume' not in df.columns:
            return VolumeResult(
                baseline_volume=0.0,
                current_volume=0.0,
                volume_expansion_ratio=1.0,
                surge_detected=False,
                volume_trend="neutral"
            )

        volume = df['volume']

        # 基准量: MA(baseline_period)
        if len(volume) >= self.config.baseline_period:
            baseline = float(volume.tail(self.config.baseline_period).mean())
        else:
            baseline = float(volume.mean())

        current = float(volume.iloc[-1])

        # 放量比率
        ratio = current / baseline if baseline > 0 else 1.0

        # 放量检测
        surge_detected = ratio >= self.config.expansion_threshold

        # 趋势判断
        volume_trend = self._determine_volume_trend(volume)

        return VolumeResult(
            baseline_volume=baseline,
            current_volume=current,
            volume_expansion_ratio=ratio,
            surge_detected=surge_detected,
            volume_trend=volume_trend
        )

    def _determine_volume_trend(self, volume: pd.Series) -> str:
        """
        判断成交量趋势

        比较短期MA和长期MA:
        - short_ma > long_ma * 1.1 -> increasing
        - short_ma < long_ma * 0.9 -> decreasing
        - 其他 -> neutral

        Args:
            volume: 成交量序列

        Returns:
            趋势字符串
        """
        if len(volume) < 20:
            return "neutral"

        short_ma = float(volume.tail(5).mean())
        long_ma = float(volume.tail(20).mean())

        if long_ma <= 0:
            return "neutral"

        if short_ma > long_ma * 1.1:
            return "increasing"
        elif short_ma < long_ma * 0.9:
            return "decreasing"
        else:
            return "neutral"
