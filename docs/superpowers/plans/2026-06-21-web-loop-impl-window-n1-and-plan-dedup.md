# web-loop: implementer 窗口 N-1 only + reviewer 端 plan 主线自查 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 web-loop skill 的 `workflow-template.js` 中落两件相互独立的事:**(A)** 把 implementer 跨轮 Read 历史 reviews 的窗口从"上 2 轮"砍到"r{N-1} only"(传递性论据,memory `web-loop-decision-layer-redesign` 第 3 条结论);**(B)** reviewer 端 plan 主线自查方案 S 增强版(round≥2 且 lens=="code" 时,reviewerPrompt 新增 ~8-10 行 plan 主线自查 + 临界规则强制换主线 + 真二选一默认收紧)。

**Architecture:** 两件事都改同一个文件 `.claude/skills/web-loop/workflow-template.js`,但改动锚点不同:(A) 改 `historyReviews` 变量(implementer prompt 段,约 L313),(B) 在 `reviewerPrompt` 函数(L113-L170)的 `reflectBlock` 之后、`refsReadInstr` 之前新增 `planDedupBlock` 段并插入 return 模板。两 task 顺序无强依赖,但本 plan 按 (A)→(B) 顺序实施(A 极简,先清掉好让 (B) 集中精力)。无 schema 改动 / 无新 task 文件 / 无新 agent dispatch。

**Tech Stack:** JavaScript (ESM)、`node --check` 语法验证、Workflow tool runtime(workflow-template.js 顶部 `export const meta` + 主线 `phase()/agent()/parallel()/pipeline()` API)、web-loop skill 的多 reviewer 视觉评审循环。

## Global Constraints

- **目标文件**:`/home/yu/PycharmProjects/Trade_Strategy-bo/.claude/skills/web-loop/workflow-template.js`(670 行,ESM,顶部 `export const meta`)
- **禁用 API**:不引入 `Date.now()` / `Math.random()` / 无参 `new Date()`(会破坏 Workflow resume)
- **prompt 内插用户字符串必须 safeInsert / safeBlock 包裹**(M5.2 转录铁律,文件 L43-L53 已定义,直接复用)
- **reviewer 红线**:永久不读历史 reviews/round_*.md;reviewer 跨轮信号只能来自 implementer 中转(impl.md reflectBlock)或本轮 issuesJson 内插
- **不破 Workflow 契约**:不动 `meta` block;不动 `agent()` / `phase()` / `parallel()` 调用形态;不引入顶层 `return`(ESM 非法)
- **不改 REVIEWER_SCHEMA**:本 plan 无 schema 字段新增/重命名/类型变更(L182-L197 维持不变)
- **不动 path2 主线代码**:本 plan 改动严格局限在 `.claude/skills/web-loop/workflow-template.js` 单文件
- **commit 信号**:每 task 一个独立 commit;commit message 中文,不加 Co-Authored-By trailer(本仓库 commit log 风格,见 `git log --oneline -5` 头几条 commit 验证)
- **不使用 --no-verify**:任何 pre-commit hook 失败,修问题不绕 hook

## 现状核实(写 plan 时已 grep + Read 确认,implementer 改前再 grep 一次锚定)

- `workflow-template.js` 已实施第一轮 P0+P1 全套(`REVIEWER_SCHEMA` 4 字段扩展 / `META_AGENT_SCHEMA` / `reflectBlock` / `stalePrimer` / 5 级指令优先级 / `decision_log.json` 读取 / `forbiddenApproaches` 内插 / `mustStaleStreak` 台账 / 强制判断题 / reviewer_stuck 信号回流)。本 plan **不需要重新实施这些**。
- 唯一遗漏的第一轮简化点 = `historyReviews` 变量仍是"上 2 轮窗口"(必读 N-1 + N-2 若存在),需简化为 N-1 only。
- 第二轮研究方案 S 是新增改动,代码里尚无 `planDedupBlock` 字样,需新增。

---

### Task 1: implementer 历史 reviews 窗口从"上 2 轮"砍到"r{N-1} only"

**Files:**
- Modify: `.claude/skills/web-loop/workflow-template.js` 中的 `historyReviews` 变量(grep 定位,约 L313 单行三元)

