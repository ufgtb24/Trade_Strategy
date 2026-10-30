# Workflow 运行时事实（给本次 team 用的参考）

> lead 于 2026-10-29 从内置 `workflow-authoring` 参考与 Workflow 工具说明摘出，外加两次真实 run 的实测观察。标「参考」的是官方参考原文的转述；标「实测」的是真跑观察到的；标「冲突」的需要 lead 真跑确认（只有主会话能调 Workflow，teammate 调不了）。

## 脚本形态

- 【参考】脚本必须以 `export const meta = {...}` 开头，meta 是纯字面量；`name`、`description` 必填；`phases` 每项是 `{ title, detail? }`，`phase()` 调用的标题须与之逐字一致（现模板写的是字符串数组 `["setup","iterate","finalize"]`，不合参考写法）。
- 【参考】脚本体在 async 上下文里跑，可直接 `await`。参考里的示例都以**顶层 `return <值>`** 结束，返回值就是 Workflow 交回主会话的结果。
- 【冲突】项目记忆 `project_web_loop_skill.md` 与模板头注释都说「顶层 return 在 ESM module 非法，必须裸顶层 `node --check`」。参考是更新的权威来源，倾向于「顶层 return 合法」。lead 会用一个不派 agent 的最小脚本真跑确认；设计可以依赖顶层 return，但要写明「若实测不接受」时的退路。若确认合法，「裸顶层 node --check」的检查方式要改成能容纳顶层 return 的（例如去掉 `export` 后包进 async 函数再 check）。
- 【参考】纯 JavaScript，不能有 TS 语法；无文件系统、无 Node API；`Date.now()`、`Math.random()`、无参 `new Date()` 会抛错（破坏 resume）。

## agent() 选项与返回

- 【参考】`agent(prompt, { label, phase, schema, model, effort, isolation, agentType })`：
  - `schema`：强制子代理用 StructuredOutput 交回、返回校验后的对象；根须 `{type:'object', properties:{...}}`，`required ⊆ properties`。
  - `model`：默认继承主会话模型；只在很有把握时覆盖。
  - `effort`：`'low' | 'medium' | 'high' | 'xhigh' | 'max'`；参考建议机械阶段用 `'low'`。**这是现模板没用上的省 token 手段。**
  - `isolation: 'worktree'`：贵，且 web-loop 红线禁用（外部 dev server 的 HMR 看不到隔离副本）。
  - `agentType`：用自定义子代理类型（与 Agent 工具同一注册表，即 `.claude/agents/*.md` 等），可借此限制工具；与 schema 可组合。
- 【参考】子代理被用户跳过、或因 API 终止性错误死掉时，`agent()` 返回 **null**。所有调用点都要处理 null。
- 【参考】`parallel(thunks)` 是屏障，某个 thunk 抛错时该位置为 null，调用本身不抛；`pipeline(items, ...stages)` 无屏障，是多阶段的默认选择。
- 【参考】并发上限 min(16, CPU 数−2)；单个 workflow 生命周期内 agent 总数上限 1000。
- 【参考】`budget` 只在用户给了「+500k」这类 token 目标时有意义：没设时 `budget.total` 为 null、`remaining()` 为 Infinity；设了就是硬上限，超了 `agent()` 抛错。所以「代理数上限」要脚本自己计数，不能靠 budget。
- 【参考】子代理开工时会注入和主会话一样的 CLAUDE.md（Explore、Plan 这类内置类型除外）。**prompt 里不要复述 CLAUDE.md 的规矩**，需要哪条点名即可。
- 【参考】workflow 子代理可通过 ToolSearch 用会话连接的 MCP 工具（playwright MCP 即此）。

## args

- 【参考】`args` 原样传入；应传真实 JSON 值。
- 【实测】项目记忆记载真 runtime 曾把 args 整体序列化成 JSON 字符串（`typeof args==='string'`）。现模板对两种都兼容（字符串则 JSON.parse），保留这一兼容。

## resume

