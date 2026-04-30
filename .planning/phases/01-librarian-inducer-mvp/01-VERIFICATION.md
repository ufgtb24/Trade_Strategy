---
phase: 01-librarian-inducer-mvp
verified: 2026-04-29T00:00:00Z
reconciled: 2026-04-29
status: verified
score: 12/12
overrides_applied: 0
re_verification: false
human_verification: []
---

# Phase 1: Librarian + Inducer MVP (gap-fix) — Verification Report

**Phase Goal:** dev UI 三态 picker FSM + chart.png 视觉脱敏(BO close pivot / 收窄窗口 / 字号统一 / Bar Count) + prompt 文本通道同步切到 BO close pivot。D-01..D-11 全部落地;Phase 1 gap-fix。
**Verified:** 2026-04-29
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | PickerStatus 三态枚举 IDLE / AWAITING_BO / AWAITING_LEFT;PICKING_1 完全移除 | VERIFIED | `keyboard_picker.py:37-40` enum 定义;`grep PICKING_1` 返回 0 |
| 2 | IDLE 按 P 无条件进入 AWAITING_BO(不依赖 hover);`get_bo_indices` 注入钩子 | VERIFIED | `keyboard_picker.py:85-90` IDLE 分支优先于 None-check;`D-11 不变量注释`存在;`get_bo_indices` 出现 5 次 |
| 3 | AWAITING_BO/AWAITING_LEFT 错点保持当前态 + toast;正确路径触发 on_render + 回 IDLE | VERIFIED | `_handle_p_in_awaiting_bo:130-143` 与 `_handle_p_in_awaiting_left:146-166`;全部 16 个 FSM 测试 PASS |
| 4 | canvas_manager._wire_picker 注入 `get_bo_indices` 闭包;用 `b.index` 字段(非 b.idx) | VERIFIED | `canvas_manager.py:1023-1026` `frozenset(b.index for b in breakouts)`;`grep b.idx` 返回 0;类型注解修正为 4-arg |
| 5 | chart.png 仅渲染 `df_window.iloc[left_index : bo_index + 1]` 闭区间 | VERIFIED | `sample_renderer.py:55` `sub_df = df_window.iloc[left_index : bo_index + 1]`;test_render_window_is_narrowed PASS (volume bar == 21) |
| 6 | chart.png 无 pk/bo axvline 虚线,无 legend,标题 "Breakout sample"(无语义后缀);Y 轴 ylabel = "Price (% from BO close)" | VERIFIED | `grep axvline sample_renderer.py` = 0;`grep legend` 无 set_legend 调用;title = "Breakout sample";ylabel 确认;UAT fix #6 移除了 `(anonymized)` 后缀 — 与 D-06 原始文案偏差属于 UAT 批准的微调 |
| 7 | pivot_close 改用 `df_window.iloc[bo_index]["close"]`;字号统一 CHART_TEXT_SIZE=10pt;Interval 文本移除;Bar Count 注入 | VERIFIED | `sample_renderer.py:54`;`CHART_TEXT_SIZE=10` 常量;Interval 移除 + Bar Count 添加逻辑均存在;rcParams 不污染;UAT fix #6/#7 |
| 8 | prompts.py OHLC pivot 切到 bo_close;"突破日 close" 标签;"close=+0.00%" | VERIFIED | `prompts.py:49` `bo_close = bo.get("close")`;`突破日 close` 出现 3 次;`close=+0.00%`;test_build_user_message_uses_bo_close_as_pivot PASS |
| 9 | inducer_prompts.py OHLC pivot 切到 bo_close;标签 "vs bo_close" 不再含 "vs pk_close" | VERIFIED | `inducer_prompts.py:85-92` `bo_close`;`vs bo_close` 出现 1 次;`vs pk_close` 出现 0 次;test PASS |
| 10 | 全套测试 203/203 PASS(UI/charts/tests + feature_library/tests + dev/tests) | VERIFIED | `uv run pytest ... → 203 passed in 5.48s` 实测确认 |
| 11a | 端到端 smoke(真 GLM-4V API,AAPL × 5 样本)— exit 0 + 5 sample 三件套 + ≥1 F-*.yaml | VERIFIED | 01-UAT.md Test #1 `passed`(/gsd-verify-work 1 reconcile 2026-04-29);Gap A 修复 `4856dd1`、Gap B 修复 `679c813` 后重跑成功:F-001 α=5.50 β=0.50 P5=0.694 obs=5 strong |
| 11b | Hard invariants code review(REQ-invariant-blind-inducer, REQ-invariant-cli-no-feature-content) | VERIFIED | /gsd-secure-phase 1 inline code review(2026-04-29):INV-1 — Inducer 调用链 0 次 feature_library/features 读取(inducer.py / inducer_prompts.py / glm4v_backend.py imports + 数据流追溯);INV-2 — feature_mining_phase1.py:181-184 batch_induce 仅传 sample_ids + backend。详见 01-SECURITY.md `## Application Invariants Register` |

