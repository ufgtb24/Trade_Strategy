# Team Brief — web-loop 决策层重设计研究

> **每位 teammate 进场后第一件事:read 本文件**(以及 §3 的关键文件清单),然后 SendMessage 给 `lead` 报自己的初始定位。

---

## 1. 用户原话(verbatim,理解需求看这个)

> 能不能在 web-loop 的 workflow 里面加入一个 opus agent 负责把 workflow 本轮运行得到的问题进行原因分析,并给出下一轮的工作指导,类似与 superpowers 的写 spec 和 writing-plan。这样才能提升代码修改的成功率和针对性,更加聪明,更加高效,更加节约 tokens,不然就像无头苍蝇乱撞。
>
> 如果有必要,可以修改,添加删除现有 agent,重新设计分工。
>
> 一个很重要的问题: web-loop 的 workflow 中的那些 opus agent 到底在干嘛,连这么重要的工作都没人做,那为什么要使用 opus。
>
> 我个人觉得,web-loop 主要从事 web 开发的提升改进,那么 playwright 中一看便知道哪里有问题,最重要的环节是分析问题怎么修改,但是这个恰恰没人做。
>
> 事实上,我在使用 web-loop 工作时,经常遇到一个小小的问题迭代很多轮也改不好的情况,因此才不得不考虑修改 web-loop
>
> 启用 agent team 思考分析我的疑惑,给出可行的 web-loop 改进方案;或者得出关于 workflow 根本不适合用来做 web 迭代的结论。

## 2. 已知背景(不要重新发现)

### 2.1 web-loop 当前架构(skill 内三主体 + 一示例)

- `.claude/skills/web-loop/SKILL.md` — 入口指令(args 表 / 智能入口层 / 红线 / 4 条原理边界)
- `.claude/skills/web-loop/workflow-template.js` — Workflow 脚本模板(setup → iterate → finalize 三阶段)
- `.claude/skills/web-loop/principles.md` — rubric 通用骨架
- `.claude/skills/web-loop/examples/path2.md` — path2 项目特化值集

### 2.2 当前 workflow 内的 agent 分工(刚做完 GOAL 持久化升级)

**Setup**(model 标在括号):
- `pw-selfcheck`(sonnet)— 浏览器自检
- `preflight`(sonnet)— rubric + smoke 基线 + curl healthUrl
- `write-goal`(sonnet)— 原子写 goal.md + goal.json

**Iterate**(每轮):
- `impl-<rtag>`(sonnet)— **implementer**,改代码 + commit
- `smoke-<rtag>`(sonnet)— 跑 smokeCmd
- `rollback-<rtag>`(sonnet,仅 smoke 红)— git checkout --.
- `refresh-<rtag>`(sonnet)— 按 kind 三档刷新(frontend HMR / backend restart / data reload)
- `capture-<rtag>`(sonnet)— 驱浏览器截图 + stateDumps probe
- `capture-fallback-<rtag>`(sonnet,仅 MCP 不可用)— 退脚本截
- `review-<ux|func|code>-<rtag>` × 3 并行(**opus**)— 看 PNG + diff,判 pass/fail,写 issues + verified
- `persist-<rtag>`(sonnet)— 写 issues.json / verified.json / round_NN.md

**Finalize**:
- `finalize`(**opus**)— 写 SUMMARY.md(4 节:GOAL/参考图/待补 STATES/已知 risk + 退出信息)

**关键观察**:opus 只用在 reviewer × 3 和 finalize(1)。每轮 4 个 opus 调用,全是裁决(pass/fail)和总结,没有任何 agent 做"为什么没改好 / 下轮该怎么改"的根因分析。implementer 直接收上一轮 must 列表,自己想办法修。

### 2.3 刚做完的 GOAL 持久化升级(本次研究的直接上下文)

- 设计文档:`docs/research/2026-06-19_web-loop-goal-persistence/final_report.md`(+ status_analysis / mechanism_design / skeptic_review)
- 实施 plan:`docs/superpowers/plans/2026-06-19-web-loop-goal-persistence.md`
- 已落 14 commits(`3e5bdca..e5ad23e` 在 `bo` 分支,未并 master)
- 主要新增能力:
  - args.goalSubgoals 拆显式子项(reviewer 逐条复核 + 收敛判据加严要求全 GOAL 子项 coveredSubgoals 覆盖)
  - args.refImages 多 role(goal / baseline / anti-example),主会话「智能入口层 §2c」持久化到 `<workdir>/refs/`,reviewer 按 role 三档差异化对照
  - reviewer prompt 14 段重排 + ⚠⚠ evidence 4 类 + goalEcho 反锚定 + lens 分级
  - verifiedLog.coveredSubgoals 跨轮聚合,收敛=`openMust==0 && allSubgoalsCovered`

