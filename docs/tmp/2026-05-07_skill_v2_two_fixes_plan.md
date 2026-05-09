# Skill v2 → v2.1 Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **NOTE：本任务全是 markdown 编辑（不是代码）**：TDD 不适用；"verification" 步骤用 Read/grep/diff 替代 pytest，最终用 smoke test 跑 skill 端到端验证。

**Goal**：把 `analyze-stock-charts` skill v2 升级到 v2.1，整合 5 个修复（peer 化 / single_group cap / 删 changelog / 改写"不要做" / LLM-only meta-rule）到单 commit。

**Architecture**：5 个修复改的文件高度重叠（5 prompts + SKILL.md + 2 references + 1 schema_version）。按文件分 task，每个 task 一次性应用该文件相关的所有修复。Phase 1（peer 化）改完后跑 smoke test 1 验证；Phase 2（single_group cap + 余下 prompts）改完后跑 smoke test 2 验证；最终 single commit 提交。

**Tech Stack**：纯 markdown 编辑。Smoke test 用 sonnet tier（~$2-5 单次）。Spec ref：`docs/tmp/2026-05-06_skill_v2_two_fixes.md`。

---

## Prerequisites（在新 session 执行此 plan 前必读）

**1. Spec 文档**：先 Read `docs/tmp/2026-05-06_skill_v2_two_fixes.md` 全文。它定义：
- 修复 1+2 的具体方案
- §9 改写的 4 种类型分类（修复 4 部分）
- 各处理规则的依据

新 session 无对话历史，spec 是 plan 的语境基础。

**2. §9 改写类型分类速查**（spec §修复 4 已详述，这里 inline 一份给 subagent）：

| 类型 | 描述 | 处理 |
|---|---|---|
| 1 | 其他 dim-expert 的分工（如"不要分析量价"）| 直接删除（不需正向替代）|
| 2 | 真实 LLM bias 防御（如"不要把右侧大涨作为 tag"）| 融入相关字段说明的正向描述 |
| 3 | 命名空间隔离（如"不读 factor_registry.py"）| 改写为正向资源声明 |
| 4 | 禁令型（如"不要修改 patterns/*"）| 删除（§4 写权限段已覆盖）|

**3. Smoke test 需要 user 提供 K 线图**：

image-cache 是 session-tied（旧 session 的 image cache 已清理）。Task 4 + Task 10 的 smoke test 必须由 user 手动拖入 3-7 张 K 线图触发，**不能由 subagent 自主执行**。

- Task 4（peer 化验证）：需要任意 1 套 3-7 张同类 K 线图（最好含至少 1 套**非 long_base** 形态，如 V 反转，验证 skill 不再误拒）
- Task 10（single_group cap 验证）：需要任意 1 套 3-7 张同类 K 线图（验证入库率提升）

**4. Subagent dispatch 模式**：

- Task 1-3, 5-9（markdown 改动）：可 dispatch implementer subagent 自主执行 → spec review → quality review
- Task 4, 10（smoke test）：**必须** orchestrator 在 user 在场时执行（需要 user 拖图触发 skill）
- Task 11（commit）：orchestrator 执行（需要 git 权限和 working tree review）

---

## File Structure

| 文件 | Phase | 修改类型 |
|---|---|---|
| `.claude/skills/analyze-stock-charts/SKILL.md` | 1 | task DAG 重排 + skip 判定 + §0.2 LLM-only meta-rule + 模型表更新 |
| `.claude/skills/analyze-stock-charts/prompts/phase-recognizer.md` | 1 | 删 go/no-go + 删 v2 changelog + 改写 §9 |
| `.claude/skills/analyze-stock-charts/prompts/synthesizer.md` | 1+2 | 删 phase-recognizer go 引用 + 删 v2 changelog + single_group cap 校验 |
| `.claude/skills/analyze-stock-charts/prompts/resistance-cartographer.md` | 2 | 删 v2 changelog + 改写 §9 + perspectives 校验软化 |
| `.claude/skills/analyze-stock-charts/prompts/volume-pulse-scout.md` | 2 | 同上 |
| `.claude/skills/analyze-stock-charts/prompts/launch-validator.md` | 2 | 同上 + 删 §17 外部研究报告引用 |
| `.claude/skills/analyze-stock-charts/prompts/devils-advocate.md` | 2 | 删 v1.4 双结构 changelog + 改写 §9 + 校验更新 |
| `.claude/skills/analyze-stock-charts/prompts/overviewer.md` | 2 | 仅修复 4（改写 §9） |
| `.claude/skills/analyze-stock-charts/references/02_memory_system.md` | 2 | §C.7 状态机更新 + 加 LLM-only 注释 |
| `.claude/skills/analyze-stock-charts/references/03_team_architecture.md` | 2 | §5.2 cross_group 软化 + 加 LLM-only 注释 |
| `docs/charts_analysis/stock_pattern_library/_meta/schema_version.md` | 2 | 升 2.1.0 |

---

## Task 1：SKILL.md 改造（Phase 1 setup）

**Files**：
- Modify: `.claude/skills/analyze-stock-charts/SKILL.md`

**修改要求**：

