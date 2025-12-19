# 数据层技术设计文档

**模块路径**：`BreakoutStrategy/data/`
**创建日期**：2025-11-16

---

## 一、模块概述

数据层负责与Tiger Open API交互，提供美股历史和实时行情数据，并管理本地缓存。

**核心职责**：
1. Tiger API封装：统一的数据获取接口
2. 数据缓存：避免重复请求，提高性能
3. 实时行情：WebSocket订阅分钟级数据
4. 数据验证：确保数据质量

**依赖**：
- 外部：`tigeropen` (Tiger API SDK)
- 内部：`config`, `utils.database`, `utils.logger`

---

## 二、模块架构

```
BreakoutStrategy/data/
├── __init__.py
├── tiger_adapter.py          # TigerDataAdapter - Tiger API封装
├── cache_manager.py          # DataCache - 数据缓存
├── realtime_stream.py        # RealtimeStream - 实时行情订阅
└── data_validator.py         # DataValidator - 数据验证
```

---

## 三、Tiger API概述

### 3.1 Tiger API配置

```python
# config/configs/default.yaml

api:
  tiger:
    rate_limit: 10                    # 请求/秒
    connection_timeout: 30
    read_timeout: 60
    data_fetch_retry_count: 3
    retry_interval: 5

  credentials:
    tiger_id: ${TIGER_ID}             # 从环境变量读取
    account: ${TIGER_ACCOUNT}
    private_key_path: ${TIGER_PRIVATE_KEY_PATH}
```

### 3.2 Tiger API主要功能

Tiger Open API提供的核心功能：

| 功能 | API方法 | 用途 |
|------|---------|------|
| 历史日K | `get_bars()` | 获取日线行情数据 |
| 历史分钟K | `get_bars()` (period='1min') | 获取分钟线数据 |
| 实时行情 | WebSocket订阅 | 实时价格/成交量推送 |
| 股票列表 | `get_all_symbols()` | 获取美股列表 |
| 基本面数据 | `get_financial_daily()` | 市值、流动性等 |
| 下单交易 | `place_order()` | 实盘交易（后期） |

---

## 四、TigerDataAdapter（Tiger API封装）

### 4.1 核心接口

