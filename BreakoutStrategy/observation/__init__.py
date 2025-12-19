"""
观察池模块 (Observation Pool)

提供突破后的股票观察和买入信号检测功能，支持：
- 回测场景：虚拟时间推进、内存存储
- 实盘场景：真实时间、数据库持久化（预留）

核心组件：
- PoolEntry: 观察池条目数据结构
- PoolManager: 双池管理器（实时池 + 日K池）
- BuySignal: 买入信号

架构模式：
- 策略模式：时间管理（ITimeProvider）、存储（IPoolStorage）
- 模板方法：池操作骨架（ObservationPoolBase）
- 事件驱动：池状态变化通知（PoolEvent）

使用示例（回测）：
    from datetime import date
    from BreakoutStrategy.observation import create_backtest_pool_manager

    # 创建回测用观察池管理器
    pool_mgr = create_backtest_pool_manager(
        start_date=date(2024, 1, 1),
        config={'daily_observation_days': 30}
    )

    # 添加突破
    pool_mgr.add_from_breakout(breakout)

    # 每日推进（处理超时转换）
    pool_mgr.advance_day()

    # 检查买入信号
    signals = pool_mgr.check_buy_signals(price_data)

使用示例（实盘预留）：
    from BreakoutStrategy.observation import create_live_pool_manager

    # 创建实盘用观察池管理器
    pool_mgr = create_live_pool_manager(db_manager=my_db)

    # 注册事件监听
    pool_mgr.add_event_listener(my_handler)
"""
from datetime import date
from typing import Optional

# 数据结构
from .pool_entry import PoolEntry
from .signals import BuySignal, PoolEvent, PoolEventType, SellSignal

# 抽象接口
from .interfaces import (
    ITimeProvider,
    IPoolStorage,
    IQuoteSubscriber,
    IPoolObserver,
    QuoteData,
)

# 策略实现
from .strategies import (
    BacktestTimeProvider,
    LiveTimeProvider,
    MemoryStorage,
    DatabaseStorage,
)

# 核心类
from .pool_base import ObservationPoolBase
from .pool_manager import PoolManager


__all__ = [
    # 数据结构
    'PoolEntry',
    'BuySignal',
    'SellSignal',
    'PoolEvent',
    'PoolEventType',

    # 抽象接口
    'ITimeProvider',
    'IPoolStorage',
    'IQuoteSubscriber',
    'IPoolObserver',
    'QuoteData',

    # 策略实现
    'BacktestTimeProvider',
    'LiveTimeProvider',
    'MemoryStorage',
    'DatabaseStorage',

    # 核心类
    'ObservationPoolBase',
    'PoolManager',

    # 工厂函数
    'create_backtest_pool_manager',
    'create_live_pool_manager',
]


# ===== 工厂函数 =====

def create_backtest_pool_manager(start_date: date,
                                  config: Optional[dict] = None) -> PoolManager:
    """
    创建回测用的观察池管理器

    特点：
    - 使用虚拟时间，支持 advance_day() 推进
    - 使用内存存储，快速读写
    - 适合批量回测验证策略

    Args:
        start_date: 回测起始日期
        config: 配置参数
            - realtime_observation_days: 实时池观察天数，默认1
            - daily_observation_days: 日K池观察天数，默认30
            - min_quality_score: 最低质量评分阈值，默认0
            - buy_confirm_threshold: 买入确认阈值，默认0.02

    Returns:
        配置好的 PoolManager 实例

    使用示例：
        pool_mgr = create_backtest_pool_manager(date(2024, 1, 1))

        # 模拟回测循环
        for day in trading_days:
            pool_mgr.add_from_breakout(today_breakouts)
            signals = pool_mgr.check_buy_signals(price_data)
            pool_mgr.advance_day()
    """
    time_provider = BacktestTimeProvider(start_date)
    storage = MemoryStorage()
    return PoolManager(time_provider, storage, config)


def create_live_pool_manager(db_manager=None,
                              config: Optional[dict] = None) -> PoolManager:
    """
    创建实盘用的观察池管理器

    特点：
    - 使用系统真实时间
    - 使用数据库存储，支持持久化
    - 支持重启恢复

    注意：
        当前为预留实现。如果不提供 db_manager，
        将使用内存存储作为后备（数据不持久化）。

    Args:
        db_manager: 数据库管理器实例（预留）
        config: 配置参数

    Returns:
        配置好的 PoolManager 实例

    使用示例：
        pool_mgr = create_live_pool_manager(db_manager=my_db)

        # 注册买入信号监听
        pool_mgr.add_event_listener(on_buy_signal)
    """
    time_provider = LiveTimeProvider()
    storage = DatabaseStorage(db_manager)
    return PoolManager(time_provider, storage, config)
