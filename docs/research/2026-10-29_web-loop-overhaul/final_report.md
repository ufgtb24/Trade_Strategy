# web-loop 重构最终报告（2026-10-29～30，agent team）

> 本文中所有项目内路径均相对 worktree 根 `.claude/worktrees/annotation-web-loop/`（分支 `annotation-web-loop`）。改的是这个 worktree 里的 `.claude/skills/web-loop/`，主目录那份没动。
> 读者：下一轮没有本次对话上下文的 AI。限定条件、口径和出处都写在正文里，不靠对话记忆。
> 状态：代码与文档已实施，**未提交**，提交需用户另行要求。测试（§4）与验收（§8）已补齐。L4 真跑查出的 V1、V2 已修，见 §8.2。
> 出处：
> - 原始问题：`原始问题.md`
> - 改动清单：`docs/tmp/2026-10-29-web-loop-improvements.md`，第 0～28 条，文末有「改完后要同步的文档」
> - 设计定稿：`design.md`，实施依据是 §2，偏差记在 §2.16
> - 审查：`review_design.md`（设计审查，K、R、S、T、U、V、X 各编号），`review_impl.md`（实施审查，I、M 编号）
> - 运行时实测：`workflow_runtime_facts.md` 末尾三批「lead 实测结果」
> - 以上文件除改动清单外，都在本目录 `docs/research/2026-10-29_web-loop-overhaul/`

## 0. 一句话结论

旧 web-loop 的毛病有三个根子：
- Workflow 脚本读写不了文件，于是让 LLM 来回抄 JSON（persist、read-state、read-impl-stuck、finalize、paused）；
- 截图让 LLM 每轮现写脚本；
- 判据拼在评审回填的字段和从没跑过的机制上。

这次的改法：
- 台账只放在脚本内存里，由纯函数推进。
- 确定性的活交给 skill 自带的两个 node 程序：`wl.mjs`、`capture.mjs`。
- 落盘靠运行时自己的 journal 回放导出，不经任何 LLM 抄写。
- 判据收成几种能写出公式的出口。

每轮 agent 从「7 个机械 agent 加 N 个评审」降为「implementer、verify 各 1 个加 N 个评审」，setup 和 finalize 一个 agent 都不派。新增原型模式（第 28 条），流程骨架不变。

验收（§8）：
- 在标注原型上用原型模式真跑了 2 轮，跑通。
- 真跑查出 1 个 must：verify 交回的形状有歧义，导致第 1 轮没有评审。已修，并用真跑的 journal 重放核对过。
- token：省下来的主要是砍掉的机械 agent，每轮 5 个，run B 每轮 12～14 个。implementer 和评审单次的输出与旧版同一量级。剩下最大的开销是 implementer 的缓存读取，每次 1200 万～1400 万。
- 测试：run-all 4 个文件、92 个场景全部通过。

## 1. 背景

- 用户原话（逐字）：「根据‘改动清单’，从第一性原理出发，釜底抽薪的修复并优化 web-loop，让它没有漏洞，更高效，更强大，并且避免 tokens 浪费。」
- 证据来源是两次真实运行，都跑在同一个静态 HTML 标注原型（`mock_v4.html`）上：
  - run A：`.claude/web-loop/2026-10-28_annotation-v4/`，6 个角度、3 轮、42 个 agent，收敛，约 145 万输出 token；
  - run B：`.claude/web-loop/2026-10-29_annotation-v5/`，6 个角度、3 轮、34 个 agent，第 3 轮被 treadmill 误判暂停，约 96 万输出 token。
  - 两次 run 的评审都约占输出 token 的 69%，各类 agent 的实测 token 见 `design.md` 文末附表。
- 用户在过程中定下的总原则：
  - 为弥补旧模型（Opus 4.6）能力不足而加的机制可以不要。
  - 流程骨架固定。动态只发生在开跑前（填参数、起草并冻结验收标准）；开跑后只留由人或主会话发起的受控改口通道。
- 团队采纳了 lead 的分类建议：与模型强弱无关的结构性约束保留、只修实现。这个分类是 lead 提的，不是用户原话；用户认可的是上一条总原则。结构性约束指：
  - 脚本读不了文件；
  - 浏览器单例会串台；
  - 停止要靠固定标准；
  - 证据由被评方以外的人采集；
  - 计数和归属由脚本确定性完成；
  - 回归检查和回滚；
  - 运行环境的拦截与红线。
- 用户拍板过的决定：
  - Q1：SUMMARY 由程序按台账生成，白话解读由主会话在对话里讲；
  - 第 26、27、28 条并入；
  - description 重写、名字不改。

## 2. 改动清单逐条落实

「落实」= 按清单做了；「改了再落实」= 目的照办、做法换了；「被取代」= 由更根本的改法覆盖；「删除」= 不做或整块删掉。

