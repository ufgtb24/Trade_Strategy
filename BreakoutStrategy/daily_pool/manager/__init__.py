"""
池管理器模块

DailyPoolManager 管理条目生命周期:
- 添加新条目
- 协调每日评估
- 收集和分发信号
- 提供统计信息
"""
from .pool_manager import DailyPoolManager

__all__ = [
    'DailyPoolManager',
]
