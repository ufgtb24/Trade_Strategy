# Chart Data 统一方案：架构提案

## 1. 四个方向对比表

| 维度 | A: Live 向 Dev 对齐 | B: Dev 向 Live 对齐 | C: 抽象公共层 | D: 保持现状 + 最小修复 |
|------|---------------------|---------------------|---------------|------------------------|
| **改动量** | 中（~120 LOC, 3 文件） | 大（~200 LOC, 4 文件）+ UI 副作用 | 大（~250 LOC, 5+ 文件） | 小（~30 LOC, 2 文件） |
| **风险** | 低：Live 补齐 Dev 已验证的逻辑 | 高：删除 Dev 已验证的 trim/adjust 逻辑 | 中：引入新抽象层，过度设计风险 | 最低 |
| **用户影响** | Live MA 从第一根 K 线即有值；图表范围略缩（无多余历史） | Dev 前置 buffer 可见（数百根空白 K 线）；破坏现有体验 | 无感知差异 | 无变化 |
| **推荐度** | **推荐** | 不推荐 | 不推荐 | 可接受（如不追求统一） |

## 2. 推荐方向：A — Live 向 Dev 对齐

### 2.1 核心分析

#### 当前 Live 的隐式契约（已验证，非 bug 但极其脆弱）

Live 的 BO index 对齐之所以"碰巧"正确，基于以下隐式不变量：

```
pkl 数据量 = scan_window_days + 400 = 580 天
scanner preprocess 请求 = [today - 180 - 415, today + 30] = 625 天
```

因为 pkl 只有 580 天数据，preprocess 的 `buffer_start`（today-595）早于 pkl 起始日，`buffer_end`（today+30）晚于 pkl 结束日，所以 **preprocess 实际上未裁剪任何行**，scanner df == raw pkl df。

**风险**：如果任何一个参数变化（scan_window_days 缩小、MA 周期加大导致 buffer 增加、pkl 数据量增加），这个隐式等式就会破裂，BO/peak 标记将画在错误位置。

#### Live 当前 MA 的处理

`draw_moving_averages` (markers.py:530-554) 有 fallback：df 无 `ma_xxx` 列时实时计算 `close.rolling(period).mean()`。因为 Live chart df 无 buffer 前缀，MA200 前 200 根 K 线为 NaN，但因 `initial_window_days=180` 只显示最右 180 天，而 pkl 有 580 天数据，前 200 根 NaN 不可见 —— **当前行为碰巧正确**，但同样脆弱。

### 2.2 方向 A 的详细设计

#### 文件级改动清单

| 文件 | 改动类型 | 估计 LOC | 说明 |
|------|----------|----------|------|
| `live/app.py` | 修改 `_rebuild_chart` | +40, -15 | 用 preprocess → trim → adjust 替换 raw pkl 读取 |
| `live/chart_adapter.py` | 新增函数 | +25 | 添加 `prepare_chart_data()` 封装 preprocess + trim 逻辑 |
| `live/pipeline/daily_runner.py` | 新增元数据传递 | +10 | 在 MatchedBreakout 中携带 scan_start/end_date |
| `live/pipeline/results.py` | 扩展 dataclass | +5 | MatchedBreakout 新增 `scan_start_date` / `scan_end_date` 字段 |

**总计：~80-120 LOC 改动，4 个文件**

#### BO index 对齐策略

**目标**：让 chart df 行数 < scanner df 行数时，BO/peak index 正确映射。

**方案**：

```
# 在 chart_adapter.py 新增
def prepare_chart_data(pkl_path, start_date, end_date, ma_period=200, atr_period=14):
    """复用 scanner 的 preprocess_dataframe，然后执行 Dev UI 的 trim 逻辑。"""
    df = pd.read_pickle(pkl_path)
    
    # Step 1: preprocess（与 scanner 完全一致的 buffer 计算）
    df = preprocess_dataframe(df, start_date, end_date, 
                               label_max_days=0,  # live 无 label buffer
                               ma_periods=[ma_period], atr_period=atr_period)
    
    # Step 2: trim 前置 buffer（与 Dev UI _trim_df_for_display 逻辑一致）
    start_dt = pd.to_datetime(start_date)
    mask = df.index >= start_dt
    first_idx = mask.argmax() if mask.any() else 0
    display_df = df.iloc[first_idx:]
    
    return display_df, first_idx  # first_idx = index_offset
```

**BO index 调整**：与 Dev 一致，`adapt_breakout` 后对每个 `ChartBreakout.index -= offset`。可复用 Dev UI 的 `_adjust_breakout_indices` 逻辑（提取为独立函数，或在 `chart_adapter.py` 中内联）。

#### MA 列处理

preprocess 已计算 `ma_xxx` 列（带 buffer），trim 后 MA 从第一根可见 K 线起就有值。**无需额外处理**——`draw_moving_averages` 会优先读预计算列。

这意味着 Live 的 MA 显示将从"前 200 根为 NaN（但被 initial_window_days 隐藏）"变为"全部有值"，行为更正确。

#### label buffer 处理

Live 无 label buffer（实盘无未来数据）。方案中 `label_max_days=0`，preprocess 不会在 end_date 之后添加缓冲。`label_buffer_start_idx` 传 `None` 给 canvas_manager，灰色区域不绘制。**无需引入 label buffer 概念**。

