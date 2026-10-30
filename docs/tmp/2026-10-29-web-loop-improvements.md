# web-loop 改动清单（2026-10-29，待用户过目后实施）

> 本文中所有项目内路径均相对 repo root。代码位置一律给可 grep 的片段，不给行号。
> 这份清单还没批准，批准前不要动 skill 文件。
> 编号是条目身份，不代表顺序：第 0～12 条是第一版清单（第 0 条为第二版新增），第 13～25 条是第二版合并历史挖掘时新增的。实施顺序见「实施顺序」节。

## 证据来源

- **两次真实运行**（会话日志里只找到这两次；另一台机器 upc 没查）：
  - **run A**：`.claude/web-loop/2026-10-28_annotation-v4/`，6 个 lens，3 轮，42 个 agent，收敛。日志 JA = `~/.claude/projects/-home-yu-PycharmProjects-Trade-Strategy/9bb134d6-42d5-4581-8c95-d87a123c5ed5/subagents/workflows/wf_45f67683-d85/journal.jsonl`。
  - **run B**：`.claude/web-loop/2026-10-29_annotation-v5/`，6 个 lens，maxRounds 5、预算 65 个 agent，实际 3 轮、34 个 agent，第 3 轮被 treadmill 误报叫停（见第 10 条）。日志 JB = 同目录下 `wf_0859d62f-41e/journal.jsonl`。下文「JB 第 N 条」指该文件第 N 行（从 0 数）。
- **两份历史挖掘**（2026-10-29，均为只读，未改仓库）：
  - 运行历史挖掘：逐条核对两次 run 的日志、台账、运行目录。
  - 设计与代码对照审计：把 2026-06-21（决策层重设计）、2026-06-22（综合审计）两组设计文档和模板逐条对照，并用模拟外壳真跑模板控制流。这两组文档已在提交 `ce28f80` 删除，原文可用 `git show 94e2193:<路径>` 取回。06-03、06-04、06-12、06-19 几份设计文档在 git 历史里找不到，无法核对。
- **控制流模拟外壳**：`docs/tmp/2026-10-29-web-loop-harness/`。`harness.mjs` 注入假的 agent / parallel / phase / log，直接 import `.claude/skills/web-loop/workflow-template.js` 真跑；`scenarios*.mjs` 是审计用的场景（S1～S12、T1/T2、U1/U2），在当前模板上能复现本文多处问题。跑法：`cd` 到该目录后 `node scenarios3.mjs`；它会在本目录生成 `_tpl_N.mjs`，跑完删掉。

skill 文件：`.claude/skills/web-loop/`，包括 `SKILL.md`、`workflow-template.js`、`principles.md`、`examples/`、`tests/`。每条改动都要在 `tests/` 里补或改对应的测试；模板改完必须对裸顶层跑一次 `node --check`（第 11 条若引入顶层 `return`，此规矩要随之改，见该条）。

## 为什么这样排序

- **现在的模板跑不过第 3 轮**（第 10 条）。不先修它，后面所有改动在第 3 轮之后都用不上，maxRounds 和代理数上限也形同虚设。
- **现有测试测不出这些毛病**（第 0 条）：24 个测试里只有 `test-mergeissues-fieldflow` 和 `test-reviewer-prompt-adversarial` 真正执行代码，其余在源码里找字符串。下面好几处毛病，对应的测试照样全绿。所以先补能真跑控制流的外壳，其余各条的验收才有地方落。
- **会丢改动、白跑一轮或让结论失真的放 P0**；花费与中途纠错放 P1；准确性与文档放 P2。每条单独提交，方便回退。

## 实施顺序

- **P0**：0 → 10 → 13 → 14 → 12 → 2 → 1 → 3 → 11
- **P1**：15 → 7 → 19 → 9 → 4 → 6 → 16 → 17 → 18 → 20 → 5 → 26 → 27 → 28
- **P2**：8 → 21 → 22 → 23 → 24 → 25，最后同步文档（文末一节）

---

## P0：会让 run 提前停、白跑、丢改动或结论失真

### 0. 补一个真跑控制流的测试外壳

- **现象**：模板头注释写「tests/dryrun.mjs 场景全绿」，但这个文件不存在，git 历史里也从没有过。06-22 审计的 T2 早就指出过，当时定为「独立 P2 工程项」，没做。本清单各条的验收都依赖它。
- **改法**：以 `docs/tmp/2026-10-29-web-loop-harness/harness.mjs` 为底，在 `.claude/skills/web-loop/tests/` 下落成正式的 `dryrun.mjs`（外壳）和若干场景测试。外壳要点：`globalThis.args` 传 JSON **字符串**（真 runtime 就是这样传的）；`agent()` 按 label 返回预设结果，并记下每次调用的 label 和 prompt，供断言。
- **验收**：把审计场景 T1、T2、U1、U2、S1、S2b、S4～S8 落成测试，先在旧模板上**确认它们失败**（证明测得出毛病），再随各条改动逐个转绿。

### 10. 「卡住了」的自动判断在第 3 轮几乎必然误报（升为 P0）

- **现象**：
  - treadmill（grep `return lastNewCum >= fixedCum && lastNewCum > 0 && lastNewCum >= prevNewCum;`）拿**全体 lens** 从第 1 轮起**累计**的新 must，去比**单个 lens 自己**修好的条数，还用 `>=`。只要有一个 lens 修好的少于全体新增数，它就成立。code 这种 lens 几乎从不报 must，所以 6 个 lens 时基本躲不开。
  - 06-21 设计文档 §3.4 的原式用的是「最近 2 轮」窗口，实现改成了从头累计。
  - 真跑证据：run B 第 3 轮那一轮修掉了 14 条，`paused.latest.md` 仍写「触发判据 treadmill」（JB 第 65 条）。按代码推算全局新增累计 9、9、12，code lens 只修好过 1 条。run A 第 3 轮同样成立，只是当时已收敛，SUMMARY 顶上误挂了「PAUSED · treadmill」。
  - 模拟：T2「ux 开头报 5 条、之后每轮修 1 条、从不新增」也在第 3 轮判成 treadmill。
  - 连带后果：maxRounds 实际等于 3；P1 meta-agent 要求 `!pausedReason`，最早也要第 3 轮才可能触发，所以从没跑过（两次 run 都没有 `decision_log.json`）；oscillating 要「修好→回归」两次，3 轮内不可能发生。
  - `finalizePausedBlock` 只看 `pausedReason`，不看是否已收敛；收敛了也挂 PAUSED。它还写「详 `${WORKDIR}/paused.md`」，实际文件叫 `paused.latest.md` / `paused.history.md`。
