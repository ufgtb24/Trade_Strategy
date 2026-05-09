# chart_class 决议交互流程 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 analyze-stock-charts skill v2.1 中由 synthesizer 在 T7 自动执行的 chart_class 同义判断 / 新建 / 合并决策，前移到 T1 (overviewer) 完成后 + T2-T5 (dim-expert) spawn 前的 lead T1.5 决议节点；user 显式决议（lead 协调 + LLM 推荐辅助），消除 alias / proposed classes / _pending 三个冗余概念。

**Architecture:** lead 在 T1 完成后增加一个不进入 TaskCreate 的内部决议节点 T1.5：读 overviewer 的 dominant_class + 库 active classes → 调 LLM 求合并候选 → 三分支处理（同名直接合并 / 有候选弹 AskUserQuestion 让 user 选 / 无候选直接新建）→ 把 final_chart_class 写入 findings.md ## 1.5.class_decision 段并注入下游 dim-expert spawn prompt。synthesizer 不再做 chart_class 决议，直接用 final_chart_class 写库。

**Tech Stack:** 纯 markdown / yaml frontmatter 编辑（无代码）。涉及文件：SKILL.md、7 prompts、references/01-03。

**Commit strategy:** 全部改动整合为单 commit `refactor(skill): v2.1 → v2.2 chart_class user-decision flow`。

**Spec reference:** `docs/tmp/2026-05-07_chart_class_user_decision_design.md`

---

## Prerequisites

执行本 plan 前确认：

1. **当前在 dev 分支**：`git status` 应显示 `On branch dev`
2. **工作树已清理**：本 plan 假设没有 unrelated 改动；执行前如有未 commit 的改动，user 应先决定（提交 / stash / 丢弃）
3. **依赖 commits 已落地**：
   - `83acbae refactor(skill): v2 → v2.1 cleanup`（5 fixes integrated）
   - `8f2fd63 fix(skill): align dim-expert §2 (model + blockedBy)`
4. **spec doc 可读**：执行 task 时 implementer 必须先 Read `docs/tmp/2026-05-07_chart_class_user_decision_design.md`
5. **执行模式**：subagent-driven 模式 — 每 task dispatch 一个 implementer subagent + 一个 spec-review subagent；review 通过后才进下一个 task。所有 subagent 都用 `tom` agent。

## File Structure

| 文件 | 类型 | 改动量 | 主要内容 |
|---|---|---|---|
| `.claude/skills/analyze-stock-charts/SKILL.md` | Modify | ~80 行（删 + 加） | §3.2.2 step 3 重写、§5.2 任务依赖图加 T1.5 注释、新增 §5.2bis "T1.5 chart_class 决议" 一节 |
| `.claude/skills/analyze-stock-charts/prompts/overviewer.md` | Modify | ~5 行 | §1 角色描述补一句关于 T1.5 衔接 |
| `.claude/skills/analyze-stock-charts/prompts/synthesizer.md` | Modify | ~60 行（主要是删） | §5.1/§5.2 case 2 整段删除、§3 输入资源调整、§4 校验第 9 项改写、§5.2 case 1 改名（无需区分 case） |
| `.claude/skills/analyze-stock-charts/prompts/phase-recognizer.md` | Modify | 2 行 | §3 输入表 dominant → final，加一句备注 |
| `.claude/skills/analyze-stock-charts/prompts/resistance-cartographer.md` | Modify | 2 行 | 同上 |
| `.claude/skills/analyze-stock-charts/prompts/volume-pulse-scout.md` | Modify | 2 行 | 同上 |
| `.claude/skills/analyze-stock-charts/prompts/launch-validator.md` | Modify | 2 行 | 同上 |
| `.claude/skills/analyze-stock-charts/references/02_memory_system.md` | Modify | ~80 行 | §A.5 schema 整段重写、§D.7 演化规则更新、§E flow 加 T1.5 描述、删 _pending 引用 |
| `.claude/skills/analyze-stock-charts/references/03_team_architecture.md` | Modify | ~10 行 | §3.1 mermaid 加 T1.5 节点、§4.3 权限矩阵 lead 加 chart_class 决议、synthesizer 移除 |
| `.claude/skills/analyze-stock-charts/references/01_analysis_dimensions.md` | Modify | ~3 行 | line 494 + 512 dominant → final、删除 proposed classes 引用 |

不改：
- `prompts/devils-advocate.md` （不引用 dominant_chart_class / aliases / _pending）
- `references/00_README.md`（不含相关引用）
- `references/02_memory_system.md` §B / §C 主体（仅删 _pending 提及）

---

## Task 1: SKILL.md §3.2.2 chart_class 流程重写

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/SKILL.md` 行 ~310-323（§3.2.2 step 3）

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent 实施以下改动：

读 spec `docs/tmp/2026-05-07_chart_class_user_decision_design.md` §3 + §6 + §8.1。然后修改 `.claude/skills/analyze-stock-charts/SKILL.md`：

将 §3.2.2 第 3 步（lines ~321-324，"synthesizer 写库" 段）整段替换为：

```markdown
3. **lead T1.5 决议**（详见 `prompts/synthesizer.md` 不再做、详见 §5.2bis）：
   - skill 入口在 overviewer T1 completed 后，读 `_meta/chart_classes.md` 的 `## active classes`
   - 三分支处理：
     - **A 同名命中**（dominant_class 在 active classes 中存在）→ text 通知 user "类已存在，将合并"，self-execute
     - **B 有候选**（LLM 找到 sim ≥ 0.5 的合并目标）→ AskUserQuestion 弹选项（新建 / 合并入 X），user 决议
     - **C 无候选**（LLM 未找到 sim ≥ 0.5）→ text 通知 user "未找到合并候选，将新建"，self-execute
   - 决议结果（final_chart_class）注入下游 T2-T5 dim-expert spawn prompt
