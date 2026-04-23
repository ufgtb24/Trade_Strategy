# Marker 堆叠间距重构：从绝对偏移到相对间距

**Date:** 2026-04-17
**Scope:** `BreakoutStrategy/UI/styles.py`, `BreakoutStrategy/UI/charts/components/markers.py`, `BreakoutStrategy/UI/charts/canvas_manager.py`（pick_event 衔接）, `BreakoutStrategy/UI/charts/components/tests/*`

## 背景与动机

当前 `markers.py` 将每个 marker 的垂直位置表达为"到 K 线 High 的绝对像素偏移"（`MARKER_OFFSET_PT`、`BO_TEXT_OVERLAP_PT` 等内联常量）。这带来三个问题：

1. **双写与漂移**：堆叠中相邻两层的实际间距 = `A.offset - B.offset`，需要手算；改任何一个数值都要重算后续层。
2. **隐藏的重叠 bug**：dev 模式在 peak+bo 同 bar 时，`peak_id`（offset=28）与 `bo_label`（offset=30，overlap 模式）只差 2pt，实际是完全遮挡——只是 `bo_label` 的 opaque bbox 盖住了 `peak_id` 让使用者没察觉。
3. **配置散落**：间距常量分散在 `draw_peaks` / `draw_breakouts` / `draw_breakouts_live_mode` 三个函数内部，调整时要跳三处。

此外，live 模式当前通过 **scatter 圆圈** + **bo_label 方框** 两个 artist 共同传达 "matched BO 的状态"（tier）。用户反馈希望合并为**单一 bo_label**，通过 label 的背景色区分四态（`current` / `visible` / `filtered_out` / `plain`），并取消圆圈。

## 目标

1. 将 marker 堆叠间距从"到 High 的绝对偏移"改为"到下方相邻层的相对间距"；最底层隐式以 K 线 High 作为"下方"。
2. 将所有 marker 相关常量集中到 `BreakoutStrategy/UI/styles.py`，成为单一 SSoT。
3. Live 模式取消 scatter 圆圈，`bo_label` 承担四态配色 + 点击拾取角色。
4. 显式在 live 堆叠中加入 `peak_id` 层（当前是"巧合对齐"，重构后是显式计算）。
5. 不保留旧常量的向后兼容层——`markers.py` 内的内联 pt 常量全部删除。

## 现状

### Dev 模式（`draw_peaks` + `draw_breakouts`）

两次独立调用，通过 `peak_indices` 集合交换"是否 overlap"信号：

| Layer | 常量 | 值 (pt) |
|---|---|---|
| `triangle` | `MARKER_OFFSET_PT`（`draw_peaks`） | 14 |
| `peak_id` | `TEXT_OFFSET_PT`（`draw_peaks`） | 28（绝对到 High） |
| `bo_label`（无 overlap） | `BO_TEXT_OFFSET_PT` | 8 |
| `bo_label`（与 peak overlap） | `BO_TEXT_OVERLAP_PT` | 30 |
| `bo_score`（加在 label 上方） | `BO_SCORE_EXTRA_PT` | 30 |

Bug：peak+bo 同 bar 时 `peak_id`(28) 与 `bo_label`(30) 几乎同位，后者的 bbox 遮盖前者。

### Live 模式（`draw_breakouts_live_mode`）

通过 4 个 scatter 组（按 tier 分桶）+ annotation label 共同渲染。间距：

| Layer | 常量 | 值 (pt) |
|---|---|---|
| `bo_label`（无 overlap） | `LABEL_OFFSET_PT` | 10 |
| `bo_label`（与 peak overlap） | `LABEL_OVERLAP_PT` | 38 |
| `bo_marker`（circle，无 overlap） | `MARKER_OFFSET_PT` | 48 |
| `bo_marker`（circle，overlap） | `MARKER_OVERLAP_PT` | 76 |

Tier 着色通过 `_draw_group` 在 scatter 的 `facecolor`/`edgecolor` 上实现；picker 挂在前三组 scatter 上，`sc.bo_chart_indices` 数组 + `event.ind[0]` 反查 bo 索引。

## 目标设计

### 1. 架构