**Interfaces:**
- Consumes: 文件已有的 `WORKDIR`、`round` 变量(本 task 不动这两个)
- Produces: `historyReviews` 字符串值仅 Read 上 1 轮 reviews;Task 2 的 reviewer 自检与本 task 无变量依赖

**Why(给实施者读):** 传递性论据 — r{N-1} implementer 已经判断过 plan_{N-1} vs plan_{N-2} 是否重复并标进 r{N-1}/impl.md 的 `reviewer_stuck` 标,r{N} implementer 没必要重做 r{N-1} 已经做过的判断。远历史承载已经经过 r{N-1} reviewer 的响应而消化,r{N} 只对最近 1 步负责即可。背景见 memory `~/.claude/projects/-home-yu-PycharmProjects-Trade-Strategy/memory/project_web_loop_decision_layer_redesign.md` 结论 3。

- [ ] **Step 1: grep 定位 `historyReviews` 变量**

Run:
```bash
grep -n "const historyReviews" /home/yu/PycharmProjects/Trade_Strategy-bo/.claude/skills/web-loop/workflow-template.js
```
Expected: 单行命中,行号 ≈ 313。若 grep 多行命中或 0 命中,**先停下来查文件**(可能上游已变,plan 与代码漂移)。

- [ ] **Step 2: Read 该行及上下文**

用 Read 工具读 `.claude/skills/web-loop/workflow-template.js` offset=`(grep 出的行号 - 3)`, limit=`8` 看到完整 ternary。当前形态应为:

```js
const historyReviews = round >= 2 ? `【优先级 4 · 历史 reviews(参考补充,验证 P1 提炼是否准确)】\n- Read ${WORKDIR}/reviews/round_${String(round - 1).padStart(2,'0')}.md(必读)\n${round >= 3 ? `- Read ${WORKDIR}/reviews/round_${String(round - 2).padStart(2,'0')}.md(若存在)\n` : ''}用于验证本轮 nextStepPlan 与上轮的差异、确认 P1 forbiddenApproaches 提炼无漏;若发现 P1 漏掉重要信号,在 impl.md 标 "P1 漏检:..."。` : '';
```

若该字符串与现状有微小差异(空格 / 换行 / 文案微调),以**真实文件**为锚做 Edit,不要硬照 plan 字面;但**核心特征**必须命中:`round - 1` 出现 + `round >= 3` 内嵌 ternary 引用 `round - 2`。

- [ ] **Step 3: Edit 替换为 N-1 only**

用 Edit 工具替换 `historyReviews` 整行三元为下面新版(把内嵌 `round >= 3` ternary 整块连同 `round - 2` 引用一起删,只留 N-1;并补一句"远历史走 P1 forbiddenApproaches"指引,避免实施者疑惑窗口为什么砍了):

```js
const historyReviews = round >= 2 ? `【优先级 4 · 历史 reviews(参考补充 · 仅最近 1 轮)】\n- Read ${WORKDIR}/reviews/round_${String(round - 1).padStart(2,'0')}.md(必读)\n用于验证本轮 nextStepPlan 与上轮的差异、确认 P1 forbiddenApproaches 提炼无漏;若发现 P1 漏掉重要信号,在 impl.md 标 "P1 漏检:..."。\n⚠ 仅读上 1 轮 reviews —— 远历史走 P1 forbiddenApproaches(优先级 3)累积清单 + 上轮 impl.md 反根因段(优先级 5)。传递性论据:r${round - 1} implementer 已就 plan_${round - 1} vs plan_${round - 2 >= 1 ? round - 2 : '?'} 重复性做过判断并标进 r${round - 1}/impl.md reviewer_stuck,无需 r${round} 重做。` : '';
```

**关键变化点(供 implementer 自检):**
- 删除:`${round >= 3 ? \`- Read ${WORKDIR}/reviews/round_${String(round - 2).padStart(2,'0')}.md(若存在)\n\` : ''}`
- 新增:`- Read ${WORKDIR}/reviews/round_${String(round - 1).padStart(2,'0')}.md(必读)` 后面、`用于验证本轮...` 之前**保留**;在结尾追加 `⚠ 仅读上 1 轮 reviews ...` 注释段

- [ ] **Step 4: node --check 语法验证**