4. **synthesizer 写库**（详见 `prompts/synthesizer.md`）：
   - 直接用 spawn prompt 注入的 `final_chart_class`，写入 `patterns/<final_chart_class>/`
   - 不再做同义判断、不再写 `## proposed classes`、不再用 `_pending/`
```

- [ ] **Step 2: spec-review subagent 审核**

dispatch tom subagent 验证：

验证 task 1 改动是否符合 spec `docs/tmp/2026-05-07_chart_class_user_decision_design.md` §3 + §8.1：
- A/B/C 三分支描述正确
- 不再提 alias / _pending / proposed classes
- 提及 §5.2bis 引用（即下个 task 会新增的章节）

如不符合，返回具体问题描述供下个迭代修复。

- [ ] **Step 3: 验证 grep 现状**

Run: `grep -n "aliases\|_pending\|proposed classes" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/SKILL.md`
Expected：还能在 §3.1 (bootstrap) / §6.4 (回滚) 等处看到引用 — 这些 task 2 处理。当前 §3.2.2 内不应再有引用。

---

## Task 2: SKILL.md §5.2 任务依赖图 + 新增 §5.2bis T1.5 决议节点

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/SKILL.md` 行 ~443-465（§5.2 任务依赖图 + 新增 §5.2bis）

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent 实施：

读 spec `docs/tmp/2026-05-07_chart_class_user_decision_design.md` §3 + §4 + §5。修改 SKILL.md：

**A. 在 §5.2 任务依赖图末尾（"`关键：T2/T3/T4/T5 全部以 T1...`" 这段后）追加一段**：

```markdown
> **T1.5 决议节点**（v2.2 新增，**不进入 TaskCreate**）：lead 在 T1 completed 后，T2-T5 spawn 前，执行 chart_class 决议（同名 / 合并 / 新建），把 final_chart_class 注入 T2-T5 spawn prompt。详见 §5.2bis。
```

**B. 在 §5.2 之后插入新章节 §5.2bis（位置在 "### 5.3 流程映射" 之前）**：

```markdown
### 5.2bis T1.5 chart_class 决议（lead 内部步骤）

skill 入口在 T1 (overviewer) completed 后、T2-T5 spawn 前执行。**不写入 TaskCreate**（lead 不发任务给自己）。

#### 步骤
1. **读取上游产出**
   - 读 `{run_dir}/findings.md ## 1.gestalt` → 取 `dominant_chart_class` + `first_impression` 摘要
   - 读 `{library_root}/_meta/chart_classes.md ## active classes` → 取已有 class 列表

2. **分支判定**
   - if `dominant_class` 在 active classes 中 → 分支 A 同名命中
   - elif active classes 为空（库初期）→ 分支 C 无候选
   - else → 调 LLM 求合并候选；若最相似 sim < 0.5 → 分支 C，否则 → 分支 B 有候选

3. **LLM 候选检索**（仅分支 B 触发）
   - prompt：`"Batch dominant_class: <name>\nBatch first_impression: <每图 1 行>\nActive classes:\n<list>\n判断 dominant_class 与每个 active class 的语义相似度，输出最相似的 1 个候选（sim ≥ 0.5 才输出）：{candidate, sim_score, rationale, key_difference}"`
   - 仅返回 1 个最相似候选；若所有 sim < 0.5 → 返回 null → 分支 C

4. **交互呈现**（仅分支 B 触发）
   - 调 `AskUserQuestion`，呈现候选 + 推荐 + 选项（"新建 <name>" / "合并入 <candidate>"）
   - **rename 承载**：lead 在 prompt 中提示用户"如要改名，请在回复中追加 `rename: <new_name>`"。lead 解析回复识别 rename 字段。具体 AskUserQuestion 调用形式由实施者决定，但保持单段 prompt（禁 2 段式）

5. **分支 A / C 通知**（不调 AskUserQuestion）
   - 分支 A: text 通知 "✓ chart_class `<name>` 已存在，本 batch 将合并入此 class"
   - 分支 C: text 通知 "✓ 未找到 sim≥0.5 的合并候选，将新建 chart_class `<name>`"

6. **持久化决议**
   - 更新 `_meta/chart_classes.md`：
     - 新建分支 (B-new / C)：在 `## active classes` 段追加新行
     - 合并/同名 (B-merge / A)：仅更新该 class 的 `last_updated`
   - 写 `{run_dir}/findings.md ## 1.5.class_decision`（详见下方 schema）

#### 决议日志 schema
写入 `{run_dir}/findings.md ## 1.5.class_decision`：

