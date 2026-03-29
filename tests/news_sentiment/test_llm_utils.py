"""测试 LLM 共享工具函数"""

from BreakoutStrategy.news_sentiment.backends._llm_utils import (
    SYSTEM_PROMPT,
    DEFAULT_SENTIMENT,
    build_user_message,
    parse_single_response,
)
from BreakoutStrategy.news_sentiment.models import NewsItem


def test_build_user_message_with_summary():
    item = NewsItem(
        title="Apple Delays Smart Home",
        summary="Product pushed back to 2027",
        source="Yahoo", published_at="2026-03-15T00:00:00Z",
        url="", ticker="AAPL", category="news", collector="finnhub",
    )
    msg = build_user_message(item, "AAPL")
    assert "股票: AAPL" in msg
    assert "Apple Delays Smart Home: Product pushed back to 2027" in msg


def test_build_user_message_without_summary():
    item = NewsItem(
        title="Apple Delays Smart Home", summary="",
        source="Yahoo", published_at="", url="",
        ticker="AAPL", category="news", collector="finnhub",
    )
    msg = build_user_message(item, "AAPL")
    assert msg == "股票: AAPL\nApple Delays Smart Home"


def test_parse_single_response_valid_json():
    content = '{"sentiment": "positive", "impact": "high", "reasoning": "Good news"}'
    result = parse_single_response(content)
    assert result.sentiment == "positive"
    assert result.impact == "high"
    assert result.impact_value == 0.80
    assert result.reasoning == "Good news"


def test_parse_single_response_markdown_wrapped():
    content = '```json\n{"sentiment": "negative", "impact": "medium", "reasoning": "Bad"}\n```'
    result = parse_single_response(content)
    assert result.sentiment == "negative"
    assert result.impact == "medium"
    assert result.impact_value == 0.50


def test_parse_single_response_invalid_returns_default():
    result = parse_single_response("this is not json at all")
    assert result.sentiment == "neutral"
    assert result.impact_value == 0.0
    assert result.reasoning == "Analysis failed"


def test_parse_single_response_embedded_json():
    content = 'Here is the analysis: {"sentiment": "neutral", "impact": "medium", "reasoning": "Mixed"} done.'
    result = parse_single_response(content)
    assert result.sentiment == "neutral"
    assert result.impact == "medium"
    assert result.impact_value == 0.50


def test_default_sentiment():
    assert DEFAULT_SENTIMENT.sentiment == "neutral"
    assert DEFAULT_SENTIMENT.impact_value == 0.0


def test_system_prompt_contains_json_format():
    assert "sentiment" in SYSTEM_PROMPT
    assert "impact" in SYSTEM_PROMPT
    assert "confidence" not in SYSTEM_PROMPT
    assert "reasoning" in SYSTEM_PROMPT
