# web-loop 决策层 P0 + P1 同步落地 · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `.claude/skills/web-loop/` 内同步落地 P0(扩 reviewer schema 4 字段 + reviewer 跨轮反思 + implementer 5 级优先级+ opus + 强制判断题 + 3 条机检判据 + paused/human-hint 续修 + finalize PAUSED 节 + SKILL.md 文档)和 P1(stall 触发的缩窄版 opus meta-agent + decision_log.json append + forbiddenApproaches 注入 implementer + escapeRequest 走 paused 通道)共 9 处改动。

**Architecture:** 全部改动集中在 `workflow-template.js`(prompt + schema + 控制流)、`SKILL.md`(文档)、`tests/test-*.mjs`(纯 node ESM regex 验证)三类文件。不引入新外部依赖、不破坏 Workflow runtime 契约(`export const meta`、`const A=...args parse`、`agent()/parallel()/pipeline()/phase()/log()`)、不破坏 resume 缓存(禁 `Date.now()`/`Math.random()`/argless `new Date()`)。所有用户字符串内插必须 `safeInsert`/`safeBlock` 包裹。

**Tech Stack:** Node.js ESM(零 npm 依赖)· Workflow runtime(Anthropic skill harness)· JSON Schema(agent schema)

---

## 必读输入文档(本 plan 自包含;新 session 不读对话上下文也能实施)

实施前 Read 这些文档拿到完整设计依据:

| 文档 | 用途 |
|---|---|
| `docs/research/2026-06-21_web-loop-decision-layer-redesign/final_report.md` | P0/P1 完整 spec(540 行,含 5 轮用户反问 + tom 第一性原理裁定后的最终设计) |
| `docs/research/2026-06-21_web-loop-decision-layer-redesign/redesigner-proposal.md` | §6 P1 缩窄版设计(R0→R2 让步轨迹 + META_AGENT_SCHEMA 物理禁双源真理依据) |
| `docs/research/2026-06-21_web-loop-decision-layer-redesign/skeptic-counter.md` | 3 条机检判据具体算法 + paused.md 协议格式 |
| `docs/research/2026-06-21_web-loop-decision-layer-redesign/architect-position.md` | reviewer schema 扩字段的设计依据(R1 翻转记录) |
| `docs/research/2026-06-21_web-loop-decision-layer-redesign/diagnostician-rootcauses.md` | 三档根因 ①(symptoms→fix 翻译层缺失)②(schema 锁死)③(mustStaleStreak 字符串脆) |
| `.claude/skills/web-loop/SKILL.md` | 当前 skill 文档(改前先读,定位 args 表 / 红线 / 续修协议节插入点) |
| `.claude/skills/web-loop/workflow-template.js` | 改动主战场(全文 431 行;关键行号在每 task 给出) |
| `.claude/skills/web-loop/principles.md` | 总则第 5 条"reviewer 指出缺陷,不设计方案"——本 plan 的 nextStepPlan 字段需明示绕开此红线副作用(出"诊断+调查方向+验证方法",非"具体实施替代方案") |

---

## Global Constraints

所有 task 隐式继承下列约束,违反任何一条 = task 不通过:

- **不破坏 Workflow runtime 契约**:`export const meta = {...}`、顶部 `const A = (typeof args === 'string' ? ... : args) || {}` 解析、`agent()`/`pipeline()`/`parallel()`/`phase()`/`log()` 调用形态——全部不动。
- **prompt 内插用户字符串必须 `safeInsert`/`safeBlock` 包裹**(M5.2 铁律,helpers 已在 `workflow-template.js:43-54` 实现)。
- **禁 `Date.now()` / `Math.random()` / 无参 `new Date()`**(破坏 Workflow resume 缓存,SKILL.md L113)。
- **每 task 单独 commit**,commit message 前缀 `web-loop/<scope>:`(scope 取 `template` / `tests` / `skill` 三选一)。
- **TDD**:每个有行为变化的 task,**先**写 `tests/test-<task-slug>.mjs`(纯 node ESM、`fs.readFileSync` + 正则/字符串断言,零外部 npm 依赖)、跑测试看 FAIL(RED)、**再**实现到 PASS(GREEN)、**再** commit。
- **每 task 同时跑 `node --check workflow-template.js`** 保语法不破。
- **不引入新外部 npm 依赖**。
- **不动 SKILL.md 之外的 docs/**——所有设计依据已在 `docs/research/2026-06-21_*` 内,本次落地不再写新文档。
- **测试模式**:沿用现有测试范式(`tests/_helpers.mjs` 已提供 `readTemplate / readSkillMd / assertContains / assertNotContains / assertMatches / ok`);新测试用同样 API,不重新发明。
- **路径**:全部相对 `/home/yu/PycharmProjects/Trade_Strategy-bo/`(本 worktree 根)。所有 `.claude/skills/web-loop/...` 路径皆从此根算起。
- **task 11 末尾 final verification 命令**:
  ```bash
  cd .claude/skills/web-loop && \
    node --check workflow-template.js && \
    for f in tests/test-*.mjs; do echo "--- $f"; node "$f" || exit 1; done && \
    echo "ALL GREEN"
  ```

---

### Task 1: 扩 REVIEWER_SCHEMA 加 4 字段(rootCauseHypothesis / affectedFiles / suggestedFix / nextStepPlan)

**Files:**
- Modify: `.claude/skills/web-loop/workflow-template.js:179-189`(`REVIEWER_SCHEMA.issues.items.properties`)
- Test: `.claude/skills/web-loop/tests/test-reviewer-schema-rootcause.mjs`(新建)

**Interfaces:**
- Consumes: 当前 `REVIEWER_SCHEMA` 形态(workflow-template.js:179-189 已含 `title/severity/evidence/matchesIssueId/matchesSubgoal/unverifiable/requiredStates/detail`)
- Produces: `REVIEWER_SCHEMA.issues.items.properties` 新增 4 字段,字段类型如下;后续 Task 2 reviewer prompt 会强制 code lens 必填这 4 字段,Task 4 implementer prompt 会消费它们。
  ```js
  rootCauseHypothesis: { type: ["string","null"] }   // code lens 必填,其他可 null
  affectedFiles: { type: "array", items: { type: "string" } }   // ["path:line", ...]
  suggestedFix: { type: ["string","null"] }
  nextStepPlan: { type: ["string","null"] }
  ```

- [ ] **Step 1: 写 RED 测试**

创建 `.claude/skills/web-loop/tests/test-reviewer-schema-rootcause.mjs`,内容:

```js
import { readTemplate, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// 4 新字段都在 REVIEWER_SCHEMA.issues.items 内
assertMatches(src, /REVIEWER_SCHEMA[\s\S]*issues:\s*\{[\s\S]*items:\s*\{[\s\S]*rootCauseHypothesis/, 'REVIEWER_SCHEMA.issues.items 含 rootCauseHypothesis');
assertMatches(src, /REVIEWER_SCHEMA[\s\S]*items:\s*\{[\s\S]*affectedFiles/, 'REVIEWER_SCHEMA.issues.items 含 affectedFiles');
assertMatches(src, /REVIEWER_SCHEMA[\s\S]*items:\s*\{[\s\S]*suggestedFix/, 'REVIEWER_SCHEMA.issues.items 含 suggestedFix');
assertMatches(src, /REVIEWER_SCHEMA[\s\S]*items:\s*\{[\s\S]*nextStepPlan/, 'REVIEWER_SCHEMA.issues.items 含 nextStepPlan');

// affectedFiles 必须是 array of string
assertMatches(src, /affectedFiles:\s*\{\s*type:\s*"array",\s*items:\s*\{\s*type:\s*"string"\s*\}\s*\}/, 'affectedFiles=array<string>');

// rootCauseHypothesis / suggestedFix / nextStepPlan 允许 null(非 code lens 可空)
assertMatches(src, /rootCauseHypothesis:\s*\{\s*type:\s*\[\s*"string"\s*,\s*"null"\s*\]\s*\}/, 'rootCauseHypothesis 允许 null');
assertMatches(src, /suggestedFix:\s*\{\s*type:\s*\[\s*"string"\s*,\s*"null"\s*\]\s*\}/, 'suggestedFix 允许 null');
assertMatches(src, /nextStepPlan:\s*\{\s*type:\s*\[\s*"string"\s*,\s*"null"\s*\]\s*\}/, 'nextStepPlan 允许 null');

ok('test-reviewer-schema-rootcause');
```

- [ ] **Step 2: 跑测试看 FAIL**

```bash
cd .claude/skills/web-loop && node tests/test-reviewer-schema-rootcause.mjs
```

Expected: 1st `assertMatches` fail with `expected to match /REVIEWER_SCHEMA[\s\S]*issues:.../`

- [ ] **Step 3: 实现 — 改 workflow-template.js:184-185(REVIEWER_SCHEMA.issues.items.properties)**

当前(workflow-template.js:184-185):
```js
    issues:{type:"array", items:{type:"object", required:["title","severity"],
      properties:{ matchesIssueId:{type:["string","null"]}, matchesSubgoal:{type:["string","null"]}, title:{type:"string"}, severity:{enum:["must","nice"]}, unverifiable:{type:"boolean"}, requiredStates:{type:"array", items:{type:"string"}}, detail:{type:"string"}, evidence:{type:"string"} }}},
```

改为:
```js
    issues:{type:"array", items:{type:"object", required:["title","severity"],
      properties:{ matchesIssueId:{type:["string","null"]}, matchesSubgoal:{type:["string","null"]}, title:{type:"string"}, severity:{enum:["must","nice"]}, unverifiable:{type:"boolean"}, requiredStates:{type:"array", items:{type:"string"}}, detail:{type:"string"}, evidence:{type:"string"},
        // ★ 2026-06-21 P0 §3.2 — 决策层根因 + 策略级 plan(code lens 必填、其他 lens 可空)
        rootCauseHypothesis:{type:["string","null"]},
        affectedFiles:{type:"array", items:{type:"string"}},
        suggestedFix:{type:["string","null"]},
        nextStepPlan:{type:["string","null"]} }}},
```

- [ ] **Step 4: 跑测试看 PASS + node --check 不报错**

```bash
cd .claude/skills/web-loop && node --check workflow-template.js && node tests/test-reviewer-schema-rootcause.mjs && node tests/test-reviewer-schema.mjs
```

Expected: 全 PASS(旧 test-reviewer-schema.mjs 也要继续过)

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/web-loop/workflow-template.js .claude/skills/web-loop/tests/test-reviewer-schema-rootcause.mjs
git commit -m "web-loop/template: REVIEWER_SCHEMA.issues 加 4 字段(rootCause/affected/fix/plan)

final_report §3.2:让 reviewer code lens 在产 verdict 那一刻顺手出根因 +
策略级 nextStepPlan,绕开 schema 锁死。其他 lens 可空。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: reviewerPrompt 加"code lens 必填 4 字段 + nextStepPlan 模板 + 跨轮反思段 + 强制 matchesIssueId 优先"

**Files:**
- Modify: `.claude/skills/web-loop/workflow-template.js:113-167`(`reviewerPrompt` 函数)
- Test: `.claude/skills/web-loop/tests/test-reviewer-prompt-rootcause.mjs`(新建)

**Interfaces:**
- Consumes: Task 1 扩好的 `REVIEWER_SCHEMA`(reviewer 模型知道这 4 字段存在);`WORKDIR`、`round` 变量(`reviewerPrompt` 已有参数,无需新增)
- Produces:
  - code lens brief 加"必填 rootCauseHypothesis + affectedFiles + nextStepPlan(策略级、3-8 行、禁代码级 prescription)"指令
  - 加"跨轮反思段":reviewer Read `<workdir>/rounds/<N-1>/impl.md` 首段 `reviewer_stuck` 标,若 true 必须给与上轮不同主线
  - 全 lens brief 加"对所有 open must 必须优先用 `matchesIssueId` 引用现有 id,只有判定真新增 bug 才新立 id"(§3.3 mustStaleStreak 语义聚类轻量修)

- [ ] **Step 1: 写 RED 测试**

创建 `.claude/skills/web-loop/tests/test-reviewer-prompt-rootcause.mjs`,内容:

```js
import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// 1. code lens brief 内强制 4 字段必填
assertContains(src, '必填 rootCauseHypothesis', 'code lens brief 强制必填 rootCauseHypothesis');
assertContains(src, '必填 affectedFiles', 'code lens brief 强制必填 affectedFiles');
assertContains(src, '必填 nextStepPlan', 'code lens brief 强制必填 nextStepPlan');

// 2. nextStepPlan 模板字样(策略级,禁代码级)
assertMatches(src, /nextStepPlan[\s\S]{0,1500}策略级|策略级[\s\S]{0,500}nextStepPlan/, 'nextStepPlan 明文「策略级」');
assertContains(src, '禁代码级', 'nextStepPlan 明文「禁代码级」prescription');
assertMatches(src, /读\s*[^\n]{0,40}→\s*改\s*[^\n]{0,40}主线\s*→\s*验证|读 X[\s\S]{0,200}改 Y[\s\S]{0,200}验证 Z[\s\S]{0,200}不要再试 W/, 'nextStepPlan 含「读 X → 改 Y 主线 → 验证 Z → 不要再试 W」模板');

// 3. 跨轮反思段:Read 上轮 impl.md 首段 reviewer_stuck 标
assertContains(src, 'reviewer_stuck', 'reviewer prompt 引用 reviewer_stuck 信号');
assertMatches(src, /Read\s*[^\n]{0,200}rounds\/[\s\S]{0,50}impl\.md/, 'reviewer prompt 含 Read rounds/<N-1>/impl.md');
assertContains(src, '不同主线', 'reviewer prompt 强制「不同主线」(reviewer_stuck=true 时)');
assertContains(src, '换措辞重写同', 'reviewer prompt 禁「换措辞重写同一 plan」');
assertContains(src, 'stuck 异议', 'reviewer prompt 异议通道');

// 4. mustStaleStreak 语义聚类(§3.3):强制 matchesIssueId 优先
assertContains(src, 'matchesIssueId', 'reviewer prompt 引用 matchesIssueId');
assertMatches(src, /matchesIssueId[\s\S]{0,300}引用现有 id|引用现有 id[\s\S]{0,300}matchesIssueId/, '强制「引用现有 id」语义聚类指令');
assertContains(src, '真新增 bug', '只有「真新增 bug」才新立 id');

ok('test-reviewer-prompt-rootcause');
```

- [ ] **Step 2: 跑测试看 FAIL**

```bash
cd .claude/skills/web-loop && node tests/test-reviewer-prompt-rootcause.mjs
```

Expected: 1st `assertContains '必填 rootCauseHypothesis'` fail.

- [ ] **Step 3: 实现 — 改 reviewerPrompt(workflow-template.js:113-167)**

**3a. 改 code lens brief**(workflow-template.js:117):

当前:
```js
    code:"你是代码质量 reviewer。主要读 git diff,评 bug / 违反 rubric 红线 / 回归。截图仅旁证。**refs 处理:不强制读图,refs 列表仅供查阅(确认本轮 diff 与视觉目标无方向相左)。**",
```

改为:
```js
    code:"你是代码质量 reviewer。主要读 git diff,评 bug / 违反 rubric 红线 / 回归。截图仅旁证。**refs 处理:不强制读图,refs 列表仅供查阅(确认本轮 diff 与视觉目标无方向相左)。**\n⚠⚠ code lens 必填 4 决策字段(P0 §3.2,2026-06-21 final_report):每条 issue 必填 **rootCauseHypothesis**(≤2 句机制假设)+ **affectedFiles**(\"path:line\" 数组,本轮代码现场)+ **nextStepPlan**(策略级 3-8 行 plan,模板「读 X → 改 Y 主线 → 验证 Z → 不要再试 W」,**禁代码级** prescription——禁具体 old_string→new_string / 函数体 snippet / 行号 patch;仅写策略 + 风险 + 验证方法 + 禁止重试什么),suggestedFix 可选(若给出 implementer 可推翻)。ux/func lens 这 4 字段可空。",
```

**3b. 全 lens brief 末尾追加 matchesIssueId 优先条款**(放在 `brief` 三档之后、函数 return 模板之前)。

找到 workflow-template.js:118-123 处的 `refsReadInstr={...}[lens]` 后,以及函数体开头(workflow-template.js:124 `return \`${brief}` 之前)。

新增一行 `const stalePrimer = ...` 然后在 return 模板内插入:

```js
  const stalePrimer = `\n⚠⚠ 语义聚类 / mustStaleStreak 防脆性(P0 §3.3,2026-06-21 final_report):对所有 open must,**优先用 matchesIssueId 引用现有 id**,只有判定为「真新增 bug」(真实独立缺陷,非旧 bug 换措辞)才新立 issue id。reviewer 换措辞重写同 bug = mustStaleStreak 重置 = STALE 退出失效 = 用户反复迭代痛点直接来源。`;
  const reflectBlock = round >= 2 ? `\n【跨轮反思(P0 §3.5a-ii,reviewer_stuck 信号回流)】本轮判定前,Read 上一轮 implementer impl.md 首段:\n  bash: cat ${WORKDIR}/rounds/${round - 1}/impl.md | head -40\n  关注首段 \`reviewer_stuck\` 字段:\n  · reviewer_stuck=true → 说明上一轮 reviewer(即上一个 fresh 你)给的 nextStepPlan 与 plan_r${round - 2 >= 1 ? round - 2 : '?'} 本质相同(同 affectedFiles + 同修法主线)、implementer 试过没解决。本轮 nextStepPlan 必须给与上轮**不同主线**(换 affectedFiles 或换修法思路),**不得换措辞重写同一 plan**。\n  · reviewer_stuck=false → 上一轮 plan 不重复,本轮按真实证据正常推进。\n  · 若你判断 implementer 的 reviewer_stuck=true 是误判(plan 应该有效但 implementer 没正确执行),在 nextStepPlan 顶部标 \"stuck 异议:implementer 误判,本轮重申同主线但详细分解步骤\"。\n  ⚠ 关键设计:本段不破 reviewer 红线——reviewer 读的是 implementer 的元判断信号(下游观察信号),不是 reviewer 自己的历史输出。新信息(经 implementer 看真实代码 + 跨轮对比中转),不污染本轮独立判断。` : '';
```

然后在 return 的模板字面量末尾(`mustFixOpen=本 lens 当前 open must 数。按 schema 输出。` 这句之前)插入:

```js
${stalePrimer}${reflectBlock}
```

具体修改后 `reviewerPrompt` 函数体末尾的 return 部分长这样(workflow-template.js:124-167 末尾段):

```js
  return `${brief}
⚠ 你是 review 层,**永久零浏览器**:只 Read capture 层已截好的 PNG + 读 git diff,**禁碰 playwright(MCP/脚本都禁)**。理由:持有浏览器只属于 capture 单层;reviewer 各自截图会重复采集 +(用 MCP 时)串台。看图足以判 rubric。
${stalePrimer}${reflectBlock}

【本次 GOAL(原文,逐字不变;完整版以 ${WORKDIR}/goal.md 为准)】
${GOAL}

【GOAL 子项清单(完整版以 ${WORKDIR}/goal.md 为准)】
${goalSubgoalsSummary}

【参考图(refs/,详 ${WORKDIR}/refs/manifest.json;⚠ role 三档严格区分,baseline/anti-example 禁模仿/反向远离)】
${refImagesSummary}

${refsReadInstr}

【截图 r${round}】
${shotList}
${consoleNote}
${probeNote||""}

【第二步 · GOAL 子项逐条复核】对照上面 GOAL 子项清单,每条:
  ⚠⚠ 关键:【evidence 必须绑本轮真实可定位证据】对每条子项,verified 数组的 evidence 字段必须含至少一项可被 grep 验证的标识:
    · screenshot 类 → 截图文件路径(精确到 \`<SHOTS_DIR>/<rtag>_<state>.png\`)+ 一句"哪几像素特征体现该子项"(如 "K线 grid 顶端到底端占视口 ≥640px / 视口 1080px = 0.59")
    · console 类   → console 输出行原文片段 + manifest.consoleErrors 索引
    · probe 类     → stateDumps 的 key 名 + 该 key 的本轮取值
    · diff 类      → git diff 中函数名 / 文件名 + 行号
  ⚠ 仅写"看起来满足" / "已实现" / "测试通过" 等不可定位修辞 = evidence 不合格,该子项 coveredSubgoals 不计入,收敛判据不通过。
  - 在 verified 数组里增一项 \`{ title: "G<id> · <desc>", evidence: "<本轮证据原文>", coveredSubgoals: ["G<id>"] }\`
  - 子项 verifiable_via 字段告诉你看哪类证据
  - 若证据不足以判定 → 在 issues 增一项 unverifiable:true,绑 matchesSubgoal: "G<id>";若是 STATES 缺失 → 同时填 requiredStates:[<state>]
⚠ 即使 issues 台账无新增,GOAL 子项仍要逐条表态——这是绕过"清 must 即 pass"的反锚定关。

【反锚定 · 先回讲 GOAL 再判 rubric】用你自己的话复述 GOAL(一两句)+ 列出本轮你判定的 GOAL 子项 id 集合 → 写进 verdict 的 goalEcho 字段。
⚠ goalEcho 字段仅作"开始判定前的注意力归位",**不作为 verdict / 收敛判定依据**。收敛判定看 coveredSubgoals 集合与 evidence 绑定(下面"绝对标准"段)。

【已验证项(各轮 verified 结论,勿重复质疑、勿再立 issue)】
${verifiedJson||"[]"}

【已知问题】逐条在 knownIssuesStatus 表态 stillPresent。⚠ 反锚定:表态必须引用**本轮**证据(截图文件名/字节数/stateDumps/manifest 字段),禁止沿用上轮表述;本轮证据与旧结论矛盾时以本轮为准。must 若仅因取证失败/证据缺失而无法判定(非确证违反),在该条 knownIssuesStatus(或新 issue)上标 unverifiable:true:
${issuesJson}

【绝对标准】must(违反 rubric/GOAL/bug/console error,挡 pass)|nice(不挡)。
**收敛判定:无 open must AND 全 GOAL 子项被本轮 verified 覆盖(coveredSubgoals 集合 ⊇ goalSubgoals.id 集合)→ pass。**
不因"更好做法"fail。out-of-scope 不当 must。绝不提替代方案。完整性铁律。issues 只放缺陷;"已修复/验证通过/全绿"等正面结论一律放 verified 数组(title+evidence+coveredSubgoals),任何 severity 都不得进 issues。mustFixOpen=本 lens 当前 open must 数。按 schema 输出。`;
```

- [ ] **Step 4: 跑测试看 PASS + 旧测试不破**

```bash
cd .claude/skills/web-loop && \
  node --check workflow-template.js && \
  node tests/test-reviewer-prompt-rootcause.mjs && \
  node tests/test-reviewer-prompt.mjs && \
  node tests/test-reviewer-schema.mjs && \
  node tests/test-reviewer-schema-rootcause.mjs
```

Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/web-loop/workflow-template.js .claude/skills/web-loop/tests/test-reviewer-prompt-rootcause.mjs
git commit -m "web-loop/template: reviewerPrompt 加 code lens 4 字段必填 + 跨轮反思 + matchesIssueId 优先

final_report §3.2/§3.3/§3.5a-ii:
- code lens brief 强制必填 rootCauseHypothesis/affectedFiles/nextStepPlan,
  禁代码级 prescription(模板:读 X→改 Y 主线→验证 Z→不要再试 W)
- 跨轮反思段:reviewer 读上轮 impl.md 首段 reviewer_stuck 信号,true
  时必须换主线(下游元判断,不破 reviewer 红线)
- 全 lens 强制 matchesIssueId 优先,治 mustStaleStreak 字符串脆

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: implementer prompt 5 级优先级 + Read affectedFiles + 强制判断题 + impl.md 首段固定结构

**Files:**
- Modify: `.claude/skills/web-loop/workflow-template.js:256-270`(`implementer` agent 调用)
- Test: `.claude/skills/web-loop/tests/test-implementer-prompt-priority.mjs`(新建)

**Interfaces:**
- Consumes: Task 1 扩好的 schema 字段(透传到 implementer);Task 2 reviewer 写出的 `reviewer_stuck` 跨轮信号(读上轮 impl.md 时已落盘)
- Produces:
  - implementer prompt 5 级指令优先级(human-hint → 本轮 must.nextStepPlan/rootCause/affected → forbiddenApproaches(P1 留空 Task 11 注入)→ 历史 reviews → 历史 impl.md 反根因)
  - 透传 must 完整对象(含新 4 字段)JSON 块
  - 强制 Read affectedFiles 实际代码段 + 强制 Read 上轮 impl.md + Read human-hint(若存在)
  - 强制 impl.md 首段固定结构(reviewer_stuck/plan 重复分析/本轮改什么/反根因)

- [ ] **Step 1: 写 RED 测试**

创建 `.claude/skills/web-loop/tests/test-implementer-prompt-priority.mjs`,内容:

```js
import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// 5 级优先级显式标定
assertContains(src, 'human-hint', 'implementer prompt 引用 human-hint');
assertMatches(src, /优先级\s*1[\s\S]{0,200}human-hint|human-hint[\s\S]{0,100}优先级\s*1/, '优先级 1 = human-hint');
assertMatches(src, /优先级\s*2[\s\S]{0,300}nextStepPlan|nextStepPlan[\s\S]{0,200}优先级\s*2/, '优先级 2 = 本轮 must.nextStepPlan');
assertContains(src, 'forbiddenApproaches', 'implementer prompt 引用 forbiddenApproaches(P1 占位)');
assertMatches(src, /优先级\s*4[\s\S]{0,300}round_|round_[\s\S]{0,200}历史/, '优先级 4 = 历史 reviews/round_<N-1>.md');
assertMatches(src, /优先级\s*5[\s\S]{0,300}反根因|反根因[\s\S]{0,200}impl\.md/, '优先级 5 = 历史 impl.md 反根因段');

// 透传 must 完整对象(含 nextStepPlan / rootCauseHypothesis / affectedFiles)
assertMatches(src, /impl-\$\{rtag\}[\s\S]{0,5000}nextStepPlan/, 'implementer prompt 含 nextStepPlan');
assertMatches(src, /impl-\$\{rtag\}[\s\S]{0,5000}rootCauseHypothesis/, 'implementer prompt 含 rootCauseHypothesis');
assertMatches(src, /impl-\$\{rtag\}[\s\S]{0,5000}affectedFiles/, 'implementer prompt 含 affectedFiles');

// 强制 Read affectedFiles 实际代码 + Read 历史 + Read human-hint
assertMatches(src, /Read\s*[^\n]{0,80}affectedFiles/, 'implementer 强制 Read affectedFiles');
assertMatches(src, /Read[\s\S]{0,200}reviews\/round_/, 'implementer Read 历史 reviews');
assertMatches(src, /human-hint-r[\s\S]{0,200}Read|Read[\s\S]{0,200}human-hint-r/, 'implementer Read human-hint-r*.md');

// 强制判断题 + impl.md 首段固定结构
assertContains(src, 'reviewer_stuck', 'implementer prompt 强制写 reviewer_stuck 标');
assertContains(src, 'plan 重复分析', 'impl.md 首段含 plan 重复分析');
assertContains(src, '反根因', 'impl.md 首段含反根因段(若有)');
assertMatches(src, /首段[\s\S]{0,500}固定结构|固定结构[\s\S]{0,300}首段/, 'impl.md 首段固定结构');

// human-hint Read 完 mv 到 consumed
assertMatches(src, /mv[\s\S]{0,200}human-hint-r[\s\S]{0,80}\.consumed\.md/, 'human-hint 消费完 mv 到 .consumed.md');

ok('test-implementer-prompt-priority');
```

- [ ] **Step 2: 跑测试看 FAIL**

```bash
cd .claude/skills/web-loop && node tests/test-implementer-prompt-priority.mjs
```

Expected: 1st assertion fail.

- [ ] **Step 3: 实现 — 改 implementer agent 调用(workflow-template.js:256-270)**

当前(workflow-template.js:256-270):
```js
  await agent(
    `【${rtag} · implementer】改进运行中的 web(改 bug / 改进现有代码,非从零)。\n\n` +
    `【本次 GOAL(原文,逐字不变;完整版以 ${WORKDIR}/goal.md 为准)】\n${safeInsert(GOAL)}\n\n` +
    `【GOAL 子项清单(${GOAL_SUBGOALS.length} 条;完整版以 ${WORKDIR}/goal.md 为准)】\n${subgoalsSummary}\n\n` +
    `${refsLineForImpl}\n\n` +
    `【已 verified 子项(勿破坏)】\n${verifiedSummary}\n\n` +
    `【本轮工作】\n` +
    (round === 1
      ? `第一轮:实现 GOAL 核心改动,子项逐条覆盖。${hasGoalRef ? '⚠ 第一轮必读 role=goal 的 ref 建立视觉心智图。' : ''}`
      : `修以下 must(优先),勿引入新问题,**勿偏离 GOAL 全局**(每改一条 must,反问自己是否拉远了某 verified 子项):\n` +
        safeBlock(JSON.stringify(openIssues.filter(i=>i.severity==="must"), null, 2), '```json')
    ) + `\n\n` +
    `⚠ 改前 \`git diff\` 看现状,勿破坏已 fixed 功能。完成写 ${WORKDIR}/rounds/${round}/impl.md,**首行 kind=frontend|backend|data**。`,
    { label:implLabel, phase:"iterate", model:"sonnet" }
  );
```

改为(注意 model 改 opus 留到 Task 4,本 task 只改 prompt 内容):
```js
  // ── 5 级指令优先级(P0 §3.5a-i / §3.5a-ii,2026-06-21 final_report)──
  // 1. human-hint-r{N}.md(用户人工指令,若存在)
  // 2. 本轮 must.nextStepPlan + rootCauseHypothesis + affectedFiles(权威·必从)
  // 3. (P1)decision_log.json 的 forbiddenApproaches(Task 11 注入,本 task 占位段)
  // 4. 历史 reviews/round_<N-1>.md / round_<N-2>.md(参考补充)
  // 5. 历史 rounds/<N-1>/impl.md 反根因段(implementer 自己上轮的判断)
  const mustWithDecision = round === 1
    ? null
    : openIssues.filter(i=>i.severity==="must");
  const mustBlock = mustWithDecision
    ? safeBlock(JSON.stringify(mustWithDecision, null, 2), '```json')
    : '(第一轮无残留 must)';
  const humanHintRead = `【优先级 1 · 用户人工指令(human-hint,若存在,自然语言)】先 bash 检测 \`test -f ${WORKDIR}/human-hint-r${round}.md\` —— 若存在则 \`Read ${WORKDIR}/human-hint-r${round}.md\`(优先级最高于一切),消化后 \`mv ${WORKDIR}/human-hint-r${round}.md ${WORKDIR}/human-hint-r${round}.consumed.md\` 防止下轮重复消费;不存在则跳过。`;
  const decisionLog = round >= 2 ? `【优先级 3 · 跨轮禁忌(forbiddenApproaches,P1 meta-agent 产物,若启用)】Read ${WORKDIR}/decision_log.json(若存在);其中 forbiddenApproaches 数组列出本 run 累计「试过且失败」的方法,**不得重试**;若你必须重试,在 impl.md 首段单独标 "重试理由:..."。若文件不存在 = P1 未触发 / 未启用,跳过本步。` : '';
  const historyReviews = round >= 2 ? `【优先级 4 · 历史 reviews(参考补充,验证 P1 提炼是否准确)】\n- Read ${WORKDIR}/reviews/round_${String(round - 1).padStart(2,'0')}.md(必读)\n${round >= 3 ? `- Read ${WORKDIR}/reviews/round_${String(round - 2).padStart(2,'0')}.md(若存在)\n` : ''}用于验证本轮 nextStepPlan 与上轮的差异、确认 P1 forbiddenApproaches 提炼无漏;若发现 P1 漏掉重要信号,在 impl.md 标 "P1 漏检:..."。` : '';
  const histImpl = round >= 2 ? `【优先级 5 · 历史 impl.md 反根因段(implementer 自报)】Read ${WORKDIR}/rounds/${round - 1}/impl.md 首段——上轮自己写的 reviewer_stuck 判断 / 反根因记录。若有 "反根因:实际机制是 Z" 段,本轮优先验证 Z 假设。` : '';

  await agent(
    `【${rtag} · implementer】改进运行中的 web(改 bug / 改进现有代码,非从零)。\n\n` +
    `${humanHintRead}\n\n` +
    `【本次 GOAL(原文,逐字不变;完整版以 ${WORKDIR}/goal.md 为准)】\n${safeInsert(GOAL)}\n\n` +
    `【GOAL 子项清单(${GOAL_SUBGOALS.length} 条;完整版以 ${WORKDIR}/goal.md 为准)】\n${subgoalsSummary}\n\n` +
    `${refsLineForImpl}\n\n` +
    `【已 verified 子项(勿破坏)】\n${verifiedSummary}\n\n` +
    `【优先级 2 · 本轮 must(权威·必从;含 nextStepPlan / rootCauseHypothesis / affectedFiles / suggestedFix 四决策字段,code lens 给的策略,2026-06-21 P0 §3.2/§3.5a-i)】\n` +
    (round === 1
      ? `(第一轮无残留 must)\n` + (hasGoalRef ? '⚠ 第一轮必读 role=goal 的 ref 建立视觉心智图。\n' : '')
      : `${mustBlock}\n\n⚠ 改前必做:\n  1. 对每条 must,先 Read affectedFiles 列出的具体行号(确认 reviewer 描述的现状与本轮真实代码一致;reviewer 看的是上轮 diff,本轮代码可能已变)。\n  2. 一句话回讲"我理解根因是 X,我要按 nextStepPlan 第 N 步改的是 Y"(写进 impl.md 首段)。\n  3. 若 nextStepPlan 给了具体 suggestedFix,可推翻——但需在 impl.md 标 "推翻 suggestedFix 因为 W"。\n  4. **勿引入新问题,勿偏离 GOAL 全局**(每改一条 must,反问自己是否拉远了某 verified 子项)。\n`
    ) + `\n` +
    `${decisionLog}\n\n${historyReviews}\n\n${histImpl}\n\n` +
    `【强制判断题(impl.md 首段固定结构,P0 §3.5a-ii reviewer_stuck 信号回流)】\n${round >= 2 ? `在执行 r${round} plan 之前,impl.md 首段必须按下面**固定结构**回答(放最顶上,本轮代码改动写在结构之后):\n\`\`\`\n- reviewer_stuck: <true|false>     # "r${round} plan 与 r${round-1} plan 是否本质相同(同 affectedFiles + 同修法主线)?"\n- plan 重复分析: <一句话>            # 若 reviewer_stuck=true,简述上轮 plan 试过 X 失败于 Y、本轮我会改在 Z 处(可微调主线)\n- 本轮我会按 plan 第 N 步改 <文件:行号>   # 若 reviewer_stuck=true,本步可偏离 plan,给理由\n- 反根因(若有): <若发现 reviewer 根因假设与实际代码不符,记 "实际机制是 Z">\n\`\`\`\n⚠ 关键设计:本段是「reviewer_stuck 信号回流」基础——下轮 reviewer 会 Read 你这段判断 reviewer 自己是否走偏。诚实表态(reviewer_stuck=true 不是攻击 reviewer,是关键反思回路);若你按 r${round-1} plan 改完没解决问题、本轮 reviewer 又给同样的 plan、你判断 plan 应换主线 → reviewer_stuck=true。` : '(第一轮无上轮 plan,本字段不适用——但仍写 impl.md 首段记本轮 kind / 改了什么)'}\n\n` +
    `⚠ 改前 \`git diff\` 看现状,勿破坏已 fixed 功能。完成写 ${WORKDIR}/rounds/${round}/impl.md,**首段固定结构如上 + 第二段往后:首行 kind=frontend|backend|data,然后正文叙述本轮改了什么**。`,
    { label:implLabel, phase:"iterate", model:"sonnet" }
  );
```

> ⚠ 本 task 暂时保留 `model:"sonnet"` —— Task 4 单独改 opus,便于 git log 区分动机。

- [ ] **Step 4: 跑测试看 PASS + 旧测试不破**

```bash
cd .claude/skills/web-loop && \
  node --check workflow-template.js && \
  node tests/test-implementer-prompt-priority.mjs && \
  node tests/test-implementer-prompt.mjs && \
  node tests/test-reviewer-prompt-rootcause.mjs && \
  node tests/test-reviewer-prompt.mjs
```

Expected: 全 PASS。注:旧 `test-implementer-prompt.mjs` 的 `'勿偏离 GOAL 全局'` 字样保留在新 prompt 的 must 段(round≥2 分支),应仍过。

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/web-loop/workflow-template.js .claude/skills/web-loop/tests/test-implementer-prompt-priority.mjs
git commit -m "web-loop/template: implementer prompt 加 5 级优先级 + 强制判断题 + 反根因段

final_report §3.5a-i/§3.5a-ii:
- 5 级优先级显式标定:human-hint > 本轮 must(含 nextStepPlan/根因/影响文件)
  > forbiddenApproaches > 历史 reviews > 历史 impl.md 反根因
- 强制 Read affectedFiles + Read 历史 + Read human-hint(若存在)+ mv consumed
- impl.md 首段固定结构(reviewer_stuck/plan 重复分析/反根因)→ 下轮
  reviewer 据此元判断走偏(不破 reviewer 红线 — 读 implementer 中转信号)

本 task 保留 model:sonnet,Task 4 单独改 opus(便于 git log 区分)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: implementer model 改 opus(用户拍板,§3.5b / §5.1)

**Files:**
- Modify: `.claude/skills/web-loop/workflow-template.js`(implementer agent options 内 `model:"sonnet"` 改 `"opus"`)
- Test: `.claude/skills/web-loop/tests/test-implementer-opus.mjs`(新建)

**Interfaces:**
- Consumes: 已在 Task 3 改完的 implementer prompt
- Produces: implementer agent 全程 opus(单一 model 字段切换,接受 token 成本)

- [ ] **Step 1: 写 RED 测试**

创建 `.claude/skills/web-loop/tests/test-implementer-opus.mjs`,内容:

```js
import { readTemplate, assertMatches, assertNotContains, ok } from './_helpers.mjs';
const src = readTemplate();

// implementer agent options 内 model:"opus"
assertMatches(src, /label:\s*implLabel[\s\S]{0,400}model:\s*"opus"/, 'implementer agent 用 opus');
assertMatches(src, /label:\s*implLabel[\s\S]{0,400}phase:\s*"iterate"/, 'implementer agent phase=iterate(契约不变)');

// 旧 sonnet 在 implementer 调用块内消失(其他 sonnet agent 保留)
// 用上下文锁定 implementer 块:label:implLabel 段内不应再有 model:"sonnet"
const implBlock = src.match(/label:implLabel[\s\S]{0,400}model:[^,}]+/);
if (!implBlock || /model:\s*"sonnet"/.test(implBlock[0])) {
  console.error(`FAIL implementer model: 仍含 sonnet — ${implBlock?.[0]||'未找到 label:implLabel 块'}`);
  process.exit(1);
}

ok('test-implementer-opus');
```

- [ ] **Step 2: 跑测试看 FAIL**

```bash
cd .claude/skills/web-loop && node tests/test-implementer-opus.mjs
```

Expected: FAIL — implementer 仍 sonnet。

- [ ] **Step 3: 实现 — 改 implementer agent options**

定位 Task 3 留下的 `{ label:implLabel, phase:"iterate", model:"sonnet" }`,改为:

```js
{ label:implLabel, phase:"iterate", model:"opus" }
```

⚠ 只改这一处(implementer)。smoke / refresh / capture / persist / rollback 等其他 sonnet agent **保持 sonnet 不动**——本决策仅针对 implementer(§5.1 决策记录明确)。

- [ ] **Step 4: 跑测试看 PASS + 全测试套件不破**

```bash
cd .claude/skills/web-loop && \
  node --check workflow-template.js && \
  for f in tests/test-*.mjs; do node "$f" || exit 1; done && echo ALL GREEN
```

Expected: ALL GREEN

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/web-loop/workflow-template.js .claude/skills/web-loop/tests/test-implementer-opus.mjs
git commit -m "web-loop/template: implementer model sonnet → opus(用户拍板,§5.1)

接受 token 成本换执行端 ceiling:
- ② 多 must 互冲需多约束联合优化 → opus 强项
- 用户原话「opus agent 负责…类似 superpowers 写 spec 和 writing-plan」
  字面落地 = opus reviewer 写 plan + opus implementer 执行
- 实质破宪法「Implementer 一律 sonnet」,但 web-loop 多轮迭代 bug-fix
  与 superpowers 一次性 task 性质不同,例外条款待 P2 加 CLAUDE.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: 3 条机检判据(oscillating / treadmill / missingStates)+ paused.md 写入

**Files:**
- Modify: `.claude/skills/web-loop/workflow-template.js`(iterate loop 末尾,history.push 后)
- Test: `.claude/skills/web-loop/tests/test-stall-criteria.mjs`(新建)

**Interfaces:**
- Consumes: 现有 `issues`(:107 mergeIssues 维护的台账)/ `history`(:379 push 的轨迹,含 `newMust` / `mustStaleStreak` / `coveredThisRound`)/ `verifiedLog`(:346)/ `GOAL_SUBGOALS` / `round`
- Produces: 新增 3 个 boolean(`oscillating` / `treadmill` / `missingStates`)+ `pausedReason`(若任一 true)+ 写 `<workdir>/paused.md` + `paused=true` 退出循环(`stalled = stalled || paused`,保留 issues.json/verified.json/refs/)

- [ ] **Step 1: 写 RED 测试**

创建 `.claude/skills/web-loop/tests/test-stall-criteria.mjs`,内容:

```js
import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// 判据 1: oscillating(regressionCount >= 2 + status open/regressed)
assertContains(src, 'oscillating', '判据 1 变量 oscillating 存在');
assertMatches(src, /regressionCount[\s\S]{0,200}>=\s*2/, '判据 1 算法 regressionCount >= 2');

// 判据 2: treadmill(REVIEW_LENSES 上同 lens 新 must 增速 ≥ 修复速持续 2 轮)
assertContains(src, 'treadmill', '判据 2 变量 treadmill 存在');
assertMatches(src, /REVIEW_LENSES\.some|REVIEW_LENSES\.some/, '判据 2 算法遍历 REVIEW_LENSES');

// 判据 3: missingStates(GOAL_SUBGOALS 上 unverifiable ≥2 轮 + requiredStates 重叠)
assertContains(src, 'missingStates', '判据 3 变量 missingStates 存在');
assertMatches(src, /GOAL_SUBGOALS[\s\S]{0,400}unverifiable/, '判据 3 引用 GOAL_SUBGOALS + unverifiable');
assertMatches(src, /requiredStates[\s\S]{0,300}重叠|重叠[\s\S]{0,200}requiredStates/, '判据 3 检测 requiredStates 重叠');

// 触发后写 paused.md + 退出循环
assertContains(src, 'paused.md', 'paused.md 协议文件');
assertMatches(src, /test\s+-f[\s\S]{0,200}paused\.md|>\s*\$\{WORKDIR\}\/paused\.md/, '写 ${WORKDIR}/paused.md');
assertContains(src, 'pausedReason', 'pausedReason 字段记录触发判据');

// 触发判据描述
assertContains(src, '判据 1', 'paused.md 描述判据 1');
assertContains(src, '判据 2', 'paused.md 描述判据 2');
assertContains(src, '判据 3', 'paused.md 描述判据 3');

ok('test-stall-criteria');
```

- [ ] **Step 2: 跑测试看 FAIL**

```bash
cd .claude/skills/web-loop && node tests/test-stall-criteria.mjs
```

Expected: FAIL

- [ ] **Step 3: 实现 — 在 iterate loop 末尾(workflow-template.js:382 `stalled = ...` 后)加 3 判据 + paused.md**

定位 workflow-template.js:382:
```js
  converged=(allPass && openMust.length===0 && allSubgoalsCovered);
  stalled=(!converged && allPresent && mustStaleStreak>=STALE_ROUNDS);
}
```

在 `stalled=...` 之后、`}` 之前(while 循环末尾)插入:

```js

  // ────────── 3 条机检判据(P0 §3.4,2026-06-21 final_report skeptic §2)──────────
  // 触发任一 = workflow stall,写 paused.md + 退出循环(保留 issues/verified/refs)
  // 续修协议(§3.7):用户写 ${WORKDIR}/human-hint-r${round+1}.md + Workflow({resumeFromRunId})

  // 判据 1:同一 must 跨轮"修复 → 回归"震荡 ≥ 2 次
  // 含义:implementer 在两个修法之间反复横跳 = ② 多 must 互冲硬证据
  const oscillating = issues.some(i =>
    i.severity === 'must' && (i.regressionCount || 0) >= 2 &&
    (i.status === 'open' || i.status === 'regressed')
  );

  // 判据 2:同 lens 新 must 累计 ≥ 老 must fixed 累计 且最近 2 轮差值单调不降
  // 含义:每修一个旧 must 引入一个新 must(原地踏步;因 id 不同 mustStaleStreak 不计)
  const treadmill = REVIEW_LENSES.some(lens => {
    const recent2 = history.slice(-2);
    if (recent2.length < 2 || round < 3) return false;
    const newCumByRound = history.map((_, idx) =>
      history.slice(0, idx + 1).reduce((s, h) =>
        s + (Array.isArray(h.verdicts) && h.verdicts.find(v => v.lens === lens) ? (h.newMust || 0) : 0), 0));
    const fixedCum = issues.filter(i =>
      i.lens === lens && i.status === 'fixed').length;
    const lastNewCum = newCumByRound[newCumByRound.length - 1];
    const prevNewCum = newCumByRound[newCumByRound.length - 2];
    return lastNewCum >= fixedCum && lastNewCum > 0 && lastNewCum >= prevNewCum;
  });

  // 判据 3:同 GOAL 子项 unverifiable 跨 ≥ 2 轮 + requiredStates 集合有重叠
  // 含义:capture STATES 漏一必要状态,workflow 内无法补,必须人补 STATES
  const missingStates = (GOAL_SUBGOALS || []).some(g => {
    const recent = issues.filter(i =>
      i.matchesSubgoal === g.id && i.unverifiable &&
      Array.isArray(i.requiredStates) && i.requiredStates.length);
    if (recent.length < 2) return false;
    const allStates = recent.flatMap(i => i.requiredStates);
    return new Set(allStates).size < allStates.length;  // 至少一 state 在多 issue 重复
  });

  const pausedReason = oscillating ? 'oscillating'
                     : treadmill ? 'treadmill'
                     : missingStates ? 'missingStates'
                     : null;

  if (pausedReason && !converged) {
    // 写 paused.md(P0 §3.7 续修协议,sketch §2.5)
    const pausedBody = `# PAUSED · runtag=${RUNTAG} · round=${round}\n\n` +
      `触发判据:**${pausedReason}**\n\n` +
      `## 判据 1 · oscillating(${oscillating})\n含义:同 must 跨轮 fixed→regressed 震荡 ≥2 次(implementer 在两修法间反复横跳;多 must 互冲硬证据)。\n${oscillating ? `震荡 must id 清单:${JSON.stringify(issues.filter(i=>i.severity==='must'&&(i.regressionCount||0)>=2).map(i=>i.id))}` : '未触发。'}\n\n` +
      `## 判据 2 · treadmill(${treadmill})\n含义:同 lens 新 must 累计 ≥ 修复累计且最近 2 轮差值单调不降(每修一旧 must 引入一新 must;mustStaleStreak 因 id 不同不计 = STALE 盲区)。\n\n` +
      `## 判据 3 · missingStates(${missingStates})\n含义:GOAL 子项 unverifiable 跨 ≥2 轮 + requiredStates 重叠 = capture STATES 漏一必要状态(workflow 内无能力补,必须人补 STATES 后重启)。\n\n` +
      `## 当前 open must 完整台账\n\`\`\`json\n${JSON.stringify(issues.filter(i=>(i.status==='open'||i.status==='regressed')&&i.severity==='must'),null,2)}\n\`\`\`\n\n` +
      `## 续修指引(P0 §3.7,零 runtime 改动)\n\n` +
      `1. 检查截图 \`${SHOTS_DIR}/${RUNTAG}_*.png\` + 完整 issues.json + verified.json + reviews/round_${String(round).padStart(2,'0')}.md\n` +
      `2. 决策三选一:\n` +
      `   a) **rubric/STATES/refImages 错位** → 改 args 起新 run\n` +
      `   b) **implementer 走偏 / reviewer 根因猜错** → 写 \`${WORKDIR}/human-hint-r${round + 1}.md\`(自然语言一段描述真实根因 / 该改什么文件),然后主会话调 \`Workflow({resumeFromRunId: "${RUNTAG}"})\` 续跑同 run、保留已 verified\n` +
      `   c) **弃 workflow** → 转主会话 + 主会话直接调 sonnet implementer 手工修\n\n` +
      `⚠ 仅同 session 内 resume 可用(SKILL.md L138 已说);跨 session 切换需起新 run。\n`;
    await agent(
      `写 ${WORKDIR}/paused.md(workflow stall 续修协议)。内容(原样写,bash heredoc):\n${safeBlock(pausedBody, '~~~')}\n` +
      `命令:bash -c "cat > ${WORKDIR}/paused.md <<'PAUSED_EOF'\n${pausedBody}\nPAUSED_EOF"`,
      { label:`paused-${rtag}`, phase:"iterate", model:"sonnet" }
    );
    log(`PAUSED at r${round}: ${pausedReason}`);
    stalled = true;  // 兼用现有 stalled 出口走 finalize
  }
}
```

> ⚠ 注意 `}` 是 while 循环的闭合。新代码插在 `stalled=...` 之后、原 `}` 之前。

- [ ] **Step 4: 跑测试看 PASS + 全测试套件不破**

```bash
cd .claude/skills/web-loop && \
  node --check workflow-template.js && \
  node tests/test-stall-criteria.mjs && \
  for f in tests/test-*.mjs; do node "$f" || exit 1; done && echo ALL GREEN
```

Expected: ALL GREEN

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/web-loop/workflow-template.js .claude/skills/web-loop/tests/test-stall-criteria.mjs
git commit -m "web-loop/template: 加 3 条机检判据 + paused.md 续修协议(零 runtime 改动)

final_report §3.4 + §3.7(skeptic §2/§3):
- 判据 1 oscillating: regressionCount>=2(② 多 must 互冲硬证据)
- 判据 2 treadmill: 新 must 增速 ≥ 修复速持续 2 轮(STALE 盲区补全)
- 判据 3 missingStates: 子项 unverifiable+requiredStates 重叠(人补 STATES)
- 触发后写 paused.md(open must + 续修指引)+ stalled=true 走 finalize
- 沿用现有 resumeFromRunId 机制,零 runtime 改动

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: finalize prompt 加 PAUSED 节(若触发 §3.4 判据)

**Files:**
- Modify: `.claude/skills/web-loop/workflow-template.js:411-430`(`finalize` agent 调用)
- Test: `.claude/skills/web-loop/tests/test-finalize-paused.mjs`(新建)

**Interfaces:**
- Consumes: Task 5 产出的 `pausedReason`(string|null) + 已有的 `exitReason`
- Produces: 若 `pausedReason` 非 null,finalize prompt 在 SUMMARY 顶部插一节 "## ⚠ PAUSED · 触发判据 X · 续修指引"

- [ ] **Step 1: 写 RED 测试**

创建 `.claude/skills/web-loop/tests/test-finalize-paused.mjs`,内容:

```js
import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// finalize 引用 pausedReason
assertContains(src, 'pausedReason', 'finalize 引用 pausedReason');

// SUMMARY 顶部 PAUSED 节
assertMatches(src, /##\s*⚠?\s*PAUSED|PAUSED\s*·\s*触发判据/, 'finalize prompt 含 PAUSED 节');

// 续修指引
assertMatches(src, /续修指引|续修协议|续修/, 'finalize PAUSED 节含续修指引');
assertContains(src, 'human-hint-r', 'finalize 提 human-hint-r{N+1}.md 写入');
assertContains(src, 'resumeFromRunId', 'finalize 提 resumeFromRunId');

ok('test-finalize-paused');
```

- [ ] **Step 2: 跑测试看 FAIL**

```bash
cd .claude/skills/web-loop && node tests/test-finalize-paused.mjs
```

Expected: FAIL — pausedReason 还未在 finalize prompt 里。

- [ ] **Step 3: 实现 — 改 finalize agent 调用(workflow-template.js:411-430)**

在 finalize agent 调用之前(workflow-template.js:411 之前)插入一个变量:

```js
const finalizePausedBlock = pausedReason
  ? `## ⚠ PAUSED · 触发判据 ${pausedReason} · 续修指引\n\n` +
    `本 run 在 r${round} 被机检判据触发暂停(详 \`${WORKDIR}/paused.md\`)。三选一:\n` +
    `1. 改 args(rubric/STATES/refImages 错位)起新 run\n` +
    `2. 写 \`${WORKDIR}/human-hint-r${round + 1}.md\`(自然语言)+ 主会话调 \`Workflow({resumeFromRunId: "${RUNTAG}"})\` 续跑同 run、保留已 verified\n` +
    `3. 弃 workflow,转主会话手工修\n\n` +
    `⚠ resumeFromRunId 仅同 session 有效(SKILL.md L138);跨 session 切换需起新 run。\n\n`
  : '';
```

然后在 `await agent(...)` 的 prompt 字符串内,在 `"写 ${WORKDIR}/SUMMARY.md(runtag=${RUNTAG})。**顶部强制 4 节**(按下面顺序),其余节按 v2.6 之前的规则不变:\n\n"` 之后立刻内插 `${finalizePausedBlock}`:

具体改前(workflow-template.js:411-414):
```js
await agent(
  `写 ${WORKDIR}/SUMMARY.md(runtag=${RUNTAG})。**顶部强制 4 节**(按下面顺序),其余节按 v2.6 之前的规则不变:\n\n` +
  `## 本次 GOAL\n\n` +
```

改后:
```js
await agent(
  `写 ${WORKDIR}/SUMMARY.md(runtag=${RUNTAG})。**顶部强制 4 节**(按下面顺序;若 pausedReason 非空,PAUSED 节放最顶上),其余节按 v2.6 之前的规则不变:\n\n` +
  finalizePausedBlock +
  `## 本次 GOAL\n\n` +
```

- [ ] **Step 4: 跑测试看 PASS + 全测试套件不破**

```bash
cd .claude/skills/web-loop && \
  node --check workflow-template.js && \
  node tests/test-finalize-paused.mjs && \
  node tests/test-finalize-summary.mjs && \
  for f in tests/test-*.mjs; do node "$f" || exit 1; done && echo ALL GREEN
```

Expected: ALL GREEN

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/web-loop/workflow-template.js .claude/skills/web-loop/tests/test-finalize-paused.mjs
git commit -m "web-loop/template: finalize SUMMARY 顶部加 PAUSED 节(若触发 §3.4 判据)

final_report §3.4 末段:若 oscillating/treadmill/missingStates 任一触发,
SUMMARY.md 顶部红字标 PAUSED 触发判据 + 三选一续修指引(改 args 起新 run /
写 human-hint-r{N+1}.md + Workflow({resumeFromRunId}) / 弃 workflow)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: SKILL.md 文档更新(args 表 STALE_ROUNDS 注 / §3.4 / §3.7 / implementer=opus 决策记录)

**Files:**
- Modify: `.claude/skills/web-loop/SKILL.md`(args 表 staleRounds 行;新增 4 节)
- Test: `.claude/skills/web-loop/tests/test-skill-doc-decision.mjs`(新建)

**Interfaces:**
- Consumes: Task 1-6 已落地的 schema / prompt / 控制流改动
- Produces:
  - args 表 `maxRounds`/`staleRounds` 行补 "P1 触发判据与 staleRounds 耦合 = max(1, staleRounds-1)" 说明
  - 新增 "三条机检判据触发说明"节(对应 final_report §3.4)
  - 新增 "续修协议:paused.md + human-hint-r{N+1}.md + Workflow({resumeFromRunId})"节(对应 §3.7)
  - 新增 "implementer = opus(本 skill 例外,§5.1 决策记录)"小节

- [ ] **Step 1: 写 RED 测试**

创建 `.claude/skills/web-loop/tests/test-skill-doc-decision.mjs`,内容:

```js
import { readSkillMd, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readSkillMd();

// args 表 staleRounds 行补 P1 耦合说明
assertMatches(src, /staleRounds[\s\S]{0,500}max\(1,?\s*staleRounds\s*-\s*1\)/, 'staleRounds 注 P1 耦合 = max(1, staleRounds-1)');

// 三条机检判据节
assertContains(src, '三条机检判据', '新节「三条机检判据」');
assertContains(src, 'oscillating', 'SKILL.md 提 oscillating');
assertContains(src, 'treadmill', 'SKILL.md 提 treadmill');
assertContains(src, 'missingStates', 'SKILL.md 提 missingStates');

// 续修协议节
assertContains(src, '续修协议', '新节「续修协议」');
assertContains(src, 'paused.md', 'SKILL.md 提 paused.md');
assertContains(src, 'human-hint-r', 'SKILL.md 提 human-hint-r{N+1}.md');
assertContains(src, 'resumeFromRunId', 'SKILL.md 提 resumeFromRunId');

// implementer = opus 决策小节
assertContains(src, 'implementer = opus', '新小节「implementer = opus(本 skill 例外)」');
assertContains(src, '§5.1', 'SKILL.md 引用 final_report §5.1 决策记录');

ok('test-skill-doc-decision');
```

- [ ] **Step 2: 跑测试看 FAIL**

```bash
cd .claude/skills/web-loop && node tests/test-skill-doc-decision.mjs
```

Expected: FAIL

- [ ] **Step 3: 实现 — 改 SKILL.md**

**3a. 改 args 表 `maxRounds`/`staleRounds` 行**(SKILL.md:44):

当前:
```
| `maxRounds`/`staleRounds` | 可选 | 收敛兜底(6 / 2) |
```

改为:
```
| `maxRounds`/`staleRounds` | 可选 | 收敛兜底(6 / 2)。⚠ 启用 P1 meta-agent 后,触发判据 = `mustStaleStreak >= max(1, staleRounds - 1)`,始终在 stalled 退出前 1 轮(或与 staleRounds=1 时同轮)给一次智力救场;判据 (b)(c) 同样挂 max(1, staleRounds-1)。详 「三条机检判据触发说明」节 |
```

**3b. 在「## 红线」节之前(SKILL.md:140 之前)插入 3 个新节**:

定位 SKILL.md:139-140(`<workdir>/issues.json + ...` 末尾、`## 红线` 之前),在其前插入:

```markdown
## 三条机检判据触发说明(P0 §3.4,2026-06-21 final_report)

iterate loop 末尾基于 issues 台账推 3 条无声判据,任一触发即写 `<workdir>/paused.md` + 退出循环(保留 issues.json/verified.json/refs/,沿用现有 stalled 出口走 finalize):

| 判据 | 含义 | 算法(workflow-template.js 末尾) |
|---|---|---|
| `oscillating` | 同一 must 跨轮"修复 → 回归"震荡 ≥2 次,implementer 在两修法间反复横跳(② 多 must 互冲硬证据) | `issues.some(i => i.severity==='must' && (i.regressionCount||0)>=2 && (i.status==='open'||i.status==='regressed'))` |
| `treadmill` | 同 lens 新 must 累计 ≥ 老 must 修复累计 且最近 2 轮差值单调不降(每修一旧 must 引入一新 must;mustStaleStreak 因 id 不同不计) | `REVIEW_LENSES.some(lens => ...)` 见代码 |
| `missingStates` | 同 GOAL 子项 unverifiable 跨 ≥2 轮 + requiredStates 集合有重叠 = capture STATES 漏一必要状态(workflow 内无能力补) | `(GOAL_SUBGOALS||[]).some(g => ...)` 见代码 |

⚠ 触发后**不硬退出**——保留所有 workdir 文件,SUMMARY 顶部显式标 PAUSED 触发判据 + 续修指引(见下节)。

## 续修协议(P0 §3.7,零 runtime 改动)

§3.4 任一判据触发时,workflow 写 `<workdir>/paused.md` + `stalled=true` 走 finalize。用户三选一:

1. **rubric/STATES/refImages 错位** → 改 args 起新 run
2. **implementer 走偏 / reviewer 根因猜错** → 写 `<workdir>/human-hint-r{N+1}.md`(自然语言一段,描述真实根因 / 该改什么文件)→ 主会话调 `Workflow({resumeFromRunId: "<runtag>"})` 续跑同 run,保留已 verified 子项不重做
3. **弃 workflow** → 转主会话 + sonnet implementer 手工修

**iterate 顶端**自动检测 `<workdir>/human-hint-r${round}.md` —— 若存在,Read 内容并以"优先级 1 · 用户人工指令"段插入 implementer prompt 顶部;消化完 `mv` 到 `human-hint-r${round}.consumed.md` 防止下轮重复消费。

**skill 入口控制流**(主会话生成 args 之前):若检测到 `<workdir>/paused.md` 存在 + `<workdir>/human-hint-r{N+1}.md` 存在 → **不走 setup**(rubric/smoke baseline 已验证)、**不重做 r1..rN**(verified 已在台账)、直接调 `Workflow({resumeFromRunId: <runtag>})` 进 iterate r{N+1}。

⚠ `resumeFromRunId` 仅同 session 有效(SKILL.md 已说);跨 session 切换 = 起新 run(失去 verified 进度)。

## implementer = opus(本 skill 例外,final_report §5.1 决策记录)

CLAUDE.md 宪法是「Implementer 一律 sonnet 禁用 haiku」,本 skill 是**单一例外**(用户 2026-06-21 拍板):

- 理由 1:web-loop implementer 每轮要做"逆向工程已出错代码 + 多约束联合权衡 + 把策略级 nextStepPlan 翻译成精确 Edit 调用"——search + 约束推理,opus 强项
- 理由 2:② 多 must 互冲在 multi-round 是结构性必然,sonnet 联合优化结构性弱
- 理由 3:用户原话"opus agent 负责…类似 superpowers 写 spec 和 writing-plan"字面落地 = opus reviewer 写 plan + opus implementer 执行
- token 成本估算:单 run 多 30-80K opus,但若 opus impl 命中率高 → 总轮数从 5-6 降到 3-4 → **总 token 可能净降**

**仅 implementer 例外,其他 sonnet agent(smoke / refresh / capture / persist / rollback)维持 sonnet**——本决策不滑坡。CLAUDE.md 加 web-loop 例外条款是 P2(详 final_report §5.1)。

```

> ⚠ 注意:`## 续修协议` 节末尾的实际换行符需保留,不要把它合并到下一节标题前;新节插入位置在 SKILL.md:139(`## 红线` 之前)。

- [ ] **Step 4: 跑测试看 PASS + 全测试套件不破**

```bash
cd .claude/skills/web-loop && \
  node --check workflow-template.js && \
  node tests/test-skill-doc-decision.mjs && \
  node tests/test-skill-doc.mjs && \
  for f in tests/test-*.mjs; do node "$f" || exit 1; done && echo ALL GREEN
```

Expected: ALL GREEN(若旧 `test-skill-doc.mjs` 因新节插入而触发其他断言失败,确认它检查的是绝对存在的字段——新节只是增加内容,不删旧内容)

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/web-loop/SKILL.md .claude/skills/web-loop/tests/test-skill-doc-decision.mjs
git commit -m "web-loop/skill: SKILL.md 加 3 节(机检判据/续修协议/implementer=opus 决策)

final_report §3.4 + §3.7 + §5.1:
- args 表 staleRounds 行补 P1 触发耦合说明 = max(1, staleRounds - 1)
- 「三条机检判据触发说明」节:oscillating/treadmill/missingStates
- 「续修协议」节:paused.md + human-hint-r{N+1}.md + resumeFromRunId
- 「implementer = opus(本 skill 例外)」节:CLAUDE.md 宪法例外记录

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: P1 — META_AGENT_SCHEMA + 触发判据 + meta-agent 调用 + 落 decision_log.json

**Files:**
- Modify: `.claude/skills/web-loop/workflow-template.js`(iterate loop 末尾,在 paused.md 块之后、while 循环末尾 `}` 之前 —— 即 reviewer 之后 / 下轮 implementer 之前)
- Test: `.claude/skills/web-loop/tests/test-p1-meta-agent.mjs`(新建)

**Interfaces:**
- Consumes:
  - 现有 `mustStaleStreak`(:359)/ `coveredThisRound` / `history`(:379)/ `verifiedLog` / `subgoalCoverage` / `STALE_ROUNDS`(:24)
  - Task 5 已加的 `pausedReason`(只在未 paused 时触发 P1)
- Produces:
  - 顶部声明 `META_AGENT_SCHEMA`(3 字段,物理禁双源真理)
  - iterate loop 末尾(reviewer 后 / 下轮 implementer 前)条件触发 meta-agent 调用
  - 写 `<workdir>/decision_log.json`(append-only)
  - 若 meta-agent 返回 `escapeRequest` 非 null → 触发等同 §3.4 paused.md 流程(扩展 `pausedReason = 'escapeRequest'`)

> ⚠ **Workflow runtime 一次性 args 冻结的副作用**:Workflow 启动后无外部参数注入通道(MEMORY 中 reference_workflow_tool_mechanics 已坐实)。P1 触发依据的"额外几轮 coveredSubgoals/git diff"信号需在循环内**自维护跨轮计数**(`coveredSubgoalsUnchangedRounds` / `gitDiffSmallRounds`),不能依赖 args。

- [ ] **Step 1: 写 RED 测试**

创建 `.claude/skills/web-loop/tests/test-p1-meta-agent.mjs`,内容:

```js
import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// META_AGENT_SCHEMA 顶部声明(物理禁双源真理:无 issues / verified / rootCauseHypothesis 字段)
assertContains(src, 'META_AGENT_SCHEMA', 'META_AGENT_SCHEMA 顶部声明');
assertMatches(src, /META_AGENT_SCHEMA[\s\S]{0,800}forbiddenApproaches/, 'schema 含 forbiddenApproaches');
assertMatches(src, /META_AGENT_SCHEMA[\s\S]{0,800}prioritizedMustIds/, 'schema 含 prioritizedMustIds');
assertMatches(src, /META_AGENT_SCHEMA[\s\S]{0,800}escapeRequest/, 'schema 含 escapeRequest');
assertMatches(src, /META_AGENT_SCHEMA[\s\S]{0,1000}required:\s*\[\s*"forbiddenApproaches"/, 'schema required = forbiddenApproaches');

// 4 类 escapeRequest type
assertContains(src, 'missing_state', 'escapeRequest type missing_state');
assertContains(src, 'rubric_too_strict', 'escapeRequest type rubric_too_strict');
assertContains(src, 'goal_unrealistic', 'escapeRequest type goal_unrealistic');
assertContains(src, 'reviewer_disagreement', 'escapeRequest type reviewer_disagreement');

// 触发判据 P1_TRIGGER_STREAK = max(1, STALE_ROUNDS - 1)
assertContains(src, 'P1_TRIGGER_STREAK', 'P1_TRIGGER_STREAK 变量');
assertMatches(src, /P1_TRIGGER_STREAK\s*=\s*Math\.max\(\s*1\s*,\s*STALE_ROUNDS\s*-\s*1\s*\)/, 'P1_TRIGGER_STREAK = max(1, STALE_ROUNDS-1)');

// 三条触发判据
assertContains(src, 'coveredSubgoalsUnchangedRounds', 'P1 触发 coveredSubgoalsUnchangedRounds');
assertContains(src, 'gitDiffSmallRounds', 'P1 触发 gitDiffSmallRounds');
assertContains(src, 'p1Triggered', 'p1Triggered 变量');

// meta-agent 调用 label + model opus
assertMatches(src, /label:\s*`?meta-agent-?[\s\S]{0,200}model:\s*"opus"/, 'meta-agent 调用 model=opus');
assertMatches(src, /label:\s*`?meta-agent[\s\S]{0,200}phase:\s*"iterate"/, 'meta-agent 调用 phase=iterate');

// schema 强约束 prompt 字样
assertContains(src, '不质疑、不修改、不复判', 'meta-agent prompt 强约束');
assertContains(src, '台账真相', 'meta-agent prompt 「reviewer 的 issues/verified 是台账真相」');

// 落 decision_log.json append-only
assertContains(src, 'decision_log.json', '落 decision_log.json');

// escapeRequest 触发 paused
assertMatches(src, /escapeRequest[\s\S]{0,500}pausedReason\s*=\s*['"]escapeRequest|pausedReason\s*=\s*['"]escapeRequest/, 'escapeRequest 非 null → pausedReason=escapeRequest');

ok('test-p1-meta-agent');
```

- [ ] **Step 2: 跑测试看 FAIL**

```bash
cd .claude/skills/web-loop && node tests/test-p1-meta-agent.mjs
```

Expected: FAIL

- [ ] **Step 3: 实现**

**3a. 顶部声明 `META_AGENT_SCHEMA`** —— 加在 `REVIEWER_SCHEMA` 声明之后(workflow-template.js:189 之后)。

```js
// ── P1 meta-agent schema(物理禁双源真理:无 issues / verified / rootCauseHypothesis 字段)──
// final_report §4.2 / redesigner-proposal §6.3.1:
//   forbiddenApproaches = 跨轮"试过且失败"清单,下轮 implementer prompt 优先级 3
//   prioritizedMustIds  = 仅排序,不新增不删除 must
//   escapeRequest       = 元判断退出通道(4 类),非 null 触发 paused.md
const META_AGENT_SCHEMA = { type:"object", required:["forbiddenApproaches"],
  properties:{
    forbiddenApproaches:{ type:"array",
      items:{ type:"object", required:["issueId","triedMethod","why_failed_evidence"],
        properties:{ issueId:{type:"string"}, triedMethod:{type:"string"}, why_failed_evidence:{type:"string"} }}},
    prioritizedMustIds:{ type:"array", items:{type:"string"} },
    escapeRequest:{ type:["object","null"],
      properties:{ type:{enum:["missing_state","rubric_too_strict","goal_unrealistic","reviewer_disagreement"]}, detail:{type:"string"} }}
  }};
```

**3b. 顶部加 P1 跨轮计数器**——在 `let round=0, mustStaleStreak=0, ...`(workflow-template.js:235)那行加两个字段。

当前:
```js
let round=0, mustStaleStreak=0, converged=false, stalled=false;
```

改为:
```js
let round=0, mustStaleStreak=0, converged=false, stalled=false, pausedReason=null;
let coveredSubgoalsUnchangedRounds=0, gitDiffSmallRounds=0;
let lastCoveredSubgoalsKey='';
```

> ⚠ 注意:`pausedReason` 早期声明替代了 Task 5 的内部声明——需要把 Task 5 那次的 `const pausedReason = ...` 改为 `pausedReason = ...`(去掉 `const`)。把这一改动合在 Task 8 step 3 内完成。

**3c. 在 history.push 之后(workflow-template.js:379-380 之间)更新计数器**:

定位 workflow-template.js:379:
```js
  history.push({ round, verdicts:present.map(v=>({lens:v.lens,verdict:v.verdict,...(v.declaredVerdict?{declaredVerdict:v.declaredVerdict}:{}),n:(v.issues||[]).length})), openMust:openMust.length, newMust, mustStaleStreak, coveredThisRound:[...coveredThisRound], allSubgoalsCovered });
```

在它后面加:
```js
  // ── P1 触发计数器(coveredSubgoals 集合连续 N 轮未增 / git diff 连续 N 轮 < 5 行)──
  const coveredKey = [...coveredThisRound].sort().join('|');
  if (round >= 2 && coveredKey === lastCoveredSubgoalsKey) coveredSubgoalsUnchangedRounds++;
  else coveredSubgoalsUnchangedRounds = 0;
  lastCoveredSubgoalsKey = coveredKey;
  // git diff 行数:轻量调一次 bash 探(脚本内 bash 是 agent 调用,只能延迟到下方)
```

**3d. 改 Task 5 加的 `const pausedReason = ...` 为赋值**:

把 Task 5 加的:
```js
  const pausedReason = oscillating ? 'oscillating'
                     : treadmill ? 'treadmill'
                     : missingStates ? 'missingStates'
                     : null;
```

改为:
```js
  pausedReason = oscillating ? 'oscillating'
               : treadmill ? 'treadmill'
               : missingStates ? 'missingStates'
               : null;
```

**3e. 在 Task 5 的 paused.md 块之后、while 循环末尾 `}` 之前** 插入 P1 触发与 meta-agent 调用:

```js

  // ────────── P1 缩窄版 meta-agent(final_report §4.2,2026-06-21)──────────
  // 位置:reviewer 后 / 下轮 implementer 前 → 触发条件具备时,本轮 reviewer 已出 must,
  //       meta-agent 写 decision_log.json,下轮 implementer prompt 优先级 3 内插。
  // 触发:三通道 OR(oscillating/treadmill 已被 §3.4 paused.md 截获,P1 只在未 paused
  //       且 P1_TRIGGER_STREAK 命中时触发),P1_TRIGGER_STREAK 与 staleRounds 自适应耦合。
  // schema 物理禁双源真理:仅 forbiddenApproaches / prioritizedMustIds / escapeRequest。
  const P1_TRIGGER_STREAK = Math.max(1, STALE_ROUNDS - 1);
  // 探 git diff 行数(挂判据 c)
  const diffStat = await agent(
    `【${rtag} · p1-diffstat】bash 跑 \`git diff HEAD~1..HEAD --stat 2>/dev/null | tail -1\`,返回 totalLines(全 stat 末行末尾 "X insertions(+), Y deletions(-)" 求 X+Y;无 commit 或失败 → 返回 0)。`,
    { label:`p1-diffstat-${rtag}`, phase:"iterate", model:"sonnet",
      schema:{ type:"object", required:["totalLines"], properties:{ totalLines:{type:"integer"} } } }
  );
  const diffLines = diffStat?.totalLines || 0;
  if (round >= 2 && diffLines < 5) gitDiffSmallRounds++;
  else gitDiffSmallRounds = 0;

  const p1Triggered = !converged && !pausedReason && round >= 2 && (
    mustStaleStreak >= P1_TRIGGER_STREAK ||
    coveredSubgoalsUnchangedRounds >= P1_TRIGGER_STREAK ||
    gitDiffSmallRounds >= P1_TRIGGER_STREAK
  );

  if (p1Triggered) {
    log(`P1 meta-agent triggered at r${round} (streak=${mustStaleStreak}/cov=${coveredSubgoalsUnchangedRounds}/diff=${gitDiffSmallRounds}, threshold=${P1_TRIGGER_STREAK})`);
    const recentReviewsList = [round, round - 1, round - 2].filter(r => r >= 1).map(r =>
      `- ${WORKDIR}/reviews/round_${String(r).padStart(2,'0')}.md`).join('\n');
    const recentImplList = [round, round - 1, round - 2].filter(r => r >= 1).map(r =>
      `- ${WORKDIR}/rounds/${r}/impl.md`).join('\n');

    const metaResult = await agent(
      `【${rtag} · meta-agent】P1 元层 agent(opus)。本轮触发判据 ` +
      `mustStaleStreak=${mustStaleStreak} / coveredSubgoalsUnchangedRounds=${coveredSubgoalsUnchangedRounds} / gitDiffSmallRounds=${gitDiffSmallRounds}(P1_TRIGGER_STREAK=${P1_TRIGGER_STREAK})。\n\n` +
      `【你的任务(redesigner-proposal §6.3 缩窄版)】\n` +
      `跨轮综合最近 ≤3 轮 reviews + impl.md + git log + decision_log.json,产出 3 字段(见 schema):\n` +
      `1. forbiddenApproaches:跨轮"试过且失败"清单(下轮 implementer 强制规避)\n` +
      `2. prioritizedMustIds:仅排序 issues.json 已有 must id 子集(不新增不删除)\n` +
      `3. escapeRequest(可空):元判断退出通道(4 类)\n\n` +
      `【⚠ 强约束 · 不破双源真理】reviewer 的 issues/verified 是台账真相,你**不质疑、不修改、不复判**;若产生对某 must 的不同看法,必须走 \`escapeRequest.type=reviewer_disagreement\` 通道(强制人工介入,不让 implementer 选边)。\n\n` +
      `【输入(Read 这些文件,不重传内容)】\n` +
      `- ${WORKDIR}/goal.md(GOAL 原文 + 子项)\n` +
      `- ${WORKDIR}/refs/manifest.json(若存在;视觉目标参考)\n` +
      `- 最近 ≤3 轮 reviews:\n${recentReviewsList}\n` +
      `- 最近 ≤3 轮 impl.md:\n${recentImplList}\n` +
      `- ${WORKDIR}/decision_log.json(若存在;上轮 P1 输出,跨轮防重复)\n\n` +
      `【其他证据 inline】\n` +
      `- 当前 issues 完整台账:${safeBlock(JSON.stringify(issues, null, 2), '\`\`\`json')}\n` +
      `- 当前 verifiedLog:${safeBlock(JSON.stringify(verifiedLog, null, 2), '\`\`\`json')}\n` +
      `- bash: cd ${UI_DIR} && git log --oneline -${Math.min(round, 5)}(若 implementer 都在源码区改动)\n\n` +
      `【escapeRequest 4 类语义】\n` +
      `- \`missing_state\` → capture STATES 漏一必要状态(workflow 内无能力补,人补 STATES 后起新 run)\n` +
      `- \`rubric_too_strict\` → rubric 验收门设过高,合理实现都判 fail(改 rubric 起新 run)\n` +
      `- \`goal_unrealistic\` → GOAL 本身在当前架构下做不到(改 goal 起新 run 或转主会话设计)\n` +
      `- \`reviewer_disagreement\` → 你判断某 must 的根因/严重度与 reviewer 不一致(强制人工介入)\n\n` +
      `按 schema 输出。`,
      { label:`meta-agent-${rtag}`, phase:"iterate", model:"opus", schema:META_AGENT_SCHEMA });

    // 落 decision_log.json append-only
    if (metaResult) {
      const logEntry = {
        round,
        forbiddenApproaches: metaResult.forbiddenApproaches || [],
        prioritizedMustIds: metaResult.prioritizedMustIds || [],
        escapeRequest: metaResult.escapeRequest || null
      };
      await agent(
        `【${rtag} · decision-log-append】把本轮 meta-agent 输出 append 到 ${WORKDIR}/decision_log.json(若文件不存在则初始化为 \`{"entries":[]}\`;append 后 entries 数组追加本轮 entry)。bash 推荐:\n` +
        `\`\`\`bash\n` +
        `python3 -c "import json,os,sys; p='${WORKDIR}/decision_log.json'; d=json.load(open(p)) if os.path.exists(p) else {'entries':[]}; d['entries'].append(json.loads(sys.argv[1])); json.dump(d, open(p,'w'), indent=2, ensure_ascii=False)" '${safeInsert(JSON.stringify(logEntry))}'\n` +
        `\`\`\`\n` +
        `若用户环境无 python3,fallback 写一个 node ESM 等价脚本到 \`/tmp/_dlog.mjs\` 跑完即删。`,
        { label:`decision-log-${rtag}`, phase:"iterate", model:"sonnet" }
      );

      // escapeRequest 非 null → 触发等同 paused.md 流程
      if (metaResult.escapeRequest && metaResult.escapeRequest.type) {
        pausedReason = 'escapeRequest';
        const escapeBody = `# PAUSED · runtag=${RUNTAG} · round=${round}\n\n` +
          `触发判据:**escapeRequest**(P1 meta-agent §4.2)\n\n` +
          `## escapeRequest.type = ${metaResult.escapeRequest.type}\n\n` +
          `${safeInsert(metaResult.escapeRequest.detail || '')}\n\n` +
          `## 续修指引\n\n` +
          `- \`missing_state\` → 补 STATES(args.states),起新 run\n` +
          `- \`rubric_too_strict\` → 改 rubric / goal,起新 run\n` +
          `- \`goal_unrealistic\` → 转主会话设计 / 重定义 GOAL,起新 run\n` +
          `- \`reviewer_disagreement\` → 主会话人工裁定 reviewer vs meta-agent 哪条对,写 \`${WORKDIR}/human-hint-r${round + 1}.md\` 后 \`Workflow({resumeFromRunId: "${RUNTAG}"})\`\n`;
        await agent(
          `写 ${WORKDIR}/paused.md(覆盖):\n${safeBlock(escapeBody, '~~~')}\n` +
          `命令:bash -c "cat > ${WORKDIR}/paused.md <<'ESC_EOF'\n${escapeBody}\nESC_EOF"`,
          { label:`paused-escape-${rtag}`, phase:"iterate", model:"sonnet" }
        );
        log(`PAUSED at r${round}: escapeRequest=${metaResult.escapeRequest.type}`);
        stalled = true;
      }
    }
  }
}
```

> ⚠ 注意 `}` 是 while 循环的闭合;新代码块插在 Task 5 paused.md 块之后、原 `}` 之前。

- [ ] **Step 4: 跑测试看 PASS + 全测试套件不破**

```bash
cd .claude/skills/web-loop && \
  node --check workflow-template.js && \
  node tests/test-p1-meta-agent.mjs && \
  for f in tests/test-*.mjs; do node "$f" || exit 1; done && echo ALL GREEN
```

Expected: ALL GREEN

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/web-loop/workflow-template.js .claude/skills/web-loop/tests/test-p1-meta-agent.mjs
git commit -m "web-loop/template: P1 缩窄版 meta-agent(opus,stall 触发,3 字段物理禁双源)

final_report §4.2 + redesigner-proposal §6.3:
- META_AGENT_SCHEMA 3 字段:forbiddenApproaches/prioritizedMustIds/
  escapeRequest(物理禁 issues/verified/rootCauseHypothesis 字段)
- P1_TRIGGER_STREAK = max(1, STALE_ROUNDS - 1) 自适应耦合(保 1 轮救场)
- 三通道触发判据(mustStaleStreak / coveredSubgoalsUnchangedRounds /
  gitDiffSmallRounds,运行时自维护跨轮计数器)
- 落 decision_log.json append-only(python3 + node ESM fallback)
- escapeRequest 非 null → pausedReason='escapeRequest' + 写 paused.md +
  stalled=true 走 finalize

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 9: P1 — forbiddenApproaches 注入下轮 implementer prompt(优先级 3)

**Files:**
- Modify: `.claude/skills/web-loop/workflow-template.js:256-270`(implementer agent 调用,把 Task 3 留的 `decisionLog` 段从"仅 Read 文件"升级为"内插 forbiddenApproaches 数组到 prompt 顶部")
- Test: `.claude/skills/web-loop/tests/test-p1-implementer-inject.mjs`(新建)

**Interfaces:**
- Consumes: Task 8 落的 `<workdir>/decision_log.json`(若存在,含历史所有 round 的 entries)
- Produces: implementer prompt 在「优先级 3 · 跨轮禁忌」段读取 decision_log.json 实际内容(不再仅指示 Read),把最新 N 轮的 forbiddenApproaches union 内插到 prompt 顶部

> ⚠ 设计选择:Task 3 的版本只让 implementer "Read decision_log.json 然后自己决定"——可靠性弱(opus implementer 可能跳过)。本 task 升级为**在脚本侧 Read 文件 + 内插**,语义更硬。但 Workflow 脚本不能直接 Read 文件(无 fs API)——只能通过先调一个 sonnet agent 把内容回传给主脚本,然后内插。这是 Workflow runtime 的硬限制。

- [ ] **Step 1: 写 RED 测试**

创建 `.claude/skills/web-loop/tests/test-p1-implementer-inject.mjs`,内容:

```js
import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// implementer prompt 含 forbiddenApproaches 内插段
assertMatches(src, /label:\s*implLabel[\s\S]{0,3000}forbiddenApproaches/, 'implementer prompt 含 forbiddenApproaches');

// 脚本侧 read decision_log.json 的 agent 调用(read-decision-log-rtag)
assertMatches(src, /label:\s*`?read-decision-log-?[\s\S]{0,200}phase:\s*"iterate"/, 'read-decision-log agent 在 iterate phase');

// forbiddenApproaches union 内插(动态生成段,基于读到的内容)
assertContains(src, 'forbiddenList', 'forbiddenList 变量(union 后内插到 prompt)');

// 优先级 3 段含"不得重试"指令
assertContains(src, '不得重试', 'implementer 强制「不得重试」forbiddenApproaches');

ok('test-p1-implementer-inject');
```

- [ ] **Step 2: 跑测试看 FAIL**

```bash
cd .claude/skills/web-loop && node tests/test-p1-implementer-inject.mjs
```

Expected: FAIL

- [ ] **Step 3: 实现 — 在 implementer 调用前(Task 3 的 `const humanHintRead = ...` 之后)加 read-decision-log + 拼装 forbiddenList**

定位 Task 3 落地的 `const decisionLog = round >= 2 ? ...` 段。改写为:

```js
  // 读 decision_log.json(若存在 P1 触发过)→ 拼装 forbiddenList 内插
  let forbiddenList = [];
  if (round >= 2) {
    const dlog = await agent(
      `【${rtag} · read-decision-log】bash 检测 \`${WORKDIR}/decision_log.json\` 是否存在;若存在 Read 整文件,返回 entries 数组的 forbiddenApproaches union(所有 entry 的 forbiddenApproaches 合并);若不存在返回空数组。返回 schema { exists: boolean, forbiddenApproaches: [] }。`,
      { label:`read-decision-log-${rtag}`, phase:"iterate", model:"sonnet",
        schema:{ type:"object", required:["exists","forbiddenApproaches"],
          properties:{ exists:{type:"boolean"},
            forbiddenApproaches:{ type:"array",
              items:{ type:"object",
                properties:{ issueId:{type:"string"}, triedMethod:{type:"string"}, why_failed_evidence:{type:"string"} }}}}}}
    );
    forbiddenList = (dlog?.forbiddenApproaches || []);
  }
  const decisionLog = (round >= 2 && forbiddenList.length)
    ? `【优先级 3 · 跨轮禁忌 forbiddenApproaches(P1 meta-agent 累计产物,${forbiddenList.length} 条)】\n` +
      safeBlock(JSON.stringify(forbiddenList, null, 2), '```json') +
      `\n⚠ 这些 (issueId, triedMethod) 组合在本 run 跨轮试过且失败(why_failed_evidence 含证据),**不得重试**;若你必须重试,在 impl.md 首段单独标 "重试理由:..." 说明为什么这次会成功。`
    : '';
```

> ⚠ Task 3 加的 `${decisionLog}` 内插 placeholder 保持不动——但这里 `decisionLog` 变量的赋值时机要求脚本侧已经 await 完 read-decision-log agent;它在循环每轮顶端早于 implementer 调用,自然满足。

- [ ] **Step 4: 跑测试看 PASS + 全测试套件不破**

```bash
cd .claude/skills/web-loop && \
  node --check workflow-template.js && \
  node tests/test-p1-implementer-inject.mjs && \
  for f in tests/test-*.mjs; do node "$f" || exit 1; done && echo ALL GREEN
```

Expected: ALL GREEN

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/web-loop/workflow-template.js .claude/skills/web-loop/tests/test-p1-implementer-inject.mjs
git commit -m "web-loop/template: forbiddenApproaches 从 decision_log.json 注入下轮 implementer

final_report §3.5a-i 优先级 3 / §4.2:
- 每轮 implementer 前先 read-decision-log agent 读 ${WORKDIR}/decision_log.json
  汇总所有历史 entry 的 forbiddenApproaches union
- 非空时硬内插 implementer prompt「优先级 3 · 跨轮禁忌」段(不再仅 Read 文件,
  把 (issueId, triedMethod, why_failed_evidence) 三元组完整 JSON 喂入)
- 强制「不得重试」指令 + 重试需说明理由

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 10: SKILL.md 加 P1 节(META_AGENT_SCHEMA / 触发判据 / decision_log.json)

**Files:**
- Modify: `.claude/skills/web-loop/SKILL.md`(在 Task 7 加的「续修协议」节之后插一节)
- Test: `.claude/skills/web-loop/tests/test-skill-doc-p1.mjs`(新建)

**Interfaces:**
- Consumes: Task 8/9 落的 P1 实现
- Produces: SKILL.md 增加 P1 节,简述触发判据 / META_AGENT_SCHEMA 物理禁双源 / decision_log.json 协议 / escapeRequest 走 paused 通道

- [ ] **Step 1: 写 RED 测试**

创建 `.claude/skills/web-loop/tests/test-skill-doc-p1.mjs`,内容:

```js
import { readSkillMd, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readSkillMd();

assertContains(src, 'P1 meta-agent', 'SKILL.md 新节「P1 meta-agent」');
assertContains(src, 'META_AGENT_SCHEMA', 'SKILL.md 提 META_AGENT_SCHEMA');
assertContains(src, 'forbiddenApproaches', 'SKILL.md 提 forbiddenApproaches');
assertContains(src, 'escapeRequest', 'SKILL.md 提 escapeRequest');
assertContains(src, 'decision_log.json', 'SKILL.md 提 decision_log.json');
assertMatches(src, /物理禁[\s\S]{0,200}双源|双源真理/, 'SKILL.md 强调物理禁双源真理');

ok('test-skill-doc-p1');
```

- [ ] **Step 2: 跑测试看 FAIL**

```bash
cd .claude/skills/web-loop && node tests/test-skill-doc-p1.mjs
```

Expected: FAIL

- [ ] **Step 3: 实现 — 改 SKILL.md**

在 Task 7 加的「续修协议」节之后(`## implementer = opus(本 skill 例外...)` 节之前)插入:

```markdown
## P1 meta-agent(缩窄版 · stall 触发 · 物理禁双源真理)

reviewer 后 / 下轮 implementer 前位置,触发条件 OR(任一):

```js
const P1_TRIGGER_STREAK = Math.max(1, STALE_ROUNDS - 1);
const p1Triggered = mustStaleStreak >= P1_TRIGGER_STREAK
                 || coveredSubgoalsUnchangedRounds >= P1_TRIGGER_STREAK
                 || gitDiffSmallRounds >= P1_TRIGGER_STREAK;
```

> 触发条件随 `staleRounds` 自适应:`staleRounds=2` → 在 mustStaleStreak==1 时(早 stalled 退出 1 轮)触发;`staleRounds=1` 激进配置下与 stalled 同轮触发,此时 P1 主要价值变成 escapeRequest 给精确失败原因。

**META_AGENT_SCHEMA 3 字段(物理禁双源真理:无 issues / verified / rootCauseHypothesis)**:
- `forbiddenApproaches`: `[{ issueId, triedMethod, why_failed_evidence }, ...]`,跨轮"试过且失败"清单 → 下轮 implementer prompt 优先级 3 内插,强制规避
- `prioritizedMustIds`: 仅排序 issues.json 已有 must id 子集(不新增不删除)
- `escapeRequest`: `{ type, detail } | null`,4 类(`missing_state` / `rubric_too_strict` / `goal_unrealistic` / `reviewer_disagreement`)

**输入**:goal.md + refs/manifest.json + 最近 ≤3 轮 reviews/round_NN.md + impl.md + git log + decision_log.json + issuesJson + verifiedLog。**模型**:opus。**位置**:reviewer 后 / 下轮 implementer 前。

**prompt 强约束**(物理禁双源):"reviewer 的 issues/verified 是台账真相,你**不质疑、不修改、不复判**;若产生对某 must 的不同看法,必须走 `escapeRequest.type=reviewer_disagreement` 通道(强制人工介入,不让 implementer 选边)"。

**落**:`<workdir>/decision_log.json` append-only(每轮 entry = `{round, forbiddenApproaches, prioritizedMustIds, escapeRequest}`)。下轮 implementer prompt 顶部内插 forbiddenApproaches(优先级 3,见 §3.5a-i 优先级模板)。

**escapeRequest 处理**:非 null → 写 `<workdir>/paused.md` + `stalled=true`(走 finalize 的 PAUSED 节)。等同 §3.4 的 paused.md 流程,**escapeRequest 是第 4 类触发判据**(`pausedReason='escapeRequest'`)。

```

- [ ] **Step 4: 跑测试看 PASS + 全测试套件不破**

```bash
cd .claude/skills/web-loop && \
  node --check workflow-template.js && \
  node tests/test-skill-doc-p1.mjs && \
  for f in tests/test-*.mjs; do node "$f" || exit 1; done && echo ALL GREEN
```

Expected: ALL GREEN

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/web-loop/SKILL.md .claude/skills/web-loop/tests/test-skill-doc-p1.mjs
git commit -m "web-loop/skill: SKILL.md 加 P1 meta-agent 节(schema/触发/decision_log)

final_report §4.2 + redesigner-proposal §6.3:
- P1_TRIGGER_STREAK = max(1, staleRounds-1) 三通道触发判据公式
- META_AGENT_SCHEMA 3 字段物理禁双源真理(无 issues/verified/rootCause)
- forbiddenApproaches 跨轮 union 注入下轮 implementer prompt 优先级 3
- escapeRequest 4 类 + reviewer_disagreement 强制人工介入通道
- decision_log.json append-only 协议

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 11: 全套件 final verification + plan 收口

**Files:**
- Test: 全部 `tests/test-*.mjs`

**Interfaces:**
- Consumes: Task 1-10 全部落地
- Produces: 一次性确认 11 个 task(其中 10 个含代码变更)全部绿,无回归

- [ ] **Step 1: 运行完整测试套件(P0 + P1 + 旧测试全绿)**

```bash
cd .claude/skills/web-loop && \
  node --check workflow-template.js && \
  for f in tests/test-*.mjs; do echo "--- $f"; node "$f" || exit 1; done && \
  echo "ALL GREEN"
```

Expected: ALL GREEN(应有 11 个 test-*.mjs 文件 PASS:5 个旧 + 6 个新)

- [ ] **Step 2: git log 确认所有 commit**

```bash
git log --oneline -12
```

Expected: 至少 10 个 `web-loop/<scope>:` commit(对应 Task 1-10),每 task 一 commit。

- [ ] **Step 3: 收口确认 — 9 处改动逐条核对(human review)**

对照 final_report §3.8 实施清单 + §4.2 P1 设计,逐条核对:

| # | 改动 | 落地 task | 核对 |
|---|---|---|---|
| 1 | REVIEWER_SCHEMA 加 4 字段 | Task 1 | grep `nextStepPlan` workflow-template.js |
| 2 | reviewerPrompt code lens brief + nextStepPlan 模板 + 跨轮反思段 | Task 2 | grep `策略级` + `reviewer_stuck` |
| 3 | implementer prompt 5 级优先级 + 强制判断题 + Read 历史 | Task 3 | grep `优先级 1` + `reviewer_stuck` + `Read affectedFiles` |
| 4 | implementer model 改 opus | Task 4 | grep `implLabel` + `model:"opus"` |
| 5 | mustStaleStreak 语义聚类(reviewer prompt 强制 matchesIssueId 优先) | Task 2(reviewer prompt 段)| grep `引用现有 id` |
| 6 | 3 条机检判据 + paused.md(写入)+ iterate 顶端 human-hint Read + mv | Task 3(human-hint Read)+ Task 5(3 判据 + paused.md) | grep `oscillating` `treadmill` `missingStates` + `human-hint-r` |
| 7 | finalize prompt 加 PAUSED 节 | Task 6 | grep `finalizePausedBlock` |
| 8 | SKILL.md 文档(args STALE_ROUNDS / §3.4 / §3.7 / implementer=opus) | Task 7 | grep `三条机检判据` + `续修协议` + `implementer = opus` |
| 9 | P1 meta-agent(schema + 触发 + decision_log + 注入 implementer + escapeRequest)+ SKILL.md 文档 | Task 8 + 9 + 10 | grep `META_AGENT_SCHEMA` + `decision_log.json` + `forbiddenList` |

> skill 入口控制流(§3.7 末段:检测 paused.md + human-hint-r{N+1}.md → 不走 setup、直接进 iterate r{N+1})**仅文档化在 SKILL.md 「续修协议」节**(Task 7)。该控制流是主会话的判断逻辑,不在 workflow 脚本内——SKILL.md 文档化 = 主会话调 skill 时按此行动,**无需脚本侧实现**(workflow 启动后已通过 resumeFromRunId 复用 cache、跳过已 cache 的 setup agent)。

- [ ] **Step 4: 总结提交**

```bash
git log --oneline -12
```

汇报 commit 数量与最终 ALL GREEN 状态。**不主动 push**(用户未授权)。

---

## Self-Review

**1. Spec coverage(对照 final_report §3.8 + §4.2)**

| Spec 项 | 落 task | 状态 |
|---|---|---|
| §3.2 扩 REVIEWER_SCHEMA 4 字段 | Task 1 | ✓ |
| §3.2/§3.5a-ii reviewerPrompt code lens 必填 + 跨轮反思 | Task 2 | ✓ |
| §3.3 mustStaleStreak 语义聚类(reviewer prompt 强制 matchesIssueId 优先,§3.3 轻量修) | Task 2 | ✓ |
| §3.4 三条机检判据 + paused.md | Task 5 | ✓ |
| §3.5a-i 5 级优先级 + 透传 must + Read affectedFiles + Read 历史 reviews + Read impl.md + Read human-hint | Task 3 | ✓ |
| §3.5a-ii 强制判断题 + impl.md 首段固定结构 | Task 3 | ✓ |
| §3.5b implementer model 改 opus | Task 4 | ✓ |
| §3.7 human-hint Read + mv consumed | Task 3(implementer prompt 内) | ✓ |
| finalize PAUSED 节 | Task 6 | ✓ |
| SKILL.md 文档(STALE_ROUNDS + §3.4 + §3.7 + opus 决策) | Task 7 | ✓ |
| §4.2 P1 META_AGENT_SCHEMA + 触发 + decision_log + escapeRequest | Task 8 | ✓ |
| §4.2 P1 forbiddenApproaches 注入 implementer | Task 9 | ✓ |
| §4.2 P1 SKILL.md 文档 | Task 10 | ✓ |
| skill 入口控制流(检测 paused.md + human-hint → 直接进 iterate r{N+1}) | Task 7(文档化)| ✓(脚本无需改;主会话按文档走) |

**2. Placeholder scan**

✓ 全部 step 含具体代码 + 具体行号 + 具体 grep/bash 命令。无"TBD / 实现下面 / 添加错误处理 / similar to Task N"等占位。

**3. Type/Name consistency**

- `pausedReason` 在 Task 5(声明)/ Task 6(finalize 引用)/ Task 8(escapeRequest 改写)三处一致;Task 8 step 3b 显式说明把 Task 5 的 `const pausedReason` 改为模块顶部 `let pausedReason=null`(声明位置上移)以便跨段共享。
- `META_AGENT_SCHEMA` 在 Task 8 单点声明,Task 10 文档引用同名。
- `forbiddenApproaches` 在 schema(Task 8)/ decision_log.json entries(Task 8)/ implementer prompt 注入(Task 9)三处字段名一致。
- `coveredSubgoalsUnchangedRounds` / `gitDiffSmallRounds` / `lastCoveredSubgoalsKey` 顶部声明位置在 Task 8 step 3b 与使用位置(Task 8 step 3c/3e)对齐。
- 旧测试(test-implementer-prompt.mjs:15 `assertContains '勿偏离 GOAL 全局'`)在新 prompt 的 must 段保留,Task 3 step 3 已确认。

无名称漂移。

---

## Execution Handoff

Plan 完整、自包含。新 session 不读本对话上下文也能直接 subagent-driven-development 实施(必读文档已在「必读输入文档」段列出)。

**可粘贴执行命令**:

```
/superpowers:subagent-driven-development docs/superpowers/plans/2026-06-21-web-loop-decision-layer-p0-p1.md
```
