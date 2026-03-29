# News Sentiment Optimization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize news_sentiment module to reduce GLM API calls from 51 to 2 by adding a three-stage news filter pipeline, removing Finnhub paid endpoint, and improving JSON parse robustness.

**Architecture:** Add `filter.py` with keyword filter → Jaccard title dedup → daily sampling pipeline. Modify Finnhub collector, api.py orchestration, config, and analyzer JSON handling.

**Tech Stack:** Pure Python (set operations for Jaccard, json.JSONDecoder for robust parsing). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-03-16-news-sentiment-optimization-design.md`

---

## File Structure

| Action | Path | Responsibility |
|---|---|---|
| Create | `BreakoutStrategy/news_sentiment/filter.py` | Three-stage filter pipeline |
| Create | `tests/news_sentiment/test_filter.py` | Filter logic tests |
| Modify | `BreakoutStrategy/news_sentiment/config.py` | Add FilterConfig dataclass |
| Modify | `configs/news_sentiment.yaml` | Add filter section, update batch_size |
| Modify | `BreakoutStrategy/news_sentiment/collectors/finnhub_collector.py` | Remove paid endpoint |
| Modify | `BreakoutStrategy/news_sentiment/analyzer.py` | JSON robustness + retry prompt |
| Modify | `BreakoutStrategy/news_sentiment/api.py` | Insert filter step |

---

### Task 1: Add FilterConfig and Update Config

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/config.py`
- Modify: `configs/news_sentiment.yaml`

- [ ] **Step 1: Add FilterConfig dataclass to config.py**

Add after `AnalyzerConfig`:

```python
@dataclass
class FilterConfig:
    """预过滤配置"""
    max_items: int
    similarity_threshold: float
    keyword_blacklist: list[str]
```

Add `filter` field to `NewsSentimentConfig`:

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
```

In `load_config()`, add after `output_cfg`:

```python
    filter_cfg = data.get('filter', {})
```

And add to the `NewsSentimentConfig` constructor (before `output_dir`):

```python
        filter=FilterConfig(
            max_items=filter_cfg.get('max_items', 20),
            similarity_threshold=filter_cfg.get('similarity_threshold', 0.6),
            keyword_blacklist=filter_cfg.get('keyword_blacklist') or [],
        ),
```

Also update `batch_size` default from 5 to 20:

```python
            batch_size=analyzer_cfg.get('batch_size', 20),
```

- [ ] **Step 2: Update configs/news_sentiment.yaml**

Add `filter` section and update `batch_size`:

```yaml
filter:
  max_items: 20
  similarity_threshold: 0.6
  keyword_blacklist: []

analyzer:
  api_key: ""
  model: "glm-4.7-flash"
  temperature: 0.1
  batch_size: 20
  request_interval: 1.0
```

- [ ] **Step 3: Verify config loads**

```bash
uv run python -c "from BreakoutStrategy.news_sentiment.config import load_config; c = load_config(); print(f'filter.max_items={c.filter.max_items}, batch_size={c.analyzer.batch_size}')"
```

Expected: `filter.max_items=20, batch_size=20`

- [ ] **Step 4: Commit**

```bash
git add BreakoutStrategy/news_sentiment/config.py configs/news_sentiment.yaml
git commit -m "feat(news_sentiment): add FilterConfig, update batch_size to 20"
```

---

### Task 2: Create Filter Module with Tests

**Files:**
- Create: `BreakoutStrategy/news_sentiment/filter.py`
- Create: `tests/news_sentiment/test_filter.py`

**Dependencies:** Task 1

- [ ] **Step 1: Write filter tests**

Create `tests/news_sentiment/test_filter.py`:

```python
"""filter.py 单元测试"""

from BreakoutStrategy.news_sentiment.filter import (
    keyword_filter,
    title_dedup,
    daily_sample,
    filter_news,
    DEFAULT_KEYWORD_BLACKLIST,
)
from BreakoutStrategy.news_sentiment.models import NewsItem


def _item(title: str, published_at: str = "2026-03-10T14:00:00Z",
          summary: str = "", category: str = "news",
          raw_sentiment: float | None = None, url: str = "") -> NewsItem:
    return NewsItem(
        title=title, summary=summary, source="Test",
        published_at=published_at, url=url, ticker="AAPL",
        category=category, collector="finnhub",
        raw_sentiment=raw_sentiment,
    )