- **改法**：
  - treadmill 按 lens 统计：`history` 里记 `newMustByLens`；只看最近两轮窗口；要求该 lens 新增**严格大于**修复，且连续两轮成立。另一个选项是整条删掉，停滞交给 `mustStaleStreak` 判。推荐前者，保留原设计「修一条冒一条」的检测意图。
  - PAUSED 节加 `!converged` 条件；文件名改成 `paused.latest.md`。
  - `exitReason` 单独区分 `paused`，不要混进 `stalled`（SKILL.md 的退出原因列表目前也漏了 stalled）。
- **验收**：T1（真停滞）仍判暂停；T2（稳步推进）不暂停；「code lens 一条 must 都没有」时第 3 轮不暂停；已收敛的 run 的 SUMMARY 不挂 PAUSED。

### 13. 用上 implementer 的返回值

- **现象**：implementer 那次调用是裸的 `await agent(`（grep `【${rtag} · implementer】`），返回值没存。于是：
  - refresh 只好再派 agent 去 impl.md 里读 kind。run B 的 impl-r02 明明交回了 `kind:"frontend"`（JB 第 34 条），refresh-r02 却因为 impl.md 不存在返回 `ready:false`（JB 第 38 条），整轮跳过。**这是第 2 条那次整轮跳过的直接原因。**
  - stuck 信号另派一个 read-impl-stuck agent 用正则从文件抽，而且读的是**上一轮**的 impl.md（grep `rounds/${round - 1}/impl.md && head -40`），差一轮；它的 schema 没有 `stuck` 字段，拼出来的 `reviewer_stuck` 永远是 false。
  - 06-22 审计 P0-1(iii) 的原文要求「workflow 主线读 implementer schema 的 reviewer_stuck 三字段」，实现跑偏了。
- **改法**：写成 `const impl = await agent(...)`；`impl.kind` 直接交给 refresh，`reviewer_stuck`、`planRepetition` 直接拼进 stuckSignal；删掉 read-impl-stuck。
- **验收**：场景 S8：implementer 返回 kind 但不写 impl.md，refresh 照常刷新、本轮照常评审。

### 14. 台账保留评审交上来的全部字段

- **现象**：mergeIssues 新建条目时（grep `issues.push({ id: nextId(v.lens, round),`）只存 9 个字段（id、lens、title、severity、unverifiable、status、bornRound、lastSeenRound、nextStepPlanHistory），丢了 `detail`、`evidence`、`matchesSubgoal`、`requiredStates`。两次 run 的 issues.json 都是这样，而评审原始返回里这些字段是有的（run A 的 rival-r01 有 11 条带 requiredStates）。06-22 审计元教训 1 明确要求「以 mergeIssues 为锚」逐字段排查第二处断点，没做。
- **后果**：
  - missingStates 判据是死代码。run B 第 1 轮就有 3 条 must（func-r1-1、rival-r1-2、razor-r1-3）同时指向 G6 和 `14-compare-box`，本该当场暂停、让人修配方，结果白跑了两轮。
  - SUMMARY 的「待补 STATES」节永远写「(无 — 本次 capture STATES 覆盖完整)」，是假安心。
  - implementer 拿到的 must 除 code lens 外只有标题，没有细节和证据。
  - 【方向题】的选项、代价、推荐全丢（第 4 条的另一半原因）。
  - 脚本自己插入的 infra / regress / shot 条目又少了 unverifiable 和 nextStepPlanHistory，形状和普通条目不一致。
- **改法**：新建条目时保留这四个字段；回归、再次报告时更新为最新值；脚本插入的条目补齐同样的字段集。
- **验收**：S1 中 detail 进台账并出现在下一轮 implementer 的 prompt 里；S2b（同一子项连续不可验证、requiredStates 相同）触发 missingStates；用 run B 第 1 轮的评审数据喂进去也能触发。

### 12. 证据缺口不挡收敛；verdict 全由台账推导

- **现象**：
  - 第一版只想改 prompt，但前提不成立：`const openMust=issues.filter(i=>(i.status==="open"||i.status==="regressed")&&i.severity==="must");` 没有排除 unverifiable，而 `converged` 要求 openMust 为 0。评审就算正确标了 unverifiable，这条 must 也会一直挡住收敛，且没有 implementer 能关掉它。run B 的 func-r1-1、rival-r1-2、razor-r1-3 从第 1 轮开到最后。模拟 U1 同样不收敛。
  - verdict 的推导是单向的：台账只能把 pass 改成 fail。评审只报了 nice、却申报 fail 时同样收敛不了（U2；run B 第 3 轮 code 和 ux 判 fail 但 must 都是 0，JB 第 59、60 条）。
  - 子项覆盖这道关几乎不起作用：run A 第 1 轮 code lens 拿 diff 宣称覆盖了 G3「新手第一眼读对」，可 G3 的衡量标准是「newbie 开着的 must 为 0」，newbie 当轮开着 4 条。code、func 两个 lens 第 1 轮就宣称覆盖全部子项（两次 run 都是），覆盖集合从此不变。
  - 同一个证据缺口，run B 第 1 轮里 func、razor、rival 记 must，ux、code 记 nice。
- **改法**：
  - 收敛只看「确证的 must」（排除 unverifiable）；unverifiable 的条目进 SUMMARY 的「待人工取证」节。
  - verdict 完全由台账推导，不采信评审自报的 pass / fail。
  - 每个子项只认它的衡量标准里点名的 lens（例如 G3 只认 newbie）；goal.md 拆子项时写明负责的 lens。
  - 评审 prompt 的判法段加硬规则：根因在截图配方或状态缺失的问题，一律 `unverifiable:true` 并填 `requiredStates`；schema 收紧为「unverifiable 必须填 requiredStates」（06-22 C_raw F3 提过，没做）。
- **验收**：U1、U2 收敛；`test-reviewer-prompt*.mjs` 断言 prompt 里有这条规则。

### 2. 一个环节出错不能悄悄跳过整轮