1. **task DAG 重排**（§5.2）：T2/T3/T4/T5 全部 blockedBy=T1（不再 T3/T4/T5 blockedBy=T2）
2. **新增 skip 判定逻辑**（§3 输入预检 + §5 流程）：T1 完成后 skill 入口检查 `median(difficulty) >= 0.7 OR homogeneity_decision == "reject"` → 标 `output_kind: skip_run`
3. **新增 §0.2 设计约束**段（紧跟 §0 Meta-team 不写代码）：内容见 spec 修复 5
4. **模型表更新**（§5.1）：mixed tier 中 phase-recognizer 从 opus 降到 sonnet（peer 化后无需 opus 算力溢价）

**Steps**：

- [ ] **Step 1：Read SKILL.md 全文获取当前结构**
- [ ] **Step 2：在 §0 Meta-team 不写代码原则之后新增 §0.2 设计约束段**

  内容（**完整复制此块**，不要简化）：

  ```markdown
  ## 0.2 设计约束（LLM-only）

  所有 skill 行为必须 LLM 可完成。具体约束：

  - **不引入** Python/Bash 脚本作为 skill 运行时依赖
  - **不引入** 需要外部数据查询（如股票 API / 数据库）的功能——skill 只看 user 提供的 K 线图
  - 所有"算法"实质是 LLM 跟结构化规则（yaml 字段比较、set 相等判定、字面匹配等），不是真函数调用

  ### 判定层级（任何新 fix 提议都按此分类）

  | 层级 | 描述 | 允许？|
  |---|---|---|
  | L1 | LLM 自由判断（如"这两条规律是否同源？"）| 允许，但低可靠度 |
  | L2 | LLM 跟结构化规则（如"set A == set B？"）| 允许，主要工作模式 |
  | L3 | 真 Python 函数（如 `numpy.corr(x, y)`）| 禁止 |

  任何新 fix 提议如包含 L3 行为，必须在 design 阶段被 reject 或降级到 L2。
  ```

- [ ] **Step 3：修改 §5.1 模型表的 mixed tier 列**：把 `phase-recognizer` 行的 mixed model 从 `claude-opus-4-7` 改为 `claude-sonnet-4-6`（与 sonnet tier 一致）
- [ ] **Step 4：修改 §5.2 任务依赖图**：

  旧版：
  ```
  T2 = TaskCreate(blockedBy=[T1])
  T3 = TaskCreate(blockedBy=[T2])
  T4 = TaskCreate(blockedBy=[T2])
  T5 = TaskCreate(blockedBy=[T2])
  ```

  新版（4 dim-expert 全 blockedBy=[T1] 并行）：
  ```
  T2 = TaskCreate(blockedBy=[T1])
  T3 = TaskCreate(blockedBy=[T1])
  T4 = TaskCreate(blockedBy=[T1])
  T5 = TaskCreate(blockedBy=[T1])
  ```

  同时删除该段后续的"T2 是 phase-recognizer 的 go/no-go 决议..."整段说明（go/no-go 不再存在）。

- [ ] **Step 5：修改 §3 输入预检 / §5 流程**：在 T1 (overviewer) 完成后、spawn T2-T5 之前，加入 skip 判定逻辑：

  ```markdown
  ### 3.x skip 判定（T1 完成后，spawn T2-T5 之前）

  skill 入口在 overviewer 写完 `## 1.gestalt` 后，按以下条件决定是否跳过下游：

  ```python
  batch = read(run_dir / "findings.md ## 1.gestalt")
  median_difficulty = median([c.difficulty for c in batch.chart_phases])

  if median_difficulty >= 0.7:
      skip_run = True
      reason = "median difficulty too high (信息不足)"
  elif batch.batch_homogeneity.homogeneity_decision == "reject":
      skip_run = True
      reason = "class 混杂度过高"
  else:
      skip_run = False
      继续 spawn T2/T3/T4/T5（并行）
  ```

  skip_run=True 时：synthesizer 走简化流，写 `output_kind: skip_run` 到 written.md。
  ```

- [ ] **Step 6：grep 验证无残留 go/no-go 引用**

  Run：`grep -n "go.*no.*go\|phase-recognizer.*go\b" .claude/skills/analyze-stock-charts/SKILL.md`
  Expected：无匹配（除非在历史段中引用）

- [ ] **Step 7：grep 验证 §0.2 已加**

  Run：`grep -n "## 0.2 设计约束" .claude/skills/analyze-stock-charts/SKILL.md`
  Expected：1 行匹配

**Acceptance Criteria**：
- §0.2 段已存在
- §5.1 mixed tier 表 phase-recognizer 行 model 字段为 `claude-sonnet-4-6`
- §5.2 任务依赖图 T2-T5 全部 blockedBy=[T1]
- §3 或 §5 含 skip 判定逻辑

---

## Task 2：phase-recognizer.md 改造

**Files**：
- Modify: `.claude/skills/analyze-stock-charts/prompts/phase-recognizer.md`

**修改要求（涵盖修复 1+3+4）**：

1. **删除 §5 schema 中的 `go` / `go_reason` 字段**
2. **删除 §5.1 中所有 go 决议规则段**
3. **删除 §7 完成信号中"go=false 时通知 lead 跳过下游"分支**（如有）
4. **删除 §1 第 5 行的 "(v1.4 Agent-2)" 版本引用**
5. **删除 §1 后的 `**v2 重要变更**：` 整段**（4 项内容）
6. **改写"v2 重要变更"段为正向当前状态**，融入 §1 你是谁
7. **改写 §9 不要做的事**（B 方案）：分类处理 7 条 negative items
8. **删除 §1 末尾 `**你不做**：` 短段**（如有 — 该 prompt 中可能没有，仅 resistance/launch 等有）

**Steps**：

- [ ] **Step 1：Read phase-recognizer.md 全文**
- [ ] **Step 2：删除 §5 schema 中 `go: true` 和 `go_reason: "..."` 两行**

  原（约 lines 50-55）：
  ```yaml
  agent_id: phase-recognizer
  merge_group: structure_phase
  go: true                           # true=下游应继续 / false=skip_run
  go_reason: "9 张图中 8 张处于低位横盘期（≥ 60 根 K 线 + 波动收敛），符合可分析状态"

  # 每图判定（必须覆盖全部 N 张）
  chart_phases:
  ```

  新：
  ```yaml
  agent_id: phase-recognizer
  merge_group: structure_phase

  # 每图判定（必须覆盖全部 N 张）
  chart_phases:
  ```

- [ ] **Step 3：删除 §5.1 中 `- go: 影响下游执行；以下任一情况 go=false：` 整段**（约 lines 130-135）
- [ ] **Step 4：删除 §1 中 "(v1.4 Agent-2)" 字样**

  原：`你是 4 位 dim-expert 之一（v1.4 Agent-2）。**v2 重新定位**：你是"专长方向不同的同伴"之一，专长方向是 \`structure_phase\`...`

  新：`你是 4 位 dim-expert 之一，专长方向是 \`structure_phase\`...`

