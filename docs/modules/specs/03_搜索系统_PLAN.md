# 搜索系统技术设计文档

**模块路径**：`BreakoutStrategy/search/`
**创建日期**：2025-11-16

---

## 一、模块概述

搜索系统负责扫描美股市场，找到已经完成突破的股票，并输出候选列表供后续观察池使用。

**核心职责**：
1. 扫描股票池，找到历史突破
2. 应用基础过滤器（市值、流动性、价格）
3. 调用技术分析模块识别凸点和突破
4. 对结果进行质量评分和排序
5. 输出格式化结果

**依赖**：
- `data`：获取股票列表和行情数据
- `analysis`：凸点识别、突破检测、质量评分
- `config`：搜索参数配置

---

## 二、模块架构

```
BreakoutStrategy/search/
├── __init__.py
├── search_engine.py          # SearchEngine - 搜索引擎主控
├── stock_filter.py           # StockFilter - 股票过滤器
├── scanner.py                # HistoricalScanner - 历史扫描器
└── result_formatter.py       # ResultFormatter - 结果格式化
```

---

## 三、工作流程

```
获取股票池 → 基础过滤 → 下载历史数据 → 凸点识别 → 突破检测 → 质量评分 → 排序输出
   ↓             ↓              ↓              ↓           ↓           ↓          ↓
 Tiger API   市值/流动性      多进程并行      分析模块     分析模块    评分模块    文件/数据库
```

---

## 四、StockFilter（股票过滤器）

### 4.1 基础过滤条件

```python
from typing import List, Dict
import pandas as pd

class StockFilter:
    """股票过滤器"""

    def __init__(self, config: Optional[dict] = None):
        """
        初始化过滤器

        Args:
            config: 过滤参数配置
        """
        if config is None:
            from BreakoutStrategy.config import ConfigManager
            cfg = ConfigManager.get_instance()
            self.config = cfg.get_section('search')
        else:
            self.config = config

        self.market_cap_min = self.config.get('market_cap_min', 1e9)  # 10亿美元
        self.avg_volume_min = self.config.get('avg_volume_min', 1e6)  # 100万股
        self.price_min = self.config.get('price_min', 5.0)
        self.price_max = self.config.get('price_max', None)

        from BreakoutStrategy.utils.logger import Logger
        self.logger = Logger.get_logger('search.filter')

    def filter_by_basics(self, symbols: List[str], market_data: pd.DataFrame) -> List[str]:
        """
        基础过滤：市值、流动性、价格

        Args:
            symbols: 股票代码列表
            market_data: 市场数据DataFrame，包含market_cap, avg_volume, price等列

        Returns:
            过滤后的股票列表
        """
        filtered = market_data[
            (market_data['market_cap'] >= self.market_cap_min) &
            (market_data['avg_volume'] >= self.avg_volume_min) &
            (market_data['price'] >= self.price_min)
        ]

        if self.price_max is not None:
            filtered = filtered[filtered['price'] <= self.price_max]

        result = filtered['symbol'].tolist()
        self.logger.info(f"Filtered {len(symbols)} → {len(result)} symbols")
        return result

    def filter_by_data_quality(self, symbol: str, df: pd.DataFrame) -> bool:
        """
        数据质量过滤

        Args:
            symbol: 股票代码
            df: 行情数据

        Returns:
            是否通过过滤

        过滤条件：
        1. 数据长度 >= min_history_days
        2. 数据验证通过
        """
        min_history_days = self.config.get('min_history_days', 252)

        # 检查数据长度
        if len(df) < min_history_days:
            self.logger.debug(f"{symbol}: insufficient data ({len(df)} < {min_history_days})")
            return False

        # 数据验证
        from BreakoutStrategy.data.data_validator import DataValidator
        is_valid, errors = DataValidator.validate_dataframe(df)
        if not is_valid:
            self.logger.warning(f"{symbol}: data validation failed - {errors}")
            return False

        return True
```

