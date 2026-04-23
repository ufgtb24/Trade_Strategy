# Dev UI vs Live UI K 线图数据流差异风险分析

## 1. 差异点清单

| 维度 | Dev UI | Live UI | 风险评级 |
|---|---|---|---|
| chart df 来源 | `preprocess_dataframe` → `_trim_df_for_display` | 原始 pkl（`pd.read_pickle`） | **medium** |
| chart df 含 MA/ATR 列 | 是 | 否 | **low** |
| chart df 起点 | scan_start（前置 buffer 被裁掉） | pkl 起点（≈T-580） | **low** |
| chart df 终点 | scan_end + label buffer | pkl 终点（≈T） | **none** |
| BO index 偏移 | 有（`_adjust_breakout_indices`） | 无 | **medium** |
| 初始视口 | 全范围展开 | 最近 180 天右对齐 | **none** |
| zoom out 极限 | scan_start ~ scan_end + label buffer | pkl 起点 ~ pkl 终点 | **low** |
| label buffer 灰色区 | 有 | 无 | **none** |
| peak/BO 检测范围 | [scan_start, scan_end] | [T-180, T] | **none** |

---

## 2. 各差异点详细分析

### 2.1 chart df 无 MA 列（risk: low）

**现状**：Live UI 在 `app.py:254` 直接 `pd.read_pickle(pkl_path)` 获取 chart df，不经过 `preprocess_dataframe`，因此 df 中不含 `ma_200` 列。

**MA 渲染行为**：`markers.py:530-539` 的 `draw_moving_averages` 有明确的 fallback 逻辑：
```python
ma_col = f"ma_{period}"
if ma_col in df.columns:
    ma_series = df[ma_col]
elif len(df) >= period:
    # 回退：实时计算
    ma_series = df["close"].rolling(window=period).mean()
else:
    continue  # 数据不足，跳过
```

Live UI 的 pkl 有 ≈580 日历天 ≈ 400 交易日的数据，`len(df) >= 200` 恒成立，因此 MA200 通过 `rolling(200).mean()` 实时计算。

**风险**：
- **不会崩溃**：fallback 路径完全可用。
- **前 199 条为 NaN**：rolling 均线的前 199 个值为 NaN，matplotlib `ax.plot` 会自动跳过 NaN 段。由于 pkl 起点 ≈ T-580，而 MA200 需要 200 交易日 ≈ 295 日历天热身，NaN 段大约覆盖 [T-580, T-285]，远在初始视口 [T-180, T] 之外。用户 zoom out 时才可能看到 MA 线断裂处，这是可接受的。
- **与 Dev UI 的差异**：Dev UI 通过 `preprocess_dataframe` 预计算 MA，前置 buffer 确保 scan_start 处 MA 已收敛。但 `_trim_df_for_display` 裁掉了前置 buffer，所以 Dev UI 的 display_df 的 MA 从第一行起就有值。Live UI 的 MA 在 display 范围的前端有 NaN 断裂。用户 zoom out 到极限时能观察到差异，但对 [T-180, T] 视口内完全无影响。
- **ATR 列**：Live UI 的 chart df 无 ATR 列，但 ATR 仅用于 tooltip 显示（`canvas_manager.py:66`）。`canvas_manager._attach_hover` 中会检查 `"atr" in df.columns`，缺失时 tooltip 不显示 ATR 信息。这是一个**功能缺失**，不是 crash 风险。

**结论**：low risk。MA 渲染不崩溃、不错位。tooltip 缺少 ATR 是小的功能缺失。

---

### 2.2 chart df 来源差异与 scanner df 行数一致性（risk: medium）

**核心假设**：Live UI 假设 "scanner df 与 chart df（pkl）行数相同"，因此 BO/peak 的 `index`（整数行号）可以直接映射到 chart df 的 `df.iloc[index]`。

**验证过程**：

