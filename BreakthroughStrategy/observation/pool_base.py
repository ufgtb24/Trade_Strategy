"""
观察池基类

采用模板方法模式，定义池操作的骨架流程。
具体的时间管理和存储逻辑通过策略注入。
"""
from datetime import datetime
from typing import Dict, List, Optional

from .interfaces import ITimeProvider, IPoolStorage
from .pool_entry import PoolEntry


class ObservationPoolBase:
    """
    观察池基类

    采用模板方法模式，定义池操作的骨架流程：
    - add: 添加条目
    - get: 获取单个条目
    - get_all: 获取所有条目
    - update_status: 更新状态
    - remove: 移除条目
    - check_timeout: 检查超时

    通过策略注入实现：
    - 时间管理：ITimeProvider（回测 vs 实盘）
    - 存储方式：IPoolStorage（内存 vs 数据库）

    使用示例：
        # 创建回测用的实时观察池
        time_provider = BacktestTimeProvider(date(2024, 1, 1))
        storage = MemoryStorage()
        pool = ObservationPoolBase(
            pool_type='realtime',
            time_provider=time_provider,
            storage=storage,
            observation_days=1
        )

        # 添加条目
        pool.add(entry)

        # 检查超时
        timeout_entries = pool.check_timeout()
    """

    def __init__(self,
                 pool_type: str,
                 time_provider: ITimeProvider,
                 storage: IPoolStorage,
                 observation_days: int,
                 config: Optional[dict] = None):
        """
        初始化观察池基类

        Args:
            pool_type: 池类型 ('realtime' 或 'daily')
            time_provider: 时间提供者
            storage: 存储策略
            observation_days: 观察天数（超时阈值）
            config: 其他配置参数
        """
        self.pool_type = pool_type
        self.time_provider = time_provider
        self.storage = storage
        self.observation_days = observation_days
        self.config = config or {}

        # 内存缓存（加速访问）
        self._entries: Dict[str, PoolEntry] = {}

        # 加载已有状态
        self._load_state()

    # ===== 模板方法 =====

    def add(self, entry: PoolEntry) -> bool:
        """
        添加条目到池中

        流程：
        1. 执行前置检查（可覆写）
        2. 设置池类型和添加日期
        3. 添加到内存缓存
        4. 按需持久化

        Args:
            entry: 要添加的条目

        Returns:
            是否添加成功
        """
        if not self._pre_add_check(entry):
            return False

        entry.pool_type = self.pool_type
        entry.add_date = self.time_provider.get_current_date()
        entry.updated_at = datetime.now()

        self._entries[entry.symbol] = entry
        self._persist_if_needed()

        print(f"[{self.pool_type}] Added {entry.symbol} "
              f"(score={entry.quality_score:.2f}, "
              f"bt_date={entry.breakthrough_date})")
        return True

    def get(self, symbol: str) -> Optional[PoolEntry]:
        """
        获取单个条目

        Args:
            symbol: 股票代码

        Returns:
            条目对象，不存在时返回 None
        """
        return self._entries.get(symbol)

    def get_all(self, status: Optional[str] = 'active') -> List[PoolEntry]:
        """
        获取所有条目

        Args:
            status: 状态过滤，None 表示返回所有状态

        Returns:
            符合条件的条目列表
        """
        entries = list(self._entries.values())
        if status:
            entries = [e for e in entries if e.status == status]
        return entries

    def update_status(self, symbol: str, new_status: str) -> bool:
        """
        更新条目状态

        Args:
            symbol: 股票代码
            new_status: 新状态

        Returns:
            是否更新成功
        """
        if symbol not in self._entries:
            return False

        entry = self._entries[symbol]
        old_status = entry.status
        entry.status = new_status
        entry.updated_at = datetime.now()

        self._persist_if_needed()

        print(f"[{self.pool_type}] Updated {symbol} status: "
              f"{old_status} -> {new_status}")
        return True

    def remove(self, symbol: str) -> Optional[PoolEntry]:
        """
        从池中移除条目

        Args:
            symbol: 股票代码

        Returns:
            被移除的条目，不存在时返回 None
        """
        if symbol not in self._entries:
            return None

        entry = self._entries.pop(symbol)
        self._persist_if_needed()

        print(f"[{self.pool_type}] Removed {symbol}")
        return entry

    def check_timeout(self) -> List[PoolEntry]:
        """
        检查超时/过期的条目

        根据 observation_days 配置，检查所有活跃条目是否超时。
        超时的条目状态会被更新为 'timeout'（实时池）或 'expired'（日K池）。

        Returns:
            超时的条目列表
        """
        current_date = self.time_provider.get_current_date()
        timeout_entries = []

        for entry in list(self._entries.values()):
            if entry.status != 'active':
                continue

            days_since_add = (current_date - entry.add_date).days
            if days_since_add >= self.observation_days:
                # 根据池类型设置不同的超时状态
                timeout_status = 'timeout' if self.pool_type == 'realtime' else 'expired'
                entry.status = timeout_status
                entry.updated_at = datetime.now()
                timeout_entries.append(entry)

        if timeout_entries:
            self._persist_if_needed()
            print(f"[{self.pool_type}] Found {len(timeout_entries)} entries timeout/expired")

        return timeout_entries

    def contains(self, symbol: str) -> bool:
        """
        检查股票是否在池中

        Args:
            symbol: 股票代码

        Returns:
            是否存在
        """
        return symbol in self._entries

    def clear(self) -> int:
        """
        清空池

        Returns:
            清空前的条目数量
        """
        count = len(self._entries)
        self._entries.clear()
        self.storage.clear(self.pool_type)
        print(f"[{self.pool_type}] Cleared {count} entries")
        return count

    # ===== 钩子方法（可覆写）=====

    def _pre_add_check(self, entry: PoolEntry) -> bool:
        """
        添加前检查

        默认检查：股票是否已在池中
        子类可覆写以添加自定义检查逻辑

        Args:
            entry: 要添加的条目

        Returns:
            是否允许添加
        """
        if entry.symbol in self._entries:
            print(f"[{self.pool_type}] {entry.symbol} already in pool, skipping")
            return False
        return True

    def _persist_if_needed(self) -> None:
        """
        按需持久化

        将内存中的数据同步到存储层。
        对于内存存储，这是一个空操作。
        对于数据库存储，会写入数据库。
        """
        self.storage.save(self.pool_type, list(self._entries.values()))

    def _load_state(self) -> None:
        """
        从存储加载状态

        在初始化时调用，从存储层加载已有数据到内存缓存。
        """
        entries = self.storage.load(self.pool_type, status=None)
        self._entries = {e.symbol: e for e in entries}
        if entries:
            print(f"[{self.pool_type}] Loaded {len(self._entries)} entries from storage")

    # ===== 统计方法 =====

    def get_statistics(self) -> Dict:
        """
        获取池统计信息

        Returns:
            统计信息字典
        """
        all_entries = list(self._entries.values())
        active_entries = [e for e in all_entries if e.status == 'active']

        avg_quality = 0.0
        if active_entries:
            avg_quality = sum(e.quality_score for e in active_entries) / len(active_entries)

        return {
            'pool_type': self.pool_type,
            'total': len(all_entries),
            'active': len(active_entries),
            'bought': len([e for e in all_entries if e.status == 'bought']),
            'timeout': len([e for e in all_entries if e.status == 'timeout']),
            'expired': len([e for e in all_entries if e.status == 'expired']),
            'avg_quality_score': avg_quality,
            'observation_days': self.observation_days
        }

    @property
    def count(self) -> int:
        """当前条目数量"""
        return len(self._entries)

    @property
    def active_count(self) -> int:
        """活跃条目数量"""
        return len([e for e in self._entries.values() if e.status == 'active'])

    def __repr__(self) -> str:
        return (f"ObservationPoolBase(type={self.pool_type!r}, "
                f"count={self.count}, active={self.active_count})")

    def __len__(self) -> int:
        return self.count
