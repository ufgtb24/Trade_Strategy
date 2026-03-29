"""
买入条件评估模块

提供多维度买入时机评估系统：
- 时间窗口评估：判断当前时间是否处于最佳买入窗口
- 价格确认评估：判断价格是否在确认区间
- 成交量验证评估：判断成交量是否支持突破有效性
- 风险过滤评估：检查各类风险条件

主要接口：
- CompositeBuyEvaluator: 组合评估器，整合四维度评估
- BuyConditionConfig: 完整配置类
- EvaluationResult: 评估结果
- EvaluationAction: 评估动作枚举
"""
from .config import (
    BuyConditionConfig,
    TimeWindowConfig,
    PriceConfirmConfig,
    VolumeVerifyConfig,
    RiskFilterConfig,
    ScoringConfig,
)
from .result import (
    EvaluationAction,
    EvaluationResult,
    DimensionScore,
)
from .base import IBuyConditionEvaluator, BaseEvaluator
from .composite import CompositeBuyEvaluator
from .components import (
    TimeWindowEvaluator,
    PriceConfirmEvaluator,
    VolumeVerifyEvaluator,
    RiskFilterEvaluator,
)

__all__ = [
    # 配置类
    'BuyConditionConfig',
    'TimeWindowConfig',
    'PriceConfirmConfig',
    'VolumeVerifyConfig',
    'RiskFilterConfig',
    'ScoringConfig',
    # 结果类
    'EvaluationAction',
    'EvaluationResult',
    'DimensionScore',
    # 接口和基类
    'IBuyConditionEvaluator',
    'BaseEvaluator',
    # 组合评估器
    'CompositeBuyEvaluator',
    # 组件评估器
    'TimeWindowEvaluator',
    'PriceConfirmEvaluator',
    'VolumeVerifyEvaluator',
    'RiskFilterEvaluator',
]