```python
from typing import Optional, List
import pandas as pd
from datetime import date, datetime
from tigeropen.tiger_open_client import TigerOpenClient
from tigeropen.common.consts import Market, BarPeriod
from tigeropen.quote.quote_client import QuoteClient

class TigerDataAdapter:
    """Tiger API数据适配器"""

    def __init__(self, config: Optional[dict] = None):
        """
        初始化Tiger API客户端

        Args:
            config: Tiger API配置（如果为None，从ConfigManager读取）
        """
        if config is None:
            from BreakoutStrategy.config import ConfigManager
            cfg = ConfigManager.get_instance()
            api_config = cfg.get_section('api')
            credentials = api_config['credentials']
        else:
            credentials = config

        # 初始化Tiger客户端
        self.client_config = TigerOpenClientConfig(
            tiger_id=credentials['tiger_id'],
            account=credentials['account'],
            private_key_path=credentials['private_key_path']
        )
        self.quote_client = QuoteClient(self.client_config)

        # 速率限制
        from BreakoutStrategy.utils.decorators import RateLimiter
        self.rate_limiter = RateLimiter(max_calls=api_config['tiger']['rate_limit'], period=1.0)

        # 日志
        from BreakoutStrategy.utils.logger import Logger
        self.logger = Logger.get_logger('data.tiger_adapter')

    def get_historical_data(
        self,
        symbol: str,
        start_date: str,  # 'YYYY-MM-DD'
        end_date: str,
        period: str = '1d'  # '1d', '1min', '5min', '15min', '30min', '1h'
    ) -> pd.DataFrame:
        """
        获取历史行情数据

        Args:
            symbol: 股票代码（如'AAPL'）
            start_date: 开始日期
            end_date: 结束日期
            period: 数据周期

        Returns:
            DataFrame包含: date, open, high, low, close, volume

        Raises:
            TigerAPIException: API调用失败
        """
        self.rate_limiter.wait()  # 速率限制

        try:
            # 转换period参数
            bar_period = self._convert_period(period)

            # 调用Tiger API
            bars = self.quote_client.get_bars(
                symbols=[symbol],
                period=bar_period,
                begin_time=start_date,
                end_time=end_date
            )

            # 转换为DataFrame
            df = self._convert_bars_to_dataframe(bars, symbol)

            self.logger.info(f"Fetched {len(df)} bars for {symbol} from {start_date} to {end_date}")
            return df

        except Exception as e:
            self.logger.error(f"Failed to fetch data for {symbol}: {e}")
            raise TigerAPIException(f"Failed to fetch historical data: {e}")

    def get_realtime_quote(self, symbol: str) -> dict:
        """
        获取实时行情快照

        Args:
            symbol: 股票代码

        Returns:
            字典包含: latest_price, latest_time, pre_close, open, high, low, volume
        """
        self.rate_limiter.wait()

        try:
            quote = self.quote_client.get_stock_briefs([symbol])[0]

            return {
                'symbol': symbol,
                'latest_price': quote.latest_price,
                'latest_time': quote.latest_time,
                'pre_close': quote.pre_close,
                'open': quote.open,
                'high': quote.high,
                'low': quote.low,
                'volume': quote.volume
            }

        except Exception as e:
            self.logger.error(f"Failed to fetch realtime quote for {symbol}: {e}")
            raise TigerAPIException(f"Failed to fetch realtime quote: {e}")

    def get_symbols_by_market(self, market: str = 'US') -> List[str]:
        """
        获取市场股票列表

        Args:
            market: 市场代码（'US', 'CN', 'HK'）

        Returns:
            股票代码列表
        """
        self.rate_limiter.wait()

        try:
            market_enum = Market.US if market == 'US' else Market.CN
            symbols = self.quote_client.get_all_symbols(market=market_enum)

            self.logger.info(f"Fetched {len(symbols)} symbols from {market}")
            return symbols

        except Exception as e:
            self.logger.error(f"Failed to fetch symbols: {e}")
            raise TigerAPIException(f"Failed to fetch symbols: {e}")

    def get_market_cap(self, symbols: List[str]) -> pd.DataFrame:
        """
        获取股票市值和基本面数据

        Args:
            symbols: 股票代码列表

        Returns:
            DataFrame包含: symbol, market_cap, avg_volume, pe_ratio等
        """
        # Tiger API提供的基本面数据获取方法
        # 具体实现依赖于Tiger API文档
        pass

    def _convert_period(self, period: str) -> BarPeriod:
        """转换period字符串为Tiger API的BarPeriod枚举"""
        period_map = {
            '1d': BarPeriod.DAY,
            '1min': BarPeriod.ONE_MINUTE,
            '5min': BarPeriod.FIVE_MINUTE,
            '15min': BarPeriod.FIFTEEN_MINUTE,
            '30min': BarPeriod.THIRTY_MINUTE,
            '1h': BarPeriod.ONE_HOUR
        }
        return period_map.get(period, BarPeriod.DAY)

    def _convert_bars_to_dataframe(self, bars, symbol: str) -> pd.DataFrame:
        """将Tiger API返回的bars转换为DataFrame"""
        if not bars:
            return pd.DataFrame()

        data = []
        for bar in bars:
            data.append({
                'date': pd.to_datetime(bar.time, unit='ms'),
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close,
                'volume': bar.volume
            })

        df = pd.DataFrame(data)
        df.set_index('date', inplace=True)
        df['symbol'] = symbol
        return df


# 自定义异常
class TigerAPIException(Exception):
    """Tiger API异常"""
    pass
```

### 4.2 速率限制器

