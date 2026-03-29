"""缓存模块单元测试"""

from unittest.mock import patch, MagicMock

from BreakoutStrategy.news_sentiment.cache import (
    SentimentCache, news_fingerprint, compute_uncovered_ranges,
)
from BreakoutStrategy.news_sentiment.analyzer import SentimentAnalyzer
from BreakoutStrategy.news_sentiment.config import AnalyzerConfig, CacheConfig
from BreakoutStrategy.news_sentiment.models import NewsItem, SentimentResult


def _item(title="News", url="https://example.com/1",
          published_at="2026-03-10T10:00:00Z") -> NewsItem:
    return NewsItem(
        title=title, summary="Summary", source="Test",
        published_at=published_at, url=url, ticker="AAPL",
        category="news", collector="finnhub",
    )


def _cache_config(tmpdir: str) -> CacheConfig:
    return CacheConfig(enable=True, cache_dir=tmpdir, news_ttl_days=30, sentiment_ttl_days=0)


# --- news_fingerprint ---

def test_fingerprint_url_based():
    """有 url 时用 url 生成指纹"""
    a = _item(url="https://example.com/article-1")
    b = _item(url="https://example.com/article-1")
    c = _item(url="https://example.com/article-2")
    assert news_fingerprint(a) == news_fingerprint(b)
    assert news_fingerprint(a) != news_fingerprint(c)


def test_fingerprint_fallback_no_url():
    """无 url 时用 title+date+source 生成指纹"""
    a = _item(title="Test News", url="", published_at="2026-03-10T10:00:00Z")
    b = _item(title="Test News", url="", published_at="2026-03-10T10:00:00Z")
    c = _item(title="Other News", url="", published_at="2026-03-10T10:00:00Z")
    assert news_fingerprint(a) == news_fingerprint(b)
    assert news_fingerprint(a) != news_fingerprint(c)


# --- compute_uncovered_ranges ---

def test_uncovered_ranges_no_coverage():
    result = compute_uncovered_ranges(("2026-03-05", "2026-03-18"), [])
    assert result == [("2026-03-05", "2026-03-18")]


def test_uncovered_ranges_full_coverage():
    result = compute_uncovered_ranges(
        ("2026-03-05", "2026-03-18"),
        [("2026-03-01", "2026-03-20")],
    )
    assert result == []


def test_uncovered_ranges_partial_right():
    result = compute_uncovered_ranges(
        ("2026-03-05", "2026-03-18"),
        [("2026-03-01", "2026-03-14")],
    )
    assert result == [("2026-03-15", "2026-03-18")]


def test_uncovered_ranges_partial_left():
    result = compute_uncovered_ranges(
        ("2026-03-05", "2026-03-18"),
        [("2026-03-10", "2026-03-20")],
    )
    assert result == [("2026-03-05", "2026-03-09")]


def test_uncovered_ranges_gap_in_middle():
    result = compute_uncovered_ranges(
        ("2026-03-01", "2026-03-20"),
        [("2026-03-01", "2026-03-05"), ("2026-03-10", "2026-03-20")],
    )
    assert result == [("2026-03-06", "2026-03-09")]


# --- SentimentCache CRUD ---

def test_cache_news_put_and_get(tmp_path):
    cache = SentimentCache(_cache_config(str(tmp_path)))
    items = [
        _item("News A", published_at="2026-03-10T10:00:00Z"),
        _item("News B", url="https://example.com/b", published_at="2026-03-12T10:00:00Z"),
    ]
    cache.put_news("AAPL", "finnhub", items)
    result = cache.get_news("AAPL", "2026-03-10", "2026-03-12", "finnhub")
    assert len(result) == 2


def test_cache_news_date_range_filter(tmp_path):
    cache = SentimentCache(_cache_config(str(tmp_path)))
    items = [
        _item("News A", url="https://a.com/1", published_at="2026-03-05T10:00:00Z"),
        _item("News B", url="https://b.com/1", published_at="2026-03-10T10:00:00Z"),
        _item("News C", url="https://c.com/1", published_at="2026-03-15T10:00:00Z"),
    ]
    cache.put_news("AAPL", "finnhub", items)
    result = cache.get_news("AAPL", "2026-03-08", "2026-03-12", "finnhub")
    assert len(result) == 1
    assert result[0].title == "News B"