- 【参考】`Workflow({ scriptPath, resumeFromRunId: "wf_..." })`。runId 是 Workflow 启动时返回的 `wf_xxx`，**不是** web-loop 的 runtag。
- 【参考】按 agent() 调用顺序，**最长的未变前缀**直接返回缓存结果；第一个 prompt/opts 变了的调用及其后所有调用实跑。同脚本同 args → 100% 命中缓存。
- 推论：暂停判据只取决于缓存结果时，原样 resume 会在同一处再判一次暂停。只往磁盘放一个 human-hint 文件、prompt 文本不变，不会让任何调用失效。

## 两次真实 run 里观察到的运行环境行为

- 【实测】子代理用 Write 写 `SUMMARY.md` 被拒：`<tool_use_error>Subagents should return findings as text, not write report files. Include this content in your final response instead.</tool_use_error>`（run A、run B 各一次）。同批子代理用 Write 写 `impl.md`、`preflight.md`、`goal.md` 没被拦；用 Bash 写 `round_N.md`、`issues.json` 没被拦。拦截依据（文件名 / 内容）未知。**设计上不要让子代理写「报告型」Markdown 文件；用 Bash 绕过属于绕开环境有意设的拦截，不采用。**
- 【实测】主会话用 SendMessage 回复 workflow 子代理，会「Resuming agent」拉起一个同 id 的副本并发干活（run B r02）。workflow 子代理的系统提示里能看到可发消息的对象列表，所以 prompt 里须明令禁止它们 SendMessage / ListAgents。
- 【实测】只有主会话能调 Workflow；teammate / subagent 调不了。任何真跑验证都要交给 lead。

## 两次 run 的规模（对照用）

| | run A | run B |
|---|---|---|
| 评审角度 | 6 | 6 |
| 轮数 | 3（收敛） | 3（第 3 轮误判暂停；第 2 轮整轮跳过） |
| agent 数 | 42 | 34 |
| 墙钟 | 1 小时 54 分 | 1 小时 35 分 |
| 输出 token | 约 145 万 | 约 96 万 |
| 缓存读取 token | 约 1.54 亿 | 约 1.31 亿 |
| 输出 token 里评审占比 | 约 69% | （同量级） |

单轮各阶段耗时：implementer 10～21 分钟；评审墙钟 13～16 分钟（rival 每轮最慢，572～965 秒）；persist 2.3～6.4 分钟且逐轮变长；smoke + refresh + capture 合计 2～3 分钟。

## lead 实测结果（2026-10-29，探针 run `wf_a163e693-730`，2 个低开销 agent）

以下结论**取代**上文标「冲突」「未知」的条目：

- **顶层 `return` 合法**：脚本末尾 `return {...}`，Workflow 把这个对象原样交回主会话。所以 finalize 可以把 SUMMARY 全文作为返回值交回，由主会话写文件。项目记忆和模板头注释里「顶层 return 非法」已过时；模板的语法检查要改成能容纳顶层 return 的方式。
- **args 这次到达时是对象**（`typeof args === 'object'`）。保留对字符串的兼容解析即可。
- **子代理写文件拦截只命中 `SUMMARY.md`**：同一个子代理用 Write 写 `SUMMARY.md` 被拒（同样的 `Subagents should return findings as text...`）；写 `directions.md`、`baseline_counts.md`、`impl.md`、`review_ux.md`、`round_01_ux.json`、`notes.txt` 全部成功。拦截看来按文件名（至少 SUMMARY 这类名字）判断。设计上：SUMMARY 由主会话写；其他 md / json 子代理可以写。不要用改名绕开拦截。
- **agentType 能换掉工具集，但内置类型去不掉 SendMessage**：`agentType:'Explore'` 的子代理没有 Write / Edit / NotebookEdit / Artifact，但仍有 Bash、SendMessage、ListAgents 和全部 playwright MCP 工具。默认的 workflow 子代理两者都有。要从工具层面去掉 SendMessage 或浏览器，只能用带显式工具白名单的自定义子代理类型（放 `.claude/agents/`；未实测，也不确定会话中途新建能否被识别）。
- **每个新 agent 的起步上下文**：默认 workflow 子代理第一次调用模型时上下文约 **5.6 万 token**（系统提示 + CLAUDE.md + 记忆索引 + 工具定义 + 任务 prompt），Explore 类型约 **2.1 万**（不注入 CLAUDE.md）。之后每调一次工具，都要把累积的整段上下文再读一遍（走缓存读取）。所以一个机械 agent 的开销 ≈ 起步上下文 × 工具调用次数：少开 agent、少调工具、prompt 别塞冗余，比换模型更省。对照：run B 缓存写入约 480 万 / 34 个 agent ≈ 每个 14 万。
- **resume 原样重放已实测**：同脚本、同 args 续跑，6 毫秒返回，0 token、0 次工具调用，两个 agent 全部取缓存。所以暂停后原样 resume 一定在同一处再停；续跑必须改变某次调用的 prompt / opts（或起新 run 注入台账）。

