"""测试重构后的 SentimentAnalyzer 编排器"""

from unittest.mock import patch, MagicMock
from BreakoutStrategy.news_sentiment.analyzer import SentimentAnalyzer
from BreakoutStrategy.news_sentiment.config import AnalyzerConfig
from BreakoutStrategy.news_sentiment.models import NewsItem, SentimentResult


def _make_config(backend="deepseek"):
    return AnalyzerConfig(
        api_key="test", backend=backend, model="test-model",
        temperature=0.1, max_concurrency=5, proxy="",
    )

def _make_items(n=3):
    return [
        NewsItem(title=f"News {i}", summary=f"Summary {i}", source="Yahoo",
                 published_at="", url="", ticker="AAPL", category="news", collector="finnhub")
        for i in range(n)
    ]


@patch("BreakoutStrategy.news_sentiment.analyzer._get_backend_registry")
def test_backend_dispatch_deepseek(mock_registry):
    mock_backend_cls = MagicMock()
    mock_backend = MagicMock()
    mock_backend.analyze_all.return_value = [
        SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good")
    ]
    mock_backend_cls.return_value = mock_backend
    mock_registry.return_value = {"deepseek": mock_backend_cls}

    analyzer = SentimentAnalyzer(_make_config("deepseek"))
    items, summary = analyzer.analyze(_make_items(1), "AAPL", "2026-01-01", "2026-03-01")
    assert len(items) == 1
    assert items[0].sentiment.sentiment == "positive"
    mock_backend.analyze_all.assert_called_once()


@patch("BreakoutStrategy.news_sentiment.analyzer._get_backend_registry")
def test_unknown_backend_raises(mock_registry):
    mock_registry.return_value = {"deepseek": MagicMock()}
    import pytest
    with pytest.raises(ValueError, match="Unknown backend"):
        SentimentAnalyzer(_make_config("nonexistent"))


@patch("BreakoutStrategy.news_sentiment.analyzer._get_backend_registry")
def test_empty_items_returns_empty(mock_registry):
    mock_registry.return_value = {"deepseek": MagicMock()}
    analyzer = SentimentAnalyzer(_make_config("deepseek"))
    items, summary = analyzer.analyze([], "AAPL", "2026-01-01", "2026-03-01")
    assert items == []
    assert summary.sentiment == "neutral"
    assert summary.total_count == 0