# --- keyword_filter ---

def test_keyword_filter_removes_low_value():
    items = [
        _item("AAPL technical analysis shows bullish pattern"),
        _item("Apple launches new product"),
        _item("AAPL price target raised to $200"),
    ]
    result = keyword_filter(items, DEFAULT_KEYWORD_BLACKLIST)
    assert len(result) == 1
    assert result[0].title == "Apple launches new product"


def test_keyword_filter_case_insensitive():
    items = [_item("AAPL Technical Analysis Report")]
    result = keyword_filter(items, DEFAULT_KEYWORD_BLACKLIST)
    assert len(result) == 0


def test_keyword_filter_empty_blacklist_keeps_all():
    items = [_item("technical analysis"), _item("Apple news")]
    result = keyword_filter(items, [])
    assert len(result) == 2


# --- title_dedup ---

def test_title_dedup_merges_similar():
    items = [
        _item("Apple Reports Record Q1 Revenue", summary="short"),
        _item("Apple Reports Record Q1 Revenue Beating Estimates", summary="longer summary here"),
    ]
    result = title_dedup(items, threshold=0.6)
    assert len(result) == 1
    assert "longer" in result[0].summary  # 保留 summary 更长的


def test_title_dedup_keeps_different():
    items = [
        _item("Apple launches new iPhone"),
        _item("Tesla recalls 500k vehicles"),
    ]
    result = title_dedup(items, threshold=0.6)
    assert len(result) == 2


def test_title_dedup_cross_day_no_merge():
    """不同日期的相似标题不合并"""
    items = [
        _item("Apple earnings report", published_at="2026-03-10T10:00:00Z"),
        _item("Apple earnings report", published_at="2026-03-11T10:00:00Z"),
    ]
    result = title_dedup(items, threshold=0.6)
    assert len(result) == 2


# --- daily_sample ---

def test_daily_sample_truncates_to_max():
    items = [_item(f"News {i}", published_at="2026-03-10T10:00:00Z") for i in range(50)]
    result = daily_sample(items, max_items=5)
    assert len(result) == 5


def test_daily_sample_redistributes_quota():
    """稀疏天的剩余配额分配给密集天"""
    items = [
        _item("Sparse day", published_at="2026-03-10T10:00:00Z"),
        *[_item(f"Dense {i}", published_at="2026-03-11T10:00:00Z") for i in range(30)],
    ]
    result = daily_sample(items, max_items=10)
    assert len(result) == 10


def test_daily_sample_prioritizes_earnings():
    items = [
        _item("Random news 1", published_at="2026-03-10T10:00:00Z"),
        _item("Random news 2", published_at="2026-03-10T11:00:00Z"),
        _item("Earnings Report", published_at="2026-03-10T12:00:00Z", category="earnings"),
    ]
    result = daily_sample(items, max_items=1)
    assert result[0].category == "earnings"


# --- filter_news (integration) ---

def test_filter_news_full_pipeline():
    items = [
        _item("Apple technical analysis bullish"),       # 关键词过滤掉
        _item("Apple launches new product"),             # 保留
        _item("Apple launches new product line today"),  # 与上一条相似，去重
        _item("Tesla earnings beat estimates", category="earnings"),  # 保留
    ]
    from BreakoutStrategy.news_sentiment.config import FilterConfig
    config = FilterConfig(max_items=20, similarity_threshold=0.6, keyword_blacklist=[])
    result = filter_news(items, config)
    assert len(result) == 2  # "Apple launches..." + "Tesla earnings..."
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/news_sentiment/test_filter.py -v
```

Expected: FAIL (filter module not found)

- [ ] **Step 3: Implement filter.py**

Create `BreakoutStrategy/news_sentiment/filter.py`:

```python
"""
新闻预过滤管道

三层过滤: 关键词去噪 → 标题相似度去重 → 按天采样截断。
全部本地计算，零 API 调用，毫秒级完成。
"""

import logging
from collections import defaultdict
from math import ceil

from BreakoutStrategy.news_sentiment.config import FilterConfig
from BreakoutStrategy.news_sentiment.models import NewsItem

