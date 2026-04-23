# Per-Factor Gate 改造：Live 管道影响分析

> 成员：live-integration
> 日期：2026-04-15
> 范围：`BreakoutStrategy/live/` 全部、`analysis/scanner.py` 中 live 复用路径
> 结论预览：**Live 不需要主动改动主干，但需要 1 项防御性 detail_panel 改动 + 1 项缓存 schema 字段**。主要变化在 detector 层和 scorer 层产出的 bo dict 本身，Live 是被动传导受益方；MatchedBreakout 契约向前兼容（加载旧缓存不破坏）。

---

## 1. Live 管道现状

### 1.1 数据流全景

```
[_step1 download]  akshare → datasets/pkls_live/*.pkl (+ .last_full_update marker)
         ↓
[_step2 scan]      ScanManager(max_buffer=get_max_buffer()) → parallel_scan
                   → list[dict]（scanner 跨进程 JSON-friendly 契约）
         ↓
[_step3 match]     TemplateManager.match_stock(template)
                   → MatchedBreakout（挑 BO 级字段 + raw_breakout 全量留存）
         ↓
[_step4 sentiment] news_sentiment.api.analyze → sentiment_score/category/summary
         ↓
[cache]            CachedResults JSON → config.cache_path (live/config.yaml 指定)
         ↓
[render]           load_cached → MatchList + ChartCanvasManager(live_mode) + DetailPanel
```

### 1.2 扫描入口：复用 ScanManager

**关键文件**：`live/pipeline/daily_runner.py:108-141` 的 `_step2_scan`

Live 通过 `ScanManager(...).parallel_scan(symbols, data_dir, num_workers)` 完成扫描，**没有自己的扫描引擎**。`ScanManager.__init__` 在 scanner.py:555 固定执行 `self.max_buffer = get_max_buffer()`，Live 对此**不传参也无法覆盖**。因此：

- Live 的 `max_buffer` 行为完全继承 `factor_registry.get_max_buffer()` 的当前值（=252）。
- `_scan_single_stock` 里 detector 的 gate 语义 live 完全继承。

### 1.3 持久化层

**cache 格式**：`live/pipeline/results.py` 定义 `MatchedBreakout` + `CachedResults`，通过 `dataclass asdict()` → JSON dump（`save_cached_results`）。加载用 `load_cached_results`，内部**字段白名单过滤**（results.py:62-64）：

```python
known_fields = {f.name for f in fields(MatchedBreakout)}
items = [MatchedBreakout(**{k: v for k, v in item_dict.items() if k in known_fields}) ...]
```

**这是向前兼容的关键**——加载时丢弃未知字段，缺失字段走 dataclass 默认值。对本次改造的直接含义：新缓存可以新增字段（如 `gate_mode`）而旧代码可以忽略；旧缓存加载到新代码，新增字段走默认值。

**cache 内容**：
- `MatchedBreakout.factors`：只含**该模板覆盖的因子**的值字典（`daily_runner.py:172`）。
- `MatchedBreakout.raw_breakout`：scanner 输出的完整 BO dict（含 quality_score / 全部因子字段 / labels）。
- `MatchedBreakout.raw_peaks`、`all_stock_breakouts`、`all_matched_bo_chart_indices`：图表渲染需要的上下文。
- `scan_metadata` **不写入 cache**——CachedResults 只有 `scan_date` + `last_scan_bar_date`，没有 detector/feature 参数快照（与 dev UI 的 JSON 输出不同）。

### 1.4 UI 消费点

| 组件 | 读取字段 | 用途 |
|---|---|---|
| `MatchList._row_values` | `sentiment_score`, `breakout_price`, `breakout_date`, `symbol` | Treeview 显示 |
| `MatchList._apply_filters` | `sentiment_score`, `breakout_price`, `breakout_date` | Date/Price/Score 过滤 |
| `MatchList.get_visible_bo_indices` | `raw_breakout["index"]` | 图表 4 级分类 |
| `DetailPanel.update_item` | `factors` dict, `sentiment_score`, `sentiment_category`, `sentiment_summary` | 底部摘要 |
| `LiveApp._rebuild_chart` | `raw_peaks`, `all_stock_breakouts`, `raw_breakout["index"]`, `all_matched_bo_chart_indices` | 图表重绘 |
| `chart_adapter.adapt_breakout` | `index`, `price`, `date`, `quality_score`, `broken_peak_ids`, `superseded_peak_ids`, `labels` | dict → ChartBreakout |

**关键：Live UI 完全不读 `per-factor` 的 `level` / `triggered` / `unavailable` 状态**。这是和 dev UI 的最大区别。

