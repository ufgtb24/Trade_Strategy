# 级联架构设计：模板验证 + 情感分析

> 2026-04-07 | cascade-design 团队研究报告

## 目标

在 template_validator 的五维度样本外验证之后，对 top-K 模板命中的突破样本追加情感分析过滤，产出带情感维度的级联统计报告，评估"技术面+情感面"联合筛选的增量价值。

---

## 1. 模块放置

**决策：独立子包 `BreakoutStrategy/cascade/`**

理由：
- 级联是 mining 输出与 news_sentiment 输入的**桥接层**，不属于任何一方的内部逻辑
- 放在 mining 中会引入 mining → news_sentiment 的硬依赖，违反当前模块独立性
- 放在 news_sentiment 中会引入对 mining 数据结构（DataFrame、triggered matrix）的依赖
- 项目历史曾设立此目录（后因过早实现被清理），说明此放置符合项目意图
- 与之前研究结论"独立风控层"的定位一致

### 文件结构

```
BreakoutStrategy/cascade/
    __init__.py          # 模块概述 docstring
    batch_analyzer.py    # 核心编排：提取样本 → 批量情感分析 → 合并结果
    filter.py            # 情感筛选逻辑（阈值判定 + 分类标记）
    models.py            # 数据类定义
    reporter.py          # 级联统计报告生成
    __main__.py          # 独立运行入口
```

---

## 2. 数据流

```
template_validator.materialize_trial()
    │
    ├── _match_templates() → matched_results (per-template 统计)
    │                        keys_test (每行的 template key)
    │                        labels_test (每行的 label 值)
    │
    ├── _compute_validation_metrics() → 五维度报告
    │
    └── [新增] cascade 入口
            │
            ▼
        ┌─────────────────────────────────────────────┐
        │  Step 1: 提取 top-K 模板命中的测试集样本      │
        │  输入: df_test, keys_test, top_k_keys        │
        │  输出: List[(symbol, date, label, template)]  │
        └──────────────────┬──────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────┐
        │  Step 2: 按 ticker 去重 + 合并时间窗口        │
        │  输入: List[(symbol, date)]                  │
        │  输出: Dict[ticker → List[breakout_date]]    │
        │  优化: 同一 ticker 多个突破共享一次采集        │
        └──────────────────┬──────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────┐
        │  Step 3: 批量情感分析                         │
        │  对每个 (ticker, breakout_date) 调用          │
        │  news_sentiment.api.analyze(                 │
        │      ticker, date_from, date_to              │
        │  )                                           │
        │  date_from = breakout_date - lookback_days   │
        │  date_to   = breakout_date                   │
        │  并发控制 + 失败容错                           │
        └──────────────────┬──────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────┐
        │  Step 4: 合并 + 情感筛选                      │
        │  将 sentiment_score 关联回每个突破样本         │
        │  按阈值分类: pass / reject / strong_reject   │
        └──────────────────┬──────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────────────┐
        │  Step 5: 级联统计报告                         │
        │  五维度原始指标 + D6 情感维度                   │
        │  对比: 筛前 vs 筛后的 median / lift / 覆盖率  │
        └─────────────────────────────────────────────┘
```

### 关键接口点

级联模块**不侵入** template_validator 的内部逻辑。它接收 template_validator 已有的输出：

```python
# template_validator 已有的输出（无需修改）
df_test: pd.DataFrame        # 包含 symbol, date, label 列
keys_test: np.ndarray         # 每行的 template key (bit-packed)
labels_test: np.ndarray       # 每行的 label 值
matched_results: list[dict]   # per-template 统计
metrics: dict                 # 五维度验证指标（含 d4_global.top_k_names）
```

级联模块从中提取所需信息，不修改 template_validator 的任何函数签名。

---

## 3. 核心数据类