logger = logging.getLogger(__name__)

DEFAULT_KEYWORD_BLACKLIST = [
    "technical analysis",
    "price target",
    "price prediction",
    "stock forecast",
    "analyst reiterate",
    "options alert",
    "options activity",
    "penny stock",
    "trading idea",
]


def filter_news(items: list[NewsItem], config: FilterConfig) -> list[NewsItem]:
    """
    三层预过滤管道

    ①关键词过滤 → ②标题相似度去重 → ③按天采样截断
    """
    blacklist = config.keyword_blacklist or DEFAULT_KEYWORD_BLACKLIST

    # Stage 1: 关键词过滤
    filtered = keyword_filter(items, blacklist)
    logger.info(f"[Filter] Keyword filter: {len(items)} -> {len(filtered)}")

    # Stage 2: 标题相似度去重
    deduped = title_dedup(filtered, config.similarity_threshold)
    logger.info(f"[Filter] Title dedup: {len(filtered)} -> {len(deduped)}")

    # Stage 3: 按天采样
    sampled = daily_sample(deduped, config.max_items)
    logger.info(f"[Filter] Daily sample: {len(deduped)} -> {len(sampled)}")

    return sampled


def keyword_filter(items: list[NewsItem], blacklist: list[str]) -> list[NewsItem]:
    """关键词黑名单过滤，去除低价值新闻"""
    if not blacklist:
        return items
    return [
        item for item in items
        if not any(kw in item.title.lower() for kw in blacklist)
    ]


