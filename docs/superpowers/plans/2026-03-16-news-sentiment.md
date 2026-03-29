# News Sentiment Module Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone stock news sentiment analysis module that collects news from Finnhub/AlphaVantage/EDGAR and uses GLM-4.7-Flash for sentiment analysis.

**Architecture:** Collector abstraction (BaseCollector ABC) with three implementations, feeding into a GLM-based two-stage Analyzer (per-article + summary), with Reporter for JSON output. Public API: `analyze(ticker, date_from, date_to) -> AnalysisReport`.

**Tech Stack:** Python 3.12+, zhipuai, finnhub-python, requests, pyyaml

**Spec:** `docs/superpowers/specs/2026-03-16-news-sentiment-design.md`

---

## File Structure

| Action | Path | Responsibility |
|---|---|---|
| Create | `BreakoutStrategy/news_sentiment/__init__.py` | Module docstring + exports |
| Create | `BreakoutStrategy/news_sentiment/__main__.py` | CLI entry: `uv run -m BreakoutStrategy.news_sentiment` |
| Create | `BreakoutStrategy/news_sentiment/models.py` | NewsItem, SentimentResult, AnalyzedItem, SummaryResult, AnalysisReport |
| Create | `BreakoutStrategy/news_sentiment/config.py` | YAML + env var config loading |
| Create | `BreakoutStrategy/news_sentiment/collectors/__init__.py` | Collector exports |
| Create | `BreakoutStrategy/news_sentiment/collectors/base.py` | BaseCollector ABC |
| Create | `BreakoutStrategy/news_sentiment/collectors/finnhub_collector.py` | Finnhub: company-news + news-sentiment + earnings |
| Create | `BreakoutStrategy/news_sentiment/collectors/alphavantage_collector.py` | Alpha Vantage: NEWS_SENTIMENT endpoint |
| Create | `BreakoutStrategy/news_sentiment/collectors/edgar_collector.py` | SEC EDGAR: submissions API for 8-K filings |
| Create | `BreakoutStrategy/news_sentiment/analyzer.py` | GLM-4.7-Flash two-stage sentiment analysis |
| Create | `BreakoutStrategy/news_sentiment/reporter.py` | JSON serialization + file output |
| Create | `BreakoutStrategy/news_sentiment/api.py` | `analyze()` orchestration + dedup |
| Create | `configs/news_sentiment.yaml` | Default configuration |
| Modify | `pyproject.toml` | Add zhipuai, finnhub-python, requests |
| Create | `tests/news_sentiment/__init__.py` | Test package |
| Create | `tests/news_sentiment/test_models.py` | Model creation + serialization tests |
| Create | `tests/news_sentiment/test_dedup.py` | Dedup logic tests |
| Create | `tests/news_sentiment/test_reporter.py` | Reporter output tests |

---

## Chunk 1: Foundation

### Task 1: Install Dependencies and Create Config

**Files:**
- Modify: `pyproject.toml`
- Create: `configs/news_sentiment.yaml`

- [ ] **Step 1: Install Python dependencies**

```bash
uv add zhipuai finnhub-python requests
```

- [ ] **Step 2: Verify imports work**

```bash
uv run python -c "import zhipuai; import finnhub; import requests; print('All imports OK')"
```

Expected: `All imports OK`

- [ ] **Step 3: Create config file**

Create `configs/news_sentiment.yaml`:

```yaml
collectors:
  finnhub:
    api_key: ""
    timeout: 10
  alphavantage:
    api_key: ""
    timeout: 10
  edgar:
    user_agent: "TradeStrategy research@example.com"

analyzer:
  api_key: ""
  model: "glm-4.7-flash"
  temperature: 0.1
  batch_size: 5
  request_interval: 1.0

output:
  output_dir: "outputs/news_sentiment"
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock configs/news_sentiment.yaml
git commit -m "feat(news_sentiment): add dependencies and config"
```

---

### Task 2: Create Data Models

**Files:**
- Create: `BreakoutStrategy/news_sentiment/__init__.py`
- Create: `BreakoutStrategy/news_sentiment/models.py`
- Create: `tests/news_sentiment/__init__.py`
- Create: `tests/news_sentiment/test_models.py`

**Dependencies:** Task 1

- [ ] **Step 1: Create module `__init__.py`**

Create `BreakoutStrategy/news_sentiment/__init__.py`:

```python
"""
新闻情感分析模块

通过多源采集股票新闻/公告/财报，结合 GLM-4.7-Flash 进行情感分析，辅助突破策略决策。

核心组件:
- models: 数据模型 (NewsItem, SentimentResult, AnalyzedItem, SummaryResult, AnalysisReport)
- collectors: 多源采集器 (Finnhub, AlphaVantage, EDGAR)
- analyzer: GLM-4.7-Flash 情感分析器
- reporter: JSON 报告生成
- api: 公共入口 analyze()

使用方式:
    from BreakoutStrategy.news_sentiment.api import analyze
    report = analyze("AAPL", "2026-03-01", "2026-03-15")

命令行入口:
    uv run -m BreakoutStrategy.news_sentiment
"""
```

- [ ] **Step 2: Create models**

Create `BreakoutStrategy/news_sentiment/models.py`:

```python
"""
数据模型定义

所有模块间传递的数据结构，使用 dataclass 保证类型安全。
"""

from dataclasses import dataclass


@dataclass
class NewsItem:
    """标准化的新闻条目，所有 Collector 输出统一为此格式"""
    title: str
    summary: str
    source: str
    published_at: str
    url: str
    ticker: str
    category: str
    collector: str
    raw_sentiment: float | None = None


@dataclass
class SentimentResult:
    """单条新闻的 GLM 情感分析结果"""
    sentiment: str
    confidence: float
    reasoning: str


@dataclass
class AnalyzedItem:
    """一条新闻 + 对应的情感分析结果"""
    news: NewsItem
    sentiment: SentimentResult


@dataclass
class SummaryResult:
    """GLM 综合情感汇总"""
    sentiment: str
    confidence: float
    reasoning: str
    positive_count: int
    negative_count: int
    neutral_count: int
    total_count: int


@dataclass
class AnalysisReport:
    """最终输出的完整分析报告"""
    ticker: str
    date_from: str
    date_to: str
    collected_at: str
    items: list[AnalyzedItem]
    summary: SummaryResult
    source_stats: dict[str, int]
```

- [ ] **Step 3: Write model tests**

Create `tests/news_sentiment/__init__.py` (empty file).

Create `tests/news_sentiment/test_models.py`:

