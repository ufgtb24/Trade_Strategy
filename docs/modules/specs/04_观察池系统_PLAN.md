# 观察池系统技术设计文档

**模块路径**：`BreakoutStrategy/observation/`
**创建日期**：2025-11-16

---

## 一、模块概述

观察池系统管理双观察池（实时观察池、日K观察池），负责股票的加入、移除、池间转换和循环跟踪。

**核心职责**：
1. 管理实时观察池（监测当日突破）
2. 管理日K观察池（监测突破后回落）
3. 实现池间转换逻辑
4. 支持循环跟踪（止盈止损后重新加入）
5. 持久化存储观察池状态

**依赖**：
- `utils.database`：数据库存储
- `config`：观察池参数

---

## 二、模块架构

```
BreakoutStrategy/observation/
├── __init__.py
├── pool_manager.py           # PoolManager - 观察池管理器（总控）
├── realtime_pool.py          # RealtimePool - 实时观察池
├── daily_pool.py             # DailyPool - 日K观察池
└── pool_entry.py             # PoolEntry - 观察池条目数据结构
```

---

## 三、核心数据结构

### 3.1 PoolEntry（观察池条目）

```python
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Optional

@dataclass
class PoolEntry:
    """观察池条目"""
    # 基本信息
    symbol: str                      # 股票代码
    add_date: date                   # 加入日期
    breakout_date: date          # 突破日期

    # 突破信息
    breakout_info: Dict = field(default_factory=dict)  # {price, type, quality_score, ...}

    # 凸点信息
    peak_info: Dict = field(default_factory=dict)          # {date, price, quality_score, ...}

    # 状态
    status: str = 'active'           # 'active', 'bought', 'timeout', 'expired'
    retry_count: int = 0             # 重试次数（循环跟踪）

    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # 数据库ID（持久化后赋值）
    id: Optional[int] = None

    def to_dict(self) -> Dict:
        """转换为字典（用于存储）"""
        return {
            'symbol': self.symbol,
            'add_date': self.add_date.isoformat(),
            'breakout_date': self.breakout_date.isoformat(),
            'breakout_info': str(self.breakout_info),
            'peak_info': str(self.peak_info),
            'status': self.status,
            'retry_count': self.retry_count,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'PoolEntry':
        """从字典创建PoolEntry"""
        import ast
        return cls(
            id=data.get('id'),
            symbol=data['symbol'],
            add_date=date.fromisoformat(data['add_date']),
            breakout_date=date.fromisoformat(data['breakout_date']),
            breakout_info=ast.literal_eval(data['breakout_info']),
            peak_info=ast.literal_eval(data['peak_info']),
            status=data['status'],
            retry_count=data['retry_count'],
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at'])
        )
```

---

## 四、RealtimePool（实时观察池）

### 4.1 功能需求

- 监测当日突破的股票
- 观察期限：`REALTIME_OBSERVATION_DAYS`（默认1天）
- 退出条件：触发买入、超时

### 4.2 实现