### 1.5 图表渲染：走 live_mode 专属路径

`canvas_manager.update_chart(display_options={"live_mode": True, ...})` 分派到 `MarkerComponent.draw_breakouts_live_mode`（markers.py:281），这是独立方法，**不显示 quality_score**（见 live.md 决策 #4：Live 用户不调参，quality_score 是噪音）。

BO 的分类只用 `bo_chart_index` 与 `visible_matched_indices` / `filtered_out_matched_indices` 集合比对，**不读任何因子值**。

---

## 2. 新方案对 Live 的**直接**影响点

以下变化在 detector / feature / scorer 层改完后，**不改 live 代码**也会自动发生：

### 2.1 正向影响

1. **idx<252 的 BO 会出现在候选中**
   scanner 产出的 `breakouts` 列表新增若干早期段 BO（对应 IPO 后前 1 年的短 lookback 期）。Live 的 `_step3_match_templates` 会把它们送入 `match_breakout`。

2. **match_breakout 对 idx<252 BO 默认过滤掉（missing-as-fail）**
   若 template 包含 volatility 因子（overshoot/day_str/pbm），`template_matcher.py:84-85` 的 `if value is None: return False` 会让这些 BO 落空。用户**看不到大量新噪音**——自动保护机制生效。

3. **drought/streak 在 idx>=252 段变诚实**
   全局 gate 消除后 detector history 完整，早段 BO 的 streak_count / drought_days 对后续 BO 不再被截断。MatchedBreakout.factors 中这两个因子值的分布会有细微漂移，但这是"修 bug"。

### 2.2 需要警惕的风险

1. **`MatchedBreakout.factors` 字典可能含 None 值**
   `daily_runner.py:172` 的 `factors={f: bo[f] for f in self.trial.template["factors"] if f in bo}` 会把 bo dict 中的 None 原样带入（key 存在即保留）。**新方案下 `bo[f]` 可能是 None**。

   下游 `DetailPanel._fmt(value)` 在 `detail_panel.py:11-14`：
   ```python
   def _fmt(value: float) -> str:
       if isinstance(value, int):
           return str(value)
       return f"{value:.2f}"
   ```
   **None 走到 `f"{None:.2f}"` → TypeError** 崩 panel。这是唯一确定的崩溃点（见 §3.1）。

2. **cache 的不可逆语义迁移**
   cache 记录扫描结果，不记录 `gate_mode`。若用户在旧语义（bo_level gate）下生成 cache，随后升级代码，新代码会**直接读旧 cache 并用新语义渲染**。表面看不出差异（因为数据已经在 cache 里固化），但用户若点"刷新"重跑 pipeline，新结果中会出现更多 BO——"看起来一样的股票，今天 BO 数变了"。

3. **增量模式问题：Live 是每次全量扫描，非 add_bar**
   `_step2_scan` 用 `ScanManager.parallel_scan`，每天**从 pkl 重新跑扫描**，不是 `detector.add_bar` 增量。这意味着没有"历史 BO 被锁定"的问题——每天都是干净重放。**per-factor gate 的增量语义在 live 下不存在**（见 §6 详述）。

4. **过时 Trial 的模板-数据 mismatch 加剧**
   Trial 的 `filter.yaml` 是基于**旧 gate 语义下跑出来的 factor_diag.yaml** 训练的。若先升级代码再用老 trial 跑扫描，template thresholds 的分布基础变了（挖掘那边 mining-pipeline 成员应会指出），选股精度会下降。这不是 live 代码 bug，但是产品层面需要提示用户"per-factor 切换后，trial 应重跑"。

---

## 3. 需要 Live **主动改动**的点

### 3.1 必须改：DetailPanel 防御 None 格式化

**位置**：`live/panels/detail_panel.py:11-14`

**问题**：`_fmt` 对 `None` 无处理，`factors={"volume": None}` 会崩。

**建议改动**：
```python
def _fmt(value) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, int):
        return str(value)
    return f"{value:.2f}"
```

这是**唯一必须改的主干代码**。代价 < 5 行，影响面只在 detail_panel。

### 3.2 建议改：CachedResults 添加 gate_mode 字段

**位置**：`live/pipeline/results.py` 的 `CachedResults` dataclass

**动机**：tom 的报告推荐 `scan_metadata` 加 `gate_mode`。Live 的 CachedResults 本身没 scan_metadata 段，但应支持一个顶层字段：

```python
@dataclass
class CachedResults:
    items: list[MatchedBreakout]
    scan_date: str
    last_scan_bar_date: str
    gate_mode: str = "per_factor"   # 新增，默认新语义；旧 JSON 加载走默认
```

