# Architect Position — web-loop 现有 opus 分工的辩护与短板

> 角色:为现有 web-loop 的 opus 分工合理性辩护(诚实地)。不是 cheerleader,该承认的短板直接承认。
> 上下文源:`.claude/skills/web-loop/workflow-template.js` · `.claude/skills/web-loop/SKILL.md` · `docs/research/2026-06-10-web-loop-agent-token-audit.md`(`docs/research/2026-06-19_web-loop-goal-persistence/` 目录在 `-bo` 这边为空,文档实际在另一个 worktree;以 SKILL.md §核心机制 + workflow 代码内的 GOAL 持久化实现作替代上下文)。

---

## 1. 当前 opus 调用图

每轮固定 4 个 opus 调用 + 收尾 1 个:

| label | 位置 | 模型 | 真实工作 |
|---|---|---|---|
| `review-ux-rN` | workflow-template.js:333-341 | opus | 多模态读 PNG + 跨轮台账推理 + GOAL 子项绑证据 + 反锚定 |
| `review-func-rN` | 同上 | opus | 读 console/网络/probe 文本 + 子项语义追溯 + 跨轮台账 |
| `review-code-rN` | 同上 | opus | 读 git diff + 找 bug/红线/回归 + 截图旁证 |
| `finalize` | :411-430 | opus | 写 SUMMARY.md 4 节(GOAL/refs/待补 STATES/risk + 退出信息) |

没有显式 model 字段的 setup/iterate 机械 agent(smoke / refresh / capture / pw-selfcheck / preflight)在 opus session 下**继承** opus —— 这是 2026-06-10 token-audit P0 已点名的配置遗漏,**不是设计**,与本研究无关,下面不再讨论。

---

## 2. 三个 reviewer × opus —— 真正在做什么(非"评分员")

把 reviewer 当"打分员"是对现有 prompt 的误读。看 `reviewerPrompt`(:113-167)+ `REVIEWER_SCHEMA`(:179-189),它干的活由三层叠加:

### 2.1 多通道证据综合(非可降级)

reviewer 同时摄入 4 类证据:
- **PNG**(多模态)—— ux 全图必读;func 按需 Read verifiable_via=screenshot 的子项对应图;code 仅在 diff 看不出渲染影响时读。
- **console / pageError / failedRequests 文本**—— func 必判 must 的硬证据。
- **stateDumps probe**(:296-297)—— canvas/WebGL 类无 DOM 界面下,**截图盲就靠它**(SKILL.md §2b 已坐实"光靠截图取证会盲"的教训)。
- **git diff** —— code 主跑道。

任务不是分别读、是**把多通道证据按 lens 挑出可定位标识绑到 GOAL 子项**(prompt:144-149 的 4 类 evidence 强制要求 + 反"看起来满足"修辞)。这一步是开放式判断 —— sonnet 边界判断弱,在"什么是 evidence、什么是修辞、像素特征怎么描述"这层不稳。

### 2.2 跨轮台账状态机推理(非可降级)

mergeIssues(:80-111)是确定性 JS,但**喂给它的指针由 reviewer 给**:
- `matchesIssueId` —— reviewer 必须认出"本轮看到的这条 ≡ 上轮台账某条",才能触发回归检测(fixed→regressed)。认错=漏报回归或误产生新 issue 双胞胎。
- `knownIssuesStatus[i].stillPresent` —— 反锚定铁律(:161-163):必须用**本轮**证据(截图文件名/字节/stateDumps/manifest 字段)表态,禁止沿用上轮表述。这是个"看了再判"的工作,不是"复制旧结论"。
- `matchesSubgoal` + `requiredStates`(:152)—— 把 unverifiable 子项绑到下次 run 该补哪个 STATES,是 actionable 信号源。

这套是**有判断后果不对称**的活:漏判 must = bug 出厂、误报 must = 多一轮。sonnet 在跨轮文本一致性 + 状态机指针稳定性上观察到的劣化是实例化的,不是理论。

### 2.3 反锚定(非可降级)

