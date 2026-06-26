# B_raw · 自动改进职责审视(teammate B · autoimprove_critic)

> 用户核心问题:web-loop 这套 skill 能否真的承担「无人值守自动迭代改进 web 应用」?
> 立场:整体**机制设计有 plausible 覆盖范围,但实际链路有数行致命断点 + 真实 LLM 行为下若干形同虚设**。下面逐项给证据,不空泛、不帮 skill 找台阶。

---

## § 自动改进总体评估

**结论(数量级估计,基于审阅 SKILL.md + workflow-template.js + tests/ 全集)**:
- 在「布局/视觉/前端 HMR + 单维 must」场景下,能无人值守跑完 1-3 轮收敛 = **约 50% 任务**。
- 在「2-3 维 must 互冲 / canvas 取证不齐 / refresh 假阴 / 后端数据链耦合」场景下,**约 30% 任务**走到 §3.4 三判据触发 paused.md → 需人介入。
- 在「最阴险的"reviewer 重写换 id 让 mustStaleStreak 永远不增,treadmill 因新 must==fixed 阈值不命中"的盲区案」下,**约 20% 任务跑死 maxRounds 也未触发任何 stall 信号** —— 这是用户问"会不会跑死了还没触发任何 stall 信号"的真实答案:**会**,下面 § 失败模式覆盖率给具体反例。

「能承担」≠ 「100% 解 100% 任务」。skill 已经覆盖了大量典型卡死,但**关键链路有 1 处硬断点(planDedupBlock 引用了根本不存在的字段)**,以及若干 reviewer/implementer prompt 指令在真实 LLM 行为下大概率被绕过。**修了那条断点 + 加几个保险后,可承担到 70-80% 的"无人值守"水位**。

---

## § 失败模式覆盖率(三判据 + P1 + planDedupBlock 联合)

### 已覆盖的卡死场景(给 skill 应得的分数)
| 场景 | 覆盖判据 | 评 |
|---|---|---|
| 同一 must fix→regress 反复 ≥2 次 | oscillating(workflow-template.js:460) | 真覆盖,逻辑正确 |
| 旧 must 一直 open + reviewer 不挪 id | mustStaleStreak ≥ STALE_ROUNDS(L422,L452) | 真覆盖,逻辑正确 |
| GOAL 子项跨 ≥2 轮 unverifiable + requiredStates 重叠(STATES 漏配) | missingStates(L482) | 真覆盖,逻辑正确(但前提是 reviewer 真给 requiredStates,见下 § 盲点) |
| 显式声明的 escape 四类(missing_state / rubric_too_strict / goal_unrealistic / reviewer_disagreement) | P1 meta-agent.escapeRequest(L549) | 设计上覆盖,但触发依赖 P1 自己识别,见下 § 盲点 |

### 漏了的卡死场景(盲区,会跑死不触发 stall)

**盲区 1 · reviewer 把 must 换措辞重写 → 新 id + treadmill 判据被同步抬高** ⚠ 最严重
- 机制:reviewer 把"K线挤在下方"换措辞为"K线 grid 高度不足",mergeIssues (L106) 因 title 不同新立 issue id。**mustStaleStreak 重置**(因 mustTransitions ≠ 0,L421-422)。
- 但 treadmill (L467) 算 `lastNewCum >= fixedCum && lastNewCum > 0 && lastNewCum >= prevNewCum` —— 这是**同向单调**累计 newMust ≥ 累计 fixedMust。若 reviewer 全程零修复(没修就没 fix),fixedCum=0,lastNewCum>0,**且新 must 单调累加,treadmill 立刻爆**。OK,这种情况 treadmill 兜得住。
- 但**变种**:reviewer r2 换措辞(newMust=1, fixedCum=0, prevNewCum=0)→ lastNewCum>=prevNewCum ✓,treadmill 触发?**等等**:L469 `if (recent2.length < 2 || round < 3) return false` —— **r2 不触发,r3 起触发**。所以 reviewer 在 r2 换措辞一次,workflow 继续到 r3 才可能触发。这有**1 轮窗口**让 implementer 继续走老路。
- 真盲区:reviewer r2 换措辞 + r3 reviewer 不换措辞(回到 r1 旧 id 重新引用)→ r3 fixedCum 可能涨(因 r2 那条新 must 在 r3 被某 lens 误判 stillPresent=false → 走 mergeIssues:97 → status=fixed)。lastNewCum 不再单调,treadmill 不触发。但实质问题没解决,**用户看到的还是同一个 bug**。这是字面字段比 id 维度盲区——三判据全建在 issue id 上,不建在「实际问题」上,**reviewer 措辞抖动 ≈ 永远不停**。
- **缓解措施**:SKILL §3.3 / stalePrimer(workflow-template.js:119)是 prompt 指令"优先用 matchesIssueId 引用现有 id",**指望 reviewer LLM 听话**;但 reviewer 是 fresh subagent、对 issues.json 跨轮记忆是文字,**LLM 真实行为下措辞抖动是高频反模式**(见 [feedback_argument_discipline] 用户语料库已论证 LLM 倾向于换措辞重述同一观察)。

**盲区 2 · "reviewer 不写 requiredStates 字段"破 missingStates**
- L482 判据要求 `i.matchesSubgoal === g.id && i.unverifiable && Array.isArray(i.requiredStates) && i.requiredStates.length`。**三条全要**。
- reviewer prompt L156 只说"若是 STATES 缺失 → 同时填 requiredStates",但**没有强约束**(不是必填,schema L189 也只是 array 类型)。
- 真实场景:reviewer 标 unverifiable=true 但漏填 requiredStates(忘了 / 不确定哪个 state 缺) → missingStates 永远 false → unverifiable 子项跑死 maxRounds。
- **改进点**:schema 改成 `if unverifiable then requiredStates required`(JSON Schema 用 `if/then` 子句),或者代码侧兜底 — `mergeIssues` 收到 `unverifiable=true && requiredStates 为空` 时报警 / 强标 "[missing requiredStates]" 让下轮 reviewer 补。

**盲区 3 · oscillating 判据要 regressionCount ≥ 2,实际可能 ≥ 3 才触发**
- L460 `(i.regressionCount || 0) >= 2`。注:regressionCount 在 L104 每次 `status==="fixed" → status="regressed"` 时 +1。
- 含义:必须 r1=open → r2=fixed → r3=regressed (count=1) → r4=fixed → r5=regressed (count=2)。**5 轮才能触发**,而 MAX_ROUNDS 默认 6。
- 即使触发也是 r5、用户已等了 5 轮。**改进点**:阈值从 2 降到 1(即 r1=open → r2=fixed → r3=regressed 即触发,3 轮见 stall),代价小、收益大。

**盲区 4 · "implementer 没改成功但 smoke 仍绿" 导致 verdict 看似 fail 但 issue 没回归 (regressionCount 不增)**
- 机制:r2 implementer 试图改但代码改错地方,r2 reviewer 仍判 must (id 不变),mustStaleStreak 涨。**这种"无效改"在 mustStaleStreak 路径里被兜住**——OK。
- 但**变种**:r2 implementer 一改导致 reviewer 把 must title 微调(因为现状变了一点) → 新 id → mustStaleStreak 重置。**回到盲区 1**。

**盲区 5 · P1 escapeRequest 依赖 LLM 自己识别 4 类语义**
- L549 P1 prompt 给 4 类语义说明,但没给"识别失败时怎么办"。LLM 可能选 `null` (不退出)、可能 4 类全不对(典型场景被遗漏)。
- 真实失败模式:rubric_too_strict 与 goal_unrealistic 边界在 LLM 看来是连续光谱,可能两 run P1 给出两种不同分类,导致下游用户看 paused.md 时困惑。

**盲区 6 · P1 触发条件 `gitDiffSmallRounds < 5 行` 易假阳/假阴**
- L527-534:`git diff --stat | tail -1` 抓最后一行 insertions+deletions。但 implementer 改完后**多数情况是有 commit 的**(rollback 路径 L338 `git checkout`,正常路径 implementer 可能自己提交)。若没 commit,git diff 含本轮所有改动;若 commit 了,git diff 只剩工作树未提交的 = 0 行。**完全取决于 implementer 是否 git commit**,这个 skill 没强制约定。
- 实际后果:diff=0 → 每轮都 < 5 → `gitDiffSmallRounds` 单调累加 → r2 就触发 P1 → P1 提前介入 = 误报。或者反过来 implementer 不 commit,diff 永远 > 5 → 永不触发。两边都不准。
- **改进点**:换成 `git log --since=<r-1 timestamp>` 数本轮的 commit 数 + 单 commit 的 stat,或者干脆删此触发条件(只留 mustStaleStreak + coveredSubgoalsUnchangedRounds)。

