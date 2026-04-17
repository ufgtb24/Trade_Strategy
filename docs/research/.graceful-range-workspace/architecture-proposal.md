# Graceful Range Degradation — 架构提案

> 日期：2026-04-16
> 作者：architect（team "graceful-range-degradation"）
> 依据：`current-behavior.md`（code-archaeologist）+ `chart-data-unification-analysis.md` Direction A

---

## 0. 执行摘要（TL;DR）

**核心判断**：
- 当前代码**已经天然是 graceful degradation 的**（preprocess / detector / features 对"缺数据"的反应都是缩窗或返回 None，**从不 raise**）。
- "理想约束 → 实际降级"不是需要新增的行为，而是**需要显式命名的既有事实**。
- Direction A（Live 向 Dev 对齐）的总体改动方向正确，但**必须升级为三层显式范围模型**：`ideal / actual / display`。
- 用户提出的"3 年显示窗口独立于扫描范围"是**数据流与 UI 语义解耦**的关键一步，应当采纳。

**推荐方案**：**Direction A++（显式三层范围 + 元数据透传 + UI 降级提示）**。Live 改动量相比 Direction A 增加约 50 LOC（元数据携带 + UI 提示），总计 ~130–170 LOC / 5 文件。Dev UI 改动 < 20 LOC（只读元数据，不改 trim/adjust 逻辑）。

---

## 1. 对 Graceful Degradation 哲学的架构性评估

### 1.1 已知工程陷阱

| 陷阱 | 描述 | 本项目是否会中招 |
|------|------|----------------|
| **隐式差异** | 同一配置在不同数据量下产生不同结果，用户难以复现 bug | ⚠️ **会**。Case B（scan_start 被 pkl 起点覆盖）目前完全无声 |
| **错误信号屏蔽** | "永不报错"把真实数据损坏（corrupt pkl、日期空洞）也降级掉 | ⚠️ 中等。目前无任何校验，损坏的 pkl 会走完整流程并产出少数 BO |
| **隐式契约漂移** | 降级行为依赖 pkl 起点等不变量，参数调整时无声破裂 | ⚠️ **会**（Direction A 原报告已识别 F1） |
| **二阶因果** | 某因子降级为 None → 下游聚合（平均分）把该样本排除 → 统计结果悄悄偏斜 | 低。per-factor gate 的 None 处理已显式，下游 mining 有过滤 |
| **测试盲区** | 降级路径不会报错，CI 里即使 pkl 缺失也"通过" | ⚠️ 中等。需要引入"声明降级已发生"的可观测 hook |

**结论**：陷阱真实存在，但**多为可观测性问题而非正确性问题**。补救方式是**让降级"可见"而非消除降级本身**。

### 1.2 是否与项目哲学冲突

| 原则 | 评估 |
|------|------|
| **第一性原理** | ✅ **契合**。首要事实是"pkl 是真实世界数据，有完整性缺陷"；理想约束是推导量。把两者分开表达是回到第一性原理。 |
| **奥卡姆剃刀** | ⚠️ **需警惕**。若为每个范围引入 `_ideal / _actual / _degraded_reason / _degraded_log` 四套字段，会变成过度设计。原则：**只给用户会看到差异的范围引入双值**，其余保持单值。 |
| **反过度设计** | ✅ 通过"最小元数据 + 单一降级检测点"达成（详见 §3.2）。 |

### 1.3 关键决策：降级的"可见性原则"

**任何降级必须在三处之一可见**：
1. **日志**（stderr/INFO）— 对开发者
2. **返回值元数据**（DataFrame.attrs 或新 dataclass 字段）— 对程序
3. **UI 视觉信号**（状态栏文字、图表阴影）— 对终端用户

**不满足任何一处的降级 = bug**。这是避免陷阱 1（隐式差异）的底线。

---

## 2. 现状符合度评估

### 2.1 当前代码对 graceful degradation 的支持度

基于 `current-behavior.md`：