**这次升级解决的是"reviewer 越深只盯 must / 视觉直觉无传递通道 / implementer 轮 ≥2 退化为修补匠"三条结构性漂移。但用户的新质疑是:漂移修了,根因分析依然没人做,该怎么办。**

### 2.4 用户真实痛点(必须装在脑子里)

> 我在使用 web-loop 工作时,**经常遇到一个小小的问题迭代很多轮也改不好的情况**。

这是研究的现实底色,不要绕开:
- "小问题"= reviewer 看一眼就能描述清楚的视觉/功能瑕疵(布局崩、按钮不响、颜色错)
- "改不好"= 多轮 must 翻来翻去,implementer 改一下又破一点,或者一直命中不到真根因
- "迭代很多轮"= 已超 STALE_ROUNDS(默认 2)?如果是,设计上应该已 stalled 退出——为什么用户感觉一直在跑?需要拆。也可能是 reviewer 提"新的等价 must",台账状态机不识别为重复

## 3. 关键文件清单(进场必读)

| 文件 | 用途 |
|---|---|
| `.claude/skills/web-loop/workflow-template.js` | Workflow 脚本(全量),agent 分工骨架 |
| `.claude/skills/web-loop/SKILL.md` | skill 入口指令 |
| `.claude/skills/web-loop/principles.md` | rubric 通用骨架 |
| `.claude/skills/web-loop/examples/path2.md` | path2 特化(states / refresh / rubric 占位) |
| `docs/research/2026-06-19_web-loop-goal-persistence/final_report.md` | 最近一轮升级的设计文档,理解为什么没加决策层 |

可按需读的次要文件:
- `docs/superpowers/plans/2026-06-19-web-loop-goal-persistence.md` — 实施 plan(174 task 步骤拆解)
- `CLAUDE.md` — 项目宪法(agent team 协议、subagent 模型选择规则等)

## 4. 团队组成(4 teammate + 1 lead)

| 角色 | 名字 | 模型 | 任务 |
|---|---|---|---|
| Lead(coordinator) | (main session) | opus | 协调、综合、最终写 final_report.md |
| Architect | `architect` | opus | 解释当前 web-loop 的 opus 分工合理性,answer "opus 在干嘛" |
| Diagnostician | `diagnostician` | opus | 拆"小问题改不好"的真实根因(不止 missing decision layer) |
| Redesigner | `redesigner` | opus | 在当前 Workflow 框架内设计加决策层方案,具体到 prompt 草案 + agent 时序 |
| Skeptic | `skeptic` | opus | 对立结论:Workflow 是否根本不适合 web 迭代,argue 转 agent team 或混合 |

## 5. 沟通协议

- **互相通信全部走 SendMessage**(按 name 寻址,不要发字面消息)。
- 你的 plain text 输出**不**被其他 agent 看到——必须 SendMessage 才传递。
- 第一轮:每位 teammate read 本简报 + 上面的关键文件,然后 SendMessage 给 `lead` 报自己的初始定位(3-5 条 bullet)。
- 中段:lead 把你的定位转给其他 teammate,他们会回应你的论点。准备进行 1-2 轮对抗辩论。
- 收尾:lead 综合所有人观点写 `final_report.md`。lead 可能在收尾前问你"你那 part 还有要补的吗"。

## 6. 工具调用纪律(全员必读)

> 调工具纪律:中途消息正文至多一句状态行(无代码 token、不预告"我去调用 X"),随后直接发调用;长篇解释只放不再调工具的收尾消息。若发现自己把调用写成了正文文字,不要停笔,在同一条消息里立即发出真正的调用。

## 7. 最终产物

- **必须**:`docs/research/2026-06-21_web-loop-decision-layer-redesign/final_report.md`(lead 综合写)
- **可选**:每位 teammate 在该目录下落自己的中间文档(如 `architect-position.md` / `diagnostician-rootcauses.md` / `redesigner-proposal.md` / `skeptic-counter.md`)。不为凑数,有就有、没有不写。

final_report.md 必须覆盖:
1. **opus 当前在干嘛**——回答用户的"为什么用 opus"质疑(architect 主笔)
2. **小问题改不好的真实根因**——可能不止决策层缺失(diagnostician 主笔)
3. **方案 A:Workflow 内加决策层**——具体到 prompt 草案、时序、token 预算(redesigner 主笔)
4. **方案 B:部分/完全替换 Workflow**——agent team 或混合架构(skeptic 主笔)
5. **推荐**——综合判断,user 接下来该做什么(lead)

## 8. 红线

- **不写代码、不动 web-loop 主体三文件**——本次是研究,只产文档。
- 文档不留到对话上下文里,落盘为准(`docs/research/2026-06-21_web-loop-decision-layer-redesign/`)。
- 不要把"小问题改不好"无脑归因为"缺决策层"——用户的痛点可能有多个并存原因,诊断要诚实。
- skeptic 必须真 skeptic,不能客气;redesigner 不能为了"有方案"而塞一个臃肿设计。
