# BO Label Marker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 dev 模式 chart 上为每个 BO 在 marker 堆叠顶端新增一层"回测 label 值"显示，支持 checkbox 开关与运行时动态调整窗口天数 N；最大值 BO 以黄底高亮，其他以橙底显示。

**Architecture:**
- 抽出纯函数 `compute_label_value(df, index, n)` 放在 `analysis/features.py`，`FeatureCalculator._calculate_labels` 与 UI 渲染路径共用，消除公式漂移。
- UI 通过 `display_options` 字典把 `show_bo_label` / `bo_label_n` 透传到 `canvas_manager → markers.draw_breakouts`；markers 内部两遍结构：先算全部 BO 的 value 与 max，再按 tier 绘制 annotation。
- 新增堆叠层 `bo_label_value`（区别于现有 `bo_label` = `[broken_peak_ids]` 方框），位于堆叠最顶端。

**Tech Stack:** Python / pandas / matplotlib / tkinter (ttk.Spinbox, ttk.Checkbutton) / pytest

**Design Spec:** `docs/superpowers/specs/2026-04-23-bo-label-marker-design.md`

---

## File Structure

**Create:**
- `BreakoutStrategy/analysis/tests/test_label_helper.py` — helper 单测 + FeatureCalculator 回归
- `BreakoutStrategy/UI/charts/components/tests/test_bo_label_value.py` — tier 分类 + annotation 渲染测试

**Modify:**
- `BreakoutStrategy/analysis/features.py` — 新增模块级 `compute_label_value()`；`_calculate_labels()` 改为调 helper；同步 docstring
- `BreakoutStrategy/UI/styles.py` — `MARKER_STACK_GAPS_PT` 增 `bo_label_value: 30`；新增 `BO_LABEL_VALUE_TIER_STYLE`
- `BreakoutStrategy/UI/charts/components/markers.py` — `draw_breakouts()` 扩展两参数 + 两遍渲染
- `BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py` — 扩展堆叠偏移断言
- `BreakoutStrategy/UI/charts/canvas_manager.py` — 读 `display_options` 并透传
- `BreakoutStrategy/dev/panels/parameter_panel.py` — 新增 checkbox + Spinbox；`get_display_options()` 扩展
- `BreakoutStrategy/dev/main.py` — `load_scan_results()` 成功后调 `set_bo_label_n_default()`
- `configs/ui_config.yaml` — 新增 `show_bo_label: false`；删除死键 `show_peak_score`

---

## Task 1: `compute_label_value()` 纯函数 helper

**Files:**
- Modify: `BreakoutStrategy/analysis/features.py` (add module-level function after imports, around line 22)
- Create: `BreakoutStrategy/analysis/tests/test_label_helper.py`

- [ ] **Step 1: 写 helper 的失败测试**

Create `BreakoutStrategy/analysis/tests/test_label_helper.py`:

```python
"""Unit tests for compute_label_value helper in analysis/features.py."""
import pandas as pd
import pytest

from BreakoutStrategy.analysis.features import compute_label_value


def _make_df(closes: list[float]) -> pd.DataFrame:
    """Minimal OHLCV-shaped DataFrame; only 'close' is read by compute_label_value."""
    n = len(closes)
    return pd.DataFrame({
        "open":  closes,
        "high":  [c * 1.01 for c in closes],
        "low":   [c * 0.99 for c in closes],
        "close": closes,
        "volume": [1000] * n,
    })


def test_basic_positive_gain():
    # close at index 0 = 10; next 3 days closes = [11, 13, 12]; max = 13
    # label = (13 - 10) / 10 = 0.3
    df = _make_df([10.0, 11.0, 13.0, 12.0, 12.5])
    assert compute_label_value(df, 0, 3) == pytest.approx(0.3)


def test_basic_negative_gain():
    # close at index 0 = 10; next 3 closes = [9, 8, 9.5]; max = 9.5
    # label = (9.5 - 10) / 10 = -0.05
    df = _make_df([10.0, 9.0, 8.0, 9.5, 9.0])
    assert compute_label_value(df, 0, 3) == pytest.approx(-0.05)


def test_insufficient_future_data_returns_none():
    # only 2 days after index 0, asking for 3
    df = _make_df([10.0, 11.0, 12.0])
    assert compute_label_value(df, 0, 3) is None


def test_zero_breakout_price_returns_none():
    df = _make_df([0.0, 1.0, 2.0, 3.0])
    assert compute_label_value(df, 0, 2) is None


def test_negative_breakout_price_returns_none():
    df = _make_df([-1.0, 1.0, 2.0, 3.0])
    assert compute_label_value(df, 0, 2) is None


def test_window_excludes_breakout_day():
    # index 1, max_days=2: future = closes[2:4] = [8, 20]; max = 20
    # label = (20 - 10) / 10 = 1.0  (breakout_price = closes[1] = 10)
    df = _make_df([999.0, 10.0, 8.0, 20.0, 5.0])
    assert compute_label_value(df, 1, 2) == pytest.approx(1.0)
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_label_helper.py -v`
Expected: all tests FAIL with `ImportError: cannot import name 'compute_label_value'`

- [ ] **Step 3: 实现 `compute_label_value`**

In `BreakoutStrategy/analysis/features.py`, add after the top-level `DEBUG_VOLUME` constant (around line 22), **before** the `class FeatureCalculator:` line:

```python
def compute_label_value(
    df: pd.DataFrame, index: int, max_days: int
) -> Optional[float]:
    """计算单个突破点的回测 label 值。

    公式：(未来 max_days 天内最高收盘价 - 突破日收盘价) / 突破日收盘价
    - 基准价：突破日收盘价
    - 窗口：突破后 1 到 max_days 天（不含突破当日）
    - 未来价格用 close（与原 `_calculate_labels` 实现一致）

    Args:
        df: OHLCV DataFrame
        index: 突破点索引
        max_days: 回看窗口天数

    Returns:
        label 值；数据不足 max_days 天、或突破日收盘价非正时返回 None
    """
    breakout_price = df.iloc[index]["close"]
    if breakout_price <= 0:
        return None

    max_end = min(len(df), index + max_days + 1)
    future_data = df.iloc[index + 1 : max_end]
    if len(future_data) < max_days:
        return None

    max_high = future_data["close"].max()
    return (max_high - breakout_price) / breakout_price
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_label_helper.py -v`
Expected: 5 tests PASS.

- [ ] **Step 5: 提交**

```bash
git add BreakoutStrategy/analysis/features.py BreakoutStrategy/analysis/tests/test_label_helper.py
git commit -m "feat(analysis): add compute_label_value helper

抽出 label 公式到模块级纯函数，供 FeatureCalculator 与 UI 渲染共用。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: 重构 `_calculate_labels` 使用 helper + 回归测试

**Files:**
- Modify: `BreakoutStrategy/analysis/features.py:418-460` (`_calculate_labels` method)
- Modify: `BreakoutStrategy/analysis/tests/test_label_helper.py` (append regression test)

- [ ] **Step 1: 写回归测试（验证重构前后行为等价）**

Append to `BreakoutStrategy/analysis/tests/test_label_helper.py`:

```python
from BreakoutStrategy.analysis.features import FeatureCalculator


def test_calculate_labels_equivalent_to_helper():
    """FeatureCalculator._calculate_labels 输出应与直接调 helper 等价。"""
    df = _make_df([10.0, 11.0, 12.5, 11.8, 13.0, 12.0, 14.0, 13.5])
    fc = FeatureCalculator({
        "label_configs": [{"max_days": 3}, {"max_days": 5}],
    })

    labels = fc._calculate_labels(df, index=1)

    assert labels == {
        "label_3": compute_label_value(df, 1, 3),
        "label_5": compute_label_value(df, 1, 5),
    }


def test_calculate_labels_default_max_days_when_missing():
    """label_configs 中 config 字典缺 max_days 时，按原实现应使用 20 天默认值。"""
    df = _make_df([10.0] + [11.0] * 25)
    fc = FeatureCalculator({"label_configs": [{}]})

    labels = fc._calculate_labels(df, index=0)

    assert "label_20" in labels
    assert labels["label_20"] == compute_label_value(df, 0, 20)


def test_calculate_labels_empty_configs():
    df = _make_df([10.0, 11.0, 12.0, 13.0])
    fc = FeatureCalculator({"label_configs": []})
    assert fc._calculate_labels(df, index=0) == {}
```

- [ ] **Step 2: 运行测试，确认第一个失败**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_label_helper.py::test_calculate_labels_equivalent_to_helper -v`
Expected: test PASSES (原实现恰好就是对的) 或 FAILS (如有细微差异)。如果 PASS，继续下一步（仍要重构）；若 FAIL，说明原实现有 bug（不应发生）。

> 注：此测试此步的主要作用是在下一步重构前锁定行为。即使它此刻已通过，步骤 3 的重构也必须保持它继续通过。

- [ ] **Step 3: 重构 `_calculate_labels` 调用 helper**

In `BreakoutStrategy/analysis/features.py`, replace `_calculate_labels` method (currently at lines 418-460) with:

```python
    def _calculate_labels(
        self, df: pd.DataFrame, index: int
    ) -> Dict[str, Optional[float]]:
        """计算回测标签字典。

        对 self.label_configs 中每个 config 调用模块级 compute_label_value。
        键名格式：label_{max_days}，如 {"label_20": 0.15, "label_40": None}。

        Args:
            df: OHLCV 数据
            index: 突破点索引

        Returns:
            标签字典；数据不足时对应值为 None
        """
        labels: Dict[str, Optional[float]] = {}
        for config in self.label_configs:
            max_days = config.get("max_days", 20)
            label_key = f"label_{max_days}"
            labels[label_key] = compute_label_value(df, index, max_days)
        return labels
```

- [ ] **Step 4: 运行 Task 1 + Task 2 全部测试**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_label_helper.py -v`
Expected: 8 tests PASS.

- [ ] **Step 5: 运行既有 analysis 测试确保未回归**

Run: `uv run pytest BreakoutStrategy/analysis/tests/ -v`
Expected: 全部 PASS（包括 test_max_effective_buffer / test_per_factor_gating / test_scanner_range_meta / test_scanner_superseded）

- [ ] **Step 6: 提交**

```bash
git add BreakoutStrategy/analysis/features.py BreakoutStrategy/analysis/tests/test_label_helper.py
git commit -m "refactor(analysis): _calculate_labels delegates to compute_label_value

公式集中到模块级 helper，_calculate_labels 仅负责遍历 label_configs。
行为等价，无输出变化。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `UI/styles.py` 新增堆叠层与 tier 样式

**Files:**
- Modify: `BreakoutStrategy/UI/styles.py:80-85` (`MARKER_STACK_GAPS_PT`) and around line 130 (新增 `BO_LABEL_VALUE_TIER_STYLE`)
- Modify: `BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py` (扩展 key 集合断言)

- [ ] **Step 1: 扩展 test_marker_offsets.py 的层集合断言**

