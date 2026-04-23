# Chart Data Unification Design

> **日期**：2026-04-16
> **范围**：统一 Dev UI 和 Live UI 的 K 线图数据流；引入三层范围（scan/compute/display）显式建模；在数据层已有的 graceful degradation 之上补齐可观测性。
> **依据**：`docs/research/chart-data-unification-analysis.md`、`docs/research/.graceful-range-workspace/{current-behavior,architecture-proposal,critique}.md`、`docs/explain/chart_data_range.md`。

---

## 1. Goal

本次重构同时达成三个目标：

1. **统一 Dev/Live 数据流**：消除 Live UI 直接 `pd.read_pickle` 而 Dev UI 走 `preprocess → trim → adjust` 两套数据流所带来的隐式不变量（参见 `chart-data-unification-analysis.md` §F1）。两端走同一条管线。
2. **三层范围显式建模**：将 **扫描范围**、**计算范围**、**显示范围** 三个概念在代码里分别命名并独立推导，让"display 独立于 scan"成为一等公民。
3. **Graceful degradation 可观测**：当 pkl 数据不覆盖理想扫描/计算/显示范围时，系统从不 raise（已是当前行为），但必须在 `df.attrs` + 日志 + UI 三处显式声明降级事实。

## 2. Architecture

### 2.1 三层范围的定义

| 层 | 定义 | 来源 |
|---|---|---|
| **扫描范围** | `[scan_start, scan_end]` | 用户配置（Dev：yaml；Live：`T - scan_window_days` ~ `T`） |
| **计算范围** | `[scan_start - compute_buffer, scan_end + label_buffer]` | 由 scan 派生。`compute_buffer ≈ 415 日历天`（= `max(MA200, Volume63, AnnualVol252) × 1.65`），`label_buffer = label_max_days × 1.5` |
| **显示范围** | `[display_start, display_end]` | 显示窗口硬下限 `DISPLAY_MIN_WINDOW = 3 年`。`display_end`：Live = `T`，Dev = `scan_end + label_buffer`。`display_start` = `max(pkl_start, min(scan_start_actual, display_end - DISPLAY_MIN_WINDOW))` |

### 2.2 三层关系

**范围定义上有依赖：**

1. `display_start ≤ scan_start` —— 3 年 display 在典型 scan 窗口（月级）下自然成立，display 始终包含 scan；若 scan > 3 年，display 退化为与 scan 同起点。
2. `compute_start = scan_start - compute_buffer` —— compute 的左边界派生自 scan_start。

**降级执行时三层独立：**

- **显示层**：display 只展示 pkl 实际覆盖的范围。pkl 不够 3 年则显示少于 3 年。
- **计算层**：preprocess 按 compute 理想范围裁切 df，若 pkl 起点晚于 `scan_start - compute_buffer` 则从 pkl 实际起点开始，MA/ATR 前缀自然为 NaN。
- **扫描层**：BO 检测通过 per-factor gate 让每个因子自检 lookback，scan 层不因某些因子 NaN 而阻塞。

这个"定义耦合、执行解耦"是 per-factor gating 重构的直接成果，也是本设计的基础。

### 2.3 数据流

```
pkl (~1125 天)
  ↓
preprocess_dataframe(df, scan_start, scan_end, label_max_days, ...)
  ├─→ 裁切 df 到 [compute_start_actual, label_buffer_end_actual]
  ├─→ 计算 MA / ATR 列
  └─→ 写 df.attrs["range_meta"] = {pkl_start, pkl_end, scan_start_ideal/actual, compute_start_ideal/actual, ...}
  ↓
compute_breakouts_from_dataframe(df, scan_start, scan_end, ...)
  ├─→ 计算 valid_start_index / valid_end_index
  ├─→ 写入 scan_start_actual / scan_end_actual 到 df.attrs["range_meta"]
  ├─→ 若 degraded，INFO 日志
  └─→ 检测 breakouts（index 相对 compute_df）
  ↓
spec = ChartRangeSpec.from_df_and_scan(df, scan_start, scan_end, display_end, DISPLAY_MIN_WINDOW)
  ↓
display_df, offset = trim_df_to_display(df, spec)
  ↓
breakouts = adjust_indices(breakouts, offset)
  ↓
canvas_manager.update_chart(display_df, breakouts, spec=spec)
  ├─→ 渲染 K 线、MA 线、BO/peak markers
  ├─→ 按 spec 画三段阴影 [display_start, scan_start_actual] / [scan_start_actual, scan_end_actual] / [scan_end_actual, display_end]
  └─→ 若 degraded，在 scan_start_actual / scan_end_actual 画橙色虚线 + 文字标注
```

