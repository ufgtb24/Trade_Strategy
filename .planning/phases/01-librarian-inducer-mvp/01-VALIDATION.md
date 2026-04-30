---
phase: 1
slug: librarian-inducer-mvp
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-29
---

# Phase 1 — Validation Strategy

> Per-phase validation contract reconstructed from completed plan SUMMARY artifacts (State B).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest（uv 管理） |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest BreakoutStrategy/UI/charts/tests/test_keyboard_picker.py BreakoutStrategy/feature_library/tests/test_sample_renderer.py BreakoutStrategy/feature_library/tests/test_prompts.py BreakoutStrategy/feature_library/tests/test_inducer_prompts.py -q` |
| **Full suite command** | `uv run pytest BreakoutStrategy/UI/charts/tests/ BreakoutStrategy/feature_library/tests/ BreakoutStrategy/dev/tests/ -q` |
| **Estimated runtime** | ~7 秒（实测 6.36s, 205 passed） |

---

## Sampling Rate

- **After every task commit:** 跑该 plan 的 quick run（受影响的单文件 / 单子目录测试）
- **After every plan wave:** 跑 `Full suite command`
- **Before `/gsd-verify-work`:** Full suite 全绿
- **Max feedback latency:** ≤ 10 秒

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | KeyboardPicker 三态 FSM (D-01/02/03/04/11) | — | N/A（本机 dev tool，无外部 surface） | unit | `uv run pytest BreakoutStrategy/UI/charts/tests/test_keyboard_picker.py -q` | ✅ | ✅ green (16 cases) |
| 1-01-02 | 01 | 1 | test_keyboard_picker.py 三态用例覆盖 | — | N/A | unit | 同上 | ✅ | ✅ green |
| 1-02-01 | 02 | 2 | _wire_picker 注入 get_bo_indices 闭包 + Callable 4-arg type-hint (D-10) | — | N/A | unit/integration | `uv run pytest BreakoutStrategy/UI/charts/tests/test_keyboard_picker.py::test_wire_picker_injects_bo_indices_closure_from_breakouts -q` | ✅ | ✅ green |
| 1-02-02 | 02 | 2 | canvas_manager.py 集成回归 | — | N/A | integration | `uv run pytest BreakoutStrategy/UI/charts/tests/ -q` | ✅ | ✅ green (17 cases) |
| 1-03-01 | 03 | 2 | sample_renderer 渲染窗口 [left,BO] + Y轴 BO close pivot + 视觉脱敏 (D-05/06/07/09) + preprocess.py kwarg | — | N/A | unit | `uv run pytest BreakoutStrategy/feature_library/tests/test_sample_renderer.py -q` | ✅ | ✅ green (10 cases，含 UAT 后扩展) |
| 1-03-02 | 03 | 2 | sample_renderer artist 级断言（fontsize / axvline / rcParams 不污染） | — | N/A | unit | 同上 | ✅ | ✅ green |
| 1-04-01 | 04 | 2 | prompts.build_user_message OHLC pivot → BO close (D-08) | — | N/A（脱敏方案 B：bo_close 缺失/非正降级 N/A，不泄漏绝对价） | unit | `uv run pytest BreakoutStrategy/feature_library/tests/test_prompts.py -q` | ✅ | ✅ green |
| 1-04-02 | 04 | 2 | inducer_prompts.build_batch_user_message OHLC pivot → BO close (D-08) | — | N/A（同上） | unit | `uv run pytest BreakoutStrategy/feature_library/tests/test_inducer_prompts.py -q` | ✅ | ✅ green |
| 1-05-01 | 05 | 3 | 注释更新：anchor dual-role | — | N/A | docs/comment | `uv run pytest BreakoutStrategy/dev/tests/ -q` | ✅ | ✅ green |
| 1-05-02 | 05 | 3 | 全套测试集成回归 (REQ-test-coverage / REQ-end-to-end-smoke) | — | N/A | suite | `uv run pytest BreakoutStrategy/UI/charts/tests/ BreakoutStrategy/feature_library/tests/ BreakoutStrategy/dev/tests/ -q` | ✅ | ✅ green (205/205) |
| 1-05-03 | 05 | 3 | 人工 dev UI UAT（D-01..D-11 端到端确认 + 7 处 UX follow-on fixes） | — | N/A | manual UAT | 见下方 Manual-Only 段 | ✅ APPROVED | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements — pyproject.toml + pytest 已在仓库内长期就绪，本 phase 全部测试均落在已存在的 tests/ 目录内，无 Wave 0 安装/脚手架任务。

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| dev UI Tk 三态 picker 端到端交互（IDLE → AWAITING_BO → AWAITING_LEFT → IDLE） + sticky/toast 视觉反馈 + chart.png 截图视觉脱敏 | D-01..D-11 综合落地 | Tk GUI 用户输入 + matplotlib 视觉 artifact 仅人眼可判定（字号 / margin / 标题文案 / 双 marker / sticky 位置 / toast 自动消失） | 1. `uv run python -m BreakoutStrategy.dev.<entry>` 启动 dev UI；2. hover 到 detected BO bar，按 P → 应见 sticky 提示 + 金色 marker；3. hover 任意 left bar（idx<bo_idx），按 P → 触发渲染 + 完整 chart.png；4. 错点（非 BO bar）→ 红色 toast + sticky 不变；5. 渲染前应见 `Capturing screenshot...` 进度提示；6. chart.png 应无 axvline / 无 legend / 无 `(anonymized)` 后缀 / 含 `Bar Count: N` 标签 / Y 轴标签 `Price (% from BO close)` 且 BO bar 处 ≈0%。已于 2026-04-29 由用户确认 `approved`（plan 05 commit `3ea99ae` 收尾）。 |

*GLM-4V 端到端 smoke（YAML loop）：plan 05 的 UAT 已涵盖端到端调用通路；如需重跑，运行 dev UI 的端到端 batch_induce 入口并目检 induced YAML（已由历史 commit `4856dd1` 与 `200ce44` 关闭 Gap A/B）。*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references（无 Wave 0 缺口）
- [x] No watch-mode flags
- [x] Feedback latency < 10s（实测 6.36s）
- [x] `nyquist_compliant: true` set in frontmatter

## Validation Audit 2026-04-29

| Metric | Count |
|--------|-------|
| Tasks audited | 11 (5 plans × 1–3 tasks) |
| COVERED | 11 |
| PARTIAL | 0 |
| MISSING | 0 |
| Manual-only escalated | 1（dev UI Tk + chart.png 视觉脱敏，UAT 已 approved） |
| Auditor agent spawned | No — `nyquist_compliant: true`，按工作流跳过 Step 5 |
| Full suite result | 205 passed in 6.36s |

**Approval:** approved 2026-04-29
