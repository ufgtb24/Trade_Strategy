"""
数据模型定义

所有模块间传递的数据结构，使用 dataclass 保证类型安全。
"""

from dataclasses import dataclass

IMPACT_MAP: dict[str, float] = {
    "negligible": 0.05,
    "low": 0.20,
    "medium": 0.50,
    "high": 0.80,
    "extreme": 1.00,
}


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
    """单条新闻的情感+影响力分析结果"""
    sentiment: str       # positive/negative/neutral
    impact: str          # negligible/low/medium/high/extreme, ""=分析失败
    impact_value: float  # IMPACT_MAP 映射值, 0.0=分析失败
    reasoning: str


@dataclass
class AnalyzedItem:
    """一条新闻 + 对应的情感分析结果"""
    news: NewsItem
    sentiment: SentimentResult


@dataclass
class SummaryResult:
    """情感聚合汇总（确定性公式计算）

    核心选股字段:
        rho: 极性分数 [-1, 1]，正/负面新闻的加权强度比
        sentiment_score: 有符号评分，= sign(rho) × confidence（连续映射，无死区截断）
    """
    sentiment: str
    confidence: float
    reasoning: str
    positive_count: int
    negative_count: int
    neutral_count: int
    total_count: int
    fail_count: int = 0
    rho: float = 0.0
    sentiment_score: float = 0.0


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
