---
status: complete
phase: 01-librarian-inducer-mvp
source:
  - 01-01-SUMMARY.md
  - 01-02-SUMMARY.md
  - 01-03-SUMMARY.md
  - 01-04-SUMMARY.md
  - 01-05-SUMMARY.md
started: 2026-04-29
updated: 2026-04-29
---

## Current Test

[all tests resolved]

## Tests

### 1. End-to-end GLM-4V smoke (Phase 1 entry script)
expected: |
  运行 `uv run python scripts/feature_mining_phase1.py`,5 个 sample 目录 + ≥1 条 F-*.yaml,exit 0,无异常。
  chart.png 视觉脱敏(窗口收窄 / 无 axvline / BO close pivot / Bar Count / 字号 10pt 统一 / 标题不带 anonymized)。
result: passed (after Gap A fix)
notes: |
  首次运行暴露 Gap A:Inducer 把所有 candidate 误判为幻觉(`hallucinated=[1, 2, 3, 4, 5]`,
  根因 id_map 键 "[N]" 字符串 vs GLM YAML 输出的裸整数失配)。
  修复 commit `4856dd1` 后重跑成功:1 candidate K=5/N=5
  "随着盘整期的延长，价格波动幅度逐渐减小，最终出现突破" 被 Librarian 强化入 F-001,
  α=5.50 β=0.50 P5=0.694 obs=5 strong;exit 0。

## Summary

total: 1
passed: 1
issues: 0 (Gap A 已修;Gap B 待决策)
pending: 0
skipped: 0
blocked: 0

## Gaps

### Gap A — Inducer 把候选误判为幻觉(已修)

severity: high
status: resolved
fix_commit: 4856dd1
fix_summary: |
  inducer.py 翻译循环归一化 supporting_id 到 "[N]" 键格式后再查 id_map:
  裸 int → "[N]";数字字符串 → "[N]";带括号字符串 → 不变;bool 提前守卫。
  新增 2 条 regression test (bare-int / digit-string),15/15 PASS。

### Gap B — 自动选择的窗口偏窄(已修)

severity: low
status: resolved
fix_commit: 679c813
fix_summary: |
  采用 B1。澄清 scripts/feature_mining_phase1.py 是批量自动化烟测入口
  (正式 feature mining 走 dev UI 由用户按 P 灵活挑选)。
  在 main() 参数声明区新增 `min_bars_before_bo: int = 30`(CLAUDE.md 无 argparse 规则),
  _ensure_samples 加 kw-only 参数透传,pk_index = min(pk_index, max(0, bo_index - min_bars_before_bo))。
  模块 docstring 更新说明脚本定位 vs dev UI 流程。
note: |
  本轮 5 个 AAPL samples 已用旧窄窗口生成(BO_AAPL_2021061[7-30]);
  脚本会跳过已存在的 sample,因此需手动 `rm -rf feature_library/samples/BO_AAPL_2021*`
  重新触发 preprocess 才能看到新的 ≥30 根窗口效果。否则当前 chart.png 保持 7 根。
