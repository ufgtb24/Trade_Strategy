# A_raw · architect_critic 独立发现

> teammate A · focus = 架构合理性 + 通用性边界 + 反模式
> 已读:`.claude/skills/web-loop/SKILL.md`(234 行)/ `principles.md`(89 行)/ `workflow-template.js`(671 行)/ `examples/path2.md`(145 行)/ `tests/` 21 个文件名
> 全部为只读审视,本阶段不动代码。

---

## § 0 口径声明(lead 2026-06-22 对齐,与 C_raw §0 / B_raw § Token 口径声明段对齐)

**本文档所有 token / cost / $X/run 表述**:
- ✅ **特指 web-loop 每次跑 workflow 时真实消耗的 LLM API token / 美元成本(运行时,每跑一次都发生)**
- ❌ **不**含修改 skill 源码本身(SKILL.md / workflow-template.js / principles.md / examples/path2.md)时 implementer / reviewer 消耗的一次性 dev token

**改动幅度**(trivial / moderate / large)= **一次性代码工程量**,与 token 维度完全独立,只用作实施排序参考,**不计入 ROI 主指标**。

两维度在 §改进建议清单 + CV-13 真版优先级表 中**并列展示**(独立两栏)。同一行的 "moderate · -$0.25-$1.1/run" 意为"一次性改 skill 工作量 moderate;改完之后每跑一次 web-loop 省 $0.25-$1.1"——两个数字**不可加和**(单位不同)。

---

## § 硬伤(可定位行 + 复现条件 + 影响范围)

### H1 · 测试套件全是文本 grep,零运行时验证(反向架构信号 · 高置信)
**定位**:`.claude/skills/web-loop/tests/*.mjs` 21 个文件全部走 `readTemplate()` + `assertContains()` 模式(`test-baseline.mjs:2` / `test-converged-logic.mjs:2` / `test-stall-criteria.mjs:2` / `test-p1-meta-agent.mjs:2` 等全部 import `_helpers.mjs`,无 `child_process` / `spawn` / `mock` / `dryrun` 任意一处)。
**复现**:一条 `assertContains(src, 'forbiddenApproaches')` 只能告诉你模板文本里出现了那个字符串——它不告诉你:(a) 触发条件正确;(b) merge 入下轮 prompt 实际有效;(c) agent 解析 schema 不撞。
**影响**:
- 已实施的 P0/P1/GOAL 三件套等机制,**测试覆盖 = 静态文本检查**,等于无;真实 bug(e.g. `mergeIssues` 状态机错、`mustStaleStreak` 计数漏 case)只能靠 path2 真实跑暴露。
- SKILL.md L3 / L14 / L15 "已实测坐实"指 path2 真跑(memory 也证实);**单元测试** 这层名存实亡。
- 反向架构信号:模板从 ESM 改成可 `import` 的 module + 把 `phase/agent/parallel/log` 抽成可 inject 的 stub —— 即可单元跑 setup/iterate dry-run, 这条没做。**这是 670 行复杂度无 runtime 测试兜底的真因**。

### H2 · `read-decision-log` + `p1-diffstat` 两个无条件 sonnet agent 调用 / 轮(token sink · 中高置信)
**定位**:`workflow-template.js:297-308`(decision-log 读取)、`:527-531`(diff stat)
**复现**:
- L297-308:`round >= 2` 一律调一次 sonnet agent 跑 `Read decision_log.json`——但 `decision_log.json` 只在 P1 触发后才写,前几轮多数为空。**为读一个可能不存在的 JSON 文件每轮起一个 agent**。
- L527-531:每轮都跑 `git diff --stat | tail -1` 仅为算 `gitDiffSmallRounds`(P1 触发条件之一)。这本身 1 行 bash,起一个 agent 调用解析。
**影响**:
- 两次 sonnet 调用 / 轮 × 6 轮 = 12 个 agent 启动,纯辅助,可全部内联到 implementer agent 的 bash 段(或在主 iterate 体走纯 `phase().bash()` 等价机制,如果 Workflow runtime 支持的话)。
- 哪怕保留 agent 调用,`read-decision-log` 完全可以在 P1 触发后才读,而不是每轮 round>=2 都读。**调用频率 = O(rounds), 而真实必要频率 = O(P1 triggers) ≈ rounds / 3**。

### H3 · `decision-log-append` 走 inline python3 fallback to node 不稳(中置信)
**定位**:`workflow-template.js:584-590`
**复现**:`decision-log-append` agent prompt 写一句 bash `python3 -c "..."` 跑 JSON merge。"用户环境无 python3,fallback 写一个 node ESM 等价脚本到 /tmp/_dlog.mjs"——但 fallback 路径是 prompt 文字让 agent 自己处理,非脚本逻辑硬保证。
**影响**:CI / 无 python 容器下走 fallback 时,agent 实际执行能否一次过 = 看 agent;失败时 P1 决策丢失。**最简修法**:`workflow-template.js` 注入 `${WORKDIR}/decision_log.json` 用纯 node 内联(无 python),完全消除歧义。改动幅度 = trivial(替换一段 prompt 字符串)。

### H4 · `paused.md` 同名覆写(escapeRequest vs 三机检)隐丢上次 paused 状态(低-中置信)
**定位**:`workflow-template.js:511-514` + `:605-608`
**复现**:同一轮 `oscillating`/`treadmill`/`missingStates` 命中后写 `paused.md`(L513);如果同轮**又**触发 P1 + `escapeRequest`(理论上会 short-circuit 因 `pausedReason` 已置位,但 L536 的 `p1Triggered` 显式 `!pausedReason`,所以同轮不会同时触发)——**跨轮**场景:r3 触发 oscillating 写 paused.md → 用户写 human-hint-r4 续修 → r4 触发 escapeRequest 也写 paused.md → r3 的 paused.md 被覆写。
**影响**:已存 paused.md 不被 rename 备份,跨轮 paused 历史丢失。SUMMARY.md 只回放最新一份。改法 = paused 时 `mv paused.md paused-r{round}.md` 再写新,trivial 改动。

### H5 · `iterate` 顶端检测 `human-hint-r${round}.md` 协议碎片化(中置信)
**定位**:SKILL.md L168 "iterate 顶端自动检测..." vs `workflow-template.js:294`(implementer prompt 内嵌一句 `test -f` 检测)
**复现**:SKILL 说"iterate 顶端"做检测,但实际是塞进 implementer agent prompt 的一段文字,**靠 implementer 自己 bash 跑 `test -f` 后决定 read**——这不是 `phase("iterate")` 入口的代码逻辑,而是 prompt-driven 软约束。
**影响**:
- 如果 implementer 漏读(opus 在 prompt 优先级 1 段,这条 reasonable),hint 静默失效。
- 没有 workflow 层 hard gate 验证 hint 已被消费(`mv .consumed.md` 也是 prompt 文字软约束)。
- SKILL.md L170 "skill 入口控制流"声明"不走 setup、不重做 r1..rN",但这部分**逻辑落地在主会话 + Workflow resumeFromRunId 隐式跳过 setup**,workflow-template.js 内本身无 paused 检测分支(没有 `if(fs.existsSync(paused.md)) ...`)。**协议在 SKILL.md 文档层,实施在主会话 / runtime 互斥层** = 主会话漏一步则人介入路径断。

### H6 · resumeFromRunId "仅同 session 有效" 是硬阻塞而非软警告(高置信 · 实操痛点)
**定位**:SKILL.md L138 / L172 "resumeFromRunId 仅同 session 有效"
**复现**:用户长跑场景常见:web-loop r3 paused → 用户去做别的 / cc 重启 / 跨天回来 → 新 session 看到 paused.md → 想 resume 续修 → **resumeFromRunId 不可用,只能起新 run**(失去 verified 进度,等于 r1..rN 白跑).
**影响**:
- 三选一里"写 human-hint + resumeFromRunId" 的 (b) 通道在跨 session 时静默坍缩到 (a) 起新 run。
- 用户实际成本 = 重跑 r1..rN(假设每轮 50K-200K opus token,跨 session 失去 N 轮进度 = 数百 K token / case)。
- 这是 Workflow runtime 限制,不是 skill 自身可修;但 SKILL.md 把它当 "一行注脚",**没设兜底**(如:跨 session 的"低保真 resume" = 起新 run 但把 verified.json 注入 setup 当 "ground truth verified")。