def _jaccard_similarity(title_a: str, title_b: str) -> float:
    """Jaccard 词集合相似度"""
    words_a = set(title_a.lower().split())
    words_b = set(title_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def title_dedup(items: list[NewsItem], threshold: float = 0.6) -> list[NewsItem]:
    """
    标题相似度去重

    按日期分组，组内比较 Jaccard 相似度，超过阈值的保留 summary 更长的。
    """
    # 按日期分组
    groups: dict[str, list[NewsItem]] = defaultdict(list)
    for item in items:
        date_key = item.published_at[:10] if item.published_at else ''
        groups[date_key].append(item)

    result: list[NewsItem] = []
    for date_key, group in groups.items():
        kept = _dedup_group(group, threshold)
        result.extend(kept)

    return result


def _dedup_group(group: list[NewsItem], threshold: float) -> list[NewsItem]:
    """对同一天的新闻组做去重"""
    if len(group) <= 1:
        return group

    kept: list[NewsItem] = []
    for item in group:
        is_duplicate = False
        for i, existing in enumerate(kept):
            if _jaccard_similarity(item.title, existing.title) >= threshold:
                # 保留 summary 更长的；等长时保留有 raw_sentiment 的
                if len(item.summary) > len(existing.summary):
                    kept[i] = item
                elif (len(item.summary) == len(existing.summary)
                      and item.raw_sentiment is not None
                      and existing.raw_sentiment is None):
                    kept[i] = item
                is_duplicate = True
                break
        if not is_duplicate:
            kept.append(item)

    return kept


def _sort_key(item: NewsItem) -> tuple:
    """排序优先级：earnings/filing优先 > 有raw_sentiment优先 > 时间倒序"""
    category_priority = 0 if item.category in ('earnings', 'filing') else 1
    sentiment_priority = 0 if item.raw_sentiment is not None else 1
    # 时间倒序：用负号或反转字符串
    time_key = item.published_at or ''
    return (category_priority, sentiment_priority, time_key)


def daily_sample(items: list[NewsItem], max_items: int) -> list[NewsItem]:
    """
    按天均匀采样，截断到 max_items

    稀疏天的剩余配额重新分配给密集天。
    """
    if len(items) <= max_items:
        return items

    # 按日期分组
    groups: dict[str, list[NewsItem]] = defaultdict(list)
    for item in items:
        date_key = item.published_at[:10] if item.published_at else ''
        groups[date_key].append(item)

    # 每组内排序
    for date_key in groups:
        groups[date_key].sort(key=_sort_key)

    num_days = len(groups)
    base_quota = ceil(max_items / num_days)

    # 第一轮：分配基础配额，收集剩余
    result: list[NewsItem] = []
    surplus_days: list[str] = []
    remaining_budget = max_items

    for date_key, group in sorted(groups.items()):
        take = min(base_quota, len(group), remaining_budget)
        result.extend(group[:take])
        remaining_budget -= take
        if len(group) > take:
            surplus_days.append(date_key)

    # 第二轮：将剩余预算分配给密集天
    if remaining_budget > 0 and surplus_days:
        for date_key in surplus_days:
            group = groups[date_key]
            already_taken = min(base_quota, len(group))
            extra = group[already_taken:]
            take = min(len(extra), remaining_budget)
            result.extend(extra[:take])
            remaining_budget -= take
            if remaining_budget <= 0:
                break

    return result[:max_items]
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/news_sentiment/test_filter.py -v
```

Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/news_sentiment/filter.py tests/news_sentiment/test_filter.py
git commit -m "feat(news_sentiment): add three-stage news filter pipeline with tests"
```

---

### Task 3: Remove Finnhub Paid Endpoint

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/collectors/finnhub_collector.py`

**Dependencies:** None (independent)

- [ ] **Step 1: Update finnhub_collector.py**

1. Update module docstring: remove "/news-sentiment" reference
2. Delete `_fetch_sentiment_score()` method entirely (lines 56-66)
3. Update `collect()` to remove sentiment_score:

```python
    def collect(self, ticker: str, date_from: str, date_to: str) -> list[NewsItem]:
        """采集公司新闻 + 财报日历"""
        items: list[NewsItem] = []
        client = self._get_client()

        items.extend(self._fetch_company_news(client, ticker, date_from, date_to))
        items.extend(self._fetch_earnings(client, ticker, date_from, date_to))

        logger.info(f"[Finnhub] {ticker}: collected {len(items)} items")
        return items
```

4. Update `_fetch_company_news()` signature — remove `sentiment_score` parameter, set `raw_sentiment=None`:

```python
    def _fetch_company_news(
        self, client: finnhub.Client, ticker: str,
        date_from: str, date_to: str,
    ) -> list[NewsItem]:
```

And in the NewsItem constructor: `raw_sentiment=None` (replace line 94).

- [ ] **Step 2: Verify import**

```bash
uv run python -c "from BreakoutStrategy.news_sentiment.collectors.finnhub_collector import FinnhubCollector; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add BreakoutStrategy/news_sentiment/collectors/finnhub_collector.py
git commit -m "fix(news_sentiment): remove Finnhub paid sentiment endpoint (403 on free tier)"
```

---

### Task 4: Enhance Analyzer JSON Robustness

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/analyzer.py`

**Dependencies:** None (independent)

- [ ] **Step 1: Add retry prompt enhancement in `_call_glm_batch`**

In `_call_glm_batch`, modify the retry loop: when `attempt == 1` (second try), append instruction to user_message. Replace lines 132-160:

```python
    def _call_glm_batch(self, batch: list[NewsItem], ticker: str) -> list[SentimentResult]:
        """对一个批次调用 GLM，返回 SentimentResult 列表"""
        lines = [f"股票: {ticker}"]
        for i, item in enumerate(batch):
            text = f"{item.title}"
            if item.summary:
                text += f": {item.summary[:200]}"
            lines.append(f"{i}. {text}")

        base_message = "\n".join(lines)

        for attempt in range(2):
            try:
                user_message = base_message
                if attempt == 1:
                    user_message += "\n\n注意：请严格只返回JSON数组，不要包含任何解释性文字。"

                client = self._get_client()
                response = client.chat.completions.create(
                    model=self._config.model,
                    messages=[
                        {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=self._config.temperature,
                    max_tokens=4096,
                )
                content = self._extract_content(response)
                return self._parse_batch_response(content, len(batch), fallback=(attempt == 1))

            except json.JSONDecodeError:
                if attempt == 0:
                    logger.warning("[Analyzer] JSON parse failed, retrying...")
                    time.sleep(self._config.request_interval)
                    continue
                logger.error("[Analyzer] JSON parse failed after retry")
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"[Analyzer] GLM call failed: {e}, retrying...")
                    time.sleep(self._config.request_interval)
                    continue
                logger.error(f"[Analyzer] GLM call failed after retry: {e}")

        return [DEFAULT_SENTIMENT] * len(batch)
```

- [ ] **Step 2: Add fallback to `_parse_batch_response`**

Replace the method:

```python
    def _parse_batch_response(self, content: str, expected_count: int,
                              fallback: bool = False) -> list[SentimentResult]:
        """解析 GLM 批量分析的 JSON 响应"""
        text = content.strip()
        if text.startswith('```'):
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])

        try:
            results_raw = json.loads(text)
        except json.JSONDecodeError:
            if not fallback:
                raise
            # 兜底：用 raw_decode 逐个提取 JSON 对象
            results_raw = self._extract_json_objects(text)
            if not results_raw:
                return [DEFAULT_SENTIMENT] * expected_count

        results_map: dict[int, SentimentResult] = {}
        for item in results_raw:
            if not isinstance(item, dict):
                continue
            idx = item.get('index', -1)
            results_map[idx] = SentimentResult(
                sentiment=item.get('sentiment', 'neutral'),
                confidence=float(item.get('confidence', 0.0)),
                reasoning=item.get('reasoning', ''),
            )

        return [results_map.get(i, DEFAULT_SENTIMENT) for i in range(expected_count)]

    @staticmethod
    def _extract_json_objects(text: str) -> list[dict]:
        """使用 JSONDecoder.raw_decode 从文本中逐个提取 JSON 对象"""
        decoder = json.JSONDecoder()
        objects = []
        idx = 0
        while idx < len(text):
            # 跳到下一个 { 或 [
            while idx < len(text) and text[idx] not in ('{', '['):
                idx += 1
            if idx >= len(text):
                break
            try:
                obj, end_idx = decoder.raw_decode(text, idx)
                if isinstance(obj, dict):
                    objects.append(obj)
                elif isinstance(obj, list):
                    objects.extend(item for item in obj if isinstance(item, dict))
                idx = end_idx
            except json.JSONDecodeError:
                idx += 1
        return objects