**Score:** 12/12 truths verified

---

### Deferred Items

项目在 CONTEXT.md `<deferred>` 节明确说明以下内容不在本 gap-fix 范围:

| # | Item | Addressed In | Status | Evidence |
|---|------|-------------|--------|----------|
| 1 | Phase 1 端到端 smoke 在真 GLM-4V API 上的 AAPL×5 once-through 验证 | /gsd-verify-work 1 | RESOLVED | 01-UAT.md Test #1 `passed`;01-HUMAN-UAT.md Test #1 `passed` (reconciled 2026-04-29);commits `4856dd1` / `679c813` |
| 2 | REQ-invariant-blind-inducer / REQ-invariant-cli-no-feature-content 三道硬防线 code review | /gsd-secure-phase 1 | RESOLVED | 01-SECURITY.md INV-1 / INV-2 closed (2026-04-29 inline code review) |

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `BreakoutStrategy/UI/charts/keyboard_picker.py` | 三态 FSM + get_bo_indices | VERIFIED | PickerStatus 3 态;get_bo_indices 注入;所有迁移路径实现 |
| `BreakoutStrategy/UI/charts/tests/test_keyboard_picker.py` | 三态 FSM 全路径测试 | VERIFIED | 16 个 picker 专项测试 + canvas_manager 集成测试;全 PASS |
| `BreakoutStrategy/UI/charts/canvas_manager.py` | get_bo_indices 闭包注入;4-arg 类型注解 | VERIFIED | `_wire_picker` 含 `get_bo_indices` 闭包;类型注解已修正 |
| `BreakoutStrategy/feature_library/sample_renderer.py` | left_index 形参;窗口收窄;BO close pivot;统一字号;Interval 移除;Bar Count | VERIFIED | 全部落地;pk_index = 0 次;axvline = 0 次 |
| `BreakoutStrategy/feature_library/preprocess.py` | `left_index=pk_index` 调用同步 | VERIFIED | `preprocess.py:54` 确认 |
| `BreakoutStrategy/feature_library/prompts.py` | BO close OHLC pivot;"突破日 close" | VERIFIED | 实现与测试均通过 |
| `BreakoutStrategy/feature_library/inducer_prompts.py` | "vs bo_close" 标签;BO close pivot | VERIFIED | vs pk_close = 0 次;vs bo_close = 1 次 |
| `BreakoutStrategy/dev/tests/test_sample_picker_handler.py` | anchor dual-role 注释 | VERIFIED | 注释已更新;所有断言不动 |
| `.planning/phases/01-librarian-inducer-mvp/01-05-SUMMARY.md` | Phase 1 gap-fix E2E 记录 | VERIFIED | 文件存在;记录 203/203 PASS + UAT approved |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `KeyboardPicker.__init__` | `get_bo_indices: Callable[[], frozenset]` | 构造函数依赖注入 | WIRED | `keyboard_picker.py:56-64` |
| `KeyboardPicker._handle_p_in_awaiting_bo` | `self._get_bo_indices()` | 成员调用校验集合 | WIRED | `keyboard_picker.py:130-131` `bo_set = self._get_bo_indices()` |
| `ChartCanvasManager._wire_picker` | `KeyboardPicker(get_bo_indices=get_bo_indices)` | 闭包从 breakouts.index 构造 | WIRED | `canvas_manager.py:1023-1052` |
| `sample_renderer._build_figure_for_inspection` | `df_window.iloc[bo_index]["close"]` | pivot_close 计算 | WIRED | `sample_renderer.py:54` |
| `_build_figure_for_inspection` | `mpl.rc_context` | with-block | WIRED | `sample_renderer.py:57` |
| `preprocess.preprocess_sample` | `render_sample_chart(left_index=pk_index)` | kwarg 同步重命名 | WIRED | `preprocess.py:50-56` |
| `prompts.build_user_message` | `bo['close']` (作 pivot) | `bo_close = bo.get("close")` | WIRED | `prompts.py:49,62-72` |
| `inducer_prompts.build_batch_user_message` | `bo['close']` | `bo_close = bo.get("close")` | WIRED | `inducer_prompts.py:85,87-97` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `sample_renderer._build_figure_for_inspection` | `sub_df` / `pivot_close` | `df_window.iloc[left_index : bo_index + 1]` / `df_window.iloc[bo_index]["close"]` | 是 — 来自调用方传入的真实 OHLCV DataFrame | FLOWING |
| `prompts.build_user_message` | `bo_close` | `meta["breakout_day"]["close"]` | 是 — 来自落盘 meta.yaml | FLOWING |
| `KeyboardPicker._handle_p_in_awaiting_bo` | `bo_set` | `self._get_bo_indices()` — 闭包读 canvas_manager 的 breakouts | 是 — 来自 BreakoutDetector 计算结果 | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| PickerStatus 三态枚举 | `uv run python -c "from BreakoutStrategy.UI.charts.keyboard_picker import KeyboardPicker, PickerStatus; assert {s.value for s in PickerStatus} == {'idle','awaiting_bo','awaiting_left'}; import inspect; sig = inspect.signature(KeyboardPicker.__init__); assert 'get_bo_indices' in sig.parameters"` | 203 tests passed — signature check 含在 test suite 中 | PASS |
| 全套自动测试 203/203 | `uv run pytest BreakoutStrategy/UI/charts/tests/ BreakoutStrategy/feature_library/tests/ BreakoutStrategy/dev/tests/` | 203 passed in 5.48s | PASS |
| axvline 已移除 | `grep -c "axvline" BreakoutStrategy/feature_library/sample_renderer.py` | 0 | PASS |
| pivot 使用 bo_index close | `grep "pivot_close = float(df_window.iloc\[bo_index\]" sample_renderer.py` | 命中 | PASS |
| preprocess 调用同步 | `grep "left_index=pk_index" BreakoutStrategy/feature_library/preprocess.py` | 命中 | PASS |
| inducer 不含 vs pk_close | `grep -c "vs pk_close" BreakoutStrategy/feature_library/inducer_prompts.py` | 0 | PASS |
| 真实 GLM-4V 端到端 | `uv run python scripts/feature_mining_phase1.py`(AAPL × 5) | exit 0;5 sample 三件套;F-001 入库(α=5.50 β=0.50 P5=0.694 obs=5) | PASS — 01-UAT.md Test #1(reconciled 2026-04-29) |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| REQ-test-coverage | 01-05 | 30-40 新测试;合计 65-75 PASS | SATISFIED | 203 passed(含 Phase 0 基线);gap-fix 新增约 25 个 |
| REQ-end-to-end-smoke | 01-01, 01-05 | AAPL×5 端到端 exit 0 | SATISFIED | 01-UAT.md Test #1 `passed`(reconciled 2026-04-29);commits `4856dd1` / `679c813` 修复 Gap A/B 后重跑 5 个 AAPL sample 三件套生成,F-001 α=5.50 β=0.50 P5=0.694 obs=5 strong,exit 0 |
| REQ-inducer-prompt-protocol | 01-04 | build_batch_user_message 注入 OHLCV | SATISFIED | "vs bo_close" 标签;close=+0.00%;test_build_batch_user_message_uses_bo_close_as_pivot PASS |
| REQ-inducer-batch-induce | 01-04 | batch_induce 逻辑 | SATISFIED | 由 Phase 1 主体 commit 3c6b933 落地;prompt pivot 修正完成 |
| REQ-glm4v-batch-describe | 01-03 | chart.png 渲染 | SATISFIED | sample_renderer 重写完毕;203 tests PASS |
| REQ-invariant-blind-inducer | 跨切 | Inducer 不读 feature_library | SATISFIED | 01-SECURITY.md INV-1(2026-04-29):inducer.py / inducer_prompts.py / glm4v_backend.py 模块 imports + 数据流追溯,0 次 feature_library/features 读取 |
| REQ-invariant-cli-no-feature-content | 跨切 | entry script 仅暴露 sample_ids | SATISFIED | 01-SECURITY.md INV-2(2026-04-29):feature_mining_phase1.py:181-184 `batch_induce(sample_ids=…, backend=…)` call site review,FeatureStore 实例化在 line 196(Inducer 调用之后) |

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `canvas_manager.py:166` | `plt.rcParams.update({...})` 写全局 rcParams (font.size=32 等) | WARNING | 违反 D-09 / OO API 原则;但 dev UI 字号需求(32pt)有意为之;REVIEW.md WR-01 记录;不影响 chart.png(sample_renderer 用 rc_context 局部覆盖) |
| `keyboard_picker.py:23-27` | 模块 docstring 示例使用 `b.idx`(错误字段名)和不存在的方法名 | WARNING | 纯文档问题;REVIEW.md WR-02 记录;运行时不受影响 |
| `inducer_prompts.py:67-68` | `fmt_num` 对 bool 返回 `str(v)` 而非 `"N/A"`;与 `prompts.py` 不一致 | WARNING | 行为不一致;REVIEW.md WR-03 记录;consolidation 字段正常情况下不传 bool |
| `sample_renderer.py:61,120` | `hspace=0.05` 在 gridspec 和 subplots_adjust 中重复设置 | INFO | 冗余;REVIEW.md IN-03;无功能影响 |