Dev UI 和 Live UI 共用此数据流。

## 3. 数据结构

### 3.1 `df.attrs["range_meta"]`（pandas 原生元数据附着）

由 `scanner.preprocess_dataframe` 初次写入，`scanner.compute_breakouts_from_dataframe` 后续 update。字段：

```python
{
    "pkl_start": date,        # pkl 实际起点
    "pkl_end": date,          # pkl 实际终点
    "scan_start_ideal": date, # 用户请求
    "scan_end_ideal": date,
    "scan_start_actual": date,  # 实际生效（由 valid_start_index 决定）
    "scan_end_actual": date,
    "compute_start_ideal": date,  # scan_start_ideal - compute_buffer
    "compute_start_actual": date, # max(compute_start_ideal, pkl_start)
    "label_buffer_end_ideal": date,  # scan_end_ideal + label_buffer
    "label_buffer_end_actual": date, # min(label_buffer_end_ideal, pkl_end)
}
```

选择 `df.attrs` 而非扩展返回签名的理由：
- pandas 1.0+ 官方机制，随 df 传递
- 向后兼容：不读 attrs 的下游零影响
- 本流程 df 不经过 concat/merge（会丢失 attrs），无损失风险

### 3.2 `ChartRangeSpec` dataclass

`BreakoutStrategy/UI/charts/range_utils.py`：

```python
from dataclasses import dataclass
from datetime import date, timedelta
import pandas as pd

DISPLAY_MIN_WINDOW = timedelta(days=1095)  # 3 年

@dataclass(frozen=True)
class ChartRangeSpec:
    scan_start_ideal:  date
    scan_end_ideal:    date
    scan_start_actual: date
    scan_end_actual:   date
    compute_start_ideal:  date
    compute_start_actual: date
    display_start:     date
    display_end:       date
    pkl_start:         date
    pkl_end:           date

    @property
    def scan_start_degraded(self) -> bool:
        return self.scan_start_actual > self.scan_start_ideal

    @property
    def scan_end_degraded(self) -> bool:
        return self.scan_end_actual < self.scan_end_ideal

    @property
    def compute_buffer_degraded(self) -> bool:
        return self.compute_start_actual > self.compute_start_ideal

    @classmethod
    def from_df_and_scan(
        cls,
        df: pd.DataFrame,
        scan_start: str,
        scan_end: str,
        display_end: date,
        display_min_window: timedelta = DISPLAY_MIN_WINDOW,
    ) -> "ChartRangeSpec":
        """从 preprocessed df.attrs + 扫描配置构造完整 spec"""
        meta = df.attrs.get("range_meta", {})
        scan_start_actual = meta.get("scan_start_actual") or meta.get("pkl_start")
        display_start = max(
            meta["pkl_start"],
            min(scan_start_actual, display_end - display_min_window),
        )
        return cls(
            scan_start_ideal=pd.to_datetime(scan_start).date(),
            scan_end_ideal=pd.to_datetime(scan_end).date(),
            scan_start_actual=scan_start_actual,
            scan_end_actual=meta["scan_end_actual"],
            compute_start_ideal=meta["compute_start_ideal"],
            compute_start_actual=meta["compute_start_actual"],
            display_start=display_start,
            display_end=display_end,
            pkl_start=meta["pkl_start"],
            pkl_end=meta["pkl_end"],
        )
```

### 3.3 `MatchedBreakout` 新字段

