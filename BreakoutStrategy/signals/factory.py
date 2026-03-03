"""
检测器工厂函数

提供统一的检测器创建接口，确保批量扫描和分析模式使用相同的参数。
默认值与 configs/signals/absolute_signals.yaml 保持一致。
"""

from typing import List, Optional, TYPE_CHECKING

from .detectors import (
    BigYangDetector,
    BreakoutSignalDetector,
    DoubleTroughDetector,
    HighVolumeDetector,
)
from .detectors.base import SignalDetector

if TYPE_CHECKING:
    from BreakoutStrategy.analysis import SupportAnalyzer


def create_detectors(config: dict) -> List[SignalDetector]:
    """
    根据配置创建检测器列表

    统一的检测器创建入口，供批量扫描和分析模式复用。
    默认值与 configs/signals/absolute_signals.yaml 保持一致。

    Args:
        config: 配置字典

    Returns:
        检测器实例列表
    """
    detectors = []

    # 突破检测器
    bo_config = config.get("breakout", {})
    if bo_config.get("enabled", True):
        detectors.append(
            BreakoutSignalDetector(
                total_window=bo_config.get("total_window", 60),
                min_side_bars=bo_config.get("min_side_bars", 15),
                min_relative_height=bo_config.get("min_relative_height", 0.2),
                exceed_threshold=bo_config.get("exceed_threshold", 0.01),
                peak_supersede_threshold=bo_config.get("peak_supersede_threshold", 0.01),
                peak_measure=bo_config.get("peak_measure", "body_top"),
                breakout_modes=bo_config.get("breakout_modes", ["close"]),
            )
        )

    # 超大成交量检测器
    hv_config = config.get("high_volume", {})
    if hv_config.get("enabled", True):
        detectors.append(
            HighVolumeDetector(
                lookback_days=hv_config.get("lookback_days", 126),
                volume_ma_period=hv_config.get("volume_ma_period", 20),
                volume_multiplier=hv_config.get("volume_multiplier", 3.0),
            )
        )

    # 大阳线检测器
    by_config = config.get("big_yang", {})
    if by_config.get("enabled", True):
        detectors.append(
            BigYangDetector(
                volatility_lookback=by_config.get("volatility_lookback", 252),
                sigma_threshold=by_config.get("sigma_threshold", 2.0),
            )
        )

    # 双底检测器
    dt_config = config.get("double_trough", {})
    if dt_config.get("enabled", False):  # 默认禁用
        trough = dt_config.get("trough", {})
        support_trough = dt_config.get("support_trough", {})
        detectors.append(
            DoubleTroughDetector(
                min_of=dt_config.get("min_of", 126),
                first_bounce_atr=float(dt_config.get("first_bounce_atr", 1.5)),
                min_tr2_depth_atr=float(dt_config.get("min_tr2_depth_atr", 0.8)),
                max_gap_days=dt_config.get("max_gap_days", 60),
                min_recovery_atr=float(dt_config.get("min_recovery_atr", 0.1)),
                atr_period=int(dt_config.get("atr_period", 14)),
                trough_window=trough.get("window", 6),
                trough_min_side_bars=trough.get("min_side_bars", 2),
                tr1_measure=dt_config.get("tr1_measure", "low"),
                tr2_measure=dt_config.get("tr2_measure", "low"),
                bounce_high_measure=dt_config.get("bounce_high_measure", "close"),
                support_trough_window=support_trough.get("window"),
                support_trough_min_side_bars=support_trough.get("min_side_bars", 1),
            )
        )

    return detectors


def calculate_max_buffer_days(config: dict) -> int:
    """
    根据配置计算所有启用检测器的最大缓冲区需求

    各检测器缓冲区需求：
    - BreakoutSignalDetector: total_window + atr_buffer
    - HighVolumeDetector: max(lookback_days, volume_ma_period)
    - BigYangDetector: volatility_lookback
    - DoubleTroughDetector: min_of + atr_period

    Args:
        config: 配置字典（与 create_detectors 使用相同格式）

    Returns:
        最大缓冲区天数（交易日）
    """
    buffer_requirements = []

    # BreakoutSignalDetector: total_window + atr_buffer
    bo_config = config.get("breakout", {})
    if bo_config.get("enabled", True):
        total_window = bo_config.get("total_window", 60)
        atr_buffer = bo_config.get("atr_buffer", 14)
        buffer_requirements.append(total_window + atr_buffer)

    # HighVolumeDetector: max(lookback_days, volume_ma_period)
    hv_config = config.get("high_volume", {})
    if hv_config.get("enabled", True):
        lookback_days = hv_config.get("lookback_days", 126)
        volume_ma_period = hv_config.get("volume_ma_period", 20)
        buffer_requirements.append(max(lookback_days, volume_ma_period))

    # BigYangDetector: volatility_lookback
    by_config = config.get("big_yang", {})
    if by_config.get("enabled", True):
        volatility_lookback = by_config.get("volatility_lookback", 252)
        buffer_requirements.append(volatility_lookback)

    # DoubleTroughDetector: min_of + atr_period
    dt_config = config.get("double_trough", {})
    if dt_config.get("enabled", False):
        min_of = dt_config.get("min_of", 126)
        atr_period = dt_config.get("atr_period", 14)
        buffer_requirements.append(min_of + atr_period)

    # 返回最大值，如果没有启用的检测器则返回默认值
    return max(buffer_requirements) if buffer_requirements else 126


def create_support_analyzer(config: dict) -> Optional["SupportAnalyzer"]:
    """
    根据配置创建支撑分析器

    Args:
        config: 配置字典

    Returns:
        SupportAnalyzer 实例，如果禁用则返回 None
    """
    sa_config = config.get("support_analysis", {})
    if not sa_config.get("enabled", True):
        return None

    # 延迟导入避免循环依赖
    from BreakoutStrategy.analysis.support_analyzer import SupportAnalyzer

    return SupportAnalyzer(
        breakout_tolerance_pct=sa_config.get("breakout_tolerance_pct", 5.0),
        trough_tolerance_pct=sa_config.get("trough_tolerance_pct", 5.0),
        max_lookforward_days=sa_config.get("max_lookforward_days", 90),
    )