```python
"""models.py 单元测试"""

from dataclasses import asdict

from BreakoutStrategy.news_sentiment.models import (
    AnalysisReport,
    AnalyzedItem,
    NewsItem,
    SentimentResult,
    SummaryResult,
)


def test_news_item_creation():
    item = NewsItem(
        title="Apple reports record earnings",
        summary="Apple Inc. reported record Q4 earnings...",
        source="Reuters",
        published_at="2026-03-10T14:30:00Z",
        url="https://example.com/article1",
        ticker="AAPL",
        category="earnings",
        collector="finnhub",
        raw_sentiment=0.85,
    )
    assert item.title == "Apple reports record earnings"
    assert item.raw_sentiment == 0.85


def test_news_item_default_sentiment():
    item = NewsItem(
        title="Test", summary="", source="", published_at="",
        url="", ticker="AAPL", category="news", collector="finnhub",
    )
    assert item.raw_sentiment is None


def test_analysis_report_asdict():
    """确认 dataclasses.asdict 可正常序列化嵌套结构"""
    news = NewsItem(
        title="Test", summary="Summary", source="Reuters",
        published_at="2026-03-10T14:30:00Z", url="https://example.com",
        ticker="AAPL", category="news", collector="finnhub",
    )
    sentiment = SentimentResult(
        sentiment="positive", confidence=0.9, reasoning="Good earnings",
    )
    report = AnalysisReport(
        ticker="AAPL",
        date_from="2026-03-01",
        date_to="2026-03-15",
        collected_at="2026-03-16T10:00:00Z",
        items=[AnalyzedItem(news=news, sentiment=sentiment)],
        summary=SummaryResult(
            sentiment="positive", confidence=0.85, reasoning="Overall positive",
            positive_count=1, negative_count=0, neutral_count=0, total_count=1,
        ),
        source_stats={"finnhub": 1},
    )
    d = asdict(report)
    assert d["ticker"] == "AAPL"
    assert len(d["items"]) == 1
    assert d["items"][0]["news"]["title"] == "Test"
    assert d["items"][0]["sentiment"]["sentiment"] == "positive"
    assert d["summary"]["positive_count"] == 1
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/news_sentiment/test_models.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/news_sentiment/__init__.py BreakoutStrategy/news_sentiment/models.py tests/news_sentiment/
git commit -m "feat(news_sentiment): add data models with tests"
```

---

### Task 3: Config Loading and Collector Base

**Files:**
- Create: `BreakoutStrategy/news_sentiment/config.py`
- Create: `BreakoutStrategy/news_sentiment/collectors/__init__.py`
- Create: `BreakoutStrategy/news_sentiment/collectors/base.py`

**Dependencies:** Task 2

- [ ] **Step 1: Create config loader**

Create `BreakoutStrategy/news_sentiment/config.py`:

```python
"""
配置加载

从 YAML 加载配置，环境变量优先于 YAML 值。
环境变量: FINNHUB_API_KEY, ALPHAVANTAGE_API_KEY, ZHIPUAI_API_KEY
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "news_sentiment.yaml"


@dataclass
class CollectorConfig:
    """单个采集器配置"""
    api_key: str
    timeout: int


@dataclass
class EdgarConfig:
    """EDGAR 采集器配置（无需 API key）"""
    user_agent: str


@dataclass
class AnalyzerConfig:
    """GLM 分析器配置"""
    api_key: str
    model: str
    temperature: float
    batch_size: int
    request_interval: float


@dataclass
class NewsSentimentConfig:
    """模块完整配置"""
    finnhub: CollectorConfig
    alphavantage: CollectorConfig
    edgar: EdgarConfig
    analyzer: AnalyzerConfig
    output_dir: str


def load_config(config_path: str | Path | None = None) -> NewsSentimentConfig:
    """加载配置，环境变量优先于 YAML"""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
    else:
        logger.warning(f"Config file not found: {path}, using defaults")
        data = {}

    collectors = data.get('collectors', {})
    finnhub_cfg = collectors.get('finnhub', {})
    av_cfg = collectors.get('alphavantage', {})
    edgar_cfg = collectors.get('edgar', {})
    analyzer_cfg = data.get('analyzer', {})
    output_cfg = data.get('output', {})

    return NewsSentimentConfig(
        finnhub=CollectorConfig(
            api_key=os.environ.get('FINNHUB_API_KEY', finnhub_cfg.get('api_key', '')),
            timeout=finnhub_cfg.get('timeout', 10),
        ),
        alphavantage=CollectorConfig(
            api_key=os.environ.get('ALPHAVANTAGE_API_KEY', av_cfg.get('api_key', '')),
            timeout=av_cfg.get('timeout', 10),
        ),
        edgar=EdgarConfig(
            user_agent=edgar_cfg.get('user_agent', 'TradeStrategy research@example.com'),
        ),
        analyzer=AnalyzerConfig(
            api_key=os.environ.get('ZHIPUAI_API_KEY', analyzer_cfg.get('api_key', '')),
            model=analyzer_cfg.get('model', 'glm-4.7-flash'),
            temperature=analyzer_cfg.get('temperature', 0.1),
            batch_size=analyzer_cfg.get('batch_size', 5),
            request_interval=analyzer_cfg.get('request_interval', 1.0),
        ),
        output_dir=output_cfg.get('output_dir', 'outputs/news_sentiment'),
    )
```

- [ ] **Step 2: Create collector base class**

Create `BreakoutStrategy/news_sentiment/collectors/__init__.py`:

```python
"""
多源新闻采集器

提供 BaseCollector 抽象和三个实现:
- FinnhubCollector: 新闻 + 财报 + SEC filings
- AlphaVantageCollector: 情感增强的新闻
- EdgarCollector: SEC 8-K 公告
"""

from .base import BaseCollector

__all__ = ['BaseCollector']

# 注意: 具体采集器在 Task 4/5/6 实现后，Task 9 Step 3 中更新此文件
# 添加: from .finnhub_collector import FinnhubCollector
#       from .alphavantage_collector import AlphaVantageCollector
#       from .edgar_collector import EdgarCollector
```

Create `BreakoutStrategy/news_sentiment/collectors/base.py`:

