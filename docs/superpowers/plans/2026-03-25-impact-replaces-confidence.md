# Impact 替代 Confidence 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 LLM 输出从 confidence(元认知自评) 切换为 impact(离散影响等级)，映射为数值后替代 confidence 参与聚合。

**Architecture:** SentimentResult 移除 confidence，新增 impact(str) + impact_value(float)。IMPACT_MAP 定义在 models.py。聚合公式结构不变，仅替换加权因子。缓存 schema 迁移（DROP 旧 sentiments 表）。

**Tech Stack:** Python dataclasses, SQLite, DeepSeek/GLM LLM backends

**Spec:** `docs/superpowers/specs/2026-03-25-impact-replaces-confidence-design.md`

**Key constraint:** 每个 commit 后全套测试必须绿色。因此 Task 1 同时更新 models.py 和所有测试文件中的 SentimentResult 构造。

---

### Task 1: 数据模型 + 全测试文件 SentimentResult 构造更新

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/models.py`
- Modify: ALL test files that construct `SentimentResult`

- [ ] **Step 1: 修改 models.py — 新增 IMPACT_MAP，重构 SentimentResult**

```python
IMPACT_MAP: dict[str, float] = {
    "negligible": 0.05,
    "low": 0.20,
    "medium": 0.50,
    "high": 0.80,
    "extreme": 1.00,
}

@dataclass
class SentimentResult:
    """单条新闻的情感+影响力分析结果"""
    sentiment: str       # positive/negative/neutral
    impact: str          # negligible/low/medium/high/extreme, ""=分析失败
    impact_value: float  # IMPACT_MAP 映射值, 0.0=分析失败
    reasoning: str
```

- [ ] **Step 2: 更新 test_models.py**

```python
# test_analysis_report_asdict 中:
sentiment = SentimentResult(
    sentiment="positive", impact="high", impact_value=0.80, reasoning="Good earnings",
)
```

- [ ] **Step 3: 更新 test_llm_utils.py — 所有 SentimentResult 构造和断言**

```python
# test_parse_single_response_valid_json:
content = '{"sentiment": "positive", "impact": "high", "reasoning": "Good news"}'
result = parse_single_response(content)
assert result.sentiment == "positive"
assert result.impact == "high"
assert result.impact_value == 0.80

# test_parse_single_response_markdown_wrapped:
content = '```json\n{"sentiment": "negative", "impact": "medium", "reasoning": "Bad"}\n```'
result = parse_single_response(content)
assert result.sentiment == "negative"
assert result.impact == "medium"
assert result.impact_value == 0.50

# test_parse_single_response_invalid_returns_default:
assert result.impact == ""
assert result.impact_value == 0.0

# test_parse_single_response_embedded_json:
content = 'Analysis: {"sentiment": "neutral", "impact": "low", "reasoning": "Mixed"} done.'
assert result.impact == "low"
assert result.impact_value == 0.20

# 新增 test_parse_single_response_invalid_impact_string:
def test_parse_single_response_invalid_impact_string():
    content = '{"sentiment": "positive", "impact": "very_high", "reasoning": "Test"}'
    result = parse_single_response(content)
    assert result.impact == ""
    assert result.impact_value == 0.0

# test_default_sentiment:
assert DEFAULT_SENTIMENT.impact == ""
assert DEFAULT_SENTIMENT.impact_value == 0.0

# test_system_prompt_contains_json_format:
assert "impact" in SYSTEM_PROMPT
assert "confidence" not in SYSTEM_PROMPT
```

- [ ] **Step 4: 更新 test_analyzer.py — SentimentResult 构造**

```python
# test_backend_dispatch_deepseek:
mock_backend.analyze_all.return_value = [
    SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good")
]
```

- [ ] **Step 5: 更新 test_time_decay.py — 所有 SentimentResult 构造**

所有 `SentimentResult(sentiment="negative", confidence=0.8, reasoning="Bad")` 改为：
```python
SentimentResult(sentiment="negative", impact="high", impact_value=0.80, reasoning="Bad")
```

所有 `SentimentResult(sentiment="positive", confidence=0.8, reasoning="Good")` 改为：
```python
SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good")
```

- [ ] **Step 6: 更新 test_cache.py — SentimentResult 构造和断言**

```python
# test_cache_sentiment_put_and_get:
sent = SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good")
# 断言:
assert result.impact == "high"
assert result.impact_value == 0.80