- **现象**：refresh 返回 `ready:false` 时执行 `history.push({ round, skippedReview:true }); continue;`，capture 失败那条分支也一样，后面的截图、评审、persist、停滞判据、meta-agent 全部跳过，也不报警。模拟 S7：每轮截图都失败，5 轮花了 34 个 agent，一次都没写 issues.json，也不暂停，最后报 max-rounds-hit。06-22 P1-6 加了 `capture_layer_bug` 这个枚举，但没有能触发它的路径。
- **改法**：
  - 主因由第 13 条消除（kind 直接用 implementer 的返回值）。implementer 没正常交回时，按上一轮的 kind 兜底（第一轮兜底 `frontend`），照常进 capture 和 review，并往台账记一条 must：`implementer 未正常交回`，lens 记 `workflow`（见第 16 条）。
  - 只有 capture 真拿不到任何截图时才跳过评审。跳过的轮次照样 persist、照样走停滞判据；**连续两轮跳过就暂停**，写明原因。
  - SUMMARY 写明哪几轮被跳过、原因是什么。
- **验收**：S7 在第 2 轮后暂停并写明原因；implementer 返回空时，capture 和 review 仍执行，台账里有一条 workflow must。

### 1. 回滚只退本轮，不冲掉前几轮

- **现象**：smoke 红了时，rollback agent 跑 `git checkout -- .`（grep `本轮致回归`）。workflow 每轮都不提交，这会把开跑以来**所有轮次**的改动连同**开跑前就有的**未提交改动一起冲掉；preflight 也不检查工作区是否干净。两次 run 都没触发过回滚，但 run B r02 证明半截改动确实会发生。
- **改法**：每轮 implementer 开工前，把当时所有脏文件（已跟踪的改动 + 未跟踪文件）整体拷到 `<workdir>/snapshots/r{N}/`，连同一份脏文件清单。回滚时：快照里有的拷回；快照里没有、现在脏了的已跟踪文件 `git checkout`；新冒出来的未跟踪文件删掉。不用 `git stash create`：它不含未跟踪文件，而且 stash 栈是所有 worktree 共用的。这份快照还能顺带算出「本轮 diff」（第 6 条要用）。
- **验收**：模拟「r1 改 A、r2 改 B 并新建 C 后 smoke 红」，回滚后 A 的改动还在，B 退回 r1 结束时的样子，C 被删；开跑前就有的未提交改动不受影响。

### 3. 子代理不要等主会话回复

- **现象**：run B 的 r02 implementer 在开工 8 分钟、一次没改文件后给主会话发消息，报告截图配方选错了框。主会话用 SendMessage 回复后，系统「Resuming agent」出一个同 id 的副本，两个进程交错改 `mock_v4.html`（JB 子日志 `agent-ad2a398dcc16afcc3.jsonl`：16:13:32 一条说「I have not edited it yet」，一秒后另一条说已经写进了一处没改完的修改）。主会话改口叫停后，文件里留下半截修改（`sideTag()` 未定义，compare 档报错）。原 implementer 带着「被叫停」交回，于是有了第 2 条的整轮跳过。
  - 根因：workflow 子代理不在 ListAgents 里单独列出，消息投不到它本身，只会拉起一个副本。
  - 系统给 workflow 子代理的提示里会列出可发消息的对象，impl-r03 也调用过 ListAgents，所以 prompt 里的禁令是必须的。
- **改法**：
  - 模板里所有 agent prompt 共用的约束段（新加一个常量，拼到每个 prompt 末尾）加一句：「需要主会话处理的事（参数错、截图配方错、权限问题），写进 `<workdir>/to-main-r{N}.md` 后继续本职工作，不要等回复，也不要用 SendMessage 找主会话。」
  - SKILL.md「红线」节加一条：主会话**不得**用 SendMessage 回复 workflow 子代理；要影响后续轮次，写 human-hint 文件（见第 15 条），或者停下来起新 run。
  - SKILL.md「监控与收尾」节加一条：主会话定期看 `<workdir>/to-main-r*.md`。
  - implementer 改为消费**所有还没消费过的** `human-hint-*.md`，不再只认 `human-hint-r${round}.md` 这个确切文件名。run B 主会话 16:15 写了 `human-hint-r4.md`，r3 的 implementer 16:14:40 已开工，第 4 轮又没开，hint 没人读到。
  - 能否用工具限制硬拦，见第 23 条。
- **验收**：`test-skill-doc*.mjs` 断言红线节里有这一条；`test-implementer-prompt*.mjs` 断言 prompt 里有 to-main 约束；dryrun 中 `human-hint-r7.md` 在第 3 轮也会被读到。

### 11. finalize 写不了 SUMMARY.md

- **根因已查清**：不是权限确认。run A 的 finalize（agent `a7d2efbb03d9f838b`）调 Write 时收到 `<tool_use_error>Subagents should return findings as text, not write report files. Include this content in your final response instead.</tool_use_error>`；run B 的 finalize 又撞上同一条（JB 最后一条）。这是运行环境对子代理写报告类文件的拦截。同一批 agent 用 Write 写 impl.md、preflight.md、goal.md 都没被拦，用 Bash 写 round_N.md 也没事，所以拦截大概按文件名或内容判断（不确定是哪种）。finalize 还因此把全文生成两遍，run A 多花约 3 万输出 token。
- **改法（推荐）**：finalize 不写文件，用 schema 把 SUMMARY 全文交回；脚本末尾把它作为 workflow 的返回值交给主会话，由主会话写 SUMMARY.md。SKILL.md「监控与收尾」节写明这一步由主会话做。
  - **先实测一件事**：运行时接不接受脚本顶层 `return`。Workflow 工具自己的说明示例以 `return { confirmed }` 结尾，官方插件的 6 个 workflow 也都用顶层 return 并注明「calling session writes .md」，所以大概率接受。但项目记忆 `project_web_loop_skill.md` 记着「顶层 return 非法、必须裸顶层 `node --check`」。实施时先用一个**不派任何 agent** 的最小脚本跑一次 Workflow 确认（调 Workflow 前须经用户同意）。若接受，「裸顶层 node --check」的规矩要改成能容纳顶层 return 的检查方式，项目记忆同步更正；若不接受，退回现行做法：主会话从 journal 里取 finalize 的返回全文代写。
  - **不推荐**：改用 Bash heredoc 写文件。实测能绕过去，但这是绕开运行环境有意设的拦截，随时可能被堵上。
  - 同理，第 4 条的 `directions.md`、第 8 条的 `baseline_counts.md` 如果由子代理写，也可能被同一条拦截挡住，实施时要试。

