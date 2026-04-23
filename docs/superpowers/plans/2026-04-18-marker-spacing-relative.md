# Marker Spacing Relative Gaps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor chart marker vertical stacking to use relative pt gaps between adjacent layers (SSoT in `UI/styles.py`), and replace live-mode scatter-circle BO markers with colored `bo_label` annotations that carry picker directly.

**Architecture:** Add `MARKER_STACK_GAPS_PT` dict + `compute_marker_offsets_pt(layers)` helper in `BreakoutStrategy/UI/styles.py`. All three `MarkerComponent` draw methods (`draw_peaks`, `draw_breakouts`, `draw_breakouts_live_mode`) build a per-bar `layers` list and query the helper for cumulative pt offsets. Live mode drops all scatter drawing; annotations carry tier colors (from new `BO_LABEL_TIER_STYLE`) and `picker=True` for the three interactive tiers.

**Tech Stack:** Python 3, matplotlib (Annotation + bbox + picker), pytest, `uv` for running.

**Spec:** `docs/superpowers/specs/2026-04-17-marker-spacing-relative-design.md`

---

## File Structure

**New files:**
- `BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py` — unit tests for the helper + dev regression anchors for `draw_peaks` / `draw_breakouts`.

**Modified files:**
- `BreakoutStrategy/UI/styles.py` — add `MARKER_STACK_GAPS_PT`, `compute_marker_offsets_pt`, `BO_LABEL_TIER_STYLE`.
- `BreakoutStrategy/UI/charts/components/markers.py` — delete all inline pt constants; `draw_peaks` / `draw_breakouts` / `draw_breakouts_live_mode` refactored to use helper; live-mode rewritten to produce tier-colored annotations with picker (no more scatter).
- `BreakoutStrategy/UI/charts/canvas_manager.py` — `_on_pick` reads `artist.bo_chart_idx` (scalar) instead of `artist.bo_chart_indices[event.ind[0]]`.
- `BreakoutStrategy/UI/charts/components/tests/test_draw_breakouts_live_mode.py` — rewritten around annotations instead of scatter collections.
- `BreakoutStrategy/UI/charts/tests/test_canvas_manager_live_mode.py` — `test_live_mode_pick_event_invokes_on_bo_picked` adjusted for annotation artist + `bo_chart_idx` field.

---

## Task 1: Add `MARKER_STACK_GAPS_PT` + `compute_marker_offsets_pt` helper (TDD)

**Files:**
- Create: `BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py`
- Modify: `BreakoutStrategy/UI/styles.py`

- [ ] **Step 1.1: Create failing test file**

Write `BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py`:

```python
"""Unit tests for compute_marker_offsets_pt helper in UI/styles.py."""
import pytest

from BreakoutStrategy.UI.styles import MARKER_STACK_GAPS_PT, compute_marker_offsets_pt


def test_single_layer_triangle():
    assert compute_marker_offsets_pt(["triangle"]) == {"triangle": 14}


def test_dev_full_stack():
    offsets = compute_marker_offsets_pt(
        ["triangle", "peak_id", "bo_label", "bo_score"]
    )
    assert offsets == {
        "triangle": 14,
        "peak_id": 28,
        "bo_label": 38,
        "bo_score": 68,
    }


def test_live_stack_with_peak():
    assert compute_marker_offsets_pt(
        ["triangle", "peak_id", "bo_label"]
    ) == {"triangle": 14, "peak_id": 28, "bo_label": 38}


def test_pure_bo_stack():
    assert compute_marker_offsets_pt(["bo_label", "bo_score"]) == {
        "bo_label": 10,
        "bo_score": 40,
    }


def test_unknown_layer_raises():
    with pytest.raises(KeyError):
        compute_marker_offsets_pt(["unknown_layer"])


def test_dict_keys_match_expected():
    assert set(MARKER_STACK_GAPS_PT.keys()) == {
        "triangle", "peak_id", "bo_label", "bo_score",
    }
```

- [ ] **Step 1.2: Run tests — verify they fail**

Run: `uv run pytest BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py -v`
Expected: all fail with `ImportError: cannot import name 'MARKER_STACK_GAPS_PT' from 'BreakoutStrategy.UI.styles'`.

- [ ] **Step 1.3: Add dict + helper to `BreakoutStrategy/UI/styles.py`**

Insert the following after the `CHART_COLORS` block (around line 60, before the `FONT_FAMILY` section):