| # | 处理 | 落在哪 | 理由 |
|---|---|---|---|
| 0 真跑控制流的测试外壳 | 改了再落实 | `tests/dryrun.mjs`、`tests/wl-fixture.mjs`、各 test 文件 | 外壳把模板正文的 INJECT 段替换掉，再包进 AsyncFunction 执行，能容纳顶层 return；parallel 按真语义实现（thunk 抛错时该位置为 null）。CORE 用 `wl.mjs` 的 loadCore 加载做单元测试。原 24 个找字符串的测试，凡是钉住已删机制的都删了 |
| 1 回滚只退本轮 | 改了再落实 | `wl.mjs` verify 第 2 步、restore | 由 node 用 git 临时 index 拍快照，不碰真 index、HEAD 和 stash，只退本轮开工前到交回后变了的路径；statesPath、rubric、`.claude/web-loop/` 豁免。smoke 红先原样复测一次；仍红才退回，退回后再跑 smoke：变绿立 `wf-regress`，仍红判定环境坏了，把改动放回去，以 blocked 结束。不再让 LLM 执行 `git checkout -- .` |
| 2 环节出错不悄悄跳过整轮 | 改了再落实 | 模板 reviewGate、reduceRound | implementer 返回空时，kind 取上一轮的值；连续 2 轮评审不了 → blocked；跳过原因进 SUMMARY 走势表。「implementer 未交回」只记在轮次记录里，不立 must |
| 3 子代理不等主会话回复 | 改了再落实 | 模板 COMMON 段、各 schema 的 `toMain` 字段、SKILL 红线 | 用 schema 字段 toMain 代替 to-main 文件，`wl.mjs status` 从 journal 里读出来；禁止子代理 SendMessage、ListAgents 和 git 写操作；主会话不得回复 workflow 子代理；hint 改为「所有没处理过的控制文件」 |
| 4 评审结果落盘、台账不来回抄 | 被取代 | journal 加 `wl.mjs export` | 评审只用 schema 交回，不写文件，否则同一份内容要生成两遍；删掉 persist。`reviews/round_NN/<lens>.json` 由 export 从 journal 写出 |
| 5 代理数上限 | 落实 | SHELL 的 `call()` 计数、`maxAgents` | 开轮前预估「2 + 角度数」，超了以 budget 结束；agent() 抛错时被接住，同样以 budget 结束；外层 try/catch 兜意外异常，以 error 结束 |
| 6 删白跑的 agent | 落实并扩大 | 模板 | 删掉 read-state、read-impl-stuck、smoke、refresh、capture、capture-fallback、persist、rollback、paused、decision-log、meta-agent、finalize；setup 的 4 个 agent 移进 `wl.mjs init`，由主会话开跑前执行 |
| 7 截图清单可以中途改 | 落实 | statesPath | args 里只认 statesPath（删掉 `states`），截图器每轮重新读这个文件 |
| 8 起点图 r00 | 改了再落实 | `wl.mjs init` | 开跑前截 r00，同时充当配方体检，有失败态就不让开跑。另出缩略总览 `r00_contact.png`，主会话只看这一张。razor 的起点计数用 schema 字段 `counts.baseline` 交回 |
| 9 截图脚本复用、视口统一 | 被取代 | `capture.mjs` | skill 自带通用截图器，执行结构化配方（steps、probe、expect、crops、viewport）；args 加 viewport，默认 2560×1440、DSF 1；manifest 按轮命名 |
| 10 treadmill 误报 | 被取代（删除） | 模板 reduceRound | 按用户的总原则删掉 treadmill、oscillating、missingStates、P1 meta-agent。停滞改成一条：连续 staleRounds 轮既没有确证 must 被修好，同一轮达成的子项个数也没有刷新历史最高 |
| 11 finalize 写不了 SUMMARY | 被取代 | `wl.mjs export` 加 renderSummary | 删掉 finalize agent，SUMMARY 由纯函数渲染、由 node 写盘。顶层 return 实测合法，只交回出口和精简台账 compactLedger |
| 12 证据缺口不挡收敛，verdict 由台账推导 | 改了再落实 | 模板 reduceRound | 子项只认 args 里点名的负责角度；unverifiable 只在 requiredStates 点名了「本轮没截成功的态」时才采信；截图失败的态上判 met 降为 unverifiable、判 gone 不生效；还有 unverifiable 时以 evidence-gap 结束，不算收敛 |
| 13 用上 implementer 的返回值 | 落实 | IMPL_SCHEMA | kind、attempts、overrides、hintsRead、deferred 都从返回值取 |
| 14 台账保留全部字段 | 落实 | Issue 数据模型 | 保留 detail、evidence、state、subgoal、requiredStates、files；脚本条目与普通条目同形 |
| 15 暂停后能续、主会话能改台账 | 改了再落实 | `continueFrom`、`control/` | 续跑一律起新 run：init 把上次 ledger.json 压成 seed，作为字面量注入 workflow.js，没有 LLM 抄写，也不靠 resume。中途纠错用三种文件：statesPath、`control/hint-*.md`、`control/override-*.json`；后两种由 implementer 开工时用 `wl.mjs intake` 读出，不改文件名 |
| 16 脚本插入的问题由脚本关 | 落实 | wf 条目 | `lens:'workflow'`，id 固定：`wf-regress`、`wf-state-<态>`、`wf-pageerror-<态>`；开关按本轮实际观察决定 |
| 17 不轻信评审回填的 lens 和 id | 落实 | 归并规则 | schema 里不再有 lens 字段，归属只看调度方；matchesIssueId 查不到时按新问题入账，并记进 badMatch |
| 18 清理不删上一次的截图 | 改了再落实 | `wl.mjs init` | 保留最近一个旧 run 和 continueFrom 那个 run 的 shots；不再碰 `.playwright-mcp/` |
| 19 截图配方要能断言 | 落实 | `capture.mjs` | expect 对探针结果做部分深比较，对不上该态记失败；SKILL 写明配方禁止用 `\|\|` 兜底、探针要记录目标。`states_v5.json` 是旧格式，没改，下次 annotation run 按新格式重写 |
| 20 smoke 看不到的回归 | 落实前半 | `capture.mjs` computeNewErrors | 按报错文本集合与上一份 manifest（含 r00）比较，新出现的报错立 `wf-pageerror-<态>`；「检查 smoke 覆盖面」没做，通用程序无从知道 |
| 21 同一件事只立一条，只认原角度关闭 | 改了再落实 | 归并规则 | 关闭只认负责角度；别的角度可以凭证据重开一次，负责角度再次判关后该条标 disputed，之后只记分歧。同轮内跨角度的重复不做语义合并，第 2 轮起靠 matchesIssueId 引用。方向题移出台账 |
| 22 统一局部放大图 | 落实 | `capture.mjs` crops | 评审改用 Explore 类型后是只读的，不能自己裁图，只用截图器产出的局部图；init 对没声明 crops 的宽视口态给提醒 |
| 23 红线改成工具限制 | 删除（暂不做） | — | 造成真实损失的是主会话的回复，靠红线加 toMain 出口解决；内置类型去不掉 SendMessage，自定义子代理类型没有实测 |
| 24 所有输出用中文 | 落实 | COMMON 段 | — |
| 25 小毛病 | 逐项落实或随机制删除 | — | healthUrl 猜端口随 preflight 移进 init，没给就不探；prioritizedMustIds、mcpLoadable、p1_skip_reason、decision-log 的 python 都随所属机制删掉；`.gitignore` 由 init 用 `git check-ignore` 真查；principles 路径写进 prompt |
| 26 开跑前起草验收标准，开跑后冻结 | 落实 | init 拷 `<W>/rubric.md`；SKILL「起草验收标准」节 | 所有 prompt 只指向冻结件。标准写错了用 override 豁免，下一次 run 改正 |
| 27 自定义评审角度 | 落实 | init 检查角度专节 | 非内置角度，以及 razor、newbie、flow，在 rubric.md 里必须有专节（标题匹配 `^#{2,4}\s*(角度\|lens)[\s:：]+<名>\s*$`），缺了就不让开跑 |
| 28 原型模式 | 落实（骨架不变） | `mode`、`schemeFiles`、`contractPath`、IMPL_SCHEMA.deferred、出口 decision-gap、内置角度 flow 与 contract | 详见 §3.7 |
| description | 落实 | SKILL.md frontmatter | 采用用户同意的草稿 |
| 文末「改完后要同步的文档」 | docs 成员负责 | SKILL.md、principles.md、examples/path2.md、仓库根 `.web-loop-refresh.md`、项目记忆 `project_web_loop_skill.md`（已更正「顶层 return 非法」） | — |
| 清单外 | 删除或改 | — | 删掉 scanSubset（死参数）和 captureBackend 加 MCP 截图路径；主会话改用 scriptPath 启动，不再粘贴脚本全文；删掉 safeInsert 和 safeBlock；删掉 code 角度必填的 nextStepPlan 等修法字段，防重复试错改由 attempts 承担；模板不写死模型 |