---

## 五、HistoricalScanner（历史扫描器）

### 5.1 核心扫描逻辑

```python
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pandas as pd

class HistoricalScanner:
    """历史突破扫描器"""

    def __init__(self, config: Optional[dict] = None):
        """初始化扫描器"""
        if config is None:
            from BreakoutStrategy.config import ConfigManager
            cfg = ConfigManager.get_instance()
            self.config = cfg.get_section('search')
            self.time_config = cfg.get_section('time')
        else:
            self.config = config
            self.time_config = config.get('time', {})

        # 初始化依赖模块
        from BreakoutStrategy.data import DataManager
        from BreakoutStrategy.analysis import PeakDetector, BreakoutDetector, QualityScorer

        self.data_manager = DataManager()
        self.peak_detector = PeakDetector()
        self.breakout_detector = BreakoutDetector()
        self.quality_scorer = QualityScorer()

        from BreakoutStrategy.utils.logger import Logger
        self.logger = Logger.get_logger('search.scanner')

    def scan_symbol(
        self,
        symbol: str,
        start_date: str,
        end_date: str
    ) -> Dict:
        """
        扫描单只股票

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            扫描结果字典：
            {
                'symbol': str,
                'peaks': List[Peak],
                'breakouts': List[Breakout],
                'recent_breakouts': List[Breakout],  # 最近N天的突破
                'success': bool
            }
        """
        try:
            # 1. 获取历史数据（需要更长的历史以识别凸点）
            # 向前扩展数据范围，确保能识别到早期凸点
            extended_start = self._extend_start_date(start_date, months=6)
            df = self.data_manager.get_historical_data(symbol, extended_start, end_date)

            if df.empty:
                self.logger.warning(f"{symbol}: no data")
                return {'symbol': symbol, 'success': False}

            # 2. 识别凸点
            peaks = self.peak_detector.detect_peaks(df)
            self.logger.debug(f"{symbol}: found {len(peaks)} peaks")

            # 3. 检测突破
            breakouts = self.breakout_detector.detect_breakouts(df, peaks)
            self.logger.debug(f"{symbol}: found {len(breakouts)} breakouts")

            # 4. 质量评分
            self.quality_scorer.score_peaks_batch(peaks)
            self.quality_scorer.score_breakouts_batch(breakouts)

            # 5. 筛选最近的突破（搜索目标时间范围内）
            historical_search_days = self.time_config.get('historical_search_days', 7)
            cutoff_date = datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=historical_search_days)

            recent_breakouts = [
                bo for bo in breakouts
                if bo.date >= cutoff_date.date()
            ]

            self.logger.info(f"{symbol}: {len(recent_breakouts)} recent breakouts "
                           f"(quality scores: {[bo.quality_score for bo in recent_breakouts]})")

            return {
                'symbol': symbol,
                'peaks': peaks,
                'breakouts': breakouts,
                'recent_breakouts': recent_breakouts,
                'success': True
            }

        except Exception as e:
            self.logger.error(f"{symbol}: scan failed - {e}")
            return {'symbol': symbol, 'success': False, 'error': str(e)}

    def _extend_start_date(self, start_date: str, months: int = 6) -> str:
        """向前扩展开始日期"""
        date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        extended = date_obj - timedelta(days=months * 30)
        return extended.strftime('%Y-%m-%d')

    def scan_multiple_symbols(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        use_multiprocessing: bool = True,
        workers: Optional[int] = None
    ) -> List[Dict]:
        """
        批量扫描多只股票

        Args:
            symbols: 股票列表
            start_date: 开始日期
            end_date: 结束日期
            use_multiprocessing: 是否使用多进程
            workers: 进程数（None表示使用CPU核心数）

        Returns:
            扫描结果列表
        """
        if not use_multiprocessing:
            # 顺序扫描
            results = []
            for symbol in symbols:
                result = self.scan_symbol(symbol, start_date, end_date)
                results.append(result)
            return results

        # 多进程扫描
        import os
        from multiprocessing import Pool
        from functools import partial

        if workers is None:
            workers = self.config.get('search_workers', os.cpu_count())

        scan_func = partial(self.scan_symbol, start_date=start_date, end_date=end_date)

        self.logger.info(f"Starting parallel scan: {len(symbols)} symbols, {workers} workers")

        with Pool(workers) as pool:
            results = pool.map(scan_func, symbols)

        successful = sum(1 for r in results if r.get('success'))
        self.logger.info(f"Scan completed: {successful}/{len(symbols)} successful")

        return results
```

