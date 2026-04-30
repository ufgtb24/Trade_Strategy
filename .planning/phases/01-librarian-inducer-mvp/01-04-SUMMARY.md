---
phase: 01-librarian-inducer-mvp
plan: "04"
subsystem: prompt-engineering
tags: [glm-4v, prompt, normalization, bo-close, pivot, tdd]

# Dependency graph
requires:
  - phase: 01-librarian-inducer-mvp
    provides: "prompts.py / inducer_prompts.py 归一化方案 B（D-08 前）"
provides:
  - "prompts.py::build_user_message OHLC pivot 切换到 BO close（D-08）"
  - "inducer_prompts.py::build_batch_user_message OHLC pivot 切换到 BO close，标签改为 vs bo_close（D-08）"
  - "两组新增 TDD 测试（RED+GREEN）验证 BO close 锚点计算与降级行为"
affects:
  - "feature_library prompt 构造链"
  - "GLM-4V 跨通道一致性（图像 Y 轴与文本通道共用 BO close 零点）"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "BO close 锚点：close 行显式输出 +0.00%，其余 OHLC 字段以 (price - bo_close) / bo_close * 100 计算"
    - "bo_close 缺失/非正时降级为 N/A 文本，不泄漏绝对价（归一化方案 B 脱敏约束延续）"
    - "TDD 流：先写 RED 测试 commit，再写 GREEN 实现 commit，各任务独立 commit"

key-files:
  created: []
  modified:
    - "BreakoutStrategy/feature_library/prompts.py"
    - "BreakoutStrategy/feature_library/inducer_prompts.py"
    - "BreakoutStrategy/feature_library/tests/test_prompts.py"
    - "BreakoutStrategy/feature_library/tests/test_inducer_prompts.py"

key-decisions:
  - "D-08: OHLC pivot 由 consolidation.pivot_close 切换到 bo['close']，使图像通道（chart.png Y 轴）与文本通道共用同一个零点"
  - "close 行恒输出 +0.00%（BO close 相对自身 = 0%），明确语义"
  - "consolidation 5 个无量纲字段保持不变，pivot 切换仅影响 breakout_day OHLC 段"

patterns-established:
  - "BO close pivot 模式：bo_close = bo.get('close')；close 恒为 +0.00%；异常时降级 N/A"
  - "TDD RED→GREEN per task，各阶段独立 commit（test/feat 类型）"

requirements-completed: [REQ-inducer-prompt-protocol, REQ-inducer-batch-induce]

# Metrics
duration: 15min
completed: 2026-04-29
---

# Phase 01 Plan 04: Prompt OHLC Pivot 切换到 BO close (D-08) Summary

**双通道 OHLC pivot 对齐：prompts.py 与 inducer_prompts.py 从 consolidation.pivot_close 切换到 bo['close']（close=+0.00%），消除 GLM-4V 图文两套不一致零点**

## Performance

- **Duration:** 约 15 min
- **Started:** 2026-04-29T00:00:00Z
- **Completed:** 2026-04-29
- **Tasks:** 2（各含 RED+GREEN 两次 commit）
- **Files modified:** 4

## Accomplishments

- `build_user_message`（prompts.py）：OHLC 计算公式改用 bo_close 作锚点，close 行恒输出 `+0.00%`，文案由"相对盘整起点 close"更新为"相对突破日 close"
- `build_batch_user_message`（inducer_prompts.py）：同步切换 OHLC pivot，标签由 `vs pk_close` 改为 `vs bo_close`，close 行恒 `+0.00%`
- 两个文件：bo_close 缺失/非正（如 close=0）时均降级为 N/A，不泄漏绝对价（归一化方案 B 脱敏约束延续）
- 新增 4 个 TDD 测试（每文件 2 个）；所有 17 个测试 PASS（原 13 个全部保留）

## Task Commits

每个任务按 TDD RED→GREEN 独立 commit：

1. **Task 1 RED: prompts.py 新增失败测试** - `cee6e0a` (test)
2. **Task 1 GREEN: prompts.py 切换 OHLC pivot 到 BO close** - `11fed5e` (feat)
3. **Task 2 RED: inducer_prompts.py 新增失败测试** - `5a4703e` (test)
4. **Task 2 GREEN: inducer_prompts.py 切换 batch OHLC pivot 到 BO close** - `d52001b` (feat)

## Files Created/Modified

- `BreakoutStrategy/feature_library/prompts.py` - build_user_message：bo_close 为锚点，close=+0.00%，降级行为更新
- `BreakoutStrategy/feature_library/inducer_prompts.py` - build_batch_user_message：vs bo_close 标签，close=+0.00%，降级行为更新
- `BreakoutStrategy/feature_library/tests/test_prompts.py` - 新增 test_build_user_message_uses_bo_close_as_pivot + test_build_user_message_handles_missing_bo_close_gracefully
- `BreakoutStrategy/feature_library/tests/test_inducer_prompts.py` - 新增 test_build_batch_user_message_uses_bo_close_as_pivot + test_build_batch_user_message_handles_missing_bo_close_gracefully

## Decisions Made

- D-08（来自 01-CONTEXT.md）：图像通道（chart.png Y 轴 BO close pivot，plan 03 已实现）与文本通道共用同一零点，GLM-4V cross-attention 时不再撕扯两套不同相对参考系
- `consolidation.pivot_close` 字段保留不动（仍是 meta.yaml 的 consolidation anchor 数据）；本 plan 仅改 prompt 中 OHLC 相对参考

## Deviations from Plan

无偏差——计划执行完全按预期。

## Issues Encountered

无。现有脱敏断言（无 ticker / 无 bo_date / 无绝对价位）在新逻辑下全部继续 PASS。

## Known Stubs

无 — 本 plan 全量实现 D-08 pivot 切换，无占位符。

## Threat Flags

无新增外部 surface — OHLC pivot 计算为纯本地字符串拼接，输入 meta dict 来自本地 yaml，非 untrusted。

## User Setup Required

无 — 无外部服务配置需求。

## Next Phase Readiness

- 文本通道与图像通道的零点已统一（BO close = 0%），GLM-4V 双通道输入一致性达成
- 可进入后续 plan（picker 状态机 / sample_renderer 渲染窗口等）

---
*Phase: 01-librarian-inducer-mvp*
*Completed: 2026-04-29*