## 3. 新架构要点

### 3.1 文件与职责（`.claude/skills/web-loop/`）

- **`workflow-template.js`**（972 行），分三段：
  - CORE：纯函数，`// ==== CORE BEGIN/END ====` 之间，包括校验、prompt、schema、归并、判据、渲染、回放；
  - INJECT：`// ==== INJECT BEGIN/END ====` 之间；
  - SHELL：调 agent 的薄壳，不含业务逻辑。
  - CORE 不得引用 agent、parallel、phase、log、args、budget，也不得用 Date.now、Math.random 等。`wl.mjs` 用 loadCore 截取这一段求值，所以回放和运行用的是同一份代码。
- **`wl.mjs`**（817 行）：子命令有 init、attach、verify、wait、intake、diff、restore、status、export；同时导出 loadCore、loadInjected、buildWorkflowSource、findJournal、parseJournal。
- **`capture.mjs`**（329 行）：子命令有 shoot、check、contact。playwright 用 `createRequire(uiDir)` 解析，优先系统 Chrome。
- **运行目录** `.claude/web-loop/<runtag>/`：
  - `args.json`
  - `workflow.js`：init 生成，模板加上注入的 args 和 seed
  - `rubric.md`：冻结件
  - `run.json`
  - `journal.jsonl`：本地副本
  - `run-record.json`
  - `control/`
  - `snap/`：快照、verify 结果、锁与日志
  - `shots/`
  - `scratch/`
  - `ledger.json`、`SUMMARY.md`、`reviews/`、`rounds/`：都由 export 写

### 3.2 运行时序与每轮 agent

1. **开跑前**，由主会话执行：
   - 写 args.json；
   - 运行 `wl.mjs init <W>`，依次做：校验、gitignore、rubric 冻结与角度专节、配方校验、原型模式检查、清理旧截图、smoke 基线、url 与 health、浏览器检查、r00 快照与截图、生成 workflow.js；
   - 看 `r00_contact.png`；
   - `Workflow({scriptPath: "<W>/workflow.js"})`，不传 args；
   - 立刻运行 `wl.mjs attach <W> <runId> <transcriptDir>`。
2. **每轮**的 agent 如下（都不传 model，一律继承会话模型）：

| agent | 类型 / effort | 做什么 |
|---|---|---|
| `impl-rNN` | 默认类型 / 不设 | 先跑 intake，再改代码，交回 kind、summary、changedFiles、attempts、hintsRead、overrides、deferred、toMain |
| `verify-rNN` | 默认类型 / low（data 档且用 .md 刷新时为 medium） | 跑 `wl.mjs verify`（可能要接着跑 `wait`），原样转交最后一行带签名的短结果 |
| `review-<L>-rNN` | Explore / 不设 | 只读：读 manifest 和截图，code 与 contract 另读 diff，按 schema 交回 known、subgoals、issues、directions |

3. **结束后**：`wl.mjs export <W>` 会先把 journal 和运行记录复制进 W，再回放，写出 ledger.json、SUMMARY.md、各轮原始返回。主会话读完 SUMMARY 后，在对话里用白话汇报。

### 3.3 台账与归属规则（CORE，脚本确定性完成）

- **条目状态**只有 open、fixed、waived 三种；回归用 regressions 计次。
- **known 表态**：只处理本角度名下开着的条目。
  - present：照旧开着；
  - gone：关闭，但条目所在的态本轮截图失败时不生效；
  - unverifiable：requiredStates 要点名本轮没截成功的态才采信，否则按确证处理；
  - decision：仅原型模式，表示同意挂起。
