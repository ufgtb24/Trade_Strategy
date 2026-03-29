"""
回测引擎模块

DailyBacktestEngine 驱动历史数据回放:
- 管理回测时间线
- 收集回测指标
- 生成回测报告
"""
from .engine import DailyBacktestEngine, BacktestResult

__all__ = [
    'DailyBacktestEngine',
    'BacktestResult',
]
