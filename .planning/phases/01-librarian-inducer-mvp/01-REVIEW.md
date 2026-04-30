---
phase: 01-librarian-inducer-mvp
reviewed: 2026-04-29T10:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - BreakoutStrategy/UI/charts/keyboard_picker.py
  - BreakoutStrategy/UI/charts/canvas_manager.py
  - BreakoutStrategy/feature_library/sample_renderer.py
  - BreakoutStrategy/feature_library/preprocess.py
  - BreakoutStrategy/feature_library/prompts.py
  - BreakoutStrategy/feature_library/inducer_prompts.py
  - BreakoutStrategy/UI/charts/tests/test_keyboard_picker.py
  - BreakoutStrategy/feature_library/tests/test_sample_renderer.py
  - BreakoutStrategy/feature_library/tests/test_prompts.py
  - BreakoutStrategy/feature_library/tests/test_inducer_prompts.py
  - BreakoutStrategy/dev/tests/test_sample_picker_handler.py
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-04-29
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Phase 1 gap-fix 的核心逻辑（三态 FSM、渲染窗口收窄、BO close pivot、prompt 文本通道对齐）整体实现正确，D-01 到 D-11 全部落地，无安全漏洞、无数据丢失风险。发现 1 个影响可维护性的 BLOCKER 级问题（全局 rcParams 污染）、2 个 WARNING 级代码质量问题（模块文档错误字段名、`fmt_num` 行为不一致）、3 个 INFO 级问题（测试命名误导、sticky artist 引用泄漏、`hspace` 双重设置冗余）。

---

## Critical Issues

无。

---

## Warnings

### WR-01: canvas_manager.py 直接写全局 `plt.rcParams`，违反 OO API 不污染原则

**File:** `BreakoutStrategy/UI/charts/canvas_manager.py:166`

**Issue:** `update_chart` 中第 166-175 行调用 `plt.rcParams.update({...})` 设置 `font.size: 32`、`axes.titlesize: 40` 等全局参数。这与 D-09 明确要求的"不污染全局 rcParams（用 `mpl.rc_context` 局部覆盖）"以及项目的"OO API 不污染全局 backend / rcParams"原则直接冲突。在同进程中 `sample_renderer.py` 使用了 `with mpl.rc_context(...)` 正确地局部覆盖，但 dev UI 的 Tk 图表每次 `update_chart` 都会永久改写全局字号，累积副作用。

**Fix:**
```python
# 替换 plt.rcParams.update({...}) 为局部 OO API 设置
# 方式一：直接在 Figure 构造后用 OO API 设置（推荐）
self.fig = plt.Figure(figsize=(fig_width, fig_height), dpi=dpi)
# 对 figure 内所有 axes 统一设置，不碰全局 rcParams:
# axes 字号等在 draw_statistics_panel / candlestick.draw 之后按需 set_*
# 方式二（等效）：
with mpl.rc_context({"font.size": 32, "axes.titlesize": 40,
                     "axes.labelsize": 28, "xtick.labelsize": 22,
                     "ytick.labelsize": 22, "legend.fontsize": 26}):
    self.fig = plt.Figure(...)
    ...  # 所有 axes 绘制都在此 context 内
```

---

### WR-02: `keyboard_picker.py` 模块文档示例使用了不存在的方法名

**File:** `BreakoutStrategy/UI/charts/keyboard_picker.py:23-27`

**Issue:** 模块顶部的使用示例代码引用了三个在 `ChartCanvasManager` 中根本不存在的方法名：
- `self._trigger_sample_render`（实际为 `on_render` 闭包）
- `self._show_toast`（实际为 `self._show_picker_toast`）
- `self._set_status_sticky`（实际为 `self._set_picker_sticky`）

此外，第 23 行使用 `b.idx` 字段，而 `canvas_manager.py:1026` 的正确实现使用 `b.index`（与 `breakout_detector.py` 一致）。模块文档示例代码直接误导维护者，且 `b.idx` 是错误的字段名。

**Fix:**
```python
# 将文档示例更新为与 canvas_manager._wire_picker 一致的真实调用形式：
picker = KeyboardPicker(
    get_hovered_bar=lambda: self._last_hover_x if self._hover_in_chart else None,
    get_bo_indices=lambda: frozenset(b.index for b in breakouts),  # b.index，非 b.idx
    on_render=on_render,           # _wire_picker 内的 on_render 闭包
    on_toast=self._show_picker_toast,
    on_sticky=self._set_picker_sticky,
    on_marker_redraw=on_marker_redraw,
)
```

