"""
突破信号检测器（适配器）

适配现有的 BreakoutDetector，将 Breakout 对象转换为 AbsoluteSignal。
"""

from typing import List, Optional

import pandas as pd

from ..models import AbsoluteSignal, SignalType
from .base import SignalDetector

from BreakoutStrategy.analysis import (
    BreakoutDetector,
    FeatureCalculator,
)
from BreakoutStrategy.analysis.indicators import TechnicalIndicators


class BreakoutSignalDetector(SignalDetector):
    """
    突破信号检测器（适配器）

    复用现有 BreakoutDetector + FeatureCalculator，
    将 Breakout 对象转换为 AbsoluteSignal。

    参数从配置字典读取，支持通过 absolute_signals.yaml 配置。
    """

    def __init__(
        self,
        total_window: int = 20,
        min_side_bars: int = 6,
        min_relative_height: float = 0.1,
        exceed_threshold: float = 0.005,
        peak_supersede_threshold: float = 0.03,
        peak_measure: str = "body_top",
        breakout_modes: Optional[List[str]] = None,
        atr_buffer: int = 14,
    ):
        self.total_window = total_window
        self.min_side_bars = min_side_bars
        self.min_relative_height = min_relative_height
        self.exceed_threshold = exceed_threshold
        self.peak_supersede_threshold = peak_supersede_threshold
        self.peak_measure = peak_measure
        self.breakout_modes = breakout_modes or ["close"]
        self.atr_buffer = atr_buffer

        # 初始化特征计算器
        self.feature_calculator = FeatureCalculator()

    def detect(self, df: pd.DataFrame, symbol: str, end_index: int = None) -> List[AbsoluteSignal]:
        """
        检测突破信号

        Args:
            df: OHLCV 数据
            symbol: 股票代码
            end_index: 检测结束索引（不含），默认检测到 df 末尾

        Returns:
            检测到的 BREAKOUT 信号列表
        """
        signals = []

        if len(df) < self.total_window + self.atr_buffer:
            return signals

        # 创建检测器
        detector = BreakoutDetector(
            symbol=symbol,
            total_window=self.total_window,
            min_side_bars=self.min_side_bars,
            min_relative_height=self.min_relative_height,
            exceed_threshold=self.exceed_threshold,
            peak_supersede_threshold=self.peak_supersede_threshold,
            peak_measure=self.peak_measure,
            breakout_modes=self.breakout_modes,
            use_cache=False,
        )

        # 预计算 ATR
        atr_series = TechnicalIndicators.calculate_atr(
            df["high"], df["low"], df["close"], period=14
        )

        # 批量检测突破
        valid_start_index = self.atr_buffer
        breakout_infos = detector.batch_add_bars(
            df,
            return_breakouts=True,
            valid_start_index=valid_start_index,
            valid_end_index=end_index,
        )

        # 转换为 AbsoluteSignal
        for breakout_info in breakout_infos:
            # 计算完整特征
            breakout = self.feature_calculator.enrich_breakout(
                df=df,
                breakout_info=breakout_info,
                symbol=symbol,
                detector=detector,
                atr_series=atr_series,
            )

            signal = AbsoluteSignal(
                symbol=symbol,
                date=breakout.date,
                signal_type=SignalType.BREAKOUT,
                price=float(breakout.price),
                details={
                    "pk_num": int(breakout.num_peaks_broken),
                    "volume_ratio": round(float(breakout.volume_surge_ratio), 2),
                    "breakout_type": breakout.breakout_type,
                    # 保存完整的 Peak 信息，用于 UI 绘制
                    "peaks": [
                        {
                            "index": peak.index,
                            "price": peak.price,
                            "date": peak.date.isoformat(),
                            "id": peak.id,
                        }
                        for peak in breakout.broken_peaks
                    ],
                    # 支撑状态（由 SupportAnalyzer 填充）
                    "support_status": None,
                },
            )
            signals.append(signal)

        return signals