- [ ] **Step 5：删除 §1 后的 `**v2 重要变更**：` 4 项整段**（about 4 lines）

  把"视角不是工作边界"和"开放观察优先"和"cross-image 对比"3 条要点融入 §1 你是谁段（去掉时间标签 v2）。例：

  新版 §1 结尾段：
  ```markdown
  你的专长方向（structure_phase）是 checklist 提示，不是工作边界——人人可发现任何视角的现象。
  你看到的是 N≈5 张同 chart_class 的图，必须做真正的 cross-image 对比（"图 1, 图 3, 图 5 都显示..."），不是逐张分析后聚合。
  ```

  删除"不映射 codebase 因子"——该信息在 §3 必读资源 / §5 schema formalization 字段说明已覆盖。

- [ ] **Step 6：删除 §1 中 `**你不做**：` 短段**（如有）—— phase-recognizer 中可能没有，跳过此步如无
- [ ] **Step 7：改写 §9 不要做的事**

  原 §9：
  ```markdown
  ## 9. 不要做的事
  - 不要分析 BO 间结构（这是 launch-validator 的强项...）
  - 不要分析阻力支撑细节...
  - 不要分析量价...
  - 不要直接给 pattern_id（synthesizer 决定 R-xxxx 编号）
  - 不要修改 patterns/* 或 chart_classes.md
  - **不要读 `factor_registry.py` 或引用现有因子名**（v2 完全解耦）
  - 不要建议 FactorInfo 字段...
  ```

  按 spec 修复 4 分类处理：

  - 类型 1（其他 dim-expert 分工 — 直接删除）：前 3 条（BO 间结构 / 阻力支撑 / 量价）→ 删除
  - 类型 4（禁令型 — §4 已覆盖删除）：第 4-5 条（不要给 pattern_id / 不要修改 patterns）→ 删除
  - 类型 3（命名空间隔离 — 改写为正向资源声明）：第 6 条（不读 factor_registry）→ 改写为 §3 必读资源段的注释："**必读资源不含** `factor_registry.py`；formalization 用通用伪代码即可"
  - 类型 1（model 不会自然做 — 直接删除）：第 7 条（FactorInfo 字段）→ 删除

  整段 §9 删除（变空）后**直接删除该 §9 段标题**（不留空段）。

- [ ] **Step 8：在 §3 必读资源段尾部加注**（融入类型 3 改写）：

  ```markdown
  **必读资源不含** `factor_registry.py`。formalization 字段（详见 §5）用通用伪代码即可（如 `amplitude / atr_ratio / percentile`），不引用具体因子名。
  ```

- [ ] **Step 9：grep 验证无 v1.x / v2 changelog 残留**

  Run：`grep -nE "v[12]\\..*Agent|\\*\\*v[12] " .claude/skills/analyze-stock-charts/prompts/phase-recognizer.md`
  Expected：无匹配（"v2 完全解耦"等表述如还在 §9 删除时一并去除）

- [ ] **Step 10：grep 验证 §9 已删**

  Run：`grep -n "^## 9. 不要做" .claude/skills/analyze-stock-charts/prompts/phase-recognizer.md`
  Expected：无匹配

- [ ] **Step 11：grep 验证 go 字段已删**

  Run：`grep -n "^go:\\|^go_reason:\\|go=false\\|go.*no.*go" .claude/skills/analyze-stock-charts/prompts/phase-recognizer.md`
  Expected：无匹配

**Acceptance Criteria**：
- §5 schema 无 go/go_reason 字段
- §5.1 无 go 决议规则段
- §1 无 v1.4/v2 changelog 段
- §9 不要做的事段已完全删除
- §3 必读资源段含 factor_registry 正向声明