```python
# utils/decorators.py

import time
from collections import deque
from threading import Lock

class RateLimiter:
    """速率限制器（令牌桶算法）"""

    def __init__(self, max_calls: int, period: float = 1.0):
        """
        Args:
            max_calls: 时间窗口内最大调用次数
            period: 时间窗口（秒）
        """
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()
        self.lock = Lock()

    def wait(self):
        """等待直到可以进行下一次调用"""
        with self.lock:
            now = time.time()

            # 移除过期的调用记录
            while self.calls and self.calls[0] <= now - self.period:
                self.calls.popleft()

            # 如果达到限制，等待
            if len(self.calls) >= self.max_calls:
                sleep_time = self.period - (now - self.calls[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                self.calls.popleft()

            # 记录此次调用
            self.calls.append(time.time())
```

---

## 五、DataCache（数据缓存）

### 5.1 缓存策略

- **缓存层级**：内存缓存（LRU） + 数据库缓存（SQLite）
- **缓存键**：`{symbol}_{start_date}_{end_date}_{period}`
- **过期策略**：
  - 日K数据：缓存60分钟
  - 分钟K数据：缓存15分钟
  - 实时数据：不缓存

### 5.2 实现

```python
from functools import lru_cache
from datetime import datetime, timedelta
import hashlib

class DataCache:
    """数据缓存管理器"""

    def __init__(self, db_manager=None, cache_duration_minutes: int = 60):
        """
        Args:
            db_manager: DatabaseManager实例
            cache_duration_minutes: 缓存有效期（分钟）
        """
        if db_manager is None:
            from BreakoutStrategy.utils.database import DatabaseManager
            self.db = DatabaseManager.get_instance()
        else:
            self.db = db_manager

        self.cache_duration = timedelta(minutes=cache_duration_minutes)

        from BreakoutStrategy.utils.logger import Logger
        self.logger = Logger.get_logger('data.cache')

    def get_cached_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        period: str = '1d'
    ) -> Optional[pd.DataFrame]:
        """
        从缓存获取数据

        Returns:
            DataFrame或None（如果缓存不存在或已过期）
        """
        cache_key = self._generate_cache_key(symbol, start_date, end_date, period)

        # 1. 检查数据库缓存
        cached = self.db.query(
            "SELECT data, cached_at FROM data_cache WHERE cache_key = ?",
            (cache_key,)
        )

        if cached:
            cached_at = datetime.fromisoformat(cached[0]['cached_at'])
            if datetime.now() - cached_at < self.cache_duration:
                # 缓存有效
                self.logger.debug(f"Cache hit: {cache_key}")
                import pickle
                return pickle.loads(cached[0]['data'])
            else:
                # 缓存过期，删除
                self.db.execute("DELETE FROM data_cache WHERE cache_key = ?", (cache_key,))
                self.logger.debug(f"Cache expired: {cache_key}")

        return None

    def cache_data(
        self,
        df: pd.DataFrame,
        symbol: str,
        start_date: str,
        end_date: str,
        period: str = '1d'
    ):
        """缓存数据到数据库"""
        cache_key = self._generate_cache_key(symbol, start_date, end_date, period)

        import pickle
        data_bytes = pickle.dumps(df)

        # 插入或更新缓存
        self.db.execute("""
            INSERT OR REPLACE INTO data_cache (cache_key, symbol, start_date, end_date, period, data, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (cache_key, symbol, start_date, end_date, period, data_bytes, datetime.now().isoformat()))

        self.logger.debug(f"Cached data: {cache_key}")

    def _generate_cache_key(self, symbol: str, start_date: str, end_date: str, period: str) -> str:
        """生成缓存键"""
        key_str = f"{symbol}_{start_date}_{end_date}_{period}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def clear_cache(self, symbol: Optional[str] = None):
        """清除缓存"""
        if symbol:
            self.db.execute("DELETE FROM data_cache WHERE symbol = ?", (symbol,))
            self.logger.info(f"Cleared cache for {symbol}")
        else:
            self.db.execute("DELETE FROM data_cache")
            self.logger.info("Cleared all cache")


# 数据库表（添加到utils/database.py的表设计中）
CREATE_DATA_CACHE_TABLE = """
CREATE TABLE IF NOT EXISTS data_cache (
    cache_key VARCHAR(32) PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    period VARCHAR(10) NOT NULL,
    data BLOB NOT NULL,
    cached_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cache_symbol ON data_cache(symbol);
"""
```