| 环节 | 是否已 graceful | 是否已可见 | Gap |
|------|---------------|-----------|-----|
| preprocess buffer 不足（Case A） | ✅ MA 前缀 NaN，不报错 | ❌ 无日志无返回值标记 | 需要元数据 |
| scan_start 早于 pkl（Case B） | ✅ 检测从 pkl 起点开始 | ❌ 完全静默（仅 DEBUG_VOLUME 可见） | **最严重**，必须修 |
| scan_end 晚于 pkl（Case C） | ✅ 用到最新数据 | ⚠️ label_buffer 着色混乱（Case E） | UI 逻辑需修 |
| label buffer 不足（Case D） | ✅ label=None | ✅ 下游 mining 有 None 处理 | 可接受 |
| UI trim 边界（Case E） | ⚠️ 原样返回整个 df | ❌ label_buffer 着色误导 | 需修 |

**判断**：**数据层已 graceful，可见性层完全缺失**。

### 2.2 Direction A 对 graceful 哲学的符合度

Direction A 的核心是"Live 复用 Dev 的 preprocess→trim→adjust"。它：

| 方面 | 评估 |
|------|------|
| 是否消除隐式 BO index 契约 | ✅ 消除（Live 不再依赖"pkl 行数 == scanner df 行数"） |
| 是否处理 pkl 起点晚于 scan_start | ⚠️ **未显式考虑**。`_trim_df_for_display` 当 `mask.any()==True` 时返回 `first_idx=0`，但这其实是降级，原设计未命名 |
| 是否支持 display 独立于 scan | ❌ Direction A 的 `display_df = trim(scan_start, scan_end+label_buffer)`，display 范围仍由 scan 决定 |
| 是否提供降级元数据 | ❌ 无 |
| 是否有 UI 可见信号 | ❌ 无 |

**Direction A 正确但不够**。用户新需求（三层解耦 + graceful 可见）需要在 A 之上加**元数据透传**和**UI 语义区**。

### 2.3 三层解耦对 graceful 的天然支持

用户提议的 `scan / compute / display` 三层，其中 `display` 独立于 `scan`（`display_start = min(scan_start, display_end - 3y)`）。这个解耦带来三个好处：

1. **display 范围只受 pkl 约束** — 即使 scan_start 被 pkl 降级了，display 仍能展示完整 3 年历史
2. **degraded 信号有视觉承载** — `[display_start, scan_start_actual]` 是天然的"非扫描区"灰色阴影区
3. **Live/Dev 差异回归本质** — 差异只剩"Live 有 3 年下限兜底，Dev 无"，而非两套数据流

**结论**：三层解耦不是额外负担，而是 graceful degradation 的**天然可视化容器**。

---

## 3. 改进架构设计

### 3.1 三层范围的显式建模

引入新 dataclass `ChartRangeSpec`，携带三层范围的 ideal/actual 双值：

```
@dataclass(frozen=True)
class ChartRangeSpec:
    # --- Scan layer (用户意图) ---
    scan_start_ideal: date       # 用户/pipeline 请求的 scan 起点
    scan_end_ideal: date         # 用户/pipeline 请求的 scan 终点
    scan_start_actual: date      # 实际扫描起点（可能被 pkl 起点降级）
    scan_end_actual: date        # 实际扫描终点（可能被 pkl 终点降级）

    # --- Compute layer (推导量) ---
    compute_start_ideal: date    # scan_start_ideal - compute_buffer
    compute_start_actual: date   # 实际 preprocess 可用起点 = max(compute_start_ideal, pkl_start)
    label_buffer_end_ideal: date # scan_end_ideal + label_buffer
    label_buffer_end_actual: date # min(label_buffer_end_ideal, pkl_end)

    # --- Display layer (视觉) ---
    display_start: date          # min(scan_start_actual, display_end - display_min_window)
    display_end: date            # 通常 = pkl_end（Live）或 label_buffer_end_actual（Dev）

    # --- Degradation flags ---
    @property
    def scan_start_degraded(self) -> bool:
        return self.scan_start_actual > self.scan_start_ideal

    @property
    def compute_buffer_degraded(self) -> bool:
        return self.compute_start_actual > self.compute_start_ideal

    @property
    def scan_end_degraded(self) -> bool:
        return self.scan_end_actual < self.scan_end_ideal
```