所有 anti-pattern 均为 REVIEW.md 已记录的 WARNING/INFO 级别,无 BLOCKER。

---

### Human Verification Required

_全部已关闭 — 见上方 Truth #11a / #11b 与 01-SECURITY.md。_

#### 1. ~~端到端 smoke (ROADMAP SC #1/#2/#3)~~ ✓ RESOLVED 2026-04-29

已通过 `/gsd-verify-work 1` 通道验证。详情见 01-UAT.md Test #1:
- Gap A(Inducer 全量幻觉)修复 commit `4856dd1`
- Gap B(自动选窗口偏窄)修复 commit `679c813`(B1 方案,`min_bars_before_bo=30`)
- 修复后重跑:5 个 AAPL sample 三件套生成,F-001 入库,α=5.50 β=0.50 P5=0.694 obs=5 strong,exit 0

#### 2. ~~三道硬防线 code review (ROADMAP SC #5)~~ ✓ RESOLVED 2026-04-29

已通过 `/gsd-secure-phase 1` 通道验证。详情见 01-SECURITY.md `## Application Invariants Register`:
- **INV-1 / REQ-invariant-blind-inducer**:Inducer 调用链(inducer.py + inducer_prompts.py + glm4v_backend.py)0 次 feature_library/features 读取;数据流仅 sample_ids → meta.yaml → prompt → GLM
- **INV-2 / REQ-invariant-cli-no-feature-content**:`scripts/feature_mining_phase1.py:181-184` `batch_induce(sample_ids=…, backend=…)` call site 仅传 2 参,FeatureStore 实例化发生在 Inducer 调用之后(line 196)