1. **`daily_runner.py:93`** 下载 `scan_window_days + 400 = 580` 日历天数据保存为 pkl。
2. **`daily_runner.py:118-120`** 通过 `ScanManager` 调用 `_scan_single_stock`，传入 `start_date = T-180`, `end_date = T`。
3. **`scanner.py:259`** 在 `_scan_single_stock` 中调用 `preprocess_dataframe(df, start_date, end_date, ...)`。
4. **`scanner.py:82-93`** `preprocess_dataframe` 计算：
   - 前截：`buffer_start = T-180 - 415天 = T-595`。pkl 起点 ≈ T-580。因为 `T-595 < T-580`，前截条件 `df.index >= T-595` 不截任何行。
   - 后截：`buffer_end = T + 30天`。pkl 终点 ≈ T。因为 `T+30 > T`，后截条件 `df.index <= T+30` 不截任何行。
   - **结论：scanner df = pkl 全量行 + MA/ATR 列。行数相同。**

5. **`app.py:254`** chart df = `pd.read_pickle(pkl_path)`，无任何截取。

**因此在当前默认参数下（scan_window=180），scanner df 行数 == chart df 行数，假设成立。**

**假设破裂场景**：

| 场景 | 会破裂吗？ | 分析 |
|---|---|---|
| `scan_window_days` 增大到 >165 | 否 | `buffer_start = T-scan_window-415`，pkl 有 `T-scan_window-400` 天数据。只要 `scan_window + 415 > scan_window + 400`（恒真），前截不生效。 |
| `scan_window_days` 减小（如 60） | 否 | `buffer_start = T-60-415 = T-475`，pkl 有 `T-460` 天数据。`T-475 < T-460`，前截仍不生效。 |
| pkl 被外部截断（手动编辑、下载失败部分写入） | **是** | 如果 pkl 实际行数少于预期，`preprocess_dataframe` 的前截可能生效（当 pkl 起点晚于 `buffer_start` 时不截，但如果 pkl 数据异常短，后续计算的 valid_start_index 可能不同）。但这是异常场景，不属于正常运行。 |
| `preprocess_dataframe` 的时间过滤遇到 `>=` vs `>` 边界差异 | **极端情况可能** | `df[df.index >= buffer_start]` 和 `pd.read_pickle` 的 index 在边界日期上有精确到纳秒的差异可能导致 ±1 行。实际中，pkl 的 DatetimeIndex 通常是日级别的 `00:00:00`，`pd.Timedelta(days=...)` 也是整天，不太可能出现亚天精度的差异。 |
| pkl 被更新但 scan cache 未刷新 | **是** | `app.py:254` 读取当前 pkl，但 scan cache 里的 BO index 是基于上次扫描时的 pkl。如果两次扫描之间 pkl 被重新下载（前复权调整改变了历史价格行数），BO index 可能指向错误的行。但 `LiveApp._on_startup` 的逻辑（`freshness.py`）在检测到数据过时时会触发重新扫描，正常流程不会命中此场景。 |

**风险评估**：在当前参数配置和正常运行流程下，假设不会破裂。但这是一个**隐性耦合**——它依赖于 `daily_runner.py:93` 的 `days_from_now = scan_window_days + 400` 恰好大于 `preprocess_dataframe` 的 `buffer_days = max(200,63,252) * 1.65 = 415`。如果未来 `TRADING_TO_CALENDAR_RATIO` 增大或新增更长的回看窗口，这个余量可能不够。

---

### 2.3 BO index 偏移的不同处理方式（risk: medium）

**Dev UI 路径**：
- `main.py:273-280`：先 `_trim_df_for_display` 裁掉前置 buffer（得到 `index_offset`），再 `_adjust_breakout_indices(breakouts, index_offset)` 将所有 BO/peak 的 `.index` 减去偏移量。
- 这样 BO.index 映射到 display_df 的 `df.iloc[bo.index]` 就是正确的行。

**Live UI 路径**：
- `app.py:259-261`：`adapt_peaks` 和 `adapt_breakout` 直接使用 `raw_bo["index"]` / `raw_peak["index"]`，不做偏移。
- chart df = pkl 全量，scanner df = pkl 全量 + MA/ATR。行数相同，所以 index 直接可用。

**Marker 错位风险**：