**设计要点**：
- **不是每个范围都有 ideal/actual**。`display_*` 和 `label_buffer_end` 只保留单值，因为它们是推导量的最终落点，degraded 状态已在上游字段中表达。
- **frozen dataclass** — 避免在渲染链中被意外修改。
- **降级用 property 派生**，不持久化为独立字段 — 遵循奥卡姆剃刀，唯一事实源是 ideal/actual 双值。

### 3.2 preprocess_dataframe 的接口演进

当前签名：
```
preprocess_dataframe(df, start_date, end_date, label_max_days, ma_periods, atr_period) -> DataFrame
```

**提案：不改签名，增加返回的元数据**（通过 `DataFrame.attrs`）：

```
def preprocess_dataframe(df, start_date, end_date, ...) -> pd.DataFrame:
    # ...existing logic (unchanged)...
    out = df  # after filtering + MA/ATR computation

    out.attrs["range_meta"] = {
        "pkl_start": df_original.index[0].date() if len(df_original) else None,
        "pkl_end": df_original.index[-1].date() if len(df_original) else None,
        "compute_start_ideal": buffer_start.date(),
        "compute_start_actual": out.index[0].date() if len(out) else None,
        "scan_start_ideal": pd.to_datetime(start_date).date() if start_date else None,
        "scan_end_ideal": pd.to_datetime(end_date).date() if end_date else None,
        "label_buffer_end_ideal": buffer_end.date() if end_date else None,
        "label_buffer_end_actual": out.index[-1].date() if len(out) else None,
    }
    return out
```

**为什么走 `attrs` 而非改签名**：
- `attrs` 是 pandas 官方的元数据附着机制（pandas ≥ 1.0），天然随 df 传递
- **向后兼容**：所有调用方（scanner / UI / live / mining）不读 attrs 时零影响
- 避免 Direction A 所担心的 "改签名需要修改所有 callsite" 问题
- 缺点：`attrs` 在某些 df 操作（concat/merge）下会丢失 — 本场景 df 不经过这些操作，安全

**不引入 fallback flag**：当前的"无声降级"本身就是正确行为，增加 flag 只会让调用方分岔为 "strict mode / graceful mode"，违反第一性原理。Graceful 是**唯一行为**，flag 只会是反模式。

### 3.3 BO 检测的 valid_start_index 调整

当前代码（`scanner.py:274-302`）已正确处理 "scan_start 早于 df 起点 → valid_start_index=0"（见 `current-behavior.md` §B2）。

**无需改算法**，只需在计算后**记录降级事实**：

```
# scanner.py compute_breakouts_from_dataframe
valid_start_index = 0
if scan_start_date:
    scan_start_dt = pd.to_datetime(scan_start_date)
    mask = df.index >= scan_start_dt
    if mask.any():
        valid_start_index = mask.argmax()
    # NEW: 降级检测
    scan_start_actual_dt = df.index[valid_start_index]
    if scan_start_actual_dt > scan_start_dt:
        logger.info(
            "scan_start degraded: requested=%s, actual=%s (pkl starts later)",
            scan_start_date, scan_start_actual_dt.date()
        )
        # 写入 df.attrs 供上层消费
        meta = df.attrs.get("range_meta", {})
        meta["scan_start_actual"] = scan_start_actual_dt.date()
        df.attrs["range_meta"] = meta
```

`scan_end` 端同理处理。关键是**唯一事实源在 df.attrs**，不散落到函数参数和返回值。

### 3.4 UI 降级可见性设计

#### 3.4.1 Dev UI（`UI/main.py`）

**状态栏**：
```
# 现状
param_panel.set_status(f"{symbol}: Computed {N} breakout(s)", "green")

# 改后
meta = df.attrs.get("range_meta", {})
degraded_msgs = []
if meta.get("scan_start_actual") and meta["scan_start_actual"] > meta["scan_start_ideal"]:
    degraded_msgs.append(f"scan_start→{meta['scan_start_actual']}")
if meta.get("compute_start_actual") > meta["compute_start_ideal"]:
    degraded_msgs.append("MA buffer short")

status = f"{symbol}: Computed {N} breakout(s)"
if degraded_msgs:
    status += f" [⚠ {', '.join(degraded_msgs)}]"
    param_panel.set_status(status, "orange")
else:
    param_panel.set_status(status, "green")
```