```python
@dataclass
class BreakoutSample:
    """被 top-K 模板命中的单个突破样本"""
    symbol: str
    date: str                    # YYYY-MM-DD
    label: float                 # 40天收益 label
    template_name: str           # 命中的模板名
    template_key: int            # bit-packed key

@dataclass
class CascadeResult:
    """单个突破样本的级联分析结果"""
    sample: BreakoutSample
    sentiment_score: float       # [-0.80, +0.80]
    sentiment: str               # positive/negative/neutral
    confidence: float            # [0, 1]
    category: str                # pass / reject / strong_reject / insufficient_data / error
    total_count: int             # 分析的新闻总数（0 表示无数据）
    analysis_report: AnalysisReport | None  # 完整情感报告（可选保留）

@dataclass
class CascadeReport:
    """级联统计报告"""
    # 输入统计
    total_samples: int           # top-K 模板命中的总样本数
    unique_tickers: int          # 去重后的 ticker 数
    # 情感分析统计
    analyzed_count: int          # 成功分析数
    error_count: int             # 失败数
    # 筛选结果
    pass_count: int              # 通过数
    reject_count: int            # 排除数（score < -0.15）
    strong_reject_count: int     # 强否决数（score < -0.40）
    insufficient_data_count: int # 数据不足（total_count==0 或 fail_ratio 过高）
    positive_boost_count: int    # 正面标记数（score > +0.30，pass 的子集）
    # 级联效果
    pre_filter_median: float     # 筛前 median label
    post_filter_median: float    # 筛后 median label
    cascade_lift: float          # 筛后 - 筛前
    # 详细结果
    results: list[CascadeResult]
```

---

## 4. 情感分析时间窗口策略

**决策：突破前 `lookback_days` 天 ~ 突破当天，默认 7 天，可配置**

```
date_from = breakout_date - timedelta(days=lookback_days)
date_to   = breakout_date
```

理由：
- half_life=3 天意味着模块设计者认为近 1-7 天的新闻最有价值，7 天覆盖了大部分有效权重
- 窗口不含突破后的日期，避免前瞻偏差（look-ahead bias）
- `dynamic_max_items` 公式在 7 天时约 26 条新闻，LLM 成本可控
- 较长窗口（14 天）可作为配置选项用于财报周期覆盖场景，但 time_decay 自然抑制远期噪声

### 时间窗口合并优化

同一 ticker 的多个突破日期可能产生重叠窗口。优化策略：

```
AAPL 突破: 2024-01-10, 2024-01-15
  窗口1: 2023-12-27 ~ 2024-01-10
  窗口2: 2024-01-01 ~ 2024-01-15
  合并:  2023-12-27 ~ 2024-01-15（一次采集，两次聚合）
```

采集阶段使用合并后的时间范围（减少 API 调用），聚合阶段对每个突破日期独立计算 sentiment_score（因为 `reference_date` 不同导致时间衰减权重不同）。这与现有缓存设计完美契合——缓存存储不含时间权重的原始 `(sentiment, confidence)`，衰减在聚合时实时计算。

---

## 5. 筛选阈值设计

**决策：复用已验证的四级阈值体系**

沿用 `docs/research/sentiment_integration_strategy.md` 中的研究结论：

| 区间 | 分类 | 处理 |
|------|------|------|
| score < -0.40 | `strong_reject` | 强否决，无条件排除 |
| score < -0.15 | `reject` | 排除（保留统计） |
| score in [-0.15, +0.30] | `pass` | 放行 |
| score > +0.30 | `pass` | 放行（标记为 positive_boost） |
| total_count == 0 | `insufficient_data` | 无新闻数据，默认放行 |

筛选后保留 `pass` 和 `insufficient_data` 样本，计算筛后统计指标。`reject` 和 `strong_reject` 样本不删除，保留在结果中供统计对比。

### 正面信号的排序层

筛选层只做排除，不因正面 sentiment 改变通过/拒绝的判定。但对**通过筛选的样本**，按 `sentiment_score` 降序排列，提供优先级排序：

