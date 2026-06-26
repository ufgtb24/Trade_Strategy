# web-loop 决策层重设计 · final report

> 团队组成:lead(opus,coordinator)+ architect(opus)+ diagnostician(opus)+ redesigner(opus)+ skeptic(opus)。3 轮辩论(R0 初始定位 + R1/R2 cross-pollination + 直接收敛)后,4 名 teammate 立场强烈对齐。
>
> 本报告产物面向用户(可直接执行决策),引用各 teammate 中间位置文档作为细节支撑。
>
> 中间文档(可选阅读):
> - [`architect-position.md`](./architect-position.md) — opus 当前分工辩护 + 翻转记录
> - [`diagnostician-rootcauses.md`](./diagnostician-rootcauses.md) — "小问题改不好"根因诊断
> - [`redesigner-proposal.md`](./redesigner-proposal.md) — decision agent 方案 v1 → v2 缩窄
> - [`skeptic-counter.md`](./skeptic-counter.md) — 对立结论 + 三条机检判据 + PAUSED-await-injection runtime 诉求

---

## 0. TL;DR(用户接下来该做的事)

**结论一句话**:你直觉是对的——决策层确实缺失,但**不需要新加 opus agent**;只需把 reviewer 已闲置的诊断 + 策略能力**通过 schema 字段释放出来**(包含策略级 plan),加上几条零成本机检判据;同时 **implementer 全程升 opus** 解执行端 ceiling。新增 decision agent 在 80% 痛点场景下是过设计。

**优先级落地路径**(立即可做 vs 实测后可叠加 vs 长期讨论):

| 优先级 | 内容 | 改动 | 谁解了你的什么痛点 |
|---|---|---|---|
| **P0 必做** | 扩 reviewer schema(rootCauseHypothesis / affectedFiles / suggestedFix / **nextStepPlan 策略级 plan**)+ implementer 透传 + 跨轮 read reviews + 多通道机检触发判据 + paused.md/human-hint 续修协议(workdir 文件通道,零 runtime 改动)+ **implementer 全程升 opus**(用户拍板接受 token 成本) | 0 新 agent;改 schema + mergeIssues + prompt + 触发判据 + skill 入口 resume 协议 + implementer model 字段改 opus | 95% 痛点("opus 闲置不诊断" + "小 bug 反复跑还不停" + "重启 = 重做 r1 已 verified 丢失" + ② **多 must 互冲的执行端 ceiling**) |
| **P1 可选叠加** | stall 触发独立 meta-agent(缩窄到 3 字段)| +1 opus / stall 事件,跨轮综合 + 禁止重试清单 + 元判断 | 跨轮元层走偏(P0 后剩余 ~5% 真难 case) |
| **P2 长期讨论** | Workflow runtime 级别真打断(`workflow.pause()` 原语,比 P0 文件通道更优雅但需 runtime 改);项目宪法明列 "web-loop implementer = opus" 例外条款 | runtime 改动 + 跨 skill 宪法修订 | runtime 级真打断 + 制度化 P0 已采用的 opus implementer |

**不要做的**:在当前 workflow 框架内单独加一个完整的 opus decision agent(redesigner v1)——它的核心价值 80% 被 P0 零成本覆盖,且引入"二审与 reviewer 双源真理"新故障源。

---

## 1. 起因 · 用户的痛点是真的

用户原话(摘):

> 我在使用 web-loop 工作时,**经常遇到一个小小的问题迭代很多轮也改不好**……playwright 中一看便知道哪里有问题,**最重要的环节是分析问题怎么修改,但是这个恰恰没人做**……web-loop 的 workflow 中的那些 opus agent 到底在干嘛?

团队 4 人一致认为这个痛点真实且 web-loop 当前架构没有充分回应——这是本次研究的合法性基础,**不在"用户感受 vs 架构客观"这层撕扯**。但**痛点的真根因不只是一个**(diagnostician 拆三档,见 §3.1)。

---

## 2. 直接回答用户原始 4 问

### 2.1 "opus 在干嘛?"

当前 4 个 opus 调用 / 轮(3 reviewer + 1 finalize)做的是 **multi-channel evidence synthesis + 跨轮台账推理 + 反锚定**(architect R0):
- 把多模态 PNG + console + git diff + stateDumps probe 4 类证据**绑到 GOAL 子项的覆盖 / 违反**(`verified.evidence` + `matchesSubgoal`)
- 用 `matchesIssueId` 跨轮锚定旧 must、触发回归检测
- 反锚定 `stillPresent` 用本轮证据,禁沿用旧表述
- `goalEcho` 强制注意力归位 GOAL(防 reviewer 漂移到只盯 must)

**这些是有判断的活,不是评分员**(架构上 reviewer 不可降 sonnet)。但 diagnostician 揭示了真问题——

### 2.2 "为什么没人做根因分析?"

**真因:reviewer 有能力但 schema 把出口锁死了**。当前 `REVIEWER_SCHEMA.issues[i]` 只有 `title/severity/detail/evidence` 字段,**没有 rootCauseHypothesis / affectedFiles / chainOfDriftFromPrevRound 字段**。code lens 已经在读 git diff、根因在它脑里,但**没有字段让它说**。

architect 翻转判定:这比"reviewer prompt 弱"还狠——**是 schema 设计 bug**。reviewer 看证据时根因就在它脑里,只是没让它输出。

### 2.3 "为什么用 opus(既然没人做最重要的根因分析)?"

opus 算力**确实被低用**(架构师诚实账):
- finalize 是 close call,偏 sonnet(机械汇总居多,真"判断"成分薄)
- code lens 读 diff 但 schema 没要根因 → opus 算力被锁在 evidence 描述层
- 部分 setup agent(pw-selfcheck / preflight)没显式 model 字段,在 opus session 下继承 opus = 配置遗漏

**修法不是砍 reviewer 改 sonnet,是让 reviewer 真用满 opus 算力**(写根因 + 影响文件 + 跨轮 drift chain)。

### 2.4 "节约 tokens?"

| 方案 | opus 调用 / 轮 | net token | 来源 |
|---|---|---|---|
| 现状 | 4 (reviewer×3 + finalize) + sonnet impl | 基线 | — |
| 扩 schema + sonnet impl | 4(reviewer 多输出几字段) | **基本持平**(reviewer prompt 略长,但少跑轮数远 > 多写字段) | diagnostician |
| **P0 落地版** = 扩 schema + **opus impl(用户拍板)** | 4 reviewer + opus impl | **每轮 input token 量级跳跃**;但 opus impl 命中率高 → 总轮数从 5-6 降到 3-4 → **总 token 可能净降** | 用户决策 |
| 加 decision agent(P1) | 5+(decision 在 stall 时触发) | **净增 ~10-15K opus / 触发** | redesigner v1 |

