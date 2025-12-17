"""
Simple Pool 模块

独立的日K级别观察池系统，基于即时判断模型（MVP 版本）。

核心组件:
- config: 配置类 (SimplePoolConfig)
- models: 数据模型 (PoolEntry, BuySignal)
- evaluator: 评估器 (SimpleEvaluator)
- manager: 管理器 (SimplePoolManager)
- utils: 工具函数 (ATR, 成交量等计算)
- backtest: 回测引擎 (SimpleBacktestEngine)

设计理念:
- 即时判断: 无状态机，每次评估独立
- 最简参数: 仅 4 个核心参数
- 三条件并行: 质量、稳定性、上涨趋势同时检查

使用方式:
    from BreakoutStrategy.simple_pool import SimplePoolManager, SimplePoolConfig

    config = SimplePoolConfig()
    manager = SimplePoolManager(config)

    entry = manager.add_entry(
        symbol="AAPL",
        breakout_date=date(2024, 1, 15),
        breakout_price=185.0,
        peak_price=187.5,
        initial_atr=2.5,
        quality_score=75.0
    )

    signals = manager.update_all(as_of_date, price_data)
"""
from .config import SimplePoolConfig
from .models import PoolEntry, BuySignal, SignalPerformance
from .evaluator import SimpleEvaluator, Evaluation
from .manager import SimplePoolManager
from .backtest import SimpleBacktestEngine, BacktestResult, compute_signal_performance

__all__ = [
    # 配置
    'SimplePoolConfig',
    # 数据模型
    'PoolEntry',
    'BuySignal',
    'SignalPerformance',
    # 评估器
    'SimpleEvaluator',
    'Evaluation',
    # 管理器
    'SimplePoolManager',
    # 回测
    'SimpleBacktestEngine',
    'BacktestResult',
    'compute_signal_performance',
]
