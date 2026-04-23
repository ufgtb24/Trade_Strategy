# Dev UI vs Live UI K 线图数据流统一分析

> 日期：2026-04-16
> 团队：chart-data-unification（risk-analyst + architect + team-lead）
> 背景：两套 UI 的 K 线图数据流差异显著，需评估是否应统一

---

## 1. 当前差异总览

| 维度 | Dev UI | Live UI | 风险 |
|---|---|---|---|
| chart df 来源 | `preprocess → trim` | 原始 pkl `pd.read_pickle` | **medium** |
| 含 MA/ATR 列 | 是（预计算） | 否（fallback 实时 rolling） | low |
| chart df 起点 | scan_start | pkl 起点（≈T-580） | low |
| chart df 终点 | scan_end + label buffer | pkl 终点（≈T） | none |
| BO index 映射 | `_adjust_breakout_indices(offset)` | 直接使用（无偏移） | **medium** |
| 初始视口 | 全范围展开 | 最近 180 天右对齐 | none |
| zoom out 极限 | scan_start ~ scan_end + label buffer | pkl 全量（≈T-580 ~ T） | low |
| label buffer 灰色区 | 有 | 无 | none |

## 2. 关键风险发现

### F1. BO index 对齐的隐式不变量（medium 风险）

Live 假设"scanner df 行数 == pkl 行数"。当前碰巧成立：

```
pkl 数据量 = scan_window_days + 400 = 580 日历天
scanner preprocess 请求 = scan_start - 415天 ~ scan_end + 30天
```

pkl 起点（T-580）晚于 preprocess buffer_start（T-595），preprocess **未截行**→ 两者行数相等。

但这依赖两个独立常量（`+400` vs `buffer_days=415`）的数值关系。任何一侧调整（如 MA 周期从 200 改为 400、`+400` 改为 `+300`）都可能无声破裂，导致 BO marker 画在错误位置。

### F2. Live MA 渲染走 fallback（low 风险）

`markers.py:530-537` 检测到无 `ma_200` 列时实时 `rolling(200).mean()`。前 200 根为 NaN，但被 `initial_window_days=180` 隐藏。zoom out 到极限可见 MA 线断裂。Dev UI 无此问题（preprocess 预计算 + trim 裁掉 NaN 前缀）。

### F3. Live tooltip 缺失 ATR（low 风险）

chart df 无 `atr` 列，tooltip 静默跳过 ATR 信息。唯一对用户可见的功能差异。

## 3. 统一方案对比

| 方向 | 改动量 | 风险 | 用户影响 | 推荐度 |
|---|---|---|---|---|
| **A. Live 向 Dev 对齐** | ~80-120 LOC, 4 文件 | 低（复用已验证逻辑） | 默认视图无变化；zoom-out 范围略缩；MA 改善 | **推荐** |
| B. Dev 向 Live 对齐 | ~200 LOC, 4+ 文件 | 高（删除已验证逻辑 + 暴露 buffer 区） | Dev 图表前置数百根空白 K 线 | 不推荐 |
| C. 抽象公共层 | ~250 LOC, 5+ 文件 | 中（过度设计） | 无 | 不推荐 |
| D. 保持现状 | ~30 LOC（文档+注释） | 最低 | 无 | 可接受 |

## 4. 推荐：方向 A — Live 向 Dev 对齐

### 4.1 核心改动

Live 补齐 Dev 已验证的 `preprocess → trim → adjust` 三步：

```
[当前]
pkl → pd.read_pickle → chart df（原始，无 MA/ATR）
BO index 直接使用（碰巧正确）

[改后]
pkl → preprocess_dataframe(start_date, end_date, label_max_days=0)
    → trim（裁掉前置 buffer）→ display_df（含 MA/ATR）
BO index -= offset（与 Dev 一致）
```

### 4.2 文件级改动

| 文件 | 改动 | LOC |
|---|---|---|
| `live/app.py` | `_rebuild_chart` 用 `prepare_chart_data` 替换 raw pkl 读取 | +40, -15 |
| `live/chart_adapter.py` | 新增 `prepare_chart_data()` 封装 preprocess + trim | +25 |
| `live/pipeline/daily_runner.py` | MatchedBreakout 携带 scan_start/end_date | +10 |
| `live/pipeline/results.py` | MatchedBreakout 新增 `scan_start_date` / `scan_end_date` | +5 |

### 4.3 关键设计决策

**label buffer**：Live 传 `label_max_days=0`（实盘无未来数据），preprocess 不在 end_date 之后添加缓冲。`label_buffer_start_idx=None` → 灰色区不绘制。

**initial_window_days**：保持 `180`（Live 显示偏好），与 Dev 的 `None`（全展开）各自保留。这是显示偏好不是数据流差异。

**MA 列**：preprocess 预计算 `ma_200` 列并带 buffer 预热，trim 后 MA 从第一根可见 K 线即有值。消除 fallback 路径的 NaN 断裂。

**ATR tooltip**：preprocess 计算 `atr` 列，chart df 自动包含。tooltip ATR 信息恢复。

### 4.4 用户可见变化

| 变化 | 影响 |
|---|---|
| Live 默认视图（最近 180 天） | **无变化** |
| Live zoom-out 极限 | 从 pkl 全量（≈T-580）缩到 scan_start（≈T-180）。前置 400 天空白历史不再可见 |
| Live MA 线 | 从第一根可见 K 线即有值（改善） |
| Live tooltip | ATR 信息恢复（改善） |
| Dev UI | **完全不变** |

## 5. 结论

| 判断维度 | 结论 |
|---|---|
| 当前是否有 crash 风险 | **无**——MA fallback 不崩、index 越界有 defensive 检查 |
| 当前是否有 marker 错位 | **无**——正常参数下 scanner df == pkl 行数 |
| 是否"迫切需要"统一 | **不迫切**——但隐式不变量脆弱 |
| 是否"值得"统一 | **是**——80-120 LOC 消除隐性风险、改善 MA/ATR 显示、减少维护两套逻辑的负担 |
| 何时做 | 下次碰 live chart 代码时顺带做（不必单开 sprint） |

---

*Team chart-data-unification · 2026-04-16*
