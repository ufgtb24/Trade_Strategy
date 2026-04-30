---
phase: 01-librarian-inducer-mvp
plan: "01"
subsystem: dev-ui-picker
tags: [fsm, keyboard-picker, unit-tests, tdd]
dependency_graph:
  requires: []
  provides: [KeyboardPicker-three-state-FSM, get_bo_indices-injection-hook]
  affects: [canvas_manager._wire_picker]
tech_stack:
  added: []
  patterns: [dependency-injection, strategy-pattern, frozenset-membership-check]
key_files:
  created: []
  modified:
    - BreakoutStrategy/UI/charts/keyboard_picker.py
    - BreakoutStrategy/UI/charts/tests/test_keyboard_picker.py
decisions:
  - "D-01 honored: IDLE 按 P 无条件进入 AWAITING_BO，不依赖 hover bar 存在"
  - "D-02 honored: 新增 get_bo_indices: Callable[[], frozenset] 注入钩子，AWAITING_BO 校验 bar 成员资格"
  - "D-03 honored: 错点统一 stay + toast，不重置不前进"
  - "D-04 honored: on_render(left_idx, right_idx) 签名不变，天然保证 right_idx == bo_idx"
  - "D-11 honored: IDLE 分支含 # marker 已为空 注释，依赖 _reset_silent 不变量"
  - "plan-02-compatibility: test_canvas_manager_picker_callback_passes_wired_df_not_full_df 暂绕过 _wire_picker（plan 02 后恢复完整集成测试）"
metrics:
  duration_seconds: 273
  completed_date: "2026-04-29T08:16:44Z"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 2
---

# Phase 01 Plan 01: KeyboardPicker 三态 FSM 重写 Summary

**One-liner:** 将 KeyboardPicker 由两态（IDLE/PICKING_1）重写为三态 FSM（IDLE/AWAITING_BO/AWAITING_LEFT），新增 get_bo_indices 注入钩子强制第一次 P 必须落在 detected BO 集合内，16/16 单元测试全 PASS。

## What Was Built

`keyboard_picker.py` 完全重写为三态状态机：

- **IDLE**: 无 sticky 提示；按 P 无条件进入 AWAITING_BO（D-01，不依赖 hover）
- **AWAITING_BO**: 按 P 校验 hover bar ∈ get_bo_indices()；合法则进入 AWAITING_LEFT 并画 marker；非法则 toast warning 保持当前态
- **AWAITING_LEFT**: 按 P 校验 hover idx < bo_idx；合法则触发 on_render(left, bo_idx) 并回 IDLE；非法（>=bo_idx 或同根）则 toast 保持当前态

`test_keyboard_picker.py` 完全重写，16 个用例覆盖所有迁移路径。

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | 重写 KeyboardPicker 为三态 FSM | 4cf7e3f | keyboard_picker.py |
| 2 | 重写 test_keyboard_picker.py | 8dd2a1a | tests/test_keyboard_picker.py |

## Verification Results

```
16 passed in 0.44s
```

- `grep -c "PICKING_1" keyboard_picker.py` → 0（旧枚举完全移除）
- `grep -c "PICKING_1" test_keyboard_picker.py` → 0
- `grep -c "get_bo_indices" keyboard_picker.py` → 5（≥ 2 要求）
- `grep -c "AWAITING_BO|AWAITING_LEFT" keyboard_picker.py` → 27（≥ 6 要求）
- `grep -c "AWAITING_BO|AWAITING_LEFT" test_keyboard_picker.py` → 42（≥ 6 要求）
- D-11 注释 `# marker 已为空` 存在于 IDLE 分支

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Compatibility] test_canvas_manager_picker_callback_passes_wired_df_not_full_df 适配**
- **Found during:** Task 2 运行测试时
- **Issue:** 该集成回归测试调用真实 `_wire_picker`，而 `_wire_picker` 当前仍为 5 钩子签名，不含新增的 `get_bo_indices`，导致 `KeyboardPicker.__init__()` missing required argument
- **Fix:** 按计划 Task 2 第 5 条指引，暂改为绕过 `_wire_picker` 直接构造 KeyboardPicker 验证 on_render 闭包语义，添加注释说明 plan 02 后恢复完整集成测试
- **Files modified:** `tests/test_keyboard_picker.py`
- **Commit:** 8dd2a1a（含 fix）

## Known Stubs

无。所有实现均完整落地，无 hardcoded 空值或 placeholder。

## Threat Flags

无。本 plan 仅修改 dev tool FSM 与单元测试，无新增网络端点或外部 surface。

## Self-Check: PASSED

- keyboard_picker.py 存在并含三态枚举: FOUND
- tests/test_keyboard_picker.py 存在并含所有新用例: FOUND
- Task 1 commit 4cf7e3f 存在: FOUND
- Task 2 commit 8dd2a1a 存在: FOUND
- 16/16 pytest PASS: CONFIRMED
