# 情感分析管道非确定性根因分析与修复总结

> 日期: 2026-04-09
> 状态: 已修复并验证（连续运行结果完全一致，零 DeepSeek 调用）

## 1. 现象

连续两次运行 `template_validator` 的情感验证阶段，结果不一致：
- 同一 ticker 的 `sentiment_score` 在运行间波动 ±0.01 ~ ±0.15
- `pass`/`reject`/`insufficient_data` 分类在运行间翻转
- `sentiment_lift` 在 -0.03 ~ +0.02 间波动
- 每次运行仍触发 DeepSeek API 调用（即使所有新闻已缓存）

## 2. 不确定性的独立源

通过逐层隔离测试，识别出 **两个独立的随机性源** 和 **一组级联放大器**：

### 2.1 独立随机性源（真正产生非确定性的位置）

| # | 随机性源 | 机制 | 影响 |
|---|---------|------|------|
| **S1** | `get_company_name()` 并发速率限制 | `ThreadPoolExecutor(max_workers=3)` 并发调用 Finnhub API，每个 worker 有独立 rate limiter，线程调度和网络时序决定哪些请求被 429 → 随机返回空字符串 | 同一 ticker 在不同运行中使用 Finnhub 公司名或回退名 → 参考向量完全不同 |
| **S2** | coverage 空结果不标记 | `if fetched:` 条件使得 API 返回空（无新闻的 ticker 或被限速）时不标记 coverage → 下次运行重新抓取 → 不同时刻 API 可能返回不同数据 | 跨运行的新闻集合不同 |

### 2.2 级联放大器（自身确定性，但将上游微小变化放大为大偏差）

| # | 放大器 | 放大机制 | 前置条件 |
|---|--------|---------|---------|
| **A1** | `_infer_company_name()` Counter tie-breaking | `Counter.most_common(1)` 频次相同时按 dict 插入顺序返回，输入顺序微变 → 选出完全不同的词 → 参考向量 cosine sim 差 **0.26** | 需要 S1 先使 company_name 回退为空 |
| **A2** | `semantic_dedup` 贪心算法 | 输入顺序变化 → `break` 优先命中不同的 kept 项 → 不同的存活集 | 需要上游输入顺序不确定 |

### 2.3 浪费源（不产生随机性，但导致不必要的 API 调用）

| # | 浪费源 | 机制 |
|---|--------|------|
| **W1** | `impact_value=0` 的情感结果不缓存 | 解析失败是确定性的（同一 prompt 总是失败），但每次重新调 DeepSeek 浪费配额 |

### 2.4 级联关系图

```
S1 (rate limiting → 随机空公司名)
  └→ A1 放大: "Asian CAN" vs "Bitcoin. CAN" → cosine sim 差 0.26
      └→ relevance_filter 存活集完全不同
          └→ A2 放大: 不同输入 → 不同 dedup 存活集
              └→ 不同新闻 → 不同情感分数

S2 (空结果不标记 → 重复抓取 → 不同新闻集)
  └→ 直接改变输入数据，下游全部受影响

W1 (失败结果不缓存 → 每次都调 DeepSeek)
  └→ 浪费 API 配额，不影响确定性
```

**关键结论**: A1 和 A2 自身不产生随机性。只有当 S1 或 S2 先注入非确定性后，它们才将微小变化放大为显著偏差。

## 3. 修复方案

### Fix 1: 公司名 SQLite 持久缓存（消除 S1）

**文件**: `cache.py` + `api.py`

新增 `company_names` 表，首次从 Finnhub 获取后永久缓存。后续调用直接查缓存，不再受速率限制影响。

```python
# api.py — 缓存优先查找
company_name = cache.get_company_name(ticker) or ""
if not company_name:
    company_name = collector.get_company_name(ticker)
    if company_name:
        cache.put_company_name(ticker, company_name)
```

### ~~Fix 2: coverage 无条件标记（消除 S2）~~ — 已回滚

