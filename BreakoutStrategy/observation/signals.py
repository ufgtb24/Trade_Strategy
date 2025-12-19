"""
观察池信号与事件定义

定义买入信号、池事件等数据结构，用于：
- 买入信号的标准化传递
- 模块间的事件驱动通信
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .pool_entry import PoolEntry


class PoolEventType(Enum):
    """观察池事件类型"""
    ENTRY_ADDED = 'entry_added'       # 条目添加到池
    ENTRY_TIMEOUT = 'entry_timeout'   # 条目超时（实时池）
    ENTRY_EXPIRED = 'entry_expired'   # 条目过期（日K池）
    ENTRY_REMOVED = 'entry_removed'   # 条目被移除
    BUY_SIGNAL = 'buy_signal'         # 产生买入信号
    POOL_TRANSFER = 'pool_transfer'   # 池间转移


@dataclass
class PoolEvent:
    """
    观察池事件

    用于模块间的事件驱动通信，支持：
    - 条目状态变化通知
    - 买入信号传递
    - 池间转移追踪
    """
    event_type: PoolEventType
    entry: 'PoolEntry'
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (f"PoolEvent(type={self.event_type.value}, "
                f"symbol={self.entry.symbol}, "
                f"timestamp={self.timestamp.isoformat()})")


@dataclass
class BuySignal:
    """
    买入信号

    当观察池中的条目满足买入条件时生成，包含：
    - 信号基本信息（股票、日期、价格）
    - 信号强度和来源
    - 交易建议（入场价、止损价、仓位）
    """

    # ===== 信号基本信息 =====
    symbol: str
    signal_date: date
    signal_price: float

    # ===== 信号来源 =====
    entry: 'PoolEntry'
    reason: str  # 'realtime_confirmation' | 'daily_breakout' | 'pullback_entry'

    # ===== 信号强度 =====
    signal_strength: float = 0.0  # 0-1，由质量评分等因素决定

    # ===== 交易建议 =====
    suggested_entry_price: float = 0.0
    suggested_stop_loss: float = 0.0
    suggested_position_size_pct: float = 0.10  # 建议仓位比例

    # ===== 元数据 =====
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ===== 派生属性 =====

    @property
    def risk_reward_ratio(self) -> float:
        """风险收益比（假设目标收益为止损的2倍）"""
        if self.suggested_stop_loss <= 0 or self.suggested_entry_price <= 0:
            return 0.0
        risk = self.suggested_entry_price - self.suggested_stop_loss
        if risk <= 0:
            return 0.0
        # 假设目标收益为风险的2倍
        reward = risk * 2
        return reward / risk

    @property
    def stop_loss_pct(self) -> float:
        """止损幅度百分比"""
        if self.suggested_entry_price <= 0:
            return 0.0
        return (self.suggested_entry_price - self.suggested_stop_loss) / self.suggested_entry_price

    def __repr__(self) -> str:
        return (f"BuySignal(symbol={self.symbol!r}, "
                f"date={self.signal_date}, "
                f"price={self.signal_price:.2f}, "
                f"strength={self.signal_strength:.2f}, "
                f"reason={self.reason!r})")


@dataclass
class SellSignal:
    """
    卖出信号（预留）

    当持仓需要卖出时生成，包含：
    - 卖出原因（止损、止盈、其他）
    - 卖出建议
    """

    # ===== 信号基本信息 =====
    symbol: str
    signal_date: date
    signal_price: float

    # ===== 信号来源 =====
    reason: str  # 'stop_loss' | 'take_profit' | 'trailing_stop' | 'manual'

    # ===== 交易建议 =====
    suggested_sell_price: float = 0.0
    position_pct: float = 1.0  # 卖出仓位比例，默认全部

    # ===== 元数据 =====
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (f"SellSignal(symbol={self.symbol!r}, "
                f"date={self.signal_date}, "
                f"price={self.signal_price:.2f}, "
                f"reason={self.reason!r})")
