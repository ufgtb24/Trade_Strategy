---
status: partial
phase: 01-librarian-inducer-mvp
source: [01-VERIFICATION.md]
started: 2026-04-29
updated: 2026-04-29
reconciled_with: 01-UAT.md
---

## Current Test

[Test #1 reconciled with 01-UAT.md;Test #2 awaiting `/gsd-secure-phase 1`]

## Tests

### 1. 真实 GLM-4V API 端到端 smoke
expected: `uv run python scripts/feature_mining_phase1.py` × AAPL × 5 样本端到端 exit 0,生成 5 个 sample 目录(chart.png + meta.yaml + nl_description.md)+ 1 个 F-*.yaml feature 条目。
follow_up_command: `/gsd-verify-work 1`
result: passed
reconciled_at: 2026-04-29
evidence: |
  实际验证发生在 01-UAT.md Test #1 通道(/gsd-verify-work 1 首轮)。
  - 首次运行暴露 Gap A(Inducer 把全部 candidate 误判为幻觉,id_map 键格式失配),
    修复 commit `4856dd1`(inducer.py supporting_id 归一化 + 2 条 regression test);
  - 自动选窗口偏窄(Gap B)采用 B1 方案,修复 commit `679c813`
    (`min_bars_before_bo=30` 写在 main() 顶部,kw-only 透传 _ensure_samples);
  - 修复后重跑:5 个 AAPL sample 三件套生成,F-001 入库,
    α=5.50 β=0.50 P5=0.694 obs=5 strong,exit 0。
  详见 01-UAT.md `## Tests > ### 1` 与 `## Gaps > Gap A/B`。

### 2. REQ-invariant 三道硬防线 code review
expected: code review 验证 `REQ-invariant-blind-inducer` (Phase 1 entry script 不向 Inducer 注入 library 内容) 与 `REQ-invariant-cli-no-feature-content` (CLI 输出不暴露 library feature 文本) 在实现中确实落地。
follow_up_command: `/gsd-secure-phase 1`
result: pending
deferred_in_context: true (CONTEXT.md `<deferred>` 节明确)

## Summary

total: 2
passed: 1
issues: 0
pending: 1
skipped: 0
blocked: 0

**Note:** Test #1 在 01-UAT.md 通道实际跑通后,本文件被回写为 reconciled。
Test #2 仍走 `/gsd-secure-phase 1` follow-up。

## Gaps

[none — Gap A/B 已在 01-UAT.md 关闭]