```python
from typing import List, Optional, Dict
from datetime import date, datetime, timedelta

class RealtimePool:
    """实时观察池"""

    def __init__(self, db_manager=None, config=None):
        """
        初始化实时观察池

        Args:
            db_manager: DatabaseManager实例
            config: 配置字典
        """
        if db_manager is None:
            from BreakoutStrategy.utils.database import DatabaseManager
            self.db = DatabaseManager.get_instance()
        else:
            self.db = db

        if config is None:
            from BreakoutStrategy.config import ConfigManager
            cfg = ConfigManager.get_instance()
            self.observation_days = cfg.get('time.realtime_observation_days', 1)
        else:
            self.observation_days = config.get('observation_days', 1)

        from BreakoutStrategy.utils.logger import Logger
        self.logger = Logger.get_logger('observation.realtime_pool')

    def add(self, entry: PoolEntry) -> bool:
        """
        添加股票到实时观察池

        Args:
            entry: 观察池条目

        Returns:
            是否成功添加
        """
        try:
            # 检查是否已存在
            existing = self.db.query(
                "SELECT id FROM observation_pool_realtime WHERE symbol = ? AND status = 'active'",
                (entry.symbol,)
            )

            if existing:
                self.logger.warning(f"{entry.symbol} already in realtime pool")
                return False

            # 插入数据库
            entry_dict = entry.to_dict()
            entry.id = self.db.insert('observation_pool_realtime', entry_dict)

            self.logger.info(f"Added {entry.symbol} to realtime pool (breakout: {entry.breakout_date})")
            return True

        except Exception as e:
            self.logger.error(f"Failed to add {entry.symbol} to realtime pool: {e}")
            return False

    def get_all(self, status: str = 'active') -> List[PoolEntry]:
        """
        获取观察池中的所有股票

        Args:
            status: 过滤状态 ('active', 'bought', 'timeout'，或None表示全部)

        Returns:
            PoolEntry列表
        """
        if status:
            rows = self.db.query(
                "SELECT * FROM observation_pool_realtime WHERE status = ?",
                (status,)
            )
        else:
            rows = self.db.query("SELECT * FROM observation_pool_realtime")

        return [PoolEntry.from_dict(row) for row in rows]

    def get_by_symbol(self, symbol: str) -> Optional[PoolEntry]:
        """获取指定股票的条目"""
        rows = self.db.query(
            "SELECT * FROM observation_pool_realtime WHERE symbol = ? AND status = 'active'",
            (symbol,)
        )

        if rows:
            return PoolEntry.from_dict(rows[0])
        return None

    def update_status(self, symbol: str, new_status: str) -> bool:
        """
        更新状态

        Args:
            symbol: 股票代码
            new_status: 新状态

        Returns:
            是否成功更新
        """
        try:
            count = self.db.update(
                'observation_pool_realtime',
                {'status': new_status, 'updated_at': datetime.now().isoformat()},
                {'symbol': symbol, 'status': 'active'}
            )

            if count > 0:
                self.logger.info(f"Updated {symbol} status: active → {new_status}")
                return True
            else:
                self.logger.warning(f"{symbol} not found or already updated")
                return False

        except Exception as e:
            self.logger.error(f"Failed to update {symbol} status: {e}")
            return False

    def remove(self, symbol: str) -> bool:
        """从观察池移除股票"""
        try:
            count = self.db.delete('observation_pool_realtime', {'symbol': symbol, 'status': 'active'})

            if count > 0:
                self.logger.info(f"Removed {symbol} from realtime pool")
                return True
            return False

        except Exception as e:
            self.logger.error(f"Failed to remove {symbol}: {e}")
            return False

    def check_timeout(self, current_date: date) -> List[PoolEntry]:
        """
        检查超时的股票

        Args:
            current_date: 当前日期

        Returns:
            超时的PoolEntry列表
        """
        timeout_entries = []

        for entry in self.get_all(status='active'):
            # 计算观察天数
            days_since_add = (current_date - entry.add_date).days

            if days_since_add >= self.observation_days:
                # 超时
                self.update_status(entry.symbol, 'timeout')
                timeout_entries.append(entry)

        if timeout_entries:
            self.logger.info(f"Found {len(timeout_entries)} timeout entries")

        return timeout_entries
```

---

## 五、DailyPool（日K观察池）

### 5.1 功能需求

- 监测突破后回落的股票
- 观察期限：`DAILY_OBSERVATION_DAYS`（默认30天）
- 退出条件：触发买入、观察期满

### 5.2 实现