### H7 · `subgoalCoverage` 全局聚合 vs 收敛判据用 `coveredThisRound`(中置信 · 设计语义不清)
**定位**:`workflow-template.js:428-433` (全局 subgoalCoverage) vs `:435-440` (本轮 coveredThisRound)
**复现**:`subgoalCoverage` 聚合所有 round 的 verified,但收敛判据 `allSubgoalsCovered = subgoalIds.every(id => coveredThisRound.has(id))` 只看**本轮**——含义:每轮 reviewer 必须对**所有**子项重新 verified,即便它在 r1 已被 verified 且后续未改动。
**影响**:
- 这是设计选择(防"曾经 verified 一直算 verified"漂移),代价是后期轮 reviewer 必须每轮把 G1-Gn 全部重新 echo evidence。**reviewer 多轮浪费 + GOAL 子项越多边际成本越大**(token cost = O(N×R) 而非 O(N))。
- principles.md / SKILL.md 没说清这是"绝对当下证据"原则——code reading 后才能猜到,**新项目接入会被 G1 已 verified 但下轮 reviewer 没复述就 fail 收敛搞糊涂**。

### H8 · "reviewer 永久零浏览器" 红线 vs 主会话 §2b 用截图诊断 = 主会话隐含破例(低置信)
**定位**:SKILL.md L74 "用户抱怨(如"K线挤在下方")→ **截当前界面**(服务在跑时)+ **读相关组件代码** → 推测技术 goal"
**复现**:主会话不在 reviewer 角色,但 §2b 让主会话开浏览器截图——这与 principles.md §7 "reviewer 永久零浏览器" 红线**不冲突**(主会话 ≠ reviewer),但 SKILL 内部口径有点滑:"红线"专指 fresh subagent 多并发,主会话可以截。
**影响**:架构上无 bug;但新人读 skill 易困惑"为什么 reviewer 不能开,主会话可以"。一句注脚可消(non-blocking)。

### H9 · `setup 清理(N-1 保留)` 的实施位置不在 workflow-template.js(中置信)
**定位**:SKILL.md L126 "时机锁死在此处——绝不在 finalize 删";但 `workflow-template.js` setup 阶段(L216-256)**无任何清理代码**,只写 preflight + write-goal.
**复现**:文档说 setup 清理,代码 setup 不清理。清理逻辑在哪里? 主会话生成 args 阶段?examples/path2.md 也没写。
**影响**:
- 旧 runtag 目录 `.claude/web-loop/<old>/shots/` 真要清理,只能靠主会话用户每次手动跑——但主会话也没明文要求这步。
- **磁盘累积 N 个 run 的 shots/(每 run 数十张 PNG,共数十 MB)**;path2 用户跨 worktree 跑久了,目录爆掉。
- 这是 SKILL.md 文档与实际 workflow 实施不一致 = cargo-cult-doc。

### H10 · `reviewer_stuck` 信号回流靠 implementer prompt 文字软约束,无 schema 强制(中置信)
**定位**:`workflow-template.js:330` 强制判断题段、`:120` reflectBlock(reviewer 读 implementer impl.md 首段)
**复现**:implementer agent 无 schema(L332 仅 `model:"opus"` 无 `schema`)——首段固定结构(`reviewer_stuck: <true|false>`)纯靠 prompt 指令。implementer 漏写 / 写错格式 = 下轮 reviewer Read 时 grep 不到。
**影响**:
- `reviewer_stuck` 是 P0 §3.5a-ii 决策层基石,**无任何 schema/正则 gate**。
- 实测教训(memory 没提)但**结构性脆**:一次 prompt drift 就静默失效。
- 改法 = 给 implementer 加 schema(`{reviewer_stuck:boolean, planRepetition:string, ...}`),改动幅度 = moderate(需保留 markdown 形态用于 reviewer 阅读 → schema 字段 + impl.md 双写)。

---

## § 设计不合理点(过度设计 / 不当抽象 / 内部矛盾)

### D1 · GOAL 三件套(goal.md + goal.json + refs/manifest.json)= "1.5 件套"足矣
**定位**:`workflow-template.js:240-255` write-goal agent
**问题**:goal.md(人可读) + goal.json(机器可读) **同源数据**两遍写,理由"消解中间状态不一致"——但同一 agent 调用里写两文件,与一次写 + 一次序列化无差。
**判定**:goal.md 一份足够。reviewer/implementer 都能解析 markdown;`goal.json` 唯一受益者是 `verified.json` join 子项 id 时,这步走 in-memory `GOAL_SUBGOALS`(已从 args 进 workflow scope)即可。**goal.json 是 cargo doc**。
**改动**:删 goal.json 写步,SKILL.md L18 / examples 同步,trivial。
**反驳**(自己驳自己):"机器可读副本备份,future tooling 解析方便"——不成立,refs/manifest.json 已是机器侧入口,GOAL 子项可直接进 manifest 或独立 subgoals.json(但 subgoalsList 也仅 in-memory 用就够)。

### D2 · `forbiddenApproaches` 字段 schema 三字段(issueId/triedMethod/why_failed_evidence)+ 跨轮 union 注入 prompt 优先级 3 = 过度仪式
**定位**:`workflow-template.js:201-212` META_AGENT_SCHEMA + `:309-313` decision_log union 注入
**问题**:
- 概念上 forbiddenApproaches 试图给 implementer "跨轮禁忌清单",但 implementer 优先级 2(本轮 must.nextStepPlan + suggestedFix)已包含该信息——reviewer 出 plan 时本应见过历史 reviews。
- P1 触发条件本身已经"stall 边缘",此时 reviewer 已陷在 plan dedup,implementer 也大概率忽略 advice。
- 三字段 schema(尤其 `why_failed_evidence`)要求 meta-agent 跨轮综合,**meta-agent 信号来源 = 同 reviewer 写的 reviews + impl.md** —— meta-agent ≈ reviewer 同源摘要,边际信息几乎为 0。
**判定**:meta-agent 提议的 forbiddenApproaches 实际价值 ≈ "上轮 reviewer plan + impl.md 反根因段"的重复摘要。**真正有价值的只有 escapeRequest**(救场退出通道)。
**改动建议**:
- 保留 escapeRequest 通道,删 forbiddenApproaches + prioritizedMustIds。
- META_AGENT_SCHEMA 收窄成单字段 `{escapeRequest: {...} | null}` —— moderate。
- 同步删 `decisionLog` 内插段(template L309-313)。
**token 影响**:每 P1 触发省一个 meta-agent agent 的 prompt header(几 K)+ 每轮省 read-decision-log 的 sonnet 调用(已在 H2 列)。

### D3 · 5 级 prompt 优先级模板(P1-P5)的可执行性疑问
**定位**:SKILL.md L196 "P1-P5 优先级模板" / `workflow-template.js:282-315`
**问题**:opus implementer 是否真按"优先级 1 > 2 > 3 > 4 > 5"听话?prompt 优先级是软约束,优先级 4(历史 reviews)+ 优先级 5(impl.md 反根因段)实际地位是"参考",但 prompt 里用"必读"措辞——opus 会全读全考虑,无层级强弱可言。**优先级模板更多是文档自我安慰,而非真触发 implementer 不同行为**。
**判定**:5 级优先级是认知模型而非运行时机制。真实需要的只有"权威·必从"(本轮 must.nextStepPlan)+ "参考"(历史)两档。**优先级 3-5 全是参考**,叫"P3/P4/P5"产生伪精细感。
**改动**:SKILL 把 P1-P5 改成"权威/参考"两档措辞;template 内同步,trivial。这不省 token 但省认知负担 + 防 cargo-cult 继续。