---

## P1：花费效率和中途纠错

### 15. 暂停后能续上，主会话能改台账

- **现象**：
  - 模板 pausedBody（grep `resumeFromRunId: "${RUNTAG}"`）和 SKILL.md「续修协议」节都让填 `resumeFromRunId: "<runtag>"`。runtag 是 web-loop 自己的目录名，运行时要的是 workflow 的 run id（如 `wf_0859d62f-41e`）加 `scriptPath`。
  - 即使填对，resume 也会按日志原样重放：已完成的 agent 直接返回缓存结果，控制流是确定的，会在同一轮再判一次暂停后进 finalize，`human-hint-r{N+1}.md` 永远轮不到。依据是官方插件 `~/.claude/plugins/marketplaces/claude-plugins-official/plugins/code-modernization/workflows/extract-rules.js` 的注释（「completed agents replay from the journal」，缓存键按调用顺序链式哈希）加推理，**没有实测**。06-21 final_report §5.2 自己也写了「需要落地后实测」，一直没人测。
  - 跨 session 的兜底（06-22 C_raw §8、B_raw #9：iterate 顶部从文件恢复台账）定了没做。
  - human-hint 只送到下一轮 implementer，到不了评审，也改不了台账。run B 第 3 轮的评审照样把那 3 条配方问题记成 must。
- **改法**：
  - 起新 run 时允许把上一次的 `issues.json`、`verified.json` 作为输入（args 里给路径），脚本据此恢复台账和轮号，不依赖 resume。
  - 加 `<workdir>/ledger-overrides.json`：脚本每轮读，可以按 id 关掉某条、标为证据不足、或豁免某个暂停判据一次。主会话中途纠错就靠它。
  - SKILL.md「续修协议」节按上面重写，删掉 `resumeFromRunId: "<runtag>"` 的写法。
- **验收**：dryrun 用上一次的台账起新 run，轮号从 N+1 继续、已验证子项不重做；overrides 里关掉的条目下一轮不再挡收敛。

### 7. 截图清单可以中途改

- **现象**：STATES 只在开跑时从 args 读一次，每轮 capture 都用同一份。run B 的 `14-compare-box` 配方选错了框，三个 lens 连报 3 条 must，跑到一半改不了。主会话 16:12:34 修了磁盘上的 `states_v5.json`，implementer r03 按修好的配方自查，在 impl.md 里写「14 已选中放量突破」；capture 用的却仍是冻结的那份，r03 的 6 个评审全部仍对 14 号截图报了同样的问题，ux-r03 还记了一条「impl.md 说已选中，和截图不符」。
- **改法**：
  - args 加 `statesPath`。capture agent 每轮自己 Read 这个文件（脚本本身读不了文件；由 agent 读，prompt 文本不变，resume 缓存也不受影响）；文件不存在或解析失败时退回 args.states。implementer 自查也必须读同一个文件。
  - SKILL.md 说明：主会话发现配方写错，直接改这个文件，下一轮就生效。
  - finalize 模板里「已知设计 risk 2」写着「中途改需求没有通道」（06-19 设计的本意），改完后同步删改。
- **验收**：dryrun 在第 2 轮前改 statesPath 文件，第 2 轮 capture 和 implementer 用的都是新配方。

### 19. 截图配方要能断言，禁止静默兜底

- **现象**：`14-compare-box` 配方写着 `a.boxes.find(...)||a.boxes[0]`，找不到目标框就悄悄选第一个；它的探针只记了 `{mode, sel:'box', tab}`，看不出选中的是哪个框。两轮 capture 都返回同样的探针值，没有任何报错。主会话开跑前的检查脚本也只确认了「选中了一个框」。这违背了模板 CAPTURE_ERR_RULE「禁止静默兜底」的本意，只是兜底写在配方里。名字匹配修好后，`states_v5.json` 里这个 `||a.boxes[0]` 仍然留着。
- **改法**：
  - 截图清单每项支持可选的 `expect`（对探针结果的期望值）。capture 照着断言，对不上就把这一态记成错误，进入下一轮的「上轮取证失败记录」，并作为第 2 条的 workflow 问题入账，不交给评审去猜。
  - SKILL.md 写明：配方里禁止用 `||` 兜底，探针必须记录「目标是谁」（如选中框的名字）。
  - `docs/research/2026-10-28_annotation-web-loop/states_v5.json` 的 14 号配方去掉 `||a.boxes[0]`，加 `expect`。
- **验收**：dryrun 中探针与 expect 不符时，该态记为 error，台账多一条 workflow 问题，评审 prompt 里不出现这张截图。

### 9. 截图脚本落盘复用，视口统一

- **现象**：
  - 模板里没有视口参数。run A 三轮的视口分别是 MCP 默认 1037 宽、`run_code` 设的 1600×900、`browser_resize` 设的 2560×1440，评审间接看错了几处。run B 的 21 条配方里 18 条手写「视口 2560x1440」。
  - capture 每轮让模型从头重写截图脚本：run B 两轮各写了一份约 6600 字符的 `_shot.mjs`，写法不同。capture-r01 写了 `shots/_manifest.json`，capture-r03 没写，r03 的 code reviewer 读到的是第 1 轮的旧清单，还为此立了一条问题（code-r3-1）。
  - implementer 每轮也自己截一遍全部状态：run B impl-r01 跑了 15 次截图脚本、读了 24 张图、裁了 9 次图，只编辑了 7 次。
- **改法**：
  - args 加 `viewport`（默认 `{width:2560,height:1440,deviceScaleFactor:1}`），单条 state 可覆盖；脚本截图和 fallback 两条路都注入这个值。
  - 第 1 轮把截图脚本落成 `<workdir>/capture.mjs`，之后每轮照跑同一份，只在清单变了或脚本报错时才重写。implementer 自查也调用同一份。
  - 清单文件按轮命名：`<workdir>/shots/${rtag}_manifest.json`。
- **验收**：dryrun 中第 2 轮 capture 的 prompt 指向已有的 `capture.mjs`；评审 prompt 引用的是本轮的 manifest 文件名。

### 4. 评审结果由评审自己落盘，台账别整份来回抄