---

## 六、SearchEngine（搜索引擎）

### 6.1 主控流程

```python
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pandas as pd

class SearchEngine:
    """搜索引擎主控"""

    def __init__(self, config: Optional[dict] = None):
        """初始化搜索引擎"""
        self.stock_filter = StockFilter(config)
        self.scanner = HistoricalScanner(config)

        if config is None:
            from BreakoutStrategy.config import ConfigManager
            cfg = ConfigManager.get_instance()
            self.config = cfg.get_section('search')
            self.quality_config = cfg.get_section('quality')
        else:
            self.config = config
            self.quality_config = config.get('quality', {})

        from BreakoutStrategy.data import DataManager
        self.data_manager = DataManager()

        from BreakoutStrategy.utils.logger import Logger
        self.logger = Logger.get_logger('search.engine')

    def search(
        self,
        end_date: Optional[str] = None,
        historical_days: Optional[int] = None,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        执行搜索

        Args:
            end_date: 结束日期（默认今天）
            historical_days: 历史搜索天数（默认从配置读取）
            use_cache: 是否使用缓存结果

        Returns:
            搜索结果DataFrame，包含列：
            - symbol: 股票代码
            - breakout_date: 突破日期
            - breakout_price: 突破价格
            - peak_date: 凸点日期
            - peak_price: 凸点价格
            - peak_quality_score: 凸点质量分数
            - breakout_quality_score: 突破质量分数
            - combined_score: 综合分数
        """
        # 1. 确定搜索时间范围
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')

        if historical_days is None:
            from BreakoutStrategy.config import ConfigManager
            cfg = ConfigManager.get_instance()
            historical_days = cfg.get('time.historical_search_days', 7)

        start_date = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=historical_days)).strftime('%Y-%m-%d')

        self.logger.info(f"Starting search: {start_date} to {end_date}")

        # 2. 获取股票池
        symbols = self._get_stock_universe()
        self.logger.info(f"Stock universe: {len(symbols)} symbols")

        # 3. 基础过滤
        # 简化版：跳过市值过滤（需要额外API调用），在扫描时通过价格和成交量过滤
        # 完整版：调用get_market_data获取市值数据进行过滤
        filtered_symbols = symbols  # 简化版

        # 4. 扫描股票
        scan_results = self.scanner.scan_multiple_symbols(
            filtered_symbols,
            start_date,
            end_date,
            use_multiprocessing=True
        )

        # 5. 提取有效结果
        valid_results = [r for r in scan_results if r.get('success') and r.get('recent_breakouts')]
        self.logger.info(f"Found {len(valid_results)} stocks with recent breakouts")

        # 6. 转换为DataFrame
        results_df = self._convert_to_dataframe(valid_results)

        # 7. 过滤低质量突破
        min_breakout_score = self.quality_config.get('breakout_quality_min_score', 70)
        high_quality = results_df[results_df['breakout_quality_score'] >= min_breakout_score]

        self.logger.info(f"High quality breakouts: {len(high_quality)}")

        # 8. 排序（按综合分数降序）
        high_quality = high_quality.sort_values('combined_score', ascending=False)

        return high_quality

    def _get_stock_universe(self) -> List[str]:
        """
        获取股票池

        策略：
        1. 首次运行：从Tiger API获取所有美股
        2. 后续运行：从缓存读取
        """
        # 简化版：使用预定义股票池（可从文件读取）
        # 完整版：调用data_manager.get_symbols()

        # 示例：使用S&P 500成分股（从文件加载）
        # 或者使用全市场扫描
        symbols = self.data_manager.get_symbols()

        # 额外过滤：价格范围
        # 这里简化处理，实际可以先获取最新价格再过滤
        return symbols

    def _convert_to_dataframe(self, scan_results: List[Dict]) -> pd.DataFrame:
        """
        将扫描结果转换为DataFrame

        Args:
            scan_results: 扫描结果列表

        Returns:
            结果DataFrame
        """
        rows = []

        for result in scan_results:
            symbol = result['symbol']
            for bo in result['recent_breakouts']:
                row = {
                    'symbol': symbol,
                    'breakout_date': bo.date,
                    'breakout_price': bo.price,
                    'breakout_type': bo.breakout_type,
                    'peak_date': bo.peak.date,
                    'peak_price': bo.peak.price,
                    'peak_type': bo.peak.peak_type,
                    'peak_quality_score': bo.peak.quality_score,
                    'breakout_quality_score': bo.quality_score,
                    'combined_score': self._calculate_combined_score(bo),
                    # 额外信息
                    'exceed_pct': bo.exceed_pct,
                    'volume_surge_ratio': bo.volume_surge_ratio,
                    'gap_up': bo.gap_up,
                    'continuity_days': bo.continuity_days,
                    'stability_score': bo.stability_score
                }
                rows.append(row)

        if not rows:
            # 返回空DataFrame但保留列结构
            return pd.DataFrame(columns=[
                'symbol', 'breakout_date', 'breakout_price', 'breakout_type',
                'peak_date', 'peak_price', 'peak_type',
                'peak_quality_score', 'breakout_quality_score', 'combined_score',
                'exceed_pct', 'volume_surge_ratio', 'gap_up', 'continuity_days', 'stability_score'
            ])

        return pd.DataFrame(rows)

    def _calculate_combined_score(self, breakout) -> float:
        """
        计算综合分数（凸点质量 + 突破质量）

        权重：
        - 凸点质量：40%
        - 突破质量：60%
        """
        peak_weight = 0.4
        breakout_weight = 0.6

        return (
            breakout.peak.quality_score * peak_weight +
            breakout.quality_score * breakout_weight
        )
```