`BreakoutStrategy/live/pipeline/results.py`：

```python
@dataclass
class MatchedBreakout:
    # ...existing fields...
    range_spec: Optional[ChartRangeSpec] = None  # 旧缓存加载为 None
```

旧 JSON 缓存不含此字段，加载后为 None，UI 按 None 走兜底（无阴影、无 ⚠）。

## 4. 文件级改动

| 文件 | 改动类型 | LOC |
|---|---|---|
| **新增 `UI/charts/range_utils.py`** | `ChartRangeSpec` + `trim_df_to_display` + `adjust_indices` + `_collect_warnings` | +90 |
| `analysis/scanner.py` | `preprocess_dataframe` 写 `df.attrs["range_meta"]`；`compute_breakouts_from_dataframe` 补 actual + INFO 日志 | +15 |
| `UI/main.py` | 移除私有 `_trim_df_for_display` / `_adjust_breakout_indices`，改用 `range_utils`；status bar 读 spec 显示 ⚠ | 净 -50 |
| `UI/charts/canvas_manager.py` | 接受 `spec: ChartRangeSpec`；三段阴影 + 降级虚线 + 文字 | +40 |
| `live/pipeline/results.py` | `MatchedBreakout` 新增 `range_spec` 字段 | +5 |
| `live/pipeline/daily_runner.py` | `DOWNLOAD_DAYS=1125` 替代 `scan_window_days + 400`；构造 `ChartRangeSpec` 写入 `MatchedBreakout` | +10 |
| `live/app.py` | `_rebuild_chart` 走 `preprocess → trim → adjust`；MatchList 行尾 ⚠ | 净 +25 |
| `live/chart_adapter.py` | 精简：只保留 `ChartPeak/ChartBreakout` + `adapt_peaks/adapt_breakout` | 净 -5 |
| **总计** | | **~130 LOC 净新增** |

### 4.1 `preprocess_dataframe` 改动

签名不变，末尾增加：

```python
out = df  # 已完成裁切 + MA/ATR 计算
out.attrs["range_meta"] = {
    "pkl_start": df_original.index[0].date() if len(df_original) else None,
    "pkl_end":   df_original.index[-1].date() if len(df_original) else None,
    "scan_start_ideal": pd.to_datetime(start_date).date() if start_date else None,
    "scan_end_ideal":   pd.to_datetime(end_date).date() if end_date else None,
    "compute_start_ideal":    buffer_start.date(),
    "compute_start_actual":   out.index[0].date() if len(out) else None,
    "label_buffer_end_ideal": buffer_end.date() if end_date else None,
    "label_buffer_end_actual": out.index[-1].date() if len(out) else None,
}
return out
```

### 4.2 `compute_breakouts_from_dataframe` 改动

计算 `valid_start_index / valid_end_index` 之后：

```python
scan_start_actual = df.index[valid_start_index].date()
scan_end_actual   = df.index[valid_end_index - 1].date()

meta = df.attrs.get("range_meta", {})
meta["scan_start_actual"] = scan_start_actual
meta["scan_end_actual"]   = scan_end_actual
df.attrs["range_meta"] = meta

if scan_start_date and scan_start_actual > pd.to_datetime(scan_start_date).date():
    logger.info(
        "scan_start degraded: requested=%s, actual=%s (pkl starts later)",
        scan_start_date, scan_start_actual
    )
if scan_end_date and scan_end_actual < pd.to_datetime(scan_end_date).date():
    logger.info(
        "scan_end degraded: requested=%s, actual=%s (pkl ends earlier)",
        scan_end_date, scan_end_actual
    )
```

### 4.3 `range_utils` 核心函数