def test_cache_sentiment_put_and_get(tmp_path):
    cache = SentimentCache(_cache_config(str(tmp_path)))
    fp = "abc123"
    sent = SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good")
    cache.put_sentiment(fp, "deepseek", "deepseek-chat", sent)
    result = cache.get_sentiment(fp, "deepseek", "deepseek-chat")
    assert result is not None
    assert result.sentiment == "positive"
    assert result.impact_value == 0.80


def test_cache_sentiment_miss_different_model(tmp_path):
    cache = SentimentCache(_cache_config(str(tmp_path)))
    fp = "abc123"
    sent = SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good")
    cache.put_sentiment(fp, "deepseek", "deepseek-chat", sent)
    result = cache.get_sentiment(fp, "glm", "glm-4.7-flash")
    assert result is None


def test_cache_coverage_tracking(tmp_path):
    cache = SentimentCache(_cache_config(str(tmp_path)))
    cache.update_coverage("AAPL", "finnhub", "2026-03-01", "2026-03-14")
    ranges = cache.get_covered_ranges("AAPL", "finnhub")
    assert ("2026-03-01", "2026-03-14") in ranges


def test_cache_disabled_is_noop(tmp_path):
    cfg = CacheConfig(enable=False, cache_dir=str(tmp_path), news_ttl_days=30, sentiment_ttl_days=0)
    cache = SentimentCache(cfg)
    cache.put_news("AAPL", "finnhub", [_item()])
    assert cache.get_news("AAPL", "2026-03-01", "2026-03-15", "finnhub") == []
    assert cache.get_sentiment("fp", "ds", "m") is None


# --- Integration tests: analyzer + cache ---

def _make_analyzer_config():
    return AnalyzerConfig(
        api_key="test", backend="deepseek", model="test-model",
        temperature=0.1, max_concurrency=5, proxy="",
    )


@patch("BreakoutStrategy.news_sentiment.analyzer._get_backend_registry")
def test_analyzer_cache_hit_skips_backend(mock_registry, tmp_path):
    """缓存命中时不调用 backend.analyze_all"""
    mock_backend = MagicMock()
    mock_backend_cls = MagicMock(return_value=mock_backend)
    mock_registry.return_value = {"deepseek": mock_backend_cls}

    cache = SentimentCache(_cache_config(str(tmp_path)))
    item = _item("Test news", url="https://example.com/cached")
    fp = news_fingerprint(item)
    sent = SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good")
    cache.put_sentiment(fp, "deepseek", "test-model", sent)

    analyzer = SentimentAnalyzer(_make_analyzer_config(), cache=cache)
    analyzed, summary = analyzer.analyze([item], "AAPL", "2026-03-01", "2026-03-15")

    mock_backend.analyze_all.assert_not_called()
    assert analyzed[0].sentiment.sentiment == "positive"


@patch("BreakoutStrategy.news_sentiment.analyzer._get_backend_registry")
def test_analyzer_cache_miss_calls_backend_and_caches(mock_registry, tmp_path):
    """缓存未命中时调用 backend 并写入缓存"""
    mock_backend = MagicMock()
    sent = SentimentResult(sentiment="negative", impact="medium", impact_value=0.50, reasoning="Bad")
    mock_backend.analyze_all.return_value = [sent]
    mock_backend_cls = MagicMock(return_value=mock_backend)
    mock_registry.return_value = {"deepseek": mock_backend_cls}

    cache = SentimentCache(_cache_config(str(tmp_path)))
    item = _item("Uncached news", url="https://example.com/new")

    analyzer = SentimentAnalyzer(_make_analyzer_config(), cache=cache)
    analyzed, summary = analyzer.analyze([item], "AAPL", "2026-03-01", "2026-03-15")

    mock_backend.analyze_all.assert_called_once()
    fp = news_fingerprint(item)
    cached = cache.get_sentiment(fp, "deepseek", "test-model")
    assert cached is not None
    assert cached.sentiment == "negative"
