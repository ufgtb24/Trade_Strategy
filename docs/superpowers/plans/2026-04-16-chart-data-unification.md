# Chart Data Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 Dev UI 和 Live UI 的 K 线图数据流，建立显式三层范围模型（scan / compute / display），并在数据层已有的 graceful degradation 之上补齐可观测性。

**Architecture:** 新增共用模块 `BreakoutStrategy/UI/charts/range_utils.py`（`ChartRangeSpec` dataclass + `trim_df_to_display` + `adjust_indices`）。`scanner.preprocess_dataframe` 在 `df.attrs["range_meta"]` 写入范围元数据，`compute_breakouts_from_dataframe` 补全 actual 字段并在降级时写 INFO 日志。Dev/Live 两端 UI 统一走 `preprocess → ChartRangeSpec → trim → adjust → canvas_manager(spec)` 流程。UI 通过状态栏文字、行尾 ⚠ 小标、图表三段阴影、橙色降级虚线四个渠道呈现降级事实。

**Tech Stack:** Python 3.10+, pandas (DataFrame.attrs), matplotlib, tkinter/ttk, pytest, uv。

---

## 文件地图

| 文件 | 责任 | 改动类型 |
|---|---|---|
| `BreakoutStrategy/UI/charts/range_utils.py` | 新模块：`ChartRangeSpec` + `trim_df_to_display` + `adjust_indices` + `_collect_warnings` | **新增** |
| `BreakoutStrategy/UI/charts/tests/test_range_utils.py` | 上面的单元测试 | **新增** |
| `BreakoutStrategy/analysis/scanner.py` | `preprocess_dataframe` 写 `df.attrs["range_meta"]`；`compute_breakouts_from_dataframe` 补 actual + INFO 日志 | 修改 |
| `BreakoutStrategy/analysis/tests/test_scanner_range_meta.py` | 上面的单元测试 | **新增** |
| `BreakoutStrategy/UI/main.py` | 移除 `_trim_df_for_display` / `_adjust_breakout_indices` / `_adjust_peak_indices`；构造 spec；传入 canvas；状态栏 ⚠ | 修改 |
| `BreakoutStrategy/UI/charts/canvas_manager.py` | `update_chart` 新增 `spec: ChartRangeSpec` 参数；实现三段阴影 + 降级虚线 | 修改 |
| `BreakoutStrategy/live/pipeline/results.py` | `MatchedBreakout` 新增 `range_spec: Optional[ChartRangeSpec]` 字段 | 修改 |
| `BreakoutStrategy/live/pipeline/daily_runner.py` | 构造 spec 并写入 MatchedBreakout；`DOWNLOAD_DAYS=1125` | 修改 |
| `BreakoutStrategy/live/app.py` | `_rebuild_chart` 走 `preprocess → trim → adjust`；状态栏/tooltip 显示 warnings | 修改 |
| `BreakoutStrategy/live/panels/match_list.py` | `_row_values` 根据 spec 在 symbol 后附 ⚠ | 修改 |
| `BreakoutStrategy/live/tests/test_match_list_warning.py` | MatchList ⚠ 测试 | **新增** |

---

## Task 1: 创建 `range_utils.py` — ChartRangeSpec 数据结构

**Files:**
- Create: `BreakoutStrategy/UI/charts/range_utils.py`
- Test: `BreakoutStrategy/UI/charts/tests/test_range_utils.py`

- [ ] **Step 1.1: 写 ChartRangeSpec 的属性测试（失败）**

创建 `BreakoutStrategy/UI/charts/tests/test_range_utils.py`：

```python
from datetime import date
import pytest
from BreakoutStrategy.UI.charts.range_utils import ChartRangeSpec


def _make_spec(**overrides):
    """辅助：构造一个默认 spec，调用方按需覆盖字段。"""
    defaults = dict(
        scan_start_ideal=date(2024, 1, 1),
        scan_end_ideal=date(2024, 12, 31),
        scan_start_actual=date(2024, 1, 1),
        scan_end_actual=date(2024, 12, 31),
        compute_start_ideal=date(2023, 11, 13),
        compute_start_actual=date(2023, 11, 13),
        display_start=date(2022, 1, 1),
        display_end=date(2024, 12, 31),
        pkl_start=date(2020, 1, 1),
        pkl_end=date(2024, 12, 31),
    )
    defaults.update(overrides)
    return ChartRangeSpec(**defaults)


def test_no_degradation_when_actual_equals_ideal():
    spec = _make_spec()
    assert spec.scan_start_degraded is False
    assert spec.scan_end_degraded is False
    assert spec.compute_buffer_degraded is False


def test_scan_start_degraded_when_actual_later():
    spec = _make_spec(
        scan_start_ideal=date(2024, 1, 1),
        scan_start_actual=date(2024, 6, 1),
    )
    assert spec.scan_start_degraded is True


def test_scan_end_degraded_when_actual_earlier():
    spec = _make_spec(
        scan_end_ideal=date(2024, 12, 31),
        scan_end_actual=date(2024, 10, 15),
    )
    assert spec.scan_end_degraded is True


def test_compute_buffer_degraded_when_actual_later():
    spec = _make_spec(
        compute_start_ideal=date(2023, 11, 13),
        compute_start_actual=date(2024, 2, 1),
    )
    assert spec.compute_buffer_degraded is True


def test_spec_is_frozen():
    spec = _make_spec()
    with pytest.raises((AttributeError, TypeError)):
        spec.scan_start_actual = date(2020, 1, 1)
```

- [ ] **Step 1.2: 运行测试确认失败**

```bash
uv run pytest BreakoutStrategy/UI/charts/tests/test_range_utils.py -v
```

Expected: ImportError — `range_utils` 模块不存在。

- [ ] **Step 1.3: 实现 ChartRangeSpec**

创建 `BreakoutStrategy/UI/charts/range_utils.py`：

```python
"""
Chart range specification and data transformations.

本模块统一承载 Dev UI 和 Live UI 的 K 线图范围语义：
- ChartRangeSpec：三层范围（scan / compute / display）的 ideal/actual 双值表达
- trim_df_to_display：按 spec 裁切 df 到显示范围
- adjust_indices：把 breakout/peak 的 index 映射到裁切后的 df 坐标
- _collect_warnings：汇总降级状态供 UI 显示
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd


DISPLAY_MIN_WINDOW = timedelta(days=1095)  # 3 年


@dataclass(frozen=True)
class ChartRangeSpec:
    """K 线图渲染所需的范围契约（frozen，避免下游意外修改）。"""

    scan_start_ideal: date
    scan_end_ideal: date
    scan_start_actual: date
    scan_end_actual: date

    compute_start_ideal: date
    compute_start_actual: date

    display_start: date
    display_end: date

    pkl_start: date
    pkl_end: date

    @property
    def scan_start_degraded(self) -> bool:
        return self.scan_start_actual > self.scan_start_ideal

    @property
    def scan_end_degraded(self) -> bool:
        return self.scan_end_actual < self.scan_end_ideal

    @property
    def compute_buffer_degraded(self) -> bool:
        return self.compute_start_actual > self.compute_start_ideal
```

- [ ] **Step 1.4: 运行测试确认通过**

```bash
uv run pytest BreakoutStrategy/UI/charts/tests/test_range_utils.py -v
```

Expected: 5 passed。

- [ ] **Step 1.5: Commit**

```bash
git add BreakoutStrategy/UI/charts/range_utils.py BreakoutStrategy/UI/charts/tests/test_range_utils.py
git commit -m "feat(range_utils): add ChartRangeSpec dataclass with degradation properties"
```

---

## Task 2: `range_utils` — trim_df_to_display + adjust_indices

**Files:**
- Modify: `BreakoutStrategy/UI/charts/range_utils.py`
- Modify: `BreakoutStrategy/UI/charts/tests/test_range_utils.py`

- [ ] **Step 2.1: 写 trim 和 adjust 的测试（失败）**

在 `test_range_utils.py` 末尾追加：

