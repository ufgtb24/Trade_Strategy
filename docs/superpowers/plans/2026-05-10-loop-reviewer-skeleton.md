# Loop + Reviewer Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the minimal file skeleton for a self-iterative thinking loop — main session iterates on a design, an isolated reviewer subagent gates approval — and prepare the first concrete task (multi-BO architecture selection) so the user can launch it via ralph-loop.

**Architecture:** Three files per task directory: `prompt.md` (procedural body — main session reads each round, cross-task reusable), `reviewer_prompt.md` (devil's-advocate critic instructions with universal 8-axis rubric, cross-task reusable), `question.md` (task-specific original problem). Plus `design.md` as the iterating artifact and `reviews/` as the cumulative critique log. ralph-loop drives the main-session iterations; each round the main session dispatches a fresh `Agent` subagent (`subagent_type: tom`) with the reviewer prompt — this gives complete context isolation. Approval flows through two layers: reviewer writes `VERDICT: APPROVED`, main session emits `<promise>APPROVED</promise>`, ralph-loop's stop hook detects the literal tag and exits.

**Tech Stack:** ralph-loop plugin (already installed at `~/.claude/plugins/cache/claude-plugins-official/ralph-loop/1.0.0/`), Claude Code `Agent` tool with `tom` subagent, plain markdown files, `.gitignore`. No new code dependencies.

Spec: `docs/research/loop_reviewer_design.md`

---

## File Structure

Files to create in `/home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/`:

| Path | Responsibility |
|---|---|
| `prompt.md` | Procedural template the main session re-reads each iteration. Cross-task reusable. |
| `reviewer_prompt.md` | Devil's-advocate critic instructions + 8-axis evaluation rubric. Cross-task reusable. |
| `question.md` | The user's original problem and constraints. Task-specific. |
| `design.md` | The iterating artifact — main session's current best answer. Empty on first iteration. |
| `reviews/` | Directory accumulating `review_NNN.md` files — reviewer's cross-iteration memory. |
| `reference.png` (optional) | Visual reference, copied from user's `prompts/` if applicable. |

Files to modify:

| Path | Change |
|---|---|
| `.gitignore` | Add `docs/tmp/loop/` so iteration artifacts stay out of git. |

The `prompt.md` and `reviewer_prompt.md` files placed under the task directory belong to the cross-task skeleton — the convention is "the task directory carries everything needed to run that task". When a second task is created later, copy those two files into the new task directory.

---

### Task 1: Set up directory structure and gitignore

**Files:**
- Create dir: `/home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/reviews/`
- Modify: `/home/yu/PycharmProjects/Trade_Strategy/.gitignore`

- [ ] **Step 1: Create the task directory hierarchy**

Run:
```bash
mkdir -p /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/reviews
```

- [ ] **Step 2: Verify directory exists**

Run:
```bash
ls -la /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture
```

Expected: lists the `reviews/` subdirectory (with no other files yet).

- [ ] **Step 3: Add `docs/tmp/loop/` to .gitignore (idempotent)**

Run:
```bash
grep -qxF 'docs/tmp/loop/' /home/yu/PycharmProjects/Trade_Strategy/.gitignore || echo 'docs/tmp/loop/' >> /home/yu/PycharmProjects/Trade_Strategy/.gitignore
```

- [ ] **Step 4: Verify gitignore takes effect**

Run:
```bash
git -C /home/yu/PycharmProjects/Trade_Strategy check-ignore -v docs/tmp/loop/multi-bo-architecture/probe.md
```

Expected output: shows the matching .gitignore line and the path. If output is empty, the rule is not picking up the path — re-check Step 3.

---

### Task 2: Write `prompt.md` (cross-task main-session procedural template)

**Files:**
- Create: `/home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/prompt.md`

- [ ] **Step 1: Write the file with this exact content**

```markdown
# Self-Iterative Thinking Loop — Main Session Prompt

You are in a self-iterative thinking session powered by ralph-loop. Each iteration, this same prompt is fed back to you. Your previous work persists in files. A reviewer subagent — running in fully isolated context — critiques your output every round. The reviewer is your only gate to exit; you cannot self-approve.

## Your task directory

Absolute path: `/home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture`

It contains:

- `question.md` — the user's original question and constraints. **Re-read this every iteration**; it is the only authoritative source of what you are solving.
- `design.md` — your own current best answer (overwritten each round). Empty on first iteration.
- `reviews/review_NNN.md` — accumulated reviewer critiques (3-digit zero-padded, sortable). The highest-numbered file = the round you must respond to next.
- `reviewer_prompt.md` — the prompt template you must pass to the reviewer subagent every round.
- `reference.png` (optional) — visual reference; use the Read tool to view if it exists.
- `notes.md` (optional) — your own scratch space; the reviewer does not read this.

## Per-iteration procedure

1. **Read `question.md`.** Treat it as authoritative. Do not let your own previous framings substitute for the user's stated question.
2. **Read `design.md`.**
   - If it does not exist or is empty, this is iteration 1. Your job is to produce the first complete design proposal grounded in `question.md`. The first version is not expected to be perfect; it is the seed for review.
   - Otherwise, this is your starting position from last round.
3. **Read every file in `reviews/`** (sorted by name). The highest-numbered file is the most recent critique; the others are your reviewer's accumulated memory across earlier rounds.
4. **Think and rewrite `design.md`.** Overwrite, do not append. Address every objection in the latest review either by revising the design or by explicitly explaining (inside `design.md`) why the objection is invalid. Do not silently drop objections — the reviewer will notice on cross-iteration consistency.
5. **Dispatch the reviewer subagent** using the `Agent` tool:
   - `subagent_type`: `tom`
   - `description`: short label, e.g. `"Reviewer iter N"`
   - `prompt`: the full content of `reviewer_prompt.md` (read it from the task directory) PLUS this line appended at the end:
     `TASK DIRECTORY: /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture`
   The reviewer will write a new `reviews/review_NNN.md` file and return.
6. **Read the new review file** the reviewer just produced (highest-numbered file in `reviews/`). Locate the line beginning with `VERDICT:`.
7. **Decide based on the VERDICT line:**
   - `VERDICT: APPROVED` → output exactly: `<promise>APPROVED</promise>`. The angle brackets and exact word `APPROVED` are required; ralph-loop's stop hook matches this literal tag.
   - `VERDICT: OBJECTIONS_REMAIN` → end your turn normally. Do NOT emit the promise. The loop will feed this prompt back next round.
   - No `VERDICT:` line found, or the review file does not exist (reviewer crashed) → log the anomaly to `notes.md` and end your turn without emitting the promise. Treat as `OBJECTIONS_REMAIN` by default.

## Critical integrity rules

- **Never fabricate a verdict.** Only emit `<promise>APPROVED</promise>` if a fresh review file you just generated literally contains `VERDICT: APPROVED`.
- **Never invent a review.** If the reviewer subagent fails to produce a file, log to `notes.md` and end the turn — the next round will retry. Do not write a fake review yourself.
- **No false promises to escape the loop.** Even if max-iterations is approaching, do not lie. Better to let the loop end naturally with unresolved objections than to claim approval that was not given.
- **Do not write code.** Your task is design, not implementation. Output is `design.md` only (plus `reviews/` indirectly via the subagent).
- **Do not modify the user's source code.** Read it freely for analysis; never edit.
```

- [ ] **Step 2: Verify content with grep**

Run:
```bash
grep -c 'VERDICT' /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/prompt.md
grep -c '<promise>APPROVED</promise>' /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/prompt.md
grep -c 'subagent_type.*tom' /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/prompt.md
```

Expected: first count ≥ 4; second ≥ 2; third ≥ 1.

---

### Task 3: Write `reviewer_prompt.md` (cross-task reviewer template)

**Files:**
- Create: `/home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/reviewer_prompt.md`

- [ ] **Step 1: Write the file with this exact content**

````markdown
# Reviewer Subagent — Devil's Advocate Critic

You are a devil's advocate critic. You run in fully isolated context, with no knowledge of the main session's internal reasoning. Your only inputs are files in the task directory provided at the END of this prompt (look for the line `TASK DIRECTORY: ...`).

## Your role — non-negotiable

You are a CRITIC, not a co-designer. Absolute rule: **never propose your own alternative design**. If you find yourself thinking "they should do X instead", rewrite that thought as "the design fails to justify why it does not do X". All your output is question and challenge, never proposal.

You are not here to make the main session feel good. You are a gatekeeper. The main session's design is APPROVED only when it passes a high bar across all eight evaluation axes below. **If any axis fails, you reject.** Default to rejection — approval is the exception, not the goal.

## Per-invocation workflow

1. **Read `question.md`** in the task directory. This is your evaluation baseline — what the user actually asked. Extract the explicit constraints and properties. Do not let `design.md`'s self-description substitute for this; cross-check whether `design.md` answers the *user's* question, not just its own restatement.
2. **Read `design.md`** in the task directory. This is the main session's current position to evaluate.
3. **Read every file in `reviews/`** in name order. Your prior selves' critiques are your cross-iteration memory. For each prior objection, determine: did the main session substantively respond, or only re-phrase to sound responsive?
4. **Verify any factual claims** in `design.md` against the codebase or referenced files. Use Read/Bash/Grep as needed. If `design.md` claims "the current factor framework does X", check whether that's true. State what you checked.
5. **Compose your review** following the strict structure below.
6. **Write the review file** to `<task_dir>/reviews/review_NNN.md` where NNN = (count of existing files in `reviews/`) + 1, zero-padded to 3 digits. Examples: `review_001.md`, `review_007.md`, `review_012.md`.
7. **Return** a brief summary stating the file path and the VERDICT line. The main session reads the file from disk to act on it.

## Eight evaluation axes

1. **Decisiveness** — Has the design selected exactly one path? "It depends" / "either A or B" / "we could go either way" all fail this axis. The user wants one solution.
2. **Question fidelity** — Does the design explicitly address every constraint stated in `question.md`? Check each one. Has the framing of the problem been preserved, or silently shifted?
3. **Comparative reasoning** (conditional) — If the question implies multiple candidate paths (and lists some), the design must give explicit reasons for rejecting the un-chosen candidates. If the question is a pure investigation, the design must show a traceable reasoning chain.
4. **No hand-waving** — Every step is concrete enough that a reader knows what is being claimed. Phrases like "via some mechanism", "an appropriate abstraction", "handle this properly", "as needed" are red flags. Demand specifics.
5. **Cross-iteration consistency** — Every objection from prior reviews must be either substantively responded to (the design changed in a way that addresses it) or explicitly acknowledged in `design.md` as un-addressable with a stated reason. Re-phrasing the same position is not a response.
6. **Falsifiability / actionability** — Does the design produce claims that can be checked, or reduce to a concrete next step (e.g., "if implemented, the first change would touch file X to add abstraction Y")? Pure abstraction without grounding fails.
7. **First-principles / Occam** — Is every component of the design demanded by the problem? Or has the main session added complexity for imagined future needs? Strip-test each component: if X were removed, would the design fail to solve the stated problem? If no, X is YAGNI bloat.
8. **Scope discipline** — Has the design drifted into problems not in `question.md`? Has it invented constraints the user did not state?

## Strict review file format

Your review file MUST follow this exact structure (markdown headings as shown). Substitute N for your iteration number.

```
# Review N

## Response check on prior objections
- Objection 1 (from review_NNN): [substantive / surface-only / dodged] — reason
- Objection 2 (from review_NNN): ...
(If this is the first review, write: "First review — no prior objections.")

## New objections this round
- ...
- ...

## Fact-checks
- (Only items where you actually checked the codebase or referenced files. State what you checked, the command/file, and the result. If you did no fact-checks this round, write: "No factual claims requiring verification this round.")

## Eight-axis evaluation
- Decisiveness: ✓/✗ — reason
- Question fidelity: ✓/✗ — reason
- Comparative reasoning: ✓/✗ — reason
- No hand-waving: ✓/✗ — reason
- Cross-iteration consistency: ✓/✗ — reason
- Falsifiability: ✓/✗ — reason
- First-principles: ✓/✗ — reason
- Scope discipline: ✓/✗ — reason

## Final verdict
VERDICT: APPROVED
```

The last line MUST be exactly one of:
- `VERDICT: APPROVED` — only if all eight axes are ✓
- `VERDICT: OBJECTIONS_REMAIN` — if any axis is ✗

No other VERDICT values. No additional text after the VERDICT line.

## Gatekeeping discipline

If you are tempted to approve "to let the main session move on" or because "this round seems good enough", you are failing your role. The user wants a solution that survives critical scrutiny, not one that silenced its critic. When in doubt, reject and explain why. The main session has up to ralph-loop's max-iterations to address you.
````

- [ ] **Step 2: Verify content with grep**

Run:
```bash
grep -c 'VERDICT: APPROVED' /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/reviewer_prompt.md
grep -c 'VERDICT: OBJECTIONS_REMAIN' /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/reviewer_prompt.md
grep -cE 'Decisiveness|Question fidelity|Comparative reasoning|No hand-waving|Cross-iteration consistency|Falsifiability|First-principles|Scope discipline' /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/reviewer_prompt.md
grep -c 'never propose your own alternative design' /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/reviewer_prompt.md
```

Expected: first ≥ 2; second ≥ 2; third ≥ 16 (each axis appears in description list AND in evaluation template); fourth ≥ 1.

---

### Task 4: Write `question.md` (multi-BO architecture task content)

**Files:**
- Create: `/home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/question.md`

- [ ] **Step 1: Write the file with this exact content**

```markdown
# Question: 描述复合多 BO 走势的架构选型

## 现象

用户观察到一种走势模式（参考同目录下 `reference.png`，如可读取），其特征不只是单个突破，而是一连串相关现象的组合：

- 短期内聚集多个突破（multi-BO clustering）
- 突破伴随放量
- 突破之前股价趋于平稳，MA40 几乎水平
- 最后一个突破后，股价稳定在比突破前更高的位置（最后一个 BO 形成台阶）

## 现状的限制

当前 BreakoutStrategy 的因子体系是 BO-centric 的：每个因子针对单个 BO 计算，且计算窗口只看 BO 之前的走势。具体的代码组织从以下入口确认（不要假设，自己读代码）：

- `BreakoutStrategy/analysis/` — 突破检测、因子计算、质量评分
- `BreakoutStrategy/factor_registry.py` — 因子元数据
- `BreakoutStrategy/mining/template_validator.py` — 模板验证逻辑
- `.claude/docs/system_outline.md` — 系统概览
- `.claude/docs/modules/` — 已实现模块的架构意图汇总

## 关键性质 / 难点

上述走势难以用现有 BO-centric 框架直接表达，因为：

1. **多 BO 整体性**：现象不是关于某一个 BO，而是关于一组 BO 的集合性质。
2. **顺序约束**：现象包含时间顺序——必须先出现 MA 持平阶段，才能算上"最后一个 BO"。
3. **非因果窗口**：最后形成的台阶发生在最后一个 BO 之后，对那个 BO 来说位于"未来"，无法纳入现有"BO 之前的走势"窗口。

## 候选方向（用户初始想法，作为锚点；允许并鼓励第 N 种）

1. **Condition_Ind 链式架构** — 参考另一项目的类
   `/home/yu/PycharmProjects/new_trade/screener/state_inds/base.py` 中的 `screener.state_inds.base.Condition_Ind`，将多个运算以条件链条串联，天然表达顺序约束。
2. **保留现架构，把走势拆解为无序因子** — 将复合走势打散为若干个与顺序无关的因子，靠这些因子的联合分布近似复合走势的特征。
3. **全新架构** — 与上述两者都不同的某种结构。

最终必须选定**有且只有一个**具体方案。如果你认为这三种都不是最优，必须显式提出第四方案，**并显式说明为什么这三种都不够**。"看情况而定"或"以上皆可"不可接受。

## 非目标

- 不写代码
- 不修改现有代码库的任何文件
- 不做完整的工程实现规划
- 不去解决"如何挖掘这种走势"的问题——只解决"用什么架构表达这种走势"

## 参考资源

主会话和 reviewer 都可以读以下位置（按需）：

- 当前因子框架：`BreakoutStrategy/analysis/`、`BreakoutStrategy/factor_registry.py`
- 模板挖矿/验证：`BreakoutStrategy/mining/template_validator.py`
- 系统概览：`.claude/docs/system_outline.md`
- 模块意图：`.claude/docs/modules/`
- 参考类：`/home/yu/PycharmProjects/new_trade/screener/state_inds/base.py`（类 `Condition_Ind`）
```

- [ ] **Step 2: Verify content**

Run:
```bash
grep -c '候选方向' /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/question.md
grep -c '非目标' /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/question.md
grep -c 'Condition_Ind' /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/question.md
```

Expected: each ≥ 1.

---

### Task 5: Initialize empty `design.md`

**Files:**
- Create: `/home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/design.md`

- [ ] **Step 1: Create the empty file**

Run:
```bash
touch /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/design.md
```

- [ ] **Step 2: Verify it exists and is empty**

Run:
```bash
test -f /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/design.md && wc -c /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/design.md
```

Expected: `0 ...design.md` (empty by design — main session writes the first version on iteration 1).

---

### Task 6: (User-driven) Place reference image

This step requires the user to identify which chart in `prompts/` illustrates the multi-BO pattern. The user has three candidates: `prompts/img.png`, `prompts/img_1.png`, `prompts/img_2.png`.

- [ ] **Step 1: Ask the user which image to use**

Pause and ask the user: "Which file under `prompts/` shows the multi-BO pattern you described? (img.png / img_1.png / img_2.png / none — skip if none)."

- [ ] **Step 2: Copy the chosen image (skip if user said none)**

Run (substitute `<chosen>`):
```bash
cp /home/yu/PycharmProjects/Trade_Strategy/prompts/<chosen>.png /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/reference.png
```

- [ ] **Step 3: Verify (skip if user said none)**

Run:
```bash
ls -la /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/reference.png
```

Expected: file exists with a positive size.

If the user skipped, that's fine — `question.md` says "如可读取", and the textual description of the pattern is sufficient.

---

### Task 7: Final verification and launch instructions

- [ ] **Step 1: Verify the full task directory contents**

Run:
```bash
ls -la /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/
```

Expected files: `prompt.md`, `reviewer_prompt.md`, `question.md`, `design.md` (0 bytes), `reviews/` (empty directory). Optional: `reference.png`.

- [ ] **Step 2: Verify the .gitignore entry is active**

Run:
```bash
git -C /home/yu/PycharmProjects/Trade_Strategy status --short docs/tmp/ 2>&1
```

Expected: empty output (no tracked changes inside `docs/tmp/`). If files inside the task dir appear in `git status`, the gitignore rule failed — re-check Task 1 Step 3.

- [ ] **Step 3: (Optional) commit the .gitignore change**

The only thing the implementation actually touches in git is `.gitignore`. If the user wants to commit it:

```bash
cd /home/yu/PycharmProjects/Trade_Strategy && git add .gitignore && git diff --cached -- .gitignore
```

If the diff looks right, ask the user before committing. If they say yes:

```bash
cd /home/yu/PycharmProjects/Trade_Strategy && git commit -m "$(cat <<'EOF'
chore: gitignore loop iteration artifacts under docs/tmp/loop/

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

If they say no, skip.

- [ ] **Step 4: Hand the launch command to the user**

Print this for the user to invoke when they're ready to start the loop:

```
/ralph-loop:ralph-loop "Read /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture/prompt.md and follow its instructions exactly. The current task directory is /home/yu/PycharmProjects/Trade_Strategy/docs/tmp/loop/multi-bo-architecture." --completion-promise "APPROVED" --max-iterations 15
```

Tell the user:
- This must be run by them (slash commands cannot be invoked from inside an assistant turn).
- The loop runs in this same Claude Code session — they should clear context first if the current session is loaded with brainstorming history.
- After it exits (or hits 15 iterations), inspect `design.md`, `reviews/`, and `notes.md` in the task directory.

- [ ] **Step 5: Done**

The skeleton is ready. The implementation plan ends here; running the loop and reviewing its output is the user's next action, not an implementation task.

---

## Self-Review Notes

- Spec coverage: every section of `docs/research/loop_reviewer_design.md` (整体环路 / 文件布局 / prompt 骨架 / reviewer 骨架 / question 骨架 / 失效模式 / 启动) is reflected in Tasks 1–7.
- Placeholder scan: file contents are written in full inside the plan; no "TBD" / "fill in later" placeholders.
- Type consistency: `<promise>APPROVED</promise>` literal, `VERDICT: APPROVED` and `VERDICT: OBJECTIONS_REMAIN` literals, `subagent_type: tom`, file naming `review_NNN.md` zero-padded — all consistent across prompt.md, reviewer_prompt.md, and the orchestration.
- Out-of-scope: not implemented in this plan (deferred to "未来改进点" in the spec):
  - Multi-perspective reviewer panel
  - reviewer-proposes-alternatives mode
  - Slash-command wrapping
  - Same-objection-loop detection
  - History-snapshot of design.md
- The plan does not commit any iteration-artifact files (they're gitignored). Only `.gitignore` itself is a candidate for commit (Task 7 Step 3, optional).