```
筛选层（硬门控，不变）：
  score < -0.40 → 强否决
  score < -0.15 → 排除
  score >= -0.15 → 放行

排序层（软信号，新增）：
  放行样本按 sentiment_score 降序排列
  score > +0.30 标记 positive_boost（UI 中可高亮显示）
```

设计理由：
- **风控职责不受污染**：筛选逻辑仍然是纯排除，正面信号不会让本应被排除的样本通过
- **正面信息不浪费**：API + LLM 成本已经付出，正面信号是免费副产品
- **实际选股场景需要排序**：top-K 模板通过 50 个突破，用户实际只关注 10-15 只，sentiment_score 排序帮助优先关注"技术面好 + 消息面好"的标的
- **可验证**：cascade 报告中对比 `positive_boost` vs 普通 `pass` 的 label 分布，用数据决定是否升级为更积极的角色

排序层的输出体现在两处：
1. `CascadeReport.results` 列表按 sentiment_score 降序排列
2. 报告新增 Section 4.1 对比 positive_boost 和普通 pass 的收益差异

### 数据充足度检查

`analyze()` 返回的 `SummaryResult` 中 `total_count == 0` 表示未找到任何新闻，此时 sentiment_score=0.0 并非"中性通过"而是"无数据"。级联层需区分两者：
- `total_count == 0`：标记为 `insufficient_data`，默认放行但在报告中单独统计
- `fail_count / total_count > 0.5`：数据质量不足，也标记为 `insufficient_data`

### 分析失败处理

`analyze()` 永不抛异常（docstring 明确保证）。API 故障时返回 neutral summary + confidence=0.0。但极端情况（网络完全中断）下仍可能出错，此时样本标记为 `category="error"`，**默认放行**。统计报告单独列出错误率和数据不足率。

---

## 6. 效率优化

### 6.1 按 ticker 去重

多个突破可能来自同一 ticker。按 ticker 分组后合并时间窗口，显著减少采集次数。

典型场景：100 个突破样本可能只涉及 30-50 个 unique ticker。

### 6.2 缓存复用

`news_sentiment` 已有两层缓存：
- **新闻缓存**：`(ticker, source, date_range) → List[NewsItem]`，增量采集，未覆盖区间才调 API
- **情感缓存**：`(fingerprint, backend, model) → SentimentResult`，单条新闻结果永久缓存

级联模块直接复用这些缓存，无需额外实现。首次运行后，同一 ticker 的后续分析几乎零 API 开销（仅采集新区间 + filter 后未缓存的新闻条目）。

### 6.3 并发控制

```python
max_concurrent_tickers: int = 5   # 同时分析的 ticker 数
```

理由：
- Finnhub API 限制 60 calls/minute（免费 tier），每只股票 2-3 次 API → 每分钟约 20 只
- 每个 ticker 的 `analyze()` 内部已有 `max_concurrency=20` 的 LLM 并发（ThreadPoolExecutor）
- 外层 5 个 ticker 串行采集（受 Finnhub 限流约束），LLM 分析阶段才需要并发
- 使用 `concurrent.futures.ThreadPoolExecutor(max_workers=5)`

### 6.4 禁用逐股报告保存

`analyze()` 默认会为每只股票生成独立 JSON 报告文件。批量场景下 200 只股票产生 200 个 JSON 文件，造成文件垃圾。

**改动建议**：给 `analyze()` 新增 `save: bool = True` 可选参数，级联调用时传 `save=False`。改动极小（api.py:169 处加条件判断），不影响单股分析的现有行为。

### 6.5 失败重试与容错

```python
max_retries: int = 2              # 单个 ticker 最大重试次数
retry_delay: float = 5.0          # 重试间隔（秒）
fail_policy: str = "pass"         # 失败时默认放行 ("pass") 或排除 ("reject")
```

