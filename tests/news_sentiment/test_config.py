"""测试配置加载的 backend 相关变更"""

import dataclasses
from BreakoutStrategy.news_sentiment.config import AnalyzerConfig


def test_analyzer_config_has_new_fields():
    """AnalyzerConfig 应包含 backend, max_concurrency, proxy"""
    config = AnalyzerConfig(
        api_key="test", backend="deepseek", model="deepseek-chat",
        temperature=0.1, max_concurrency=20, proxy="http://localhost:7890",
    )
    assert config.backend == "deepseek"
    assert config.max_concurrency == 20
    assert config.proxy == "http://localhost:7890"


def test_analyzer_config_no_batch_size():
    """AnalyzerConfig 不应再包含 batch_size 和 request_interval"""
    fields = {f.name for f in dataclasses.fields(AnalyzerConfig)}
    assert "batch_size" not in fields
    assert "request_interval" not in fields


from BreakoutStrategy.news_sentiment.config import (
    TimeDecayConfig, CacheConfig, FilterConfig, NewsSentimentConfig,
    DynamicMaxItemsConfig,
)


def test_time_decay_config_fields():
    """TimeDecayConfig 应包含 enable, half_life, sample_prefer_recent, sample_alpha"""
    cfg = TimeDecayConfig(enable=True, half_life=3.0, sample_prefer_recent=True, sample_alpha=0.25)
    assert cfg.enable is True
    assert cfg.half_life == 3.0
    assert cfg.sample_prefer_recent is True
    assert cfg.sample_alpha == 0.25


def test_cache_config_fields():
    """CacheConfig 应包含 enable, cache_dir, news_ttl_days, sentiment_ttl_days"""
    cfg = CacheConfig(enable=True, cache_dir="cache/test", news_ttl_days=30, sentiment_ttl_days=0)
    assert cfg.enable is True
    assert cfg.sentiment_ttl_days == 0


def test_dynamic_max_items_config_fields():
    """DynamicMaxItemsConfig 应包含 base, min_items, max_items 且有默认值"""
    cfg = DynamicMaxItemsConfig()
    assert cfg.base == 10.0
    assert cfg.min_items == 15
    assert cfg.max_items == 100


def test_filter_config_has_time_decay():
    """FilterConfig 应包含 time_decay 和 dynamic_max_items 字段"""
    fields = {f.name for f in dataclasses.fields(FilterConfig)}
    assert "time_decay" in fields
    assert "dynamic_max_items" in fields


def test_sentiment_config_has_cache():
    """NewsSentimentConfig 应包含 cache 字段"""
    fields = {f.name for f in dataclasses.fields(NewsSentimentConfig)}
    assert "cache" in fields