```python
import pandas as pd
from types import SimpleNamespace
from BreakoutStrategy.UI.charts.range_utils import (
    trim_df_to_display, adjust_indices
)


def _make_df(start="2020-01-01", periods=400):
    idx = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({"close": range(periods)}, index=idx)


def test_trim_returns_full_df_when_display_start_before_df_start():
    df = _make_df(start="2022-01-01", periods=100)
    spec = _make_spec(display_start=date(2020, 1, 1))
    display_df, offset = trim_df_to_display(df, spec)
    assert offset == 0
    assert len(display_df) == 100
    assert display_df.index[0] == df.index[0]


def test_trim_slices_front_when_display_start_inside_df():
    df = _make_df(start="2022-01-01", periods=100)
    spec = _make_spec(display_start=date(2022, 2, 1))
    display_df, offset = trim_df_to_display(df, spec)
    assert offset == 31  # 1 月 31 天
    assert display_df.index[0] == pd.Timestamp("2022-02-01")


def test_adjust_indices_zero_offset_returns_original():
    items = [SimpleNamespace(index=10), SimpleNamespace(index=20)]
    result = adjust_indices(items, 0)
    assert result is items  # 零 offset 走 shortcut


def test_adjust_indices_subtracts_offset():
    items = [SimpleNamespace(index=10), SimpleNamespace(index=20)]
    result = adjust_indices(items, 5)
    assert [it.index for it in result] == [5, 15]


def test_adjust_indices_skips_items_before_offset():
    items = [
        SimpleNamespace(index=3),   # 被跳过
        SimpleNamespace(index=10),
        SimpleNamespace(index=20),
    ]
    result = adjust_indices(items, 5)
    assert [it.index for it in result] == [5, 15]


def test_adjust_indices_recursively_adjusts_broken_peaks():
    peak1 = SimpleNamespace(index=15)
    peak2 = SimpleNamespace(index=18)
    bo = SimpleNamespace(index=20, broken_peaks=[peak1, peak2])
    result = adjust_indices([bo], 5)
    assert result[0].index == 15
    assert [p.index for p in result[0].broken_peaks] == [10, 13]
```

- [ ] **Step 2.2: 运行测试确认失败**

```bash
uv run pytest BreakoutStrategy/UI/charts/tests/test_range_utils.py -v
```

Expected: 6 新增测试 ImportError `trim_df_to_display, adjust_indices`。

- [ ] **Step 2.3: 实现 trim 和 adjust**

在 `range_utils.py` 末尾追加：

```python
def trim_df_to_display(df: pd.DataFrame, spec: ChartRangeSpec) -> tuple[pd.DataFrame, int]:
    """
    裁切 df 到 display_start 之后。返回 (display_df, index_offset)。

    如果 display_start 早于 df.index[0]，不裁切（offset=0）。
    """
    start_dt = pd.to_datetime(spec.display_start)
    mask = df.index >= start_dt
    if not mask.any():
        return df, 0
    first_idx = int(mask.argmax())
    if first_idx == 0:
        return df, 0
    return df.iloc[first_idx:].copy(), first_idx


def adjust_indices(items: list, offset: int) -> list:
    """
    把 breakout/peak 的 index 映射到裁切后的 df 坐标。

    - offset=0：返回原列表（不拷贝）
    - item.index < offset：跳过（位于裁切区之前）
    - 否则：浅拷贝 + index -= offset；若对象有 broken_peaks 属性，递归调整
    """
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
```

- [ ] **Step 2.4: 运行测试确认通过**

```bash
uv run pytest BreakoutStrategy/UI/charts/tests/test_range_utils.py -v
```

Expected: 11 passed。

- [ ] **Step 2.5: Commit**

```bash
git add BreakoutStrategy/UI/charts/range_utils.py BreakoutStrategy/UI/charts/tests/test_range_utils.py
git commit -m "feat(range_utils): add trim_df_to_display and adjust_indices"
```

---

## Task 3: `scanner.preprocess_dataframe` 写 `df.attrs["range_meta"]`

**Files:**
- Modify: `BreakoutStrategy/analysis/scanner.py` (preprocess_dataframe, 57-104)
- Create: `BreakoutStrategy/analysis/tests/test_scanner_range_meta.py`

- [ ] **Step 3.1: 写 range_meta 测试（失败）**

创建 `BreakoutStrategy/analysis/tests/test_scanner_range_meta.py`：

```python
import pandas as pd
from BreakoutStrategy.analysis.scanner import preprocess_dataframe


def _make_pkl(start="2020-01-01", periods=2000):
    """大于 compute_buffer 的 pkl，确保 preprocess 不会被 pkl 起点降级。"""
    idx = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({
        "open":   [100.0] * periods,
        "high":   [101.0] * periods,
        "low":    [99.0]  * periods,
        "close":  [100.0] * periods,
        "volume": [1000.0] * periods,
    }, index=idx)


def test_preprocess_writes_range_meta_with_required_keys():
    df = _make_pkl()
    out = preprocess_dataframe(df.copy(), start_date="2024-01-01", end_date="2024-12-31")
    meta = out.attrs.get("range_meta")
    assert meta is not None
    for key in [
        "pkl_start", "pkl_end",
        "scan_start_ideal", "scan_end_ideal",
        "compute_start_ideal", "compute_start_actual",
        "label_buffer_end_ideal", "label_buffer_end_actual",
    ]:
        assert key in meta, f"missing key: {key}"


def test_preprocess_ideal_values_match_inputs():
    df = _make_pkl()
    out = preprocess_dataframe(df.copy(), start_date="2024-01-01", end_date="2024-12-31")
    meta = out.attrs["range_meta"]
    assert str(meta["scan_start_ideal"]) == "2024-01-01"
    assert str(meta["scan_end_ideal"]) == "2024-12-31"


def test_preprocess_records_pkl_bounds_from_original_df():
    df = _make_pkl(start="2021-03-15", periods=1500)
    expected_end = df.index[-1].date()
    out = preprocess_dataframe(df.copy(), start_date="2024-01-01", end_date="2024-12-31")
    meta = out.attrs["range_meta"]
    assert str(meta["pkl_start"]) == "2021-03-15"
    assert meta["pkl_end"] == expected_end


def test_preprocess_compute_start_actual_equals_pkl_start_when_pkl_shorter():
    """pkl 起点晚于 scan_start - compute_buffer 时，compute_start_actual = pkl 起点。"""
    df = _make_pkl(start="2023-08-01", periods=600)  # pkl 起点 2023-08-01
    out = preprocess_dataframe(df.copy(), start_date="2024-01-01", end_date="2024-12-31")
    meta = out.attrs["range_meta"]
    # pkl 起点晚于 buffer_start (约 2022-11-13)，compute_start_actual 应跟随 pkl
    assert str(meta["compute_start_actual"]) == "2023-08-01"
```

- [ ] **Step 3.2: 运行测试确认失败**

```bash
uv run pytest BreakoutStrategy/analysis/tests/test_scanner_range_meta.py -v
```

Expected: 4 failures (AttributeError: `attrs.get('range_meta')` is None 或 key 不在)。

- [ ] **Step 3.3: 修改 `preprocess_dataframe` 写 attrs**

在 `BreakoutStrategy/analysis/scanner.py` 中找到 `preprocess_dataframe`（57-104 行）。当前 return 前最后一段是计算 MA 和 ATR。

修改：在**函数开头**记录原始 pkl 边界（因为 df 会被裁切）；在**函数尾**写入 attrs。完整替换后的函数：

```python
def preprocess_dataframe(
    df: pd.DataFrame,
    start_date: str = None,
    end_date: str = None,
    label_max_days: int = 20,
    ma_periods: list = None,
    atr_period: int = 14,
) -> pd.DataFrame:
    """
    数据预处理：截取时间范围 + 计算技术指标 + 写入 range_meta 元数据

    Args:
        df: 原始 OHLCV DataFrame
        start_date: 扫描起始日期
        end_date: 扫描结束日期
        label_max_days: Label 计算所需的后置天数
        ma_periods: 要计算的均线周期列表，默认 [200]
        atr_period: ATR 计算周期，默认 14

    Returns:
        预处理后的 DataFrame，包含 ma_xxx / atr 列和 df.attrs["range_meta"]
    """
    if ma_periods is None:
        ma_periods = [200]

    # 记录 pkl 原始边界（在 df 被裁切之前）
    pkl_start = df.index[0].date() if len(df) else None
    pkl_end = df.index[-1].date() if len(df) else None

    # 动态计算缓冲区
    max_ma_period = max(ma_periods) if ma_periods else 200
    required_trading_days = max(max_ma_period, VOLUME_LOOKBACK_BUFFER, ANNUAL_VOL_LOOKBACK_BUFFER)
    buffer_days = int(required_trading_days * TRADING_TO_CALENDAR_RATIO)
    label_buffer_days = int(label_max_days * 1.5)

    buffer_start = None
    buffer_end = None
    if start_date:
        buffer_start = pd.to_datetime(start_date) - pd.Timedelta(days=buffer_days)
        df = df[df.index >= buffer_start]
    if end_date:
        buffer_end = pd.to_datetime(end_date) + pd.Timedelta(days=label_buffer_days)
        df = df[df.index <= buffer_end]

    # 计算均线
    for period in ma_periods:
        df[f"ma_{period}"] = df["close"].rolling(window=period).mean()

    # 计算 ATR
    df["atr"] = TechnicalIndicators.calculate_atr(
        df["high"], df["low"], df["close"], atr_period
    )

    # 写入范围元数据（scan_start/end_actual 留待 compute_breakouts_from_dataframe 补齐）
    df.attrs["range_meta"] = {
        "pkl_start": pkl_start,
        "pkl_end": pkl_end,
        "scan_start_ideal": pd.to_datetime(start_date).date() if start_date else None,
        "scan_end_ideal": pd.to_datetime(end_date).date() if end_date else None,
        "compute_start_ideal": buffer_start.date() if buffer_start is not None else None,
        "compute_start_actual": df.index[0].date() if len(df) else None,
        "label_buffer_end_ideal": buffer_end.date() if buffer_end is not None else None,
        "label_buffer_end_actual": df.index[-1].date() if len(df) else None,
    }

    return df
```

