# skeptic-counter — 反框立场与未让步论据

> 本文档由 skeptic 团队成员落,聚焦经过三轮辩论后**未让步的根本立场** + 关键技术细节,供 lead 综合 final_report 时引用。让步部分(检查点 A 强制 gate / impl 升 opus 立即生效 / 重 runtime 改动)不在本文档,已收回。

---

## 1. 根本立场(未让步):Workflow 适合"自动化质量门",不适合"探索性 bug 修复"

### 1.1 论点

web-loop 当前的产品-市场契合度有一处错位:它的架构(deterministic JS 控制流 + args 启动冻结 + 全自动多轮)优势适合**已知验收标准下的多轴回归扫描**;但用户实际使用场景是**视觉/功能一眼能看出的小 bug 修复**——后者根本不该自动多轮迭代。

把任务按"是否需要中途改变方向"二分:

| 类别 | 例子 | 是否适合 workflow |
|---|---|---|
| **自动化质量门** | 发布前回归扫一遍 5 个交互轴的视觉 + console + 代码 diff;一次性把"GOAL 子项全覆盖 + 无 console error + 无回归"作为客观判据跑通 | ✓ 适合 — 此时 reproducible / 跨轮台账 / 文档化 SUMMARY 真值钱 |
| **探索性 bug 修复** | "K线挤在下方"、"按钮压住了"、"侧栏被撑没"——用户看一眼就知道问题在哪,只是不想自己改代码 | ✗ 不适合 — 用户本来就在等结果,自动多轮的"reproducible / 不依赖人在循环"在这里**用不上**,反而代价是"args 冻结无中途纠错" |

用户原话"经常遇到一个小小的问题迭代很多轮也改不好"——形容词"小小"不是说"GOAL 简单",而是说"在用户看来一目了然"。**一目了然的视觉/功能 bug 用全自动多轮去解,本身就是工具与场景错配**。

### 1.2 给用户的明确建议(请 final_report 末尾"使用建议"节收入)

何时**该**用 web-loop:
- 发布前回归扫描(多 STATES × 多 lens × 验收标准客观沉淀)
- 多人协作时需要文档化的 SUMMARY / 跨轮台账作为评审输入
- 一次性大改后跑兜底验收(用户不想盯,愿意等机器自动跑)
- 验收标准能用文字 + 像素阈值精确表达(rubric 写得出)

何时**不该**用 web-loop,换"用户 + 主会话 + sonnet implementer + tom 偶尔召唤"的人在回路:
- 视觉/功能一眼能看的小 bug(用户看截图比 reviewer 快)
- 验收标准本身依赖主观判断("看着舒服"、"颜色搭配自然")
- 当前任务进入第 3 轮还没收敛——3 轮没改好,第 4 轮多半也改不好,**这是 web-loop 产品上限,不是参数问题**
- 用户本来就在浏览器前看着——workflow 的 long-running 优势在这里反而是劣势

这一节的价值:**与其优化工具让它在场景错位时少痛,不如让用户明确知道何时该弃用它**。这是用户友好,不是工具悲观主义。

### 1.3 与团队共识的关系

团队共识(扩 schema + 3 判据 PAUSED + impl 升 opus 长期 + checkpoint 软鼓励)是**在保持 workflow 范式前提下的最大化优化**——这套合体方案我接受。但即便它全部落地,**不能消除 1.1 的场景错位**:对探索性 bug 修复,workflow 永远不如人在回路快。

合体方案的意义是"workflow 在适合的场景下更好用 + 在不适合的场景下早点 PAUSED 退给人"——这后半句正是 (b) 混合架构的精髓被吸收。final_report 须显式承认:**workflow 在探索性 bug 修复场景下的根本极限,合体方案无法消除**。

---

## 2. 三条机检判据(详细算法)— P0 落地依据

### 2.1 设计原则

不靠"3 轮硬数"的拍脑袋阈值;基于 issues 台账已有数据通道,**零新 agent、零新 reviewer 字段**(扩 schema 那条 diagnostician 主笔的字段是另一回事;本节判据**完全基于现有 issues / history 数据**)。任一触发即写 paused.md、主循环 break、保留状态等用户。

### 2.2 判据 1 · 同一 must 跨轮"修复 → 回归"震荡 ≥ 2 次

**信号定义**:某 must id 状态轨迹存在 `open → fixed → regressed → open` 至少一次,**且** `regressionCount ≥ 2`。

**含义**:implementer 在两个修法之间反复横跳——每改一处破另一处。这是 **②多 must 互冲** 的硬证据(execution-end 因果建模不足)。

**已有数据通道**:
- `issues[i].status` 状态机(open / fixed / regressed,workflow-template.js mergeIssues 维护)
- `issues[i].regressionCount`(workflow-template.js:104 已实现 `h.regressionCount=(h.regressionCount||0)+1`)