---

### WR-03: `inducer_prompts.py` 的 `fmt_num` 对 `bool` 返回 `str(v)` 而非 `"N/A"`，与 `prompts.py` 行为不一致

**File:** `BreakoutStrategy/feature_library/inducer_prompts.py:67-68`

**Issue:** `inducer_prompts.py` 内的 `fmt_num` 函数对 `bool` 类型返回 `str(v)`（即 `"True"` 或 `"False"`），而 `prompts.py` 中的同名函数返回 `"N/A"`。如果 `consolidation` 字段（如 `consolidation_height_pct`）意外传入 `bool` 值，`inducer_prompts` 会将 `"True"` / `"False"` 注入 batch prompt，形成语义错误的文本通道内容；两个模块的降级行为不一致也使维护者难以预期。

**Fix:**
```python
# inducer_prompts.py 中 fmt_num 改为与 prompts.py 一致：
def fmt_num(v) -> str:
    if isinstance(v, bool):
        return "N/A"   # 与 prompts.py 统一，而非 str(v)
    return f"{v:.2f}" if isinstance(v, (int, float)) else "N/A"
```

---

## Info

### IN-01: `test_build_user_message_handles_missing_pivot_close_gracefully` 测试名称与实际覆盖场景不符

**File:** `BreakoutStrategy/feature_library/tests/test_prompts.py:111-134`

**Issue:** 测试名称和 docstring 说"pivot_close 缺失时降级"，但测试数据中 `bo['close'] = 104.0`（有效正数），实际走的是正常 OHLC 计算分支，不会触发任何降级逻辑。测试实际上只验证了"有效 bo_close 下不泄漏绝对价"，与命名描述的场景不匹配。真正的"missing pivot_close 降级"测试（`bo_close` 为 0 或缺失）已由 `test_build_user_message_handles_missing_bo_close_gracefully` 覆盖，该测试存在重复/混淆。

**Fix:** 重命名测试或替换数据以真正覆盖 pivot_close 缺失场景（若仍需保留对旧字段的兼容测试）；或删除该测试并在注释中说明已由 `_missing_bo_close_gracefully` 测试覆盖。

---

### IN-02: `_cleanup()` 不清除 `_picker_sticky_artist` 引用，存在跨 figure 生命周期的悬挂引用

**File:** `BreakoutStrategy/UI/charts/canvas_manager.py:400-442`

**Issue:** `_cleanup()` 清理了 canvas、fig、annotation、crosshair 等资源，但未清除 `_picker_sticky_artist`（若存在）。在下一次 `update_chart` 时：(1) `_cleanup()` 运行销毁旧 fig；(2) `_cancel_picker_toast()` 被调用（line 145）清理 toast；(3) **sticky artist 没有被清理**，其引用继续指向已销毁 fig 上的死亡 artist。当新 fig 构建后 `_set_picker_sticky` 被调用时，会尝试 `art.remove()` 并通过 `except: pass` 静默忽略失败。这不会导致崩溃，但持有的死亡 artist 引用在 GC 前会占用内存，且 sticky 在 `update_chart` 期间（从 cleanup 到新 sticky 写入前）处于未清理状态。

**Fix:**
```python
# 在 _cleanup() 末尾加入 sticky artist 清理（与 toast 处理对称）：
if getattr(self, "_picker_sticky_artist", None) is not None:
    try:
        self._picker_sticky_artist.remove()
    except Exception:
        pass
    self._picker_sticky_artist = None
```

---

### IN-03: `sample_renderer.py` 中 `hspace` 在 `gridspec` 和 `subplots_adjust` 中重复设置

**File:** `BreakoutStrategy/feature_library/sample_renderer.py:61-63` 和 `120`

**Issue:** `hspace=0.05` 在 `fig.add_gridspec(hspace=0.05)` 和 `fig.subplots_adjust(hspace=0.05)` 中均设置，两者值相同。`subplots_adjust` 的 `hspace` 会覆盖 `gridspec` 的 `hspace`，导致 `gridspec` 中的设置是无效的冗余代码。虽然结果一致，但维护者读代码时会疑惑两处设置是否有意为之。

**Fix:** 删除 `fig.add_gridspec` 中的 `hspace=0.05`，仅保留 `fig.subplots_adjust` 中的统一设置：
```python
gs = fig.add_gridspec(2, 1, height_ratios=[PRICE_PANEL_RATIO, VOLUME_PANEL_RATIO])
# hspace 统一由后面的 subplots_adjust 控制
```

---

_Reviewed: 2026-04-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
