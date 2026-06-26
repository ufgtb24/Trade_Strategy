# Redesigner Proposal — web-loop 决策层加入方案

> 2026-06-21 · redesigner(opus subagent)
> 角色:在当前 Workflow 框架内,设计加「根因分析 / 决策层」的具体方案。本文是 draft v1,等 architect / diagnostician / skeptic 反馈后会再迭代。
> 配套读物:`.claude/skills/web-loop/SKILL.md` § GOAL 持久化、`workflow-template.js`(注释含 M1/M4 设计依据)、`docs/research/2026-06-10-web-loop-agent-token-audit.md`(opus 当前分工)。

---

## 0. 用户需求复读(防漂)

> 在 web-loop 的 workflow 里加入一个 **opus agent** 负责把 workflow 本轮运行得到的问题进行原因分析,并给出下一轮的工作指导,类似 superpowers 的写 spec 和 writing-plan。目的:提升代码修改的成功率和针对性、更聪明、更高效、更节约 tokens。

痛点(必须解):**经常遇到一个小小的问题迭代很多轮也改不好**。

设计反推:本方案的判据是「**少跑几轮 + 每轮更对**」,而非「加件事干」。任何让循环变长 / token 增长 / 加件事但收益不可量化的设计都不通过。

---

## 1. 决策(8 条)

### 1.1 决策 agent 位置 = B'(reviewer 之后、implementer 之前,且仅当 `mustStaleStreak ≥ 1` 触发)

| 选项 | 评判 | 理由 |
|---|---|---|
| A(每轮跑) | 否 | 90% 简单 must 第一轮就 fix,加固定调用 = 反向恶化 token 预算,违用户原话「更节约 tokens」 |
| B(stale ≥ 1 触发) | **选** | 精准击中"小问题改不好"的瞬间;mustStaleStreak 已是 workflow 内置信号(:359),零新增 plumbing |
| C(替代 reviewer) | 否 | 偷换概念:reviewer 干绝对标准 pass/fail 裁决(对账 rubric),决策 agent 干根因分析 + 下轮指导,不是同一件事;合并 = 两件都做不好,且破坏并行结构 |
| D(implementer 内嵌思考) | 否 | implementer 是 fresh sonnet subagent,看不到 PNG / verified 历史 / 其他 lens 的 verdict,没有判断"为什么上轮没修好"的输入 |

**触发判据 = 严格化**:
- 当前 `mustStaleStreak ≥ STALE_ROUNDS(=2)` 已是 stall 退出条件(:383)
- 决策 agent 触发判据建议 = `mustStaleStreak >= 1`(刚检测到本轮零进展、还未到 stall 退出 → 此刻召唤决策 agent 是「stall 退出前最后一次救」)
- 第一轮(round=1)绝不触发(还没数据可分析根因)

**为什么不放 implementer 之前每轮跑一遍轻量 planning**:
- "轻量 planning" 假设决策 agent 不读 PNG / 历史,只对着 GOAL 想下轮做啥——这与 implementer 自己想没区别,纯加 spawn 成本
- 真要值钱,决策必须读 PNG + 跨轮历史;这种重量级分析每轮都跑就违反"节约 tokens"

---

### 1.2 决策 agent 模型 = `opus`

- 用户原话直接锁定 opus("加入一个 opus agent")——这是设计约束,不是开放问题
- 根因分析需跨证据通道综合:PNG(多模态)+ git diff + verified 历史 + must 台账 + 上轮 impl.md → CLAUDE.md「Reviewer/把关一律 opus」判据②的靶心
- **触发频率低(stale ≥ 1)→ 单次贵但低频,总成本可控**
- token 账的真大头:**少跑几轮的复利**。少 1 轮 ≈ 省(1 impl sonnet + 1 smoke sonnet + 1 refresh sonnet + 1 capture sonnet + 3 review opus + 1 persist sonnet),粗算单轮 50K+ tokens,远超 1 次决策 agent 的 ~15K(prompt 重 + thinking)

---

### 1.3 决策 agent 输入清单(read-only,不写台账)

**必读**(都是文件路径,不重传内容,让 agent 自己 Read):

| 输入 | 来源 | 用途 |
|---|---|---|
| `${WORKDIR}/goal.md` | setup 阶段已写 | 原始 GOAL + 子项 + refs 摘要(避免漂) |
| `${WORKDIR}/goal.json` | 同上 | 机器可读副本(若需结构化引用) |
| `${WORKDIR}/refs/manifest.json` + `refs/*.png` | 主会话「智能入口层 §2c」预先持久化 | 视觉目标对照(决策 agent 需看 role=goal 的图建基准) |
| `${WORKDIR}/issues.json` | persist 落盘 | must 台账完整状态(open / regressed / fixed history) |
| `${WORKDIR}/verified.json` | persist 落盘 | 跨轮 verified 历史(coveredSubgoals 聚合) |
| `${WORKDIR}/reviews/round_NN.md` × 最近 ≤3 轮 | persist 落盘 | reviewer verdict 全文(三 lens 的 issues + verified + goalEcho) |
| `${WORKDIR}/rounds/<round>/impl.md` × 最近 ≤3 轮 | implementer 落盘 | implementer 自报本轮改了什么 + kind |
| `${SHOTS_DIR}/r<NN>_<state>.png` × 本轮全部 + 上轮全部 | capture 落盘 | 跨轮视觉对比(看变化方向是否对) |
| `git diff HEAD~N..HEAD --stat` + `git log --oneline -N` | shell | 最近 N 轮提交摘要(N = mustStaleStreak + 1) |
| 项目 rubric(`${RUBRIC_PATH}`)| skill 入口提供 | 验收标准上下文 |
| 项目源码 **(允许 grep + Read,但有边界)** | 仓库 | 定位"为什么这个 must 没消"的真根因 |