---

## 六、RealtimeStream（实时行情订阅）

### 6.1 WebSocket订阅

Tiger API提供WebSocket推送实时行情数据。

```python
from tigeropen.push.push_client import PushClient
from tigeropen.common.consts import QuoteKeyType
from typing import Callable, List
import threading

class RealtimeStream:
    """实时行情订阅器"""

    def __init__(self, config=None):
        """初始化WebSocket客户端"""
        if config is None:
            from BreakoutStrategy.config import ConfigManager
            cfg = ConfigManager.get_instance()
            credentials = cfg.get_section('api')['credentials']
        else:
            credentials = config

        # 初始化Push Client
        client_config = TigerOpenClientConfig(
            tiger_id=credentials['tiger_id'],
            account=credentials['account'],
            private_key_path=credentials['private_key_path']
        )
        self.push_client = PushClient(client_config)

        # 订阅回调
        self.callbacks = {}  # {symbol: [callback1, callback2, ...]}

        # 日志
        from BreakoutStrategy.utils.logger import Logger
        self.logger = Logger.get_logger('data.realtime')

        # 连接状态
        self.is_connected = False

    def subscribe(self, symbols: List[str], callback: Callable[[dict], None]):
        """
        订阅实时行情

        Args:
            symbols: 股票代码列表
            callback: 回调函数，接收实时数据字典

        Example:
            >>> def on_quote(data):
            >>>     print(f"{data['symbol']}: ${data['latest_price']}")
            >>>
            >>> stream = RealtimeStream()
            >>> stream.subscribe(['AAPL', 'TSLA'], on_quote)
            >>> stream.connect()
        """
        for symbol in symbols:
            if symbol not in self.callbacks:
                self.callbacks[symbol] = []
            self.callbacks[symbol].append(callback)

        self.logger.info(f"Subscribed to {len(symbols)} symbols")

    def connect(self):
        """连接WebSocket并开始接收数据"""
        if self.is_connected:
            self.logger.warning("Already connected")
            return

        # 设置回调
        self.push_client.quote_changed = self._on_quote_changed
        self.push_client.connect_callback = self._on_connect
        self.push_client.disconnect_callback = self._on_disconnect

        # 连接
        self.push_client.connect()

        # 订阅行情
        symbols = list(self.callbacks.keys())
        self.push_client.subscribe_quote(symbols, quote_key_type=QuoteKeyType.ALL)

        self.is_connected = True
        self.logger.info(f"Connected to Tiger WebSocket, subscribed {len(symbols)} symbols")

    def _on_quote_changed(self, symbol: str, quote_data):
        """行情数据回调（Tiger API调用）"""
        if symbol in self.callbacks:
            # 转换为统一格式
            data = {
                'symbol': symbol,
                'latest_price': quote_data.latest_price,
                'latest_time': quote_data.latest_time,
                'open': quote_data.open,
                'high': quote_data.high,
                'low': quote_data.low,
                'volume': quote_data.volume,
                'timestamp': datetime.now()
            }

            # 调用所有注册的回调
            for callback in self.callbacks[symbol]:
                try:
                    callback(data)
                except Exception as e:
                    self.logger.error(f"Callback error for {symbol}: {e}")

    def _on_connect(self):
        """WebSocket连接成功回调"""
        self.is_connected = True
        self.logger.info("WebSocket connected")

    def _on_disconnect(self):
        """WebSocket断开回调"""
        self.is_connected = False
        self.logger.warning("WebSocket disconnected, attempting reconnect...")

        # 自动重连
        import time
        time.sleep(5)
        self.connect()

    def unsubscribe(self, symbols: List[str]):
        """取消订阅"""
        for symbol in symbols:
            if symbol in self.callbacks:
                del self.callbacks[symbol]

        if self.is_connected:
            self.push_client.unsubscribe_quote(symbols)

        self.logger.info(f"Unsubscribed {len(symbols)} symbols")

    def disconnect(self):
        """断开WebSocket连接"""
        if self.is_connected:
            self.push_client.disconnect()
            self.is_connected = False
            self.logger.info("Disconnected from Tiger WebSocket")
```