`goalEcho`(:155-156)+ `coveredSubgoalIds` —— reviewer 自复述 GOAL + 列出本轮覆盖的子项 id 集合,**注意力归位 GOAL**。这一字段不进收敛判据,纯仪式,但本身是 GOAL 持久化升级的核心抗漂手段(治"reviewer 越深只盯 must"的结构性漂移)。

仪式的价值在"开始判定前调用思考层 attention",sonnet 的 attention 自校准弱可观察。

### 2.4 token-audit tom 第一性原理裁断的独立确认

2026-06-10 token-audit 在 opus/sonnet 二元判据下独立得出同一结论:
- ux 真读图(判据①多模态 + ②开放式把关)—— 不建议降。
- code 读 diff 找 bug —— "**Opus 4.8 相对 sonnet 增量最大的能力靶心**"—— 不建议降。
- **func 是唯一有降级正当性的口子**(主读 console 文本)—— 可试 sonnet,代价 = 偶发 GOAL-追溯漏判由 holistic 兜底。

这是另一轮 agent team 在不同任务框定下独立做的判断,结论与我一致。

---

## 3. finalize × opus —— 诚实承认 close call

finalize(:411-430)主体是机械汇总:
- `finalizeGoalBlock` 从 `subgoalCoverage` 推 ✓/✗/? —— 纯查表。
- `finalizeRefsBlock` 从 `REF_IMAGES` 转字符串 —— 纯遍历。
- `finalizeMissingStates` 从 `issues.filter(unverifiable && requiredStates)` 转字符串 —— 纯过滤。
- 退出信息(`exitReason` / `leftoverConfirmed` / `leftoverUnverifiable`)—— 全由脚本预算好,prompt 内插。

真有"判断"成分的只两条:
1. "**不得把 stalled/max-rounds 伪装成 converged**" 的完整性约束(:428)。
2. 4 节叙述的连贯性 / 排版判断。

**承认:这一处用 opus 是 close call,sonnet 化空间客观存在**。token-audit 当时标"opus 维持(close call)",理由是"单次调用、极廉",但这是成本论据、不是能力论据。从能力维度,sonnet 完全够干这活。

这是 architect 立场内**唯一没法用能力论据辩护的 opus 用例**。如果用户要砍一个 opus 调用,先砍这里。

---

## 4. 当初为什么把 opus 放在 reviewer 而非 implementer / 独立决策 agent

### 4.1 项目宪法层

CLAUDE.md 明令"**Implementer 一律 sonnet、Reviewer 一律 opus**"—— 这是项目级跨 skill 红线、非 web-loop 私有选择。底层逻辑:

**reviewer-as-thinking-layer**:把开放式判断(GOAL 满足度判定 / 回归识别 / 设计偏离 / 完整性 / 反锚定)前置到把关层;implementer 收一个**收窄的 must 列表 + verified 摘要**执行,刚好契合 "**impl = 执行既定方案、reviewer = 开放式把关**" 的非对称分工。

这套范式 path2 长期跑通(参见 `MEMORY.md` 里 path2 重构 9 个 plan 的 spec/quality 双审 + finalize holistic 记录,所有 reviewer 一律 opus)。

### 4.2 web-loop 当初没加"独立决策 agent" —— 设计取向是什么

设计假设:**reviewer 拿到 GOAL+证据+台账+diff 之后,自然就"够做下一步指令"了**。implementer prompt(:256-270)只是把 `openIssues.filter(must)` 喂回去,信任 sonnet implementer 自己能从 must 描述里推出"改哪、怎么改"。

**这一假设在 GOAL 持久化升级前后都没被显式验证**。GOAL 持久化升级解决的是 "GOAL 不丢、子项有覆盖判据" 的漂移问题,但**没有正面回答**"r2 该怎么改"的综合 —— 这是个空缺,不是有意省略。

**用户的质疑("最重要的环节是分析问题怎么修改,但是这个恰恰没人做")在事实层面是对的。** architect 的辩护不延伸到否认这个空缺。

---

## 5. 对"加根因分析 agent"的态度:有条件支持

### 5.1 支持的论据

用户痛点真实("小问题改不好"在用户实测里反复出现),且 implementer prompt 现状(:256-270)在跨轮综合上确实薄:
- 收到的就是 must 列表 + verifiedLog 摘要,没人帮它综合"为什么 r1 这么改没解决"。
- implementer 是 sonnet,在跨轮综合 / 假设生成上能力本就被项目宪法限定。
- GOAL 持久化的"反锚定"是 reviewer 侧的,implementer 侧没有同等强度的反锚定。

