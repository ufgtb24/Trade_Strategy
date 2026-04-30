---
phase: 01-librarian-inducer-mvp
plan: "02"
subsystem: dev-ui-picker
tags: [canvas-manager, keyboard-picker, tdd, get-bo-indices, type-hint]
dependency_graph:
  requires: [01-01-KeyboardPicker-three-state-FSM]
  provides: [canvas-manager-get_bo_indices-wired, _wire_picker-4arg-type-hint]
  affects: [dev-UI-P-key-interaction]
tech_stack:
  added: []
  patterns: [closure-dependency-injection, forward-reference-type-hint]
key_files:
  created: []
  modified:
    - BreakoutStrategy/UI/charts/canvas_manager.py
    - BreakoutStrategy/UI/charts/tests/test_keyboard_picker.py
decisions:
  - "D-10 honored: _wire_picker 内部构造 get_bo_indices 闭包 frozenset(b.index for b in breakouts)，作为 KeyboardPicker 第二个 kwarg 注入"
  - "D-11 honored: _redraw_endpoint_markers 保持不变，AWAITING_LEFT 时画 [bo_idx]、IDLE 时画 [] 由 plan 01 FSM 已实现"
  - "WARNING 5 resolved: on_endpoints_picked 类型注解从 Callable[[int,int],None] 修正为 Callable[[int,int,'pd.DataFrame',list],None]，使用 forward reference 避免 import 循环"
  - "test_canvas_manager_picker_callback_passes_wired_df_not_full_df 恢复兼容：plan 02 实施后新测试直接调真实 _wire_picker"
metrics:
  duration_seconds: 129
  completed_date: "2026-04-29T08:24:38Z"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 2
---

# Phase 01 Plan 02: canvas_manager _wire_picker 接通新三态 FSM Summary

**One-liner:** 在 `_wire_picker` 中注入 `get_bo_indices` 闭包（`frozenset(b.index for b in breakouts)`）并修正 `on_endpoints_picked` 类型注解为 4-arg forward-reference 签名，17/17 单元测试全 PASS。

## What Was Built

`canvas_manager.py` 的 `_wire_picker` 方法完成两项修改：

1. **`get_bo_indices` 闭包注入（D-10）**: 新增内部函数 `get_bo_indices() -> frozenset`，从闭包捕获的 `breakouts` 列表（即 `update_chart` 传入的 `list[Breakout]`）读取 `.index` 字段构造 `frozenset[int]`，作为 `KeyboardPicker.__init__` 的第二个必须 kwarg 传入。`Breakout.index` 字段名与 `breakout_detector.py` 一致（不是 `.idx`）。

2. **类型注解修正（WARNING 5）**: `on_endpoints_picked` 的类型注解从旧的 2-arg `Callable[[int, int], None]` 修正为 4-arg `Callable[[int, int, 'pd.DataFrame', list], None]`，使用 forward reference（单引号字符串字面量）避免 runtime import 依赖；`list` 表示 `list[Breakout]` 而不强行 import 类型。

`test_keyboard_picker.py` 追加一个新集成回归用例：
- `test_wire_picker_injects_bo_indices_closure_from_breakouts`: 通过 mock ChartCanvasManager 实例调用真实 `_wire_picker`，断言 `cm._picker._get_bo_indices()` 返回 `frozenset({5, 10})`（基于 `breakouts=[bo1(index=5), bo2(index=10)]`）

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 RED | 添加失败测试 test_wire_picker_injects_bo_indices_closure_from_breakouts | 7a31271 | tests/test_keyboard_picker.py |
| 1 GREEN | _wire_picker 注入 get_bo_indices + 修正 on_endpoints_picked 类型注解 | b9037c7 | canvas_manager.py |

## Verification Results

```
17 passed in 0.44s
```

- `grep -c "get_bo_indices" canvas_manager.py` → 2（定义 + 传参，≥ 2 要求）
- `grep "frozenset(b.index"` → 命中（字段名正确为 .index 非 .idx）
- `grep "b\.idx[^_]" canvas_manager.py` → 空（无错误字段引用）
- `grep "Callable\[\[int, int, .pd.DataFrame., list\]"` → 命中（WARNING 5 acceptance）
- `python -c` 断言全部 PASS（inspect.getsource 验证）

## Deviations from Plan

无 — 计划执行完全按规格落地，无偏差。

## Known Stubs

无。

## Threat Flags

无。本 plan 仅修改 dev tool 集成层，无新增网络端点或外部 surface。

## Self-Check: PASSED

- canvas_manager.py 修改已 commit b9037c7: FOUND
- test_keyboard_picker.py 追加测试已 commit 7a31271: FOUND
- 17/17 pytest PASS: CONFIRMED
- get_bo_indices count ≥ 2: CONFIRMED
- b.idx 无误引用: CONFIRMED
- Callable 4-arg 类型注解存在: CONFIRMED
