# News Sentiment Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为新闻情感分析管道添加三项增强功能：max_items 动态化、时间衰减加权、缓存机制。

**Architecture:** 三个功能相互正交，按依赖顺序实现：(1) config 层扩展为后续功能提供配置基础，(2) max_items 动态化最简单且独立，(3) 时间衰减改动 filter.py + analyzer.py，(4) 缓存新建 cache.py 并集成到 api.py + analyzer.py。所有改动通过 `enable` 开关保持向后兼容。

**Tech Stack:** Python 3.12, dataclasses, SQLite (stdlib), math, hashlib, numpy (已有依赖)

**Design Docs:**
- `docs/research/time_weighted_pipeline_design.md` — 时间衰减设计
- `docs/research/sentiment_cache_design.md` — 缓存架构设计

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `BreakoutStrategy/news_sentiment/config.py` | 修改 | 新增 TimeDecayConfig, CacheConfig；FilterConfig 加 time_decay；NewsSentimentConfig 加 cache |
| `BreakoutStrategy/news_sentiment/filter.py` | 修改 | 新增 `_compute_time_weights()`；`filter_news` 加 `reference_date`；`diversity_sample` 加时间加权 FPS |
| `BreakoutStrategy/news_sentiment/api.py` | 修改 | max_items 动态化；传递 reference_date 和 time_decay；缓存集成（增量采集 + 传入 cache） |
| `BreakoutStrategy/news_sentiment/analyzer.py` | 修改 | `_summarize` 加时间加权聚合；`analyze` 加缓存查找/写入 |
| `BreakoutStrategy/news_sentiment/cache.py` | **新建** | SentimentCache 类、news_fingerprint()、compute_uncovered_ranges() |
| `configs/news_sentiment.yaml` | 修改 | 新增 time_decay 和 cache 配置段 |
| `tests/news_sentiment/test_time_decay.py` | **新建** | 时间衰减单元测试 |
| `tests/news_sentiment/test_cache.py` | **新建** | 缓存单元测试 |
| `tests/news_sentiment/test_config.py` | 修改 | 新增配置测试 |
| `tests/news_sentiment/test_filter.py` | 修改 | 新增时间加权 diversity_sample 测试 |
| `tests/news_sentiment/test_analyzer.py` | 修改 | 新增时间加权汇总测试 |

---

## Task 1: 扩展配置层 (TimeDecayConfig + CacheConfig)

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/config.py:48-66` (FilterConfig + NewsSentimentConfig)
- Modify: `configs/news_sentiment.yaml`
- Test: `tests/news_sentiment/test_config.py`

- [ ] **Step 1: 写测试 — 验证新 dataclass 字段存在**

```python
# tests/news_sentiment/test_config.py — 追加

import dataclasses
from BreakoutStrategy.news_sentiment.config import (
    TimeDecayConfig, CacheConfig, FilterConfig, NewsSentimentConfig,
)


def test_time_decay_config_fields():
    """TimeDecayConfig 应包含 enable, half_life, sample_alpha"""
    cfg = TimeDecayConfig(enable=True, half_life=3.0, sample_alpha=0.25)
    assert cfg.enable is True
    assert cfg.half_life == 3.0
    assert cfg.sample_alpha == 0.25


def test_cache_config_fields():
    """CacheConfig 应包含 enable, cache_dir, news_ttl_days, sentiment_ttl_days"""
    cfg = CacheConfig(enable=True, cache_dir="cache/test", news_ttl_days=30, sentiment_ttl_days=0)
    assert cfg.enable is True
    assert cfg.sentiment_ttl_days == 0


def test_filter_config_has_time_decay():
    """FilterConfig 应包含 time_decay 字段"""
    fields = {f.name for f in dataclasses.fields(FilterConfig)}
    assert "time_decay" in fields


def test_sentiment_config_has_cache():
    """NewsSentimentConfig 应包含 cache 字段"""
    fields = {f.name for f in dataclasses.fields(NewsSentimentConfig)}
    assert "cache" in fields
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/news_sentiment/test_config.py -v`
Expected: FAIL — TimeDecayConfig 和 CacheConfig 不存在

- [ ] **Step 3: 实现 — config.py 新增 dataclass + load_config 解析**

在 `config.py` 中 `FilterConfig` 之前新增:

```python
@dataclass
class TimeDecayConfig:
    """时间衰减配置"""
    enable: bool
    half_life: float       # 半衰期（天数）
    sample_alpha: float    # 采样阶段时间偏好强度


@dataclass
class CacheConfig:
    """缓存配置"""
    enable: bool
    cache_dir: str
    news_ttl_days: int       # 新闻缓存过期天数 (0=永不过期)
    sentiment_ttl_days: int  # 情感结果缓存过期天数 (0=永不过期)
```

修改 `FilterConfig` 加字段（使用 `field(default_factory=...)` 保证向后兼容）:
```python
from dataclasses import dataclass, field

@dataclass
class FilterConfig:
    """预过滤配置"""
    max_items: int
    semantic_filter_threshold: float
    semantic_dedup_threshold: float
    relevance_threshold: float
    time_decay: TimeDecayConfig = field(
        default_factory=lambda: TimeDecayConfig(enable=False, half_life=3.0, sample_alpha=0.25)
    )
```

修改 `NewsSentimentConfig` 加字段（cache 放在最后，使用 default_factory）:
```python
@dataclass
class NewsSentimentConfig:
    """模块完整配置"""
    finnhub: CollectorConfig
    alphavantage: CollectorConfig
    edgar: EdgarConfig
    analyzer: AnalyzerConfig
    filter: FilterConfig
    output_dir: str
    proxy: str
    cache: CacheConfig = field(
        default_factory=lambda: CacheConfig(enable=False, cache_dir='cache/news_sentiment',
                                             news_ttl_days=30, sentiment_ttl_days=0)
    )