---

## 七、ResultFormatter（结果格式化）

### 7.1 输出格式

```python
from typing import List
import pandas as pd
from datetime import datetime

class ResultFormatter:
    """结果格式化器"""

    @staticmethod
    def save_to_file(df: pd.DataFrame, output_path: str, format: str = 'csv'):
        """
        保存结果到文件

        Args:
            df: 结果DataFrame
            output_path: 输出路径
            format: 格式 ('csv', 'excel', 'json')
        """
        if format == 'csv':
            df.to_csv(output_path, index=False)
        elif format == 'excel':
            df.to_excel(output_path, index=False)
        elif format == 'json':
            df.to_json(output_path, orient='records', date_format='iso')
        else:
            raise ValueError(f"Unsupported format: {format}")

    @staticmethod
    def save_to_database(df: pd.DataFrame, db_manager):
        """
        保存结果到数据库

        Args:
            df: 结果DataFrame
            db_manager: DatabaseManager实例
        """
        for _, row in df.iterrows():
            # 插入或更新breakouts表
            db_manager.execute("""
                INSERT OR REPLACE INTO breakouts
                (symbol, breakout_date, breakout_price, breakout_type,
                 peak_date, peak_price, quality_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row['symbol'],
                row['breakout_date'],
                row['breakout_price'],
                row['breakout_type'],
                row['peak_date'],
                row['peak_price'],
                row['breakout_quality_score'],
                datetime.now().isoformat()
            ))

    @staticmethod
    def format_for_observation_pool(df: pd.DataFrame) -> List[Dict]:
        """
        格式化为观察池条目

        Returns:
            观察池条目列表
        """
        entries = []

        for _, row in df.iterrows():
            entry = {
                'symbol': row['symbol'],
                'breakout_date': row['breakout_date'],
                'breakout_info': {
                    'price': row['breakout_price'],
                    'type': row['breakout_type'],
                    'quality_score': row['breakout_quality_score']
                },
                'peak_info': {
                    'date': row['peak_date'],
                    'price': row['peak_price'],
                    'quality_score': row['peak_quality_score']
                },
                'add_date': datetime.now().date(),
                'status': 'pending'  # 待加入观察池
            }
            entries.append(entry)

        return entries

    @staticmethod
    def generate_summary_report(df: pd.DataFrame) -> str:
        """
        生成搜索摘要报告

        Returns:
            报告文本
        """
        if df.empty:
            return "No breakouts found."

        report = []
        report.append(f"=== Breakout Search Report ===")
        report.append(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"\nTotal breakouts: {len(df)}")
        report.append(f"Unique symbols: {df['symbol'].nunique()}")
        report.append(f"\n--- Quality Distribution ---")
        report.append(f"Average combined score: {df['combined_score'].mean():.1f}")
        report.append(f"Average breakout score: {df['breakout_quality_score'].mean():.1f}")
        report.append(f"Average peak score: {df['peak_quality_score'].mean():.1f}")

        report.append(f"\n--- Top 10 Candidates ---")
        top10 = df.head(10)
        for idx, row in top10.iterrows():
            report.append(
                f"{row['symbol']:6s} | "
                f"{row['breakout_date']} | "
                f"Price: ${row['breakout_price']:7.2f} | "
                f"Score: {row['combined_score']:5.1f} | "
                f"Type: {row['breakout_type']:6s}"
            )

        return "\n".join(report)
```