# test_cache_sentiment_miss_different_model:
sent = SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good")

# test_analyzer_cache_hit_skips_backend:
sent = SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good")

# test_analyzer_cache_miss_calls_backend_and_caches:
sent = SentimentResult(sentiment="negative", impact="medium", impact_value=0.50, reasoning="Bad")
```

- [ ] **Step 7: 更新 test_deepseek_backend.py — mock 响应 JSON 和断言**

```python
# test_analyze_all_single_item:
client.chat.completions.create.return_value = _mock_response(
    '{"sentiment": "positive", "impact": "high", "reasoning": "Strong earnings"}'
)
assert results[0].sentiment == "positive"
assert results[0].impact == "high"
assert results[0].impact_value == 0.80

# test_analyze_all_concurrent:
client.chat.completions.create.return_value = _mock_response(
    '{"sentiment": "neutral", "impact": "low", "reasoning": "Mixed"}'
)

# test_analyze_all_api_failure_returns_default:
assert results[0].impact == ""
assert results[0].impact_value == 0.0
```

- [ ] **Step 8: 更新 test_glm_backend.py — mock 响应 JSON 和断言**

```python
# test_analyze_all_basic:
msg.content = '{"sentiment": "negative", "impact": "high", "reasoning": "Delays"}'

# test_thinking_mode_extracts_from_reasoning_content:
msg.reasoning_content = '分析过程...\n```json\n{"sentiment": "positive", "impact": "medium", "reasoning": "Good"}\n```'

# test_api_failure_returns_default:
assert results[0].impact == ""
assert results[0].impact_value == 0.0
```

- [ ] **Step 9: 更新 test_finbert_roberta_backend.py — 断言**

所有 `.confidence` 断言改为 `.impact` / `.impact_value`。

- [ ] **Step 10: 更新 test_reporter.py — SentimentResult 构造 + dict-key 断言**

```python
# test_report_serialization:
SentimentResult(sentiment="positive", impact="high", impact_value=0.80, reasoning="Good earnings")

# test_save_report_creates_file (约 L66):
# 旧: assert loaded['items'][0]['sentiment']['confidence'] == 0.9
# 新:
assert loaded['items'][0]['sentiment']['impact'] == "high"
assert loaded['items'][0]['sentiment']['impact_value'] == 0.80
```

- [ ] **Step 11: 运行全套测试确认全部失败（因生产代码未改）**

Run: `uv run pytest tests/news_sentiment/ -v 2>&1 | tail -5`
Expected: 多个 FAIL（预期行为）

- [ ] **Step 12: Commit**

```bash
git add BreakoutStrategy/news_sentiment/models.py tests/news_sentiment/
git commit -m "refactor: IMPACT_MAP + SentimentResult(impact, impact_value) + all tests updated"
```

---

### Task 2: LLM 工具层 — Prompt + 解析

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/backends/_llm_utils.py`

- [ ] **Step 1: 修改 _llm_utils.py**