---

## 七、DataValidator（数据验证）

### 7.1 数据质量检查

```python
class DataValidator:
    """数据验证器"""

    @staticmethod
    def validate_dataframe(df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        验证DataFrame数据质量

        检查项：
        1. 必需列是否存在
        2. 是否有空值
        3. 价格是否为正数
        4. high >= low, high >= open, high >= close
        5. 成交量是否为非负数
        6. 是否有异常的价格变动（单日涨跌超过50%）

        Returns:
            (是否通过, 错误信息列表)
        """
        errors = []

        # 1. 检查必需列
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = set(required_columns) - set(df.columns)
        if missing_columns:
            errors.append(f"Missing columns: {missing_columns}")
            return False, errors

        # 2. 检查空值
        null_counts = df[required_columns].isnull().sum()
        if null_counts.sum() > 0:
            errors.append(f"Null values found: {null_counts[null_counts > 0].to_dict()}")

        # 3. 检查价格为正数
        for col in ['open', 'high', 'low', 'close']:
            if (df[col] <= 0).any():
                errors.append(f"{col} has non-positive values")

        # 4. 检查价格逻辑
        if (df['high'] < df['low']).any():
            errors.append("high < low in some rows")
        if (df['high'] < df['open']).any():
            errors.append("high < open in some rows")
        if (df['high'] < df['close']).any():
            errors.append("high < close in some rows")

        # 5. 检查成交量
        if (df['volume'] < 0).any():
            errors.append("volume has negative values")

        # 6. 检查异常价格变动
        df['change_pct'] = df['close'].pct_change()
        abnormal_changes = df[abs(df['change_pct']) > 0.5]
        if len(abnormal_changes) > 0:
            errors.append(f"Abnormal price changes detected: {len(abnormal_changes)} rows")

        return len(errors) == 0, errors

    @staticmethod
    def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """
        清洗DataFrame数据

        处理：
        1. 填充缺失值（前向填充）
        2. 移除异常值
        """
        df = df.copy()

        # 前向填充
        df.fillna(method='ffill', inplace=True)

        # 移除价格逻辑错误的行
        df = df[df['high'] >= df['low']]
        df = df[df['high'] >= df['open']]
        df = df[high'] >= df['close']]

        # 移除极端异常（涨跌幅超过100%）
        df['change_pct'] = df['close'].pct_change()
        df = df[abs(df['change_pct']) <= 1.0]
        df.drop(columns=['change_pct'], inplace=True)

        return df
```

---

## 八、统一接口：DataManager

为了简化上层模块的使用，提供统一的数据管理接口：

```python
class DataManager:
    """数据管理器（统一接口）"""

    def __init__(self):
        """初始化所有数据组件"""
        self.tiger = TigerDataAdapter()
        self.cache = DataCache()
        self.stream = RealtimeStream()
        self.validator = DataValidator()

        from BreakoutStrategy.utils.logger import Logger
        self.logger = Logger.get_logger('data.manager')

    def get_historical_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        period: str = '1d',
        use_cache: bool = True,
        validate: bool = True
    ) -> pd.DataFrame:
        """
        获取历史数据（带缓存和验证）

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            period: 周期
            use_cache: 是否使用缓存
            validate: 是否验证数据

        Returns:
            DataFrame
        """
        # 1. 尝试从缓存获取
        if use_cache:
            df = self.cache.get_cached_data(symbol, start_date, end_date, period)
            if df is not None:
                self.logger.debug(f"Loaded from cache: {symbol}")
                return df

        # 2. 从Tiger API获取
        df = self.tiger.get_historical_data(symbol, start_date, end_date, period)

        # 3. 验证数据
        if validate:
            is_valid, errors = self.validator.validate_dataframe(df)
            if not is_valid:
                self.logger.warning(f"Data validation failed for {symbol}: {errors}")
                df = self.validator.clean_dataframe(df)
                self.logger.info(f"Data cleaned for {symbol}")

        # 4. 缓存数据
        if use_cache:
            self.cache.cache_data(df, symbol, start_date, end_date, period)

        return df

    def subscribe_realtime(self, symbols: List[str], callback: Callable):
        """订阅实时行情"""
        self.stream.subscribe(symbols, callback)
        self.stream.connect()

    def get_symbols(self, min_price: float = 5.0, min_volume: int = 1000000) -> List[str]:
        """
        获取符合条件的股票列表

        Args:
            min_price: 最低价格
            min_volume: 最低平均成交量

        Returns:
            股票代码列表
        """
        all_symbols = self.tiger.get_symbols_by_market('US')

        # 过滤（需要获取基本面数据）
        # 简化版本：直接返回所有符号，后续在搜索阶段过滤
        return all_symbols
```