```python
def trim_df_to_display(df: pd.DataFrame, spec: ChartRangeSpec) -> tuple[pd.DataFrame, int]:
    """裁切 df 到 display_start，返回 (display_df, index_offset)。"""
    start_dt = pd.to_datetime(spec.display_start)
    mask = df.index >= start_dt
    first_idx = mask.argmax() if mask.any() else 0
    return df.iloc[first_idx:].copy(), first_idx


def adjust_indices(items: list, offset: int) -> list:
    """把 breakout/peak 的 index 减去 offset，跳过 index < offset 的条目。"""
    if offset == 0:
        return items
    result = []
    for item in items:
        if item.index < offset:
            continue
        new_item = item.__class__.__new__(item.__class__)
        new_item.__dict__.update(item.__dict__)
        new_item.index = item.index - offset
        if hasattr(new_item, "broken_peaks") and new_item.broken_peaks:
            new_item.broken_peaks = adjust_indices(new_item.broken_peaks, offset)
        result.append(new_item)
    return result


def _collect_warnings(spec: ChartRangeSpec) -> list[str]:
    """汇总当前降级状态供 UI 显示。"""
    warnings = []
    if spec.scan_start_degraded:
        warnings.append(f"scan_start→{spec.scan_start_actual}")
    if spec.scan_end_degraded:
        warnings.append(f"scan_end→{spec.scan_end_actual}")
    if spec.compute_buffer_degraded:
        warnings.append("MA buffer short")
    return warnings
```

## 5. UI 降级可见性

### 5.1 图表三段阴影（Dev/Live 共用）

在 `canvas_manager.update_chart(df, breakouts, ..., spec: ChartRangeSpec)` 内部：

```
|← pkl_start   display_start   scan_start_actual   scan_end_actual   display_end →|
|              [灰 alpha=0.15] [无阴影 主扫描区]   [灰 alpha=0.15]                 |
|              "pre-scan"                           "post-scan/label"             |
```

- 阴影颜色统一灰色（`#808080`, alpha=0.15），保持 K 线可读性
- 阴影区内照常渲染 K 线、MA、BO markers（BO 不会出现在阴影区，因为 detection 受 `valid_start/end_index` 约束）

### 5.2 降级虚线（Dev/Live 共用）

- `spec.scan_start_degraded` → 在 `scan_start_actual` 画橙色虚线，顶部文字 `scan start (req {scan_start_ideal})`
- `spec.scan_end_degraded` → 在 `scan_end_actual` 画橙色虚线，顶部文字 `scan end (req {scan_end_ideal})`
- `compute_buffer_degraded` 不画虚线（MA 线自身 NaN 即是视觉信号）

### 5.3 状态信息（Dev/Live 各自 widget）

Dev UI（`UI/main.py`）：

```python
warnings = _collect_warnings(spec)
status = f"{symbol}: Computed {N} breakout(s)"
if warnings:
    status += f" ⚠ {', '.join(warnings)}"
    param_panel.set_status(status, "orange")
else:
    param_panel.set_status(status, "green")
```

Live UI（`live/app.py`）：

```python
warnings = _collect_warnings(current.range_spec) if current.range_spec else []
match_list.mark_row(current.symbol, warning="⚠" if warnings else "")
# MatchList 行悬停 tooltip 展示完整 warnings
```

共用 `_collect_warnings(spec)` 函数定义于 `range_utils.py`。

### 5.4 日志

`scanner.compute_breakouts_from_dataframe` 在降级发生时写 INFO 日志（见 §4.2）。两个 UI 都调 scanner，日志统一。

## 6. Live 下载量调整

`BreakoutStrategy/live/pipeline/daily_runner.py`：

```python
# 当前
days_from_now=self.scan_window_days + 400,  # 180 + 400 = 580

# 改后
DOWNLOAD_DAYS = 1125  # 3 年 display (1095) + 30 天安全垫
days_from_now=DOWNLOAD_DAYS,
```

推导：`max(display_window=1095, scan_window + compute_buffer + label_buffer = 180+415+30 = 625) + safety = 1095 + 30 = 1125`。

**代价仅限磁盘**：
- akshare 总是拉全部历史，`days_from_now` 只控制本地切片后保存的范围
- 单个 pkl 文件：50KB → ~95KB（约 1.9×）
- 整个 `datasets/pkls/` 目录：约 1.9×（假设 5000 symbols，250MB → 475MB）
- 网络/时间：无变化