```python
# ============================================================================
# Marker 堆叠间距（单位: points）
# ============================================================================
#
# 每层值 = "到下方相邻层的像素间距"；当此层是堆叠最底时，"下方"即 K 线 High。
# 字典中 key 顺序无语义；实际堆叠顺序由 draw_* 调用时传入的 layers 列表决定。
#
# 用途：dev 和 live 两种 chart 渲染路径共用，几何属于 UI 基础设施。
# 调整此处数值即可统一生效。

MARKER_STACK_GAPS_PT = {
    "triangle": 14,   # peak 倒三角
    "peak_id":  14,   # peak ID 数字文本
    "bo_label": 10,   # BO 的 [broken_peak_ids] 方框
    "bo_score": 30,   # BO 分数方框（仅 dev）
}


def compute_marker_offsets_pt(layers: list[str]) -> dict[str, float]:
    """按堆叠顺序（自下而上）累加 gap，返回每层到 K 线 High 的累计像素偏移。

    Args:
        layers: 本 bar 实际存在的 marker 层名，自下而上顺序。

    Returns:
        dict mapping layer name -> cumulative pt offset from High.

    Example:
        >>> compute_marker_offsets_pt(["triangle", "peak_id", "bo_label", "bo_score"])
        {'triangle': 14, 'peak_id': 28, 'bo_label': 38, 'bo_score': 68}

    Raises:
        KeyError: layer 名不在 MARKER_STACK_GAPS_PT 中。
    """
    offsets: dict[str, float] = {}
    cumulative = 0.0
    for layer in layers:
        cumulative += MARKER_STACK_GAPS_PT[layer]
        offsets[layer] = cumulative
    return offsets
```

- [ ] **Step 1.4: Run tests — verify pass**

Run: `uv run pytest BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py -v`
Expected: 6 passed.

- [ ] **Step 1.5: Commit**

```bash
git add BreakoutStrategy/UI/styles.py BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py
git commit -m "feat(styles): add MARKER_STACK_GAPS_PT dict and compute_marker_offsets_pt helper"
```

---

## Task 2: Add `BO_LABEL_TIER_STYLE` to `styles.py`

**Files:**
- Modify: `BreakoutStrategy/UI/styles.py`
- Modify: `BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py` (append test)

- [ ] **Step 2.1: Add failing test**

Append to `BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py`:

```python
def test_bo_label_tier_style_has_four_tiers():
    from BreakoutStrategy.UI.styles import BO_LABEL_TIER_STYLE
    assert set(BO_LABEL_TIER_STYLE.keys()) == {
        "current", "visible", "filtered_out", "plain",
    }


def test_bo_label_tier_style_colors_follow_spec():
    from BreakoutStrategy.UI.styles import BO_LABEL_TIER_STYLE, CHART_COLORS
    current_color = CHART_COLORS["bo_marker_current"]

    assert BO_LABEL_TIER_STYLE["current"]["bg"] == current_color
    assert BO_LABEL_TIER_STYLE["current"]["fg"] == "#FFFFFF"

    assert BO_LABEL_TIER_STYLE["visible"]["bg"] == CHART_COLORS["bo_marker_visible"]
    assert BO_LABEL_TIER_STYLE["visible"]["fg"] == current_color

    assert BO_LABEL_TIER_STYLE["filtered_out"]["bg"] == CHART_COLORS["bo_marker_filtered_out"]
    assert BO_LABEL_TIER_STYLE["filtered_out"]["fg"] == current_color

    assert BO_LABEL_TIER_STYLE["plain"]["bg"] == CHART_COLORS["breakout_text_bg"]
    assert BO_LABEL_TIER_STYLE["plain"]["fg"] == current_color
```

- [ ] **Step 2.2: Run tests — verify fail**

Run: `uv run pytest BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py::test_bo_label_tier_style_has_four_tiers BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py::test_bo_label_tier_style_colors_follow_spec -v`
Expected: both fail with `ImportError`.

- [ ] **Step 2.3: Add `BO_LABEL_TIER_STYLE` to styles.py**

Insert immediately after the `compute_marker_offsets_pt` function (added in Task 1):

```python
# ============================================================================
# Live 模式 bo_label 四态配色（dev 模式不使用）
# ============================================================================
#
# current      : matched + 通过 filter + 当前选中
# visible      : matched + 通过 filter + 未选中
# filtered_out : matched + 未通过 filter
# plain        : 未匹配 template
#
# 所有 tier 的边框统一使用 CHART_COLORS["bo_marker_current"]（深蓝）。

BO_LABEL_TIER_STYLE = {
    "current":      {"bg": CHART_COLORS["bo_marker_current"],       "fg": "#FFFFFF"},
    "visible":      {"bg": CHART_COLORS["bo_marker_visible"],       "fg": CHART_COLORS["bo_marker_current"]},
    "filtered_out": {"bg": CHART_COLORS["bo_marker_filtered_out"],  "fg": CHART_COLORS["bo_marker_current"]},
    "plain":        {"bg": CHART_COLORS["breakout_text_bg"],        "fg": CHART_COLORS["bo_marker_current"]},
}
```

- [ ] **Step 2.4: Run tests — verify pass**

