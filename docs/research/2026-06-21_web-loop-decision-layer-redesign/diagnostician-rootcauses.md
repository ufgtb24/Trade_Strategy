# Diagnostician — "小问题改不好" 根因诊断清单

> 供 final_report.md 综合引用。
> 范围:从用户实测视角("一个小小的问题迭代很多轮也改不好")反推 web-loop 内的真实根因,不预设"加决策层"为唯一答案。
> 方法:逐条根因 + 贡献度 + "加决策层能否解决" + "更高 ROI 修法"。
> Meta 观察:简报 §3 引用的 `docs/research/2026-06-19_web-loop-goal-persistence/final_report.md` 目录为空,GOAL 持久化升级的设计意图只能从 `workflow-template.js` 内嵌注释 + SKILL.md §2c + principles.md 推断 — 本清单据此构建。

---

## 1. 三大主根因(按用户实测视角的真实贡献度排序)

### 根因 #A — symptoms→fix 翻译层缺失(决策层缺失的真正形态)

- **贡献度**:**高**(直接命中用户痛点)。
- **机制定位**:`workflow-template.js:256-270` implementer prompt 把 `openIssues.filter(severity==="must")` 当 JSON 原样喂入,无任何"为什么上一轮没修好"的环节。reviewer 写的 must 是 `{title, severity, evidence, requiredStates}` — `evidence` 描述的是"现状是什么"(K 线被挤到底部 / grid 占视口 30%),不是"为什么是这样"(markers `start_idx` 被 ECharts 当 y 维污染价格轴 / ResizeObserver 在某 state 未触发 / CSS 优先级被遮蔽)。
- **后果**:implementer 拿症状只能猜根因 → 猜错则下一轮 reviewer 写出**同症状描述**(现象没变)→ `mustStaleStreak` 累加 → 3 轮 stalled 退出。用户主观感受 = "我看到 reviewer 都说清楚了 K 线挤,怎么改了 3 轮还挤"。
- **加根因分析 agent 能解决吗**:能,但**不必新建 agent**。最高 ROI 是扩 reviewer schema 让 code lens 在产 verdict 时**顺手**出 `rootCauseHypothesis + affectedFiles`(opus 已在读 diff,能力闲置)。
- **真正的修法**(主推):
  - `REVIEWER_SCHEMA.issues` 增 3 字段:`rootCauseHypothesis: string`(单句机制,code lens 必填)、`affectedFiles: string[]`("path:line" 格式,code lens 必填)、`suggestedFix: string | null`(可选,implementer 可推翻)。
  - implementer prompt 强制 `Read affectedFiles 的具体行号 + 回讲一句"我理解根因是 X、要改的是 Y"`,作为"根因落地到代码现场"的硬钩子。

### 根因 #B — reviewer 的 schema 把"看到现象" 误锁为"评分上限",诊断能力被 principles 第 5 条副作用闲置

