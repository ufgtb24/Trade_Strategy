"""
存储策略实现

提供不同场景下的存储方式：
- MemoryStorage: 内存存储，适合回测（快速、无持久化）
- DatabaseStorage: 数据库存储，适合实盘（持久化、重启恢复）
"""
from datetime import datetime
from typing import Dict, List, Optional

from ..interfaces import IPoolStorage
from ..pool_entry import PoolEntry


class MemoryStorage(IPoolStorage):
    """
    内存存储

    使用字典在内存中存储池数据。适合回测场景：
    - 快速读写
    - 无需持久化
    - 进程结束后数据丢失

    使用示例：
        storage = MemoryStorage()
        storage.save('realtime', [entry1, entry2])
        entries = storage.load('realtime')
    """

    def __init__(self):
        """初始化内存存储"""
        self._data: Dict[str, Dict[str, PoolEntry]] = {
            'realtime': {},
            'daily': {}
        }

    def save(self, pool_type: str, entries: List[PoolEntry]) -> None:
        """
        保存池状态（覆盖模式）

        Args:
            pool_type: 池类型 ('realtime' 或 'daily')
            entries: 要保存的条目列表
        """
        self._ensure_pool_type(pool_type)
        self._data[pool_type] = {e.symbol: e for e in entries}

    def load(self, pool_type: str, status: Optional[str] = 'active') -> List[PoolEntry]:
        """
        加载池状态

        Args:
            pool_type: 池类型 ('realtime' 或 'daily')
            status: 状态过滤，None 表示加载所有状态

        Returns:
            符合条件的条目列表
        """
        self._ensure_pool_type(pool_type)
        entries = list(self._data.get(pool_type, {}).values())
        if status:
            entries = [e for e in entries if e.status == status]
        return entries

    def update_entry(self, pool_type: str, entry: PoolEntry) -> bool:
        """
        更新单个条目

        Args:
            pool_type: 池类型
            entry: 要更新的条目

        Returns:
            是否更新成功
        """
        self._ensure_pool_type(pool_type)
        if entry.symbol in self._data.get(pool_type, {}):
            entry.updated_at = datetime.now()
            self._data[pool_type][entry.symbol] = entry
            return True
        return False

    def delete_entry(self, pool_type: str, symbol: str) -> bool:
        """
        删除单个条目

        Args:
            pool_type: 池类型
            symbol: 股票代码

        Returns:
            是否删除成功
        """
        self._ensure_pool_type(pool_type)
        if symbol in self._data.get(pool_type, {}):
            del self._data[pool_type][symbol]
            return True
        return False

    def is_persistent(self) -> bool:
        """返回 False，内存存储不持久化"""
        return False

    def clear(self, pool_type: Optional[str] = None) -> None:
        """
        清空存储

        Args:
            pool_type: 指定池类型，None 表示清空所有池
        """
        if pool_type is None:
            self._data = {'realtime': {}, 'daily': {}}
        elif pool_type in self._data:
            self._data[pool_type] = {}

    def _ensure_pool_type(self, pool_type: str) -> None:
        """确保池类型存在"""
        if pool_type not in self._data:
            self._data[pool_type] = {}

    def get_count(self, pool_type: Optional[str] = None) -> int:
        """
        获取条目数量

        Args:
            pool_type: 指定池类型，None 表示所有池

        Returns:
            条目数量
        """
        if pool_type:
            return len(self._data.get(pool_type, {}))
        return sum(len(pool) for pool in self._data.values())

    def __repr__(self) -> str:
        counts = {k: len(v) for k, v in self._data.items()}
        return f"MemoryStorage(counts={counts})"


