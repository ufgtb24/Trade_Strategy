"""时间衰减单元测试"""

import math
from BreakoutStrategy.news_sentiment.filter import _compute_time_weights, diversity_sample
from BreakoutStrategy.news_sentiment.embedding import embed_texts
from BreakoutStrategy.news_sentiment.models import NewsItem


def _item(title: str, published_at: str) -> NewsItem:
    return NewsItem(
        title=title, summary="", source="Test",
        published_at=published_at, url="", ticker="AAPL",
        category="news", collector="finnhub",
    )


# --- _compute_time_weights ---

def test_time_weights_same_day():
    """参考日期当天 -> 权重 1.0"""
    items = [_item("News", "2026-03-15T10:00:00Z")]
    weights = _compute_time_weights(items, "2026-03-15", 3.0)
    assert weights[0] == 1.0


def test_time_weights_one_half_life():
    """半衰期天数后 -> 权重 0.5"""
    items = [_item("News", "2026-03-12T10:00:00Z")]
    weights = _compute_time_weights(items, "2026-03-15", 3.0)
    assert abs(weights[0] - 0.5) < 0.01


def test_time_weights_two_half_lives():
    """两个半衰期后 -> 权重 0.25"""
    items = [_item("News", "2026-03-09T10:00:00Z")]
    weights = _compute_time_weights(items, "2026-03-15", 3.0)
    assert abs(weights[0] - 0.25) < 0.01


def test_time_weights_no_date_gets_full_weight():
    """无发布日期 -> 保守给满权重 1.0"""
    items = [_item("News", "")]
    weights = _compute_time_weights(items, "2026-03-15", 3.0)
    assert weights[0] == 1.0


def test_time_weights_future_date_gets_full_weight():
    """未来日期 -> 权重 1.0"""
    items = [_item("News", "2026-03-20T10:00:00Z")]
    weights = _compute_time_weights(items, "2026-03-15", 3.0)
    assert weights[0] == 1.0


# --- diversity_sample with time weights ---

def test_diversity_sample_time_weighted_prefers_recent():
    """时间加权时，近期新闻在多样性相近时优先入选"""
    items = [
        _item("Apple launches new product line", "2026-03-01T10:00:00Z"),
        _item("Apple releases new product update", "2026-03-02T10:00:00Z"),
        _item("Apple announces product changes", "2026-03-05T10:00:00Z"),
        _item("Apple reveals new features today", "2026-03-13T10:00:00Z"),
        _item("Apple unveils latest innovation", "2026-03-14T10:00:00Z"),
        _item("Apple presents new technology", "2026-03-15T10:00:00Z"),
    ]
    embeddings = embed_texts([i.title for i in items])
    time_weights = _compute_time_weights(items, "2026-03-15", 3.0)

    result = diversity_sample(items, embeddings, max_items=3,
                              time_weights=time_weights, alpha=0.25)
    dates = [r.published_at[:10] for r in result]
    recent_count = sum(1 for d in dates if d >= "2026-03-13")
    assert recent_count >= 2


def test_diversity_sample_no_time_weights_unchanged():
    """time_weights=None 时行为与原始 FPS 完全一致"""
    items = [_item(f"Topic {i} news", "2026-03-10T10:00:00Z") for i in range(20)]
    embeddings = embed_texts([i.title for i in items])
    result_original = diversity_sample(items, embeddings, max_items=5)
    result_none = diversity_sample(items, embeddings, max_items=5, time_weights=None)
    assert [r.title for r in result_original] == [r.title for r in result_none]


# --- analyzer.py time-weighted summarize ---

from unittest.mock import patch, MagicMock
from BreakoutStrategy.news_sentiment.analyzer import SentimentAnalyzer
from BreakoutStrategy.news_sentiment.config import AnalyzerConfig, TimeDecayConfig
from BreakoutStrategy.news_sentiment.models import SentimentResult


def _make_analyzer_config():
    return AnalyzerConfig(
        api_key="test", backend="deepseek", model="test-model",
        temperature=0.1, max_concurrency=5, proxy="",
    )