- **现象**：
  - persist 写 `reviews/round_${round}.md`（例如 `round_1.md`），读的地方用 `round_${String(round).padStart(2,'0')}.md`。run A 的 impl-r02 先 `cat round_01.md` 失败，再 ls 才找到 round_1.md，属于「靠运气读到」。
  - 更根本的是 persist 的 prompt 里根本没有评审原文，只有一句「追加 reviews/round_N.md」：run A r1 用标题拼了一份，r3 干脆不写（JA 第 82 条：「任务文本没有给出要追加的内容，我没有自己编」），run B 写的是几百字节的英文摘要。run A 的 SUMMARY 声称方向题选项和代价「写在 round_1.md、round_2.md 正文里」，实际只有标题，事后只能写脚本从日志里挖。
  - persist 每轮要把整份 issues 和 verified（run A 第 3 轮约 10 万字符）再输出一遍：耗时 2.3、4.6、6.4 分钟一路涨，都在关键路径上；run A 光这一步输出约 15 万 token，占全部输出 10%；persist-r02 自报「手误多填了一个 suggestedFix」。
  - verified 记录每轮全量塞给 5 个评审：run A 结束时 verified.json 108KB，第 3 轮每个评审的 prompt 约 7.9 万字符，其中 verified 约 3.9 万；跑到 5 轮会再翻一倍左右。prompt 里还写「已验证项勿重复质疑」，和 principles 轴⑤「已修的不得复现」相矛盾。
- **改法**：
  - 每个评审最后自己把完整结果写到 `reviews/round_NN/<lens>.json`（两位数轮号），包括【方向题】的选项、代价、推荐。
  - persist 只写本轮增量，回报写入字节数，脚本侧对账；不再整份重抄。
  - 给评审的 verified 只放标题，且只放相关子项最近一次的那条。「勿重复质疑」改成「已修的若复现，按回归报」。
  - `<workdir>/directions.md` 从台账筛出【方向题】生成，finalize 直接引用。
  - 注意第 11 条：子代理写 `directions.md` 可能被拦截，先试。
- **验收**：dryrun 跑 3 轮，`reviews/round_01～03/` 下各 lens 文件齐全；persist 的 prompt 长度不随轮数线性增长；`directions.md` 收齐各轮方向题。

### 6. 压缩每轮固定开销：删掉两个白跑的 agent

- **现象**：不算评审，每轮还有 read-state、implementer、smoke、refresh、capture、read-impl-stuck、persist 这 7 个 agent。
  - read-state 四次都返回 `exists:false`（JA 第 32、58 条，JB 第 32、40 条），因为 `decision_log.json` 从没产生过。它量的「diff 行数」（grep `git diff --stat 2>/dev/null | tail -1`）是开跑以来的累计、且量在本轮改动之前（run B：167、212），所以「少于 5 行」在第一次改动后就不可能成立。code reviewer 看到的也是累计 diff，分不出本轮改了什么。06-22 B_raw 盲区 6、C_raw F5 当初都建议删这条判据，合并时反而留下了。
  - 「子项覆盖不变」计数：code、func 第 1 轮就宣称覆盖全部子项，从第 2 轮起每轮加 1，实际等于「轮数 ≥ 3」（第 12 条改完后要重新核对）。
  - read-impl-stuck 由第 13 条删掉。
  - 这些机械 agent 每个只跑 8～50 秒，真正花时间的固定开销是 persist（第 4 条）。
- **改法**：
  - 删 read-state：meta-agent 跑没跑过脚本自己知道，forbidden 列表由脚本记在内存里；删掉「diff 太小」判据。本轮 diff 改用第 1 条的快照来算，交给 code reviewer。
  - 删 read-impl-stuck（第 13 条）。
  - 每轮固定开销从 7 降到 5；再把 smoke 和 refresh 合成一个就是 4（可选）。
- **验收**：dryrun 中每轮固定 agent 数为 5（或 4）；依赖 label 的测试同步更新。

### 16. 脚本自己插入的问题由脚本自己关

- **现象**：`regress-`、`infra-`、`shot-` 三类条目都写死 `lens:"code"`，只能由 code lens 关掉。lenses 不含 code 时永远关不掉。模拟 S6：只有 ux 一个 lens，第 1 轮刷新失败一次，之后 ux 全部 pass，跑 4 轮后 stalled、剩 1 条 must。run B 也有一条 infra-r02。
- **改法**：这三类及第 2 条新增的「implementer 未正常交回」都标 `lens:"workflow"`，在下一轮对应环节成功时由脚本自动关闭。
- **验收**：S6 收敛。

### 17. 不轻信评审回填的 lens 名和问题 id

- **现象**：
  - 归属用的是评审自己回填的 `v.lens`。模拟 S5：rival 回填成 "ux"，问题就记到了 ux 名下。
  - `matchesIssueId` 写错（比如 `ux-r1-01`）时，这条新问题被静默丢掉；模拟 S4 最后报「0 must left」。stalePrimer 又强推评审优先用 matchesIssueId，放大了这个风险。
- **改法**：用调度侧自己知道的 lens 覆盖回填值；matchesIssueId 查无此 id 时按新问题入账，并记一条日志。
- **验收**：S4、S5 归属和计数正确。

### 18. 开跑清理不删上一次的截图

- **现象**：SKILL.md「setup 清理」小标题写「N-1 保留」，正文和代码却删掉所有旧 run 的截图。run B 的 cleanup 返回 `cleaned_runtags:["2026-10-28_annotation-v4"]`，run A 的目录里现在已没有 shots/（报告要用的图事先拷走了，这次没造成损失）。它还整删 `.playwright-mcp/`（返回 `deleted_mcp:true`），不管别的会话是否正在用，也违反项目 CLAUDE.md「保留目录本身」的规矩。
- **改法**：真正保留上一次 run 的截图，只删更早的；清 `.playwright-mcp` 改用 `find .playwright-mcp -mindepth 1 -delete`。注意第 8 条新增的起点图也在 shots/ 里，同受此条保护。
- **验收**：dryrun 构造三个旧 run 目录，清理后只有最旧的两个没了 shots/。

### 20. smoke 看不到的回归也要拦