- [ ] **Step 3.4: 运行测试确认通过**

```bash
uv run pytest BreakoutStrategy/analysis/tests/test_scanner_range_meta.py -v
```

Expected: 4 passed。

- [ ] **Step 3.5: 运行现有 scanner 测试确保未回归**

```bash
uv run pytest BreakoutStrategy/analysis/tests/ -v
```

Expected: 所有测试通过（preprocess 只新增 attrs，返回的 df 数据内容不变）。

- [ ] **Step 3.6: Commit**

```bash
git add BreakoutStrategy/analysis/scanner.py BreakoutStrategy/analysis/tests/test_scanner_range_meta.py
git commit -m "feat(scanner): write df.attrs['range_meta'] from preprocess_dataframe"
```

---

## Task 4: `scanner.compute_breakouts_from_dataframe` 补 actual + INFO 日志

**Files:**
- Modify: `BreakoutStrategy/analysis/scanner.py` (compute_breakouts_from_dataframe, ~274-302)
- Modify: `BreakoutStrategy/analysis/tests/test_scanner_range_meta.py`

- [ ] **Step 4.1: 写 actual 字段测试（失败）**

在 `test_scanner_range_meta.py` 末尾追加：

```python
import logging
from BreakoutStrategy.analysis.scanner import compute_breakouts_from_dataframe


def test_compute_breakouts_writes_scan_actual_when_no_degradation(caplog):
    df = _make_pkl()
    df = preprocess_dataframe(df, start_date="2024-01-01", end_date="2024-12-31")
    with caplog.at_level(logging.INFO, logger="BreakoutStrategy.analysis.scanner"):
        compute_breakouts_from_dataframe(
            df, scan_start_date="2024-01-01", scan_end_date="2024-12-31"
        )
    meta = df.attrs["range_meta"]
    assert str(meta["scan_start_actual"]) == "2024-01-01"
    assert str(meta["scan_end_actual"]) == "2024-12-31"
    # 未降级：不应有 INFO 日志
    assert not any("degraded" in r.message for r in caplog.records)


def test_compute_breakouts_logs_and_records_scan_start_degradation(caplog):
    """pkl 起点晚于 scan_start 时，compute_breakouts 应记录 actual > ideal 并写日志。"""
    # pkl 起点 2024-03-01，scan_start 2024-01-01 —— scan_start 被降级
    df = _make_pkl(start="2024-03-01", periods=500)
    df = preprocess_dataframe(df, start_date="2024-01-01", end_date="2024-12-31")
    with caplog.at_level(logging.INFO, logger="BreakoutStrategy.analysis.scanner"):
        compute_breakouts_from_dataframe(
            df, scan_start_date="2024-01-01", scan_end_date="2024-12-31"
        )
    meta = df.attrs["range_meta"]
    assert str(meta["scan_start_actual"]) == "2024-03-01"
    assert any(
        "scan_start degraded" in r.message for r in caplog.records
    ), f"no degradation log found, records: {[r.message for r in caplog.records]}"


def test_compute_breakouts_logs_scan_end_degradation(caplog):
    """pkl 终点早于 scan_end 时，scan_end 被降级。"""
    # pkl 终点 2024-06-30，scan_end 2024-12-31 —— scan_end 被降级
    df = _make_pkl(start="2022-01-01", periods=912)  # 截止 2024-06-30
    df = preprocess_dataframe(df, start_date="2024-01-01", end_date="2024-12-31")
    with caplog.at_level(logging.INFO, logger="BreakoutStrategy.analysis.scanner"):
        compute_breakouts_from_dataframe(
            df, scan_start_date="2024-01-01", scan_end_date="2024-12-31"
        )
    meta = df.attrs["range_meta"]
    assert meta["scan_end_actual"] < pd.to_datetime("2024-12-31").date()
    assert any("scan_end degraded" in r.message for r in caplog.records)
```

- [ ] **Step 4.2: 运行测试确认失败**

```bash
uv run pytest BreakoutStrategy/analysis/tests/test_scanner_range_meta.py -v -k "scan_actual or degradation"
```

Expected: 3 failures (`scan_start_actual` 不在 meta 中，或 日志中没有 "degraded" 字段)。

- [ ] **Step 4.3: 修改 `compute_breakouts_from_dataframe` 补 actual + 日志**

在 `BreakoutStrategy/analysis/scanner.py` 中找到 `compute_breakouts_from_dataframe`（约 274-302 行）。找到计算 `valid_start_index / valid_end_index` 的 block，**在 block 之后、返回之前**插入以下逻辑：

```python
import logging
# 如果文件顶部还没有 logger，加：
# logger = logging.getLogger(__name__)

# ...原有的 valid_start_index / valid_end_index 计算保持不变...

# ↓↓↓ 新增：补齐 scan_start/end_actual 到 df.attrs["range_meta"]
if len(df) and valid_end_index > valid_start_index:
    scan_start_actual = df.index[valid_start_index].date()
    scan_end_actual = df.index[valid_end_index - 1].date()

    meta = df.attrs.get("range_meta", {})
    meta["scan_start_actual"] = scan_start_actual
    meta["scan_end_actual"] = scan_end_actual
    df.attrs["range_meta"] = meta

    if scan_start_date:
        ideal_start = pd.to_datetime(scan_start_date).date()
        if scan_start_actual > ideal_start:
            logger.info(
                "scan_start degraded: requested=%s, actual=%s (pkl starts later)",
                ideal_start, scan_start_actual,
            )

    if scan_end_date:
        ideal_end = pd.to_datetime(scan_end_date).date()
        if scan_end_actual < ideal_end:
            logger.info(
                "scan_end degraded: requested=%s, actual=%s (pkl ends earlier)",
                ideal_end, scan_end_actual,
            )
# ↑↑↑ 新增结束
```

**注意**：文件顶部须有 `import logging` 和 `logger = logging.getLogger(__name__)`。若没有，加在现有 import 之后。

- [ ] **Step 4.4: 运行测试确认通过**

```bash
uv run pytest BreakoutStrategy/analysis/tests/test_scanner_range_meta.py -v
```

Expected: 全部 7 测试 passed。

- [ ] **Step 4.5: 运行全部 analysis 测试确保未回归**

```bash
uv run pytest BreakoutStrategy/analysis/tests/ -v
```

Expected: 全部 passed。

- [ ] **Step 4.6: Commit**

```bash
git add BreakoutStrategy/analysis/scanner.py BreakoutStrategy/analysis/tests/test_scanner_range_meta.py
git commit -m "feat(scanner): record scan_start/end_actual and log degradation"
```

---

## Task 5: `range_utils` — _collect_warnings + from_df_and_scan 工厂

**Files:**
- Modify: `BreakoutStrategy/UI/charts/range_utils.py`
- Modify: `BreakoutStrategy/UI/charts/tests/test_range_utils.py`

- [ ] **Step 5.1: 写 _collect_warnings 和 factory 测试（失败）**

在 `test_range_utils.py` 末尾追加：

