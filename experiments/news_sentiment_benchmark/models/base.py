"""
Benchmark 模型统一接口

所有被测模型实现 BaseSentimentModel，返回 ItemResult 列表。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ItemResult:
    """单条分析结果"""
    sentiment: str       # "positive" | "negative" | "neutral"
    confidence: float    # 0.0-1.0
    reasoning: str
    failed: bool = False


@dataclass
class BenchmarkResult:
    """模型整体评测结果"""
    model_name: str
    items: list[ItemResult] = field(default_factory=list)
    total_time: float = 0.0
    fail_count: int = 0


class BaseSentimentModel(ABC):
    """情感分析模型基类"""
    name: str = "base"

    @abstractmethod
    def analyze_batch(self, texts: list[str], ticker: str) -> list[ItemResult]:
        """分析一批文本，返回逐条结果"""