- **别的角度**：可以用 matchesIssueId 引用；对已修好的条目，非负责角度只能重开一次，负责角度再次判关后标 disputed。
- **子项合成状态**：全部 met → met；任一 unmet → unmet；有角度未表态或缺席 → pending；只剩 unverifiable → unverifiable。pending 排在 unverifiable 前。
- **进展**：本轮有 must 被修好（wf-regress 不算），或同一轮达成的子项个数超过历史最高，或原型模式下有条目变成 agreed。
- **挂起（仅原型模式）**：
  - implementer 提议后，条目先是 proposed，仍算确证 must；
  - 负责角度当轮回 decision，才变 agreed；
  - 前置筛选：条目的 files 落在 schemeFiles 上，或标题和描述里出现术语表的词。
  - 这样被评方不能自己豁免 must（审查编号 X1）。
- **人工修正**：override 支持 waive 与 unverifiable；不合法的进 overrideErrors。

### 3.4 出口集合

| 出口 | 含义 | 判据 |
|---|---|---|
| converged | 全部达标 | 可评审、角度到齐、sigOk，没有开着的 must（确证与取证缺口都没有），所有子项本轮被负责角度判 met |
| evidence-gap | 能修的都修完了，剩下要人补证据 | 可评审、角度到齐、sigOk，确证 must 为 0，没有 unmet 或 pending 子项，还有 unverifiable 的 must 或子项 |
| decision-gap | 仅原型模式：剩下的要用户拍板 | 可评审、角度到齐、sigOk，除 agreed 条目外确证 must 为 0，有 agreed 条目，没有 pending 子项，每个 unmet 子项都挂着 agreed 条目 |
| blocked | 环境或代理一再失败 | url 重试 30 秒仍不通；退回后 smoke 仍红；smoke 红而快照不可用；连续 2 轮没能评审；同一角度在连续 2 个可评审轮都没交回 |
| stalled | 评审正常，但没进展 | 第一个评审轮之后，连续 staleRounds（默认 2）轮无进展；连续两轮「本轮无改动」也归这里 |
| max-rounds | 跑满 | 本 run 轮数达到 maxRounds（app 默认 5，原型默认 3） |
| budget | 预算或代理数上限 | 开轮前 `used + 2 + lenses > maxAgents`，或 agent() 抛错 |
| error | 脚本意外异常 | 外层 catch 接住 |
| interrupted | 仅回放用 | export 回放时没有出口、又不是 max-rounds 或 budget |

所有出口都结束本 run，不存在「暂停后原地续」。续跑起新 run，带上 continueFrom。

### 3.5 回滚、快照与 verify

- `snap/snap.idx` 是整个 run 复用的临时 index，各棵树的含义：
  - `r00.tree`：开跑前；
  - `rNN.tree`：本轮交回后；
  - `rNN.restored.tree`：本轮被退回后；
  - `green.tree`：最近一次 smoke 绿。
- 本轮开工前的树 pre 取 `r(N-1).restored.tree`，没有就取 `r(N-1).tree`，再没有就取 r00。
- verify 的真活由脱离的 worker 做（审查编号 I1）：前台最多等约 9 分钟，没等到打印 pending，之后用 wait 接着等；同一轮不会起第二个 worker；intake 会先等上一轮的 worker。
- 后端重启的做法（审查编号 R1）：按 healthUrl 端口查监听进程号、精确 kill，等端口释放后 detached 启动；返回 200 且监听进程号换了，才算成功。所有等待都用 node 定时器，不写 shell 的 sleep。
- 短结果只含判定字段加 sig，完整结果在 `snap/rNN.verify.json`（审查编号 S2）。签名对不上的轮次照常评审，但不开关 wf 条目，也不能以收尾类出口结束（审查编号 S1）。
- 本轮无改动就跳过评审（审查编号 N1）。条件：上一轮评审过、没有 override、无改动、配方没变、档位是 frontend 或 none。
- `wl.mjs restore --to rNN|green|r00|before-restore [--dry-run]`：只在用户要求时由主会话执行。

### 3.6 落盘与交接

- **journal 定位**：
  - 优先用 run.json（attach 写入）；
  - 其次在 `~/.claude/projects` 下递归找 `<runId>/journal.jsonl`；
  - 最后按内容认：verify 结果里 manifest 路径带 `<W 绝对路径>/shots/`，只读开头 256 KB，**不按 label 认**，因为 label 在不同 run 之间会重复。
- **复制**：verify 每轮把原始 journal 复制成本地副本；export 收尾时再复制一次，并复制运行记录。
- **最小留痕**：每轮 log 一行紧凑记录，完整保留在运行记录的 logs 里。
- **顶层 return** 交回 compactLedger。journal 读不到时，用 `wl.mjs export --from-ledger <文件>` 出简版 SUMMARY。

### 3.7 原型模式（第 28 条）

- **何时用**：界面先行、后端没开发，原型背后的模拟逻辑和演示数据就是方案。主会话判断后写进给用户点头的摘要。
- **默认角度**：newbie、razor、flow、contract。**默认 maxRounds**：3。
- **方案层按产物划界**：schemeFiles 里的字段与计算，加上 rubric「术语表」里的词。init 从 rubric 抽出术语表，写进 `INJECTED.derived.terms`。
- **后端要求清单 contractPath**：
  - 放在原型旁边、不被忽略，随快照一起回滚；
  - init 发现它不存在或还是原样骨架时，拦下不让开跑。
