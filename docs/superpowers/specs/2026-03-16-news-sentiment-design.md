# 股票新闻情感分析模块设计

## 概述

为突破策略系统新增 `news_sentiment` 模块，通过采集股票相关新闻、公告、财报信息，结合 GLM-4.7-Flash 进行情感分析，辅助投资决策。当前阶段作为独立模块，后续集成为因子参与突破评分。

## 需求

1. 给定股票代码和时间段，收集相关新闻、公告、财报
2. 测试多个免费数据源，评估信息质量，选择最佳路径
3. 使用 GLM-4.7-Flash 对收集到的信息进行逐条 + 综合情感分析
4. 结果保存为 JSON 文件

## 架构：采集器抽象 + 分析器分离

```
Collector(抽象) ──→ Analyzer ──→ Reporter
  ├─ FinnhubCollector        (GLM情感分析)   (JSON输出)
  ├─ AlphaVantageCollector
  └─ EdgarCollector
```

每个数据源实现统一的 `Collector` 接口，返回标准化的 `NewsItem`。`Analyzer` 负责调用 GLM 做逐条+汇总分析。`Reporter` 负责组装最终 JSON。

## 模块结构

```
BreakoutStrategy/news_sentiment/
├── __init__.py           # 模块概述，导出公共 API
├── __main__.py           # 入口: uv run -m BreakoutStrategy.news_sentiment
├── models.py             # 数据模型
├── collectors/
│   ├── __init__.py
│   ├── base.py           # Collector 抽象基类
│   ├── finnhub.py        # Finnhub 采集器
│   ├── alphavantage.py   # Alpha Vantage 采集器
│   └── edgar.py          # SEC EDGAR 采集器
├── analyzer.py           # GLM-4.7-Flash 情感分析器
├── reporter.py           # JSON 报告生成
└── api.py                # 公共入口 analyze()
```

- 配置文件：`configs/news_sentiment.yaml`（tracked in git，不含敏感信息）
- 输出目录：`outputs/news_sentiment/`
- 入口：`__main__.py` 中 `main()` 函数顶部声明参数变量（不使用 argparse）

## 日期格式约定

- 所有日期参数（`date_from`, `date_to`）使用 `YYYY-MM-DD` 格式（仅日期，无时间）
- `NewsItem.published_at` 使用完整 ISO 8601 datetime（如 `2026-03-15T14:30:00Z`），保留源 API 返回的精度

## 数据模型（models.py）

### NewsItem

```python
@dataclass
class NewsItem:
    """标准化的新闻条目，所有 Collector 输出统一为此格式"""
    title: str                    # 标题
    summary: str                  # 摘要/正文片段
    source: str                   # 来源（Reuters, SEC, etc.）
    published_at: str             # 发布时间，完整 ISO 8601 datetime
    url: str                      # 原文链接
    ticker: str                   # 关联股票
    category: str                 # 类型: "news" | "earnings" | "filing"
    collector: str                # 采集源: "finnhub" | "alphavantage" | "edgar"
    raw_sentiment: float | None   # 数据源自带的情感分(如有)
```

### SentimentResult

```python
@dataclass
class SentimentResult:
    """单条新闻的 GLM 情感分析结果"""
    sentiment: str                # "positive" | "negative" | "neutral"
    confidence: float             # 0.0-1.0
    reasoning: str                # 简要分析理由
```

### AnalyzedItem

```python
@dataclass
class AnalyzedItem:
    """一条新闻 + 对应的情感分析结果"""
    news: NewsItem
    sentiment: SentimentResult
```

### SummaryResult

```python
@dataclass
class SummaryResult:
    """GLM 综合情感汇总"""
    sentiment: str                # "positive" | "negative" | "neutral"
    confidence: float             # 0.0-1.0
    reasoning: str                # 综合分析理由
    positive_count: int
    negative_count: int
    neutral_count: int
    total_count: int
```

### AnalysisReport