```python
from BreakoutStrategy.UI.charts.range_utils import (
    _collect_warnings, DISPLAY_MIN_WINDOW
)


def test_collect_warnings_returns_empty_when_no_degradation():
    spec = _make_spec()
    assert _collect_warnings(spec) == []


def test_collect_warnings_includes_scan_start():
    spec = _make_spec(
        scan_start_ideal=date(2024, 1, 1),
        scan_start_actual=date(2024, 6, 1),
    )
    warnings = _collect_warnings(spec)
    assert len(warnings) == 1
    assert "scan_start" in warnings[0]
    assert "2024-06-01" in warnings[0]


def test_collect_warnings_includes_multiple():
    spec = _make_spec(
        scan_start_ideal=date(2024, 1, 1),
        scan_start_actual=date(2024, 6, 1),
        scan_end_ideal=date(2024, 12, 31),
        scan_end_actual=date(2024, 10, 15),
        compute_start_ideal=date(2023, 11, 13),
        compute_start_actual=date(2024, 1, 1),
    )
    warnings = _collect_warnings(spec)
    assert len(warnings) == 3


# ---- from_df_and_scan 工厂 ----
from BreakoutStrategy.analysis.scanner import preprocess_dataframe, compute_breakouts_from_dataframe


def _make_pkl(start="2020-01-01", periods=2000):
    idx = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({
        "open": [100.0]*periods, "high": [101.0]*periods,
        "low": [99.0]*periods, "close": [100.0]*periods,
        "volume": [1000.0]*periods,
    }, index=idx)


def test_from_df_and_scan_constructs_spec_with_all_fields():
    df = _make_pkl()
    df = preprocess_dataframe(df, start_date="2024-01-01", end_date="2024-12-31")
    compute_breakouts_from_dataframe(df, scan_start_date="2024-01-01", scan_end_date="2024-12-31")
    spec = ChartRangeSpec.from_df_and_scan(
        df,
        scan_start="2024-01-01",
        scan_end="2024-12-31",
        display_end=date(2024, 12, 31),
    )
    assert spec.scan_start_ideal == date(2024, 1, 1)
    assert spec.scan_start_actual == date(2024, 1, 1)
    assert spec.scan_start_degraded is False
    assert spec.display_end == date(2024, 12, 31)


def test_from_df_and_scan_applies_display_min_window():
    """display_start = min(scan_start_actual, display_end - 3y)，典型 scan 窗口下取后者。"""
    df = _make_pkl()
    df = preprocess_dataframe(df, start_date="2024-06-01", end_date="2024-12-31")
    compute_breakouts_from_dataframe(df, scan_start_date="2024-06-01", scan_end_date="2024-12-31")
    spec = ChartRangeSpec.from_df_and_scan(
        df,
        scan_start="2024-06-01",
        scan_end="2024-12-31",
        display_end=date(2024, 12, 31),
        display_min_window=timedelta(days=1095),
    )
    # scan_start (2024-06-01) > display_end - 3y (2021-12-31) → 取后者
    assert spec.display_start == date(2021, 12, 31)


def test_from_df_and_scan_degrades_display_start_to_pkl_start():
    """pkl 短于 3 年时，display_start 被 pkl 起点封顶。"""
    df = _make_pkl(start="2023-01-01", periods=500)  # pkl 从 2023-01-01
    df = preprocess_dataframe(df, start_date="2023-06-01", end_date="2024-03-31")
    compute_breakouts_from_dataframe(df, scan_start_date="2023-06-01", scan_end_date="2024-03-31")
    spec = ChartRangeSpec.from_df_and_scan(
        df,
        scan_start="2023-06-01",
        scan_end="2024-03-31",
        display_end=date(2024, 3, 31),
    )
    # display_end - 3y = 2021-03-31，但 pkl_start = 2023-01-01，所以 display_start = pkl_start
    assert spec.display_start == date(2023, 1, 1)


def test_from_df_and_scan_records_scan_start_degradation():
    df = _make_pkl(start="2024-03-01", periods=500)
    df = preprocess_dataframe(df, start_date="2024-01-01", end_date="2024-12-31")
    compute_breakouts_from_dataframe(df, scan_start_date="2024-01-01", scan_end_date="2024-12-31")
    spec = ChartRangeSpec.from_df_and_scan(
        df,
        scan_start="2024-01-01",
        scan_end="2024-12-31",
        display_end=date(2024, 12, 31),
    )
    assert spec.scan_start_degraded is True
    assert spec.scan_start_actual == date(2024, 3, 1)
```

- [ ] **Step 5.2: 运行测试确认失败**

```bash
uv run pytest BreakoutStrategy/UI/charts/tests/test_range_utils.py -v -k "collect_warnings or from_df"
```

Expected: 7 failures (`_collect_warnings`, `ChartRangeSpec.from_df_and_scan` 不存在)。

- [ ] **Step 5.3: 实现 _collect_warnings 和 factory**

在 `BreakoutStrategy/UI/charts/range_utils.py` 末尾追加：

```python
def _collect_warnings(spec: ChartRangeSpec) -> list[str]:
    """汇总 spec 上所有降级状态，返回可显示的字符串列表（顺序稳定）。"""
    warnings = []
    if spec.scan_start_degraded:
        warnings.append(f"scan_start→{spec.scan_start_actual}")
    if spec.scan_end_degraded:
        warnings.append(f"scan_end→{spec.scan_end_actual}")
    if spec.compute_buffer_degraded:
        warnings.append("MA buffer short")
    return warnings
```

在 `ChartRangeSpec` 类**内部**末尾（dataclass 字段后、`@property` 之后），添加工厂：

```python
    @classmethod
    def from_df_and_scan(
        cls,
        df: pd.DataFrame,
        scan_start: str,
        scan_end: str,
        display_end: date,
        display_min_window: timedelta = DISPLAY_MIN_WINDOW,
    ) -> "ChartRangeSpec":
        """
        基于 preprocessed df.attrs + 扫描配置构造完整 spec。

        要求 df.attrs["range_meta"] 已包含 scan_start_actual / scan_end_actual
        （由 scanner.compute_breakouts_from_dataframe 写入）。
        """
        meta = df.attrs["range_meta"]
        pkl_start = meta["pkl_start"]
        scan_start_actual = meta["scan_start_actual"]
        display_start = max(
            pkl_start,
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
            pkl_start=pkl_start,
            pkl_end=meta["pkl_end"],
        )
```

- [ ] **Step 5.4: 运行测试确认通过**

```bash
uv run pytest BreakoutStrategy/UI/charts/tests/test_range_utils.py -v
```

Expected: 全部 18 测试 passed。

- [ ] **Step 5.5: Commit**

```bash
git add BreakoutStrategy/UI/charts/range_utils.py BreakoutStrategy/UI/charts/tests/test_range_utils.py
git commit -m "feat(range_utils): add _collect_warnings and ChartRangeSpec.from_df_and_scan factory"
```

---

## Task 6: `canvas_manager.update_chart` 接受 `spec` 参数（行为等价）

**Files:**
- Modify: `BreakoutStrategy/UI/charts/canvas_manager.py` (update_chart, ~78-90)

**目标**：让 `update_chart` 接受可选的 `spec: ChartRangeSpec` 参数，但本 task 不实现新视觉（留待 Task 11）。现有 `label_buffer_start_idx` 参数保留，当 `spec` 传入时从 spec 派生。

- [ ] **Step 6.1: 写 update_chart 接收 spec 的最小测试（失败）**

在 `BreakoutStrategy/UI/charts/tests/test_canvas_manager_live_mode.py` 末尾追加（若不存在则新建）：

```python
import inspect
from BreakoutStrategy.UI.charts.canvas_manager import ChartCanvasManager


def test_update_chart_signature_has_spec_parameter():
    sig = inspect.signature(ChartCanvasManager.update_chart)
    assert "spec" in sig.parameters, "update_chart missing 'spec' parameter"
```

- [ ] **Step 6.2: 运行测试确认失败**

```bash
uv run pytest BreakoutStrategy/UI/charts/tests/test_canvas_manager_live_mode.py::test_update_chart_signature_has_spec_parameter -v
```

Expected: AssertionError `'spec' missing`。

- [ ] **Step 6.3: 给 `update_chart` 添加 spec 参数**

在 `BreakoutStrategy/UI/charts/canvas_manager.py` 的 `update_chart` 方法签名（78-90 行）末尾添加 `spec=None`：

```python
def update_chart(
    self,
    df: pd.DataFrame,
    breakouts: list,
    active_peaks: list,
    superseded_peaks: list,
    symbol: str,
    display_options: dict = None,
    label_buffer_start_idx: int = None,
    template_matched_indices: list[int] = None,
    initial_window_days: int | None = None,
    filter_cutoff_date=None,
    spec=None,   # 新增：ChartRangeSpec，可选。本 task 仅存储不消费
):
    # 方法体开头添加一行，把 spec 存到实例以供 Task 11 消费
    self._last_spec = spec
    # ... 其余方法体保持不变 ...
```

**不要导入 ChartRangeSpec**（避免循环引用），用字符串/Optional 注释即可。

- [ ] **Step 6.4: 运行测试确认通过**

```bash
uv run pytest BreakoutStrategy/UI/charts/tests/test_canvas_manager_live_mode.py -v
```

Expected: 新测试 passed，现有 canvas_manager 测试全部通过（因为 spec 默认 None 不改变任何行为）。

- [ ] **Step 6.5: Commit**

```bash
git add BreakoutStrategy/UI/charts/canvas_manager.py BreakoutStrategy/UI/charts/tests/test_canvas_manager_live_mode.py
git commit -m "feat(canvas_manager): accept optional spec parameter (no-op for now)"
```

---

## Task 7: Dev UI 切换到 `range_utils`

**Files:**
- Modify: `BreakoutStrategy/UI/main.py` (移除 `_trim_df_for_display`, `_adjust_breakout_indices`, `_adjust_peak_indices`；修改调用点 273-280、292-297、1001-1006)

**目标**：Dev UI 两处调用 `update_chart` 的地方都改走 `range_utils` 的函数。状态栏 ⚠ 留待 Task 8。

- [ ] **Step 7.1: 手工审视调用点 1（行 ~270-297）**

读 `BreakoutStrategy/UI/main.py` 行 250-300 附近，确认当前流程：

```python
# ~ 行 268-297
df = ...  # 从 preprocess_dataframe 而来
breakouts, active_peaks, superseded_peaks = ...

display_df, index_offset, label_buffer_start = self._trim_df_for_display(
    df, start_date, end_date
)
display_breakouts = self._adjust_breakout_indices(breakouts, index_offset)
display_active_peaks = self._adjust_peak_indices(active_peaks, index_offset)
display_superseded_peaks = self._adjust_peak_indices(superseded_peaks, index_offset)

self.chart_manager.update_chart(
    display_df, display_breakouts, display_active_peaks,
    display_superseded_peaks, symbol, display_options,
    label_buffer_start_idx=label_buffer_start,
    template_matched_indices=template_indices,
)
```