```

修改 `load_config` 中 filter 和 cache 解析:
```python
    time_decay_cfg = filter_cfg.get('time_decay', {})
    cache_cfg = data.get('cache', {})

    # ... 在 return NewsSentimentConfig 中:
    filter=FilterConfig(
        max_items=filter_cfg.get('max_items', 20),
        semantic_filter_threshold=filter_cfg.get('semantic_filter_threshold', 0.65),
        semantic_dedup_threshold=filter_cfg.get('semantic_dedup_threshold', 0.75),
        relevance_threshold=filter_cfg.get('relevance_threshold', 0.55),
        time_decay=TimeDecayConfig(
            enable=time_decay_cfg.get('enable', False),
            half_life=time_decay_cfg.get('half_life', 3.0),
            sample_alpha=time_decay_cfg.get('sample_alpha', 0.25),
        ),
    ),
    cache=CacheConfig(
        enable=cache_cfg.get('enable', True),
        cache_dir=cache_cfg.get('cache_dir', 'cache/news_sentiment'),
        news_ttl_days=cache_cfg.get('news_ttl_days', 30),
        sentiment_ttl_days=cache_cfg.get('sentiment_ttl_days', 0),
    ),
```

- [ ] **Step 4: 修复所有引用 FilterConfig 构造的现有测试**

`tests/news_sentiment/test_filter.py` 中的 `_default_config` 需要更新:
```python
def _default_config(**overrides) -> FilterConfig:
    from BreakoutStrategy.news_sentiment.config import TimeDecayConfig
    defaults = dict(
        max_items=20, semantic_filter_threshold=0.65,
        semantic_dedup_threshold=0.75, relevance_threshold=0.55,
        time_decay=TimeDecayConfig(enable=False, half_life=3.0, sample_alpha=0.25),
    )
    defaults.update(overrides)
    return FilterConfig(**defaults)
```

- [ ] **Step 5: 运行全部测试，确认通过**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/news_sentiment/test_config.py tests/news_sentiment/test_filter.py -v`
Expected: ALL PASS

- [ ] **Step 6: 更新 YAML 配置文件**

在 `configs/news_sentiment.yaml` 的 `filter:` 段末尾追加 `time_decay:`，并新增 `cache:` 顶层段:

```yaml
filter:
  # ... 现有字段保持不变 ...
  time_decay:
    enable: true
    half_life: 3.0           # 半衰期（天），3天前权重50%
    sample_alpha: 0.25       # 采样时间偏好强度

cache:
  enable: true
  cache_dir: "cache/news_sentiment"
  news_ttl_days: 30          # 新闻30天后过期
  sentiment_ttl_days: 0      # 情感结果永不过期
```

- [ ] **Step 7: Commit**

```bash
git add BreakoutStrategy/news_sentiment/config.py configs/news_sentiment.yaml tests/news_sentiment/test_config.py tests/news_sentiment/test_filter.py
git commit -m "feat(news_sentiment): add TimeDecayConfig and CacheConfig to config layer"
```

---

## Task 2: max_items 动态化

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/api.py:42-44` (在 filter_news 调用前)
- Test: `tests/news_sentiment/test_filter.py` (追加)

- [ ] **Step 1: 写测试 — 验证动态计算公式**

```python
# tests/news_sentiment/test_filter.py — 追加

def test_dynamic_max_items_short_window():
    """3天窗口 → clamp(10*sqrt(3), 15, 100) = 17 → 钳制到 15"""
    from BreakoutStrategy.news_sentiment.api import _compute_dynamic_max_items
    assert _compute_dynamic_max_items(3) == 15


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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/news_sentiment/test_filter.py::test_dynamic_max_items_short_window -v`
Expected: FAIL — `_compute_dynamic_max_items` 不存在

- [ ] **Step 3: 实现 — api.py 新增函数 + 在 analyze() 中调用**

在 `api.py` 顶部 import 区新增:
```python
import math
from datetime import date
```

在 `analyze` 函数之前新增:
```python
def _compute_dynamic_max_items(num_days: int, base: float = 10.0,
                                min_items: int = 15, max_cap: int = 100) -> int:
    """根据时间跨度动态计算 max_items = clamp(base * sqrt(num_days), min, max)"""
    raw = base * math.sqrt(max(1, num_days))
    return int(min(max_cap, max(min_items, raw)))
```

在 `analyze()` 函数的步骤 2（采集）之后、步骤 3（过滤）之前插入:
```python
    import dataclasses

    # 2.8 动态调整 max_items（使用副本，不修改传入的 config）
    try:
        d_from = date.fromisoformat(date_from)
        d_to = date.fromisoformat(date_to)
        num_days = max(1, (d_to - d_from).days)
        dynamic_max = _compute_dynamic_max_items(num_days)
        config = dataclasses.replace(
            config,
            filter=dataclasses.replace(config.filter, max_items=dynamic_max),
        )
        logger.info(f"Dynamic max_items: {dynamic_max} (num_days={num_days})")
    except ValueError:
        pass  # 日期格式错误时保持原值
```

注意：使用 `dataclasses.replace()` 创建浅拷贝，避免修改传入的 config 对象。
在批量分析多只股票或回测时，同一 config 会被复用，就地修改会导致 bug。

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/news_sentiment/test_filter.py -v -k "dynamic_max_items"`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/news_sentiment/api.py tests/news_sentiment/test_filter.py
git commit -m "feat(news_sentiment): dynamic max_items based on sqrt(num_days)"
```

---

## Task 3: 时间衰减 — filter.py 采样层

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/filter.py:46-49` (filter_news 签名), `228-258` (diversity_sample)
- Create: `tests/news_sentiment/test_time_decay.py`

- [ ] **Step 1: 写测试 — _compute_time_weights**

