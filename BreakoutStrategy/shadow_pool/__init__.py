"""
Shadow Pool - 无过滤数据收集模块

用于收集突破后行为数据，为"由简入繁"规则迭代提供数据基础。

核心特点:
- 独立计算模式：每个突破独立计算 MFE/MAE，无时间驱动循环
- 简单过滤：调用方直接过滤 bo.date 和 bo.price
- 数据导向：输出可分析的 MFE/MAE 数据集

组件:
- ShadowResult: 完整跟踪结果（含 MFE/MAE）
- compute_shadow_result: 纯函数，计算单个突破的指标
- ShadowBacktestEngine: 批量计算引擎
"""

from .models import ShadowEntry, ShadowResult
from .calculator import compute_shadow_result
from .engine import ShadowBacktestEngine

__all__ = [
    'ShadowEntry',
    'ShadowResult',
    'compute_shadow_result',
    'ShadowBacktestEngine',
]