### 联合覆盖率打分
- mustStaleStreak(STALE)→ 50% 卡死场景
- oscillating → 5-10%(实际罕见,需要 regressionCount ≥2)
- treadmill → 10-15%(r3+ 才看)
- missingStates → 10%(且 reviewer 必须填 requiredStates)
- P1 escapeRequest → 10-15%(LLM 主动识别)
- **联合覆盖 ≈ 70-80% 卡死场景**;盲区 1+2+3+6 联合 ≈ 20-30% 任务可能跑死不触发 stall。

---

## § 已实施机制的盲点 / 反模式

### 盲点 A · planDedupBlock 引用了**不存在的字段** —— 硬链路断点 ⚠ P0 必修
**位置**:workflow-template.js:121
**问题**:planDedupBlock 对 reviewer 说"你能在本 prompt 上方 issuesJson 看到本轮每条 must 已有的'历史 nextStepPlan'字段"。
**实际**:`mergeIssues` (L80-111) 在 L107 push 新 issue 时**只塞 8 个字段**:
```
{ id, lens, title, severity, unverifiable, status, bornRound, lastSeenRound }
```
**完全没有把 reviewer 输出里的 `nextStepPlan / rootCauseHypothesis / affectedFiles / suggestedFix` 复制进去**。
**所以 issuesJson(L266 `JSON.stringify(issues, null, 2)`)里**永远没有 nextStepPlan 字段**。
**后果**:planDedupBlock 自查机制(reviewer round≥2 + code lens)整个**空转** —— reviewer LLM 被指示去看一个不存在的字段,自查必然无法进行,可能编出"看起来是同主线"的幻觉判断,或者忽略本段。
**测试盲区**:tests/test-reviewer-prompt.mjs(只 grep 字符串)和 tests/test-implementer-prompt-priority.mjs(只验证 prompt 含 nextStepPlan 子串)都**没有验证数据流转**。`mergeIssues` 单元测试也不存在(看 `tests/` 列表无)。
**改法**:
- workflow-template.js:107 修 push 字段:
  ```js
  if(!dup) issues.push({
    id:nextId(v.lens,round), lens:v.lens, title:it.title, severity:it.severity,
    unverifiable:it.unverifiable===true, status:"open", bornRound:round, lastSeenRound:round,
    // ★ planDedupBlock 真实兜底需要的 4 字段(P0 §3.2,reviewer code lens 必填)
    rootCauseHypothesis: it.rootCauseHypothesis || null,
    affectedFiles: it.affectedFiles || [],
    suggestedFix: it.suggestedFix || null,
    nextStepPlan: it.nextStepPlan || null,
    nextStepPlanHistory: it.nextStepPlan ? [{round, plan: it.nextStepPlan}] : []
  });
  ```
- 同时 L97 / L104 status 变化时(fix/regress)别清掉这些字段。
- mergeIssues 在已有 id 命中(L103-104,it.matchesIssueId)时,append 到 `nextStepPlanHistory`(让 reviewer 真能看到多轮主线)。
- 加测试 `tests/test-issues-decision-fields.mjs`:造一个 reviewer 输出含 nextStepPlan,run mergeIssues,验证 issues[0].nextStepPlan === "..."。

### 盲点 B · `reflectBlock` 让 reviewer 直接 cat 上轮 impl.md (L120) ≠ "reviewer 不读自己历史输出" 红线
**位置**:workflow-template.js:120,SKILL.md §3.5a-ii
**问题**:reflectBlock 让 reviewer `cat ${WORKDIR}/rounds/${round-1}/impl.md | head -40`。这部分是 implementer 写的,**严格来说不算"reviewer 读自己历史输出"**。但 impl.md 首段 "plan 重复分析" 字段(L330)是 implementer 在引用上轮 plan—**间接把上轮 reviewer 的 plan 信号送进了本轮 reviewer**。
**是否破红线**:技术上不破(implementer 是中间转译器,提供"observation"而非 reviewer 原话)。**真红线问题**:这个间接通道只能传"plan 重复 yes/no",不传 plan 内容本身;但本轮 reviewer 写 nextStepPlan 时还是要参考 plan 主线 → 必须靠**盲点 A 修后的 nextStepPlanHistory** 才能让 reviewer 看历史主线 → 才能真正自查"我这轮是不是又写了同主线"。
**结论**:reflectBlock 不破红线,但**功能不足以独立支撑 planDedup**;盲点 A 是真实生命线。

### 盲点 C · `historyReviews`(L314)让 reviewer 读上一轮 reviews/round_NN.md —— 这个**直接**给 implementer
**位置**:workflow-template.js:314。这个是给 **implementer**(优先级 4),不是 reviewer。**OK,我误读了**;reviewer 不读历史 reviews。但 reflectBlock 是 reviewer 看 implementer 的 impl.md,**这是真实存在的信号回流通道**。

### 盲点 D · `forbiddenApproaches` 注入 implementer 优先级 3 vs 优先级 1 (人工 hint) 的实际效力
**位置**:L310-313。
**问题**:`decisionLog` 段在 implementer prompt 里,**结构上紧接在 `historyReviews / histImpl` 之前**(L329),距离 prompt 顶部 humanHintRead(L294)很远(约 50-80 行)。优先级声称 P3,但 prompt 物理位置在末段。
**真实 LLM 行为**:Opus implementer 高概率读完顶部 P1 / P2 后,P3 段被「注意力衰减」覆盖。**反复违 forbidden 的可能**:中高(约 30-40% 场景,基于 LLM prompt 顺序敏感性观察)。
**缓解措施**:
- L310 段加"⚠ 这些 (issueId, triedMethod) 组合在本 run 跨轮试过且失败,**不得重试**" —— 这行措辞强,但放在长 prompt 末段。
- decision_log union 累计后无上限,后期可能上百条 forbidden(超过 implementer 注意力上限)→ **建议加 prioritizedMustIds 反向过滤**:只内插与本轮 openMust 相关的 forbidden 条目,跨 must id 的旧 forbidden 折叠摘要。
**改法**:
- workflow-template.js:310:把 forbiddenList 用 openIssues 的 id 集合过滤,只保留 issueId 在本轮 openMust 内的 forbidden。代码 ~3 行。
- 提一段简短"已 verified 子项 → 不要再动这些代码块" 也加到 forbidden 段。