**用户原话"节约 tokens"在 P0 落地版下需理解为"单 run 总 token"而非"单次 spawn token"**——opus impl 的"少跑 2 轮"红利通常足以抵消单次成本上升,但实测前不保证。详 §5.1 决策记录。

---

## 3. 主推 P0(必做):扩 reviewer schema + 多通道机检触发 + paused 提示

> **0 新 agent。** 改 schema + mergeIssues + 几段 prompt + 控制流。是 diagnostician 主菜,4 人一致认同为投入产出最高的修法。

### 3.1 用户痛点的真根因(diagnostician 三档)

把"小问题改不好"拆成可机检的三档,**不要无脑归因为"缺决策层"**:

| 档 | 表现 | 范围内/外 | 解法 |
|---|---|---|---|
| ① **must 描述不准** | reviewer 写"K 线被压"→ implementer 想成"K 线高度太小"实际是"侧栏宽度抢空间" | 范围内 · 低效 | §3.2 扩 schema(根因 + nextStepPlan)|
| ② **多 must 互冲** | 改 G1 破 G3,改 G3 破 G2,需要联合优化 | 范围内 · 执行端 ceiling | §3.2 nextStepPlan 给策略 + **§3.5 implementer 全程升 opus**(用户拍板) |
| ③ **rubric/GOAL 错位** | reviewer 客观判 must,但 GOAL 子项本身和用户真意有差距 | 范围外 · 设计错位 | §3.4 机检判据 + §3.7 human-hint 续修协议(用户给一句话,workflow 续跑同 run、不重做 r1) |

> 注:diagnostician 文档(`diagnostician-rootcauses.md`)对 #C(`mustStaleStreak` 字符串去重脆)标"中等贡献度"——直接解释"很多轮"为什么不被 STALE 兜住,虽不是 #A/#B 的直接体感原因,但修法独立且必修(P0 §3.3 并列)。

P0 主推方案完整覆盖 ①②③:① 靠扩 schema 让 reviewer 给根因 + 策略级 plan;② 靠 **implementer 全程升 opus**(用户决定接受 token 成本,理由见 §5.1)在多约束联合优化上获得 opus 强项;③ 靠机检退人 + **human-hint 续修协议**(用户写 `human-hint-r{N}.md`,workflow resume 同 run、保留已 verified 子项不重做)。**这是 skeptic R3 提出的"零 runtime 改动"轻量方案,沿用现有 resume 机制**(详 §3.7)。

### 3.2 扩 reviewer schema(diagnostician 主推)

`REVIEWER_SCHEMA.issues[i]` 增 4 字段:

```js
issues: [{
  // 现有
  title, severity, evidence, matchesIssueId, matchesSubgoal, unverifiable, detail,

  // ★新增(M5.3,本次设计):
  rootCauseHypothesis: string,         // ≤2句机制假设(code lens 必填,其他 lens 可选)
  affectedFiles: ["path:line", ...],   // diff 锚点(code lens 必填,其他 lens 可选)
  suggestedFix: string | null,         // 可选,implementer 可推翻;明标"hypothesis 不是 prescription"
  nextStepPlan: string                 // ★策略级 plan,3-8 行自然语言(code lens 必填,其他 lens 可选)
}]
```

**`nextStepPlan` 字段设计**(本研究关键升级,用户反问触发):

reviewer 是 opus、已经看着证据,加一段"下轮 implementer 该怎么干"几乎零额外成本。这正是用户原话"类似 superpowers 写 spec 和 writing-plan"的字面落地——把 opus 的策略思考能力暴露给 implementer。

**内容粒度**:**策略级**(不到代码级)。模板:

```
1. Read affectedFiles 列出的代码段,确认现状是 X
2. 修法主线:把 Y 改为 Z(策略,非具体行号 / 函数体)
3. 风险:可能破坏已 verified 子项 G2,改完用 probe 检查 store.foo 仍为 true
4. 调试方法:若改完仍触发同样 must,在 console 加 log 检查 W 的值
5. 不要再试:上轮的"改 CSS 高度"路径——根因不在 CSS
```

**禁止给代码级 prescription**(具体 `path:line` 的 `old_string`/`new_string` patch / 函数体 snippet)。理由:
- implementer(即便升 opus 后)在多约束推理场景下仍可能"死板照搬"——reviewer 写的 patch 可能基于上轮的过时代码,本轮已经动过
- 长代码片段在 prompt 间转译时容易产生"建议代码 vs 实际 Edit 字符串"的混淆,引发 byte-mismatch
- 策略级 plan **强制 implementer Read 实际代码 + 自己理解 + 自己写 Edit 调用**,有自纠错机会

**关键设计**:
- **只 code lens 必填 4 字段**——它本就是唯一读 diff 的 lens,根因 + 策略是 home turf;ux/func 出根因是越权,且会触发"3 路 reviewer 建议冲突 → 谁来 merge"的伪问题(reviewer parallel 红线 vs. 独立 decision agent 的取舍依据 see §4.1)
- **suggestedFix vs nextStepPlan 区别**:suggestedFix = 单行"换什么"(可选,implementer 可推翻);nextStepPlan = 多行"该如何攻"(策略 + 风险 + 验证方法 + 禁止重试)。两者层级不同,implementer 优先看 nextStepPlan
- **绕开 `principles.md` 总则第 5 条"reviewer 不设计方案"的红线副作用**:本字段输出的是"诊断 + 调查方向 + 验证方法",非"建议替代方案的具体实施";reviewer 看着证据时的策略思考本就是它的本职合理延伸
- **r1 也立刻生效**——reviewer 第 1 轮就在出根因 + plan,implementer 第 1 轮就受益(不像独立 decision agent 要等 staleStreak≥1 才触发)

**implementer prompt 改**:透传完整 must 对象(含新 4 字段)+ 一条强制指令:

```
⚠ 改前必做:
1. Read affectedFiles 列出的具体行号(确认 reviewer 描述的现状是否与本轮真实代码一致)
2. Read 上一轮 reviews/round_{N-1}.md 顶部 + impl.md 首段(看上轮试了什么、为什么没成)
3. 一句话回讲"我理解根因是 X,我要按 nextStepPlan 第 N 步改的是 Y"
若你认为根因或 plan 猜错了,在本轮 impl.md 首段记下"反根因:实际机制是 Z / 偏离 plan 因为 W",仍可修但需说明理由。
```

### 3.3 mustStaleStreak 语义聚类(diagnostician #C)

**当前 bug**:`mergeIssues` 用 `x.title === it.title` 纯字符串去重(`workflow-template.js:106`)。reviewer 这轮写 "K 线 grid 被压缩到视口 30%",下轮写 "K 线垂直高度不足导致蜡烛拥挤"——**同一个 bug、新 issue id 入台账、mustStaleStreak 重置**,无限迭代。

