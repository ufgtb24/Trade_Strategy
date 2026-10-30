# web-loop 重构设计（architect，2026-10-29）

> 本文中所有项目内路径均相对 repo root（即 worktree 根 `.claude/worktrees/annotation-web-loop/`）。要改的是这个 worktree 里的 `.claude/skills/web-loop/`，**绝不碰**主目录那份。
> 读法：§0 一句话；§1 逐条决定；§2 目标设计（implementer 唯一依据）；§3 测试计划；§4 lead 真跑点；§5 方向题；§6 残留风险。
> skeptic 的攻击清单 `review_design.md` 第一部分 K1～K26 在文中以「回应 Kn」标出处理方式。

## 0. 一句话结论

问题的根子有三个：**脚本读写不了文件，于是让 LLM 来回抄 JSON**（persist、read-state、read-impl-stuck、finalize、paused 都是这样来的）；**截图让 LLM 每轮现写脚本**；**判据靠评审回填的字段和从没跑过的机制拼起来**。改法相应也是三条：

1. **台账只放在脚本内存里，由纯函数推进。** 落盘不再派 agent，靠运行时自己的 `journal.jsonl`，它已经按 label 记下每个 agent 的完整结构化返回（已核对 run A、B 两份）。skill 自带一个 node 工具 `wl.mjs`，用同一份纯函数回放 journal，导出台账、各轮评审原文和 SUMMARY，全程不经 LLM 抄写。
2. **确定性的活交给 skill 自带的 node 程序。** 截图器 `capture.mjs` 执行结构化配方，带断言、局部图、统一视口，也检查新出现的页面报错。`wl.mjs verify` 一条命令依次做完快照、smoke（按退出码判；红了就按快照只退回本轮改动，再复跑一次，区分是改坏了还是环境坏了）、刷新和截图，并给结果签名。LLM 只负责转交结果，签名对不上就不采信。
3. **判据从头定义，只留能写出公式的。** 收敛、取证缺口、停滞、环境故障、预算五种出口都由台账推导，删掉 treadmill、oscillating、missingStates 和 P1 meta-agent。

每轮 agent 从「7 个机械 agent + N 个评审」降到「implementer + verify + N 个评审」。setup 和 finalize 一个 agent 都不派（续跑的台账和 args 由 init 注入脚本）。按 run B 的实测量估算，每个评审轮的输出 token 降约 3 成，每个 run 另省 finalize、setup 和 persist 的全部开销（§2.11）。

**总原则**：
- **用户 2026-10-29 定下**：为弥补旧模型（Opus 4.6）能力不足而加的机制可以不要。
- **lead 的分类建议**，团队采纳，见 §1.5：与模型强弱无关的结构性约束保留，只修实现。结构性约束指：脚本读不了文件、浏览器单例会串台、停止要靠固定标准、证据由被评方以外的人采集、计数和归属由脚本确定性完成、回归检查和回滚、运行环境的拦截与红线。
- 流程骨架固定。动态只发生在开跑前（填参数、起草并冻结验收标准）；开跑后只留由人或主会话发起的受控改口通道。
- 模板里不写死模型，一律继承会话模型；机械环节用 effort 调低开销。
- 两种模式共用一副骨架：真实应用（app）和界面先行的原型（prototype，第 28 条）。模式只改默认值、多一份产出和一个出口，不改流程。

---

## 1. 逐条决定（清单第 0～25 条 + description + 清单外发现）

| # | 决定 | 理由（一句话） |
|---|---|---|
| 0 | **改了再采纳** | 外壳把模板正文包进 `AsyncFunction` 执行（能容纳顶层 return，parallel 按真语义：thunk 抛错时该位置为 null），另加纯函数单元测试和「回放与运行一致」测试。现有 24 个找字符串的测试中，测的机制已删的一并删掉（§3）。 |
| 10 | **被新判据取代（按用户总原则删）** | treadmill、oscillating、missingStates、PAUSED 节全删。「停滞」改成一条：**连续 K 轮既没有确证 must 被修好，子项同时达成的个数也没有刷新最高纪录**（§2.7）。理由：treadmill 不但没拦下过任何失败，还在真跑里叫停过一次正常推进的 run；oscillating 在 maxRounds≤5 时最早第 5 轮才可能成立，没有实际作用；漏报的代价有 maxRounds 封顶。exitReason 改为单独的枚举，不再有「暂停」。 |
| 13 | **采纳** | 保存 `impl` 的返回值；kind、attempts、overrides、hintsRead 都从这里取；删 read-impl-stuck。 |
| 14 | **采纳（扩为完整数据模型）** | 条目保留 detail、evidence、state、subgoal、requiredStates、files；脚本插入的条目与普通条目同形（§2.6）。 |
| 12 | **采纳，加脚本侧校验（回应 K4）** | verdict 不再让评审申报，由台账推导。子项只认 args 里点名的负责角度。unverifiable 只在 requiredStates 点名了「本轮没截成功的状态」时才采信，否则按确证处理。还有 unverifiable 时不算收敛，单列为出口 `evidence-gap`。 |
| 2 | **改了再采纳** | implementer 返回空时，kind 用上一轮的值兜底，本轮照常 verify 和评审。只有拿不到可评审的截图才跳过评审；跳过的轮照样推进判据，**连续 2 轮跳过 → `blocked`**。「implementer 未交回」只记在轮次记录里，不立 must（它不是代码缺陷，不该挡收敛）。 |
| 1 | **改了再采纳（按 lead 的分类建议归为结构性约束；保留回滚是团队的判断，它延续现有行为。改成确定性实现）** | 由 `wl.mjs verify` 在 node 里完成，不派 agent。每轮用 git 临时 index 存快照，不碰真 index、HEAD 和 stash（采纳 K9）。smoke 红时，只退回「本轮开工前快照 → 本轮交回后快照」之间变了的路径，豁免 statesPath、rubric、workdir（回应 K9）。退回后再跑一次 smoke（回应 K1）：变绿说明是本轮改坏的，立 `wf-regress` must，被退回的 diff 存档交给下一轮；仍然红说明是环境或基线坏了，就把本轮改动放回去，以 `blocked` 结束。连续 2 轮被退回 → `blocked`（§2.9）。 |
| 3 | **改了再采纳** | 不让 agent 写 to-main 文件（可能撞上「报告型文件」拦截），改为每个 schema 都带 `toMain` 字段，`wl.mjs status` 从 journal 里读出来展示。共用约束段写明：禁 SendMessage、ListAgents，不等回复，不做 git 写操作（回应 K12）。SKILL.md 红线：主会话不得回复 workflow 子代理。hint 改为「所有未处理过的控制文件」，不再按确切文件名匹配。 |
| 11 | **被 `wl.mjs export` 取代** | 删 finalize agent。SUMMARY 由纯函数 `renderSummary` 渲染，`wl.mjs export` 从 journal 回放后写盘，不经 LLM，也就不会撞写文件拦截（回应 K13、K15）。顶层 return（lead 已实测合法）交回出口和一份精简台账，完整台账不经它落盘（理由见 §2.12）。 |
| 15 | **改了再采纳** | 续跑一律起新 run：`args.continueFrom = 上次 workdir`。init 从上次的 ledger.json 算出精简台账（seed），作为字面量注入新 run 的 workflow.js（采纳 R4），全程没有 LLM 抄写，也不派 seed agent。不依赖 resume（它跨 session 能否用没有实测，也没必要）。中途纠错有三个文件：statesPath、`control/hint-*.md`、`control/override-*.json`；后两个由 implementer 开工时用 `wl.mjs intake` 读出。「豁免暂停一次」不做（回应 K21）：所有出口都是结束，续跑本身就是豁免。 |
| 7 | **采纳（只留 statesPath）** | args 删除 `states`，只认 statesPath。截图器每轮自己读这个文件，主会话中途改文件，下一轮即生效；implementer 自查用的也是同一个截图器、同一份文件。 |
| 19 | **采纳，由截图器执行断言** | 配方可以写 `expect`，与探针结果做部分深比较，对不上该态记为失败，并立 `wf-state-<态>` must；评审 prompt 不出现失败态的截图（回应 K23）。`states_v5.json` 不在本次改动范围：它是旧格式，下次 annotation run 按新格式重写时一并去掉 `\|\|` 兜底。 |
| 9 | **被 `capture.mjs` 取代（更彻底）** | 不让 LLM 每轮写截图脚本，也不让它写一次后复用；skill 自带通用截图器。args 加 `viewport`（默认 2560×1440、DSF 1），单个状态可以覆盖。清单文件按轮命名：`shots/rNN_manifest.json`。 |
| 4 | **被 journal + export 取代** | 评审不写文件（回应 K13：否则同一份结果要生成两遍）；删 persist；`reviews/round_NN/<lens>.json` 由 export 从 journal 写出。评审不再收到 verified 日志，只拿到自己负责的子项。方向题移出台账，单独存放，结束时全文进 SUMMARY。 |
| 6 | **采纳并扩大** | 删 read-state、read-impl-stuck、smoke、refresh、capture、capture-fallback、persist、rollback agent（回滚改在 node 里做）、paused、decision-log、meta-agent、finalize；setup 的 cleanup、pw-selfcheck、preflight、write-goal 移进 `wl.mjs init`，由主会话在开跑前跑。每轮固定开销从 7 个 agent 降到 2 个。 |
| 16 | **采纳** | `lens:"workflow"`，id 固定（`wf-regress`、`wf-state-<态>`、`wf-pageerror-<态>`）。脚本按本轮实际观察开或关，不经评审。 |
| 17 | **采纳** | 归属只看调度方知道的 lens，schema 里不再有 lens 字段；matchesIssueId 查不到时按新问题入账，并记进 `badMatch`。 |
| 18 | **改了再采纳** | 清理放在 `wl.mjs init` 里：保留最近一个旧 run 和 continueFrom 那个 run 的 `shots/`，更早的删掉；**不再碰 `.playwright-mcp/`**（新流程不用 MCP，那个目录不归 web-loop 管）。 |
| 20 | **采纳前半** | 截图器拿本轮和上一份清单（含 r00）比，某个态上一份没有页面报错、这一份有，就立 `wf-pageerror-<态>` must；开跑前就有的报错不自动立条目（回应 K26）。「检查 smoke 覆盖面」不做：通用程序没法知道项目的 smoke 覆盖了什么。 |
| 5 | **采纳** | 加 `maxAgents`，脚本自己计数；`agent()` 抛错（预算耗尽）时被 `call()` 接住，以 `budget` 结束。外层 try/catch 兜住意外异常，以 `error` 结束（回应 K8）。 |
| 8 | **改了再采纳** | 起点图 r00 由 `wl.mjs init` 在开跑前截，同时充当配方体检：r00 有失败态就不让开跑。razor 的起点计数用 schema 字段 `counts.baseline` 交回，存进台账，不写 `baseline_counts.md`。 |
| 21 | **改了再采纳（回应 K6）** | 关闭只认负责角度。别的角度可以凭证据「重开」一次已修的条目：负责角度再次判关后，该条目标为 `disputed`，之后别的角度的重开只记分歧、不再生效。同一轮内跨角度的重复不做语义合并：显示时按截图状态分组，第 2 轮起靠 matchesIssueId 引用已有条目。评审只对自己名下的条目表态。 |
| 22 | **采纳** | 局部图在配方的 `crops` 里声明（选择器或 clip），由截图器产出。评审用 Explore 类型，是只读的，不能自己裁图写文件，所以只用截图器产出的局部图；小字区域在配方里必须声明 crops，init 对没有 crops 的态给提醒（U2）。各角度读图范围不同（回应 K16）：code 默认不读图；func 只读自己子项和问题涉及的状态；其余角度读全部。 |
| 23 | **暂不采纳** | 真正造成损失的是主会话的回复（拉起了副本）。修法是红线加 `toMain` 这条正当出口；agentType 还要另建 `.claude/agents/*.md` 并实测，收益不足以抵消这些成本。如果以后再出现违规，再做。 |
| 24 | **采纳** | 写进共用约束段。 |
| 25 | **逐项** | 猜端口探 healthUrl：随 preflight 一起移进 init，没给就不探。`prioritizedMustIds`、`mcpLoadable`、`p1_skip_reason`、decision-log 那段 python：随所属机制一起删。`.gitignore` 检测：init 里用 `git check-ignore -q <workdir>` 真查，不通过就不让开跑。principles 路径：拼进 implementer 和评审的 prompt。 |
| 26 | **采纳** | init 把 rubricPath 拷成 `<workdir>/rubric.md`，所有 prompt 只指向这份冻结快照，SKILL.md 写明「跑的过程中不改判断标准」。标准写错了，就用 override 豁免受影响的条目，改正后的标准从下一次 run 生效。起草步骤写进 SKILL.md 智能入口层：固定来源、固定结构、给用户几句话摘要（标出沿用和新加的部分），点头后才开跑。理由：能停下来全靠「对照一份不变的标准」，这是结构性约束。 |
| 27 | **采纳** | 内置角度 ux、func、code、rival、razor、newbie 用内置的角色说明；其他角度名的角色说明统一为「完全按冻结 rubric 里『角度 <名>』专节判」。init 检查每个非内置角度在 rubric.md 里有专节（标题匹配 `^#{2,4}\s*<可选编号>(角度\|lens)[\s:：]+<名>\s*$`，不区分大小写；可选编号如「7.」「5.1」，见 V2），razor、newbie 也必须有专节（它们依赖 rubric 里的任务清单、数法、正确含义），缺专节不能开跑。「模拟用户走流程」类角度只能按截图清单里排好顺序的状态来判，不能点击；SKILL.md 给一个专节样例。 |
| 28 | **采纳，按骨架不变落地（§2.15）** | 加 `mode: app\|prototype`（T5，写进给用户点头的摘要）。原型模式改五处：<br>1. 后端要求清单 `contractPath` 放在原型旁边、不被忽略的位置，随快照一起回滚（T3）。<br>2. 方案层按产物划界（T1）：args 里的 `schemeFiles` 里的字段与计算，加上 rubric「术语表」里的词。implementer 遇到方案层的 must 用 `deferred` 正式挂起，脚本只在条目确实落在方案层时才采信（T2）。本轮碰了方案文件，交给 contract 角度核对。<br>3. 演示数据覆盖边界：写进配方起草指引。<br>4. 默认角度换成 newbie、razor、flow、contract；contract 只能把「代码与清单不一致」或「未经拍板改了方案」记成 must，后端可行性一律进方向题（T4）；rival 的「同一概念两种说法」检查交给 newbie（T6）。<br>5. 节奏：默认 maxRounds 3，新增出口 `decision-gap`，表示「只剩等你拍板的事」（T2）。<br>方向题 Q2「默认角度」与本条合并：证据只覆盖原型场景，所以只在原型模式里换默认，真实应用的默认不变。 |
| description | **采纳** | 采用用户已同意的草稿（§2.14），SKILL.md「何时用 / 不用」补上「结果不落到页面上的逻辑不归它管」。 |
| 外-1 | **删 `scanSubset`** | 模板只在 SUMMARY 的一句提示里用到它，从没传给任何 agent。需要子集的项目把它写进 `.web-loop-refresh.md`。 |
| 外-2 | **删 `captureBackend` 和 MCP 截图路径** | 两次 run 都没走 MCP 截图。视口不统一、截图落点要 mv 这类问题都出在这条路径上。 |
| 外-3 | **主会话改用 `scriptPath` 启动，不再粘贴脚本全文** | 现 SKILL.md 让主会话把 800 行模板作为 `script` 参数粘进去，每次启动多出约 2.5 万输出 token，还有抄错的风险。待 lead 实测确认 `scriptPath` 可用（§4 L1）。 |
| 外-4 | **删 safeInsert / safeBlock** | JS 模板字符串插入的值不会被再次解析；safeInsert 反倒往 prompt 里塞反斜杠，第 25 条那个引号问题也出在它身上。 |
| 外-5 | **删 code lens 必填的 rootCauseHypothesis、nextStepPlan、suggestedFix 及 dedupBlock** | 让评审写修法与 principles §0.5「不提替代方案」相矛盾，也是在 implementer（能看全部代码、亲手改代码）的职责上重复花 token。防止重复试错改由 `attempts` 承担：implementer 自报每条 must 试过的做法，条目仍开着就原样交回给下一轮。保留可选的 `files`（问题所在的 `path:line`）。 |

| 外-6 | **不写死模型；评审用 Explore；verify 用默认类型加 effort low** | 模板里删掉全部 `model:`，一律继承会话模型，以后换更强的模型能自动用上。<br>**评审**用 `agentType:'Explore'`：lead 实测它跑在 claude-opus-5-5 上，没有被降成弱模型；起步约 2.1 万，默认类型约 5.6 万。评审每次调用工具都少重读约 3.5 万 token。它的系统提示是只读模式、不注入 CLAUDE.md，正好合「评审零浏览器、不写文件」，代价是评审要用到的规范必须写进冻结的 rubric（U2）。<br>**verify** 不能用 Explore：它要写快照、回滚、重启、截图，与只读的系统提示冲突，可能被拒做（lead 实测）。所以用默认类型加 `effort:'low'`。<br>也考虑过把 verify 并进 implementer，没有采纳：采证和回滚不该由被评方执行（结构性约束），implementer 看到自己的改动被退回后还可能在同一个 agent 里接着改，把轮次搅乱。多一个 agent 的起步开销约 5.6 万，相对评审可以忽略。<br>**implementer** 保持默认类型，因为它需要 Edit、Write 和项目 CLAUDE.md 里的编码规范。 |