- **contract 角度的 must 只有三类**：改了方案文件而清单没跟上；清单与代码不一致；未经拍板改了方案。后端可行性一律进方向题。
- **rival 的「同一概念两种说法」检查**交给 newbie。
- **SUMMARY 的「原型产出」节**：列出清单路径、本 run 对清单的改动、「方案受影响的地方」。

### 3.8 模型、类型与 token

- **模型**：不写死，继承会话模型。
- **类型**：
  - 评审用 Explore：只读、不注入 CLAUDE.md、起步上下文约 2.1 万 token（默认类型约 5.6 万）；lead 实测跑在 claude-opus-5-5 上。
  - verify 不能用 Explore：它的系统提示是只读模式，与写快照、截图冲突。
- **token 估算**（来自 `design.md` §2.11；L4 实测见 §8.1，降幅主要来自砍掉的代理）：每个评审轮的输出 token 比 run B 降约 28%～32%；每个 run 另省 finalize（3.2 万～3.9 万）、persist（每轮 2.5 万～7.3 万）和 setup 的 4 个 agent；主会话启动不再粘贴脚本全文（约 2.5 万）。

## 4. 测试覆盖

- 入口：`node .claude/skills/web-loop/tests/run-all.mjs`。
- 文件：
  - `test-design-scenarios.mjs`：D、P 系列，真跑 SHELL 外壳；
  - `test-wl-tools.mjs`：W 系列，在临时 git 仓库里真跑 `wl.mjs`，W9 起真实 http 服务；
  - `test-capture.mjs`：C 系列；
  - `test-skill-doc.mjs`：文档关键句；
  - `legacy-baseline-scenarios.mjs`：旧模板上应当失败的基线；
  - 辅助文件：`dryrun.mjs`、`wl-fixture.mjs`、`_helpers.mjs`。
- **最终数字**：run-all 共 4 个测试文件（test-design-scenarios、test-capture、test-skill-doc、test-wl-tools），87 个场景全部通过，0 失败（L4 之后补了 D44～D46、W18，现为 92 个，见 §8.2）；完整跑一遍约 2.5～3 分钟。
- **稳定性**：tester 把 `test-wl-tools.mjs` 连跑 10 遍，每遍 20/20；skeptic 单独跑 4 遍、implementer 连跑 5 遍，也全部通过。作为对照，修 I2（截图重试）之前，skeptic 跑 4 遍有 2 遍撞上截图错误。
- **收尾时新增的场景**：
  - W15：restore 的 dry-run，以及用 before-restore 撤销；
  - W16：verify 先报 pending，再用 wait 取到结果，可重复调用；
  - W17：红路径下等待上限很小时，退回结果和退回后的快照都在；
  - D43：I4，被退回后下一轮强制按 data 档刷新；
  - C2：加了 shotRetries 的断言。
- **没覆盖的**：envOk:false 时 30 秒的真实重试等待、attach 命令、真实 Workflow 运行时，最后一项留给 L4。
- skeptic 抽查过，确认真跑了控制流的：
  - D25：回放与运行一致，含「每个 debug 场景自动回放比对」；
  - D36、D37、D40、D42：挂起；
  - D38：签名；
  - W4b、W4c：回滚；
  - W9：后端重启后进程号要变；
  - W16、W17：verify worker 的 pending 与等待。
- **实施审查的 must 都已修复**：I1、I2，以及 nice 的 I4、I5；skeptic 定的收尾条件已满足。
  - M1：run-all 每个文件的超时从 120 秒改为 900 秒，超时被杀时 FAIL 行注明「超时被杀」。
  - M2：intake 缺省最多等 100 秒，没等到就报 verifyRunning。

## 5. 实测过的运行时事实

全部出自 `workflow_runtime_facts.md` 末尾三批「lead 实测结果」，以那里为准：
- **启动与返回**：
  - scriptPath 能直接启动仓库内的脚本文件；
  - 顶层 return 合法，返回值原样交回主会话；
  - args 到达时是对象，模板仍兼容字符串。
- **模型与 effort**：不写 model 时继承会话模型 claude-opus-5-5；`model:'sonnet'` 生效；`effort:'low'` 被接受。每个新 agent 的起步上下文约 5.4 万～5.6 万 token，与模型无关；Explore 约 2.1 万。之后每调一次工具，都要把整段上下文再读一遍。
- **journal**：
  - 依次是 launched、每个 agent 一条 started、一条 result，边跑边写；
  - 不记最终返回值，最终返回值在 `<会话目录>/workflows/<runId>.json`，resume 会覆盖这个文件；
  - 目录会随会话 slug、会话 id 变化。
- **写文件拦截**：子代理用 Write 写 `SUMMARY.md` 会被拦，其他 md、json 不拦。
- **Explore 类型**：没有 Write、Edit，但仍有 Bash、SendMessage、ListAgents、playwright；系统提示是只读模式。
- **resume**：同脚本、同 args 原样 resume 是全量重放（0 token），所以会在同一处再停。
- **后台服务**：子代理用 nohup 或 setsid 起的服务能活过子代理，run_in_background 起的不行；`$!` 拿到的是外层包装 shell 的进程号。
- **长命令**：前台 shell sleep 会被拦；一条真正跑 240 秒的前台命令（timeout 设 300000）正常完成。Bash 默认超时 2 分钟、上限 10 分钟。

## 6. 与 design 的偏差

都已写回 `design.md` §2.16 和对应小节：
- **implementer 实施中提出、architect 确认的 8 处**：
  1. staleRounds 允许 1～20；
  2. 子项状态 pending 排在 unverifiable 前；
  3. verify 短结果加 manifest 字段，在签名内，用于按内容认 journal；
  4. `--no-change-hint` 只在「上一轮评审过」且本轮没有应用 override 时才加；
  5. impl 抛错时直接 break、不归并该轮，replay 在同一处停；
  6. 形状校验只丢坏掉的元素，顶层类型不对或 kind 非法才整份作废；
  7. init 最后一步才拷 rubric.md；
  8. 退回后复跑变绿，也把本轮记为最近一次绿。