In `BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py`, find `test_dict_keys_match_expected` (around line 41) and replace the expected set:

```python
def test_dict_keys_match_expected():
    assert set(MARKER_STACK_GAPS_PT.keys()) == {
        "triangle", "peak_id", "bo_label", "bo_score", "bo_label_value",
    }
```

Also add a new test after `test_pure_bo_stack` (around line 34):

```python
def test_full_stack_with_label_value():
    offsets = compute_marker_offsets_pt(
        ["triangle", "peak_id", "bo_label", "bo_score", "bo_label_value"]
    )
    assert offsets == {
        "triangle": 14,
        "peak_id": 28,
        "bo_label": 38,
        "bo_score": 68,
        "bo_label_value": 98,
    }


def test_label_value_alone_above_bo_label():
    # BO Label on, BO Score off: label_value stacks directly above bo_label
    offsets = compute_marker_offsets_pt(["bo_label", "bo_label_value"])
    assert offsets == {"bo_label": 10, "bo_label_value": 40}
```

- [ ] **Step 2: 新增 tier style 断言测试**

In the same file, add after the existing `test_bo_label_tier_style_colors_follow_spec` (around line 64):

```python
def test_bo_label_value_tier_style_structure():
    from BreakoutStrategy.UI.styles import BO_LABEL_VALUE_TIER_STYLE
    assert set(BO_LABEL_VALUE_TIER_STYLE.keys()) == {"max", "other"}
    for tier in ("max", "other"):
        assert set(BO_LABEL_VALUE_TIER_STYLE[tier].keys()) == {"bg", "fg"}


def test_bo_label_value_tier_style_colors_follow_spec():
    from BreakoutStrategy.UI.styles import BO_LABEL_VALUE_TIER_STYLE
    # max: 黄底深蓝字
    assert BO_LABEL_VALUE_TIER_STYLE["max"]["bg"] == "#FFD700"
    assert BO_LABEL_VALUE_TIER_STYLE["max"]["fg"] == "#0000FF"
    # other: 橙底深蓝字
    assert BO_LABEL_VALUE_TIER_STYLE["other"]["bg"] == "#FFA500"
    assert BO_LABEL_VALUE_TIER_STYLE["other"]["fg"] == "#0000FF"
```

- [ ] **Step 3: 运行新测试，确认失败**

Run: `uv run pytest BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py -v`
Expected: `test_dict_keys_match_expected` / `test_full_stack_with_label_value` / `test_label_value_alone_above_bo_label` / `test_bo_label_value_tier_style_structure` / `test_bo_label_value_tier_style_colors_follow_spec` FAIL；既有其他测试仍 PASS。

- [ ] **Step 4: 修改 `UI/styles.py`**

In `BreakoutStrategy/UI/styles.py`, replace the `MARKER_STACK_GAPS_PT` dict (around lines 80-85) with:

```python
MARKER_STACK_GAPS_PT = {
    "triangle":       20,   # peak 倒三角
    "peak_id":        14,   # peak ID 数字文本
    "bo_label":       14,   # BO 的 [broken_peak_ids] 方框
    "bo_score":       30,   # BO 分数方框（仅 dev）
    "bo_label_value": 30,   # BO 回测 label 值方框（仅 dev，最顶层）
}
```

Then, after the existing `BO_LABEL_TIER_STYLE` definition (around line 130), add:

```python

# ============================================================================
# Dev 模式 bo_label_value 两态配色
# ============================================================================
#
# max   : 所有可见 BO 中 label 值最大的那个（若并列最大，全部算 max）——
#         黄底 + 深蓝字（强烈高亮，便于一眼定位"窗口内最高涨幅"的 BO）。
# other : 其他有 label 值的 BO —— 橙底 + 深蓝字。
#
# 边框统一使用 fg（深蓝）。

BO_LABEL_VALUE_TIER_STYLE = {
    "max":   {"bg": "#FFD700", "fg": "#0000FF"},  # 黄底深蓝字
    "other": {"bg": "#FFA500", "fg": "#0000FF"},  # 橙底深蓝字
}
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `uv run pytest BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py -v`
Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add BreakoutStrategy/UI/styles.py BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py
git commit -m "feat(styles): add bo_label_value stacking layer and tier style

新增 MARKER_STACK_GAPS_PT['bo_label_value']=30 和 BO_LABEL_VALUE_TIER_STYLE
(max=黄底, other=橙底, 字色统一深蓝)。为 draw_breakouts 的新显示层奠定基础。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `markers.draw_breakouts` 扩展渲染 label value

**Files:**
- Modify: `BreakoutStrategy/UI/charts/components/markers.py:126-252` (`draw_breakouts` method)
- Create: `BreakoutStrategy/UI/charts/components/tests/test_bo_label_value.py`

- [ ] **Step 1: 写 tier 分类与渲染失败测试**

Create `BreakoutStrategy/UI/charts/components/tests/test_bo_label_value.py`:

```python
"""Tests for BO label value marker rendering (tier classification + positioning)."""
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest
from types import SimpleNamespace

from BreakoutStrategy.UI.charts.components.markers import MarkerComponent
from BreakoutStrategy.UI.styles import BO_LABEL_VALUE_TIER_STYLE


@pytest.fixture
def ax_and_df():
    # 20 根 K 线，close 逐日上涨；提供足够的未来数据使 label_n<=10 都可算
    fig, ax = plt.subplots(figsize=(6, 4))
    closes = [10.0 + i * 0.5 for i in range(20)]
    df = pd.DataFrame({
        "open":  closes,
        "high":  [c * 1.01 for c in closes],
        "low":   [c * 0.99 for c in closes],
        "close": closes,
        "volume": [1000] * 20,
    })
    ax.plot(range(20), df["close"])
    ax.set_ylim(8, 25)
    yield ax, df
    plt.close(fig)


