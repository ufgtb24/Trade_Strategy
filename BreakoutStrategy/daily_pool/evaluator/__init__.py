"""
评估器模块

DailyPoolEvaluator 协调三个分析器和状态机:
- 调用分析器获取证据
- 聚合证据
- 驱动状态机
- 生成买入信号
"""
from .daily_evaluator import DailyPoolEvaluator, PhaseEvaluation

__all__ = [
    'DailyPoolEvaluator',
    'PhaseEvaluation',
]