**图表灰色阴影**（新语义）：
- 当前：只在 `[scan_end, scan_end + label_buffer]` 画灰色（表示 label buffer）
- 改后：三段语义化阴影
  - `[display_start, scan_start_actual]` — 浅蓝（"pre-scan history"，可选灰）
  - `[scan_start_actual, scan_end_actual]` — 无阴影（主扫描区）
  - `[scan_end_actual, display_end]` — 浅灰（"post-scan / label buffer"）
- 当 `scan_start_actual > scan_start_ideal`，在 `scan_start_actual` 位置画竖虚线 + 文字 "scan start (requested: YYYY-MM-DD)"

#### 3.4.2 Live UI（`live/app.py`）

- MatchList 中被 pkl 降级的 symbol，在列标注 `⚠`
- tooltip 显示 "scan window: [2023-01-15 (req 2023-01-01), 2026-04-15]"
- 图表阴影逻辑与 Dev 一致

**实现收敛**：把 "阴影计算 + 降级文本绘制" 封装进 `canvas_manager.draw_range_spec(spec: ChartRangeSpec)`，Dev/Live 共用同一函数。

### 3.5 Live `days_from_now` 设计

当前：`days_from_now = scan_window_days + 400`（即 90+400=490 天 ≈ 1.35 年）

**问题**：新需求要求 display 至少 3 年（1095 天）。现有下载量远远不够。

**选项分析**：

| 选项 | 下载量 | 优点 | 缺点 |
|------|-------|------|------|
| X1. 刚好 3 年 + compute_buffer | ~1095 + 415 = 1510 天 | 精确满足需求 | 不留缓冲，未来扩展（如 5 年 display）要改代码 |
| X2. 3 年 + compute_buffer + 冗余 | ~1510 + 180 = **1700 天** | 安全垫，应对未来 display 扩展或 MA 周期提升 | 下载略多，每次 +190 天约增 10% 时间/存储 |
| X3. 策略型下载（远期粗粒度） | 分段 | 存储优化 | 复杂度爆炸，违反奥卡姆 |

**推荐 X2：1700 天（≈4.65 年）**。理由：
1. **pkl 是 live runner 每日覆盖式下载**（`daily_runner.py:93`），10% 冗余不累积
2. **3 年下限是硬需求**，0 安全垫在 MA 周期未来提升到 400 时会破裂
3. **奥卡姆满足**：一个常量 `DOWNLOAD_DAYS = 1700`，注释说明其由 `3y display + compute_buffer + safety` 推导

代码改动（`daily_runner.py`）：
```
# 现状
days_from_now=self.scan_window_days + 400,

# 改后
# Display requires 3y history; compute needs ~415d buffer for MA200/vol/annual-vol;
# safety margin for future MA period growth.
DOWNLOAD_DAYS = 1700  # ~4.65 years
days_from_now=DOWNLOAD_DAYS,
```

`scan_window_days` 从下载尺寸解耦，只保留其原意："scan 窗口 = 最近 N 天的 BO 检测区间"。

### 3.6 display_start 的推导

**核心公式**（由用户提出，已确认合理）：
```
display_start = min(scan_start_actual, display_end - DISPLAY_MIN_WINDOW)
display_end   = pkl_end                          # Live
             或 = label_buffer_end_actual         # Dev
DISPLAY_MIN_WINDOW = timedelta(days=1095)        # Live 3 年
DISPLAY_MIN_WINDOW = None                        # Dev（全展开）
```

**边界处理**：
- 若 pkl 起点晚于 `display_end - 3y`，则 `display_start = pkl_start`（再次降级，graceful）
- `display_start` 不参与 trim！display 是**视觉最左边界**，不裁剪数据
- trim 的截断点仍是 `compute_start_actual`（移除无用的极早期 buffer，只保留 [display_start, display_end] 需要的范围）