---

## 九、使用示例

```python
from BreakoutStrategy.data import DataManager

# 初始化数据管理器
dm = DataManager()

# 1. 获取历史数据（带缓存）
df = dm.get_historical_data('AAPL', '2023-01-01', '2024-01-01')
print(f"Loaded {len(df)} bars")

# 2. 订阅实时行情
def on_quote(data):
    print(f"{data['symbol']}: ${data['latest_price']:.2f}")

dm.subscribe_realtime(['AAPL', 'TSLA'], on_quote)

# 3. 获取股票列表
symbols = dm.get_symbols(min_price=10.0, min_volume=5000000)
print(f"Found {len(symbols)} symbols")
```

---

## 十、性能优化

### 10.1 批量获取数据

```python
def get_multiple_symbols(
    symbols: List[str],
    start_date: str,
    end_date: str,
    use_multiprocessing: bool = True,
    workers: int = 8
) -> Dict[str, pd.DataFrame]:
    """
    批量获取多只股票的历史数据

    使用多进程加速
    """
    if not use_multiprocessing:
        # 顺序获取
        results = {}
        for symbol in symbols:
            try:
                results[symbol] = dm.get_historical_data(symbol, start_date, end_date)
            except Exception as e:
                logger.error(f"Failed to fetch {symbol}: {e}")
        return results

    # 多进程获取
    from multiprocessing import Pool
    from functools import partial

    def fetch_symbol(symbol):
        try:
            return symbol, dm.get_historical_data(symbol, start_date, end_date)
        except Exception as e:
            logger.error(f"Failed to fetch {symbol}: {e}")
            return symbol, None

    with Pool(workers) as pool:
        results_list = pool.map(fetch_symbol, symbols)

    results = {symbol: df for symbol, df in results_list if df is not None}
    return results
```

---

## 十一、测试方案

```python
# tests/data/test_tiger_adapter.py
import pytest
from BreakoutStrategy.data.tiger_adapter import TigerDataAdapter

class TestTigerDataAdapter:

    @pytest.fixture
    def adapter(self):
        """创建TigerDataAdapter实例（需要配置API密钥）"""
        # 注意：需要有效的Tiger API credentials
        return TigerDataAdapter()

    def test_get_historical_data(self, adapter):
        """测试获取历史数据"""
        df = adapter.get_historical_data('AAPL', '2024-01-01', '2024-01-31')

        assert not df.empty
        assert 'open' in df.columns
        assert 'high' in df.columns
        assert 'low' in df.columns
        assert 'close' in df.columns
        assert 'volume' in df.columns

    def test_rate_limiter(self, adapter):
        """测试速率限制"""
        import time
        start = time.time()

        # 连续调用15次（速率限制10次/秒）
        for i in range(15):
            adapter.get_realtime_quote('AAPL')

        elapsed = time.time() - start
        # 应该至少需要1秒（因为超过了10次/秒的限制）
        assert elapsed >= 1.0
```

---

**文档状态**：初稿完成
**下一步**：编写搜索系统设计文档