Run: `uv run pytest BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py -v`
Expected: 8 passed (6 from Task 1 + 2 new).

- [ ] **Step 2.5: Commit**

```bash
git add BreakoutStrategy/UI/styles.py BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py
git commit -m "feat(styles): add BO_LABEL_TIER_STYLE for live-mode bo_label tier colors"
```

---

## Task 3: Refactor `draw_peaks` to use helper (TDD regression anchor)

**Files:**
- Modify: `BreakoutStrategy/UI/charts/components/markers.py`
- Modify: `BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py` (append)

- [ ] **Step 3.1: Append regression tests for `draw_peaks` offsets**

Append to `test_marker_offsets.py`:

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from types import SimpleNamespace

from BreakoutStrategy.UI.charts.components.markers import MarkerComponent


@pytest.fixture
def axes_with_df():
    fig, ax = plt.subplots(figsize=(6, 4))
    df = pd.DataFrame({
        "open":  [1.0, 1.1, 1.2, 1.3, 1.4],
        "high":  [1.1, 1.2, 1.3, 1.4, 1.5],
        "low":   [0.9, 1.0, 1.1, 1.2, 1.3],
        "close": [1.05, 1.15, 1.25, 1.35, 1.45],
    })
    ax.plot(range(5), df["close"])
    ax.set_ylim(0.8, 1.6)
    yield ax, df
    plt.close(fig)


def _find_annotation_by_text(ax, text_substring: str):
    for t in ax.texts:
        if text_substring in t.get_text():
            return t
    return None


def test_draw_peaks_without_id_has_no_text(axes_with_df):
    ax, df = axes_with_df
    peak = SimpleNamespace(index=2, price=1.2, id=None)
    MarkerComponent.draw_peaks(ax, df, [peak])
    assert len(ax.texts) == 0


def test_draw_peaks_with_id_annotation_at_28pt(axes_with_df):
    ax, df = axes_with_df
    peak = SimpleNamespace(index=2, price=1.2, id=7)
    MarkerComponent.draw_peaks(ax, df, [peak])
    ann = _find_annotation_by_text(ax, "7")
    assert ann is not None
    # xytext y should equal triangle(14) + peak_id(14) = 28
    assert ann.xyann[1] == pytest.approx(28)
```

- [ ] **Step 3.2: Run tests — should PASS against current code (regression anchors, values chosen to match current)**

Run: `uv run pytest BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py::test_draw_peaks_without_id_has_no_text BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py::test_draw_peaks_with_id_annotation_at_28pt -v`
Expected: 2 passed (current `TEXT_OFFSET_PT = 28` already yields 28pt).

- [ ] **Step 3.3: Refactor `draw_peaks` in `markers.py`**

Replace the body of `draw_peaks` (lines ~35-120 in current file). Target replacement — locate this block:

```python
        # 像素偏移常量（单位: points）—— 不依赖 ylim，缩放后间距恒定
        MARKER_OFFSET_PT = 14  # scatter 倒三角中心到 K 线 High 的间距
        TEXT_OFFSET_PT = 28    # peak ID 文本到 K 线 High 的间距

        from matplotlib.transforms import offset_copy
        marker_trans = offset_copy(
            ax.transData, fig=ax.get_figure(),
            x=0.0, y=MARKER_OFFSET_PT, units="points",
        )
```

Replace with:

```python
        from matplotlib.transforms import offset_copy
        from BreakoutStrategy.UI.styles import compute_marker_offsets_pt
```

And inside the `for peak in peaks:` loop, immediately after `color = marker_color`, compute per-peak offsets:

```python
            layers = ["triangle", "peak_id"] if peak.id is not None else ["triangle"]
            offsets = compute_marker_offsets_pt(layers)
            marker_trans = offset_copy(
                ax.transData, fig=ax.get_figure(),
                x=0.0, y=offsets["triangle"], units="points",
            )