### 5.2 防臃肿条件(5 条)

1. **位置必须在 reviewer 后、implementer 前** —— 用 reviewer 已综合的 4 类证据 + 台账,**不再多通道分析一遍**(否则 = 复制 reviewer 的工)。
2. **干的活 ≠ 再看一遍证据,而是综合 + 修法假设**:读 r1..rN 的 verdict + 残留 must + verified.evidence + 子项覆盖矩阵 + git diff →
   输出 r(N+1) 的修法假设(改哪个文件 / 改什么方向 / 上一轮为什么没改好 / 哪几个 must 该 batch 一起改 / 优先级排序)。
3. **触发条件 ≠ 每轮**:r1 没历史可分析、纯增成本。建议**从 r2 起、或 mustStaleStreak≥1 起**才插。这样 r1 走原路径(zero overhead),只在出现"改不好"信号时才付决策成本。
4. **模型必须 opus** —— 它干的就是开放式综合 + 假设生成,刚好契合 reviewer-as-thinking-layer 的延伸。**不能为了"省钱降 sonnet"** —— 那等于把同一个"模型边界判断弱"问题搬到决策层,白做。
5. **不写状态** —— 决策 agent 只输出 prompt 给下一轮 implementer 用,**不动 issues.json / verified.json / 台账状态机**。决策错了下轮 reviewer 还能纠正;让它写状态会变成第二份事实源,与现有反锚定机制打架。

### 5.3 替代方案对比:折进 reviewer 的 ChainOfImprovement 字段

skeptic / redesigner 可能推的对照方案:**给 reviewer schema 加一个 `chainOfImprovement` 字段(或类似)**,reviewer 已经看完所有证据,顺手输出"下轮改法建议"。

| 维度 | 独立决策 agent | 折进 reviewer |
|---|---|---|
| 新增 spawn | +1/轮(r2 起) | 0 |
| token 成本 | 多一份输入(verified + 台账) | reviewer prompt 略长 |
| 一致性 | 单一决策源,自然 merge + 排序 | 3 reviewer 各自出建议、可能矛盾;implementer 需自己 merge |
| 责任边界 | reviewer 判 "现状如何" / 决策 agent 判 "下一步" | reviewer 同时干 "现状 + 下一步",注意力分散风险 |
| 调试性 | 决策可单独审计、单独迭代 prompt | 决策与 review 捆绑,迭代一个动另一个 |
| 失败模式 | 决策 agent 跑偏 → 下轮 reviewer 兜底纠正 | reviewer 跑偏 → 同时影响 review 质量与决策质量 |

**我倾向独立 agent**,核心理由是**责任边界 + 单一决策源消除 merge 不一致**;但承认"折进 reviewer"在 token / 时延上更优,值得 redesigner 正面对辩 —— 不要因为我倾向独立 agent 就直接否决折叠方案。

### 5.4 对 skeptic 可能刺的"决策 agent 是补丁"预演

预演 skeptic 论点(team-lead 已预告):"加决策 agent 是补丁;真正的范式是 superpowers 的写 spec/writing-plan,但那是**静态、可预先详尽列出**的;web 迭代的修法假设是**动态发现**的,不一定能 spec 化;所以这个 agent 注定干不好"。

architect 回应草稿:

- **承认前半段**:superpowers 写 spec 范式确实预设 spec 是相对静态的(用户能在 spec 阶段把全部需求列出)。web 迭代的"修法假设"确实是动态发现的 —— **同意,不要硬套**。
- **但范式不需要硬套**。决策 agent 不是"写 spec",而是 superpowers 范式里 `executing-plans` / `receiving-code-review` 那一层 —— 在已知 GOAL 不动、已知 r1..rN 走过什么路、已知现在残留什么的前提下,做"下一步该走哪"的开放式综合。这一类活在 superpowers 体系里**本就是 opus 干的**(plan executor 接收 review 后的"下一步决定"层)。
- **真正的 trade-off** 在:这个综合能力的边际收益,是否覆盖每轮 +1 opus 调用的 token 成本 + 多一道串行延迟。这是 trade-off 而不是"补丁 vs 范式"的对立。
- **可证伪点**:如果 redesigner 给出的决策 agent prompt 草案,跑出来的 r(N+1) 修法假设 ≡ implementer 自己从 must 列表能推出的方向(也就是说,决策 agent 没产生增量信息),那这个 agent 确实是补丁,该砍。**判据应该在 prompt 草案 + dry-run 上做实证,不在原则之争上判**。