def _find_annotation_by_bbox_facecolor(ax, hex_color: str):
    """返回 bbox facecolor 匹配 hex_color 的所有 annotation。"""
    from matplotlib.colors import to_hex
    matches = []
    for t in ax.texts:
        bbox = t.get_bbox_patch()
        if bbox is None:
            continue
        fc = to_hex(bbox.get_facecolor(), keep_alpha=False).lower()
        if fc == hex_color.lower():
            matches.append(t)
    return matches


def test_show_label_off_by_default_no_label_value_annotation(ax_and_df):
    ax, df = ax_and_df
    bo = SimpleNamespace(index=2, price=df.iloc[2]["close"], broken_peak_ids=[5], quality_score=80.0)
    MarkerComponent.draw_breakouts(ax, df, [bo], peaks=[])
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    orange = _find_annotation_by_bbox_facecolor(ax, "#FFA500")
    assert yellow == []
    assert orange == []


def test_single_bo_with_show_label_is_max_tier(ax_and_df):
    ax, df = ax_and_df
    bo = SimpleNamespace(index=2, price=df.iloc[2]["close"], broken_peak_ids=[5], quality_score=80.0)
    MarkerComponent.draw_breakouts(
        ax, df, [bo], peaks=[],
        show_label=True, label_n=5,
    )
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    assert len(yellow) == 1
    # 单值即是 max；应为百分比格式，带 + 号（closes 逐日上涨故 value > 0）
    assert "%" in yellow[0].get_text()
    assert yellow[0].get_text().startswith("+")


def test_multi_bo_max_vs_other_tier(ax_and_df):
    ax, df = ax_and_df
    # index=2 的 close=11.0；label_n=3 的未来最高=12.5，value≈(12.5-11)/11≈0.1364
    # index=5 的 close=12.5；label_n=3 的未来最高=14.0，value≈(14-12.5)/12.5=0.12
    # index=10 的 close=15.0；label_n=3 的未来最高=16.5，value=0.1
    # 故 index=2 的 BO 为 max
    bos = [
        SimpleNamespace(index=2,  price=df.iloc[2]["close"],  broken_peak_ids=[1], quality_score=70.0),
        SimpleNamespace(index=5,  price=df.iloc[5]["close"],  broken_peak_ids=[2], quality_score=75.0),
        SimpleNamespace(index=10, price=df.iloc[10]["close"], broken_peak_ids=[3], quality_score=80.0),
    ]
    MarkerComponent.draw_breakouts(
        ax, df, bos, peaks=[],
        show_label=True, label_n=3,
    )
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    orange = _find_annotation_by_bbox_facecolor(ax, "#FFA500")
    assert len(yellow) == 1
    assert len(orange) == 2


def test_insufficient_future_data_skipped(ax_and_df):
    ax, df = ax_and_df
    # 只有 1 个 BO，位于倒数第 2 行，label_n=5 数据不够
    bo = SimpleNamespace(index=18, price=df.iloc[18]["close"], broken_peak_ids=[1], quality_score=70.0)
    MarkerComponent.draw_breakouts(
        ax, df, [bo], peaks=[],
        show_label=True, label_n=5,
    )
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    orange = _find_annotation_by_bbox_facecolor(ax, "#FFA500")
    assert yellow == []
    assert orange == []


def test_all_none_values_no_annotation(ax_and_df):
    ax, df = ax_and_df
    # 所有 BO 都在 df 末端，label_n=10 数据不够
    bos = [
        SimpleNamespace(index=18, price=df.iloc[18]["close"], broken_peak_ids=[1], quality_score=70.0),
        SimpleNamespace(index=19, price=df.iloc[19]["close"], broken_peak_ids=[2], quality_score=75.0),
    ]
    MarkerComponent.draw_breakouts(
        ax, df, bos, peaks=[],
        show_label=True, label_n=10,
    )
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    orange = _find_annotation_by_bbox_facecolor(ax, "#FFA500")
    assert yellow == []
    assert orange == []


def test_tied_max_values_all_get_max_tier(ax_and_df):
    """多个 BO value 并列最大时，全部标为 max tier。"""
    ax, df = ax_and_df
    # 构造一个 df，使 index=2 和 index=5 的 label 值相同
    closes = [10.0] * 20
    closes[0] = 10.0
    closes[3] = 11.0   # index=2 的 future[1:5] 最高
    closes[4] = 11.0
    closes[6] = 11.0   # index=5 的 future[6:9] 最高
    closes[7] = 11.0
    df_tied = pd.DataFrame({
        "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes, "volume": [1000] * 20,
    })
    bos = [
        SimpleNamespace(index=2, price=10.0, broken_peak_ids=[1], quality_score=70.0),
        SimpleNamespace(index=5, price=10.0, broken_peak_ids=[2], quality_score=75.0),
    ]
    MarkerComponent.draw_breakouts(
        ax, df_tied, bos, peaks=[],
        show_label=True, label_n=3,
    )
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    orange = _find_annotation_by_bbox_facecolor(ax, "#FFA500")
    assert len(yellow) == 2
    assert len(orange) == 0