**副产品登记**：本次研究对象是工具链，没有带及格线的量化研究，没有要登记到 `docs/feature_candidates.md` 的条目。

### 1.5 机制分类：弥补模型能力的脚手架（a）与结构性约束（b）

分类本身是 **lead 的建议**，团队采纳；依据是用户的总原则「为旧模型弥补能力的机制可以不要」。判法：(a) 类默认删，除非两次真实 run 里有它确实拦下过某个失败的证据；(b) 类保留，只修实现。

| 机制 | 类 | 两次 run 里的证据 | 去留 |
|---|---|---|---|
| P1 meta-agent 及三个触发、decision_log、forbiddenApproaches | a | 从没触发过 | 删。防止重复试错改由 implementer 自报的 attempts 原样交回（脚本确定性完成，属 b） |
| treadmill、oscillating | a | treadmill 误停过 1 次，没拦下过任何失败；oscillating 走不到 | 删 |
| implementer 五级优先级说教、reviewer_stuck 回流、planRepetition | a | read-impl-stuck 读错了轮次，拼出来的信号恒为 false，等于从没起过作用 | 删。human hint 作为人工权威的通道保留（b），只留一句「hint 优先」 |
| stalePrimer（劝评审优先用 matchesIssueId 的长段） | a | — | 删说教，留契约句（b）：「自己名下的旧问题在 known 里按 id 表态；复现已修的问题用 matchesIssueId 引用，不要换个说法另立一条」 |
| 防漂移、反锚定的说教段、goalEcho、「以 goal.md 为准」每轮重读 | a | — | 删。GOAL 原文内联在 prompt 里，读一次就够 |
| 评审要写本轮可定位证据 | b | 子项判定的输入格式 | 保留一句 |
| code lens 的 nextStepPlan 格式约束、rootCauseHypothesis 必填 | a | — | 删，保留可选的 files |
| 「implementer=opus 例外」整节论证、写死的 model | a | — | 删，继承会话模型 |
| refs 的 goal / baseline / anti-example 三档 | b（属于信息，不是说教） | — | 保留语义，压成 3 行 |
| newbie 看不到别的角度的条目；评审不读历史评审 | b（评审独立） | — | 保留 |
| 脚本读不了文件 → 由 node 工具完成确定性的读写 | b | persist 抄错、finalize 写不成 | 改为 wl.mjs 和 capture.mjs |
| 浏览器只由截图层持有，评审零浏览器 | b | — | 保留；截图层改为程序 |
| 停止问题：对照固定标准判过不过 | b | 早期实验：按「问题清空才停」跑 50 轮不收敛，按固定标准 3 轮收敛 | 保留，并冻结 rubric（第 26 条） |
| 证据由被评方以外的人采集 | b | 两次 run 的 implementer 都自截自评过 | 保留：截图由程序采集，implementer 的自查截图不作为评审证据 |
| 计数和归属由脚本完成 | b | treadmill 误报，归属用了评审回填的 lens | 全部移进 CORE |
| 回归检查和回滚 | b（lead 的分类建议） | run B r02 留下了半截改动 | 保留，改成确定性快照回滚（第 1 条），这是团队的判断 |
| 运行环境的拦截与红线（SUMMARY.md 写不成、SendMessage 会拉起副本、kill 要精确、不设 isolation、只能本地跑） | b | 两次 run 都撞上过 | 保留，写进红线；SUMMARY 改由 export 写 |

---

### 1.6 skeptic 第 1 轮审查与 journal 补审的处理记录

| 编号 | 级别 | 处理 | 落在哪 |
|---|---|---|---|
| R1 后端重启会把旧进程当成新进程 | must | 采纳：按 healthUrl 端口查监听进程号、精确 kill、等端口释放，再 detached 启动；返回 200 且进程号变了才算刷新成功 | §2.9 第 3 步，W9 |
| R2 截图失败的态上仍能判 met 或 gone | must | 采纳：met 降为 unverifiable，gone 不生效 | §2.6 第一遍，D31、D32 |
| R3 implementer 的 summary 发给了全部评审 | must | 采纳：只发给 code | §2.11 评审 prompt 第 6 项，P2 |
| R4 seed 要 LLM 原样抄写台账 | must | 采纳首选方案：init 把 args 和 seed 注入 workflow.js；删掉 seed agent 和 argsHash | §2.2、§2.4，D22～D24，W5 |
| R5 不退回时缺「最近一次绿」的提示，Q1 对比不公平 | must | 回滚已经恢复（用户原则把它定为结构性约束），Q1 删除；(i) 采纳：SUMMARY 第一条固定写工作区状态和 restore 命令 | §2.12 |
| R6 主会话看 r00 会读 21 张大图 | must | 采纳：缩略总览 r00_contact.png | §2.3、§2.9，C2 |
| J1 证据不能只靠 journal 待在原处 | must | 采纳：verify 每轮、export 收尾时各把 journal 复制进 workdir，export 还复制运行记录 | §2.9 第 0 步、§2.10，W10 |
| J2 定位 journal 不能只靠 wfId | must | 采纳：启动后立刻 attach 写 run.json；递归查找，不写死层级；按内容兜底 | §2.10，W10 |
| J3 最小留痕 | nice | 采纳：每轮 log 一行，运行记录的 logs 会完整保留 | §2.4、§6 |
| J4 进行中读到写了一半的行 | nice | 采纳 | §2.10，W6 |
| N1 无改动轮跳过评审 | nice | 采纳（有了确定性快照，代价只是一行判断）：无改动、配方没变、本轮没有 override、档位是 frontend 或 none 时才跳过 | §2.9 第 2b 步，D33 |
| N2 新报错按文本比较 | nice | 采纳 | §2.9，C1 |
| N3 smoke 之前先探环境 | nice | 采纳：url 不通 → 当轮 blocked | §2.9 第 0 步，D34 |
| N4 绝对路径，截断 changed | nice | 采纳 | §2.9 第 1 步 |
| N5 自动发现 journal | nice | 并入 J2 | §2.10 |
| N6 init 和 verify 可能撞上限或被判卡住 | nice | 等 lead 的 4 分钟实测；退路是把 verify 拆成两条命令 | §4 |
| N7 子项漏表态 | nice | 采纳：记 untabledSubgoals | §2.6，D35 |
| N8 kind 的简单兜底 | nice | 采纳 | §2.9 第 3 步，W11 |
| N9 缺「默认评审角度数」方向题 | nice | 原作为方向题 Q2，现已并入第 28 条（只在原型模式里换默认） | §2.15、§5 |
| N10 不用 shell sleep | nice | 采纳：等待一律用 node 定时器 | §2.9 |
| S1 签名对不上时，okSet 和 R2 的校验都会失效 | must | 采纳：converged、evidence-gap、decision-gap 三个出口都要求 sigOk；签名对不上的轮照常评审、照常记账，但不能从这一轮收尾 | §2.6 第 4 步，D38 |
| S2 转交的那一行太长，容易走样 | must | 采纳：完整结果写进 `snap/rNN.verify.json`，交回的行只留判定要用的短字段加 sig；wf 条目的 detail 指向这个文件；约定路径（manifest、rejected.diff）由 CORE 按轮号算出，不经转交 | §2.5、§2.9 第 5 步 |
| S3 smoke 偶发失败 | nice | 采纳：smoke 红时先原样复测一次，仍红才回滚；复测变绿记 `flaky:true` | §2.9 第 2 步，D39 |
| S4 Q2 题面补 rival 的代价 | nice | Q2 已并入第 28 条，不再提问；rival 那项检查交给 newbie（T6） | §2.15 |
| S5 统计签名失配次数 | nice | 采纳，放进 L4 | §4 |
| T1 方案层按产物划界 | must | 采纳 | §2.15 |
| T2 implementer 正式挂起方案层问题，加 decision-gap 出口 | must | 采纳 | §2.5、§2.6、§2.15，D36、D37 |
| T3 后端要求清单不放 workdir | must | 采纳：清单放在原型旁边、不被忽略，随快照一起回滚；init 检查 | §2.15，W12 |
| T4 contract 角度的 must 只限「代码与清单不一致」 | must | 采纳，另加一类「未经拍板改了方案」（implementer 退回或挂起都修得了）；后端可行性一律进方向题 | §2.15 |
| T5 args 加 mode | nice | 采纳 | §2.2 |
| T6 rival 的术语检查交给谁 | nice | 交给 newbie 的内置角色说明（两种模式都适用） | §2.11 |
| U1 journal 不能按 label 认 | must | 采纳：按内容认（verify 结果里带 `<W 绝对路径>/shots/`），没有 run.json 时从第 2 轮起复制 | §2.9 第 0 步、§2.10 |
| X1（原 W1）挂起只要 implementer 一方提出就生效 | must | 采纳：挂起先作为提议，负责角度当轮同意才生效、才算进展；关键词和文件条件保留为前置筛选 | §2.6 applyImpl 第 6 步、§2.15，D36、D37、D40 |
| X2 清单还是原样骨架 | nice | 采纳：init 拦下 | §2.10 第 4b 步 |
| X3 §2.15 表格那一行跟着改 | nice | 采纳 | §2.15 |
| V3 url 瞬断就判 blocked | nice | 采纳：重试 30 秒 | §2.9 第 0 步 |
| V4 连续 noChange 应记 stalled | nice | 采纳：noChange 只计入 streak，不计入 skipStreak | §2.6，D33 |
| U2 评审用 Explore 时读不到 CLAUDE.md，也不能建文件 | nice | 采纳：rubric 收录评审要用到的规范原文；删掉「自裁图」；小字区域必须声明 crops | §2.11、§2.14 |
| lead：verify 不能用 Explore | 事实 | 采纳：verify 用默认类型加 effort low | 外-6 |
| lead：前台命令跑 240 秒正常完成 | 事实 | verify 的 Bash timeout 设 600000；单次 verify 必须在 10 分钟内完成，数据重扫超过的项目不适合用本 skill，在 SKILL 里写明；init 由主会话执行，太慢时可以用后台运行加 Monitor | §2.9、§6 |

## 2. 目标设计

### 2.1 文件布局

skill 目录 `.claude/skills/web-loop/`：

| 文件 | 作用 | 谁写 |
|---|---|---|
| `workflow-template.js` | 上半是 CORE（纯函数：校验、prompt、schema、归并、判据、渲染、回放），下半是 SHELL（调 agent 的薄壳） | implementer |
| `wl.mjs` | node CLI：`init` / `verify` / `intake` / `diff` / `restore` / `status` / `export`；同时 `export function loadCore(path)` 供测试和 capture.mjs 用 | implementer |
| `capture.mjs` | node CLI + 可 import：`shoot` / `check` / `contact`；导出纯函数 `validateStates`、`matchExpect`、`computeNewErrors`、`buildSummary` | implementer |
| `SKILL.md`、`principles.md`、`examples/path2.md` | 文档 | docs（按 §2.14 要点） |
| `tests/` | 外壳、场景、单元测试 | tester |

单次 run 目录 `.claude/web-loop/<runtag>/`（已被 `.gitignore` 覆盖）：

```
args.json            主会话写；init 补默认值后写回
workflow.js          init 生成：模板 + INJECT 段（args 与续跑 seed 的字面量）；Workflow 用 scriptPath 指向它，不传 args；
                     回放也从它取 CORE 与 INJECT（保证回放用的就是跑的那份代码和输入）
goal.md              init 从 args 渲染（给人看；prompt 里已内联，不要求 agent 读）
rubric.md            init 从 rubricPath 拷贝，冻结；所有 prompt 只指向它（第 26 条）
run.json             {runId, transcriptDir}；主会话在 Workflow 返回后立刻写（`wl.mjs attach`）
journal.jsonl        运行时 journal 的本地副本（verify 每轮复制，export 再复制一次）
run-record.json      运行记录 `<会话目录>/workflows/<runId>.json` 的副本（export 复制；含 logs 与最终返回值）
states.json          （可选位置）主会话写的截图配方；statesPath 也可以指向项目内文件
refs/                主会话按 SKILL「参考图持久化」写
control/             主会话中途放 hint-*.md、override-*.json；只读不改名
snap/                git 临时 index（snap.idx）；rNN.verify.json（verify 的完整结果，S2）；r00.tree（开跑前）；rNN.tree（本轮 implementer 交回后）；
                     rNN.restored.tree（本轮被退回后）；rNN.rejected.diff（被退回的改动）；green.tree（最近一次 smoke 绿的树）
shots/               r00_*、rNN_<态>.png、rNN_<态>__<crop>.png、rNN_manifest.json；失败态另存 rNN_<态>.failed.png；
                     r00_contact.png（起点图缩略总览，主会话开跑前只看这张，回应 R6）
scratch/impl-rNN/    implementer 自查截图
ledger.json          export 写（完整台账，续跑的来源）
SUMMARY.md           export 写
reviews/round_NN/<lens>.json, rounds/round_NN/{impl,verify}.json   export 写（原始返回，审计用）
```

### 2.2 args 契约（`args.json`，主会话写，init 校验并补默认值）

```jsonc
{
  "runtag": "2026-10-30_annotation-v6",
  "workdir": ".claude/web-loop/2026-10-30_annotation-v6",   // 相对 repo root
  "skillDir": ".claude/skills/web-loop",                     // init 补默认
  "goal": "（用户需求翻成的技术目标，原文）",
  "goalSubgoals": [ { "id": "G1", "desc": "…", "lenses": ["ux"], "measurable": "…", "states": ["01-x"], "relatedRefs": [] } ],
  "refImages": [],                    // 同现行 §2c
  "lenses": ["ux", "func", "code"],
  "url": "http://localhost:5173/",    // 也可是 file:// 
  "statesPath": ".claude/web-loop/<runtag>/states.json",
  "viewport": { "width": 2560, "height": 1440, "deviceScaleFactor": 1 },   // init 补默认
  "uiDir": "path2_web_ui",            // 从这里解析 @playwright/test 或 playwright（回应 K10）
  "rubricPath": "…",                  // 主会话起草的验收标准源文件；init 拷成 <workdir>/rubric.md 冻结
  "smokeCmd": "…",
  "restartCmd": null, "healthUrl": null, "refreshDataCmd": null,
  "maxRounds": 5, "staleRounds": 2, "maxAgents": null,
  "continueFrom": null,               // 上次 run 的 workdir；init 据此算出 seed 并注入 workflow.js
  "mode": "app",                      // app | prototype（T5；写进给用户点头的摘要）
  "schemeFiles": [],                  // 仅 prototype：方案文件（演示数据、模拟逻辑所在文件，如 data.js）
  "contractPath": null                // 仅 prototype：后端要求清单，放在原型旁边、不被 .gitignore 忽略（T3）
}
```

`validateArgs(A)`（CORE，init 与 SHELL 共用）规则：
- 必填非空：runtag、workdir、goal、goalSubgoals（≥1 条）、lenses（≥1，去重，匹配 `^[a-z][a-z0-9_-]*$`，不得叫 `workflow`）、url、statesPath、uiDir、rubricPath、smokeCmd。
- 每个子项：id 唯一；desc 非空；`lenses` 非空且是 args.lenses 的子集。
- `maxRounds` 取 1～20 的整数，默认 5；`staleRounds` 取 1～20，默认 2（可以大于 maxRounds，等于关掉停滞判据）；`maxAgents` 为 null，或不小于 `2 + lenses.length` 的整数。
- viewport 三个字段都是正数；默认 2560/1440/1。
- 返回 `{cfg, errors}`，cfg 已补齐默认值。
- **args 不经 LLM 抄写（采纳 R4）**：init 把校验过的 args 和续跑 seed 作为字面量写进 `<W>/workflow.js` 的 INJECT 段（`// ==== INJECT BEGIN ====` 与 `// ==== INJECT END ====` 之间，内容是 `const INJECTED = { v: 1, args: {…}, seed: {…} | null };`）。主会话调 `Workflow({ scriptPath })` 时不传 args；脚本只认 INJECTED，忽略运行时 args。
- SHELL 开头：INJECTED 缺失，或 validateArgs 有 errors → `throw "BLOCKED: …"`（此时一个 agent 都还没派）。
- mode 为 prototype 时：schemeFiles 至少 1 个；contractPath 必填；lenses 默认 `["newbie","razor","flow","contract"]`；maxRounds 默认 3。app 模式下 schemeFiles、contractPath 必须为空，lenses 默认 `["ux","func","code"]`。
- init 从 rubric.md 的「## 术语表」一节抽出词表（标题可以是 2～4 个 #，前面可以带编号，如「## 7. 术语表」，见 V2）（每行 `- <词>：<含义>`，取冒号前的部分并去掉反引号），写进 `INJECTED.derived.terms`。CORE 判断条目是否属于方案层时会用到它。
- 仅供测试的字段 `debug: true`：finalReturn 额外带上完整的 S（`state`）。init 不写这个字段。

`canonHash(x)`（CORE）：先把对象键递归排序后 `JSON.stringify`，再算 32 位 FNV-1a（按 UTF-16 码元），输出 8 位小写十六进制。只用来校验 verify 结果经 LLM 转交时有没有走样，不涉及安全。

### 2.3 运行时序

**主会话，开跑前**（SKILL.md「生成并运行」节）：
1. 智能入口层照旧填 args，新增三件事：
   - 子项要写 `lenses`；
   - 截图配方按 §2.9 的结构化格式写进 statesPath；
   - 起草验收标准（第 26 条，固定来源、固定结构，自定义角度要有专节），给用户几句话摘要，连同所选的评审角度一起请用户点头。