**修法两选一**:
- **轻量**(推荐):reviewer prompt 强制要求"对所有 open must 必须先用 `matchesIssueId` 引用现有 id,只有判定为真新增 bug 才新立 id"。从 prompt 层堵,不改 mergeIssues 算法。
- **重量**(若轻量实测不够):在 mergeIssues 加语义聚类——比较新 must 与现有 open must 的 title + evidence 余弦相似度 >0.7 视为 dup,或调一次轻量 opus 二次判定(零新 agent,折进 persist 阶段)。

### 3.4 多通道机检触发判据(skeptic 主推)

**当前 STALE_ROUNDS=2 + 字符串去重**的退出条件太脆。skeptic 给出 3 条基于现有 issues 台账数据的硬判据,**零新 agent 字段、零新数据采集**:

```js
// 判据 1:同一 must 跨轮"修复→回归"震荡 ≥ 2 次
const oscillating = issues.some(i =>
  i.regressionCount >= 2 && i.status === "open" || i.status === "regressed"
);
// 含义:implementer 在两个修法之间反复横跳(②多 must 互冲的硬证据)

// 判据 2:同 lens 新 must 增速 ≥ 老 must 修复速 持续 2 轮
const treadmill = REVIEW_LENSES.some(lens => {
  const lastTwo = history.slice(-2);
  if (lastTwo.length < 2) return false;
  const newCnt = lastTwo.reduce((s, h) => s + (h.newMust || 0), 0);
  const fixedCnt = issues.filter(i => i.lens === lens && i.status === "fixed"
    && i.lastSeenRound >= round - 1).length;
  return newCnt >= fixedCnt && newCnt > 0;
});
// 含义:每修一个旧 must 引入一个新 must,但 mustStaleStreak 不计(因为 id 不同)

// 判据 3:同子项 unverifiable ≥ 2 轮且 requiredStates 重叠
const missingStates = (GOAL_SUBGOALS||[]).some(g => {
  const recent = issues.filter(i => i.matchesSubgoal === g.id && i.unverifiable);
  if (recent.length < 2) return false;
  const states = recent.flatMap(i => i.requiredStates || []);
  return new Set(states).size < states.length;  // 至少一个 state 在多 issue 重复
});
// 含义:capture STATES 漏了一个必要状态,workflow 内无法补、必须人补 STATES
```

**任一触发 → 写 paused.md + workflow break + SUMMARY 顶部红字提示**:
```markdown
## ⚠ PAUSED · 触发判据 <N>:<short>
本 run 已自动停止,可能原因:<判据描述>。建议:<改 args 提示>。
完整诊断见 paused.md。
```

**触发后不是"硬退出"**(那是当前 max-rounds 的副作用)——保留 issues.json / verified.json / refs/,SUMMARY 详细标 paused 原因 + 建议用户怎么改 args。用户读完决定:
- 改 args 起新 run(改 rubric / 加 STATES / 加 refImages)
- 弃 workflow,转主会话手工修

**真打断**(workflow 暂停 → 用户给一句话 → workflow 续跑同 run)需要 Workflow runtime 改动,见 §5.2,本研究列为 P2 长期建议。

### 3.5 implementer 升级:跨轮 read 历史 + 全程升 opus(用户决策)

**两个独立但同时落地的升级**:

#### 3.5a · 跨轮 read 历史 reviews(architect 提)

implementer fresh subagent per round,**当前只读 issuesJson 摘要**(`workflow-template.js:262`)。让它在 prompt 顶部 Read `<workdir>/reviews/round_<N-1>.md` 和 `round_<N-2>.md`(若存在),以及 `<workdir>/rounds/<N-1>/impl.md`(上轮自己的"反根因"段),拿到完整跨轮上下文。

**这一改动单独就回答了 redesigner v1 的"跨轮综合"诉求 80%**——implementer 自己读历史,不需要 decision agent 中转。结合 §3.2 reviewer 出根因 + nextStepPlan,implementer 就有完整跨轮上下文。

##### 3.5a-i · prompt 优先级模板(tom 第一性原理裁定补丁)

tom 在裁定 nextStepPlan 跨轮隔离设计时,提出 implementer prompt 必须显式标定优先级,否则 opus implementer 会把多个 plan 当等权信号。落地模板:

```
【本轮(r{N})reviewer 给出的 must 与 nextStepPlan(权威 · 必从)】
{r{N} must JSON,含 nextStepPlan_r{N}}

【参考历史(只用于"上轮试过什么 / 是否在重复"判断 · 非指令)】
- reviews/round_{N-1}.md 摘要(reviewer 上轮 plan_r{N-1} + 你 r{N-1} 的 impl.md "反根因"段)
- reviews/round_{N-2}.md 摘要(若存在)

【(P1 若启用)decision_log.json forbiddenApproaches】
[{issueId, triedMethod, why_failed_evidence}, ...]
```

**5 级指令优先级**(implementer 必从):
1. 用户人工指令(`<workdir>/human-hint-r{N}.md`,若存在,§3.7)
2. 本轮 reviewer 给的当前 must 对象内 `nextStepPlan_r{N}` + `rootCauseHypothesis` + `affectedFiles`
3. (P1 若启用)`decision_log.json` 里的 `forbiddenApproaches`——结构化禁忌清单,直接遵守
4. 历史 `reviews/round_<N-1>.md` / `round_<N-2>.md`——补充细节,验证 P1 提炼是否准确;若发现 P1 漏掉重要信号,在 impl.md 标"P1 漏检:..."
5. 历史 `rounds/<N-1>/impl.md` "反根因"段——上轮自己的判断

##### 3.5a-ii · 强制判断题 + reviewer_stuck 信号回流(tom 关键补丁)

implementer prompt 末尾**强制要求 impl.md 首段先回答一个判断题**,在执行 r{N} plan 之前:

```
【你的任务】
1. 按 r{N} nextStepPlan 执行,不要按 r{N-1}/r{N-2} plan 执行。
2. 但在 impl.md 首段,先回答一个判断题:
   "r{N} plan 与 r{N-1} plan 是否本质相同(同 affectedFiles + 同修法主线)?"
   - 若不同 → 正常按 r{N} plan 推进,impl.md 标 reviewer_stuck=false。
   - 若相同 → 说明 r{N-1} 没解决问题,reviewer 在原地踏步。回讲"上轮 plan 试过 X,失败于 Y;本轮我会改在 Z 处"(可微调主线),impl.md 标 reviewer_stuck=true。
3. impl.md 首段固定结构:
   ```
   - reviewer_stuck: <true|false>
   - plan 重复分析: <一句话>
   - 本轮我会按 plan 第 N 步改 <文件:行号>(若 reviewer_stuck=true,本步可偏离 plan,给理由)
   - 反根因(若有): <若发现 reviewer 的根因假设与实际代码不符,在此记 "实际机制是 Z">
   ```
```