```python
# tests/news_sentiment/test_time_decay.py

import math
from BreakoutStrategy.news_sentiment.filter import _compute_time_weights
from BreakoutStrategy.news_sentiment.models import NewsItem


def _item(title: str, published_at: str) -> NewsItem:
    return NewsItem(
        title=title, summary="", source="Test",
        published_at=published_at, url="", ticker="AAPL",
        category="news", collector="finnhub",
    )


def test_time_weights_same_day():
    """参考日期当天 → 权重 1.0"""
    items = [_item("News", "2026-03-15T10:00:00Z")]
    weights = _compute_time_weights(items, "2026-03-15", 3.0)
    assert weights[0] == 1.0


def test_time_weights_one_half_life():
    """半衰期天数后 → 权重 0.5"""
    items = [_item("News", "2026-03-12T10:00:00Z")]
    weights = _compute_time_weights(items, "2026-03-15", 3.0)
    assert abs(weights[0] - 0.5) < 0.01


def test_time_weights_two_half_lives():
    """两个半衰期后 → 权重 0.25"""
    items = [_item("News", "2026-03-09T10:00:00Z")]
    weights = _compute_time_weights(items, "2026-03-15", 3.0)
    assert abs(weights[0] - 0.25) < 0.01


def test_time_weights_no_date_gets_full_weight():
    """无发布日期 → 保守给满权重 1.0"""
    items = [_item("News", "")]
    weights = _compute_time_weights(items, "2026-03-15", 3.0)
    assert weights[0] == 1.0


def test_time_weights_future_date_gets_full_weight():
    """未来日期 → 权重 1.0"""
    items = [_item("News", "2026-03-20T10:00:00Z")]
    weights = _compute_time_weights(items, "2026-03-15", 3.0)
    assert weights[0] == 1.0
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/news_sentiment/test_time_decay.py -v`
Expected: FAIL — `_compute_time_weights` 不存在

- [ ] **Step 3: 实现 — filter.py 新增 _compute_time_weights**

在 `filter.py` 的 `_days_between` 函数之后新增:

```python
def _compute_time_weights(
    items: list[NewsItem], reference_date: str, half_life: float,
) -> list[float]:
    """
    计算每条新闻的时间衰减权重 w(t) = exp(-ln2/half_life * t)

    Args:
        items: 新闻列表
        reference_date: 参考日期 YYYY-MM-DD（通常为 date_to）
        half_life: 半衰期（天数）

    Returns:
        与 items 等长的权重列表，范围 (0, 1]
    """
    import math
    decay_lambda = math.log(2) / half_life
    ref = date.fromisoformat(reference_date)
    weights = []
    for item in items:
        date_str = item.published_at[:10] if item.published_at else ''
        if not date_str:
            weights.append(1.0)
            continue
        try:
            d = date.fromisoformat(date_str)
            days = max(0, (ref - d).days)
            weights.append(math.exp(-decay_lambda * days))
        except ValueError:
            weights.append(1.0)
    return weights
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/news_sentiment/test_time_decay.py -v`
Expected: ALL PASS

- [ ] **Step 5: 写测试 — 时间加权 diversity_sample**

```python
# tests/news_sentiment/test_time_decay.py — 追加

from BreakoutStrategy.news_sentiment.embedding import embed_texts
from BreakoutStrategy.news_sentiment.filter import diversity_sample


def test_diversity_sample_time_weighted_prefers_recent():
    """时间加权时，近期新闻在多样性相近时优先入选"""
    # 6 条 Apple 新闻，内容相似但日期不同
    items = [
        _item("Apple launches new product line", "2026-03-01T10:00:00Z"),  # 远期
        _item("Apple releases new product update", "2026-03-02T10:00:00Z"),
        _item("Apple announces product changes", "2026-03-05T10:00:00Z"),
        _item("Apple reveals new features today", "2026-03-13T10:00:00Z"),
        _item("Apple unveils latest innovation", "2026-03-14T10:00:00Z"),  # 近期
        _item("Apple presents new technology", "2026-03-15T10:00:00Z"),    # 最近
    ]
    embeddings = embed_texts([i.title for i in items])
    time_weights = _compute_time_weights(items, "2026-03-15", 3.0)

    result = diversity_sample(items, embeddings, max_items=3,
                              time_weights=time_weights, alpha=0.25)
    # 近期新闻（03-13~03-15）应更多被选中
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
```

- [ ] **Step 6: 运行测试，确认失败**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/news_sentiment/test_time_decay.py::test_diversity_sample_time_weighted_prefers_recent -v`
Expected: FAIL — `diversity_sample` 不接受 `time_weights` 参数

- [ ] **Step 7: 实现 — 修改 diversity_sample 和 filter_news**

修改 `diversity_sample` 签名和实现（替换原函数）:

```python
def diversity_sample(
    items: list[NewsItem], embeddings: np.ndarray, max_items: int,
    time_weights: list[float] | None = None,
    alpha: float = 0.25,
) -> list[NewsItem]:
    """
    Greedy Diversity Sampling（FPS cosine 版，可选时间加权）

    当提供 time_weights 时，调整评分: adjusted = max_sim - alpha * tw
    近期新闻（tw≈1）获得时间加分，在多样性相近时优先入选。
    alpha=0 或 time_weights=None 退化为原始 FPS。
    """
    if len(items) <= max_items:
        return items

    sim = cosine_similarity_matrix(embeddings, embeddings)

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-10
    emb_norm = embeddings / norms

    # 种子选择
    if time_weights is not None:
        tw = np.array(time_weights)
        weighted_centroid = (emb_norm * tw[:, np.newaxis]).mean(axis=0)
        weighted_centroid = weighted_centroid / (np.linalg.norm(weighted_centroid) + 1e-10)
        seed = int(np.argmax(emb_norm @ weighted_centroid))
    else:
        centroid = emb_norm.mean(axis=0)
        seed = int(np.argmax(emb_norm @ centroid))

    selected = [seed]
    max_sim_arr = sim[:, seed].copy()

    for _ in range(max_items - 1):
        max_sim_arr[selected] = np.inf
        if time_weights is not None:
            adjusted = max_sim_arr - alpha * tw
            next_idx = int(np.argmin(adjusted))
        else:
            next_idx = int(np.argmin(max_sim_arr))
        selected.append(next_idx)
        max_sim_arr = np.maximum(max_sim_arr, sim[:, next_idx])

    selected.sort()
    return [items[i] for i in selected]
