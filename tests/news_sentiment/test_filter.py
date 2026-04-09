"""filter.py 语义过滤单元测试"""

from BreakoutStrategy.news_sentiment.config import FilterConfig
from BreakoutStrategy.news_sentiment.embedding import embed_texts
from BreakoutStrategy.news_sentiment.filter import (
    diversity_sample,
    filter_news,
    relevance_filter,
    semantic_dedup,
    semantic_filter,
)
from BreakoutStrategy.news_sentiment.models import NewsItem


def _item(title: str, published_at: str = "2026-03-10T14:00:00Z",
          summary: str = "", category: str = "news",
          raw_sentiment: float | None = None) -> NewsItem:
    return NewsItem(
        title=title, summary=summary, source="Test",
        published_at=published_at, url="", ticker="AAPL",
        category=category, collector="finnhub",
        raw_sentiment=raw_sentiment,
    )


def _default_config(**overrides) -> FilterConfig:
    from BreakoutStrategy.news_sentiment.config import TimeDecayConfig
    defaults = dict(
        max_items=20, semantic_filter_threshold=0.65,
        semantic_dedup_threshold=0.75, relevance_threshold=0.55,
        time_decay=TimeDecayConfig(enable=False, half_life=3.0, sample_alpha=0.25),
    )
    defaults.update(overrides)
    return FilterConfig(**defaults)


# --- semantic_filter ---

def test_semantic_filter_removes_clickbait():
    """低价值投资建议类标题被过滤"""
    items = [
        _item("Top 5 Stocks to Buy and Hold Forever"),
        _item("Apple launches new iPhone model"),
        _item("You Won't Believe This Stock's Returns"),
    ]
    embeddings = embed_texts([i.title for i in items])
    filtered, _ = semantic_filter(items, embeddings, threshold=0.65)
    # 至少 Apple 新闻应保留，clickbait 应被过滤
    titles = [i.title for i in filtered]
    assert "Apple launches new iPhone model" in titles
    assert len(filtered) < len(items)


def test_semantic_filter_keeps_real_news():
    """真正的财经新闻不被过滤"""
    items = [
        _item("Apple Reports Record Q1 Revenue of $124 Billion"),
        _item("Fed Raises Interest Rates by 25 Basis Points"),
        _item("Tesla Recalls 500,000 Vehicles Over Safety Concerns"),
    ]
    embeddings = embed_texts([i.title for i in items])
    filtered, _ = semantic_filter(items, embeddings, threshold=0.65)
    assert len(filtered) == 3


# --- semantic_dedup ---

def test_semantic_dedup_merges_same_event():
    """同一事件的不同报道被合并"""
    items = [
        _item("Apple Cuts China App Store Fee to 25%", summary="short"),
        _item("Apple Reduces App Store Commission in China After Pressure", summary="longer summary here"),
    ]
    embeddings = embed_texts([i.title for i in items])
    result, result_emb = semantic_dedup(items, embeddings, threshold=0.75)
    assert len(result) == 1
    assert len(result_emb) == 1
    assert "longer" in result[0].summary


def test_semantic_dedup_keeps_different_events():
    """不同事件不被合并"""
    items = [
        _item("Apple launches new iPhone"),
        _item("Tesla recalls 500k vehicles"),
        _item("Fed raises interest rates"),
    ]
    embeddings = embed_texts([i.title for i in items])
    result, result_emb = semantic_dedup(items, embeddings, threshold=0.75)
    assert len(result) == 3
    assert len(result_emb) == 3


def test_semantic_dedup_respects_day_gap():
    """相隔超过 3 天的相似标题不合并"""
    items = [
        _item("Apple earnings report released", published_at="2026-03-03T10:00:00Z"),
        _item("Apple earnings report released", published_at="2026-03-10T10:00:00Z"),
    ]
    embeddings = embed_texts([i.title for i in items])
    result, _ = semantic_dedup(items, embeddings, threshold=0.75, max_day_gap=3)
    assert len(result) == 2


def test_semantic_dedup_merges_within_day_gap():
    """相隔 1 天的相似标题可以合并"""
    items = [
        _item("Apple earnings report released", published_at="2026-03-10T10:00:00Z"),
        _item("Apple earnings report released", published_at="2026-03-11T10:00:00Z"),
    ]
    embeddings = embed_texts([i.title for i in items])
    result, _ = semantic_dedup(items, embeddings, threshold=0.75, max_day_gap=3)
    assert len(result) == 1


# --- relevance_filter ---

def test_relevance_filter_removes_unrelated():
    """与目标股票无关的新闻被过滤"""
    items = [
        _item("Apple Reports Record Q1 Revenue"),
        _item("Apple Launches New iPhone Model"),
        _item("Volkswagen Q4 Earnings Call Transcript"),
        _item("Sony Fighting $2.7 Billion UK Lawsuit"),
        _item("Fed Raises Interest Rates by 25 Basis Points"),
    ]
    embeddings = embed_texts([i.title for i in items])
    result, result_emb = relevance_filter(items, embeddings, ticker="AAPL", threshold=0.55, company_name="Apple")
    titles = [r.title for r in result]
    assert "Apple Reports Record Q1 Revenue" in titles
    assert "Apple Launches New iPhone Model" in titles
    assert len(result) < len(items)
    assert len(result_emb) == len(result)