- **贡献度**:**高**(与 #A 是同一现象的两面:#A 谈下游怎么消费,#B 谈上游为什么产不出根因)。
- **机制定位**:`principles.md` 总则第 5 条 "reviewer 指出缺陷,不设计方案"本意防越权,但**副作用**是把 reviewer 锁死在症状层 — `REVIEWER_SCHEMA.issues` 只让填 title/severity/evidence/detail,**无 `rootCauseHypothesis` 字段**。reviewer 是 opus、有 git diff 访问权(`reviewerPrompt brief.code` 段)、有源码 Read 权,**完全有能力诊断机制**,只是 schema 不要这条信息。能力闲置 = opus 算力浪费 = 用户原话"为什么用 opus"的精确答案。
- **后果**:每轮 4 次 opus(reviewer×3 + finalize)只做"评分",**没有任何 opus 调用做诊断**;诊断职责落到 sonnet implementer 头上 → 模型能力错配。
- **加根因分析 agent 能解决吗**:**部分能** — 独立 decision agent 能补做诊断,但是"补做"而非"原产",且引入双源真理风险(decision agent 看 3 reviewer 文本 + 重读证据,可能与 reviewer 自己判定冲突)。
- **真正的修法**(主推,与 #A 修法合并):同上 — 扩 schema 让根因在 reviewer 产 verdict 那一刻**单源**产出,不再需要独立 agent "再翻一遍"。
- **关键约束**:**只让 code lens 出根因**,ux/func 仅出 evidence。理由:code lens 是唯一读 diff 的 lens,根因机制本就是它的 home turf;ux/func 出根因纯属越权 + 三路同出必冲突 + implementer 要自己 merge(architect 的 ChainOfImprovement 方案的真实失败模式)。

### 根因 #C — `mustStaleStreak` 的字符串去重脆,reviewer 换表述就重置台账 → 无限迭代直至 max-rounds

- **贡献度**:**中**(直接解释用户原话"很多轮"为什么不会被 STALE 兜住)。
- **机制定位**:`workflow-template.js:106` `issues.find(x=>x.lens===v.lens&&x.title===it.title&&...)` — 纯字符串相等比对。reviewer 这轮写 "K 线 grid 被压缩到视口 30%",下轮写 "K 线垂直高度不足导致蜡烛拥挤" — 同一 bug,**新 issue id 入台账,`mustTransitions` 计数 + 1 → `streak` 归零**。STALE 状态机本意 "修不动就停",实际 "换说法就刷新"。`STALE_ROUNDS=2` 形同虚设。
- **后果**:用户体感"一个小问题反复几轮还在"。**这是设计 bug,不是 prompt 调优问题**。
- **加根因分析 agent 能解决吗**:**不能**。decision agent 解决的是"诊断不够深",而 #C 是台账机制本身的脆性 — 即使每条 issue 都附带完美根因,只要 reviewer 用新 title 重写,台账还是会判定为"新进展"。
- **真正的修法**(P0 必修,独立于 #A/#B):
  - 强制每轮 reviewer 在 `knownIssuesStatus` 表态时,只能引用现存 id(`matchesIssueId`),不允许在 `issues` 里新立同 lens 同语义的问题。
  - 或:在 `persist` agent 之前插一个 sonnet 微 agent 做"两 issue 是否同根因"的语义去重(成本远低于独立 decision agent)。

---

## 2. 反对的"看似根因"

| 编号 | 简报种子 | 我的判断 | 理由 |
|---|---|---|---|
| #3 | STATES 清单不全 | **不是当下主因** | path2 examples §2 已显式列 5 态 + canvas 取证须知 + probe 示例,GOAL 持久化升级也把 STATES 缺失绑到 `requiredStates` 字段。当前残留问题是反映在 SUMMARY "## 待补 STATES" 节里的、不是无声 漂移。 |
| #4 | probe 缺失 | **不是当下主因** | 同 #3 — `principles.md` 第 8 条已明令 "stateDumps 与截图同级证据"。当前 path2 已有 probe 实证(2026-06-12 教训)。 |
| #5 | refresh 路径错 | **低贡献** | `workflow-template.js:282-294` 已三档分流 + impl.md 首行 `kind` 锚点 + `refresh.md` 落盘。失败有 `infra-${rtag}` must 兜底。 |
| #6 | implementer 上下文窄 | **正确诊断的一半** | 上下文窄是真问题,但**根因不在"窄"本身,而在"喂的内容是症状不是根因"**。窄 + 喂根因(扩 schema 后)= 可消费;窄 + 喂症状(现状)= 盲改。修法是 #A,不是给 implementer 加权限或扩上下文。 |
| #7 | visual feedback 不准 | **被 GOAL 持久化机制处理过** | reviewer 是 opus 多模态、Read PNG 直接看,加 `goalEcho` + 子项 evidence 锚点 + role-tagged refs(`workflow-template.js:120-122` 三档 refs 处理),视觉判定精度已不弱。 |
| #8 | verified 机制误锁 | **设计上已规避** | `workflow-template.js:371-377` `coveredThisRound` 按本轮 verified 重算,不存在"前轮 verified 就锁死"。这条担忧不成立。 |
| #10 | capture sandbox 看不到关键交互 | **属 #3/#4 同一族** | 已被 STATES + probe 机制覆盖。 |
| #11 | 伪小问题(架构耦合) | **拒绝当兜底解释** | 无法证伪 + 把它当解释会让讨论失焦。用户原话的"小小的问题"是观察,不是判断 — 不要替用户重新定义他的痛点。 |

---

## 3. 收敛时未充分讨论的两条结构性边界(skeptic 提出,我承认但拒绝用作 #A/#B/#C 否决理由)

这两条是**工具范围天花板**而非工具内部低效;用户痛点 99% 落在天花板之下,A/B/C 修了就能拿大头收益。

1. **args 启动冻结**:`SKILL.md` 红线 "refs 持久化必须主会话干"(`~/.claude/image-cache/<uuid>` 对 spawn subagent 不可见)+ workflow 启动后无外部注入通道。后果:跑到 r4 时用户发现新参考图 / 新约束,只能起新 run。`refs/` 是主会话「智能入口层 §2c」预写、workflow 不重写(`workflow-template.js:229`)。
2. **无打断权**:workflow 是无监管长跑,即使 reviewer 发现"GOAL 拆错了"(`SKILL.md` 红线 §2c 末尾的 "single point of failure" 风险),也只能按错的 GOAL 继续跑;只有 finalize 时在 SUMMARY 的"## 已知设计 risk"节兜底提示人工复核。

**对最终方案的含义**:扩 schema + 语义聚类是 P0,不解此 2 条结构性边界;skeptic 的 (b) 增量(stalled 时降级到 agent team / 人工)是 P1 兜底,真正回答了"探索性 bug 修复"的范围天花板。

---

## 4. 一句话主张(供 final_report 引用)

> 当前 web-loop 每轮 4 次 opus 全用于评分和总结,**没有任何 opus 在做诊断**;扩 reviewer schema 让 code lens 在产 verdict 那一刻**顺手**出根因 + 影响文件 + 可选 fix,opus 算力首次被用满,零新调用、零双源真理风险、token 净降。这同时回答了用户原话里的"为什么用 opus" / "怎么修才不无头苍蝇" / "节约 tokens" 三问。
>
> 与扩 schema 并列必修的是 `mustStaleStreak` 的语义聚类(强制 `matchesIssueId`),否则 reviewer 换表述就刷新台账,STALE 退出形同虚设 — 用户原话"很多轮"的直接来源。
>
> 这两条修完之后,用户痛点 99% 落地解决;剩下的"args 启动冻结 / 无打断权"是工具范围天花板,需 skeptic 的 (b) 兜底,不是扩 schema 的范畴。