```

Replace the hard-coded `transform=marker_trans` (which used the loop-invariant transform) with the per-peak `marker_trans` built above. In the `ax.annotate(f"{peak.id}", ...)` block, replace `xytext=(0, TEXT_OFFSET_PT),` with `xytext=(0, offsets["peak_id"]),`.

Final `draw_peaks` body (for reference — replacing lines from "像素偏移常量" through end of method):

```python
        from matplotlib.transforms import offset_copy
        from BreakoutStrategy.UI.styles import compute_marker_offsets_pt

        for peak in peaks:
            peak_x = peak.index

            # 获取基准高度 (K bar high)
            if has_high and 0 <= peak_x < len(df):
                base_price = df.iloc[peak_x][high_col]
            else:
                base_price = peak.price

            color = marker_color

            layers = ["triangle", "peak_id"] if peak.id is not None else ["triangle"]
            offsets = compute_marker_offsets_pt(layers)

            marker_trans = offset_copy(
                ax.transData, fig=ax.get_figure(),
                x=0.0, y=offsets["triangle"], units="points",
            )

            # 1. 绘制峰值标记（倒三角，像素偏移避免遮挡 K 线）
            ax.scatter(
                peak_x,
                base_price,
                marker="v",
                s=400,
                facecolors="none" if style == "normal" else color,
                edgecolors=color,
                linewidths=2,
                zorder=5,
                alpha=1.0 if style == "normal" else 0.6,
                label="Peak" if peak == peaks[0] else None,
                transform=marker_trans,
            )

            # 2. 添加 ID 标注（像素偏移，不受 Y 轴缩放影响）
            if peak.id is not None:
                ax.annotate(
                    f"{peak.id}",
                    xy=(peak_x, base_price),
                    xycoords="data",
                    xytext=(0, offsets["peak_id"]),
                    textcoords="offset points",
                    fontsize=20,
                    ha="center",
                    va="bottom",
                    color=text_id_color,
                    weight="bold",
                )
```

- [ ] **Step 3.4: Run tests — verify still pass**

Run: `uv run pytest BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py -v`
Expected: 10 passed.

- [ ] **Step 3.5: Commit**

```bash
git add BreakoutStrategy/UI/charts/components/markers.py BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py
git commit -m "refactor(markers): draw_peaks uses compute_marker_offsets_pt helper"
```

---

## Task 4: Refactor `draw_breakouts` (dev) to use helper

**Files:**
- Modify: `BreakoutStrategy/UI/charts/components/markers.py`
- Modify: `BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py` (append)

This task actually *changes* behavior: current code has `bo_label` at 8pt (pure) / 30pt (overlap); new values are 10pt / 38pt. Tests are written for NEW values so they fail against current code.

- [ ] **Step 4.1: Append failing tests for `draw_breakouts` offsets**

Append to `test_marker_offsets.py`:

```python
def test_draw_breakouts_pure_bo_offsets(axes_with_df):
    ax, df = axes_with_df
    bo = SimpleNamespace(index=2, price=1.2, broken_peak_ids=[5], quality_score=80.0)
    MarkerComponent.draw_breakouts(ax, df, [bo], peaks=[])
    label = _find_annotation_by_text(ax, "[5]")
    assert label is not None
    assert label.xyann[1] == pytest.approx(10)   # bo_label gap=10, no layers below
    score = _find_annotation_by_text(ax, "80")
    assert score is not None
    assert score.xyann[1] == pytest.approx(40)   # bo_label(10) + bo_score(30)


def test_draw_breakouts_peak_overlap_offsets(axes_with_df):
    ax, df = axes_with_df
    bo = SimpleNamespace(index=2, price=1.2, broken_peak_ids=[5], quality_score=80.0)
    peak = SimpleNamespace(index=2, price=1.2, id=3)
    MarkerComponent.draw_breakouts(ax, df, [bo], peaks=[peak])
    label = _find_annotation_by_text(ax, "[5]")
    assert label is not None
    # triangle(14) + peak_id(14) + bo_label(10) = 38
    assert label.xyann[1] == pytest.approx(38)
    score = _find_annotation_by_text(ax, "80")
    assert score is not None
    # 38 + bo_score(30) = 68
    assert score.xyann[1] == pytest.approx(68)


def test_draw_breakouts_peak_without_id_overlap_offsets(axes_with_df):
    ax, df = axes_with_df
    bo = SimpleNamespace(index=2, price=1.2, broken_peak_ids=[5], quality_score=80.0)
    peak_no_id = SimpleNamespace(index=2, price=1.2, id=None)
    MarkerComponent.draw_breakouts(ax, df, [bo], peaks=[peak_no_id])
    label = _find_annotation_by_text(ax, "[5]")
    # triangle(14) + bo_label(10) = 24 (peak_id layer skipped because id is None)
    assert label.xyann[1] == pytest.approx(24)
```

- [ ] **Step 4.2: Run tests — verify FAIL**

Run: `uv run pytest BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py::test_draw_breakouts_pure_bo_offsets BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py::test_draw_breakouts_peak_overlap_offsets BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py::test_draw_breakouts_peak_without_id_overlap_offsets -v`
Expected: 3 failures (label at 8 vs expected 10; label at 30 vs expected 38; etc.).

- [ ] **Step 4.3: Refactor `draw_breakouts` in `markers.py`**

Locate the constants block in `draw_breakouts` (around lines 158-162):

```python
        # 像素偏移常量（单位: points）—— 不依赖 ylim，缩放后间距恒定
        BO_TEXT_OFFSET_PT = 8        # breakout 文本到 K 线 High 的间距
        BO_TEXT_OVERLAP_PT = 30      # 与 peak 重叠时的文本间距
        BO_SCORE_EXTRA_PT = 30       # 分数标签在 ID 文本上方的额外间距

        # 构建峰值索引集合，用于快速查找重叠
        peak_indices = {p.index for p in peaks} if peaks else set()
