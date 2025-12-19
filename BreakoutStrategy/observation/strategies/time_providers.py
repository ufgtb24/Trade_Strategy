"""
时间提供者策略实现

提供不同场景下的时间管理：
- BacktestTimeProvider: 回测用，支持虚拟时间推进
- LiveTimeProvider: 实盘用，使用系统真实时间
"""
from datetime import date, datetime, timedelta
from typing import Optional

from ..interfaces import ITimeProvider


class BacktestTimeProvider(ITimeProvider):
    """
    回测时间提供者

    维护一个虚拟日期，支持手动推进。用于回测场景中
    模拟时间流逝，与观察池的超时检查配合使用。

    使用示例：
        time_provider = BacktestTimeProvider(date(2024, 1, 1))
        print(time_provider.get_current_date())  # 2024-01-01
        time_provider.advance(5)
        print(time_provider.get_current_date())  # 2024-01-06
    """

    def __init__(self, start_date: date):
        """
        初始化回测时间提供者

        Args:
            start_date: 回测起始日期
        """
        self._current_date = start_date
        self._start_date = start_date

    def get_current_date(self) -> date:
        """获取当前虚拟日期"""
        return self._current_date

    def get_current_datetime(self) -> datetime:
        """获取当前虚拟日期时间（设为当天 9:30 开盘时间）"""
        return datetime.combine(self._current_date, datetime.min.time().replace(hour=9, minute=30))

    def advance(self, days: int = 1) -> None:
        """
        推进虚拟时间

        Args:
            days: 推进的天数（必须为正数）

        Raises:
            ValueError: 如果 days <= 0
        """
        if days <= 0:
            raise ValueError(f"Days must be positive, got {days}")
        self._current_date += timedelta(days=days)

    def is_backtest_mode(self) -> bool:
        """返回 True，表示回测模式"""
        return True

    def reset(self) -> None:
        """重置到起始日期"""
        self._current_date = self._start_date

    def set_date(self, new_date: date) -> None:
        """
        直接设置当前日期

        Args:
            new_date: 新的日期
        """
        self._current_date = new_date

    @property
    def start_date(self) -> date:
        """获取起始日期"""
        return self._start_date

    @property
    def days_elapsed(self) -> int:
        """已经过的天数"""
        return (self._current_date - self._start_date).days

    def __repr__(self) -> str:
        return f"BacktestTimeProvider(current={self._current_date}, start={self._start_date})"


class LiveTimeProvider(ITimeProvider):
    """
    实盘时间提供者

    使用系统真实时间，不支持时间推进。用于实盘场景中
    获取当前真实日期。

    使用示例：
        time_provider = LiveTimeProvider()
        print(time_provider.get_current_date())  # 今天的日期
    """

    def __init__(self, timezone: Optional[str] = None):
        """
        初始化实盘时间提供者

        Args:
            timezone: 时区（预留，暂未实现）
        """
        self._timezone = timezone

    def get_current_date(self) -> date:
        """获取系统当前日期"""
        return datetime.now().date()

    def get_current_datetime(self) -> datetime:
        """获取系统当前日期时间"""
        return datetime.now()

    def advance(self, days: int = 1) -> None:
        """
        实盘模式不支持时间推进

        Raises:
            NotImplementedError: 总是抛出
        """
        raise NotImplementedError("Live mode does not support time advancement")

    def is_backtest_mode(self) -> bool:
        """返回 False，表示实盘模式"""
        return False

    def __repr__(self) -> str:
        return f"LiveTimeProvider(current={self.get_current_date()})"