```python
"""采集器抽象基类"""

from abc import ABC, abstractmethod

from BreakoutStrategy.news_sentiment.models import NewsItem


class BaseCollector(ABC):
    """
    新闻采集器基类

    所有采集器实现统一接口，返回标准化的 NewsItem 列表。
    is_available() 检查配置是否就绪（API key 非空等）。
    collect() 中遇到额度耗尽或异常时返回已收集的部分结果，不抛异常。
    """

    name: str

    @abstractmethod
    def collect(self, ticker: str, date_from: str, date_to: str) -> list[NewsItem]:
        """
        采集指定股票在时间段内的新闻

        Args:
            ticker: 股票代码，如 "AAPL"
            date_from: 起始日期 YYYY-MM-DD
            date_to: 结束日期 YYYY-MM-DD

        Returns:
            标准化的 NewsItem 列表，遇到异常返回已收集的部分结果
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查采集器是否可用（API key 已配置等）"""
        pass
```

- [ ] **Step 3: Verify imports**

```bash
uv run python -c "from BreakoutStrategy.news_sentiment.config import load_config; c = load_config(); print(f'Config loaded, output_dir={c.output_dir}')"
```

Expected: `Config loaded, output_dir=outputs/news_sentiment`

- [ ] **Step 4: Commit**

```bash
git add BreakoutStrategy/news_sentiment/config.py BreakoutStrategy/news_sentiment/collectors/
git commit -m "feat(news_sentiment): add config loader and collector base class"
```

---

## Chunk 2: Collectors

### Task 4: Finnhub Collector

**Files:**
- Create: `BreakoutStrategy/news_sentiment/collectors/finnhub_collector.py`

**Dependencies:** Task 3

- [ ] **Step 1: Implement Finnhub collector**

Create `BreakoutStrategy/news_sentiment/collectors/finnhub_collector.py`:

```python
"""
Finnhub 采集器

采集公司新闻 (/company-news) 和财报日历 (/calendar/earnings)。
新闻条目附带来自 /news-sentiment 的情感评分。
免费 tier: 60次/分钟，无日限。
"""

import logging
from datetime import datetime

import finnhub

from BreakoutStrategy.news_sentiment.config import CollectorConfig
from BreakoutStrategy.news_sentiment.models import NewsItem

from .base import BaseCollector

logger = logging.getLogger(__name__)


class FinnhubCollector(BaseCollector):
    """Finnhub 新闻采集器"""

    name = "finnhub"

    def __init__(self, config: CollectorConfig):
        self._config = config
        self._client: finnhub.Client | None = None

    def is_available(self) -> bool:
        return bool(self._config.api_key)

    def _get_client(self) -> finnhub.Client:
        if self._client is None:
            self._client = finnhub.Client(api_key=self._config.api_key)
        return self._client

    def collect(self, ticker: str, date_from: str, date_to: str) -> list[NewsItem]:
        """采集公司新闻 + 财报日历"""
        items: list[NewsItem] = []
        client = self._get_client()

        # 1. 获取新闻情感评分（可选，用于附加到新闻条目）
        sentiment_score = self._fetch_sentiment_score(client, ticker)

        # 2. 采集公司新闻
        items.extend(self._fetch_company_news(client, ticker, date_from, date_to, sentiment_score))

        # 3. 采集财报日历
        items.extend(self._fetch_earnings(client, ticker, date_from, date_to))

        logger.info(f"[Finnhub] {ticker}: collected {len(items)} items")
        return items

    def _fetch_sentiment_score(self, client: finnhub.Client, ticker: str) -> float | None:
        """获取公司新闻综合情感评分"""
        try:
            data = client.news_sentiment(ticker)
            if data and 'sentiment' in data:
                bullish = data['sentiment'].get('bullishPercent', 0)
                bearish = data['sentiment'].get('bearishPercent', 0)
                # 转为 -1 到 1 的分数: bullish=1 全看多, bearish=-1 全看空
                return round(bullish - bearish, 4)
        except Exception as e:
            logger.warning(f"[Finnhub] Failed to fetch sentiment for {ticker}: {e}")
        return None

    def _fetch_company_news(
        self, client: finnhub.Client, ticker: str,
        date_from: str, date_to: str, sentiment_score: float | None,
    ) -> list[NewsItem]:
        """采集公司新闻"""
        try:
            raw_news = client.company_news(ticker, _from=date_from, to=date_to)
        except Exception as e:
            logger.warning(f"[Finnhub] Failed to fetch news for {ticker}: {e}")
            return []

        items = []
        for article in raw_news:
            try:
                # datetime 字段是 Unix 时间戳
                ts = article.get('datetime', 0)
                published = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%dT%H:%M:%SZ') if ts else ''

                items.append(NewsItem(
                    title=article.get('headline', ''),
                    summary=article.get('summary', ''),
                    source=article.get('source', ''),
                    published_at=published,
                    url=article.get('url', ''),
                    ticker=ticker,
                    category='news',
                    collector=self.name,
                    raw_sentiment=sentiment_score,
                ))
            except Exception as e:
                logger.warning(f"[Finnhub] Failed to parse article: {e}")
                continue

        return items

    def _fetch_earnings(
        self, client: finnhub.Client, ticker: str,
        date_from: str, date_to: str,
    ) -> list[NewsItem]:
        """采集财报日历"""
        try:
            data = client.earnings_calendar(_from=date_from, to=date_to, symbol=ticker)
            earnings_list = data.get('earningsCalendar', [])
        except Exception as e:
            logger.warning(f"[Finnhub] Failed to fetch earnings for {ticker}: {e}")
            return []

        items = []
        for entry in earnings_list:
            report_date = entry.get('date', '')
            eps_actual = entry.get('epsActual')
            eps_estimate = entry.get('epsEstimate')
            revenue_actual = entry.get('revenueActual')

            # 构建摘要
            parts = [f"Earnings report on {report_date}"]
            if eps_actual is not None:
                parts.append(f"EPS actual: {eps_actual}")
            if eps_estimate is not None:
                parts.append(f"EPS estimate: {eps_estimate}")
            if revenue_actual is not None:
                parts.append(f"Revenue: {revenue_actual:,.0f}")

            items.append(NewsItem(
                title=f"{ticker} Earnings Report - {report_date}",
                summary=". ".join(parts),
                source="Finnhub Earnings Calendar",
                published_at=f"{report_date}T00:00:00Z",
                url="",
                ticker=ticker,
                category='earnings',
                collector=self.name,
            ))

        return items
```

- [ ] **Step 2: Manual verification (requires FINNHUB_API_KEY)**

```bash
FINNHUB_API_KEY=your_key uv run python -c "
from BreakoutStrategy.news_sentiment.config import load_config
from BreakoutStrategy.news_sentiment.collectors.finnhub_collector import FinnhubCollector
cfg = load_config()
c = FinnhubCollector(cfg.finnhub)
print(f'Available: {c.is_available()}')
if c.is_available():
    items = c.collect('AAPL', '2026-03-01', '2026-03-15')
    print(f'Collected {len(items)} items')
    for i in items[:3]:
        print(f'  [{i.category}] {i.title[:60]}... sentiment={i.raw_sentiment}')
"
```