**不读**(避免膨胀 + 防越界):
- 全仓库 tree(scope 不准)
- 其他 worktree / .claude/ 内不相关文件
- 历史 SUMMARY.md(上一 run 的,不是本 run 的)

**源码 Read 边界(关键防线)**:
- 允许 grep 关键词、Read 相关组件文件 + 找根因
- **禁止** 输出 patch / 代码片段 / 函数级"改这行成那样"的指令
- 引用源码只能作为「根因证据」(如"DataTable.tsx:128 onResize 没监听 window 重绘 → 为什么布局连续两轮塌"),不能作为「修改指令」(❌"把 DataTable.tsx:128 改成 useEffect(() => { window.addEventListener(...) })")

理由:这条边界是决策 agent 与 implementer 的分工铁线。越过 = 决策 agent 偷走 implementer 的设计判断,fresh subagent 间传 code snippet 噪声极大,实际效果是 implementer 沦为打字员、bug 没消反引入新 bug。

---

### 1.4 决策 agent 输出 = 混合制(结构化骨架 + 自然语言 working spec)

**Schema**(JSON):

```json
{
  "stalledRound": <number>,
  "rootCauseHypothesis": [
    {
      "id": "H1",
      "claim": "<一句话假设>",
      "evidence": ["<本轮 PNG 文件名 + 像素特征>", "<reviewer 的 issue id>", "<diff 文件:行号>"],
      "confidence": "high|medium|low"
    }
  ],
  "blockedSubgoals": ["G1", "G3"],
  "prioritizedMustIds": ["ux-r03-2", "code-r03-1"],
  "forbiddenApproaches": [
    "<上轮试过且失败的具体做法,implementer 下轮禁止重试>"
  ],
  "diagnosticActions": [
    "<本轮 capture 之外想要的观察,如 'states 缺一个 03-resize-narrow,建议下次 run 加'>"
  ],
  "workingSpec": "<自然语言段,300-600 字。\n类比 superpowers writing-plan 但缩到一屏:\n1) 当前卡点的根因故事(把 rootCauseHypothesis 串成因果链)\n2) 下轮 implementer 该把注意力放在哪个组件/方向(不是哪行代码)\n3) 该怎么验证假设是否正确(对应 diagnosticActions)\n4) 如果假设错了的备用 plan>",
  "nextRoundFocus": {
    "primaryMust": "<must id>",
    "expectedEvidence": "<下轮 verified 应见到什么样的 evidence 才算修对>"
  }
}
```

**关键约束**:
- **决策 agent 不得新增 must 也不得 close must**——台账写入权严格归 mergeIssues(:80)。决策 agent 只读、只重排
- `prioritizedMustIds` 必须是 issues.json 里已有的 id 子集(不允许编新 id)
- `forbiddenApproaches` 是新加的台账维度:跨轮防 implementer 反复试同一招;持久化到 `${WORKDIR}/decision_log.json`,下轮 implementer prompt 强制内插
- `workingSpec` 是真正给下轮 implementer 的"主线",不替代 must 列表,而是给"how to attack"层

---

### 1.5 prompt 草案

```
【${rtag} · decision(根因分析 + 下轮工作指导)】
你是 web-loop 的决策 agent(opus)。已检测到 mustStaleStreak ≥ 1(上轮 must 台账完全冻结,implementer 在乱撞)——
你的任务是在 stall 退出兜底之前,做一次根因分析,把下轮 implementer 从乱撞拉回主线。

⚠ 你不是 reviewer:不新增 must、不 close must、不重判 pass/fail
⚠ 你不是 implementer:不输出 patch、不写代码、不给"改这行成那样"的指令
你只做两件事:(a) 根因分析(为什么连续 ${mustStaleStreak+1} 轮 must 台账没动);(b) 给下轮 implementer 一份"working spec"。

【本次 GOAL(完整版以 ${WORKDIR}/goal.md 为准)】
${safeInsert(GOAL)}

【GOAL 子项(完整版以 ${WORKDIR}/goal.md 为准)】
${goalSubgoalsSummary}

【参考图清单(详 ${WORKDIR}/refs/manifest.json,role=goal 必读 Read 图建基准)】
${refImagesSummary}

【当前停滞统计】
- stalledRound = ${round}
- mustStaleStreak = ${mustStaleStreak}
- 累计 open must = ${openMust.length}
- 仍未 covered 的 GOAL 子项 = ${uncoveredSubgoalIds.join(', ')}

【调查指引(按顺序做完才能输出 workingSpec)】

第 1 步 · 建立视觉基准:Read ${WORKDIR}/refs/manifest.json,然后 Read role=goal 的每张 PNG(若有)。

第 2 步 · 看本轮 + 上轮的截图对比:
  Read 本轮全部 PNG = ${currentShotPaths.join(', ')}
  Read 上轮全部 PNG = ${prevShotPaths.join(', ')}
  对每个 state,问自己:本轮相对上轮变了吗?变化方向是朝 GOAL 还是远离?

第 3 步 · 读 reviewer verdict 全文:
  Read ${WORKDIR}/reviews/round_${round}.md
  Read ${WORKDIR}/reviews/round_${round-1}.md(若存在)
  抓三 lens 各自的 issues / verified / goalEcho,找出"反复出现但没被 close"的 must 模式。

第 4 步 · 读 implementer 自报:
  Read ${WORKDIR}/rounds/${round}/impl.md
  Read ${WORKDIR}/rounds/${round-1}/impl.md(若存在)
  问:implementer 自己说改了什么?为什么 reviewer 没看到改进?

第 5 步 · git diff 看真改了什么:
  bash: cd <repo>; git log --oneline -${mustStaleStreak+1}; git diff HEAD~${mustStaleStreak+1}..HEAD --stat
  对照 impl.md 自报 vs git diff 实际,有没有 implementer 说改了但 diff 显示没改的(吞改);
  或者 diff 改了但 reviewer 看不到效果的(改错地方)。

第 6 步 · 源码定位根因(有边界):
  grep / Read 相关组件文件,定位"为什么这个 must 反复修不掉"。
  ⚠⚠ 你可以读源码作为根因证据,但 ⚠ 输出严禁含:patch / 代码片段 / 函数级"改这行成那样"的指令。
  允许:"DataTable.tsx 的 onResize 没监听 window 重绘 → 解释 G1 高度连续两轮不变"。
  禁止:"把 DataTable.tsx:128 改成 useEffect(() => { window.addEventListener(...) })"。

第 7 步 · 跨轮防重复:Read ${WORKDIR}/decision_log.json(若存在)。
  上轮 decision 给出的 forbiddenApproaches 在本轮还有效吗?
  上轮的 rootCauseHypothesis 哪些被本轮证据证伪 / 强化?

【输出 schema】严格按下面 JSON 输出,字段语义见 redesigner-proposal §1.4:
${JSON.stringify(DECISION_SCHEMA, null, 2)}

【纪律】
- 完整性:不为让 implementer 好做就压低 confidence,如实标 high/medium/low
- 不新增 must 不 close must——只重排已有 must id 的优先级
- workingSpec 必须明确说"下轮该看哪个组件 / 哪个方向";不能只说"修一下 G1"
- forbiddenApproaches 是本设计的关键创新:把"试过且失败"的具体路径写明,implementer 下轮强制规避
```