由于 `load_cached_results` 用 `data["scan_date"]` 等 `__getitem__` 方式（results.py:67-71），**新增字段必须走 `.get()` 否则旧 JSON 会 KeyError**。实际上 `load_cached_results` 的现有结构需要小调整：

```python
return CachedResults(
    items=items,
    scan_date=data["scan_date"],
    last_scan_bar_date=data["last_scan_bar_date"],
    gate_mode=data.get("gate_mode", "bo_level"),  # 旧 cache 默认旧语义
)
```

**注意**：旧 cache 默认 `bo_level` 语义，标记为"历史语义"——UI 可选择显示提示"此缓存基于旧 gate 模式，建议重新扫描"。这是**可选增强**，不改现有 UX 不会崩。

### 3.3 不用改：其他所有消费点都已 None-safe

- `MatchList._apply_filters` 已用 `if it.sentiment_score is None` 分支（match_list.py:589）。`breakout_price` 和 `breakout_date` 由 daily_runner 保证非 None（取自 bo dict 的必填字段）。
- `MatchList._row_values`：`sentiment_score` 已处理 None；`breakout_price` / `breakout_date` 非 None。
- `chart_adapter.adapt_breakout`：`quality_score` 用 `raw_bo.get("quality_score")` 返回 `Optional[float]`，markers 层已 `if bo.quality_score is not None` 保护（不过 live_mode 分支根本不读它）。
- 所有 peak/bo 的 index、price、date、broken_peak_ids **都不受 per-factor gate 影响**——这些是 detector 本身的输出，在 gate 消除后只会**更齐全**，不会变 None。

---

## 4. MatchedBreakout 字段 None 安全性审计

| 字段 | 类型（声明） | per-factor 后可能 None？ | 消费点风险 |
|---|---|---|---|
| `symbol` | str | 否 | - |
| `breakout_date` | str | 否 | - |
| `breakout_price` | float | 否（取自 `bo["price"]`, scanner 总给 float） | - |
| `factors: dict[str, float]` | dict | **是**（值可能 None） | **DetailPanel._fmt 会 TypeError，见 §3.1** |
| `sentiment_score` | float \| None | 是（已有） | 已处理 |
| `sentiment_category` | str | 否 | - |
| `sentiment_summary` | str \| None | 是（已有） | 已处理 |
| `raw_breakout: dict` | dict | 否（dict 本身非 None） | 内部 key 如 "overshoot" 可能 None。但 live 只读 `raw_breakout["index"]`（整数，非因子）—**无风险** |
| `raw_peaks` | list | 否 | peak 是 detector 输出，gate 改造前后都非 None |
| `all_stock_breakouts` | list | 否 | 同上 |
| `all_matched_bo_chart_indices` | list | 否 | - |

**结论**：唯一真实崩溃点是 **`factors` 字典值 None 进入 `_fmt`**（§3.1）。其他字段要么本来就 None-safe，要么不受 gate 改造影响。

---

## 5. Live UI 是否需同步 scorer-ui 的改动

### 5.1 Grep 证据：Live **不复用** `ScoreDetailWindow` / `score_tooltip` / `FactorDetail`

```
grep -rn "ScoreDetailWindow|score_tooltip|FactorDetail" BreakoutStrategy/live
# → 无匹配
```

### 5.2 解释

Dev UI 的 `score_tooltip.py` 显示**每个因子的 level/trigger/multiplier** 明细，是策略调参的决策信号。Live 的设计哲学（live.md 决策 #1 + #4）明确拒绝这种信息：**Live 用户不调参，看 factor level 反而是噪音**。

因此 scorer-ui 成员对 `FactorDetail.unavailable` 的新增、对 score_tooltip 的 "N/A" 显示扩展，**对 live UI 完全透明，live 不需同步改**。

### 5.3 唯一的 Live 显示层改动

就是 §3.1 的 `detail_panel._fmt` 加 None 分支，**这不需要 FactorDetail 扩展**——DetailPanel 读的是 `MatchedBreakout.factors` 这个纯值字典（daily_runner 在 match 阶段从 bo dict 拷贝出来的），和 FactorDetail 对象链路完全分离。

---

## 6. 增量扫描的特殊边界情形（Live 特殊性澄清）

团队原任务书担心的"增量模式下过去 BO 要不要追溯补算"——**在 live 下不存在这个问题**：

### 6.1 Live 是每日全量重跑