@patch("BreakoutStrategy.news_sentiment.analyzer._get_backend_registry")
def test_summarize_time_decay_recent_positive_dominates(mock_registry):
    """近期正面 + 远期负面 → 时间衰减后应偏正面"""
    mock_backend = MagicMock()
    sentiments = (
        [SentimentResult(sentiment="negative", impact="high", impact_value=0.80, reasoning="Bad")] * 5
        + [SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good")] * 3
    )
    mock_backend.analyze_all.return_value = sentiments
    mock_backend_cls = MagicMock(return_value=mock_backend)
    mock_registry.return_value = {"deepseek": mock_backend_cls}

    items = (
        [_item(f"Bad news {i}", "2026-03-01T10:00:00Z") for i in range(5)]
        + [_item(f"Good news {i}", "2026-03-14T10:00:00Z") for i in range(3)]
    )

    td = TimeDecayConfig(enable=True, half_life=3.0)
    analyzer = SentimentAnalyzer(_make_analyzer_config())
    _, summary = analyzer.analyze(items, "AAPL", "2026-03-01", "2026-03-15", time_decay=td)
    assert summary.sentiment == "positive"
    assert summary.rho > 0
    assert summary.sentiment_score > 0


@patch("BreakoutStrategy.news_sentiment.analyzer._get_backend_registry")
def test_summarize_no_time_decay_negative_dominates(mock_registry):
    """同样的数据，无时间衰减 → 负面数量多应偏负面"""
    mock_backend = MagicMock()
    sentiments = (
        [SentimentResult(sentiment="negative", impact="high", impact_value=0.80, reasoning="Bad")] * 5
        + [SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good")] * 3
    )
    mock_backend.analyze_all.return_value = sentiments
    mock_backend_cls = MagicMock(return_value=mock_backend)
    mock_registry.return_value = {"deepseek": mock_backend_cls}

    items = (
        [_item(f"Bad news {i}", "2026-03-01T10:00:00Z") for i in range(5)]
        + [_item(f"Good news {i}", "2026-03-14T10:00:00Z") for i in range(3)]
    )

    analyzer = SentimentAnalyzer(_make_analyzer_config())
    _, summary = analyzer.analyze(items, "AAPL", "2026-03-01", "2026-03-15")
    assert summary.sentiment == "negative"
    assert summary.rho < 0
    assert summary.sentiment_score < 0


# --- evidence 归一化 + scarcity 保护 ---


@patch("BreakoutStrategy.news_sentiment.analyzer._get_backend_registry")
def test_evidence_normalization_removes_quantity_bias(mock_registry):
    """同比例正负面，热门股(15条) vs 冷门股(5条)的 confidence 偏差应 < 10%"""
    mock_backend = MagicMock()
    mock_backend_cls = MagicMock(return_value=mock_backend)
    mock_registry.return_value = {"deepseek": mock_backend_cls}

    # 热门股：10 正面 + 3 负面 + 2 中性 = 15 条
    hot_sentiments = (
        [SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good")] * 10
        + [SentimentResult(sentiment="negative", impact="medium", impact_value=0.50, reasoning="Bad")] * 3
        + [SentimentResult(sentiment="neutral", impact="medium", impact_value=0.50, reasoning="Meh")] * 2
    )
    hot_items = [_item(f"Hot news {i}", "2026-03-10T10:00:00Z") for i in range(15)]

    # 冷门股：3 正面 + 1 负面 + 1 中性 = 5 条（近似相同比例）
    cold_sentiments = (
        [SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good")] * 3
        + [SentimentResult(sentiment="negative", impact="medium", impact_value=0.50, reasoning="Bad")] * 1
        + [SentimentResult(sentiment="neutral", impact="medium", impact_value=0.50, reasoning="Meh")] * 1
    )
    cold_items = [_item(f"Cold news {i}", "2026-03-10T10:00:00Z") for i in range(5)]

    analyzer = SentimentAnalyzer(_make_analyzer_config())

    # 热门股
    mock_backend.analyze_all.return_value = hot_sentiments
    _, hot_summary = analyzer.analyze(hot_items, "NVDA", "2026-03-01", "2026-03-15")

    # 冷门股
    mock_backend.analyze_all.return_value = cold_sentiments
    _, cold_summary = analyzer.analyze(cold_items, "XYZ", "2026-03-01", "2026-03-15")

    assert hot_summary.sentiment == "positive"
    assert cold_summary.sentiment == "positive"
    # 偏差 < 10%（归一化前为 27%~81%）
    bias = abs(hot_summary.confidence - cold_summary.confidence) / cold_summary.confidence
    assert bias < 0.10, (
        f"Quantity bias too large: hot={hot_summary.confidence}, "
        f"cold={cold_summary.confidence}, bias={bias:.1%}"
    )


@patch("BreakoutStrategy.news_sentiment.analyzer._get_backend_registry")
def test_scarcity_protection(mock_registry):
    """1 条方向性新闻的 confidence 应显著低于 3+ 条"""
    mock_backend = MagicMock()
    mock_backend_cls = MagicMock(return_value=mock_backend)
    mock_registry.return_value = {"deepseek": mock_backend_cls}

    analyzer = SentimentAnalyzer(_make_analyzer_config())

    # 1 条正面新闻
    mock_backend.analyze_all.return_value = [
        SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good"),
    ]
    items_1 = [_item("Single news", "2026-03-14T10:00:00Z")]
    _, summary_1 = analyzer.analyze(items_1, "A", "2026-03-01", "2026-03-15")

    # 4 条正面新闻（同 impact_value）
    mock_backend.analyze_all.return_value = [
        SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good"),
    ] * 4
    items_4 = [_item(f"News {i}", "2026-03-14T10:00:00Z") for i in range(4)]
    _, summary_4 = analyzer.analyze(items_4, "B", "2026-03-01", "2026-03-15")

    # scarcity 惩罚：1 条新闻 confidence 应为 4 条的约 1/3
    assert summary_1.confidence < summary_4.confidence
    assert summary_1.confidence < summary_4.confidence * 0.5