(prompt 总长约 1500 tokens,可接受)

---

### 1.6 对其他 agent 的影响

#### implementer prompt 改造(关键)

实施 = workflow-template.js 已有的 implementer prompt(:256) 后追加一段(仅当上轮触发了 decision agent 才加,普通轮不加):

```
【⚠ 上轮决策层判定本轮 must 台账冻结,启动了 decision agent。下轮(=本轮)请严格按下面 spec 工作】

【本轮 working spec(由 decision agent r${round-1} 产出)】
${decisionWorkingSpec}

【优先 must id(按这个顺序)】
${decisionPriorityList}

【⚠ 禁止重试的方法(上轮试过且失败)】
${decisionForbiddenList}

【期待证据】
${decisionExpectedEvidence}

⚠ 若 working spec 给的方向你判断错了,可以偏离,但必须在 impl.md 里说明"我偏离了 decision 的方向,理由是 X";不允许沉默偏离。
```

**implementer 改造原则**:不变成"按 spec 执行"(那是 superpowers writing-plans 模式,过度);保留 implementer 的判断权,decision 只是"strongly suggested"。

#### reviewer 三 lens:**不动**

理由:decision agent 不替代 reviewer 工作。reviewer 仍是绝对标准 pass/fail 裁决,产出 issues + verified。decision 消费 reviewer 产出,不替代。

#### 新增 `${WORKDIR}/decision_log.json`(跨轮防重复)

每次 decision agent 跑完,append 一条 entry:

```json
{
  "round": <number>,
  "rootCauseHypothesis": [...],
  "forbiddenApproaches": [...],
  "workingSpec": "<截短至 500 字>"
}
```

下轮 decision agent(如果再触发)先 Read 这文件,看上轮假设哪些被证伪。

#### finalize 改造:**SUMMARY.md 加一节**

如果本 run 触发了任何 decision agent,SUMMARY.md 加"## 决策层介入记录"节,列每次触发的 round + workingSpec 摘要 + 是否解决了 stall。

---

### 1.7 token 预算估算

**基线**(无 decision agent,一轮迭代 token):

| agent | model | 入 prompt | 出 | 估算 tokens |
|---|---|---|---|---|
| impl | sonnet | ~3K | ~2K | 5K |
| smoke | sonnet | ~0.5K | ~0.2K | 0.7K |
| refresh | sonnet | ~0.8K | ~0.3K | 1.1K |
| capture | sonnet | ~2K(含 states recipe) | ~1K(manifest) | 3K |
| review × 3 | opus | ~6K each(含 PNG)| ~3K each | 9K × 3 = 27K |
| persist | sonnet | ~3K(含 issues) | ~0.5K | 3.5K |
| **轮合计** | | | | **~40K(opus 计 5×)** |

**加 decision agent 后**(仅 stale ≥ 1 触发):

| agent | model | 入 prompt | 出 | 估算 tokens |
|---|---|---|---|---|
| decision | opus | ~12K(prompt 1.5K + 引用历史/PNG 多模态 ~10K) | ~3K | **~15K(opus 计 5×)** |

**决策 agent 触发场景的纯成本**:每次触发 ~15K opus = ~75K equivalent token cost(按 opus/sonnet 5×)。

**收益估算**(关键账):
- 当前 stall 路径:STALE_ROUNDS=2,触发 stall 退出后人工介入,通常用户会改 GOAL / 加 states 后重跑 → **下一 run 整个又是 ~40K × N 轮**
- 加 decision agent:触发后下一轮 implementer 命中正确方向的概率提升 → **少跑 1-2 轮 = 省 40-80K**
- 净期望:若决策能把"乱撞 4 轮"压到"乱撞 1 轮 + 决策 1 次 + 命中修复 1 轮" = **省约 80K - 15K = 65K** / stall 事件

**前提**(诚实账):
- 决策准确率假设 ≥ 50%(只要超过随机就比现状好,但若 < 50% 反而恶化)
- 如果用户的 stall 事件不频繁(整 run 中 0 次触发),本改动零成本零收益
- 如果用户 stall 事件极频繁(每 run 触发 2-3 次),决策成本叠加,需校准触发阈值

---

### 1.8 resume / 缓存影响