- `_step1_download_data`：每天用 `multi_download_stock(..., clear=False)`，akshare 的 `stock_us_daily` **每次都返回全部历史**，pkl 文件被整个覆盖（非 append）。
- `_step2_scan`：`ScanManager.parallel_scan` 内部为每只股票新建 `BreakoutDetector`（`_scan_single_stock` → `compute_breakouts_from_dataframe` → `BreakoutDetector(...)`），**不复用前一天的 detector 状态**。
- 没有 `detector.add_bar(single_bar)` 的流式调用。

### 6.2 含义

1. **"idx 刚过某因子 buffer 时要不要追溯补算"** 的问题不存在——每天都是干净重放，每个 BO 的因子值按当天重算的 detector state + 当天完整 df 算，和"昨天的 detector 状态"无关。
2. **过去 BO 不会被"锁定"成 unavailable**——今天扫的时候，去年某只股票 idx=200 的 BO 依然在 idx=200 位置，它的 overshoot 依然因为 idx<252 而 None。每天都一样。
3. **用户视角**：不会感知"昨天的 BO 今天解锁了"的奇怪行为。

### 6.3 有一个隐性影响：df 窗口长度

`daily_runner._step1` 下载 `self.scan_window_days + 400` 天（默认 90+400=490 日历天），即：
- `preprocess_dataframe` 再按 `max(VOLUME_LOOKBACK_BUFFER=63, ANNUAL_VOL_LOOKBACK_BUFFER=252)` ≈ 252 trading days × 1.65 ≈ 416 日历天做 buffer 截断。
- 490 日历天刚好能覆盖 252 trading × 1.65 + 近 90 天扫描窗 ≈ 455 天，**有余量**。

**per-factor gate 后对这个不影响**：df 预处理的 `required_trading_days=252` 是 "pandas rolling 需要的历史长度"，和 detector 的 BO gate 无关，**不会因为 gate 消除而减少下载量**。scanner.py:243 注释也说得很清楚：max_buffer 只影响 BO 级 gate，不影响 df 预处理。

**但有个值得注意的次级效应**：gate 消除后，idx ∈ [252-buffer, 252] 区间的 BO 会出现。如果这些 BO 匹配到 template（尤其是只含 age/test/height/streak/drought 的"短 buffer 模板"），它们的图表显示需要从 pkl 文件的该 index 反推显示——pkl 文件必须有足够早的历史。当前 490 天下载对于 scan_window=90 是足的，但**若用户把 scan_window_days 调大到接近 400**，早段 BO 的历史窗就可能不足（chart 会显示空白 gap）。这是 edge case，当前 config 默认值安全。

---

## 7. 持久化兼容策略

### 7.1 旧 cache → 新代码

- **加载鲁棒性**：`load_cached_results` 用白名单过滤 + `dataclass` 默认值，**向前兼容**。新代码加 `gate_mode` 字段，旧 JSON 加载走默认。
- **语义解读**：旧 cache 的 BO 集是旧语义下产的，但渲染不依赖 gate_mode 元数据，**不会出错**。只是可能会让用户困惑"我重新扫一下，BO 数变了"。
- **建议 UI 提示**：toolbar 的 status 显示 `gate_mode=bo_level (legacy cache, suggest refresh)` 文案，非阻塞。

### 7.2 新 cache → 旧代码（不常见，但要考虑）

若用户降级回旧代码，加载新 cache：
- `MatchedBreakout` 加了新字段（若未来还加）——白名单过滤丢弃，不崩。
- `factors` dict 含 None 值——旧代码 DetailPanel 会崩（因为旧代码没改 `_fmt`）。这是**旧代码的问题，非本次改动引入**。
- 可接受：项目无官方降级路径，降级自行承担风险。

### 7.3 factor_diag/filter.yaml 与 cache 的跨版本

Trial 的 `filter.yaml` 是挖掘产出，不在 live cache 路径上。Trial 升级要看 mining-pipeline 成员的建议，live 只是消费者。**Live 不存储 filter.yaml 到 cache**——每次启动 `TrialLoader(config.trial_dir).load()` 重新读文件（app.py:42），所以 trial 更新会立即生效。

---

## 8. 用户可见性评估

### 8.1 Live UI 用户几乎感知不到变化

**不变的**：
- 界面布局、列表行为、图表渲染路径（live_mode 分支不读因子）。
- Filter 交互（Date/Price/Score 过滤器语义不变）。
- Sentiment 列的语义。
- 星标规则（`sentiment_score > 0.30`）。
- 键盘导航、图表 pick、companion/current 高亮。