`analyze()` 内部已有四层容错（采集器级 → 公司名查询 → LLM 单条级 2 次重试 → LLM 整体级），docstring 声明"永不抛异常"。外层仅需处理极端情况（如网络完全中断）。DeepSeek backend 的单条重试在 `deepseek_backend.py` 中实现，失败条目返回 `DEFAULT_SENTIMENT`（impact_value=0.0），在聚合时被自动排除。

### 6.6 进度报告

批量分析可能耗时较长。需要进度回调：

```python
def on_progress(completed: int, total: int, ticker: str, result: CascadeResult):
    """进度回调，供 UI 或命令行显示"""
    pass
```

### 6.7 性能预估

| 场景 | 采集 | 过滤 | LLM 分析 | 总计 |
|------|------|------|----------|------|
| 50 只股票，首次运行 | ~2.5 min | ~0.5 min | ~4-8 min | ~7-11 min |
| 200 只股票，首次运行 | ~10 min | ~2 min | ~15-30 min | ~30-45 min |
| 任意数量，100% 缓存命中 | ~0 | ~0.5 min | ~0 | < 1 min |

瓶颈分析：LLM 分析占总耗时 60-80%。Finnhub 采集限流 60 次/分钟为次要瓶颈。缓存建立后重复实验的边际成本趋零。

---

## 7. 统计报告设计

### 对标 template_validator 报告

template_validator 产出五维度验证报告（D1-D5）。级联报告在此基础上新增 D6 情感维度，并重新计算筛后的 D4 指标。

### 报告结构

```
# Cascade Validation Report

## 0. Summary
  - 输入: N 个 top-K 模板命中样本，M 个 unique ticker
  - 情感分析: K 成功，J 失败
  - 筛选: P 通过，R 排除，S 强否决
  - Cascade lift: +X.XXXX（筛后 median - 筛前 median）

## 1. Pre-filter Baseline（引用 template_validator D4 指标）
  - Template lift (pre-filter): 原始值
  - Matched median (pre-filter): 原始值

## 2. Sentiment Distribution
  - Score 分布直方图（文本）
  - 按 category 分类统计
  - 按 sentiment 标签统计
  | Category | Count | % | Median Label |
  |----------|-------|---|-------------|

## 3. Cascade Effect（核心指标）
  | Metric | Pre-filter | Post-filter | Delta |
  |--------|-----------|-------------|-------|
  | Sample count | N | P | -R-S |
  | Median label | X.XXXX | Y.YYYY | +Z.ZZZZ |
  | Q25 | ... | ... | ... |
  | Q75 | ... | ... | ... |
  | Mean | ... | ... | ... |

## 4. Rejected Sample Analysis
  - 被排除样本的 label 分布（验证排除是否合理）
  - 如果 rejected 样本的 median label 低于 pass 样本，说明 sentiment 筛选有效
  | Group | N | Median | Q25 | Q75 |
  |-------|---|--------|-----|-----|
  | pass | ... | ... | ... | ... |
  | reject | ... | ... | ... | ... |
  | strong_reject | ... | ... | ... | ... |
  | insufficient_data | ... | ... | ... | ... |
  | error | ... | ... | ... | ... |

## 4.1 Positive Boost Analysis
  - 验证正面 sentiment 是否有选股增量价值
  - positive_boost (score > +0.30) vs 普通 pass 的 label 分布对比
  | Group | N | Median | Q25 | Q75 | Mean |
  |-------|---|--------|-----|-----|------|
  | positive_boost | ... | ... | ... | ... | ... |
  | normal_pass | ... | ... | ... | ... | ... |
  - boost_lift = positive_boost median - normal_pass median
  - 如果 boost_lift > 0 且样本量充足，正面信号有排序价值

## 5. Per-Template Cascade Comparison
  - 每个 top-K 模板筛前/筛后的统计量对比
  | Template | Pre N | Pre Med | Post N | Post Med | Rejected | Lift |

## 6. Judgment
  - cascade_lift > 0 → 情感筛选有增量价值
  - rejected_median < pass_median → 筛选方向正确
  - error_rate < 20% → 数据质量可接受
  - boost_lift > 0 → 正面信号有排序价值（参考指标，不影响主判定）
```