- **实施审查之后新增的行为**：
  - verify 拆成前台与 worker，加 wait（I1）；
  - intake 先等上一轮 worker，最多约 100 秒（M2）；
  - 截图这一步重试 2 次，超时不重试（I2）；
  - forceDataRefresh（I4）；
  - 按内容认 journal 时只读开头 256 KB（I5）；
  - app 模式禁用 contract 角度；
  - restore 加 before-restore 目标；
  - export 加 --from-ledger。

## 7. 已知局限

1. **原型模式下，方案文档本身从不由 web-loop 修改**。方案文档指纯文字的研究或设计文档，如研究报告的「已定方向」、`.scratch` 下的规格。SUMMARY 只在「原型产出」一节列出「方案受影响的地方」，并写明「方案文档由主会话经用户同意后再改」。没有任何机制保证主会话真的回头去改，这一步可能漏掉。这一条由 lead 核对源码确认：模板 renderSummary 里写的是「方案受影响的地方（方案文档本身由主会话经用户同意后再改）」。
2. **落盘依赖运行时内部的 journal 格式与位置**，这是没有文档的内部约定，位置已经变过一次。三层缓解：每轮复制本地副本；每轮 log 留痕；返回值带 compactLedger。解析只用 type、label、result 三个字段，失败时报错并给出第一行原文。
3. **评审改用 Explore 后的判断质量**只核实了模型一致，没有质量对照。L4 结果：没看到明显变浅，保持 Explore；样本只有 1 轮 3 个评审，置信度低（§8.1）。另外，rubric 必须自包含：Explore 读不到 CLAUDE.md 和用户级 rules，界面文字规范、词表条文都要原文收进 rubric。
4. **LLM 转交只剩 verify 的短结果一处**，有签名保护。签名失配的轮次不能收尾。L4：签名失配 0 次；形状异常 1 次（V1，已修，见 §8.2）。
5. **原型模式的方案层判定是启发式的**：files 交集或术语匹配，外加负责角度同意。漏判最坏是 stalled，误判最坏是提前以 decision-gap 结束；两者都在 SUMMARY 里看得到。
6. **同一轮内跨角度的重复问题不合并**，第 1 轮计数会偏高。停滞判据不看计数，所以不会因此误停。
7. **回滚管不到被 .gitignore 忽略的文件**，因为快照不收录它们。
8. **单次 verify 必须在 worker 的生命周期内跑完**。前台和 wait 各最多等约 9 分钟，可以接力等，但数据重扫特别长的项目会让 verify agent 反复等；SKILL 建议改用数据子集。init 由主会话执行，太慢时可以后台运行加 Monitor。
9. **Explore 和默认类型都还有 SendMessage**，「不发消息」仍靠 prompt 加 toMain 出口。真正造成损失的是主会话的回复，已写进红线。
10. **healthUrl 要选「业务就绪后才回 200」的接口**，例如返回实际数据的列表接口。只报进程存活的健康检查可能让截图截到空数据，这一条已写进 SKILL。
11. **token**：L4 实测（§8.1）显示，省下来的主要是砍掉的机械 agent，单个 implementer 和评审的输出并没有变少。剩下最大的开销是 implementer 反复读大文件产生的缓存读取，这次没处理。评审 effort 没调，继承默认。
12. **原型模式的默认角度不查代码内部是否一致**。例如注释和代码不符、同一件事两套算法：newbie 和 flow 只看截图，contract 只比清单和代码。L4 暗中对照的 10 处可疑点只覆盖到 1 处（§8.1）。需要查这一类时，加 code 或 rival 角度。

## 8. 验收

### 8.0 结果摘要（lead 2026-10-30 跑完后写）

- **L3**：init、status、export 在真实运行目录上都正常。parseJournal 能解析真实 journal。
- **L4**：跑通了。真跑查出 1 个必须修的缺陷 V1（verify 交回形状有歧义，导致第 1 轮整轮没有评审）。修复见 8.2。
- **token**：每轮代理数从 run B 的 12～14 个降到 5 个，机械开销基本消失。但 implementer 和 newbie 单次的输出与 run B 同一量级，所以省下来的主要是砍掉的代理，单个代理并没有变便宜。剩下最大的开销是 implementer 的缓存读取，每次 1200 万～1400 万。

### 8.1 L4 实测（run `wf_e32a7de5-3ce`，运行目录 `.claude/web-loop/2026-10-30_annotation-proto`）

**设置**
- 原型模式，评审角度 newbie、flow、contract，maxRounds 2，起点 e195d8b。
- 验收标准 `docs/research/2026-10-28_annotation-web-loop/rubric_v6.md`，截图配方 `states_v6.json`（18 个态，2560×1440，带局部图），后端要求清单 `repro/backend_contract.md`（46 条）。

**出口与结果**
- 出口：`max-rounds`，2 轮。
- 子项：G1、G2 met，G3 unmet。
- 1 条开着的 contract must：清单漏写标注文件 charts[] 每项的键 symbol、boxes、buy_points。
- 方向题 2 个：成员链里 ⊂ 的读向；会话题链接靠什么定位买点。

**开销**
- 7 个代理，0 个出错。
- harness 统计子代理共 122 万 token，319 次工具调用。
- 墙钟 36.7 分钟：impl-r01 约 11 分钟，impl-r02 约 13 分钟，verify 每轮约 30 秒，评审 3～11 分钟。

**页面改动**：mock_v4.html +29 行，共 7 处界面层修改，没有改动方案文件 data.js。
- r1：
  - 图上还没有买点时，bracket 轨至少留一行高，原先轨名压在下一条轨上；
  - 属性名不从字中间折行；
  - 定义输入框改成多行、随内容长高；
  - 选中买点的两条范围竖线改为先画，不再穿过签上的字。