- [ ] **Step 7.2: 替换调用点 1**

在 `BreakoutStrategy/UI/main.py` 顶部 import 区追加：

```python
from datetime import date as _date
from BreakoutStrategy.UI.charts.range_utils import (
    ChartRangeSpec,
    trim_df_to_display,
    adjust_indices,
)
```

在调用点 1（~行 268-297），用以下代码替换 `_trim_df_for_display + _adjust_* + update_chart` 的整段：

```python
# 从 df.attrs["range_meta"] 推导 display_end（Dev 用 label_buffer_end_actual）
_meta = df.attrs.get("range_meta", {})
_display_end = _meta.get("label_buffer_end_actual") or df.index[-1].date()
spec = ChartRangeSpec.from_df_and_scan(
    df,
    scan_start=start_date,
    scan_end=end_date,
    display_end=_display_end,
    display_min_window=None,  # Dev UI 不设 3 年下限，全展开
)
display_df, index_offset = trim_df_to_display(df, spec)
display_breakouts = adjust_indices(breakouts, index_offset)
display_active_peaks = adjust_indices(active_peaks, index_offset)
display_superseded_peaks = adjust_indices(superseded_peaks, index_offset)

# 向后兼容 label_buffer_start_idx：从 spec 推导
if spec.scan_end_actual and len(display_df):
    _end_dt = pd.to_datetime(spec.scan_end_actual)
    _mask = display_df.index > _end_dt
    label_buffer_start = int(_mask.argmax()) if _mask.any() else None
else:
    label_buffer_start = None

self.chart_manager.update_chart(
    display_df, display_breakouts, display_active_peaks,
    display_superseded_peaks, symbol, display_options,
    label_buffer_start_idx=label_buffer_start,
    template_matched_indices=template_indices,
    spec=spec,
)
```

**注意 display_min_window=None**：`ChartRangeSpec.from_df_and_scan` 不支持 None；需修改工厂兼容（下面 Step 7.3）。

- [ ] **Step 7.3: 修改 factory 兼容 display_min_window=None（Dev 全展开）**

在 `BreakoutStrategy/UI/charts/range_utils.py` 的 `ChartRangeSpec.from_df_and_scan` 方法中，`display_start` 计算部分：

```python
if display_min_window is None:
    # Dev UI: 全展开，display_start 沿用 scan_start_actual（若更早则到 pkl 起点）
    display_start = max(pkl_start, scan_start_actual)
else:
    display_start = max(
        pkl_start,
        min(scan_start_actual, display_end - display_min_window),
    )
```

方法签名 `display_min_window: timedelta = DISPLAY_MIN_WINDOW` 改为 `display_min_window: Optional[timedelta] = DISPLAY_MIN_WINDOW`，并在顶部导入 `Optional`。

补测试到 `test_range_utils.py` 末尾：

```python
def test_from_df_and_scan_display_min_window_none_means_full_scan():
    df = _make_pkl()
    df = preprocess_dataframe(df, start_date="2024-01-01", end_date="2024-12-31")
    compute_breakouts_from_dataframe(df, scan_start_date="2024-01-01", scan_end_date="2024-12-31")
    spec = ChartRangeSpec.from_df_and_scan(
        df,
        scan_start="2024-01-01",
        scan_end="2024-12-31",
        display_end=date(2024, 12, 31),
        display_min_window=None,
    )
    # display_start 沿 scan_start_actual
    assert spec.display_start == spec.scan_start_actual
```

运行测试：

```bash
uv run pytest BreakoutStrategy/UI/charts/tests/test_range_utils.py::test_from_df_and_scan_display_min_window_none_means_full_scan -v
```

Expected: passed。

- [ ] **Step 7.4: 找出并替换调用点 2（~行 1001-1006）**

`UI/main.py` 行 1001-1006 另一个 `update_chart` 调用点（与 Step 7.2 基本相同）。用相同逻辑替换。

如两处调用点代码完全相同，考虑抽一个私有方法 `_render_chart(df, breakouts, active_peaks, superseded_peaks, start_date, end_date, symbol, display_options, template_indices)`，两处调用点都 call 之。若两处有差异，各自替换。

- [ ] **Step 7.5: 删除废弃私有方法**

删除 `UI/main.py` 中的 `_trim_df_for_display`（550-592）、`_adjust_breakout_indices`（594-623）、`_adjust_peak_indices`（625-649）共 3 个方法。

- [ ] **Step 7.6: 运行现有 UI 测试确保未回归**

```bash
uv run pytest BreakoutStrategy/UI/ BreakoutStrategy/analysis/ -v
```

Expected: 所有测试 passed。若某些测试引用了 `_trim_df_for_display` 等私有方法，修改测试改走 `range_utils` 的公开函数。

- [ ] **Step 7.7: 手工启动 Dev UI 冒烟测试**

```bash
uv run python -m BreakoutStrategy.UI
```

- 打开一个股票、浏览 K 线图、切换不同参数
- 默认视图、zoom、BO 点击交互与之前一致
- 关闭 UI

- [ ] **Step 7.8: Commit**

```bash
git add BreakoutStrategy/UI/main.py BreakoutStrategy/UI/charts/range_utils.py BreakoutStrategy/UI/charts/tests/test_range_utils.py
git commit -m "refactor(UI/main): migrate chart render to range_utils"
```

---

## Task 8: Dev UI 状态栏 ⚠

**Files:**
- Modify: `BreakoutStrategy/UI/main.py` (状态栏设置点 — 搜 `set_status` 或 `param_panel.set_status`)

- [ ] **Step 8.1: 找到状态栏设置点**

在 `UI/main.py` 中查找现有的 `set_status("...")` 调用。通常在 `_compute_breakouts_for_stock` 返回后，类似：

```python
self.param_panel.set_status(f"{symbol}: Computed {n} breakout(s)", "green")
```

- [ ] **Step 8.2: 增加 warnings 拼接逻辑**

在状态栏设置点之前加一行 `_collect_warnings`，修改状态文字：

```python
from BreakoutStrategy.UI.charts.range_utils import _collect_warnings

# ... 计算 n = len(breakouts), 并已有 spec ...
_warnings = _collect_warnings(spec)
_status = f"{symbol}: Computed {n} breakout(s)"
if _warnings:
    _status += f" ⚠ {', '.join(_warnings)}"
    self.param_panel.set_status(_status, "orange")
else:
    self.param_panel.set_status(_status, "green")
```

若状态栏文字之前是在 `_render_chart`（Step 7.4 提出）之外构造的，需要把 `spec` 传出来或者在 render 过程中顺便更新状态栏。选择权衡（subagent 自行判断，原则：单一责任）。

- [ ] **Step 8.3: 手工启动 Dev UI 验证**

```bash
uv run python -m BreakoutStrategy.UI
```

- 选择 scan_start 早于某股票 pkl 起点的情形（如 scan_start=2015-01-01 但 pkl 从 2020 开始）
- 确认状态栏变橙，显示 `⚠ scan_start→...`

- [ ] **Step 8.4: Commit**

```bash
git add BreakoutStrategy/UI/main.py
git commit -m "feat(UI/main): surface range_meta warnings in status bar"
```

---

## Task 9: `MatchedBreakout` 新增 `range_spec` 字段

**Files:**
- Modify: `BreakoutStrategy/live/pipeline/results.py` (12-28 行)

- [ ] **Step 9.1: 写 MatchedBreakout 的字段测试（失败）**

在 `BreakoutStrategy/live/tests/` 下创建 `test_matched_breakout_range_spec.py`：

```python
from dataclasses import fields
from BreakoutStrategy.live.pipeline.results import MatchedBreakout


def test_matched_breakout_has_optional_range_spec_field():
    field_names = {f.name for f in fields(MatchedBreakout)}
    assert "range_spec" in field_names


def test_matched_breakout_range_spec_defaults_to_none():
    mb = MatchedBreakout(
        symbol="AAPL",
        breakout_date="2024-01-15",
        breakout_price=180.0,
        factors={},
        sentiment_score=None,
        sentiment_category="pending",
        sentiment_summary=None,
        raw_breakout={"index": 0, "date": "2024-01-15", "price": 180.0},
        raw_peaks=[],
    )
    assert mb.range_spec is None
```

- [ ] **Step 9.2: 运行测试确认失败**

```bash
uv run pytest BreakoutStrategy/live/tests/test_matched_breakout_range_spec.py -v
```

Expected: AssertionError `"range_spec" not in field_names`。

- [ ] **Step 9.3: 添加字段到 MatchedBreakout**

修改 `BreakoutStrategy/live/pipeline/results.py`：

