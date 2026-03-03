"""
Daily 池模块

独立的日K级别观察池系统，基于阶段状态机模型评估突破后的"回调-企稳-再启动"过程。

核心组件:
- models: 数据模型 (Phase, DailyPoolEntry, DailySignal, PhaseHistory)
- config: 配置系统 (DailyPoolConfig, YAML加载)
- state_machine: 阶段状态机 (PhaseStateMachine)
- analyzers: 分析器 (PricePattern, Volatility, Volume)
- evaluator: 评估器 (DailyPoolEvaluator)
- manager: 管理器 (DailyPoolManager)
- backtest: 回测引擎 (DailyBacktestEngine)

设计理念:
- 过程优于状态：阶段状态机替代加权评分，准确建模"回调-企稳-再启动"过程
- 证据聚合模式：三个分析器独立分析，状态机综合判断
- ATR标准化：所有阈值以ATR为单位，自动适应不同股票
"""
from .models import Phase, DailyPoolEntry, DailySignal, SignalType, SignalStrength
from .models import PhaseHistory, PhaseTransition
from .config import DailyPoolConfig, load_config
from .state_machine import AnalysisEvidence, PhaseTransitionResult, PhaseStateMachine
from .analyzers import (
    SupportZone, ConsolidationRange, PricePatternResult, VolatilityResult, VolumeResult,
    PricePatternAnalyzer, VolatilityAnalyzer, VolumeAnalyzer
)
from .evaluator import DailyPoolEvaluator, PhaseEvaluation
from .manager import DailyPoolManager
from .backtest import DailyBacktestEngine, BacktestResult

__all__ = [
    # 数据模型
    'Phase',
    'DailyPoolEntry',
    'DailySignal',
    'SignalType',
    'SignalStrength',
    'PhaseHistory',
    'PhaseTransition',
    # 配置
    'DailyPoolConfig',
    'load_config',
    # 状态机
    'AnalysisEvidence',
    'PhaseTransitionResult',
    'PhaseStateMachine',
    # 分析器结果
    'SupportZone',
    'ConsolidationRange',
    'PricePatternResult',
    'VolatilityResult',
    'VolumeResult',
    # 分析器
    'PricePatternAnalyzer',
    'VolatilityAnalyzer',
    'VolumeAnalyzer',
    # 评估器
    'DailyPoolEvaluator',
    'PhaseEvaluation',
    # 管理器
    'DailyPoolManager',
    # 回测
    'DailyBacktestEngine',
    'BacktestResult',
]