## 7. 分阶段交付

按 commit 切分，合并为一个 PR（除非显式另开 PR）：

| Commit | 范围 | 行为变化 |
|---|---|---|
| **C1** | 新增 `range_utils.py`（`ChartRangeSpec` + `trim_df_to_display` + `adjust_indices` + `_collect_warnings`）；`scanner` 写 `df.attrs["range_meta"]` + INFO 日志 | 无 |
| **C2** | Dev UI（`UI/main.py`）切换到 `range_utils`，传 `spec` 给 canvas_manager | 等价 |
| **C3** | Live UI（`live/app.py`）切换到 `preprocess → trim → adjust`；`MatchedBreakout` 新增 `range_spec`；`daily_runner` 构造 spec | 默认视图等价；zoom-out 极限从 pkl 全量缩到 display（580 天内无变化） |
| **C4** | `canvas_manager` 实现三段阴影 + 降级虚线；Dev status bar ⚠ / Live MatchList ⚠ | 新视觉 |
| **C5** | `DOWNLOAD_DAYS=1125` | pkl 磁盘占用 ~1.9× |

C1-C5 合一 PR。旧 JSON 缓存（无 `range_spec`）加载后 UI 无 ⚠、无新阴影（旧数据无法重建 spec）。

## 8. 验收标准

1. **功能：Case B（scan_start 早于 pkl）**
   - status bar 橙色 ⚠ + INFO 日志 + 图表橙色虚线 + 文字 `scan start (req YYYY-MM-DD)`
   - `df.attrs["range_meta"]["scan_start_actual"] != scan_start_ideal`

2. **功能：三层范围显式**
   - Live 任意选股图表默认展示 3 年（除非 pkl < 3 年，此时降级展示 pkl 全量）
   - 修改 `scan_window_days` 不影响 `display_start/end`

3. **功能：graceful**
   - 任何 pkl 起点/终点/完整性问题均不 raise
   - BO 检测仍产出尽可能多的结果
   - 各因子按 per-factor gate 独立判定

4. **兼容性**
   - Dev UI 当前视图除新增阴影外无变化
   - Live UI 默认视图（最近 180 天）无变化
   - 旧 JSON 缓存可正常加载（range_spec=None → UI 兜底无 ⚠ 无阴影）

5. **代码质量**
   - `trim_df_to_display` 和 `adjust_indices` 仅在 `range_utils.py` 一处实现
   - Dev/Live 的 `_rebuild_chart` 调用结构一致

## 9. 风险

| 风险 | 严重度 | 缓解 |
|---|---|---|
| `df.attrs` 在 concat/merge 下丢失 | 低 | 本流程不经过这些操作；单测 pin attrs 存在 |
| `ChartRangeSpec.from_df_and_scan` 构造失败 | 中 | 内部 try/except，失败返回 None；UI 按 None 兜底 |
| 旧 MatchedBreakout 缓存无 range_spec | 中 | 字段定义为 Optional；UI 按 None 走原有渲染 |
| IPO 股票频繁触发 ⚠ | 无（设计确认） | 用户确认：降级可见即是事实通知，无需 heuristic 区分 |
| 三段阴影在 zoom-out 极限视觉负荷 | 低 | alpha=0.15 对 K 线可读性影响小 |
| 1125 天 pkl 磁盘占用 ~1.9× | 低 | 约 225MB 增量，接受 |

## 10. 非目标（Out of Scope）

- **IPO vs 配置错误的启发式区分**：用户明确视为事实通知，不做特殊处理
- **回测（非 Live、非 Dev）UI**：本重构以 `range_utils` 共用层为基础，未来接入成本极低，但本次不实施
- **scan 配置在 yaml 中的结构调整**：保持现状
- **`preprocess_dataframe` 签名变更**：保持向后兼容，只新增 `df.attrs` 输出
- **MA 周期等运算参数调优**：与本重构无关

---

*Spec 完成。实施前用 `superpowers:writing-plans` 转为实施计划。*