---

## Task 3：synthesizer.md Phase 1 部分（删 phase-recognizer go 引用 + v2 changelog）

**Files**：
- Modify: `.claude/skills/analyze-stock-charts/prompts/synthesizer.md`

**修改要求**：

1. **删除所有引用 phase-recognizer.go 字段的段**（synthesizer 不再读 go 字段）
2. **删除 §7 v2 新增职责 段**（changelog）
3. **删除 §13 v2 删除职责 段**（changelog）
4. **删除 §131 v2 不再输出 段**（changelog）
5. **(Phase 2 部分 single_group cap 校验改动留到 Task 5)**

**Steps**：

- [ ] **Step 1：Read synthesizer.md 全文**
- [ ] **Step 2：grep 找出 phase-recognizer.go 相关引用**

  Run：`grep -n "go.*field\\|go=true\\|go=false\\|phase-recognizer.*go" .claude/skills/analyze-stock-charts/prompts/synthesizer.md`
  Expected：找到 1-3 处需删除

- [ ] **Step 3：逐条删除 go 字段引用**（具体行数取决于文件）
- [ ] **Step 4：删除 §7 起的 `**v2 新增职责**：` 整段**

  策略：把段中实质内容（写库流程的 v2 新增步骤）拆解为正向 "你的职责包括..." 列表，融入 §1 你是谁。

- [ ] **Step 5：删除 §13 `**v2 删除职责**：` 整段**（纯 negative，不需要替代）
- [ ] **Step 6：删除 §131 `**v2 不再输出**：` 段**

  把"不再输出 proposed_factors.yaml"信息融入 §7 写库流程段（正向描述："写库不输出 proposed_factors.yaml；落地为因子由 user 独立调用 add-new-factor skill 接管"）。

- [ ] **Step 7：grep 验证无 v2 changelog 残留**

  Run：`grep -nE "\\*\\*v[12] " .claude/skills/analyze-stock-charts/prompts/synthesizer.md`
  Expected：无匹配

**Acceptance Criteria**：
- 无 phase-recognizer.go 引用
- 无 `**v2 新增/删除/不再输出**` 段标题
- 实质信息保留（v2 新增的写库步骤、v2 删除的 proposed_factors 行为）以正向当前状态描述

---

## Task 4：Smoke Test 1（验证 Phase 1）

**Files**：
- Read only：`docs/charts_analysis/stock_pattern_runs/<new_runId>/`

**修改要求**：跑两次 sonnet tier smoke test 验证 peer 化生效。

**Steps**：

> **重要**：本 task 必须 orchestrator 执行（不能 dispatch subagent），因为需要 user 在场拖入图片触发 skill。

- [ ] **Step 1：请 user 提供 3-7 张 K 线图（任意一套同形态类别）**

  Orchestrator 提示 user：
  > "Phase 1 验证需要你拖入 3-7 张同类 K 线图触发 smoke test。
  > 推荐：1 套 long_base_breakout 形态（验证 4 dim-expert 并行）+ 1 套 v_reversal 或其他非-range 形态（验证 V 反转不再被拒）。
  > 如果只有 long_base 一套，也可以——验证核心是 task DAG 并行 + skip_run 路径"

- [ ] **Step 2：拿到图后 user 触发**

  user 输入：`@1.png @2.png @3.png ... 用 sonnet 跑 analyze-stock-charts 分析`

  skill 会 spawn team。orchestrator 监控。

- [ ] **Step 3：检查 task DAG 行为（peer 化验证）**

  在 run 期间观察：
  - T2/T3/T4/T5 是否在 T1 完成后**同时**变 in_progress（不再 T3/T4/T5 等 T2）
  - written.md 是否含 `output_kind: validated_added` 或 `no_new_pattern`（不应该 skip_run）

  Run（在 run 完成后）：`grep "output_kind" docs/charts_analysis/stock_pattern_runs/<runId>/written.md`
  Expected：`validated_added` 或 `no_new_pattern`

- [ ] **Step 4：（可选）跑 V 反转 batch 验证**

  如果 user 提供了 V 反转图：拖入 + "用 sonnet 跑"。

  期望：output_kind ≠ `skip_run`（旧版会 phase != range → go=false）。

  如果 user 没提供 V 反转图：跳过此步，仅靠 Step 3 验证 peer 化。

**Acceptance Criteria**：
- Step 3：4 dim-expert 并行启动确认（task list 中 T2-T5 同时变 in_progress）✓
- Step 3：output_kind ≠ skip_run ✓
- Step 4（如执行）：V 反转 batch 不被 skill 拒绝 ✓
- 无 written.md 报错

**注意**：smoke test 的输出（`runs/<runId>/` 和 `_pending/<batch>/`）**不要 commit**，是临时 run 数据。

---

## Task 5：synthesizer.md Phase 2 部分（single_group cap 校验）

**Files**：
- Modify: `.claude/skills/analyze-stock-charts/prompts/synthesizer.md`

**修改要求**：

1. **修改 §4 校验清单**：`cross_group_diversity == false` 不再 reject，改为 `confidence_cap: medium`
2. **更新写库流程**（§5）：single-group finding 准入主库 `patterns/<class>/`（与 cross-group 同目录），但 confidence 上限 medium

**Steps**：