### D4 · `planDedupBlock`(L121)和 `reflectBlock`(L120)和强制判断题(L330)三处机制都在做"同一主线检测",彼此重叠
**问题**:
- reflectBlock(reviewer 读 implementer 上轮 reviewer_stuck 判断)
- planDedupBlock(reviewer 自查同主线 + 强制换主线临界规则)
- 强制判断题(implementer 必写 reviewer_stuck 首段)
三处都在防"reviewer 反复给同 plan / implementer 反复试同主线" 的死循环,**机制三重叠 prompt-side**。
**判定**:三段拼起来 prompt 重几 K,且 reviewer 看完 reflectBlock + planDedupBlock 后还要再做"临界规则强制换主线" + "真二选一倾向 默认查重收紧"两段细则——**判断负担过重,实际 reviewer 多半只走 fast path**。
**改动**:三段并 1 段,核心 = "若上轮 reviewer_stuck=true 且本轮你判定主线相同 → 强制换主线",其余细则砍掉。moderate 改动。
**反驳**(自己驳自己):"细则是 2026-06-21 brainstorm 推导,自己删风险大"——同意,B 应交叉验证(是否实测过细则提升收敛率)。

### D5 · `unverifiable` + `requiredStates` + `matchesSubgoal` 三态串联触发 missingStates 判据 = 检测过窄
**定位**:`workflow-template.js:482-489` 判据 3
**问题**:触发条件 = "同 GOAL 子项 unverifiable 跨 ≥2 轮 + requiredStates 集合有重叠"——但要 reviewer **同时**填 unverifiable:true、matchesSubgoal、requiredStates(三字段),只要一个漏填,判据不触发。
**判定**:实际能否触发,完全看 reviewer 是否准确填齐三字段。schema 上三字段都不是 required(`REVIEWER_SCHEMA` L189 仅 `title`+`severity` required)→ reviewer 漏填即静默失效。
**改动**:reviewer schema 把 unverifiable + requiredStates 升 required(条件性 required:仅在 issue 来自 GOAL 子项时);moderate。

### D6 · 670 行单文件 ESM 模板,无内部 module 拆分(可读性 trade-off)
**定位**:`workflow-template.js` 全文
**问题**:meta / safeInsert / mergeIssues / reviewerPrompt / scriptCapturePrompt / setup / iterate 主线 / finalize 全在一个 .js 文件——已经到了"读到 reviewer prompt 第 100 行你已忘了 mergeIssues 状态机的细节"。
**判定**:这是 Workflow tool 的限制(`script:` 必须是一个 string)。无法拆 ESM module;唯一可行的是用 JS 的注释 + region marker 切节,或者在 `.claude/skills/web-loop/lib/*.js` 拆函数 + 主 `workflow-template.js` 用 `cat parts/*.js` 拼装的脚本生成模板.**主会话生成模板那步走 generator 可解,但 trade-off = 调试时要看拼装结果**。
**改动**(不建议改):保留单文件,但在文件顶部加 region table of contents(行号 + 节名),trivial。

### D7 · `captureBackend` 三档(mcp / script / script-parallel)真用了几档?
**定位**:`workflow-template.js:29` 默认 `mcp`、L375 `mcpUnavailable` 自动退脚本
**问题**:用户 path2 实测一直 mcp + 自动 fallback;`script-parallel` "逃生口"对应"states 海量、单态慢、分叉不可串行复用"——path2 五态全在数秒内串行完成,**script-parallel 这一档零真实使用**。
**判定**:`script-parallel` 是预防性设计;若 path2 之外未来项目都不到 50+ state,这档永久 dead code.
**改动建议**:
- 保留(trivial,十几行代码,不痛);
- 或精简成"mcp + script 单一脚本"两档,并行档延后到真需要,trivial 删除。
**反驳**:"未来扩展性" —— YAGNI,需要时再加。

### D8 · `lastShotErrors`(L361 captureMemo)跨轮记忆机制单点(中置信)
**定位**:`workflow-template.js:382` (lastShotErrors = ...filter) + L361 captureMemo 插入
**问题**:capture 跨轮记忆只看上轮 errors。如果某 state 连续 3 轮失败,记忆只反映 r-1,**不积累跨多轮 trial method 历史** —— capture agent 不知道"前 2 轮试过 X/Y 都不行"。
**影响**:小;capture 失败本身是低频事件(path2 实测大多一轮就好)。**改进 ROI 边际**。
**建议**:不动(non-blocking)。

---

## § "通用于任意 web 项目" vs 仅 path2 实测的差距

### G1 · SKILL.md L3 自述 "通用于任意带浏览器界面的 web 项目" —— 实测覆盖率 ≈ 1
- 主体三文件(SKILL.md / principles.md / workflow-template.js)代码层 path2 渗透:**仅 examples/path2.md 引用 + 占位**(principles.md L49/L66/L72/L89 全是〔项目特化:...path2 见 examples/path2.md〕)。
- 但**概念层 path2 渗透深**:
  - "canvas/WebGL 类无 DOM 界面(ECharts 等)" SKILL.md L75 作为 first-class 概念升级到 §2b 智能入口层。
  - "stateProbe 第二证据通道"在 principles.md §8 列入合法证据 + workflow-template.js MANIFEST_SHAPE 强制 schema 字段——**这是 path2 ECharts canvas 痛点的解决方案被 promotion 到通用约定**。
  - "_e2e hook 须调用、ECharts getZr().storage.getDisplayList() 取真实图形"具体到指令级。
- 真实 DOM-only web 项目(React/Vue 普通表单 / 后台 dashboard)用本 skill = states/probe 全跳过、canvas 段死代码—— **没问题,只是 "通用" 在那种场景下 = 9 成机制空跑**。

### G2 · 通用骨架成立的实证条件
- args 字段 14+ 个,**真实通用必填字段** = url / smokeCmd / rubricPath / uiDir / shotsDir / workdir(自动) / runtag(自动)= 5-7 字段。
- `states` / `probe` / `captureBackend` / `scanSubset` / `refreshDataCmd` / `restartCmd` / `healthUrl` = 项目类型(canvas vs DOM / 数据驱动 vs 纯前端 / 有 backend vs 静态)决定的可选项。
- 实操结论:**通用骨架成立的最小集**是 setup + iterate + reviewer schema + capture/review 解耦——这部分 5 个文件 100% 通用。**path2 特化都在 examples + 概念渗透**,理论上换项目只动 examples/<新>.md + 写自己的 .web-loop-refresh.md.
- 但 SKILL.md 自身花大量篇幅讲 ECharts/canvas 取证(L75 / L34 examples)= **新项目接入时认知噪声**,而非通用必读。
- **结论**:骨架通用 ✓;**SKILL.md 内容比例严重 path2-bias**(canvas/ECharts/probe 段位置过靠前 + 占大比重)→ 新项目读者会以为这是通用必读。

### G3 · 改进建议(通用性差距)
- `SKILL.md §2b` canvas/ECharts/probe 段移到 examples/path2.md(本是 path2 实测教训)或独立 `principles-canvas.md`;SKILL.md 本体保持 DOM-first 默认假设.
- `principles.md §8` "stateDumps 与截图同级合法证据" 保留(确是通用机制),但 "canvas 交互无视觉差异时" 改注脚.

---

## § 改进建议清单(actionable · file:line + 改法 + 改动幅度 + 运行成本 Δ/run)

⚠ **两维度独立**(lead 2026-06-22 口径对齐,见 CV-6 / CV-16-bis):
- **改动幅度**(trivial / moderate / large)= 一次性修 skill 源码工作量,不复发
- **运行成本 Δ/run** = 改后每次跑 web-loop workflow 真实 token / $ 增减,**每跑一次都发生**