```

- [ ] **Step 3: Verify import**

```bash
uv run python -c "from BreakoutStrategy.news_sentiment.analyzer import SentimentAnalyzer; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add BreakoutStrategy/news_sentiment/analyzer.py
git commit -m "fix(news_sentiment): enhance JSON parse robustness with retry prompt and fallback extraction"
```

---

### Task 5: Integrate Filter into API Pipeline

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/api.py`

**Dependencies:** Tasks 1, 2

- [ ] **Step 1: Update api.py**

Add import at top:

```python
from BreakoutStrategy.news_sentiment.filter import filter_news
```

Insert filter step between dedup and analyzer (after line 96, before line 98):

```python
    # 3.5 预过滤
    filtered_items = filter_news(unique_items, config.filter)
    logger.info(f"Filtered: {len(unique_items)} -> {len(filtered_items)} items")
```

Change the analyzer call to use `filtered_items`:

```python
    # 4. 情感分析
    try:
        analyzer = SentimentAnalyzer(config.analyzer)
        analyzed_items, summary = analyzer.analyze(filtered_items, ticker, date_from, date_to)
```

- [ ] **Step 2: Run all tests**

```bash
uv run pytest tests/news_sentiment/ -v
```

Expected: All tests PASS (filter + models + reporter + dedup)

- [ ] **Step 3: Commit**

```bash
git add BreakoutStrategy/news_sentiment/api.py
git commit -m "feat(news_sentiment): integrate filter pipeline into analyze() flow"
```

---

### Task 6: End-to-End Verification

**Dependencies:** Tasks 1-5

- [ ] **Step 1: Run E2E with EDGAR + GLM**

```bash
ZHIPUAI_API_KEY="your_key" uv run -m BreakoutStrategy.news_sentiment
```

Verify logs show filter pipeline running and reduced GLM calls.

- [ ] **Step 2: Run E2E with Finnhub (if key available)**

```bash
FINNHUB_API_KEY="your_key" ZHIPUAI_API_KEY="your_key" uv run -m BreakoutStrategy.news_sentiment
```

Verify: no 403 warning, filter reduces 248 → ~20 items, 2 GLM calls, completes in 3-5 minutes.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(news_sentiment): complete optimization - filter pipeline, batch_size 20, JSON robustness"
```