Run:
```bash
node --check /home/yu/PycharmProjects/Trade_Strategy-bo/.claude/skills/web-loop/workflow-template.js
```
Expected: 退出码 0(无输出 = 语法正确)。若报 SyntaxError,看错误行号 / 字符列,常见原因:
- 嵌套模板字符串内有未转义的反引号 →  转义为 `` \` ``
- 三元嵌套层级错位 → Read 上下文,把 ternary 配对清楚
- 结尾分号缺失 → 补 `;`

**禁用 sed 修这种 bug**——直接用 Edit 在出错点改。

- [ ] **Step 5: grep 验证无残留 N-2 引用**

Run:
```bash
grep -n "round - 2\|round >= 3" /home/yu/PycharmProjects/Trade_Strategy-bo/.claude/skills/web-loop/workflow-template.js | grep -v "round - 2 >= 1"
```
Expected: **0 命中**(除了新版本中 `round - 2 >= 1 ? round - 2 : '?'` 这种纯文案插值是允许的,grep 用 `grep -v` 已排除;若文件其他位置原本就有 `round - 2`/`round >= 3` 引用且与本 task 无关,记下行号后用 Read 工具确认是否属于其他功能再决定是否影响——本 task 不动其他位置)。

- [ ] **Step 6: commit**

Run:
```bash
cd /home/yu/PycharmProjects/Trade_Strategy-bo
git add .claude/skills/web-loop/workflow-template.js
git commit -m "web-loop/skill: implementer historyReviews 窗口砍到 N-1 only(传递性)"
```

**注:不加 Co-Authored-By trailer**——按本仓库 commit log 风格(参考 `git log --oneline -5`,前 5 条均无 trailer)。

---

### Task 2: reviewerPrompt 加 `planDedupBlock` 段(方案 S 增强版)

**Files:**
- Modify: `.claude/skills/web-loop/workflow-template.js` 中 `reviewerPrompt` 函数(grep 定位,约 L113-L170);需在两处改动:
  - **(2a)** 函数体内,`reflectBlock` 变量定义之后(约 L120 之后)新增 `planDedupBlock` 变量定义
  - **(2b)** 函数 return 模板字符串中,把 `planDedupBlock` 插入到 `${reflectBlock}` 之后(约 L128)

**Interfaces:**
- Consumes: `reviewerPrompt` 已有形参 `lens`、`round`(本 task 用这两个判触发条件)
- Produces: 当 `round >= 2 && lens === "code"` 时,reviewer 收到的 prompt 多 ~8-10 行 plan 主线自查指引;其他 lens / round=1 时为空字符串(无侵入)

**Why(给实施者读):** 第二轮 agent team 研究方案 S — reviewer 在出 `nextStepPlan` 前做一次自检,对照 `issuesJson` 中**早已可见**的历史 `nextStepPlan` 字段(skeptic §1.2 致命洞察:`issuesJson` 全内插,每条 must 都含 `nextStepPlan` 字段跨轮持久),若主线相同必须举具体失败证据,否则换主线。临界规则在双信号(reviewer_stuck=true + 自检判主线同)时强制换主线;真二选一子子集(reviewer_stuck=false + 反根因为空 + 主线同)默认换主线。**不引入** schema 字段 / 标签 enum / repeatCount / 新 P1 触发判据 / jq 派生视图。详 research final_report(若文件存在 `docs/research/2026-06-21_web-loop-plan-dedup-redesign/final_report.md`;若文件缺失,本 task 的 prompt 文本 §Step 3 即权威 spec)。

- [ ] **Step 1: grep 定位 reviewerPrompt 函数边界 + reflectBlock 变量**

Run:
```bash
grep -nE "^function reviewerPrompt|const stalePrimer|const reflectBlock|const refsReadInstr|^}" /home/yu/PycharmProjects/Trade_Strategy-bo/.claude/skills/web-loop/workflow-template.js | head -20
```
Expected: 看到大致以下顺序:
```
113:function reviewerPrompt(...)
119:  const stalePrimer = ...
120:  const reflectBlock = round >= 2 ? `...` : '';
121:  const refsReadInstr={...
170:}
```

记下 `reflectBlock` 末尾行号(约 L120 整行)+ `refsReadInstr={` 起始行号(约 L121)。`planDedupBlock` 定义将插在这两者之间。

- [ ] **Step 2: Read 函数 return 模板看清当前 `${reflectBlock}` 嵌入位置**

用 Read 工具读 `.claude/skills/web-loop/workflow-template.js` offset=125, limit=10,确认 return 模板字符串中 `${reflectBlock}` 出现在第 128 行附近、单独一行嵌入(形如 `${stalePrimer}${reflectBlock}\n`)。记下精确字符串作为 Step 5 Edit 的 old_string 锚定。

- [ ] **Step 3: Edit 新增 `planDedupBlock` 变量(2a)**

用 Edit 工具在 `const reflectBlock = ... : '';` 那一行之后、`const refsReadInstr={` 之前插入下面 const(整段一次性插入,**不分多次插入**):

old_string(选 `reflectBlock = ...` 那行末尾的换行 + 下一行 `const refsReadInstr={` 一句,确保唯一性):

按 Read 出来的精确字符串组装。具体:取 reflectBlock 那行**完整结尾**(包括 `` : ''; ``)+ 紧接的 `\n  const refsReadInstr={` 一段作为 old_string;new_string 在中间插入新 const。

new_string 整段(中文 prompt 文本,逐字 — 不裁不缩):

```js
  const planDedupBlock = (round >= 2 && lens === "code") ? `\n【plan 主线自查(code lens · round≥2,2026-06-21 方案 S)】出 nextStepPlan 前必做一次自检:\n你能在本 prompt 上方 issuesJson 看到本轮每条 must 已有的"历史 nextStepPlan"字段(若有)——这是上轮(及更早)reviewer 给的 plan 主线、跨轮持久。\n对照你即将写的 plan 主线(affectedFiles 集合 + 修法核心一句话),与历史 nextStepPlan 主线对比:\n  · 若你判断本轮 plan 与历史本质相同 → 在新 nextStepPlan 顶部加一行:\n      "[同主线 r<N>] 原因:<上轮 implementer 已实际试过且失败的具体证据>"\n    具体失败证据 = 引用上轮 impl.md 反根因段 / git diff 实际改动行 / console error / 截图特征,\n    可被 grep 定位;不接受"再试一次" / "本轮重新尝试" 类空洞理由。\n    若无法举出具体失败证据 → 直接换主线;不写"[同主线]"注释。\n\n【临界规则 · 强制换主线】若上轮 impl.md 首段 reviewer_stuck=true 且本轮你自检判定主线相同\n  → 强制换主线(此时不允许写"[同主线]"注释继续;双信号都指向"同主线被试且不行"是最高确信场景);\n  若你判断换不了主线(找不到其他根因) → 在 escapeRequest 标 reviewer_disagreement 退出。\n\n【真二选一倾向 · 默认查重收紧】若上轮 impl.md reviewer_stuck=false 且反根因段为空 且本轮你自检判定主线相同\n  → 此时缺乏跨角色信号区分 case(a)plan 错 / case(b)impl 错 / case(f)刷新假阴\n  → 默认换主线(救 case(a)/(g) 优先;case(b) 走 status quo 的 implementer 反根因 + mustStaleStreak 兜底)\n  → 若你坚持重出,必须在原因里引用具体失败证据(同上规则);无证据即换主线。\n\n注:本段是纯行为指引,不引入新 schema 字段;自检结果落入 nextStepPlan 字符串字面即可(可被后续 grep "\\[同主线 r" 提取做事后监控)。` : '';
```

**关键自检要点:**
- 触发条件 `round >= 2 && lens === "code"` 与 (2a) `reflectBlock` 的 `round >= 2` 仅在 lens 维度收紧——非 code lens 时本块为空字符串(`ux`/`func` 的 plan 重复由现有 `mustStaleStreak` 机制覆盖,不需本块)
- 全段中文 prompt **不引用任何用户输入字符串**(无 `${GOAL}`/`${ISSUES}` 等),因此**不需要** `safeInsert` 包裹(`safeInsert` 仅用于内插用户提供的不可信字符串,详 L43-L48 实现);静态模板字面字符直接进 prompt 即可

- [ ] **Step 4: node --check 语法验证(早查,防嵌套模板反引号配对错)**

Run:
```bash
node --check /home/yu/PycharmProjects/Trade_Strategy-bo/.claude/skills/web-loop/workflow-template.js
```
Expected: 退出码 0。常见错:
- 模板字符串内单引号配对、反引号需转义 `` \` ``(本段无反引号字面)
- ternary `? \`...\` : ''` 闭合 → 用 Read 比对新插入段与 reflectBlock 是否结构对齐

- [ ] **Step 5: Edit 把 `planDedupBlock` 插入 return 模板字符串(2b)**

用 Edit 工具,把 return 模板字符串里 `${stalePrimer}${reflectBlock}` 替换为 `${stalePrimer}${reflectBlock}${planDedupBlock}`。

具体 Edit:
- old_string: 取 Read Step 2 看到的精确字符串(应类似 `${stalePrimer}${reflectBlock}\n`)
- new_string: 在 `${reflectBlock}` 后加 `${planDedupBlock}` 后再换行(形如 `${stalePrimer}${reflectBlock}${planDedupBlock}\n`)

若 old_string 唯一性不足,把上下文扩到包含前一行/后一行确保唯一。

- [ ] **Step 6: 二次 node --check 验证**

Run:
```bash
node --check /home/yu/PycharmProjects/Trade_Strategy-bo/.claude/skills/web-loop/workflow-template.js
```
Expected: 退出码 0。

- [ ] **Step 7: grep 验证新段已落地 + 触发条件 + 模板插入位置**

Run:
```bash
grep -nE "planDedupBlock|plan 主线自查|临界规则 · 强制换主线|真二选一倾向" /home/yu/PycharmProjects/Trade_Strategy-bo/.claude/skills/web-loop/workflow-template.js
```
Expected: 至少 5 行命中:
- 1 行 `const planDedupBlock = ...` 定义
- 1 行 `${planDedupBlock}` 在 return 模板内
- 3 行 prompt 内文(`plan 主线自查` / `临界规则 · 强制换主线` / `真二选一倾向`)

若任一缺失:Read 文件相应段落,检查 Edit 是否漏了。

- [ ] **Step 8: 手动产物自检(可选但强烈推荐)**

跑一小段 node 内联脚本,模拟调用 `reviewerPrompt` 验证产物字符串包含 planDedupBlock 内容,仅对 `round=2, lens="code"` 触发、对 `round=2, lens="ux"` 不触发、对 `round=1, lens="code"` 不触发。

Run:
```bash
cd /home/yu/PycharmProjects/Trade_Strategy-bo
node --input-type=module -e "
import { readFileSync } from 'fs';
const src = readFileSync('.claude/skills/web-loop/workflow-template.js','utf8');
// 用 regex 提取 reviewerPrompt 函数体(粗略;只为本自检,不做正式解析)
const fnMatch = src.match(/function reviewerPrompt[\s\S]*?\n\}/);
if (!fnMatch) { console.error('FAIL: 未匹配 reviewerPrompt 函数'); process.exit(1); }
const fnSrc = fnMatch[0];
const has = (label, cond) => console.log((cond?'PASS':'FAIL')+' · '+label);
has('包含 planDedupBlock 定义', /const planDedupBlock\s*=/.test(fnSrc));
has('触发条件正确(round >= 2 && lens === \"code\")', /round >= 2 && lens === \"code\"/.test(fnSrc));
has('return 模板内嵌入 planDedupBlock', /\\\$\\{planDedupBlock\\}/.test(fnSrc));
has('包含临界规则文案', /临界规则 · 强制换主线/.test(fnSrc));
has('包含真二选一倾向文案', /真二选一倾向 · 默认查重收紧/.test(fnSrc));
"
```
Expected:5 行全 PASS。

**注**:这只是结构自检,**不**模拟跑真 workflow(workflow 端到端测在本 plan 范围外;后续靠真实 web-loop run 验证 reviewer 是否吐 `[同主线 r<N>]` 注释)。

- [ ] **Step 9: commit**

Run:
```bash
cd /home/yu/PycharmProjects/Trade_Strategy-bo
git add .claude/skills/web-loop/workflow-template.js
git commit -m "web-loop/skill: reviewerPrompt 加 plan 主线自查 + 临界规则(方案 S)"
```

---

## 完成后:整体回归验证(非 task 内,subagent-driven 最终 holistic 阶段做)

- [ ] **R1: 整文件 node --check 再跑一次**

```bash
node --check /home/yu/PycharmProjects/Trade_Strategy-bo/.claude/skills/web-loop/workflow-template.js
```
Expected: 0。

- [ ] **R2: 两 commit 都在 + 工作树干净**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy-bo
git log --oneline -3
git status
```
Expected: 最近 2 commit 是本 plan 产出(`historyReviews 窗口...` + `plan 主线自查...`),工作树 clean。

- [ ] **R3: grep 跨 task 关键不变量一次确认**

```bash
# (A) historyReviews 已 N-1 only
grep -A2 "const historyReviews" /home/yu/PycharmProjects/Trade_Strategy-bo/.claude/skills/web-loop/workflow-template.js | head -4
# 应只出现 round - 1,不出现 round - 2(除文案插值 round - 2 >= 1 ? round - 2 : '?')
# (B) planDedupBlock 已添 + 嵌入 return
grep -cE "planDedupBlock" /home/yu/PycharmProjects/Trade_Strategy-bo/.claude/skills/web-loop/workflow-template.js
# 应输出 2 或更多(定义 1 + 引用 ≥1)
```

- [ ] **R4: reviewer 红线 + 现有契约未被破坏**

```bash
# reviewer 永久零浏览器 / 永久不读历史 reviews/round_*.md(红线不破)
grep -nE "永久零浏览器|reviews/round_" /home/yu/PycharmProjects/Trade_Strategy-bo/.claude/skills/web-loop/workflow-template.js | head -10
```
**人工检查**:确认所有 `reviews/round_<N>.md` 的 Read 引用都在 **implementer** prompt 段(`historyReviews` 变量),**不在** `reviewerPrompt` 函数内(reviewerPrompt 内只允许通过 `issuesJson` 看 plan 历史字段,这是 issuesJson 内插不是 Read reviews/*.md;两者本质不同)。

如果 R4 发现 `reviewerPrompt` 函数内出现了 `reviews/round_` 字符串,**回滚**(本 plan 误破红线了)。本 plan 的 planDedupBlock 文案应只引用 `issuesJson` 字段,不引用 reviews 文件。

---

## Self-Review(写 plan 时已自查)

**1. Spec 覆盖**:
- (A) implementer N-1 only 窗口 → Task 1 全覆盖
- (B) reviewer plan 主线自查 + 临界规则 + 真二选一默认收紧 → Task 2 §Step 3 prompt 文本三段齐
- 不应该做的事(无 schema 改 / 无标签 enum / 无 jq 视图 / 无 P1 新触发 / 不破 reviewer 红线)→ 全在 Global Constraints + R4 校验

**2. Placeholder 扫描**:本 plan 所有 Step 都给了具体 grep / Edit / node 命令 + 完整 prompt 文本块;Task 2 §Step 3 的 `planDedupBlock` 整段是 verbatim 落地代码,无 TBD / 见上 / 类似 X 等空洞引用。

**3. 类型 / 锚点一致性**:
- `reviewerPrompt` 函数签名沿用现有(L113);无新形参
- `historyReviews` 变量名不变;只改三元右值
- `planDedupBlock` 是新增 const,名字唯一(grep 验证)
- 两 task 都用 `node --check` 做语法 gate;两 task 改动锚点不重叠(historyReviews 在 implementer 段、planDedupBlock 在 reviewerPrompt 函数体),无 cross-task 冲突

**4. 自包含性**:
- 所有源材料(memory 结论 3 / agent team 方案 S 文本)都内联到 plan 各 Task 的 prompt 文本或 Why 段
- 不依赖 `docs/research/2026-06-21_web-loop-plan-dedup-redesign/final_report.md` 文件(若该文件缺失,Task 2 §Step 3 的 `planDedupBlock` verbatim 文本即权威 spec)
- 不依赖第一轮 final_report 文件(workflow-template.js 已实施 P0+P1 全套,plan 不需要重读 spec)

---

## Execution Handoff(供新 session 粘贴)

新 session 启动后,直接粘贴以下命令:

```
/superpowers:subagent-driven-development docs/superpowers/plans/2026-06-21-web-loop-impl-window-n1-and-plan-dedup.md
```

或如果偏好 inline 执行:

```
/superpowers:executing-plans docs/superpowers/plans/2026-06-21-web-loop-impl-window-n1-and-plan-dedup.md
```

**Subagent-driven(推荐)**:每 task fresh subagent + 双审(spec + quality);本 plan 仅 2 task,加每 task 双审 + 最终 holistic = 共约 6-7 个 subagent dispatch,代价低。

**Inline**:在当前 session 用 executing-plans 跑;少了 subagent 开销但同时少了 task 级 context 隔离;两 task 极短,inline 也可行。