---

## 八、使用示例

### 8.1 简单搜索

```python
from BreakoutStrategy.search import SearchEngine, ResultFormatter

# 1. 初始化搜索引擎
engine = SearchEngine()

# 2. 执行搜索（搜索过去7天的突破）
results = engine.search()

# 3. 查看结果
print(f"Found {len(results)} high-quality breakouts")
print(results[['symbol', 'breakout_date', 'combined_score']].head(10))

# 4. 保存结果
formatter = ResultFormatter()
formatter.save_to_file(results, 'output/breakouts_20240116.csv')

# 5. 生成报告
report = formatter.generate_summary_report(results)
print(report)
```

### 8.2 自定义搜索

```python
# 搜索过去30天的突破
results = engine.search(
    end_date='2024-01-15',
    historical_days=30
)

# 进一步筛选：只要跳空突破
gap_up_only = results[results['gap_up'] == True]

# 按质量分数降序
top_candidates = gap_up_only.sort_values('combined_score', ascending=False).head(20)
```

### 8.3 定时搜索

```python
import schedule
import time

def daily_search():
    """每日搜索任务"""
    engine = SearchEngine()
    results = engine.search()

    # 保存结果
    timestamp = datetime.now().strftime('%Y%m%d')
    formatter = ResultFormatter()
    formatter.save_to_file(results, f'output/breakouts_{timestamp}.csv')

    # 发送报告
    report = formatter.generate_summary_report(results)
    print(report)

    # 如果有高质量突破，添加到观察池
    if len(results) > 0:
        from BreakoutStrategy.observation import PoolManager
        pool_manager = PoolManager()

        entries = formatter.format_for_observation_pool(results)
        for entry in entries:
            # 根据突破日期决定加入哪个观察池
            if entry['breakout_date'] == datetime.now().date():
                pool_manager.add_to_realtime_pool(entry)
            else:
                pool_manager.add_to_daily_pool(entry)

# 每天收盘后执行（美东时间16:30）
schedule.every().day.at("16:30").do(daily_search)

while True:
    schedule.run_pending()
    time.sleep(60)
```