```

修改 `filter_news` 签名，新增 `reference_date` 参数:

```python
def filter_news(
    items: list[NewsItem], config: FilterConfig,
    ticker: str = "", company_name: str = "",
    reference_date: str = "",
) -> list[NewsItem]:
```

修改 Stage 4 调用:
```python
    # Stage 4: 多样性采样（可选时间加权）
    if config.time_decay.enable and reference_date:
        time_weights = _compute_time_weights(deduped, reference_date, config.time_decay.half_life)
        sampled = diversity_sample(
            deduped, deduped_embeddings, config.max_items,
            time_weights=time_weights, alpha=config.time_decay.sample_alpha,
        )
    else:
        sampled = diversity_sample(deduped, deduped_embeddings, config.max_items)
    logger.info(f"[Filter] Diversity sample: {len(deduped)} -> {len(sampled)}")
```

- [ ] **Step 8: 运行全部测试，确认通过**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/news_sentiment/test_time_decay.py tests/news_sentiment/test_filter.py -v`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add BreakoutStrategy/news_sentiment/filter.py tests/news_sentiment/test_time_decay.py
git commit -m "feat(news_sentiment): time-weighted diversity sampling in filter pipeline"
```

---

## Task 4: 时间衰减 — analyzer.py 汇总层

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/analyzer.py:63-89` (analyze 签名), `91-188` (_summarize)
- Test: `tests/news_sentiment/test_time_decay.py` (追加)
- Test: `tests/news_sentiment/test_analyzer.py` (修改 mock)

- [ ] **Step 1: 写测试 — 时间加权汇总**

```python
# tests/news_sentiment/test_time_decay.py — 追加

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
    # 5 条远期负面（权重低）+ 3 条近期正面（权重高）
    sentiments = (
        [SentimentResult(sentiment="negative", confidence=0.8, reasoning="Bad")] * 5
        + [SentimentResult(sentiment="positive", confidence=0.8, reasoning="Good")] * 3
    )
    mock_backend.analyze_all.return_value = sentiments
    mock_backend_cls = MagicMock(return_value=mock_backend)
    mock_registry.return_value = {"deepseek": mock_backend_cls}

    items = (
        [_item(f"Bad news {i}", "2026-03-01T10:00:00Z") for i in range(5)]   # 远期
        + [_item(f"Good news {i}", "2026-03-14T10:00:00Z") for i in range(3)]  # 近期
    )

    td = TimeDecayConfig(enable=True, half_life=3.0, sample_alpha=0.25)
    analyzer = SentimentAnalyzer(_make_analyzer_config())
    _, summary = analyzer.analyze(items, "AAPL", "2026-03-01", "2026-03-15", time_decay=td)

    # 近期正面权重高，应压过远期负面
    assert summary.sentiment == "positive"


@patch("BreakoutStrategy.news_sentiment.analyzer._get_backend_registry")
def test_summarize_no_time_decay_negative_dominates(mock_registry):
    """同样的数据，无时间衰减 → 负面数量多应偏负面"""
    mock_backend = MagicMock()
    sentiments = (
        [SentimentResult(sentiment="negative", confidence=0.8, reasoning="Bad")] * 5
        + [SentimentResult(sentiment="positive", confidence=0.8, reasoning="Good")] * 3
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

    # 无衰减，5 negative > 3 positive
    assert summary.sentiment == "negative"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/news_sentiment/test_time_decay.py::test_summarize_time_decay_recent_positive_dominates -v`
Expected: FAIL — `analyze()` 不接受 `time_decay` 参数

- [ ] **Step 3: 实现 — analyzer.py 加时间衰减**

在 `analyzer.py` 顶部新增 import:
```python
from datetime import date
from BreakoutStrategy.news_sentiment.config import TimeDecayConfig
```

新增 `_compute_time_weights` 内联函数（在 `_get_backend_registry` 之后）:
```python
def _compute_time_weights(
    items: list[NewsItem], reference_date: str, half_life: float,
) -> list[float]:
    """计算每条新闻的时间衰减权重"""
    decay_lambda = math.log(2) / half_life
    ref = date.fromisoformat(reference_date)
    weights = []
    for item in items:
        date_str = item.published_at[:10] if item.published_at else ''
        if not date_str:
            weights.append(1.0)
            continue
        try:
            d = date.fromisoformat(date_str)
            days = max(0, (ref - d).days)
            weights.append(math.exp(-decay_lambda * days))
        except ValueError:
            weights.append(1.0)
    return weights
```

修改 `analyze` 方法签名:
```python
def analyze(self, items: list[NewsItem], ticker: str,
            date_from: str, date_to: str,
            time_decay: TimeDecayConfig | None = None,
) -> tuple[list[AnalyzedItem], SummaryResult]:
```

传递给 `_summarize`:
```python
summary = self._summarize(analyzed_items, ticker, date_from, date_to, time_decay=time_decay)
```

修改 `_summarize` 签名和 Step 0:
```python
def _summarize(self, analyzed_items: list[AnalyzedItem],
               ticker: str, date_from: str, date_to: str,
               time_decay: TimeDecayConfig | None = None,
) -> SummaryResult:
```

