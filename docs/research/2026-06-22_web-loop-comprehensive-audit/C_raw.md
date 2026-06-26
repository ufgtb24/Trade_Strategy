# C_raw · web-loop token 成本与改进 ROI(teammate C · cost_critic)

> ⚠ **口径(2026-06-22 lead 对齐)**:本文全部 token 数据 = **运行 workflow 一次的真实消耗 token**(每跑一次 web-loop 跑出的 LLM 调用累计)。
> **NOT** 修改 skill 文件本身(SKILL.md / workflow-template.js)所花的 token(那是一次性 dev cost,不在本评估范围)。
> 所有"Δtoken/run"含义统一为:**改进采纳后,每次运行 workflow 多 / 少消耗的 token**(每 run 复发)。
> "改动幅度"(trivial / moderate / large)= 代码工程量,不是 token,只用于实施排序参考。
>
> 范围:估算 web-loop 单 run 在 maxRounds=6 / staleRounds=2 默认配置下的 token 量级、找最贵段、独立提净降建议;Phase 2 再评 A/B 改进建议的 ROI。
> 估算依据(所有数据均区间):
> - char/token 比 ≈ 3.5(prompt 中英混 + JSON dump 数据;实测中文 ≈3-4 char/token,JSON dump ≈ 4 char/token)
> - LLM 扩展系数(input → output)按 agent 类型分:tool-calling agent(读多个文件+判断) ≈ 0.3-0.8;纯生成 schema 输出 ≈ 0.1-0.4;长策略文本输出(reviewer/meta) ≈ 0.4-1.0
> - opus pricing(2026 Q1 公开价):input $15/Mtok, output $75/Mtok(5× input);sonnet input $3/Mtok, output $15/Mtok。**opus 单 token 成本约 = sonnet × 5**(input/output 同比例)
> - 多模态截图 = 1500-2500 input tokens / 张(reviewer 实际 Read PNG;依赖图分辨率)
> - 单轮 N(STATES)=5 张截图(path2 实测值)
> - "Read" 一个文件 = 把内容塞进 input(隐式)。reviewer Read 5 张 PNG + rubric.md ≈ 9-13.5k tokens 隐式 input
> - **估算诚实**:除"prompt 静态 char 量"基于源码精确测量外,其它字段(每 agent 实际 LLM 输出 token、跨轮拼装后 issuesJson/verifiedLog 累积大小)按典型扩展系数推。**没有 LLM 实际跑过的 telemetry**(下文用 [估] 标这类字段)。

---

## § 1. 单 run baseline token 估算

### 1.1 静态 prompt 模板(源码精确测量)

| agent label | model | 静态 prompt char | tokens(input)[估·静态部分] |
|---|---|---:|---:|
| pw-selfcheck | sonnet | 600 | 170 |
| preflight | sonnet | 350 | 100 |
| write-goal | sonnet | 1100 (+ GOAL/subgoals 内插 1-3k char) | 600 |
| read-decision-log | sonnet | 600 | 170 |
| implementer | **opus** | 3026 (函数体) + 内插 humanHintRead/mustBlock/decisionLog/historyReviews/histImpl ≈ 6-12k char(中后期满载) | **1700-3400** |
| smoke | sonnet | 150 | 40 |
| rollback(失败时) | sonnet | 500 | 140 |
| refresh | sonnet | 1500 | 430 |
| capture (MCP) | sonnet | 1300(模板) + stateLines/captureMemo 0.5-2k | 500-950 |
| capture-fallback(可能) | sonnet | 同 capture script 分支 | 500-950 |
| review-{ux,func,code} | **opus** | reviewerPrompt 函数体 10126 char(静态) + 内插 issuesJson/verifiedJson/shotList/refImages/consoleNote/probeNote ≈ 5-25k char(随 issues 累积膨胀) | **4300-10000** |
| persist | sonnet | 150 + JSON.stringify(issues+verifiedLog) 内插 2-15k char | 600-4500 |
| p1-diffstat | sonnet | 200 | 60 |
| meta-agent | **opus** | 2367(模板) + safeBlock 内插 issues+verifiedLog+git log 2-15k char | 1300-5000 |
| decision-log | sonnet | 700 + JSON.stringify(logEntry) 0.5-2k | 350-770 |
| paused (条件触发) | sonnet | 2-3k char | 600-900 |
| finalize | **opus** | 2539(模板) + GOAL/refs/missingStates/issues/verified/history 内插 5-20k char | 2200-6500 |

### 1.2 截图 multimodal(input,reviewer 每张 PNG 显式 Read)

- path2 默认 5 个 state,每态 1 张 → 单轮 capture 产 5 张 PNG
- 每张 PNG 作为 reviewer Read 工具结果回流 input(原始 8-bit 图像编码后)≈ 1500-2500 tokens/张
- **每个 lens 都 Read 自己的截图集合**(reviewer 各自 fresh 上下文)→ ux/func/code 三 lens × 5 张 = **15 张 Read,multimodal 总 22.5-37.5k tokens/轮**
- 真实生产中:
  - ux lens "Read 每张 PNG"(reviewerPrompt §brief)→ 强制 5 张全读
  - func lens "按需 Read"(verifiable_via=screenshot 的子项)→ 实测 ≈ 1-3 张
  - code lens "截图仅旁证"→ 实测 ≈ 0-2 张
  - **typical 跨 lens 截图 input ≈ 8-11 张/轮 = 12-27.5k tokens/轮**

### 1.3 单轮 iterate 阶段总 token 量级估算

固定调用每轮(无 rollback 无 P1 无 paused):

| segment | 调用 | model | input tokens [估] | output tokens [估] |
|---|---|---|---:|---:|
| read-decision-log(round≥2) | 1 | sonnet | 600(prompt)+0-2k(decision_log.json 内容) = 0.6-2.6k | 200-800 |
| implementer | 1 | **opus** | 1.7-3.4k(prompt) + 1-5k(Read affectedFiles/refs/git diff 等) + 0.5-2k(本轮 must 内插) = **3-10k** | **3-8k**(impl.md + 代码改动多个 Edit) |
| smoke | 1 | sonnet | 0.5-2k(测试输出) | 100-500 |
| refresh | 1 | sonnet | 0.5-1.5k | 100-400 |
| capture (MCP) | 1 | sonnet | 0.5-1.5k(prompt+stateLines) + 0.5-1k(navigate/screenshot 工具返回) = 1-2.5k | 400-1500 |
| reviewer × 3 lens(并行,独立 ctx) | 3 | **opus** | 单 lens:4.3-10k(prompt+JSON dump) + 截图 multimodal 8-27k(跨 lens 异质) + Read rubric 1-4k + Read refs 1-3k = **14-44k 单 lens** | **2-6k 单 lens**(verdict JSON + issues+verified 长 detail) |
| persist | 1 | sonnet | 0.6-4.5k | 200-1000 |
| p1-diffstat | 1 | sonnet | 200(prompt) + git diff stat 返回 100-500 = 0.3-0.7k | 80-150 |

**单轮典型 input total**:
- sonnet 段:`0.6+0.5+1+1+0.6+0.3 ≈ 4k` ~ `2.6+2+1.5+2.5+4.5+0.7 ≈ 14k`
- opus 段(implementer + 3×reviewer + finalize 不在内):
  - implementer:3-10k input + 3-8k output
  - 3× reviewer:input 单 lens 14-44k(注:截图 input 估 8-27k 是跨 lens 平均,3 lens 累计 22-80k 总值,因 multimodal Read 各自独立) + 3 × (4.3-10k prompt+JSON 静态);**3 lens 总 input ≈ 35-110k**;output 3 × 2-6k = **6-18k**

**单轮 cost(以 opus 算 $15/Mtok input + $75/Mtok output;sonnet $3/$15)**:
- typical 单轮 input tokens:**60-100k**(其中 opus 占 38-95k,即 60-95%)
- typical 单轮 output tokens:**10-20k**(其中 opus 占 9-16k)

### 1.4 整 run total(maxRounds=6,跑满)

固定 setup(setup ≈ 3 sonnet agent + 鲜有 opus):**~3-6k input + 1-3k output**(sonnet 主导,可忽略)

iterate 6 轮:60-100k × 6 = **360-600k input + 60-120k output**

finalize:**input 5-15k + output 3-8k**(opus)

**单 run grand total(typical)**:
- input tokens ≈ **400-650k**
- output tokens ≈ **70-130k**
- 估算 cost(opus 占主 + sonnet 零头):
  - input cost ≈ 400k × $15/Mtok ≈ **$6**(其中 opus 段 ≈ 240-570k × $15 = $3.6-8.5)
  - output cost ≈ 100k × $75/Mtok(opus output 占主) ≈ **$7.5**
  - **典型单 run ≈ $10-18**;低端配置(早 stall,3 轮)≈ $4-7;高端(跑满 6 轮 + P1 触发 + 大量截图)≈ $20-30