**单一 SSoT：** `BreakoutStrategy/UI/styles.py` 新增一个字典 + 一个辅助函数：

```python
# Marker 堆叠间距（单位: points）
# 每层值 = 到下方相邻层的像素间距；当此层是堆叠最底时，"下方"即 K 线 High。
# 实际堆叠顺序由 draw_* 调用时传入的 layers 列表决定。
MARKER_STACK_GAPS_PT = {
    "triangle": 14,   # peak 倒三角
    "peak_id":  14,   # peak ID 数字文本
    "bo_label": 10,   # BO 的 [broken_peak_ids] 方框
    "bo_score": 30,   # BO 分数方框（仅 dev 使用）
}
```

**语义统一：** 每个 key 的值都表示"到下方相邻层的像素间距"；不再区分"绝对 vs 相对"。字典内的 key 顺序无语义，实际堆叠顺序由 draw 函数在 per-bar 粒度上决定。

**几何放共享 `UI/styles.py` 的理由：** CLAUDE.md 明确 `UI/` 是 dev/live 共享基础设施；且 `triangle` / `peak_id` / `bo_label` 三层的 gap 值在 dev 和 live 之间一致——放一处避免双写漂移。`bo_score` 虽只 dev 用，单个 key 的共存成本远低于拆库。

### 2. 数据

**`styles.py` 新增：**

```python
MARKER_STACK_GAPS_PT = {
    "triangle": 14,
    "peak_id":  14,
    "bo_label": 10,
    "bo_score": 30,
}

# Live 模式 bo_label 四态配色（dev 模式不使用；参考键来自 CHART_COLORS）
BO_LABEL_TIER_STYLE = {
    "current":      {"bg": CHART_COLORS["bo_marker_current"],      "fg": "#FFFFFF"},
    "visible":      {"bg": CHART_COLORS["bo_marker_visible"],      "fg": CHART_COLORS["bo_marker_current"]},
    "filtered_out": {"bg": CHART_COLORS["bo_marker_filtered_out"], "fg": CHART_COLORS["bo_marker_current"]},  # 青绿
    "plain":        {"bg": CHART_COLORS["breakout_text_bg"],       "fg": CHART_COLORS["bo_marker_current"]},
}
# 所有 tier 的 bo_label 边框统一为 CHART_COLORS["bo_marker_current"]
```

`CHART_COLORS` 本身不改：`bo_marker_filtered_out` 保持现值 `#14DCB8`（青绿）。

**Helper：**

