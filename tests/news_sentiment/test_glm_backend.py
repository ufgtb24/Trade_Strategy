"""测试 GLM Backend（mock API 调用）"""

from unittest.mock import patch, MagicMock
from BreakoutStrategy.news_sentiment.backends.glm_backend import GLMBackend
from BreakoutStrategy.news_sentiment.config import AnalyzerConfig
from BreakoutStrategy.news_sentiment.models import NewsItem


def _make_config():
    return AnalyzerConfig(
        api_key="test-key", backend="glm", model="glm-4.7-flash",
        temperature=0.1, max_concurrency=5, proxy="",
    )

def _make_item(title="Apple rises", summary="Good earnings"):
    return NewsItem(
        title=title, summary=summary, source="Yahoo",
        published_at="2026-03-15T00:00:00Z", url="",
        ticker="AAPL", category="news", collector="finnhub",
    )


@patch("BreakoutStrategy.news_sentiment.backends.glm_backend.ZhipuAI")
def test_analyze_all_basic(mock_zhipu_cls):
    client = MagicMock()
    mock_zhipu_cls.return_value = client
    msg = MagicMock()
    msg.content = '{"sentiment": "negative", "impact": "high", "reasoning": "Delays"}'
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    client.chat.completions.create.return_value = resp

    backend = GLMBackend(_make_config())
    results = backend.analyze_all([_make_item()], "AAPL")
    assert len(results) == 1
    assert results[0].sentiment == "negative"


@patch("BreakoutStrategy.news_sentiment.backends.glm_backend.ZhipuAI")
def test_thinking_mode_extracts_from_reasoning_content(mock_zhipu_cls):
    """GLM 思考模式下 content 为空，结果在 reasoning_content 中"""
    client = MagicMock()
    mock_zhipu_cls.return_value = client
    msg = MagicMock()
    msg.content = ''
    msg.reasoning_content = '分析过程...\n```json\n{"sentiment": "positive", "impact": "medium", "reasoning": "Good"}\n```'
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    client.chat.completions.create.return_value = resp

    backend = GLMBackend(_make_config())
    results = backend.analyze_all([_make_item()], "AAPL")
    assert results[0].sentiment == "positive"


@patch("BreakoutStrategy.news_sentiment.backends.glm_backend.ZhipuAI")
def test_api_failure_returns_default(mock_zhipu_cls):
    client = MagicMock()
    mock_zhipu_cls.return_value = client
    client.chat.completions.create.side_effect = Exception("API error")
    backend = GLMBackend(_make_config())
    results = backend.analyze_all([_make_item()], "AAPL")
    assert len(results) == 1
    assert results[0].sentiment == "neutral"
    assert results[0].impact_value == 0.0