- **现象**：run B r02 的半截改动让 compare 档抛 ReferenceError，smoke-r02 却通过了（JB 第 36 条），因为 smoke 只开默认档和题视图。implementer r03 建议扩大 smoke 范围，只写在 impl.md 里，没人看；func-r03 和 code-r03 把它记成了【方向题】。
- **改法**（二选一或都做）：
  - capture 的 manifest 已经按状态记了 pageErrors：某个状态上一轮没报错、这一轮报错了，就按回归处理（记 regress 条目，必要时回滚）。这一条不依赖项目怎么写 smoke，推荐先做。
  - preflight 检查 smoke 是否覆盖了截图清单里出现的各个 mode，没覆盖就提示主会话。
- **验收**：dryrun 中第 2 轮某状态新出现 pageError，台账多一条 regress。

### 5. 加代理数上限

- **现象**：模板没有总量控制，主会话按「每轮约 7 个机械 agent + lens 数」手算 maxRounds。run B 定了 65 个，实际只用了 34 个，是因为第 10 条。运行时另有 token 预算和每个 run 1000 个 agent 的上限；预算耗尽时 `agent()` 直接抛错，整个 run 没有任何结果，web-loop 对此完全没有防护（见官方 extract-rules.js 的 capacity guards 注释）。
- **改法**：
  - args 加 `maxAgents`。脚本维护已用 agent 计数（包一层小函数，每次 `agent()` +1）。
  - 每轮开头预估本轮用量（固定开销 + lens 数 + 可能的 rollback / meta），会超上限就不开新一轮，`exitReason='budget'`，照常进 finalize。同时查 `budget.remaining()`，给 finalize 留余量。
  - SKILL.md 的 args 表补上这一行。必须在第 10 条之后做，否则上限碰不到。
- **验收**：模拟实测（6 个 lens）：setup 4 个，第 1 轮 11 个，之后每轮 13 个，暂停或跑 meta 的那轮 14 个（第 6 条做完后会变少，验收数随之更新）。`maxAgents` 设 30、6 个 lens 时跑完 2 轮停下，exitReason 为 budget。

---

## P2：证据与报告的准确性

### 8. 开跑前先截一组起点图（第 0 轮）

- **现象**：第一组截图就已经是改过以后的，没有「改之前」可对照。rubric 要求的心智负担起点计数（概念、规则、固定词），只能由主会话在开跑前另外做（run A 的 `baseline.md`）；run B 只能退成逐轮增删计数。
- **改法**：setup 末尾按 STATES 截一组 `r00_*`；razor 在第 1 轮评审时多交一份起点计数，存成 `<workdir>/baseline_counts.md`，后面各轮都对照它；finalize 输出前后对照的截图清单。注意第 11 条的拦截和第 18 条的清理。
- **代价**：多 1 个 capture agent。

### 21. 同一件事只立一条，只认原 lens 关闭

- **现象**：
  - mergeIssues 只按「同 lens 且同标题」去重（grep `x.lens===v.lens&&x.title===it.title`）。run B 的 `14-compare-box` 被立了 5 条（func、rival、razor 记 must，ux、code 记 nice）；TVGN 1600 宽右缘被 rival 和 newbie 各立一条。run A 方向题 13 个议题对应 22 条。must 数被放大，还助长了第 10 条的误报。
  - 只要有任何 lens 报「还在」，条目就保持开着（`reportedStillIn` 优先于 `goneByOwner`）。run A 第 3 轮 razor 的 4 条 nice，razor 自己说已经没了，别的 lens 说还在，于是一直开着。每个评审每轮还要对全部开着的问题逐条表态（run A 第 2、3 轮每人 53 条），包括别人的和方向题。这也是 rival 每轮都最慢（572～965 秒，决定一轮墙钟）的原因之一。
- **改法**：
  - 评审交回后加一步按截图状态或主题合并；prompt 要求跨 lens 用 matchesIssueId 引用已有条目（配合第 17 条的校验）。
  - 只认原 lens 的关闭判断；别的 lens 只能拿证据报「回归了」。
  - 方向题移出台账，由第 4 条的 `directions.md` 承接，不再要求每个评审逐条表态。
- **验收**：dryrun 中两个 lens 对同一状态报同一问题，台账只有一条；非原 lens 说「还在」不阻止原 lens 关闭。

### 22. 评审统一用 capture 产出的局部放大图

- **现象**：2560 宽的整页截图读进来会被缩小，侧栏小字看不清，评审只好各自裁图。run B 评审读了 231 张自裁图、跑了 94 次裁图命令，读正式截图只有 171 次；单个评审最多读了 40 张自裁图。run B 第 1 轮有 6 个文件名被两个评审同时写过（如 crops/19_right、crops/20_right），没找到真读错的实例，但写入时间只差几十秒。
- **改法**：capture 按状态统一产出局部放大图（如侧栏元素截图、主图区域 2 倍图），写进 manifest；评审需要再裁时用自己的子目录 `rv-<lens>-r<N>/`。
- **验收**：manifest 里每个状态至少有一张局部图；评审 prompt 里写明裁图目录。

### 23. 红线改成工具限制（待实测）

- **现象**：「评审不碰浏览器」「implementer 不发消息」都只是 prompt 里的一句话。run B 的 impl-r02 实际调用了 SendMessage，impl-r03 调了 ListAgents。
- **改法**：`agent()` 有 `agentType` 选项，可以指定一个工具受限的子代理类型来硬拦。先实测它能否限制工具；能的话，评审去掉浏览器工具，implementer 去掉 SendMessage / ListAgents。

### 24. 所有输出用中文

- **现象**：run B 有 3 个评审输出英文（ux-r01、func-r03、code-r03），台账 34 条标题里 8 条是英文，persist-r01 写的 round_1.md 也是英文；run A 没有这个问题，原因没查出来。
- **改法**：在第 3 条那个共用约束段里加「输出用中文」。

### 25. 小毛病合集

- preflight 没给 healthUrl 时自己猜端口去探（run B 探了 5173 和 8000，报「无响应」），写进 preflight.md 容易误导。没给就不探。
- `prioritizedMustIds`、`pwOk.mcpLoadable` 采了没人用，删掉。
- `p1_skip_reason` 一旦非空，之前累计的 forbidden 全部作废（S12），改成保留。
- decision-log 那条推荐的 python3 命令：safeInsert 产出的 `\"` 放进单引号后 `json.loads` 报错，这条路径从没真跑过。改成脚本内维护（第 6 条）后可整段删掉。
- SKILL.md「红线」节说 setup 检测 `.gitignore` 里有没有 `.claude/web-loop/`、没有就报 must，代码里没有这一步。补上或删掉这句（仓库 .gitignore 已有这一项）。
- SKILL.md 说评审对照 `principles.md`，但模板从不把 principles.md 的路径交给任何 agent。补上路径。