Step 0 改为:
```python
        # Step 0: 有效/无效分离 + 分组统计（可选时间加权）
        pos_confs: list[float] = []
        neg_confs: list[float] = []
        pos_tw: list[float] = []
        neg_tw: list[float] = []
        neu_tw_sum = 0.0
        neu_valid = 0
        fail_count = 0

        # 预计算时间权重
        if time_decay and time_decay.enable:
            item_tw = _compute_time_weights(
                [a.news for a in analyzed_items], date_to, time_decay.half_life,
            )
        else:
            item_tw = [1.0] * len(analyzed_items)

        for i, item in enumerate(analyzed_items):
            s, c = item.sentiment.sentiment, item.sentiment.confidence
            tw = item_tw[i]
            if c == 0.0:
                fail_count += 1
                continue
            if s == 'positive':
                pos_confs.append(c)
                pos_tw.append(tw)
            elif s == 'negative':
                neg_confs.append(c)
                neg_tw.append(tw)
            else:
                neu_valid += 1
                neu_tw_sum += tw

        n_p, n_n, n_u = len(pos_confs), len(neg_confs), neu_valid
        w_p = sum(c * t for c, t in zip(pos_confs, pos_tw))
        w_n = sum(c * t for c, t in zip(neg_confs, neg_tw))
```

修改 Step 1 rho 分母:
```python
        rho_denom = w_p + w_n + neu_tw_sum * _W0_RHO
```

修改 neutral-only 分支（Step 3 的 `n_p==0 and n_n==0` 分支），将 `n_u` 替换为 `neu_tw_sum`:
```python
        else:
            if n_p == 0 and n_n == 0:
                k_neu = _K * _K_NEU_MULT
                base_conf = _CAP * (1.0 - math.exp(-neu_tw_sum / k_neu))
```
理由：`neu_tw_sum` 在无衰减时等于 `n_u`（每条权重 1.0），向后兼容。有衰减时，远期 neutral 证据贡献减小，语义上合理。

其余 Step 2-5 的公式不变（它们的输入 w_p, w_n 已经是时间加权值）。

- [ ] **Step 4: 运行全部测试，确认通过**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/news_sentiment/test_time_decay.py tests/news_sentiment/test_analyzer.py -v`
Expected: ALL PASS

- [ ] **Step 5: 修改 api.py 传递参数**

在 `api.py` 的 `filter_news` 调用处加 `reference_date`:
```python
    filtered_items = filter_news(
        all_items, config.filter,
        ticker=ticker, company_name=company_name,
        reference_date=date_to,
    )
```

在 `analyzer.analyze` 调用处加 `time_decay`:
```python
    analyzed_items, summary = analyzer.analyze(
        filtered_items, ticker, date_from, date_to,
        time_decay=config.filter.time_decay,
    )
```

- [ ] **Step 6: 运行全部 news_sentiment 测试**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/news_sentiment/ -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add BreakoutStrategy/news_sentiment/analyzer.py BreakoutStrategy/news_sentiment/api.py tests/news_sentiment/test_time_decay.py
git commit -m "feat(news_sentiment): time-weighted aggregation in summarize stage"
```

---

## Task 5: 缓存模块 — cache.py

**Files:**
- Create: `BreakoutStrategy/news_sentiment/cache.py`
- Create: `tests/news_sentiment/test_cache.py`

- [ ] **Step 1: 写测试 — news_fingerprint**

```python
# tests/news_sentiment/test_cache.py

from BreakoutStrategy.news_sentiment.cache import (
    SentimentCache, news_fingerprint, compute_uncovered_ranges,
)
from BreakoutStrategy.news_sentiment.config import CacheConfig
from BreakoutStrategy.news_sentiment.models import NewsItem, SentimentResult


def _item(title="News", url="https://example.com/1",
          published_at="2026-03-10T10:00:00Z") -> NewsItem:
    return NewsItem(
        title=title, summary="Summary", source="Test",
        published_at=published_at, url=url, ticker="AAPL",
        category="news", collector="finnhub",
    )


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
```

- [ ] **Step 2: 写测试 — compute_uncovered_ranges**

```python
# tests/news_sentiment/test_cache.py — 追加

def test_uncovered_ranges_no_coverage():
    """无覆盖 → 全部未覆盖"""
    result = compute_uncovered_ranges(("2026-03-05", "2026-03-18"), [])
    assert result == [("2026-03-05", "2026-03-18")]


def test_uncovered_ranges_full_coverage():
    """完全覆盖 → 无未覆盖"""
    result = compute_uncovered_ranges(
        ("2026-03-05", "2026-03-18"),
        [("2026-03-01", "2026-03-20")],
    )
    assert result == []


def test_uncovered_ranges_partial_right():
    """右侧缺口"""
    result = compute_uncovered_ranges(
        ("2026-03-05", "2026-03-18"),
        [("2026-03-01", "2026-03-14")],
    )
    assert result == [("2026-03-15", "2026-03-18")]


def test_uncovered_ranges_partial_left():
    """左侧缺口"""
    result = compute_uncovered_ranges(
        ("2026-03-05", "2026-03-18"),
        [("2026-03-10", "2026-03-20")],
    )
    assert result == [("2026-03-05", "2026-03-09")]


def test_uncovered_ranges_gap_in_middle():
    """中间缺口"""
    result = compute_uncovered_ranges(
        ("2026-03-01", "2026-03-20"),
        [("2026-03-01", "2026-03-05"), ("2026-03-10", "2026-03-20")],
    )
    assert result == [("2026-03-06", "2026-03-09")]
```

- [ ] **Step 3: 写测试 — SentimentCache CRUD**