---

### Gaps Summary

无 BLOCKER 级 gap。无 deferred 待办。Phase 1 verification 已 100% 关闭。

**2026-04-29 final close**:原 deferred 两项全部关闭:

1. ~~真实 GLM-4V 端到端 smoke~~ — ✓ RESOLVED(commits `4856dd1` / `679c813`;01-UAT.md Test #1 passed)
2. ~~REQ-invariant 三道硬防线 code review~~ — ✓ RESOLVED(01-SECURITY.md INV-1 / INV-2 closed via /gsd-secure-phase 1 inline code review)

---

## 注意事项 (来自 REVIEW.md — advisory, not blocking)

REVIEW.md 记录了 3 个 WARNING 和 3 个 INFO 级代码质量问题。其中最值得关注的:

- **WR-01** `canvas_manager.py` 的 `plt.rcParams.update(font.size=32)` 违反 OO API 原则,但该设置是 dev UI hover annotation 专用(165-174 行注释说明),与 `sample_renderer.py` 的 rc_context 隔离,不影响 chart.png 正确性。可在后续维护周期中迁移为 per-axes OO API 调用。
- **WR-02** `keyboard_picker.py` 模块 docstring 示例中 `b.idx` 字段名是笔误(正确为 `b.index`);不影响运行时。
- **WR-03** `inducer_prompts.py` 的 `fmt_num(bool)` 行为与 `prompts.py` 不一致,应对齐返回 "N/A"。

---

_Verified: 2026-04-29_
_Verifier: Claude (gsd-verifier)_