## lead 实测结果 · 第二批（探针 run `wf_6feba183-903`，1 个 agent；另查前一探针的落盘文件）

- **scriptPath 可以直接启动仓库内的脚本文件**（`repro/probe2.workflow.js`），不必把全文粘进 `script`。
- **`model:'sonnet'` 生效**（agent 记录里是 claude-sonnet-5-5）；不写 model 时继承会话模型 claude-opus-5-5。**`effort:'low'` 被接受**，记进了 agent 记录。sonnet 的起步上下文同样约 5.4 万 token，换模型省的是单价，省不掉起步量。
- **journal 格式**：`<Transcript dir>/journal.jsonl`，依次是 `launched`、每个 agent 一条 `started`（key、agentId、label、phase），再一条 `result`（key、agentId、result 为完整返回值、toolsUsed）。边跑边写。
- **journal 不记 workflow 的最终返回值**。最终返回值在 `<会话目录>/workflows/<runId>.json` 的 `result` 字段（同文件有 args、status、totalTokens、defaultModel），且**会被 resume 覆盖**（resume 后记的是重放那次，totalTokens 为 0）。resume 命中缓存的调用不往 journal 追加新行。
- **journal 的目录会变**：run A、B 的 journal 开跑时在 worktree slug 目录下，后来出现在主目录 slug 下；`/branch` 后新 run 落在新会话 id 目录。依赖 journal 的工具不能猜路径，要由主会话在启动时记下 Transcript dir 和 runId，结束时把 journal 拷进运行目录。

## lead 实测结果 · 第三批（探针 `wf_5bd9fe37-d90`、`wf_fd80c6c7-ac3`）

- **子代理起的后台服务能否活过子代理**：`nohup 命令 > log 2>&1 &` 和 `setsid nohup … &` 起的服务，在子代理结束后仍然活着；Bash 工具 `run_in_background:true` 起的服务会随子代理一起结束。子代理 Bash 里 `echo $!` 记到的是外层包装 shell 的进程号（不是监听端口的进程），杀旧进程只能按端口查。
- **长命令**：前台 `sleep 240` 会被 Bash 工具直接拦下（提示改用 Monitor 或后台）。一条真正跑 240 秒的前台命令（Bash 调用设 `timeout:300000`）正常跑完，没有被判成卡住。注意 Bash 工具默认超时 2 分钟、上限 10 分钟，超过 2 分钟的命令要显式设 timeout，超过 10 分钟的要改成后台起 + 按条件轮询。
- **Explore 类型**：实测用的模型与会话相同（claude-opus-5-5）；系统提示写明「CRITICAL: READ-ONLY MODE … STRICTLY PROHIBITED from creating new files」，所以凡是要写文件、改文件、起进程的环节都不能用它。
- **子代理能找到并复制本 run 的 journal**：`find ~/.claude/projects -path '*subagents/workflows/*/journal.jsonl' -mmin -10` 再 grep 自己唯一的 label，可以定位到并 cp 出来。