```yaml
batch_dominant_class: long_consolidation_breakout
final_chart_class: long_base_breakout
decision_branch: B-merge       # A-existing / B-merge / B-new / C-no-candidate
user_decided_at: 2026-05-07T14:23:11+08:00

llm_candidate:                  # 仅 branch B 时填，否则省略
  candidate: long_base_breakout
  sim_score: 0.78
  rationale: "..."
  key_difference: "..."
  recommendation: merge

user_choice: merge_into          # new / merge_into
user_renamed: false
user_renamed_to: ""
notification_only: false         # branch A / C 时为 true
```

#### 错误处理
| 异常 | 处理 |
|---|---|
| user 不回复 AskUserQuestion | 不设硬超时（AskUserQuestion 阻塞 lead，user 可随时回复） |
| LLM 候选检索失败 | 重试 1 次；仍失败 → 降级为分支 C 新建 + 通知 user |
| user 自定义名 = 已有 class | 拒绝 + 重新弹问 |
| user 自定义名含非法字符 | 拒绝 + 提示 `[a-z][a-z0-9_]*` 格式 |
| chart_classes.md 锁失败 | 30s 重试；仍失败 → abort run，runs/ 标 `status=incomplete` |
| user abort skill | TeamDelete，runs/ 标 `status=user_aborted_at_t1_5` |
| 库为空（首次 run）| 跳过 LLM 检索（active classes 空），直接走分支 C |

#### 注入下游 spawn prompt
T2-T5 dim-expert spawn 时元信息段加 `final_chart_class`：

```
=== 本次 run 元信息（由 skill 入口注入）===
...
dominant_chart_class : <overviewer 给的，仅供参考>
final_chart_class    : <T1.5 决议结果，dim-expert 用此值>
class_decision_branch: <A-existing / B-merge / B-new / C-no-candidate>
history_baseline     : <patterns/<final_chart_class>/*.md frontmatter 摘要>
counterexample_protocols: <历史 protocol 列表>
```
```

- [ ] **Step 2: spec-review subagent 审核**

dispatch tom subagent 验证：

验证 task 2 改动是否符合 spec `docs/tmp/2026-05-07_chart_class_user_decision_design.md` §3 + §4 + §5：
- §5.2bis 含完整 6 步骤 + 决议日志 schema + 错误处理矩阵 + spawn 注入示例
- §5.2 末尾段含 T1.5 引用
- 没有占位符 / TBD / 空段

如不符合，返回问题描述。

- [ ] **Step 3: 验证 grep**

Run: `grep -n "T1.5\|class_decision\|final_chart_class" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/SKILL.md`
Expected：能看到至少 8-10 处匹配（§3.2.2 + §5.2 + §5.2bis 多次提及）

---

## Task 3: SKILL.md §3.1 bootstrap + §6.4 写入崩溃 — 删除 _pending 引用

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/SKILL.md` 行 ~209-251（§3.1）+ ~565-575（§6.4）

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent 实施：

读 spec `docs/tmp/2026-05-07_chart_class_user_decision_design.md` §6 + §8.1。修改 SKILL.md：

**A. §3.1 bootstrap 步骤 1 目录结构**：找到 "patterns/_retired/" 那段（约 line 217-225），删除 `_pending` 相关条目（如果有），目录结构应仅保留：

```
patterns/
└── _retired/                       # 空目录，未来废弃规律的归宿
```

**B. §3.1 bootstrap 步骤 2 写入初始模板** — 找 chart_classes.md 的初始内容，确认它没有 `## proposed classes` 段。如有，删除。

**C. §6.4 写入崩溃恢复表** — 找有无 _pending 提及。如果 STEP 4 后处理提到 `patterns/_pending/`，删除该行。

如某段无相关引用，跳过该段，保留该 step 的其他改动。

- [ ] **Step 2: spec-review subagent 审核**

dispatch tom subagent 验证：

验证 SKILL.md 中已无 `_pending` / `proposed classes` / `aliases` 残留：

```bash
grep -n "_pending\|proposed classes\|aliases" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/SKILL.md
```

Expected：0 匹配。如有残留，返回具体行号供修复。

- [ ] **Step 3: 验证 grep**

Run: `grep -n "_pending\|proposed classes\|aliases" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/SKILL.md`
Expected：0 匹配

---

## Task 4: prompts/overviewer.md §1 角色描述补衔接说明

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/prompts/overviewer.md` 行 ~3-12（§1）

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent 实施：

修改 `.claude/skills/analyze-stock-charts/prompts/overviewer.md` §1 段（line 3 起，"## 1. 你是谁" 节内）：

在现有 §1 末尾追加一段（保留原内容不改）：

```markdown