```

Replace with:

```python
        from BreakoutStrategy.UI.styles import compute_marker_offsets_pt

        # 构建峰值索引集合（两层：是否存在 peak / peak 是否带 id）
        peak_indices = {p.index for p in peaks} if peaks else set()
        peak_id_indices = (
            {p.index for p in peaks if getattr(p, "id", None) is not None}
            if peaks else set()
        )
```

Locate the per-bo loop body (starting around line 166):

```python
        for bo in breakouts:
            bo_x = bo.index

            # 获取基准高度
            if has_high and 0 <= bo_x < len(df):
                base_price = df.iloc[bo_x][high_col]
            else:
                base_price = bo.price

            color = marker_color

            # 检查是否与峰值重叠
            is_overlap = bo_x in peak_indices
            text_offset = BO_TEXT_OVERLAP_PT if is_overlap else BO_TEXT_OFFSET_PT

            # 绘制突破分数
            if (
                show_score
                and hasattr(bo, "quality_score")
                and bo.quality_score is not None
            ):
                score_offset = text_offset
                if hasattr(bo, "broken_peak_ids") and bo.broken_peak_ids:
                    score_offset += BO_SCORE_EXTRA_PT
                ...  # annotate score
            ...  # annotate label
```

Replace with:

```python
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

            offsets = compute_marker_offsets_pt(layers) if layers else {}

            # 绘制突破分数（在 bo_label 上方；若无 broken_peak_ids 则 score 退到 bo_label 位置）
            if has_score:
                if has_broken_ids:
                    score_y = offsets["bo_score"]
                else:
                    # 只有 score、无 label：临时把 "bo_label" 作为最上层占 score 的位置
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

- [ ] **Step 4.4: Run tests — verify pass**

Run: `uv run pytest BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py -v`
Expected: 13 passed.

- [ ] **Step 4.5: Commit**

```bash
git add BreakoutStrategy/UI/charts/components/markers.py BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py
git commit -m "refactor(markers): draw_breakouts uses helper; fix peak_id/bo_label overlap bug"
```

---

## Task 5: Rewrite `draw_breakouts_live_mode` (annotations instead of scatter) + update pick handler

**Files:**
- Rewrite: `BreakoutStrategy/UI/charts/components/tests/test_draw_breakouts_live_mode.py`
- Modify: `BreakoutStrategy/UI/charts/components/markers.py` (rewrite `draw_breakouts_live_mode`)
- Modify: `BreakoutStrategy/UI/charts/canvas_manager.py` (`_on_pick`)
- Modify: `BreakoutStrategy/UI/charts/tests/test_canvas_manager_live_mode.py` (pick event test)

- [ ] **Step 5.1: Rewrite `test_draw_breakouts_live_mode.py`**

Replace the entire file content with:

```python
"""Unit tests for MarkerComponent.draw_breakouts_live_mode (annotation-based)."""
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
import pandas as pd
import pytest

from BreakoutStrategy.UI.charts.components.markers import MarkerComponent
from BreakoutStrategy.UI.styles import BO_LABEL_TIER_STYLE, CHART_COLORS


@pytest.fixture
def axes_with_df():
    fig, ax = plt.subplots(figsize=(6, 4))
    df = pd.DataFrame({
        "open":  [1.0, 1.1, 1.2, 1.3, 1.4],
        "high":  [1.1, 1.2, 1.3, 1.4, 1.5],
        "low":   [0.9, 1.0, 1.1, 1.2, 1.3],
        "close": [1.05, 1.15, 1.25, 1.35, 1.45],
    })
    ax.plot(range(5), df["close"])
    ax.set_ylim(0.8, 1.6)
    yield ax, df
    plt.close(fig)


def _make_bo(index, broken_peak_ids):
    return SimpleNamespace(index=index, broken_peak_ids=broken_peak_ids, price=1.0)


def _find_tier_annotation(ax, tier: str):
    for t in ax.texts:
        if getattr(t, "bo_tier", None) == tier:
            return t
    return None


def _bbox_rgb(ann) -> tuple:
    """Return RGB tuple of annotation's bbox facecolor (ignoring alpha)."""
    face = ann.get_bbox_patch().get_facecolor()
    return tuple(face[:3])


def test_current_bo_drawn_as_annotation_with_tier_style(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=2,
        visible_matched_indices={2},
    )
    ann = _find_tier_annotation(ax, "current")
    assert ann is not None
    assert _bbox_rgb(ann) == pytest.approx(to_rgb(BO_LABEL_TIER_STYLE["current"]["bg"]), abs=0.01)
    assert ann.get_color() == BO_LABEL_TIER_STYLE["current"]["fg"]


def test_visible_matched_drawn_as_visible_tier(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=100,
        visible_matched_indices={2, 100},
    )
    ann = _find_tier_annotation(ax, "visible")
    assert ann is not None
    assert _bbox_rgb(ann) == pytest.approx(to_rgb(BO_LABEL_TIER_STYLE["visible"]["bg"]), abs=0.01)
    assert _find_tier_annotation(ax, "current") is None


def test_filtered_out_drawn_as_filtered_tier(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=100,
        visible_matched_indices=set(),
        filtered_out_matched_indices={2},
    )
    ann = _find_tier_annotation(ax, "filtered_out")
    assert ann is not None
    assert _bbox_rgb(ann) == pytest.approx(to_rgb(BO_LABEL_TIER_STYLE["filtered_out"]["bg"]), abs=0.01)


def test_plain_drawn_as_plain_tier(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=100,
        visible_matched_indices={100},
    )
    ann = _find_tier_annotation(ax, "plain")
    assert ann is not None
    assert _bbox_rgb(ann) == pytest.approx(to_rgb(BO_LABEL_TIER_STYLE["plain"]["bg"]), abs=0.01)


def test_border_color_uniform_across_tiers(axes_with_df):
    ax, df = axes_with_df
    bos = [
        _make_bo(0, [1]),  # current
        _make_bo(1, [2]),  # visible
        _make_bo(2, [3]),  # filtered_out
        _make_bo(3, [4]),  # plain
    ]
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, bos,
        current_bo_index=0,
        visible_matched_indices={0, 1},
        filtered_out_matched_indices={2},
    )
    border_rgb = to_rgb(CHART_COLORS["bo_marker_current"])
    for tier in ("current", "visible", "filtered_out", "plain"):
        ann = _find_tier_annotation(ax, tier)
        edge = ann.get_bbox_patch().get_edgecolor()
        assert tuple(edge[:3]) == pytest.approx(border_rgb, abs=0.01), tier


def test_pickable_tiers_have_picker_and_idx(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7]), _make_bo(3, [8])],
        current_bo_index=2,
        visible_matched_indices={2, 3},
    )
    current = _find_tier_annotation(ax, "current")
    visible = _find_tier_annotation(ax, "visible")
    assert current.get_picker() is not None
    assert visible.get_picker() is not None
    assert current.bo_chart_idx == 2
    assert visible.bo_chart_idx == 3


def test_plain_tier_has_no_picker(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=100,
        visible_matched_indices={100},
    )
    plain = _find_tier_annotation(ax, "plain")
    assert plain.get_picker() is None


def test_label_text_matches_broken_peak_ids(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [3, 5, 8])],
        current_bo_index=2,
        visible_matched_indices={2},
    )
    ann = _find_tier_annotation(ax, "current")
    assert ann.get_text() == "[3,5,8]"


def test_empty_breakouts_noop(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [],
        current_bo_index=None,
        visible_matched_indices=set(),
    )
    assert len(ax.texts) == 0
    assert len(ax.collections) == 0


def test_bo_without_broken_peak_ids_is_skipped(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [])],
        current_bo_index=2,
        visible_matched_indices={2},
    )
    # No broken_peak_ids -> no label to draw
    assert len(ax.texts) == 0


def test_bo_label_offset_matches_helper_with_peak(axes_with_df):
    ax, df = axes_with_df
    bo_idx = 2
    fake_peak = SimpleNamespace(index=bo_idx, price=1.2, id=5)
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(bo_idx, [7])],
        current_bo_index=bo_idx,
        visible_matched_indices={bo_idx},
        peaks=[fake_peak],
    )
    ann = _find_tier_annotation(ax, "current")
    # triangle(14) + peak_id(14) + bo_label(10) = 38
    assert ann.xyann[1] == pytest.approx(38)


def test_bo_label_offset_without_peak(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=2,
        visible_matched_indices={2},
    )
    ann = _find_tier_annotation(ax, "current")
    # bo_label only = 10
    assert ann.xyann[1] == pytest.approx(10)


def test_all_tiers_produce_four_annotations(axes_with_df):
    ax, df = axes_with_df
    bos = [
        _make_bo(0, [1]),  # current
        _make_bo(1, [2]),  # visible
        _make_bo(2, [3]),  # filtered_out
        _make_bo(3, [4]),  # plain
    ]
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, bos,
        current_bo_index=0,
        visible_matched_indices={0, 1},
        filtered_out_matched_indices={2},
    )
    tiers = {getattr(t, "bo_tier", None) for t in ax.texts if getattr(t, "bo_tier", None)}
    assert tiers == {"current", "visible", "filtered_out", "plain"}
    # No scatter artists
    assert len(ax.collections) == 0
```

