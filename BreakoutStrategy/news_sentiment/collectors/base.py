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
