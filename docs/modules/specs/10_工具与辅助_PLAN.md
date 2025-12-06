# 工具与辅助模块技术设计文档

## 文档信息

- **模块名称**：工具与辅助（Utils & Helpers）
- **模块路径**：`BreakthroughStrategy/utils/`
- **文档版本**：v1.0
- **创建日期**：2025-11-16
- **最后更新**：2025-11-16
- **作者**：开发团队
- **状态**：设计中

---

## 一、模块概述

### 1.1 模块职责

工具与辅助模块提供系统运行所需的基础工具和辅助功能，包括日志记录、数据库管理和日期时间处理等通用功能。

**核心职责**：
1. 提供统一的日志系统（多级别、多输出、日志轮转）
2. 管理数据库连接和操作（SQLite/PostgreSQL）
3. 提供日期时间工具（交易日判断、日期范围生成、时区转换）
4. 提供其他通用工具（文件操作、数据格式转换等）

### 1.2 设计目标

- **易用性**：提供简洁的API，屏蔽底层复杂性
- **稳定性**：处理各种异常情况，确保系统稳定运行
- **高性能**：优化数据库查询性能
- **可扩展性**：易于添加新的工具函数

### 1.3 依赖关系

**外部依赖**：
- `logging`：Python标准日志库
- `sqlite3` / `psycopg2`：数据库驱动
- `pandas`：数据处理
- `pytz`：时区处理

**内部依赖**：
- `config`：配置管理（读取日志级别、数据库配置等）

**被依赖模块**：
- 所有其他模块

---

## 二、架构设计

### 2.1 模块内部架构

```
BreakthroughStrategy/utils/
├── __init__.py                # 导出主要工具类
├── logger.py                  # Logger - 日志系统
├── database.py                # DatabaseManager - 数据库管理
├── date_utils.py              # DateUtils - 日期工具
├── file_utils.py              # FileUtils - 文件操作工具
├── format_utils.py            # FormatUtils - 数据格式转换
└── decorators.py              # 装饰器工具（性能监控、异常捕获等）
```

### 2.2 类图

```
┌─────────────────────────────────────┐
│            Logger                   │
│ ─────────────────────────────────── │
│ - _logger: logging.Logger           │
│ - _handlers: List[Handler]          │
│ ─────────────────────────────────── │
│ + __init__(name, config)            │
│ + debug(msg, *args, **kwargs)       │
│ + info(msg, *args, **kwargs)        │
│ + warning(msg, *args, **kwargs)     │
│ + error(msg, *args, **kwargs)       │
│ + critical(msg, *args, **kwargs)    │
│ + add_handler(handler)              │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│        DatabaseManager              │
│ ─────────────────────────────────── │
│ - _conn: Connection                 │
│ - _db_type: str                     │
│ - _connection_pool: Pool            │
│ ─────────────────────────────────── │
│ + __init__(config)                  │
│ + execute(sql, params) -> Cursor    │
│ + query(sql, params) -> List[Row]   │
│ + insert(table, data) -> int        │
│ + update(table, data, where) -> int │
│ + delete(table, where) -> int       │
│ + begin_transaction()               │
│ + commit()                          │
│ + rollback()                        │
│ + close()                           │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│          DateUtils                  │
│ ─────────────────────────────────── │
│ + is_trading_day(date) -> bool      │
│ + get_trading_days(start, end) -> List│
│ + next_trading_day(date) -> date    │
│ + prev_trading_day(date) -> date    │
│ + convert_timezone(dt, from, to)    │
│ + date_range(start, end, freq)      │
└─────────────────────────────────────┘
```

---

## 三、子模块详细设计

### 3.1 Logger（日志系统）

#### 3.1.1 功能需求

- 支持多级别日志（DEBUG, INFO, WARNING, ERROR, CRITICAL）
- 支持多输出（控制台、文件）
- 支持日志文件轮转（按大小或时间）
- 支持按模块配置不同日志级别
- 日志格式可配置

#### 3.1.2 接口定义

