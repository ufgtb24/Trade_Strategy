---
phase: 01-librarian-inducer-mvp
plan: "03"
subsystem: feature-library/sample-renderer
tags: [chart-rendering, normalization, tdd, matplotlib]
dependency_graph:
  requires: []
  provides:
    - sample_renderer.render_sample_chart(left_index=) 新签名
    - _build_figure_for_inspection(left_index=) 新签名
    - BO close 作 Y 轴 pivot（跨样本几何同构）
  affects:
    - BreakoutStrategy/feature_library/preprocess.py（调用方 kwarg 同步）
tech_stack:
  added: []
  patterns:
    - mpl.rc_context 局部字号覆盖（不污染全局 rcParams）
    - CandlestickComponent.draw 收窄子 df 调用
key_files:
  created: []
  modified:
    - BreakoutStrategy/feature_library/sample_renderer.py
    - BreakoutStrategy/feature_library/preprocess.py
    - BreakoutStrategy/feature_library/tests/test_sample_renderer.py
decisions:
  - "渲染窗口收窄：df_window.iloc[left_index : bo_index + 1]，original df 仍传整段"
  - "pivot_close 在切片前计算（df_window.iloc[bo_index]['close']），避免 bo_index 在子 df 失效"
  - "axvline 检测区分：使用 line.get_transform() == ax.get_xaxis_transform() 而非 xdata 相等，避免误判 K 线影线"
metrics:
  duration: "~15 min"
  completed: "2026-04-29T08:17:33Z"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
---

# Phase 01 Plan 03: sample_renderer 重写（D-05..D-09）Summary

**One-liner:** 重写 sample_renderer 实现渲染窗口收窄至 [left_index, bo_index]、视觉脱敏（删 axvline/legend）、BO close 作 Y 轴 pivot、mpl.rc_context 字号压缩，同步 preprocess.py kwarg 重命名。

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | 重写 sample_renderer.py D-05..D-09 + 同步 preprocess.py kwarg | 5e5e9d9 | sample_renderer.py, preprocess.py |
| 2 | 扩展 test_sample_renderer.py 断言新行为（含具体字号 artist 级断言） | a9f1589 | test_sample_renderer.py |

## What Was Built

### Task 1: sample_renderer.py 重写

实现了 D-05 到 D-09 全部四个决策：

**D-05 渲染窗口收窄：**
- `_build_figure_for_inspection` 和 `render_sample_chart` 形参 `pk_index` → `left_index`
- 函数内先计算 `pivot_close = float(df_window.iloc[bo_index]["close"])`（切片前）
- 然后 `sub_df = df_window.iloc[left_index : bo_index + 1]`
- CandlestickComponent.draw、volume bar、xlim 全部用 sub_df

**D-06 视觉脱敏：**
- 删除 ax_price 两条 axvline（pk 橙色 + bo 蓝色）
- 删除 ax_vol 两条 axvline
- 删除 `ax_price.legend(loc="upper left")`
- 标题保持 `"Breakout sample (anonymized)"`，无语义后缀

**D-07 Y 轴 BO close pivot：**
- `pivot_close = float(df_window.iloc[bo_index]["close"])`（原为 pk_index）
- `ax_price.set_ylabel("Price (% from BO close)")`
- `_pct_fmt` 公式不变，零点移至 BO close

**D-09 字号压缩：**
- `with mpl.rc_context({"font.size": 8}):` 包裹整个 Figure 构造
- title fontsize=10，xlabel/ylabel fontsize=8，tick_params labelsize=7

**preprocess.py 同步：**
- `render_sample_chart(..., pk_index=pk_index)` → `render_sample_chart(..., left_index=pk_index)`
- 注释明确 pk_index 在数据层仍是 consolidation anchor；sample_renderer 视角是"窗口左端"

### Task 2: 测试扩展

旧测试全部同步 API（`pk_index=` → `left_index=`），新增 4 个测试函数：

- `test_render_window_is_narrowed_to_left_to_bo_inclusive`：volume bar 数量断言（= bo_index - left_index + 1）
- `test_render_does_not_draw_pk_or_bo_axvline`：无 axvline（transform 区分法）+ 无 legend
- `test_render_does_not_pollute_global_rcparams_font_size`：font.size rcParams 不污染
- `test_render_applies_specific_fontsizes`：title=10、label=8、tick=7 artist 级断言

全部 8 测试 PASS（4 旧 + 4 新）。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 修复 has_vline 检测逻辑区分 K 线影线与 axvline**
- **Found during:** Task 2（test 失败调试）
- **Issue:** 计划中 `has_vline` 用 `xs[0] == xs[1]`（xdata 相等）检测垂直线，但 CandlestickComponent.draw 用 `Line2D([x, x], [low, high])` 绘制影线，格式与 axvline 相同，导致误判。
- **Fix:** 改用 `line.get_transform() == ax.get_xaxis_transform()` 区分 —— axvline 使用 BlendedGenericTransform（xaxis_transform），K 线影线使用 transData，两者不同。
- **Files modified:** test_sample_renderer.py（has_vline 函数内部）
- **Commit:** a9f1589

## Success Criteria Check

| Criterion | Result |
|-----------|--------|
| pytest 100% PASS（8/8） | PASS |
| grep axvline sample_renderer.py == 0 | 0 (OK) |
| grep 'Price (% from BO close)' == 1 | 1 (OK) |
| grep 'with mpl.rc_context' >= 1 | 1 (OK) |
| grep 'pk_index' sample_renderer.py == 0 | 0 (OK) |
| grep `df_window.iloc[bo_index]["close"]` 命中 | 命中 |
| grep 'left_index=pk_index' preprocess.py 命中（BLOCKER 1） | 命中 |
| test_render_applies_specific_fontsizes PASS（WARNING 6） | PASS |

## Known Stubs

无。所有功能完整实现，无 placeholder 或 hardcoded stub。

## Threat Flags

无新增外部 surface。sample_renderer 仅渲染本地 df_window，STRIDE 不适用。

## Self-Check: PASSED

- FOUND: sample_renderer.py
- FOUND: preprocess.py
- FOUND: test_sample_renderer.py
- FOUND: commit 5e5e9d9 (Task 1)
- FOUND: commit a9f1589 (Task 2)
- STATE.md / ROADMAP.md 未修改（0 diff lines）
