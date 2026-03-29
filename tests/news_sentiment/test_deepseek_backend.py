"""测试 DeepSeek Backend（mock API 调用）"""

from unittest.mock import patch, MagicMock
from BreakoutStrategy.news_sentiment.backends.deepseek_backend import DeepSeekBackend
from BreakoutStrategy.news_sentiment.config import AnalyzerConfig
from BreakoutStrategy.news_sentiment.models import NewsItem


def _make_config():
    return AnalyzerConfig(
        api_key="test-key", backend="deepseek", model="deepseek-chat",
        temperature=0.1, max_concurrency=5, proxy="",
    )

def _make_item(title="Apple rises", summary="Good earnings"):
    return NewsItem(
        title=title, summary=summary, source="Yahoo",
        published_at="2026-03-15T00:00:00Z", url="",
        ticker="AAPL", category="news", collector="finnhub",
    )


def _mock_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@patch("BreakoutStrategy.news_sentiment.backends.deepseek_backend.OpenAI")
def test_analyze_all_single_item(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _mock_response(
        '{"sentiment": "positive", "impact": "high", "reasoning": "Strong earnings"}'
    )
    backend = DeepSeekBackend(_make_config())
    results = backend.analyze_all([_make_item()], "AAPL")
    assert len(results) == 1
    assert results[0].sentiment == "positive"
    assert results[0].impact == "high"
    assert results[0].impact_value == 0.80


@patch("BreakoutStrategy.news_sentiment.backends.deepseek_backend.OpenAI")
def test_analyze_all_concurrent(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _mock_response(
        '{"sentiment": "neutral", "impact": "medium", "reasoning": "Mixed"}'
    )
    backend = DeepSeekBackend(_make_config())
    items = [_make_item(f"News {i}") for i in range(5)]
    results = backend.analyze_all(items, "AAPL")
    assert len(results) == 5
    assert all(r.sentiment == "neutral" for r in results)


@patch("BreakoutStrategy.news_sentiment.backends.deepseek_backend.OpenAI")
def test_analyze_all_api_failure_returns_default(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.side_effect = Exception("API error")
    backend = DeepSeekBackend(_make_config())
    results = backend.analyze_all([_make_item()], "AAPL")
    assert len(results) == 1
    assert results[0].sentiment == "neutral"
    assert results[0].impact_value == 0.0
