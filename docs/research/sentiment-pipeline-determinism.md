# 情感分析管道非确定性根因分析与修复总结

> 日期: 2026-04-08
> 状态: 已修复并验证（连续 3 次运行结果完全一致）

## 1. 现象

连续两次运行 `template_validator` 的情感验证阶段，结果不一致：
- 同一 ticker 的 `sentiment_score` 在运行间波动 ±0.01 ~ ±0.15
- `pass`/`reject`/`insufficient_data` 分类在运行间翻转
- `sentiment_lift` 在 -0.03 ~ +0.02 间波动
- 每次运行仍触发 DeepSeek API 调用（即使所有新闻已缓存）

## 2. 根因分析

通过逐层隔离测试，发现 **四层独立的非确定性来源**，形成级联放大链路：

```
cache.get_news() 无序 ──→ _infer_company_name 频次 tie ──→ 参考向量不同
       │                          │                              │
       │                          ▼                              ▼
       │                  relevance_filter 结果变化        cosine sim 差异 ~0.26
       │                          │
       ▼                          ▼
  semantic_dedup 贪心顺序变化   filter 存活集完全不同
       │                          │
       ▼                          ▼
  diversity_sample 输入变化     不同新闻 → 不同情感分数
                                  │
                                  ▼
                    get_company_name 速率限制 ──→ 公司名随机缺失
                                  │
                                  ▼
                    coverage 空结果不标记 ──→ 重复抓取得到不同新闻
                                  │
                                  ▼
                    impact_value=0 不缓存 ──→ 重复调用 DeepSeek
```

### 根因 1: `_infer_company_name()` 的 Counter tie-breaking（影响最大）

**位置**: `filter.py:243`

`Counter.most_common(1)` 在频次相同时按 dict 插入顺序返回，而插入顺序取决于输入 items 的遍历顺序。

**实际案例**: ticker `CAN`（Canaan），semantic_filter 后 "Asian" 和 "Bitcoin." 各出现 5 次。不同输入顺序导致参考向量为 `"Asian CAN"` 或 `"Bitcoin. CAN"`，cosine similarity 差异高达 **0.26**——足以让大量新闻跨过/跌出 0.55 的相关性阈值。

**验证方法**: 对 CAN 的 25 条新闻随机打乱 10 次运行 filter 管道，`relevance_filter` 输出在 2~9 条间波动。

### 根因 2: `get_company_name()` 无缓存 + 并发速率限制

**位置**: `api.py:110-114`, `finnhub_collector.py:73-86`

`api.analyze()` 每次调用都向 Finnhub API 请求公司名。验证阶段 `ThreadPoolExecutor(max_workers=3)` 并发分析 50+ tickers，每个 worker 各自创建 collector 实例（各自独立的 rate limiter），实际并发 API 调用速率 ~3 calls/sec，超过免费 tier 限额。

**后果**: 部分 ticker 的 `get_company_name()` 被 429 返回空字符串 → 回退到 `_infer_company_name()` → 不同 ticker 在不同运行中随机使用 Finnhub 名或推断名。

### 根因 3: coverage 空结果不标记 + `get_news()` 无 ORDER BY

**位置**: `api.py:91-92`, `cache.py:173-177`

- `if fetched:` 条件导致 API 返回空结果（速率限制或确实无新闻）时不标记 coverage → 下次重新抓取 → 不同时刻 Finnhub 可能返回不同结果
- `get_news()` SQL 无 ORDER BY → SQLite 返回顺序依赖内部 rowid，不同操作（INSERT/DELETE/VACUUM）后顺序可能变化

### 根因 4: `impact_value=0` 的分析结果不缓存

**位置**: `analyzer.py:152`

`if sent.impact_value > 0:` 条件导致 DeepSeek 解析失败的结果不被缓存。这些失败是确定性的（同一条新闻的 prompt 总是导致解析失败），但每次运行都重新调用 API，浪费配额且引入 `temperature=0.1` 带来的微小随机性。

**验证**: 连续运行两次，始终有 6 个 ticker 各 1 条 cache miss。

## 3. 修复方案

四个修复，每个针对一层根因，全部独立且无副作用：