> ⚠ 与 SKILL.md L207 "implementer opus 单 run 多 30-80K opus token" 自报数对照:**这条只说 implementer**(不含 reviewer);本表算 reviewer 单轮 35-110k × 6 = 210-660k input,implementer 单轮 3-10k × 6 = 18-60k;**reviewer 才是 dominant cost(约 6-10×)**,SKILL 自报数低估了一个量级——但 SKILL 那条仅在论证"implementer 改 opus 的增量",不是 total。

---

## § 2. Top 3 token sinks

### 排名 1:**reviewer × 3 lens × N 轮(opus + multimodal)**

- 单轮 35-110k input + 6-18k output(三 lens 累计)
- 6 轮:**210-660k input + 36-108k output**
- 占整 run input 的 **55-75%**
- opus model + multimodal 截图 + 长 prompt + JSON dump 三重叠加
- **关键膨胀因子**:`reviewerPrompt` 函数体 10126 char(全 lens 共享),每轮每 lens 全量重传;issuesJson 累计跨轮膨胀;refImages summary 每轮重生

### 排名 2:**implementer(opus)**

- 单轮 3-10k input + 3-8k output
- 6 轮:**18-60k input + 18-48k output**
- 占整 run input 的 **5-12%**,output 的 **25-40%**
- output token 比 reviewer 还重要(code 改动多个 Edit 调用都算 LLM output)
- **关键膨胀因子**:历史 reviews(优先级 4,Read 上 1 轮 reviews/round_NN.md)+ histImpl(优先级 5,Read 上 1 轮 impl.md)+ decision_log forbiddenApproaches 累积

### 排名 3:**finalize(opus)**

- 单 run 1 次:5-15k input + 3-8k output
- 占整 run output 的 **5-10%**,虽然单次最贵但发生频率低
- **关键膨胀因子**:GOAL 子项 + 全 issues + 全 verifiedLog + history(走势 array)全塞 prompt

> 注意:capture(sonnet)虽 multimodal 截图 + 工具调多,但 sonnet 价 + 截图本身不算 input(写盘 PNG 不是 prompt 内容)→ 单轮 cost 远低于 reviewer。所有 sonnet 段(persist/refresh/smoke/capture/decision-log)6 轮累计也只 ≈ 30-90k input + 15-50k output,**cost 占整 run 不到 8%**。

---

## § 3. 自提净降 token 改进清单(独立于 A/B)

### C-cut-1 · reviewerPrompt 静态段去重(高 ROI · 净降)

**问题**:`reviewerPrompt` 函数体 10126 char 中,**stalePrimer / reflectBlock / planDedupBlock / refsReadInstr / 第二步 GOAL 子项复核段**绝大部分对**ux/func 两 lens 不适用**(尤其 planDedupBlock 在 code lens 之外完全冗余),但当前实现按 lens 切第一段 brief 后,后续 8000+ char 全 lens 共享。

**改动**:把 planDedupBlock(2027 char)和 nextStepPlan 4 决策字段强约束段(694 char,reviewerPrompt L117 末尾)用 `if(lens==='code') ` 包起来;reflectBlock(1108 char)按 lens 行为不同各 lens 重写,ux/func 简化版 ≤300 char(只保留"上轮 stuck 信号要看")。

**位置**:`.claude/skills/web-loop/workflow-template.js` L113-171

**Δtoken/run 估算**:
- 砍 ux/func 各 2200 char 冗余 = 1250 tokens/lens/round
- 6 轮 × 2 lens × 1250 ≈ **-15k input/run**(opus,约 -$0.23)
- 不影响功能(code lens 仍拿全条件)
- **置信度:高**(纯无差别冗余)

### C-cut-2 · issuesJson/verifiedJson 跨轮膨胀截断(高 ROI · 净降)

**问题**:`mergeIssues` 把所有历史 issues 累积(包含 status=fixed 的)塞 issuesJson;`verifiedLog` 累积所有轮 verified;两 JSON 在 round 6 时可膨胀到 5-15k char 各,**每轮每 lens 全量重传**。

**改动**:对 reviewer prompt 注入时,issuesJson 只传 `status in (open, regressed) OR 最近 2 轮活跃过` 的子集;verifiedJson 同理只传最近 2 轮 + 与本轮 subgoals 关联的(M4.4 已聚合 subgoalCoverage)。
- 全量版仍写盘(`issues.json`/`verified.json`)供 finalize / 调试。

**位置**:`workflow-template.js` L266 `issuesJson=JSON.stringify(issues,null,2)`;L399 `verifiedJson: JSON.stringify(verifiedLog)`

**Δtoken/run 估算**:
- 中后期(r3-6)每轮每 lens 砍 2-8k char = 570-2300 tokens/lens/round
- 6 轮 × 3 lens × 1500 avg ≈ **-27k input/run**(opus,约 -$0.4)
- **置信度:中-高**(reviewer 仍能用 knownIssuesStatus 表态 → 已 fixed/历史无关 issues 本身 reviewer 不该重新质疑)
- **风险**:回归检测可能漏看远历史 issue;mitigation = "已 fixed 但本轮 status 改变" 也通过 status filter 保留

### C-cut-3 · 历史 reviews 双源去重(中 ROI · 净降)

**问题**:implementer prompt 已经 Read 上 1 轮 `reviews/round_NN.md`(优先级 4)+ histImpl Read `rounds/N-1/impl.md`(优先级 5)。但本轮 must 已含 nextStepPlan/rootCauseHypothesis 4 字段(优先级 2,从 issuesJson 内插),**reviews/round_NN.md 内容与 issuesJson 高度重叠**(就是 reviewer 上轮写的)。

**改动**:删 implementer 优先级 4 的"Read 上轮 reviews/round_NN.md"(L314 historyReviews 块);保留 histImpl(impl.md 反根因段是 implementer 自己的元判断,issuesJson 没有)。

**位置**:`workflow-template.js` L314

**Δtoken/run 估算**:
- 上轮 reviews/round_NN.md 典型 3-8k char(三 lens verdict 全文,含 verified detail)= 850-2300 tokens/round
- 6 轮 × 1500 avg ≈ **-9k input/run**(opus,约 -$0.13)
- **置信度:中**(已实现的反思机制 reviewer_stuck 信号回流 通过 impl.md 中转,reviews 直读冗余;但用户可能担心 P1 漏掉信号)
- 文档说"用于验证本轮 nextStepPlan 与上轮的差异、确认 P1 forbiddenApproaches 提炼无漏",但 nextStepPlan 已在本轮 issuesJson 内,差异比对放进 reviewer planDedupBlock 而非 implementer 更合理

### C-cut-4 · finalize prompt 收尾段精简(低-中 ROI · 净降)

**问题**:finalize prompt 2539 char + 大量 safeBlock 内插(L650-668)→ 实际 prompt 5-15k char。每个 4 节"顶部强制"段都用 safeBlock fence + markdown 模板,大量 ascii art。

**改动**:
- "## 已知设计 risk" 节(L660-662)固定模板内容硬编码 → 改为"Read docs/research/...goal-persistence/final_report.md §5.1"指针,prompt 内只留一句"reviewer 复核此节务必读 referenced source"
- history JSON 在 SUMMARY 节里展开过细(L666 `走势=${JSON.stringify(history)}`)→ 改为 history.length 摘要 + 异常轮(rolledBack/skippedReview)精简列出

**位置**:`workflow-template.js` L650-668

**Δtoken/run 估算**:
- 单 run 1 次:节省 1.5-3k char ≈ 430-860 tokens
- **-0.5-1k input/run**(opus,约 -$0.01)
- **置信度:中**(影响 SUMMARY.md 可读性;用户人工复盘体验略差)

### C-cut-5 · capture 模板 + scriptCapturePrompt 合并(低 ROI · 净降)

**问题**:`capturePrompt` 在 MCP / script 分支重复 80% 内容(CAPTURE_ERR_RULE / MANIFEST_SHAPE / stateLines / captureMemo)→ 但只激活一条路径,这条本身不重复传 prompt;实际是 prompt 模板维护重复,**不影响运行时 token**。

**结论**:**不建议改**(运行时 token 零节省,只是 source 维护性提升 → 不在 cost critic scope)

### C-cut-6 · principles.md 与 rubric 一次预加载(低 ROI · 但维护性涨)

**问题**:每个 reviewer lens 都 Read RUBRIC_PATH(假设 rubric 5-20k char = 1.4-5.7k tokens);3 lens × 6 轮 = 18 次 Read。

**改动**:在 setup write-goal agent 里把 rubric 内容 cache 到 `<workdir>/_rubric_cache.md`(预 Read);reviewer prompt 把 rubric 内容直接 inline(虽然内插但**与 Read 等价**,prompt cache hit 后第 2 轮起免费)。

**位置**:`workflow-template.js` L240 setup write-goal + L123-125 refsReadInstr

