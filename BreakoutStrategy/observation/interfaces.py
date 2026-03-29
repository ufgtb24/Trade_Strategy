"""
观察池抽象接口定义

定义策略模式所需的抽象接口，支持：
- 时间管理策略（回测 vs 实盘）
- 存储策略（内存 vs 数据库）
- 行情订阅策略（实盘预留）
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .pool_entry import PoolEntry


class ITimeProvider(ABC):
    """
    时间提供者接口

    抽象时间获取逻辑，使得：
    - 回测场景可以模拟时间推进
    - 实盘场景使用真实系统时间

    实现类：
    - BacktestTimeProvider: 可手动推进的虚拟时间
    - LiveTimeProvider: 使用系统真实时间
    """

    @abstractmethod
    def get_current_date(self) -> date:
        """
        获取当前日期

        Returns:
            当前日期（回测为虚拟日期，实盘为系统日期）
        """
        pass

    @abstractmethod
    def get_current_datetime(self) -> datetime:
        """
        获取当前日期时间

        Returns:
            当前日期时间
        """
        pass

    @abstractmethod
    def advance(self, days: int = 1) -> None:
        """
        推进时间（仅回测使用）

        Args:
            days: 推进的天数

        Raises:
            NotImplementedError: 实盘模式不支持时间推进
        """
        pass

    @abstractmethod
    def is_backtest_mode(self) -> bool:
        """
        是否为回测模式

        Returns:
            True 表示回测模式，False 表示实盘模式
        """
        pass


class IPoolStorage(ABC):
    """
    池存储接口

    抽象存储逻辑，使得：
    - 回测场景可以使用内存存储（快速、无需持久化）
    - 实盘场景可以使用数据库存储（持久化、重启恢复）

    实现类：
    - MemoryStorage: 内存字典存储
    - DatabaseStorage: 数据库存储（SQLite/PostgreSQL）
    """

    @abstractmethod
    def save(self, pool_type: str, entries: List['PoolEntry']) -> None:
        """
        保存池状态

        Args:
            pool_type: 池类型 ('realtime' 或 'daily')
            entries: 要保存的条目列表
        """
        pass

    @abstractmethod
    def load(self, pool_type: str, status: Optional[str] = 'active') -> List['PoolEntry']:
        """
        加载池状态

        Args:
            pool_type: 池类型 ('realtime' 或 'daily')
            status: 状态过滤，None 表示加载所有状态

        Returns:
            符合条件的条目列表
        """
        pass

    @abstractmethod
    def update_entry(self, pool_type: str, entry: 'PoolEntry') -> bool:
        """
        更新单个条目

        Args:
            pool_type: 池类型
            entry: 要更新的条目

        Returns:
            是否更新成功
        """
        pass

    @abstractmethod
    def delete_entry(self, pool_type: str, symbol: str) -> bool:
        """
        删除单个条目

        Args:
            pool_type: 池类型
            symbol: 股票代码

        Returns:
            是否删除成功
        """
        pass

    @abstractmethod
    def is_persistent(self) -> bool:
        """
        是否持久化存储

        Returns:
            True 表示数据会持久化到磁盘，False 表示仅在内存中
        """
        pass

    @abstractmethod
    def clear(self, pool_type: Optional[str] = None) -> None:
        """
        清空存储

        Args:
            pool_type: 指定池类型，None 表示清空所有池
        """
        pass


# ===== 行情相关接口（实盘预留）=====

@dataclass
class QuoteData:
    """
    行情数据标准结构

    用于实盘行情订阅的数据传递
    """
    symbol: str
    price: float
    high: float
    low: float
    open: float
    volume: int
    timestamp: datetime

    @property
    def is_valid(self) -> bool:
        """检查数据是否有效"""
        return self.price > 0 and self.volume >= 0


class IQuoteSubscriber(ABC):
    """
    行情订阅接口（实盘预留）

    定义实盘行情订阅的标准接口，具体实现需要：
    - 对接具体的行情 API（如 Tiger API）
    - 处理连接管理和重连
    - 实现回调分发

    实现类（未来）：
    - TigerQuoteSubscriber: Tiger API 行情订阅
    """

    @abstractmethod
    def subscribe(self,
                  symbols: List[str],
                  callback: Callable[[QuoteData], None]) -> bool:
        """
        订阅行情

        Args:
            symbols: 要订阅的股票代码列表
            callback: 行情回调函数

        Returns:
            是否订阅成功
        """
        pass

    @abstractmethod
    def unsubscribe(self, symbols: List[str]) -> bool:
        """
        取消订阅

        Args:
            symbols: 要取消订阅的股票代码列表

        Returns:
            是否取消成功
        """
        pass

    @abstractmethod
    def unsubscribe_all(self) -> bool:
        """
        取消所有订阅

        Returns:
            是否取消成功
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """
        检查连接状态

        Returns:
            是否已连接
        """
        pass

    @abstractmethod
    def get_subscribed_symbols(self) -> List[str]:
        """
        获取当前订阅的股票列表

        Returns:
            已订阅的股票代码列表
        """
        pass


class IPoolObserver(ABC):
    """
    观察池观察者接口（实盘预留）

    用于实现观察者模式，监听观察池状态变化

    实现类（未来）：
    - NotificationObserver: 发送通知
    - LoggingObserver: 记录日志
    - UIObserver: 更新UI显示
    """

    @abstractmethod
    def on_entry_added(self, entry: 'PoolEntry') -> None:
        """当条目被添加时调用"""
        pass

    @abstractmethod
    def on_entry_removed(self, entry: 'PoolEntry', reason: str) -> None:
        """当条目被移除时调用"""
        pass

    @abstractmethod
    def on_status_changed(self,
                          entry: 'PoolEntry',
                          old_status: str,
                          new_status: str) -> None:
        """当条目状态变化时调用"""
        pass

    @abstractmethod
    def on_buy_signal(self, entry: 'PoolEntry', signal_data: dict) -> None:
        """当产生买入信号时调用"""
        pass