**reviewer_stuck 信号回流到下轮 reviewer**(§3.2 reviewer prompt 同步补一段):

```
【跨轮反思(reviewer 端)】
本轮开始前,Read 上轮 rounds/<N-1>/impl.md 首段:
- 若 reviewer_stuck=true → 说明上轮 reviewer(即上一个 fresh 你)的 nextStepPlan 与 plan_r{N-2} 本质相同、implementer 试过没解决。
- 本轮 nextStepPlan 必须给出与上轮**不同主线**(换 affectedFiles 或换修法思路),不得简单换措辞重写同一 plan。
- 若你判断 reviewer_stuck=true 是 implementer 误判(plan 应该有效但 implementer 没正确执行),在 nextStepPlan 顶部标 "stuck 异议:implementer 误判,本轮重申同主线但详细分解步骤"。
```

**关键设计**:本补丁**不破 reviewer 红线**——reviewer 红线是"reviewer 不读自己的历史输出"(防被旧表述污染),但**读 implementer 关于 reviewer 是否走偏的元判断**(`reviewer_stuck=true`+ 一句话原因)是**下游观察信号**,不是 reviewer 自己的历史。这条信号经过 implementer 的认知层中转,是新信息(implementer 看真实代码 + 跨轮对比后得出的判断),不污染 reviewer 本轮独立判断。

这条补丁让 reviewer 端获得了"我上轮是不是走偏了"的反思回路,**P1 元层 agent 不在场时也能闭合 reviewer 跨轮重复 plan 的故障模式**(原本只能靠 P1 跨轮综合发现的事,现在 reviewer 自己通过 implementer 的元判断信号也能发现)。

#### 3.5b · implementer 全程升 opus(用户拍板,绕过 A/B 实测前置)

**当前 implementer 是 sonnet**(`workflow-template.js` 里每次 `await agent(..., {model:"sonnet"})`),由 CLAUDE.md 项目宪法"Implementer 一律 sonnet 禁用 haiku"约束。

**用户决策**:web-loop 内 implementer 改为**全程 opus**(不再有条件、不再轮 ≥2 才升),理由是接受 token 成本以换执行端能力。

**论据**(refer skeptic R1 §3 三条递进 + 用户反问):
- web-loop implementer 即便收到策略级 nextStepPlan,仍要做**多约束联合权衡 + 跨轮上下文综合 + 把策略翻译成精确 Edit 调用**——这是 search + 约束推理,正是 opus 比 sonnet 强的能力维度
- ② 多 must 互冲(改 G1 破 G3 的震荡循环)是 web-loop 多轮迭代的结构性必然,sonnet 在联合优化上结构性弱;等数据 = 等已知结论
- 把 opus 砸在 reviewer × 3 看同一张图三遍、让 sonnet 在多轮深坑里挖,**是模型分工错配**;web-loop 与 superpowers task(新增功能 / 模块解耦)性质不同,宪法语境不覆盖
- 用户原话"opus agent 负责…类似 superpowers 写 spec 和 writing-plan"暗含 "opus 写 + 执行" 的设计,本研究采用 "opus reviewer 写 nextStepPlan + opus implementer 按 plan 执行" 即用户意图的字面落地

**token 成本估算**(用户拍板接受):
- sonnet impl 平均 ~3-5K input tokens / 轮,opus impl 约 5× 输入价格
- 单 run 跑 3-6 轮,multi-round 累计单 run 多花 ~30-80K opus tokens
- **若 opus impl 命中率高 → 总轮数从 5-6 降到 3-4 → 总 token 净降**(opus impl 替代了 sonnet impl 多跑的 2-3 轮)
- 用户接受最坏情况 token 多花,认 multi-round 体感改善优先

**项目宪法对齐**:本决策实质破宪法"Implementer 一律 sonnet"。final_report 建议 P2 阶段在 CLAUDE.md 加 web-loop 例外条款(详 §5.1)。短期不阻塞 P0 落地——这是用户对自己项目的明确授权,不需要等跨 skill 讨论。

### 3.7 human-hint 续修协议(skeptic R3 方案 1 · 零 runtime 改动)

**问题**:§3.4 触发 paused 后,如果用户起新 run = 重做 setup + r1 + 已 verified 子项重证 = 高代价。skeptic R3 给出一个**沿用现有 resume 机制的零 runtime 改动方案**,把"硬退出+重做"升级为"暂停+用户给一句话+续跑"。

**协议**:
1. **workflow stall 触发时**(§3.4 任一判据):
   - 写 `<workdir>/paused.md`(含本轮 must + 截图清单 + reviewer rootCauseHypothesis + 触发判据)
   - 主循环 `break`,**保留** `issues.json` / `verified.json` / `refs/` / `reviews/`
   - finalize 顶部红字:`## ⚠ PAUSED · 触发判据 N · 写 human-hint-r{N+1}.md 后用 Workflow({resumeFromRunId}) 续跑`
2. **用户在主会话**:
   - Read `<workdir>/paused.md` 看诊断
   - 决策:写 `<workdir>/human-hint-r{N+1}.md`(自然语言,如"实际问题是 ECharts grid.bottom 没传,改 chart options 而不是改 CSS")
   - 调 `Workflow({resumeFromRunId: <runtag>})`(主会话本就支持)
3. **skill 入口检测**:
   - 检测到 `<workdir>/paused.md` 存在 + `<workdir>/human-hint-r{N+1}.md` 存在 → **不走 setup**(rubric/smoke baseline 已验证)、**不重做 r1..rN**(verified 已在台账)、直接进 iterate r{N+1}
4. **iterate 顶端**:
   - 检测 `<workdir>/human-hint-r{round}.md` 存在 → Read 内容,插入 implementer prompt 顶部 "【用户人工指令(优先级最高)】" 段
   - Read 完 `mv` 到 `<workdir>/human-hint-r{round}.consumed.md` 防止下轮重复消费

**优点**:
- **零 runtime 改动**(Workflow tool 不变)
- **零新 args 字段**(用 workdir 文件协议)
- **已 verified 子项不丢**(resume 同 run,台账完整保留)
- **用户口语注入通道**(implementer 看到用户的自然语言指令,效果等价于"主会话直接告诉 implementer 真根因")

**缺点**:
- 跨 session resume 不支持(SKILL.md 已说 `resumeFromRunId` 仅同 session 有效)——只能在同一个 CC session 内续跑;真正跨 session 续修是 P2(workflow.pause() runtime 原语)
- 用户得记得检查 paused.md 并主动写 human-hint(不是自动推送)

**关键**:这条让 P0 的"打断 + 续修"真正闭环——不需要任何 runtime 改动,只需 skill 内部多一个文件读写协议。