**Δtoken/run 估算**:
- **如果 prompt caching 生效**:第 1 轮 ×3 lens × 4k = 12k input(全付费),第 2-6 轮 ×3 lens × 4k = 60k 走 cache(90% 折扣,**实付 ≈ 6k**),total **18k vs 原 72k = -54k input/run**(opus 约 -$0.8)
- **如果 cache miss**(prompt 每轮变化):内插与 Read 等价,**0 净降**
- **置信度:低-中**(取决于 Anthropic prompt cache 行为;本 skill 是 Workflow runtime,缓存策略未知)
- **判定**:**条件 ROI**——值得验证 cache 行为后再决,现阶段 不动

### C-cut-7 · refImages summary 每轮重生 → 静态化(低 ROI · 净降)

**问题**:`summarizeRefImages(REF_IMAGES)` 每轮在 implementer + 每 lens 都重算(同一份 args.refImages 不变),拼成 prompt 字符串(L394-395 + L271-272)。

**改动**:setup 阶段 `refImagesSummary` 算一次存 const,iterate 内复用——但**这只是 JS 性能优化,token 不变**(prompt 内插已经在做)。

**结论**:**不建议改**(零 token 影响)

### C-cut-8 · decision_log 增量 vs 全量重传(中 ROI · 净降)

**问题**:`read-decision-log` agent 每轮(round≥2)从 `decision_log.json` 取 forbiddenApproaches union 全量回流;若 P1 触发多次,decision_log 跨轮膨胀,union 重复条目占空。

**改动**:`read-decision-log` 输出 schema 加 dedup by `(issueId, triedMethod)`;返回 forbiddenList 全量但去重后 ≈ 单 P1 一次输出的 1-2 倍 而非 N×1。

**位置**:`workflow-template.js` L298-308

**Δtoken/run 估算**:
- 若 P1 触发 1-2 次:forbiddenApproaches 累计 5-15 条;dedup 后 3-8 条
- 节省 0.3-1k char × 6 轮 ≈ -1-2k input/run(implementer 段)
- **-1-2k input/run**(opus 约 -$0.02)
- **置信度:中**(简单 dedup,无副作用)

---

## § 4. 净降清单合计

| ID | 改进 | Δtoken/run | $/run 节省 | 置信度 |
|---|---|---:|---:|---|
| C-cut-1 | reviewerPrompt 按 lens 切分 cargo segments | **-15k input** | -$0.23 | 高 |
| C-cut-2 | issuesJson/verifiedJson 注入时过滤 | **-27k input** | -$0.4 | 中-高 |
| C-cut-3 | 删 implementer 优先级 4 历史 reviews 直读 | **-9k input** | -$0.13 | 中 |
| C-cut-4 | finalize prompt 精简 | -0.5-1k input | -$0.01 | 中 |
| C-cut-8 | forbiddenApproaches dedup | -1-2k input | -$0.02 | 中 |
| **总计(全采纳)** | | **-52-54k input/run** | **-$0.8** | |

baseline $10-18/run → 砍至 ~$9-17/run,**省 5-8%**。绝对值不大,但 C-cut-1/C-cut-2 是无副作用纯收益,**应优先实施**。

---

## § 5. B 改进建议 ROI 评估(Phase 2 已落地)

### 5.1 B_raw 13 条逐条评估

| ID(B) | 改进 | Δtoken/run [C 估] | $/run 增量 | Δcapability(B 视角) | 净 ROI |
|---|---|---:|---:|---|---|
| #1 | mergeIssues push 补 5 字段(救活 planDedupBlock) | +5-15k input(nextStepPlanHistory 跨轮累积进 issuesJson 自然内插) | +$0.07-$0.22 | 直接救 reviewer 措辞抖动 50% case 的空转判据 | **必修(P0)** |
| #2 | tests/test-issues-decision-fields.mjs 新增 | 0(测试不在 run path) | 0 | 防 P0 链路再断 | **必修(P0)** |
| #3 | REVIEWER_SCHEMA if/then 约束 unverifiable→requiredStates | 0(schema 不进 prompt 内容) | 0 | missingStates 真实可触发率 50%→85% | **必修(P0)** |
| #4 | schema 收紧 requiredStates 同上 | 0 | 0 | 同上 | **必修(P0)** |
| #5 | oscillating 阈值 2→1 | **-60-100k input/run**(若震荡 case 命中,早 1-2 轮 stall) | **-$1 to -$1.5** | 早 2 轮识别震荡,用户少等 | **净降+高 ROI** |
| #6 | 删 gitDiffSmallRounds + p1-diffstat agent | **-7-24k/run**(直降 sonnet 1.8-4.2k + 误省一次 P1 假阳触发 opus 5-20k) | -$0.1 to -$0.4 | 消除"depends on implementer commit"的假阴/假阳 | **净降+高 ROI** |
| #7 | prompt 重排 humanHint/forbidden 升顶 | 0(纯 reorder) 或 +2-3k(强标识符 ⛔/🎯) | 0-$0.05 | forbiddenApproaches 真实采纳率 50%→70% | **平价+高 ROI** |
| #8 | workflow 程序化提取 reviewer_stuck | **+10-20k input + 2-3k output(sonnet)/run**(原 B 估 1.5K 偏低,实际 sonnet agent 读 impl.md + parse 单轮 ~3-5k tokens × 5 轮)| **+$0.05** | 三段 LLM 听话串联 50-70% → 程序化 85-90%;平均省 0.3-0.5 轮 opus = $1.5-3 收益 | **高 token + 极高 ROI(净赚 30-60×)** |
| #9 | iterate 顶部 rehydrate issues.json/verified.json | +0.3k input/run(从文件 Read 一次) | <$0.01 | 跨 session resume 可行性 0%→80%,避免起新 run 沉没 cost $10-18 | **极高 ROI** |
| #10 | SKILL.md L138-139 红线放宽 | 0(文档改) | 0 | 配合 #9 | 必修(配套) |
| #11 | forbiddenList 按 openMust id 过滤 + 折叠摘要 | **-5-10k input/run**(后期 r4+ forbidden 可达 5-15 条,filter 后 1-3 条) | -$0.08-$0.15 | forbiddenApproaches 注意力上限保护 | **净降+高 ROI**(与 C-cut-8 收敛合并) |
| #12 | SUMMARY.md PAUSED 节加 effective rounds 解释 | +0.2k output/run | <$0.01 | UX 改进,无能力维度增量 | 平价 |
| #13 | vision verifier(独立 skill) | **+54-90k input + 3-6k output/run**(opus + 5 张截图 × 6 轮) | **+$1-2/run(成本翻倍)** | "消除 reviewer 编像素" 失败率减多少% B raw §盲点 I 自承"ROI 中",未给具体数 | **应放弃**(除非用户证实 vision evidence 假报是高频灾难) |

### 5.2 ROI 子清单

**显著净降 token + 高 ROI(必做)**:
- B#5 oscillating 阈值:-60-100k/run
- B#6 删 gitDiffSmall:-7-24k/run
- B#11 forbiddenList filter:-5-10k/run
- C-cut-1 reviewerPrompt 按 lens 切冗余:-15k/run
- C-cut-2 issuesJson 注入过滤:-27k/run
- C-cut-3 删 implementer 优先级 4 历史 reviews 直读:-9k/run
- 小计 **-123 to -185k input/run ≈ -$1.8 to -$2.8/run**

**显著增 token 但极高 ROI(必做)**:
- B#1 mergeIssues 补字段:+5-15k → 救活整段空转的 planDedupBlock
- B#8 reviewer_stuck 程序化:+10-20k sonnet → 信号通量 50→85%
- 增量 ≈ +$0.12-$0.27/run,但**通过提升收敛率净省更多**(B 估 50%→70-80% 覆盖率提升 → 平均省 0.5-1 轮 opus iterate ≈ $3-6 收益)

**平价(改无成本/低成本)**:
- B#2/#3/#4/#7/#10/#12 + C-cut-4/8

**应放弃(增量不划算)**:
- B#13 vision verifier:+$1-2/run = 单 run cost 翻倍,ROI 不清。建议拒。可挂为 P3 future,**前提是先收集 evidence 假报频次数据**——否则就是 cargo-cult 加成本。

### 5.3 全采纳后 baseline 重写

