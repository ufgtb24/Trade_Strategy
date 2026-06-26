# web-loop 全面审核 · Final Report

**日期**:2026-06-22
**作者**:agent team(lead = 主会话;teammate A · architect_critic / B · autoimprove_critic / C · cost_critic,全 opus)
**审计对象**:`.claude/skills/web-loop/`(SKILL.md + workflow-template.js + principles.md + examples/path2.md + tests/)
**中间产物**:`A_raw.md` / `B_raw.md` / `C_raw.md`(本目录),Phase 2 三方 SendMessage 交叉验证 + 末尾「§ 交叉验证修正」段
**口径声明**:本报告中 "token / cost / $X/run" 一律指**运行 workflow 一次的成本**(不是修改 skill 文件本身的工作量);"改动幅度 trivial/moderate/large" 指**一次性实现工作量**,与运行 token 是独立两维

---

## 0 · Executive Summary(给用户读)

### 用户核心问题答案

| 问题 | 答案 |
|---|---|
| 还有哪些**硬伤** | 2 条 P0(必修)+ 5 条 P1(强烈建议)+ 若干 P2/P3 |
| 还有哪些**设计不合理** | 8 条主要(D1-D8),核心 = GOAL 三件套有冗余 / P1 meta-agent 字段重叠 / 5 级 prompt 优先级过度形式化 / 反 dedupe 信号三处重复 |
| 是否能承担**自动改进** | **当前 ~50%**(可观察 UX bug / 单点 console error / GOAL 明确 + states 完整);**修盲点 + P0/P1 后 ~70-80%**;剩 15-20% 必依赖人(GOAL 拆错 / canvas 不可取证 / 多 must 真冲突 / ref vs GOAL 自相矛盾) |
| **token 成本** | baseline **单 run $10-18**(maxRounds=6 跑满,opus 占 60-95%);全采纳改进后 **$7-15**(省 17-22%);**SKILL.md L207 自报"opus 30-80K"系统性低估 6-10×**(只算 implementer,未算 reviewer × 3 lens × 6 轮) |

### Top-3 必读发现

**T1 · Task 2(commit 137874f)实际产生 dead code**(本次 audit 直接副产物)
- `planDedupBlock` 文案让 reviewer 读 "issuesJson 中本轮每条 must 已有的历史 nextStepPlan 字段";但 `mergeIssues`(`workflow-template.js:107`)新建 issue 时只保留 `id/lens/title/severity/unverifiable/status/bornRound/lastSeenRound` — `REVIEWER_SCHEMA`(L189-L194)输出的 4 决策字段 `rootCauseHypothesis/affectedFiles/suggestedFix/nextStepPlan` **全部被丢弃**
- 后果:planDedupBlock 的核心机制(对比历史 plan 主线判同主线)在数据流上**断点**;reviewer 永远看到"历史 nextStepPlan = undefined",自检退化为"我自己想的"
- A、B 各自独立确证(B 先抓,A 重读 schema + mergeIssues 复证),lead 实测 grep + Read 确认
- **修法**:`mergeIssues` 新建 issue 时把 4 决策字段(+ round 时间戳)一并保存为 `nextStepPlanHistory: [{round, rootCauseHypothesis, affectedFiles, suggestedFix, nextStepPlan}]` 跨轮累积数组

**T2 · 测试套件全是文本 grep,无 runtime 数据流测试**(`tests/` 目录 21 个文件几乎全 `cat ... | grep`)
- T1 的硬伤直接根因 — 现有测试只验"workflow-template.js 字符串里有这段文本",不验"运行时 nextStepPlan 真的从 reviewer 端流到下一轮 reviewer 端"
- 类似 latent 数据流 bug 几乎必然还有 — audit 时间限制下未全面排查
- 修法见 P0-1 后续(`test-mergeissues-fieldflow.mjs` 跑真 mergeIssues 函数验持久化)

**T3 · 自动改进能力 50%(当前) ≠ 70-80%(修 P0+P1 后)**
- 50% 当前 = 修 T1 之前的实然(planDedupBlock 死代码 + reviewer_stuck 链路靠 prompt 自觉)
- 70-80% 修 P0/P1 后 = T1 fix + reviewer_stuck schema 化 + P1 meta-agent 字段收窄
- 剩 15-20% 必依赖人 = 架构层硬阻塞(非技术能解):GOAL 拆错 / canvas 不可取证 / 多 must 真冲突 / ref-vs-GOAL 自相矛盾

### 改进 ROI 概览

| 优先级 | 条数 | 净 token 影响 | Capability 提升 | 建议 |
|---|---|---|---|---|
| **P0**(必修) | 2 | -10 ~ -30k input/run | 50% → 60-65% | 立即修 |
| **P1**(强烈) | 5 | -30 ~ -90k input/run | +10-15% | 同 PR 跟随 |
| **P2**(应做) | 3 | -50 ~ -90k input/run | +0-3% | 优化 |
| **P3**(可选) | 3 | 微 / 中性 | 文档健康度 | 闲时做 |
| **B#13 vision verifier** | 1 | **+$1-2/run** | 失败率不详 | **建议放弃** |