**统一 trim 逻辑**（替代现有 `_trim_df_for_display`）：
```
def trim_df_to_display(df: pd.DataFrame, spec: ChartRangeSpec) -> tuple[pd.DataFrame, int]:
    """
    裁剪 df 到 display_start 之后。返回 (display_df, index_offset_for_bo_adjust)。
    """
    mask = df.index >= pd.to_datetime(spec.display_start)
    first_idx = mask.argmax() if mask.any() else 0
    return df.iloc[first_idx:].copy(), first_idx
```

注意：`_adjust_breakout_indices` 逻辑不变（仍用 `offset`）。

---

## 4. 与 Direction A 的 Diff 级差异

| 维度 | Direction A 原方案 | Direction A++ 改进方案 | 状态 |
|------|-------------------|---------------------|------|
| Live 走 `preprocess → trim → adjust` | ✅ | ✅ | **不变** |
| `prepare_chart_data()` 封装函数 | 在 `chart_adapter.py` | **移至** `UI/charts/range_utils.py`（Dev/Live 共用） | 🔄 **重构** |
| MatchedBreakout 新增字段 | `scan_start_date`, `scan_end_date`（2 个 str） | **改为** `range_spec: ChartRangeSpec`（单一对象，含 6 个字段） | 🔄 **改进** |
| `_trim_df_for_display` | Dev 私有方法 | **提取为** `trim_df_to_display(df, spec)`，Dev/Live 共用 | 🔄 **重构** |
| `_adjust_breakout_indices` | Dev 私有方法 | **提取为** `adjust_indices(items, offset)`，Dev/Live 共用 | 🔄 **重构** |
| `preprocess_dataframe` 签名 | 不改 | **不改，但写入 `df.attrs["range_meta"]`** | ➕ **新增** |
| `daily_runner.days_from_now` | 保持 `scan_window_days + 400` | **改为** 常量 `1700` | 🔄 **修改** |
| UI 降级可见性 | 无 | **新增** 状态栏警告 + 图表阴影分段 + 竖虚线标注 | ➕ **新增** |
| `display_start` 推导 | 等于 `scan_start` | **独立公式** `min(scan_start_actual, display_end - 3y)` | ➕ **新增** |
| label_buffer 灰色区 | Dev 有, Live 无 | **三段语义化**（pre-scan / main / post-scan），Dev/Live 一致 | 🔄 **改进** |
| `ChartRangeSpec` dataclass | 无 | **新增**，作为图表数据的唯一范围契约 | ➕ **新增** |

**LOC 增量估算**：

| 文件 | Direction A | Direction A++ | Delta |
|------|------------|-------------|-------|
| `live/app.py` | +40/-15 | +45/-20 | +10 |
| `live/chart_adapter.py` | +25 | +10（仅保留 peak/bo 适配） | -15 |
| `live/pipeline/daily_runner.py` | +10 | +5（只改常量） | -5 |
| `live/pipeline/results.py` | +5 | +15（range_spec 字段） | +10 |
| `UI/charts/range_utils.py`（新） | - | +90（trim/adjust/spec） | +90 |
| `UI/main.py` | 0 | +10（状态栏警告） | +10 |
| `UI/charts/canvas_manager.py` | 0 | +40（阴影分段 + 降级标注） | +40 |
| `analysis/scanner.py` | 0 | +15（attrs 写入 + 日志） | +15 |
| **总计** | ~80–120 LOC | ~170 LOC | +50–90 |

改动**略大于 Direction A**，但：
- 消除 Dev/Live 代码重复（共用 range_utils）
- 一次性引入"三层范围 + 降级可见"双重能力
- 后续新增 UI（如 backtest UI）可零额外成本接入

---

## 5. 风险与回退策略

### 5.1 已识别风险

| 风险 | 严重度 | 缓解 |
|------|-------|------|
| `df.attrs` 在某些 pandas 操作下丢失 | 低 | 本流程 df 不经过 concat/merge；单测 pin `attrs` 存在 |
| `ChartRangeSpec` 字段过多导致构造错误 | 中 | 工厂函数 `ChartRangeSpec.from_df_and_scan(df, scan_start, scan_end)` 封装推导逻辑 |
| 阴影语义变化用户一时不适应 | 低 | 保留原 label_buffer 灰色区作为 "post-scan" 段，视觉延续 |
| Live 下载量从 490→1700 天（3.5x）导致首次运行变慢 | 中 | 在 update_confirm 对话框显示预估时间；marker 机制避免重复全量下载 |
| `days_from_now=1700` 触发 akshare 限频 | 低 | akshare 限频按请求次数，不按天数；风险不增 |