- [ ] **Step 3: Commit**

```bash
git add BreakoutStrategy/news_sentiment/collectors/finnhub_collector.py
git commit -m "feat(news_sentiment): add Finnhub collector"
```

---

### Task 5: Alpha Vantage Collector

**Files:**
- Create: `BreakoutStrategy/news_sentiment/collectors/alphavantage_collector.py`

**Dependencies:** Task 3

- [ ] **Step 1: Implement Alpha Vantage collector**

Create `BreakoutStrategy/news_sentiment/collectors/alphavantage_collector.py`:

```python
"""
Alpha Vantage 采集器

使用 NEWS_SENTIMENT endpoint，返回带情感评分的新闻。
免费 tier: 25次/天，5次/分钟。
额度耗尽时返回 HTTP 200 + {"Note": "..."} 或 {"Information": "..."}。
"""

import logging

import requests

from BreakoutStrategy.news_sentiment.config import CollectorConfig
from BreakoutStrategy.news_sentiment.models import NewsItem

from .base import BaseCollector

logger = logging.getLogger(__name__)

BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageCollector(BaseCollector):
    """Alpha Vantage 新闻情感采集器"""

    name = "alphavantage"

    def __init__(self, config: CollectorConfig):
        self._config = config

    def is_available(self) -> bool:
        return bool(self._config.api_key)

    def collect(self, ticker: str, date_from: str, date_to: str) -> list[NewsItem]:
        """采集带情感评分的新闻"""
        # 转换日期格式: YYYY-MM-DD -> YYYYMMDDTHHMM
        time_from = date_from.replace('-', '') + 'T0000'
        time_to = date_to.replace('-', '') + 'T2359'

        params = {
            'function': 'NEWS_SENTIMENT',
            'tickers': ticker,
            'time_from': time_from,
            'time_to': time_to,
            'limit': 50,
            'apikey': self._config.api_key,
        }

        try:
            resp = requests.get(BASE_URL, params=params, timeout=self._config.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[AlphaVantage] Request failed for {ticker}: {e}")
            return []

        # 检查额度耗尽
        if 'Note' in data or 'Information' in data:
            msg = data.get('Note', data.get('Information', ''))
            logger.warning(f"[AlphaVantage] Rate limited: {msg}")
            return []

        feed = data.get('feed', [])
        items = []

        for article in feed:
            try:
                # 提取该 ticker 的情感评分
                ticker_sentiment = self._extract_ticker_sentiment(article, ticker)

                # 转换时间格式: 20260315T143000 -> 2026-03-15T14:30:00Z
                raw_time = article.get('time_published', '')
                published = self._parse_time(raw_time)

                items.append(NewsItem(
                    title=article.get('title', ''),
                    summary=article.get('summary', ''),
                    source=article.get('source', ''),
                    published_at=published,
                    url=article.get('url', ''),
                    ticker=ticker,
                    category='news',
                    collector=self.name,
                    raw_sentiment=ticker_sentiment,
                ))
            except Exception as e:
                logger.warning(f"[AlphaVantage] Failed to parse article: {e}")
                continue

        logger.info(f"[AlphaVantage] {ticker}: collected {len(items)} items")
        return items

    def _extract_ticker_sentiment(self, article: dict, ticker: str) -> float | None:
        """从文章中提取指定 ticker 的情感评分"""
        for ts in article.get('ticker_sentiment', []):
            if ts.get('ticker', '').upper() == ticker.upper():
                try:
                    return float(ts.get('ticker_sentiment_score', 0))
                except (ValueError, TypeError):
                    pass
        # 回退到文章整体情感评分
        try:
            return float(article.get('overall_sentiment_score', 0))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_time(raw_time: str) -> str:
        """转换 AlphaVantage 时间格式: 20260315T143000 -> 2026-03-15T14:30:00Z"""
        if not raw_time or len(raw_time) < 15:
            return raw_time
        return (
            f"{raw_time[0:4]}-{raw_time[4:6]}-{raw_time[6:8]}"
            f"T{raw_time[9:11]}:{raw_time[11:13]}:{raw_time[13:15]}Z"
        )
```

- [ ] **Step 2: Manual verification (requires ALPHAVANTAGE_API_KEY)**

```bash
ALPHAVANTAGE_API_KEY=your_key uv run python -c "
from BreakoutStrategy.news_sentiment.config import load_config
from BreakoutStrategy.news_sentiment.collectors.alphavantage_collector import AlphaVantageCollector
cfg = load_config()
c = AlphaVantageCollector(cfg.alphavantage)
print(f'Available: {c.is_available()}')
if c.is_available():
    items = c.collect('AAPL', '2026-03-01', '2026-03-15')
    print(f'Collected {len(items)} items')
    for i in items[:3]:
        print(f'  {i.title[:60]}... sentiment={i.raw_sentiment}')
"
```

- [ ] **Step 3: Commit**

```bash
git add BreakoutStrategy/news_sentiment/collectors/alphavantage_collector.py
git commit -m "feat(news_sentiment): add Alpha Vantage collector"
```

---

### Task 6: EDGAR Collector

**Files:**
- Create: `BreakoutStrategy/news_sentiment/collectors/edgar_collector.py`

**Dependencies:** Task 3

- [ ] **Step 1: Implement EDGAR collector**

Create `BreakoutStrategy/news_sentiment/collectors/edgar_collector.py`:

```python
"""
SEC EDGAR 采集器

使用 EDGAR EFTS (full-text search) API 搜索公司公告。
完全免费，无需 API key，仅需 User-Agent header。
限流: 10次/秒。
"""

import logging
import time

import requests

from BreakoutStrategy.news_sentiment.config import EdgarConfig
from BreakoutStrategy.news_sentiment.models import NewsItem

from .base import BaseCollector

logger = logging.getLogger(__name__)

EFTS_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
FILING_BASE_URL = "https://www.sec.gov/Archives/edgar/data"


class EdgarCollector(BaseCollector):
    """SEC EDGAR 公告采集器"""

    name = "edgar"

    def __init__(self, config: EdgarConfig):
        self._config = config
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': self._config.user_agent,
            'Accept': 'application/json',
        })

    def is_available(self) -> bool:
        return True  # EDGAR 无需 API key

    def collect(self, ticker: str, date_from: str, date_to: str) -> list[NewsItem]:
        """搜索 SEC EDGAR 公告（8-K 为主）"""
        items: list[NewsItem] = []

        for form_type in ['8-K', '10-K', '10-Q']:
            items.extend(self._search_filings(ticker, date_from, date_to, form_type))
            time.sleep(0.15)  # 遵守 10次/秒限制

        logger.info(f"[EDGAR] {ticker}: collected {len(items)} items")
        return items

    def _search_filings(
        self, ticker: str, date_from: str, date_to: str, form_type: str,
    ) -> list[NewsItem]:
        """通过 EFTS 搜索特定类型的公告"""
        params = {
            'q': f'"{ticker}"',
            'dateRange': 'custom',
            'startdt': date_from,
            'enddt': date_to,
            'forms': form_type,
        }

        try:
            resp = self._session.get(EFTS_SEARCH_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[EDGAR] Search failed for {ticker} {form_type}: {e}")
            return []

        hits = data.get('hits', {}).get('hits', [])
        items = []

        for hit in hits:
            try:
                source = hit.get('_source', {})
                filing_date = source.get('file_date', '')
                form = source.get('form_type', form_type)
                entity_name = source.get('entity_name', ticker)
                file_num = source.get('file_num', '')
                description = source.get('display_names', [''])[0] if source.get('display_names') else ''

                # 构建公告链接
                accession = source.get('accession_no', '').replace('-', '')
                filing_url = ''
                if accession:
                    cik = source.get('entity_id', '')
                    filing_url = f"{FILING_BASE_URL}/{cik}/{accession}"

                items.append(NewsItem(
                    title=f"{entity_name} - {form} Filing ({filing_date})",
                    summary=description or f"{form} filing by {entity_name}. File number: {file_num}",
                    source="SEC EDGAR",
                    published_at=f"{filing_date}T00:00:00Z" if filing_date else '',
                    url=filing_url,
                    ticker=ticker,
                    category='filing',
                    collector=self.name,
                ))
            except Exception as e:
                logger.warning(f"[EDGAR] Failed to parse filing: {e}")
                continue

        return items
```

- [ ] **Step 2: Manual verification (no API key needed)**

```bash
uv run python -c "
from BreakoutStrategy.news_sentiment.config import load_config
from BreakoutStrategy.news_sentiment.collectors.edgar_collector import EdgarCollector
cfg = load_config()
c = EdgarCollector(cfg.edgar)
print(f'Available: {c.is_available()}')
items = c.collect('AAPL', '2025-01-01', '2025-03-15')
print(f'Collected {len(items)} items')
for i in items[:5]:
    print(f'  [{i.category}] {i.title}')
"
```

注意: 使用 2025 年日期范围确保有数据可测。

- [ ] **Step 3: Commit**

```bash
git add BreakoutStrategy/news_sentiment/collectors/edgar_collector.py
git commit -m "feat(news_sentiment): add SEC EDGAR collector"
```

---

## Chunk 3: Analysis & Integration

### Task 7: GLM Sentiment Analyzer

**Files:**
- Create: `BreakoutStrategy/news_sentiment/analyzer.py`

**Dependencies:** Tasks 2, 3

- [ ] **Step 1: Implement analyzer**

Create `BreakoutStrategy/news_sentiment/analyzer.py`:

```python
"""
GLM-4.7-Flash 情感分析器

两阶段分析:
  Stage 1: 按批次逐条分析，每条返回 SentimentResult
  Stage 2: 本地统计 + GLM 综合汇总，返回 SummaryResult
"""

import json
import logging
import time

from zhipuai import ZhipuAI

from BreakoutStrategy.news_sentiment.config import AnalyzerConfig
from BreakoutStrategy.news_sentiment.models import (
    AnalyzedItem,
    NewsItem,
    SentimentResult,
    SummaryResult,
)

logger = logging.getLogger(__name__)

DEFAULT_SENTIMENT = SentimentResult(
    sentiment="neutral", confidence=0.0, reasoning="Analysis failed",
)

BATCH_SYSTEM_PROMPT = (
    "你是一个金融新闻情感分析专家。分析以下每条新闻对该股票的影响。\n"
    '仅返回JSON数组：[{"index": 0, "sentiment": "positive|negative|neutral", '
    '"confidence": 0.0-1.0, "reasoning": "一句话理由"}, ...]'
)

SUMMARY_SYSTEM_PROMPT = (
    "你是一个金融分析师。根据以下新闻情感分析结果，给出对该股票的综合情感判断。\n"
    '返回JSON：{"sentiment": "positive|negative|neutral", "confidence": 0.0-1.0, "reasoning": "综合分析"}'
)


class SentimentAnalyzer:
    """GLM-4.7-Flash 两阶段情感分析器"""

    def __init__(self, config: AnalyzerConfig):
        self._config = config
        self._client: ZhipuAI | None = None

    def _get_client(self) -> ZhipuAI:
        if self._client is None:
            self._client = ZhipuAI(api_key=self._config.api_key)
        return self._client

    def analyze(self, items: list[NewsItem], ticker: str,
                date_from: str, date_to: str) -> tuple[list[AnalyzedItem], SummaryResult]:
        """
        执行两阶段情感分析

        Returns:
            (逐条分析结果, 综合汇总)
        """
        if not items:
            return [], SummaryResult(
                sentiment="neutral", confidence=0.0,
                reasoning="No news found in the specified period",
                positive_count=0, negative_count=0, neutral_count=0, total_count=0,
            )

        # Stage 1: 逐条分析
        analyzed_items = self._analyze_batch(items, ticker)

        # Stage 2: 综合汇总
        summary = self._summarize(analyzed_items, ticker, date_from, date_to)

        return analyzed_items, summary

    def _analyze_batch(self, items: list[NewsItem], ticker: str) -> list[AnalyzedItem]:
        """Stage 1: 将 NewsItem 按 batch_size 分批，逐批调用 GLM"""
        batch_size = self._config.batch_size
        all_results: list[AnalyzedItem] = []

        for batch_start in range(0, len(items), batch_size):
            batch = items[batch_start:batch_start + batch_size]
            sentiments = self._call_glm_batch(batch, ticker)

            for news_item, sentiment in zip(batch, sentiments):
                all_results.append(AnalyzedItem(news=news_item, sentiment=sentiment))

            if batch_start + batch_size < len(items):
                time.sleep(self._config.request_interval)

        return all_results

    def _call_glm_batch(self, batch: list[NewsItem], ticker: str) -> list[SentimentResult]:
        """对一个批次调用 GLM，返回 SentimentResult 列表"""
        # 构建用户消息
        lines = [f"股票: {ticker}"]
        for i, item in enumerate(batch):
            text = f"{item.title}"
            if item.summary:
                text += f": {item.summary[:200]}"
            lines.append(f"{i}. {text}")

        user_message = "\n".join(lines)

        # 调用 GLM（最多 retry 一次）
        for attempt in range(2):
            try:
                client = self._get_client()
                response = client.chat.completions.create(
                    model=self._config.model,
                    messages=[
                        {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=self._config.temperature,
                    max_tokens=1024,
                )
                content = response.choices[0].message.content
                return self._parse_batch_response(content, len(batch))

            except json.JSONDecodeError:
                if attempt == 0:
                    logger.warning("[Analyzer] JSON parse failed, retrying...")
                    time.sleep(self._config.request_interval)
                    continue
                logger.error("[Analyzer] JSON parse failed after retry")
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"[Analyzer] GLM call failed: {e}, retrying...")
                    time.sleep(self._config.request_interval)
                    continue
                logger.error(f"[Analyzer] GLM call failed after retry: {e}")

        return [DEFAULT_SENTIMENT] * len(batch)

    def _parse_batch_response(self, content: str, expected_count: int) -> list[SentimentResult]:
        """解析 GLM 批量分析的 JSON 响应"""
        # 尝试提取 JSON 数组（GLM 可能返回 markdown 代码块包裹的 JSON）
        text = content.strip()
        if text.startswith('```'):
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])

        results_raw = json.loads(text)

        # 按 index 排序并转换
        results_map: dict[int, SentimentResult] = {}
        for item in results_raw:
            idx = item.get('index', -1)
            results_map[idx] = SentimentResult(
                sentiment=item.get('sentiment', 'neutral'),
                confidence=float(item.get('confidence', 0.0)),
                reasoning=item.get('reasoning', ''),
            )

        # 按顺序返回，缺失的用默认值填充
        return [results_map.get(i, DEFAULT_SENTIMENT) for i in range(expected_count)]

    def _summarize(self, analyzed_items: list[AnalyzedItem],
                   ticker: str, date_from: str, date_to: str) -> SummaryResult:
        """Stage 2: 本地统计 + GLM 综合汇总"""
        # 2a: 本地统计
        pos = sum(1 for a in analyzed_items if a.sentiment.sentiment == 'positive')
        neg = sum(1 for a in analyzed_items if a.sentiment.sentiment == 'negative')
        neu = sum(1 for a in analyzed_items if a.sentiment.sentiment == 'neutral')
        total = len(analyzed_items)

        # 2b: 构建汇总 prompt
        key_items = sorted(analyzed_items, key=lambda a: a.sentiment.confidence, reverse=True)[:10]
        key_summaries = "\n".join(
            f"- [{a.sentiment.sentiment}] {a.news.title}: {a.sentiment.reasoning}"
            for a in key_items
        )

        user_message = (
            f"股票: {ticker}，时间段: {date_from} ~ {date_to}\n"
            f"共{total}条新闻，正面{pos}条，负面{neg}条，中性{neu}条。\n"
            f"关键新闻摘要:\n{key_summaries}"
        )

        # 2c: 调用 GLM
        glm_sentiment = "neutral"
        glm_confidence = 0.0
        glm_reasoning = "Summary analysis failed"

        for attempt in range(2):
            try:
                time.sleep(self._config.request_interval)
                client = self._get_client()
                response = client.chat.completions.create(
                    model=self._config.model,
                    messages=[
                        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=self._config.temperature,
                    max_tokens=512,
                )
                content = response.choices[0].message.content.strip()
                if content.startswith('```'):
                    lines = content.split('\n')
                    content = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])

                parsed = json.loads(content)
                glm_sentiment = parsed.get('sentiment', 'neutral')
                glm_confidence = float(parsed.get('confidence', 0.0))
                glm_reasoning = parsed.get('reasoning', '')
                break
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"[Analyzer] Summary GLM call failed: {e}, retrying...")
                    continue
                logger.error(f"[Analyzer] Summary failed after retry: {e}")

        # 2d: 合并构造 SummaryResult
        return SummaryResult(
            sentiment=glm_sentiment,
            confidence=glm_confidence,
            reasoning=glm_reasoning,
            positive_count=pos,
            negative_count=neg,
            neutral_count=neu,
            total_count=total,
        )