```python
# tests/news_sentiment/test_cache.py — 追加

import tempfile


def _cache_config(tmpdir: str) -> CacheConfig:
    return CacheConfig(enable=True, cache_dir=tmpdir, news_ttl_days=30, sentiment_ttl_days=0)


def test_cache_news_put_and_get(tmp_path):
    """写入新闻 → 按日期范围读取"""
    cache = SentimentCache(_cache_config(str(tmp_path)))
    items = [
        _item("News A", published_at="2026-03-10T10:00:00Z"),
        _item("News B", published_at="2026-03-12T10:00:00Z"),
    ]
    cache.put_news("AAPL", "finnhub", items)
    result = cache.get_news("AAPL", "2026-03-10", "2026-03-12", "finnhub")
    assert len(result) == 2


def test_cache_news_date_range_filter(tmp_path):
    """只返回请求范围内的新闻"""
    cache = SentimentCache(_cache_config(str(tmp_path)))
    items = [
        _item("News A", published_at="2026-03-05T10:00:00Z"),
        _item("News B", published_at="2026-03-10T10:00:00Z"),
        _item("News C", published_at="2026-03-15T10:00:00Z"),
    ]
    cache.put_news("AAPL", "finnhub", items)
    result = cache.get_news("AAPL", "2026-03-08", "2026-03-12", "finnhub")
    assert len(result) == 1
    assert result[0].title == "News B"


def test_cache_sentiment_put_and_get(tmp_path):
    """写入情感结果 → 查找命中"""
    cache = SentimentCache(_cache_config(str(tmp_path)))
    fp = "abc123"
    sent = SentimentResult(sentiment="positive", confidence=0.9, reasoning="Good")
    cache.put_sentiment(fp, "deepseek", "deepseek-chat", sent)
    result = cache.get_sentiment(fp, "deepseek", "deepseek-chat")
    assert result is not None
    assert result.sentiment == "positive"
    assert result.confidence == 0.9


def test_cache_sentiment_miss_different_model(tmp_path):
    """不同 model → 缓存未命中"""
    cache = SentimentCache(_cache_config(str(tmp_path)))
    fp = "abc123"
    sent = SentimentResult(sentiment="positive", confidence=0.9, reasoning="Good")
    cache.put_sentiment(fp, "deepseek", "deepseek-chat", sent)
    result = cache.get_sentiment(fp, "glm", "glm-4.7-flash")
    assert result is None


def test_cache_coverage_tracking(tmp_path):
    """覆盖区间追踪"""
    cache = SentimentCache(_cache_config(str(tmp_path)))
    cache.update_coverage("AAPL", "finnhub", "2026-03-01", "2026-03-14")
    ranges = cache.get_covered_ranges("AAPL", "finnhub")
    assert ("2026-03-01", "2026-03-14") in ranges


def test_cache_disabled_is_noop(tmp_path):
    """enable=False 时所有操作返回空"""
    cfg = CacheConfig(enable=False, cache_dir=str(tmp_path), news_ttl_days=30, sentiment_ttl_days=0)
    cache = SentimentCache(cfg)
    cache.put_news("AAPL", "finnhub", [_item()])
    assert cache.get_news("AAPL", "2026-03-01", "2026-03-15", "finnhub") == []
    assert cache.get_sentiment("fp", "ds", "m") is None
```

- [ ] **Step 4: 运行测试，确认全部失败**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/news_sentiment/test_cache.py -v`
Expected: FAIL — `cache` 模块不存在

- [ ] **Step 5: 实现 — cache.py**

创建 `BreakoutStrategy/news_sentiment/cache.py`:

```python
"""
新闻情感分析缓存

两层缓存:
  1. NewsItem 缓存 — 避免重复采集（按 ticker+collector+日期索引）
  2. SentimentResult 缓存 — 避免重复 LLM 分析（按 news_fingerprint+backend+model 索引）

使用 SQLite 持久化，支持回测场景的跨次复用。
"""

import hashlib
import json
import logging
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from BreakoutStrategy.news_sentiment.config import CacheConfig
from BreakoutStrategy.news_sentiment.models import NewsItem, SentimentResult

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def news_fingerprint(item: NewsItem) -> str:
    """生成新闻的唯一指纹（16字符 hex）"""
    if item.url:
        return hashlib.sha256(item.url.encode()).hexdigest()[:16]
    key = f"{item.title}|{item.published_at}|{item.source}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def compute_uncovered_ranges(
    requested: tuple[str, str],
    covered: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """
    计算请求范围中未被覆盖的子区间（区间差集）

    Args:
        requested: (date_from, date_to) YYYY-MM-DD
        covered: 已覆盖区间列表

    Returns:
        未覆盖的子区间列表
    """
    req_start = date.fromisoformat(requested[0])
    req_end = date.fromisoformat(requested[1])

    if not covered:
        return [requested]

    # 排序并合并已覆盖区间
    intervals = sorted(
        (date.fromisoformat(s), date.fromisoformat(e)) for s, e in covered
    )
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        if s <= merged[-1][1] + timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    # 从 requested 中减去 merged
    uncovered = []
    cursor = req_start
    for cs, ce in merged:
        if cursor > req_end:
            break
        if cs > cursor:
            uncovered.append((
                cursor.isoformat(),
                min(cs - timedelta(days=1), req_end).isoformat(),
            ))
        cursor = max(cursor, ce + timedelta(days=1))

    if cursor <= req_end:
        uncovered.append((cursor.isoformat(), req_end.isoformat()))

    return uncovered