- [ ] **Step 1：Read synthesizer.md §4 校验段当前状态**
- [ ] **Step 2：找出 cross_group_diversity 相关校验**

  Run：`grep -n "cross_group_diversity\\|跨.*group\\|merge_group.*多样" .claude/skills/analyze-stock-charts/prompts/synthesizer.md`

- [ ] **Step 3：修改校验逻辑**

  旧（约 §4 校验项）：
  ```markdown
  - [ ] perspectives_used ≥ 2 且**跨 ≥ 2 个 merge_group**（cross_group_diversity = true）
        → 否则 reject_finding(reason: "single_group_combo")
  ```

  新：
  ```markdown
  - [ ] perspectives_used ≥ 2（必填）
        → 否则 reject_finding(reason: "insufficient_perspectives")

  - [ ] cross_group_diversity == true？
        → true：confidence 可达 high
        → false：confidence_cap = medium（仍准入库，但永远不能 high → 不进 mining）
  ```

- [ ] **Step 4：更新 §5 写库流程**

  在写 `patterns/<class>/R-XXXX.md` 步骤补充：

  ```markdown
  - 写入 frontmatter 时：
    - 如 cross_group_diversity == true：confidence 由 evidence 决定（hypothesis / partially-validated / validated）
    - 如 cross_group_diversity == false：confidence 上限 medium（即使 distinct_batches_supported ≥ 3 也不能升 validated）
    - 同时 frontmatter 加 `mining_mode: ready_for_mining: <true if confidence == high else false>`
  ```

- [ ] **Step 5：grep 验证修改正确**

  Run：`grep -n "single_group_combo\\|cross_group.*reject" .claude/skills/analyze-stock-charts/prompts/synthesizer.md`
  Expected：无匹配（旧校验已删除）

**Acceptance Criteria**：
- §4 校验项 cross_group 从 hard reject 改为 confidence cap
- §5 写库流程含 confidence_cap 逻辑
- 无残留 `single_group_combo` 作 reject reason

---

## Task 6：3 dim-expert prompts 改造（resistance / volume-pulse / launch）

**Files**：
- Modify: `.claude/skills/analyze-stock-charts/prompts/resistance-cartographer.md`
- Modify: `.claude/skills/analyze-stock-charts/prompts/volume-pulse-scout.md`
- Modify: `.claude/skills/analyze-stock-charts/prompts/launch-validator.md`

**修改要求（每个文件相同模式 — 修复 3+4）**：

1. 删除 §1 后的 `**v2 重要变更**：` 整段，融入 §1 当前状态描述
2. 删除 `**你不做**：` 短段
3. 改写 §9 不要做的事（B 方案分类删除/改写）
4. 修改 §6 防偏差硬约束 #1：从"≥ 2 视角且跨 ≥ 2 group 必填" → "≥ 2 视角必填；跨 group 推荐但非必须"
5. **额外（仅 launch-validator）**：删除 §17 引用 `dimension_review_2026-05-04` 报告（保留实质内容："如发现 BO 序列拓扑现象，照样报告"）

**Steps**：

- [ ] **Step 1：对每个文件应用相同模式**（按 resistance → volume → launch 顺序）

- [ ] **Step 2：每文件 Step A：删除 §1 后的 `**v2 重要变更**：` 段**

  与 Task 2 Step 5 相同处理：把"视角不是工作边界"+"开放观察优先"+"cross-image 对比"3 条融入 §1 当前状态描述（去掉 v2 时间标签）。

- [ ] **Step 3：每文件 Step B：删除 `**你不做**：` 短段**（约 line 13）

- [ ] **Step 4：每文件 Step C：改写 §9 按类型删除/融入**

  类似 Task 2 Step 7：按 4 类处理（其他 dim-expert 分工删 / bias 防御融入 / 命名空间隔离改写 / 禁令删）。

  每个文件的 §9 内容略不同，按实际处理。删除空段。

- [ ] **Step 5：每文件 Step D：修改 §6 防偏差硬约束 #1**

  旧：`1. **≥ 2 视角约束保留**：你的 finding 至少含 2 个 perspectives_used；synthesizer 跨 group 多样性校验在合并阶段执行`

  新：`1. **≥ 2 视角约束**：你的 finding 至少含 2 个 perspectives_used。跨 group 推荐（synthesizer 可给 high confidence），单 group 也可（confidence 上限 medium）。`

- [ ] **Step 6：仅 launch-validator Step E：删除 §17 外部引用**

  原 §17 含：`...见 dimension_review_2026-05-04 报告 §2.1`

  新：`如发现"短期内多次 BO + bo_label 互不相同 + 没有超涨 + 放量持续"等序列拓扑现象，照样报告，perspectives_used 写 G，并在 cross_image_observation 段说明这是序列拓扑特征。`

- [ ] **Step 7：grep 验证无 changelog 残留**

  Run：`grep -nE "\\*\\*v[12] |dimension_review_2026" .claude/skills/analyze-stock-charts/prompts/resistance-cartographer.md .claude/skills/analyze-stock-charts/prompts/volume-pulse-scout.md .claude/skills/analyze-stock-charts/prompts/launch-validator.md`
  Expected：无匹配