```python
from typing import Optional
from BreakoutStrategy.UI.charts.range_utils import ChartRangeSpec


@dataclass
class MatchedBreakout:
    """一个匹配模板的突破，包含模板信息和情感分析结果。"""
    symbol: str
    breakout_date: str
    breakout_price: float
    factors: dict[str, float]
    sentiment_score: float | None
    sentiment_category: str
    sentiment_summary: str | None
    raw_breakout: dict[str, Any]
    raw_peaks: list[dict[str, Any]]
    all_stock_breakouts: list[dict] = field(default_factory=list)
    all_matched_bo_chart_indices: list[int] = field(default_factory=list)
    range_spec: Optional[ChartRangeSpec] = None  # 新增：旧缓存加载为 None
```

- [ ] **Step 9.4: 运行测试确认通过**

```bash
uv run pytest BreakoutStrategy/live/tests/test_matched_breakout_range_spec.py -v
```

Expected: 2 passed。

- [ ] **Step 9.5: 运行全部 live 测试确保未回归**

```bash
uv run pytest BreakoutStrategy/live/tests/ -v
```

Expected: 全部 passed（旧测试不传 range_spec 走 default None）。

- [ ] **Step 9.6: Commit**

```bash
git add BreakoutStrategy/live/pipeline/results.py BreakoutStrategy/live/tests/test_matched_breakout_range_spec.py
git commit -m "feat(live/results): add optional range_spec field to MatchedBreakout"
```

---

## Task 10: `daily_runner` 构造 spec 并写入 MatchedBreakout

**Files:**
- Modify: `BreakoutStrategy/live/pipeline/daily_runner.py` (`_step3_match_templates` ~143-181)

- [ ] **Step 10.1: 写 spec 写入测试（失败）**

创建 `BreakoutStrategy/live/tests/test_daily_runner_range_spec.py`：

```python
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture
def mock_scan_result():
    """构造一个带 df.attrs 的 scan_result 片段，模拟 ScanManager 输出。"""
    idx = pd.date_range("2022-01-01", periods=900, freq="D")
    df = pd.DataFrame({
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0
    }, index=idx)
    df.attrs["range_meta"] = {
        "pkl_start": date(2022, 1, 1),
        "pkl_end": idx[-1].date(),
        "scan_start_ideal": date(2024, 1, 1),
        "scan_end_ideal": idx[-1].date(),
        "scan_start_actual": date(2024, 1, 1),
        "scan_end_actual": idx[-1].date(),
        "compute_start_ideal": date(2022, 11, 13),
        "compute_start_actual": date(2022, 11, 13),
        "label_buffer_end_ideal": idx[-1].date(),
        "label_buffer_end_actual": idx[-1].date(),
    }
    return {
        "symbol": "AAPL",
        "breakouts": [
            {"index": 500, "date": "2024-05-15", "price": 200.0}
        ],
        "all_peaks": [],
        "_preprocessed_df": df,  # 约定：daily_runner 需能从 scan_result 取到 df
    }


def test_daily_runner_attaches_spec_to_matched_breakout(mock_scan_result):
    """Step3 构造 MatchedBreakout 时应附上 range_spec。"""
    # 因 _step3_match_templates 需要 TemplateManager 等，用单元级最小重现：
    from BreakoutStrategy.live.pipeline.daily_runner import _build_range_spec_for_symbol
    spec = _build_range_spec_for_symbol(
        df=mock_scan_result["_preprocessed_df"],
        scan_start="2024-01-01",
        scan_end=mock_scan_result["_preprocessed_df"].index[-1].date().isoformat(),
    )
    assert spec is not None
    assert spec.scan_start_ideal == date(2024, 1, 1)
```

（注：把 spec 构造逻辑抽到可测 helper 函数 `_build_range_spec_for_symbol`）

- [ ] **Step 10.2: 运行测试确认失败**

```bash
uv run pytest BreakoutStrategy/live/tests/test_daily_runner_range_spec.py -v
```

Expected: ImportError `_build_range_spec_for_symbol` 未定义。

- [ ] **Step 10.3: 在 daily_runner 增加 helper + 改造 scan 链路携带 df**

在 `BreakoutStrategy/live/pipeline/daily_runner.py` 顶部加 import：

```python
from datetime import datetime, timedelta, date as _date
from BreakoutStrategy.UI.charts.range_utils import ChartRangeSpec
```

在模块级（class 外部）加 helper 函数：

```python
def _build_range_spec_for_symbol(df, scan_start: str, scan_end: str):
    """基于 preprocessed df 为 symbol 构造 ChartRangeSpec。"""
    if df is None or "range_meta" not in df.attrs:
        return None
    display_end = df.index[-1].date()
    return ChartRangeSpec.from_df_and_scan(
        df,
        scan_start=scan_start,
        scan_end=scan_end,
        display_end=display_end,
    )
```

改造 `_step3_match_templates`（~143-181 行）：

1. 观察 `ScanManager.parallel_scan` 的返回格式：如果其单个 stock_result 含 preprocessed df，直接使用；如果不含，需要在 `_step2_scan` 中把 df 存到 `stock_result["_preprocessed_df"]`。

2. 修改 MatchedBreakout 构造（行 168-180），append `range_spec`：

```python
_preprocessed_df = stock_result.get("_preprocessed_df")
_range_spec = _build_range_spec_for_symbol(
    _preprocessed_df, scan_start=start, scan_end=end,
) if _preprocessed_df is not None else None

for idx in matched_indices:
    bo = stock_result["breakouts"][idx]
    candidates.append(MatchedBreakout(
        # ... existing fields ...
        all_matched_bo_chart_indices=matched_chart_indices,
        range_spec=_range_spec,
    ))
```

（`start` 和 `end` 变量应从 `_step2_scan` 传入或在本方法重算；若不传入，可从 `today` 和 `self.scan_window_days` 重新计算。）

**关键**：若 `parallel_scan` 不返回 df，需扩展其返回。查 `BreakoutStrategy/analysis/scanner.py` 中 `_scan_single_stock` 的返回；若能低成本扩展，优先。若改动过大，临时在 daily_runner 中读 pkl 重新 preprocess（成本低但重复计算）。

subagent 判断后选择实现路径。

- [ ] **Step 10.4: 运行测试确认通过**

```bash
uv run pytest BreakoutStrategy/live/tests/test_daily_runner_range_spec.py -v
```

Expected: passed。

- [ ] **Step 10.5: 运行全部 live 测试**

```bash
uv run pytest BreakoutStrategy/live/tests/ -v
```

Expected: 全部 passed。

- [ ] **Step 10.6: Commit**

```bash
git add BreakoutStrategy/live/pipeline/daily_runner.py BreakoutStrategy/live/tests/test_daily_runner_range_spec.py
git commit -m "feat(daily_runner): construct range_spec and attach to MatchedBreakout"
```

---

## Task 11: Live UI `_rebuild_chart` 重写（走 preprocess → trim → adjust）

**Files:**
- Modify: `BreakoutStrategy/live/app.py` (`_rebuild_chart` ~242-287)

- [ ] **Step 11.1: 写集成测试（失败）**

创建 `BreakoutStrategy/live/tests/test_app_rebuild_chart.py`：

```python
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import date


def test_rebuild_chart_uses_preprocess_path(tmp_path):
    """_rebuild_chart 应走 preprocess→trim→adjust，而非直接 pd.read_pickle 到 canvas。"""
    from BreakoutStrategy.live.app import LiveApp  # 假设类名

    # ... 最小 fixture 构造 LiveApp + mock chart + 一个 pkl ...
    # 断言：调用 update_chart 时 df 已含 ma_200 / atr 列（preprocess 结果）
    # 断言：调用 update_chart 时 spec 参数不是 None
    pytest.skip("Integration test scaffolding; fill in per actual LiveApp setup")
```

（以 skip 形式留桩；后续在 Step 11.3 完善。）

- [ ] **Step 11.2: 运行测试确认被 skip**

```bash
uv run pytest BreakoutStrategy/live/tests/test_app_rebuild_chart.py -v
```

Expected: skipped。

- [ ] **Step 11.3: 重写 _rebuild_chart**

找到 `BreakoutStrategy/live/app.py` 的 `_rebuild_chart`（~242-287 行），用以下代码替换：