> **v2.2 衔接说明**：你输出的 `dominant_chart_class` 不是最终落库使用的 class——lead 会在 T1.5 节点（你 completed 后、dim-expert spawn 前）协调 user 做决议（同名直接合并 / 选合并入既有 class / 新建）。最终落库 class 名（`final_chart_class`）由 lead 注入下游 dim-expert spawn prompt。你的职责仍是给出尽可能精确的视觉直觉分类。
```

不改 §6 / §7 同质性校验逻辑——overviewer 的 outlier_ratio 警告（warn 分支 SendMessage 给 lead）保持原状，lead 在 T1.5 内独立决定是否同时让 user 处理同质性问题。

- [ ] **Step 2: spec-review subagent 审核**

dispatch tom subagent 验证：

验证 task 4 改动符合 spec `docs/tmp/2026-05-07_chart_class_user_decision_design.md` §8.1 (overviewer 部分)：
- §1 末尾含 v2.2 衔接说明
- §6/§7 未改（overviewer 的 outlier 检查不改）
- 总改动应 ≤ 5 行

如不符合，返回问题。

---

## Task 5: prompts/synthesizer.md §5.1 / §5.2 / §3 / §4 重写

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/prompts/synthesizer.md` 行 ~9（§1 内 chart_class 写库 description）、行 ~63（§4 校验第 9 项）、行 ~68-99（§5.1 + §5.2 case 1/2）、行 ~204-205（§4.2 NEW 候选字段校验内 chart_class 一致性）、行 ~300（§7 自检列表第 10 项）

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent 实施：

读 spec `docs/tmp/2026-05-07_chart_class_user_decision_design.md` §5.2 + §8.1（synthesizer 部分）。修改 `.claude/skills/analyze-stock-charts/prompts/synthesizer.md`：

**A. §1 内 chart_class 写库 description**（约 line 9）替换：

旧：
```markdown
2. **chart_class 写库**：根据 overviewer 给的 dominant chart_class，把 finding 归入 `patterns/<class>/`；新 class 写入 `chart_classes.md` 的 `## proposed classes` 等 user 决议
```

新：
```markdown
2. **chart_class 写库**：直接用 spawn prompt 注入的 `final_chart_class`（lead 已在 T1.5 完成 user 决议），把 finding 归入 `patterns/<final_chart_class>/`。**不再做同义判断**——chart_class 决议已上移到 lead T1.5（详见 SKILL.md §5.2bis）
```

**B. §4 校验第 9 项**（约 line 63）替换：

旧：
```markdown
9. ✅ **chart_class 一致性**：finding 的 chart_class 必须与本次 batch 的 dominant_class 相同；outlier 图发现的 finding 标 chart_class=outlier_class（如有）
```

新：
```markdown
9. ✅ **chart_class 一致性**：finding 的 chart_class 必须等于 spawn prompt 注入的 `final_chart_class`（lead T1.5 决议结果）；outlier 图发现的 finding 仍标 chart_class=outlier_class（如有，由 dim-expert 标记）
```

**C. §5 chart_class 写库流程整段重写**（约 line 68 "## 5. chart_class 写库流程" 到 line 110 "### 5.3 跨 batch 累积..." 之前）：

旧 §5.1（同义判断）+ §5.2（writing 流程 case 1 / case 2）整段替换为：

```markdown
## 5. chart_class 写库流程

收到 4 个 dim-expert 完成信号 + devils-advocate 5 项校验通过后，直接用 spawn prompt 注入的 `final_chart_class` 写库（lead 已在 T1.5 完成同义判断 / user 决议）。

### 5.1 写入流程

对每条通过 §4 12 项校验的 finding：

- 写入 `patterns/<final_chart_class>/R-XXXX-<name>.md`（新 R 编号）；single-group finding（cross_group_diversity == false）与 cross-group finding 同目录准入主库
- 同步更新：
  - `_meta/charts_index.md`（per-chart_id 的 included_in_patterns 列）
  - `_meta/chart_classes.md` 中 `<final_chart_class>` 的 `patterns_count`（新增 N 条 finding 即 +N）+ `last_updated`

### 5.2 不再做的事（v2.2 移除）

以下职责已上移到 lead T1.5（详见 SKILL.md §5.2bis）：

- ❌ chart_class 同义判断（不再调 LLM 比对 active classes）
- ❌ aliases 维护（aliases 概念已消除）
- ❌ proposed classes 段写入（已消除）
- ❌ `patterns/_pending/<batch_id>/` 暂存（已消除）

如发现 spawn prompt 中的 `final_chart_class` 在 chart_classes.md 中不存在 → SendMessage 给 team-lead 报错（不强行写入主库），lead 修复或 abort。
```

**D. §3 必读资源**（约 line 30-46）— 找 chart_classes.md 引用，更新描述为"读决议后的 active classes（`## active classes` 段）"。

**E. §4.2 NEW 候选字段校验**（约 line 200-205）— 把 "chart_class 与本 batch 的 dominant_class 一致" 改为 "chart_class 与 spawn prompt 的 final_chart_class 一致"。

**F. §7 自检列表第 10 项**（约 line 300）— 同样把 "dominant_class" 改为 "final_chart_class"。

完成后 grep 验证：
```bash
grep -n "dominant_class\|aliases\|_pending\|proposed classes" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/synthesizer.md
```
Expected：0 匹配（chart_class 决议相关引用全清）。

- [ ] **Step 2: spec-review subagent 审核**

dispatch tom subagent 验证：

验证 task 5 改动符合 spec `docs/tmp/2026-05-07_chart_class_user_decision_design.md` §5.2 + §8.1（synthesizer 部分）：

- §1 description 改为"直接用 final_chart_class，不做同义判断"
- §5 整段重写为简化的写入流程
- §5.1 chart_class 同义判断整段删除（旧版 line 72-82 应不复存在）
- §5.2 case 2（_pending）整段删除
- §4 第 9 项 / §4.2 / §7 第 10 项中"dominant_class"全部改为"final_chart_class"
- grep 无残留