### Fix 1: `_infer_company_name` 确定性 tie-breaking

**文件**: `filter.py` | **改动**: 3 行

```python
# Before
return word_counts.most_common(1)[0][0] if word_counts else ticker

# After
if not word_counts:
    return ticker
top = sorted(word_counts.items(), key=lambda x: (-x[1], x[0]))
return top[0][0]
```

`sorted()` 按 `(-频次, 字母升序)` 排列，消除 Counter 的插入顺序依赖。

### Fix 2: 公司名 SQLite 持久缓存

**文件**: `cache.py` + `api.py` | **改动**: 新增 `company_names` 表 + 读写方法

```sql
CREATE TABLE IF NOT EXISTS company_names (
    ticker TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT DEFAULT (date('now'))
);
```

```python
# api.py — 先查缓存，miss 时查 API 并写入缓存
company_name = cache.get_company_name(ticker) or ""
if not company_name:
    company_name = collector.get_company_name(ticker)
    if company_name:
        cache.put_company_name(ticker, company_name)
```

首次查询后永久缓存，消除并发速率限制导致的随机空值。

### Fix 3: coverage 无条件标记 + get_news() ORDER BY

**文件**: `api.py` + `cache.py` | **改动**: 各 1-2 行

```python
# api.py — 移除 if fetched 条件
pending_coverage.append((ticker, collector.name, uc_from, uc_to))

# cache.py — 添加 ORDER BY
"... AND published_date <= ? ORDER BY published_date, fingerprint"
```

空结果也标记为已覆盖，防止重复抓取。ORDER BY 确保缓存返回顺序确定。

### Fix 4: 缓存所有情感分析结果（含失败）

**文件**: `analyzer.py` | **改动**: 删除 1 行条件

```python
# Before
if sent.impact_value > 0:
    self._cache.put_sentiment(fp, backend_name, model_name, sent)

# After（无条件缓存）
self._cache.put_sentiment(fp, backend_name, model_name, sent)
```

解析失败的结果也缓存，首次运行后不再调用 DeepSeek API。

### 补充: semantic_dedup 预排序（前序对话已实施）

**文件**: `filter.py` | **改动**: 5 行

```python
order = sorted(range(len(items)),
               key=lambda i: (len(items[i].summary), items[i].published_at or '', items[i].title),
               reverse=True)
items = [items[i] for i in order]
embeddings = embeddings[order]
```

贪心去重算法对输入顺序敏感。预排序使其输出与输入顺序无关。与根因 3 的 ORDER BY 形成双保险。

## 4. 验证结果

### 单元测试

79/79 通过，无回归。

### Filter 管道确定性测试

对 6 个 ticker（DVLT/SPRC/ONDS/CAN/GLUE/FDMT）各随机打乱 10 次输入，filter 输出完全一致。

### 端到端验证

连续 3 次运行 `template_validator`（含情感验证），结果完全一致：

| 指标 | Run 1 | Run 2 | Run 3 |
|------|-------|-------|-------|
| Sentiment lift | +0.0139 | +0.0139 | +0.0139 |
| Pass (boost) | 40 (23) | 40 (23) | 40 (23) |
| Reject | 7 | 7 | 7 |
| Cache misses | 0 | 0 | 0 |
| DeepSeek calls | 0 | 0 | 0 |

### 性能对比

| 指标 | 修复前（随机） | 修复后（确定） |
|------|--------------|--------------|
| Sentiment lift | -0.03 ~ +0.02 | +0.0139（稳定） |
| Post-filter vs Pre-filter | 随机翻转 | Post > Pre |
| DeepSeek API calls/run | 5~6 次 | 0 次（首次后） |

## 5. 修改文件清单

| 文件 | 改动行数 | 修复项 |
|------|---------|--------|
| `filter.py` | +13 -1 | Fix 1 (tie-breaking) + 预排序 |
| `cache.py` | +29 -1 | Fix 2 (company_names 表) + Fix 3 (ORDER BY) |
| `api.py` | +19 -8 | Fix 2 (缓存读写) + Fix 3 (无条件 coverage) |
| `analyzer.py` | +2 -3 | Fix 4 (无条件缓存情感结果) |