### 判定逻辑

```python
def judge_cascade(report: CascadeReport) -> tuple[str, list[str]]:
    """
    三级判定: EFFECTIVE / MARGINAL / INEFFECTIVE

    - EFFECTIVE: cascade_lift > 0 且 rejected_median < pass_median
    - MARGINAL: cascade_lift > 0 但 rejected_median >= pass_median（方向不确定）
    - INEFFECTIVE: cascade_lift <= 0（情感筛选无增量价值）
    """
```

---

## 8. 配置设计

### configs/cascade.yaml

```yaml
# 级联验证配置
cascade:
  # 情感分析时间窗口
  lookback_days: 7                # 突破前回溯天数（7 天覆盖大部分有效权重）

  # 筛选阈值
  thresholds:
    strong_reject: -0.40          # 强否决线
    reject: -0.15                 # 排除线
    positive_boost: 0.30          # 正面标记线（统计用，不影响筛选）

  # 数据充足度
  min_total_count: 1              # 新闻数低于此值标记为 insufficient_data
  max_fail_ratio: 0.5             # fail_count/total_count 超过此值标记为 insufficient_data

  # 效率控制
  max_concurrent_tickers: 5       # 同时分析的 ticker 数
  max_retries: 2                  # 单 ticker 最大重试
  retry_delay: 5.0                # 重试间隔（秒）
  fail_policy: "pass"             # 失败时策略: "pass" | "reject"
  save_individual_reports: false   # 是否保存每只股票的 JSON 报告

  # 报告
  report_name: "cascade_report.md"
```

情感分析的其他配置（backend、model、缓存等）复用 `configs/news_sentiment.yaml`，不重复定义。

---

## 9. 接口设计

### 核心函数签名

```python
# batch_analyzer.py

def run_cascade(
    df_test: pd.DataFrame,
    keys_test: np.ndarray,
    top_k_keys: set[int],
    top_k_names: dict[int, str],
    cascade_config: dict | None = None,
    sentiment_config: NewsSentimentConfig | None = None,
    on_progress: Callable | None = None,
) -> CascadeReport:
    """
    级联分析主入口。

    从 template_validator 的输出中提取 top-K 模板命中样本，
    批量执行情感分析，筛选后产出级联报告。

    内部调用 analyze(save=False) 避免产生逐股 JSON 文件。

    Args:
        df_test: 测试集 DataFrame（需包含 symbol, date, label 列）
        keys_test: 每行的 template key (bit-packed int array)
        top_k_keys: top-K 模板的 key 集合
        top_k_names: key → template_name 映射
        cascade_config: 级联配置（默认从 cascade.yaml 加载）
        sentiment_config: 情感分析配置（默认从 news_sentiment.yaml 加载）
        on_progress: 进度回调 (completed, total, ticker, result) → None

    Returns:
        CascadeReport 包含完整统计和逐样本结果
    """
```

```python
# filter.py

def classify_sample(
    sentiment_score: float,
    total_count: int,
    fail_count: int,
    thresholds: dict,
) -> str:
    """
    根据 sentiment_score 和数据充足度分类。

    优先级：数据充足度检查 > 阈值判定。
    total_count == 0 或 fail_count/total_count > max_fail_ratio 时
    返回 "insufficient_data"，不参与阈值判定。

    Returns:
        "strong_reject" | "reject" | "pass" | "insufficient_data"
    """
```

```python
# reporter.py

def generate_cascade_report(
    cascade_report: CascadeReport,
    pre_filter_metrics: dict,       # template_validator 的 D4 指标
    output_path: Path,
) -> None:
    """生成 Markdown 级联验证报告。"""
```