class DatabaseStorage(IPoolStorage):
    """
    数据库存储（实盘预留）

    使用数据库持久化存储池数据。适合实盘场景：
    - 数据持久化
    - 支持重启恢复
    - 支持历史查询

    注意：
        当前为预留实现，数据库管理器接入后需要补充具体逻辑。

    使用示例：
        storage = DatabaseStorage(db_manager)
        storage.save('realtime', [entry1, entry2])
        entries = storage.load('realtime')
    """

    def __init__(self, db_manager=None):
        """
        初始化数据库存储

        Args:
            db_manager: 数据库管理器实例（预留）
        """
        self.db = db_manager
        # 如果没有提供 db_manager，使用内存备份
        self._fallback = MemoryStorage() if db_manager is None else None

    def save(self, pool_type: str, entries: List[PoolEntry]) -> None:
        """
        保存池状态

        Args:
            pool_type: 池类型
            entries: 要保存的条目列表
        """
        if self._fallback:
            # 无数据库时使用内存备份
            self._fallback.save(pool_type, entries)
            return

        # TODO: 实现数据库保存逻辑
        # table = f'observation_pool_{pool_type}'
        # for entry in entries:
        #     self.db.upsert(table, entry.to_db_dict(), ['symbol'])
        print(f"[DatabaseStorage] save {len(entries)} entries to {pool_type} (not implemented)")

    def load(self, pool_type: str, status: Optional[str] = 'active') -> List[PoolEntry]:
        """
        加载池状态

        Args:
            pool_type: 池类型
            status: 状态过滤

        Returns:
            符合条件的条目列表
        """
        if self._fallback:
            return self._fallback.load(pool_type, status)

        # TODO: 实现数据库加载逻辑
        # table = f'observation_pool_{pool_type}'
        # if status:
        #     rows = self.db.query(f"SELECT * FROM {table} WHERE status = ?", (status,))
        # else:
        #     rows = self.db.query(f"SELECT * FROM {table}")
        # return [PoolEntry.from_db_dict(row) for row in rows]
        print(f"[DatabaseStorage] load from {pool_type} (not implemented)")
        return []

    def update_entry(self, pool_type: str, entry: PoolEntry) -> bool:
        """
        更新单个条目

        Args:
            pool_type: 池类型
            entry: 要更新的条目

        Returns:
            是否更新成功
        """
        if self._fallback:
            return self._fallback.update_entry(pool_type, entry)

        # TODO: 实现数据库更新逻辑
        # table = f'observation_pool_{pool_type}'
        # entry.updated_at = datetime.now()
        # count = self.db.update(table, entry.to_db_dict(), {'symbol': entry.symbol})
        # return count > 0
        print(f"[DatabaseStorage] update {entry.symbol} in {pool_type} (not implemented)")
        return False

    def delete_entry(self, pool_type: str, symbol: str) -> bool:
        """
        删除单个条目

        Args:
            pool_type: 池类型
            symbol: 股票代码

        Returns:
            是否删除成功
        """
        if self._fallback:
            return self._fallback.delete_entry(pool_type, symbol)

        # TODO: 实现数据库删除逻辑
        # table = f'observation_pool_{pool_type}'
        # count = self.db.delete(table, {'symbol': symbol})
        # return count > 0
        print(f"[DatabaseStorage] delete {symbol} from {pool_type} (not implemented)")
        return False

    def is_persistent(self) -> bool:
        """返回 True，数据库存储是持久化的"""
        return self.db is not None

    def clear(self, pool_type: Optional[str] = None) -> None:
        """
        清空存储

        Args:
            pool_type: 指定池类型，None 表示清空所有池
        """
        if self._fallback:
            self._fallback.clear(pool_type)
            return

        # TODO: 实现数据库清空逻辑
        # if pool_type:
        #     self.db.execute(f"DELETE FROM observation_pool_{pool_type}")
        # else:
        #     self.db.execute("DELETE FROM observation_pool_realtime")
        #     self.db.execute("DELETE FROM observation_pool_daily")
        print(f"[DatabaseStorage] clear {pool_type or 'all'} (not implemented)")

    def __repr__(self) -> str:
        if self._fallback:
            return f"DatabaseStorage(fallback={self._fallback})"
        return f"DatabaseStorage(db={self.db})"