### 5.2 分阶段实施建议

**Phase 1（必须）**：`ChartRangeSpec` + `preprocess_dataframe.attrs` + 日志降级通知
→ 这一步**零行为变化**，只增加可观测性。任何时候都可停止且无回退成本。

**Phase 2（Direction A 核心）**：`trim_df_to_display` + `adjust_indices` 提取 + Live 接入
→ Live 图表 BO 对齐契约从隐式变显式，行为对最终用户不变（默认视图）。

**Phase 3（UI 可见性）**：状态栏警告 + 图表阴影分段 + 降级竖线
→ 用户侧可见变化，需要 UX 二次确认。

**Phase 4（Live 下载量调整）**：`days_from_now=1700`
→ 首次运行时间变化，需要在 progress_dialog 提示用户。

Phase 1–2 可合并 PR；Phase 3–4 独立 PR（各自有不同用户影响）。

---

## 6. 设计自检：是否过度设计？

对照奥卡姆剃刀：

| 新增抽象 | 是否必要 | 替代方案是否更简单 |
|----------|--------|----------------|
| `ChartRangeSpec` dataclass | ✅ 必要。6 个日期字段若散落在函数参数里，`update_chart()` 签名会膨胀到不可读 | 散落参数 → 更差 |
| `range_utils.py` 新文件 | ✅ 必要。当前 `_trim_df_for_display` 是 Dev 私有方法，Live 要复用必须提取 | 复制粘贴 → 违反 DRY |
| `df.attrs["range_meta"]` | ✅ 必要。降级事实需要跨函数边界传递 | 全局 var / 重新计算 → 更差 |
| 三段语义化阴影 | ✅ 必要。graceful degradation 的视觉承载 | 仅用状态栏文字 → 图表上降级不可见 |
| `ChartRangeSpec.from_df_and_scan` 工厂 | ✅ 必要。推导逻辑集中，避免 6 处重复 |  构造函数 + 手动填充 → 出错面大 |

**结论**：所有新增抽象都服务于"graceful 可见"这一核心目标，无冗余。

---

## 7. 验收标准

架构提案被认为成功实现，当且仅当：

1. **Graceful 仍然成立**：任何 pkl 缺失/过期场景下，系统不 raise，仍产出尽可能多的 BO。
2. **Graceful 可见**：Case B 场景（scan_start 早于 pkl）必然触发以下三处之一：
   - stderr INFO 日志
   - `df.attrs["range_meta"]["scan_start_actual"]` 值≠ideal
   - UI 状态栏 `⚠` 标记
3. **三层解耦**：修改 `scan_start` 或 `scan_end` 不影响 `display_start / display_end` 的独立推导。
4. **Dev/Live 数据流统一**：`trim_df_to_display` 和 `adjust_indices` 函数在 Dev 和 Live 两处调用，**无第三处内联实现**。
5. **Live 3 年显示**：任意选中一个 BO，图表默认展示至少 3 年历史（除非 pkl 本身不够）。
6. **零破坏性回归**：Dev UI 图表视觉与当前行为一致（除新增阴影分段外）。

---

## 8. 结论

| 决策点 | 结论 |
|--------|------|
| graceful degradation 是否合理 | ✅ 是，且已是当前代码事实行为 |
| 主要 gap | ❌ 可见性层完全缺失（尤其 Case B） |
| Direction A 是否仍有效 | ✅ 方向正确，但需升级为 A++（增加三层范围 + 元数据 + UI 可见） |
| 改进方案是否违反奥卡姆 | ❌ 否，所有新增抽象有明确的必要性 |
| 改动量 | ~170 LOC / 8 文件，分 4 阶段交付 |
| 推荐 | **立即启动 Phase 1（零行为变化）；Phase 2–4 根据优先级排期** |

---

*Team graceful-range-degradation · architect · 2026-04-16*
