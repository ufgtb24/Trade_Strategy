# Patch: phase-recognizer §2 model + 7 prompts §2 model audit

> **Patch type**：follow-up consistency patch
> **Apply after**：主 commit `skill v2 → v2.1 cleanup` 完成
> **Status**：待执行
> **Estimate**：~30 min（含 grep 审计 + 1-2 行编辑）
> **Single commit**：`fix(skill): align dim-expert §2 model recommendation with SKILL.md model table`

---

## 背景：为什么需要这个 patch

主 plan `2026-05-07_skill_v2_two_fixes_plan.md` 的 Task 1 改了 SKILL.md §5.1 模型表（mixed tier 中 phase-recognizer 从 opus 降到 sonnet）。但**主 plan 漏了一步**：

每个 dim-expert prompt 自己的 `§2 推荐模型` 行也声明了模型推荐。如果 SKILL.md 模型表说 sonnet，但 prompt §2 说"必须用 opus"，会出现：

1. **Agent 看到自己的 prompt 说"必须 opus"，运行时却被 spawn 为 sonnet**——可能行为困惑
2. **未来开发者读 prompt 时 §2 信息过时**——错误推断"必须 opus"
3. **prompt §2 的 rationale 已不成立**（如 phase-recognizer 现写"前置过滤错了会浪费下游全部算力，必须用 opus"，peer 化后此理由消失）

---

## 修复目标

让每个 prompt 的 §2 推荐模型行**与 SKILL.md 模型表一致**，且 rationale 反映当前角色（peer dim-expert）。

---

## Task 1：审计当前状态（先看再改）

**Files**：6 prompts + SKILL.md（仅读）

**Steps**：

- [ ] **Step 1：读 SKILL.md §5.1 模型表**

  Run：`grep -A20 "^### 5.1\\|^## 5.1" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/SKILL.md`

  记录每个 agent 在 opus / mixed / sonnet 三档的 model：

  | name | opus tier | mixed tier | sonnet tier |
  |---|---|---|---|
  | overviewer | (填) | (填) | (填) |
  | phase-recognizer | (填) | (填) | (填) |
  | resistance-cartographer | (填) | (填) | (填) |
  | volume-pulse-scout | (填) | (填) | (填) |
  | launch-validator | (填) | (填) | (填) |
  | devils-advocate | (填) | (填) | (填) |
  | synthesizer | (填) | (填) | (填) |

- [ ] **Step 2：grep 各 prompt §2 推荐模型行**

  Run：
  ```bash
  for f in /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/*.md; do
    echo "=== $(basename $f) ==="
    grep -A1 "推荐模型" "$f" | head -3
  done
  ```

  记录每个 prompt 的 §2 model 推荐 + rationale。

- [ ] **Step 3：识别不一致项**

  对比 Step 1 表格 vs Step 2 输出。规则：

  prompt §2 应该推荐**该 agent 在「最常用 tier」(默认 opus tier) 的 model**，且不应说"必须 X"——只是推荐。可写"opus 推荐；mixed/sonnet tier 也支持"。

  特别关注（已知问题）：
  - phase-recognizer §2 当前写 "claude-opus-4-7（前置过滤错了会浪费下游全部算力，必须用 opus）" — 此 rationale 已不成立，必须改

  其他可能不一致：
  - 各 dim-expert 的 §2 model 是否与 SKILL.md mixed/sonnet 列一致
  - rationale 是否提到"必须"等绝对化措辞

**Acceptance Criteria**：
- 列出所有不一致项（agent 名 + 当前 §2 内容 + 建议改写）

---

## Task 2：修复 phase-recognizer §2（已知问题）

**Files**：
- Modify: `.claude/skills/analyze-stock-charts/prompts/phase-recognizer.md`

**Steps**：

- [ ] **Step 1：定位当前 §2**

  Run：`grep -n "推荐模型" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/phase-recognizer.md`

- [ ] **Step 2：修改 §2 推荐模型行**

  旧（已知）：
  ```markdown
  - 推荐模型：**claude-opus-4-7**（前置过滤错了会浪费下游全部算力，必须用 opus）
  ```

  新：
  ```markdown
  - 推荐模型：**claude-opus-4-7**（opus tier 默认；mixed / sonnet tier 用 claude-sonnet-4-6 — peer dim-expert 不涉及关键决策，sonnet 即可）
  ```

  注意：
  - 默认推荐仍是 opus（与 opus tier 一致），不要把默认改 sonnet
  - 删除"必须用 opus"的绝对化措辞 + "前置过滤错了..."的过期 rationale
  - 加上 mixed/sonnet tier 的 sonnet fallback 说明

- [ ] **Step 3：grep 验证修改**

  Run：`grep -A2 "推荐模型" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/phase-recognizer.md`
  Expected：无 "必须用 opus" 字样；含 "mixed / sonnet" 措辞

**Acceptance Criteria**：
- §2 推荐模型行已无 "必须" 措辞
- §2 推荐模型行含 mixed/sonnet tier 的 sonnet fallback 说明
- rationale 反映 peer dim-expert 角色

---

## Task 3：修复其他 prompt §2（按 Task 1 审计结果）

**Files**：
- Modify（按需）：6 个 prompts 中**有不一致**的（phase-recognizer 已在 Task 2 处理，跳过）

**Steps**：