**会变的**：
- 候选列表**可能增多**（idx<252 的 BO 有机会命中短 buffer 模板）。实际数量取决于 template 是否依赖 volatility 因子——若 trial top-1 模板包含 overshoot/day_str/pbm，新增数量接近 0（missing-as-fail）；若模板只用 age/height/streak，新增会可观。
- 候选列表**可能质量分布漂移**：drought/streak 诚实化后，早段模板的 median 会变（挖掘端的事，但 live 感知是"有些分数边缘的候选出现/消失"）。

### 8.2 是否需要用户学新概念？

**不需要**。Live 的交互完全建立在 MatchedBreakout 的高层字段（symbol/date/price/sentiment_score）上，per-factor gate 是扫描层的实现细节，不向用户暴露。

**唯一可能出现的新 UX 元素**：DetailPanel 的 Factors 行可能显示 `volume=N/A`（若 bo 因 lookback 不足而 None）。这是合理的显示，不需要解释"per-factor gate"——用户只看到"这个因子没数据"，心智模型简单。

### 8.3 团队目标符合度

团队目标是"发生在底部，用户使用不受影响"。Live 完美符合：
- 改动发生在 detector + feature + scorer 层（"底部"）。
- Live UI 仅一处 5 行的防御性改动（`_fmt` 加 None 分支）。
- 无新概念进入用户视野。
- 图表、列表、筛选、导航全部不变。

---

## 9. 跨成员协作点

### 9.1 给 detector-arch 的请求

- 请确认：`_serialize_factor_fields`（scanner.py:28-39）的序列化在 nullable 扩展后，**所有 lookback 因子都走 `None → None` 分支**（而不是 `None → 0.0`）。live 依赖这个来让 `MatchedBreakout.factors` 的值保留 None 语义；如果这里被填成 0.0，live 就失去了区分"不可用"和"真 0"的能力。
- 请确认：`scan_metadata` 是否新增 `gate_mode` 字段。如果加了，live 虽然不存 scan_metadata，但 ScanManager 对 live 的暴露需一致（目前 ScanManager 不返回 metadata，只 parallel_scan 返回 list[dict]，metadata 仅 `save_results` 时写入）。

### 9.2 给 scorer-ui 的通知

- Live **不复用** `ScoreDetailWindow` / `score_tooltip`。你的 `FactorDetail.unavailable` 扩展对 live 透明，live 不需同步改。
- 但请保持 scanner 输出的 bo dict 中 `quality_score` 字段语义：**factors 可能 None，但 quality_score 本身应保持 float 或 None**（取决于 scorer 的 total_score 是否因所有因子都 None 而退化为 base_score；这个对 live 不关键，因为 live_mode 不展示 quality_score）。

### 9.3 给 mining-pipeline 的建议

- Trial 的 filter.yaml 在 per-factor gate 切换后语义发生漂移（因子分布变），**live 侧建议**：为每个 trial 在 filter.yaml 里加一个 `_meta.gate_mode` 字段，让 `TrialLoader` 可以检测"当前代码 gate_mode vs trial 训练 gate_mode"不匹配并提示。
- Live 仅读 top-1 template 和 thresholds，对因子阈值的改动会自动生效——不需要 live 代码配合。

### 9.4 给 team-lead 的 3 个最关键发现

1. **Live 完全复用 `ScanManager.get_max_buffer()`**，自己不干预——改造下沉到 detector 层后 live 自动继承，**无需 live 主动改扫描调用**。
2. **唯一确定的崩溃点**：`detail_panel._fmt` 不处理 `None`，而新方案下 `MatchedBreakout.factors` 的值字典会含 None。这是必须改的 5 行代码。
3. **Live **不复用 dev UI 的 score_tooltip**——live_mode 渲染路径独立，用户不看因子 level 明细，所以 scorer-ui 成员的改动对 live 透明。只存在一个轻量 CachedResults schema 扩展（加 `gate_mode` 字段）可做可不做，属于可选增强。

---

## 10. 附录：Live 改动点速查表

| 文件 | 位置 | 改动类型 | 必要性 |
|---|---|---|---|
| `live/panels/detail_panel.py` | `_fmt`（第 11-14 行） | 加 None → "N/A" 分支 | **必须** |
| `live/pipeline/results.py` | `CachedResults` | 新增 `gate_mode` 字段 + `load_cached_results` 用 `.get()` 读 | 可选 |
| `live/panels/toolbar.py` | - | （若 §7.1 建议采纳）增加 legacy cache 提示 | 可选增强 |
| `live/pipeline/trial_loader.py` | - | （若 mining 侧配合）读取 filter.yaml 的 `_meta.gate_mode` 做版本检查 | 可选增强 |

Live 主干（scan/match/sentiment/render）**无需任何改动**，自动继承 detector 层的新语义。