```python
class Logger:
    """日志管理器"""

    def __init__(self, name: str, config: Optional[dict] = None):
        """
        初始化日志器

        Args:
            name: 日志器名称（通常是模块名）
            config: 日志配置（如果为None，从ConfigManager读取）
        """

    def debug(self, msg: str, *args, **kwargs):
        """记录DEBUG级别日志"""

    def info(self, msg: str, *args, **kwargs):
        """记录INFO级别日志"""

    def warning(self, msg: str, *args, **kwargs):
        """记录WARNING级别日志"""

    def error(self, msg: str, *args, **kwargs):
        """记录ERROR级别日志"""

    def critical(self, msg: str, *args, **kwargs):
        """记录CRITICAL级别日志"""

    def exception(self, msg: str, *args, **kwargs):
        """记录异常信息（包含堆栈）"""

    def add_handler(self, handler: logging.Handler):
        """添加自定义Handler"""

    @staticmethod
    def get_logger(name: str) -> 'Logger':
        """
        获取或创建Logger实例（单例模式）

        Args:
            name: 日志器名称

        Returns:
            Logger实例
        """
```

#### 3.1.3 实现细节

```python
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

class Logger:
    _instances = {}  # 单例模式：缓存Logger实例

    def __init__(self, name: str, config: Optional[dict] = None):
        self.name = name
        self._logger = logging.getLogger(name)

        # 从配置读取日志设置
        if config is None:
            from BreakthroughStrategy.config import ConfigManager
            config_mgr = ConfigManager.get_instance()
            config = config_mgr.get_section('logging')

        # 设置日志级别
        level = self._get_log_level(name, config)
        self._logger.setLevel(level)

        # 添加Handler
        self._setup_handlers(config)

    def _get_log_level(self, name: str, config: dict) -> int:
        """获取日志级别（支持模块级别配置）"""
        # 优先使用模块特定级别
        module_levels = config.get('modules', {})
        if name in module_levels:
            return getattr(logging, module_levels[name].upper())

        # 使用全局级别
        return getattr(logging, config.get('level', 'INFO').upper())

    def _setup_handlers(self, config: dict):
        """设置日志Handler"""
        handlers_config = config.get('handlers', {})

        # 控制台Handler
        if handlers_config.get('console', {}).get('enabled', True):
            console_handler = logging.StreamHandler()
            console_level = handlers_config['console'].get('level', 'INFO')
            console_handler.setLevel(getattr(logging, console_level.upper()))
            console_handler.setFormatter(self._get_formatter(config))
            self._logger.addHandler(console_handler)

        # 文件Handler
        if handlers_config.get('file', {}).get('enabled', True):
            file_config = handlers_config['file']
            log_file = self._get_log_filename(file_config.get('filename'))

            # 创建日志目录
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)

            # 使用RotatingFileHandler
            max_bytes = file_config.get('max_bytes', 10 * 1024 * 1024)  # 10MB
            backup_count = file_config.get('backup_count', 30)

            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_level = file_config.get('level', 'DEBUG')
            file_handler.setLevel(getattr(logging, file_level.upper()))
            file_handler.setFormatter(self._get_formatter(config))
            self._logger.addHandler(file_handler)

    def _get_formatter(self, config: dict) -> logging.Formatter:
        """获取日志格式化器"""
        fmt = config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        return logging.Formatter(fmt)

    def _get_log_filename(self, filename_template: str) -> str:
        """生成日志文件名（支持日期占位符）"""
        from datetime import datetime
        return filename_template.replace('{date}', datetime.now().strftime('%Y%m%d'))

    def debug(self, msg: str, *args, **kwargs):
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        self._logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        self._logger.critical(msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs):
        self._logger.exception(msg, *args, **kwargs)

    @classmethod
    def get_logger(cls, name: str) -> 'Logger':
        """获取Logger实例（单例）"""
        if name not in cls._instances:
            cls._instances[name] = cls(name)
        return cls._instances[name]
```

---

### 3.2 DatabaseManager（数据库管理）

#### 3.2.1 功能需求

- 支持SQLite和PostgreSQL
- 连接池管理（PostgreSQL）
- 事务支持
- 参数化查询（防止SQL注入）
- 自动重连机制
- 数据库表结构管理

#### 3.2.2 数据库表设计

