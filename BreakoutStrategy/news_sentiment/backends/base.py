"""分析器后端抽象接口"""

from abc import ABC, abstractmethod

from BreakoutStrategy.news_sentiment.config import AnalyzerConfig
from BreakoutStrategy.news_sentiment.models import NewsItem, SentimentResult


class BaseAnalyzerBackend(ABC):
    """分析器后端基类，所有 backend 实现此接口"""

    def __init__(self, config: AnalyzerConfig):
        self._config = config

    @abstractmethod
    def analyze_all(self, items: list[NewsItem], ticker: str) -> list[SentimentResult]:
        """处理所有新闻，返回逐条 SentimentResult。内部自行决定并发/批处理策略。"""