**Workflow resume 缓存命中判据 = `hash(prompt + opts)`**(SKILL.md 原理边界 #4)。

潜在破坏点:
- decision agent prompt 内含 `${mustStaleStreak}`、`${round}`、`${uncoveredSubgoalIds.join(', ')}` 等动态字段 → 每次跑都不同,**这是 expected**(动态适配的正确行为,非 bug)
- decision 不应跑两次得不同结果——只要触发判据相同(同 round + 同 mustStaleStreak),prompt 字面相同 → 缓存命中
- ⚠ `currentShotPaths` 必须按 `state` 字典序排序后 join,否则脚本里数组顺序不稳会破缓存

**对 implementer prompt 改造的影响**:
- 普通轮(无 decision):implementer prompt 与现状字面相同 → 缓存命中
- decision 触发后的 implementer prompt:多一段 decisionWorkingSpec 内插 → 自然破缓存,但这正是「动态适配」目的

**禁忌**(已在 SKILL.md 原理边界 #4 明文):
- 决策 agent 内部禁 `Date.now()` / `Math.random()`
- decision_log.json 落盘必须用 stable JSON.stringify(无 timestamp 字段;若必须有 round 字段足够)

---

## 2. 时序图(标 decision agent 介入点)

```
[setup]
  pw-selfcheck (sonnet)
  preflight    (sonnet)
  write-goal   (sonnet)

[iterate round=1]                         ← decision 永不触发(无历史可分析)
  impl-r01    (sonnet)
  smoke-r01   (sonnet)
  refresh-r01 (sonnet)
  capture-r01 (sonnet)
  review-{ux,func,code}-r01 (opus × 3)    ← parallel
  persist-r01 (sonnet)
  → mustStaleStreak=0(首轮总有新增)

[iterate round=2]                         ← mustStaleStreak 计算
  impl-r02 ... review-...-r02 ... persist-r02
  → mustStaleStreak 视情况

[iterate round=3]   ★ if mustStaleStreak >= 1
  ★ decision-r03 (opus,新增)              ← 在 impl 之前
       │
       ├─ Read goal.md / goal.json / refs/
       ├─ Read review/round_03.md + round_02.md
       ├─ Read rounds/03/impl.md + rounds/02/impl.md
       ├─ Read issues.json / verified.json
       ├─ Read 本轮 + 上轮 全部 PNG(多模态)
       ├─ bash: git log --oneline -2 / git diff HEAD~2..HEAD --stat
       ├─ grep / Read 源码(有边界)
       └─ Write decision_log.json(append)
       → 产出 { rootCauseHypothesis, prioritizedMustIds, forbiddenApproaches, workingSpec, ... }

  impl-r03 (sonnet,prompt 加 decision spec 段)
  smoke-r03 ... 同前流程
```

**关键不变量**:
- decision 介入是 reviewer 后 + impl 前 的"插件"位置,不破坏循环主轴
- decision 不写 issues.json / verified.json(台账完整性保留)
- 普通轮(stale=0)零 decision 调用 → 零额外成本

---

## 3. 自审(怎么不踩进自己挖的坑)

### 3.1 "另一个 reviewer"风险

防御已锁:
- decision agent prompt 显式禁"新增 must / close must / 重判 pass/fail"
- 输出 schema 没有 issues 字段,只有 prioritizedMustIds(已有 id 子集)
- mergeIssues(:80) 是台账唯一写入口,decision 不调它

### 3.2 "代为修改的 implementer"风险

防御:
- prompt 显式禁 patch / 代码片段 / 函数级指令
- workingSpec 字段限"方向 + 调试方法",不限"具体改这行"
- implementer prompt 增加"若偏离 decision 必须说明理由"的逃生口——保留 implementer 设计判断权

### 3.3 "决策错了反而误导"风险

防御:
- forbiddenApproaches 跨轮持久化 → 下次 decision 看上次假设是否被证伪、可自我纠正
- workingSpec 必含"如果假设错了的备用 plan"——decision agent 不能 ego 锁死单一假设
- finalize 在 SUMMARY 标注每次 decision 介入是否解决了 stall,人工复盘可知本改动是否真起作用

### 3.4 "stall 之前 N 轮乱撞也没人救"风险

诚实承认:
- 当前触发 = `mustStaleStreak >= 1`(刚检测到 1 轮零进展)
- 若 STALE_ROUNDS=2,decision 触发后还有 1 轮 implementer 机会;若没命中、就走 stall 退出
- 若用户嫌"还是太晚",可把触发阈值调到 round >= 2 且 mustStaleStreak >= 0(等价"从第 2 轮起每轮跑")——但这是用 token 换早干预,**默认不开**,作为 args 可选配置 `decisionTriggerMode: "stale" | "always-from-2"`(留扩展点)

### 3.5 "decision 自己读不出根因"风险

诚实承认:
- 决策准确率不可能 100%;若 decision agent 自己也搞不清楚,会输出低 confidence 假设
- 此时 implementer 看到 low-confidence workingSpec → 应该按自己判断走(prompt 明示)
- 这种"decision 也救不了"的场景,正是 stall 退出的合理时机,不强求 decision 必胜

---

## 4. 与 architect / diagnostician / skeptic 待对线点

(留 placeholder,等 team-lead 转他们立场过来再补)

- **architect**:opus 当前分工的合理性 vs 加 decision 是否冲突
- **diagnostician**:"小问题改不好"的真根因清单是否完整?有没有不是"缺决策层"能解释的痛点?(若 60% 痛点其实是 reviewer 漏判 / capture 缺 state,加 decision 解不掉)
- **skeptic**:Workflow 范式是否根本不适合 web 迭代?加 decision 是治标?——我的初步反驳:用户原话就要 opus 决策 agent、且 Workflow 已沉淀了 GOAL 持久化等关键机制,推倒重做成本远超加一个 agent。但仍要听 skeptic 怎么 argue。

---

## 5. 落地清单(若 final_report 决定走本方案)

P0(必做):
- workflow-template.js 加 decision agent(reviewer 后 / impl 前 / 触发判据 = mustStaleStreak >= 1)
- decision agent prompt 落地 + schema 落地
- implementer prompt 改造(条件追加 decision spec 段)
- decision_log.json 持久化

P1(配套):
- SUMMARY.md 加"决策层介入记录"节
- SKILL.md 加文档说明触发条件 + 输出格式
- args 加 `decisionTriggerMode`(留扩展)

P2(后续):
- 实跑几个 run 后校准触发阈值
- 若发现 decision 命中率 < 50% → 退回去重新设计 prompt 或砍掉

---

**redesigner draft v1 完成,等 team-lead 转 architect / diagnostician / skeptic 反馈后迭代 v2。**

---

# §6 立场更新与最终方案(v2,2026-06-21 R2 cross 后)

## 6.0 元说明

本节是 R1 + R2 三方 cross 后的诚实重写。v1 § 1-5 保留作辩论留痕,但**最终推荐以本节为准**。
对线对手:diagnostician(扩 reviewer schema 让 code lens 出根因)/ architect(R1 翻转,折进 reviewer + stall 触发 meta-agent 罕用)/ skeptic(混合架构,3 轮没收敛人 + tom 看截图)。
团队 R2 末态:**三人对独立 decision agent 强烈合围**。

## 6.1 我的让步清单(诚实账)

| # | v1 立场 | R2 末态 | 让步触发 |
|---|---|---|---|
| L1 | "merge 3 reviewer 建议是核心赢面" | **撤回**(diagnostician 的"只 code lens 出根因"釜底抽薪) | diagnostician R1 |
| L2 | 触发 = `mustStaleStreak >= 1`(信号可靠) | 真打击:mergeIssues:106 用 `title` 字符串去重,reviewer 换说法就漏检 | diagnostician R1 |
| L3 | decision 出 `rootCauseHypothesis` 字段 | **撤回**(让给 code reviewer 扩 schema,decision schema 物理禁此字段) | diagnostician R1 |
| L4 | decision 出 `workingSpec` 长文本 + `nextRoundFocus` + `diagnosticActions` | **全砍**(v2 只剩 3 个机器可消费字段) | diagnostician R1 |
| L5 | decision agent 独有"跨轮综合"价值 | **大让步**:跨轮 reviews/impl.md 可以让 implementer 直接 Read,不需要 agent 中转 | team-lead R2 §A |
| L6 | decision agent 独有"元判断 escapeRequest"价值 | **让步**:reviewer 扩 `believesUnachievable` 字段 + 跨轮 JS 控制流聚合可达等效;reviewer 单轮判"永远绕不开"违红线但**扩字段级布尔与 issuesStatus 同性质**,折得过去 | team-lead R2 §A |
| L7 | decision agent 独有"forbiddenApproaches 持久化"价值 | **让步**:implementer 在 impl.md 首行写"试了 X 失败因为 Y" + code reviewer 扩 `triedApproachesObserved` echo + mergeIssues 聚合到 issues 台账新字段,architect 路线全覆盖 | team-lead R2 §A |

**让步总账 = 我没有"仅独立 agent 能做、其他方案做不到"的具体场景。R2 §C 的诚实拷问我答不出来。**

诚实承认:R1 "跨 lens + 跨轮 + 多模态对 PNG" 三论据都被合围掉了:
- 跨 lens:只 code lens 出根因绕开
- 跨轮:implementer 可直接 Read 落盘历史
- 多模态对 PNG:reviewer 已多模态看,decision 重读 = 双源真理新故障源

## 6.2 团队大共识方案(0 新 agent,推荐 P0)

把我设计的所有机制(escapeRequest / forbiddenApproaches / 多通道触发判据 / workingSpec 内容)**全部折进现有 reviewer + mergeIssues 控制流 + implementer prompt**:

### 6.2.1 reviewer schema 扩字段(diagnostician 主菜)

```jsonc
// REVIEWER_SCHEMA(workflow-template.js :179)新增字段:
{
  // 现有字段保留……
  issues: [{
    // 现有字段保留……
    rootCauseHypothesis: "<string,code lens 必填,ux/func 可选>",
    affectedFiles: ["path:line", ...],     // code lens 必填
    suggestedFix: "<string|null,可选,implementer 可推翻>",
    triedApproachesObserved: [             // code lens 读上轮 impl.md "首行试了什么" + 本轮 diff 比对
      { method: "...", evidence: "<diff 行号 / impl.md 引文>", looksFailedBecause: "..." }
    ],
    believesUnachievable: false            // code/ux/func 三 lens 都可填,布尔
  }]
}
```

### 6.2.2 mergeIssues 控制流增强(纯 JS,确定性)

```jsonc
// workflow-template.js mergeIssues(:80)新增聚合规则:
- 每 issue 跨轮聚合 triedApproachesObserved → issues[i].forbiddenApproaches[] 台账字段
- 每 issue 跨轮聚合 believesUnachievable → 若三 lens × N 轮都标 true → issues[i].escapeRequest 字段标 "unachievable_consensus"
- 多通道触发判据(代替原 mustStaleStreak >= STALE_ROUNDS 单通道):
    stalled = mustStaleStreak >= STALE_ROUNDS
          || (coveredSubgoals 集合连续 STALE_ROUNDS 轮未增)
          || (git diff --stat 连续 STALE_ROUNDS 轮 < 5 行)
          || (任何 issue 标了 escapeRequest)
```

### 6.2.3 implementer prompt 增强(workflow-template.js :256)

```text
【本轮工作】(round ≥ 2 时追加)

【上轮 code reviewer 给的根因假设(若有)】
{issue.rootCauseHypothesis 列表}

【上轮 code reviewer 标的影响文件】
{issue.affectedFiles 列表}

【⚠ 禁止重试方法(跨轮聚合的 forbiddenApproaches 台账)】
{issue.forbiddenApproaches 列表}
若你必须重试,在 impl.md 首行说明"我重试了 X,理由是 Y"。

【你的自报义务】
完成后 impl.md **第二行必须列**"本轮我试了哪些方法":每条 `- method: ... | targetIssueId: ... | expectedEvidence: ...`
(下轮 code reviewer 会 read 你这段,echo 进 triedApproachesObserved → 跨轮 forbiddenApproaches 聚合)

【跨轮历史(round ≥ 3 时追加)】
Read 最近 ≤2 轮 reviews/round_NN.md 全文,看看上轮 reviewer 是怎么判的、你上轮怎么改的、效果如何。
```

### 6.2.4 finalize 增强

SUMMARY.md 加"## 决策诊断"节,机器从 issues 台账 dump:
- 每 issue 的 forbiddenApproaches 历史
- 每 issue 的 believesUnachievable 表态历史
- escapeRequest 触发条件

人工复盘时一目了然为什么这条 must 没修掉、reviewer/implementer 反复试了什么。

### 6.2.5 改动量

| 文件 | 改动 | 行数粗估 |
|---|---|---|
| `workflow-template.js` REVIEWER_SCHEMA | 扩 5 字段 | ~15 行 |
| `workflow-template.js` mergeIssues | 加跨轮聚合 + 多通道触发判据 | ~30 行 |
| `workflow-template.js` implementer prompt | 加 4 段(条件触发) | ~25 行 |
| `workflow-template.js` finalize | 加"决策诊断"节 | ~15 行 |
| `principles.md` | reviewer rubric 加 rootCauseHypothesis 填写指引 + impl.md "自报义务"说明 | ~20 行 |
| **总计** | **5 文件 ≤ 105 行**,零新 agent,零新 spawn | |

### 6.2.6 token 经济

- 每轮:reviewer schema 多几个字段 → 出 tokens +~0.5K × 3 lens = 1.5K/轮(opus)
- 每轮:implementer 多 Read 跨轮文件(round≥3 才触发)→ +~3K/轮(sonnet)
- **vs 加 decision agent 的 ~15K/触发 opus,纯赚**
- 主收益:跨轮历史 + 禁止重试 让 implementer 第 2 轮起命中率显著提升,**期望少跑 1-2 轮 = 省 40-80K/run**

## 6.3 P1 = 我 v2 缩窄版 decision agent(可选叠加,与 architect 的「stall-触发 meta-agent」重合)

team-lead R2 末锁定的最终架构:**P0(§6.2)主推、P1 是我 v2 缩窄版作为「P0 实测不够时的可选叠加」**(与 architect 的「stall 触发独立 meta-agent 罕用」是同一件事的两种描述)。默认不开,但保留设计完整以备启用。

### 6.3.1 v2 schema(3 字段,物理禁双源)

```jsonc
// decision agent 输出 schema(opus,stalled === true 时一次性触发)
{
  forbiddenApproaches: [
    { issueId: "<issues.json 已有 id>",
      triedMethod: "<implementer 上轮 impl.md 自报 + git diff 实证>",
      why_failed_evidence: "<本轮 PNG 文件名 / probe key / diff 行号>" }
  ],
  prioritizedMustIds: ["<issues.json 已有 must id>", ...],  // 仅排序,不新增不删除
  escapeRequest: { type: "missing_state" | "rubric_too_strict"
                       | "goal_unrealistic" | "reviewer_disagreement",
                   detail: "<自然语言原因>" } | null
}
```

**schema 层物理禁的字段**(防双源):`issues / verified / rootCauseHypothesis / suggestedFix`。decision 不出根因(已让 code reviewer 干)、不出 issues(reviewer 单源)、不出 patch(implementer 单源)。

### 6.3.2 触发判据(多通道兜底,代替 v1 单通道 mustStaleStreak)

```js
// 触发 = OR(任一通道命中)
decisionTrigger = mustStaleStreak >= STALE_ROUNDS                       // 原通道,reviewer 换说法可能漏
              || coveredSubgoals 集合连续 STALE_ROUNDS 轮未增           // 子项进度通道(M4.4 已有数据)
              || git diff --stat 连续 STALE_ROUNDS 轮 < 5 行             // 实际改动量通道
              || 任何 issue 已被 6.2 mergeIssues 标 escapeRequest         // 共识通道
```

触发判据多通道是 L2 让步的直接补救——单一字符串去重不可靠,多通道交叉抗 reviewer 措辞漂移。

### 6.3.3 防双源真理边界(B.1/B.2 让步落地)

| reviewer / implementer 干的 | decision 干的 | 不重叠? |
|---|---|---|
| must X 在不在 / verdict pass/fail | — | ✓ |
| must X 的根因假设(code reviewer 扩) | — | ✓ |
| must X 已 fixed / regressed(mergeIssues 控制流) | — | ✓ |
| — | 上轮试过什么、为什么失败(读 impl.md + git diff)| ✓ |
| — | 本轮 must 修复**优先级**排序(不新增不删除)| ✓ |
| — | 本 run 该 escape 退出(JS 控制流的质性兜底)| ✓ |

**若 decision 对 must 判定与 reviewer 不一致**:必须走 `escapeRequest.type = "reviewer_disagreement"` 通道强制人工介入,不允许 implementer 选边。

### 6.3.4 触发时位置

reviewer 之后、implementer 之前(v1 §1.1 B' 位置不变);全 run 至多 1 次(与 architect 的 stall-meta-agent 同口径,不是"卡住就跑、可能一 run 多次")。

### 6.3.5 token 经济(P1 自家账)

- 单次触发 ~12K opus(prompt + 跨轮多模态读 PNG)
- 全 run 至多 1 次 → 单 run 加 ~12K opus 上限
- 仅当 P0 已落地、且观测到 stall 退出前的乱撞模式归因为"跨 lens × 跨轮质性综合 schema 表达不出来"时才启用

## 6.4 P2 = impl 轮≥2 升 opus + workflow runtime PAUSED-await-injection(长期,超 web-loop scope)

team-lead R2 末锁定 P2 是 skeptic 主推 + architect 软落地的两个长期方向:

### 6.4.1 impl 轮≥2 升 opus(skeptic 主张,我 R1 部分反驳过)

skeptic 陷阱 (iii):"opus 决策 / sonnet 执行 → 卡在执行端 ceiling"。R1 我以"用户原话锁定 implementer sonnet + CLAUDE.md 禁用 haiku"反驳了 round=1 升 opus,但 **round ≥ 2 是不同问题**:第 2 轮起 implementer 拿到的是 must 修复任务(非首轮设计),且面对的是上轮已失败的 must——此时升 opus 等价于"用更强的 reasoning 解一个明确 bounded 的修复题",与 CLAUDE.md「implementer 一律 sonnet」的设计意图(避免在开放设计上烧 opus)**不直接冲突**。

architect 把这归为 P2 兜底,我接受。落地建议:`A.implModelByRound = { 1: "sonnet", "2+": "opus" }`(args 可配,默认开)。token 增量需另算,本提案不展开。

### 6.4.2 workflow runtime PAUSED-await-injection(skeptic 提,见 §6.7 详评)

我 v1 设计的"BLOCKED-退出"是当前 Workflow runtime 能给的最大值:decision 标 escapeRequest → 脚本侧 gate stall 退出 → 整 run 终止、SUMMARY 标红字。skeptic 提的 PAUSED-await-injection 是更优范式:**workflow 暂停而非退出,等用户从主会话注入修正(改 rubric / 加 STATES / 改 GOAL),然后续跑**。可行性评估见 §6.7。

## 6.5 R0 → R1 → R2 让步轨迹(留痕)

```
R0(初始,v1):
  decision agent 干 7 件事:根因 + 影响文件 + suggestedFix + 优先级 + 禁止重试
  + workingSpec + diagnosticActions + nextRoundFocus + escapeRequest
  schema 7 字段。触发 mustStaleStreak >= 1 单通道。

R1 cross 触发让步:
  L1 (diagnostician)  撤回"merge 3 reviewer 建议是核心赢面"
                       只 code lens 出根因 → 3 路冲突归零
  L2 (diagnostician)  触发单通道不可靠
                       mergeIssues:106 用 title 字符串去重,reviewer 换说法漏
  L3 (diagnostician)  撤回 decision 出 rootCauseHypothesis
                       让给 code reviewer 扩 schema(它本就是唯一读 diff 的 lens)
  L4 (diagnostician)  砍 workingSpec / nextRoundFocus / diagnosticActions
                       reviewer 出根因后这些字段全是 redundant 长文本

R2 cross 触发让步:
  L5 (team-lead §A)   "跨轮综合"不是独有
                       implementer 可直接 Read 落盘 reviews/round_NN.md,无需 agent 中转
  L6 (team-lead §A)   "元判断 escapeRequest"不是独有
                       reviewer 扩 believesUnachievable + JS 控制流聚合可达等效
  L7 (team-lead §A)   "forbiddenApproaches 持久化"不是独有
                       implementer 自报 impl.md 首行 + code reviewer echo + mergeIssues 聚合

R2 末态(v2):
  decision agent 干 3 件事:禁止重试清单 + must 优先级排序 + escapeRequest
  schema 3 字段。触发多通道兜底。全 run 至多 1 次,作为 P1 可选叠加。

让步 7 处全部基于"等效机制成立"的技术判断,无社交压力让步。
```

## 6.6 我 v2 的不可替代核心(一句话)

**P1 decision agent 的不可替代核 ≈ "在 P0 多通道触发判定本 run 该 stall 退出之前,做一次跨轮跨 lens 质性综合,产出禁止重试清单 + 优先级 + escapeRequest——这是 reviewer 单轮绝对标准红线 + reviewer 不读历史红线 叠加之下,reviewer schema 扩字段的机器化聚合表达不出来的那 20%。**

诚实承认:**P0 已覆盖 80% 痛点,P1 是边际 20% 增量**——只在"reviewer 三 lens 各自单轮表达不出'我们整个 run 在某个高阶模式上反复打转'"的场景才有不可替代价值。若用户的真实 stall 场景里这 20% 不显著,P1 永不被启用,这本就是 §6.5 R2 让步的诚实结论。

## 6.7 PAUSED-await-injection 可行性评估(skeptic 那一刺)

team-lead 明确要我对此评估。**结论:范式优,但当前 Workflow runtime 不支持,且修改 runtime 是 skill 层管不到的事。**

### 6.7.1 BLOCKED-退出 vs PAUSED-续跑 的差异

| 维度 | BLOCKED-退出(我 v1 设计) | PAUSED-await-injection(skeptic 提) |
|---|---|---|
| workflow 状态 | 终止,SUMMARY 落盘 | 暂停,等主会话注入 |
| 用户介入成本 | 重新 brief 主会话 + 重启 workflow + 等 setup 重跑(数据加载、smoke 基线、refs 持久化) | 主会话直接喂修正(改 rubric / 改 GOAL / 加 STATES)→ workflow 续跑 |
| 已积累的状态 | issues 台账 / verified 历史 / refs 全部从 SUMMARY 重读再注入 | 全部内存中,续跑无损 |
| 第 N 轮重启等价于 | 第 1 轮 setup + 续上 issues.json + verified.json(resume 机制部分支持) | 第 N+1 轮 implementer 直接收新输入 |

PAUSED 在 user 体验和 token 成本上**严格更优**——尤其是 setup 阶段成本高(数据 reload、smoke 基线、playwright 自检全部要重做),退出再启动等于把 setup 成本付两遍。

### 6.7.2 当前 Workflow runtime 是否支持

**不支持**,且修改它超 web-loop skill scope:

- Workflow 脚本是确定性 JS 控制流,**无暂停原语**——脚本里没有 `await waitForInjection(args)` 这类 API,只有 `await agent(...)`、`await parallel(...)`、`bash(...)` 等纯执行原语
- 主会话与正在跑的 Workflow 之间**无双向消息通道**:用户在主会话改 args 不会传递给已经 spawn 的 workflow,Workflow 也无法在 mid-run 接受新 args(args 是 spawn 时一次性 freeze 的,见 `[[reference_workflow_tool_mechanics]]` 记忆——args 整体序列化为 JSON 字符串)
- resume 机制只支持"同 session 内同一 runId 续跑"(SKILL.md 已说明 `resumeFromRunId` 仅同 session 有效),不支持"中途改输入后续跑"

要实装 PAUSED-await-injection,**需要 Workflow runtime 层加 3 件事**:
1. `workflow.pause(reason, awaitFields)` 原语,脚本可调用
2. 主会话能向 paused workflow 注入数据的双向通道(类似 SendMessage 但目标是 workflow runId)
3. workflow 续跑时重新计算 prompt hash + 跳过已 cache 的 agent 调用(已有,但 PAUSED 续跑的语义边界要重新定义)

### 6.7.3 当前能做的最大值 = BLOCKED-退出 + 状态可机器续跑

我 v1 的 BLOCKED-退出已经是 skill 层能做的最大值。可做的微小改善:

- SUMMARY 顶部写"机器可读续跑摘要"(JSON 块):issues.json / verified.json / decision_log.json 全部路径 + 当前 round + escapeRequest type/detail——让用户重启时,主会话能一键读取这些状态注入新 args,把"重新 brief"成本从「重读 SUMMARY 自然语言」压到「JSON 喂回去」
- args 加 `resumeContext` 字段(可选),接受上一 run 的状态 JSON,setup 阶段跳过 smoke 基线 + refs 重持久化(若 hash 匹配则复用)

这两条**也是 skill 层可做**,作为 P2 长期项的"近期可改善"子项。但 PAUSED-续跑本身仍需 runtime 改造。

### 6.7.4 给 skeptic 的诚实回应

skeptic 是对的:**PAUSED 范式更优**。但这超 web-loop skill scope——本研究的输出是 web-loop 的设计建议,不是 Workflow runtime 改造提案。可上报 runtime 维护者(主会话)作长期产品 backlog,但本提案不展开。

## 6.8 最终立场 + 推荐落地路径

### 6.8.1 一句话立场

**用户原话「加入一个 opus agent」是真需求,本研究的诚实结论是:这个需求的 80% 内容(根因 / 工作指导 / 节约 tokens / 提升成功率)由 P0 扩 reviewer schema + mergeIssues 跨轮聚合 + implementer 自报义务覆盖,不需要新 agent;剩余 20%(跨 lens × 跨轮质性综合)用 P1 缩窄版 decision agent 在 stall 退出前一次性触发兜底。直接按用户字面要求每轮加一个 opus decision agent 是过设计,会引入双源真理新故障源。**

### 6.8.2 推荐落地路径(给 final_report 综合)

| 阶段 | 内容 | 谁动 | 何时 |
|---|---|---|---|
| **P0**(立即) | 扩 reviewer schema + mergeIssues 跨轮聚合 + implementer 自报义务(§6.2) | web-loop skill 维护者 | 团队大共识,可立即实施 |
| **观察期** | 跑 5-10 个真 run,统计 P0 落地后 stall 模式是否消失 | 用户 + 自动统计 | P0 后 1-2 周 |
| **P1**(条件叠加) | 我 v2 缩窄版 decision agent(§6.3),stall 触发,3 字段 schema | web-loop skill 维护者 | 仅当 P0 实测不够、且乱撞模式归因为跨 lens × 跨轮质性综合时 |
| **P2.a**(长期) | impl 轮≥2 升 opus(§6.4.1) | web-loop skill 维护者 | 与 P1 独立、可并行 |
| **P2.b**(超 scope) | Workflow runtime PAUSED-await-injection(§6.7) | Workflow runtime 维护者 | 长期产品 backlog,本提案上报但不展开 |
| **退路** | 若 P0 + P1 + P2.a 全实测无效 → 反思 capture STATES 设计或 Workflow 范式边界,非 agent 数量问题 | 用户 | 兜底 |

### 6.8.3 自审(动机性让步检查)

- 团队 3 vs 1 合围压力存在,但 L1-L7 每条让步前都让对方拿出"reviewer / implementer 能等效做"的具体技术机制
- L1-L4(R1)是 diagnostician 用 schema 设计技术性反驳,让得心服
- L5-L7(R2)是 team-lead 在 R2 §A 把"跨轮 / 跨 lens / 多模态"三论据逐一戳穿,我重推后确实答不出独有场景
- §6.3 P1 保留了我 v2 缩窄版作为可选叠加,不是被完全推翻——这正是 team-lead R2 末锁定的"团队共识 + 残留我方价值"双重收口
- §6.6 一句话核心捍卫诚实标"20% 边际增量",不夸大

**结论**:让步是技术驱动,P1 残留是技术驱动,无社交妥协。final_report 可放心引用本节作为 P0/P1/P2 三层方案的设计依据。
