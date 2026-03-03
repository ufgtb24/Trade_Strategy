"""
绝对信号数据模型

数据结构：
- SignalType: 信号类型枚举
- AbsoluteSignal: 单个绝对信号
- SignalStats: 股票信号统计结果
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional


class SignalType(Enum):
    """信号类型枚举"""
    BREAKOUT = "B"      # 突破前期高点
    HIGH_VOLUME = "V"   # 超大成交量
    BIG_YANG = "Y"      # 大阳线
    DOUBLE_TROUGH = "D" # 双底（带反弹确认）


@dataclass
class AbsoluteSignal:
    """
    绝对信号数据结构

    Attributes:
        symbol: 股票代码
        date: 信号发生日期
        signal_type: 信号类型
        price: 信号发生时的收盘价
        strength: 信号强度（默认 1.0，所有信号等权）
        details: 信号特有属性（不同类型信号有不同属性）
    """
    symbol: str
    date: date
    signal_type: SignalType
    price: float
    strength: float = 1.0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalStats:
    """
    股票信号统计结果

    Attributes:
        symbol: 股票代码
        signal_count: 统计窗口内信号总数
        signals: 信号列表
        latest_signal_date: 最近信号日期
        latest_price: 最新价格
    """
    symbol: str
    signal_count: int
    signals: List[AbsoluteSignal]
    latest_signal_date: date
    latest_price: float
    weighted_sum: float = 0.0        # 加权信号强度总和
    sequence_label: str = ""         # 信号序列标签 (纯展示)
    amplitude: float = 0.0           # lookback 窗口内价格振幅
    turbulent: bool = False          # 是否为异常走势股票（暴涨或暴涨-暴跌完成型）
    forward_return: Optional[float] = None  # 前瞻涨幅: scan_date close → N 天内最高价