- [ ] **Step 8：grep 验证 §9 已删**

  Run：`grep -n "^## 9. 不要做" .claude/skills/analyze-stock-charts/prompts/resistance-cartographer.md .claude/skills/analyze-stock-charts/prompts/volume-pulse-scout.md .claude/skills/analyze-stock-charts/prompts/launch-validator.md`
  Expected：无匹配

**Acceptance Criteria**：
- 3 文件无 v2 changelog 段标题
- 3 文件无 §9 不要做段
- 3 文件 §6 防偏差 #1 已软化
- launch-validator §17 无外部研究报告引用

---

## Task 7：devils-advocate.md 改造

**Files**：
- Modify: `.claude/skills/analyze-stock-charts/prompts/devils-advocate.md`

**修改要求（修复 2+3+4）**：

1. 删除 §1 后的 `**v1.4 双结构职责**：` 整段，融入 §1
2. 改写 §9 不要做的事
3. 修改 5 项校验中 #1：从"perspectives_used 跨 ≥ 2 group" → "perspectives_used ≥ 2"（删除跨 group 部分）

**Steps**：

- [ ] **Step 1：Read devils-advocate.md 全文**

- [ ] **Step 2：删除 §1 后的 `**v1.4 双结构职责**：` 段**

  把段中实质内容（职责 A 反方质疑 + 职责 B 写库前 5 项校验否决权）融入 §1 当前职责描述。

- [ ] **Step 3：改写 §9 按 4 类处理**（同 Task 2 Step 7）

- [ ] **Step 4：修改 5 项校验 #1**

  Run：`grep -n "perspectives_used.*跨\\|跨.*merge_group\\|cross_group_diversity" .claude/skills/analyze-stock-charts/prompts/devils-advocate.md`

  找出 5 项校验段。修改 #1：

  旧：`1. perspectives_used ≥ 2 且**跨 ≥ 2 个独立 merge_group**`

  新：`1. perspectives_used ≥ 2（跨 group 推荐但非必须 — synthesizer 会按 cross_group_diversity 字段决定 confidence 上限）`

- [ ] **Step 5：grep 验证修改**

  Run：`grep -nE "v1\\.4|\\*\\*v[12] |^## 9. 不要做" .claude/skills/analyze-stock-charts/prompts/devils-advocate.md`
  Expected：无匹配

**Acceptance Criteria**：
- §1 无 v1.4 双结构 changelog 段
- §9 不要做段已删
- 5 项校验 #1 已软化（不再要求跨 group）

---

## Task 8：overviewer.md 改造（仅修复 4）

**Files**：
- Modify: `.claude/skills/analyze-stock-charts/prompts/overviewer.md`

**修改要求**：仅 §9 改写（overviewer 无 v1.x/v2 changelog 段）。

**Steps**：

- [ ] **Step 1：Read overviewer.md §9 段**

- [ ] **Step 2：grep 确认无 changelog 段**

  Run：`grep -nE "\\*\\*v[12] " .claude/skills/analyze-stock-charts/prompts/overviewer.md`
  Expected：无匹配

- [ ] **Step 3：改写 §9 不要做的事**（同 Task 2 Step 7 模式）

  例如 overviewer §9 可能含：
  - 不要给规律级判断（→ 删除，§1 已说明 overviewer 不做规律级判断）
  - 不要修改 input.md（→ 类型 4 禁令型，§4 写权限已覆盖，删除）
  - 不要写 yaml 之外的"分析评论"（→ 类型 2 真实倾向，融入 §5 字段说明的正向描述）

- [ ] **Step 4：删除 §9 整段**（如全删除完）

- [ ] **Step 5：grep 验证 §9 已删**

  Run：`grep -n "^## 9. 不要做" .claude/skills/analyze-stock-charts/prompts/overviewer.md`
  Expected：无匹配

**Acceptance Criteria**：
- §9 不要做段已删
- 真实倾向防御内容融入相关字段说明

---

## Task 9：references/02 + 03 + schema_version 升级

**Files**：
- Modify: `.claude/skills/analyze-stock-charts/references/02_memory_system.md`
- Modify: `.claude/skills/analyze-stock-charts/references/03_team_architecture.md`
- Modify: `docs/charts_analysis/stock_pattern_library/_meta/schema_version.md`

**修改要求**：

1. `02 §C.7` 状态机：single-group hypothesis 可入库，但晋级路径上限 partially-validated（不能 validated）
2. `02` 加 LLM-only 注释（指向 SKILL.md §0.2）
3. `03 §5.2` cross_group 多样性约束：从"硬约束"改为"confidence 软分层"
4. `03` 加 LLM-only 注释（指向 SKILL.md §0.2）
5. `schema_version.md` 升 2.1.0 + 加本次升级历史

**Steps**：

- [ ] **Step 1：Read 02_memory_system.md §C.7 状态机段**

- [ ] **Step 2：修改 §C.7 状态机**

  在 `validated` 升级条件后加注：

  ```markdown
  > **v2.1 single-group cap**：cross_group_diversity == false 的 finding 入库时 confidence_cap = medium，永远不能升 validated（即使 distinct_batches_supported ≥ 3 + 0 反例）。
  > 这类 finding 仍可达 partially-validated，作为 user 探索素材或未来跨 batch 联立的输入。
  ```