- r2：
  - 两段之间的 → 放大到 14px；
  - 定义输入框的占位符去掉「(shared)」；
  - merge 下拉框限宽。

**design §4 L4 核对清单逐项结果**

| # | 项 | 结果 |
|---|---|---|
| 1 | init 通过；r00 总览图正确；rubric 冻结 | 通过：用时 25 秒，18 个态全部截成功。init 第一次被拒，原因是术语表标题写成了「## 7. 术语表」，正则只认不带编号的写法（见 V2） |
| 2 | label 顺序 | impl-r01、verify-r01、impl-r02、verify-r02、3 个 review-…-r02。**r01 缺 3 个评审**（V1） |
| 3 | 两轮 sig 都校验通过；Bash 没有超时；journal 第 1 轮后就已复制进运行目录 | r02 签名通过；r01 交回形状不对，按缺席处理。两轮 verify 各约 30 秒，没有出现 pending |
| 4 | 跑到中途 status 能看到台账 | 跑的时候没有调用；跑完后对运行目录调用 status，台账、子项、方向题、toMain 都正常 |
| 5 | export 写出各件 | SUMMARY.md、ledger.json、run-record.json、reviews/round_02/{newbie,flow,contract}.json 都在，各章节齐全 |
| 6 | token 对照 run B | 见下表 |
| 7 | 评审 prompt 字符数 | 评审 3.2k～3.7k 字，implementer 4.0k，verify 1.5k（任务正文，不计 harness 前缀）。design 估算约 1.3 万（按 run A 第 3 轮的规模），run A 第 3 轮实测约 7.9 万。本次条目少，所以偏低 |
| 8 | 没有调用 SendMessage 或 ListAgents | 7 个代理全部没有调用 |
| 9 | Explore 评审的模型与质量 | 模型都是 claude-opus-5-5。质量见下面「评审发现质量」 |
| 10 | 签名失配；拒做 | 签名失配 0 次；形状异常 1 次（V1）；没有代理拒做 |
| 11 | 原型产出 | 清单在 r1、r2 都随改动更新；本次没有挂起条目，所以 SUMMARY 没有「等你拍板」；「方案受影响的地方」为空，和改动一致 |

**每个代理的 token**（按消息 id 去重；run B 数据取自 design §6 附表）

| 代理 | 输出 | 缓存读取 | 缓存写入 | 工具调用 | run B 同类单次输出 |
|---|---|---|---|---|---|
| impl-r01 | 5.5 万 | 1213 万 | 30.9 万 | 58 次调用（Read 49，Bash 27，Edit 9） | 4.8 万～10.5 万 |
| impl-r02 | 6.7 万 | 1365 万 | 30.2 万 | 70 次调用（Bash 42，Read 40，Edit 25） | 同上 |
| verify-r01 / r02 | 0.09 万 / 0.08 万 | 5.6 万 | 5.8 万 | 1 次 Bash | run B 每轮：smoke + refresh + capture + read-* 约 1 万，persist 2.5 万～7.3 万 |
| review-newbie-r02（Explore） | 6.0 万 | 492 万 | 20.9 万 | Read 38，Bash 22 | 5.2 万～7.3 万；run B 评审缓存读取 420 万～990 万 |
| review-flow-r02（Explore） | 1.7 万 | 100 万 | 10.2 万 | Read 19，Bash 7 | 新角度，无对照 |
| review-contract-r02（Explore） | 2.5 万 | 293 万 | 14.8 万 | Bash 28，Read 4 | 新角度，无对照 |

- verify 用默认类型，起步缓存写入约 5.8 万，和 design 当初测的约 5.6 万一致；Explore 评审起步更轻，但读图后缓存写入涨到 10 万～21 万。
- 降幅主要来自结构：每轮 2 + 角度数 个代理，run B 每轮 12～14 个；没有 setup、persist、finalize。design §2.11 估的「评审输出降 25%～35%」这次无法单独验证：newbie 一个对照点落在 run B 范围内，flow 和 contract 是新角度。
- 剩下的大头是 implementer 的缓存读取：40～49 次 Read 反复读 166KB 的 mock_v4.html，对话越长，每次调用重读的上下文越多。要再省，下一步可以考虑：implementer 按需只读文件片段，或者限制自查截图的次数。本次没有改。

**评审发现质量（Explore）**
- newbie 读了 38 张图，判 G1 met，0 条 must，提了 1 个方向题：⊂ 读向。这一条证据具体，指到截图文件名和元素，有实质内容。和 run B newbie 每轮 2～3 条不能直接比：页面已经过两次运行和手动修改，状态不同。
- flow 指出配方覆盖不到两处：缩略图跳图那一步；「画已有特征的框 = 1 下」走的是在命名轨上直接拖的那条路，没有对应的态。这两处它写进了 toMain，没有硬判。
- contract 抓到一条清单遗漏，确实存在（charts[] 的键名）。
- **暗中对照**：docs 起草清单时，读代码记下了 10 处可疑点，没有告诉评审。本 run 只覆盖到 1 处，即「导出的买点没有 id，会话题链接定位不到买点」，以方向题的形式出现。其余 9 处是代码内部的不一致，例如：常量定义了没用到、注释和代码不符、相邻两段配对有两套算法。newbie 和 flow 只看截图，contract 只比清单和代码，而这些不一致没写进清单，所以三个角度都不负责这一类。**结论**：原型模式的默认角度不查代码内部一致性。需要查时，加 code 或 rival 角度。
- **结论**：没有看到「明显变浅」的证据，REVIEW_OPTS 保持 Explore。样本只有 1 轮 3 个评审，置信度低。

