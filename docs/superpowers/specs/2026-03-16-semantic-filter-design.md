# 语义过滤替换设计

## 概述

用 fastembed (bge-small-en-v1.5) + numpy cosine similarity 替换 filter.py 中的关键词过滤和 Jaccard 去重，实现语义过滤和语义去重。daily_sample 不变。

## 架构

```
248条新闻
  ↓ embed_texts() — 一次性 embedding (~3s)
  ↓
①语义过滤: 与低价值模板向量比较，max cosine > 0.5 则过滤
  ↓
②语义去重: 同日期内 cosine > 0.85 视为同事件，保留 summary 更长的
  ↓
③daily_sample (不变): 按天均匀采样到 max_items
  ↓
~20条高质量新闻 → GLM 分析
```

## 新增文件

### embedding.py

```python
# BreakoutStrategy/news_sentiment/embedding.py
```

- 使用 `fastembed` 的 `TextEmbedding` 类加载 `BAAI/bge-small-en-v1.5`（130MB, ONNX, CPU）
- 单例模式管理模型实例，避免重复加载
- `embed_texts(texts: list[str]) -> np.ndarray` — 批量 embedding
- `cosine_similarity_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray` — numpy 矩阵运算

### 低价值新闻模板

预定义在 filter.py 中：

```python
LOW_VALUE_TEMPLATES = [
    "top stocks to buy for long term investment",
    "best growth stocks to buy and hold forever",
    "you won't believe how much money this stock made",
    "should you buy this stock right now before it's too late",
    "this dividend stock pays monthly income to investors",
    "stock price prediction and forecast for next year",
    "technical analysis chart pattern shows bullish signal",
    "options trading alert unusual activity detected",
    "penny stock could be the next big winner",
    "millionaire maker one stock that could change your life",
]
```

## 重写 filter.py

### filter_news() 新流程

```python
def filter_news(items, config):
    # 1. 一次性 embedding 所有标题
    titles = [item.title for item in items]
    embeddings = embed_texts(titles)

    # 2. 语义过滤（替换 keyword_filter）
    filtered, filtered_embeddings = semantic_filter(items, embeddings, config.semantic_filter_threshold)

    # 3. 语义去重（替换 title_dedup）
    deduped = semantic_dedup(filtered, filtered_embeddings, config.semantic_dedup_threshold)

    # 4. 按天采样（不变）
    return daily_sample(deduped, config.max_items)
```

### semantic_filter()

- 将 LOW_VALUE_TEMPLATES embedding（可缓存为模块级变量）
- 计算每条新闻与所有模板的 cosine similarity
- 每条新闻取与模板的最大相似度，> threshold (0.5) 则过滤

### semantic_dedup()

- 计算 filtered_embeddings 的全量 cosine similarity 矩阵
- 按日期分组，组内相似度 > threshold (0.85) 的合并
- 合并策略：保留 summary 更长的条目

### daily_sample()

不变，从 filter.py 现有代码保留。

## 配置变更

### FilterConfig

```python
@dataclass
class FilterConfig:
    max_items: int                    # 20
    semantic_filter_threshold: float  # 0.5
    semantic_dedup_threshold: float   # 0.85
```

移除 `keyword_blacklist` 和 `similarity_threshold`。

### configs/news_sentiment.yaml

```yaml
filter:
  max_items: 20
  semantic_filter_threshold: 0.5
  semantic_dedup_threshold: 0.85
```

## 依赖

```bash
uv add fastembed
```

首次运行自动下载 bge-small-en-v1.5 模型到 `~/.cache/fastembed`（~130MB）。

## 文件变更清单

| Action | Path | 变更 |
|---|---|---|
| Create | `BreakoutStrategy/news_sentiment/embedding.py` | 模型管理 + cosine similarity |
| Rewrite | `BreakoutStrategy/news_sentiment/filter.py` | 语义过滤 + 语义去重（保留 daily_sample） |
| Modify | `BreakoutStrategy/news_sentiment/config.py` | FilterConfig 字段更新 |
| Modify | `configs/news_sentiment.yaml` | 新阈值配置 |
| Rewrite | `tests/news_sentiment/test_filter.py` | 语义过滤/去重测试 |