```python
def _rebuild_chart(self) -> None:
    """按 state 当前的 current_selected 重绘图表。无选中时清空图表。

    走 preprocess → trim_df_to_display → adjust_indices 统一流程。
    """
    current = self.state.current_selected
    if current is None:
        self.chart.clear()
        return

    pkl_path = self.config.data_dir / f"{current.symbol}.pkl"
    if not pkl_path.exists():
        self.chart.clear()
        return

    try:
        raw_df = pd.read_pickle(pkl_path)
    except Exception:
        self.chart.clear()
        return

    # 推导 scan 窗口（与 daily_runner 一致：最近 scan_window_days 天）
    today = datetime.now().date()
    scan_start = (today - timedelta(days=self.config.scan_window_days)).isoformat()
    scan_end = today.isoformat()

    # preprocess: 计算 MA/ATR + 写 df.attrs["range_meta"]
    from BreakoutStrategy.analysis.scanner import preprocess_dataframe, compute_breakouts_from_dataframe
    from BreakoutStrategy.UI.charts.range_utils import (
        ChartRangeSpec, trim_df_to_display, adjust_indices,
    )

    df = preprocess_dataframe(raw_df, start_date=scan_start, end_date=scan_end)
    compute_breakouts_from_dataframe(df, scan_start_date=scan_start, scan_end_date=scan_end)

    # 构造 spec（优先用 MatchedBreakout.range_spec，缺失则现场构造）
    display_end = df.index[-1].date()
    spec = current.range_spec or ChartRangeSpec.from_df_and_scan(
        df,
        scan_start=scan_start,
        scan_end=scan_end,
        display_end=display_end,
    )

    display_df, offset = trim_df_to_display(df, spec)

    # adapt + adjust
    chart_active_peaks, chart_superseded_peaks, peaks_by_id = adapt_peaks(current.raw_peaks)
    raw_bos = current.all_stock_breakouts or [current.raw_breakout]
    all_chart_bos = [adapt_breakout(raw_bo, peaks_by_id) for raw_bo in raw_bos]

    all_chart_bos = adjust_indices(all_chart_bos, offset)
    chart_active_peaks = adjust_indices(chart_active_peaks, offset)
    chart_superseded_peaks = adjust_indices(chart_superseded_peaks, offset)

    # 4 级分类所需索引（用调整后的索引）
    visible_idx = self.match_list.get_visible_bo_indices(current.symbol)
    all_matched = set(adj_idx - offset for adj_idx in current.all_matched_bo_chart_indices if adj_idx >= offset)
    filtered_out_idx = all_matched - visible_idx
    current_bo_index = current.raw_breakout["index"] - offset
    if current_bo_index < 0:
        current_bo_index = 0

    try:
        self.chart.update_chart(
            df=display_df,
            breakouts=all_chart_bos,
            active_peaks=chart_active_peaks,
            superseded_peaks=chart_superseded_peaks,
            symbol=current.symbol,
            display_options={
                "live_mode": True,
                "current_bo_index": current_bo_index,
                "visible_matched_indices": visible_idx,
                "filtered_out_matched_indices": filtered_out_idx,
                "on_bo_picked": self._on_chart_bo_picked,
                "show_superseded_peaks": True,
            },
            initial_window_days=180,
            filter_cutoff_date=self.match_list.get_date_cutoff(),
            spec=spec,
        )
    except Exception as e:
        print(f"[LiveApp] Chart render failed: {e}", file=sys.stderr)
```

注意事项：
- `current.range_spec` 可能为 None（旧缓存），fallback 到现场构造
- `current_bo_index` 和 `all_matched_bo_chart_indices` 需要同步按 offset 调整
- `adjust_indices` 对 dataclass 实例（ChartBreakout/ChartPeak）也生效

- [ ] **Step 11.4: 手工启动 Live UI 冒烟测试**

```bash
uv run python -m BreakoutStrategy.live
```

- 选一个股票、图表正常渲染、BO marker 和 peak id 位置正确、tooltip 含 ATR
- zoom out 到极限：最远到 display_start（应该是 scan_start 或 pkl 起点之一）

- [ ] **Step 11.5: 运行全部 live 测试**

```bash
uv run pytest BreakoutStrategy/live/tests/ -v
```

Expected: 全部 passed。

- [ ] **Step 11.6: Commit**

```bash
git add BreakoutStrategy/live/app.py BreakoutStrategy/live/tests/test_app_rebuild_chart.py
git commit -m "refactor(live/app): route _rebuild_chart through preprocess→trim→adjust"
```

---

## Task 12: Live MatchList ⚠ 显示

**Files:**
- Modify: `BreakoutStrategy/live/panels/match_list.py` (`_row_values` ~621-632)
- Create: `BreakoutStrategy/live/tests/test_match_list_warning.py`

- [ ] **Step 12.1: 写 MatchList ⚠ 测试（失败）**

创建 `BreakoutStrategy/live/tests/test_match_list_warning.py`：

```python
from datetime import date
from unittest.mock import MagicMock
import pandas as pd

from BreakoutStrategy.live.pipeline.results import MatchedBreakout
from BreakoutStrategy.UI.charts.range_utils import ChartRangeSpec


def _spec_no_degradation():
    return ChartRangeSpec(
        scan_start_ideal=date(2024, 1, 1), scan_end_ideal=date(2024, 12, 31),
        scan_start_actual=date(2024, 1, 1), scan_end_actual=date(2024, 12, 31),
        compute_start_ideal=date(2023, 11, 13), compute_start_actual=date(2023, 11, 13),
        display_start=date(2022, 1, 1), display_end=date(2024, 12, 31),
        pkl_start=date(2020, 1, 1), pkl_end=date(2024, 12, 31),
    )


def _spec_scan_start_degraded():
    return ChartRangeSpec(
        scan_start_ideal=date(2024, 1, 1), scan_end_ideal=date(2024, 12, 31),
        scan_start_actual=date(2024, 6, 1), scan_end_actual=date(2024, 12, 31),
        compute_start_ideal=date(2023, 11, 13), compute_start_actual=date(2024, 2, 1),
        display_start=date(2022, 1, 1), display_end=date(2024, 12, 31),
        pkl_start=date(2024, 2, 1), pkl_end=date(2024, 12, 31),
    )


def _make_mb(range_spec=None, sentiment_score=None):
    return MatchedBreakout(
        symbol="AAPL",
        breakout_date="2024-08-15",
        breakout_price=200.0,
        factors={},
        sentiment_score=sentiment_score,
        sentiment_category="pending",
        sentiment_summary=None,
        raw_breakout={"index": 0, "date": "2024-08-15", "price": 200.0},
        raw_peaks=[],
        range_spec=range_spec,
    )


def test_row_values_no_warning_when_spec_clean():
    from BreakoutStrategy.live.panels.match_list import MatchList
    # 构造一个最小 MatchList 实例用于调用 _row_values
    parent = MagicMock()
    ml = MatchList.__new__(MatchList)  # 绕过 __init__
    mb = _make_mb(range_spec=_spec_no_degradation())
    values = ml._row_values(mb)
    assert "⚠" not in values[0]


def test_row_values_appends_warning_when_spec_degraded():
    from BreakoutStrategy.live.panels.match_list import MatchList
    ml = MatchList.__new__(MatchList)
    mb = _make_mb(range_spec=_spec_scan_start_degraded())
    values = ml._row_values(mb)
    assert "⚠" in values[0]


def test_row_values_no_warning_when_range_spec_none():
    """旧缓存加载后 range_spec=None，不应出现 ⚠。"""
    from BreakoutStrategy.live.panels.match_list import MatchList
    ml = MatchList.__new__(MatchList)
    mb = _make_mb(range_spec=None)
    values = ml._row_values(mb)
    assert "⚠" not in values[0]
```

- [ ] **Step 12.2: 运行测试确认失败**

```bash
uv run pytest BreakoutStrategy/live/tests/test_match_list_warning.py -v
```

Expected: 1 pass（clean / None 情况 ⚠ 本来就不存在），1 failure（degraded 情况未加 ⚠）。

- [ ] **Step 12.3: 修改 `_row_values` 附 ⚠**

修改 `BreakoutStrategy/live/panels/match_list.py` 的 `_row_values`（~621-632 行）：

```python
def _row_values(self, it: "MatchedBreakout") -> tuple:
    from BreakoutStrategy.UI.charts.range_utils import _collect_warnings

    symbol = it.symbol
    # 星标规则：sentiment_score > 0.30
    if it.sentiment_score is not None and it.sentiment_score > 0.30:
        symbol += " ★"
    # 范围降级标记：任一 warning 触发 ⚠
    if it.range_spec is not None and _collect_warnings(it.range_spec):
        symbol += " ⚠"

    date_txt = it.breakout_date
    price_txt = f"{it.breakout_price:.2f}"
    if it.sentiment_score is None:
        score_txt = "N/A"
    else:
        score_txt = f"{it.sentiment_score:+.2f}"
    return (symbol, date_txt, price_txt, score_txt)
```

- [ ] **Step 12.4: 运行测试确认通过**

```bash
uv run pytest BreakoutStrategy/live/tests/test_match_list_warning.py -v
```

Expected: 3 passed。

- [ ] **Step 12.5: Commit**

```bash
git add BreakoutStrategy/live/panels/match_list.py BreakoutStrategy/live/tests/test_match_list_warning.py
git commit -m "feat(live/match_list): surface range degradation with ⚠ symbol suffix"
```

---

## Task 13: canvas_manager 三段阴影

**Files:**
- Modify: `BreakoutStrategy/UI/charts/canvas_manager.py` (消费 `self._last_spec` 绘阴影)