2. `mkdir -p <workdir>`，用 Write 写 `<workdir>/args.json`（以及 states.json、refs/）。
3. `node .claude/skills/web-loop/wl.mjs init <workdir>`（Bash timeout 设 600000）。不通过就按报错修 args 或配方，修完重跑 init。通过后**主会话只 Read 一张 `shots/r00_contact.png`**（起点图缩略总览，带态名，回应 R6），确认配方截到的是想要的画面；没写 expect 的态或看着可疑的态，再单独读那一张整图。这一步代价低，能挡住 run B 那类配方选错框的问题。
4. 调 `Workflow({ scriptPath: "<workdir>/workflow.js" })`，**不传 args**（args 和 seed 已由 init 注入脚本）。检查返回 status 为 `async_launched`；remote 立即中止，同现行。
5. **立刻**运行 `node …/wl.mjs attach <workdir> <runId> <Transcript dir>`，写 `run.json`。runId 和 Transcript dir 都在启动时打印的信息里（回应 J2；lead 实测 journal 所在目录会随会话 slug、会话 id 变化，不能猜）。

**Workflow 内**（§2.4）：iterate 各轮，没有 setup agent → 顶层 return 一个小对象。

**主会话，跑的过程中**：可以随时 `node …/wl.mjs status <workdir>`，看当前轮、开着的确证 must、子项状态、各 agent 的 toMain 留言。要纠错只能用三种文件（§2.8）；**不得用 SendMessage 回复 workflow 子代理，不得在 run 期间改代码**。

**主会话，结束后**：`node …/wl.mjs export <workdir>`（会先把 journal 和运行记录复制进 workdir）→ 读 SUMMARY.md → 用白话向用户汇报。续跑见 §2.8。

### 2.4 每轮流程与 agent 表

SHELL 伪代码（`call` 包装：计数 + 接住 throw）：

```js
// ==== INJECT BEGIN ====   （模板里是 const INJECTED = null;  init 生成 workflow.js 时替换成字面量）
const INJECTED = null;
// ==== INJECT END ====
if (!INJECTED || INJECTED.v !== 1) throw new Error('BLOCKED: workflow.js 未经 wl.mjs init 生成');
const { cfg, errors } = validateArgs(INJECTED.args);
if (errors.length) throw new Error('BLOCKED: args 无效：' + errors.join('；'));

let used = 0, threw = null;
async function call(prompt, opts) { used++; try { return await agent(prompt, opts); } catch (e) { threw = String(e?.message || e); return null; } }

const S = initState(cfg, INJECTED.seed);       // seed 版本不认识时 initState 抛 BLOCKED

phase('iterate');
try {
  for (let i = 0; i < cfg.maxRounds && !S.exit; i++) {
    if (threw) { markExit(S, 'budget', threw); break; }
    if (cfg.maxAgents != null && used + roundAgentEstimate(cfg) > cfg.maxAgents) { markExit(S, 'budget', `已用 ${used}`); break; }
    const round = S.round + 1, rt = rtag(round);
    const impl = await call(implPrompt(cfg, S, round), { label: `impl-${rt}`, phase: 'iterate', schema: IMPL_SCHEMA });
    applyImpl(cfg, S, round, impl);
    const verify = await call(verifyPrompt(cfg, S, round), { label: `verify-${rt}`, phase: 'iterate', effort: verifyEffort(cfg, S), schema: VERIFY_SCHEMA });
    const gate = reviewGate(verify);                       // {reviewable, skipReason, okStates|null}
    const reviews = gate.reviewable
      ? await parallel(cfg.lenses.map(L => () => call(reviewerPrompt(cfg, S, round, L, verify), { label: `review-${L}-${rt}`, phase: 'iterate', ...REVIEW_OPTS, schema: reviewerSchema(L) })))
      : null;
    reduceRound(cfg, S, round, verify, reviews);          // 含出口判定
    log(roundLine(S));      // 一行紧凑记录：轮号、kind、smoke、截图成功数、修好/新增/重开的 id、开着的确证 must 数、子项达成数、streak（J3）
  }
  if (!S.exit) markExit(S, threw ? 'budget' : 'max-rounds', threw);
} catch (e) { markExit(S, 'error', String(e?.message || e)); }
return finalReturn(cfg, S, used);                          // 小对象，见 §2.12
```

- `rtag(n) = 'r' + String(n).padStart(2, '0')`。label 一律为 `impl-rNN`、`verify-rNN`、`review-<lens>-rNN`（回放靠它们，**不得改**）。
- `roundAgentEstimate(cfg) = 2 + cfg.lenses.length`。
- **模型与类型**：所有 agent 都**不传 `model`**，继承会话模型。`REVIEW_OPTS` 是 CORE 常量，设为 `{ agentType: 'Explore' }`（见外-6；万一评审质量出问题，改回 `{}` 只需改这一处）。implementer 不传 agentType 也不传 effort；评审不传 effort。
- 状态 S 允许在原地修改，但只能由 CORE 函数修改，SHELL 里不写任何业务逻辑。纪律：同样的 cfg 加同样的结果序列，必须得出同样的 S（回放据此成立，§3 D25 测它）。
- `meta`：`{ name: "web-loop", description: "多轮迭代改进运行中的 web 应用：implement → verify（快照/smoke/刷新/截图）→ 多角度评审 → 台账判收敛", phases: [{title:"iterate", detail:"每轮 implement → verify → review"}] }`。

agent 表：

| agent | 何时 | 类型 / effort（模型一律继承） | 输入要点（§2.11 详） | 交回 | 写文件 |
|---|---|---|---|---|---|
| `impl-rNN` | 每轮 | 默认类型 / 不设 | 先跑 intake；GOAL、子项现状、确证 must 全文（含 attempts）、取证缺口和方向题的标题、nice 标题、最近修好的条目、上一轮被退回的 diff 路径、自查命令、`<workdir>/rubric.md` 与 principles 路径 | IMPL_SCHEMA | 只改项目源码；自查截图写 `scratch/impl-rNN/` |
| `verify-rNN` | 每轮 | 默认类型 / low（kind=data 且刷新方式是 .md 说明文件时用 medium） | 跑 `node <skillDir>/wl.mjs verify <workdir> --round N --kind K`；data 档的 .md 刷新先照文件做完，再给命令加 `--refreshed`；把最后一行 JSON 原样交回。全程尽量只调一两次工具 | VERIFY_SCHEMA | 无（命令自己写 snap/、shots/） |
| `review-<L>-rNN` | 可评审的轮 | Explore（REVIEW_OPTS）/ 不设 | 角色说明、GOAL、自己负责的子项、证据指针（本轮 manifest、r00 manifest；只有 code 另给 `wl.mjs diff` 命令和 implementer 的 summary）、自己名下的开着条目全文、`<workdir>/rubric.md`；非 newbie 另给别的角度开着条目的标题、已修条目的标题、方向题标题 | reviewerSchema(L) | 不写任何文件 |

- **评审读图范围**（回应 K16，写在角色说明里）：ux、rival、razor、newbie 读全部成功态的整页图，局部图按需读；func 读自己子项的 `states`、自己名下条目所在的态，以及 manifest 里有报错的态，其余按需；code 默认不读图，读 diff 和 manifest 里的报错文本。所有角色都写明「一次并行 Read 多张图」，减少轮次。

### 2.5 Schema 全文（CORE 常量）

```js
const STR = { type: 'string' }, STRS = { type: 'array', items: { type: 'string' } };
const TO_MAIN = { type: ['string', 'null'] };

const IMPL_SCHEMA = { type: 'object', required: ['kind', 'summary', 'changedFiles', 'attempts', 'hintsRead', 'overrides'],
  properties: {
    kind: { enum: ['frontend', 'backend', 'data', 'none'] },
    summary: STR,                                   // ≤10 行：改了什么、为什么
    changedFiles: STRS,
    attempts: { type: 'array', items: { type: 'object', required: ['issueId', 'approach'],
      properties: { issueId: STR, approach: STR } } },
    hintsRead: STRS,                                // intake 列出的 hint 文件名（本轮已遵循）
    overrides: { type: 'array', items: { type: 'object', required: ['key', 'id', 'action'],
      properties: { key: STR, id: STR, action: STR, requiredStates: STRS, note: STR } } },  // intake 原样转交
    deferred: { type: 'array', items: { type: 'object', required: ['issueId', 'title', 'options', 'recommend'],   // 仅原型模式采信（T2）
      properties: { issueId: STR, title: STR, options: { type: 'array', items: { type: 'object', required: ['choice', 'cost'],
        properties: { choice: STR, cost: STR } } }, recommend: STR, why: STR } } },
    toMain: TO_MAIN } };

const VERIFY_SCHEMA = { type: 'object', required: ['result'],
  properties: { result: { type: ['string', 'null'] },   // wl.mjs verify 最后一行文本本身（含 sig），由 CORE 的 verifyLine 解析；命令本身挂了填 null（V1）
                note: STR, toMain: TO_MAIN } };

function reviewerSchema(lens) {
  const s = { type: 'object', required: ['known', 'subgoals', 'issues', 'directions'],
    properties: {
      known: { type: 'array', items: { type: 'object', required: ['id', 'status', 'evidence'],
        properties: { id: STR, status: { enum: ['present', 'gone', 'unverifiable', 'decision'] }, evidence: STR, requiredStates: STRS } } },
      subgoals: { type: 'array', items: { type: 'object', required: ['id', 'status', 'evidence'],
        properties: { id: STR, status: { enum: ['met', 'unmet', 'unverifiable'] }, evidence: STR, requiredStates: STRS } } },
      issues: { type: 'array', items: { type: 'object', required: ['title', 'severity', 'detail', 'evidence'],
        properties: { title: STR, severity: { enum: ['must', 'nice'] }, state: { type: ['string', 'null'] },
          subgoal: { type: ['string', 'null'] }, detail: STR, evidence: STR,
          matchesIssueId: { type: ['string', 'null'] }, unverifiable: { type: 'boolean' }, requiredStates: STRS, files: STRS } } },
      directions: { type: 'array', items: { type: 'object', required: ['title', 'options', 'recommend'],
        properties: { title: STR, options: { type: 'array', items: { type: 'object', required: ['choice', 'cost'],
          properties: { choice: STR, cost: STR } } }, recommend: STR, why: STR } } },
      toMain: TO_MAIN } };
  if (lens === 'razor') s.properties.counts = { type: 'object', properties: { now: { type: 'object' }, baseline: { type: 'object' } } };
  return s;
}
```

`wl.mjs verify` 把**完整结果**写进 `snap/rNN.verify.json`，内容包括 smoke 末尾 40 行、changed 全表、各失败态的报错原文、刷新日志末尾、env 说明、journal 复制情况。**最后一行**只打印判定要用的短字段（S2），verify agent 原样转交的就是这一行，签名覆盖除 sig 以外的全部字段：

```jsonc
{ "round": 3, "kind": "frontend", "kindAdjusted": null,
  "envOk": true, "noChange": false, "journalCopied": true,
  "snapOk": true, "changedCount": 1, "schemeTouched": [],          // 原型模式：本轮改到的方案文件（路径，最多 10 个）
  "smoke": { "pass": true, "flaky": false, "rolledBack": false, "envBroken": false },
  // smoke 红：复测仍红 → 退回；复跑变绿 → pass:false, rolledBack:true；退回后复跑仍红 → pass:false, envBroken:true（改动已放回）
  //           快照不可用 → pass:false, rolledBack:false, envBroken:false, snapOk:false；复测变绿 → pass:true, flaky:true
  "refreshOk": true,
  "capture": { "okStates": ["01-a"], "failedStates": ["14-b"], "errorStates": ["07-q1"], "newErrors": [] },   // 没截图时为 null
  "manifest": "/abs/…/.claude/web-loop/<rt>/shots/r03_manifest.json",   // 在签名内；CORE 不读，只供按内容认 journal（U1）
  "sig": "1f2e3d4c" }
```

约定路径由 CORE 按轮号算出，不经转交：
- manifest：`<W>/shots/rNN_manifest.json`；
- 完整结果：`<W>/snap/rNN.verify.json`；
- 被退回的改动：`<W>/snap/rNN.rejected.diff`。

### 2.6 台账数据模型与归并规则（CORE）

```js
S = {
  round: 0,                 // 已完成的最后一轮（续跑时从 seed 继承）
  runFirstRound: 1,         // 本 run 的第一轮（显示用）
  issues: [Issue], directions: [Direction],
  subgoals: { [id]: { desc, lenses, byLens: { [lens]: { status, evidence, requiredStates, round } } } },
  rounds: [RoundRecord],
  lastKind: 'frontend', streak: 0, skipStreak: 0, missStreak: { [lens]: 0 }, everReviewed: false,
  bestMet: 0,               // 历史上同一轮达成子项个数的最大值（停滞判据用，回应 skeptic「新子项达成相对什么」）
  lastGreenRound: 0,        // 最近一次 smoke 绿的轮（0 = 开跑前）；SUMMARY 给恢复命令
  counters: { ['<lens>-r<round>']: k },
  doneControl: [],          // 已处理的控制文件 key（hint 文件名、override 的 "文件名#序号"）
  overrideErrors: [], toMain: [ { round, from, text } ],
  baselineCounts: {}, lastCounts: {},
  exit: null, exitDetail: null }

Issue = { id, lens /* 负责角度或 'workflow' */, title, severity /* must|nice */, detail, evidence, state, subgoal,
  unverifiable, requiredStates, humanUnverifiable, files, status /* open|fixed|waived */, waiveReason,
  bornRound, lastSeenRound, fixedRound, regressions, reopenedBy, disputed,
  alsoReportedBy: [lens], dissent: [{ round, lens, evidence }], attempts: [{ round, approach }],
  needsDecision /* 仅原型模式：null | 'proposed'（implementer 提议）| 'agreed'（负责角度同意，等用户拍板） */, proposal, decisionId /* 对应的方向题 id */ }

Direction = { id /* dir-<lens>-r<round>-<k> */, lens, round, title, options, recommend, why, alsoBy: [lens] }

RoundRecord = { round, kind, implOk, implSummary, changedFiles, verifyOk, sigOk, smoke, refreshOk,
  capture: { ok, failed: [...], newErrors: [...] } | null, reviewed, skipReason, missingLenses: [],
  fixed: [ids], born: [ids], reopened: [ids], dissents: n, badMatch: [ids], untabled: { [lens]: [ids] },
  unverifiableRejected: [..], goneIgnored: [ids], metDowngraded: [subgoalIds], untabledSubgoals: { [lens]: [ids] },
  malformed: [labels], deferRejected: [{id, reason}], schemeTouched: [paths], envOk, noChange, kindAdjusted, met: [subgoalIds], openConfirmed, openUnverifiable, progress, streak }
```

**id**：评审新条目 `<lens>-r<round>-<k>`（k 按「角度+轮」计数，只在新建时递增）；方向题 `dir-<lens>-r<round>-<k>`；脚本条目 `wf-regress`、`wf-state-<态>`、`wf-pageerror-<态>`（id 固定，开关由观察决定）。

**`applyImpl(cfg, S, round, impl)`**（verify 之前调用）：
1. 新建 RoundRecord：`implOk = impl != null`，记下 kind、summary、changedFiles。
2. `S.lastKind = impl?.kind ?? S.lastKind`。
3. overrides：key 已在 `doneControl` 里的跳过；否则校验——id 必须存在；action 为 `waive` 时把 status 置为 `waived`，waiveReason 写「人工：<note>」；action 为 `unverifiable` 时置 `unverifiable=true, humanUnverifiable=true`，requiredStates 依次取 o.requiredStates、原值、`[state]`。不合法的写进 `overrideErrors`。合法与否，key 都记进 `doneControl`（避免每轮重复报错）。
4. attempts：id 有效的追加 `{round, approach}`，无效的忽略。
5. hintsRead 并入 `doneControl`，toMain 追加到 `S.toMain`。
6. deferred（T2）：只在 `cfg.mode==='prototype'` 时处理，否则全部记进 `rec.deferRejected`（原因写「app 模式」）。
   - **前置筛选**：条目必须存在、处于 open、是 must、负责角度是评审（不是 workflow），并且属于方案层，才进入提议。属于方案层的判据：条目的 files 与 `cfg.schemeFiles` 有交集（按路径前缀比较，去掉 `:行号`），或者条目的 title 加 detail 里出现了 `derived.terms` 中的某个词。
   - **通过筛选**（回应 X1：被评方不能自己豁免 must）：置 `needsDecision='proposed'`，把提议（title、options、recommend、why）记在 `issue.proposal`。这时**还不算挂起**：它照常算确证 must，也不算进展。
   - **由负责角度表态**：本轮评审 prompt 里，负责角度会在自己名下的这一条上看到提议的标题、选项和理由（看不到 implementer 的 summary），known 的 status 多一个 `'decision'`：
     - 回 `'decision'`：同意这条要用户拍板。置 `needsDecision='agreed'`，新建方向题 `dir-impl-r<round>-<k>`（lens 记 `implementer`），填好 decisionId。
     - 回 `'present'`：不同意。needsDecision 清空，并记进 `rec.deferRejected`（原因写「负责角度不同意」）。
     - 回 `'gone'`：照常关闭。
     - 负责角度本轮缺席：提议保持 proposed，下一轮再表态。
   - **已同意的条目**：之后各轮负责角度回 `'decision'` 或 `'present'`，都维持 agreed；回 `'gone'` 时照常关闭，needsDecision 清空。对没有提议的条目回 `'decision'`，按 `'present'` 处理，并记进 rec。
   - **没通过筛选**：直接记进 `rec.deferRejected` 并写明原因，条目照常算确证 must。

