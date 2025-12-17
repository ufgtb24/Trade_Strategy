"""
适配器模块

提供 JSON 扫描结果与观察池系统之间的数据转换功能：
- BreakoutJSONAdapter: JSON ↔ Breakout 对象转换
- EvaluationContextBuilder: 构建买入评估所需的上下文数据

使用示例：
    from BreakoutStrategy.observation.adapters import BreakoutJSONAdapter

    adapter = BreakoutJSONAdapter()
    result = adapter.load_single(symbol, stock_data, df)
    breakouts = result.breakouts
"""
from .json_adapter import BreakoutJSONAdapter, LoadResult
from .context_builder import EvaluationContextBuilder

__all__ = [
    'BreakoutJSONAdapter',
    'LoadResult',
    'EvaluationContextBuilder',
]