| # | 建议 | 文件:行 | 改法 | 改动幅度 | 运行成本 Δ/run(C_raw 数据) |
|---|---|---|---|---|---|
| A1 | 删 goal.json,留 goal.md 单文件(D1) | template:240-255 | write-goal agent 只写 goal.md;reviewer/implementer Read goal.md 即可 | trivial | 0 token(setup 单次写,prompt 内插不变) |
| A2 | META_AGENT_SCHEMA 收窄到仅 escapeRequest(D2,与 B#14 互斥 two-track) | template:201-212 / 295-308 / 309-313 | 删 forbiddenApproaches + prioritizedMustIds + decision_log union 注入逻辑;保留 escapeRequest paused.md 通道 | moderate | **-13-57k input + -0.5-3k output / run**(read-decision-log + decision-log-append + P1 体瘦身合计)≈ **-$0.25 to -$1.1/run** |
| A3 | 5 级 prompt 优先级砍成"权威/参考"两档(D3) | SKILL:196 / template:282-315 | 文案上去掉 P1-P5,改"权威·必从" + "参考";不改逻辑 | trivial | 0 token(纯措辞调整) |
| A4 | planDedupBlock + reflectBlock + 强制判断题三段并 1 段(D4) | template:120-121 / 330 | 保留"上轮 reviewer_stuck=true + 本轮主线相同 → 强制换主线"核心,删细则 | moderate | **-1-3k input/run** ≈ **-$0.02 to -$0.05/run**(prompt 4-6k char 压到 1-2k × reviewer 3 lens × N 轮) |
| A5 | reviewer schema 把 unverifiable/requiredStates/matchesSubgoal 升条件 required(D5) | template:189(REVIEWER_SCHEMA) | issue.matchesSubgoal 非空时,unverifiable + requiredStates 必填 | trivial | 0 token(schema 字段约束不进 prompt 内容) |
| A6 | implementer agent 加 schema 强制 reviewer_stuck 字段(H10,与 B#8 互补;真版收敛 B#8 主推 A6 作 backup) | template:332 | { reviewer_stuck:boolean, planRepetition:string, mdSnippet:string } + impl.md 双写 | moderate | **+0.3-0.8k output/run**(schema 输出额外字段)≈ **<+$0.01/run** |
| A7 | read-decision-log + p1-diffstat 只在 P1 触发可能时调,不每轮(H2) | template:297-308 / 527-531 | 用 mustStaleStreak 已知态前置 short-circuit;或合并进 implementer agent 末尾 bash | moderate | **-1-9k input + -0.7-1k output/run** ≈ **-$0.02 to -$0.12/run** |
| A8 | decision-log-append 用纯 node 内联,删 python3 fallback(H3) | template:584-590 | 一段固定 node ESM 脚本 | trivial | 0 token(prompt 内 bash 写法,稳定性提升;与 A2 互动:A2 全采纳则 A8 一并消除) |
| A9 | paused.md 同名覆写改为 paused-r{round}.md(H4) | template:511-514 / 605-608 | mv old → 写 new | trivial | **+0.1k output/run**(每次 paused 多写一份带 round 文件名)≈ **<+$0.01/run** |
| A10 | SKILL.md canvas/ECharts/probe 段降权,移到 examples/path2.md(G1/G3) | SKILL:75 / principles:23 部分 | §2b canvas 子段全文搬走;principles.md §8 保留通用 stateDumps 概念 | moderate(文档移动) | 0 token(文档侧改动,与 run 无关) |
| A11 | setup 清理逻辑放进 workflow-template.js setup phase(H9) | template:216-256 | 加 cleanup agent:按显式枚举 + 豁免清单,删旧 runtag shots/ | moderate | **+0.5k input + 0.3k output/run**(新增一个 cleanup sonnet agent)≈ **<+$0.01/run** |
| A12 | 跨 session resume 兜底:起新 run 但注入 verified.json(H6,与 B#9 互补;真版收敛 B#9 主推) | SKILL:170-172 | 主会话生成 args 时检测 paused.md → 起新 run + args 注入 already_verified 列表 | moderate-large | 0 run-time token(主会话端处理,不进 workflow loop)|

---

## § 不动建议(看似可改实际不建议)

### N1 · 670 行单文件 workflow-template.js 不拆模块
理由:Workflow runtime `script:` 必须 string;拆 module + generator 增加调试链路。trade-off 当前看 string 调试 → 单文件好.

### N2 · `captureBackend=script-parallel` 死代码保留
理由:小代码量(十几行),保留预防性;YAGNI 删除会丢失"path2 之外大 states 项目"的逃生口。**等真不需要再删**。

### N3 · `lastShotErrors` 单轮跨轮记忆
理由:低频问题,改进 ROI 低,不动。

### N4 · principles.md §7 "reviewer 永久零浏览器"红线
理由:该红线**是** capture/review 解耦的根本(H8 只是文档措辞小困惑),不应放松。

### N5 · args 14+ 字段集
理由:14 字段里 7 个真实通用必填、其余项目类型决定的可选(G2 已述)。**字段数本身不是 bug**;真正问题是 SKILL.md 表格把所有字段平铺让新读者以为都要懂。改法属 A10(降权 canvas 段)的延伸,不是删 args.

---

## § 总评(一句话)

骨架(capture/review 解耦 + GOAL 持久化 + 收敛判据三件套 + paused.md 续修协议)架构合理且实测有效;**问题集中在概念层 path2 渗透过深(SKILL 内 canvas 段位置靠前) + meta-agent forbiddenApproaches 这层过度仪式(无边际信息) + 测试套件全是文本 grep 等 cargo-cult-doc 反向信号**。改 12 条里 A1/A2/A8/A9 是 trivial 净降复杂度;A3/A6/A10/A11 是 moderate 直击通用性 + 自动改进健壮度;不动 N1-N5 各有理由。

---

## § 交叉验证修正(Phase 2)

### CV-1 · 漏抓补录:mergeIssues 字段穿透断点(P0,B 抓到我漏)

**来源**:B · autoimprove_critic SendMessage 「盲点 A · planDedupBlock 引用了不存在的字段」。

**事实确证**(我重读 workflow-template.js:80-111 + REVIEWER_SCHEMA:183-198 后):
- REVIEWER_SCHEMA L190-194 明确定义 reviewer 输出 4 决策字段 `rootCauseHypothesis / affectedFiles / suggestedFix / nextStepPlan`(code lens 必填,其他 lens 可空)。
- `mergeIssues` L107 push 新 issue 时只复制 8 字段 `{id, lens, title, severity, unverifiable, status, bornRound, lastSeenRound}`——4 决策字段全部丢弃。
- `issuesJson = JSON.stringify(issues,null,2)`(L266)塞进 reviewer prompt 的 issues 数组里**永远没有** `nextStepPlan` 字段。
- `planDedupBlock`(L121)对 reviewer 说"issuesJson 里能看到本轮每条 must 已有的'历史 nextStepPlan'字段"——**虚承诺,dead code**。

**这是本次 audit 的 top-1 P0 硬伤**,我 A_raw.md 漏列。功劳归 B。

**修法**(trivial):
- `workflow-template.js:107` push 字段对象补 `rootCauseHypothesis: it.rootCauseHypothesis, affectedFiles: it.affectedFiles, suggestedFix: it.suggestedFix, nextStepPlan: it.nextStepPlan`(6 行)。

**联动**:与我 A_raw.md H1(测试套件全是文本 grep)+ H10(reviewer_stuck 无 schema 强制)同源根因 —— **无 runtime 数据流转测试**。盲点 A 是"`assertContains(src, 'nextStepPlan')` 在 reviewerPrompt 段 + REVIEWER_SCHEMA 段 grep 都通过,但 mergeIssues 段不在 grep 范围"的典型 case。

**对原 A_raw.md 影响**:
- 这条 P0 优先级高于 A1-A12 任何一条;final_report 应作为 top-1 actionable。
- A6(implementer schema 强制 reviewer_stuck)与 B §盲点 E(workflow 程序化提取)是同一改法两面,应合并为一条 P0:**implementer agent 加 schema 必填 `{reviewer_stuck, planRepetition}` → workflow 直接读 schema 塞下轮 reviewer prompt**。

### CV-2 · 与 B 的 Q1-Q3 架构判断(回信摘要)

**Q1 · reviewer 跨轮记忆通道盘点**:
- (a) verifiedJson ✓ 真活
- (b) issuesJson ✗ 盲点 A 之前 dead;修后变活 = reviewer 跨轮记忆**主通道**
- (c) reflectBlock(implementer 中转)= 二级摘要信号
- (d) planDedupBlock = 依赖 (b),修盲点 A 后立即生效

**判断**:盲点 A 修上去 + reviews N-1 砍掉(commit 02420b4+137874f),(b) 字段持久化是主-辅设计的基石——不修则整套白瞎。

**Q2 · P1 双源真理禁让 reviewer 修 issues = 红线滑坡代价吗?**
**判断:不是滑坡,是必要的**。双源真理放开 → meta-agent 与 reviewer 对同一 must 严重度竞争写 → mustStaleStreak/收敛判据全不可信。escapeRequest.type=reviewer_disagreement 强制人工介入是正确解。**不该删双源禁令**。

**Q3 · workflow 程序化提取 impl.md reviewer_stuck 是否破"reviewer 不读历史 reviews"红线?**
**判断:不破**。数据源 = implementer self-report,不是 reviewer 自己上轮 review;reflectBlock(L120)当前设计已是同一逻辑,只是把"reviewer 自己 cat"升级到"workflow 程序化提取塞 prompt"——更可靠,不变性质。**红线本意**(memory project_web_loop_decision_layer_redesign 2026-06-21)= reviewer 不复读自己上轮防同源锚定,非"任何跨轮信号都禁"。

### CV-3 · 与 C 的核心 1-3 架构判断(回信摘要)

**核心 1 · reviewer × 3 lens 改 × 1 multi-lens prompt?**
**判断:架构合规**(无任何红线禁多 lens 各自独立 — 真红线只 §7 reviewer 永久零浏览器,是 capture 并发性非 review 并发性)。
- × 1 multi-lens 单 opus segment 串行输出 ux/func/code → input ≈ -2/3, 墙钟 +2x。
- **必保留 lens 字段**(mergeIssues L80-111 lens-归属状态机依赖 lens 维度);output schema 改 `{verdicts: [REVIEWER_SCHEMA × 3]}` → mergeIssues / 收敛判据全套零改。
- moderate 改动,墙钟代价由 lead 拍。**不是 cargo-cult,是 cost-bias**(并行优化与 cost 目标冲突)。

**核心 2 · C-cut-2 reviewer prompt issuesJson filter 仅 open/regressed?**
**判断:架构强背书,trivial 改动**。证据链:
- L266 `issuesJson=JSON.stringify(issues,null,2)` 全状态无过滤。
- reviewer 任务 = 对 open/regressed 表态 stillPresent;**fixed 不该让 reviewer 复判**(违反 principles §9)。
- fixed 信息已转移到 verifiedLog;mergeIssues regression 检测靠 workflow 内存数组,不需要 reviewer prompt 看 fixed。
- 改法:`issues.filter(i => i.status==='open'||i.status==='regressed')` 塞 prompt。

**推进 final_report**。

**核心 3 · GOAL 三件套成本面 + prompt cache**:
- (a) 删 goal.json 不论 cache 是否生效都对(A_raw D1)。
- (b) goal.md + refs/manifest.json 必要,不删(memory project_web_loop_decision_layer_redesign 论证防多轮漂移)。
- (c) **真问题是 prompt cache 实际激活否,不是三件套设计**——架构上 prompt 段顺序已 cache 友好(冻结段在前)。若 cache 实际未生效,C 估算 120-240k 重复传是 SKILL.md L210-212 "30-80K opus" 低估几个量级的真因;若激活,三件套零成本。**SKILL token 估算应更新,但属次要 doc-debt 非核心硬伤**。

### CV-4 · 综合后改进优先级重排(final_report 用)

把 A_raw.md A1-A12 + B 盲点 A + C C-cut-2 合并后,**P0(必修,影响自动改进闭环正确性)**:

| 优先级 | 改进 | 来源 | 改动幅度 |
|---|---|---|---|
| **P0-1** | mergeIssues L107 补 4 决策字段 + implementer schema 必填 `{reviewer_stuck, planRepetition}` + workflow 读 schema 塞下轮 reviewer prompt(替代 cat impl.md) | B 盲点 A + A6 + B §盲点 E **合并** | moderate |
| **P0-2** | reviewer issuesJson 注入按 status filter(去 fixed) | C C-cut-2 + A 背书 | trivial |
| P1-1 | 删 goal.json,留 goal.md 单文件 | A D1 | trivial |
| P1-2 | META_AGENT_SCHEMA 收窄到仅 escapeRequest;删 forbiddenApproaches + prioritizedMustIds | A D2(待 B 在 B_raw.md 表态) | moderate |
| P1-3 | read-decision-log + p1-diffstat 合并入 implementer / short-circuit | A H2 / A7 | moderate |
| P2 | reviewer × 3 lens → × 1 multi-lens 保留 lens 字段(墙钟 trade-off 由 lead 拍) | C 核心 1 + A 背书 | moderate |
| P2 | 5 级 prompt 优先级砍成"权威/参考"两档 | A D3 | trivial |
| P2 | planDedupBlock + reflectBlock + 强制判断题三段并 1 段 | A D4 | moderate |
| P3 | 其余 A1-A12 剩余条目(paused.md 覆写 / setup 清理实施缺失 / SKILL canvas 段下放 examples) | A | trivial-moderate |

### CV-5 · 我未变 / 未撤的立场

- A_raw.md H1(测试套件全文本 grep)**升级**:盲点 A 是其直接受害者,印证测试反向架构信号严重。
- A_raw.md H6(resumeFromRunId 跨 session 硬阻塞)**保留**:B/C 都未挑战,需 lead 综合时单列。
- A_raw.md G1-G3(SKILL 内容 path2-bias 严重,canvas 段需下放 examples)**保留**:B/C 未触及通用性边界,我视角独立确证。
- A_raw.md N1-N5 不动建议**保留**:670 行单文件不拆 / script-parallel 死代码保留 / lastShotErrors 单轮 / reviewer 零浏览器红线 / args 字段数本身非 bug。

### CV-6 · 口径对齐(lead 紧急澄清,2026-06-22)

**两类 cost 不可混淆**(lead SendMessage 明令):

- **A 维度 · 改动幅度**(trivial / moderate / large):**一次性修 skill 文件的复杂度**;即"开发者一次性投入"成本,与运行 token 独立。
- **C 维度 · 运行 token Δ**:改后**每次跑 web-loop workflow** 真实多 / 少消耗多少 token;**每次 run 重复发生**。

**§ 改进建议清单 / CV-4 优先级表 中"改动幅度"一列 = 一次性 cost,非运行时 cost**;运行时 cost 由 C C_raw.md 评估。两者**不可加在同一列**。

final_report 排序应同时看两维:
- trivial 一次性 + 高运行 ROI(如 C-cut-2 issuesJson filter)= 最佳投入,优先做
- moderate 一次性 + 持续运行降本(如 reviewer × 1 multi-lens)= 次优,衡量墙钟代价后做
- trivial 一次性 + 运行 ROI 中性(如 paused.md 覆写、删 python3 fallback)= 健壮度修补,见 P0-P3 分档
- moderate 一次性 + 运行 ROI 中性但闭环正确性必修(如 P0-1 mergeIssues 字段穿透)= 优先级高于运行 ROI 维度,不省钱也必做

我给 C 的挑战(每轮无条件 read-decision-log + p1-diffstat agent token sink)= **运行时 cost 视角**,口径正确;C-cut-2 issuesJson filter 同。

⚠ CV-4 表中 "改动幅度" 字段**一律理解为一次性实现工作量,不参与运行 token ROI 算术**;运行 ROI 维度独立见 C_raw.md。

---

### CV-7 · 真版 Phase 2(读 B_raw.md + C_raw.md 全文后,修正多条 CV-1~CV-6 立场)

CV-1~CV-6 是基于 SendMessage 摘要做的初轮收敛;读完 B_raw §修正 1-9 + C_raw §6.1-6.6 后,以下立场要更正。

### CV-8 · 真核心分歧(P1 forbiddenApproaches 删 vs 修):**我接受 B 反论的关键前提,但仍坚持 A2 是有理由的后撤位置——two-track 收敛**

CV-1 表里我把 "META_AGENT_SCHEMA 收窄到仅 escapeRequest" 列为 P1-2,语气近乎拍板。**这是越权**;真实状态是与 B#14 的 P1 路径冲突,应表达为 two-track。

**B 的关键反论我接受**:
- 我原 §D2 隐含前提是 "reviewer 跨轮看 reviews 后 forbiddenApproaches 信息≈0";B 指出 reviewer 端**没有 historyReviews 通道**(只有 implementer L314 才有),reviewer 只能靠 reflectBlock 间接 + issuesJson(且字段穿透前 dead)。**所以 P1 meta-agent 跨 ≤3 轮综合"tried+failed 配对识别"在 reviewer 端确实无法替代**——B 视角不是"另一份摘要",是另一个综合范围.
- 我对 implementer prompt 优先级 3 forbiddenApproaches 真采纳率有疑——B 把"30-50% 真用率 × 80%+ 触发 = 期望 24-40% 真有用,边际 ROI 微负"的数据点拿出来,这与我直觉一致;但 B 提了 #14 p1_skip_reason 让 50-70% 真命中率落地——这条改进我没考虑过,且 C 估 +0 token 增量、ROI 5-30×。

**我仍坚持 A2 的合理性**:即使 B#14 落地,P1 完整 3 字段 + decision_log 链路 + read-decision-log + decision-log-append 全套开销在 C §6.3 估算下仍是 $0.5-$1.5/run 持续成本;若 b#14 后真命中率到 70%,期望收益还是 15-25% × $0.3-$1.5 ≈ $0.05-$0.4/run,**仍是 cost 净亏 case**。但 capability 维度(stalled 救场)我无法证否——B 的 panel 案例(多 must 互冲、canvas 隐式状态、cross-cutting refactor)确实是 reviewer 自己解不了的。

**真实收敛 = two-track**(与 B/C 三方一致):
- Track 1(B+C 主推):采纳 #14 p1_skip_reason + 保留 forbiddenApproaches/prioritizedMustIds 完整 3 字段。**前置条件 = 实测某 run 检查 forbiddenApproaches 实际产出内容是否真重复**(C 也提此为唯一能判定的 evidence)。
- Track 2(A 后撤):**不加 #14** + 收窄 META_AGENT_SCHEMA 到单 escapeRequest 字段(A2)。worst-case 后撤位置,放弃 capability 救场但稳省 -$0.25 to -$1.1/run。

**判别点 = 用户/lead 是否相信 #14 能把 50-70% 真命中率落地**;我建议 lead 综合时**默认走 Track 1**(因为 sunk cost / stalled 救场失败 +$0.5-$1/run 抵消大部分 Track 2 成本优势,见 C §6.3)。**撤回 CV-1 表的"P1-2"拍板措辞**。

### CV-9 · CV-2 Q1 "reviewer 跨轮记忆通道盘点" 措辞误读修正

我原说 reviewer 有 (a) verifiedJson + (b) issuesJson + (c) reflectBlock + (d) planDedupBlock 四通道。B 在 §盲点 C 指出**我误读了 historyReviews**:`historyReviews`(L314)给的是 **implementer 不是 reviewer**;reviewer 端 reviewer 自己**不读历史 reviews**(N-1 砍后更严)。

正确盘点:
- (a) `verifiedJson` ✓ 真活
- (b) `issuesJson` ✓ 但盲点 A 修复前 dead,修复后变活(主通道)
- (c) `reflectBlock` ✓ 是 reviewer 看 implementer impl.md 首段的间接信号通道,implementer 是中转
- (d) `planDedupBlock` ✓ 依赖 (b),盲点 A 修后立即生效
- **reviewer 自己不读历史 reviews**(N-1 之后是 0,自始至终是 0)

CV-2 Q1 措辞不变结论,但 "(b) 是 reviewer 跨轮记忆主通道" 这话需要补一句:**reviewer 跨轮信号本来就只有间接通道,不存在直接读历史 reviews 的设计**——这是 architecture choice,不是限制。

### CV-10 · A6 vs B#8:接受 B/C 一致倾向 = B#8 主推,A6 作可选 backup

CV-2 Q3 我说 "A6 + B §盲点 E 应合并叙述"——B 进一步精化(§修正 2):
- 单加 A6 schema 不推荐:schema 会拉走 implementer attention budget,代码改动质量降 15-25%(prompt eng 经验值)
- B#8 更优:workflow 加 sonnet agent 程序化 parse impl.md 首段 YAML 字段 → 下游 reviewer 直接拿 workflow 变量,跳过 reviewer LLM cat 链路 50-70% 衰减
- **B 推荐:B#8 单 track 主推;若 lead 仍担心 prompt drift,A6 schema 加 + B#8 双轨叠加**(代价小,backup 兜底)

C §6.1 A6 评估 +0.3-0.8k output/run(schema 输出额外字段);C §6.5 表标 "B#8 略胜 — 不依赖 opus 听话"。

**我接受 B/C 一致**:B#8 主推,A6 仅作为 backup 选项。CV-1 表 P0-1 应改为 "mergeIssues L107 补 4 字段 + B#8 workflow 程序化 parse reviewer_stuck(主推)+ A6 schema 强制为可选 backup"。

### CV-11 · C §6.4 暴露的 SKILL.md L207 校准点(我 A_raw.md 漏抓)

C 通过我给的挑战 (g) 暴露**重要发现**:**SKILL.md L207 "opus 命中率提升降轮数 → 总 token 净降"是乐观假设,实测反向净增 $1.1-$3.6/run**。

证据链(C §6.4):
- B 数据 "80%+ run r2 触发 P1" = "opus 在 r1→r2 一轮内没救场"
- opus implementer 6 轮 cost $1.6-$4.5 vs sonnet 估 5-6 轮 $0.5-$0.9 = opus 净增 $1.1-$3.6/run

但 C 同时提:**capability 维度看 opus 命中率可能仍更高(只是不到能净降 token 的程度)**;B 视角"opus 强项 = search + 约束推理"对"逆向工程已出错代码"的真实价值**独立于 token 维度**。

**我 A_raw.md 没单列这条** — final_report 应在 SKILL.md L200 "implementer = opus 例外条款决策记录"段加校准:"opus implementer 当前数据下未实现 token 净降假设,反向净增 $1.1-$3.6/run;capability 维度仍可能优,但 cost 维度乐观估算应更新"。这条用户可能不爱听(2026-06-21 拍板的例外条款被实测打脸),但属于审计的诚实结论。

### CV-12 · C §6.5 表 "reviewer × 3 lens 是否合并 — A 未提" 错误,需告 C 更新

C §6.5 表 last-but-one row 标 "(A 未提)(B 未提) — A 没回 — 保留 3 lens 是 capability 选择"。**这是 C 误记**——我 CV-3 已明确背书 ×1 multi-lens(保留 lens 字段让 mergeIssues 零改),C 也回了我"input -2/3 但墙钟 +2x trade-off 由 lead 拍"。

我会 SendMessage to C 提醒修正这条;final_report 这条应填:
- A 立场:背书 ×1 multi-lens(保留 lens 字段)
- B 立场:未提
- C 立场:技术合规,墙钟 trade-off 待 lead 拍
- 收敛:moderate 改动,lead 综合时按用户实际等候耐心拍板

### CV-13 · 综合后改进优先级真版(替代 CV-4)

CV-4 表为 SendMessage 摘要轮初轮收敛,未反映 B/C 真版互修。真版优先级表(供 final_report 用):

| 优先级 | 改进 | 来源 / 改动幅度 / 运行 token Δ |
|---|---|---|
| **P0-1** | mergeIssues L107 补 4 决策字段(`rootCauseHypothesis`/`affectedFiles`/`suggestedFix`/`nextStepPlan`)+ append nextStepPlanHistory(B 盲点 A 核心修法)| B 盲点 A · trivial 一次性 · 运行 token 中性(+少量 issues schema 字段穿透成本,启用 planDedup 真功能) |
| **P0-2** | reviewer issuesJson 注入按 status filter(fixed 转 verifiedLog,reviewer prompt 只 open/regressed)| C C-cut-2 · trivial · -27k input/run(C 估) |
| **P0-3** | 测试套件改造 5 核心机制为 dry-run 数据流测试 + 抽 mergeIssues 等纯函数到 lib | A H1 + B §盲点 A 扩充 · moderate-large · 0 运行 token(开发健壮性维度) |
| **P1-1** | 删 goal.json,留 goal.md 单文件 | A D1 · trivial · 0 运行 token |
| **P1-2** | **(two-track)** P1 路径 — Track 1: 加 #14 p1_skip_reason + 保留 3 字段 / Track 2: 删 forbiddenApproaches+prioritizedMustIds 仅留 escapeRequest | A D2 vs B #14 冲突 · moderate · Track 1 净降 -$0.05 to -$0.3/run(B#14)Track 2 净降 -$0.25 to -$1.1/run(A2,但 sunk cost 风险 +$0.5-$1/run 抵消大部分)· **默认走 Track 1** |
| **P1-3** | read-decision-log + p1-diffstat short-circuit / 合并(B #6 + A H2 / A7)| B#6 + A 合并 · moderate · -1-9k input + -0.7-1k output/run |
| **P1-4** | reviewer_stuck 信号:B#8 workflow 程序化 parse(主推)+ A6 schema 强制为可选 backup | A6 + B#8 · moderate · +0.5k input + 0.3k output/run(新增 sonnet parse agent)/ +0.3-0.8k output/run(A6 schema 字段) |
| **P1-5** | 跨 session resume:B#9 iterate 顶部 rehydrate(主推)+ A12 主会话注入(补充)| A H6 + B#9 · moderate · 0 运行 token(从 issues.json/verified.json cold-start) |
| **P2-1** | reviewer × 3 lens → × 1 multi-lens(保留 lens 字段让 mergeIssues 零改)| C 核心 1 + A 背书 · moderate · -2/3 reviewer input · 墙钟 +2x trade-off |
| **P2-2** | planDedupBlock + reflectBlock + 强制判断题三段并 1 段(reflectBlock 核心 + 删 planDedup 细则 + 留强制判断题)| A D4 + B §盲点 F 收敛 · moderate · -1-3k input/run |
| **P2-3** | 5 级 prompt 优先级砍成"权威/参考"两档 + 物理顶部 + 强标识符切分(humanHint/forbiddenApproaches 共置)| A D3 + B§盲点 H 叠加 · trivial · 0 运行 token(prompt 重排)|
| **P2-4** | SKILL.md L207 "opus 命中率净降 token" 校准:实测反向净增 $1.1-$3.6/run;capability 维度仍可能优 | C §6.4 + A 漏抓 · trivial · 文档校准 |
| **P3-1** | paused.md 同名覆写改 paused-r{round}.md | A H4 · trivial · +0.1k output/run |
| **P3-2** | setup 清理实施缺失 → 落地 workflow setup phase | A H9 · moderate · +0.5k input + 0.3k output/run |
| **P3-3** | SKILL.md canvas/ECharts/probe 段降权到 examples/path2.md(通用性) | A G1-G3 + A10 · moderate(文档移动)· 0 运行 token |
| **P3-4** | decision-log-append 改纯 node 内联,删 python3 fallback | A H3 + A8 · trivial · 与 P1-2 Track 2 互动:若选 A2 全删,A8 一并消除 · 0 运行 token |
| **P3-5** | reviewer schema 升 unverifiable/requiredStates/matchesSubgoal 条件 required | A5 + B#3/#4 收敛 · trivial · 0 运行 token |
| 不动 | 670 行单文件不拆 / `captureBackend=script-parallel` 死代码 / `lastShotErrors` 单轮 / reviewer 零浏览器红线 / args 字段数本身 / 双源真理禁令 | A N1-N5 + CV-2 Q2 保留 |

### CV-14 · 我未撤的独立硬伤(B/C 未触及)

- **A H6 / 现 P1-5 跨 session resume**:B/C 同向(B#9 实现更简洁),已纳入。
- **A G1-G3 / 现 P3-3 通用性边界**:SKILL 内容 path2-bias(canvas/ECharts/probe 概念渗透到 §2b first-class)——B/C 都未触及,我视角独立确证,纳入。
- **A H1 / 现 P0-3 测试套件全文本 grep**:B 强烈认可并扩充(测试盲区 = 盲点 A 等多条字段穿透 bug 的同源根因);P0-3 必修。
- **A 总评 "概念层 path2 渗透过深 + meta-agent forbiddenApproaches 过度仪式 + cargo-cult-doc 反向信号"** 中 "forbiddenApproaches 过度仪式" 经 B 反论修正为 two-track 表达,其他保留。

### CV-15 · 给 lead 的最终建议

1. **P0-1 + P0-2 + P0-3** 三条 P0 是 final_report top priority,不论 P1 path 选 1/2 都要做。
2. **P1-2(P1 路径)** 默认走 Track 1(B#14),前置条件 = 实测某 run 看 forbiddenApproaches 是否真重复。若实测后真重复,可降级到 Track 2(A2)。
3. **P2-1(reviewer ×1 multi-lens)** 墙钟 +2x 是真实代价;若用户实操多在线等(非夜跑),保留 ×3 lens 并行;若多离线长跑,采用 ×1 input 节省 2/3。
4. **CV-11(SKILL.md L207 opus 例外条款校准)** 是诚实结论但用户可能不爱听,放在 final_report "诚实校准" 段;不是要求改决策,只是数据更新.
5. **CV-9 reviewer 跨轮信号 by design 受限** 应在 final_report 中明确表态——架构选择不是 bug,不可被未来"补充 reviewer 历史"建议无意中破坏。

---

### CV-16 · B 终轮回信三方收敛确认 + escapeRequest 新补缺

**收到 B 终轮 SendMessage(在 B_raw 落盘 + 真版收敛 §修正 1-9 后的最终对线)**——三方立场表(P1 forbiddenApproaches / reviewer_stuck schema / 三段并 1)与 A 真版 CV-13 完全一致:

| 议题 | A 立场 | B 立场 | C 立场 | 收敛 |
|---|---|---|---|---|
| forbiddenApproaches | 删 | 保留+加 p1_skip_reason | ROI 高,采纳 #14 | **two-track**:p1_skip_reason 加 → 保留;不加 → 删 |
| reviewer_stuck schema | 加 (H10) | 程序化 parse (#8) | 都 0 增量 | **双轨叠加更稳**(B#8 主推 + A6 backup) |
| 三段并 1 (D4) | 三段并 1 删细则 | 配合盲点 A 修后简化 planDedup 留 2 if-then | 0 token | **基本同向收敛** |

CV-8/CV-10/CV-13 P2-2 与上表完全匹配,确认 A 真版立场已与 B 完全对齐。

**B 提出的新补缺(我接受)**:`escapeRequest` 当前 4 类(missing_state / rubric_too_strict / goal_unrealistic / reviewer_disagreement)**缺 1 类 = `capture_layer_bug`**:
- `missing_state` 是 STATES list 配错(漏一观察轴);
- `capture_layer_bug` 是 STATES 对但 capture agent 连续 N 轮 shots failed(`workflow-template.js:384` 已有 `issues.push({id:'shot-${rtag}',...})` 兜底,但**没走 escapeRequest 通道**);
- **两类需要不同人介入指引**:`missing_state` 用户补 STATES;`capture_layer_bug` 用户 debug 浏览器/playwright/MCP 加载/sandbox 路径,与补 STATES 无关。

**B 同时明确反对加 `reviewer_lens_disagreement`**:已隐含在 `reviewer_disagreement.detail`(不限 lens 数),新增 type 只是叶级别加细,无新区分。我接受 B 这条判断。

**对 final_report 影响**(给 lead):
- P1 path Track 1(B#14 p1_skip_reason + 保留 3 字段)中,`escapeRequest` enum 类型应是 **5 类**(原 4 类 + `capture_layer_bug`),不是 4 类。
- workflow-template.js 的 META_AGENT_SCHEMA `escapeRequest.type.enum` 需对应更新。
- SKILL.md L186-194 的"escapeRequest 4 类语义"段需更新为 5 类。

**B 终轮静默待命,A 真版立场已最终收束。**

### CV-17 · C 终轮回信:三条架构判断已落 C_raw §8.10 F24/F25,数字校准 + 新前置任务

**收到 C 终轮 SendMessage**——C 把我 CV-3 三条核心架构判断全部融入 C_raw §8.10:

**核心 1 → C_raw F24 "reviewer × 1 multi-lens"**:
- C 给的精确数字:**-$2.25 to -$4.5/run**,**整个 audit 单条最大净降**
- 我提的关键约束("保留 lens 字段,schema 改 `{verdicts: [REVIEWER_SCHEMA × 3]}`,mergeIssues + verdict 推导全套零改")已记录
- F24 与 C_raw F8(reviewerPrompt 按 lens 切冗余)关系:F24 实施时 F8 by-design 成立;F8 单独实施仍有效
- final_report 决策点:**lead 拍墙钟 vs 成本**(墙钟 ×3 trade-off)

**核心 2 → C_raw F9 issuesJson 过滤升级 P0+**:
- 我的架构论证("fixed 已转移 verifiedLog / principles §9 红线 / mergeIssues regression 检测靠 workflow 内存数组")C 已收入 §8.10.2
- F9 从"P1 高 ROI"升级为 **"P0+ 架构合规修复"**,同时是 net cost 净降 -$0.4/run
- 对应我 CV-13 表 P0-2,排序与 C 一致

**核心 3 → 我 D1 + C_raw 新 F25 prompt cache 实测前置调查**(纳入):
- F17 删 goal.json 保留必采(我 D1 论证 + C 成本面双背书)
- 我提的"真问题是 prompt cache 实际激活否"被 C 升级为新 **F25 前置调查任务**:派 1 sonnet agent 跑 dry run 抽 `cache_creation_input_tokens` vs `cache_read_input_tokens` telemetry → lead 在 final_report § "实施前必做" 段单列
- F25 **不直接产生改动,但决定其他改动的优先级排序**:cache 生效 → 三件套零成本(A1 / D1 是 architecture cleanup 而非 cost cut);未生效 → 需加"prompt 模板前 X token 冻结"红线(SKILL.md 应加这条)

**对 CV-13 真版优先级表的影响**:
- CV-13 P2-1 "reviewer × 3 lens → × 1 multi-lens" 行运行成本 Δ/run 精确化为 **-$2.25 to -$4.5/run**(原表只标 "-2/3 input")
- **新增 P0-pre · F25 prompt cache 实测调查**(前置必做,在所有 P0/P1/P2 之前):
  - 改动幅度:trivial-moderate(派 1 sonnet agent + telemetry parse)
  - 运行成本 Δ/run:0(单次调查,不进 loop)
  - 价值:决定其他改动优先级排序(cache 未生效 → goal.md + GOAL 三件套真有运行成本;生效 → A1 / D1 是 architecture cleanup 而非 cost cut)

**最终 final_report 三大决策点(三方对齐,A 视角确认)**:
1. **F24 reviewer 1-vs-3 lens** — lead 拍墙钟 vs 成本(-$2.25 to -$4.5/run;架构 A 已背书合规;墙钟代价 +2x)
2. **F16 P1 路径 1 vs 2(B#14 修补 vs A2 全删)** — lead 拍 capability vs 成本(Track 2 净降 -$0.25-$1.1/run;sunk cost 风险 +$0.5-$1/run 抵消大部分;默认 Track 1)
3. **F25 prompt cache 实测** — 前置必做(决定 GOAL 三件套是 architecture cleanup 还是 cost cut)

**最大上限场景**(C §8.10.4):F24 + 路径 1 → -$3.9 to -$7.5/run;F24 + 路径 2 → 最乐观 baseline $1.5-13.5(原 $10-18 / 7 倍降幅上限);保守不动 F24(墙钟敏感)→ baseline $7-15/run(省 17-22%)。

C 已最终静默,A 视角接受 C 全部数字校准 + F25 前置纳入。

---

### CV-18 · B 真正终轮 5 点全接受 + final_report § 红线节新增表态

**B 真正终轮 SendMessage 全接受真版收敛 5 点**(P1 two-track / reviewer_stuck B#8 主推 + A6 backup / CV-9 reviewer 跨轮 by design / P0-3 测试改造扩充 / 5 级优先级+跨 session resume+decision-log 削减合并)。无新分歧。

**B 唯一新增建议(我背书)**:**final_report § 红线节加一句 CV-9 派生的架构表态**——
> **"reviewer 跨轮信号 by design 受限:主通道 = issuesJson 字段持久化(P0-1 修后)、辅 = reflectBlock + verifiedJson;禁追加 reviewer 直读 historyReviews(破独立性原则,reviewer 自始至终零自我同源锚定)。"**

这条比"删 X / 加 Y"型改进更重要——它**封堵未来误改方向**。若未来有人看到"reviewer 跨轮信号弱"就想补 reviewer 直读 historyReviews,会无意中破红线(reviewer 同源偏差锚定 + 独立性丢失)。final_report 必须显式表态防误改。

**B 同时澄清 P0-3 测试改造的最小可测集**:抽 mergeIssues / oscillating-treadmill-missingStates 三判据计算 / verdict 推导 / 收敛判据 5 项纯函数到 lib;主模板单文件保留(与 A N1 不冲突)。**我接受此最小集**作 P0-3 落地范围。

**final_report § 6 综合三方收敛矩阵建议**(B/A 都同意):
- 主表 = A CV-13 改进优先级表(P0-pre / P0-P3 + 不动)
- P0-1 详写 = B_raw §Phase 2 终态修正段(3 sub-item 拆法)
- 运行成本 Δ/run = C_raw §5 ROI 评估
- § 红线节 = CV-9 + CV-18 派生表态(reviewer 跨轮 by design 受限 + 双源真理禁令保留)

**A 视角真正最终对齐**:CV-1~CV-18 全部交叉验证完成,B/C 都已宣布最终静默,三方矩阵零分歧。

---

(真版交叉验证完成 + B 终轮收敛 + capture_layer_bug 补缺 + CV-17 C 数字校准 + F25 prompt cache 前置 + CV-18 B 5 点全接受 + § 红线节新增表态;A_raw.md 真正最终最终收束)