如不符合，返回问题。

- [ ] **Step 3: 验证 grep**

Run: `grep -n "dominant_class\|aliases\|_pending\|proposed classes" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/synthesizer.md`
Expected：0 匹配

Run: `grep -n "final_chart_class" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/synthesizer.md`
Expected：≥ 4 处匹配

---

## Task 6: 4 个 dim-expert prompts 批量更新（dominant → final）

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/prompts/phase-recognizer.md` 行 ~23
- Modify: `.claude/skills/analyze-stock-charts/prompts/resistance-cartographer.md` 行 ~24
- Modify: `.claude/skills/analyze-stock-charts/prompts/volume-pulse-scout.md` 行 ~24
- Modify: `.claude/skills/analyze-stock-charts/prompts/launch-validator.md` 行 ~26

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent 实施：

对 4 个 dim-expert prompt 应用相同改动模式。每个 prompt §3 必读资源表中的"本次 run 元信息"行格式如下：

旧（4 个 prompt 都是同样格式）：
```markdown
| 本次 run 元信息 | spawn prompt 注入 | chart_paths / run_id / run_dir / dominant_chart_class |
```

新：
```markdown
| 本次 run 元信息 | spawn prompt 注入 | chart_paths / run_id / run_dir / final_chart_class（lead T1.5 决议结果，取代旧 dominant_chart_class） |
```

每个 prompt 在 §3 表格末尾追加一段说明（每个 prompt 都加同样的内容）：

```markdown

> **v2.2 衔接说明**：`final_chart_class` 由 lead 在 T1.5 完成 user 决议后注入（详见 SKILL.md §5.2bis）。如果是合并入既有 class（branch B-merge / A），你能在 spawn prompt 的 `history_baseline` 字段拿到该 class 的历史规律 baseline + counterexample protocols；如果是新建 class（branch B-new / C），baseline 为空但状态明确（不是"还没决议"的 ambiguous）。
```

完成 4 个 prompt 后 grep 验证：
```bash
grep -n "dominant_chart_class" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/phase-recognizer.md /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/resistance-cartographer.md /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/volume-pulse-scout.md /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/launch-validator.md
```
Expected：0 匹配

```bash
grep -c "final_chart_class" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/phase-recognizer.md
```
Expected：≥ 2 处

- [ ] **Step 2: spec-review subagent 审核**

dispatch tom subagent 验证：

对 4 个 dim-expert prompt 检查：
- §3 表格中"本次 run 元信息"行已用 final_chart_class
- §3 表格末尾追加了 v2.2 衔接说明
- 4 个 prompt 改动**完全一致**（除文件路径外）
- grep 无 dominant_chart_class 残留

如不符合，返回具体 prompt + 问题。

- [ ] **Step 3: 验证 grep**

Run:
```bash
grep -rn "dominant_chart_class" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/
```
Expected：仅 overviewer.md 仍有引用（因为它是输出 dominant_chart_class 的角色，保留）

---

## Task 7: references/02_memory_system.md §A.5 重写 + 全文删 _pending 引用

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/references/02_memory_system.md` 行 ~70（§A.1 目录结构）+ ~133-176（§A.5 chart_classes.md schema）+ ~691-696（§D.7 演化规则）

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent 实施：

读 spec `docs/tmp/2026-05-07_chart_class_user_decision_design.md` §6 + §8.1（02 memory_system 部分）。修改 `.claude/skills/analyze-stock-charts/references/02_memory_system.md`：

**A. §A.1 顶层目录结构**（约 line 52-95）— 找到 `patterns/` 下的 `_pending/` 行，删除：

旧：
```
│   │   ├── _pending/                   ← batch 等待 user 决议新 class 时暂存
```

整行删除（连同前后逗号 / 缩进对齐）。

**B. §A.5 chart_classes.md schema 整段重写**（约 line 133-176）替换为：

```markdown
### A.5 `_meta/chart_classes.md`（class registry）

**用途**：维护已注册的 chart_class 列表 + descriptions。lead 在每次 batch 的 T1.5 节点（详见 SKILL.md §5.2bis）读它做合并候选检索；user 在 AskUserQuestion 中决议；synthesizer 写库时直接用 `final_chart_class`，不读 chart_classes.md 做同义判定。

**v2.2 schema 变化**：
- ❌ 移除 `aliases` 字段（性能 cache 价值随库扩大递减；user 决议替代）
- ❌ 移除 `## proposed classes` 段（决议同步落地，无需暂存）
- ✅ 新增 `## decision history` 段（跨 run 审计追溯 user 决议历史）

**新 schema 模板**：

```markdown
# Chart Classes Registry

> 本 batch 视觉类别（chart_class）的活跃注册表。每个 chart_class 对应 `patterns/<class_name>/` 一个目录。
> 决议由 user 在每次 batch 的 T1.5 节点完成（lead 协调），synthesizer 写库时直接使用 final_chart_class。

## active classes

| class_name | description | first_seen_run | patterns_count | last_updated |
|---|---|---|---|---|
| long_base_breakout | 宽幅区间内的低波动横盘 ≥40 日后突破 | 2026-05-06_112923_0bea3 | 5 | 2026-05-07_142311 |
| v_reversal | 深 V 反转后上涨 | 2026-05-10_xxxxxx_xxxxx | 3 | 2026-05-15_xxxxxx |

## decision history

> 每次 T1.5 决议追加一行（含分支、最终结果、所属 run）。供审计与跨 run 追溯用。

| run_id | dominant_class | final_class | branch | user_choice |
|---|---|---|---|---|
| 2026-05-06_112923_0bea3 | long_consolidation_breakout | long_base_breakout | B-merge | merge_into |
```

