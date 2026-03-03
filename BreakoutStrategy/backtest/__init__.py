"""
回测模块

基于观察池系统的回测引擎，支持：
- 从 JSON 扫描结果加载历史突破
- 按日期推进模拟交易
- 买入信号检测和执行
- 持仓管理（止盈/止损）
- 绩效统计

使用示例：
    from BreakoutStrategy.backtest import BacktestEngine, BacktestConfig

    config = BacktestConfig(initial_capital=100000)
    engine = BacktestEngine(config, 'outputs/scan.json', 'datasets/pkls')
    result = engine.run('2024-01-01', '2024-06-30')

    print(f"Total Return: {result.performance['total_return']:.2%}")
"""
from .engine import BacktestEngine, BacktestConfig, BacktestResult, Trade

__all__ = [
    'BacktestEngine',
    'BacktestConfig',
    'BacktestResult',
    'Trade',
]