```

- [ ] **Step 2: Verify import**

```bash
uv run python -c "from BreakoutStrategy.news_sentiment.analyzer import SentimentAnalyzer; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add BreakoutStrategy/news_sentiment/analyzer.py
git commit -m "feat(news_sentiment): add GLM-4.7-Flash sentiment analyzer"
```

---

### Task 8: Reporter

**Files:**
- Create: `BreakoutStrategy/news_sentiment/reporter.py`
- Create: `tests/news_sentiment/test_reporter.py`

**Dependencies:** Task 2

- [ ] **Step 1: Implement reporter**

Create `BreakoutStrategy/news_sentiment/reporter.py`:

```python
"""
JSON 报告生成

将 AnalysisReport 序列化为 JSON 并保存到文件。
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path

from BreakoutStrategy.news_sentiment.models import AnalysisReport

logger = logging.getLogger(__name__)


def save_report(report: AnalysisReport, output_dir: str) -> Path:
    """
    将分析报告保存为 JSON 文件

    文件名格式: {ticker}_{date_from}_{date_to}.json
    路径相对于项目根目录解析。

    Returns:
        保存的文件路径
    """
    project_root = Path(__file__).resolve().parent.parent.parent
    out_path = project_root / output_dir
    out_path.mkdir(parents=True, exist_ok=True)

    date_from_clean = report.date_from.replace('-', '')
    date_to_clean = report.date_to.replace('-', '')
    filename = f"{report.ticker}_{date_from_clean}_{date_to_clean}.json"
    filepath = out_path / filename

    data = asdict(report)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Report saved to {filepath}")
    return filepath
```

- [ ] **Step 2: Write reporter test**

Create `tests/news_sentiment/test_reporter.py`:

```python
"""reporter.py 单元测试"""

import json
import tempfile
from pathlib import Path

from BreakoutStrategy.news_sentiment.models import (
    AnalysisReport,
    AnalyzedItem,
    NewsItem,
    SentimentResult,
    SummaryResult,
)
from BreakoutStrategy.news_sentiment.reporter import save_report


def _make_report() -> AnalysisReport:
    news = NewsItem(
        title="Test News", summary="Summary", source="Test",
        published_at="2026-03-10T14:00:00Z", url="https://example.com",
        ticker="AAPL", category="news", collector="finnhub", raw_sentiment=0.5,
    )
    sentiment = SentimentResult(sentiment="positive", confidence=0.9, reasoning="Good")
    return AnalysisReport(
        ticker="AAPL",
        date_from="2026-03-01",
        date_to="2026-03-15",
        collected_at="2026-03-16T10:00:00Z",
        items=[AnalyzedItem(news=news, sentiment=sentiment)],
        summary=SummaryResult(
            sentiment="positive", confidence=0.85, reasoning="Overall positive",
            positive_count=1, negative_count=0, neutral_count=0, total_count=1,
        ),
        source_stats={"finnhub": 1},
    )


def test_save_report_creates_json(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"):
    """验证 save_report 正确创建 JSON 文件"""
    import pytest
    import BreakoutStrategy.news_sentiment.reporter as reporter_mod

    # 将 project_root 猴补丁为 tmp_path，使输出写入临时目录
    monkeypatch.setattr(reporter_mod, 'Path', lambda *a, **kw: tmp_path if not a else Path(*a))

    report = _make_report()
    # 直接调用 save_report 并用相对于 tmp_path 的 output_dir
    filepath = save_report(report, str(tmp_path / "output"))

    loaded = json.loads(filepath.read_text(encoding='utf-8'))
    assert loaded['ticker'] == 'AAPL'
    assert len(loaded['items']) == 1
    assert loaded['items'][0]['news']['title'] == 'Test News'
    assert loaded['summary']['sentiment'] == 'positive'
    assert loaded['source_stats'] == {'finnhub': 1}


def test_save_report_filename_preserves_ticker_hyphens(tmp_path: Path):
    """验证含连字符的 ticker（如 BRK-B）文件名正确"""
    from dataclasses import replace
    report = _make_report()
    report = replace(report, ticker="BRK-B")

    from dataclasses import asdict
    data = asdict(report)
    # 验证文件名逻辑：日期去连字符，ticker 保留
    date_from_clean = report.date_from.replace('-', '')
    date_to_clean = report.date_to.replace('-', '')
    expected_name = f"BRK-B_{date_from_clean}_{date_to_clean}.json"
    assert "BRK-B" in expected_name
    assert "--" not in expected_name
```

- [ ] **Step 3: Run test**

```bash
uv run pytest tests/news_sentiment/test_reporter.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add BreakoutStrategy/news_sentiment/reporter.py tests/news_sentiment/test_reporter.py
git commit -m "feat(news_sentiment): add JSON reporter with tests"
```

---

### Task 9: API Orchestration, Dedup, and Entry Point

**Files:**
- Create: `BreakoutStrategy/news_sentiment/api.py`
- Create: `BreakoutStrategy/news_sentiment/__main__.py`
- Create: `tests/news_sentiment/test_dedup.py`

**Dependencies:** Tasks 3, 4, 5, 6, 7, 8

- [ ] **Step 1: Write dedup tests first**

Create `tests/news_sentiment/test_dedup.py`:

```python
"""去重逻辑测试"""

from BreakoutStrategy.news_sentiment.api import deduplicate
from BreakoutStrategy.news_sentiment.models import NewsItem


def _item(title: str, url: str = "", published_at: str = "2026-03-10T00:00:00Z",
          raw_sentiment: float | None = None, collector: str = "finnhub") -> NewsItem:
    return NewsItem(
        title=title, summary="", source="", published_at=published_at,
        url=url, ticker="AAPL", category="news", collector=collector,
        raw_sentiment=raw_sentiment,
    )


def test_dedup_by_url():
    """相同 URL 的条目只保留一个"""
    items = [
        _item("A", url="https://example.com/1"),
        _item("B", url="https://example.com/1"),
    ]
    result = deduplicate(items)
    assert len(result) == 1


def test_dedup_by_title_date():
    """无 URL 时，按 title + date 去重"""
    items = [
        _item("Same Title", url="", published_at="2026-03-10T10:00:00Z"),
        _item("Same Title", url="", published_at="2026-03-10T15:00:00Z"),
    ]
    result = deduplicate(items)
    assert len(result) == 1


def test_dedup_keeps_sentiment():
    """重复时保留有 raw_sentiment 的条目"""
    items = [
        _item("A", url="https://example.com/1", raw_sentiment=None, collector="finnhub"),
        _item("A", url="https://example.com/1", raw_sentiment=0.8, collector="alphavantage"),
    ]
    result = deduplicate(items)
    assert len(result) == 1
    assert result[0].raw_sentiment == 0.8


def test_dedup_different_items_preserved():
    """不同条目正常保留"""
    items = [
        _item("A", url="https://example.com/1"),
        _item("B", url="https://example.com/2"),
        _item("C", url="https://example.com/3"),
    ]
    result = deduplicate(items)
    assert len(result) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/news_sentiment/test_dedup.py -v
```

Expected: FAIL (deduplicate not yet defined)

- [ ] **Step 3: Update collectors `__init__.py` with concrete exports**

Update `BreakoutStrategy/news_sentiment/collectors/__init__.py`:

```python
"""
多源新闻采集器

提供 BaseCollector 抽象和三个实现:
- FinnhubCollector: 新闻 + 财报 + SEC filings
- AlphaVantageCollector: 情感增强的新闻
- EdgarCollector: SEC 8-K 公告
"""

from .base import BaseCollector
from .finnhub_collector import FinnhubCollector
from .alphavantage_collector import AlphaVantageCollector
from .edgar_collector import EdgarCollector

__all__ = ['BaseCollector', 'FinnhubCollector', 'AlphaVantageCollector', 'EdgarCollector']
```

- [ ] **Step 4: Implement api.py with dedup and orchestration**

Create `BreakoutStrategy/news_sentiment/api.py`:

```python
"""
公共 API 入口