def test_relevance_filter_keeps_related():
    """与目标股票直接相关的新闻保留"""
    items = [
        _item("Apple Reports Record Q1 Revenue"),
        _item("Apple Launches New iPhone Model"),
        _item("Apple Cuts App Store Commission"),
    ]
    embeddings = embed_texts([i.title for i in items])
    result, _ = relevance_filter(items, embeddings, ticker="AAPL", threshold=0.55, company_name="Apple")
    assert len(result) == 3


# --- diversity_sample ---

def test_diversity_sample_truncates_to_max():
    """截断到 max_items"""
    items = [_item(f"News {i}", published_at="2026-03-10T10:00:00Z") for i in range(50)]
    embeddings = embed_texts([i.title for i in items])
    result = diversity_sample(items, embeddings, max_items=5)
    assert len(result) == 5


def test_diversity_sample_covers_different_topics():
    """不同主题被覆盖"""
    items = [
        _item("Apple launches new iPhone model"),
        _item("Apple releases new iPad lineup"),
        _item("Apple unveils new MacBook Pro"),
        _item("Tesla recalls 500k vehicles over safety issue"),
        _item("Fed raises interest rates by 25 basis points"),
        _item("Oil prices surge amid Middle East tensions"),
    ]
    embeddings = embed_texts([i.title for i in items])
    result = diversity_sample(items, embeddings, max_items=3)
    # 应覆盖不同主题（Apple/Tesla/Fed/Oil），而不是选 3 条 Apple 新闻
    titles = [r.title for r in result]
    apple_count = sum(1 for t in titles if "Apple" in t)
    assert apple_count <= 2  # 至多 2 条 Apple，至少选 1 条非 Apple


def test_diversity_sample_deterministic():
    """确定性：同输入同输出"""
    items = [_item(f"Topic {i} news article") for i in range(30)]
    embeddings = embed_texts([i.title for i in items])
    result1 = diversity_sample(items, embeddings, max_items=10)
    result2 = diversity_sample(items, embeddings, max_items=10)
    assert [r.title for r in result1] == [r.title for r in result2]


def test_diversity_sample_no_truncation_when_under_limit():
    """数量不超过 max_items 时原样返回"""
    items = [_item(f"News {i}") for i in range(3)]
    embeddings = embed_texts([i.title for i in items])
    result = diversity_sample(items, embeddings, max_items=10)
    assert len(result) == 3


# --- filter_news (integration) ---

def test_filter_news_full_pipeline():
    """完整管道集成测试"""
    items = [
        _item("Top 10 Best Stocks to Buy Now"),               # 语义过滤掉
        _item("Apple Reports Record Revenue"),                 # 保留
        _item("Apple Posts Highest Earnings in History"),       # 与上一条语义相似
        _item("Tesla Announces New Factory in Mexico"),         # 保留
    ]
    config = _default_config(semantic_dedup_threshold=0.7)
    result = filter_news(items, config, ticker="AAPL")
    # 至少过滤掉 clickbait，可能去重 Apple 的两条
    assert len(result) <= 3


def test_dynamic_max_items_short_window():
    """3天窗口 → clamp(10*sqrt(3), 15, 100) = int(17.32) = 17（min钳制不触发，17 > 15）"""
    from BreakoutStrategy.news_sentiment.api import _compute_dynamic_max_items
    assert _compute_dynamic_max_items(3) == 17


def test_dynamic_max_items_medium_window():
    """15天窗口 → clamp(10*sqrt(15), 15, 100) = 38"""
    from BreakoutStrategy.news_sentiment.api import _compute_dynamic_max_items
    assert _compute_dynamic_max_items(15) == 38


def test_dynamic_max_items_long_window():
    """90天窗口 → clamp(10*sqrt(90), 15, 100) = 94"""
    from BreakoutStrategy.news_sentiment.api import _compute_dynamic_max_items
    assert _compute_dynamic_max_items(90) == 94


def test_dynamic_max_items_very_long_window():
    """150天窗口 → clamp(10*sqrt(150), 15, 100) = 100（上限钳制）"""
    from BreakoutStrategy.news_sentiment.api import _compute_dynamic_max_items
    assert _compute_dynamic_max_items(150) == 100


def test_dynamic_max_items_custom_config():
    """DynamicMaxItemsConfig 自定义参数应正确传递到 _compute_dynamic_max_items"""
    from BreakoutStrategy.news_sentiment.api import _compute_dynamic_max_items
    # base=5, min=10, max=50: clamp(5*sqrt(30), 10, 50) = int(27.38) = 27
    assert _compute_dynamic_max_items(30, base=5.0, min_items=10, max_cap=50) == 27
    # 上限钳制: clamp(5*sqrt(200), 10, 50) = 50
    assert _compute_dynamic_max_items(200, base=5.0, min_items=10, max_cap=50) == 50
    # 下限钳制: clamp(5*sqrt(1), 10, 50) = 10
    assert _compute_dynamic_max_items(1, base=5.0, min_items=10, max_cap=50) == 10