**形状校验**：
- `normalizeImpl` / `normalizeReview`：顶层所需的数组字段类型不对，或 impl 的 kind 非法，就整份当作 null，并把 label 记进 rec.malformed。数组里个别元素形状不对或枚举值非法，只丢掉那个元素。
- verify 的 result 缺 smoke 字段，同样当作 null。
- 保证任何返回形状都不会让 CORE 抛错。

**`verifyLine(verify)`**（L4 查出 V1 后新增）：从 verify 的返回里取出短结果对象。
- result 是字符串：取最后一个非空行再 JSON.parse。
- 兜底一：result 已经是解析好的对象（带 smoke 字段），直接认。
- 兜底二：result 是包了一层的对象，就在它的字符串字段里找能解析出带 smoke 字段对象的那一个。
- 都不成立 → null。

`normalizeVerify` 在 verifyLine 的结果上规整字段。

**`reviewGate(verify, round)`**：
- 先算 `sigOk`：verifyLine 取出的对象去掉 sig 后，`canonHash` 等于其中的 sig，**并且对象里的 round 等于本轮**。round 对不上（转交了别一轮的结果），一律按签名不符处理。
- `verify?.result` 为空 → 跳过（「verify 未交回」）。
- `envOk === false` → 跳过（「服务不可达」）。
- `noChange === true` → 跳过（「本轮无改动」）。
- `smoke.pass === false` → 跳过（rolledBack 时为「本轮改动使 smoke 失败，已退回」，否则为「smoke 失败」）。
- `refreshOk === false` → 跳过（「刷新失败」）。
- `capture` 为空或 `okStates` 为空 → 跳过（「无可用截图」）。
- 其余情况可评审。
- sig 对不上时**仍然评审**（截图和 manifest 都在磁盘上，评审直接读文件），但本轮不按 result 开关 wf 条目，`okStates` 视为未知，而且本轮不能以收尾类出口结束（S1）。

**`reduceRound(cfg, S, round, verify, reviews)`**：

```
rec = 当前 RoundRecord；res = verify?.result；gate = reviewGate(verify)
1) 脚本条目（只在 sigOk 时执行）：
   smoke.rolledBack===true → openWf('wf-regress', '第 N 轮改动使 smoke 失败，已退回', 'smoke 输出见 <W>/snap/rNN.verify.json；被退回的改动见 <W>/snap/rNN.rejected.diff')
   smoke.pass===true → closeWf('wf-regress')；S.lastGreenRound=round
   capture 非空：failedStates[] → openWf('wf-state-'+s, '截图失败：'+s, '原因见 <W>/shots/rNN_manifest.json 中该态的 error', s)；okStates[] → closeWf('wf-state-'+s)
                newErrors[] → openWf('wf-pageerror-'+s, '新出现页面报错：'+s, …, s)
                okStates 里不在 errorStates 中的 s → closeWf('wf-pageerror-'+s)
   openWf：不存在→新建(lens:'workflow', severity:'must', status:'open', bornRound=round)；已 fixed→status=open, regressions++；均更新 lastSeenRound、detail
   closeWf：存在且 open → fixed, fixedRound=round
2) 若可评审：okSet = sigOk ? new Set(okStates) : null
   accept(R) = R 非空 && (okSet===null || R.some(s => !okSet.has(s)))        // 回应 K4
   第一遍（顺序与角度顺序无关）：对每个 lens L，r = reviews[i]
     r==null → rec.missingLenses.push(L)；continue
     known：只处理「status=open 且 lens===L」的条目；id 不在其中 → 忽略
       gone        → 若 okSet 已知且 iss.state 非空且 iss.state∉okSet：不生效（那个态本轮没截成功，凭不了证据），记进 rec.goneIgnored（回应 R2）
                     否则 status=fixed, fixedRound=round；若 reopenedBy 非空则 disputed=true、reopenedBy=null
       present     → lastSeenRound=round, evidence=k.evidence；若非 humanUnverifiable，置 unverifiable=false
       unverifiable→ R = k.requiredStates 非空 ? k.requiredStates : (iss.requiredStates 非空 ? iss.requiredStates : (iss.state ? [iss.state] : []))
                     accept(R) ? (unverifiable=true, requiredStates=R) : (按 present 处理，rec.unverifiableRejected.push(id))
       L 名下开着、但这一轮没表态的条目 → 不改，记进 rec.untabled[L]
     subgoals：只处理负责角度含 L 的子项 → byLens[L] = {status, evidence, requiredStates, round}
       status==='unverifiable' 且 !accept(requiredStates) → 改成 'unmet'，并记进 unverifiableRejected
       status==='met' 且 okSet 已知且子项声明了 states 且这些 states 一个都不在 okSet 里 → 改成 'unverifiable'、requiredStates=子项的 states，并记进 rec.metDowngraded（回应 R2）
       L 负责、但这一轮没给出结论的子项 → 记进 rec.untabledSubgoals[L]（N7），SUMMARY 列出
   第二遍：对每个 lens L 的 r.issues（按顺序）
     规整：unverifiable 且 requiredStates 为空、有 state → requiredStates=[state]；unverifiable 且 !accept → unverifiable=false，并记进 rejected
     m = matchesIssueId ? 按 id 查 : null
       m 存在且 open    → lastSeenRound=round；m.lens!==L 时把 L 并入 alsoReportedBy；continue
       m 存在且 fixed   → 若 L===m.lens：重开（status=open, regressions++, reopenedBy=null, lastSeenRound, evidence）
                          否则若 m.fixedRound===round || m.disputed：只记 dissent{round,lens,evidence}
                          否则：重开（status=open, regressions++, reopenedBy=L）
                          continue
       m 存在且 waived  → 忽略；continue
       有 matchesIssueId 但查不到 → rec.badMatch.push(该 id)，按新条目处理
       同 lens、同标题、仍开着的条目已存在 → 更新 lastSeenRound；continue
       新建：id=nextId(L,round)，lens=L，status=open，bornRound=lastSeenRound=round，其余字段取自评审
     directions：标题完全相同的已存在 → 把 L 并入 alsoBy；否则新建
     counts（仅 razor）：若 baselineCounts[L] 为空且 r.counts.baseline 存在，则赋值；lastCounts[L]=r.counts.now
     toMain 追加
3) 统计：
   confirmedOpen   = issues.filter(status==='open' && severity==='must' && !unverifiable)
   unverifOpen     = issues.filter(status==='open' && severity==='must' &&  unverifiable)
   sgStatus(g)     = 负责角度 g.lenses 的 byLens[L] 必须都满足 round===本轮：全为 met→'met'；任一 unmet→'unmet'；
                     其余若有负责角度未表态或缺席→'pending'；否则（只剩 unverifiable）→'unverifiable'
                     （pending 排在 unverifiable 前：有角度没表态时不能算「只剩取证缺口」）
   met             = 状态为 'met' 的子项 id（本轮可评审时才算，否则为 []）
   fixedNow        = severity==='must' 且 fixedRound===round 的条目数（含 wf-state、wf-pageerror；不含 wf-regress，
                     因为把 smoke 修回绿只是回到起点；waived 不算）
   progress        = fixedNow>0 || met.length > S.bestMet || 本轮有条目变成 agreed（原型模式：负责角度同意交给用户拍板，也算推进；只提议不算）         // 子项按「刷新最高纪录」计，时有时无的覆盖不会反复清零计数
   S.bestMet       = max(S.bestMet, met.length)
   if (gate.reviewable && !S.everReviewed) { S.everReviewed=true; S.streak=0 }   // 第一个评审轮只作起点
   else S.streak = progress ? 0 : S.streak+1
   S.skipStreak = (gate.reviewable || noChange) ? 0 : S.skipStreak+1     // V4：noChange 不算环境故障，只计入 streak（无进展），连续两轮 → stalled
   对每个 L：可评审轮里 reviews[L]==null → missStreak[L]++；可评审轮里交回了 → 0；跳过的轮不变
4) 出口（按序取第一个成立的）：
   allPresent = gate.reviewable && rec.missingLenses.length===0；sigOk = gate.sigOk
   closable   = allPresent && sigOk                                        // S1：签名对不上的轮不能收尾
   confirmedX = confirmedOpen.filter(i => i.needsDecision !== 'agreed')     // 只扣除负责角度同意过的（X1）
   a. closable && confirmedOpen.length===0 && unverifOpen.length===0 && 全部子项为 'met'             → 'converged'
   b. closable && confirmedOpen.length===0 && 没有子项为 'unmet' 或 'pending'（剩下的只有取证缺口）  → 'evidence-gap'
   b2. closable && cfg.mode==='prototype' && confirmedX.length===0 && 有 needsDecision==='agreed' 的条目
       && 没有 pending 的子项 && 每个 unmet 的子项都至少挂着一条 agreed 条目（issue.subgoal===g.id）→ 'decision-gap'（T2）
   c00. envOk===false                                                  → 'blocked'（detail：「url 不可达，服务没在跑」）
   c0. smoke.envBroken===true                                             → 'blocked'（detail：「退回本轮改动后 smoke 仍红：环境或基线坏了；本轮改动已放回」）
   c1. smoke.pass===false 且 !rolledBack 且 !envBroken（快照不可用、无法退回；判据用 snapOk===false）→ 'blocked'（detail：「smoke 红且无法退回，工作区停在本轮改动后的状态」）
   c. S.skipStreak>=2                                                     → 'blocked'（detail：最近两轮的 skipReason，含「连续两轮改动都被退回」）
   d. 有某个 L 的 missStreak[L]>=2                                         → 'blocked'（detail：「角度 L 连续两轮没交回」，回应 K7）
   e. S.streak>=cfg.staleRounds                                           → 'stalled'（detail：开着的确证 must 与未达成的子项）
   （SHELL 另判 'budget' / 'max-rounds' / 'error'）
5) S.round=round；把 openConfirmed/openUnverifiable/met/progress/streak 写进 rec
```

需要特别指出的几点：
- 「开着」只有 `status==='open'` 这一种状态，原来的 `regressed` 合并进来，用 `regressions` 计次。
- 确证 must 包含 wf 条目，它们都挡收敛。修好 wf-state 和 wf-pageerror 算进展；wf-regress 被关闭不算进展，因为那只是回到上一轮的状态。所以「改坏 → 退回 → 下一轮没别的进展」会累计成停滞或环境故障，不会无限循环。
- 子项「达成」要求本轮所有负责角度都给了 met。证据只认本轮，旧证据不延续（防「曾经覆盖过就一直算覆盖」）。
- verdict 只是显示用的推导值：某角度名下没有开着的确证 must，且它负责的子项都 met，就记 pass，不进任何判据。

**`initState(cfg, seed)`**：没有 seed 时各字段取空值，子项按 cfg 初始化。有 seed 时：
- 继承 round、issues、directions、everReviewed、lastKind、baselineCounts、lastCounts、doneControl（续跑用新 workdir，control/ 是新的，所以这里一般是空集）。
- 子项只在 id 与 desc 都没变时继承 byLens。
- 负责角度不在 cfg.lenses 里、也不是 workflow 的开着条目：置为 waived，waiveReason「所属角度本次未启用」（回应 K20）。
- streak、skipStreak、missStreak 清零，`runFirstRound = seed.round + 1`。

**`toSeed(S)`**（init 在 continueFrom 时调用，结果注入 INJECTED.seed）：开着的条目给全字段；fixed 和 waived 的条目只留 `{id, lens, title, severity, state, status, fixedRound, disputed}`；directions 全量；子项给 `{desc, lenses, byLens}`；外加 round、everReviewed、lastKind、baselineCounts、lastCounts，以及 `v: 1`。

### 2.7 判据定义汇总

| 出口 | 一句话 | 公式 |
|---|---|---|
| `converged` | 全部达标 | 本轮可评审 ∧ 角度到齐 ∧ sigOk ∧ 没有开着的 must（确证与取证缺口都没有）∧ 所有子项本轮被负责角度判 met |
| `evidence-gap` | 能修的都修完了，剩下的要人补证据 | 本轮可评审 ∧ 角度到齐 ∧ sigOk ∧ 确证 must 为 0 ∧ 没有 unmet 或 pending 的子项 ∧ 还有 unverifiable 的 must 或子项 |
| `decision-gap` | 仅原型模式：能改的都改完了，剩下的要你拍板 | 本轮可评审 ∧ 角度到齐 ∧ sigOk ∧ 除负责角度同意挂起（agreed）的条目外，确证 must 为 0 ∧ 有 agreed 条目 ∧ 没有 pending 子项 ∧ 每个 unmet 子项都挂着 agreed 条目 |
| `blocked` | 环境或代理一再失败 | 退回本轮改动后 smoke 仍红（环境坏了）；或 smoke 红而快照不可用；或连续 2 轮没能评审（含连续 2 轮被退回）；或同一角度在连续 2 个可评审轮都没交回 |
| `stalled` | 评审正常进行，但没有进展 | 第一个评审轮之后，连续 `staleRounds`（默认 2）轮既没有确证 must 被修好（wf-regress 不算），同一轮达成的子项个数也没有超过历史最高 |
| `max-rounds` | 本 run 跑满 maxRounds | SHELL 循环自然结束 |
| `budget` | 代理数达到上限，或运行时预算耗尽（agent 抛错） | 开轮前 `used + 2 + lenses > maxAgents`，或 call 接到 throw |
| `error` | 脚本意外异常 | 外层 catch 接住 |

这些出口一律结束本 run，不存在「暂停后原地续」。所有出口都有对应的 SUMMARY「下一步」段落（§2.12）。

「正常情况怎么放过」逐条核对：
- 稳步推进（T2）：每轮都有修好的条目，streak 恒为 0。
- code 角度从不报 must：判据看全体，与单个角度的数字无关。
- 偶发一轮改坏：按快照退回，复跑 smoke 变绿，本轮不评审（skipStreak=1）；下一轮正常推进后 skipStreak 归零。
- 偶发一个角度一轮没交回：missStreak=1，下一轮交回即归零。
- 评审正当地报出取证缺口（点名了没截成功的态）：采信，不挡出口 b。

### 2.8 续跑与中途纠错

**续跑**（任何出口之后，用户说「继续」）：
1. 新 runtag、新 workdir；args 基本照旧（可以按 SUMMARY 改配方、子项、角度），加 `continueFrom: <旧 workdir>`。
2. `wl.mjs init` 额外检查 `<旧 workdir>/ledger.json` 存在（不存在就先对旧 run 跑 export）。
3. init 用 `toSeed(上次 ledger)` 生成 seed 并注入新的 workflow.js，Workflow 内直接 `initState(cfg, INJECTED.seed)`。轮号接着 `ledger.round + 1` 往下编；每轮所有子项照常重新验证（只认本轮证据，回应 K20），延续下来的是条目身份、attempts、方向题和起点计数。
4. 运行时自带的 resume（`resumeFromRunId`）只用于「同一 session 内 run 被意外打断后原样续」，不在 SKILL 流程里推荐，文档里作为一句附注。

**中途纠错**（run 进行中，主会话做；下一轮生效）：

| 要做的事 | 做法 | 谁读、何时生效 |
|---|---|---|
| 截图配方写错、要加状态 | 直接改 statesPath 文件；先在终端跑 `node …/capture.mjs shoot --workdir <W> --round 99 --only <态> --out <W>/scratch/main` 试一下 | 下一轮 verify 的截图器 |
| 告诉 implementer 真实根因、该改哪 | 写 `<W>/control/hint-<任意名>.md`（自然语言） | 下一轮 implementer 开工时 intake |
| 某条问题其实是配方问题或不该管 | 写 `<W>/control/override-<任意名>.json`：`{"id":"func-r1-1","action":"unverifiable","requiredStates":["14-b"],"note":"…"}` 或 `{"id":"…","action":"waive","note":"…"}`（单个对象或数组） | 同上；在本轮评审之前生效，评审看不到被 waive 的条目 |

`wl.mjs intake <W> --done <逗号分隔的 key>`：列出 `control/` 下 key 不在 done 里的 `hint-*.md` 和 `override-*.json`，打印 `{hints:[{key,text}], overrides:[{key,...}]}`，**不改文件名**（回应 K11）。override 的 key 是「文件名#序号」。implementer 的 prompt 里直接写好 `--done` 列表（取自 `S.doneControl`）。implementer 中途挂掉的话，什么都不算处理过，下一轮会重新读到。

### 2.9 截图与快照设计（`capture.mjs` 与 `wl.mjs verify`）

**配方格式**（statesPath 是一个 JSON 数组；`validateStates` 校验，init 时执行）：

```jsonc
{ "state": "14-compare-box",                   // 唯一，^[A-Za-z0-9_-]+$
  "note": "compare 档选中放量突破框",            // 给评审看：这个态展示什么
  "path": "#q=q3",                             // 可选，拼在 url 后
  "viewport": { "width": 1600, "height": 900 }, // 可选，覆盖 args.viewport
  "steps": [ { "wait": 800 }, { "eval": "S.mode='compare'; S.sel=…; render()" }, { "waitFor": ".panel" },
             { "click": "#btn" }, { "press": "Escape" }, { "css": "#wrap{height:auto!important}" },
             { "pw": "await page.mouse.move(100,200)" } ],
  "fullPage": false,
  "probe": "({mode:S.mode, box:S.sel&&S.sel.name})",   // 页面里求值的表达式
  "expect": { "mode": "compare", "box": "放量突破" },    // 对探针结果做部分深比较
  "crops": [ { "name": "side", "selector": "#side" }, { "name": "chart", "clip": { "x": 0, "y": 0, "width": 1600, "height": 900 } } ] }
```

