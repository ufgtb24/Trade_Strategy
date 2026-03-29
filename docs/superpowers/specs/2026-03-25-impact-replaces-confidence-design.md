# Design: Impact 替代 Confidence（Phase 1+2）

## Context

当前 LLM 对每条新闻返回 `(sentiment, confidence, reasoning)`，其中 confidence 是 LLM 的元认知自评（"我多确定"）。分析表明 impact（"新闻对股价影响多大"）是更本质的维度：它是一阶事件属性而非二阶元认知，可回溯验证，且 LLM 的领域知识回忆能力优于元认知自省。

本次改动将 LLM 输出从 confidence 切换为离散 impact 等级，映射为数值后替代 confidence 参与聚合公式。聚合公式结构不变。

## 设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 兼容策略 | 干净替换，移除 SentimentResult.confidence | 不保留臃肿的双字段，旧缓存通过 schema 迁移清空 |
| 失败标记 | `impact=""`, `impact_value=0.0` | 语义明确：空=失败，negligible=真正无影响 |
| SummaryResult.confidence | 保留名称 | 聚合后的 certainty×sufficiency 语义是"确定性"，名称仍准确 |
| Impact 等级 | 5 档离散分类 | 分类任务 LLM 一致性 >> 连续值回归 |
| 无效 impact 字符串 | 视为分析失败 | LLM 返回无法识别的 impact 值时，`impact=""`, `impact_value=0.0` |

## Impact 映射表

```python
IMPACT_MAP: dict[str, float] = {
    "negligible": 0.05,   # <0.5% 股价影响
    "low":        0.20,   # 0.5-2%
    "medium":     0.50,   # 2-5%
    "high":       0.80,   # 5-15%
    "extreme":    1.00,   # >15%
}
```

## 文件改动

### 1. `BreakoutStrategy/news_sentiment/models.py`

**SentimentResult 重构**：

```python
IMPACT_MAP: dict[str, float] = {
    "negligible": 0.05, "low": 0.20,
    "medium": 0.50, "high": 0.80, "extreme": 1.00,
}

@dataclass
class SentimentResult:
    """单条新闻的情感+影响力分析结果"""
    sentiment: str       # positive/negative/neutral
    impact: str          # negligible/low/medium/high/extreme, ""=分析失败
    impact_value: float  # IMPACT_MAP 映射值, 0.0=分析失败
    reasoning: str
```

- 移除 `confidence: float` 字段
- `SummaryResult` 不变（`confidence` 保留，语义=聚合后确定性）

### 2. `BreakoutStrategy/news_sentiment/backends/_llm_utils.py`

**导入 IMPACT_MAP**：

```python
from BreakoutStrategy.news_sentiment.models import NewsItem, SentimentResult, IMPACT_MAP
```

**SYSTEM_PROMPT**：

```python
SYSTEM_PROMPT = (
    "你是一个金融新闻影响力分析专家。评估以下新闻对该股票价格的潜在影响。\n"
    '仅返回JSON：{"sentiment": "positive|negative|neutral", '
    '"impact": "negligible|low|medium|high|extreme", "reasoning": "一句话理由"}\n'
    "impact等级: negligible(<0.5%), low(0.5-2%), medium(2-5%), high(5-15%), extreme(>15%)"
)
```

**DEFAULT_SENTIMENT**：

```python
DEFAULT_SENTIMENT = SentimentResult(
    sentiment="neutral", impact="", impact_value=0.0, reasoning="Analysis failed",
)
```

**_obj_to_result**：

```python
def _obj_to_result(obj: dict) -> SentimentResult:
    impact_str = obj.get('impact', '')
    impact_val = IMPACT_MAP.get(impact_str, 0.0)
    return SentimentResult(
        sentiment=obj.get('sentiment', 'neutral'),
        impact=impact_str if impact_str in IMPACT_MAP else '',
        impact_value=impact_val,
        reasoning=obj.get('reasoning', ''),
    )
```

### 3. `BreakoutStrategy/news_sentiment/backends/finbert_roberta_backend.py`

FinBERT+RoBERTa 后端不使用 LLM，直接通过 soft-vote 产生概率。将 soft-vote probability 映射为 impact 等级：

```python
def _prob_to_impact(prob: float) -> tuple[str, float]:
    """将 soft-vote 概率映射为 impact 等级"""
    if prob >= 0.85:
        return "high", 0.80
    elif prob >= 0.65:
        return "medium", 0.50
    elif prob >= 0.45:
        return "low", 0.20
    else:
        return "negligible", 0.05
```

构造 SentimentResult 时使用映射后的 impact：

```python
impact_label, impact_val = _prob_to_impact(confidence)
results.append(SentimentResult(
    sentiment=sentiment,
    impact=impact_label,
    impact_value=impact_val,
    reasoning=f"FinBERT={fb_scores}, RoBERTa={rb_scores}",
))
```

### 4. `BreakoutStrategy/news_sentiment/analyzer.py`