---

## 1 · P0 硬伤(必修)

### Disambiguation 准则(决策时同时看两维)

A CV-6 给的两维 disambiguation 准则(本节所有 P0/P1/P2 用此评级):

| 改动幅度 × 运行 ROI | 评级 |
|---|---|
| trivial 一次性 + 高运行 ROI | **最佳**,优先做(如 P0-2) |
| moderate 一次性 + 持续运行降本 | 次优(如 P2-1 multi-lens) |
| trivial 一次性 + 运行 ROI 中性 | 健壮度修补(如 P2-3 paused append-only) |
| moderate 一次性 + 运行 ROI 中性但**闭环正确性必修** | **优先级高于 ROI**,不省钱也必做(如 P0-1) |

### P0-1 · mergeIssues 字段穿透断点(三件套合并 fix · B+A 终态共识)

**Severity**:Critical(我刚 commit 的 Task 2 实际 dead code · 三方共识 P0-top1)

**评级**:moderate 一次性 + 运行 ROI 微正(+5-15k input)但**闭环正确性必修** — 不省钱也必做

本条是 B 终态请求的"三件套合并"P0-1(B + A 全盘共识)。三件套同步修才完整 — 任一缺都 planDedupBlock / reviewer_stuck 链路仍断:

#### (i) mergeIssues 补 4 决策字段 + nextStepPlanHistory

**Location**:`workflow-template.js:107`(新建 issue 处);同步 `workflow-template.js:102-104`(matchesIssueId 路径,status 变更时也要 append)
**Root cause**:reviewer 出的 4 决策字段(`rootCauseHypothesis`/`affectedFiles`/`suggestedFix`/`nextStepPlan`,REVIEWER_SCHEMA L189-L194)在 mergeIssues 新建 issue 时**未持久化进 issues**;每轮 issuesJson 内插 reviewer prompt 时只带 `id/lens/title/severity/...` 八字段。planDedupBlock 文案"对照历史 nextStepPlan 字段"永远看到 undefined。

```js
// workflow-template.js:107 修改 issues.push(...)
if(!dup) issues.push({
  id: nextId(v.lens, round),
  lens: v.lens,
  title: it.title,
  severity: it.severity,
  unverifiable: it.unverifiable === true,
  status: "open",
  bornRound: round,
  lastSeenRound: round,
  // ★ 新增:跨轮决策字段历史(供 planDedupBlock 自检)
  nextStepPlanHistory: [{
    round,
    rootCauseHypothesis: it.rootCauseHypothesis || null,
    affectedFiles: it.affectedFiles || [],
    suggestedFix: it.suggestedFix || null,
    nextStepPlan: it.nextStepPlan || null
  }]
});
// 同 status 变更路径(L102-104)在 regressed 时也 append 一条新 round 的 nextStepPlanHistory
```

- 改动幅度:**moderate**(~30 行)
- 运行 token Δ/run:**+5 ~ +15k input/run**(C 实测 vs B 初估 "0 增量")

#### (ii) implementer schema 必填 `reviewer_stuck` 三字段

**Location**:implementer agent 的 output schema(grep "implementer" schema 定位)
**Root cause**:当前 reviewer_stuck 信号靠 prompt 提示 implementer 在 impl.md 首段标 — LLM 半数概率漏标 / 措辞不一致 / reviewer 端 bash cat 解析脆。

```js
// implementer 输出 schema 新增必填字段
{
  reviewer_stuck: { type: "boolean" },         // 是否判定上轮 reviewer plan 与 plan_<N-2> 同主线且无效
  planRepetition: { type: "string" },          // 同主线时的具体证据(diff 行 / console / 截图特征)
  mdSnippet: { type: "string" }                // 标到 impl.md 首段的精确文本(用于反向 audit)
}
```
- 改动幅度:**moderate**(schema + implementer prompt 同步)
- 运行 token Δ/run:**+0**(schema 字段不增加输出长度,只约束结构)

#### (iii) workflow 程序化读 schema 字段塞下轮 reviewer prompt 顶部

**Location**:`reviewerPrompt` 函数体内的 reflectBlock(`workflow-template.js:120`)
**Root cause**:当前 reflectBlock 让 reviewer `bash: cat ${WORKDIR}/rounds/${round - 1}/impl.md | head -40` 读 impl.md 首段;但 reviewer **不应直读 implementer 文件**,且 bash parse 脆(措辞 / 缩进 / markdown 变动均破)。