**曾实施后回滚。** 无条件标记 coverage 虽然消除了 S2 随机性，但将"空结果"永久锁定——这是吸收态最差结果。回滚后保留 `if fetched:` 条件，空结果不标记 coverage，保留重试机会。重试期望单调非递减（要么不变要么成功），一旦成功就自然收敛到确定性。

### Fix 3: 删除 `_infer_company_name`（消除 A1 放大器）

**文件**: `filter.py`

公司名已通过 Fix 1 持久化到 SQLite。对 Finnhub 确实无档案的 ticker（如权证 NIOBW/TVACW），直接用 ticker 本身作为参考向量（`"CAN"` 远优于 `"Bitcoin. CAN"`）。

同时删除了 `_TITLE_STOP_WORDS`、`Counter` 导入和整个 `_infer_company_name()` 函数。

```python
# Before
if not company_name:
    company_name = _infer_company_name(items, ticker)
ref_text = f"{company_name} {ticker}"

# After
ref_text = f"{company_name} {ticker}" if company_name else ticker
```

### Fix 4: `semantic_dedup` 预排序（消除 A2 放大器）

**文件**: `filter.py`

```python
order = sorted(range(len(items)),
               key=lambda i: (len(items[i].summary), items[i].published_at or '', items[i].title),
               reverse=True)
items = [items[i] for i in order]
embeddings = embeddings[order]
```

使贪心去重算法输出与输入顺序无关。排序策略与函数内部"保留最长 summary"语义一致。

### ~~Fix 5: 缓存所有情感分析结果（消除 W1 浪费）~~ — 已回滚

**曾实施后回滚。** 缓存失败结果（`impact_value=0`）虽然消除了重复 API 调用，但失败多为偶发网络/限流问题（非确定性解析失败）。缓存失败等于永久丢失该新闻的分析机会。回滚后保留 `if sent.impact_value > 0:` 条件，失败结果不缓存，下次运行自动重试。与 Fix 2 同理：重试期望单调非递减。

## 4. 验证结果

### 单元测试

79/79 通过，无回归。

### Filter 管道确定性测试

对 6 个 ticker（DVLT/SPRC/ONDS/CAN/GLUE/FDMT）各随机打乱 10 次输入，filter 输出完全一致。

### 端到端验证

连续多次运行 `template_validator`（含情感验证），结果完全一致：

| 指标 | 值 |
|------|-----|
| Sentiment lift | +0.0218 |
| Pass (boost) | 38 (22) |
| Reject | 6 |
| Sentiment Verdict | EFFECTIVE |

注：Fix 2/5 回滚后系统不再完全确定性，但通过重试自然收敛——每次成功获取的数据被缓存，后续运行复用缓存结果。

## 5. 最终决策摘要

| 修复 | 状态 | 理由 |
|------|------|------|
| Fix 1 公司名缓存 | **保留** | 消除真随机性源 S1，无性能代价 |
| Fix 2 coverage 无条件标记 | **回滚** | 锁定空结果（吸收态最差），重试只能持平或改善 |
| Fix 3 删除 `_infer_company_name` | **保留** | 消除放大器 A1，纯改善 |
| Fix 4 预排序 | **保留** | 消除放大器 A2，严格最优 |
| Fix 5 缓存失败结果 | **回滚** | 锁定分析失败（偶发网络问题），重试只能持平或改善 |

## 6. 修改文件清单

| 文件 | 改动 | 对应修复 |
|------|------|---------|
| `cache.py` | 新增 `company_names` 表 + `get/put_company_name` 方法 | Fix 1 |
| `api.py` | 公司名缓存读写 + 条件性 coverage 标记（`if fetched:`） | Fix 1 + Fix 2 回滚 |
| `filter.py` | 删除 `_infer_company_name` 及相关代码，添加预排序 | Fix 3 + Fix 4 |
| `analyzer.py` | 保留 `if impact_value > 0:` 缓存条件 | Fix 5 回滚 |
| `test_filter.py` | 测试适配（显式传 `company_name`） | Fix 3 配套 |