**`analyze` 方法**（缓存写入守卫，约 L133）：

```python
# 旧: if sent.confidence > 0:
# 新:
if sent.impact_value > 0:
```

**`_summarize` 方法** — 替换加权因子：

```python
# 旧: s, c = item.sentiment.sentiment, item.sentiment.confidence
# 新:
s = item.sentiment.sentiment
iv = item.sentiment.impact_value

# 旧: if c == 0.0: fail_count += 1
# 新:
if iv == 0.0:
    fail_count += 1
    continue
```

- `pos_confs` / `neg_confs` 重命名为 `pos_impacts` / `neg_impacts`
- `pos_tw` / `neg_tw` 不变
- 日志输出中 `conf` → `impact`
- docstring 中 "confidence=0.0 视为无效" 更新为 "impact_value=0.0 视为无效"

**`_generate_reasoning` 方法** — 替换 confidence 引用：

```python
# 旧: valid_items = [a for a in analyzed_items if a.sentiment.confidence > 0]
# 新:
valid_items = [a for a in analyzed_items if a.sentiment.impact_value > 0]

# 旧: top = sorted(valid_items, key=lambda a: a.sentiment.confidence, reverse=True)[:3]
# 新:
top = sorted(valid_items, key=lambda a: a.sentiment.impact_value, reverse=True)[:3]

# 旧: f"[{a.sentiment.sentiment}|{a.sentiment.confidence:.1f}] {a.news.title[:60]}"
# 新:
f"[{a.sentiment.sentiment}|{a.sentiment.impact}] {a.news.title[:60]}"
```

公式结构（rho, certainty, sufficiency, opp_penalty, f_fail）完全不变。

### 5. `BreakoutStrategy/news_sentiment/__main__.py`

SummaryResult.confidence 保留，`Internals:` 行不变。

**Top 5 排序和显示**：

```python
# 旧: a.sentiment.confidence * _time_weight(a)
# 新:
a.sentiment.impact_value * _time_weight(a)

# 旧: f"[{item.sentiment.sentiment}|{item.sentiment.confidence:.1f}|tw={tw:.2f}]"
# 新:
f"[{item.sentiment.sentiment}|{item.sentiment.impact}|tw={tw:.2f}]"
```

### 6. `BreakoutStrategy/news_sentiment/cache.py`

**Schema 迁移**：旧 `sentiments` 表有 `confidence REAL` 列，无 `impact`/`impact_value` 列。直接读写会 crash。

策略：在 `_init_tables` 中检测旧 schema 并迁移：

```python
def _init_tables(self):
    c = self._conn.cursor()
    # 检测旧 schema：sentiments 表有 confidence 列但无 impact 列
    c.execute("PRAGMA table_info(sentiments)")
    cols = {row[1] for row in c.fetchall()}
    if 'confidence' in cols and 'impact' not in cols:
        c.execute("DROP TABLE sentiments")
        self._conn.commit()

    c.executescript("""
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
        ...  -- news 和 coverage 表不变
    """)
```

**put_sentiment**：

```python
c.execute(
    "INSERT OR REPLACE INTO sentiments "
    "(fingerprint, backend, model, sentiment, impact, impact_value, reasoning) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)",
    (fingerprint, backend, model,
     result.sentiment, result.impact, result.impact_value, result.reasoning),
)
```

**get_sentiment**：

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

### 7. 测试更新

所有构造 `SentimentResult(sentiment=..., confidence=..., reasoning=...)` 的测试改为新签名 `SentimentResult(sentiment=..., impact=..., impact_value=..., reasoning=...)`。

涉及文件（按影响分类）：

**构造/访问 SentimentResult 的测试**：
- `tests/news_sentiment/test_time_decay.py`
- `tests/news_sentiment/test_analyzer.py`
- `tests/news_sentiment/test_cache.py`
- `tests/news_sentiment/test_llm_utils.py`
- `tests/news_sentiment/test_models.py`
- `tests/news_sentiment/test_reporter.py`
- `tests/news_sentiment/test_deepseek_backend.py`
- `tests/news_sentiment/test_glm_backend.py`
- `tests/news_sentiment/test_finbert_roberta_backend.py`

**不涉及 SentimentResult 的测试（不受影响）**：
- `tests/news_sentiment/test_config.py`
- `tests/news_sentiment/test_filter.py`

## 不变的部分

- 聚合公式结构（rho → certainty × sufficiency → sentiment_score）
- 聚合参数（`_K`, `_BETA`, `_CAP` 等，留给 Phase 3 校准）
- `SummaryResult` 的 `confidence` 字段名和 `sentiment_score` 计算
- `filter.py`（不涉及 SentimentResult）
- `config.py`（无新配置项）
- `api.py`（不直接构造 SentimentResult，SummaryResult.confidence 保留）
- 新闻采集和过滤管道

## 验证

```bash
uv run pytest tests/news_sentiment/ -v
```

所有测试通过即可。