检查 `markers.py` 中 `draw_peaks:94` 和 `draw_breakouts:200`：
```python
peak_x = peak.index  # 整数索引
# ...
if has_high and 0 <= peak_x < len(df):
    base_price = df.iloc[peak_x][high_col]
```

以及 `draw_breakouts_live_mode:341`：
```python
bo_x = bo.index
base_price = (
    df.iloc[bo_x][high_col] if has_high and 0 <= bo_x < len(df) else bo.price
)
```

所有 marker 绘制都用 `df.iloc[index]` 获取价格。如果 index 与 df 行数不匹配，会：
1. 如果 `index >= len(df)`：回退到 `bo.price`，marker 位置使用 BO 记录的价格而非 K 线实际价格。轻微偏差，不崩溃。
2. 如果 `index < 0`：`0 <= peak_x < len(df)` 检查通过（Python 负索引不等于期望行为），但 `df.iloc[-1]` 会取到最后一行。**这是一个 defensive 漏洞**，但在当前流程中 index 不会为负。

**当前风险**：在正常运行中不会出现 marker 错位。但两套不同的 index 映射策略增加了维护者的认知负担。

---

### 2.4 canvas_manager 处理两种 df 格式的复杂度（risk: low）

**实际影响点**：

1. **MA 渲染**（`canvas_manager.py:260-270`）：`draw_moving_averages` 自带 fallback，无需 canvas_manager 区分。
2. **ATR tooltip**（`canvas_manager.py:66`）：`_attach_hover` 检查 `"atr" in df.columns`。Live UI 无 ATR 列时 tooltip 不显示 ATR。不需要显式分支。
3. **label_buffer_start_idx**（`canvas_manager.py:273-274`）：Live UI 传 `None`，不绘制灰色区。
4. **live_mode 分支**（`canvas_manager.py:231-244`）：已通过 `display_options["live_mode"]` 显式切换 `draw_breakouts` vs `draw_breakouts_live_mode`。
5. **initial_window_days**（`canvas_manager.py:291`）：`None` → 全展开，`180` → 右对齐 180 天。统一处理。

**结论**：canvas_manager 对两种 df 格式的适配是**隐式的**（通过 column 存在性检查和参数默认值），而非显式 if/else 分支。这减少了代码量但增加了隐性假设。如果未来 Live UI 也需要 label buffer 灰色区或 Dev UI 也需要 4-tier BO 渲染，需要新增代码，但不需要重构现有逻辑。

---

### 2.5 zoom out 可见范围 vs 检测范围不一致（risk: low）

**现象**：Live UI 用户可以 zoom out 到 T-580，但 peak/BO 只在 [T-180, T] 范围内存在。用户看到 T-580 到 T-180 之间有 400 天的"空白"K 线（无任何 peak/BO 标记）。

**用户体验影响**：
- 可能困惑："为什么这段时间没有任何突破标记？"
- 但这不是 bug——预热 buffer 区确实不应产出 peak/BO。
- Dev UI 通过 `_trim_df_for_display` 裁掉了预热 buffer，用户看不到这些"空白"区域。

**是否需要修复**：这是一个**UX 不一致**，不是功能 bug。可以通过以下方式缓解（不在本分析范围内实现）：
1. 限制 zoom out 极限到 scan_window 范围附近
2. 在预热 buffer 区域画浅灰背景标注"历史参考区"

---

## 3. 隐性假设破裂场景枚举

### 场景 A：pkl 更新 + cache 不刷新

**触发条件**：用户手动替换 `datasets/pkls_live/XXX.pkl`（如用新脚本下载），但不触发 Live UI 的 pipeline 重新扫描。

**后果**：`app.py:254` 读到新 pkl（可能行数变化），但 `CachedResults` 里的 `raw_breakout["index"]` 基于旧 pkl。Marker 指向错误的 K 线。

**缓解**：当前 `DataFreshnessChecker` 对比 `.last_full_update` marker 文件日期和最新 pkl 的修改时间，会检测到不一致并提示重新扫描。但如果用户拒绝重新扫描并使用旧 cache，就会命中此问题。

**严重性**：medium——用户可观察到 marker 明显错位，但不会导致 crash。

### 场景 B：preprocess_dataframe 缓冲区计算常量变更

