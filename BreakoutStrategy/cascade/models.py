"""
级联验证数据模型

所有模块间传递的数据结构，使用 dataclass 保证类型安全。
"""

from dataclasses import dataclass, field

from BreakoutStrategy.news_sentiment.models import AnalysisReport


@dataclass
class BreakoutSample:
    """被 top-K 模板命中的单个突破样本"""
    symbol: str
    date: str                    # YYYY-MM-DD
    label: float                 # 40天收益 label
    template_name: str           # 命中的模板名
    template_key: int            # bit-packed key


@dataclass
class CascadeResult:
    """单个突破样本的级联分析结果"""
    sample: BreakoutSample
    sentiment_score: float       # [-0.80, +0.80]
    sentiment: str               # positive/negative/neutral
    confidence: float            # [0, 1]
    category: str                # pass / reject / strong_reject / insufficient_data / error
    total_count: int             # 分析的新闻总数（0 表示无数据）
    analysis_report: AnalysisReport | None = None


@dataclass
class CascadeReport:
    """级联统计报告"""
    # 输入统计
    total_samples: int
    unique_tickers: int
    # 情感分析统计
    analyzed_count: int
    error_count: int
    # 筛选结果
    pass_count: int
    reject_count: int
    strong_reject_count: int
    insufficient_data_count: int
    positive_boost_count: int
    # 级联效果
    pre_filter_median: float
    post_filter_median: float
    cascade_lift: float
    # 详细结果
    results: list[CascadeResult] = field(default_factory=list)