### 5.5 对 diagnostician 可能反驳的"根因不在缺决策层" 预演

预演 diagnostician 论点:"小问题改不好"可能根因不止"缺决策层" —— 可能是:
(a) STATES 覆盖不够,reviewer 看不到关键交互态;
(b) probe 缺失,canvas 类问题盲拍;
(c) refresh 档不对,改了但没生效;
(d) implementer 选择 sonnet 本身就是上限,加什么决策都没用;
(e) GOAL 子项拆错,reviewer 在错的轴上判 pass。

architect 立场:**diagnostician 这些根因大概率有真货,我不抢这个 part**。但承认决策层缺失 ≠ 唯一根因,不影响我的核心立场 —— **决策层缺失是其中一个独立根因,加决策 agent 是该根因的对症解,与其他根因的解(补 STATES / 补 probe / 修 refresh / 调 GOAL 拆解)正交、不互斥**。如果用户接受多管齐下,这几个解可以并行落地。

---

## 6. 立场总结

| 问题 | architect 立场 |
|---|---|
| reviewer × 3 opus 在做什么? | 多通道证据综合 + 跨轮台账推理 + 反锚定 —— 非评分员,sonnet 化代价大 |
| 这些工作能降 sonnet 吗? | ux/code 不建议降;func 是唯一降级口子(代价 = 偶发漏判) |
| finalize opus 合理吗? | close call,偏 sonnet 一侧;能力论据弱、唯成本论据 |
| reviewer-as-thinking-layer 是不是只是评分员? | 不是;它是"前置把关 + 状态机指针 + 注意力归位"三合一,sonnet implementer 在收窄 must 列表后才能干执行的活 |
| 为什么当初没加独立决策 agent? | 设计假设 reviewer 综合 + sonnet implementer 自推已够;**这一假设在 GOAL 持久化升级前后都没被显式验证** —— 这是空缺,不是设计 |
| "小问题改不好"是真痛点吗? | 是;用户实测信号该接 |
| 该加根因分析 agent 吗? | 有条件支持(5 条防臃肿条件,见 §5.2);独立 agent 与折进 reviewer 是真 trade-off,值得 redesigner 正面对辩 |
| 这是补丁还是范式? | 不是补丁;是 reviewer-as-thinking-layer 的延伸,在 superpowers 体系里有同类先例 |
| 决策层缺失是唯一根因吗? | 不是;与 diagnostician 可能列的其他根因正交,不互斥 |

---

## 7. R1 Update — 听 diagnostician / redesigner / skeptic 后立场翻转(诚实记录)

> 本节是 R1 cross-pollination 后的立场修正。R0 写完 §1-§6 后,team-lead 转来 diagnostician 的 thesis(reviewer 能力闲置)+ redesigner 的"绝对裁决 vs 根因综合"对辩 + skeptic 关于 impl 升 opus 的质问。架构师默认应防"动机性辩护"——R0 立场如果有错就承认。R1 翻转两条主立场,记录在此。

### 7.1 翻转 1:reviewer "已在做有判断的活" → **修正为 "做的是评判 + 状态机指针,根因诊断被 schema 锁死"**

R0 §2 论证 reviewer × opus 做了多通道证据综合 + 跨轮台账推理 + 反锚定,不是"评分员"——**这段没错,但不完整**。

完整的事实是:reviewer 现在做的活,**信息出口被 REVIEWER_SCHEMA(workflow-template.js:179-189)锁死在 issues[i].{title, severity, detail, evidence} 四字段**。即:

- reviewer 看到 `must.X 这一轮还在` 这层 — 有出口字段(matchesIssueId / stillPresent)。
- reviewer 推出 `must.X 没改好是因为根因不在 impl 改的那一处` 这层 — **没出口字段**。
- code lens 已在读 git diff,能看出 `impl 把 must 字面照搬改了一处,但根因在另一处` — **没出口字段**。

**结论**:diagnostician 的 thesis "reviewer 能力闲置" 对。**不是 prompt 弱,是 schema 锁死**。R0 §2 把 reviewer 的现状评判能力写得很扎实,这部分维持,但**没说出"根因诊断输出被 schema 锁死"的真核 bug**。R1 在此补回这条。

### 7.2 翻转 2:R0 倾向独立 decision agent → **R1 主推折进 reviewer schema 加根因字段(并保留 stall-触发 meta-agent 作罕用兜底)**

R0 §5.3 列了 trade-off 表,我标"我倾向独立 agent,核心理由是责任边界 + 单一决策源"。R1 翻转,理由如下:

**redesigner "3 reviewer 会冲突 → 需 merge → 所以独立 agent" 这条不成立**:
- mergeIssues(:80-111)已经在做 issue 维度的跨 lens 协调。
- 每个 reviewer **只在自己 lens 负责的 issue 上**写 **自己视角的 rootCauseHypothesis**(ux 视觉根因 / func 功能根因 / code 代码根因)→ 附在**不同 issue id** 上,**天然不冲突、是分工不是重叠**。
- 独立 decision agent 自己也只有一个视角(综合视角),**不解决盲区**,反多一层 LLM 二手解读(reviewer 综合 → decision 重读 → impl 又读 = 3 道转录损失)。

**折进 reviewer 的真胜出 = 信息距离一手 vs 二手 + code lens 闲置只有折进解**:
- 一手:reviewer 看着证据**直接写根因**,而非 decision agent 读 reviewer 摘要重综合。
- code lens 已读 git diff,suspectFiles 字段**只有 code lens 能填好** — decision agent 不读 diff、靠 reviewer 摘要,suspectFiles 信号到不了它手里。

**具体形态**(REVIEWER_SCHEMA :179-189 加 3 字段):

```
issues[i] += {
  rootCauseHypothesis: "为什么本轮没改好/真根因猜测(≤2 句)",
  suspectFiles: ["src/Chart.vue:42-60", ...],     // code lens 必填,其他 lens 可选
  chainOfDriftFromPrevRound: "上轮改了 X,但 X 不是根因因为 Y(仅 r≥2 要求)"
}
```

implementer prompt(:256-270)改 1 行透传这 3 字段给 impl。**零新 spawn、零新模型决策、零额外串行延迟**。

**让步 / stall-触发独立 meta-agent 的真胜场**:
- 当 mustStaleStreak ≥ 1 时,reviewer 已连续两轮在同一 must 上写过 rootCauseHypothesis 没奏效 — **这才是 reviewer 干不了的元综合**("读 r(N-1) 和 r(N) 两次 reviewer 写的 rootCauseHypothesis + 实际 impl 的 diff,判断 reviewer 假设是否系统性走偏")。
- reviewer 看不到自己上轮的元问题,**只有跳出 reviewer 视角的 meta-agent 能干**。
- 每 run 触发 0-1 次,不每轮。

**最终立场:折进 reviewer schema(每轮,P0)+ stall-触发独立 meta-agent(罕用,P1 可选叠加)**,两者不互斥。这一立场与 redesigner 的"缩窄版 decision agent(mustStaleStreak≥1 触发)"在触发点上重合,差别只在"每轮折进 reviewer 的根因字段"是 R1 新增,redesigner 没主张。

### 7.3 对 skeptic "impl 升 opus" 的立场(R0 没正面回应,R1 补)

skeptic 刺成立:**CLAUDE.md 宪法 "Implementer 一律 sonnet" 成立有隐含前提 = "reviewer 已吸收开放式判断"**;web-loop 现状违反前提(reviewer 没做根因诊断 → impl 实际在被迫做开放式设计 → 卡 sonnet ceiling)。**宪法不是无条件正确,边界外是真问题**。

**两条解路**:

- **路 A(我主张)**:修复前提 — schema 加根因字段让 reviewer 真做诊断,impl 真收窄到"在指定文件段实施已 hypothesized 的修法",sonnet 继续够,**宪法不让步**。
  - 成本:reviewer prompt + schema 重做(中等)。
  - 风险:reviewer 写错根因 → 下轮反锚定纠正(有自愈环)。
- **路 B(skeptic 主张)**:接受前提不修 — impl 升 opus 直接突破 ceiling,**宪法 web-loop 例外**。
  - 成本:每轮 impl opus 化(impl 是全脚本最大 spawn,token 量级跳跃;token-audit §1 已坐实 spawn 固定开销按模型单价计费)。
  - 风险:宪法滑坡(path2 主线 impl 也会被推升 opus)。

**我倾向 A,但 B 是真选项不是盲区** — 若 A 实测无效是兜底升级路径,**不该被宪法预先否决**。

**本研究 scope 边界**:impl 升 opus = 跨 skill 项目级宪法修订,理应单独立项 + 用 A 路径实测数据做决策。final_report 应**优先建议 A、把 B 列为"A 实测无效后的兜底"**,**不该在本研究里拍板砍宪法**。skeptic 若坚持 B 首选,需补"**A 路径为什么必然失败**"的论据(不是 "可能失败")。

### 7.4 立场最终态(供 final_report 引用)

| 维度 | R0 立场 | R1 翻转后立场 |
|---|---|---|
| reviewer × 3 opus 的真实工作 | 多通道证据综合 + 跨轮台账 + 反锚定,sonnet 化代价大 | **维持** "评判 + 状态机指针" 部分;**修正** "根因诊断被 schema 锁死、能力闲置 diagnostician 对" |
| ux / code lens 模型 | 不建议降 sonnet | 维持(token-audit 已坐实) |
| func lens 模型 | 唯一降级口子(代价 = 偶发 GOAL-追溯漏判) | 维持 |
| finalize 模型 | close call,偏 sonnet 一侧、能力论据弱 | 维持 |
| 决策层方案 | 倾向独立 decision agent(R0 §5.3) | **翻转**:主推**折进 reviewer schema 加 3 字段(每轮、零新 spawn)**;独立 meta-agent 仅 stall-触发(罕用,P1 可选) |
| 是否加 ChainOfImprovement | R0 列为 "对照方案" | 升级形态:不止 ChainOfImprovement,而是 `rootCauseHypothesis + suspectFiles + chainOfDriftFromPrevRound` 三字段 |
| impl 升 opus | 未正面表态 | **承认 skeptic 刺成立**:宪法成立有前提、web-loop 现状违反前提;**主走 A、B 是兜底不是首选,本研究不拍板** |
| "决策层缺失是唯一根因"? | 不是,与 diagnostician 其他根因正交 | 维持;**与 diagnostician 立场基本对齐,合并战线** |

### 7.5 给 lead 写 final_report 的引用建议

1. **TL;DR 推荐里**:把折进 reviewer schema 列为 P0(我和 redesigner R1 后立场重合;diagnostician 揭示 schema 锁死是直接论据)。
2. **"opus 在干嘛" 那节**:维持 R0 §2 的 reviewer "评判 + 状态机指针" 论述(reviewer 不是评分员是事实),但**必须加** R1 §7.1 的修正(根因诊断被 schema 锁死、能力闲置)—— 否则会把"reviewer 已 opus 所以没问题"的错误归因传给读者。
3. **"小问题改不好" 根因节**:让 diagnostician 主笔,我的立场就是补充 schema 锁死视角。
4. **决策 agent vs 折进 reviewer 设计 trade-off 节**:把 R1 §7.2 的表直接引用,**诚实记录我 R0→R1 翻转** — 这是研究的可信度信号,不是减分。
5. **impl 升 opus 节**:按 R1 §7.3 写,A 是主推、B 是兜底、本研究不拍板宪法修订。
6. **诚实分歧节**:与 redesigner 在"是否需要独立 agent"上的残留分歧 = 我主张折进 + stall 兜底,redesigner 主张缩窄版独立 agent;两者在 stall 触发点重合,差别在每轮的根因字段是否折进 reviewer。这个 trade-off 未必能在纸面定论,**值得实测**。