**触发条件**：`TRADING_TO_CALENDAR_RATIO` 从 1.65 增大（如改为 2.0），或新增比 `ANNUAL_VOL_LOOKBACK_BUFFER=252` 更长的回看窗口。

**后果**：`buffer_days = required_trading_days * ratio` 增大，`buffer_start` 可能早于 pkl 起点。但因为 `df[df.index >= buffer_start]` 在 buffer_start 早于 pkl 起点时不截行，所以**实际不影响行数**。

不过反方向的场景更危险：如果 `daily_runner.py:93` 的 `days_from_now = scan_window_days + 400` 中的 400 被减小（如改为 300），pkl 数据变短，而 `preprocess_dataframe` 的前截开始生效，scanner df 行数 < pkl 行数，index 偏移出现。

**严重性**：high（如果发生）——但当前代码无此问题。

### 场景 C：pkl 含非交易日的脏数据

**触发条件**：akshare 返回的数据包含周末/节假日的行（价格为 0 或重复）。

**后果**：`preprocess_dataframe` 不做脏数据清洗。`pd.read_pickle` 也不做。两边行数仍一致，但 BO 的 `index` 可能指向脏行，marker 位置正确但价格标注可能异常。

**严重性**：low——akshare 的 US stock daily 数据通常不含非交易日行。

### 场景 D：scanner 的股票级预筛（volume filter）截断 df

**检查**：`scanner.py:244-248` 中 `scan_df = df.copy()` 只是用于检查平均成交量，不修改传给 `preprocess_dataframe` 的 `df`。所以**不影响行数**。

**严重性**：none。

---

## 4. 结论：当前差异的总体风险评估

### 总体判断：**可以共存，但需要文档化隐性约束**

当前两套数据流在正常运行条件下不会产生 bug。关键隐性假设（"scanner df 与 pkl 行数相同"）在当前参数配置下恒成立，且有 `DataFreshnessChecker` 作为安全网。

**不构成"迫切需要统一"的理由**：
1. 无 crash 风险：MA 渲染有 fallback，index 越界有 defensive 检查。
2. 无 marker 错位：正常流程下 scanner df 与 pkl 行数恒等。
3. UX 差异是合理的：Dev UI 面向回测分析（需要 label buffer 灰色区），Live UI 面向实盘监控（不需要 label buffer）。
4. 维护复杂度可接受：canvas_manager 通过参数化（`live_mode`、`initial_window_days`、`label_buffer_start_idx`）而非 if/else 分支处理差异，新增需求不需要重构。

**需要注意的事项**：
1. **`daily_runner.py:93` 的 `+400` 必须始终 >= `preprocess_dataframe` 的 `buffer_days`**（当前 415）。如果修改任一常量，需同步检查。建议在代码中加注释标注此约束。
2. **Live UI tooltip 缺少 ATR 信息**是一个小功能缺失，可按需修复（在 `_rebuild_chart` 中对 chart df 计算 ATR，或改用 preprocess_dataframe 的输出）。
3. **pkl 手动替换场景**应在用户文档中警告"替换 pkl 后需重新运行 pipeline"。

### 三个最关键发现

1. **scanner df 与 pkl 行数相等的假设成立但脆弱**：依赖 `daily_runner:93` 的 `+400` >= `preprocess_dataframe` 的 `buffer_days=415` 这一数值巧合（当前 400 < 415，但因为 pkl 起点早于 buffer_start 所以不截行）。这个关系不是显式代码保证的，而是两个独立常量的数值关系碰巧满足。

2. **Live UI 的 MA 渲染走 fallback 路径（实时 rolling 计算）**：功能正确但与 Dev UI 的预计算路径不一致。在初始视口 [T-180, T] 内无差异，zoom out 到极限时 Live UI 的 MA 线前端有 NaN 断裂而 Dev UI 没有。

3. **Live UI tooltip 缺失 ATR 数据**：chart df 无 `atr` 列，`canvas_manager._attach_hover` 的 ATR 相关逻辑静默跳过。这是唯一一个对用户可见的功能差异，但不影响核心图表功能。