```python
def compute_marker_offsets_pt(layers: list[str]) -> dict[str, float]:
    """
    按堆叠顺序（自下而上）累加 gap，返回每层到 K 线 High 的累计像素偏移。

    Args:
        layers: 本 bar 实际存在的 marker 层名，自下而上顺序。

    Returns:
        dict mapping layer name → 累计 pt offset。

    Example:
        >>> compute_marker_offsets_pt(["triangle", "peak_id", "bo_label", "bo_score"])
        {"triangle": 14, "peak_id": 28, "bo_label": 38, "bo_score": 68}

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

### 3. 接口变化

#### `markers.py::draw_peaks`

- 删除内联常量 `MARKER_OFFSET_PT`、`TEXT_OFFSET_PT`。
- 每个 peak 本地构造 `layers`：
  - 有 `peak.id` → `["triangle", "peak_id"]`
  - 无 → `["triangle"]`
- 调 `compute_marker_offsets_pt(layers)` 取 pt，喂给 `offset_copy`（scatter）和 `xytext`（annotate）。
- `draw_peaks` 不感知 bo：peak_id 永远紧贴 triangle，不为上方的 bo 让位（上方的 bo 自己往上推）。
- 签名不变。

#### `markers.py::draw_breakouts`（dev）

- 删除内联常量 `BO_TEXT_OFFSET_PT`、`BO_TEXT_OVERLAP_PT`、`BO_SCORE_EXTRA_PT`。
- 在函数开头构建两个集合（替代当前的单一 `peak_indices`）：
  - `peak_indices = {p.index for p in peaks}`
  - `peak_id_indices = {p.index for p in peaks if p.id is not None}`
- 每个 bo 本地构造 `layers`（自下而上）：
  - `bo_x in peak_id_indices`（同 bar 有 peak 且 peak 带 id）→ `["triangle", "peak_id", "bo_label", "bo_score"]`
  - `bo_x in peak_indices - peak_id_indices`（同 bar 有 peak 但无 id）→ `["triangle", "bo_label", "bo_score"]`
  - 仅 bo → `["bo_label", "bo_score"]`
- 调 `compute_marker_offsets_pt(layers)` 取 pt，喂给 `xytext`。
- 签名不变。

#### `markers.py::draw_breakouts_live_mode`（live）

- **删除**：内联常量 `LABEL_OFFSET_PT`、`LABEL_OVERLAP_PT`、`MARKER_OFFSET_PT`、`MARKER_OVERLAP_PT`；整个 scatter 圆圈绘制路径（`_draw_group` 内部函数、`trans_normal`/`trans_overlap` 两个 `offset_copy`、`buckets` 分桶结构）。
- **保留**：`_classify_bo` tier 分类逻辑（位于模块顶层）。
- **新增**：每个 bo
  1. 调 `_classify_bo` 得 tier（四态之一）。
  2. 构造 `layers`（同 dev 的逻辑，只是无 `bo_score`）：
     - `bo_x in peak_id_indices` → `["triangle", "peak_id", "bo_label"]`
     - `bo_x in peak_indices - peak_id_indices` → `["triangle", "bo_label"]`
     - 纯 bo → `["bo_label"]`
  3. 调 `compute_marker_offsets_pt(layers)` 取 pt。
  4. 从 `BO_LABEL_TIER_STYLE[tier]` 查 `bg`/`fg`，构造 annotate 的 `bbox`（`facecolor=bg, edgecolor=bo_marker_current, textcolor=fg`）。
  5. 前三个 tier（`current` / `visible` / `filtered_out`）的 annotation 设置 `picker=True, pickradius=8`。`plain` 不设 picker。
  6. annotation artist 上挂 `.bo_chart_idx = bo.index` 和 `.bo_tier = tier`（一 bo 一 artist，不再用数组索引）。
- 签名不变（兼容 canvas_manager 的现有调用）。

#### `canvas_manager.py` pick_event 衔接

当前 pick_event 回调通过 `event.artist.bo_chart_indices[event.ind[0]]` 取 bo 索引。重构后改为 `event.artist.bo_chart_idx`（标量，因每个 annotation 对应单个 bo）。

### 4. 测试策略

采用 TDD：每个新/改测试先写失败版 → 写实现 → 验证通过 → 下一个。

#### 新增：`BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py`

覆盖 helper 本身：

- `test_single_layer_triangle`：`["triangle"]` → `{"triangle": 14}`
- `test_dev_full_stack`：`["triangle","peak_id","bo_label","bo_score"]` → `{"triangle":14,"peak_id":28,"bo_label":38,"bo_score":68}`
- `test_live_stack_with_peak`：`["triangle","peak_id","bo_label"]` → `{"triangle":14,"peak_id":28,"bo_label":38}`
- `test_pure_bo_stack`：`["bo_label","bo_score"]` → `{"bo_label":10,"bo_score":40}`
- `test_unknown_layer_raises`：未知 layer 抛 `KeyError`。

#### 改写：`test_draw_breakouts_live_mode.py`

所有基于 scatter 的断言改为基于 annotation：

- 新辅助 `_find_tier_annotation(ax, tier)`：遍历 `ax.texts`（含 annotation），返回 `ann.bo_tier == tier` 的第一个。
- `test_current_bo_drawn_in_current_group` → `test_current_bo_drawn_as_annotation`：断言存在 `bo_tier="current"` 的 annotation，`bbox` 的 facecolor 匹配 `BO_LABEL_TIER_STYLE["current"]["bg"]`，文字颜色匹配 `fg`。
- `test_visible_matched_*`、`test_filtered_out_*`、`test_plain_*`：类似。`plain` 验证 bbox facecolor 为白色 `breakout_text_bg`。
- `test_pickable_groups_have_picker_and_indices` → `test_pickable_tiers_have_picker_and_idx`：断言前三个 tier 的 annotation `.get_picker() is not None`，且 `.bo_chart_idx == expected_bo_index`（注意是 `_idx` 单数）。`plain` 无 picker。
- `test_label_still_drawn`：保留，改为查找 tier annotation 且断言文本。
- `test_empty_noop`：`ax.collections` 不再需要检查（scatter 已移除）；改为 `ax.texts` 为空。
- `test_overlap_stacks_above_peak` → `test_bo_label_offset_matches_helper`：
  - peaks 参数传入 bo 同 index 的 peak → annotation 的 `xytext` y 分量应等于 `compute_marker_offsets_pt(["triangle","peak_id","bo_label"])["bo_label"]` = 38。
  - 无 peaks → 应为 `compute_marker_offsets_pt(["bo_label"])["bo_label"]` = 10。
- `test_all_tiers_populated_produces_four_scatters` → `test_all_tiers_populated_produces_four_annotations`：4 种 tier 各有一个 annotation，`ax.collections` 不再增加。

#### 新增（dev）：`test_draw_peaks_and_breakouts_offsets.py`（或补在 `test_marker_offsets.py` 内）

当前 dev 侧没有独立测试覆盖 draw_peaks / draw_breakouts 的 offset 行为。补几个回归锚点：

- `test_draw_peaks_triangle_only`：无 `peak.id` 的 peak，annotate 不创建 peak_id 文本，scatter 的 offset transform 的 y 分量 = 14pt。
- `test_draw_peaks_with_id`：有 `peak.id` 的 peak，peak_id annotation 的 `xytext` y = 28pt。
- `test_draw_breakouts_pure_bo_offsets`：无 peak overlap 时，`[...]` label 的 `xytext` y = 10pt，score 的 y = 40pt。
- `test_draw_breakouts_peak_overlap_offsets`：peak overlap 时 label y = 38，score y = 68。

#### 不需要改

- `test_bo_classifier.py`：`_classify_bo` 逻辑未动。
- `test_canvas_manager_live_mode.py`：只验证分派（live vs dev），marker 细节不涉及——但 pick_event 衔接可能需要补一个小测试验证 `bo_chart_idx` 访问路径（如果这个分支有覆盖）。
- `test_filter_range.py` / `test_axes_interaction.py` / `test_range_utils.py` / `test_tooltip_anchor.py`：无关。

### 5. 范围之外

- **不**新增 CHART_COLORS 键，不改色值。
- **不**改动 dev 模式的 `bo_label` / `bo_score` 颜色 —— 仅 live 的 `bo_label` 按 tier 着色。
- **不**引入 live 的 `bo_score`（live 一贯不显示 quality_score）。
- **不**调整 `draw_resistance_zones` / `draw_moving_averages` / `draw_price_line` / `draw_template_highlights` —— 这些不是堆叠 marker，与间距无关。
- **不**提供旧常量的向后兼容别名。

## 修改文件清单

| 文件 | 类型 | 概要 |
|---|---|---|
| `BreakoutStrategy/UI/styles.py` | 修改 | 新增 `MARKER_STACK_GAPS_PT`、`BO_LABEL_TIER_STYLE`、`compute_marker_offsets_pt` |
| `BreakoutStrategy/UI/charts/components/markers.py` | 修改 | 删除所有内联 pt 常量；`draw_peaks` / `draw_breakouts` / `draw_breakouts_live_mode` 改调 helper；live 删除 scatter 路径；live annotation 按 tier 上色 + 挂 picker |
| `BreakoutStrategy/UI/charts/canvas_manager.py` | 修改 | pick_event 回调改读 `event.artist.bo_chart_idx`（原为 `.bo_chart_indices[event.ind[0]]`） |
| `BreakoutStrategy/UI/charts/components/tests/test_draw_breakouts_live_mode.py` | 改写 | 所有 scatter 断言 → annotation 断言 |
| `BreakoutStrategy/UI/charts/components/tests/test_marker_offsets.py` | 新增 | helper 的单元测试 + dev 侧 draw_peaks / draw_breakouts offset 回归锚点 |