**字段语义**：
- `class_name`：chart_class 主名（unique）
- `description`：1 行描述（lead 在新建分支时用 first_impression 概括）
- `first_seen_run`：首次出现的 runId
- `patterns_count`：当前 class 下的 pattern 数（仅 active / partially-validated / validated 状态）
- `last_updated`：最近一次 patterns_count 变更或 last_updated 触碰的时间戳
- decision history `branch`：A-existing / B-merge / B-new / C-no-candidate
- decision history `user_choice`：new / merge_into（branch A / C 时为空，notification_only）

**演化规则**：
- 新 class 由 lead 在 T1.5 决议 (B-new / C 分支) 后追加到 `## active classes`，写入即生效
- 现有 class 的 `patterns_count` 由 synthesizer 在 §5 写库后增量更新
- decision history 由 lead 在每次 T1.5 完成时追加 1 行
- class 不引入自动拆分机制（user 想拆分时手动改本文件 + 移动 patterns 子目录文件）
```

**C. §D.7 演化规则**（约 line 691-696）— 找有无提及 aliases / proposed classes / _pending 的段，整段重写为：

旧：
```markdown
- 同义于已有 class → 加入该 class 的 aliases，本次 batch 归该 class
- 不同义 → 写入 `chart_classes.md` 的 `## proposed classes` 段，**user 决议是否新增**
- 在 user 决议前，本次 batch 的 patterns 暂存于 `patterns/_pending/<batch_id>/`，决议后归档
```

新：
```markdown
- chart_class 决议由 lead 在 T1.5 完成（详见 SKILL.md §5.2bis）：
  - 同名命中（A）→ 直接合并入该 class
  - LLM 推荐合并候选（B）→ user 选新建或合并
  - 无候选（C）→ 直接新建
- patterns 直接写入 `patterns/<final_chart_class>/`，无 `_pending/` 暂存
- aliases 概念已消除（v2.2）
```

**D. §E STEP 流程**（约 line 372 注释段、search "synthesizer 在 LLM 语义聚类后用 cluster 名作为正式 key"）— 找到 v2 描述提到 aliases 的段落，删除 aliases 提及，加一句 "lead T1.5 已完成 chart_class 决议；synthesizer 直接用 spawn prompt 注入的 final_chart_class，不参与同义判断"。

完成后 grep 验证：
```bash
grep -n "_pending\|aliases\|proposed classes" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/references/02_memory_system.md
```
Expected：0 匹配

- [ ] **Step 2: spec-review subagent 审核**

dispatch tom subagent 验证：

验证 task 7 改动符合 spec `docs/tmp/2026-05-07_chart_class_user_decision_design.md` §6 + §8.1（02 部分）：
- §A.5 schema 已重写（新版含 active classes + decision history 两段表格）
- §A.1 目录结构无 `_pending/` 行
- §D.7 演化规则已更新
- §E 注释段已加 lead T1.5 描述
- grep 无残留

如不符合，返回具体段 + 问题。

- [ ] **Step 3: 验证 grep**

Run:
```bash
grep -n "_pending\|aliases\|proposed classes" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/references/02_memory_system.md
```
Expected：0 匹配

---

## Task 8: references/03_team_architecture.md §3.1 工作流图 + §4.3 权限矩阵

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/references/03_team_architecture.md` 行 ~108-148（§3.1 mermaid 流程图）+ ~243-256（§4.3 权限矩阵）

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent 实施：

读 spec `docs/tmp/2026-05-07_chart_class_user_decision_design.md` §2.1（架构总览）+ §8.1（03 部分）。修改 `.claude/skills/analyze-stock-charts/references/03_team_architecture.md`：

**A. §3.1 Mermaid 流程图** — 在 T1 (overviewer) 节点之后、T2-T5 节点之前插入 T1.5 决议节点。具体在 mermaid 内：

找到形如：
```
overviewer --> phase-recognizer
overviewer --> resistance-cartographer
...
```

改为：
```
overviewer --> lead_t1_5[lead T1.5: chart_class 决议<br/>同名 / 合并 / 新建]
lead_t1_5 --> phase-recognizer
lead_t1_5 --> resistance-cartographer
lead_t1_5 --> volume-pulse-scout
lead_t1_5 --> launch-validator
```

并在 mermaid 外加一段：

```markdown
> **T1.5 决议节点**（v2.2 新增，**不进入 TaskCreate**）：lead 在 overviewer 完成后协调 user 做 chart_class 决议。详见 SKILL.md §5.2bis。
```

**B. §4.3 权限矩阵** — 找到权限表（class 写入 / 同义判断 / 历史 baseline 注入 等行），调整：

