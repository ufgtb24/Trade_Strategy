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
        sentiment="positive", impact="high", impact_value=0.80, reasoning="Good earnings",
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