- [ ] **Step 3：在 02 顶部 frontmatter 后加 LLM-only 引用**

  ```markdown
  > **设计约束**：所有规律库 IO 协议必须 LLM 可完成。详见 `SKILL.md §0.2 设计约束（LLM-only）`。
  ```

- [ ] **Step 4：Read 03_team_architecture.md §5.2 段**

- [ ] **Step 5：修改 §5.2 cross_group 多样性段**

  旧：硬约束（每条入库规律 perspectives_used 必须跨 ≥ 2 个 merge_group）
  新：confidence 软分层（cross_group=true → confidence 可 high；cross_group=false → confidence_cap medium，仍准入库）

  保留"防伪组合"的设计意图说明（这是 design rationale），但当前规则改为软分层。

- [ ] **Step 6：在 03 顶部加 LLM-only 引用**（同 Step 3）

- [ ] **Step 7：升 schema_version.md 到 2.1.0**

  Read 当前 schema_version.md，追加：

  ```markdown
  | 2.1 | 2026-05-07 | phase-recognizer peer 化（删 go/no-go）；single_group_rule 软化为 confidence cap medium；删除 prompts 中 v1.x/v2 changelog；改写"不要做"段为正向；锁定 LLM-only 设计约束 |
  ```

- [ ] **Step 8：grep 验证 02 / 03 引用 §0.2**

  Run：`grep -n "§0.2\\|0.2 设计约束" .claude/skills/analyze-stock-charts/references/02_memory_system.md .claude/skills/analyze-stock-charts/references/03_team_architecture.md`
  Expected：每个文件 1 行匹配

**Acceptance Criteria**：
- 02 §C.7 含 v2.1 single-group cap 说明
- 03 §5.2 已从硬约束改为 confidence 软分层
- 02 / 03 顶部引用 SKILL.md §0.2
- schema_version.md current = 2.1, 升级历史含本次

---

## Task 10：Smoke Test 2（验证 Phase 2）

**Files**：
- Read only

**修改要求**：跑 sonnet tier smoke test 验证 single_group cap 生效。

**Steps**：

> **重要**：本 task 同 Task 4，必须 orchestrator 在 user 在场时执行。

- [ ] **Step 1：请 user 提供同一套 long_base_breakout K 线图（与 Task 4 相同最佳，便于对比入库率）**

  Orchestrator 提示 user：
  > "Phase 2 验证 single_group cap 生效。请用与 Task 4 相同的 5 张图（如果还在），或任意 3-7 张同类 K 线图重跑。
  > 验证目标：入库率从旧版 ~17% 提升到 ~50%（约 6/12 finding 入库 vs 旧版 2/12）"

  user 拖图 + `用 sonnet 跑 analyze-stock-charts 分析`

- [ ] **Step 2：验证入库率提升**

  期望（按 spec 验证标准 1）：
  - 入库规律数从 2 → ~6（新增 e1-01 / e2-01 / e3-01 / e3-03 进 medium）
  - written.md 中无 `cross_group_diversity` 作为 reject 原因
  - 4 dim-expert 并行启动（peer 化效果）

- [ ] **Step 3：检查新规律 confidence**

  Read `_pending/<runId>/R-pending-*.md`：
  - cross_group=true 的规律：confidence 可达 high（如距离 validated 还差 distinct_batches，则为 hypothesis）
  - cross_group=false 的新增规律：confidence 上限 medium

**Acceptance Criteria**：
- 入库率 ≥ 50%（约 6/12 finding 入库 vs 旧版 17%）
- 4 dim-expert 并行启动
- single-group 规律 confidence ≤ medium

---

## Task 11：Single Commit + 最终验证

**Files**：
- 所有 Task 1-9 改的文件
- 不包含：`docs/charts_analysis/stock_pattern_runs/` 下 smoke test 产出

**修改要求**：单 commit 提交所有 skill 改动。

**Steps**：

- [ ] **Step 1：git status 检查改动文件**

  Run：`git status`

  期望改动：
  ```
  modified:   .claude/skills/analyze-stock-charts/SKILL.md
  modified:   .claude/skills/analyze-stock-charts/prompts/phase-recognizer.md
  modified:   .claude/skills/analyze-stock-charts/prompts/synthesizer.md
  modified:   .claude/skills/analyze-stock-charts/prompts/resistance-cartographer.md
  modified:   .claude/skills/analyze-stock-charts/prompts/volume-pulse-scout.md
  modified:   .claude/skills/analyze-stock-charts/prompts/launch-validator.md
  modified:   .claude/skills/analyze-stock-charts/prompts/devils-advocate.md
  modified:   .claude/skills/analyze-stock-charts/prompts/overviewer.md
  modified:   .claude/skills/analyze-stock-charts/references/02_memory_system.md
  modified:   .claude/skills/analyze-stock-charts/references/03_team_architecture.md
  modified:   docs/charts_analysis/stock_pattern_library/_meta/schema_version.md
  ```

  如有 smoke test 产出（`stock_pattern_runs/` 下），不要 add。

- [ ] **Step 2：git diff review 关键改动**

  Run：`git diff .claude/skills/analyze-stock-charts/SKILL.md .claude/skills/analyze-stock-charts/prompts/phase-recognizer.md`

  人工 review：
  - SKILL.md §0.2 已添加
  - phase-recognizer 无 go 字段、无 changelog、无 §9
  - 无意外删除