- [ ] **Step 1：对每个 Task 1 标记为不一致的 prompt 应用相同模式**

  统一模板：
  ```markdown
  - 推荐模型：**<opus tier 的 model>**（opus tier 默认；mixed / sonnet tier 用 <对应 model> — <一句话 rationale>）
  ```

  例如 resistance-cartographer 当前若是 `claude-sonnet-4-6（视角清晰、判断标准化程度高）`：

  新：
  ```markdown
  - 推荐模型：**claude-opus-4-7**（opus tier 默认；mixed / sonnet tier 用 claude-sonnet-4-6 — 视角清晰、判断标准化程度高）
  ```

  特别注意 overviewer：
  - chart_class 自动命名需要强视觉分类能力
  - opus tier + mixed tier 都用 opus（不降 sonnet）
  - 仅 sonnet tier 用 sonnet
  - rationale 应保留"chart_class 自动命名需视觉分类能力"

- [ ] **Step 2：synthesizer / advocate 特别处理**

  这两个非 dim-expert 角色的 §2 模型推荐：
  - 都是 opus tier + mixed tier 用 opus（关键写库 / 反方质疑工作）
  - sonnet tier 才降 sonnet
  - rationale 应反映"语义判断 / 整合写库高 stakes"

- [ ] **Step 3：每改一个文件 grep 验证**

  Run：`grep -A2 "推荐模型" <file>`
  Expected：与 SKILL.md §5.1 模型表的 opus tier 列一致；含 mixed/sonnet fallback 说明

**Acceptance Criteria**：
- 6 prompts §2 推荐模型行均与 SKILL.md §5.1 一致
- 无 "必须 X" 等绝对化措辞
- 各 rationale 反映当前角色（peer dim-expert / 关键判断 等）

---

## Task 4：最终全局一致性校验

**Files**：仅读

**Steps**：

- [ ] **Step 1：grep 全局检查"必须"措辞残留**

  Run：`grep -rn "必须用 opus\\|必须用 sonnet\\|must use opus\\|must use sonnet" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/`
  Expected：无匹配

- [ ] **Step 2：grep 检查所有 §2 推荐模型行的 model**

  Run：
  ```bash
  for f in /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/prompts/*.md; do
    model=$(grep "推荐模型" "$f" | grep -oE "claude-(opus|sonnet)-[0-9-]+" | head -1)
    echo "$(basename $f): $model"
  done
  ```

  对比 SKILL.md §5.1 opus tier 列，每行都应一致。

- [ ] **Step 3：spot-check：mixed tier 中 phase-recognizer 是否真的 sonnet**

  Run：`grep -A30 "^### 5.1\\|^## 5.1" /home/yu/PycharmProjects/Trade_Strategy/.claude/skills/analyze-stock-charts/SKILL.md | grep "phase-recognizer"`
  Expected：能看到 `phase-recognizer | tom | ... | claude-opus-4-7 | claude-sonnet-4-6 | claude-sonnet-4-6 |` 这种格式

**Acceptance Criteria**：
- 无 "必须 X" 措辞
- 7 prompt 的 §2 model 与 SKILL.md §5.1 opus tier 列一致
- mixed tier phase-recognizer 确认是 sonnet

---

## Task 5：Single commit

**Files**：所有 Task 2 / 3 改的文件（最多 7 个 prompts）

**Steps**：

- [ ] **Step 1：git status 检查**

  Run：`git status`
  Expected：仅 prompts/*.md 改动（无其他文件）

- [ ] **Step 2：git diff review**

  Run：`git diff .claude/skills/analyze-stock-charts/prompts/`
  人工 review：
  - §2 model 行修改正确
  - 无意外删除其他段
  - rationale 已反映当前角色

- [ ] **Step 3：commit**

  Run：
  ```bash
  git add .claude/skills/analyze-stock-charts/prompts/
  git commit -m "$(cat <<'EOF'
  fix(skill): align dim-expert §2 model recommendation with SKILL.md model table

  Follow-up to "skill v2 → v2.1 cleanup" commit.

  问题：主 commit 改了 SKILL.md §5.1 模型表（mixed tier phase-recognizer
  从 opus 降到 sonnet），但 prompts/*.md 各自的 §2 推荐模型行未同步更新。
  特别地，phase-recognizer §2 仍写"必须用 opus（前置过滤错了会浪费下游
  全部算力）"——peer 化后此 rationale 已不成立。

  本 patch:
  - 删除 §2 中"必须用 X"的绝对化措辞
  - 各 prompt §2 model 与 SKILL.md §5.1 opus tier 列对齐
  - 加 mixed/sonnet tier 的 fallback 说明
  - phase-recognizer §2 rationale 反映 peer 角色（不再是 gatekeeper）

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

- [ ] **Step 4：git status 验证**

  Run：`git status`
  Expected：working tree clean

**Acceptance Criteria**：
- 单 commit 完成
- working tree clean
- commit message 含问题描述 + patch 内容

---

## 完成后处理

此 patch 文档可删除（属 docs/tmp/ 一次性 plan）：

```bash
rm docs/tmp/2026-05-07_skill_v2_phase_recognizer_model_patch.md
```

---

## 与主 commit 的关系

- **主 commit**：`refactor(skill): v2 → v2.1 cleanup (5 fixes integrated)` — 5 个修复整合
- **本 patch commit**：`fix(skill): align dim-expert §2 model recommendation` — 一致性补丁

git history 上这两个 commit 是父子关系：

```
* fix(skill): align dim-expert §2 model recommendation  ← 本 patch
* refactor(skill): v2 → v2.1 cleanup (5 fixes integrated)  ← 主 commit
* (主 commit 之前的状态)
```

如需回滚：单独 revert 本 patch（不影响主 commit）；或一起 revert（连主 commit 一起回滚）。

---

## 执行模式

可由 subagent-driven 模式执行（全是 markdown 编辑）。Task 1 审计 → Task 2/3 修复 → Task 4 校验 → Task 5 commit，每 task dispatch implementer + spec review。

或 inline 执行（半小时内可完成）。