- [ ] **Step 5.2: Run tests — verify all fail**

Run: `uv run pytest BreakoutStrategy/UI/charts/components/tests/test_draw_breakouts_live_mode.py -v`
Expected: majority fail (current impl still produces scatter collections, not annotations with `.bo_tier`). Some tests may pass incidentally (e.g., `test_empty_breakouts_noop`).

- [ ] **Step 5.3: Rewrite `draw_breakouts_live_mode` in `markers.py`**

Locate the current `draw_breakouts_live_mode` method (lines ~238-367). Replace the entire method with:

```python
    @staticmethod
    def draw_breakouts_live_mode(
        ax,
        df: pd.DataFrame,
        breakouts: list,
        current_bo_index,
        visible_matched_indices: set[int] | None = None,
        filtered_out_matched_indices: set[int] | None = None,
        peaks: list = None,
        colors: dict = None,
    ):
        """Live UI 专用：以彩色 bo_label annotation 作为单一 BO marker。

        四态（current / visible / filtered_out / plain）通过 BO_LABEL_TIER_STYLE
        查背景/文字色，边框统一为 CHART_COLORS['bo_marker_current']（深蓝）。
        前三态 annotation 挂 picker=True 并记 `.bo_chart_idx` + `.bo_tier`。

        注：`colors` 参数为签名兼容保留（canvas_manager 仍会传入），实际使用的
        颜色一律取自 BO_LABEL_TIER_STYLE / CHART_COLORS（SSoT）。
        """
        if not breakouts:
            return

        if visible_matched_indices is None:
            visible_matched_indices = set()
        if filtered_out_matched_indices is None:
            filtered_out_matched_indices = set()

        from BreakoutStrategy.UI.styles import (
            BO_LABEL_TIER_STYLE,
            CHART_COLORS,
            compute_marker_offsets_pt,
        )

        border_color = CHART_COLORS["bo_marker_current"]

        high_col = "high" if "high" in df.columns else "High"
        has_high = high_col in df.columns

        peak_indices = {p.index for p in peaks} if peaks else set()
        peak_id_indices = (
            {p.index for p in peaks if getattr(p, "id", None) is not None}
            if peaks else set()
        )

        tier_zorder = {
            "current": 13,
            "visible": 12,
            "filtered_out": 11,
            "plain": 10,
        }

        for bo in breakouts:
            if not getattr(bo, "broken_peak_ids", None):
                continue

            bo_x = bo.index
            base_price = (
                df.iloc[bo_x][high_col]
                if has_high and 0 <= bo_x < len(df)
                else bo.price
            )

            tier = _classify_bo(
                bo_x,
                current_bo_index,
                visible_matched_indices,
                filtered_out_matched_indices,
            )

            # 构造本 bar 实际存在的堆叠层（自下而上）
            if bo_x in peak_id_indices:
                layers = ["triangle", "peak_id", "bo_label"]
            elif bo_x in peak_indices:
                layers = ["triangle", "bo_label"]
            else:
                layers = ["bo_label"]
            offset_pt = compute_marker_offsets_pt(layers)["bo_label"]

            style = BO_LABEL_TIER_STYLE[tier]
            text = "[" + ",".join(map(str, bo.broken_peak_ids)) + "]"

            kwargs = dict(
                xy=(bo_x, base_price),
                xycoords="data",
                xytext=(0, offset_pt),
                textcoords="offset points",
                fontsize=20,
                ha="center",
                va="bottom",
                color=style["fg"],
                weight="bold",
                zorder=tier_zorder[tier],
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor=style["bg"],
                    edgecolor=border_color,
                    linewidth=1.5,
                    alpha=0.9,
                ),
            )
            if tier in ("current", "visible", "filtered_out"):
                kwargs["picker"] = True

            ann = ax.annotate(text, **kwargs)
            ann.bo_chart_idx = bo_x
            ann.bo_tier = tier
```

- [ ] **Step 5.4: Run tests — verify all pass**

Run: `uv run pytest BreakoutStrategy/UI/charts/components/tests/test_draw_breakouts_live_mode.py -v`
Expected: 14 passed.

- [ ] **Step 5.5: Update `canvas_manager._on_pick`**

Locate `_on_pick` in `BreakoutStrategy/UI/charts/canvas_manager.py` (lines 367-380):

```python
    def _on_pick(self, event):
        """matplotlib pick_event handler：BO marker 点击反向同步到 MatchList。"""
        cb = getattr(self, "_on_bo_picked_callback", None)
        if cb is None:
            return
        artist = event.artist
        idxs = getattr(artist, "bo_chart_indices", None)
        if not idxs:
            return
        # event.ind 是被点中的点在 scatter offsets 里的索引
        for i in event.ind:
            if 0 <= i < len(idxs):
                cb(idxs[i])
                return
```