### 3.8 P0 实施清单

| # | 文件 | 改动 |
|---|---|---|
| 1 | `workflow-template.js:179-189` | `REVIEWER_SCHEMA.issues.items` 加 **4 字段**(rootCauseHypothesis / affectedFiles / suggestedFix / **nextStepPlan**) |
| 2 | `workflow-template.js:113-167` | `reviewerPrompt()` code lens brief 加"必填 rootCauseHypothesis + affectedFiles + nextStepPlan(策略级、3-8 行、禁代码级 prescription)"指令;**加跨轮反思段:Read 上轮 impl.md 首段 `reviewer_stuck` 标,若 true 必须给不同主线**(§3.5a-ii reviewer_stuck 信号回流补丁) |
| 3 | `workflow-template.js:260-285` | `implementer` prompt 透传 must 完整对象(含 nextStepPlan)+ 5 级指令优先级(§3.5a-i)+ 强制 Read affectedFiles 段 + Read 历史 reviews 段 + Read 上轮 impl.md + Read `human-hint-r{round}.md` 段 + **强制判断题 + impl.md 首段固定结构(含 `reviewer_stuck` 标)**(§3.5a-ii) |
| 4 | `workflow-template.js:260-285` | **implementer agent options 改 `{model:"opus"}`**(用户拍板,§3.5b)|
| 5 | `workflow-template.js:80-111` | `mergeIssues` 或 reviewer prompt 加"强制 matchesIssueId 优先"(§3.3 轻量修)|
| 6 | `workflow-template.js:340-381` | iterate loop 加 §3.4 三条判据,任一触发 → break + 写 paused.md;iterate 顶端加 §3.7 human-hint read + mv consumed |
| 7 | `workflow-template.js:411-430` | `finalize` prompt 加"## ⚠ PAUSED · 触发判据 N · 续修指引"节(若触发)|
| 8 | `SKILL.md` | args 表说明 STALE_ROUNDS;新增"判据 1/2/3 触发说明"节;新增"§3.7 续修协议:`paused.md` + `human-hint-r{N+1}.md` + `Workflow({resumeFromRunId})`"小节;**新增"implementer = opus(本 skill 例外,见 §5.1 决策记录)"小节** |
| 9 | skill 入口控制流(在主会话生成 args 之前) | 检测 `<workdir>/paused.md` + `<workdir>/human-hint-r{N+1}.md` → 不走 setup、直接进 iterate r{N+1} |

无新 agent、无外部依赖。**唯一 model 决策**:implementer 从 sonnet 改 opus(用户拍板)。

---

## 4. 可选叠加 P1:stall 触发的独立 meta-agent(缩窄版)

> P0 实测后若仍有 ~20% "P0 后还卡住"的难 case 才叠加。**不在 P0 同步落**。

### 4.1 团队为什么没把"独立 decision agent" 列入 P0

辩论 R2 后,redesigner 大让步缩窄到只干 3 件 reviewer 物理上干不了的事:**跨轮综合 / 禁止重试清单 / 元判断 escapeRequest**。这与 architect 提的"stall 触发独立 meta-agent(罕用)"立场重合。

但 P0 §3.5(implementer 跨轮 read 历史 reviews) **已经把"跨轮综合"在 implementer 端解决了 80%**——implementer 自己读历史 + 拿到 reviewer 根因,自然能避免"重试同一招"。
P0 §3.4 机检判据 + paused.md **已经把"元判断"在控制流端解决了 80%**——workflow 自己知道"我不行"。

剩余 ~20% 难 case:reviewer 自己写的 root cause hypothesis 系统性走偏(连续 2 轮 implementer 按 reviewer 根因改、改不对)。这才是 meta-agent 真不可替代的窄场景:

> meta-agent 干的事 = 读最近 ≤3 轮 `reviews/round_NN.md` 全文 + `impl.md` 全文 + git diff,**判断 reviewer 自己的根因假设是否系统性走偏**(reviewer 红线要求"绝对标准不读历史"反向看不到这个元问题)。

### 4.2 缩窄设计(redesigner v2 最终方案)

```js
// 触发判据(三选一):
// (a) mustStaleStreak >= max(1, STALE_ROUNDS - 1)  ← ★必须与 STALE_ROUNDS 耦合,见下方
// (b) coveredSubgoals 集合连续 2 轮未增
// (c) git diff --stat 连续 2 轮 < N 行(implementer 改得越来越保守)

// schema 物理禁止双源真理:
const META_AGENT_SCHEMA = { type:"object", required:["forbiddenApproaches"],
  properties: {
    forbiddenApproaches: { type: "array",
      items: { required:["issueId","triedMethod","why_failed_evidence"], ... }
    },
    prioritizedMustIds: { type:"array", items:{type:"string"} },
    escapeRequest: { type:["object","null"],
      properties: { type:{enum:["missing_state","rubric_too_strict","goal_unrealistic","reviewer_disagreement"]}, detail:{type:"string"} }
    }
  }
  // 注意:无 issues, 无 verified, 无 rootCauseHypothesis 字段
  // (防双源真理 — must 判定 + 根因诊断 = reviewer 单源)
};

// 输入(读这些文件,不重读 PNG):
//   - goal.md + refs/manifest.json
//   - 最近 ≤3 轮 reviews/round_NN.md 全文 + impl.md 全文
//   - decision_log.json(append-only)
//   - issuesJson + verifiedLog

// 落:
//   - decision_log.json append(跨轮持久化 forbiddenApproaches)
//   - 下轮 implementer prompt 顶部内插
```

**关键防护(架构师 + redesigner 共同提)**:
- meta-agent 输出 schema 物理禁止 `issues / verified / rootCauseHypothesis` 字段——从 schema 层封死双源
- meta-agent prompt 强约束:"reviewer 的 issues/verified 是台账真相,你不质疑、不修改、不复判"
- 若 meta-agent 产生"对 must X 的不同看法"必须走 `escapeRequest.type=reviewer_disagreement` 通道——**强制人工介入,不让 implementer 选边**

**触发判据与 `staleRounds` 的耦合(必读)**:

P1 的真实价值是在 `staleRounds` 触发硬退出**之前**给一次智力救场。所以触发条件不能简单写死 `mustStaleStreak >= 1`,必须**随用户调 staleRounds 自适应**,**始终留 1 轮救场窗口**:

```js
const P1_TRIGGER_STREAK = Math.max(1, STALE_ROUNDS - 1);
// 默认 staleRounds=2 → P1 触发在 mustStaleStreak == 1(早 1 轮)
// 若用户改 staleRounds=3 → P1 触发在 == 2(始终早 1 轮)
// 若用户改 staleRounds=1(激进退出)→ P1 触发在 == 1(与退出同轮,救完立即退出)
```

**三条触发判据与 staleRounds 三种典型配置下的行为**:

| `staleRounds` | P1 触发(`mustStaleStreak == ?`) | staleRounds 退出 | 救场窗口 |
|---|---|---|---|
| 2(默认) | == 1 | == 2 | **1 轮**(P1 在 r3 跑,r4 implementer 收到 forbidden + 救成则避免 stalled,救不成则 r4 后 == 2 触发 stalled)|
| 3(更保守) | == 2 | == 3 | 1 轮(同上) |
| 1(更激进) | == 1 | == 1 | **0 轮**(P1 与 stalled 同轮触发,效果等价于"退出前给一次救场判断 + 立即退出"——此时 P1 主要价值变成"用 `escapeRequest` 给用户更精确的失败原因",而非"避免退出") |
| 0 / 极端值 | 不触发 | 不退出 | P1 退化(不建议) |

**判据 (b) (c) 也建议挂 staleRounds**:
- 判据 (b) `coveredSubgoals 集合连续 N 轮未增` 中的 N 也应该 = `Math.max(1, STALE_ROUNDS - 1)`,保持与 (a) 同窗口宽度
- 判据 (c) `git diff --stat 连续 N 轮 < threshold` 同理

**实施时必须暴露给用户**:`staleRounds` 已在 args 表(SKILL.md L44),P1 触发判据是它的隐式衍生,**不需要新 args 字段**——只是控制流推导。SKILL.md 加一句说明即可:"启用 P1 后,P1 触发判据 = `mustStaleStreak >= max(1, staleRounds - 1)`,始终在 stalled 退出前 1 轮(或与 staleRounds=1 时同轮)给一次智力救场"。

### 4.3 P1 vs P0 边际收益估算

| 维度 | P0 | P0+P1 |
|---|---|---|
| 痛点覆盖率 | **95%**(diagnostician ①③ 完整;② 由 opus implementer + nextStepPlan 覆盖) | 95-98%(剩余 ~3-5% 真元层走偏 case) |
| token cost | 基线持平 | +~15K opus / stall 触发(假设每 run ≤1 次) |
| 复杂度 | 低(无新 agent) | 中(新 agent + decision_log.json + 触发判据控制流) |
| 调试性 | 高(纯 schema + control flow) | 中(需要审计 meta-agent vs reviewer 的边界守护) |

**判定 P1 是否值得叠加的实测信号**:
- P0 落地后 ≥3 run 的 SUMMARY 中,paused 触发判据频率 ≥30% → P0 不够,叠加 P1
- 反之 paused 触发判据频率 <10% → P0 已够,P1 不必做

---

## 5. 长期建议 P2(超 web-loop scope,需要更大范围讨论)

### 5.1 implementer 全程升 opus(用户最终拍板,已纳入 P0 落地)

> 本节记录这个决策的辩论轨迹与最终用户决定。**实施已在 P0 §3.5b 提到,落地清单 §3.8 #4 已列**。本节存在意义是事后审计 + 推动项目宪法修订。

**辩论轨迹**:

| 阶段 | 立场 | 主张 |
|---|---|---|
| R0/R1 skeptic | 立即升 | "看得见 ≠ 知道怎么改",sonnet 在多轮深坑里挖 = 模型分工错配 |
| R1 architect | 不立即升 | 宪法"Impl 一律 sonnet"有隐含前提 = "reviewer 已吸收开放式判断";修前提(路径 A)比破宪法(路径 B)稳 |
| R2 skeptic 让步 | 软落地为 P2 兜底 | 等 P0 + 扩 schema 实测后,若 ② 仍占主因再触发升 opus |
| lead 综合(初稿) | 取 architect 路径 | impl 升 opus 列 P2 长期讨论,要等 ≥3 run 实测数据 |
| **用户反问** | **立即升** | 即便加策略级 nextStepPlan,sonnet implementer 仍要做多约束联合权衡,这部分仍卡 ceiling |
| **用户最终拍板** | **立即升,接受 token 成本** | 不等数据,接受最坏情况单 run 多 30-80K opus tokens 换执行端能力 |

**用户决策依据(诚实记录)**:
- 即便加 nextStepPlan(策略级 plan)给 implementer,sonnet 仍要 Read 实际代码 + 多约束联合权衡 + 把策略翻译成精确 Edit 调用
- ② 多 must 互冲 在 web-loop 多轮迭代里是结构性必然,"等数据"等于等已知结论
- 用户原话"opus agent 负责…类似 superpowers 写 spec 和 writing-plan"——精确落地 = opus reviewer 写 plan + opus implementer 执行(不是 opus 写 + sonnet 执行,因为本场景下"执行"也需要 opus 级推理)
- token 成本可接受;若 opus impl 命中率高 → 总轮数下降 → 总 token 可能净降

**项目宪法影响**(P2 长期讨论):
- 本决策实质破宪法 "Implementer 一律 sonnet 禁用 haiku"(CLAUDE.md)
- 建议在 CLAUDE.md 加 web-loop 例外条款,措辞如:
  > **Implementer 模型默认 sonnet,例外**:web-loop skill(多轮迭代修 bug 场景)implementer 用 opus——理由:每轮 implementer 干"逆向工程已出错代码 + 多约束联合权衡",与 superpowers 一次性实施 task 性质不同,sonnet 结构性弱。
- 跨 skill 影响评估:path2 主线开发(superpowers + writing-plans 模式)的 implementer 仍维持 sonnet,**不滑坡**;web-loop 是单一 multi-round bug-fix 场景的明确例外