### 26. 开跑前起草验收标准，开跑后冻结（用户 2026-10-29 同意）

- **现象**：每次开跑前的验收标准（rubric）都是主会话按需求现写的。run B 的 `docs/research/2026-10-28_annotation-web-loop/rubric_v5.md` 是主会话把用户几天来定下的配色规范、悬停说明写法、术语规定收拢成硬规则 H1～H14 写成的。这一步价值很大，但 SKILL.md 没写怎么做、从哪取、要不要给用户过目，全凭主会话发挥。
- **改法**：
  - SKILL.md 智能入口层加固定一步「起草验收标准」。来源固定为：本次需求；之前定过的决定（如研究报告里的「已定方向」、配色规范）；项目的界面文字规范（`~/.claude/rules/ui-text-style.md` 之类用户级 rule）；项目词表（`GLOSSARY-MAP.md` 指向的各 GLOSSARY）；项目 CLAUDE.md 的红线；续跑时上一次的 rubric。
  - 结构固定：硬规则（每条能在截图、探针或 diff 上核对，并注明出处）、已定决定（不再当方向题提）、已知方向题、razor 用的任务清单与起点计数法、newbie 用的各签 / 列 / 颜色的正确含义、各评审角度的专节（含第 27 条的自定义角度）。
  - 起草后给用户几句话的摘要（不是整份文件），标出哪些是沿用、哪些是本次新加，用户点头后才开跑。
  - **开跑时把 rubric 拷成 `<workdir>/rubric.md` 冻结**，评审只读这份快照。跑的过程中不改判断标准：标准写错了，用第 15 条的台账覆盖豁免受影响的条目，改正后的标准从下一次 run 生效。截图清单（第 7 条）可以中途改，因为它管的是取证，不是判断标准。
- **为什么冻结**：web-loop 能停下靠「对照一份不变的标准判过不过」。早期验证：按「问题清空才停」跑 50 轮不收敛，按固定标准判 3 轮收敛。标准若可由代理在跑的过程中改，就失去停止的依据。
- **验收**：dryrun 中评审 prompt 指向 `<workdir>/rubric.md`；setup 有拷贝快照的步骤。

### 27. 评审角度可按需求自定义

- **现象**：模板已支持「没登记的角度名，对照 rubric 里同名一节判」，但 SKILL.md 没写这一节怎么写，也没有拦截写错名字的情况（名字拼错时该角度会在没有专节的情况下乱判）。
- **改法**：
  - SKILL.md 写明自定义角度专节的写法：看哪些截图状态、判什么、什么算必须修、对哪些子项负责（与第 12 条「子项只认点名的角度」衔接）。
  - preflight 检查：每个不在内置清单里的角度名，冻结的 rubric 里都必须有同名专节，没有就在开跑前报错停下。正常情况（专节存在）直接放过。
  - 写明限制：评审永远不碰浏览器，所以「模拟用户走一遍流程」这类角度，是按截图清单里排好顺序的一串状态来判，自己不能点击。要覆盖的流程步骤必须在截图清单里排出来。
  - 示例：在 SKILL.md 或 examples 里给一个「模拟用户走完整个流程」角度的专节样例。
- **验收**：dryrun 中传入一个 rubric 里没有专节的角度名，preflight 报错停下；有专节时正常进入第 1 轮。

### 28. 原型模式：界面先行、后端未开发时的打磨（用户 2026-10-29 同意并入）

- **场景**：界面主导的项目设计里，界面和交互流程先打磨（它决定后端怎么做），后端代码还没开工。原型背后的模拟逻辑和演示数据本身就是方案。标注原型 `mock_v4.html` 就是这种情况：只有 `data.js` 演示数据，没有后端。
- **这一阶段真正的产出有三样**：界面与交互流程；界面对后端的要求（要哪些数据、系统算什么、判什么）；过程中用户拍板的决定。现模板只管第一样。
- **改法**：主会话在开跑前判断用哪种模式（没有后端、静态页，或用户说明是原型时，用原型模式），骨架不变，改五处：
  1. **多一份产出：后端要求清单**（`<workdir>/backend_contract.md` 或同等 JSON）。原型里每一处模拟逻辑、每个演示数据字段都对应一条要求。implementer 每轮改动模拟逻辑或数据时同步更新；finalize 交回，作为后端设计的起点。
  2. **方案层面的修改不许 implementer 自己做主**：改数据长什么样、系统算什么、用什么词，只能提方向题等用户拍板（冻结的 rubric 里「已定决定」覆盖的除外）。纯界面层（布局、配色、文案）照常改。方案文档（如研究报告「已定方向」、`.scratch` 下的规格）作为第 26 条起草验收标准的来源之一；finalize 列出「方案受影响的地方」，方案文档由主会话经用户同意后再改（那是共享状态）。
  3. **演示数据要覆盖边界情况**：截图清单要排进空、很多、互相矛盾等边界数据的状态。implementer 可以补演示数据，但每个新字段都要进后端要求清单。
  4. **默认评审角度换一套**：原型代码将来要扔，审代码质量无意义。两次 run 里 func、code 两个角度确证的界面 must 都是 0，newbie 最多（run A 5 条、run B 4 条）。原型模式默认用：newbie、razor、「模拟用户走流程」，加一个「后端要求一致性」角度（读本轮 diff 和后端要求清单：模拟逻辑或演示数据与清单对不上，记必须修；原型展示的数据疑似后端拿不到，只提方向题、不记必须修，因为可行性不归 web-loop 判断）。这同时回答了「默认评审角度能不能减」：证据只覆盖原型场景，就只在原型模式里换，真实应用的默认不动。
  5. **节奏是「短跑 + 拍板 + 再跑」**：每次 2～3 轮，停下让用户拍板方向题，带着已定决定（写进下一次的 rubric，第 26 条）和上次台账（第 15 条）开下一次。run A → 用户定 D1～D5 → run B 就是这个节奏。