```python
class DailyPool:
    """日K观察池"""

    def __init__(self, db_manager=None, config=None):
        """初始化日K观察池"""
        if db_manager is None:
            from BreakoutStrategy.utils.database import DatabaseManager
            self.db = DatabaseManager.get_instance()
        else:
            self.db = db_manager

        if config is None:
            from BreakoutStrategy.config import ConfigManager
            cfg = ConfigManager.get_instance()
            self.observation_days = cfg.get('time.daily_observation_days', 30)
        else:
            self.observation_days = config.get('observation_days', 30)

        from BreakoutStrategy.utils.logger import Logger
        self.logger = Logger.get_logger('observation.daily_pool')

    def add(self, entry: PoolEntry, allow_duplicate: bool = False) -> bool:
        """
        添加股票到日K观察池

        Args:
            entry: 观察池条目
            allow_duplicate: 是否允许重复添加（循环跟踪）

        Returns:
            是否成功添加
        """
        try:
            # 检查是否已存在
            if not allow_duplicate:
                existing = self.db.query(
                    "SELECT id FROM observation_pool_daily WHERE symbol = ? AND status = 'active'",
                    (entry.symbol,)
                )

                if existing:
                    self.logger.warning(f"{entry.symbol} already in daily pool")
                    return False

            # 插入数据库
            entry_dict = entry.to_dict()
            entry.id = self.db.insert('observation_pool_daily', entry_dict)

            self.logger.info(f"Added {entry.symbol} to daily pool (retry: {entry.retry_count})")
            return True

        except Exception as e:
            self.logger.error(f"Failed to add {entry.symbol} to daily pool: {e}")
            return False

    def get_all(self, status: str = 'active') -> List[PoolEntry]:
        """获取观察池中的所有股票"""
        if status:
            rows = self.db.query(
                "SELECT * FROM observation_pool_daily WHERE status = ?",
                (status,)
            )
        else:
            rows = self.db.query("SELECT * FROM observation_pool_daily")

        return [PoolEntry.from_dict(row) for row in rows]

    def get_by_symbol(self, symbol: str) -> Optional[PoolEntry]:
        """获取指定股票的条目"""
        rows = self.db.query(
            "SELECT * FROM observation_pool_daily WHERE symbol = ? AND status = 'active'",
            (symbol,)
        )

        if rows:
            return PoolEntry.from_dict(rows[0])
        return None

    def update_status(self, symbol: str, new_status: str) -> bool:
        """更新状态"""
        try:
            count = self.db.update(
                'observation_pool_daily',
                {'status': new_status, 'updated_at': datetime.now().isoformat()},
                {'symbol': symbol, 'status': 'active'}
            )

            if count > 0:
                self.logger.info(f"Updated {symbol} status: active → {new_status}")
                return True
            return False

        except Exception as e:
            self.logger.error(f"Failed to update {symbol} status: {e}")
            return False

    def remove(self, symbol: str) -> bool:
        """从观察池移除股票"""
        try:
            count = self.db.delete('observation_pool_daily', {'symbol': symbol, 'status': 'active'})

            if count > 0:
                self.logger.info(f"Removed {symbol} from daily pool")
                return True
            return False

        except Exception as e:
            self.logger.error(f"Failed to remove {symbol}: {e}")
            return False

    def check_expiry(self, current_date: date) -> List[PoolEntry]:
        """
        检查过期的股票

        Args:
            current_date: 当前日期

        Returns:
            过期的PoolEntry列表
        """
        expired_entries = []

        for entry in self.get_all(status='active'):
            # 计算观察天数
            days_since_add = (current_date - entry.add_date).days

            if days_since_add >= self.observation_days:
                # 过期
                self.update_status(entry.symbol, 'expired')
                expired_entries.append(entry)

        if expired_entries:
            self.logger.info(f"Found {len(expired_entries)} expired entries")

        return expired_entries
```

---

## 六、PoolManager（观察池管理器）

### 6.1 池间转换逻辑

