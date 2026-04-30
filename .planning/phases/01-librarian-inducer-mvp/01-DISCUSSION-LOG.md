# Phase 1: Librarian + Inducer MVP - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-29
**Phase:** 1-librarian-inducer-mvp
**Areas discussed:** Phase status reconciliation, Picker FSM, BO 视觉标记, Y 轴 pivot, chart.png 字体

---

## Phase 1 状态对齐(meta-question)

| Option | Description | Selected |
|--------|-------------|----------|
| 已完成,改走验证/收尾 | `/gsd-verify-work 1` 走 SPEC §9 acceptance,/gsd-validate-phase 自动审计;discuss 中止 | |
| 补 CONTEXT.md 用作回溯文档 | 从 git + 代码 + 研究反向抽决策草稿 | |
| **Phase 1 还有未完成的 gap** | 围绕用户列举的 gap 生成针对性 gray areas | ✓ |
| 其实想讨论 Phase 1.5 | 切到 `/gsd-discuss-phase 1.5` | |

**User's choice:** Phase 1 还有未完成的 gap
**Notes:** 触发用户列举具体 gap;用户列出 4 条:
  1. 渲染窗口太宽、保留虚线(应只画两端点之间)
  2. 第二次点击不再代表 pk(语义重构)
  3. 强制第一次点 BO,设计提示状态机
  4. chart.png 字体过大

---

## Picker FSM(状态机 + 错点行为 + 文案)

| Option | Description | Selected |
|--------|-------------|----------|
| 错点留在当前态 | 三态机 IDLE → AWAITING_BO → AWAITING_LEFT;错点 toast warn + 保持当前态,不重置 | ✓ |
| 错点 reset 回 IDLE | 严格但反复劳动多;错点 toast error + 立即回 IDLE | |

**User's choice:** 错点留在当前态(推荐选项)
**Notes:** Preview 中给出了完整 FSM 转移图,用户接受;状态机本身的三态结构无异议(IDLE → AWAITING_BO → AWAITING_LEFT → IDLE)。

---

## BO 视觉标记(chart.png 上是否仍需提示哪一根是 BO)

| Option | Description | Selected |
|--------|-------------|----------|
| 不标,依靠位置约定 + prompt 文本 | chart.png 不画虚线 / 不加文字;prompt 中说明 right-most = breakout day | ✓ |
| 给最右 bar 加轻量描边/箭头 | 不画虚线但视觉上轻提示 | |
| 标题加 right edge = BO 后缀 | 标题保留脱敏但暗示语义 | |

**User's choice:** 不标,依靠位置约定 + prompt 文本(推荐选项)
**Notes:** 与用户原话"图中没有必要保留虚线以及关于虚线意义的注释"一致。图象通道保持最干净,语义由 prompt 文本通道独占传递。

---

## Y 轴 pivot(归一化基线)

第一次 AskUserQuestion 时用户选"先让我看 tom 研究再定"。spawned `tom` agent 做第一性原理研究,产出 `docs/research/feature_mining_chart_pivot_decision.md`。重新提问后:

| Option | Description | Selected |
|--------|-------------|----------|
| **采用 tom 推荐:BO close = 0%(右端)** | pivot = df_window.iloc[-1]['close'];文本通道同步切到 BO close 锚点 | ✓ |
| 坚持原推荐:左端 close = 0% | pivot = df_window.iloc[0]['close'];与 prompts.py 现有表述一致 | |
| 我要先读报告再定 | 暂不拍板 | |

**User's choice:** 采用 tom 推荐(BO close = 0%)
**Notes:** tom 报告核心论据 — BO 是这批样本的语义不变量,本体论锚点(突破日)= 视觉锚点(画面右端)= OCR 锚点(Y 轴 0% 标签)三重重合;盘整带在不同样本里的几何位置与 Y 轴文字主体强同构,是 fastembed cosine ≥ 0.85 合并的唯一可靠路径。次推荐为左端 close,弱在"窗口起点是用户主观挑的,跨样本不可比 → Y 轴文字模式发散,反而引入跨样本噪声"。

**关键关联决策**:用户接受 tom 报告"两通道同步切 pivot"的建议 → CONTEXT D-08(prompts.py / inducer_prompts.py 文本通道也切到 BO close 锚点)。

---

## chart.png 字体压缩

| Option | Description | Selected |
|--------|-------------|----------|
| **只缩字号** | rcParams font=8 / title=10 / xy-label=8 / xy-tick=7;figsize 与 DPI 不变 | ✓ |
| 只缩 figsize | figsize (12,8) → (8,5);K 线密度变高 | |
| 两者组合 | font=8 + figsize=(10,6);调参成本高 | |
| 用户给具体数字 | Other 自填 | |

**User's choice:** 只缩字号(推荐选项)
**Notes:** 保持 1200×800 输出尺寸不损失 K 线主体可视面积;rcParams 必须用 `mpl.rc_context` 局部覆盖(防御 OO API 不污染全局原则)。

---

## Claude's Discretion

- 状态机 sticky / toast 文案的英文措辞(只要语义不变,Claude 在实施时可微调)
- `_pct_fmt` 中"百分号位置 / 小数位"细节
- `prompts.py` 文本通道中 breakout_day 行的中文表述(在保持"零点 = BO close"前提下)

## Deferred Ideas

- Phase 1 SPEC §9 #5 三道硬防线 code review → `/gsd-secure-phase 1`
- Phase 1 SPEC §9 #1 端到端 smoke(真 GLM-4V API)→ `/gsd-verify-work 1`
- G0/G1/G2/G3 ablation(脱敏研究 §8)未跑
- Phase 1.5 `epoch_tag` / `superseded_by` 激活
- dev UI 启动时是否默认提示"按 P 开始挑选"(发现性问题)

## Spawned Sub-research

- `tom` agent → `docs/research/feature_mining_chart_pivot_decision.md`(第一性原理 pivot 选择研究,改变了 Q3 推荐方向)