**检测代码草案**(主循环末尾,verdicts 处理后):
```js
const oscillating = issues.filter(i =>
  i.severity === 'must' && (i.regressionCount || 0) >= 2
);
if (oscillating.length > 0) {
  triggerPause('oscillation', { issues: oscillating.map(i => i.id) });
}
```

**触发后**:paused.md 顶部段落清单震荡的 must id,提示用户"implementer 在多个修法之间反复横跳——可能存在隐藏约束冲突,建议人工诊断真根因后注入 hint。"

### 2.3 判据 2 · 同 lens 新 must 增速 ≥ 老 must 修复速

**信号定义**:对每个 lens,累计 `newMust(round=1..n)` ≥ 累计 `fixedMust(round=1..n)`,**且**最近 2 轮该差值 `(newCum - fixedCum)` 单调不降。

**含义**:每修一个旧 must 就引入一个新 must,implementer 在原地踏步——但因为新 must id 不同,mustStaleStreak 不计(这是当前 stalled 检测的盲区)。

**已有数据通道**:
- `history[i].newMust`(workflow-template.js:355 已记录)
- `issues[i].status === 'fixed' && issues[i].lens` 推导 fixedMust

**检测代码草案**:
```js
const lenses = REVIEW_LENSES;
for (const lens of lenses) {
  const newCum = history.reduce((s, h) =>
    s + (h.verdicts?.find(v => v.lens === lens) ? h.newMust : 0), 0);
  const fixedCum = issues.filter(i =>
    i.lens === lens && i.status === 'fixed').length;
  if (newCum >= fixedCum && newCum >= 3 && round >= 3) {
    // 还要看最近 2 轮该差值是否单调不降:
    const last2Diff = history.slice(-2).map(h => /* recompute */);
    if (last2Diff[1] >= last2Diff[0]) {
      triggerPause('treadmill', { lens, newCum, fixedCum });
    }
  }
}
```

**触发后**:paused.md 标"原地跑步机"——某 lens 新 must 增速持平/超过修复速,implementer 在无效改动,建议用户改 rubric 或细化 must 描述。

### 2.4 判据 3 · 同子项 (matchesSubgoal) 在 ≥2 轮内 unverifiable

**信号定义**:某 GOAL 子项 id 的 unverifiable issue 连续 ≥2 轮存在,且这些 issue 的 `requiredStates` 字段非空且重叠。

**含义**:capture STATES 漏了一个必要状态,workflow 内**无法靠 implementer 解决**——这是 ① 信息缺失型的硬范围外,必须人补 STATES。当前 unverifiable 标志本身只防"误判 fail",没有触发任何后续动作,等于把信息浪费了。

**已有数据通道**:
- `issues[i].unverifiable`(workflow-template.js 已实现)
- `issues[i].requiredStates`(REVIEWER_SCHEMA 已声明)
- `issues[i].matchesSubgoal`(REVIEWER_SCHEMA 已声明)

**检测代码草案**:
```js
const unvBySubgoal = {};
for (const i of issues) {
  if (i.unverifiable && i.matchesSubgoal && (i.requiredStates || []).length) {
    (unvBySubgoal[i.matchesSubgoal] ??= []).push(i);
  }
}
for (const [sg, list] of Object.entries(unvBySubgoal)) {
  // "连续 ≥2 轮存在"判据:这些 issue 的 lastSeenRound 跨度 ≥ 2 且最近 1 轮命中
  const rounds = new Set(list.map(i => i.lastSeenRound));
  if (rounds.size >= 2 && rounds.has(round)) {
    const allStates = new Set(list.flatMap(i => i.requiredStates));
    triggerPause('missing-states', { subgoal: sg, requiredStates: [...allStates] });
  }
}
```

**触发后**:paused.md 列"GOAL 子项 G<sg> 连续 N 轮 unverifiable,缺 STATES = [...],workflow 无能力补"——指引用户回主会话「智能入口层」补 STATES 后重启 run(此 case 必须重启,因为 STATES 是 args 字段、冻结)。

### 2.5 PAUSED 触发后的 workdir 协议(P0 最小落地)

**写 paused.md**(workflow 主循环 break 前最后一步):
```markdown
# PAUSED · runtag=<rtag> · round=<N>
触发判据:<oscillation|treadmill|missing-states>
触发细节:<JSON 形式的判据细节,如震荡 must id 清单>

## 当前 open must
<JSON>

## 当前 reviewer 最新 rootCauseHypothesis(扩 schema 落地后填)
<text>

## 主会话需要的动作
请审阅本轮 issues + 截图(<SHOTS_DIR>/<rtag>_*.png),然后:
- 若问题在 args(rubric/STATES/refImages 错位)→ 改 args 启动新 run
- 若问题在 implementer 走偏 → 在本 workdir 写 human-hint-r<N+1>.md(自然语言一段),然后 Workflow({ resumeFromRunId: "<rtag>" }) 续跑
- 若放弃 web-loop → 转主会话 + sonnet implementer 手工修
```