```python
@dataclass
class AnalysisReport:
    """最终输出的完整分析报告"""
    ticker: str
    date_from: str                        # YYYY-MM-DD
    date_to: str                          # YYYY-MM-DD
    collected_at: str                     # 分析执行时间 ISO 8601
    items: list[AnalyzedItem]             # 逐条分析结果
    summary: SummaryResult                # 综合汇总
    source_stats: dict[str, int]          # 各源采集数量，如 {"finnhub": 12, "edgar": 3}
```

JSON 序列化由 `Reporter` 通过 `dataclasses.asdict()` 完成。

## Collector 抽象与实现

### 基类

```python
from abc import ABC, abstractmethod

class BaseCollector(ABC):
    """采集器基类"""
    name: str                              # "finnhub" | "alphavantage" | "edgar"

    @abstractmethod
    def collect(self, ticker: str, date_from: str, date_to: str) -> list[NewsItem]: ...

    @abstractmethod
    def is_available(self) -> bool: ...
```

### `is_available()` 语义

- 返回 `True` 当 API key 非空（EDGAR 无需 key，始终可用）
- 不做预检查额度。额度耗尽通过 `collect()` 中的响应检测处理：收到 429 或特殊响应体时 log 警告，返回已收集的部分结果

### 采集器对比

| 采集器 | API Key | 返回内容 | 自带情感 | 特殊处理 |
|---|---|---|---|---|
| **Finnhub** | 需要 | 新闻 + 财报日历 + SEC filings | 有（`/news-sentiment`） | 新闻和情感需两次调用 |
| **AlphaVantage** | 需要 | 情感增强的新闻 | 有（per-article score） | 25次/天，超额返回200+特殊JSON |
| **EDGAR** | 不需要 | 8-K/10-K/10-Q 公告元数据 | 无 | 需 ticker→CIK 映射，User-Agent header |

### Category 映射

| Collector | Endpoint | Maps to category |
|---|---|---|
| Finnhub | `/company-news` | `"news"` |
| Finnhub | `/calendar/earnings` | `"earnings"` |
| AlphaVantage | `NEWS_SENTIMENT` | `"news"` |
| EDGAR | `submissions` (8-K) | `"filing"` |

### Alpha Vantage 额度检测

Alpha Vantage 在额度耗尽时返回 HTTP 200，响应体包含 `{"Note": "...daily limit..."}` 或 `{"Information": "..."}` 键。Collector 必须检查这些键，发现后视为额度耗尽，log 警告并返回已收集结果。

### 去重策略

去重 key = `url`（非空时），否则 `(title, published_at[:10])`。出现重复时保留 `raw_sentiment` 非空的条目（信息更丰富）。

### 采集策略

`api.py` 中按顺序调用所有可用的采集器，合并去重。任一采集器超额或异常时 log 警告并跳过，不影响其他源。

## 情感分析器（analyzer.py）

### 两阶段分析流程

```
Stage 1: 逐条分析
  将 NewsItem 按 batch_size 分批，每批一次 GLM 调用
  → 返回 list[SentimentResult]

Stage 2: 综合汇总
  2a. Analyzer 本地统计 Stage 1 结果，计算 positive/negative/neutral_count 和 total_count
  2b. 将统计数据 + 关键新闻摘要组装为 prompt，调用 GLM
  2c. GLM 返回 {"sentiment", "confidence", "reasoning"} 三个字段
  2d. Analyzer 将 GLM 返回的三字段 + 本地统计的四个 count 字段合并构造 SummaryResult
```

### 关键设计

- **SDK**: 使用 `zhipuai` 包，`client.chat.completions.create(model="glm-4.7-flash")`
- **temperature**: 0.1（分类任务需要确定性输出）
- **批量优化**: 按 `batch_size` 分批（默认5），最后一批可能不足 batch_size。每批一次 GLM 调用
- **输出格式**: prompt 约束为 JSON，代码端 `json.loads()` 解析，失败时 retry 一次
- **限流**: 请求间 sleep `request_interval` 秒（默认1s），适配免费 tier
- **API Key**: 优先从环境变量 `ZHIPUAI_API_KEY` 读取，回退到配置文件

