"""
突破选股策略系统

BreakthroughStrategy是一套完整的突破选股策略系统，用于美股市场的量化交易。

主要模块：
- analysis: 技术分析模块（凸点识别、突破检测、质量评分）
- data: 数据层（Tiger API数据获取、缓存）
- search: 搜索系统（历史突破搜索）
- observation: 观察池系统（双观察池管理）
- monitoring: 监测系统（实时监控）
- trading: 交易执行（Tiger API交易）
- risk: 风险管理（止盈止损）
- backtest: 回测系统（策略回测、参数优化）
- config: 配置管理
- utils: 工具与辅助
"""

__version__ = '0.1.0'
__author__ = 'Yu'