- 新增 lead 一行 "chart_class 决议（T1.5）" → ✅
- 调整 synthesizer 行 "chart_class 同义判断" → ❌（v2.2 移除，已上移到 lead）
- synthesizer 行 "chart_class 写库（用 final_chart_class）" → ✅ 保留

具体格式参考已有矩阵的列对齐。

完成后 grep 验证：
```bash
grep -n "T1.5\|chart_class 决议" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/references/03_team_architecture.md
```
Expected：≥ 3 处匹配

- [ ] **Step 2: spec-review subagent 审核**

dispatch tom subagent 验证：

验证 task 8 改动符合 spec `docs/tmp/2026-05-07_chart_class_user_decision_design.md` §2.1 + §8.1（03 部分）：
- §3.1 mermaid 含 lead_t1_5 节点 + T1.5 决议描述段
- §4.3 权限矩阵 lead 加 chart_class 决议权限、synthesizer 移除"同义判断"权限
- grep 能找到至少 3 处 T1.5 引用

如不符合，返回问题。

---

## Task 9: references/01_analysis_dimensions.md 删 dominant / proposed classes 引用

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/references/01_analysis_dimensions.md` 行 494（chart_class 字段示例）+ 行 512（chart_class 写库描述）

- [ ] **Step 1: implementer subagent 执行**

dispatch tom subagent 实施：

修改 `.claude/skills/analyze-stock-charts/references/01_analysis_dimensions.md`：

**A. line 494** — 找：
```markdown
    chart_class: <由 overviewer 给的 dominant class>
```
替换为：
```markdown
    chart_class: <lead T1.5 决议后的 final_chart_class，由 spawn prompt 注入>
```

**B. line 512** — 找：
```markdown
6. **chart_class 写库**（v2 新增）：根据 overviewer 给的 dominant chart_class 把 finding 归入 `patterns/<class>/`；新 class 写 `chart_classes.md` 的 `## proposed classes` 等 user 决议
```
替换为：
```markdown
6. **chart_class 写库**（v2.2 修订）：直接用 spawn prompt 注入的 `final_chart_class`（lead 在 T1.5 完成 user 决议），把 finding 归入 `patterns/<final_chart_class>/`。无 proposed classes 段、无 _pending 暂存。详见 SKILL.md §5.2bis
```

完成后 grep 验证：
```bash
grep -n "dominant\|proposed classes\|_pending\|aliases" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/references/01_analysis_dimensions.md
```
Expected：0 匹配（如果还有其他位置漏改，列出来给下个 task）

- [ ] **Step 2: spec-review subagent 审核**

dispatch tom subagent 验证：

验证 task 9 改动：
- line 494 / 512 已替换
- grep 无残留

如不符合，返回问题。

---

## Task 10: 全局一致性 audit

**Files:** 仅读

- [ ] **Step 1: 执行全局 grep**

Run:
```bash
echo "=== 检查 1: dominant_chart_class（应仅在 overviewer.md 中保留）==="
grep -rn "dominant_chart_class" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/

echo ""
echo "=== 检查 2: aliases（应 0 匹配）==="
grep -rn "aliases" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/

echo ""
echo "=== 检查 3: _pending（应 0 匹配）==="
grep -rn "_pending" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/

echo ""
echo "=== 检查 4: proposed classes（应 0 匹配）==="
grep -rn "proposed classes\|## proposed" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/

echo ""
echo "=== 检查 5: final_chart_class（应在 SKILL.md / 4 dim-expert / synthesizer 都有）==="
grep -rln "final_chart_class" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/