- 每个 step 恰好一个键。eval 用 `page.evaluate(src => (0, eval)(src), code)` 执行语句；pw 用 `new AsyncFunction('page', code)` 执行。
- **配方禁止用 `||` 写兜底；探针必须记录「目标是谁」**（如选中框的名字），要能断言的写进 expect。这两条写进 SKILL.md。
- 任一步抛错、某个 crop 的选择器找不到、探针抛错、expect 不符 → 该态失败。error 写成「step 3 (click #btn)：<原始 message>」或「expect 不符：box 期望 放量突破 实际 平台」，**不吞异常**。失败态仍截一张 `rNN_<态>.failed.png` 给人排查，但不列入 okStates。
- 页面报错不判失败，分别记进 `consoleErrors`（console 里 type=error 的）、`pageErrors`（未捕获异常）、`failedRequests`。

**`capture.mjs`**：
- `shoot --workdir W --round N [--only a,b] [--out DIR]`：读 `W/args.json` 取 url、statesPath、viewport、uiDir，用 `createRequire(path.resolve(uiDir) + '/')` 依次尝试解析 `@playwright/test`、`playwright`，再动态 import（回应 K10）。`chromium.launch({channel:'chrome', args:['--no-sandbox','--disable-dev-shm-usage']})`，失败就退回不带 channel 再试一次，实际用了哪个记进 manifest 的 `browser` 字段。每个态单独开一个 context（设 viewport 与 deviceScaleFactor），串行执行。打印进度行，**最后一行**输出 summary JSON。
  - 写 `shots/rNN_<态>.png`、`shots/rNN_<态>__<crop>.png`、`shots/rNN_manifest.json`：`{round, url, browser, viewport, states:[{state, note, ok, error, shot, crops:[{name,path}], probe, consoleErrors, pageErrors, failedRequests}]}`。
  - `computeNewErrors`（采纳 N2）：上一份 manifest 取 shots/ 里轮号小于 N 的最大一份（含 r00）。某个态在上一份里存在，这一份的 pageErrors 文本集合里出现了上一份没有的文本（取每条的首行；去掉其中的 `:行:列` 数字后比较），就算新报错；上一份里没有的态不算。
  - 带 `--out` 是自查模式：写到 DIR，不比上一份，不签名。
  - 只有浏览器起不来或参数错时退出码非 0；有失败态时退出码仍是 0（失败是数据，不是程序错误）。
- `check --workdir W`：起浏览器，goto url，打印 `{ok, status, browser, error}`。
- `contact --workdir W --round N`（R6）：用同一个浏览器渲染一个本地 HTML，把该轮各态整页图按网格排成缩略图（每格宽 480 像素，下方写态名，失败态标红框并写出错误首行），截成 `shots/rNN_contact.png`。不依赖任何图像库。

**`wl.mjs verify <W> --round N --kind K [--refreshed] [--no-change-hint]`**（一个进程按顺序做完；所有等待和轮询都用 node 定时器实现，不写 shell 的 sleep，因为前台 sleep 会被 Bash 工具拦下，回应 N10）：
0. **留证与环境**：
   - 复制 journal（J1、U1：只复制、不解析）：若 `<W>/run.json` 存在，复制 `<transcriptDir>/journal.jsonl`。没有 run.json 且 N≥2 时，在 `~/.claude/projects` 下找最近 24 小时改过的 `…/workflows/*/journal.jsonl`，挑出含有 `"<W 的绝对路径>/shots/` 字样的那一份（第 1 轮的 verify 结果里一定有它）。**不按 label 认**，因为 label 在不同 run 之间会重复。唯一就复制成 `<W>/journal.jsonl` 并补写 run.json；找不到或有多份，只在完整结果里记一句。
   - 探一下 url（http(s) 发 GET，file:// 检查文件存在）。不通就每 2 秒重试，最多 30 秒（V3：dev server 瞬断几秒不该停掉整个 run），仍不通 → `envOk:false`，直接输出（N3：服务没在跑，这一轮修不了任何东西）。
1. **快照**（git 命令都带环境变量 `GIT_INDEX_FILE=<W 的绝对路径>/snap/snap.idx`。这个 index 整个 run 复用，首次由 init 用 `git read-tree HEAD` 建；之后带 stat 缓存，所以很快）：
   - `git add -A && git write-tree` 得到本轮交回后的树，写进 `snap/rNN.tree`。
   - 本轮开工前的树 `pre` 取 `r(N-1).restored.tree`，没有就取 `r(N-1).tree`，再没有就取 `r00.tree`。
   - `changed` = `git diff --name-status --no-renames <pre> <rNN.tree>`，去掉豁免路径。豁免路径是 statesPath、rubricPath、`.claude/web-loop/` 下的一切、workdir。
   - **不碰真 index、HEAD 和 stash**，不提交。失败时记 `snapOk=false` 并继续。GIT_INDEX_FILE 一律用绝对路径；结果里的 `changed` 最多列 50 条，另附总数 `changedCount`（N4）。
   - 同时记下 statesPath 文件内容的 canonHash，写进 `snap/rNN.states`，供 N1 判断「本轮无改动」用。
   - 原型模式：changed 里落在 schemeFiles 内的路径记为 `schemeTouched`。
   - 作用有三个：回滚、给 code 评审准确的本轮 diff、给 SUMMARY 列出本 run 的累计改动。
2. **smoke**：在 repo root 用 shell 跑 smokeCmd，以退出码判 pass，取末尾 40 行，写进完整结果。
   - **绿**：把 `rNN.tree` 拷成 `green.tree`，继续第 3 步。
   - **红**：先不动改动，原样复测一次（S3）。复测变绿 → 记 `flaky:true`，按绿处理；仍红 → 往下走。
   - **复测仍红且 snapOk**，按快照退回：
     1. 先把 `git diff --no-renames <pre> <rNN.tree> -- <changed 路径>` 存到 `snap/rNN.rejected.diff`。
     2. 用另一个临时 index `snap/restore.idx` 恢复：`git read-tree <pre>`，再 `git checkout-index -f -- <pre 里存在的 changed 路径>`；pre 里不存在的路径（本轮新增的）直接删掉。
     3. 退回后再跑一次 smoke。
        - 变绿：再拍一次快照写进 `rNN.restored.tree`，同时拷成 `green.tree`；结果写 `rolledBack:true`（被退回的 diff 在约定路径 `snap/rNN.rejected.diff`）。
        - 仍红：说明不是本轮改动造成的。用同样的办法从 `rNN.tree` 把这些路径恢复回去（本轮删掉的再删一次）；结果写 `envBroken:true`。
     4. 两种情况都到此为止（capture 为 null）。
   - **红但快照不可用**：不动工作区，直接输出。
   - 只有回滚动工作区里的文件，而且只动 changed 路径。开跑前就有的未提交改动在 pre 里，退回时会原样恢复；主会话中途改的配方属于豁免路径，不受影响（回应 K9）。被忽略的文件不进快照，回滚管不到，SKILL.md 写明这一点。
2b. **本轮无改动就不评审**（采纳 N1）：changedCount 为 0，statesPath 的哈希与上一轮相同，并且 prompt 带了 `--no-change-hint`，并且实际档位是 frontend 或 none，就输出 `noChange:true` 并停下，不截图。`--no-change-hint` 由脚本在「上一轮评审过」且「本轮没有应用任何 override」时加上。上一轮没评审过，它的改动就还没被看过，不能跳过。这一轮不评审，skipReason 写「本轮无改动」：评审结果必然与上一轮相同，没必要重跑。这一轮计入 streak（无进展），不计入 skipStreak（V4）。
3. **刷新**：
   - **实际档位**（采纳 N8）：kind 为 frontend 或 none，但 changed 里有 uiDir 之外的源码文件（扩展名 .py .ts .js .mjs .vue .go .rs .java .rb .json .yaml .yml），并且配了 restartCmd → 按 backend 处理，结果里写 `kindAdjusted:"backend"`。
   - **frontend / none**：不做事（截图器每次都新开浏览器）。带 `--refreshed` 时也不做事。
   - **backend**（回应 R1，lead 实测）：
     1. 从 healthUrl 解析端口，`lsof -ti:<port> -sTCP:LISTEN` 取旧的监听进程号，逐个 kill（只按端口查到的进程号，绝不 pkill 或按名字杀）。
     2. 用 node 定时器轮询，最多 15 秒等端口释放；
     3. `spawn(restartCmd, {shell:true, detached:true, stdio:['ignore', 日志, 日志]}).unref()`，日志写 `<W>/snap/restart-rNN.log`；不等它退出（它就是那个常驻进程）。
     4. 每 500 毫秒轮询 healthUrl，最多 90 秒。**返回 200，且端口上的监听进程号与旧的不同**，才算成功；超时或进程号没变 → `ok:false`，note 附上日志末尾。
     - 不能用 `$!` 记进程号：实测它拿到的是外层包装 shell 的进程号，不是监听端口的那个进程。
   - **data**：先做 backend 那几步，refreshDataCmd 是命令就执行。是 .md 说明文件而又没带 `--refreshed`，则 `refreshOk=false`，完整结果的 note 写「需先按说明文件刷新」。缺 restartCmd 或 healthUrl → refreshOk=false，并在完整结果里写明原因。
   - 刷新失败就停下。
4. **截图**：调用 `capture.shoot()`，进程内 import，不另起进程。
5. 把完整结果写进 `snap/rNN.verify.json`。组装短结果（§2.5 的字段），`sig = canonHash(去掉 sig 的短结果)`，canonHash 用 `loadCore(<W>/workflow.js)` 里的那份，保证与脚本一致；短结果打印在最后一行。
   - verify agent 调这条命令时，Bash 的 timeout 必须设为 600000。lead 实测：默认超时 2 分钟，上限 10 分钟，前台跑 240 秒正常完成。
   - 单次 verify 必须在 10 分钟内跑完。数据重扫超过这个时长的项目，要么在 `.web-loop-refresh.md` 里改用数据子集，要么不适合用本 skill；这一点写进 SKILL。

**`wl.mjs diff <W> --round N | --run`**：打印 `git diff <pre(N)> <rNN.tree>`（pre 的取法同上）；`--run` 时打印 `git diff <r00.tree> <最新的 restored 或 tree>`。可以带 `-- <路径>` 过滤。code 评审用它看本轮 diff，树 id 不经过 LLM。

**`wl.mjs restore <W> --to <rNN|green|r00> [--dry-run]`**：复用回滚用的同一个函数。先拍一份当前快照，再把与目标树之间变了的非豁免路径恢复成目标树的样子。仅在用户明确要求时由主会话执行，先跑 `--dry-run` 列出要动的路径给用户看。SUMMARY 遇到 blocked 和 stalled 时会给出这条命令，以及最近一次 smoke 绿的是哪一轮（回应 skeptic「blocked 时工作区停在坏状态」）。

### 2.10 `wl.mjs` 其余命令

- `loadCore(templatePath)`：读文件，截取 `// ==== CORE BEGIN ====` 与 `// ==== CORE END ====` 之间的源码，用 `new Function(src + '\nreturn {validateArgs, canonHash, initState, applyImpl, normalizeImpl, normalizeReview, reviewGate, reduceRound, markExit, finalReturn, toSeed, replay, renderSummary, compactLedger, implPrompt, verifyPrompt, reviewerPrompt, reviewerSchema, IMPL_SCHEMA, VERIFY_SCHEMA, REVIEW_OPTS, BUILTIN_LENSES, rtag, roundAgentEstimate}')()` 求值。CORE 里**不得引用** agent、parallel、phase、log、args、budget，也不得用 `Date.now`、`Math.random`、无参 `new Date`、`structuredClone`、`require`、`import`（测试 D27 用空作用域加载 CORE 来检查）。
- `init <W>`：按序执行，任一步失败就打印错误并以退出码 1 结束：
  1. 读 args.json，执行 validateArgs；
  2. `git check-ignore -q <W>`；
  3. 确认 rubricPath 与 `<skillDir>/principles.md` 可读；rubric 的检查对象是 rubricPath 原文件；拷成 `<W>/rubric.md` 放在 init 的最后一步，所有检查都通过之后才拷（已存在且内容不同就报错，不覆盖冻结件）；
     检查角度专节：每个不在内置清单 BUILTIN_LENSES = [ux, func, code, rival, razor, newbie, flow, contract] 里的角度，以及 razor、newbie、flow（flow 的专节要列出流程经过的状态顺序），在 rubric.md 里都要有专节，标题匹配 `^#{2,4}\s*<可选编号>(角度|lens)[\s:：]+<名>\s*$`（不区分大小写；可选编号如「7.」「5.1」，见 V2），缺了就报错（第 27 条）；
  4. 解析 statesPath 并执行 validateStates；没有声明 crops、视口宽度超过 1600 的态，打印提醒「小字区域请声明 crops」（不算错误，U2）；
  4b. prototype 模式：schemeFiles 都要存在；contractPath 不能被 .gitignore 忽略，也不能在 workdir 里（T3）。contractPath 不存在，就生成一个只有标题和说明的骨架，**并以退出码 1 结束**；内容仍与骨架完全相同时同样拦下（X2），要求主会话先按原型现状补齐清单。否则第 1 轮会被 contract 角度报的一大批「清单缺字段」占满。rubric.md 必须有「## 术语表」一节；
  5. 确认 refImages 的路径都存在；
  6. 有 continueFrom 时确认 `<continueFrom>/ledger.json` 存在；
  7. 清理旧截图（§1 第 18 条）；
  8. 跑 smokeCmd 拿基线，必须退出码为 0；
  9. 给了 healthUrl 就要求返回 200；
  10. 跑 `capture.check`；
  11. 建快照 index 并拍 `snap/r00.tree`；
  12. 截 r00，有失败态就报错并列出原因；
  13. 渲染 goal.md，把模板拷成 `workflow.js`；
  14. 补默认值写回 args.json；有 continueFrom 时读 `<continueFrom>/ledger.json` 并执行 toSeed；生成 `<W>/workflow.js`：模板全文，把 INJECT 段替换成 `const INJECTED = {v:1, args, seed};`（`JSON.stringify` 生成字面量）；打印「OK」和下一步的 Workflow 调用。
  15. 同时生成 `shots/r00_contact.png`（R6，由 capture.mjs 的 contact 子命令生成）。
- `attach <W> <runId> <transcriptDir>`：写 `<W>/run.json`。transcriptDir 必须存在，否则报错。
- 导出给测试和 capture.mjs 用的函数：`loadCore(path)`、`loadInjected(workflowJsPath)`（截取 INJECT 段并求值）、`buildWorkflowSource(templateSrc, injected)`（init 与测试外壳共用）、`findJournal(W, opts)`、`parseJournal(text)`。
- `status <W> [--journal <path>]`：找到 journal（见下；进行中时优先读原始 journal，因为它比本地副本新），以「进行中」模式回放，打印当前轮与阶段、开着的确证 must（id、角度、标题、所在态）、取证缺口、子项状态、各轮一行走势、全部 toMain 留言、overrideErrors，已结束的话还有出口。
- `export <W> [--journal <path>]`：先把原始 journal 复制成 `<W>/journal.jsonl`，把运行记录 `<会话目录>/workflows/<runId>.json` 复制成 `<W>/run-record.json`（会话目录 = transcriptDir 往上三级，以实测为准；找不到就跳过并提示）。再用本地副本以「结束」模式回放，写出 ledger.json（完整 S，加上 `meta:{runtag, runId, exitReason, agentsUsed}`）、SUMMARY.md、`reviews/round_NN/<lens>.json`、`rounds/round_NN/{impl,verify}.json`，最后打印 SUMMARY 的路径。
- **找 journal**（回应 J1、J2，lead 实测：目录会随会话 slug、会话 id 变化）：
  1. `--journal` 优先。
  2. 其次是 `<W>/run.json` 的 `transcriptDir/journal.jsonl`。
  3. 再其次，在 `~/.claude/projects` 下递归找 `<runId>/journal.jsonl`，不写死目录层级。
  4. 最后按内容兜底：递归找所有 `workflows/*/journal.jsonl`，挑出含有 `"<W>/shots/` 字样的（verify 结果里的 manifest 路径带它）。唯一就用它，并补写 run.json；有多份则列出来报错。
  5. 原始文件都找不到时，用本地副本 `<W>/journal.jsonl`，并提示它可能缺最后一轮。
  - **解析**：逐行 JSON。最后一行写了一半时跳过（J4）。`type:'started'` 记下 key→label 与开始顺序；`type:'result'` 记下 label→result（result 是字符串时尝试 JSON.parse）；launched 和其他不认识的 type 忽略。一个 started、result 都没解析出来时，大声报错，报出第一行原文，并指引去看 run-record.json 的 logs（J3）。
- **`replay(cfg, seed, view, mode)`**（CORE）：`view = { results: {label: result}, started: [按开始顺序的 label] }`；mode 取 `'live'` 或 `'end'`；返回 `{ S, stage, agentsUsed }`，S.exit 已填好，stage 是进行中时的提示，例如「r03 评审中：ux、func 已交回」。流程：
  - `initState(cfg, seed)`，seed 取自 workflow.js 的 INJECT 段。
  - 对 round = S.round+1, … 循环：impl 和 verify 都没开始过就停。
  - 缺结果的处理：「进行中」模式下，已开始但没结果的视为进行中，停在这里并报告阶段。「结束」模式下视为 null。另外，只要更靠后的 label 已经开始，前面缺结果的一律视为 null（agent 失败时 journal 可能不写 result）。
  - 之后按 SHELL 同样的顺序调用 applyImpl、reduceRound。
  - 结束模式下若没有出口，依次判断：
    - 本 run 的轮数等于 maxRounds → 'max-rounds'；
    - `maxAgents` 不为 null 且「已开始的 label 数 + 2 + lenses 数」大于 maxAgents → 'budget'；
    - 否则 → 'interrupted'。这是回放专用的出口名，涵盖运行时预算、错误或被手动停止，此时 SUMMARY 提示看 Workflow 的返回值。
  - agentsUsed 取已开始的 label 数。

### 2.11 prompt 上下文预算与 token 估算

**共用约束段 `COMMON`**（拼在每个 prompt 末尾，回应清单第 3、24 条与 K12）：

> 【通用约束】全部输出用中文（字段值、标题、说明）。不要用 SendMessage 或 ListAgents，也不要等任何回复；需要主会话处理的事（参数错、截图配方错、缺权限）写进返回的 toMain 字段，然后继续本职工作。不写报告或总结类文件，结果只通过结构化返回交回。不做 git commit / stash / checkout / reset / clean。

**implementer prompt**（各段按以下顺序；正文由 implementer 照这个要点写）：
1. 角色：改进正在运行的应用，改的是已有代码。
2. 第一步，跑 intake 命令（附 done 列表），hint 的优先级最高；把 overrides 原样填进返回值。
3. GOAL 原文。
4. 子项表，每行：id、desc、负责角度、关联的态、上一个可评审轮的状态和证据（证据 ≤200 字）。
5. refs 摘要（role 分三档的说明保留，压成 3 行）。
6. 「必须处理」：开着的确证 must，按所在态分组，wf 条目放最前。每条写 id、负责角度、标题、detail（≤800 字）、evidence（≤400 字）、files，以及最近 3 次 attempts 加一句「上轮评审仍判存在」。
7. 「待人工取证」与「方向题（等用户决定，不要自行实现）」：只列标题。
8. 「可选（nice）」：只列标题，最多 20 条。
9. 「最近两轮修好的（不要改回去）」：只列标题。
10. 规则：
    - 先读相关代码，确认现状；
    - 试过、评审仍判存在的做法不要原样重试，要重试就在 summary 里写明这次有什么不同；
    - 不改 statesPath 指向的文件、rubric 和 args.json，配方有问题写进 toMain；
    - kind 按实际改动填，prompt 只列出本 run 支持的档：没有 restartCmd 就不能填 backend，没有 refreshDataCmd 就不能填 data。
11. 自查：`node <skillDir>/capture.mjs shoot --workdir <W> --round <N> --only <态…> --out <W>/scratch/impl-rNN`，不要自己写截图脚本。
12. 列出 `<workdir>/rubric.md`（冻结件）和 principles 的路径。
13. COMMON。

原型模式（mode=prototype）的 implementer prompt 另加一段（T1、T2、T3）：
- 方案层 = schemeFiles 里的字段与计算，加上 rubric 术语表里的词（附词表）。
- 方案层的 must 如果 rubric「已定决定」里没有现成答案，**不要改**，在 deferred 里挂起，写清选项、各自代价和推荐。
- 界面层（其余一切）照常改。
- 补充演示数据、改动 schemeFiles 时，同一轮里同步更新 contractPath 的后端要求清单，每个新字段都要写进去。
- 负责角度已同意挂起（agreed）的条目，列在「等你拍板」一节，不要动它们。只是提议过（proposed）、还没被同意的，仍在「必须处理」里；被否决的条目，照常修。

上一轮被退回的情况由 wf-regress 条目表达，放在「必须处理」最前面，detail 里有 smoke 报错末尾和 `snap/rNN.rejected.diff` 的路径。prompt 要求 implementer 先读这份 diff，再决定怎么重做。

预估 6k～12k 字符，与现在相当；去掉了 reviews 文件、impl.md、decision_log 这些「去读某文件」的指令。

**verify prompt**：命令（上一轮评审过、且本轮没有应用任何 override 时，由 CORE 加上 `--no-change-hint`）、kind 说明（data 的 .md 刷新流程）、「Bash 的 timeout 设 600000」、「只跑这一条命令，不要读截图、不要做别的检查」、「把最后一行 JSON 原样放进 result，不要改动任何字符」、COMMON。约 1k 字符。理想情况是 2 次模型调用：一次发命令，一次交回结果。lead 实测：每次调用工具都要把整段上下文再读一遍。

**评审 prompt**：
1. 角色说明：
   - 内置角度压缩成 3～6 行，保留现在 ux、func、code、rival、razor、newbie 的核心判法；去掉 verdict 和收敛规则的说明，加上读图范围。
   - newbie 补一项检查（T6）：同一概念在两处叫法不同，或同一个词在两处意思不同，都记 must。
   - flow（模拟用户走流程，原型模式默认）：按 rubric「角度 flow」专节列出的状态顺序，把截图当成一次连贯操作来判。每一步下一步该做什么是否看得出、前后状态是否衔接、走完能不能完成专节写的任务。你不能点击；专节没排出来的步骤，记 unverifiable，requiredStates 写缺的那个态。
   - contract（后端要求一致性，原型模式默认）：读 `cfg.contractPath`、schemeFiles，以及 `wl.mjs diff <W> --round N -- <schemeFiles 和 contractPath>`。**must 只有三类**：
     ① 本轮改了方案文件，清单没跟上；
     ② 清单里有、代码里没有，或代码里有、清单里没有的字段或计算；
     ③ 本轮改变了方案层的含义或计算，而这项改动不在 rubric「已定决定」里（implementer 退回或挂起都修得了）。
     「后端可能拿不到」「这样算是否合理」一律写进 directions，不记 must（T4）。
     contract 也能看本轮 diff（同 code），但看不到 implementer 的 summary。
   - 非内置角度统一写：「你是『<名>』评审角度。看哪些状态、判什么、什么算 must，完全按 `<workdir>/rubric.md` 里『角度 <名>』专节；专节要你按顺序看一串状态时，就按截图清单里的顺序把它们当作一次连贯的操作流程来判，你自己不能点击（第 27 条）。」
2. 零浏览器；你是只读的，不要创建任何文件。看不清就读 manifest 里该态的局部图，局部图也不够时记 unverifiable，requiredStates 写「<态>__需要局部图」。一次并行读多张图。
3. GOAL 原文。
4. 本角度负责的子项：id、desc、measurable、关联的态（没有就写「本角度不负责子项，subgoals 交空数组」）。
5. refs 指引（按角度，压成 2～4 行）。
6. 证据：本轮 manifest 的路径、r00 manifest 的路径；code 和 contract 另给看 diff 的命令 `node <skillDir>/wl.mjs diff <W> --round N`；**只有 code** 另给本轮 implementer 的 summary（≤1500 字）和改动文件。其他角度一律看不到 implementer 的自述，免得被「已修好 X」锚定（回应 R3，属于 (b) 类的评审独立）；本轮失败的态及原因（「这些态没有截图，不要猜」）；开跑前就有的报错不算本次的问题。
7. 「你名下待复核的问题」：开着条目的全字段（原型模式下，带提议的条目附上提议的标题、选项和理由，并说明：同意它要用户拍板就回 decision，不同意就照常回 present），detail ≤400 字，evidence ≤300 字，**必须逐条在 known 里表态**。
8. 非 newbie 才给：
   - 其他角度开着的问题，每条一行，写 id、标题、所在态（同一件事用 matchesIssueId 引用，不另立，也不替它表态）；
   - 已修好的问题，每条一行，最多 40 条（复现了就用 matchesIssueId 引用它来报）；
   - 方向题标题（不要重复提）。
9. 判法：
   - 绝对标准、must 与 nice 的定义（引 principles §0）；超出范围的不当 must；不提替代方案；正面结论不写进 issues。
   - 子项的 evidence 必须是本轮可以定位的证据：截图文件名加看到了什么、探针的键和值、报错原文、diff 里的文件和函数。
   - **根因在截图配方或缺少某个状态的问题，一律 unverifiable:true，并在 requiredStates 写出需要哪个态（可以是清单里还没有的新态名）。点名的态如果本轮已经截成功，会被按确证问题处理。**
   - 需要用户拍板的取舍写进 directions（写明选项、各自代价、推荐），不进 issues。
   - detail 不超过 6 行，evidence 不超过 3 行。
10. razor 额外：本 run 起点计数还没有时（prompt 会注明），先按 rubric 的数法数 r00 起点图，填进 counts.baseline；每轮都要填 counts.now，并和起点对照。
11. 列出 `<workdir>/rubric.md` 和 principles 的路径（第一步读 rubric），并注明：标准在本 run 内冻结，有异议写进 toMain 或 directions，不要自行放宽或加码。
12. COMMON。

预估 run A 第 3 轮那种规模下，prompt 约 1 万～1.5 万字符；当时实测约 7.9 万字符，其中 verified 约 3.9 万、全量 issues 约 3 万。

**token 估算**（依据：本次按消息 id 去重，统计了 run A、B 每个 agent 的 usage，原始数据见 §6 附表；都是估计，**待真跑验证**）：

| 项 | run B 实测（每个评审轮，6 个角度） | 新设计（估计） | 依据 |
|---|---|---|---|
| agent 数 | 12～14 | 8 | 去掉 read-state、smoke、refresh、capture、read-impl-stuck、persist；每个 agent 光启动就要写约 5.5 万 token 的缓存（实测每个机械 agent 的 newin 在 5.5 万～6 万之间） |
| 评审输出 | 6 × 3.8 万～6.9 万 ≈ 30 万 | 约 20 万～23 万（降 25%～35%） | 每个评审要表态的条目从约 53 条降到自己名下的 5～10 条；子项只判自己负责的；prompt 从约 7.9 万字符降到约 1.3 万；局部图预先截好，替掉一部分「裁图再读图」的轮次（run B 的评审共跑了 94 次裁图命令、读了 231 张自裁图）；code 默认不读图 |
| implementer 输出 | 5.4 万～8.8 万 | 降约 10%～20% | 自查改用截图器，不用再写截图脚本（run B impl-r01 跑了 15 次截图脚本、裁图 9 次） |
| persist | 2.5 万～4.8 万（run A 最高 7.3 万） | 0 | journal 加 export |
| smoke + refresh + capture + read-* | 约 1 万 | verify 约 1k～2k | 一条命令，原样转交结果 |
| 每轮合计输出 | 约 43 万 | 约 29 万～32 万（降约 28%～32%） | |
| 起步上下文与反复重读 | 每个 agent 起步约 5.6 万 | verify 用 Explore，约 2.1 万；评审暂用默认类型，以后对照实验通过再切 | 评审平均 30～60 次工具调用，每次少重读约 3.5 万，单个评审就少读约 100 万～200 万缓存 token（run B 每个评审的缓存读取在 420 万～990 万之间） |
| 每个 run 的固定开销 | setup 4 个 agent、finalize 3.2 万～3.9 万输出、paused agent | setup 0 个（续跑也是 0 个）、finalize 0 | init 和 export 在 node 里做 |
| 主会话 | 每次启动粘贴脚本全文（约 2.5 万输出） | 0（scriptPath） | 待 L1 确认 |
| 墙钟（每轮） | persist 2.3～6.4 分钟，smoke + refresh + capture 2～3 分钟 | verify 约 1.5～2 分钟（21 个态），没有 persist | 评审轮次少了，评审墙钟预计也会缩短 |

缓存读取（两次 run 共 1.3 亿～1.5 亿 token，其中评审约占 66%）大致随评审的对话轮次同比例下降，预计降 20%～30%。

### 2.12 结束交接

- **顶层 return**：`finalReturn(cfg, S, used)` 返回 `{ exitReason, exitDetail, rounds: S.round, runFirstRound, agentsUsed, workdir, next: "node <skillDir>/wl.mjs export <workdir>", ledger: compactLedger(S) }`。compactLedger 只保留条目的 id、lens、severity、status、unverifiable、title、state，以及各子项状态、方向题标题、各轮一行记录，约 2k～4k token。用意是 journal 万一读不到时，主会话手里至少还有一份可用的骨架，又不至于把完整台账灌进主会话上下文。
- **为什么权威台账不走顶层 return**（L1 实测 return 合法，回应 skeptic 的建议 1）：
  - 返回值会整个进入主会话上下文。完整台账含 detail 和 evidence，约 1.5 万～5 万 token。
  - 主会话要把它落盘，就得再输出一遍，这正是本次要消灭的「LLM 抄 JSON」。
  - journal 里已经逐条记下了每个 agent 的原始返回，用同一份 CORE 回放就能零抄写地重建，D25 测试保证回放结果与运行时一致。
  - 所以 journal 是落盘的权威来源，返回值里的 compactLedger 只作为兜底和即时概览。
- **退路**：journal 若读不到（格式变了或找不到），wl.mjs 会大声报错，不会静默产出空台账。这时用 `wl.mjs export --from-ledger <文件>`，从 compactLedger 渲染一份简版 SUMMARY：主会话把返回值里的 ledger 写进文件，再跑这条命令。
- **`renderSummary(cfg, S, info)`** 的章节，按顺序：
  1. 标题、结论（出口的白话说法和枚举值）、轮数、agent 数；
  2. 「需要你做的事」，按出口给出：
     - 第一条固定写工作区现在的状态：「最后一轮 smoke 是绿 / 红 / 未跑；最近一次绿是 rK」。只要出口不是 converged 或 evidence-gap，或者最后一轮不是绿的，就紧接着给出已算好路径的 `wl.mjs restore <W> --to green --dry-run` 命令（回应 R5）。
     - 然后是：evidence-gap 时列出要补的态；decision-gap 时列出等你拍板的方向题（挂起的条目逐条对应）；stalled 时列出卡住的条目和它们的 attempts；blocked 时列出原因；方向题有几个。
  3. 子项表（子项、负责角度、状态、最近证据）；
  4. 还开着的确证 must，按所在态分组；
  5. 待人工取证（含 requiredStates）；
  6. 方向题全文；
  7. 可选改进（nice）；
  8. 评审分歧（dissent、disputed）；
  9. 每轮走势表（轮、kind、smoke、截图成功数/总数、是否评审、修好、新增、重开、开着的确证 must、子项达成数、streak）；
  10. 本 run 改动的文件（来自快照）；
  11. 给主会话的留言；
  12. 台账修正与异常（overrideErrors、badMatch、untabled、untabledSubgoals、unverifiableRejected、goneIgnored、metDowngraded、kindAdjusted、malformed）；
  13. 截图对照（各态的 r00 与最后一轮路径）；
  13b. 仅原型模式：后端要求清单的路径，以及本 run 对它的改动（`wl.mjs diff <W> --run -- <contractPath>`）；「方案受影响的地方」，即动过方案文件的轮次、对应的挂起条目和方向题。方案文档本身由主会话经用户同意后再改，SUMMARY 只列出来；
  14. 怎么续跑（命令模板），以及怎么人工退回：最近一次 smoke 绿是哪一轮，对应的 `wl.mjs restore … --to green --dry-run` 命令。

### 2.13 删除清单（模板中整块删除）

- 删除的 agent：cleanup-old-runs、pw-selfcheck、preflight、write-goal、read-state、smoke、rollback（回滚改由 wl.mjs verify 完成）、refresh、capture、capture-fallback、read-impl-stuck、persist、paused、paused-escape、meta-agent、decision-log、finalize。
- 删除的选项：所有 `model:"opus"` 和 `model:"sonnet"`。
- 删除的结构：verifiedLog、subgoalCoverage、lastShotErrors 与 captureMemo、lensView、stalePrimer、dedupBlock、refsReadInstr（压缩后并进角色说明）、ADVERSARIAL_LENS_BRIEF（同上）、META_AGENT_SCHEMA、oscillating、treadmill、missingStates、pausedReason、P1_TRIGGER_STREAK、coveredSubgoalsUnchangedRounds、gitDiffSmallRounds、safeInsert、safeBlock、CHROME_LAUNCH、MANIFEST_SHAPE、CAPTURE_ERR_RULE（规则改由 capture.mjs 执行）。
- 删除的 args：states、captureBackend、scanSubset、shotsDir（改为固定的 `<workdir>/shots`）。
- 删除的评审字段：lens、verdict、mustFixOpen、goalEcho、coveredSubgoalIds、verified、knownIssuesStatus（改名为 known，语义也换了）、rootCauseHypothesis、nextStepPlan、suggestedFix、affectedFiles（改名为 files）。
- 删除的 implementer 字段与产物：reviewer_stuck、planRepetition、mdSnippet、impl.md。

### 2.14 文档同步要点（交给 docs，设计定稿后写）

- **description**（替换原文；人话部分不得再换回内部词）：
  > 自动多轮迭代改进一个正在运行、有浏览器界面的应用：功能逻辑、交互、布局、文案都能改。每轮改完自动截图，由几个不同角度的评审（界面、功能、代码，可加独立复核、新手第一眼、砍多余元素）对照验收标准打分，直到达标。用户说「自动迭代改进 / 打磨 XX 工具或界面」「从多个角度评审并自动改」「loop 优化」「反复改到满意」时使用。页面上看不到结果的问题（后端算得对不对、性能）不归它管。
- **SKILL.md** 要改的地方：
  - 「何时用 / 不用」补一句：结果不落到页面上的逻辑，不适合用它判断。
  - 核心机制：
    - 回归 gate 改为「快照回滚 + 复跑区分环境故障」（§2.9）；
    - 收敛判据改为 §2.7；
    - 验收标准开跑时冻结（第 26 条）；
    - 补一段「为什么流程骨架固定」：动态只在开跑前，开跑后只有受控改口通道。
  - args 表改为 §2.2。
  - 智能入口层：
    - 子项要写 `lenses`；
    - 配方按 §2.9 的结构化格式写，禁止 `||` 兜底，探针要记录目标，能断言的写 expect，小字区域声明 crops；
    - 新增「起草验收标准」一步，照第 26 条的来源、结构和摘要确认来写；
    - 新增「选评审角度」一步：app 模式默认 ux、func、code，原型模式默认 newbie、razor、flow、contract，用户可以增减；
    - 新增「自定义评审角度」专节写法：看哪些状态、判什么、什么算 must、对哪些子项负责，并附一个「模拟用户走完整个流程」角度的样例（第 27 条）。
  - 「生成并运行」改为 §2.3 的四步（init → 看 r00 → scriptPath 启动）。
  - 「监控与收尾」写 status、export，以及主会话负责用白话汇报。
  - 「中途纠错与续跑」改为 §2.8。
  - 「出口」一节改为 §2.7 的表。
  - 删掉「三条机检判据」「续修协议」「P1 meta-agent」三节。
  - 「implementer = opus」改为只陈述现行做法。
  - 红线：
    - 主会话不得 SendMessage 回复 workflow 子代理，不得在 run 期间改代码；
    - 只接受 async_launched；
    - 评审零浏览器；
    - kill 精确；
    - 不设 isolation；
    - `.claude/web-loop/` 必须被忽略（init 会检查）；
    - refs 由主会话持久化。
  - 删掉指向已不存在文档的出处：06-03、06-19、各处「P0 §」。
  - **原型模式**一节（第 28 条，§2.15）：
    - 怎么判断模式（没有后端的静态页，或用户说明是原型），并写进给用户点头的摘要；
    - schemeFiles、contractPath 怎么填；
    - 配方要排进空、很多、互相矛盾等边界数据的状态；
    - 默认角度和 maxRounds；
    - 「短跑 + 拍板 + 再跑」：decision-gap 结束后，主会话把用户的拍板写进下一次 rubric 的「已定决定」，再带着 continueFrom 起下一次。
  - **rubric 必须自包含**（U2）：评审用 Explore 类型，不注入 CLAUDE.md 和用户级 rules，所以界面文字规范、词表里评审要用到的条文都要原文收进 rubric.md，不能写「按 CLAUDE.md」。
  - 配方里小字区域必须声明 crops，评审不能自己裁图。
  - 单次 verify 必须在 10 分钟内完成（smoke、刷新、截图合计）。
  - allowlist 提示：`node .claude/skills/web-loop/*` 以及 smoke、restart 用到的命令。
- **principles.md**：
  - §0.3 的 disposition 改为「由台账推导，评审不申报」；
  - §0.8、§0.9 去掉 verified 数组，改为「正面结论不进 issues，子项达成写在 subgoals 里」，并加上 unverifiable 必须点名 requiredStates；
  - 轴⑤的注释改为「smoke 红时按快照退回本轮改动、本轮不评审」；
  - 「评分轴 ↔ lens」表说明这是默认归属，子项的实际负责角度以 args 为准。
- **examples/path2.md**、`.web-loop-refresh.md`：按清单末节重写；states 示例改为结构化格式；再补一个「静态页 + node smoke」的示例。

---

### 2.15 原型模式汇总（第 28 条，骨架不变）

| 项 | app（默认） | prototype |
|---|---|---|
| 何时用 | 有后端、有真实数据的应用 | 界面先行、后端没开发，原型背后的模拟逻辑和演示数据就是方案；主会话判断后写进点头摘要（T5） |
| 默认角度 | ux、func、code | newbie、razor、flow、contract |
| 默认 maxRounds | 5 | 3（短跑 + 拍板 + 再跑） |
| 产出 | 改好的界面 | 改好的界面、后端要求清单（contractPath）、方向题与「方案受影响的地方」 |
| implementer 能改什么 | 一切 | 界面层照常改；方案层（schemeFiles 的字段与计算、术语表里的词）没有已定决定时只能挂起（deferred） |
| 挂起怎么防滥用 | 不启用，全部拒收 | 两道关（X1）：① 前置筛选，条目的 files 落在 schemeFiles 上，或者标题和描述里出现术语表的词；② 该条目的负责角度当轮表态同意（known 回 decision）。只有同意后才扣出确证 must、才算进展。真正的方案层问题当轮就能同意，decision-gap 仍可当轮收尾 |
| 谁核对方案层没被偷偷改 | — | contract 角度：读本轮 diff 里的 schemeFiles 和清单 |
| 额外出口 | — | decision-gap |
| 回滚 | 快照回滚 | 同左；清单不在 workdir、不被忽略，所以随代码一起退回（T3） |

实现上只多出这些：mode、schemeFiles、contractPath 三个 args；derived.terms；IMPL_SCHEMA.deferred；Issue.needsDecision；出口 b2；verify 结果里的 schemeTouched；flow 和 contract 两段内置角色说明；init 的 4b 步；SUMMARY 的 13b 节。

### 2.16 实施中的澄清（implementer 提出，architect 确认）

除了正文已同步改写的几处，还有：
- **impl 调用抛错**（预算耗尽）：SHELL 直接 break，不归并该轮，以 budget 结束。replay 在 end 模式下遇到「verify 从没开始」的轮就停，两边一致。verify 或评审抛错时照常归并本轮，下一轮开头以 budget 结束。
- **复跑变绿后的 lastGreenRound**：smoke 被退回后复跑变绿，S.lastGreenRound 也记为本轮（这时 green.tree 已是退回后的树），SUMMARY 的恢复命令与之一致。

**实施审查（`review_impl.md`）之后新增的行为**。代码为准，正文相应小节以这里为补充：

| # | 行为 | 落在哪 | 为什么（审查编号） |
|---|---|---|---|
| 1 | **verify 拆成前台与 worker**：前台 detached 起 `wl.mjs verify … --worker` 干真活。worker 把完整结果写进 `snap/rNN.verify.json`，把短结果行写进 `snap/rNN.verify.out`，最后删锁 `rNN.verify.lock`；日志写 `rNN.verify.log`。前台最多等约 9 分钟，等到就打印短行；没等到就打印 `{"pending":true,"round":N}` 并以 0 退出，之后用 `wl.mjs wait <W> --round N` 接着等（同样最多约 9 分钟）。同一轮已经有结果或 worker 还活着时，不会再起第二个 worker，否则重跑会拿已退回的工作区重拍快照，把 pre 树搞乱。verify prompt 写明：拿到带 sig 的那行之前不要交回。 | `wl.mjs` cmdVerify、cmdWait、awaitVerify；模板 verifyPrompt | I1：红的路径最多跑三遍 smoke 再加重启和截图，会超过 Bash 的 10 分钟上限，被杀在回滚中途 |
| 2 | **intake 先等上一轮的 worker**：最多等约 100 秒（落在 Bash 默认 2 分钟以内）。没等完就在输出里给出 `verifyRunning`；implementer prompt 写明这时要再跑一次 intake，不能先动代码。 | `wl.mjs` cmdIntake；模板 implPrompt | I1 的连带问题，以及 M2（intake 不必要求加长 timeout） |
| 3 | **截图这一步失败最多再试 2 次**：间隔 300 毫秒；超时类错误不重试，因为多半是元素不可见，重试只会白等。重试次数记进 manifest 的 `shotRetries`。包住的有整页图、crop（locator 与 clip）、失败态留证图、总览图；步骤、探针、expect 的失败不经过它。 | `capture.mjs` withShotRetry | I2：Chrome 偶发「Unable to capture screenshot」，没有重试时会误报配方错误，或制造假进展 |
| 4 | **`S.forceDataRefresh`**：用 .md 说明文件刷新数据的那一轮如果被退回，下一轮强制按 data 档刷新；刷新成功后清除。 | 模板 applyImpl、reduceRound | I4：被退回轮次的数据是用被拒的代码生成的 |
| 5 | **按内容认 journal 时只读文件开头 256 KB**：verify-r01 的结果行在 journal 很靠前的位置，够用。 | `wl.mjs` journalsByContent | I5：避免每轮整读 24 小时内的全部 journal |
| 6 | **app 模式不能用 contract 角度**，validateArgs 报错。**restore 增加 `--to before-restore`**：每次 restore 前先拍当前树，写进 `snap/before-restore.tree`，用来撤销这次退回。**`export --from-ledger <文件>`**：journal 读不到时，用 Workflow 返回值里的 compactLedger 渲染简版 SUMMARY（§2.12 的退路，现已实现）。 | 模板 validateArgs；`wl.mjs` cmdRestore、cmdExport | 防误用；人工退回要能撤销；兜底路径 |
| V1（L4） | **verify 的结果改为原样转交文本**：VERIFY_SCHEMA.result 改为字符串，内容就是 `wl.mjs verify` 最后那一行。CORE 用 verifyLine 取出并解析，兜底也认已解析的对象和包了一层的对象。签名按解析出的对象核对；结果行里的 round 与本轮不同时，按签名不符处理。 | 模板 VERIFY_SCHEMA、verifyLine、normalizeVerify、reviewGate；verify prompt | L4 实测：schema 要求 object 时，verify agent 交回的形状有歧义，被判成「verify 未交回」，r01 没有评审。让 LLM 原样抄一行文本，比抄成对象更不容易走样 |
| V2（L4） | **init 认术语表和角度专节的标题时放宽**：2～4 个 #，前面可以带编号（「## 7. 术语表」「### 5.1 角度 flow」）。 | `wl.mjs` hasLensSection、glossaryTerms、flow 专节查找 | L4 实测：原先要求标题一字不差，rubric 标题带编号或层级不同时，init 认不出术语表或专节 |

## 3. 测试计划（tester）

外壳 `tests/dryrun.mjs`：读模板全文，把 `export const meta` 换成 `const meta`，INJECT 段替换成 `const INJECTED = {v:1, args:<场景 args>, seed:<场景 seed 或 null>};`（与 init 生成 workflow.js 的做法相同，最好直接调用 wl.mjs 导出的同一个生成函数 `buildWorkflowSource(templateSrc, injected)`），再包进 `new AsyncFunction('agent','parallel','phase','log','args','budget', body)` 执行，拿到返回值；运行时 args 传 undefined。`agent` 记录每次调用的 `{label, prompt, opts}`，按 `respond(label, prompt, calls)` 返回结果；respond 返回 `THROW` 时模拟抛错。`parallel` 按真语义实现：某个 thunk 抛错时该位置为 null，整体不抛（回应 K25）。CORE 用 `wl.mjs` 的 `loadCore` 加载，直接做单元测试。另提供 `fakeVerify({okStates, failedStates, …})` 辅助函数，按 §2.5 的短结果形状生成带正确 sig 的 verify 结果。

| # | 场景（输入） | 断言 | 对应判据 |
|---|---|---|---|
| D1 | T1 真停滞：ux 每轮都把 r1 那 2 条报为 present，子项一直 unmet；staleRounds=2 | 第 3 轮以 `stalled` 结束（r1 只作起点） | §2.7 stalled |
| D2 | T2 稳步推进：ux 第 1 轮报 5 条，之后每轮 gone 1 条、不新增 | 不会出现 stalled；最后一条 gone 且子项 met 的那一轮 `converged` | stalled 放过 |
| D3 | 6 个角度，code 从不报 must，其余角度每轮都修好 1 条 | 跑满之前不出现 stalled 或 blocked | 回应第 10 条 |
| D4 | S7：capture 每轮 okStates 都为空 | 第 2 轮以 `blocked` 结束；评审一次都没派；SUMMARY 写明两轮跳过的原因 | blocked |
| D5 | implementer 返回 null | verify 的 prompt 里 kind 取上一轮的值（第一轮取 frontend）；本轮照常评审；轮次记录里 implOk=false；不新增 must | 第 2、13 条 |
| D6 | U1：唯一一条 must 被标为 unverifiable，requiredStates 点名一个不在 okStates 里的态，子项都 met | 以 `evidence-gap` 结束，不是 converged | 第 12 条、出口 b |
| D6b | 同上，但 requiredStates 点名的态本轮已截成功 | 按确证处理；unverifiableRejected 有记录；不会以 evidence-gap 结束 | K4 |
| D7 | U2：评审只报 nice，子项都 met | `converged` | 出口 a |
| D8 | S4：matchesIssueId 写成不存在的 id | 按新条目入账；badMatch 有记录 | 第 17 条 |
| D9 | 一个角度连续两个可评审轮都返回 null | `blocked`，detail 写明是哪个角度 | K7 |
| D10 | S6：只有 ux，第 1 轮 verify 返回 rolledBack，第 2 轮全部通过、子项 met | 第 1 轮不评审，立 wf-regress；第 2 轮 wf-regress 置为 fixed，且不计为进展；第 2 轮 `converged` | 第 16 条、第 1 条 |
| D10b | verify 返回 envBroken | 当轮以 `blocked` 结束，detail 写「环境或基线坏了」 | K1 |
| D10c | 连续两轮 rolledBack | 第 2 轮以 `blocked` 结束 | 第 1 条 |
| D11 | 负责角度 gone、其他角度同一轮 matches 该条 | 关闭；记一条 dissent；不重开 | K6 |
| D12 | 第 r 轮由负责角度修好；第 r+1 轮另一角度 matches → 重开（reopenedBy）；第 r+2 轮负责角度 gone → fixed 且 disputed；第 r+3 轮另一角度再 matches | r+1 重开；r+3 只记 dissent，状态仍是 fixed | 第 21 条、K6 |
| D13 | 负责角度自己 matches 一条已修好的条目 | 重开，regressions=1 | 回归通道（K2） |
| D14 | verify 的 failed 含态 X → 下一轮 X 截成功 | wf-state-X 先开后关；关闭那一轮 progress=true | 第 16、19 条 |
| D15 | newErrors 含态 Y | 立 wf-pageerror-Y 条目；之后 Y 截成功且不在 errorStates 里时关闭 | 第 20 条 |
| D16 | verify 的 sig 被篡改（改掉一个字符） | 照常评审；本轮不开关任何 wf 条目；sigOk=false | 签名采信 |
| D17 | impl 交回 override：waive 一个有效 id，外加一个无效 id | 有效的置为 waived，本轮评审的 prompt 里没有它；无效的进 overrideErrors；两个 key 都进 doneControl，下一轮 intake 的 --done 里包含它们 | 第 15 条 |
| D18 | impl 交回 attempts | 下一轮 impl 的 prompt 里出现该条目的 attempts，以及「上轮评审仍判存在」 | 第 13 条、外-5 |
| D19 | 6 个角度、maxAgents=20 | 第 2 轮后以 `budget` 结束（用掉 16 个，16+8>20） | 第 5 条 |
| D20 | 第 2 轮的 impl 抛错（模拟预算耗尽） | 以 `budget` 结束；不崩；有顶层返回值 | 第 5 条、K8 |
| D21 | reduceRound 收到形状异常的评审结果（issues 是字符串），或形状异常的 impl / verify 结果 | 不崩。CORE 的 `normalizeReview`、`normalizeImpl` 和 verify 结果校验把形状不对的返回一律当作 null：评审算缺席，并记进 rec.malformed | K8 |
| D22 | 续跑：INJECTED.seed 的 round=3，带 2 条开着的条目 | 第一个 label 就是 `impl-r04`（没有 seed agent）；impl 的 prompt 里有延续下来的条目；负责角度不在新 lenses 里的条目置为 waived | 第 15 条、K20、R4 |
| D23 | INJECTED.seed 的 v 不是 1 | 一个 agent 都没调就 throw，消息以 BLOCKED 开头 | R4 |
| D24 | INJECTED 为 null（模板没经 init 直接跑），或 args 无效 | 一个 agent 都没调就 throw | §2.2 |
| D25 | **回放一致**：任选几个场景跑完后，把 calls 转成假 journal（started 与 result 两种行）→ `replay` | 回放得到的 S 与 SHELL 最终的 S 深度相等，出口相同 | journal 方案的根基 |
| D26 | label、类型、effort | 每轮 label 依次是 impl、verify、各 review；**任何调用的 opts 里都没有 model**；verify 不带 agentType，effort 为 low；impl 不带 agentType；review 带 `agentType:'Explore'` | §2.4、外-6 |
| D28 | 冻结标准 | implementer 和评审的 prompt 都指向 `<workdir>/rubric.md`，不含 args.rubricPath 的原路径 | 第 26 条 |
| D29 | 自定义角度 `flow`（不是内置角度） | 评审 prompt 的角色说明是「按 rubric.md 里『角度 flow』专节」，并写明不能点击 | 第 27 条 |
| D31 | 子项声明的 states 本轮都截图失败，负责角度却给了 met | 降为 unverifiable，metDowngraded 有记录，当轮不会 converged | R2 |
| D32 | 条目所在的态本轮截图失败，负责角度却给了 gone | 不关闭，goneIgnored 有记录 | R2 |
| D36 | 原型模式：impl 挂起一条 files 落在 schemeFiles 上的确证 must，负责角度当轮对它回 decision；其余条目都 gone，子项 met | 该条目 needsDecision 先为 proposed、再为 agreed；新增方向题 dir-impl-…；负责角度的 prompt 里有提议内容，但没有 implementer 的 summary；当轮 `decision-gap` | T2、X1 |
| D37 | 原型模式下挂起一条与方案层无关的 must；app 模式下挂起任意条目；原型模式下挂起一条通过筛选的条目，但负责角度回 present | 三种都不生效，deferRejected 写明原因（第三种为「负责角度不同意」）；条目照常挡收敛；当轮不算进展 | T2、X1 |
| D40 | 提议的条目负责角度本轮缺席 | 保持 proposed，不扣、不算进展；下一轮负责角度回 decision 后才变 agreed | X1 |
| D38 | verify 的 sig 被篡改，其余条件都满足收敛 | 当轮不以 converged 结束（S1），下一轮签名正常即可收敛 | S1 |
| D39 | verify 返回 smoke.flaky:true（pass:true） | 照常评审；不立 wf-regress | S3 |
| D33 | verify 返回 noChange:true；接着下一轮也返回 noChange:true | 两轮都不派评审；staleRounds=2 时第 2 轮以 `stalled` 结束，不是 blocked（V4） | N1、V4 |
| D34 | verify 返回 envOk:false | 不派评审，当轮以 `blocked` 结束 | N3 |
| D35 | 负责角度交回的 subgoals 漏了一条自己负责的子项 | untabledSubgoals 有记录，该子项算 pending | N7 |
| D30 | 子项进展按历史最高计：第 1 轮 met 2 个，第 2 轮 1 个，第 3 轮 2 个，三轮都没有修好的条目 | 第 2、3 轮都不算进展；staleRounds=2 时第 3 轮 `stalled` | §2.7 |
| D27 | 模板能在 AsyncFunction 里编译通过；CORE 在空作用域里加载，不引用禁用的全局名 | 通过 | 第 0、11 条 |
| P1 | implementer prompt | 含 intake 命令和 done 列表、条目的 detail 与 evidence、COMMON（禁 SendMessage、要求中文、toMain、禁 git 写）、principles 路径、自查命令 | 第 3、14、24、25 条 |
| P2 | 评审 prompt | 含本轮 manifest 路径（rNN）、principles 路径、unverifiable 规则那句、wl.mjs diff 命令；newbie 的 prompt 里不含其他角度的标题和已修好的标题；只有 code 的 prompt 含 implementer 的 summary；只有 code 和 contract 含 diff 命令（R3）；任何评审的 prompt 里都没有「crops/」写入指令（U2）；评审 prompt 长度在已修好条目从 0 增到 100 时增幅有上限（截断到 40 条） | 第 4、21、22、25 条，K14 |
| P4 | 原型模式的 prompt | implementer 的 prompt 含方案层定义、术语表、「挂起写 deferred」、「改 schemeFiles 要同步清单」；contract 的 prompt 列出三类 must，并写明「后端可能拿不到」进 directions；newbie 的 prompt 含「同一概念两种叫法记 must」 | 第 28 条、T1、T4、T6 |
| P3 | 子项只交给负责角度 | 角度 X 的 prompt 只含 lenses 含 X 的子项；不负责子项的角度提示交空数组 | 第 12 条 |
| C1 | `capture.mjs` 的纯函数 | matchExpect 能做部分深比较、能读出嵌套路径、不符时报出路径；computeNewErrors 处理上一份缺失和上一份没有该态的情况，也能抓出「已有一条旧报错的态又冒出新的报错文本」（N2）；validateStates 能拒绝重名、未知 step 键、非法态名 | 第 19、20 条 |
| C2 | 截图器集成（本机能解析到 playwright 时才跑，否则跳过）：静态 HTML，三个态，分别是 ok、expect 不符、选择器找不到；再跑 contact | manifest 形状正确；okStates 与 failed 的原因文本正确；局部图文件存在；最后一行 JSON 可以解析；`rNN_contact.png` 存在 | 第 9、19、22 条，R6 |
| W1 | `wl.mjs intake`：临时目录放 2 个 hint 和 1 个 override 数组 | 打印的 key 正确；--done 能过滤；文件名不变 | K11 |
| W2 | `wl.mjs init` 的校验：args 缺字段、子项的负责角度不在 lenses 里、workdir 没被忽略（临时 git 仓库） | 以退出码 1 结束，错误信息正确 | §2.2、第 25 条 |
| W3 | init 的清理：构造 3 个旧 run 目录（含 shots） | 只有最新的那个旧 run 保留 shots；`.playwright-mcp` 不动 | 第 18 条 |
| W4 | 快照：临时 git 仓库，改一个已跟踪文件、新建一个未跟踪文件、删一个文件 | `verify` 的 snap.changed 三个都列出；真 index 和 `git stash list` 都没变；`wl.mjs diff` 输出对 | K9 |
| W4b | 回滚：临时仓库，开跑前已有一个脏文件 P；r1 改 A（smoke 绿）；r2 改 B、新建 C、删 D，同时「主会话」改了 statesPath 文件 X；smoke 命令在 B 被改时失败 | r2 结束后：A 保留 r1 的改动；B、D 恢复成 r1 结束时的样子；C 被删；P 保持脏的样子；X 保留主会话的修改；rejected.diff 存在；结果为 rolledBack:true | 第 1 条、K9 |
| W4c | 回滚后 smoke 仍红（smoke 命令恒为 false） | B、C、D 恢复到 r2 交回后的样子（改动被放回）；结果为 envBroken:true | K1 |
| W8 | init 检查角度专节：lenses 含 flow，rubric 没有「## 角度 flow」；再补上专节重跑 | 第一次以退出码 1 结束并点名 flow；第二次通过；`<W>/rubric.md` 已生成；rubric.md 已存在而内容不同时报错 | 第 26、27 条 |
| W5 | init 带 continueFrom：上次 workdir 里放一份 ledger.json | 生成的 workflow.js 的 INJECT 段可以解析，seed 等于 toSeed(ledger)（fixed 条目被压缩）；这个 workflow.js 能被 AsyncFunction 编译 | 第 15 条、R4 |
| W9 | 后端重启：临时起一个 node http 服务占 healthUrl 端口，restartCmd 起一个新的同端口服务 | verify 的 refreshOk 为 true，端口上的监听进程号变了，旧进程已退出；restartCmd 起不来（端口仍被旧进程占着、进程号不变）时 refreshOk 为 false | R1 |
| W10 | 找 journal：① run.json 指向的 journal；② 没有 run.json，但 ~/.claude/projects 下（测试里改用临时 HOME）有一份含 `"<W>/shots/` 字样的 journal；③ 有两份这样的 journal | ① 和 ② 都能找到，② 会补写 run.json；③ 报错并列出两份；verify 运行后 `<W>/journal.jsonl` 与原文件逐字节相同 | J1、J2 |
| W11 | kind=frontend，changed 里有 uiDir 之外的 .py，且配了 restartCmd | 按 backend 刷新，kindAdjusted 为 "backend" | N8 |
| W12 | init 的原型模式检查：contractPath 在 workdir 里，或被 .gitignore 忽略；rubric 缺「## 术语表」；flow 缺专节；以及全部正确 | 前三种以退出码 1 结束并指出问题；全部正确时 INJECTED.derived.terms 等于术语表里的词 | T3、第 27 条 |
| W13 | verify 的短结果与完整结果：smoke 输出里带引号、反斜杠、ANSI 颜色码 | 最后一行只含 §2.5 的短字段，能 JSON.parse；`snap/rNN.verify.json` 里有完整的 smoke 末尾 | S2 |
| W14 | journal 按内容认：临时 HOME 下放两份 journal，label 相同，只有一份含 `"<W>/shots/` | 认中的是那一份，不按 label 认 | U1 |
| W6 | journal 解析：读 run B 真实 journal（文件不存在就跳过）；再造一份最后一行只写了一半的 journal；再造一份全是不认识内容的 journal | 真实 journal 的 started 与 result 配对数正确，result 为字符串时能 parse；半行被跳过不报错；全不认识时报错，并带出第一行原文 | §2.10、J3、J4 |
| W7 | `export` 渲染：D2 跑完后经假 journal 导出 | SUMMARY 含 §2.12 的全部章节标题；converged 时没有「需要你做的事」里的阻塞项 | 第 11 条 |

现有测试的处置：凡是断言已删机制（P1、read-state、stuck、reviewer_stuck schema、mergeIssues 的 fieldflow、finalize-paused、reviewer prompt 的 rootcause 与 stuck 注入、implementer 的 opus 与 priority 文本等）的，一律删除。`test-skill-doc*`、`test-examples-path2` 改成断言新文档的关键句：description 原文、红线里「不得回复 workflow 子代理」、配方禁止 `||`。

---

## 4. 需要 lead 真跑确认的点（预算：几个 0～1 个代理的小实测 + 一次约 15 个代理的验收真跑）

**已由 lead 实测确认，设计已据此定稿**（三次探针：wf_a163e693-730、wf_6feba183-903、wf_5bd9fe37-d90，详见 `workflow_runtime_facts.md`）：
- scriptPath 能启动仓库里的脚本文件。
- 顶层 return 合法，返回值原样交回主会话。
- args 到达时是对象。
- 不写 model 时继承会话模型；`effort:'low'` 会被接受。
- journal 的格式与写入：
  - 依次是 launched、每个 agent 一条 started、一条 result；
  - 边跑边写；
  - 不记最终返回值，最终返回值在 `<会话目录>/workflows/<runId>.json`，resume 会覆盖这个文件；
  - 位置会随会话 slug、会话 id 变化。
- 子代理只有写 SUMMARY.md 会被拦。
- Explore 类型起步约 2.1 万 token，但仍有 SendMessage 和 playwright。
- nohup 或 setsid 起的服务在子代理结束后还活着，用 run_in_background 起的会跟着死；`$!` 拿到的是外层包装 shell 的进程号。
- 前台 shell 里的长 sleep 会被 Bash 工具拦下。

**全部实测点已有结论**，没有待回报的项。

**L3（0 个 agent，实施完成后由主会话跑）**：
1. 用 `node .claude/skills/web-loop/wl.mjs status <任意目录> --journal <wf_6feba183-903 的 journal>` 和 `export` 确认能解析真 journal。
2. 在验收用的 workdir 上跑一次 `wl.mjs init`，看报错，看 `r00_contact.png`。
3. Read 一下生成的 workflow.js 末尾和 INJECT 段，确认能被 AsyncFunction 编译（测试 W5 也测这一项）。

**L4（验收真跑，约 10 个代理）**：标注原型 mock_v4，**原型模式**，3 个评审角度（建议 newbie、flow、contract；schemeFiles 设为 data.js，contractPath 设在 mock_v4 旁边），`maxRounds: 2`，代理数 = 2 × (2 + 3) = 10。逐项核对：
1. init 通过，`r00_contact.png` 是想要的画面，`<W>/rubric.md` 已冻结。
2. 用 `Workflow({scriptPath})` 启动，不传 args；随即执行 attach。journal 里的 label 依次是 impl-r01、verify-r01、3 个 review-…-r01，r02 同样。
3. 两轮 verify 的 sig 都校验通过，Bash 没有超时；`<W>/journal.jsonl` 在第 1 轮 verify 之后就已存在。
4. run 中途 `wl.mjs status` 能看到第 1 轮的台账。
5. 结束后 `wl.mjs export` 写出 SUMMARY.md、ledger.json、run-record.json、`reviews/round_01|02/<lens>.json`，SUMMARY 各章节齐全，出口合理。
6. 按消息 id 去重，统计每个 agent 的输出 token 和缓存读取，和 §2.11、§6 附表的 run B 数据对照，写进 final_report。这是降幅估算的验证。
7. 评审 prompt 的字符数落在 §2.11 估计的范围内。
8. 任何 agent 都没调用过 SendMessage 或 ListAgents（看各子日志的 toolsUsed）。
9. 评审（Explore）的子日志 `message.model` 是会话模型。评审的工具调用次数、缓存读取，与 run B 同类评审对照。评审的发现（must 条数、有没有明显漏判）和 run B 同类角度的大体相当；如果明显变浅，就把 REVIEW_OPTS 改回 `{}`，写进 final_report。
10. 统计 verify 签名失配的次数（S5），以及有没有任何 agent 拒做（verify 改用默认类型后，不应再出现只读模式的冲突）。
11. 原型模式的几样产出都在：contract 文件随改动更新；如果有挂起的条目，SUMMARY 列出了「等你拍板」。

不需要再测的：
- resume 语义：设计不依赖它。
- 写文件拦截：子代理不写 SUMMARY.md。
- 自定义子代理类型：第 23 条不做。
- Explore 用的模型（lead 已实测为 claude-opus-5-5）、子代理能找到并复制 journal（lead 已实测；设计改为按内容认，见 U1）、前台跑 240 秒的命令（lead 已实测，正常完成）。
- detached 后端在子代理结束后能不能活：lead 已实测，node 的 `spawn(detached:true)` 加 `unref()` 等同于 setsid；端口和进程号相关的逻辑由 W9 在本地测。

---

## 5. 需要用户拍板的方向题（1 个，已决）

以下几件原本要问的事，已经有了结论：
- **回滚**：保留并改成确定性快照实现。这是团队的判断，依据是 lead 的分类建议，它延续现有行为（第 1 条）。
- **treadmill**：按用户的总原则删除。它没有拦下过任何失败，反而误停过一次（第 10 条）。
- **默认评审角度**：并入第 28 条（用户已同意）。只在原型模式里换成 newbie、razor、flow、contract，真实应用的默认 ux、func、code 不动，因为证据只覆盖原型场景。

**Q1. 结束总结：由程序按台账生成，白话解读由主会话在对话里给你（推荐） / 保留一个专门写总结的 agent。**
- **已决（用户 2026-10-29 拍板）：程序按台账生成 SUMMARY，白话解读由主会话在对话里讲。** 按 §2.12 实施，不派写总结的 agent。
- 这在决定：SUMMARY.md 是表格加原文的「台账报告」，还是一篇 AI 写的文章。
- 推荐程序生成：
  - 内容一字不差地来自台账，不会漏、不会编；
  - 每次 run 省掉约 3.5 万输出 token 和 3～5 分钟；
  - 子代理也不用再碰 SUMMARY.md 这个会被拦截的文件名，以前两次 run 的总结都因此没写成。
  - 读起来更像报表，所以白话的来龙去脉由主会话读完后在对话里讲给你。
- 保留总结 agent：读起来更顺，代价是上面那些都回来了。

---

## 6. 残留风险（实施后照实写进 final_report）

1. **export 和 status 依赖运行时的 journal 格式与位置**，这是内部约定，没有文档，位置已经变过一次。三层缓解（J1～J3）：
   - verify 每轮、export 收尾时各把原始 journal 复制进 workdir，格式以后变了，原始数据也还在；
   - 每轮 log() 一行紧凑记录（含本轮新增、修好、重开的 id），会完整保留在运行记录的 logs 里，export 时也复制进 workdir；
   - 顶层返回值带 compactLedger。
   解析只用 type、label、result 三个字段，失败时大声报错；用两份真实 journal 做回归测试（W6）。
2. **LLM 转交只剩 verify 结果一处**（args 和 seed 已经注入脚本），带签名；签名对不上时照常评审，但不按它开关 wf 条目。
3. **同一轮内跨角度的重复问题不合并**，第 1 轮的计数会偏高。新的停滞判据不看计数，所以不会因此误停；显示时按截图状态分组。
4. **单个 Bash 命令可能超时**：verify 一次（smoke 加 21 个态）可能要 1～3 分钟，prompt 里要求把 Bash timeout 设为 600000。workflow 自己的「agent 卡住」超时具体怎么判没有文档；截图器边跑边打印进度行，以免被当成卡住。
5. **评审 effort 没调**：没有证据表明调低不伤判断质量，暂时继承默认。等新设计真跑一次以后，可以拿一轮做对照实验。
6. 本文的 token 降幅都是估算，以第一次真跑的实测为准（§2.11 写了依据）。
7. **Explore 类型仍有 SendMessage、ListAgents 和 playwright 工具**（lead 实测），所以「不发消息、不碰浏览器」仍靠 prompt 加 toMain 出口。真正造成损失的是主会话的回复，已写进红线。如果 L4 里看到子代理违规，再考虑带工具白名单的自定义子代理类型。
8. **回滚管不到被 .gitignore 忽略的文件**：快照不收录它们。SKILL.md 写明这一点；implementer 不应改动被忽略的文件。
9. **评审改用 Explore 后的判断质量**只有模型一致这一条实测，没有质量对照。L4 拿 run B 同类角度对照，明显变浅就改回默认类型（一处常量）。
10. **原型模式的方案层判定是启发式的**：files 与 schemeFiles 有交集，或者标题和描述里出现术语表的词。漏判会让该挂起的条目照常挡收敛，最坏是 stalled；误判会让不该挂起的条目被挂起，最坏是提前以 decision-gap 结束。两种情况都能在 SUMMARY 里看到，由主会话复核。

### 附表：两次 run 每类 agent 的实测输出 token（按消息 id 去重）

| agent 类 | run A 合计（3 轮） | run B 合计（第 1、3 轮评审） | 单次范围 |
|---|---|---|---|
| review-rival | 23.9 万 | 13.6 万 | 6.6 万～9.3 万 |
| implementer | 23.6 万 | 20.2 万 | 4.8 万～10.5 万 |
| review-newbie | 19.0 万 | 12.6 万 | 5.2 万～7.3 万 |
| review-razor / code / func / ux | 13.3 万～14.9 万 | 7.8 万～9.7 万 | 3.6 万～6.0 万 |
| persist | 14.8 万 | 7.2 万 | 2.5 万～7.3 万 |
| finalize | 3.2 万 | 3.9 万 | — |
| capture | 2.2 万 | 1.4 万 | 0.6 万～0.8 万 |
| 其余机械 agent | 每个 0.03 万～0.5 万，但每个都要写约 5.5 万 token 的缓存 | 同左 | — |
