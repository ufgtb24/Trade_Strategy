"""
绝对信号检测模块

绝对信号是反映市场真实意图的实质性事件：
- 不依赖人为定义的参数（如均线周期）
- 代表大资金入场或重大事件驱动
- 在力量震荡后呈现稳定控制

支持的信号类型：
- BREAKOUT (BO): 突破前期高点
- HIGH_VOLUME (HV): 超大成交量
- BIG_YANG (BY): 大阳线
- DOUBLE_TROUGH (DT): 双底
"""

from .models import SignalType, AbsoluteSignal, SignalStats
from .aggregator import SignalAggregator
from .scanner import AbsoluteSignalScanner, scan_single_stock

__all__ = [
    "SignalType",
    "AbsoluteSignal",
    "SignalStats",
    "SignalAggregator",
    "AbsoluteSignalScanner",
    "scan_single_stock",
]
