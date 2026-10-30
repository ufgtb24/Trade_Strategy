# 现有 24 个测试审计（2026-10-29）

结论：真正执行模板代码的只有 2 个（`test-mergeissues-fieldflow`、`test-reviewer-prompt-adversarial`，都靠正则从源码里抠出函数再 `new Function`/import，抠法本身脆弱）。其余 22 个在源码或 SKILL.md 里找字符串，行为对错一概不管。`test-examples-path2` 现在就是红的（`examples/path2.md` 过时），其余全绿。

处置建议：**删** = 删除并由 dryrun 场景代替；**改** = 保留意图，改成断言「渲染出来的 prompt / 调用选项」；**留** = 保留。最终删改等设计定稿后做。

| 文件 | 在测什么 | 约束行为吗 | 建议 |
|---|---|---|---|
| test-baseline | 源码含 `export const meta`、`phase("setup")` 等 | 否；且与新模板（顶层 return、phases 对象形态）冲突 | 删；由 G0（模板能跑、phases 被调用）代替 |
| test-args-helpers | 含 `function safeInsert` 等字符串；测试内另写了一份 safeInsertExpect 自测 | 否（测的是测试里自带的副本） | 改：若 safeInsert 保留，用 dryrun 渲染 write-goal 的 prompt，断言含特殊字符的 goal 被转义后可解析；否则删 |
| test-converged-logic | 收敛式写成 `allPass && openMust.length===0 && allSubgoalsCovered` | 否；且与第 12 条（verdict 由台账推导、unverifiable 不挡收敛）相冲 | 删；由 U1、U2 及新增「子项只认指定 lens」场景代替 |
| test-examples-path2 | `examples/path2.md` 含若干字符串 | 否；现已失败（过时） | 随 examples 重写一起改：断言文档里的 args JSON 能被 `JSON.parse`、字段名都在模板读取的 args 集合里 |
| test-finalize-paused | finalize 含 PAUSED 节、`resumeFromRunId` | 否；`resumeFromRunId: "<runtag>"` 本身是错的 | 删；由 T4 + 新增「暂停时 SUMMARY 含续修指引且不含 runtag 误用」场景代替 |
| test-finalize-summary | finalize 含若干节标题 | 否 | 改：dryrun 取 finalize 的返回值/prompt，断言各节存在（第 11 条后 SUMMARY 是返回值） |
| test-implementer-opus | `model: "opus"` 正则 | 弱 | 改：断言 `impl-*` 调用的 `opts.model`（若设计保留 opus） |
| test-implementer-prompt-priority | prompt 内权威等级用语，跨 5000 字符的正则 | 否 | 改：断言真实渲染出的 impl prompt（含 hint 通配、forbidden、nextStepPlan）；H1、S1 已覆盖一部分 |
| test-implementer-prompt | prompt 含 GOAL/子项/参考图段 | 否 | 改：同上，渲染后断言 |
| test-implementer-schema-reviewerstuck | 正则抠 agent 调用块，看含 `reviewer_stuck` 等字面 | 否 | 改：断言 `opts.schema.properties` 字段；S8 覆盖使用侧 |
| test-mergeissues-fieldflow | **真跑** mergeIssues，抠函数后 import | 是 | 留并扩（第 14、17、21 条字段保留/查无 id/跨 lens 去重）；抠函数的方式随重构改成 dryrun 观察台账 |
| test-p1-implementer-inject | `forbiddenList`、`不得重试` 字面 | 否 | 改：渲染断言；设计若删 read-state/改 forbidden 记账则随之改 |
| test-p1-meta-agent | META_AGENT_SCHEMA 字面 + 枚举字符串 | 否 | 改：触发 meta-agent 的场景里断言 `opts.schema` 与 prompt；设计若删 meta-agent 则删 |
| test-reviewer-prompt | reviewerPrompt 含若干段落字面 | 否 | 改：取 `review-*` 调用的真实 prompt 断言（含第 12 条新增硬规则） |
| test-reviewer-prompt-adversarial | **真跑** reviewerPrompt 并检查对抗 lens 注入 | 是 | 留；抠函数方式不稳，设计若重构函数则改成取 dryrun 的 prompt |
| test-reviewer-prompt-rootcause | 同上，rootCause 相关字面 | 否 | 改：渲染断言 |
| test-reviewer-schema | REVIEWER_SCHEMA 字面 | 弱 | 改：断言 `opts.schema`（unverifiable 必须填 requiredStates 的收紧也在这里测） |
| test-reviewer-schema-rootcause | schema 字段正则 | 弱 | 同上，并入 test-reviewer-schema |
| test-reviewerprompt-stuck-injection | 函数签名含 stuckSignal、不含某条 cat 命令 | 否 | 删；S8 覆盖 |
| test-setup-write-goal | write-goal 的 label/phase 字面 | 否 | 改：断言 write-goal 调用存在且 prompt 含 goal 文本 |
| test-skill-doc-decision | SKILL.md 字面；还钉死了 `implementer = opus`、`§5.1`（清单要求删的失效出处） | 否；会阻碍清单里的文档修订 | 删；换成一个文档一致性测试（见下） |
| test-skill-doc-p1 | SKILL.md 含 P1 meta-agent 字面 | 否 | 删（同上） |
| test-skill-doc | SKILL.md args 表含若干字段 | 弱 | 改成文档一致性测试 |
| test-stall-criteria | 三个判据变量名字面 | 否 | 删；由 T1/T2/T3/S2b 及新增 oscillating 场景代替 |

## 建议新增的非场景测试：文档与模板一致性（真有约束力）

1. 模板读取的每个 `A.xxx` 字段都出现在 SKILL.md 的 args 表里（反向：表里的字段模板都读）。
2. SKILL.md 与模板里不得出现 `resumeFromRunId: "<runtag>"` / `${RUNTAG}` 这种错误用法。
3. 模板里引用的 `${WORKDIR}/...` 文件名（paused.latest.md 等）在 SKILL.md 里写法一致。
4. description 不含内部词（Workflow、smoke、refresh、rubric、reviewer）。
5. 模板里没有 `Date.now`、`Math.random`、无参 `new Date`（dryrun 外壳已让它们抛错，G0 即覆盖）。
