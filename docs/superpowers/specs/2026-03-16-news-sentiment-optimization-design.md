# news_sentiment 模块优化设计

## 概述

对已实现的 news_sentiment 模块进行性能优化，解决 AAPL 15天248条新闻导致 GLM 调用 51 次、耗时 50-100 分钟的问题。优化后预期 2 次 GLM 调用、3-5 分钟完成。

## 问题诊断

1. **Finnhub 403**：`/news-sentiment` 是付费端点，免费 tier 返回 403，每次产生无意义的 WARNING
2. **新闻量过大**：248 条未过滤新闻全量送 GLM，batch_size=5 导致 50 次批次调用
3. **大量重复报道**：同一事件的不同媒体文章 URL 不同，精确去重无效
4. **JSON 解析脆弱**：GLM 思考模式输出格式不稳定，51 次调用中必然遇到解析失败

## 优化方案

### 1. 新增预过滤模块（filter.py）

新建 `BreakoutStrategy/news_sentiment/filter.py`，实现三层过滤管道：

```
filter_news(items, config) -> list[NewsItem]
  ├─ ①keyword_filter(items)                    — 关键词黑名单去噪，O(n)
  ├─ ②title_dedup(items, threshold=0.6)        — Jaccard 标题相似度去重，O(n²)
  └─ ③daily_sample(items, max_items=20)         — 按天均匀采样截断
```

全部为本地纯 Python 计算，零 API 调用，毫秒级完成。

#### 关键词过滤

黑名单关键词列表（可配置），过滤标题中包含以下低价值模式的新闻：

```python
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
```

匹配方式：`any(kw in title.lower() for kw in blacklist)`，宽松策略，只去明显噪音。

**配置语义**：YAML 中 `keyword_blacklist` 字段不存在或为空列表 `[]` 时使用 `DEFAULT_KEYWORD_BLACKLIST`；非空列表则完全覆盖默认值。`config.py` 中使用 `blacklist = cfg_list or DEFAULT_KEYWORD_BLACKLIST` 实现此逻辑。

#### 标题相似度去重

- 算法：Jaccard 词集合相似度 = |A ∩ B| / |A ∪ B|
- 阈值：0.6（可配置），同日期内超过阈值的标题视为同一事件
- 合并策略：保留 summary 更长的条目（信息更丰富），若等长则保留有 raw_sentiment 的
- 分组：按 `published_at[:10]`（日期）分组后在组内去重，避免跨日期误合并
- 纯 Python 实现，不引入新依赖

#### 按天采样

- 按 `published_at[:10]` 分组
- 每天初始配额 = `ceil(max_items / 天数)`
- 稀疏天（实际新闻 < 配额）的剩余配额重新分配给密集天
- 最终结果截断到 `max_items`（结果为"至多 max_items 条"，数据不足时可以更少）
- 组内排序优先级：category 为 earnings/filing 优先 > 有 raw_sentiment 的优先 > 按时间倒序

#### 过滤顺序理由

关键词过滤(O(n)) → 标题去重(O(n²)) → 采样截断。将廉价+高选择性的操作放前面，缩小后续 O(n²) 去重的输入规模。

### 2. 修改 Finnhub Collector

删除 `_fetch_sentiment_score()` 方法及其调用。`collect()` 直接调用 `_fetch_company_news()` 和 `_fetch_earnings()`。`_fetch_company_news()` 的 `sentiment_score` 参数移除，`raw_sentiment` 统一设为 `None`。

消除每次运行的 403 WARNING 日志噪音和无意义的网络请求。

### 3. 修改 api.py 流程

在现有 `deduplicate()` 之后、`analyzer.analyze()` 之前，插入 `filter_news()` 调用：

```
采集 → URL精确去重(现有) → 预过滤(新增) → 情感分析 → 报告
```

增加日志：`logger.info(f"Filtered: {len(unique_items)} -> {len(filtered_items)} items")`

过滤后数量通过日志记录，不修改 `source_stats`（保持纯采集器维度语义）。

### 4. 增大 batch_size

将 `analyzer` 配置中的 `batch_size` 默认值从 5 改为 20：YAML 文件和 `config.py` 中 `analyzer_cfg.get('batch_size', 5)` 的硬编码默认值都需更新。过滤到 20 条后只需 1 次批次调用 + 1 次汇总 = 2 次 GLM 调用。

### 5. 增强 JSON 解析鲁棒性

#### _call_glm_batch 改进

重试时在 user_message 末尾追加指令：`"\n\n注意：请严格只返回JSON数组，不要包含任何解释性文字。"`

#### _parse_batch_response 兜底

兜底逻辑在**第二次尝试**（retry 后）的 `_parse_batch_response` 内触发，不影响首次失败的 retry 路径：

- 首次 JSON 解析失败 → 触发 `_call_glm_batch` 的 `except json.JSONDecodeError` → retry 整个 GLM 调用
- 第二次 JSON 解析失败 → `_parse_batch_response` 内尝试兜底提取
- 兜底方式：使用 `json.JSONDecoder().raw_decode()` 从文本中逐个提取 JSON 对象（正确处理嵌套大括号），拼装为结果列表
- 兜底也失败 → 返回 `[DEFAULT_SENTIMENT] * expected_count`

### 6. 配置变更

`configs/news_sentiment.yaml` 新增 `filter` 段：

```yaml
filter:
  max_items: 20
  similarity_threshold: 0.6
  keyword_blacklist: []   # 留空使用默认黑名单，非空则覆盖

analyzer:
  batch_size: 20          # 从 5 改为 20
```

新增 `FilterConfig` dataclass，在 `config.py` 中加载。

### 7. 预期效果

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 过滤后新闻数 | 251（无过滤） | ~20 |
| GLM 调用次数 | 51 | 2 |
| 总耗时 | 50-100 分钟 | 3-5 分钟 |
| 解析成功率 | ~90-95% | ~99%（调用少，出错概率低） |
| 403 日志噪音 | 每次 1 条 | 无 |

## 修改文件清单

| Action | Path | 变更 |
|---|---|---|
| Create | `BreakoutStrategy/news_sentiment/filter.py` | 三层过滤管道 |
| Modify | `BreakoutStrategy/news_sentiment/collectors/finnhub_collector.py` | 移除付费端点调用 |
| Modify | `BreakoutStrategy/news_sentiment/api.py` | 插入过滤步骤 |
| Modify | `BreakoutStrategy/news_sentiment/analyzer.py` | JSON 解析增强 + batch_size 默认值 |
| Modify | `BreakoutStrategy/news_sentiment/config.py` | 新增 FilterConfig |
| Modify | `configs/news_sentiment.yaml` | 新增 filter 段，batch_size 改为 20 |
| Create | `tests/news_sentiment/test_filter.py` | 过滤逻辑测试 |

## 依赖

无新增 Python 依赖。Jaccard 相似度纯 Python set 运算。