**workflow 检测 human-hint-r<N+1>.md**(iterate 循环顶端):
- 若存在,Read 内容 + 在 implementer prompt 顶部插入 `【用户人工指令(优先级最高)】<内容>` 段
- 执行完后 `mv human-hint-r<N+1>.md human-hint-r<N+1>.consumed.md` 防止下轮重复消费

**零 runtime 改动**:这套协议完全基于现有 workdir 文件 + 现有 resume 机制(SKILL.md 监控收尾节已说同 session resume 可用)。

---

## 3. PAUSED-await-injection(P2 长期诉求 · 跨 workflow runtime)

### 3.1 P0 的天花板

P0 的"workdir 文件通道 + 同 session resume"有两个不让步的限制,但都属于 runtime 改动范畴,**超 web-loop scope**,故放 P2:

1. **同 session 限制**:SKILL.md 明确说 `resumeFromRunId` 仅同 session 有效。用户如果关了 IDE 或换电脑,paused 的 run 就废了——只能重启新 run(失去已 verified 的 GOAL 子项进度)。
2. **用户必须主动触发 resume**:workflow break 后,如果用户没及时看到 paused.md(没盯监控),状态就僵持。理想是 workflow 进入 "yield" 状态,等到用户 SendMessage 自动续。

### 3.2 真打断 vs 退出 vs 续修

|  | 退出 | 打断(P0 实现) | 续修(P2 理想) |
|---|---|---|---|
| workflow 状态 | terminate | break + workdir 留档 | yield · 等 SendMessage |
| 用户上下文成本 | 重启 run,r1 重做 | 保留已 verified,resume 续跑 | 同打断,但用户感知"workflow 还在,只是停下等我" |
| 跨 session 容灾 | N/A(新 run) | ✗ 限同 session | ✓ runtime 持久化 yield 态 |
| 用户主动 vs 被动 | 主动重启 | 主动 resume | 被动响应(workflow 主动通知用户) |
| 实施成本 | 0(纯 prompt 字段) | 小(workdir 协议) | 大(runtime 改造) |

**P0 已经从"退出"升级到"打断"——这是真增量**,化解了 redesigner BLOCKED-for-human 的执行不彻底。**但 P2 才是理想形态**,final_report 应记录这条长期诉求,因为它对应"真正的人在回路"。

### 3.3 推动机制

P2 不在 web-loop scope 内能解决,需要跨 skill 推动 Workflow runtime 改造:
- runtime 支持 "yield" 态:workflow 在某个 agent 调用后可声明 `await user.injection(timeoutMs)`,runtime 持久化整个 workflow 状态(同 resumeFromRunId 机制),收到对应 SendMessage 后恢复执行。
- web-loop 是首个会使用这个能力的 skill;说服点 = "现在所有 workflow 都是 fire-and-forget,加了 yield 就能支持人在回路"——这是 superpowers 框架的范式扩展。

**风险**:runtime 改动影响所有 workflow,需要做向后兼容设计。final_report 仅记录诉求,不细化方案。

---

## 4. 团队剩余分歧(诚实记录)

lead 已确认 architect 与 skeptic 在 **impl 轮≥2 升 opus 的时机**上仍有时间轴分歧:

- **architect 主张**:A 路径(扩 schema)实测完才能判断升 opus 是否必要,以及触发条件应在 mustStaleStreak ≥ 1 时切换。这是 evidence-first 的工程纪律。
- **skeptic 主张**:用户痛点已经发生,等 A 路径实测可能拖月级时间。如果 ② 多 must 互冲在 A 实测时仍是主因,**已经在 P0 部署"判据 1 震荡触发 PAUSED"了**——这条已经替代"升 opus"作为 ② 类问题的临时止损。所以 architect 的 evidence-first 我接受。

**分歧实质上已收敛**:P0 的判据 1 + paused 接管了 ② 类问题的临时应对;升 opus 是 ② 类问题的彻底解决方案,放 P2 等数据。final_report 可以写"团队对升 opus 的时间轴有理性分歧,但 P0 已经提供临时止损,分歧不阻塞落地"。

---

## 5. 不让步清单(一句话汇总,供 final_report 引用核对)

| 立场 | 落地 |
|---|---|
| Workflow 不适合探索性 bug 修复(根本) | final_report 末尾"使用建议"节 |
| 加独立 decision opus agent 不该做 | P0 拒绝,理由 = 零增量 over diagnostician 扩 schema |
| 三条机检判据替代硬数 2 轮 STALE | P0 必落,§2 已给完整算法 |
| PAUSED-await-injection 是理想形态 | P2 记录,不阻塞 P0 |
| 升 opus 必须有触发条件(mustStaleStreak ≥ 1)而非整体切换 | P2 记录时机分歧已收敛 |

---

> 本文档结束。lead 综合 final_report 时直接引用本节论据 / 算法,不必复述。我已挂机。