```python
from BreakoutStrategy.news_sentiment.models import NewsItem, SentimentResult, IMPACT_MAP

SYSTEM_PROMPT = (
    "你是一个金融新闻影响力分析专家。评估以下新闻对该股票价格的潜在影响。\n"
    '仅返回JSON：{"sentiment": "positive|negative|neutral", '
    '"impact": "negligible|low|medium|high|extreme", "reasoning": "一句话理由"}\n'
    "impact等级: negligible(<0.5%), low(0.5-2%), medium(2-5%), high(5-15%), extreme(>15%)"
)

DEFAULT_SENTIMENT = SentimentResult(
    sentiment="neutral", impact="", impact_value=0.0, reasoning="Analysis failed",
)

def _obj_to_result(obj: dict) -> SentimentResult:
    """将 JSON 对象转为 SentimentResult"""
    impact_str = obj.get('impact', '')
    impact_val = IMPACT_MAP.get(impact_str, 0.0)
    return SentimentResult(
        sentiment=obj.get('sentiment', 'neutral'),
        impact=impact_str if impact_str in IMPACT_MAP else '',
        impact_value=impact_val,
        reasoning=obj.get('reasoning', ''),
    )
```

- [ ] **Step 2: 运行 LLM 工具 + backend 测试**

Run: `uv run pytest tests/news_sentiment/test_llm_utils.py tests/news_sentiment/test_deepseek_backend.py tests/news_sentiment/test_glm_backend.py -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add BreakoutStrategy/news_sentiment/backends/_llm_utils.py
git commit -m "refactor: LLM prompt and parsing switch to impact levels"
```

---

### Task 3: FinBERT+RoBERTa 后端适配

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/backends/finbert_roberta_backend.py`

- [ ] **Step 1: 新增 _prob_to_impact 映射函数，修改 analyze_all**

```python
from BreakoutStrategy.news_sentiment.models import IMPACT_MAP

def _prob_to_impact(prob: float) -> tuple[str, float]:
    """将 soft-vote 概率映射为 impact 等级"""
    if prob >= 0.85:
        return "high", IMPACT_MAP["high"]
    elif prob >= 0.65:
        return "medium", IMPACT_MAP["medium"]
    elif prob >= 0.45:
        return "low", IMPACT_MAP["low"]
    else:
        return "negligible", IMPACT_MAP["negligible"]
```

`analyze_all` 中：
```python
sentiment, confidence = _soft_vote(fb_scores, rb_scores)
impact_label, impact_val = _prob_to_impact(confidence)
results.append(SentimentResult(
    sentiment=sentiment,
    impact=impact_label,
    impact_value=impact_val,
    reasoning=f"FinBERT={fb_scores}, RoBERTa={rb_scores}",
))
# 失败分支:
results.append(SentimentResult(
    sentiment="neutral", impact="", impact_value=0.0, reasoning=f"Error: {e}",
))
```

- [ ] **Step 2: 运行测试**

Run: `uv run pytest tests/news_sentiment/test_finbert_roberta_backend.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add BreakoutStrategy/news_sentiment/backends/finbert_roberta_backend.py
git commit -m "refactor: FinBERT+RoBERTa backend outputs impact levels"
```

---

### Task 4: 缓存 schema 迁移

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/cache.py`

- [ ] **Step 1: 修改 cache.py**

`_init_tables` 新增迁移检测：

```python
def _init_tables(self):
    c = self._conn.cursor()
    c.execute("PRAGMA table_info(sentiments)")
    cols = {row[1] for row in c.fetchall()}
    if 'confidence' in cols and 'impact' not in cols:
        c.execute("DROP TABLE sentiments")
        self._conn.commit()
```

sentiments 表 schema：

```sql
CREATE TABLE IF NOT EXISTS sentiments (
    fingerprint TEXT NOT NULL,
    backend TEXT NOT NULL,
    model TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    impact TEXT NOT NULL DEFAULT '',
    impact_value REAL NOT NULL DEFAULT 0.0,
    reasoning TEXT NOT NULL,
    created_at TEXT DEFAULT (date('now')),
    PRIMARY KEY (fingerprint, backend, model)
);
```

`put_sentiment`:
```python
c.execute(
    "INSERT OR REPLACE INTO sentiments "
    "(fingerprint, backend, model, sentiment, impact, impact_value, reasoning) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)",
    (fingerprint, backend, model,
     result.sentiment, result.impact, result.impact_value, result.reasoning),
)
```