**实施触发**:不在 P0 落地后等实测,**直接同 P0 一起落**(§3.8 实施清单 #4 已列)。

### 5.2 Workflow runtime 级真打断(workflow.pause() 原语)

**与 P0 §3.7 的关系**:P0 §3.7 已经用"workdir 文件协议 + 现有 resume 机制"实现了 90% 的"打断 + 续修"能力,**零 runtime 改动**。本节是 P2 长期讨论的 runtime 级别更优雅版,**不是 P0 的前提**——P0 自洽。

**当前 P0 §3.7 协议的局限**(skeptic R3 + redesigner v2 §6.7 共同评估):
- **跨 session resume 不支持**:`resumeFromRunId` 仅同 session 有效——用户切 session(关 CC 重开)就续不上,只能起新 run
- **依赖用户主动检查**:需要用户记得 Read paused.md 并写 human-hint(不是 push notification)
- **resume 重跑设置 setup 时**:虽然 P0 §3.7 通过 skill 入口控制流跳过 setup,但底层 Workflow 缓存机制理论上仍可能重跑 setup agent(取决于 prompt hash 是否稳定);需要落地后实测

**P2 真 runtime 改动需要的能力**(redesigner v2 §6.7):
1. **`workflow.pause()` 原语**:workflow 内 agent 主动发起暂停,而不是 break 整个脚本
2. **主会话→paused-workflow 双向通道**:用户在主会话给"一句话指示",push 到暂停的 workflow,不需要文件中转
3. **续跑语义边界**:resume 后从暂停点继续,而不是从头重缓存判定

**lead 综合判断**:
- P0 §3.7 已经把 90% 的人在回路场景做掉(同 session 续修),够用户使用
- P2 这条是 Workflow tool 的**范式演进**,影响所有用 Workflow 的 skill(不只 web-loop),应提交给 superpowers/Workflow tool 团队作长期 backlog
- **不在 web-loop 单独实施**,等 runtime 改动落地后 P0 §3.7 自然升级

### 5.3 finalize agent close call → 偏 sonnet(architect 提)

architect R0 诚实账:`finalize` 用 opus 是 close call,主体是机械汇总(verifiedLog / leftoverMust / SUMMARY 4 节模板),"判断"成分仅 2 条(stalled 完整性约束 + GOAL 子项 ✓/✗/? 标注)。**这是 token-audit 已识别的边际机会**。

**lead 综合判断**:作为 P2 单独提交,改动小但需要实测 sonnet 版 SUMMARY 质量。若 sonnet 写的 SUMMARY 区分 stalled/converged/max-rounds 不准 → 维持 opus。

---

## 6. 使用建议(skeptic 提:何时该用 web-loop,何时该不用)

skeptic 提了一个**未被三人反驳**的根本分类(R2 §A 三档拆 + §D 收敛汇总):

| 场景 | 用 web-loop | 用其他 |
|---|---|---|
| **自动化质量门** —— 发布前回归扫一遍 5 个交互轴的视觉 + console + 代码 diff | ✓ 对路。web-loop 的 reproducible / 跨轮台账 / SUMMARY 文档化才真值钱 | — |
| **多 STATES × 多 lens × 收敛标准需要客观沉淀** | ✓ 同上 | — |
| **探索性 bug 修复** —— "K 线挤""按钮压住"这类用户一眼能看的小 bug | ✗ 错配。**3 轮没改好就停,人 + tom 看截图比 6 轮 workflow 快 5 倍、省 token 10 倍** | 用户本人看 + 主会话直接派 sonnet implementer + tom 卡住时分析 |

**核心边界**:web-loop 适合"机械执行 + 客观判定"、不适合"探索性根因"。**用户的"小问题改不好"痛点恰恰落在边界**——他在 web-loop 上跑的多是探索性 bug。

**P0 落地后**:web-loop 在探索性 bug 上的天花板会向上提一档(从"反复无效迭代"到"提前停 + 给出根因 + 建议改 args"),但**仍不替代人在回路的快路径**。建议在 SKILL.md 加一节"何时该用 / 不该用",让用户主动选场景。

---

## 7. 关键 trade-off 表(投票收敛过程)

| 议题 | 立场 | architect | diagnostician | redesigner | skeptic |
|---|---|---|---|---|---|
| 加独立 decision agent | 必做 | R0:✓ → R1:折进 | ✗ | R0:✓ → R2:缩窄 | ✗ |
| 扩 reviewer schema | 主推 | R1:✓(翻转) | ✓ 主推 | R2:✓(采纳) | ✓ |
| 机检判据(3 条)替代硬数 2 轮 | 主推 | ✓ | ✓ | ✓(多通道兜底) | ✓ 主推 |
| stall 触发 meta-agent(P1 缩窄) | 罕用可选 | ✓ niche 价值 | ✗ 过设计 | R2:✓ 缩窄保留 | ✗ |
| implementer 全程升 opus | **用户最终拍板:立即升,纳入 P0** | A 实测后 | 未表态 | implicitly 接受 sonnet | 立即做 |
| Workflow runtime PAUSED-await-injection | 长期建议 | (未评) | (未评) | R2:可行需 runtime 改 | ✓ 强烈主张 |
| 完全替换为 agent team / 全人工 | 不推荐 | ✗ | ✗ | ✗ | ✗(自己也不主推) |

**5/6 议题强收敛**。1 个原剩余分歧(impl 升 opus 时机)被**用户最终拍板取 skeptic 立场**:不等数据、立即升、接受 token 成本(详 §5.1)。

---

## 8. 团队立场演变(诚实记录,供未来研究参考)

### R0 → R1 → R2 各 teammate 关键翻转

**architect**:
- R0:倾向独立 decision agent + reviewer 已做综合 sonnet 化代价大
- **R1 翻转**:主推折进 reviewer schema(每轮)+ stall 触发独立 meta-agent(罕用),承认"schema 锁死 rootCause 是设计 bug 不是 prompt 弱",承认 skeptic 关于宪法的刺成立(但建议本研究不拍板)
- R2:维持 R1 立场

**diagnostician**:
- R0 即给清晰 3 根因 + 主推扩 schema(0 新 agent)+ 次选叠加 decision + 不推 agent team
- R1/R2:立场稳固,论据愈发收紧,#C 根因(mustStaleStreak 字符串去重)被所有人正面承认

**redesigner**:
- R0:独立 decision agent,位置 B'(staleStreak≥1),输出混合制(workingSpec + 结构化)
- R1 让步 4 处:采纳扩 schema 作输入富集 / 多通道触发判据 / escapeRequest 字段 / workingSpec 强化
- **R2 大让步**:撤回"merge 是核心赢面",缩窄 decision agent schema 60%(3 字段)、物理禁双源真理,核心捍卫缩窄到一句:**跨轮看 impl.md + reviews 历史,产出禁止重试清单 + 元判断 escapeRequest**——这两件事 reviewer 物理上干不了

**skeptic**:
- R0 主推(b)混合架构,4 条锋利质询给其他三人
- R1 给三条递进论据破宪法 + 主推合体方案(扩 schema + impl 升 opus + 两 checkpoint)
- **R2 接受让步**:checkpoint A 改可选(沿用智能入口层回讲点头机制,不强制 gate)+ impl 升 opus 软落地为 P2 兜底;**给出 3 条机检判据**(基于现有 issues 台账数据,零新字段)

### 用户原 4 问 ↔ 团队回答归一

| 用户问 | 团队回答(综合) |
|---|---|
| "opus 在干嘛" | reviewer × 3 做有判断的活,但 schema 把根因诊断锁死、opus 算力闲置(architect R1 + diagnostician) |
| "为什么这么重要的工作没人做" | reviewer 有能力但没字段输出;补字段就行,不需要新 agent(P0 §3.2) |
| "重新设计分工" | 没必要重新设计,P0 只改 schema + prompt + 控制流(0 新 agent) |
| "节约 tokens" | P0 净持平,新 agent 净增——你的直觉对(§2.4) |

---

## 9. 落地路径(给用户的可执行建议)

### Step 1(本周可做):P0 实施

按 §3.8 实施清单做 9 处改动(7 处 workflow-template.js + 1 处 SKILL.md + 1 处 skill 入口控制流)。**无新 agent**,但**含 1 处 model 决策**(implementer sonnet → opus,用户已拍板)。

落地包含 4 件实质内容,缺一不可:
1. **扩 reviewer schema 4 字段**(rootCauseHypothesis / affectedFiles / suggestedFix / **nextStepPlan 策略级 plan**)+ code lens 必填 + ux/func 可选
2. **implementer 全程升 opus**(用户决策,§3.5b / §5.1)+ 跨轮 Read 历史 reviews / impl.md / human-hint
3. **mustStaleStreak 语义聚类**(§3.3 reviewer prompt 强制 matchesIssueId 优先)
4. **3 条机检判据 + paused.md/human-hint 续修协议**(§3.4 + §3.7)

建议另起一个 implementation plan 跑 superpowers:writing-plans + subagent-driven-development,与本次 GOAL 持久化升级(`docs/superpowers/plans/2026-06-19-web-loop-goal-persistence.md`)同范式实施。

### Step 2(2-3 周后):P0 实测
跑 ≥3 个真实 web 迭代 run,统计:
- 触发 paused 判据(§3.4 三条)的频率
- 触发后用户重启新 run 的次数 / 比例
- 同一 run 内"小问题改不好"的主观感受(诚实日志)

判定信号(§4.3):
- paused 触发频率 ≥30% AND 重启后仍困难 → 真元层走偏,叠加 P1
- paused 触发频率 <10% → P0 已够,不必 P1
- paused 触发频率高但主观感受改善 → 退人成功了,工具发挥正常

### Step 3(实测后):P1 / P2 决策
- P0 不够(paused 触发频率 ≥30% 且续修后仍困难)→ 落 §4 缩窄版 meta-agent
- 用户希望"真打断 vs 退出" → 推动 P2 §5.2 PAUSED-await-injection 与 superpowers/Workflow 团队对齐
- P0 落地半年后(数据足够)→ 推动 CLAUDE.md 加 "web-loop implementer = opus" 例外条款(§5.1),把 P0 已采用的决策制度化

### 关键不做的事(避免反复犯)
- ✗ **不要单独加完整 decision opus agent**——P0 已覆盖 95%(含 nextStepPlan + opus impl),新 agent 引入双源真理 + token 净增
- ✗ **不要让 ux/func reviewer 也出 rootCauseHypothesis / nextStepPlan**——3 路冲突回到原点,只 code lens 出根因 + plan 是 P0 的关键正确性
- ✗ **不要让 reviewer 在 nextStepPlan 里写代码级 patch / 函数体 / 具体行号 old_string→new_string**——只写策略级(读哪 / 改什么主线 / 风险 / 验证 / 不要再试什么),代码级会触发死板照搬
- ✗ **不要在 P0 落地前砍 reviewer × 3 的 opus**——它们做的多通道证据综合 + 跨轮台账推理是有判断的活
- ✗ **不要把 web-loop 当万能 web 迭代工具**——探索性 bug 修复有更快的路径(skeptic §6)
- ✗ **不要让 path2 主线 implementer 也升 opus**——本次 implementer 升 opus 是 web-loop 单一例外(多轮迭代修 bug 场景),superpowers + writing-plans 一次性实施任务的 implementer 维持 sonnet

---

## 10. 附录 · 中间文档索引

- [`00-team-brief.md`](./00-team-brief.md) — 团队简报(本研究入口)
- [`architect-position.md`](./architect-position.md) — opus 当前分工辩护 + 翻转记录(若 architect 已落)
- [`diagnostician-rootcauses.md`](./diagnostician-rootcauses.md) — 三根因诊断 + 排序(若 diagnostician 已落)
- [`redesigner-proposal.md`](./redesigner-proposal.md) — decision agent v1 → v2 缩窄轨迹(redesigner 已落 v1,v2 §6 已请求补)
- [`skeptic-counter.md`](./skeptic-counter.md) — 对立结论 + 3 机检判据 + PAUSED-await-injection runtime 诉求(若 skeptic 已落)

---

**研究完成日期**:2026-06-21
**lead session**:opus 4.7
**辩论轮次**:R0 初始 + R1/R2 cross-pollination + 收敛
**团队完整画像**:architect / diagnostician / redesigner / skeptic 各自 R0→R1→R2 演变完整保留,无统一意见的部分(impl 升 opus 时机)明记为剩余分歧。

**用户接下来该做**:read §0 TL;DR + §9 落地路径。若决定做 P0,启动 implementation plan(superpowers:writing-plans)按 §3.8 实施清单 9 条展开。

---

## 修订记录

- **2026-06-21 lead 初稿**:P0 = 扩 schema 3 字段 + 多通道判据 + paused 退人;P1 = 缩窄 decision agent;P2 = impl 升 opus(等数据)+ runtime PAUSED
- **2026-06-21 用户反问 1**:战 P0 把 PAUSED 续修协议从 P2 提到 P0(skeptic R3 方案 1,零 runtime 改动)
- **2026-06-21 用户反问 2**:质问"为什么给 sonnet 设计判断权";lead 承认 redesigner v2 撤 workingSpec 论据错位;P0 加第 4 字段 `nextStepPlan` 策略级 plan;reviewer 写 plan 但禁代码级 prescription
- **2026-06-21 用户反问 3 + 拍板**:接受 implementer 全程升 opus 的 token 成本;§5.1 从 P2 长期讨论提到 P0 同步落地;§3.5b 记录决策;§3.8 实施清单加 #4 model 改动;§9 关键不做的事加"path2 主线不滑坡"约束
- **2026-06-21 用户反问 4**:质问 P1 触发条件 `mustStaleStreak >= 1` 是否应与 `staleRounds` 解耦;§4.2 补"P1 触发判据与 staleRounds 耦合"小节,定型 `P1_TRIGGER_STREAK = max(1, STALE_ROUNDS - 1)`,始终留 1 轮救场窗口;判据 (b)(c) 同理挂 staleRounds
- **2026-06-21 用户反问 5 + tom 第一性原理裁定**:质问 r3 implementer 同时看 r1/r2/r3 plan 是否合理 / 是否应只看 r3 plan + P1 常态化;**tom 裁定方案 A**(当前设计),论据=信息论无损(implementer 是 opus 不需要 P1 有损压缩)/ fault tolerance 严格胜(P1 新增故障源)/ 经济性(B 用 95% 死成本换 5% 救命)/ B 在 r1/r2 无历史可综合 → 让步触发就坍缩成 A;§3.5a 补"prompt 优先级模板(5 级)"+ "强制判断题 + reviewer_stuck 信号回流"两条 tom 补丁;§3.8 实施清单 #2/#3 同步更新