---

## 九、性能优化

### 9.1 增量搜索

对于已经扫描过的股票，只需检查最新数据：

```python
class IncrementalSearchEngine(SearchEngine):
    """增量搜索引擎"""

    def incremental_search(self, last_search_date: str) -> pd.DataFrame:
        """
        增量搜索：只检查自上次搜索以来的新突破

        Args:
            last_search_date: 上次搜索日期

        Returns:
            新的突破结果
        """
        # 只需要检查last_search_date之后的数据
        # 对于已知凸点，只需检查是否有新的突破
        # 对于新数据，需要重新识别凸点
        pass
```

### 9.2 分批处理

对于大股票池（如全市场扫描），分批处理：

```python
def search_in_batches(symbols: List[str], batch_size: int = 100):
    """分批搜索"""
    engine = SearchEngine()

    all_results = []
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        print(f"Processing batch {i//batch_size + 1}/{len(symbols)//batch_size + 1}")

        # 扫描当前批次
        results = engine.scanner.scan_multiple_symbols(batch, start_date, end_date)
        all_results.extend(results)

        # 保存中间结果（防止崩溃丢失）
        # ...

    return all_results
```

---

## 十、测试方案

```python
# tests/search/test_search_engine.py
import pytest
from BreakoutStrategy.search import SearchEngine
from datetime import datetime, timedelta

class TestSearchEngine:

    @pytest.fixture
    def engine(self):
        return SearchEngine()

    def test_search(self, engine):
        """测试搜索功能"""
        # 搜索过去7天
        end_date = datetime.now().strftime('%Y-%m-%d')
        results = engine.search(end_date=end_date, historical_days=7)

        # 验证结果格式
        assert 'symbol' in results.columns
        assert 'breakout_date' in results.columns
        assert 'combined_score' in results.columns

        # 验证质量分数范围
        if len(results) > 0:
            assert (results['combined_score'] >= 0).all()
            assert (results['combined_score'] <= 100).all()

    def test_scanner_single_symbol(self, engine):
        """测试单只股票扫描"""
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        result = engine.scanner.scan_symbol('AAPL', start_date, end_date)

        assert result['success'] == True
        assert 'peaks' in result
        assert 'breakouts' in result
        assert isinstance(result['peaks'], list)
```

---

## 十一、输出文件格式示例

### 11.1 CSV格式

```csv
symbol,breakout_date,breakout_price,breakout_type,peak_date,peak_price,peak_quality_score,breakout_quality_score,combined_score
AAPL,2024-01-15,195.50,yang,2023-12-20,190.00,85.5,88.3,87.2
TSLA,2024-01-14,248.50,yang,2023-11-10,245.00,92.3,90.7,91.3
NVDA,2024-01-13,520.00,gap_up,2024-01-05,510.00,78.5,95.2,88.4
```

### 11.2 观察池格式（JSON）

```json
[
  {
    "symbol": "AAPL",
    "breakout_date": "2024-01-15",
    "breakout_info": {
      "price": 195.50,
      "type": "yang",
      "quality_score": 88.3
    },
    "peak_info": {
      "date": "2023-12-20",
      "price": 190.00,
      "quality_score": 85.5
    },
    "add_date": "2024-01-16",
    "status": "pending"
  }
]
```

---

## 十二、待优化事项

1. **智能股票池**：
   - 当前使用全市场扫描，耗时较长
   - 可以先用简单规则筛选（如成交量突增、价格突破MA），再进行深度分析

2. **缓存机制**：
   - 缓存已识别的凸点和突破
   - 只检查新数据

3. **优先级队列**：
   - 对于大股票池，优先扫描活跃股票
   - 根据历史表现动态调整优先级

4. **并行优化**：
   - 当前使用multiprocessing，可以考虑分布式计算（如Ray）

---

**文档状态**：初稿完成
**下一步**：编写回测系统设计文档