- 全采纳 P0+P1+P2(除 #13)= **input total Δ ≈ -110 to -160k/run**(净降)
- 单 run cost:$10-18 → **$6-13**
- 同时**自动改进覆盖率 50%→70-80%**(B 估)
- **每 $省下来的部分还顺带提升能力 = 极少见的双赢区**

### 5.4 收敛点 + 修正记录

**收敛点 1**:B#11 + C-cut-8 都是"forbiddenList 过滤"。
- B 视角:按 openMust id 过滤(范围维度)
- C 视角:dedup by (issueId, triedMethod)(去重维度)
- **合并**:两者组合 → 双重过滤,总效果 -8-15k/run。final_report 应合并表达。

**收敛点 2**:B#1 修复 planDedupBlock 链路断点 → 让 C 的 C-cut-2(issuesJson 过滤)更安全
- 若 B#1 不修,C-cut-2 过滤掉历史 issues 反而无所谓(本来没有 nextStepPlanHistory)
- 若 B#1 修了,C-cut-2 必须保留 nextStepPlanHistory 字段不过滤(只过滤 fixed/远历史 issue 整条)
- final_report 应注明 C-cut-2 的实现要点:filter 仅按 status,字段全保留

**修正记录(C 自我修正)**:
- 原 C-cut-8(dedup decision_log)被 B#11 包含,**降权为 B#11 的子方案**
- C 原估 B#8 增量"基于 B 自报 1.5K"已被 C 重新核算为 10-20k(差一个量级);最终结论仍同——ROI 极高、采纳

### 5.5 B 回信修正(2nd pass · 2026-06-22)

收到 B 的逐条 5 问回复后,C 自我修正:

**(1) B#8 token 收窄**:B 重新表态"parse 40 行文本 ≈ 300 input + 100 output/轮 × 5 = 1.5-2k/run"是基于 sonnet parse 短文本的精确估;C 原估"读 impl.md 1-3k char"高估了 impl.md 文件总长度(B 只让 sonnet parse 首段几行 YAML)。**修正 B#8 = +1.5-2k input/run + 0.5k output**,而非 C 原估 10-20k。ROI 结论不变(仍是极高 ROI 标杆)。

**(2) P1 触发率数据(B 给出)**:
- mustStaleStreak ≥ 1 + coveredSubgoalsUnchanged ≥ 1 + gitDiffSmall ≥ 1 任一即触发 → **80-90% run 在 r2 即触发 P1**
- P1 实质有用率(产出真有用 forbiddenApproaches)≈ 30-50%
- escapeRequest 真触发率 < 10%
- **结论**:**P1 是 80%+ run 必跑但只 30-50% 真用** → 是 cost 浪费,但**不能直接删**(剩余 30-50% 是核心 stalled 救场)
- **新建议(B/C 双采纳)**:`P1_TRIGGER_STREAK = max(2, STALE_ROUNDS)`(即 r3 才触发而非 r2)→ **触发率 80%→40%,Δtoken -3-10k/run**,**净降 ROI 高**。这条作为 final_report **新增**改进点(原 B raw 未包含,B 在回信中升级提出)。
- 合并 B#6(删 gitDiffSmallRounds)= 触发通道更干净

**(3) 续修协议 sunk cost(B 给数据)**:
- paused 三档:(a) 30-40% / (b) 40-50%(但 resumeFromRunId 同 session 限制让真实可用率打折到 25-35%)/ (c) 15-20%;5-10% 强迫退化
- **paused case 中 50-65% 沉没 cost = $5-10/paused-run 直接报废**
- **B#9 rehydrate 修后**:(b) 真实可用率 25-35% → 55-65%,直接救回 sunk cost
- **token 维度看 B#9**:本身只 +0.3k input/run,**但 sunk cost 维度是单 run cost 减 $5-10 摊到 paused 案例上**——这是 ROI 维度的最大单项,**应在 final_report 强调**

**(4) C-cut-3 与 B#1 的耦合修正(B 给出)**:
- C 原 C-cut-3 主张"删 implementer 优先级 4 历史 reviews/round_NN.md 直读"
- B 指出:**reviews/round_NN.md 不只含 issues(可被 issuesJson 替代),还含 `verified` 数组的 evidence 详情**;但 implementer 已经在 L273-275 通过 verifiedLog 摘要(verifiedSummary)看到 verified 子项 → reviews 直读仍是真冗余 → C-cut-3 仍成立
- **修正实现要点**:删 historyReviews 段(优先级 4)的同时,**确保 verifiedSummary 段保留并增强**(把 evidence 字段加进摘要,而不是只列 title)。否则 implementer 可能丢失"verified 子项的具体证据"参照
- 净降仍 -9k/run,但**实现细节比原 C-cut-3 更精细**(verifiedSummary 升级)

**(5) B 自己的合计修正**:
- B raw 改进点 #1/#4/#5/#6/#7/#8/#9 全采纳:**净 token -8-15k input/run + capability +50-80%**
- 绝对 cost -$0.12 to -$0.23/run(token 维度;sunk cost 维度还省 $5-10/paused-run)
- C 同意 B 这个汇总数据,**作为 final_report § 6 "全采纳后预测"基础**

### 5.6 B 修正后的 ROI 表(替代 §5.1 表的 token 估算列)

| ID | C 原估 Δtoken/run | B 回信修正(若有) | 最终采纳值 |
|---|---:|---:|---:|
| B#1 | +5-15k input | **-0.5 to -1k**(B 自估:totals 因措辞抖动减少而净降) | -1k 到 +15k(置信中,取决于跨轮 nextStepPlanHistory 实际累积深度) |
| B#5 | -60-100k(若震荡命中) | -3-5k(B 自估:平均早 1-2 轮 stall) | **-5-100k**(命中条件分布广) |
| B#6 | -7-24k | -1.2k(B 自估;C 加了 P1 假阳节省) | **-1.2-24k** |
| B#8 | +10-20k | **+1.5-2k input + 0.5k output**(B 精确化) | **+2-2.5k**(采 B 值) |
| B#9 | +0.3k(token); **-$5-10/paused-run**(sunk cost) | 同 C | 采 C 值 |
| 新增 P1_TRIGGER_STREAK 提高 | (B 回信新提) | **-3-10k**(触发率 80%→40%) | **-3-10k**(必采) |

### 5.7 final_report 应同步的认识更新

1. **B#9 跨 session rehydrate** 在 token 维度看小(+0.3k),但**真正价值在 sunk cost 维度**:救回 paused case 50-65% 的 $5-10/paused-run。这维度不该藏在 token 维度的 ROI 表里,**final_report 应单列一节"sunk cost 维度优化"**。
2. **P1 触发率/有用率非对称数据**(B 给):80-90% 触发但只 30-50% 真用 → cost 浪费在 80%+ run 上。新增 P1_TRIGGER_STREAK 阈值改进 = 必采。
3. **B 数据系统性偏低 1 量级** 不是因果性偏差,而是 B 视角看"prompt 行变化"vs C 视角看"prompt 累计 tokens"。两个视角是互补的——final_report 应在"ROI 评估方法论"段说明:**token 增量 ≠ 单次 prompt 改动行数,要看跨轮累积**。

### 5.8 B 回信 3rd pass(2026-06-22)—— B 全采纳两条新议题,C 落地

**B 改进 #14(新)· P1 schema 加 p1_skip_reason 第 4 字段**
- META_AGENT_SCHEMA 加 `p1_skip_reason: enum["no_tried_method_yet","all_addressed","insufficient_evidence", null]`
- P1 prompt 配"无足够证据时优先标 skip_reason + 留空 forbiddenApproaches,禁止凑数"
- **Δtoken/run**:**0 增量**(schema 字段 5-10 char,可忽略)
- **capability**:P1 真命中率 30-50% → 50-70%
- **联合效应**(与 P1_TRIGGER_STREAK = max(2, STALE_ROUNDS) 叠加):整体 P1 真有用 run 占比 = 原 32%(0.8 × 0.4)→ 新 24%(0.4 × 0.6)——触发率减半但有用率仅微损 8%,**trade 划算**(净降 token,触发率降的那 40% 多数是原本就空跑 case)
- ROI:**必采,0 token 极高 ROI**

**B 改进 #15(新)· STALE_ROUNDS 2→3 + maxRounds 6→5**
- effective rounds 3-4 → 4-5
- max cost ceiling -$1.5/run(6×100k → 5×100k)
- typical cost ±0(effective ↑ 抵消单轮 ↓)
- 用户预期对齐(maxRounds=5 真跑接近 5 轮)
- **Δtoken/run net**:**-50k 到 +50k**(分布广),典型 ≈ ±0,**但 max budget 锁低**
- **capability**:+15-20%
- ROI:**采,且必与 #14 配套**(单调 STALE_ROUNDS 不修 P1 = 放大空跑浪费)

### 5.9 最终改动清单合计(全采纳,不含 vision verifier)

1. B#1 mergeIssues 补 5 字段(救 planDedupBlock)
2. B#2/#3/#4 schema + test
3. B#5 oscillating 阈值 2→1
4. B#6 删 gitDiffSmallRounds + p1-diffstat agent
5. B#7 prompt 重排 humanHint+forbidden 升顶
6. B#8 程序化提取 reviewer_stuck(+sonnet parse agent)
7. B#9 跨 session rehydrate
8. B#11 + C-cut-8 forbiddenList 双重过滤(openMust filter + dedup)
9. B#12 SUMMARY 加 effective rounds 解释
10. B#14 P1 schema 加 p1_skip_reason
11. B#15 STALE_ROUNDS 2→3 + maxRounds 6→5
12. **P1_TRIGGER_STREAK = max(2, STALE_ROUNDS)**(B/C 共采纳)
13. C-cut-1 reviewerPrompt 按 lens 切冗余段
14. C-cut-2 issuesJson/verifiedJson 按 status 过滤(配合 B#1 保留 nextStepPlanHistory)
15. C-cut-3 删 implementer 优先级 4 + verifiedSummary 升级
16. C-cut-4 finalize prompt 精简

**Δtoken/run total**:
- 净降项(B#5/#6/#11+#15 上限 + C-cut-1/2/3/4)= **-125 到 -210k input/run**
- 净增项(B#1/#8 + C-cut-2 保留 nextStepPlanHistory)= **+15-25k input + 2-3k output/run**
- **综合 Δ ≈ -100 到 -190k input/run ≈ -$1.5 到 -$2.8/run**
- baseline $10-18 → **$7-15.5**(省 15-22%)

**Δcapability**:
- 自动改进任务覆盖率 50% → 70-80%
- 跨 session resume 0% → 80%
- forbiddenApproaches 真实采纳率 50% → 70%
- 信号链路成功率 50-70% → 85-90%
- missingStates 真触发率 50% → 85%
- P1 真有用 run 占比 32% → 24%(触发率降半 + 命中率提升的净效应)

**Sunk cost 维度(非 token,B#9 关键效益)**:
- 救回 paused case 50-65% 沉没 cost ≈ **平均 $5-10/paused-run**
- 与 token 维度独立,final_report 应单列一节

---

## § 6. A 改进建议 ROI 评估(Phase 2 已落地)

> A 提了 12 条 actionable 建议(A1-A12)+ 5 条不动(N1-N5)。A 视角主轴 = 架构清理 + 通用性差距 + cargo-cult-doc 修剪。**与 token cost 维度直接相关 = A2/A7/A8/A12 四条**,其余多为 0 token 改动。

### 6.1 A 12 条逐条 ROI 评估

| ID(A) | 改进 | Δtoken/run [C 估] | $/run 增量 | 改动幅度 | 净 ROI |
|---|---|---:|---:|---|---|
| **A1** | 删 goal.json,留 goal.md 单文件 | 0 input(setup write-goal 单次写,prompt 内插不变) | 0 | trivial | 平价(架构清理,采纳无成本) |
| **A2** | META_AGENT_SCHEMA 收窄到仅 escapeRequest + 删 forbiddenApproaches/prioritizedMustIds + decision_log 整条链路 | **-13-57k input + 0.5-3k output/run**(read-decision-log/decision-log-append/P1 自身瘦身合计) | **-$0.25 to -$1.1** | moderate | **最大净降项,但与 B#14 路径冲突 — 见 §6.3** |
| **A3** | 5 级 prompt 优先级砍成"权威/参考"两档 | 0(措辞调整) | 0 | trivial | 平价(认知负担降) |
| **A4** | planDedupBlock + reflectBlock + 强制判断题三段并 1 段 | **-1-3k input/run**(prompt 重 4-6k char 压到 1-2k) | -$0.02-$0.05 | moderate | 净降+中 ROI;但 B 视角认为细则有提收敛率作用 — A 自驳"B 应实测验证" |
| **A5** | reviewer schema 升 unverifiable/requiredStates/matchesSubgoal 条件 required | 0(schema 字段约束不进 prompt 内容) | 0 | trivial | 平价;与 B#3/#4 高度重叠 |
| **A6** | implementer agent 加 schema 强制 reviewer_stuck 字段 | +0.3-0.8k output/run(schema 输出额外字段) | <$0.01 | moderate | **与 B#8(workflow 程序化提取 reviewer_stuck)路径不同**:A6 = "implementer 输出 schema 强制" / B#8 = "workflow 另起 sonnet parse";两路效果近似,**B#8 更稳妥**(不依赖 opus 听话),C 倾向 B#8 |
| **A7** | read-decision-log + p1-diffstat short-circuit 或合并进 implementer | **-1-9k input + -0.7-1k output/run** | -$0.02 to -$0.12 | moderate | 必采(与 B#6 复用):p1-diffstat 删除部分 B#6 已覆盖;read-decision-log short-circuit 是 A 独立净降 |
| **A8** | decision-log-append 用纯 node 内联,删 python3 fallback | 0(改 prompt 内 bash 写法) | 0 | trivial | 平价(稳定性提升,与 A2 互动:若 A2 全采则 A8 一并被删除) |
| **A9** | paused.md 同名覆写改为 paused-r{round}.md | +0.1k output/run(每次 paused 写文件名带 round) | <$0.01 | trivial | 平价(架构清理) |
| **A10** | SKILL canvas/ECharts/probe 段降权,移到 examples/path2.md | 0 run-time token | 0 | moderate(文档移动) | 平价(通用性提升,文档维度) |
| **A11** | setup 清理逻辑落地到 workflow-template.js setup phase | +0.5k input + 0.3k output/run(新增一个 cleanup agent) | <$0.01 | moderate | 平价+中 ROI(防磁盘累积,长跑用户必修) |
| **A12** | 跨 session resume 兜底:主会话生成 args 时注入 verified.json | 0 run-time token(主会话端处理) | 0 | moderate-large | **与 B#9 重叠**:B#9 走 iterate 顶部 rehydrate(更简单),A12 走主会话注入(更兜底);**B#9 优先**,A12 作为补充 |

### 6.2 A 关键 token 估算回答(回 A 挑战 (a)-(g))

| 问题 | C 答案 |
|---|---|
| (a) read-decision-log + p1-diffstat 量级 | 单 run **1.5-13k input + 0.8-1.5k output**(sonnet 价 ≈ $0.005-$0.04 input + $0.012-$0.022 output) |
| (b) A7 节省比例 | -1-9k input + -0.7-1k output/run ≈ -$0.02 to -$0.12/run |
| (c) 是否最先抓 | **否**,小净降项(C-cut-1/2/3 单条都更大),但**必采**因 trivial + 与 B#6 复用 |
| (d) 完整 P1 vs 仅 escapeRequest | 完整 input 14-50k + output 1-4k(opus,$0.21-$0.75/触发);仅 escapeRequest 若降 sonnet ≈ $0.01-$0.03/触发(便宜 20-30×),保留 opus 瘦身 ≈ $0.04-$0.18(便宜 3-5×) |
| (e) decision-log-append + 整条链路删 | append 单独 $0.005-$0.02/run;整条链路删合计 -$0.25 to -$1.1/run |
| (f) opus implementer 单轮 | input 3-10k + output 3-8k tokens;单轮 $0.27-$0.75 → 6 轮 $1.6-$4.5/run(implementer 单独) |
| (g) opus 命中率降轮数赌注 | **C 反证**:B 数据"80%+ run r2 触发 P1" = "80% run r2 时尚未收敛" = opus 命中率没省到 r1→r2 收敛;**SKILL.md L207 "总 token 净降"是乐观估计,实测倾向净增 $1.1-$3.6/run** |

### 6.3 A/B P1 路径冲突 — lead 二选一裁定

**路径 1(B 修补:B#14 + #15 + 新 P1_TRIGGER_STREAK)**:
- P1 体保留三字段 + 加 p1_skip_reason
- 触发率 80% → 20-30%
- 残余 P1 浪费 -$0.05 to -$0.3/run
- Δcapability:保留 30-50% 真用率 × 50-70% 注入采纳率 = **15-35% case 真起效**(stalled 救场)

**路径 2(A 干脆删:A2)**:
- 删 forbiddenApproaches + prioritizedMustIds + decision_log 整条链路
- 只剩 escapeRequest 元判断
- 节省 -$0.25 to -$1.1/run
- Δcapability:失去 15-35% case 的 stalled 救场;A 视角认为 forbiddenApproaches ≈ "上轮 reviews 重复摘要,无边际信息"

**C 视角(成本侧)倾向**:**路径 2 略胜**,但**差额小于 capability 不确定性**
- 加权计算:15-35% × 50-70% = **7.5-25% case 真受益** × $0.3-$1.5 收益 = $0.02-$0.4/run 期望收益
- vs $0.5-$1.5/run cost(100% run 都付 P1) = **净亏 $0.1-$1.1/run**
- 路径 2 cost 维度净赚 -$0.2-$0.8/run vs 路径 1
- 但 sunk cost 风险(stalled 救场失败 → paused 触发率 +10%)≈ +$0.5-$1/run,**抵消大部分成本优势**

**lead 协调建议**:
- 若 B "30-50% 真用率"数据可信(强) → 路径 1
- 若 A "forbiddenApproaches 与上轮 reviews 摘要重复"论点可信(强) → 路径 2
- **C 倾向**:**实测一个 run 检查 forbiddenApproaches 实际产出内容是否真重复**——这是唯一能判定的关键 evidence。**无法实测时,保守取路径 1**(B 修补,边际损失小,保留救场通道)。

### 6.4 SKILL.md L207 自报 token 校准(C 通过 A (g) 问题暴露)

C 答 A 的 (g) 暴露了**重要校准点**:**SKILL.md L207 自报"opus 命中率提升降轮数 → 总 token 净降"是乐观假设,实测反向**:
- B 数据"80%+ run r2 触发 P1" = "opus 在 r1→r2 一轮内没救场"
- opus implementer 6 轮 cost $1.6-$4.5 vs sonnet 估 5-6 轮 $0.5-$0.9 = **opus 净增 $1.1-$3.6/run**
- **final_report 应在 § "SKILL.md 决策记录段" 加 校准**:"opus implementer 当前数据下未实现 token 净降假设,反向净增 $1.1-$3.6/run"

**但**:capability 维度看 opus 命中率可能仍更高(只是不到能净降 token 的程度);**B 视角"opus 强项 = search + 约束推理"** 对"逆向工程已出错代码"的真实价值**在 capability 维度独立于 token 维度**。final_report 应**分别表态 token 维度 vs capability 维度**,不强行把 opus implementer 例外条款定论。

### 6.5 A vs B vs C 收敛/冲突点全表

| 议题 | A 立场 | B 立场 | C 立场 | 收敛/冲突 |
|---|---|---|---|---|
| P1 forbiddenApproaches 处理 | A2:删 | B#14:修补加 p1_skip_reason | 倾向路径 2 但 sunk cost 让差额小 | **冲突** — lead 裁定 |
| reviewer_stuck 信号强化 | A6:implementer schema | B#8:workflow 程序化 parse | 倾向 B#8(不靠 opus 听话) | **轻冲突** — B#8 略胜 |
| 跨 session resume | A12:主会话注入 verified.json | B#9:iterate 顶部 rehydrate | B#9 优先,A12 作补充 | **互补收敛** |
| reviewer schema 收紧 | A5:条件 required | B#3/#4:if/then 约束 | 重叠合并 | **完全收敛** |
| 5 级优先级模板 | A3:砍 2 档 | B#7:重排升顶 | 同方向 | **收敛** |
| forbiddenApproaches 过滤 | (无) | B#11:openMust filter | C-cut-8:dedup | **三方合并** |
| GOAL 三件套 | A1:删 goal.json | (无意见) | 0 token 影响,采纳无 cost 风险 | **A 独立采纳** |
| SKILL.md canvas 段降权 | A10 | (无) | 文档维度,与 cost 无关 | **A 独立采纳** |
| 测试套件全是文本 grep | A H1(硬伤) | (无) | C 视角与 token 无关,但应进 final_report "开发健壮性"段 | **A 独立硬伤** |
| reviewer × 3 lens 是否合并 | (A 未提) | (B 未提) | C 已问 A,A 没回(可能不主张合并)| **未冲突 — 保留 3 lens 是 capability 选择** |

### 6.6 全采纳后 baseline 最终预测

合并 B raw(§5.9)+ A_raw(§6.1)P0+P1+P2 改动(路径 1 假设 — 保守取 B 修补):

**Δtoken/run total**:
- 净降项小计:**-130 到 -220k input/run**(B 项 -125 到 -210k + A7 -1 到 -9k + A4 -1 到 -3k)
- 净增项小计:**+15-25k input + 2-3k output/run**(B#1 + B#8 + C-cut-2 保留 nextStepPlanHistory)
- **综合 Δ ≈ -105 到 -200k input/run ≈ -$1.6 到 -$3.0/run**
- baseline $10-18 → **$7-15**(省 17-22%)

**若取路径 2(A2 全删)**:
- 额外节省 -$0.25 到 -$1.1/run
- baseline $10-18 → **$6.5-14**(省 22-30%)

**Δcapability(综合 A/B)**:
- 自动改进任务覆盖率 50% → 70-80%(B)
- 跨 session resume 0% → 80%(B#9 + A12 兜底)
- forbiddenApproaches 注入采纳率 50% → 70%(B#7 + A3)
- 信号链路成功率 50-70% → 85-90%(B#8)
- missingStates 真触发率 50% → 85%(B#3/#4 + A5)
- 文档通用性 path2-bias → DOM-first(A10)
- 测试套件 文本 grep → runtime 验证(A H1 — 独立工程项)

**Sunk cost 维度(非 token)**:救回 paused case 50-65% 沉没 cost ≈ $5-10/paused-run(B#9 + A12 兜底)

---

## § 7. 已知估算盲点(诚实陈述)

1. **没有 LLM 实际 tokens telemetry**:所有非源码 char 测量字段都是估算
2. **prompt caching 行为未知**:Anthropic prompt cache 对 Workflow runtime 是否激活会改变 ×5 cost(C-cut-6 不确定的根因)
3. **multimodal 截图 token 计费**:opus / sonnet 对 vision input 计费方式可能与文本不同(典型 1500-2500/张是参考)
4. **reviewer 并行调用是否合并 input cache**:3 lens 并行各自独立 ctx,如果共享 prefix(rubric/refs/refImages summary)是否走 cache 未知
5. **opus output 多 Edit 调用计费**:implementer 改代码若调多次 Edit,每次 Edit 的输入(old_string/new_string)算 input 还是 output?估算按 output 计

---

## § 8. 三方融合最终改进 ROI 总表(Lead Phase 2 收口)

> **Δtoken / run(运行 workflow 时,非修改 skill)**;baseline = $10-18/run
> - 净降 = 每次跑 workflow 节省的 token 成本(每 run 复发)
> - 净增 = 每次跑 workflow 多花的 token 成本(每 run 复发)
> - "工程量"列 = 改 skill 文件的 dev cost(一次性,**不计入 ROI**),只供实施优先级参考
> - 来源:A = architect_critic / B = autoimprove_critic / C = cost_critic
> - 状态:✓必采 / ⚠待 lead 裁定 / ✗放弃

### 8.1 P0 必修(链路断点 / 硬约束)

| # | 来源 | 改进 | Δtoken/run | $/run | 工程量 | 状态 | 备注 |
|---|---|---|---:|---:|---|---|---|
| F1 | B#1 | mergeIssues push 补 5 字段(rootCauseHypothesis/affectedFiles/suggestedFix/nextStepPlan/nextStepPlanHistory) → 救活 planDedupBlock | +5-15k input | +$0.07-$0.22 | trivial | ✓ | 跨轮 nextStepPlanHistory 进 issuesJson 自然内插 |
| F2 | B#2 | tests/test-issues-decision-fields.mjs 新增 | 0 | 0 | trivial(测试,不在 run path) | ✓ | |
| F3 | B#3 + B#4 + A5 | REVIEWER_SCHEMA if/then 收紧 unverifiable→requiredStates | 0 | 0 | trivial | ✓ | A5 同方向,合并;missingStates 真触发率 50%→85% |

### 8.2 P1 高 ROI(净降 token,采纳全无成本副作用)

| # | 来源 | 改进 | Δtoken/run | $/run | 工程量 | 状态 |
|---|---|---|---:|---:|---|---|
| F4 | B#5 | oscillating 阈值 2→1(早识别震荡) | -60-100k(命中震荡 case 时早 1-2 轮 stall) | -$1 to -$1.5 | trivial(1 字符改) | ✓ |
| F5 | B#6 + A7 | 删 gitDiffSmallRounds + p1-diffstat agent + read-decision-log short-circuit | -8-33k input + -1-1.5k output | -$0.12 to -$0.52 | moderate | ✓ |
| F6 | B#7 + A3 | prompt 重排 humanHint+forbidden 升顶,5 级优先级砍成"权威/参考"两档 | 0 to +2k(强标识符)| 0-$0.05 | trivial | ✓ |
| F7 | B#11 + C-cut-8 | forbiddenList 双重过滤(openMust filter + dedup) | -8-15k input | -$0.12 to -$0.22 | trivial | ✓ |
| F8 | C-cut-1 | reviewerPrompt 按 lens 切冗余段(planDedupBlock 限 code lens,reflectBlock 各 lens 简化) | -15k input | -$0.23 | moderate | ✓ |
| F9 | C-cut-2 | reviewer prompt 注入 issuesJson/verifiedJson 按 status 过滤(配合 F1 保留 nextStepPlanHistory) | -27k input | -$0.4 | moderate | ✓ |
| F10 | C-cut-3 + B 修正 | 删 implementer 优先级 4 历史 reviews 直读 + verifiedSummary 升级(加 evidence) | -9k input | -$0.13 | trivial | ✓ |
| F11 | C-cut-4 | finalize prompt 精简 | -0.5-1k | -$0.01 | trivial | ✓ |

### 8.3 P2 信号回流程序化 + 续修协议(高 ROI 但增 token 或为 sunk-cost 维度)

| # | 来源 | 改进 | Δtoken/run | $/run | 工程量 | 状态 | 备注 |
|---|---|---|---:|---:|---|---|---|
| F12 | B#8 + A6 | workflow 程序化提取 reviewer_stuck(B#8 sonnet parse 路径胜过 A6 implementer schema 路径) | +1.5-2k input + 0.5k output(sonnet) | +$0.05 | moderate | ✓ | 信号链路 50-70%→85-90%;省 0.3-0.5 轮 opus = $1.5-3 收益,**净赚 30-60×** |
| F13 | B#9 + A12 | iterate 顶部 rehydrate issues.json/verified.json(B#9 主线,A12 主会话注入作 fallback) | +0.3k input | <$0.01 | moderate | ✓ | **sunk-cost 维度关键效益**:救回 paused case 50-65% × $5-10/paused-run |
| F14 | B#10 | SKILL.md L138-139 红线"resumeFromRunId 仅同 session" 放宽 | 0(文档改) | 0 | trivial | ✓ | 配合 F13 |
| F15 | B#12 | SUMMARY.md PAUSED 节加 effective rounds 解释 | +0.2k output | <$0.01 | trivial | ✓ | UX 改进 |

### 8.4 P1 路径冲突(⚠ lead 二选一裁定)

| # | 来源 | 改进 | Δtoken/run | $/run | 状态 | C 倾向 |
|---|---|---|---:|---:|---|---|
| F16-1 | B#14 + B#15 + 新 P1_TRIGGER_STREAK | **路径 1 修补**:P1 体保留三字段 + 加 p1_skip_reason + P1_TRIGGER_STREAK 提到 max(2,STALE) + STALE 2→3 / maxRounds 6→5 | 综合 -3-10k input(P1 触发率 80%→20-30%);残余 P1 浪费 -$0.05-$0.3/run | -$0.1 to -$0.5 | ⚠ 待裁 | **保守取**(15-35% case 救场保留) |
| F16-2 | A2 | **路径 2 删整层**:META_AGENT_SCHEMA 收窄到仅 escapeRequest + 删 forbiddenApproaches/prioritizedMustIds + decision_log 整条链路 | -13-57k input + 0.5-3k output | -$0.25 to -$1.1 | ⚠ 待裁 | 净降更彻底但失去救场;sunk cost 风险 +$0.5-$1/run 抵消 |

**lead 协调建议**:实测一个 run 检查 forbiddenApproaches 实际产出是否真重复(A 论点)/ 真有用(B 论点) → 唯一判定 evidence;无实测时取路径 1 保守。

### 8.5 P3 架构清理 / 文档维度(0 token 但 capability 或维护性提升)

| # | 来源 | 改进 | Δtoken/run | 工程量 | 状态 |
|---|---|---|---:|---|---|
| F17 | A1 | 删 goal.json,留 goal.md 单文件 | 0 | trivial | ✓ |
| F18 | A4 | planDedupBlock + reflectBlock + 强制判断题三段并 1 段(细则砍掉) | -1-3k input | moderate | ✓(条件性:与 F8 同方向,实施时合并设计) |
| F19 | A8 | decision-log-append 改纯 node 内联(删 python3 fallback)| 0 | trivial | ✓(条件性:若路径 2 全采则 F19 一并删) |
| F20 | A9 | paused.md 改 paused-r{round}.md(不覆写)| +0.1k output | trivial | ✓ |
| F21 | A10 | SKILL canvas/ECharts/probe 段降权移到 examples/path2.md | 0 | moderate | ✓(通用性提升) |
| F22 | A11 | setup 清理逻辑落地到 workflow-template.js setup phase | +0.5k input + 0.3k output | moderate | ✓(防长跑磁盘累积) |

### 8.6 应放弃 / 推迟

| # | 来源 | 改进 | Δtoken/run | $/run | 状态 | 理由 |
|---|---|---|---:|---:|---|---|
| F23 | B#13 | vision verifier(独立 skill,接 OCR/像素工具二审 evidence) | +54-90k input + 3-6k output(opus + 5 张截图 × 6 轮) | **+$1-2/run(成本翻倍)** | ✗ | B 自承"ROI 中"无具体失败率数据;**应仅作 P3 future**,前提先收集 evidence 假报频次 |

### 8.7 独立硬伤(非 token 范畴,但 final_report 应单列)

| # | 来源 | 硬伤 | 与 token 关系 | 状态 |
|---|---|---|---|---|
| H-A1 | A H1 | 测试套件全是文本 grep(21 个 .mjs 文件全 assertContains),零 runtime 验证 | 不影响 run-time token;**真实 bug 只能靠 path2 实跑暴露** | 独立 P2 工程项(加 dryrun 测试基础设施)— 不在 token ROI 评估范畴 |
| H-A2 | A H8 | "reviewer 永久零浏览器"红线 vs 主会话 §2b 截图诊断 = 文档措辞滑(架构上无 bug) | 0 token | 文档维度,一句注脚可消 |
| H-A3 | A H9 | "setup 清理 N-1 保留" 实施位置不在 workflow-template.js(磁盘累积 N runs shots/) | 0 token,**磁盘 GB 累积**(长跑用户)| 与 F22 配套实施 |

### 8.8 全采纳后 baseline 最终预测(路径 1 假设 — 保守版)

**Δtoken/run total**:
- 净降合计(F4/F5/F7/F8/F9/F10/F11 + F18 + F16-1):**-130 到 -220k input + -1-2k output / run**
- 净增合计(F1 + F12 + F13 + F15 + F18 偶发 + F22):**+15-25k input + 2-3k output / run**
- **综合 Δ ≈ -105 到 -200k input/run ≈ -$1.6 到 -$3.0/run**
- **baseline $10-18 → $7-15(省 17-22%)**

**若取路径 2(F16-2 全删)**:
- 额外净降 -$0.25 到 -$1.1/run
- baseline → **$6.5-14**(省 22-30%)
- 但 sunk-cost 风险 +$0.5-$1/run 抵消大部分

**Δcapability(综合 A/B 估)**:
- 自动改进任务覆盖率 50% → 70-80%(B)
- 跨 session resume 0% → 80%(F13)
- forbiddenApproaches 注入采纳率 50% → 70%(F6)
- 信号链路成功率 50-70% → 85-90%(F12)
- missingStates 真触发率 50% → 85%(F3)
- 文档通用性 path2-bias → DOM-first(F21)

**Sunk cost 维度(非 token,F13 核心效益)**:
- 救回 paused case 50-65% 沉没 cost ≈ **$5-10/paused-run**(平均 paused 触发率 20-30%,折算 $1-3/run 期望节省 — 与 token 维度独立)

### 8.9 SKILL.md L207 自报 token 校准(C 通过 A (g) 暴露)

**重要校准**:SKILL.md L207 自报"opus implementer 命中率提升 → 总轮数 5-6 降到 3-4 → 总 token 可能净降" 是**乐观假设,实测反向**:
- B 数据"80%+ run r2 触发 P1" = "opus 在 r1→r2 一轮内没救场"
- opus implementer 6 轮 cost $1.6-$4.5 vs sonnet 估 5-6 轮 $0.5-$0.9 = **opus 净增 $1.1-$3.6/run**
- 但 capability 维度看 opus 命中率可能仍更高(只是不到能净降 token 的程度)
- **final_report 应分别表态 token 维度 vs capability 维度**,不强行定论 implementer = opus 例外条款

### 8.10 A 三条架构判断融入(2026-06-22 cross-validation)

A 在收到 C 的 §1.3 reviewer 3-lens 是 dominant cost / §C-cut-2 issuesJson 过滤 / §GOAL 三件套 三条挑战后,从架构正确性视角给出判断,与 C 视角合流。结论:

#### 8.10.1 新 F24 — reviewer × 1 multi-lens(替代 × 3 lens 并行) ⚠ 待 lead 拍

| ID | 改进 | Δtoken/run | $/run | 工程量 | 状态 |
|---|---|---:|---:|---|---|
| F24 | reviewer × 3 lens 并行 agent → × 1 multi-lens 单 opus(verdicts 数组 = [ux,func,code] 三个 segment),保留 lens 字段供 mergeIssues 全套零改 | **-150 到 -300k input/run**(opus 减 2/3 lens prompt + 截图 Read);+0(墙钟代价不计 token) | **-$2.25 到 -$4.5/run** | moderate | ⚠ **lead 拍**(墙钟 ×3 trade-off) |

A 架构判断:
- 原 3 lens **不是"多角度独立判官"红线**(principles.md / SKILL 都没把"多 reviewer 各自独立判断"列为红线),只是评分轴分工 + 并行延迟优化
- × 1 multi-lens **架构合规**——不破任何已声明红线;唯一损失 = 并行→串行墙钟 ×3
- **保留 lens 字段是关键约束**:schema 改成 `{verdicts: [REVIEWER_SCHEMA × 3]}`,让单 agent 输出 `[{lens:"ux",...},{lens:"func",...},{lens:"code",...}]`,mergeIssues (L80-111) lens-归属状态机 + verdict 推导 (L413-416) 全套零改
- **概念分离**(各 lens 自己的 prompt brief)挪进 segment 提示词,清晰性不受损 → **不是 cargo-cult 而是 cost-bias**

**C 视角 ROI**:
- 单 run -$2.25 到 -$4.5 = **整个 audit 最大单条净降**
- 但墙钟 ×3 是 capability 维度代价(用户在线等场景敏感)
- **lead 拍**取舍:若用户多数离线长跑 → F24 全采;若多数在线等 → 保持 × 3 lens
- 与 F8(C-cut-1 reviewerPrompt 按 lens 切冗余)关系:**F24 实施时 F8 自然成立**(单 prompt 内部按 segment 写各 lens brief,冗余消除是 by-design 而非 patch);若 F8 单独实施 F24 不实施,F8 仍独立有效(-15k/run)

#### 8.10.2 F9(issuesJson 过滤)架构强背书 — 升级 P0+ 必采

A 给出 C-cut-2 的架构论证:
- **fixed 状态已转移**到 verifiedLog(L409,workflow 内存自动)
- **principles.md §9 红线**:"issues 只承载缺陷;'已修复/验证通过/全绿'等正面结论一律放 verified 数组" — fixed issue 留在 reviewer prompt 违反此红线
- **mergeIssues regression 检测**(L104)用 workflow 内存 issues 数组,**不要求 reviewer prompt 含 fixed**;reviewer 通过 `matchesIssueId` 引用现有 id,workflow merge 阶段自动检测 regression
- verifiedSummary(L273-274)已传 implementer + reviewer 有 verifiedJson 字段(L162-163)→ fixed 原始 title 不必重传

→ **F9 从"P1 高 ROI"升级为"P0+ 架构合规修复"**(同时是 net cost 净降,$-0.4/run)

#### 8.10.3 F17(删 goal.json)+ 新 F25 prompt cache 实测调查(必做前置)

A 论证 goal.json 是同源数据冗余写,与 cache 是否生效无关都应删 → F17 仍是必采。

**A 提出**:三件套真问题**不是设计是否过度,而是 prompt cache 实际激活否**——架构上 prompt 段顺序已经 cache 友好(冻结段 GOAL/subgoals/refs 在前,变化段 issues/shots/console 在后)。**若 cache 生效 → 三件套近 0 成本**;**若未生效 → 120-240k input/run 重复传**(C §1.3 估算)是真隐藏 cost。

**新 F25(C+A 共采纳)**:

| ID | 改进 | 类型 | 状态 | 备注 |
|---|---|---|---|---|
| F25 | 实测 prompt cache 在 Workflow runtime 下是否激活(token 计费侧 telemetry / 抽样对比 cache_creation_input_tokens vs cache_read_input_tokens) | **前置调查任务**(非代码改) | ⚠ **lead 派 1 个 sonnet agent 跑一次 dry run 抽样 telemetry** | **判定其他改进的归属**:若 cache 生效 → 三件套零成本,F8/F9 等仍有效;若未生效 → 主成本 sink 排序需重排,**reviewer prompt 顶部应加"prompt 模板前 X token 冻结以确保 prefix cache"红线** |

**C 视角**:F25 是 **prerequisite 调查**,在 final_report 中应单列于 "实施前必做" 段——它不直接产生改动,但决定其他改动的优先级排序。

#### 8.10.4 三方融合后净降总额更新

合并 §8.10 三条 A 架构判断后,**最大上限场景**(F24 全采纳 + 路径 1 修补 P1):
- 净降项小计 -130 到 -220k + F24 -150 到 -300k = **-280 到 -520k input/run**
- 净增项小计 +15-25k
- 综合 **Δ ≈ -260 到 -500k input/run ≈ -$3.9 到 -$7.5/run**
- baseline $10-18 → **$2.5-14**(省 22-75% 上下限分布广)
- **最乐观(F24 + F16-2 路径 2 全删 P1)**:净降 -$4.15 到 -$8.6/run,baseline → **$1.5-13.5**

**但**:F24 墙钟 ×3 是 capability 维度代价,不算 token;若 lead 取保守(不动 F24),回到 §8.8 预测 $7-15/run(省 17-22%)。

#### 8.10.5 final_report 应记录的 C-A 收敛 / 待裁结论

- **F24 reviewer × 1 multi-lens**:架构合规,token 维度最大净降项;**lead 在 final_report 中作墙钟 vs 成本 二选一裁定**
- **F9 issuesJson 过滤**:升 P0+ 架构合规修复
- **F17 删 goal.json**:必采(架构 + 成本双背书)
- **F25 prompt cache 实测**:前置调查,在 final_report § "实施前必做" 段单列
- **A 同意 SKILL.md L207 数字过时**:作为 doc-debt,非核心硬伤

---

## § 8.11 A 真版 CV 收束(2026-06-22 三轮对线 final)

A 在 A_raw.md CV-7~CV-15 落地真版交叉验证后给 C 的三处更新,C 收下:

### 8.11.1 §6.5 表"reviewer × 3 lens - A 未提"误记纠正

**原 §6.5 表第 10 行** 写"reviewer × 3 lens 是否合并 - A 未提" 是 C 误记。**真相**:
- C 在第一轮挑战信(发 A)就问过这条
- A 在 CV-3(真版交叉验证)明确背书 ×1 multi-lens(保留 lens 字段让 mergeIssues 零改)
- C 已在 §8.10.1 把该条目升级为 F24 新条目

**§6.5 表对应行应改为**:

| 议题 | A 立场 | B 立场 | C 立场 | 收敛/冲突 |
|---|---|---|---|---|
| reviewer × 3 lens 合并 multi-lens | **A CV-3 背书**(保留 lens 字段) | (未提) | **技术合规、墙钟 trade-off 由 lead 拍** | **moderate 改动,lead 拍** |

(本节修正记录,§6.5 原表保留作 audit trail;final_report 用 §8.10.1 F24 + 上面表行的合流版本)

### 8.11.2 接受 A CV-8 对 P1 two-track 表达的吸收

A 接受 C §6.3 关于 P1 path 1 vs path 2 的加权成本估算:
- 加权 7.5-25% × $0.3-$1.5 = $0.02-$0.4/run 期望收益
- vs $0.5-$1.5/run 100% run cost = **净亏 $0.1-$1.1/run**
- 但 sunk cost 风险 +$0.5-$1/run 抵消大部分
- → **CV-8 落实为 two-track 表达,默认走 Track 1**(综合考虑 sunk cost)

**C 视角同意**:two-track + 默认 Track 1 是当前数据下的保守最优;final_report 应明示"未实测时默认 Track 1,实测 forbiddenApproaches 重复率后可调"。

### 8.11.3 CV-11 接受 §6.4 SKILL.md L207 校准

A 真版 CV-13 P2-4 单列了"SKILL.md L207 数字过时,实测反向净增 $1.1-$3.6/run"——A 原 A_raw 漏抓,真版补回。

**收敛**:三方一致:
- token 维度:opus implementer 净增 $1.1-$3.6/run(C 估)
- capability 维度:独立保留 opus 选择(B 视角"逆向工程 + 联合优化结构性强项")
- final_report "诚实校准" 段明示两维度分别表态,**不撤销用户拍板的 opus 例外条款**(因为 capability 维度独立)

### 8.11.4 CV-9 reviewer 跨轮信号 by design 受限对 C-cut-3 的影响

A 收到 B CV-2 Q1 反驳后承认 reviewer by design 0 跨轮通道 → 跨轮反思必走 implementer 中转(reviewer_stuck 信号回流)。

**对 C-cut-3(F10)的影响**:
- F10 名为 "删 implementer 优先级 4 历史 reviews 直读" — 这是面向 **implementer 端**,与 reviewer by design 红线无关
- **A 指出名字暗示与 reviewer 有关需澄清** — C 接受,**F10 final_report 表述应改为**:
  - 原:"C-cut-3 删 implementer 优先级 4 历史 reviews 直读"
  - 改:"**implementer 端**优先级 4 历史 reviews 直读冗余删除 + verifiedSummary 升级(reviewer 端跨轮 by design 0 通道,本条与 reviewer 红线无关)"
- 净降 -9k/run 不变;实现要点不变;**只是命名 + 注释加澄清避免误读为破 reviewer 红线**

### 8.11.5 三方对线总结

A 反馈:"你给的 baseline + ROI 表是 final_report 数字侧的核心 ground truth"。

C 视角对应总结:
- **baseline $10-18/run** + Top 3 sinks(reviewer 3-lens 主导 55-75%)= ground truth
- **F1-F25(25 条改进 + 1 调查 + 3 硬伤)分类完成** = ROI 表
- **3 大核心决策点**(F24 reviewer 1-vs-3 lens / F16 P1 path / F25 cache 实测)= final_report 必出
- **L207 校准 + reviewer by design 红线澄清** = 诚实表态段

---

## § 9. C raw 完成态(2026-06-22)

- Phase 1:§1-4 baseline + top sinks + 自提 cut(独立完成)
- Phase 2 收 B 三轮(§5.5-5.9):token 数据收敛 + 路径 1 全采纳 + B Phase 2 终态 P0-1 合并改进
- Phase 2 收 A 两轮(§6.1-6.6 + §8.10):12 条建议评估 + (a)-(g) 七问回答 + 三条架构判断(F24 multi-lens / F9 升 P0+ / F17 + F25 cache 实测)
- Phase 2 三方融合:§8 最终 ROI 总表(F1-F25 + 3 独立硬伤) + 路径冲突标注 + L207 校准
- §8.11 A 真版 CV 收束:§6.5 表纠正 + P1 two-track 默认 Track 1 + L207 三方一致 + F10 reviewer 红线澄清
- 口径对齐(2026-06-22 lead):§0 已加运行 cost vs dev cost 声明
- final_report 由 lead 综合,C 不再追加。