echo ""
echo "=== 检查 6: T1.5 决议引用（应在 SKILL.md / 03 team_architecture 中至少各 1 处）==="
grep -rn "T1.5\|chart_class 决议" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/ | head -10
```

Expected：
- 检查 1：仅 overviewer.md 出现 `dominant_chart_class`
- 检查 2/3/4：0 匹配
- 检查 5：SKILL.md / synthesizer.md / 4 dim-expert prompts / 02 memory_system / 03 team_architecture 都至少 1 处
- 检查 6：≥ 5 处匹配

- [ ] **Step 2: 全局 review subagent 检查内部一致性**

dispatch tom subagent 检查：

读 spec `docs/tmp/2026-05-07_chart_class_user_decision_design.md` 全文。
扫描以下 9 个文件，检查决议流程描述的一致性：

- `.claude/skills/analyze-stock-charts/SKILL.md`
- `.claude/skills/analyze-stock-charts/prompts/overviewer.md`
- `.claude/skills/analyze-stock-charts/prompts/phase-recognizer.md`
- `.claude/skills/analyze-stock-charts/prompts/resistance-cartographer.md`
- `.claude/skills/analyze-stock-charts/prompts/volume-pulse-scout.md`
- `.claude/skills/analyze-stock-charts/prompts/launch-validator.md`
- `.claude/skills/analyze-stock-charts/prompts/synthesizer.md`
- `.claude/skills/analyze-stock-charts/references/02_memory_system.md`
- `.claude/skills/analyze-stock-charts/references/03_team_architecture.md`

具体检查项：
1. T1.5 在 SKILL.md §5.2bis 描述与 03 team_architecture mermaid 一致
2. final_chart_class 字段在 SKILL.md 注入示例 + dim-expert prompt §3 表 + synthesizer 校验描述中**完全同名**
3. decision_branch 4 个值（A-existing / B-merge / B-new / C-no-candidate）在 SKILL.md / 02 memory_system schema 中一致
4. 各文件无相互矛盾或过时的 v2.0/v2.1 残留描述
5. 错误处理矩阵（SKILL.md §5.2bis）与 spec §7 一致

返回：发现的不一致列表（含文件名 + 行号 + 问题描述）。如完全一致，返回 "✅ all consistent"。

- [ ] **Step 3: 修复（如有）**

如 step 2 返回不一致，dispatch implementer subagent 修复每条；fix 完后回到 step 1 重跑 grep。

直到 step 1 / step 2 都通过为止。

---

## Task 11: 单 commit

**Files:** 仅 git

- [ ] **Step 1: git status 检查**

Run: `git status`
Expected：仅以下文件 modified：
- `.claude/skills/analyze-stock-charts/SKILL.md`
- `.claude/skills/analyze-stock-charts/prompts/overviewer.md`
- `.claude/skills/analyze-stock-charts/prompts/synthesizer.md`
- `.claude/skills/analyze-stock-charts/prompts/phase-recognizer.md`
- `.claude/skills/analyze-stock-charts/prompts/resistance-cartographer.md`
- `.claude/skills/analyze-stock-charts/prompts/volume-pulse-scout.md`
- `.claude/skills/analyze-stock-charts/prompts/launch-validator.md`
- `.claude/skills/analyze-stock-charts/references/01_analysis_dimensions.md`
- `.claude/skills/analyze-stock-charts/references/02_memory_system.md`
- `.claude/skills/analyze-stock-charts/references/03_team_architecture.md`

如有非本 plan 改动的文件出现，user 应先决定（stash / commit 单独 / 还原）后再继续。

- [ ] **Step 2: git diff review**

Run: `git diff .claude/skills/analyze-stock-charts/`

人工 review 关键点：
- §5.2bis 新增完整
- synthesizer §5.1/§5.2 case 2 已删除（不是注释掉）
- §A.5 schema 完整重写（无残留旧 schema）
- 4 个 dim-expert 改动一致

- [ ] **Step 3: commit**

Run:
```bash
git add .claude/skills/analyze-stock-charts/
git commit -m "$(cat <<'EOF'
refactor(skill): v2.1 → v2.2 chart_class user-decision flow

把 chart_class 同义判断 / 新建 / 合并的决策权前移到 T1 (overviewer) 完成后 + T2-T5 (dim-expert) spawn 前的 lead T1.5 决议节点。user 显式决议（lead 协调 + LLM 推荐辅助）。

主要变化：
- SKILL.md 新增 §5.2bis "T1.5 chart_class 决议" 节（lead 内部步骤，不进 TaskCreate）
- §3.2.2 chart_class 流程重写（lead 三分支处理：同名 / 有候选 / 无候选）
- synthesizer §5 整段重写为简化的"直接用 final_chart_class"流程
- 4 个 dim-expert §3 输入表 dominant_chart_class → final_chart_class
- 02 §A.5 chart_classes.md schema 重写（移除 aliases / proposed classes，新增 decision history）
- 03 §3.1 mermaid 工作流加 lead_t1_5 节点
- 删除整个 _pending / aliases / proposed classes 概念

设计 spec：docs/tmp/2026-05-07_chart_class_user_decision_design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: git status 验证**

Run: `git status`
Expected：working tree clean（仅 docs/tmp/ 下的 spec / plan 文档可能 untracked，正常）

- [ ] **Step 5: git log 验证**

Run: `git log --oneline -5`
Expected：最近 1 行是 `refactor(skill): v2.1 → v2.2 chart_class user-decision flow`

---

## 完成判定

全 11 个 task 完成 + Task 10 audit grep 全绿 + Task 11 commit 成功 → plan 实施完成。

后续（不在本 commit）：
- 现有 `_pending/2026-05-06_112923_0bea3/` 下的 2 条 pending pattern 由 user 手动决议（迁移到 active class 或废弃）
- `docs/explain/analyze_stock_charts_logic_analysis.md` 用户文档更新（事后单独 commit）
- 本 plan + spec 文档（`docs/tmp/2026-05-07_chart_class_user_decision_*.md`）可在事后清理（属一次性 plan）

---

## 执行模式建议

按用户偏好 **subagent-driven 模式**：

每 task 流程：
1. dispatch implementer subagent (`tom`) — 拿 spec + 本 task 描述执行修改
2. dispatch spec-review subagent (`tom`) — 验证改动符合 spec
3. 如 review 不通过 → 回到 step 1 with 反馈；通过 → 进下一 task
4. Task 10 多一步：global review subagent 检查跨文件一致性

每 task 估时（含 implementer + review 两轮）：
- Task 1-2: 30 min（核心 SKILL.md 改动）
- Task 3-4: 15 min（小改动）
- Task 5: 30 min（synthesizer 删较多）
- Task 6: 15 min（4 prompt 同模式批改）
- Task 7: 45 min（02 memory_system 重写最重）
- Task 8: 20 min
- Task 9: 10 min
- Task 10: 20 min（audit）
- Task 11: 10 min（commit）

**总计估时**：约 3.5-4 hr，符合 spec §8.2 估算。