**L4 查出的缺陷**
- **V1（must）**：verify 交回的形状有歧义。
  - 现象：verify-r01 把带 sig 的那行 JSON 当字符串，包在自造的 line 字段里交回：`{"result":{"line":"{…}"}}`。VERIFY_SCHEMA 的 result 只要求是对象、没有必填字段，所以能通过校验；normalizeVerify 找不到 smoke，判成形状不对、按缺席处理，r01 的 3 个评审都没有派。
  - 根因：prompt 要「把那一行原样放进 result，不改动任何字符」，schema 却要 result 是对象，两者矛盾。
  - 后果：白跑半轮；r01 的改动没人评审，contract 角度只看了 r02 的 diff，r01 对清单的改动没有逐行核对。
  - 处理：交给 implementer 修，tester 补回归测试，skeptic 复审。建议的改法是 result 改成字符串原样交回，由 CORE 解析，同时兼容对象和 {line} 两种形状。结果见 8.2。
- **V2（nice）**：rubric 的「## 术语表」和角度专节标题必须一字不差，带编号就不认。建议允许标题前带编号。

### 8.2 V1、V2 修复（L4 之后，implementer 修，skeptic 认可）

- **V1**：`workflow-template.js`。
  - `VERIFY_SCHEMA.result` 改成字符串，内容就是 `wl.mjs verify` 最后那一行文本本身。verify prompt 写明「填那一行文本本身，不要改写成对象，也不要再包一层字段」。这样 prompt 和 schema 不再打架。
  - 新函数 `verifyLine` 负责取出结果：字符串就取最后一个非空行，再 JSON.parse；兜底也认已经解析好的对象，以及包了一层的对象（任一字符串字段能解析出含 smoke 的对象就算）。pending 行、乱码、null 都不认。
  - 签名按解析出的对象核对，先排好字段顺序再算，所以不受排版和键顺序影响。
  - skeptic 加了一条 nice：结果行的 round 和本轮不同时，按签名不符处理。照常评审，但不按它开关 wf 条目，也不能从这一轮收尾。这是为了防止 verify 误转交了上一轮的那一行。
  - 用 L4 的真实 journal 重放核对：旧代码对 verify-r01 判「verify 未交回」，新代码判可评审，签名也对得上；r02 新旧一致。已经跑完的 run 回放用的是它自己目录里那份 `workflow.js`，不受这次修改影响。
- **V2**：`wl.mjs`。认术语表和角度专节时，标题用 2～4 个 #，前面可以带编号，例如「## 7. 术语表」「### 5.1 角度 flow」「## 4) 角度 razor」。SKILL.md 已同步。
- **回归测试**（tester）：
  - `fakeVerify` 默认改成按字符串交回；
  - D44：四种交回形式（字符串、前面夹着杂讯行的字符串、已解析好的对象、`{line}`）都能评审，`sigOk` 为真；pending、乱码、null 都不认；
  - D45：整流程里第 1 轮 verify 包了一层交回，第 1 轮照常派出评审；
  - D46：schema 允许字符串；
  - W18：带编号的标题能通过 init。
- **run-all**：4 个文件、92 个场景全部通过（tester 另加 D47：结果行轮号和本轮不同时 sigOk 为假、照常评审、不开 wf-state 条目；lead 最后跑了一遍确认）。
- **没有再跑一次真跑来验证 V1 修复。** 理由是 V1 的修复点完全落在 CORE 的纯函数里，真实交回的样本（L4 的 journal）已经重放验证过。下一次真实使用时，留意第 1 轮是否派出了评审。

- **L3 小实测**（0 个 agent）：对真实 journal 跑 `wl.mjs status` 和 `export`，并在验收用的 workdir 上跑一次 `wl.mjs init`。
  - 已完成第 1 项（lead 跑）：parseJournal 解析真实 journal `wf_6feba183-903` 成功，started 和 results 都对，badLines 为 0。
  - status、export、init 需要一个在 git 仓库里、带 args 的运行目录，所以放到 L4 里一起验证。结果：都通过，见 8.1 第 1、4、5 项。
- **L4 小规模真跑**：在标注原型上用原型模式，3 个评审角度、2 轮，约 10 个 agent，核对清单见 `design.md` §4 第 1～11 项。结果见 8.1；实际用了 7 个 agent，因为 V1 导致 r01 没有评审。
  - **起点**：提交 `e195d8b` 的页面。
  - **旧运行产物的处理原则**（用户 2026-10-30 定）：
    - 用户拍板过的决定有效；
    - 旧 web-loop 自己下的判断（收敛与否、问题清单、条数、残留）一律作废，不喂给新运行；
    - 页面交给新版从头评。
  - 所以 L4 不用 continueFrom 接旧台账。L4 的验收标准只从用户拍过板的来源起草。
  - 要重点记录的数字：
    - 每个 agent 的输出 token 与缓存读取（按消息 id 去重），与 `design.md` 附表的 run B 对照；
    - 评审 prompt 的字符数；
    - 签名失配次数；
    - 有没有 agent 调用过 SendMessage 或 ListAgents；
    - Explore 评审的发现质量，与 run B 同类角度对照。

## 9. 给下一轮的提示

- 改判据或归并规则，只改模板的 CORE 段；改完跑 run-all，D25 会检查回放与运行是否一致。
- 不要把 seed 或 args 改成经 agent 抄写，也不要恢复 persist 或 finalize agent：这正是本次要消灭的 LLM 抄 JSON。
- 主会话启动 Workflow 后必须马上 attach；结束后必须 export，再读 SUMMARY 汇报。
- 本目录（`docs/research/2026-10-29_web-loop-overhaul/`）是研究目录，实施完成后可能被删。skill 的代码、测试和文档不得引用它。