```python
class PoolManager:
    """观察池管理器（总控）"""

    def __init__(self, db_manager=None, config=None):
        """初始化观察池管理器"""
        self.realtime_pool = RealtimePool(db_manager, config)
        self.daily_pool = DailyPool(db_manager, config)

        from BreakoutStrategy.utils.logger import Logger
        self.logger = Logger.get_logger('observation.manager')

    def add_from_search_results(self, search_results: pd.DataFrame):
        """
        从搜索结果添加到观察池

        逻辑：
        - 当日突破 → 实时观察池
        - 过去几天突破 → 日K观察池

        Args:
            search_results: 搜索结果DataFrame
        """
        today = datetime.now().date()

        for _, row in search_results.iterrows():
            entry = PoolEntry(
                symbol=row['symbol'],
                add_date=today,
                breakout_date=row['breakout_date'],
                breakout_info={
                    'price': row['breakout_price'],
                    'type': row['breakout_type'],
                    'quality_score': row['breakout_quality_score']
                },
                peak_info={
                    'date': row['peak_date'],
                    'price': row['peak_price'],
                    'quality_score': row['peak_quality_score']
                }
            )

            # 判断加入哪个池
            if row['breakout_date'] == today:
                self.realtime_pool.add(entry)
            else:
                self.daily_pool.add(entry)

    def move_timeout_to_daily_pool(self):
        """将实时观察池超时的股票转入日K观察池"""
        today = datetime.now().date()
        timeout_entries = self.realtime_pool.check_timeout(today)

        for entry in timeout_entries:
            # 重置add_date为今天
            entry.add_date = today
            entry.status = 'active'

            # 转入日K观察池
            self.daily_pool.add(entry)

            self.logger.info(f"Moved {entry.symbol} from realtime to daily pool (timeout)")

    def re_add_after_trade(self, symbol: str, entry_info: Dict):
        """
        循环跟踪：交易后重新加入日K观察池

        Args:
            symbol: 股票代码
            entry_info: 原始的突破信息
        """
        # 创建新的条目
        entry = PoolEntry(
            symbol=symbol,
            add_date=datetime.now().date(),
            breakout_date=entry_info['breakout_date'],
            breakout_info=entry_info['breakout_info'],
            peak_info=entry_info['peak_info'],
            retry_count=entry_info.get('retry_count', 0) + 1  # 增加重试次数
        )

        # 加入日K观察池
        self.daily_pool.add(entry, allow_duplicate=True)

        self.logger.info(f"Re-added {symbol} to daily pool after trade (retry: {entry.retry_count})")

    def cleanup_expired(self):
        """清理过期条目"""
        today = datetime.now().date()

        # 日K观察池过期检查
        expired_entries = self.daily_pool.check_expiry(today)

        self.logger.info(f"Cleaned up {len(expired_entries)} expired entries")

    def get_all_active_symbols(self) -> List[str]:
        """获取所有活跃观察的股票代码"""
        realtime_symbols = [e.symbol for e in self.realtime_pool.get_all('active')]
        daily_symbols = [e.symbol for e in self.daily_pool.get_all('active')]

        all_symbols = list(set(realtime_symbols + daily_symbols))
        return all_symbols

    def get_statistics(self) -> Dict:
        """获取观察池统计信息"""
        return {
            'realtime_pool': {
                'active': len(self.realtime_pool.get_all('active')),
                'bought': len(self.realtime_pool.get_all('bought')),
                'timeout': len(self.realtime_pool.get_all('timeout'))
            },
            'daily_pool': {
                'active': len(self.daily_pool.get_all('active')),
                'bought': len(self.daily_pool.get_all('bought')),
                'expired': len(self.daily_pool.get_all('expired'))
            },
            'total_active': len(self.get_all_active_symbols())
        }
```

---

## 七、使用示例

### 7.1 添加搜索结果到观察池

```python
from BreakoutStrategy.observation import PoolManager
from BreakoutStrategy.search import SearchEngine

# 1. 搜索突破
engine = SearchEngine()
results = engine.search()

# 2. 添加到观察池
pool_manager = PoolManager()
pool_manager.add_from_search_results(results)

# 3. 查看统计
stats = pool_manager.get_statistics()
print(f"Realtime pool: {stats['realtime_pool']['active']} active")
print(f"Daily pool: {stats['daily_pool']['active']} active")
```