`get_sentiment`:
```python
c.execute(
    "SELECT sentiment, impact, impact_value, reasoning FROM sentiments "
    "WHERE fingerprint=? AND backend=? AND model=?",
    (fingerprint, backend, model),
)
row = c.fetchone()
if row is None:
    return None
return SentimentResult(sentiment=row[0], impact=row[1], impact_value=row[2], reasoning=row[3])
```

- [ ] **Step 2: 运行缓存单元测试（不含 analyzer 集成测试）**

Run: `uv run pytest tests/news_sentiment/test_cache.py -v -k "not analyzer"`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add BreakoutStrategy/news_sentiment/cache.py
git commit -m "refactor: cache schema migrates from confidence to impact"
```

---

### Task 5: 聚合公式适配 (analyzer.py)

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/analyzer.py`

- [ ] **Step 1: 修改 analyzer.py**

**`analyze` 方法** — 缓存写入守卫（约 L133）:
```python
if sent.impact_value > 0:
```

**`_summarize` 方法** — 变量替换:

```python
pos_impacts: list[float] = []
neg_impacts: list[float] = []
# ...
for i, item in enumerate(analyzed_items):
    s = item.sentiment.sentiment
    iv = item.sentiment.impact_value
    tw = item_tw[i]
    if iv == 0.0:
        fail_count += 1
        continue
    if s == 'positive':
        pos_impacts.append(iv)
        pos_tw.append(tw)
    elif s == 'negative':
        neg_impacts.append(iv)
        neg_tw.append(tw)
    else:
        neu_valid += 1
        neu_tw_sum += tw

n_p, n_n, n_u = len(pos_impacts), len(neg_impacts), neu_valid
w_p = sum(c * t for c, t in zip(pos_impacts, pos_tw))
w_n = sum(c * t for c, t in zip(neg_impacts, neg_tw))
```

docstring: "confidence=0.0 视为无效" → "impact_value=0.0 视为无效"

**`_generate_reasoning` 方法**:
```python
valid_items = [a for a in analyzed_items if a.sentiment.impact_value > 0]
top = sorted(valid_items, key=lambda a: a.sentiment.impact_value, reverse=True)[:3]
headlines = "; ".join(
    f"[{a.sentiment.sentiment}|{a.sentiment.impact}] {a.news.title[:60]}"
    for a in top
)
```

- [ ] **Step 2: 运行全套测试（含 analyzer + cache 集成测试）**

Run: `uv run pytest tests/news_sentiment/test_analyzer.py tests/news_sentiment/test_time_decay.py tests/news_sentiment/test_cache.py -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add BreakoutStrategy/news_sentiment/analyzer.py
git commit -m "refactor: aggregation uses impact_value instead of confidence"
```

---

### Task 6: 输出层 + 全局验证

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/__main__.py`

- [ ] **Step 1: 修改 __main__.py**

Top 5 排序和显示:
```python
ranked = sorted(
    report.items,
    key=lambda a: (
        a.sentiment.sentiment != 'neutral',
        a.sentiment.impact_value * _time_weight(a),
    ),
    reverse=True,
)
# ...
print(f"  [{item.sentiment.sentiment}|{item.sentiment.impact}|tw={tw:.2f}] "
      f"{item.news.title[:60]}")
```

注释更新: "ordered by confidence" → "ordered by impact_value"

- [ ] **Step 2: 搜索 SentimentResult.confidence 残留**

```bash
grep -rn '\.confidence' BreakoutStrategy/news_sentiment/ tests/news_sentiment/ | grep -v SummaryResult | grep -v '#'
```

Expected: 无匹配

- [ ] **Step 3: 运行全套测试**

Run: `uv run pytest tests/news_sentiment/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add BreakoutStrategy/news_sentiment/__main__.py
git commit -m "refactor: output displays impact instead of confidence"
```