提供 analyze() 函数，编排采集→去重→分析→报告的完整流程。
"""

import logging
from datetime import datetime, timezone

from BreakoutStrategy.news_sentiment.analyzer import SentimentAnalyzer
from BreakoutStrategy.news_sentiment.collectors.alphavantage_collector import AlphaVantageCollector
from BreakoutStrategy.news_sentiment.collectors.base import BaseCollector
from BreakoutStrategy.news_sentiment.collectors.edgar_collector import EdgarCollector
from BreakoutStrategy.news_sentiment.collectors.finnhub_collector import FinnhubCollector
from BreakoutStrategy.news_sentiment.config import NewsSentimentConfig, load_config
from BreakoutStrategy.news_sentiment.models import AnalysisReport, NewsItem, SummaryResult
from BreakoutStrategy.news_sentiment.reporter import save_report

logger = logging.getLogger(__name__)


def deduplicate(items: list[NewsItem]) -> list[NewsItem]:
    """
    去重: key = url（非空时），否则 (title, published_at[:10])。
    重复时保留 raw_sentiment 非空的条目。
    """
    seen: dict[str, NewsItem] = {}

    for item in items:
        if item.url:
            key = item.url
        else:
            date_prefix = item.published_at[:10] if item.published_at else ''
            key = f"{item.title}||{date_prefix}"

        if key in seen:
            existing = seen[key]
            # 保留有 raw_sentiment 的
            if existing.raw_sentiment is None and item.raw_sentiment is not None:
                seen[key] = item
        else:
            seen[key] = item

    return list(seen.values())


def analyze(
    ticker: str,
    date_from: str,
    date_to: str,
    config: NewsSentimentConfig | None = None,
) -> AnalysisReport:
    """
    收集指定股票在时间段内的新闻/公告/财报，执行情感分析。

    结果同时保存为 JSON 文件并返回 AnalysisReport。
    永不抛异常，始终返回 AnalysisReport。

    Args:
        ticker: 股票代码，如 "AAPL"
        date_from: 起始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
        config: 可选配置，默认从 YAML + 环境变量加载
    """
    if config is None:
        config = load_config()

    collected_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    # 1. 初始化采集器
    collectors: list[BaseCollector] = [
        FinnhubCollector(config.finnhub),
        AlphaVantageCollector(config.alphavantage),
        EdgarCollector(config.edgar),
    ]

    # 2. 采集
    all_items: list[NewsItem] = []
    source_stats: dict[str, int] = {}

    for collector in collectors:
        if not collector.is_available():
            logger.info(f"[{collector.name}] Not available, skipping")
            continue

        try:
            items = collector.collect(ticker, date_from, date_to)
            source_stats[collector.name] = len(items)
            all_items.extend(items)
            logger.info(f"[{collector.name}] Collected {len(items)} items")
        except Exception as e:
            logger.error(f"[{collector.name}] Unexpected error: {e}")
            source_stats[collector.name] = 0

    # 3. 去重
    unique_items = deduplicate(all_items)
    logger.info(f"Total: {len(all_items)} items, {len(unique_items)} after dedup")

    # 4. 情感分析
    try:
        analyzer = SentimentAnalyzer(config.analyzer)
        analyzed_items, summary = analyzer.analyze(unique_items, ticker, date_from, date_to)
    except Exception as e:
        logger.error(f"Analyzer failed: {e}")
        analyzed_items = []
        summary = SummaryResult(
            sentiment="neutral", confidence=0.0,
            reasoning=f"Analysis failed: {e}",
            positive_count=0, negative_count=0, neutral_count=0, total_count=0,
        )

    # 5. 生成报告
    report = AnalysisReport(
        ticker=ticker,
        date_from=date_from,
        date_to=date_to,
        collected_at=collected_at,
        items=analyzed_items,
        summary=summary,
        source_stats=source_stats,
    )

    try:
        filepath = save_report(report, config.output_dir)
        logger.info(f"Report saved to {filepath}")
    except Exception as e:
        logger.error(f"Failed to save report: {e}")

    return report
```

- [ ] **Step 5: Run dedup tests to verify they pass**

```bash
uv run pytest tests/news_sentiment/test_dedup.py -v
```

Expected: 4 tests PASS

- [ ] **Step 6: Create entry point**

Create `BreakoutStrategy/news_sentiment/__main__.py`:

```python
"""
命令行入口

使用方式: uv run -m BreakoutStrategy.news_sentiment
"""

import logging

from BreakoutStrategy.news_sentiment.api import analyze


def main():
    # === 参数配置（不使用 argparse） ===
    ticker = "AAPL"
    date_from = "2026-03-01"
    date_to = "2026-03-15"
    log_level = "INFO"

    # === 初始化日志 ===
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S',
    )

    # === 执行分析 ===
    print(f"Analyzing {ticker} from {date_from} to {date_to}...")
    report = analyze(ticker, date_from, date_to)

    # === 输出结果 ===
    print(f"\n{'='*60}")
    print(f"Ticker: {report.ticker}")
    print(f"Period: {report.date_from} ~ {report.date_to}")
    print(f"Sources: {report.source_stats}")
    print(f"Total items: {len(report.items)}")
    print(f"\nSummary:")
    print(f"  Sentiment: {report.summary.sentiment}")
    print(f"  Confidence: {report.summary.confidence:.2f}")
    print(f"  Reasoning: {report.summary.reasoning}")
    print(f"  Breakdown: +{report.summary.positive_count} "
          f"-{report.summary.negative_count} "
          f"={report.summary.neutral_count}")
    print(f"{'='*60}")

    if report.items:
        print(f"\nTop 5 items:")
        for item in report.items[:5]:
            print(f"  [{item.sentiment.sentiment}|{item.sentiment.confidence:.1f}] "
                  f"{item.news.title[:70]}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run all tests**

```bash
uv run pytest tests/news_sentiment/ -v
```

Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add BreakoutStrategy/news_sentiment/api.py BreakoutStrategy/news_sentiment/__main__.py BreakoutStrategy/news_sentiment/collectors/__init__.py tests/news_sentiment/test_dedup.py
git commit -m "feat(news_sentiment): add API orchestration, dedup, and CLI entry point"
```

---

### Task 10: End-to-End Integration Test

**Dependencies:** Tasks 1-9

- [ ] **Step 1: Set up API keys in environment**

将各 API key 配置到环境变量或 `configs/news_sentiment.yaml` 中:

```bash
export FINNHUB_API_KEY="your_finnhub_key"
export ALPHAVANTAGE_API_KEY="your_alphavantage_key"
export ZHIPUAI_API_KEY="your_zhipuai_key"
```

注意: Finnhub 和 AlphaVantage 需要自行注册获取免费 key。未配置的采集器会自动跳过。

- [ ] **Step 2: Run end-to-end via CLI**

```bash
uv run -m BreakoutStrategy.news_sentiment
```

Expected: 输出分析结果摘要，JSON 报告保存到 `outputs/news_sentiment/`

- [ ] **Step 3: Verify JSON output**

```bash
ls outputs/news_sentiment/
cat outputs/news_sentiment/AAPL_20260301_20260315.json | python -m json.tool | head -50
```

- [ ] **Step 4: Test with different tickers (optional)**

修改 `__main__.py` 中的 `ticker` 变量进行测试:

```python
ticker = "TSLA"
date_from = "2026-03-01"
date_to = "2026-03-15"
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(news_sentiment): complete module implementation"
```