def test_label_value_offset_above_bo_score(ax_and_df):
    """label_value annotation 的 y 偏移 = bo_label(10) + bo_score(30) + bo_label_value(30) = 70 (pure BO, no peak)."""
    ax, df = ax_and_df
    bo = SimpleNamespace(index=2, price=df.iloc[2]["close"], broken_peak_ids=[5], quality_score=80.0)
    MarkerComponent.draw_breakouts(
        ax, df, [bo], peaks=[],
        show_score=True, show_label=True, label_n=3,
    )
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    assert len(yellow) == 1
    assert yellow[0].xyann[1] == pytest.approx(70)


def test_label_value_without_score_takes_score_slot(ax_and_df):
    """开 BO Label、关 BO Score 时，label_value 退到 bo_score 的位置。

    堆叠: bo_label(10) + bo_label_value(30) = 40 (pure BO, no peak)
    """
    ax, df = ax_and_df
    bo = SimpleNamespace(index=2, price=df.iloc[2]["close"], broken_peak_ids=[5], quality_score=80.0)
    MarkerComponent.draw_breakouts(
        ax, df, [bo], peaks=[],
        show_score=False, show_label=True, label_n=3,
    )
    yellow = _find_annotation_by_bbox_facecolor(ax, "#FFD700")
    assert len(yellow) == 1
    assert yellow[0].xyann[1] == pytest.approx(40)
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest BreakoutStrategy/UI/charts/components/tests/test_bo_label_value.py -v`
Expected: 全部 FAIL（`draw_breakouts` 还不接受 `show_label` / `label_n` 参数；或传入后未绘制）

- [ ] **Step 3: 修改 `draw_breakouts` 签名与实现**

In `BreakoutStrategy/UI/charts/components/markers.py`, locate `def draw_breakouts(` (around line 127). Replace the whole method (signature + body, currently lines 127-252) with:

```python
    @staticmethod
    def draw_breakouts(
        ax,
        df: pd.DataFrame,
        breakouts: list,
        highlight_multi_peak: bool = True,
        peaks: list = None,
        colors: dict = None,
        show_score: bool = True,
        show_label: bool = False,
        label_n: int = 20,
    ):
        """
        绘制突破标记

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame
            breakouts: Breakout 对象列表
            highlight_multi_peak: 多峰值突破是否使用大标记
            peaks: 当前图表中绘制的峰值列表 (用于避免重叠)
            colors: 颜色配置字典
            show_score: 是否显示 quality_score
            show_label: 是否显示回测 label 值（窗口 = label_n 天）
            label_n: label 计算窗口天数
        """
        if not breakouts:
            return

        colors = colors or {}
        marker_color = colors.get("breakout_marker", "#0000FF")
        text_bg_color = colors.get("breakout_text_bg", "#FFFFFF")
        text_score_color = colors.get("breakout_text_score", "#FF0000")

        high_col = "high" if "high" in df.columns else "High"
        has_high = high_col in df.columns

        from BreakoutStrategy.UI.styles import (
            BO_LABEL_VALUE_TIER_STYLE,
            compute_marker_offsets_pt,
        )
        from BreakoutStrategy.analysis.features import compute_label_value

        # 构建峰值索引集合（两层：是否存在 peak / peak 是否带 id）
        peak_indices = {p.index for p in peaks} if peaks else set()
        peak_id_indices = (
            {p.index for p in peaks if getattr(p, "id", None) is not None}
            if peaks else set()
        )

        # 第 1 遍：若开启 show_label，为所有 BO 预先计算 label value，并找出最大值
        bo_label_values: dict[int, float] = {}
        max_label_value = None
        if show_label:
            for bo in breakouts:
                v = compute_label_value(df, bo.index, label_n)
                if v is not None:
                    bo_label_values[bo.index] = v
            if bo_label_values:
                max_label_value = max(bo_label_values.values())

        # 第 2 遍：逐 BO 绘制
        for bo in breakouts:
            bo_x = bo.index

            if has_high and 0 <= bo_x < len(df):
                base_price = df.iloc[bo_x][high_col]
            else:
                base_price = bo.price

            color = marker_color

            has_broken_ids = bool(getattr(bo, "broken_peak_ids", None))
            has_score = (
                show_score
                and hasattr(bo, "quality_score")
                and bo.quality_score is not None
            )
            has_label_value = show_label and bo_x in bo_label_values

            # 构造本 bar 实际存在的堆叠层（自下而上）
            layers: list[str] = []
            if bo_x in peak_indices:
                layers.append("triangle")
                if bo_x in peak_id_indices:
                    layers.append("peak_id")
            if has_broken_ids:
                layers.append("bo_label")
            if has_score and has_broken_ids:
                layers.append("bo_score")
            if has_label_value and (has_score or has_broken_ids):
                layers.append("bo_label_value")

            offsets = compute_marker_offsets_pt(layers) if layers else {}

            # 绘制突破分数
            if has_score:
                if has_broken_ids:
                    score_y = offsets["bo_score"]
                else:
                    tmp_layers = layers + ["bo_label"]
                    score_y = compute_marker_offsets_pt(tmp_layers)["bo_label"]

                score_text = f"{bo.quality_score:.0f}"
                ax.annotate(
                    score_text,
                    xy=(bo_x, base_price),
                    xycoords="data",
                    xytext=(0, score_y),
                    textcoords="offset points",
                    fontsize=20,
                    ha="center",
                    va="bottom",
                    color=text_score_color,
                    weight="bold",
                    zorder=12,
                    bbox=dict(
                        boxstyle="round,pad=0.2",
                        facecolor=text_bg_color,
                        edgecolor=text_score_color,
                        linewidth=1.0,
                        alpha=0.8,
                    ),
                )

            # 绘制回测 label 值
            if has_label_value:
                value = bo_label_values[bo_x]
                # Tier 分类（浮点等值用容差）
                is_max = (
                    max_label_value is not None
                    and abs(value - max_label_value) < 1e-9
                )
                tier = "max" if is_max else "other"
                tier_style = BO_LABEL_VALUE_TIER_STYLE[tier]

                # 计算 y 偏移
                if "bo_label_value" in offsets:
                    label_value_y = offsets["bo_label_value"]
                else:
                    # 只有 label_value，无 score 无 broken_ids：退到 bo_score 位
                    tmp_layers = layers + ["bo_score"]
                    label_value_y = compute_marker_offsets_pt(tmp_layers)["bo_score"]

                sign = "+" if value >= 0 else ""
                value_text = f"{sign}{value * 100:.1f}%"

                ax.annotate(
                    value_text,
                    xy=(bo_x, base_price),
                    xycoords="data",
                    xytext=(0, label_value_y),
                    textcoords="offset points",
                    fontsize=20,
                    ha="center",
                    va="bottom",
                    color=tier_style["fg"],
                    weight="bold",
                    zorder=12,
                    bbox=dict(
                        boxstyle="round,pad=0.2",
                        facecolor=tier_style["bg"],
                        edgecolor=tier_style["fg"],
                        linewidth=1.0,
                        alpha=0.9,
                    ),
                )

            # 在上方显示被突破的 peaks id 列表
            if has_broken_ids:
                peak_ids_text = ",".join(map(str, bo.broken_peak_ids))
                ax.annotate(
                    f"[{peak_ids_text}]",
                    xy=(bo_x, base_price),
                    xycoords="data",
                    xytext=(0, offsets["bo_label"]),
                    textcoords="offset points",
                    fontsize=20,
                    ha="center",
                    va="bottom",
                    color=color,
                    weight="bold",
                    zorder=11,
                    bbox=dict(
                        boxstyle="round,pad=0.3",
                        facecolor=text_bg_color,
                        edgecolor=color,
                        linewidth=1.5,
                        alpha=0.9,
                    ),
                )
```

- [ ] **Step 4: 运行 test_bo_label_value.py，确认通过**

Run: `uv run pytest BreakoutStrategy/UI/charts/components/tests/test_bo_label_value.py -v`
Expected: 全部 PASS（8 tests）。

- [ ] **Step 5: 运行 markers 既有测试，确认未回归**

Run: `uv run pytest BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py -v`
Expected: 全部 PASS（包括新增与既有）。

- [ ] **Step 6: 运行完整 UI charts 测试套件**

Run: `uv run pytest BreakoutStrategy/UI/charts/ -v`
Expected: 全部 PASS。

- [ ] **Step 7: 提交**

```bash
git add BreakoutStrategy/UI/charts/components/markers.py \
        BreakoutStrategy/UI/charts/components/tests/test_bo_label_value.py
git commit -m "feat(markers): render BO label value with tier-aware styling

draw_breakouts 新增 show_label/label_n 参数；两遍渲染结构先算全部 value
再按 max/other tier 绘制（黄底/橙底 + 深蓝字）。保持既有 bo_score /
broken_peak_ids 行为不变。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `canvas_manager` 透传 display_options

**Files:**
- Modify: `BreakoutStrategy/UI/charts/canvas_manager.py:115-120` (读 display_options) and `:251-260` (调 draw_breakouts)

- [ ] **Step 1: 读并扩展 display_options**

In `BreakoutStrategy/UI/charts/canvas_manager.py`, locate the block around line 116-118:

```python
        display_options = display_options or {}
        show_bo_score = display_options.get("show_bo_score", True)
        show_superseded_peaks = display_options.get("show_superseded_peaks", False)
```

Replace with:

```python
        display_options = display_options or {}
        show_bo_score = display_options.get("show_bo_score", True)
        show_superseded_peaks = display_options.get("show_superseded_peaks", False)
        show_bo_label = display_options.get("show_bo_label", False)
        bo_label_n = display_options.get("bo_label_n", 20)
```

- [ ] **Step 2: 把新参数传给 `draw_breakouts`**

In the same file, find the dev-mode `else` branch around lines 251-260:

```python
        else:
            self.marker.draw_breakouts(
                ax_main,
                df,
                breakouts,
                highlight_multi_peak=True,
                peaks=all_drawn_peaks,
                colors=colors,
                show_score=show_bo_score,
            )
```

Replace with:

```python
        else:
            self.marker.draw_breakouts(
                ax_main,
                df,
                breakouts,
                highlight_multi_peak=True,
                peaks=all_drawn_peaks,
                colors=colors,
                show_score=show_bo_score,
                show_label=show_bo_label,
                label_n=bo_label_n,
            )
```

- [ ] **Step 3: 运行 canvas_manager 既有测试**

Run: `uv run pytest BreakoutStrategy/UI/charts/tests/ -v`
Expected: 全部 PASS（包括 `test_canvas_manager_live_mode.py` 等）。`show_bo_label` 不传时默认 `False`，dev 分支未勾选 checkbox 也默认 `False`，不改变既有表现。

- [ ] **Step 4: 提交**

```bash
git add BreakoutStrategy/UI/charts/canvas_manager.py
git commit -m "feat(canvas): forward show_bo_label/bo_label_n to draw_breakouts

从 display_options 读取新 key，只在 dev 分支透传。Live 分支不受影响。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `parameter_panel` 新增 BO Label checkbox 与 N Spinbox

**Files:**
- Modify: `BreakoutStrategy/dev/panels/parameter_panel.py` (初始化变量 + UI 构建 + `get_display_options` + 新方法 `set_bo_label_n_default`)

- [ ] **Step 1: 初始化新 `BooleanVar` / `IntVar`**

In `BreakoutStrategy/dev/panels/parameter_panel.py`, locate the block (around line 64-69):

```python
        # 显示选项变量
        self.show_bo_score_var = tk.BooleanVar(
            value=defaults.get("show_bo_score", True)
        )
        self.show_superseded_peaks_var = tk.BooleanVar(
            value=defaults.get("show_superseded_peaks", True)
        )
```

Append after it:

```python
        self.show_bo_label_var = tk.BooleanVar(
            value=defaults.get("show_bo_label", False)
        )
        # bo_label_n 的初始值来自默认 20；scan 加载后由 set_bo_label_n_default 更新
        self.bo_label_n_var = tk.IntVar(value=20)
```

- [ ] **Step 2: 在工具栏添加 "BO Label" 复选框 + N Spinbox**

In `_create_ui` method, locate the existing BO Score checkbox block (around lines 169-174):

```python
        # 显示选项复选框
        ttk.Checkbutton(
            container,
            text="BO Score",
            variable=self.show_bo_score_var,
            command=self._on_checkbox_changed,
        ).pack(side=tk.LEFT, padx=5)
```

Append immediately after it, **before** the `SU_PK` Checkbutton (around line 176):

```python
        # BO Label 复选框 + N Spinbox（同一组）
        self.show_bo_label_checkbox = ttk.Checkbutton(
            container,
            text="BO Label",
            variable=self.show_bo_label_var,
            command=self._on_bo_label_toggle,
        )
        self.show_bo_label_checkbox.pack(side=tk.LEFT, padx=(5, 2))

        ttk.Label(container, text="N:").pack(side=tk.LEFT)
        self.bo_label_n_spin = ttk.Spinbox(
            container,
            from_=1,
            to=200,
            increment=1,
            textvariable=self.bo_label_n_var,
            width=4,
            command=self._on_checkbox_changed,
            state="disabled",   # 默认 checkbox 关，Spinbox 灰显
        )
        self.bo_label_n_spin.pack(side=tk.LEFT, padx=(2, 5))

        # Spinbox 直接输入数字时也要触发刷新（command 只响应箭头点击）
        self.bo_label_n_var.trace_add(
            "write", lambda *_: self._on_checkbox_changed()
        )
```

- [ ] **Step 3: 新增 `_on_bo_label_toggle` 方法（联动 Spinbox 启停）**

In the same file, locate `_on_checkbox_changed` (around line 241-246):

```python
    def _on_checkbox_changed(self):
        """复选框状态改变回调"""
        if self.on_display_option_changed_callback:
            self.on_display_option_changed_callback()
        elif self.on_param_changed_callback:
            self.on_param_changed_callback()
```

Add a new method immediately after it:

```python
    def _on_bo_label_toggle(self):
        """BO Label checkbox toggle：同步 Spinbox 启停，并触发重绘。"""
        if self.show_bo_label_var.get():
            self.bo_label_n_spin.config(state="normal")
        else:
            self.bo_label_n_spin.config(state="disabled")
        self._on_checkbox_changed()
```

- [ ] **Step 4: 扩展 `get_display_options` 返回字段**

In the same file, locate `get_display_options` (around line 275-280):

```python
    def get_display_options(self):
        """获取显示选项"""
        return {
            "show_bo_score": self.show_bo_score_var.get(),
            "show_superseded_peaks": self.show_superseded_peaks_var.get(),
        }
```

Replace with:

```python
    def get_display_options(self):
        """获取显示选项"""
        try:
            n = self.bo_label_n_var.get()
        except tk.TclError:
            # Spinbox 文本非整数（用户输入非法字符时），回退默认
            n = 20
        return {
            "show_bo_score": self.show_bo_score_var.get(),
            "show_superseded_peaks": self.show_superseded_peaks_var.get(),
            "show_bo_label": self.show_bo_label_var.get(),
            "bo_label_n": n,
        }
```

- [ ] **Step 5: 新增 `set_bo_label_n_default` 方法**

In the same file, add the following method after `get_display_options`:

```python
    def set_bo_label_n_default(self, max_days: int):
        """把 Spinbox 当前值重置为指定默认值。

        通常在加载新 scan 时由 main.py 调用，让 Spinbox 默认反映扫描时的
        label_configs[0].max_days，与股票列表 Label 列的聚合基准一致。

        Args:
            max_days: 扫描的窗口天数；clamp 到 [1, 200]
        """
        n = max(1, min(200, int(max_days)))
        self.bo_label_n_var.set(n)
```

- [ ] **Step 6: 手工冒烟：启动 dev UI，核对控件出现且可交互**

Run: `uv run python -m BreakoutStrategy.dev.main`
Expected:
- 窗口顶部工具栏可见 "BO Label" checkbox 和紧邻的 "N: [20 ⇅]" Spinbox
- Spinbox 默认灰显
- 勾选 "BO Label"，Spinbox 可编辑
- 取消勾选，Spinbox 恢复灰显

手工验证后关闭窗口。

- [ ] **Step 7: 提交**

```bash
git add BreakoutStrategy/dev/panels/parameter_panel.py
git commit -m "feat(dev/panel): add BO Label checkbox and N Spinbox

复选框控制是否显示回测 label marker；Spinbox (1..200) 设置计算窗口天数，
checkbox 关闭时灰显保留值。get_display_options() 返回扩展的 show_bo_label /
bo_label_n 字段。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `main.py` 在加载 scan 后设置 Spinbox 默认 N

**Files:**
- Modify: `BreakoutStrategy/dev/main.py:137-172` (`load_scan_results` method)

- [ ] **Step 1: 在 scan 加载成功后调用 `set_bo_label_n_default`**

In `BreakoutStrategy/dev/main.py`, locate `load_scan_results` (around line 137). Find the line:

```python
            # 加载到股票列表
            self.stock_list_panel.load_data(self.scan_data)
```

Immediately **before** that line, insert:

```python
            # 从 scan metadata 读取 label_configs[0].max_days，更新 Spinbox 默认 N
            label_max_days = self.config_loader.get_label_max_days_from_json(
                self.scan_data
            )
            if label_max_days is not None:
                self.param_panel.set_bo_label_n_default(label_max_days)

```

> 注：`get_label_max_days_from_json` 已存在于 `config/ui_loader.py`；无 `label_configs` 时返回 None，此时保留 Spinbox 当前值（若从未加载过 scan，初始值 20）。

- [ ] **Step 2: 手工冒烟：加载一个真实 scan 文件，观察 Spinbox 值**

Run: `uv run python -m BreakoutStrategy.dev.main`

加载任意已有 scan JSON（例如 `outputs/scan_results/` 下的文件，或最近的扫描结果）。检查：
- Spinbox 的值应自动更新为 scan metadata 中的 `label_configs[0].max_days`
- 如 scan 的 label_configs 不存在，Spinbox 保持 20 或上一次的值

- [ ] **Step 3: 提交**

```bash
git add BreakoutStrategy/dev/main.py
git commit -m "feat(dev): initialize BO Label N from scan metadata on load

load_scan_results 成功后从 scan JSON 读 label_configs[0].max_days，
调 param_panel.set_bo_label_n_default() 同步 Spinbox。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: `ui_config.yaml` 清理与新增

**Files:**
- Modify: `configs/ui_config.yaml` (lines 8-10, `ui.display_options`)

- [ ] **Step 1: 验证 `show_peak_score` 确实无代码引用**

Run: `grep -rn "show_peak_score" /home/yu/PycharmProjects/Trade_Strategy/ --include="*.py"`
Expected: 无输出（只有 yaml 里那行死键）。

- [ ] **Step 2: 编辑 `configs/ui_config.yaml`**

Current (lines 7-10):

```yaml
ui:
  display_options:
    show_bo_score: true
    show_peak_score: false
```

Replace to:

```yaml
ui:
  display_options:
    show_bo_score: true
    show_bo_label: false
```

- [ ] **Step 3: 手工冒烟：再次启动 dev，核对默认**

Run: `uv run python -m BreakoutStrategy.dev.main`
Expected:
- "BO Label" checkbox 初始未勾选（对应 `show_bo_label: false`）
- Spinbox 灰显

关闭窗口。

- [ ] **Step 4: 提交**

```bash
git add configs/ui_config.yaml
git commit -m "chore(config): add show_bo_label default; drop dead show_peak_score key

新增 display_options.show_bo_label: false 默认；show_peak_score 在代码中
已无引用，作为早期残留移除。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: 端到端 Manual QA

**Files:** 无

- [ ] **Step 1: 运行完整测试套件，确认绿**

Run: `uv run pytest BreakoutStrategy/ -v`
Expected: 全部 PASS（新增 + 既有）。

- [ ] **Step 2: 启动 dev 并加载真实 scan**

Run: `uv run python -m BreakoutStrategy.dev.main`

加载一个含多个 BO 的 scan JSON。

- [ ] **Step 3: 逐项手工验证清单**

逐项检查并在脑中 ✓：

1. 不勾选 "BO Label"：chart 上无黄/橙方框
2. 勾选 "BO Label"：每个有足够未来数据的 BO 在 bo_score 上方出现彩色方框；值格式形如 `+15.0%` 或 `-3.2%`
3. 最大值 BO 黄底深蓝字，其余橙底深蓝字
4. Spinbox N 改为 10：marker 值立即刷新；改为 40：同样立即刷新
5. 最近几个 BO（距今 < N 天）：不显示 label value 方框，其他层正常
6. 关闭 "BO Score" 保留 "BO Label"：label marker 退到 bo_score 原本的位置（视觉上高度下降一层）
7. 切换到另一只股票：Spinbox N 值保持不变（session 内持久）
8. 加载另一个 scan JSON（如 label_configs 中 max_days 不同）：Spinbox N 自动重置为新 scan 的值
9. BO 很多且部分并列最大（极少见，不强求复现）：并列都是黄底
10. 取消勾选 "BO Label"：彩色方框消失，Spinbox 灰显

- [ ] **Step 4: 若上述均通过，标记 feature 完成**

此 task 无代码提交。若手工 QA 中发现偏离，回到相应 Task 修复后重跑 Step 1-3。

---

## Self-Review Notes

- 所有 spec 章节（§1 目标 / §2 UI / §3 数据流 / §4 helper / §5 渲染 / §6 配置 / §7 测试 / §8 文件清单）均有对应 task 实现
- 类型/函数名一致：`compute_label_value(df, index, max_days)` 签名统一；`show_label` / `label_n` 参数名在 markers / canvas_manager 间一致；`show_bo_label` / `bo_label_n` 在 display_options dict / ui_config.yaml / parameter_panel 间一致
- 无 TBD / TODO / "similar to Task N" 等占位
- 每个 task 含完整代码块与可执行命令；TDD 节奏（失败测试 → 最小实现 → 通过 → 提交）贯穿全程