```sql
-- historical_data: 历史行情数据缓存
CREATE TABLE historical_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);
CREATE INDEX idx_historical_symbol_date ON historical_data(symbol, date);

-- peaks: 凸点信息
CREATE TABLE peaks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,
    peak_date DATE NOT NULL,
    peak_price REAL NOT NULL,
    peak_type VARCHAR(20),  -- 'normal', 'special'
    quality_score REAL,
    suppression_days INTEGER,
    volume_surge_ratio REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, peak_date)
);
CREATE INDEX idx_peaks_symbol ON peaks(symbol);

-- breakthroughs: 突破信息
CREATE TABLE breakthroughs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,
    breakthrough_date DATE NOT NULL,
    breakthrough_price REAL NOT NULL,
    breakthrough_type VARCHAR(20),  -- 'yang', 'yin', 'shadow'
    peak_id INTEGER,  -- 关联的凸点ID
    quality_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (peak_id) REFERENCES peaks(id),
    UNIQUE(symbol, breakthrough_date)
);
CREATE INDEX idx_breakthroughs_symbol ON breakthroughs(symbol);

-- observation_pool_realtime: 实时观察池
CREATE TABLE observation_pool_realtime (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,
    breakthrough_id INTEGER NOT NULL,
    add_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'active',  -- 'active', 'bought', 'timeout'
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (breakthrough_id) REFERENCES breakthroughs(id),
    UNIQUE(symbol, breakthrough_id)
);
CREATE INDEX idx_pool_realtime_status ON observation_pool_realtime(status);

-- observation_pool_daily: 日K观察池
CREATE TABLE observation_pool_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,
    breakthrough_id INTEGER NOT NULL,
    add_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'active',  -- 'active', 'bought', 'expired'
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (breakthrough_id) REFERENCES breakthroughs(id),
    UNIQUE(symbol, breakthrough_id)
);
CREATE INDEX idx_pool_daily_status ON observation_pool_daily(status);

-- orders: 订单记录
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id VARCHAR(50) UNIQUE NOT NULL,  -- Tiger API订单ID
    symbol VARCHAR(20) NOT NULL,
    order_type VARCHAR(20) NOT NULL,  -- 'buy', 'sell'
    price_type VARCHAR(20) NOT NULL,  -- 'market', 'limit', 'stop'
    quantity INTEGER NOT NULL,
    price REAL,
    status VARCHAR(20),  -- 'submitted', 'filled', 'cancelled', 'rejected'
    filled_quantity INTEGER DEFAULT 0,
    filled_avg_price REAL,
    commission REAL,
    submit_time TIMESTAMP,
    fill_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_orders_symbol ON orders(symbol);
CREATE INDEX idx_orders_status ON orders(status);

-- positions: 持仓记录
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) UNIQUE NOT NULL,
    quantity INTEGER NOT NULL,
    avg_cost REAL NOT NULL,
    current_price REAL,
    unrealized_pnl REAL,
    buy_order_id VARCHAR(50),
    buy_time TIMESTAMP,
    stop_loss_price REAL,
    take_profit_price REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (buy_order_id) REFERENCES orders(order_id)
);

-- trades: 成交记录
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,
    buy_order_id VARCHAR(50),
    sell_order_id VARCHAR(50),
    buy_price REAL NOT NULL,
    sell_price REAL,
    quantity INTEGER NOT NULL,
    buy_time TIMESTAMP NOT NULL,
    sell_time TIMESTAMP,
    holding_days INTEGER,
    realized_pnl REAL,
    pnl_pct REAL,
    commission REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (buy_order_id) REFERENCES orders(order_id),
    FOREIGN KEY (sell_order_id) REFERENCES orders(order_id)
);
CREATE INDEX idx_trades_symbol ON trades(symbol);

-- config_history: 配置变更历史
CREATE TABLE config_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_key VARCHAR(200) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by VARCHAR(100),
    change_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 3.2.3 接口定义

```python
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