- [ ] **Step 3：grep 全局校验**

  Run：
  ```bash
  grep -rnE "\\*\\*v[12] |v1\\.4 Agent" .claude/skills/analyze-stock-charts/prompts/
  ```
  Expected：无匹配（所有 changelog 段已删）

  Run：
  ```bash
  grep -rn "^## 9. 不要做" .claude/skills/analyze-stock-charts/prompts/
  ```
  Expected：无匹配（所有 §9 已删）

  Run：
  ```bash
  grep -rn "single_group_combo\\|cross_group.*reject" .claude/skills/analyze-stock-charts/prompts/
  ```
  Expected：无匹配（single_group rule 已软化）

- [ ] **Step 4：git add + commit**

  Run：
  ```bash
  git add .claude/skills/analyze-stock-charts/ docs/charts_analysis/stock_pattern_library/_meta/schema_version.md
  git commit -m "$(cat <<'EOF'
  refactor(skill): v2 → v2.1 cleanup (5 fixes integrated)

  1. phase-recognizer 从 gatekeeper 退化为 peer dim-expert
     - 删除 go/no-go 决策权
     - 早停权限上移到 skill 入口（基于 difficulty + homogeneity）
     - task DAG: T2/T3/T4/T5 全部 blockedBy=T1 并行
     - mixed tier phase-recognizer 同步降到 sonnet

  2. single_group_combo rule 软化（confidence cap）
     - 从 hard reject 改为 confidence_cap = medium
     - single-group finding 准入主库（mining 不取，user 探索素材）
     - 不引入 decoupling_check / 合成层 / _single_dim 等复杂组件

  3. 删除 prompt 中开发过程叙述
     - 5 prompts 删除 v2/v1.4 changelog 段
     - 现状包装成历史的内容改写为正向当前状态
     - launch-validator 删除外部研究报告引用

  4. 改写 prompts §9 "不要做的事" 段为正向
     - 其他 dim-expert 分工类直接删除
     - 真实 LLM bias 防御融入相关字段说明
     - 命名空间隔离改写为正向资源声明

  5. SKILL.md §0.2 锁定 LLM-only 设计约束
     - 显式 L1/L2/L3 判定层级
     - 禁止 L3（真 Python 函数）
     - 02/03 references 加 LLM-only 引用

  schema_version: 2.0 → 2.1

  详见 docs/tmp/2026-05-06_skill_v2_two_fixes.md

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

- [ ] **Step 5：git status 验证 commit 成功**

  Run：`git status`
  Expected：working tree clean（除可能的 stock_pattern_runs/ 残留）

- [ ] **Step 6：清理 docs/tmp/**

  此 plan 文档（`2026-05-07_skill_v2_two_fixes_plan.md`）和 spec（`2026-05-06_skill_v2_two_fixes.md`）属一次性 plan，commit 完成后可删除。

  ```bash
  # 可选 — 删除 plan + spec
  # rm docs/tmp/2026-05-07_skill_v2_two_fixes_plan.md
  # rm docs/tmp/2026-05-06_skill_v2_two_fixes.md
  ```

- [ ] **Step 7：更新 docs/explain/analyze_stock_charts_logic_analysis.md**

  按 spec "实施后需更新" 清单：反映 v2.1.0 变化（约 §4.3 / §6 / §8.5 三处）。

  这一步可独立 commit（不在 cleanup commit 内）。

**Acceptance Criteria**：
- 所有 11 个文件改动入单 commit
- commit message 含 5 个修复说明
- working tree clean
- explain 文档已更新（独立 commit）

---

## Self-Review

按 writing-plans skill 自检：

**Spec coverage**：
- 修复 1 (peer 化)：Task 1 (SKILL.md) + Task 2 (phase-recognizer.md) + Task 3 (synthesizer.md 引用) + Task 4 (smoke test 1) ✓
- 修复 2 (single_group cap)：Task 5 (synthesizer.md 校验) + Task 6 (3 dim-expert §6) + Task 7 (advocate) + Task 9 (references) + Task 10 (smoke test 2) ✓
- 修复 3 (删 changelog)：Task 2/3/6/7 各文件中处理 ✓
- 修复 4 (改写"不要做")：Task 2/6/7/8 各文件中处理 ✓
- 修复 5 (LLM-only meta)：Task 1 (SKILL.md §0.2) + Task 9 (02/03 引用) ✓

**Placeholder scan**：无 TBD/TODO/"implement later"

**Type consistency**：跨 task 引用的字段名一致（cross_group_diversity / confidence_cap / merge_group / chart_class / phase）

**注意事项**：
- 本 plan 中 Phase 1 smoke test (Task 4) 是 verification 不是 commit。所有 commit 在 Task 11 单次完成
- 改 prompt 时优先**删除**而非"重命名"——保留必要信息时用正向语言重写，但不留过渡 / 兼容性段

---

## Execution Handoff

**Plan complete and saved to `docs/tmp/2026-05-07_skill_v2_two_fixes_plan.md`. Two execution options:**

**1. Subagent-Driven（recommended）** - 每 task dispatch fresh subagent + spec review + quality review，task 间 review，快速迭代

**2. Inline Execution** - 在当前 session 用 executing-plans batch 跑 + checkpoint review

**Which approach?**
