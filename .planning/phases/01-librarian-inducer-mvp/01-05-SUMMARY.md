---
phase: 01-librarian-inducer-mvp
plan: 05
status: complete
type: execute
wave: 3
completed: 2026-04-29
requirements_addressed: [REQ-test-coverage, REQ-end-to-end-smoke]
---

# Plan 01-05 — Phase 1 Gap-Fix E2E Integration

## Summary

端到端集成验证 + 手工 dev UI UAT,确认 plan 01-01..01-04 落地后链路协同。
UAT 过程中发现 7 处 dev UI / chart.png UX gap,**全部就地修复**(commit 列表见下),
最终用户回 `approved`。

## Tasks

| # | Type | Status | Commit |
|---|------|--------|--------|
| 1 | auto (注释更新) | DONE | `c2f4dba` docs(01-05): update anchor dual-role comments |
| 2 | auto (全套测试) | DONE | `3dcda53` chore(01-05): full test suite 201 passed |
| 3 | checkpoint:human-verify | APPROVED (with 7 follow-on fixes) | see UAT fixes table |

## Auto-test report (Task 2)

```
uv run pytest \
  BreakoutStrategy/UI/charts/tests/ \
  BreakoutStrategy/feature_library/tests/ \
  BreakoutStrategy/dev/tests/
→ 201 passed in 6.61s
```

最终全套 (UI/charts + feature_library + dev/tests) 在 7 处 UX 修复后 **203/203 PASS**。

## UAT-driven Fixes (Task 3 follow-ons)

| # | Commit | Title | 触发场景 |
|---|--------|-------|---------|
| 1 | `0ad6716` | fix(picker): make sticky text visible inside price axes | 第一次 P 后 chart 顶端无任何 sticky 提示 → 定位 `subplots_adjust(top=0.99)` 把 `transAxes y=1.02` 文字裁到 figure 外。改为 `y=0.98 va="top"` + 白色半透明圆角 bbox |
| 2 | `b3dfccf` | fix(picker): show progress sticky + dual markers before sync render | 第二次 P 后 UI 卡顿无反馈,实际上已完成截图 → on_render 入口先画双 marker + sticky `Capturing screenshot...`,`canvas.draw()` + `flush_events()` 同步刷屏后再跑长任务 |
| 3 | `aacd7df` | feat(picker): show toast as chart overlay below sticky | 错点警告 (`This bar is not a detected BO...`) 只 print 到 terminal,用户盯 chart 看不到 → 扩展 `_show_picker_toast` 在 sticky 之下加 chart overlay,warning=红/info=蓝,2.5s Tk `after()` 自动消失;新增 `_cancel_picker_toast` helper,在 fig 重建处和 render 入口处 cancel 防 stale artist / 截图烘焙 |
| 4 | `00e7f38` | style(picker): enlarge sticky/toast font and tighten vertical spacing | sticky/toast 字号偏小、间距过宽 → sticky 13→18pt,toast 11→15pt,toast y=0.88→0.93 |
| 5 | `d90bbfe` | style(picker): match toast font size to sticky (18pt) | toast 字号继续与 sticky 对齐 |
| 6 | `0433ed6` | style(sample_renderer): unify font size to title (10pt), drop anonymized & Bar Index, tighten margins | chart.png 视觉脱敏:标题去 `(anonymized)` 后缀;全图字号统一到 title size (10pt) — 含 ylabel / tick / offset text / candlestick.py 注入文本;移除 volume xlabel `Bar Index`;`subplots_adjust(left=0.06, right=0.99, top=0.94, bottom=0.05)` 收紧四边到 ~5% |
| 7 | `3ea99ae` | style(sample_renderer): drop Interval annotation, add Bar Count label | candlestick.py 硬编码 `Interval: 1M(21)` 文字对 GLM-4V 是噪音 → 移除;volume 子图底部居中加 `Bar Count: N` 让模型直接读到样本窗口长度 |

### 修复涉及的源文件 / 测试

- `BreakoutStrategy/UI/charts/canvas_manager.py`(sticky/toast 渲染 + render 闭包 progress feedback)
- `BreakoutStrategy/feature_library/sample_renderer.py`(chart.png 标题/字号/Bar Count/margin)
- `BreakoutStrategy/feature_library/tests/test_sample_renderer.py`(替换 D-09 differential-fontsize 断言为 unified-fontsize + 新增 Interval-removed/Bar-Count 断言;7→10 用例)

## Key files

- `BreakoutStrategy/dev/tests/test_sample_picker_handler.py` (Task 1 anchor dual-role 注释更新;无逻辑改动)

## D-01..D-11 落地状态

| Decision | 状态 | 验证途径 |
|----------|------|---------|
| D-01 三态 FSM (IDLE / AWAITING_BO / AWAITING_LEFT) | ✓ | UAT 操作 + test_keyboard_picker.py 16 用例 |
| D-02 P1 必须 ∈ BO 集合 | ✓ | UAT 错点 toast + test |
| D-03 错点 stay+toast 不重置 | ✓ | UAT 多次错点 sticky 不变 + test |
| D-04 on_endpoints_picked 签名不变 | ✓ | sample_picker_handler 测试不动 |
| D-05 渲染窗口 [left, BO] 闭区间 | ✓ | test_render_window_is_narrowed_to_left_to_bo_inclusive |
| D-06 视觉去标注 (axvline / legend / anonymized) | ✓ | UAT chart.png + test_render_does_not_draw_pk_or_bo_axvline |
| D-07 Y 轴 BO close pivot | ✓ | UAT ylabel "Price (% from BO close)" + 0% at BO bar |
| D-08 prompt 文本通道同步切 BO close | ✓ | test_prompts.py / test_inducer_prompts.py 17/17 PASS |
| D-09 字号压缩 + rcParams 不污染 | ✓ → 改为 unified to title size (10pt) per UAT 反馈 |
| D-10 BO 集合注入 KeyboardPicker | ✓ | test_canvas_manager_wire_picker_passes_get_bo_indices |
| D-11 marker 重绘语义 | ✓ | UAT 进 AWAITING_LEFT 出现金线、回 IDLE 清空 |

## Self-Check

- [x] All Task 1 / Task 2 / Task 3 done
- [x] 全套测试 203/203 PASS (UI/charts + feature_library + dev/tests)
- [x] User UAT approved D-01..D-11 全部落地(含 7 处 follow-on fixes)
- [x] 无残留 gap;chart.png 视觉脱敏与 prompt 通道同步到 BO close pivot;dev UI 三态 FSM + 反馈链路完整

## Self-Check: PASSED