**修法**:workflow 主线在 iterate r{N} 顶端 read implementer schema 的 `reviewer_stuck` 三字段 → 程序化拼成纯字符串 → 内插 reviewer prompt(替代 reflectBlock 的 bash cat 指令)。
- 改动幅度:**moderate**(~20 行 + reflectBlock 重写)
- 运行 token Δ/run:**~0 net**(替换式,非新增)

#### 三件套联动 Capability 提升

- planDedupBlock 从 dead code → 真自检(读到真实 nextStepPlanHistory)
- reviewer_stuck 信号链路 50-70% → 90%+(schema 化 + 程序化解析,不再靠 LLM 自觉)
- 不破 reviewer 红线:数据源 implementer schema(下游可观察信号),非 reviewer 自己读历史 reviews

**Test gate**(必加,与 T2 同源根因修法):
- `tests/test-mergeissues-fieldflow.mjs` 实跑 `mergeIssues` 验 4 字段持久化(input → output → next round 内插)
- `tests/test-implementer-schema-reviewerstuck.mjs` 实跑 implementer schema 验 reviewer_stuck 字段强制
- `tests/test-reviewerprompt-stuck-injection.mjs` 实跑 reviewerPrompt 验 reviewer_stuck 经程序化注入

### P0-2 · reviewer issuesJson 按 status filter(架构合规 + cost,F9 升级)

**Severity**:Critical(架构合规 + cost 双重)
**架构合规**:`principles.md §9`(反锚定 + 正面结论走 verified 通道)红线:"issues 只承载缺陷;已修复/验证通过/全绿等正面结论一律放 verified 数组" — reviewer prompt 把 `fixed/closed` 状态 issue 留在 issuesJson **违反此红线**(让 reviewer 把已修复 issue 当还在 open 来 anchor)。修法既净降 token 也修架构违规。
**Cost**:每轮 reviewer 重复 read 已 fixed/closed issues 是 token 大头之一。

**Location**:`workflow-template.js` 中 reviewerPrompt 函数体内插 `issuesJson` 处(L113-L170 区间,具体行号 grep "issuesJson" 定位)

**Root cause**:`issuesJson` 把所有 status 的 issue 都内插进 reviewer prompt;reviewer 只关心 `open/regressed`(决策依据),`fixed/closed` 是噪声。

**修法**:
```js
// reviewer prompt 内插前过滤
const activeIssues = issues.filter(i => i.status === "open" || i.status === "regressed");
const issuesJson = JSON.stringify(activeIssues);
```
- 改动幅度:**trivial**(2-3 行)
- 运行 token Δ/run:**-15 ~ -30k input/run**(随历史轮数累积放大)
- Capability 含义:零损失(reviewer 本就不该重审 closed issue)

---

## 2 · P1 改进(强烈建议跟随 P0 同 PR)

### P1-1 · 删 META_AGENT_SCHEMA 的 forbiddenApproaches + prioritizedMustIds,保留 escapeRequest;P1 meta-agent 改为"escapeRequest-only with p1_skip_reason"

**A vs B 关键分歧 → lead 综合裁定**:

| 视角 | A 主张 | B 主张 | C 数据 |
|---|---|---|---|
| forbiddenApproaches | 信号源同 reviewer(opus 重审 reviewer 输出),边际信息≈0,删 | 加 p1_skip_reason 第 4 字段剔除"被迫填充"case,真命中率 30-50% → 50-70% | 路径 1(B 修补)残余 -$0.05-0.3/run;路径 2(A 删)节省 -$0.25-1.1/run |
| prioritizedMustIds | 仅排序无新决策,删 | 同上(可加 p1_skip_reason) | 同上 |
| escapeRequest | **保留**(唯一独立信号源,人介入触发器) | 保留 | 共识 |