### 7.2 定时清理和转换

```python
import schedule

def daily_pool_maintenance():
    """每日观察池维护任务"""
    pool_manager = PoolManager()

    # 1. 实时观察池超时 → 日K观察池
    pool_manager.move_timeout_to_daily_pool()

    # 2. 清理过期条目
    pool_manager.cleanup_expired()

    # 3. 统计
    stats = pool_manager.get_statistics()
    print(f"Pool maintenance completed: {stats}")

# 每天收盘后执行
schedule.every().day.at("17:00").do(daily_pool_maintenance)
```

### 7.3 循环跟踪

```python
# 交易系统止盈止损后
def on_trade_closed(symbol: str, pnl: float):
    """交易关闭回调"""
    pool_manager = PoolManager()

    # 获取原始信息
    entry = pool_manager.daily_pool.get_by_symbol(symbol)

    if entry:
        # 重新加入观察池（循环跟踪）
        pool_manager.re_add_after_trade(symbol, {
            'breakout_date': entry.breakout_date,
            'breakout_info': entry.breakout_info,
            'peak_info': entry.peak_info,
            'retry_count': entry.retry_count
        })
```

---

## 八、数据库表结构

```sql
-- 实时观察池表
CREATE TABLE observation_pool_realtime (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,
    add_date DATE NOT NULL,
    breakout_date DATE NOT NULL,
    breakout_info TEXT,
    peak_info TEXT,
    status VARCHAR(20) DEFAULT 'active',
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_pool_realtime_symbol ON observation_pool_realtime(symbol);
CREATE INDEX idx_pool_realtime_status ON observation_pool_realtime(status);

-- 日K观察池表
CREATE TABLE observation_pool_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,
    add_date DATE NOT NULL,
    breakout_date DATE NOT NULL,
    breakout_info TEXT,
    peak_info TEXT,
    status VARCHAR(20) DEFAULT 'active',
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_pool_daily_symbol ON observation_pool_daily(symbol);
CREATE INDEX idx_pool_daily_status ON observation_pool_daily(status);
```

---

## 九、测试方案

```python
# tests/observation/test_pool_manager.py
import pytest
from BreakoutStrategy.observation import PoolManager, PoolEntry
from datetime import date, datetime, timedelta

class TestPoolManager:

    @pytest.fixture
    def pool_manager(self):
        return PoolManager()

    def test_add_to_realtime_pool(self, pool_manager):
        """测试添加到实时观察池"""
        entry = PoolEntry(
            symbol='TEST',
            add_date=date.today(),
            breakout_date=date.today(),
            breakout_info={'price': 100.0},
            peak_info={'price': 95.0}
        )

        success = pool_manager.realtime_pool.add(entry)
        assert success == True

        # 验证已添加
        retrieved = pool_manager.realtime_pool.get_by_symbol('TEST')
        assert retrieved is not None
        assert retrieved.symbol == 'TEST'

    def test_timeout_transfer(self, pool_manager):
        """测试超时转换"""
        # 添加一个过期的条目
        entry = PoolEntry(
            symbol='TEST',
            add_date=date.today() - timedelta(days=2),  # 2天前
            breakout_date=date.today() - timedelta(days=2)
        )
        pool_manager.realtime_pool.add(entry)

        # 执行超时检查和转换
        pool_manager.move_timeout_to_daily_pool()

        # 验证已转移
        assert pool_manager.realtime_pool.get_by_symbol('TEST') is None
        assert pool_manager.daily_pool.get_by_symbol('TEST') is not None
```

---

**文档状态**：初稿完成
**下一步**：编写监测系统 + 交易执行 + 风险管理设计文档（合并为最后两份）
