"""
分析器模块

三个独立的分析器，负责从价格数据中提取证据:
- PricePatternAnalyzer: 价格模式分析（回调深度、支撑位、企稳区间）
- VolatilityAnalyzer: 波动率分析（ATR序列、收敛分数）
- VolumeAnalyzer: 成交量分析（基准量、放量检测）

设计理念:
    分析器只计算"事实"，不做阈值判断。
    阈值判断由状态机根据配置执行。
"""
from .results import (
    SupportZone,
    ConsolidationRange,
    PricePatternResult,
    VolatilityResult,
    VolumeResult,
)
from .price_pattern import PricePatternAnalyzer
from .volatility import VolatilityAnalyzer
from .volume import VolumeAnalyzer

__all__ = [
    # 结果数据类
    'SupportZone',
    'ConsolidationRange',
    'PricePatternResult',
    'VolatilityResult',
    'VolumeResult',
    # 分析器
    'PricePatternAnalyzer',
    'VolatilityAnalyzer',
    'VolumeAnalyzer',
]