class DatabaseManager:
    """数据库管理器"""

    def __init__(self, config: Optional[dict] = None):
        """
        初始化数据库管理器

        Args:
            config: 数据库配置（如果为None，从ConfigManager读取）
        """

    def execute(self, sql: str, params: Optional[tuple] = None) -> Any:
        """
        执行SQL语句（INSERT, UPDATE, DELETE）

        Args:
            sql: SQL语句
            params: 参数（使用?占位符，防止SQL注入）

        Returns:
            Cursor对象

        Example:
            >>> db.execute("INSERT INTO peaks (symbol, peak_date, peak_price) VALUES (?, ?, ?)",
                          ("AAPL", "2024-01-15", 195.50))
        """

    def query(self, sql: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        执行查询SQL语句

        Args:
            sql: SQL查询语句
            params: 参数

        Returns:
            结果列表（字典格式）

        Example:
            >>> results = db.query("SELECT * FROM peaks WHERE symbol = ?", ("AAPL",))
        """

    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """
        插入数据（简化接口）

        Args:
            table: 表名
            data: 数据字典

        Returns:
            插入记录的ID

        Example:
            >>> db.insert('peaks', {
                    'symbol': 'AAPL',
                    'peak_date': '2024-01-15',
                    'peak_price': 195.50
                })
        """

    def update(self, table: str, data: Dict[str, Any], where: Dict[str, Any]) -> int:
        """
        更新数据

        Args:
            table: 表名
            data: 更新数据字典
            where: 条件字典

        Returns:
            更新的记录数

        Example:
            >>> db.update('observation_pool_realtime',
                         {'status': 'bought'},
                         {'symbol': 'AAPL', 'status': 'active'})
        """

    def delete(self, table: str, where: Dict[str, Any]) -> int:
        """
        删除数据

        Args:
            table: 表名
            where: 条件字典

        Returns:
            删除的记录数
        """

    @contextmanager
    def transaction(self):
        """
        事务上下文管理器

        Example:
            >>> with db.transaction():
                    db.insert('orders', {...})
                    db.insert('positions', {...})
        """

    def create_tables(self):
        """创建所有表（如果不存在）"""

    def close(self):
        """关闭数据库连接"""

    @staticmethod
    def get_instance() -> 'DatabaseManager':
        """获取DatabaseManager单例"""
```

#### 3.2.4 实现示例

```python
import sqlite3
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

class DatabaseManager:
    _instance = None

    def __init__(self, config: Optional[dict] = None):
        if config is None:
            from BreakthroughStrategy.config import ConfigManager
            config_mgr = ConfigManager.get_instance()
            config = config_mgr.get_section('data')['database']

        self._db_type = config.get('type', 'sqlite')
        self._conn = None

        if self._db_type == 'sqlite':
            db_path = config.get('path', 'datasets/breakthrough.db')
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row  # 返回字典格式

    def query(self, sql: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """执行查询"""
        cursor = self._conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """插入数据"""
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        cursor = self._conn.cursor()
        cursor.execute(sql, tuple(data.values()))
        self._conn.commit()
        return cursor.lastrowid

    @contextmanager
    def transaction(self):
        """事务上下文"""
        try:
            yield
            self._conn.commit()
        except Exception as e:
            self._conn.rollback()
            raise

    @classmethod
    def get_instance(cls) -> 'DatabaseManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
```

---

### 3.3 DateUtils（日期工具）

#### 3.3.1 功能需求

- 判断是否为美股交易日
- 获取交易日范围
- 获取下一个/上一个交易日
- 时区转换（美国东部时间 ↔ UTC ↔ 本地时间）
- 生成日期范围

#### 3.3.2 接口定义

```python
from datetime import date, datetime, timedelta
from typing import List
import pytz

class DateUtils:
    """日期时间工具"""

    # 美股假期列表（简化版，实际需要维护完整列表）
    US_MARKET_HOLIDAYS = [
        # 2024年假期
        date(2024, 1, 1),   # New Year's Day
        date(2024, 1, 15),  # Martin Luther King Jr. Day
        date(2024, 2, 19),  # Presidents Day
        date(2024, 3, 29),  # Good Friday
        date(2024, 5, 27),  # Memorial Day
        date(2024, 6, 19),  # Juneteenth
        date(2024, 7, 4),   # Independence Day
        date(2024, 9, 2),   # Labor Day
        date(2024, 11, 28), # Thanksgiving
        date(2024, 12, 25), # Christmas
        # 2025年假期
        # ...
    ]

    @staticmethod
    def is_trading_day(d: date) -> bool:
        """
        判断是否为美股交易日

        Args:
            d: 日期

        Returns:
            是否为交易日（周一至周五且非假期）
        """
        # 周末
        if d.weekday() >= 5:
            return False
        # 假期
        if d in DateUtils.US_MARKET_HOLIDAYS:
            return False
        return True

    @staticmethod
    def get_trading_days(start: date, end: date) -> List[date]:
        """
        获取日期范围内的所有交易日

        Args:
            start: 开始日期
            end: 结束日期

        Returns:
            交易日列表
        """
        trading_days = []
        current = start
        while current <= end:
            if DateUtils.is_trading_day(current):
                trading_days.append(current)
            current += timedelta(days=1)
        return trading_days

    @staticmethod
    def next_trading_day(d: date) -> date:
        """
        获取下一个交易日

        Args:
            d: 当前日期

        Returns:
            下一个交易日
        """
        next_day = d + timedelta(days=1)
        while not DateUtils.is_trading_day(next_day):
            next_day += timedelta(days=1)
        return next_day

    @staticmethod
    def prev_trading_day(d: date) -> date:
        """获取上一个交易日"""
        prev_day = d - timedelta(days=1)
        while not DateUtils.is_trading_day(prev_day):
            prev_day -= timedelta(days=1)
        return prev_day

    @staticmethod
    def convert_timezone(
        dt: datetime,
        from_tz: str = 'UTC',
        to_tz: str = 'America/New_York'
    ) -> datetime:
        """
        时区转换

        Args:
            dt: 日期时间
            from_tz: 源时区
            to_tz: 目标时区

        Returns:
            转换后的日期时间
        """
        if dt.tzinfo is None:
            dt = pytz.timezone(from_tz).localize(dt)
        return dt.astimezone(pytz.timezone(to_tz))

    @staticmethod
    def date_range(
        start: date,
        end: date,
        freq: str = 'D'  # 'D': daily, 'W': weekly, 'M': monthly
    ) -> List[date]:
        """
        生成日期范围

        Args:
            start: 开始日期
            end: 结束日期
            freq: 频率

        Returns:
            日期列表
        """
        import pandas as pd
        return pd.date_range(start, end, freq=freq).date.tolist()
```

---

## 四、装饰器工具

### 4.1 性能监控装饰器

```python
import time
import functools
from typing import Callable

def timer(func: Callable) -> Callable:
    """
    性能监控装饰器：记录函数执行时间

    Example:
        >>> @timer
        >>> def my_function():
        >>>     time.sleep(1)
        >>> my_function()
        [INFO] my_function executed in 1.002s
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = Logger.get_logger(func.__module__)
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        logger.info(f"{func.__name__} executed in {elapsed:.3f}s")
        return result
    return wrapper
```

### 4.2 异常捕获装饰器

```python
def catch_exceptions(logger: Optional['Logger'] = None, reraise: bool = False):
    """
    异常捕获装饰器：自动记录异常日志

    Args:
        logger: 日志器（可选）
        reraise: 是否重新抛出异常

    Example:
        >>> @catch_exceptions(reraise=True)
        >>> def risky_function():
        >>>     raise ValueError("Something went wrong")
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal logger
            if logger is None:
                logger = Logger.get_logger(func.__module__)
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Exception in {func.__name__}: {str(e)}")
                if reraise:
                    raise
                return None
        return wrapper
    return decorator
```

### 4.3 重试装饰器

```python
def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    重试装饰器：自动重试失败的操作

    Args:
        max_attempts: 最大尝试次数
        delay: 初始延迟（秒）
        backoff: 延迟递增倍数

    Example:
        >>> @retry(max_attempts=3, delay=1, backoff=2)
        >>> def unreliable_api_call():
        >>>     # 可能失败的API调用
        >>>     pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = Logger.get_logger(func.__module__)
            current_delay = delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts")
                        raise
                    logger.warning(f"{func.__name__} attempt {attempt} failed: {e}. Retrying in {current_delay}s...")
                    time.sleep(current_delay)
                    current_delay *= backoff

        return wrapper
    return decorator
```

---

## 五、测试方案

### 5.1 单元测试

```python
# tests/utils/test_logger.py
import pytest
from BreakthroughStrategy.utils.logger import Logger

class TestLogger:

    def test_logger_singleton(self):
        """测试Logger单例模式"""
        logger1 = Logger.get_logger('test')
        logger2 = Logger.get_logger('test')
        assert logger1 is logger2

    def test_log_levels(self, caplog):
        """测试不同日志级别"""
        logger = Logger.get_logger('test')
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        # 验证日志输出

# tests/utils/test_database.py
import pytest
from BreakthroughStrategy.utils.database import DatabaseManager

class TestDatabaseManager:

    @pytest.fixture
    def db(self, tmp_path):
        """创建临时数据库"""
        config = {
            'type': 'sqlite',
            'path': str(tmp_path / "test.db")
        }
        db = DatabaseManager(config)
        db.create_tables()
        yield db
        db.close()

    def test_insert_and_query(self, db):
        """测试插入和查询"""
        db.insert('peaks', {
            'symbol': 'AAPL',
            'peak_date': '2024-01-15',
            'peak_price': 195.50
        })

        results = db.query("SELECT * FROM peaks WHERE symbol = ?", ('AAPL',))
        assert len(results) == 1
        assert results[0]['peak_price'] == 195.50

    def test_transaction(self, db):
        """测试事务"""
        with db.transaction():
            db.insert('peaks', {'symbol': 'AAPL', 'peak_date': '2024-01-15', 'peak_price': 195.50})
            db.insert('peaks', {'symbol': 'TSLA', 'peak_date': '2024-01-16', 'peak_price': 245.00})

        results = db.query("SELECT COUNT(*) as count FROM peaks")
        assert results[0]['count'] == 2

# tests/utils/test_date_utils.py
from datetime import date
from BreakthroughStrategy.utils.date_utils import DateUtils

class TestDateUtils:

    def test_is_trading_day(self):
        """测试交易日判断"""
        # 工作日
        assert DateUtils.is_trading_day(date(2024, 1, 2)) == True  # Tuesday
        # 周末
        assert DateUtils.is_trading_day(date(2024, 1, 6)) == False  # Saturday
        # 假期
        assert DateUtils.is_trading_day(date(2024, 1, 1)) == False  # New Year's Day

    def test_get_trading_days(self):
        """测试获取交易日范围"""
        start = date(2024, 1, 1)
        end = date(2024, 1, 7)
        trading_days = DateUtils.get_trading_days(start, end)
        # 应该排除1/1（假期）、1/6-1/7（周末）
        assert len(trading_days) == 4

    def test_next_trading_day(self):
        """测试获取下一个交易日"""
        # 从周五到下周一
        friday = date(2024, 1, 5)
        next_day = DateUtils.next_trading_day(friday)
        assert next_day == date(2024, 1, 8)  # Monday
```

---

## 六、未决问题

### 6.1 日志存储

- **问题**：是否需要将日志存储到数据库（除了文件）？
- **用途**：便于查询和分析
- **建议**：初期使用文件日志，后期可考虑添加数据库日志Handler

### 6.2 数据库迁移

- **问题**：如何处理数据库表结构变更？
- **方案**：使用数据库迁移工具（如Alembic）
- **建议**：阶段一手动管理，阶段二引入Alembic

---

## 七、实施检查清单

### 7.1 开发阶段

- [ ] 实现Logger类
- [ ] 实现DatabaseManager类
- [ ] 实现DateUtils类
- [ ] 实现装饰器工具（timer, catch_exceptions, retry）
- [ ] 编写数据库表创建SQL
- [ ] 实现数据库表创建逻辑

### 7.2 测试阶段

- [ ] Logger单元测试
- [ ] DatabaseManager单元测试
- [ ] DateUtils单元测试
- [ ] 装饰器测试

### 7.3 文档阶段

- [ ] API文档
- [ ] 数据库表结构文档
- [ ] 日志使用指南

---

**文档状态**：待评审
**下一步**：评审本设计文档，开始编码实现