### 盲点 E · `reviewer_stuck` 信号回流的实际信号通量
**位置**:reviewer 端 L120(reflectBlock),implementer 端 L330(强制判断题)
**问题**:整条链路是:
1. r1 reviewer 写 nextStepPlan_r1。
2. r2 implementer 在 impl.md 首段判断 plan_r2 vs plan_r1 是否本质相同 → reviewer_stuck=true/false。**但 implementer 此时还没看 r2 plan**(r2 plan 在 r2 reviewer 后才生成,r2 implementer 看的是 r2 must 而非 r2 plan?……等等,L324 优先级 2 就是 **r2 reviewer 给的 plan**(传递性:r1 reviewer 出 must,r2 implementer 来改,可是 r2 implementer 改完后才有 r2 capture+r2 reviewer。所以 L324 内容是 **r1 reviewer 残留 must**(L290:`mustWithDecision = openIssues.filter(i=>i.severity==="must")`,即 r1 出的 must。所以实际是):
   - r2 implementer 看的是 r1 reviewer 给的 must.nextStepPlan_r1 → 是同一份。
   - r2 implementer 写 impl.md 时,`reviewer_stuck` 判断的是 "r2 plan vs r1 plan 是否本质相同",但 r2 plan **此时不存在**(L330 prompt 语义混乱:"r${round} plan 与 r${round-1} plan 是否本质相同")。
   - 真实场景:r2 implementer 只能看 r1 plan 一份,无法判断"r2 vs r1 是否相同"——除非 implementer 把 r2 plan 假想为"r1 plan 的下一轮"。
3. r2 capture + r2 reviewer 跑。r2 reviewer 在 reflectBlock 里 cat r1 impl.md 看上轮 reviewer_stuck —— **但 r1 implementer 写的 reviewer_stuck 字段无意义**(r1 没有上轮 plan 可比)。
4. r3 reviewer 在 reflectBlock 里 cat r2 impl.md —— 这才是真实信号点。
**真问题**:
- L330 强制判断题在 r≥2 才生效(`round >= 2 ?`),但语义上 "r2 plan vs r1 plan" 本身就含混(r2 plan 还未出)。implementer LLM 大概率会把 reviewer_stuck 误读为"r1 plan 本轮是否还有效"——和设计语义有偏移。
- L120 reflectBlock 在 r≥2 才生效,但 "上一轮 reviewer 给的 nextStepPlan 与 plan_r${round-2}" 的比较 —— 这是**两个 reviewer 历史 plan 互比**,设计是想说 r2 reviewer 跟 r1 reviewer 给的 plan 是否重复。实际通过 implementer impl.md 中转一手。
- 链路成立的条件:
  - r2 implementer 在 impl.md 首段诚实标 reviewer_stuck (依赖 LLM 听话)
  - r3 reviewer 在 reflectBlock 真去 cat (依赖 LLM 听话)
  - r3 reviewer 看到 reviewer_stuck=true 后真的换主线 (依赖 LLM 听话)
- **三段串联 LLM 听话率打折后,真实信号成功传递率 ≈ 50-70%**(三段各 80-90% × 串联)。
**改进点**:
- 不要靠 LLM 中转。让 workflow 程序化提取 r2 impl.md 首段的 reviewer_stuck 字段,赋给一个 workflow 变量 `lastReviewerStuck`,直接内插到 r3 reviewer prompt 顶部 "REVIEWER_STUCK=true,本轮强制换主线" —— **不依赖 implementer / reviewer 自己 cat**。
- workflow-template.js:加一个 agent 调用读 impl.md 首段,parse `reviewer_stuck` 字段(YAML 头格式),把结果作为 prompt 变量。

### 盲点 F · planDedupBlock 的"临界规则"与"真二选一"两段逻辑复杂,LLM 听话率下降
**位置**:workflow-template.js:121。
**问题**:planDedupBlock 是一段 50+ 行的复杂条件指令(临界规则 + 真二选一倾向 + 默认查重收紧 + 例外条款)。LLM 在长复杂指令下听话率显著下降(prompt engineering 经验值:简单规则 90%,复杂条件 60-70%)。
**结合盲点 A**:planDedupBlock 还引用了不存在的 nextStepPlan 字段,**当字段不存在时,LLM 在"对照即将写的 plan 主线 vs 历史 nextStepPlan 主线对比"步骤会触发不确定行为**——可能编故事说"看不到历史 plan,我推断 r1 plan 是 X"。
**改进点**:
- 盲点 A 修后,把 planDedupBlock 简化为 2 条 if-then:
  1. 若 nextStepPlanHistory 含本轮你计划写的主线 (相似度 by LLM) → 必须换主线,否则 escapeRequest=reviewer_disagreement
  2. 否则正常出 plan
- 移除"真二选一倾向"段(过于复杂,LLM 难听话)。

### 盲点 G · resumeFromRunId 同 session 限制是真实痛点
**位置**:SKILL.md L138-139, L172
**问题**:用户写完 human-hint-r{N+1}.md 后,必须**同一个 Claude Code session** 调 Workflow({resumeFromRunId}) 才有效。但实际场景中:
- 用户可能关闭 session 准备隔天再续修(常见)
- 用户切换设备(memory `feedback_multi_source_verification_discipline` 表明用户跨多机)
- session compact 后,Workflow runtime 状态可能丢失
**真实后果**:跨 session 切换 = 起新 run = 丢失 verified 进度 = 必须从 r1 跑全套,**人工 hint 信号实际能保留的时间窗 ≈ 几小时**。
**实际频率**:中等(20-30% 续修 case 会遭遇跨 session 失效)。
**改进点**:
- workflow-template.js:进 iterate 顶部先尝试 Read `${WORKDIR}/issues.json` + `${WORKDIR}/verified.json`,如果存在则**从这两文件 rehydrate** issues 数组、verifiedLog 数组、round 计数器,而不是只靠 Workflow runtime 的 memory。
- 这样跨 session 也能 resume —— **从文件 cold-start**。技术可行性高(workflow 已经在写这两文件)。
- Skill.md L138-139 红线"resumeFromRunId 同 session"可以删,跨 session 也能跑(只是 Workflow runtime 自身的 promise/log 状态丢了,无关紧要)。
**估 token 影响**:无改变(只是从文件 rehydrate 一次,数 KB 额外读取)。

### 盲点 H · "5 级优先级模板" 在 implementer 真实行为下不真分层
**位置**:workflow-template.js:282-329
**问题**:5 级 (humanHint / mustWithDecision / decisionLog / historyReviews / histImpl) 都串在同一 prompt 里,prompt 上各段距离 prompt 顶部远近 ≠ "优先级 1-5"。如:
- humanHintRead 是 `cat ${WORKDIR}/human-hint-rN.md` 命令(L294)在 prompt 顶部
- mustBlock 在 L324(优先级 2)
- decisionLog 在 L329(优先级 3,**在 historyReviews / histImpl 同段**)
- historyReviews 也在 L314 / L329(优先级 4)
- histImpl 在 L315 / L329(优先级 5)
**真实 LLM 行为**:对 opus implementer,5 级优先级**是 prompt 文本的等价 5 段,LLM 不会真按数字优先级排序行为**。实际听话顺序更接近"prompt 段落物理位置 + 强调词频次"。
**结合盲点 D**:forbiddenApproaches 在末段 + 50+ 行长度 → 真实采纳率 < 50%。
**改进点**:
- 把 humanHint / forbiddenApproaches 都放 prompt **顶部** (优先级 1 + 3 共置),用 `## ⛔ 绝对禁忌`、`## 🎯 本轮主任务` 等强标识符切分。
- 把 历史 reviews + histImpl 都丢到 prompt 底部(优先级 4-5 弱信号)。
- 减少 prompt 总长(目前 implementer prompt 接近 5K token,opus 长 prompt 末段衰减率 30-40%)。

### 盲点 I · 自检 prompt 全程依赖 LLM 自报、无机器验证
**问题**:整个 web-loop 机制 100% 依赖 reviewer / implementer / P1 meta-agent 三类 LLM 输出诚实回报。无任何"机器验证 LLM 输出真实性"的环节(例外:smoke gate 是机器验证回归)。
- reviewer 谎报 verdict=pass + verified 假证据 → 提前收敛
- implementer 谎报 reviewer_stuck=false → 信号回流断
- P1 meta-agent 选错 escapeRequest 类 → 续修指引错
**已有兜底**:
- L412-416 verdict 从台账推导:若 lens 有 open must 但申报 verdict=pass,强制改成 fail。**这是机器兜底,非常关键**,但只兜了 verdict 一项。
- evidence 必须绑"截图文件名/probe key/diff 函数名"(L148-153),勉强算机器可 grep 验证,但 reviewer 编"<SHOTS_DIR>/r02_03-pick-hit.png 显示 K线 grid 高度 670px ≈ 视口 1080 的 62%"——文件存在 ✓ 但**"670px"是 LLM 凭空捏造的,无任何机器验证**。
**改进点**:
- evidence 验证再加强:probe key 必须存在于 manifest.stateDumps 实际 keys,workflow 程序化校验;screenshot evidence 加 OCR / 像素比例计算辅助(代价大,需要单独的 vision agent 二审)。
- 或更轻量:统计 mustStaleStreak、verified.coveredSubgoals 跨轮变化 → 若 verified 突然在某轮覆盖全部子项但 issues 台账无明显进展(open must 多于 fixed),触发"verifier 二审"信号到 P1。

### 盲点 J · maxRounds=6 默认值在结合三判据后偏少
**位置**:SKILL.md L141, workflow-template.js:24
**问题**:
- 三判据 + STALE_ROUNDS=2 默认在 r3-r4 才可能触发
- P1_TRIGGER_STREAK = max(1, 2-1) = 1,r2 起触发
- maxRounds=6 给的实际 effective rounds 在触发 stall 后可能只跑 2-3 轮就停
**真实后果**:用户期望 6 轮,实际经常 3-4 轮就 paused 或 stalled。无大问题(stalled 不算失败,只是要求人介入)。但用户可能会觉得"才 3 轮就 give up?"
**改进点**:无需改默认值。在 SUMMARY.md PAUSED 节顶部明示"本 run 跑了 r{N},stalled 触发于 r{N},maxRounds={MAX} 未跑满"——让用户明白原因。当前已有(L641-648 finalizePausedBlock 提到"本 run 在 r${round} 被机检判据触发暂停"),但没显式"未跑满"。

---

## § 必依赖人 的 case 清单(典型场景,不是空泛"复杂 bug")

1. **GOAL 拆解错** —— 智能入口层主会话 LLM 把"K线挤压"误拆成 G1(K线高度)+ G2(标签位置)而漏掉真正的根因(grid padding)。Workflow 内无任何机制让 reviewer 推翻 GOAL_SUBGOALS(args 启动后冻结)。**人介入必须**。门槛 = 改 args 起新 run = 5-10 分钟。
2. **后端长 latency / 数据流断** —— smoke gate 绿、capture 截图无差异、reviewer 误判 verdict=pass 但实际后端某接口 500 — refresh agent 报 ready 但实际后端 timeout。无机器验证 refresh 真实健康度(仅 healthUrl 200 check,不验业务数据)。**人介入门槛 = 看 console + 后端日志**。
3. **reviewer 三 lens 一致漏看某 must** —— UX/func/code 三 lens 都没意识到 console 里某个 deprecation warning 是 P0 (实际是即将 break) → workflow converged → 人验证后必须重跑。**人介入门槛 = 跨 lens 集成判断**(LLM 弱项)。
4. **canvas 取证根本不可能** —— ECharts 复杂渲染、像素级特征 LLM 看不出(memory `project_path2_web_ui_levels_lanes` 案例已坐实) → unverifiable 跨轮 → 但 reviewer 漏写 requiredStates(盲区 2)→ missingStates 不触发 → 跑死 maxRounds。**人介入门槛 = 看 stateDumps 手判**。
5. **多 must 互冲是真实双向 trade-off** —— "K线占垂直 60% (G1)" vs "标签清晰可读 (G2,需要标签下方 padding)" 真冲突 → P1 escapeRequest=goal_unrealistic? 但 LLM 大概率不会选这个 escape,因为认知上没 escape 习惯 → 跑死 maxRounds 触发 stalled。**人介入门槛 = 重定义 GOAL**(必要)。
6. **rubric / GOAL / refImages 自相矛盾** —— 用户上传的 ref role=goal 显示 K 线占 80% 高度,但 GOAL_SUBGOALS 写 60%。reviewer 应当报 escapeRequest=rubric_too_strict,但 LLM 大概率会忽略矛盾、按 GOAL_SUBGOALS 判 → 跑死。

**估计**:1-6 类 case 累计约 20-30% 任务会必然依赖人介入。其中 case 4 / case 6 是"出现频率高且 workflow 内无能力解" 的硬阻塞。

---

## § 改进建议清单(actionable,每条 = 文件:行 + 改法 + 期望提升)

> **⚠ Token 口径声明(2026-06-22 lead 对齐)**:本节及后续所有"Δtoken/run / $X/run / token 净降/增量"指 **运行 workflow 时**每跑一次 web-loop 真实消耗的 LLM API 费用(运行复发),**不包含**修改 skill 源码本身的一次性 dev cost。"改动 ~X 行 / 改动幅度 trivial/moderate/large" 才是实现工作量,与 token 运行成本独立。两维度在 final_report 总表分两栏并列。

### P0 必修(链路断点)
1. **workflow-template.js:107(mergeIssues push 字段补全)**:加 rootCauseHypothesis / affectedFiles / suggestedFix / nextStepPlan / **nextStepPlanHistory** 5 字段。`mergeIssues` 在 id 已存在路径(L103-104)append 到 nextStepPlanHistory。预期提升:planDedupBlock 真生效,reviewer 真能看历史主线;**P0 优先级最高**,改动 ~10 行。
2. **workflow-template.js:121(planDedupBlock 简化)**:删"真二选一"段,只留 if-then 两条规则。等盲点 A 修完后此段才有意义。改动 ~30 行删除。
3. **tests/test-issues-decision-fields.mjs(新增)**:造 reviewer 输出含 nextStepPlan,跑 mergeIssues,验证 issues 含决策字段;造 r2 reviewer 引用 r1 同 id must,验证 nextStepPlanHistory.length===2。新增 ~80 行。
4. **workflow-template.js:189 REVIEWER_SCHEMA(收紧 requiredStates)**:用 JSON Schema `if: {properties:{unverifiable:{const:true}}}, then: {required: ["requiredStates"]}` 强制 unverifiable→requiredStates。改动 ~5 行。预期提升:missingStates 判据真实可触发率从 ~50% 提到 ~85%。

### P1 高 ROI(改进自动改进能力)
5. **workflow-template.js:460(oscillating 阈值从 2 降到 1)**:`(i.regressionCount || 0) >= 1`。预期提升:震荡场景在 r3 即触发(vs 之前 r5),用户少等 2 轮。改动 1 字符。
6. **workflow-template.js:527-534(gitDiffSmallRounds 改成 commit-based 或删除)**:删此触发条件,仅保留 mustStaleStreak + coveredSubgoalsUnchangedRounds 双通道。预期提升:消除"取决于 implementer 是否 commit"的假阴/假阳。改动 ~10 行删除。
7. **workflow-template.js:329(prompt 重排)**:把 humanHint + forbiddenApproaches 都升到 prompt 顶部 (强标识符 ⛔/🎯 切分)、5 级模板缩成 3 级 (人工 / 必从 / 参考)。预期提升:forbiddenApproaches 真实采纳率 50%→70%。改动 ~30 行重排。
8. **workflow-template.js:120 reflectBlock 改成 workflow 程序化提取**:在 r2 implementer 后加一个 sonnet agent parse impl.md 首段,把 reviewer_stuck 作为 workflow 变量 `lastReviewerStuck`,r3 reviewer prompt 顶部内插 `REVIEWER_STUCK_FROM_LAST_ROUND=${lastReviewerStuck}`。预期提升:信号链路成功率 50-70% → 85-90%。改动 ~20 行新增 + 删 reflectBlock cat 指令。

### P2 实操痛点(续修协议)
9. **workflow-template.js:iterate 顶部 rehydrate**:进 iterate 前 Read issues.json / verified.json,从文件恢复 issues 数组 + verifiedLog + 由 verifiedLog round 字段最大值推 round 计数。预期提升:跨 session resume 可行性 0% → 80%(只剩 Workflow runtime ID 必须新生成,但能继承状态)。改动 ~30 行。
10. **SKILL.md L138-139 / L172 红线放宽**:配合 #9 改后,"resumeFromRunId 仅同 session"红线删,加"跨 session resume 通过文件 rehydrate 自动支持"。改动 SKILL ~10 行。

### P2 信号通量(已经设计了但还差临门一脚)
11. **workflow-template.js:310 forbiddenList 按本轮 openMust id 过滤 + 折叠摘要**:避免 forbidden 累积超 LLM 注意力上限。改动 ~5 行。
12. **workflow-template.js:639 SUMMARY.md "PAUSED 节" 加 effective rounds 解释**:"本 run 跑了 r{N},stalled 触发于 r{N},maxRounds={MAX} 未跑满,因为 …"。改动 ~5 行。

### P3 长期(机器验证 LLM 输出)
13. **新增 vision verifier agent (P3)**:某些 GOAL 子项 (`verifiable_via=screenshot` + `measurable` 有数值)接入轻量 OCR / 像素比例工具验 evidence。代价大、ROI 中。改动 ~150 行(可拆 separate skill)。

---

## § 估算自动改进能力修复后的提升

修盲点 A (planDedupBlock 链路断点) + 盲点 B/D/H (prompt 优先级) + 盲点 E (信号回流程序化):
- 真实 "无人值守解需求" 任务覆盖率从 50% → 70-80%
- "跑死不触发 stall" 任务从 20% → 5-10%
- 人介入门槛比例从 30% → 15-20%
- 跨 session resume 可行(配合 #9)

剩余 hard limit (必依赖人) ≈ 15-20% 任务,主要是 GOAL 拆解错 / canvas 不可取证 / 多 must 真冲突 —— 这部分不是技术能解的,是设计层硬阻塞。

---

## § 与 SKILL.md 宣称的对比(诚实表态)

| SKILL.md 宣称 | 实测结论 |
|---|---|
| "三机检判据 + P1 联合保险" | 联合覆盖 70-80% 卡死,**有 5-10% 真盲区**(盲区 1+3+6) |
| "planDedupBlock 是 reviewer 自查兜底" | **当前是空转**(链路断点,盲点 A),修后才生效 |
| "5 级 prompt 优先级模板" | **实测 LLM 不按 5 级排序**,prompt 物理位置 + 强调词决定 |
| "reviewer 永久零浏览器" | 真红线,严格遵守,无破绽(reflectBlock 通过 implementer 中转算 observation) |
| "无人值守自动迭代" | **能,但当前覆盖率 ~50%,修后 ~70-80%**,剩 15-20% 必人介入 |

---

## § Cold-read 自查 · 低置信度条目(留 Phase 2 用 A/C 视角修)

> 我在写 B_raw 后冷读一遍,主动标出依赖未经实测的假设、场景未充分外延、或推论链有跳跃的条目。这些不是要 retract,而是诚实标"等 A/C 修正"。

### 低置信 L1 · "20% 任务跑死 maxRounds 不触发 stall" 数量级 [置信:中]
- 来源:§ 总体评估顶段。
- 依据:盲区 1(reviewer 措辞抖动)+ 盲区 2(reviewer 漏 requiredStates)+ 盲区 6(gitDiff 假阳/假阴)的**叠加假设**,未做组合概率精算。
- 风险:若 reviewer LLM(opus) 在 path2 实测中措辞抖动率远低于我估的 30-40%,这 20% 会被高估到 5-10%。
- 求 A:你看路径过的 path2 真实历史 SUMMARY.md / issues.json,reviewer 在多轮间是否真给同一 bug 换措辞?
- 求 C:这 20% × 单 run $10-18 = $2-3.6 期望 token 损失/run,我估算口径对吗?

### 低置信 L2 · "盲区 1 reviewer 措辞抖动率 30-40%" [置信:低-中]
- 来源:§ 失败模式覆盖率盲区 1。
- 依据:memory `feedback_argument_discipline` 用户语料库观察 LLM 倾向于换措辞重述,**但语料库不是 web-loop 实测**;30-40% 是经验估计、不是 telemetry。
- 风险:opus reviewer 在「issuesJson 内有完整旧 must title 可对照」+「stalePrimer 强 prompt 提示用 matchesIssueId」双约束下,真实抖动率可能 ≤ 15%。
- 求 A 实测视角:path2 历史 run 的 issues.json 里,跨轮 must title **有多少是新增 id 但实际同一 bug**?
- 若 ≤ 15%:盲区 1 改为「中度」非「最严重」,B_raw §盲区联合覆盖率会重算。

### 低置信 L3 · "prompt 顺序敏感性,P3 段被注意力衰减 30-40%" [置信:低]
- 来源:§ 盲点 D / 盲点 H。
- 依据:LLM prompt engineering 经验值,非 web-loop 特定。opus 的长 prompt 末段衰减率在不同任务上有差异;有的任务因 system message 设计反而末段更受关注。
- 风险:这是 prompt engineering 民间观察,Claude opus 在结构化标识符 (P1-P5 标签 + 强调词) 下可能确实分层,衰减率可能 ≤ 15%。
- 求 A 架构视角:5 级优先级模板是否被实测验证过?有无对应 anti-test(prompt 末段指令故意违反)?
- 若实测 LLM 真按 5 级听话:B_raw §盲点 H + §改进 7(prompt 重排)收益降到 5-10% capability 增量。

### 低置信 L4 · "treadmill r3 才触发 + 盲区窗口 1 轮" [置信:高,但有边界]
- 来源:§ 盲区 1 中段「等等」推论。
- 依据:L469 `if (recent2.length < 2 || round < 3) return false` 是代码硬限制,这部分置信高。
- 但**"1 轮窗口"**的实际危害取决于 implementer 在 r2 是否能多措辞修一遍——若能,可能在 r3 reviewer 出 verdict 前就把 must 修了。盲区 1 假设的"实质问题没解决"未必发生。
- 求 C:盲区 1 实际危害到 token 浪费的概率 ≈ 30-40% 还是 60-70%?

### 低置信 L5 · "P1 实质命中率 30-50%" 数字 [置信:低]
- 来源:我回 C SendMessage 时给的数。
- 依据:LLM 主动产 forbiddenApproaches 的"tried+failed"配对识别能力凭直觉估,**未做 path2 历史 P1 触发统计**。
- 风险:opus meta-agent 在长 context (3 轮 reviews + impl.md)下可能识别率更高(60-80%),或更低(15-25%)。
- 求 A 架构视角:P1 真实命中率是 web-loop 设计**实证盲区**(无 telemetry)还是已有反复测试?
- 求 C 成本视角:若 P1 命中率 ≥ 60%,5-20k input/run 是合理代价;若 ≤ 30%,确实浪费。

### 低置信 L6 · "续修协议 paused.md a/b/c 三档命中率" [置信:低]
- 来源:我回 C SendMessage 时给的 a=30-40% / b=40-50% / c=15-20% 分布。
- 依据:**直觉估**,非实测;path2 历史的 paused.md 记录我没具体读。
- 风险:实际分布可能更偏 (b)(用户写 hint 是低门槛行为)→ "跨 session 失效"危害放大;或更偏 (c)(用户耐心低,直接转手工)→ workflow 设计本身价值下降。
- 求 A:你能读 `.claude/web-loop/<runtag>/` 历史目录吗?统计有多少 paused.md / 多少 human-hint 文件,推真实分布?

### 低置信 L7 · "盲点 E 三段串联 LLM 听话率 50-70%" [置信:低]
- 来源:§ 盲点 E。
- 依据:**80-90% 各段单点听话率 × 三段串联** 的简单概率乘法估。
- 风险:LLM 听话率不是独立事件,opus implementer 在 r2 诚实标 reviewer_stuck 后,opus reviewer 在 r3 读 impl.md 也会高度关注(强信号),所以串联不一定 ×3 衰减;真实可能 ≥ 80%。
- 求 A:架构上 reflectBlock 的实证依据是什么?(从 SKILL.md L120 看是 P0 §3.5a-ii redesign 引入,但未必有实测验证。)

### 低置信 L8 · "改进 7 (prompt 重排) capability +20%" 数字 [置信:低]
- 来源:§ 改进 P1 第 7 条。
- 依据:基于盲点 D/H 的衰减率估,衰减率本身置信低(见 L3)。
- 这条改进**风险最低**(改 prompt 顺序无副作用),即使提升只 5%,采纳也无害——但宣称 +20% 是高估的可能性大。

---

### 自查总结
- **高置信(可作为 final_report 主结论)**:盲点 A (链路断点,代码可见) / 盲点 B-C 红线判断 / 盲点 G (resumeFromRunId 同 session 限制是 SKILL.md 自报) / 盲区 3 (oscillating 阈值算术) / 盲区 6 (gitDiff 假阳/假阴是代码可见缺陷) / 改进 P0 全部 / 改进 5+6+9 三条。
- **中置信(求 A/C 协助修正)**:盲区 1+2 实际危害 / 盲点 D/H 衰减率 / 盲点 E 信号链路成功率 / P1 命中率 / paused 命中率分布 / 改进 7+8 capability 增益。
- **底线**:即使中置信全部高估 2 倍,**盲点 A 仍是 P0 必修**(代码可见的硬断点,不依赖任何估计)。这条不会因 Phase 2 修正而退守。

---

## § Phase 2 追加 · 回 C 的两条新议题(C SendMessage 2026-06-22)

### 议题 1 · P1 schema 加第 4 字段 `p1_skip_reason`(采纳)

**C 的发现**:80% 触发率 × 30-50% 真用率 = 60-70% 触发是"P1 跑了但产空 forbiddenApproaches"。根因是 reviewer 在 r1→r2 时第一轮新 must 没有 "tried+failed" 配对可提炼,P1 被迫产空数组或幻觉填充。

**采纳。延伸为 P1 改进**:

**改进 #14(新)** · workflow-template.js:205 META_AGENT_SCHEMA 加第 4 字段:
```js
p1_skip_reason: { type:["string","null"],
  enum:["no_tried_method_yet","all_addressed","insufficient_evidence",null] }
```
- `no_tried_method_yet` = r1→r2 这种"还没尝试过任何修法"的第一触发场景
- `all_addressed` = 上轮所有 must 在本轮真实 fixed(虽 mustStaleStreak 触发但其实在进展)
- `insufficient_evidence` = LLM 看 3 轮 reviews 没看到清晰 tried+failed 配对
- null = P1 真识别到 forbidden 配对,正常产出 forbiddenApproaches

P1 prompt 加一句:"若你判断本轮无足够证据提炼 forbiddenApproaches,**优先标 p1_skip_reason 非 null** + forbiddenApproaches 留空数组,**禁止填充凑数条目**(这是 P1 命中率退化的主因)。"

预期提升:**P1 真命中率从 30-50% → 50-70%**(剔除被迫填充的 case);0 token 增量(field 本身 ≤ 30 char)。**P1 高 ROI**。

### 议题 2 · maxRounds=6 默认 vs effective 3-4 轮:capability 问题非 cost 问题

**C 的辨析**:这是 cost 还是 capability?

**我倾向 capability 问题**,理由 + 一条 cost-aware 微调建议:

- **capability 问题主线证据**:盲区 1(reviewer 措辞抖动)让 mustStaleStreak 在 r2 立刻不再积累(因 mustTransitions ≠ 0,reviewer 换措辞 = 新 id = 算 transition),实际 r2 就把 STALE 计数清零;但 P1 同时在 r2 因 coveredSubgoalsUnchangedRounds=1 触发(几乎必然),走 P1 段 → 若 P1 产生 escapeRequest 就 paused。**结果**:用户给 maxRounds=6,实际跑到 r3-r4 就被 P1 escapeRequest 提前退,**不是 STALE 退,而是 P1 提前 escape**。这是 capability 退化(本来该继续跑被 P1 误退)而非 cost 优化(用户期望多跑)。

- **cost-aware 微调建议(改进 #15,新)**:把 STALE_ROUNDS 默认从 2 改到 3,**但配合 maxRounds 从 6 降到 5** —— 同时给 P1 加议题 1 的 p1_skip_reason 让 P1 escape 不轻易触发。净效果:
  - 平均 effective rounds 从 3-4 提到 4-5(capability ↑)
  - cost 净变化:max budget 从 6×100k=600k → 5×100k=500k(-100k input/run 上限,≈ -$1.5/run);typical 因 effective 提到 4-5 可能持平或微涨
  - **关键收益**:用户期望与实际更对齐("跑 5 轮 = 平均实际跑到接近 5 轮"),不再有"6 轮 ≈ 实际 3-4"的预期落差
- **不采纳的方案**:单独放宽 STALE_ROUNDS=3 而不动 maxRounds → cost 上限直接到 7×100k=700k = $20+,用户嫌贵概率大。

**建议 #15 在 final_report § 改进 P2 实操痛点段加入**,代价小(改 2 个默认值)、ROI 高(预期对齐)。

---

## § 交叉验证修正(Phase 2 · 与 A architect_critic / C cost_critic 互校后)

> 本节是与 A_raw / C_raw 互发 SendMessage 后的最终态收敛,**修正 B_raw 前文中任何与最终立场不一致的点,后续 final_report 以本节为准**。

### 修正 1 · A §D2 forbiddenApproaches 删除提案 — **B 反驳并精化保留**

**A 的主张**:meta-agent 信号源 = reviewer 同源材料(reviews + impl.md + issues),边际信息 ≈ 0,故 P1 三字段砍到只剩 escapeRequest 单字段。

**B 的反论**(已 SendMessage 详回 A):
- **信号源同源 ≠ 综合视角同源**:reviewer 是 lens 切分 + fresh per 轮,只看本轮 + 上 1 轮(historyReviews 在 implementer 端,reviewer 端无 reviews 通道);meta-agent 是 opus 跨 ≤ 3 轮综合。这两者综合范围真不同——**跨 ≥ 3 轮的"tried+failed" 配对识别只有 meta-agent 能做**。
- **A 论据的隐含前提是 reviewer 能跨轮看 reviews**——这只在 B_raw §盲点 A (mergeIssues 补 nextStepPlanHistory 字段) 修复后才部分成立,且仍只支撑"看 plan 主线",不支撑"看 tried+failed 配对证据"。
- **但 A 在「未修 p1_skip_reason」状态下是对的**:P1 当前 30-50% 命中率 × 80%+ 触发 = 期望 24-40% 真有用,边际 ROI 微负;加 #14 p1_skip_reason 后真命中率 50-70%,期望 40-55%,边际 ROI 正向 5-30×。

**最终立场(给 final_report 用)**:**two-track 推荐**(mutually exclusive):
- Track 1(B+C 推荐):**采纳 #14 加 p1_skip_reason** + 保留 forbiddenApproaches + prioritizedMustIds 完整 3 字段
- Track 2(A 推荐):**不加 p1_skip_reason** + 收窄 META_AGENT_SCHEMA 到单 escapeRequest 字段(A §D2 改动 A2)

两条 track 的判别点 = "用户/lead 是否相信 #14 能把 50-70% 真命中率落地"。我倾向 Track 1,但承认 Track 2 在 worst case 也是合理后撤位置。

### 修正 2 · A §H10 implementer 加 schema 强制 reviewer_stuck — **B 反对单加 schema,推荐双轨叠加**

**A 的主张**:给 implementer agent 加 `{reviewer_stuck:boolean, planRepetition:string, ...}` 必填 schema,防 prompt drift 静默失效。

**B 的反论**(已 SendMessage 详回 A):
- **schema 会拉走 implementer attention budget,代码改动质量降 15-25%**(prompt eng 经验值,长 prompt + schema 输出对长尾代码 bug 不利)
- **B_raw §改进 #8 是更优方案**:不动 implementer schema,workflow 加 1 sonnet agent 程序化 parse impl.md 首段 YAML 字段 → 下游 r3 reviewer 直接拿 workflow 变量,跳过 reviewer LLM cat 链路 50-70% 衰减
- B 方案不影响 implementer 本职,只改 workflow 状态机消费侧

**最终立场**:**双轨叠加**(上游 schema + 下游程序化 parse,二者非互斥):
- 主推 B #8(workflow 程序化 parse)作为唯一改动
- 若 lead 仍担心 prompt drift,A H10 schema 加 + B #8 双轨叠加更稳(代价小,backup 兜底)
- 单加 schema(A H10 单 track)不推荐——无 backup,且影响 implementer 代码改动质量

### 修正 3 · A §D4 三段并 1(planDedupBlock + reflectBlock + 强制判断题) — **B 基本同向收敛**

A 主张三段重叠 prompt-side 几 K,reviewer 判断负担过重,应并 1。
B_raw §盲点 F 提的也是"planDedupBlock 50+ 行复杂条件指令简化为 2 条 if-then"。

**最终立场**:基本同向。final_report 改进段可合并表达:
- **改进合并项**:三段中保留 reflectBlock 核心("若上轮 reviewer_stuck=true 且本轮主线相同 → 强制换主线"一条) + 删 planDedupBlock 的"真二选一倾向 / 默认查重收紧"细则 + 强制判断题维持(因为这是 reviewer_stuck 信号源头)
- 改动幅度:moderate

### 修正 4 · A §H1 测试套件全是文本 grep,零运行时验证 — **B 强烈认可,纳入 B 改进表**

A 指出 21 个测试文件全 `assertContains(src, 'forbiddenApproaches')` 模式,只 grep 源码不跑数据流。这与我 B_raw §盲点 A 发现的"测试盲区"完全一致(test-reviewer-prompt.mjs / test-implementer-prompt-priority.mjs / test-stall-criteria.mjs / test-p1-meta-agent.mjs 全是字符串 grep)。

**最终立场**:**纳入 B_raw §改进 P0 第 3 条扩充**:
- 原 B P0 第 3 条仅新增 test-issues-decision-fields.mjs(造 reviewer 输出 + 跑 mergeIssues + 验证字段)
- **扩展为**:把 21 个测试中**至少 5 个核心机制**(mergeIssues / stall 三判据 / P1 触发 / verdict 推导 / 收敛判据)改造成 dry-run 数据流测试。需要把 workflow-template.js 抽 mergeIssues 等纯函数到独立 lib,主模板用 generator 拼装(A §D6 提到此 trade-off,A 自己 N1 标"不动";B 改建议:**仅抽纯函数,主模板仍单文件**,可测试性与单文件调试可同时获得)。
- 改动幅度:moderate-large(1-2 天工作量),但 ROI 极高(消除所有"prompt drift 静默失效"风险)

### 修正 5 · A §H6 resumeFromRunId 跨 session 失去 verified 进度 — **B 直接对齐我的 #9**

A 把 H6 标"硬阻塞而非软警告 · 高置信 · 实操痛点",与 B_raw §盲点 G 完全一致。A 改进 A12 给的方案("起新 run 但注入 verified.json")与 B 改进 #9 ("iterate 顶部 rehydrate")是**同一问题的两种实现**:
- B #9 在 workflow-template.js iterate 顶部 cold-start Read issues.json + verified.json
- A A12 在 args 生成阶段(主会话)注入 already_verified 列表

**最终立场**:**B #9 实现更简洁**(纯 workflow 改动,无需主会话适配),A A12 是 fallback;final_report 用 B #9 写法。

### 修正 6 · A §H2 read-decision-log + p1-diffstat 每轮 sonnet agent — **B 部分采纳**

A 指出两个无条件 sonnet agent / 轮(read-decision-log + p1-diffstat)是 token sink。B_raw §改进 #6 已主张删 gitDiffSmallRounds 通道(顺便删 p1-diffstat agent);B 现追加采纳 A §A7:
- **read-decision-log**:从"每轮 round≥2 一律读" 改为"在 P1 触发判定后才读"(把 decision-log read 内联到 P1 meta-agent agent 的 prompt 而非前置独立 agent),改动小,C 估省 -300-700 token/轮 × 6 轮 = -1.8-4.2k/run + 早期轮净减 5-6 个 agent 调用

**最终立场**:B 改进 #6 + 新追加 A §A7 ⇒ **合并改进项**:删 p1-diffstat 整 agent + read-decision-log 内联到 P1 触发后。

### 修正 7 · A §D1 GOAL 三件套 vs B 无补充 — **接受 A 结论**

A §D1 主张 goal.json 是 cargo doc 删之(reviewer/implementer 都能解析 markdown,goal.md 一份足够)。B focus 是自动改进职责,此设计点不在 B scope。**接受 A 结论**,纳入 final_report。

### 修正 8 · A §D3 5 级优先级模板 vs B §盲点 H — **A 文档侧 + B 物理位置侧叠加**

A 主张 SKILL.md / template 文案上把 P1-P5 改成"权威/参考"两档(文档简化);
B §盲点 H 主张把 humanHint + forbiddenApproaches 升 prompt 物理顶部(实施侧重排)。

**最终立场**:两个改进**叠加**——A 改文档侧表达,B 改 prompt 物理位置 + 强标识符切分;互补不冲突。

### 修正 9 · A §G1-G3 通用性差距 — **B 视角无补充**

A 分析(SKILL.md 自报"通用"但实测覆盖率 = 1 项目 + canvas/probe/ECharts 概念渗透过深)是架构维度独立观察,不在 B focus scope,**接受 A 结论**。

---

### 给 final_report 的三方收敛矩阵(最终态)

| 议题 | A 立场 | B 立场 | C 立场 | 最终收敛 |
|---|---|---|---|---|
| forbiddenApproaches 删除 | 删(D2/A2) | 保留 + #14 p1_skip_reason | ROI 高,采纳 #14 | **two-track**:Track1 加 #14 保留 / Track2 不加则删 |
| reviewer_stuck schema (H10) | 加 schema | 程序化 parse (#8) | 都 0 增量 | **B #8 主推 + A H10 双轨叠加为可选** |
| 三段并 1 (D4) | 并 1 删细则 | 简化 planDedup 留 2 if-then | 0 token | **合并:reflectBlock 核心 + 删 planDedup 细则 + 留强制判断题** |
| 测试 runtime 验证 (H1) | 必修 | 纳入 P0 第 3 条扩充 | 0 token,P0 必修 | **改造 5 核心机制测试为 dry-run + 抽纯函数到 lib** |
| 跨 session resume (H6/G/#9) | A12 args 注入 | #9 iterate 顶部 rehydrate | 0 token,sunk cost 救回 $5-10 | **B #9 实现更简洁,主推** |
| 每轮 sonnet agent (H2) | A7 P1 触发后读 | #6 删 gitDiffSmallRounds | -1.2 到 -7-24k/run | **合并:删 p1-diffstat + read-decision-log 内联** |
| GOAL 三件套 (D1) | 删 goal.json | 不在 B scope | 0 token | **接受 A 结论** |
| 5 级优先级 (D3 / B §盲点 H) | 改"权威/参考"两档 | prompt 重排升 P3 到顶 | 0 token | **A 文档侧 + B 物理位置侧叠加** |
| P1 加 p1_skip_reason (#14) | 不在 A scope | C 提出 + B 采纳 | 0 token,ROI 极高 | **采纳**(配合 Track 1) |
| STALE_ROUNDS 2→3 + maxRounds 6→5 (#15) | 不在 A scope | C 提出 + B 采纳 | -$1.5/run 上限 | **采纳**(预期对齐) |

---

**总结**:B 与 A 的论据冲突仅在 D2(P1 删 vs 留)与 H10(schema vs 程序化 parse)两处真分歧,其余基本同向或互补。final_report § 改进段按上表生成即可。

**B 交叉验证完成。**

---

## § Token 口径声明(lead 紧急澄清后追加)

> **「token / cost / $X/run」= web-loop 每次跑一轮 workflow 真实消耗的 LLM API 费用,运行时复发**。
> **「改动 ~X 行 / 改动幅度 trivial/moderate/large」= 一次性修改 skill 源码的实现工作量,与 token 运行成本独立**。

### B_raw 改进清单口径核查(逐条)

| 改进 # | "代价 / cost" 字段 | 口径核查 |
|---|---|---|
| #1-4 P0 | "改动 ~10/30/80/5 行" + capability 提升 | 口径正确:都是实现工作量 + capability,无 token 成本 claim |
| #5 oscillating | "改动 1 字符" + capability + 净降总 token | 口径正确:实现工作量 + capability + **运行 token 净降 -3-5k input/run** |
| #6 删 gitDiffSmallRounds | "改动 ~10 行删除" + **-1.2k/run**(C 修正为 -7-24k/run) | 口径正确:都标 /run |
| #7 prompt 重排 | "改动 ~30 行重排" + 0 token 增量 | 口径正确 |
| #8 程序化 parse impl.md | "改动 ~20 行新增" + **+1.5-2k sonnet/run** | 口径正确 |
| #9 iterate 顶部 rehydrate | "改动 ~30 行" + 0 token | 口径正确 |
| #10 SKILL.md 红线放宽 | "改动 ~10 行" | 口径正确:纯文档,无 token claim |
| #11 forbiddenList filter | "改动 ~5 行" + 5-10k/run 净降(C 估) | 口径正确 |
| #12 SUMMARY 加 effective rounds | "改动 ~5 行" + 0 token | 口径正确 |
| #13 vision verifier | ⚠ **"代价大、ROI 中。改动 ~150 行"** | **口径混淆 — 拆分** |
| #14 p1_skip_reason | "0 token 增量" | 口径正确:field 几十 char 进 prompt,无 /run 增量 |
| #15 STALE_ROUNDS 2→3+maxRounds 6→5 | "-$1.5/run 上限" | 口径正确:运行成本 |

### 改进 #13 口径修正

原写"代价大、ROI 中。改动 ~150 行" 隐藏两个不同维度:

- **实现工作量**(一次性 skill 源码改动):~150 行 + 单独 skill 拆分,1-2 天工程
- **每 run token 成本**(运行 vision verifier 复发):每 run +1 opus agent(vision verifier 1-2k input + 1.5-2.5k tokens/screenshot × 5 张 × N 轮 + 输出 0.5-1k)≈ **+9-15k input + 0.5-1k output / 轮 × 平均 4-5 轮 ≈ +36-75k input/run + 2-5k output/run**(C 估的口径,与 C_raw 数据对齐)= **~$0.6-1.2/run 增量**

→ final_report 应拆开表达:**实现工作量 ~150 行(一次性) + 每 run +$0.6-1.2(运行复发)**

---

## § Phase 2 终态修正(A 全盘承认盲点 A + 合并叙述升级)

A 在最终轮 SendMessage 中**全盘承认盲点 A**(漏抓),并把 A §H10 (implementer schema 强制) 与 B §盲点 E (workflow 程序化 parse) **升级为合并叙述**。两条之前列为"真分歧"的议题,A 主动让步后变成"同一改法的两面",我接受并合并。

### 终态修正 1 · A 承认盲点 A 是 P0 硬伤 → B 漏列 A_raw 的 P0 改进合并

A 原话:"L107 push 新 issue 时只复制 8 字段...4 个决策字段在 mergeIssues 这层全部丢弃。planDedupBlock L121 对 reviewer 说'issuesJson 里能看到本轮每条 must 已有的历史 nextStepPlan 字段'是**虚承诺**——这字段在 issues 数组里根本不存在。这是 P0 硬伤,我 A_raw.md 漏列。"

A 也确认 H1(测试零 runtime) + 盲点 A 是**同源根因**:`assertContains(src, 'nextStepPlan')` 在 reviewerPrompt 段 + REVIEWER_SCHEMA 段 grep 都通过,但 mergeIssues 段不在 grep 范围 → "无 runtime 数据流转测试 = 字段穿透链路无 gate"。

### 终态修正 2 · 修正 2(H10 vs #8)从"双轨叠加为可选"升级为"合并叙述 P0 改进"

A 在 Q3 回应中主动让步,认可:
- 我 §盲点 E "workflow 程序化提取"(机制)= A §A6 / H10 "implementer schema 强制"(契约)= **同一改法的两面**
- 合并叙述:**implementer agent 加 schema 必填 `{reviewer_stuck:boolean, planRepetition:string}` → workflow 直接从 schema 字段塞下轮 reviewer prompt → 替代当前"reviewer bash cat impl.md 首段 grep 关键字"的脆弱通道**

**B 接受**:之前我反对单加 schema 的理由(attention budget 拉走代码改动质量)在 A 的合并方案下被消解——schema 字段是 implementer 元判断 self-report,不影响代码改动主线;workflow 程序化读 schema 比读 markdown 首段更可靠。**这是上游 + 下游同时改的双重保险**,比我原先单走 #8 更稳。

### 终态修正 3 · A 答 Q2(双源真理禁令)= 不是滑坡是必要

A 论证:双源真理一旦允许,issue.status 转移有竞态,mustStaleStreak / 收敛判据全不可信;reviewer 跨轮自校准代价通过 "绝对标准原则" 降低,真要校准走 escapeRequest 而非允许跨轮自修。**B 接受**——这条不变。B_raw 原先就没主张破双源真理,只是想问架构动机,A 给了清晰答案。

### 终态修正 4 · A 答 Q1(reviewer 跨轮记忆通道)= 修盲点 A 后 issuesJson 成主通道

A 盘点 reviewer 4 个跨轮信号通道,确认:
- (a) verifiedJson — 全聚合 ✓
- (b) issuesJson — **盲点 A 修后 4 决策字段持久化,变 reviewer 跨轮记忆主通道**
- (c) reflectBlock — implementer 中转,辅
- (d) planDedupBlock — 依赖 (b),修盲点 A 后才活

**架构上 reviewer 历史 reviews 砍到 N-1 only** 是有意设计(防 token 爆 + 防 reviewer 同源锚定),前提是 issuesJson 字段持久化能用。**盲点 A 不修 = 整套主-辅设计白瞎**——这进一步坐实盲点 A P0 必修级别。

### 终态修正 5 · final_report top-1 actionable(A 请求 B 合并写)

把以下 3 条合并为 final_report 第 1 条 P0 改进(优先级最高):

**P0-1 合并改进 · 修盲点 A + 升级 reviewer_stuck 信号通道**:
- **(i) 数据持久化**:workflow-template.js:107 mergeIssues 补 4 决策字段(rootCauseHypothesis / affectedFiles / suggestedFix / nextStepPlan + nextStepPlanHistory append)
  - 改动幅度:trivial(~10 行)
  - 每 run 运行成本:+5-15k input/run(C 估,issuesJson 自然膨胀;但救活 planDedupBlock + reviewer 跨轮主通道,杠杆 5-30×,净降总轮数 → 总成本反降)
- **(ii) 契约强约束**:implementer agent(workflow-template.js:332)加 schema 必填 `{reviewer_stuck:boolean, planRepetition:string, mdSnippet:string}` + impl.md 双写
  - 改动幅度:moderate(schema 定义 + impl.md 输出格式)
  - 每 run 运行成本:+0(opus 输出含 schema 字段不额外计费)
- **(iii) 程序化消费**:workflow 直接从 implementer schema 字段塞下轮 reviewer prompt 顶部 `REVIEWER_STUCK_FROM_LAST_ROUND=...`,替代当前 reviewer bash cat impl.md 首段 grep 关键字
  - 改动幅度:moderate(~20 行 reviewer prompt 重排 + 删 reflectBlock cat 指令)
  - 每 run 运行成本:0(原 reflectBlock cat 也产生 sonnet/opus 调用,新方案净不变)

合并预期提升:
- planDedupBlock 从 dead code → live(reviewer 跨轮主通道)
- reviewer_stuck 信号链路成功率 50-70% → 90%+
- 测试盲区暴露(为 P0 第 2 条 H1 改造测试为 dry-run 数据流转铺垫)

**P0-1 是本次 audit 最高 ROI 改动,A 主动请求合并叙述并 acknowledge 漏抓 + 把功劳归 B**。

### 终态收敛矩阵(覆盖之前的)

| 议题 | 之前矩阵立场 | 终态(A 让步后) |
|---|---|---|
| 盲点 A 字段持久化 | B 主张 P0 必修,A 未列 | **A 全盘承认,B 漏列 → P0-1 合并改进** |
| reviewer_stuck schema vs 程序化 parse | 双轨叠加为可选 | **合并为 P0-1 (ii)+(iii)**,A schema + B 程序化是同一改法两面 |
| forbiddenApproaches 删 vs 留 | two-track | 仍 two-track,无新信号 |
| 三段并 1 (D4) | 合并改进 | 不变 |
| 测试 runtime 验证 (H1) | P0 必修 | 与盲点 A 同源根因,**绑定 P0-1 一起改** |
| 跨 session resume | B #9 主推 | 不变 |
| 每轮 sonnet agent (H2) | 合并改进 | 不变 |
| GOAL 三件套 (D1) | 接受 A 结论 | 不变 |
| 5 级优先级 (D3 / 盲点 H) | A 文档 + B 物理位置叠加 | 不变 |

---

**B Phase 2 终态完成**。final_report 框架已就位:
- P0-1 合并改进(盲点 A + schema + 程序化 parse 三合一,A 主动请求合并叙述)
- P0 其余(测试 dry-run / oscillating 阈值 / requiredStates 收紧)
- P1 高 ROI 6 条(#5-#8 + #14 + #15)
- P2 实操 + 信号通量 4 条(#9-#12)
- two-track 决策点 1 处(forbiddenApproaches 删 vs 留)
- P3 候选 1 条(vision verifier,已分拆口径)


### A_raw 改动幅度词与 token 口径相互独立(给 A 的口径备忘)

A_raw §改进 A1-A12 用 "trivial / moderate / moderate-large" 标改动幅度——这是**实现工作量**维度,与本节 token 运行成本维度独立。两者在 final_report 中**应分两栏并列**(改动幅度 + 每 run 运行成本),不混入同一字段。

例:A §A2(META_AGENT_SCHEMA 收窄)= **改动 moderate**(实现工作量) + **运行 -5-20k input/run × opus + 省 1 read-decision-log sonnet agent / 轮**(token 运行)→ 两维都要在 final_report 给数。