**lead 综合**:**取路径 1**(B 的 #14 p1_skip_reason 补丁)— 理由:
- A 的"信号源同 reviewer"论据**部分对**(meta-agent 输入确实重叠 reviewer 输出),但 reviewer 是 lens 切分且每轮 fresh、meta-agent 是跨轮整合(还多 read decision_log.json + git log + impl.md 反根因段),仍有独立信号
- B 的 #14 用 30 token schema 字段把"未触发的 case 显式标 N/A"→ implementer 不再被迫读空 forbiddenApproaches 段,节省的不是 P1 输出 token、是下轮 implementer 的 prompt 噪声
- C 估算:cost 差额(路径 1 vs 路径 2)= -$0.2 ~ -$0.8/run,小于 capability 不确定性(15-35% case stalled 救场)的潜在损失

**修法**:META_AGENT_SCHEMA 加 `p1_skip_reason: {type:["string","null"], enum:["no-stall","reviewer-already-clear","forbidden-not-applicable",null]}`。当 forbiddenApproaches 为空时强制填非空 reason(非 null)— LLM 不再为了填字段而硬造伪 forbidden。
- 改动幅度:**trivial**(单 schema 字段 + 一行 prompt 提示)
- 运行 token Δ/run:**+0.5 ~ +1.5k**(每轮 P1 加 30 token);下游 implementer prompt 节省 1-3k(forbiddenApproaches 显式 N/A 不再附冗余空段说明) → **净 0 ~ -2k/run**

**保留双源真理禁令(B Q2 + A 复证)**:reviewer issues 是真相,meta-agent 不修不复判;若产生 reviewer 不同意见走 `escapeRequest.type=reviewer_disagreement` 退出。这条不动。

### P1-2 · read-decision-log + p1-diffstat 两个 sonnet agent 合并 short-circuit

**Location**:`workflow-template.js` 中每轮 iterate 末尾两个 sonnet agent 调用(grep "read-decision-log" + "p1-diffstat" 定位)

**Root cause**:无条件每轮各起一个 agent;`read-decision-log` 在 round=1 时 decision_log.json 为空、`p1-diffstat` 在前几轮 diff 必然不小 — 都是无效调用。

**修法**:合并为单 sonnet agent + round>=2 短路;round=1 跳过整段。
- 改动幅度:**moderate**(~15 行)
- 运行 token Δ/run:**-2.5 ~ -6k/run**(每轮砍 2 个 agent 调用 → 6 轮 = 12 → 6)

### P1-3 · 删 goal.json(GOAL 三件套 → 1.5 件套)

**A §D1**:goal.json 是 cargo doc — goal.md 单文件 + in-memory subgoals 即可;goal.json 内容 100% 派生自 goal.md / refImages,reviewer 实际 Read goal.md 不读 goal.json。

**修法**:setup 阶段删 goal.json 写入逻辑;reviewer prompt 不再引用 goal.json;goalSubgoalsSummary 仍从 args.goalSubgoals 内插。
- 改动幅度:**trivial**(2 处删除)
- 运行 token Δ/run:**~0**(reviewer 不读 goal.json,本来就无运行成本影响 — 净化的是 setup 一次性 write + 文档复杂度)
- Capability 含义:0 退化;一次性减一份 disk artifact + SKILL §2c 一节文档

### P1-4 · 5 级 prompt 优先级 P1-P5 → 2 档"权威 / 参考"

**A §D3**:5 级层级是设计者的认知模型,opus 不按层级强弱听话;真正区分 = "必须遵循" vs "参考补充"。

**修法**:
- 原 P1(用户人工指令)→ "权威 · 必须遵循"
- 原 P2(must)→ "权威 · 必须遵循"
- 原 P3(forbiddenApproaches)→ "权威 · 必须规避"
- 原 P4(历史 reviews)→ "参考补充"
- 原 P5(历史 impl.md)→ "参考补充"
- 改动幅度:**moderate**(~40 行 prompt 文本调整 + 注释 sync)
- 运行 token Δ/run:**-1 ~ -3k**(收紧每段抬头说明)

### P1-6 · escapeRequest enum 加第 5 类 `capture_layer_bug`(A CV-16 补缺)

**Location**:
- `workflow-template.js` 中 META_AGENT_SCHEMA.escapeRequest.type.enum(grep `"missing_state"` 定位)
- `SKILL.md` L186-L194 "escapeRequest 4 类语义" 段

**Root cause**:STATES 配置对、但 capture agent 连续 N 轮失败(playwright/MCP/sandbox 路径问题)无独立 escapeRequest 通道;`workflow-template.js:384` 用 `issues.push({id:'shot-${rtag}',...})` 兜底但不走 paused.md 退出。

**与 `missing_state` 的区分**(必须分开,不可合并):
- `missing_state` = STATES list 配错 → 人介入 = 改 args 补 STATES → 起新 run
- `capture_layer_bug` = playwright/MCP/sandbox 路径问题 → 人介入 = 调浏览器 debug → 修后续跑

**修法**:
```js
// META_AGENT_SCHEMA.escapeRequest.type
enum: ["missing_state", "rubric_too_strict", "goal_unrealistic", "reviewer_disagreement", "capture_layer_bug"]
```
+ SKILL.md 5 类语义段同步;P1 meta-agent prompt 加触发指引(连续 ≥2 轮 capture issue 同 id 时触发 capture_layer_bug)

- 改动幅度:**trivial**(schema 一字 + SKILL 一节)
- 运行 token Δ/run:**~0**(enum 项)
- Capability 含义:capture 层 bug 不再淹没在 must 队列里,跳到 paused 让用户专项 debug

**B 同时反对**:`reviewer_lens_disagreement` 不应加细 — 已隐含在 `reviewer_disagreement.detail` 字段,无新区分

### P1-5 · planDedupBlock + reflectBlock + 强制判断题三段并 1 段

**A §D4**:三段都在防"同 plan 主线反复"死循环 — 但写在 reviewer prompt 三处独立位置,导致 reviewer 读 3 次重复指引。

**修法**:统一为单一"plan-dedup-and-stuck-detection"段,内嵌 reflectBlock(impl.md reviewer_stuck) + planDedupBlock(自检主线相同) + 临界规则(强制换主线) + 真二选一倾向。
- 前置依赖:**P0-1 必先修**(否则 planDedupBlock 仍引用 undefined 字段)
- 改动幅度:**moderate**(~50 行 reviewerPrompt 重构)
- 运行 token Δ/run:**-3 ~ -6k**(去重)

---

## 3 · P2 优化(应做,可单独 PR)

### P2-1 · reviewer × 3 lens → × 1 multi-lens

**A CV-3 核心 1**:reviewer 三 lens(ux/func/code)各起 opus agent → 同 manifest read 3 次 + prompt 静态段重复 3 份;改 × 1 multi-lens 单 agent 输出三 lens verdict。
- 运行 token Δ/run:**-50 ~ -90k input/run**(input 大头)
- 墙钟:**+2x**(串行三 lens,opus 单 agent 总输出更长)
- **trade-off 由用户拍**:省钱 vs 等更久
- 改动幅度:**moderate**(REVIEWER_SCHEMA 加 lens-array,mergeIssues 兼容,prompt 重写)

### P2-2 · SKILL.md canvas/ECharts/probe 段下放 examples/path2.md

**A §G1**:SKILL.md §2b 把 canvas/probe/getDisplayList 等 ECharts-specific 内容当作 first-class 通用指引 — 新项目接入会被噪声困扰。
- 改动幅度:**trivial**(文档迁移)
- 运行 token Δ/run:0(文档,不进 prompt)
- Capability 含义:通用性宣称更诚实

### P2-3 · paused.md 不覆写、改 append-only 历史轨迹

**A § N4 反建议** ❌ → 改:A 原本想保留覆写、B 指出每次 paused.md 覆写丢历史
- 修法:`paused.md` 改 `paused.history.md`(append-only,每次 stall 加段),旧 paused.md 命名 `paused.latest.md`
- 改动幅度:**trivial**
- 运行 token Δ/run:0

---

## 4 · P3 可选

### P3-1 · setup 清理实施缺失(SKILL.md §运维确认 ➜ workflow-template.js 缺对应代码)
SKILL 写"删旧 runtag 的 shots/、删 .playwright-mcp/",workflow-template.js setup 段实际只写了 ensure mkdir,未删旧。建议 setup 顶部加 cleanup 步骤。

### P3-2 · resumeFromRunId 跨 session 失效兜底
A §H6:主会话起新 run 时检测 paused.md + verified.json,可注入新 run 的 setup,减少跨 session 重做。改动幅度 large,token 影响中性。

### P3-3 · maxRounds 6→5 + staleRounds 2→3
B #15:既然 80%+ run 在 r2 触发 P1,maxRounds=5 已足;staleRounds=3 让 P1 触发对齐 stall 1 轮前。
- 运行 token Δ/run:**-$1.5/run 上限**(maxRounds 砍 1 轮)
- 改动幅度:trivial
- 但有 capability 风险:多 must 复杂 case 可能 r5 后才收 — 建议作为默认 + 用户可 override

---

## 5 · 建议放弃

### B#13 vision verifier(额外 opus agent 用于复核截图)

- B 自评 "代价大 ROI 中,失败率无具体数据"
- C 实测:+1 个 opus agent / 轮 × 6 轮 = **+$1-2/run**(几乎单 run cost 翻倍)
- 无证据支持失败率改善达到 15%+
- **结论**:不实施,改 P3-future(收集 6 个月 run 的假报频次再评估)

---

## 6 · 自动改进职责评估(用户核心问题)

### 当前 ~50% 自动覆盖

可承担:
- 单点可观察 UX bug(布局崩 / 元素遮挡)
- 单点 console error 修复
- GOAL 明确 + states 完整 + refImages 提供的视觉对照任务
- 单 lens single must 反复迭代

不能承担(skill 当前的硬阻塞):
- planDedupBlock 链路断点(T1)→ 跨轮 plan 同主线无信号 → 反复修同处 stalled
- reviewer_stuck schema 化缺失(B 盲点 D)→ 信号靠 prompt 自觉 → reviewer 半数概率漏读
- META_AGENT_SCHEMA forbiddenApproaches "被迫填充"假信号(B #14)→ implementer 规避无效内容

### 修 P0+P1 后 ~70-80%

新覆盖:
- planDedupBlock 真自检 → 跨轮 plan 同主线时强制换主线
- reviewer_stuck schema 化 → 跨轮信号 100% 不漏
- p1_skip_reason → forbiddenApproaches 真信号占比 50-70%

### 剩 15-20% 必依赖人(架构层硬阻塞,非技术能解)

- **GOAL 拆错**:用户自然语言模糊 → §2b 自然语言诊断拆出错 subgoals → 整 run 走偏(skill 无法自检 GOAL 自身)
- **canvas 不可取证**:probe 漏配 / e2e hook 不存在 → reviewer 看不到关键交互,但跑 N 轮也凑不出截图证据
- **多 must 真冲突**:GOAL 内嵌矛盾(如"K线占 60% 高 + 侧栏 320px 宽 + 1024px 屏" → 数学不可同时满足)→ 修一个 must 必引入另一个
- **ref-vs-GOAL 自相矛盾**:用户口语 GOAL 与贴的 ref 图实际相悖 → reviewer 在两边 oscillate

这 15-20% 的人介入门槛:写 `human-hint-r{N+1}.md` 一段自然语言根因 → resumeFromRunId 续跑(同 session)。跨 session 失效是 P3-2 兜底点。

### 一个未被三人共识但 lead 觉得值得 flag 的事

**implementer = opus 例外条款的成本论据(SKILL.md L207)实测反向**:
- SKILL 说"opus 命中率提升 → 总轮数 5-6 降到 3-4 → 总 token 净降"
- C 实测:opus implementer 比 sonnet implementer 净增 $1.1-3.6/run
- B 数据"80%+ run r2 触发 P1" = opus 并没在 r1→r2 一轮内救场
- 这与 SKILL 写的"opus 强项 = 逆向 + 多约束权衡 + 翻译 plan 到 Edit"判断不冲突,但**乐观推论"总 token 净降"未实证**
- 建议 final_report 之后单独评估:opus implementer 真值得吗?or 改 sonnet + opus reviewer 是否更优?(本次 audit 未答此问)

---

## 7 · Token 成本详表

### Baseline(改进前,maxRounds=6 跑满)

| 阶段 | 模型 | 调用数 | input tokens(估) | output tokens(估) | 备注 |
|---|---|---|---|---|---|
| setup | sonnet | 4-5 | 8-15k | 2-5k | 一次性 |
| capture / smoke / refresh / persist | sonnet | 5-7 / 轮 × 6 = 30-42 | 70-130k | 15-30k | 截图 multimodal 中度 |
| reviewer × 3 lens | opus | 3 / 轮 × 6 = 18 | **220-380k** | 30-55k | **dominant**,55-75% input |
| implementer | opus | 1 / 轮 × 6 = 6 | 70-120k | **25-50k** | output 大头 |
| P1 meta-agent | opus | 0-6(随触发) | 8-30k | 2-8k | typical 触发 2-3 次 |
| finalize | opus | 1 | 20-35k | 5-12k | 一次性,单次最贵 |
| **TOTAL** | | | **400-650k** | **70-130k** | **$10-18/run** |

### 改进后(全采纳 P0+P1)

| 改进 | Δ input/run | Δ output/run | Δ cost/run |
|---|---|---|---|
| P0-1 mergeIssues 补字段 | +5-15k | +0-2k | +$0.07-0.22 |
| P0-2 issuesJson status filter | -15-30k | 0 | -$0.22-0.45 |
| P1-1 META_AGENT_SCHEMA 加 p1_skip_reason | +0.5-1.5k(P1)/-1-3k(下游) | 0 | -$0.0 ~ -$0.04 |
| P1-2 合并 read-decision-log + p1-diffstat | -2.5-6k | -0.5-1k | -$0.05-0.12 |
| P1-3 删 goal.json | 0 | 0 | 0 |
| P1-4 5 级 → 2 档 | -1-3k | 0 | -$0.01-0.05 |
| P1-5 三段并 1 段 | -3-6k | 0 | -$0.05-0.09 |
| P2-1 reviewer × 3 → × 1 multi-lens | **-50-90k** | -5-10k | **-$0.75-1.5** |
| P2-3 paused.md append-only | 0 | 0 | 0 |
| P3-3 maxRounds 6→5 + staleRounds 2→3 | -50-100k(整轮) | -10-20k | -$1-2 |
| **NET(不含 P2-1 / P3-3)** | -30-90k | | **-$0.4-0.8** |
| **NET(含全部)** | -130-250k | | **-$2.15-4.3** → baseline → **$7-15** |

### Top 3 Token Sinks(改进前)

1. **reviewer × 3 lens × 6 轮 opus**(55-75% input)
2. **implementer × 6 轮 opus**(25-40% output;每轮 prompt 历史累积)
3. **finalize 单次 opus**(单次最贵,但 1 次)

---

## 8 · 已知盲点与诚实陈述

### 三方共同盲点
- 无 LLM 实测 telemetry(token 估算靠 prompt 字符数 × 模型常数,非真账单)
- Anthropic prompt cache 行为未知(opus 并行调用是否共享 prefix?reviewer × 3 lens 是否 cache 命中?)
- multimodal 截图计费规则按典型估,实际可能浮动 1.5-2×

### A 独立盲点
- 通用性宣称 vs 实测差距只能据 SKILL.md 内容 + path2 唯一实例判断,无其他真项目对照
- canvas/stateDumps 第二证据通道是否仍最优 — 未实测对比"reviewer 开浏览器"的真实串台风险

### B 独立盲点
- 自动改进覆盖率 50/70/80 是基于 SKILL.md 描述 + 单一 path2 实跑推论,非统计数据
- "必依赖人 15-20%" 估算的上界(实际可能 25-30%)

### C 独立盲点
- opus 与 sonnet 实际 pricing 比可能浮动(每月可能不同)
- opus implementer 比 sonnet 实测净增的真实区间需要 A/B test

### Lead 盲点
- 本 audit 在 2026-06-22(单日)完成,无时间真跑 1-2 个真实 web 项目验通用性
- "Task 2 dead code" 已实测 grep + Read 代码确证,但**未实跑 1 个完整 web-loop run 看 reviewer 真的拿到 undefined 文本**(代码逻辑足够确定不需此步,但严格说仍是 inference)

---

## 9 · 决策项(等用户拍板)

| # | 议题 | 推荐 | 替代 |
|---|---|---|---|
| **0** | **F25 prompt cache 实测前置**(C 提出,决定其他优先级排序)| **立即派 1 sonnet agent 跑 dry-run 抽 telemetry**(cache_creation_input_tokens vs cache_read_input_tokens)— 若 cache 已生效,GOAL 三件套去冗余收益近 0;若未生效,要加"prompt 模板前 X token 冻结"红线 | 不测,接受全 baseline 估算的 ±2× 不确定性 |
| 1 | P0-1 三件套是否立即 fix(修 Task 2 dead code + reviewer_stuck schema 化) | **修**(三件套同 PR · Task 2 dead code 不修等于沉没成本) | 留 → 接受 137874f 为已知 dead code |
| 2 | P1-1 路径(p1_skip_reason vs 整删 forbiddenApproaches) | **B 路径 1**(p1_skip_reason)| A 路径 2(整删)— 节 $0.2-0.8/run 但失去 15-35% 救场 |
| 3 | **F24 / P2-1 reviewer × 3 → × 1 multi-lens(C 标 "整个 audit 最大单条净降项")**:省 **$2.25-4.5/run** 但墙钟 ×3 | **看用户场景**:多数离线长跑 → 全采(最大降本);多数在线等待 → 保持 × 3 lens(并行体验) | 不改 |
| 4 | P3-3 maxRounds 6→5 / staleRounds 2→3 | **采纳为新默认**(节 -$1-2/run,复杂 case 用户可 override) | 不改 |
| 5 | implementer = opus 例外是否仍合理(SKILL.md L207 乐观推论未实证) | **本 audit 不答**,建议另起 A/B test 评估 sonnet implementer vs opus implementer | / |
| 6 | 自动改进 70-80% 是否够你的实际场景 | 你定义"够":够用 = OK;不够 = 上述外补 P3 + 长期收集失败 case 反推 P4 改进 | / |

### 最大上限场景(三方综合估算)

| 路径 | 改动 | Δ/run | baseline → 终态 | 备注 |
|---|---|---|---|---|
| 保守 | P0-1/2 + P1 + 不动 F24 | -$0.4-0.8/run | $10-18 → $7-15 | 省 17-22%,墙钟不变 |
| 极致 | + F24(multi-lens)+ F16-1(P1 路径 1)| -$3.9-7.5/run | $10-18 → **$2.5-14** | 省 22-75%,墙钟 ×3 |
| 最激进 | + F24 + F16-2(P1 路径 2 整删) | -$4.5-8.5/run | $10-18 → $1.5-13.5 | 省 25-92%,但失 15-35% 救场 case |

---

## 10 · 不动建议(audit 看上去可优化但实际不建议改)

- **N1 · capture / review 解耦红线**:reviewer 永久零浏览器 — 实测有效绕开多 reviewer 抢 MCP 单例串台,不动
- **N2 · 主会话 vs Workflow 工具的智能负担划分**(主会话懂项目、Workflow 不懂)— 这是 Workflow 工具的固有限制,SKILL 设计正确不动
- **N3 · implementer = opus 例外** — 见决策 5,需 A/B 不在本 audit
- **N4 · paused.md 覆写 → P2-3 改 append-only**(A 原主张不动 → 被 B 反驳改为应改,见 P2-3)
- **N5 · stateDumps 第二证据通道**(canvas/ECharts 路线)— 有效,不动
- **N6 · reviewer 跨轮信号受限是 by-design,不是 bug**(A CV-9 强调):reviewer 当前 by design 只读 N-1 reviews(2026-06-22 Task 1 commit 02420b4 已收紧到 N-1 only)、不读自己历史输出 — 这是为防自我同源锚定,**未来切勿"改进"为让 reviewer 直读多轮历史**(会破红线)。跨轮信号正确通道 = implementer schema(下游可观察)+ issuesJson(状态机持久化)+ P1 meta-agent(独立 opus 整合)。三通道齐备 ≠ reviewer 直读历史 reviews

---

## 11 · 改进路线图建议

### Sprint 1(立即,2-4h)
- **P0-1 三件套**(mergeIssues 补字段 + implementer schema 必填 reviewer_stuck + workflow 程序化注入)
  - 三件套**必须同步修**;任一缺都断链
- P0-1 配套 3 个 runtime test(同源根因 T2)
- P0-2 issuesJson status filter(trivial,放同 PR)
- P1-3 删 goal.json(trivial,放同 PR)
- **单 PR 合并**

### Sprint 2(1-2 周内,2-4h)
- P1-1 P1 meta-agent + p1_skip_reason
- P1-2 read-decision-log 合并 short-circuit
- P1-4 5 级 → 2 档
- P1-5 三段并 1 段(前置 P0-1 完成)
- 单 PR

### Sprint 3(后续,看用户偏好)
- P2-1 reviewer multi-lens(墙钟 trade-off 用户拍)
- P2-2 SKILL canvas 下放 examples
- P3-1/2/3 闲时

---

## 12 · 三方收敛全表 + 详细 ROI 总表参照

**详细参照**:
- C_raw.md **§8 最终融合 ROI 总表**(F1-F23 + H-A1/A2/A3,4 大类 + 1 决策项 + 1 放弃)— **最权威的 23 条改进 ROI 表**
- B_raw.md **§ Phase 2 终态修正段**(完整收敛矩阵 + P0-1 三件套合并改进详写)
- A_raw.md **§CV-1..CV-6**(架构维度 cross-validation 修正 + 两维 disambiguation 准则)

### 三方收敛全表(本 report 浓缩版)

| 议题 | A | B | C | 最终 |
|---|---|---|---|---|
| planDedupBlock dead code | ✓ confirmed(CV-1)| ✓ raised(盲点 A)| ✓ confirmed | **P0-1**(三方收敛) |
| issuesJson status filter | ✓ A1 类 | ✓(协作 cut-2)| ✓ C-cut-2 | **P0-2** |
| META_AGENT_SCHEMA 收窄 | A 主删 2 字段 | B 主修补 + p1_skip_reason | C 数据 lead | **P1-1**(B 路径胜) |
| 测试零 runtime | ✓ H1 | ✓ 盲点 B | ✓ | **背景动力**(进 P0-1 必跟测试) |
| 跨 session resume | ✓ H6 | ✓ | ✓ | **P3-2** |
| 每轮 sonnet agent 冗余 | ✓ H2 | ✓ 应做 | ✓ | **P1-2** |
| GOAL 三件套 | ✓ D1 (1.5 件) | ✓ | ✓ | **P1-3** |
| 5 级优先级 | ✓ D3 | ✓ | ✓ | **P1-4** |
| 三段并 1 段 | ✓ D4 | ✓ | ✓ | **P1-5** |
| reviewer × 3 → × 1 multi-lens | ✓ 架构合规 | ✓ 应做 | ✓ -$0.75-1.5/run | **P2-1**(用户拍墙钟) |
| SKILL canvas path2-bias | ✓ G1 | ✓ | n/a | **P2-2** |
| vision verifier(B#13)| 未涉 | ✓ 自评代价大 | ✓ +$1-2/run | **放弃**(三方收敛) |
| reviewer_stuck schema 化 | ✓ A6 | ✓ #8 / 盲点 E | ✓ 高 ROI | **合并入 P0-1**(B+A6+B盲点E 同源)|

---

## 13 · 附:本 audit 自己的元教训

1. **测试套件用文本 grep 是反向架构信号**:P0-1 这种 latent 数据流 bug 几乎必然还有 — 本 audit 时间限制下未全面排查 mergeIssues 之外的字段穿透。**建议把 mergeIssues 当作 anchor**,grep 所有"reviewer 输出 → mergeIssues 持久化 → 下轮 reviewer 内插"路径上每个字段,确认无第二处类似断点。
2. **agent team 三方独立调研 + cross-validate 抓到了 lead 单人会漏的**:planDedupBlock dead code 是 B 单独抓到、A 通过重读代码确证、C 提供成本背景的协作产物 — lead(本会话)是 Task 2 的 implementer 但**没意识到 mergeIssues 不持久化新字段**(只验了 prompt 文本)。这是 SDD 流程"reviewer 只看 diff"自身的盲点 — 本次 audit 是这盲点的修补。
3. **token 口径混淆是研究 audit 的常见 risk**:lead 在 Phase 2 中段对齐"运行 workflow"vs"修改 skill"两口径,三方都顺利对齐。final_report 一律按"每 run 运行成本"口径报。

---

**End of final_report.md**