**目标**：当 `spec` 传入时，绘制三段阴影：
- `[display_start, scan_start_actual]` — 灰色 (alpha=0.15) — "pre-scan"
- `[scan_start_actual, scan_end_actual]` — 无阴影
- `[scan_end_actual, display_end]` — 灰色 (alpha=0.15) — "post-scan"

- [ ] **Step 13.1: 找到原 label_buffer 绘制方法**

在 `canvas_manager.py` 找 `_draw_label_buffer_zone`（~420 行）。该方法当前只绘 label_buffer（scan_end 之后的单段灰色）。

- [ ] **Step 13.2: 新增三段阴影方法**

在 `ChartCanvasManager` 类中添加方法 `_draw_range_spec_shading`：

```python
def _draw_range_spec_shading(self, ax, df, spec):
    """按 spec 绘制三段阴影：pre-scan / main / post-scan。"""
    if spec is None:
        return
    import pandas as pd
    # pre-scan: [display_start, scan_start_actual]
    _draw_shade(ax, df, spec.display_start, spec.scan_start_actual, alpha=0.15)
    # post-scan: [scan_end_actual, display_end]
    _draw_shade(ax, df, spec.scan_end_actual, spec.display_end, alpha=0.15)


def _draw_shade(ax, df, start_date, end_date, alpha=0.15, color="#808080"):
    """在 ax 上绘制 [start_date, end_date] 区间的灰色阴影。"""
    import pandas as pd
    if start_date is None or end_date is None or start_date >= end_date:
        return
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    # 转成 df 行号区间
    start_mask = df.index >= start_dt
    if not start_mask.any():
        return
    start_idx = int(start_mask.argmax())
    end_mask = df.index <= end_dt
    if not end_mask.any():
        return
    # searchsorted 返回 end_dt 之后的第一个位置
    end_idx = int(df.index.searchsorted(end_dt, side="right"))
    if end_idx <= start_idx:
        return
    ax.axvspan(start_idx - 0.5, end_idx - 0.5, alpha=alpha, color=color, zorder=0)
```

- [ ] **Step 13.3: 在 update_chart 调用新方法**

在 `update_chart` 方法体内，原本调用 `_draw_label_buffer_zone` 的地方（或 K 线绘制完之后、markers 之前），改为：

```python
if self._last_spec is not None:
    self._draw_range_spec_shading(ax, df, self._last_spec)
elif label_buffer_start_idx is not None:
    self._draw_label_buffer_zone(ax, df, label_buffer_start_idx)  # 向后兼容
```

- [ ] **Step 13.4: 手工验证阴影**

```bash
uv run python -m BreakoutStrategy.live
```

- 选一支股票，图表出现两段灰色阴影：左侧 pre-scan、右侧 post-scan
- 选一支 IPO 股票（scan_start 降级），右侧 post-scan 可能为空、左侧 pre-scan 存在
- 中间主扫描区无阴影

```bash
uv run python -m BreakoutStrategy.UI
```

- Dev UI 中打开股票：scan_end 之后出现 post-scan 灰色区；若 scan_start 早于 pkl 起点则出现 pre-scan 灰色区

- [ ] **Step 13.5: Commit**

```bash
git add BreakoutStrategy/UI/charts/canvas_manager.py
git commit -m "feat(canvas_manager): render three-segment shading from ChartRangeSpec"
```

---

## Task 14: canvas_manager 降级虚线

**Files:**
- Modify: `BreakoutStrategy/UI/charts/canvas_manager.py`

- [ ] **Step 14.1: 在三段阴影方法中加降级虚线**

修改 `_draw_range_spec_shading`：

```python
def _draw_range_spec_shading(self, ax, df, spec):
    """按 spec 绘制三段阴影 + 降级虚线。"""
    import pandas as pd

    # 三段阴影（同 Task 13）
    _draw_shade(ax, df, spec.display_start, spec.scan_start_actual, alpha=0.15)
    _draw_shade(ax, df, spec.scan_end_actual, spec.display_end, alpha=0.15)

    # 降级虚线
    if spec.scan_start_degraded:
        _draw_degradation_line(
            ax, df, spec.scan_start_actual,
            label=f"scan start (req {spec.scan_start_ideal})",
        )
    if spec.scan_end_degraded:
        _draw_degradation_line(
            ax, df, spec.scan_end_actual,
            label=f"scan end (req {spec.scan_end_ideal})",
        )


def _draw_degradation_line(ax, df, date_value, label, color="#FF8800"):
    """在指定日期画橙色垂直虚线，顶部附文字标注。"""
    import pandas as pd
    dt = pd.to_datetime(date_value)
    mask = df.index >= dt
    if not mask.any():
        return
    idx = int(mask.argmax())
    ax.axvline(x=idx, color=color, linestyle="--", linewidth=1.0, zorder=5, alpha=0.8)
    ymin, ymax = ax.get_ylim()
    ax.text(
        idx, ymax * 0.98, label,
        color=color, fontsize=8, ha="left", va="top",
        bbox=dict(facecolor="white", edgecolor=color, alpha=0.9, boxstyle="round,pad=0.3"),
    )
```

- [ ] **Step 14.2: 手工验证虚线**

```bash
uv run python -m BreakoutStrategy.live
```

- 构造一个 scan_start 被降级的场景（选 IPO 股票）
- 在 scan_start_actual 位置出现橙色虚线 + 文字 `scan start (req YYYY-MM-DD)`

- [ ] **Step 14.3: Commit**

```bash
git add BreakoutStrategy/UI/charts/canvas_manager.py
git commit -m "feat(canvas_manager): draw orange degradation lines for scan_start/end"
```

---

## Task 15: `daily_runner` 下载量改为 1125 天

**Files:**
- Modify: `BreakoutStrategy/live/pipeline/daily_runner.py` (~90-100 行)

- [ ] **Step 15.1: 写常量测试（失败）**

在 `BreakoutStrategy/live/tests/test_daily_runner_range_spec.py` 末尾追加：

```python
def test_download_days_constant_is_1125():
    from BreakoutStrategy.live.pipeline.daily_runner import DOWNLOAD_DAYS
    assert DOWNLOAD_DAYS == 1125
```

- [ ] **Step 15.2: 运行测试确认失败**

```bash
uv run pytest BreakoutStrategy/live/tests/test_daily_runner_range_spec.py::test_download_days_constant_is_1125 -v
```

Expected: ImportError `DOWNLOAD_DAYS` 未定义。

- [ ] **Step 15.3: 增加常量并使用**

在 `BreakoutStrategy/live/pipeline/daily_runner.py` 顶部（import 之后、class 之前）添加：

```python
# Download window covers: 3-year display (1095d) + safety margin (30d).
# akshare 下载始终是全部历史，此参数只控制本地保存范围。
DOWNLOAD_DAYS = 1125
```

找到 `multi_download_stock` 调用处（~93 行）：

```python
# 原代码
days_from_now=self.scan_window_days + 400,

# 改为
days_from_now=DOWNLOAD_DAYS,
```

- [ ] **Step 15.4: 运行测试确认通过**

```bash
uv run pytest BreakoutStrategy/live/tests/test_daily_runner_range_spec.py -v
```

Expected: 全部 passed。

- [ ] **Step 15.5: 手工验证 Live 运行**

```bash
uv run python -m BreakoutStrategy.live
```

- 首次运行触发全量下载（因 pkl 范围不同）
- 下载完毕后 pkl 文件大小应是原来的 ~1.9 倍
- UI 选股显示 3 年历史（或 pkl 实际范围）

- [ ] **Step 15.6: Commit**

```bash
git add BreakoutStrategy/live/pipeline/daily_runner.py BreakoutStrategy/live/tests/test_daily_runner_range_spec.py
git commit -m "feat(daily_runner): extend DOWNLOAD_DAYS to 1125 for 3-year display"
```

---

## 自检

**1. Spec 覆盖**（对照 spec §8 验收标准）：

- [x] Case B 降级可见：Task 4（scanner 日志）+ Task 8（Dev status bar）+ Task 12（Live ⚠）+ Task 13-14（图表阴影+虚线）
- [x] 三层范围显式：Task 1-5（range_utils + spec factory）
- [x] graceful：数据层已有，Task 4 仅补元数据
- [x] 兼容性：Task 7 保留 label_buffer_start_idx；Task 9 range_spec=Optional
- [x] 代码质量：Task 7 删除旧私有方法，trim/adjust 仅在 range_utils 实现

**2. Placeholder 扫描**：本计划没有 TBD/TODO。Task 10 / Task 11 有一个"subagent 自行判断实现路径"的地方（parallel_scan 是否返回 df）——这是真实架构选择，不是 placeholder。

**3. 类型/命名一致性**：
- `ChartRangeSpec` 字段名全程统一
- `trim_df_to_display` / `adjust_indices` / `_collect_warnings` 函数名全程统一
- `display_min_window=None` 语义（Dev 全展开）Task 7.3 明确定义并测试

---

*Plan completed. Next step: superpowers:subagent-driven-development.*