### 错误处理

- GLM API 网络错误/超时：retry 一次，仍失败则该批次所有条目设为 `SentimentResult(sentiment="neutral", confidence=0.0, reasoning="Analysis failed")`
- API key 无效/额度耗尽：log 错误，所有未分析条目设为默认 neutral
- JSON 解析失败：retry 一次（重新调用 GLM），仍失败则该批次设为默认 neutral
- `analyze()` 函数永不抛异常，始终返回 `AnalysisReport` 对象

### 零条新闻处理

如果所有 Collector 返回空结果，跳过 GLM 分析。返回 `AnalysisReport` with `items=[]`，`summary` 设为 `SummaryResult(sentiment="neutral", confidence=0.0, reasoning="No news found in the specified period", ...counts=0)`。

### Prompt 模板

**逐条分析（批量版）：**

```
System: 你是一个金融新闻情感分析专家。分析以下每条新闻对该股票的影响。
仅返回JSON数组：[{"index": 0, "sentiment": "positive|negative|neutral",
"confidence": 0.0-1.0, "reasoning": "一句话理由"}, ...]

User: 股票: {ticker}
0. {title}: {summary}
1. {title}: {summary}
...
```

注：prompt 和 JSON 响应均使用 0-based 索引，与 Python list 一致。

**综合汇总：**

```
System: 你是一个金融分析师。根据以下新闻情感分析结果，给出对该股票的综合情感判断。
返回JSON：{"sentiment": "...", "confidence": ..., "reasoning": "综合分析"}

User: 股票: {ticker}，时间段: {date_from} ~ {date_to}
共{n}条新闻，正面{pos}条，负面{neg}条，中性{neu}条。
关键新闻摘要：...
```

## 公共 API（api.py）

```python
def analyze(ticker: str, date_from: str, date_to: str) -> AnalysisReport:
    """
    收集指定股票在时间段内的新闻/公告/财报，执行情感分析。
    结果同时保存为 JSON 文件并返回 AnalysisReport。
    """
```

调用链：

```
analyze("AAPL", "2026-03-01", "2026-03-15")
  → 加载配置
  → 依次调用各 Collector.collect()，合并去重
  → Analyzer 逐条分析 + 综合汇总
  → Reporter 生成 JSON 保存到 outputs/news_sentiment/AAPL_20260301_20260315.json
  → 返回 AnalysisReport
```

## 配置（configs/news_sentiment.yaml）

```yaml
collectors:
  finnhub:
    api_key: ""              # 留空则跳过，优先读环境变量 FINNHUB_API_KEY
    timeout: 10
  alphavantage:
    api_key: ""              # 留空则跳过，优先读环境变量 ALPHAVANTAGE_API_KEY
    timeout: 10
  edgar:
    user_agent: "YourName your@email.com"  # SEC 要求

analyzer:
  api_key: ""                # 优先读环境变量 ZHIPUAI_API_KEY
  model: "glm-4.7-flash"
  temperature: 0.1
  batch_size: 5              # 每次批量分析的新闻条数
  request_interval: 1.0      # 请求间隔(秒)

output:
  output_dir: "outputs/news_sentiment"
```

配置文件 tracked in git，仅含非敏感默认值。API key 通过环境变量注入，YAML 中的值作为 fallback。

## 依赖

新增 Python 包：
- `zhipuai` — GLM-4.7-Flash SDK
- `finnhub-python` — Finnhub API client
- `requests` — HTTP 请求（Alpha Vantage, SEC EDGAR）

## 后续扩展

- 将情感分析结果量化为 factor，注册到 `FACTOR_REGISTRY`。`AnalysisReport` 可通过 `SummaryResult` 映射为数值（如 positive=1.0, neutral=0.0, negative=-1.0，加权 confidence）
- 在观察池买入判断时作为额外维度参与评估
- 支持批量股票分析