- **不做的事**：web-loop 不设计后端，也不判断后端做不做得到；只把「界面需要后端提供什么」整理清楚、标出可疑处，可行性留给方案讨论和将来的实现。
- **验收**：dryrun 中原型模式开跑时默认角度为上述四个；implementer 返回里有后端要求清单的变更；方案层修改以方向题出现而非直接改动；finalize 的返回值里含后端要求清单与「方案受影响的地方」。

---

## 改完后要同步的文档

- **`SKILL.md`**：
  - args 表加 `maxAgents`、`statesPath`、`viewport`、上一次台账的路径（第 15 条）；
  - 「红线」节加第 3 条，删掉或补实 `.gitignore` 检测那句；
  - 「监控与收尾」节加 to-main 文件、主会话写 SUMMARY（第 11 条）；
  - 「三条机检判据」节按第 10 条更正 treadmill 的含义；missingStates 在第 14 条后才真正生效；
  - 「续修协议」节按第 15 条重写；
  - 退出原因补上 `stalled` 和 `paused`；
  - 截图配方禁止 `||` 兜底、探针记录目标（第 19 条）；
  - 删掉失效出处：`2026-06-03-web-loop-skill-feasibility.md`（git 历史里从没有过）、`2026-06-19_web-loop-goal-persistence/final_report.md`、各处「P0 §3.x」「final_report §5.1」（指向 ce28f80 删掉的文档）；
  - 「implementer = opus」一节说 CLAUDE.md 里有「Implementer 一律 sonnet」，项目 CLAUDE.md 已没有这一条；「总 token 可能净降」06-22 审计已指出没有实证。两处改成只陈述现行做法。
- **`workflow-template.js` 注释**：删掉「tests/dryrun.mjs 场景全绿」（第 0 条做完后改成真实的测试名）、`docs/tmp/2026-06-12-web-loop-skill-improvements.md` 等失效出处；finalize 的「已知设计 risk 2」按第 7 条改。
- **`examples/path2.md`**：和项目现状对不上，需要按 path2_web 当前代码重写：
  - rubricPath 指向的 `docs/superpowers/specs/2026-06-02-path2-web-ui-design.md` 不存在；
  - states 里的 `data-role-node`、`.hrow` 已找不到，`roleVisible` / `selectedEventId` 已改为 nodeVisible，`__e2e.chart()` 已改为 `chartMain()` / `chartSub()`；
  - §3 刷新模板：`bottom_breakout_burst` 已改为 bottom_burst，请求体 `pattern_id` 现在是 `pattern_ids` 列表，轮询路由 `/scans/<pid>/<ts>` 现在是 `/scans/{name}`；
  - §7 提到的「自动模式（详 CLAUDE.md）」和「派 tom」都已不存在；
  - 补一个「静态页 + node smoke」的示例（run A、B 就是这样跑的）。
- **仓库根 `.web-loop-refresh.md`**：同样过时，端口写死 8000（`configs/path2_web.yaml` 里是 8001），路由也是旧的。它把 404 解释为「扫描进行中，继续重试」，路由一错就会一直等。按 SKILL.md §2a 的占位端口写法重写。
- **项目记忆 `project_web_loop_skill.md`**：第 11 条实测后，更正「顶层 return 非法」那条教训。
- **`docs/research/2026-10-28_annotation-web-loop/final_report.md` 第 6 节**：引用的 run A 日志路径已失效（原在 `-home-yu-PycharmProjects-Trade-Strategy--claude-worktrees-annotation-web-loop/9bb134d6.../` 下，现在在 `-home-yu-PycharmProjects-Trade-Strategy/9bb134d6.../` 下），改成现路径。
- **skill 的 `description`：重写（用户 2026-10-29 已同意；名字 `web-loop` 不改）。**
  - **为什么改**：用户第一次提这类需求时的原话是「我想自动迭代改进标注工具，从提升功能的逻辑性，降低用户心智负担等多个角度入手，自动迭代优化(loop)……找一个合适的工具」，没有直接触发 web-loop，绕道 find-skills 才找回来。现行描述有三处问题：
    - 写满内部词（Workflow、smoke、refresh、playwright、rubric、reviewer），用户提需求时不会说这些，违反项目 CLAUDE.md「创作 skill」节「触发词只取用户会自然说出口的词」。
    - 「视觉+功能评审」读起来偏外观，用户因此误以为它的重点是美化页面。实际上它改的是程序（前端、后端、数据三档都能改），只是把浏览器里看得到的结果当判断依据。
    - 后加的对抗评审（rival / razor / newbie）没进描述，违反同节「功能扩展后必须回头改 description」。
  - **为什么不改名**：名字字面意思（有浏览器界面的应用 + 多轮循环）没错；「判断依据只来自页面能看到的东西」这类边界，两三个词装不下，只能写进描述；用户已习惯叫它 web-loop；改名要牵动 skill 目录、`.claude/web-loop/` 运行目录、`.gitignore`、`.web-loop-refresh.md` 和 9 条项目记忆。
  - **新描述草稿**（用户已过目，实施时可在不改原意的前提下润色；人话部分不得再换回内部词）：
    > 自动多轮迭代改进一个正在运行、有浏览器界面的应用：功能逻辑、交互、布局、文案都能改。每轮改完自动截图，由几个不同角度的评审（界面、功能、代码，可加独立复核、新手第一眼、砍多余元素）对照验收标准打分，直到达标。用户说「自动迭代改进 / 打磨 XX 工具或界面」「从多个角度评审并自动改」「loop 优化」「反复改到满意」时使用。页面上看不到结果的问题（后端算得对不对、性能）不归它管。
  - SKILL.md 正文「何时用 / 不用」一节同步补一句：结果不落到页面上的逻辑（后端计算对错、性能、并发）不适合用它判断，应走测试或评估脚本。
  - 若有断言 description 文本的测试（`tests/test-skill-doc*.mjs`），同步更新。

## 拿不准、需要实施时先实测的

- resume 会原样重放（第 15 条）：依据是官方插件注释加推理，没有真跑。
- 运行时接不接受顶层 `return`（第 11 条）。
- 「不许写报告类文件」的拦截按文件名还是按内容判断；`directions.md`、`baseline_counts.md` 能不能由子代理写。
- `agentType` 能否限制工具（第 23 条）。
- 两份挖掘的频率都只基于 2 次 run；upc 那台机器上有没有别的 run 没查。