### 与 template_validator 的集成

级联分析是 **可选步骤**，通过 `materialize_trial()` 的参数控制：

```python
# template_validator.py 新增参数
def materialize_trial(
    ...
    run_cascade: bool = False,          # 新增：是否执行级联验证
    cascade_config: dict | None = None, # 新增：级联配置
):
```

当 `run_cascade=True` 时，在 OOS 验证（Step 5）完成后，调用 `cascade.batch_analyzer.run_cascade()` 执行 Step 6。

---

## 10. 设计决策汇总

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | 模块位置 | `BreakoutStrategy/cascade/` 独立子包 | 桥接层，不属于 mining 或 sentiment |
| 2 | 数据粒度 | per-breakout（每个突破点独立分析） | 与 template_validator 的粒度一致 |
| 3 | 时间窗口 | 突破前 7 天（可配置） | half_life=3 天覆盖大部分有效权重 + 避免前瞻偏差 |
| 4 | 筛选策略 | 四级阈值（复用已验证方案） | -0.40/-0.15/+0.30，已有研究支撑 |
| 5 | 缓存策略 | 复用 news_sentiment 已有缓存 | 无需额外实现，增量采集+情感缓存 |
| 6 | 并发策略 | 外层 5 ticker × 内层 20 LLM | 适配 Finnhub 60 calls/min（~20 ticker/min） |
| 7 | 失败策略 | 默认放行 + 统计错误率 | 不因 API 故障排除技术面合格样本 |
| 8 | 侵入性 | 不修改 template_validator 内部函数 | 仅在 materialize_trial 末尾追加调用 |
| 9 | 报告格式 | 对标五维度报告 + D6 情感维度 | 与现有报告体系一致 |
| 10 | 配置分离 | cascade.yaml 独立 + 复用 news_sentiment.yaml | 职责分离，不重复定义 |
| 11 | 时间窗口合并 | 同 ticker 多突破合并采集，独立聚合 | 减少 API 调用，利用缓存正交设计 |
| 12 | 判定体系 | EFFECTIVE / MARGINAL / INEFFECTIVE | 三级判定，与 template_validator 对齐 |
| 13 | 正面信号 | 不影响筛选，但作为排序信号输出 | 风控职责不污染；排序帮助用户优先关注技术+消息面双优标的 |
| 14 | analyze() 改造 | 新增 `save=False` 参数 | 批量场景避免产生大量 JSON 文件垃圾 |
| 15 | 数据充足度 | total_count==0 或 fail_ratio>0.5 → insufficient_data | 区分"无数据"与"中性通过"，默认放行 |
| 16 | 主判据 | 仅用 sentiment_score + total_count | 不单独用 confidence 或 rho（已融合） |

---

## 11. 已知局限与后续工作

1. **历史新闻可得性**：测试集可能跨越较早时期（如 2023 年），部分小盘股历史新闻稀缺，情感分析可能退化为 neutral（低 confidence）。报告中需标注 insufficient_data 占比。当前仅 Finnhub 启用（AlphaVantage 25次/天对批量是死穴，EDGAR 已禁用），新闻源单一加剧此问题。

2. **API 成本**：首次运行 50 个 ticker × ~26 条新闻/ticker × LLM 调用 ≈ 1300 次 LLM 请求。DeepSeek 约 $0.015，可接受。后续复用缓存成本趋零。

3. **UI 集成**：当前设计仅覆盖数据处理流程。后续需在 UI 中：
   - template_validator 报告页增加"运行级联验证"按钮
   - 显示级联报告
   - 进度条展示批量分析进度

4. **统计显著性**：cascade_lift 基于小样本（top-K 模板命中的测试集样本，通常 20-100 个），需谨慎解读。可考虑 bootstrap 置信区间。

5. **sentiment_score 阈值校准**：当前阈值来自先验研究，未在实际级联数据上校准。积累足够数据后可做 ROC 分析优化阈值。