#### initial_window_days 差异

不属于数据流统一范畴。Dev 用 `None`（全展开），Live 用 `180`（右对齐）。这是显示偏好，各自保留即可。

### 2.3 `_rebuild_chart` 改动后伪代码

```python
def _rebuild_chart(self) -> None:
    current = self.state.current_selected
    if current is None:
        self.chart.clear()
        return

    pkl_path = self.config.data_dir / f"{current.symbol}.pkl"
    if not pkl_path.exists():
        self.chart.clear()
        return

    # 新：走 preprocess → trim → adjust 流程
    display_df, index_offset = prepare_chart_data(
        pkl_path, 
        start_date=self.state.scan_start_date,  # 从 pipeline 元数据获取
        end_date=self.state.scan_end_date,
    )

    chart_active_peaks, chart_superseded_peaks, peaks_by_id = adapt_peaks(current.raw_peaks)
    raw_bos = current.all_stock_breakouts or [current.raw_breakout]
    all_chart_bos = [adapt_breakout(raw_bo, peaks_by_id) for raw_bo in raw_bos]
    
    # 新：调整 index（与 Dev UI 一致）
    all_chart_bos = adjust_breakout_indices(all_chart_bos, index_offset)
    chart_active_peaks = adjust_peak_indices(chart_active_peaks, index_offset)
    chart_superseded_peaks = adjust_peak_indices(chart_superseded_peaks, index_offset)

    # ... 后续渲染逻辑不变 ...
    self.chart.update_chart(
        df=display_df,
        # ... 其余参数同前 ...
        initial_window_days=180,
    )
```

## 3. 用户可见变化清单

| 变化 | 影响 | 严重度 |
|------|------|--------|
| Live 图表 X 轴范围缩小 | 从"全量 pkl（~580天）"变为"scan_start .. today（~180天）"，前置 buffer 被 trim | **视觉变化**：图表数据密度提高，缩放范围缩小。但因 `initial_window_days=180` 本来只显示最右 180 天，默认视图无变化；zoom-out 极限变化（不能再左滑到 1.5 年前） |
| Live MA 显示改善 | MA200 从第一根可见 K 线即有值（之前前 200 根为 NaN，被 initial_window 隐藏） | **正面改善** |
| Peak/BO 标记位置 | 当前碰巧正确；统一后**保证正确** | **消除隐性风险** |

## 4. 不推荐的方向及理由

### B: Dev 向 Live 对齐 — 不推荐

**核心问题**：要求 Dev 放弃 `_trim_df_for_display` + `_adjust_breakout_indices`，直接用 raw pkl 作为 chart df。

- **破坏性**：Dev pkl 通常包含数年历史数据（非 Live 的仅 580 天），图表会显示数千根 K 线，前几百根是计算 buffer（MA/ATR 预热期），用户可见但无分析意义
- **BO index 反而有问题**：Dev 的 scanner 在 preprocess 后的 df 上计算 BO index，如果 chart df 改为 raw pkl，index 不对齐问题从 Live 转嫁到 Dev
- **label buffer 灰色区域失效**：trim 逻辑同时负责计算 `label_buffer_start_idx`，删掉后无法正确标记
- **改动量大且高风险**：需要重写 Dev 的整个数据加载流程，可能引发 JSON 缓存兼容性问题

### C: 抽象公共层 — 不推荐

**核心问题**：过度设计。

- Dev 和 Live 的数据流差异本质上是"Live 缺失了 preprocess→trim→adjust 三步"，不是"两套不同的逻辑需要抽象统一"
- 引入 `ChartDataPreparer` 类意味着 5+ 文件改动、新的抽象层、新的测试需求
- 违反项目的奥卡姆剃刀原则：问题的根因是 Live 缺步骤，补上步骤即可，无需为此创建抽象
- 如果 Dev/Live 的参数差异（label_buffer、initial_window_days）需要通过配置对象传递，抽象层的复杂度会迅速膨胀

### D: 保持现状 — 可接受但不推荐

**在什么情况下选 D**：如果近期不会改动 `scan_window_days`、MA 周期、或 pkl 数据量，当前的隐式契约暂时成立。

**不推荐的原因**：
- 隐式不变量是维护负担：任何碰到这几个参数的改动都可能无声地引入 BO 绘制错位 bug
- 两套逻辑意味着每次修改 canvas_manager 的渲染逻辑都需要验证两个路径
- MA fallback（实时计算）的行为与预计算列的行为存在微妙差异（NaN 边界不同），长期看是 bug 源

## 5. 推荐方案总结

| 指标 | 值 |
|------|-----|
| **推荐方向** | A: Live 向 Dev 对齐 |
| **推荐理由** | Live 补齐 Dev 已验证的 preprocess→trim→adjust 三步，消除隐式 index 不变量，改善 MA 显示，改动量小且风险低 |
| **改动量** | ~80-120 LOC, 4 个文件 |
| **涉及文件** | `live/app.py`, `live/chart_adapter.py`, `live/pipeline/daily_runner.py`, `live/pipeline/results.py` |
| **用户可见变化** | 默认视图无变化；zoom-out 范围略缩；MA 显示更完整 |
| **风险** | 低：复用 Dev 已验证逻辑，不改 canvas_manager 渲染层 |