Replace with:

```python
    def _on_pick(self, event):
        """matplotlib pick_event handler：BO marker 点击反向同步到 MatchList。"""
        cb = getattr(self, "_on_bo_picked_callback", None)
        if cb is None:
            return
        artist = event.artist
        idx = getattr(artist, "bo_chart_idx", None)
        if idx is None:
            return
        cb(idx)
```

- [ ] **Step 5.6: Update `test_canvas_manager_live_mode.py::test_live_mode_pick_event_invokes_on_bo_picked`**

In `BreakoutStrategy/UI/charts/tests/test_canvas_manager_live_mode.py`, replace the body of `test_live_mode_pick_event_invokes_on_bo_picked` (lines ~134-160):

```python
def test_live_mode_pick_event_invokes_on_bo_picked(tk_container, minimal_df):
    """模拟 pick_event 触发，验证回调拿到正确的 bo_chart_idx。"""
    from types import SimpleNamespace
    mgr = ChartCanvasManager(tk_container)
    received = []
    mgr.update_chart(
        df=minimal_df,
        breakouts=[_fake_bo(10), _fake_bo(12)],
        active_peaks=[], superseded_peaks=[],
        symbol="TEST",
        display_options={
            "live_mode": True,
            "current_bo_index": 10,
            "visible_matched_indices": {10, 12},
            "on_bo_picked": lambda i: received.append(i),
        },
    )
    # 找到某个可点击 annotation，伪造 pick_event
    target = None
    for t in mgr.fig.axes[0].texts:
        if getattr(t, "bo_tier", None) == "visible":
            target = t
            break
    assert target is not None
    fake_event = SimpleNamespace(artist=target)
    mgr._on_pick(fake_event)
    assert received == [target.bo_chart_idx]
```

- [ ] **Step 5.7: Run the updated canvas_manager test**

Run: `uv run pytest BreakoutStrategy/UI/charts/tests/test_canvas_manager_live_mode.py -v`
Expected: all pass (the updated test plus the existing dispatch tests).

- [ ] **Step 5.8: Commit**

```bash
git add BreakoutStrategy/UI/charts/components/markers.py BreakoutStrategy/UI/charts/components/tests/test_draw_breakouts_live_mode.py BreakoutStrategy/UI/charts/canvas_manager.py BreakoutStrategy/UI/charts/tests/test_canvas_manager_live_mode.py
git commit -m "refactor(markers): live-mode bo_label replaces scatter with 4-tier picker annotation"
```

---

## Task 6: Full chart test suite verification

**Files:** (read-only verification)

- [ ] **Step 6.1: Run all chart tests**

Run: `uv run pytest BreakoutStrategy/UI/charts/ -v`
Expected: all pass. If any unrelated test fails, investigate and fix before marking done.

- [ ] **Step 6.2: Run all BreakoutStrategy tests to catch accidental regressions**

Run: `uv run pytest BreakoutStrategy/ -q`
Expected: all pass (or same pre-existing failures as baseline, nothing new).

- [ ] **Step 6.3: Manual sanity check — open dev UI**

Run (foreground in terminal):
```bash
uv run python -m BreakoutStrategy.dev.main
```

Visually verify on a stock with BO markers:
- Pure BO bar: `[ids]` label sits ~10pt above candle high, score ~40pt above.
- Peak+BO bar: triangle ~14pt, `peak_id` ~28pt, `[ids]` ~38pt, score ~68pt. No overlap between `peak_id` and `[ids]` (the previous bug).

- [ ] **Step 6.4: Manual sanity check — open live UI**

Run (foreground in terminal):
```bash
uv run python -m BreakoutStrategy.live
```

Visually verify:
- BO markers no longer have circle scatter on top — only the `[ids]` label visible.
- Four tier colors distinguishable: deep blue (current), light blue (visible), cyan (filtered_out), white (plain).
- Click on a visible BO label → MatchList selection updates (via `_on_bo_picked`).

- [ ] **Step 6.5: Commit (if any last fixes needed)**

Only if Step 6.1/6.2 surfaced issues requiring code changes:
```bash
git add <touched files>
git commit -m "fix(markers): <specific issue>"
```
Otherwise, no commit.

---

## Notes on Scope

- No backward-compatibility aliases for deleted constants — spec explicitly opts out.
- `colors` parameter on `draw_breakouts_live_mode` is retained for signature compatibility with `canvas_manager` but ignored; all tier colors come from `BO_LABEL_TIER_STYLE` / `CHART_COLORS`.
- Edge case `bo` without `broken_peak_ids`: dev `draw_breakouts` promotes score into the `bo_label` slot via `tmp_layers` hack (preserves current behavior); live `draw_breakouts_live_mode` skips the BO entirely (no label to draw, no other artist).