class SentimentCache:
    """新闻情感分析缓存管理器"""

    def __init__(self, config: CacheConfig):
        self._enabled = config.enable
        self._news_ttl = config.news_ttl_days
        self._sentiment_ttl = config.sentiment_ttl_days

        if not self._enabled:
            self._conn = None
            return

        cache_dir = PROJECT_ROOT / config.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        db_path = cache_dir / "cache.db"
        self._conn = sqlite3.connect(str(db_path))
        self._init_tables()

    def _init_tables(self):
        c = self._conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS news (
                fingerprint TEXT NOT NULL,
                ticker TEXT NOT NULL,
                collector TEXT NOT NULL,
                published_date TEXT NOT NULL,
                data JSON NOT NULL,
                created_at TEXT DEFAULT (date('now')),
                PRIMARY KEY (fingerprint)
            );
            CREATE INDEX IF NOT EXISTS idx_news_lookup
                ON news(ticker, collector, published_date);

            CREATE TABLE IF NOT EXISTS sentiments (
                fingerprint TEXT NOT NULL,
                backend TEXT NOT NULL,
                model TEXT NOT NULL,
                sentiment TEXT NOT NULL,
                confidence REAL NOT NULL,
                reasoning TEXT NOT NULL,
                created_at TEXT DEFAULT (date('now')),
                PRIMARY KEY (fingerprint, backend, model)
            );

            CREATE TABLE IF NOT EXISTS coverage (
                ticker TEXT NOT NULL,
                collector TEXT NOT NULL,
                date_from TEXT NOT NULL,
                date_to TEXT NOT NULL,
                PRIMARY KEY (ticker, collector, date_from, date_to)
            );
        """)
        self._conn.commit()

    def put_news(self, ticker: str, collector: str, items: list[NewsItem]) -> None:
        if not self._enabled or not items:
            return
        c = self._conn.cursor()
        for item in items:
            fp = news_fingerprint(item)
            pub_date = item.published_at[:10] if item.published_at else ''
            data = json.dumps({
                'title': item.title, 'summary': item.summary,
                'source': item.source, 'published_at': item.published_at,
                'url': item.url, 'ticker': item.ticker,
                'category': item.category, 'collector': item.collector,
                'raw_sentiment': item.raw_sentiment,
            }, ensure_ascii=False)
            c.execute(
                "INSERT OR REPLACE INTO news (fingerprint, ticker, collector, published_date, data) "
                "VALUES (?, ?, ?, ?, ?)",
                (fp, ticker, collector, pub_date, data),
            )
        self._conn.commit()

    def get_news(self, ticker: str, date_from: str, date_to: str,
                 collector: str) -> list[NewsItem]:
        if not self._enabled:
            return []
        c = self._conn.cursor()
        c.execute(
            "SELECT data FROM news WHERE ticker=? AND collector=? "
            "AND published_date >= ? AND published_date <= ?",
            (ticker, collector, date_from, date_to),
        )
        items = []
        for (data_json,) in c.fetchall():
            d = json.loads(data_json)
            items.append(NewsItem(**d))
        return items

    def put_sentiment(self, fingerprint: str, backend: str, model: str,
                      result: SentimentResult) -> None:
        if not self._enabled:
            return
        c = self._conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO sentiments "
            "(fingerprint, backend, model, sentiment, confidence, reasoning) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fingerprint, backend, model,
             result.sentiment, result.confidence, result.reasoning),
        )
        self._conn.commit()

    def get_sentiment(self, fingerprint: str, backend: str,
                      model: str) -> SentimentResult | None:
        if not self._enabled:
            return None
        c = self._conn.cursor()
        c.execute(
            "SELECT sentiment, confidence, reasoning FROM sentiments "
            "WHERE fingerprint=? AND backend=? AND model=?",
            (fingerprint, backend, model),
        )
        row = c.fetchone()
        if row is None:
            return None
        return SentimentResult(sentiment=row[0], confidence=row[1], reasoning=row[2])

    def get_covered_ranges(self, ticker: str,
                           collector: str) -> list[tuple[str, str]]:
        if not self._enabled:
            return []
        c = self._conn.cursor()
        c.execute(
            "SELECT date_from, date_to FROM coverage "
            "WHERE ticker=? AND collector=?",
            (ticker, collector),
        )
        return [(r[0], r[1]) for r in c.fetchall()]

    def update_coverage(self, ticker: str, collector: str,
                        date_from: str, date_to: str) -> None:
        if not self._enabled:
            return
        c = self._conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO coverage (ticker, collector, date_from, date_to) "
            "VALUES (?, ?, ?, ?)",
            (ticker, collector, date_from, date_to),
        )
        self._conn.commit()

    def stats(self) -> dict:
        if not self._enabled:
            return {"enabled": False}
        c = self._conn.cursor()
        c.execute("SELECT COUNT(*) FROM news")
        news_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM sentiments")
        sentiment_count = c.fetchone()[0]
        return {"enabled": True, "news": news_count, "sentiments": sentiment_count}

    def clear(self, ticker: str | None = None) -> None:
        if not self._enabled:
            return
        c = self._conn.cursor()
        if ticker:
            c.execute("DELETE FROM news WHERE ticker=?", (ticker,))
            c.execute("DELETE FROM sentiments WHERE fingerprint IN "
                       "(SELECT fingerprint FROM news WHERE ticker=?)", (ticker,))
            c.execute("DELETE FROM coverage WHERE ticker=?", (ticker,))
        else:
            c.execute("DELETE FROM news")
            c.execute("DELETE FROM sentiments")
            c.execute("DELETE FROM coverage")
        self._conn.commit()
```

- [ ] **Step 6: 运行测试，确认通过**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/news_sentiment/test_cache.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add BreakoutStrategy/news_sentiment/cache.py tests/news_sentiment/test_cache.py
git commit -m "feat(news_sentiment): add SentimentCache with SQLite persistence"
```

---

## Task 6: 缓存集成 — api.py + analyzer.py

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/api.py` (增量采集 + 传入 cache)
- Modify: `BreakoutStrategy/news_sentiment/analyzer.py` (缓存查找/写入)

- [ ] **Step 1: 实现 — api.py 增量采集**

在 `api.py` 顶部新增 import:
```python
from BreakoutStrategy.news_sentiment.cache import SentimentCache, compute_uncovered_ranges
```

在 `analyze()` 函数开头，config 加载之后新增缓存初始化:
```python
    cache = SentimentCache(config.cache)
```

替换原有的采集循环（步骤 2）为增量采集版本:
```python
    # 2. 增量采集（缓存感知）
    all_items: list[NewsItem] = []
    source_stats: dict[str, int] = {}

    for collector in collectors:
        if not collector.is_available():
            logger.info(f"[{collector.name}] Not available, skipping")
            continue

        try:
            # 查询已覆盖区间
            covered = cache.get_covered_ranges(ticker, collector.name)
            uncovered = compute_uncovered_ranges((date_from, date_to), covered)

            # 从缓存获取已有新闻
            cached_items = cache.get_news(ticker, date_from, date_to, collector.name)

            # 仅采集未覆盖范围
            new_items: list[NewsItem] = []
            for uc_from, uc_to in uncovered:
                fetched = collector.collect(ticker, uc_from, uc_to)
                new_items.extend(fetched)

            # 写入缓存
            if new_items:
                cache.put_news(ticker, collector.name, new_items)
            for uc_from, uc_to in uncovered:
                cache.update_coverage(ticker, collector.name, uc_from, uc_to)

            combined = cached_items + new_items
            source_stats[collector.name] = len(combined)
            all_items.extend(combined)
            logger.info(
                f"[{collector.name}] {len(cached_items)} cached + "
                f"{len(new_items)} new = {len(combined)} items"
            )
        except Exception as e:
            logger.error(f"[{collector.name}] Unexpected error: {e}")
            source_stats[collector.name] = 0
```

- [ ] **Step 2: 实现 — analyzer.py 缓存集成**

修改 `SentimentAnalyzer.__init__` 接受可选 cache:
```python
def __init__(self, config: AnalyzerConfig, cache: SentimentCache | None = None):
    self._config = config
    self._cache = cache
    # ... registry/backend 初始化不变
```

顶部新增 import:
```python
from BreakoutStrategy.news_sentiment.cache import SentimentCache, news_fingerprint
```

修改 `analyze` 方法中 Stage 1，在 `self._backend.analyze_all` 调用处加缓存逻辑:
```python
        # Stage 1: 缓存查找 + backend 分析
        backend_name = self._config.backend
        model_name = self._config.model

        if self._cache:
            cached_results: dict[int, SentimentResult] = {}
            uncached_indices: list[int] = []
            uncached_items: list[NewsItem] = []

            for i, item in enumerate(items):
                fp = news_fingerprint(item)
                cached = self._cache.get_sentiment(fp, backend_name, model_name)
                if cached is not None:
                    cached_results[i] = cached
                else:
                    uncached_indices.append(i)
                    uncached_items.append(item)

            logger.info(
                f"[Cache] {len(cached_results)} hits, {len(uncached_items)} misses"
            )

            if uncached_items:
                new_sentiments = self._backend.analyze_all(uncached_items, ticker)
                for idx, sent in zip(uncached_indices, new_sentiments):
                    if sent.confidence > 0:
                        fp = news_fingerprint(items[idx])
                        self._cache.put_sentiment(fp, backend_name, model_name, sent)
                    cached_results[idx] = sent

            sentiments = [cached_results[i] for i in range(len(items))]
        else:
            sentiments = self._backend.analyze_all(items, ticker)
```

在 `api.py` 中传入 cache 给 analyzer:
```python
    analyzer = SentimentAnalyzer(config.analyzer, cache=cache)
```

- [ ] **Step 3: 写测试 — analyzer 缓存集成**

```python
# tests/news_sentiment/test_cache.py — 追加

from unittest.mock import patch, MagicMock
from BreakoutStrategy.news_sentiment.analyzer import SentimentAnalyzer
from BreakoutStrategy.news_sentiment.config import AnalyzerConfig


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
    sent = SentimentResult(sentiment="positive", confidence=0.9, reasoning="Good")
    cache.put_sentiment(fp, "deepseek", "test-model", sent)

    analyzer = SentimentAnalyzer(_make_analyzer_config(), cache=cache)
    analyzed, summary = analyzer.analyze([item], "AAPL", "2026-03-01", "2026-03-15")

    # backend 不应被调用
    mock_backend.analyze_all.assert_not_called()
    assert analyzed[0].sentiment.sentiment == "positive"


@patch("BreakoutStrategy.news_sentiment.analyzer._get_backend_registry")
def test_analyzer_cache_miss_calls_backend_and_caches(mock_registry, tmp_path):
    """缓存未命中时调用 backend 并写入缓存"""
    mock_backend = MagicMock()
    sent = SentimentResult(sentiment="negative", confidence=0.7, reasoning="Bad")
    mock_backend.analyze_all.return_value = [sent]
    mock_backend_cls = MagicMock(return_value=mock_backend)
    mock_registry.return_value = {"deepseek": mock_backend_cls}

    cache = SentimentCache(_cache_config(str(tmp_path)))
    item = _item("Uncached news", url="https://example.com/new")

    analyzer = SentimentAnalyzer(_make_analyzer_config(), cache=cache)
    analyzed, summary = analyzer.analyze([item], "AAPL", "2026-03-01", "2026-03-15")

    # backend 应被调用
    mock_backend.analyze_all.assert_called_once()
    # 结果应被缓存
    fp = news_fingerprint(item)
    cached = cache.get_sentiment(fp, "deepseek", "test-model")
    assert cached is not None
    assert cached.sentiment == "negative"
```

- [ ] **Step 4: 运行全部 news_sentiment 测试**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/news_sentiment/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/news_sentiment/api.py BreakoutStrategy/news_sentiment/analyzer.py tests/news_sentiment/test_cache.py
git commit -m "feat(news_sentiment): integrate cache into collect and analyze pipeline"
```

---

## Task 7: 最终集成验证

- [ ] **Step 1: 运行全部测试**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/news_sentiment/ -v`
Expected: ALL PASS

- [ ] **Step 2: 添加 cache/ 到 .gitignore**

确认 `cache/` 目录在 `.gitignore` 中（缓存数据不应提交）:
```
cache/
```

- [ ] **Step 3: 最终 Commit**

```bash
git add .gitignore
git commit -m "chore: add cache/ to .gitignore"
```
