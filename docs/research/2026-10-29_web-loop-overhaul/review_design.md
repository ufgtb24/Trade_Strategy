# skeptic 复核记录（web-loop overhaul）

> 本文所有项目内路径相对 worktree 根。复现脚本在 `docs/research/2026-10-29_web-loop-overhaul/repro/skeptic/`，跑法：进该目录 `node <脚本>.mjs`（基于 `docs/tmp/2026-10-29-web-loop-harness/harness.mjs`，`h.mjs` 多了一个「对模板文本打补丁」的参数，用来模拟某条改动之后的行为）。
> 标记：**must** = 会让 run 白跑、丢改动、结论失真或明显浪费 token；**nice** = 值得做但不做也不出大事。

## 一、开工前攻击清单（改动清单第 0～25 条没覆盖到的）

### A. run 以错误方式结束

**K1 [must] 回滚轮不进任何停机判据，也不 persist。**
- 场景：smoke 因环境原因（dev server 挂了、端口被占）每轮都红。
- 后果：每轮 opus implementer（10～21 分钟）干完就被回滚，跑满 maxRounds，退出原因 max-rounds-hit，台账一次都没落盘。环境故障被当成「本轮改动致回归」，好的改动被冲掉。
- 证据：`repro/skeptic/k1_rollback_loop.mjs` → 5 次 impl、5 次 rollback、0 次 persist、不暂停。模板 grep `history.push({ round, rolledBack:true }); continue;`。第 2 条只覆盖 refresh / capture 跳过，没覆盖这条分支。
- 建议：回滚后同一个 agent 再跑一次 smoke。恢复后仍红 → 不是本轮改动造成的 → 把本轮改动放回去（K9 的快照能做到）并暂停，写明「基线已坏」；恢复后变绿 → 确认是回归，照常进下一轮。连续两轮回滚也暂停。
- 正常放过：偶发一次回滚、下一轮 smoke 绿，流程不变。

**K2 [must] 回归通道是断的：修好的条目 id 从此不出现在任何评审 prompt 里。**
- 机制：`issuesJson` 只放 open / regressed；verified 只有标题、没有 id。评审复现一个已修的问题时只能新立一条。
- 后果：`regressed` 状态和 oscillating 判据实际走不到（两次 run 的 regressionCount 全为 0）；回归被记成「新 must」，在第 10 条的新 treadmill 里会被算作「冒一条」。第 4 条写「已修的若复现，按回归报」，但没给评审拿到 id 的通道，照写等于空话。
- 证据：`repro/skeptic/k2_regress_channel.mjs` → r03 评审 prompt 不含已修的 ux-r1-1，复现被记成新条目 ux-r3-1、regressionCount=0。
- 建议：评审 prompt 附一张「本 lens 名下已修条目：id + 标题」短表（不带正文），供 matchesIssueId 引用。

**K3 [must] treadmill 修好后，P1 meta-agent 会从第 3 轮起每轮都跑。**
- 机制：「子项覆盖集合连续不变」被当成停滞信号。可覆盖已满且不变是好状态；code / func 第 1 轮就宣称全覆盖（两次 run 都是），于是 r3 起恒真。现在之所以从没跑过，只是因为 treadmill 抢先在 r3 叫停。
- 后果：每轮多一个 opus，prompt 内联整份台账和 verifiedLog（run A 第 3 轮 verified 108KB）；而且每轮都把 escapeRequest（能让 run 暂停）交给一个从没在生产里跑过的 agent。
- 证据：`repro/skeptic/k3_meta_always_on.mjs`（把 treadmill 置 false 模拟第 10 条修好后）→ 稳步推进的 run 在 r03、r04、r05 都触发 meta-agent。项目记忆 `project_web_loop_decision_layer_redesign` 结论 1：P1 的存在理由绑在「停滞边缘触发」，常态化等于用 95% 的死成本换 5% 的救场。
- 建议：删掉「覆盖不变」触发（或只在覆盖不全时计数）；meta-agent 不内联整份台账，只给 open must；这条路径（含 decision-log 那段必炸的 python 引号，第 25 条）改完要在 dryrun 里真走一遍。也可以考虑整段删掉 P1（零次生产运行、价值未证），交给 code lens 的「plan 主线自查」+ 停滞判据。

**K4 [must] 第 12 条「unverifiable 不挡收敛」会打开假收敛的口子。**
- 机制：unverifiable 是评审自填的布尔；owner 还能在 knownIssuesStatus 里随时把一条确证 must 翻成 unverifiable（grep `if(k&&typeof k.unverifiable==="boolean") iss.unverifiable=k.unverifiable;`）。
- 场景：没有 goalSubgoals 的 run，或评审把难修的真 bug 标成「证据不足」→ 当轮收敛。
- 建议：脚本侧校验——unverifiable 只在 requiredStates 至少点名一个「本轮没截到的态」（不在本轮 manifest 的成功态里，或该态本轮 error / expect 失败）时采信，否则按确证 must 处理；收敛时若还有 unverifiable must，退出原因单列（如 `converged-with-gaps`），SUMMARY 顶部写明。
- 正常放过：真缺态的问题点名的态确实不在清单里，照样采信、不挡收敛。

**K5 [must] missingStates 的修法要和第 14、21 条一起定，否则要么误停、要么仍是死代码。**
- (i) 它不看 status：已关闭的、或配方已被主会话中途修好（第 7 条）的旧 unverifiable 条目照样计数 → 修好之后仍误停。
- (ii) 它按「条目数 ≥ 2 且有态重复」判：第 21 条把跨 lens 的同一件事合并成一条后，同轮几个 lens 报同一缺态只剩 1 条 → 永不触发。第 14 条的验收「run B 第 1 轮就该暂停」恰恰依赖 3 条没合并的条目。
- 建议：改成「同一个态在连续两轮的 open unverifiable must 里被点名」，只数 open，按轮数不按条目数。

**K6 [must] 第 21 条「只认原 lens 关闭、别的 lens 只能报回归」会制造假 oscillating。**
- 场景：owner 说没了 → fixed；rival 说还在 → regressed（regressionCount+1）；下一轮 owner 又说没了、rival 又说还在 → regressionCount=2 → 以 oscillating 暂停。
- 这是评审之间的分歧，不是 implementer 在两种修法之间来回跳。
- 建议：非 owner 重开单独记（如 `disputedBy`），不计入 regressionCount；分歧持续两轮进 SUMMARY「评审分歧」节，不触发暂停。

**K7 [nice] 某个 lens 每轮都返回 null（超时、API 终止错、用户在 /workflows 里跳过）。**
- 后果：allPresent 恒假 → 既不能收敛也不能 stalled；它名下的问题永远关不掉；静默跑满。
- 建议：缺席记进 history；同一 lens 连续两轮缺席 → 暂停并写明。

**K8 [must] 脚本中途任何异常都会让 finalize 不执行。**
- 场景：预算耗尽时 agent() 直接抛错；LLM 交回意外形状触发 TypeError。
- 后果：没有 SUMMARY、没有返回值；若按第 4 条把 persist 缩成增量甚至删掉，台账只剩 journal。
- 建议：iterate 整段包 try/catch；SUMMARY 由脚本自己拼字符串（不派 agent），catch 后照样作为顶层 return 交回，退出原因 `error`。预算耗尽后 agent() 不能再调，所以收尾不能依赖 agent。

### B. 丢改动、污染工作区

**K9 [must] 第 1 条的回滚会冲掉主会话中途的修改。**
- 场景正是第 7 条鼓励的：主会话跑到一半修 statesPath 文件（run B 的 `states_v5.json` 就是未跟踪文件，`git status` 里是 `??`），或改 rubric、写笔记。本轮 smoke 一红：快照里有的被拷回旧版（主会话的修复被撤），快照里没有的新文件被删。
- 建议：回滚只动「本轮 implementer 动过的路径」，即 implementer 开工前、交回后两个快照之间变了的路径；statesPath、rubricPath、workdir 显式豁免。
- 正常放过：没人并发改文件时，效果与清单原方案相同。
- 附（nice，强烈建议）：快照用 git 临时 index 做，比拷文件稳。`GIT_INDEX_FILE=<workdir>/snap.idx` 下 `git read-tree HEAD && git add -A && git write-tree` 得到一个 tree id：已跟踪 + 未跟踪（尊重 .gitignore）、删除、改名、符号链接、可执行位一次全收；不碰真 index、HEAD 和全 worktree 共用的 stash 栈；同内容自动去重。本轮 diff = `git diff <前 tree> <后 tree>`，正好交给 code reviewer（第 6 条）。做成 skill 自带的小 shell 脚本（save / diff / restore），测试里能在临时仓库真跑。拷文件法要自己处理删除、改名、指向目录的软链。

**K10 [must] 第 9 条把 capture.mjs 放在 `<workdir>/`，会 import 不到 @playwright/test。**
- 机制：node 按脚本文件所在目录往上找 node_modules。本仓库 @playwright 只装在 `path2_web_ui/node_modules`（根目录没有，已核对）。这正是模板要求「在 ${UI_DIR} 写 _shot.mjs」的原因（项目记忆 `project_web_loop_skill`：「必须在前端项目目录内跑，否则 ESM import 失败」）。
- 但放进 uiDir 又会变成源码区的未跟踪文件：进快照、进 code reviewer 的 diff、被回滚删。
- 建议：脚本放 workdir，用 `createRequire(<uiDir>/)` 解析 @playwright/test 的绝对路径再动态 import。

**K11 [nice] human-hint 的消费记录靠改文件名，有两个坑。**
- hint 被本轮 implementer 消费（mv 成 .consumed）后本轮被回滚：效果撤了，hint 也再没人读到。
- 第 3 条「消费所有 `human-hint-*.md`」的通配会把 `human-hint-r3.consumed.md` 也匹配进去。
- 建议：不改文件名；implementer 在 schema 里交回读过的 hint 文件名，脚本内存记「已生效」，本轮回滚就从已生效里撤掉。

**K12 [nice] 第 3 条的共用约束段补一句：不得 git commit / stash / checkout / reset / clean。** implementer 一旦 commit，基于工作区的快照和本轮 diff 全部失真；stash 栈全 worktree 共用。

### C. token 浪费

**K13 [must] 第 4 条「每个评审自己把完整结果写到 reviews/round_NN/<lens>.json」会让评审输出翻倍。**
- 评审已经用 StructuredOutput 交回完整结果，再 Write 一遍就是同一份内容生成两次；评审占全部输出 token 约 69%（run A 约 100 万）。persist 是同一个病：LLM 抄写脚本内存里已有的数据（第 4 条减成增量，但仍是每轮抄）。
- 事实：脚本内存里有全部结果；runtime 的 `journal.jsonl` 已逐条落盘每个 agent 的 result（核对过 JB 前几行，`{"type":"result","label":...,"result":{...}}`）。中途再让 LLM 持久化是重复的。
- 建议：一份数据只让 LLM 生成一次。评审只交 schema、不写文件；删 persist；结束时脚本把 SUMMARY 正文（脚本渲染，见 K15）作为顶层 return 交回，主会话写 SUMMARY.md。大块数据（issues / verified / 各轮评审原文 / directions）若不想进主会话上下文，由一个 effort:'low' 的 agent 在收尾写一次 `final.json`（.json 不在拦截范围，项目记忆已记实测）——这仍是一次抄写，但只一次。中途进度用 log() 打一行。

**K14 [must] 第 14 条把 detail / evidence 存进台账后，issuesJson 原样发给每个评审会显著变大。**
- 现在除 newbie 外，每个评审都收到所有 lens 的全部 open 条目（含 nextStepPlanHistory），第 14 条再加正文。第 21 条只取消了「逐条表态」的义务，没说不发正文。
- 建议：评审只拿自己名下条目的全文；别的 lens 的条目只给 id + 标题（供 matchesIssueId 引用）；完整正文只给 implementer。

**K15 [must] finalize 用 opus 读一份内联了 history、全部 verifiedLog、全部残留条目的 prompt，再写 SUMMARY。**
- 这些节几乎全是脚本已拼好的块，它只是转抄。run A 的 finalize 还花了约 2 分钟读模板诊断误挂的 PAUSED。
- 建议：同 K8 / K13，SUMMARY 由脚本确定性渲染，不派 agent；同时根治第 11 条（写不了 SUMMARY.md）。

**K16 [nice] 每个评审都读全部截图。**
- run B 21 张 2560 宽；图一旦读进上下文，之后每次工具调用都按缓存读取再计费——两次 run 1.3～1.5 亿缓存读取主要来自这里。第 22 条往 manifest 再加局部图，若要求都读，只会更多。
- 建议：按 lens 给截图子集（code 默认不读图、按需；func 只读子项 relatedStates 指向的；ux / rival / razor / newbie 读全部），局部图「需要时再读」。

**K17 [nice] 「逐条子项表态」逼出一批不是缺陷的 nice 条目。**
- run A 74 条里约 10 条是「G4 的 H6 判定归 ux；本 lens 只核了 H7」「G3 · 不归 razor 主判」这类（newbie-r1-9/10/11、razor-r1-7～10、newbie-r2-3/4），进了台账就每轮发给所有评审。
- 建议：配合第 12 条「子项只认点名 lens」，prompt 改成只对自己负责的子项给 verified，其余不表态、不立条目。

**K18 [nice] implementer 本轮什么都没改时，capture + 5～6 个 opus 评审照样全跑。** 有 K9 的前后快照，脚本可直接判「本轮无改动」→ 跳过 capture / review，沿用上轮结论并计入停滞。

**K19 [nice] 删掉没人用却每轮都要生成的东西。**
- 评审 schema：mustFixOpen（只出现在 schema 里）、verdict（第 12 条后由台账推导）、lens（第 17 条后由调度覆盖）、goalEcho（只对 newbie 有用）。
- write-goal：goal.md 与 prompt 里的内联摘要逐字相同，prompt 再写「以 goal.md 为准」会诱导重复 Read；goal.md 可由主会话开跑前写（它手上就有内容），setup 少一个 agent。
- implementer 的 verifiedSummary 是全轮次全 lens 全量，同第 4 条，只放每个子项最近一条。

### D. resume / 确定性

**K20 [must，澄清即可] 第 15 条「用上次台账起新 run、已验证子项不重做」与收敛规则冲突。**
- 收敛要求「本轮」所有子项被覆盖，每轮评审都要重新验证全部子项，没有「不重做」这回事。
- 另：恢复的台账里有某 lens 的 open must、而新 run 的 lenses 不含它（例如为省钱去掉 rival）→ 这些条目永远没人能关 → 永不收敛。设计要写明：owner 不在新 lenses 里的条目转「待人工」或改挂 workflow。

**K21 [nice] ledger-overrides.json 只能由 agent 读（脚本读不了文件）。** 原样 resume 时那次读取命中缓存，新写的覆盖不生效；只在实时 run / 新 run 有效，文档要写清。「豁免某个暂停判据一次」在新 run 里本来就没有对象（history 已清零），可以不做。

### E. 靠 LLM 回填做判定（清单没提的）

- **K22 [nice]** smoke / preflight 的 pass 由 LLM 读输出判断。改成 agent 原样交回退出码 + 末尾若干行，脚本按退出码定。
- **K23 [nice]** 第 19 条的 expect 若由 capture LLM「照着断言」，仍是 LLM 判定；而第 7 条让最新清单只在文件里，脚本手上没有最新 expect。建议断言写进跑截图的脚本代码里，manifest 直接给 `expectOk`。更彻底的做法：配方改成结构化步骤（goto / wait / eval / css / shot），由 skill 自带的通用截图器执行，LLM 不再每轮写 6600 字符的脚本（第 9 条的根治版；视口、manifest 命名也一并固定）。
- **K24 [nice]** 刷新档位依赖 implementer 自报 kind。有了 K9 的本轮改动路径，可以按 args 声明的路径规则在脚本侧推导，自报只作兜底。
- **K26 [nice]** 「控制台 / 网络错误 func 必判 must」：开跑前就有的无害报错（如 favicon 404）会变成永远关不掉的 must。和第 20 条同一个机制：按「这个态上一轮 / 第 0 轮没有、这一轮有」判，旧报错不自动立 must。

### G. 「默认评审角度数可以减」的证据够不够（给方向题用）

两次 run 的台账里，按 lens 数确证 must（排除截图配方问题、刷新失败这类非界面缺陷）：

| lens | run A must | run B must | 与别的 lens 重复的 |
|---|---|---|---|
| newbie | 5 | 4 | A：灰三角 ≈ rival-r1-2；可见范围 ≈ ux-r1-1。B：TVGN 右缘 ≈ rival-r3-1 |
| rival | 2 | 2（另 1 条是配方） | 见上 |
| razor | 1 | 2（另 1 条是配方） | 无 |
| ux | 1 | 1 | A：视口截断，func / razor / rival 各有一条 nice 说同一件事 |
| func | 0 | 0（唯一 1 条是配方） | — |
| code | 0 | 0（唯一 1 条是 infra-r02，脚本插入） | — |

- 能说明的：在这两次 run 上，func、code 两个 lens 一条确证的界面 must 都没出过；能独立撑起 must 的是 newbie、razor、rival、ux。
- 不能说明的：两次 run 是同一个静态 HTML 原型（无后端、无数据刷新），目标是术语与心智负担，rubric 也是为此写的。func / code 在有后端逻辑、有真实数据的应用上是否同样空转，这两次 run 给不出证据。所以证据只够支持「这类以界面文字和读法为主的需求，可以不默认带 func / code」，不够支持「通用默认值减少」。
- 另：code lens 在新设计里如果还承担「给 implementer 写根因与修法」的职责（nextStepPlan），减掉它要同时决定这份职责去哪。

### F. 测试外壳

**K25 [must，给 tester] 顶层 return 引入后，现外壳会在解析期就挂。**
- 现外壳 `await import(<模板拷贝>)`；顶层 return 在 ES module 里是语法错。外壳要先把 `export const meta` 改成 `const meta`、整体包进 async 函数再执行，并拿到 return 值断言。
- 外壳的 `parallel` 用 Promise.all；真 runtime 里某个 thunk 抛错时该位置为 null、整体不抛。外壳要按真语义实现，否则测不出 K7 这类问题。

## 二、design.md 初稿审查（第 1 轮）

总体：K1～K26 的处理我逐条核对过，绝大部分落实得比我建议的更彻底（确定性截图器、journal 回放、签名、子项负责角度校验、disputed 机制、try/catch + 脚本渲染 SUMMARY）。下面只列还要改的。

### must

**R1 后端重启会把旧进程当成新进程（§2.9 verify 第 3 步）。**
- 现写法：detached 启动 restartCmd，「最多等 60 秒让它退出」，再轮询 healthUrl 到 200。没有任何一步杀旧进程。
- 失败场景：`examples/path2.md` 的 restartCmd 是 `uv run python -m path2_web.main`，一个常驻服务、自己不杀旧进程。新进程因端口被占立刻退出 → healthUrl 由**旧进程**答 200 → `refresh.ok=true` → 评审看的是没重启的旧后端 → implementer 的后端修复被判「没修好」，白跑若干轮，结论失真。（旧模板靠 refresh agent 按提示自己 `lsof -ti:<port> | xargs kill`；改成确定性程序后这一步没人做了。）
- 改法：verify 自己按 healthUrl 的端口找监听进程号（`lsof -ti:<port> -sTCP:LISTEN`），kill 后等端口释放，再 detached 启动 restartCmd（不等它退出），轮询到 200 **且**监听进程号已不是旧的。restartCmd 的契约写进 SKILL：「启动服务的命令，可以常驻」。加测试 W8：起一个小 node http 服务占端口，跑 verify --kind backend，断言监听进程号变了。detached 子进程在 verify 所在 agent 结束后能否存活，加进 §4 实测。
- 正常放过：frontend / none 轮不受影响；restartCmd 本身就「先杀再起再退出」的项目，我们先杀一次也无害。

**R2 截图失败的态上也能判「达成」「已修好」（§2.6 reduceRound）。**
- accept() 只校验 unverifiable 的申报，`met` 和 `gone` 完全不看本轮截没截到。
- 失败场景：G6 的 states 是 `14-b`，本轮 14-b 截图失败（expect 不符或页面报错），评审 prompt 里没有这张图，负责角度凭印象给 G6 `met`、给 14-b 上的旧 must `gone` → 子项达成、条目关闭 → 可能当轮 `converged`。这正是 K4 的对称口子。
- 改法（只在 okSet 已知时）：子项声明了 states 而本轮一个都不在 okSet → `met` 降为 `unverifiable`（requiredStates = 这些态）；条目有 `state` 且不在 okSet → `gone` 不生效，记进 rec.untabled（或新字段）。
- 正常放过：态都截成功时与现设计完全一样。

**R3 implementer 的 summary 发给了全部评审，包括 newbie（§2.11 评审 prompt 第 6 项）。**
- 旧模板只让 code 看 diff，没有任何评审看得到 implementer 的自述。新设计把「本轮 implementer 的 summary（≤1500 字）」放进所有角度的证据段（第 8 项才区分 newbie）。
- 后果：评审被「已修好 X」的自述锚定，倾向判 gone / met；newbie 的「第一眼」直接被污染。这是 lead 点名要守的 (b) 类「评审独立、证据由被评方以外的人采集」。run B 的 ux-r03 就记过「impl.md 说已选中，和截图不符」——说明评审确实会读到并受它影响，那次只是碰巧拆穿了。
- 改法：summary 与改动文件只给 code（要看 diff 的意图）；其余角度只拿截图、manifest、探针。

**R4 续跑的 seed 让 LLM 原样抄写整份压缩台账（§2.4、§2.6 toSeed）。**
- 体量：toSeed 对开着的条目给全字段（detail、evidence、attempts）、方向题全量。run A 规模：49 条开着的条目 + 22 条方向题，加上第 14 条存进的正文，估计 6 万字节以上，约 2 万输出 token；错一个字符哈希就不符 → BLOCKED，没有重试，续跑直接失败。
- 首选改法（前提 L1 证实 scriptPath 可用）：`wl.mjs init` 把 seed（以及 args）作为字面量写进 `<W>/workflow.js` 的 SHELL 段，同时写 `<W>/seed.json` 供回放。删 seed agent 和 argsHash 校验——没有任何 LLM 抄写，也就不需要哈希。
- 退路（scriptPath 不可用时）：seed 只带精简版——开着的条目 id / lens / title / severity / state / unverifiable / requiredStates / detail（≤300 字）/ 最近 3 次 attempts；fixed 只带 id / lens / title / state / fixedRound / disputed；方向题只带标题（全文已在上一次的 SUMMARY 里）；哈希不符时换一个新 agent 重试一次。

**R5 不退回的收尾要能一步回到「最后一个绿的状态」，Q1 要把另一选项写成它最好的样子。**
- (i) 在 blocked、max-rounds、budget、error 任一出口下，只要最后一轮 smoke 是红的，工作区就停在坏的状态。§2.12 第 14 节「怎么人工退回某一轮」只是通用说明。要求：这种情况下 SUMMARY 的「需要你做的事」第一条写明「最后一个 smoke 绿的快照是 rK」和那条具体命令（已按 `git diff --name-status rK.tree <当前>` 算好路径）。
- (ii) Q1 选项 2 写的是清单原版的回滚（撤一整轮、要处理主会话的修改）。我在 K1 / K9 提的版本没有这两个代价：只撤本轮 implementer 前后快照之间变了的路径，statesPath、rubric、workdir 豁免；撤完再跑一次 smoke——仍红说明是环境问题，就把改动放回去并以 blocked 结束，变绿才确认是回归。Q1 要按这个版本写代价，并注明用户自己的分类原则把「回归检查和回滚」列在结构性、要保留。否则用户是在一个被弱化的对照项上做决定。（两种都可以选，我不坚持回滚，只要求比较公平。）

**R6 主会话「看一眼 r00 截图」不能是读 21 张 2560 宽整图（§2.3 第 3 步）。**
- 主会话是长寿上下文。21 张图约 3 万多 token，读进去以后这次会话后面的每一轮都要按缓存读取再计费。
- 改法：capture.mjs 顺手出一张总览图 `shots/r00_contact.png`（同一个浏览器里渲染一个带态名的缩略图网格页再截一张）；主会话看总览图，只对没写 expect 的态或看着可疑的态再读整图。SKILL.md 照此写。

### nice

- **N1（K18 再提）**：impl 返回 null 且 `snap.changed` 为空、statesPath 文件也没变时，本轮评审结果必然与上轮相同。可以跳过评审，按「跳过轮」计（skipReason「本轮无改动」），省一整轮评审（run B 每轮约 30 万输出 token）。
- **N2**：computeNewErrors 按「上一份为空、这一份非空」判，已经有一条旧报错的态再冒新报错会被漏掉。改成按报错文本集合比较：这一份里有、上一份没有的文本算新报错。
- **N3**：verify 跑 smoke 前先探一下 url（和 healthUrl），不通就以「环境」跳过、不立 wf-smoke。否则 dev server 挂了时，下一轮 implementer 会去「修」一个与代码无关的 smoke 失败（甚至改 smoke 脚本让它过）。
- **N4**：`GIT_INDEX_FILE` 用绝对路径；verify 结果里的 `snap.changed` 截断到前 50 条加总数，限制转交长度（本仓库 `.playwright-mcp/` 这类未忽略目录会让列表很长）。
- **N5**：wfId 丢了时 status / export 找不到 journal。可以自动发现：遍历 journal，找 verify 结果里 manifest 路径以 `<W>/shots/` 开头的那一份，唯一即用。
- **N6**：两处耗时可能撞上限：init（smoke 基线 + r00 截图，path2 的 smoke 是 pytest + vue-tsc + vitest）可能超过 Bash 的 10 分钟上限；verify 一条命令同理，且 agent「卡住」超时只看模型有没有动静，命令行里的进度输出要等命令结束才回到 agent，并不能防超时。建议 §4 加一个「单条 Bash 跑 4 分钟」的实测，init 支持分步。
- **N7**：子项在负责角度的回答里被漏掉（角度到齐、但 subgoals 里没这条）时只会一直是 pending，rec 里没有记录。补一个 `untabledSubgoals`，SUMMARY 里列出。
- **N8（K24 简版）**：kind=frontend 而 `snap.changed` 里有 uiDir 之外的源码文件、且配了 restartCmd 时，verify 自动按 backend 刷新并在结果里注明。一行判断，挡住「改了后端却报前端」。
- **N9**：§5 还缺「默认评审角度数」这道方向题。证据见本文第一部分 G 节：两次 run 里 func、code 没出过一条确证的界面 must；但两次都是同一个静态原型、以文字和读法为主的目标，只够支持「这类需求不默认带 func / code」，不够支持通用默认值减少。外-5 删了 code 的修法字段后，code 的独有职责只剩读 diff 找 bug，这一点也该写进题面。

### 对「脚手架 (a) / 结构性 (b)」分类的核对（lead 交代的两头审）

- 删掉的 (a) 类，证据都站得住：P1（生产零次运行）、treadmill（两次 run 都误报，run B 因此提前结束）、oscillating（回归通道断，结构上走不到，K2）、reviewer_stuck（schema 无 stuck 字段，恒为 false，第 13 条）、stalePrimer 和反锚定说教、goal.md 每轮重读、nextStepPlan 格式。删了它们，我找不到会让 run 白跑或结论失真的场景。被删机制里属于 (b) 的那部分都已保留：「旧问题用 id 表态、不换说法另立」写进了评审判法，「证据必须本轮可定位」也写进了，human-hint 通道保留并且优先级最高。
- (b) 类被弱化的有两处：① 回滚（R5，作为 Q1 交用户拍板可以接受，但题面要公平）；② 评审独立（R3，新加的 implementer summary 下发）。
- 残留的、没有真跑证据支撑的新机制：disputed / dissent（由 K6 推出来的，没有真实案例），以及 verify 签名（有间接证据：persist-r02 自报「手误多填了一个 suggestedFix」，说明 LLM 转交确实会走样）。两者成本都低，我不要求删。

## 三、「台账从 journal 回放」这条依赖（lead 点名重点审）

先核对的事实：
- run A、B 的 journal 已从 worktree 的项目目录挪到主目录的项目目录（N18），说明 journal 所在目录会随会话 slug、会话 id 变。
- 会话目录下的 `workflows/<runId>.json`（运行记录）里有 `args`、`script`、`logs`（全部 log() 行）、`workflowProgress`（每个 agent 的 label、agentId、tokens、`resultPreview`）、`totalTokens`、`agentCount`。`resultPreview` 是截断的，不能代替 journal；`logs` 是完整的。lead 实测最终返回值也存在这个文件里，但 resume 会覆盖它。
- 本机没有设 `cleanupPeriodDays`。Claude Code 默认会清理 30 天前的会话记录；会不会连 `subagents/workflows/` 一起清，我没核实。

**J1 [must] 证据留存不能只靠 journal 原地待着、再加上主会话记得跑 export。**
- 失败场景：主会话上下文被压缩，丢了 wfId；或者用户直接关了会话，没跑 export；或者几周后才想起来「继续」。这时 journal 可能已经挪了目录或被清理掉，ledger.json 从来没生成，续跑和回看都做不了，一整个 run 的评审原文全部丢失。
- 改法：把**原始 journal 文件**复制进 `<W>/journal.jsonl`，不解析、只 cp。由两处来做：
  - `wl.mjs verify` 每轮第一步做（从第 2 轮起，按 J2 的办法找到本 run 的 journal）。不多派 agent，每轮只多一次文件复制。
  - export 开头再做一次，补上最后一轮。
- status、export 优先读本地副本。这样即使 journal 格式变了，原始数据也还在，以后换个解析器就能重读。
- 正常放过：只是每轮多一次 cp。

**J2 [must] 找 journal 不能只靠 wfId。**
- 现设计里 wfId 只活在主会话上下文里，第一次 `status/export --run` 时才写进 run.json。
- 改法：
  - SKILL 第 4 步改成：Workflow 一返回，**立刻**写 `<W>/run.json`（不用等到第一次 status）。
  - wl.mjs 增加按内容的兜底查找：在 `~/.claude/projects/` 下递归找 `*/workflows/*/journal.jsonl`，挑出含有 verify 结果、且 manifest 路径以 `<W>/shots/` 开头的那一份。唯一就用；有多份就报错并列出。verify 每轮自取 journal 也用这个办法（第 1 轮还没有 verify 结果可以对照，所以从第 2 轮起取）。
  - glob 的层级别写死成 `*/*/subagents/workflows/`，改成递归查找 `<wfId>/journal.jsonl`。目录结构已经变过一次。

**J3 [nice→建议] journal 格式变了怎么办，要有不依赖它的最小留痕。**
- 现设计的兜底是顶层返回值里的 compactLedger。但返回值所在的运行记录会被 resume 覆盖；回放也只在 run 正常走到 return 时才有。
- 补两条：
  - ① 脚本每轮结束 `log()` 一行紧凑记录（轮号、出口相关计数、本轮新增 / 修好 / 重开的 id）。运行记录的 `logs` 字段会完整保留它，不依赖 journal 格式，异常中断时也有。
  - ② export 解析失败时，报出第一处不认识的行，并告诉主会话退回运行记录里的 logs 和返回值。
- §6 残留风险第 1 条按这三层改写：本地原始副本、运行记录、返回值。

**J4 [nice]** `status` 是在 run 进行中读 journal，最后一行可能只写了一半，解析失败时要跳过这一行，不能报错。

**R1 补（lead 实测后）**：nohup + & 或 setsid 起的后台服务在子代理结束后仍活着；run_in_background 起的会随子代理一起死；`$!` 拿到的是外层包装 shell 的进程号。所以：
- verify 用 node `spawn(..., {detached:true, stdio:[ignore, logfd, logfd]})` + `unref()` 起 restartCmd（等价 setsid），kill 旧进程只按端口查监听进程号；「新进程已接管」也按端口查监听进程号，不用 `$!`。
- **N10 [nice]** 前台 `sleep N` 会被 Bash 工具拦下。所有等待、轮询都写在 wl.mjs 里用 node 定时器；SKILL 和 `.web-loop-refresh.md` 的写法指引里不要出现 shell `sleep` 轮询（`.web-loop-refresh.md` 第 3 步用 `curl --max-time` 等 SSE，没问题）。

## 四、design.md 修订版审查（第 2 轮）

### 已解决

- 回滚保留，确定性实现（§2.9 verify 第 2 步）：只退本轮 changed 路径、豁免配方 / 标准 / 运行目录；退后复跑 smoke，区分「本轮改坏」和「环境坏」；envBroken 时放回改动，以 blocked 结束；wf-regress 被关闭不算进展；W4b、W4c 测试到位。K1、K9、R5 都已解决（R5(i) 由 restore 命令和 lastGreenRound 覆盖，R5(ii) 因回滚保留而不再适用）。
- 「新子项达成」按历史最高计（bestMet），D30 测它。
- 第 26、27 条（冻结 rubric、角度专节检查）、§1.5 分类表：没有问题。

### 第 1 轮的 must 仍未进修订版（可能是消息时间差，逐条核对过原文）

- **R1**：§2.9 第 3 步原文仍是「启动 restartCmd……最多等 60 秒让它退出……轮询 healthUrl」，没有杀旧进程，也没有确认端口换了主人。要按 R1 和「R1 补」改。lead 实测：nohup / setsid 起的进程能活过子代理；`$!` 不可靠，只能按端口查。
- **R2**：§2.6 reduceRound 的 subgoals 和 known.gone 仍不看 okSet。
- **R3**：§2.11 评审 prompt 第 6 项仍把 implementer summary 发给所有角度，包括 newbie。
- **R4**：仍是 seed agent 加哈希。lead 已确认 scriptPath 可用，首选方案（init 把 seed 和 args 写进 `<W>/workflow.js`）可以直接做。
- **R6**：§2.3 第 3 步仍是「主会话看一眼 r00 截图」，没有总览图。
- **J1、J2**：§2.10「找 journal」仍只靠 wfId 加写死层级的 glob，run.json 也仍在第一次 `--run` 时才写，没有本地 journal 副本。

### 新增 must

**S1 签名对不上时，本轮不得以 converged / evidence-gap 结束。**
- 现设计：sig 不符时 okSet=null，`accept(R)` 退化成「只要点名了态就采信」；R2 要加的「失败态上不能判达成 / 修好」也只能在 okSet 已知时执行。§4 又写明 verify 用 Explore，「模型弱一点也无妨」——签名失配会更常见。
- 失败场景：某轮 verify 转交走了样 → okSet 未知 → 负责角度在实际截图失败的态上判 met、把真 bug 标成 unverifiable → 当轮 converged 或 evidence-gap。
- 改法：出口 a、b 都加条件 `sigOk`。sig 不符的轮照常评审、照常记账，只是不能从这一轮收尾，下一轮再判。
- 正常放过：签名对得上时毫无影响。

**S2 verify 交回的那一行要短，长内容放文件。**
- 现在这一行带着 smoke 末尾 40 行（`tail`，常含引号、反斜杠、ANSI 颜色码）、完整的 `changed` 列表、每个失败态的报错原文。LLM 逐字转交这种内容最容易走样。
- 失败场景：某轮改坏 → verify 回滚成功 → 交回的行里 tail 有颜色码，转交时丢了一个转义 → sig 不符 → 「脚本条目只在 sigOk 时执行」→ **wf-regress 没立**。下一轮 implementer 不知道自己上一轮的改动已被退回，也拿不到 rejected.diff 的路径。lastGreenRound 也没更新。
- 改法：wl.mjs 把完整结果写进 `snap/rNN.verify.json`；交回的行只留脚本判定要用的字段（round、kind、snap.ok、smoke 的 pass / rolledBack / envBroken、refresh.ok、okStates、失败态名、新报错态名、该文件路径、sig），全部是短 ASCII 或态名。wf 条目的 detail 写「详见 snap/rNN.verify.json」，implementer 和评审去读文件。
- 正常放过：语义不变，只是行变短。

### 新增 nice

- **S3（回滚前先复测一次）**：smoke 红时，先在原样的改动上再跑一次 smoke，仍红才退回。现设计里一次偶发失败（时序抖动）会走「退回 → 复跑变绿」，被判成本轮改坏，整轮 implementer 的工作被撤掉。多跑一次 smoke 只发生在红的时候。
- **S4（Q2 题面）**：rival 在两次 run 里各有 1 条别的角度没报成 must 的问题（run A：`buy not_in n` 把「没判断」算成「没有」，razor 只记了 nice；run B：悬停里把 buy 叫成「正例」）。两条都是「同一概念两种说法」，正是这类需求的核心。按「独有 must」数：newbie 约 6、razor 3、rival 2、ux 2、func 0、code 0。Q2 推荐的「界面读法类 → ux、newbie、razor」去掉了 rival，题面应写明这个代价：去掉 rival 就少了专门查术语一致性的那双眼睛。
- **S5**：§4 L2 只核对评审用 Explore 时的模型。verify、seed 也用 Explore，若它固定用更弱的模型，L4 验收里要统计 verify 的签名失配次数（第 3 项已有「sig 都校验通过」，保留即可）。

## 五、第 28 条「原型模式」与 lead 两条新事实（第 2 轮补充）

### 原型模式（清单第 28 条）

**T1 [must] 「方案层只能提方向题」的边界要按产物判，不能让 implementer 按意图自己判。**
- 现写法：方案层 =「改数据长什么样、系统算什么、用什么词」，界面层 =「布局、配色、文案」。「用什么词」和「文案」正好重叠。而两次 run 的 must 大多是术语类：run A 的 `buy not_in n`、run B 的「正例」、`labels` 与 `label`。
- 失败场景 ①（过严）：implementer 把改词都当方案层，只提方向题、不改 → 评审的 must 原样开着 → 连续 2 轮没进展 → stalled。整个 run 只产出一堆方向题，出口标签还不对。
- 失败场景 ②（过松）：implementer 把改数据字段的含义当「文案」顺手改了 → 违反规则，而且没有任何一道检查拦得住。
- 改法：按产物划界，写进冻结的 rubric。
  - 方案层 = ① 原型模式 args 里声明的「方案文件」（演示数据文件、模拟逻辑所在的文件，例如 `data.js`）里的字段与计算；② rubric「已定决定 / 术语表」里列出的词。
  - 界面层 = 其余一切，包括术语表以外的文案。
  - verify 已有 `changed` 路径：本轮改到方案文件 → 交给后端要求一致性角度去核对（见 T4），不靠 implementer 自报。

**T2 [must] implementer 要有「这条要拍板，我不能改」的正式出口，出口要单列。**
- 现 IMPL_SCHEMA 没有 directions 字段，implementer 想提方向题只能写 toMain 或硬改。
- 被它挂起的 must 若照常算确证 must：挡收敛、无进展 → 2 轮后 stalled。白花 2 轮，结论还写成「卡住了」，其实是「等你拍板」。这正是第 28 条第 5 点「短跑 + 拍板 + 再跑」该有的收尾。
- 改法：
  - IMPL_SCHEMA 加 `deferred: [{issueId, direction:{title, options, recommend}}]`。脚本把对应条目标 `needsDecision`，方向题入 directions。
  - 出口加 `decision-gap`：本轮可评审、角度到齐、sigOk，除 needsDecision 外的确证 must 为 0。与 evidence-gap 同级，SUMMARY「需要你做的事」列出这些方向题。
  - 防滥用：只有 T1 定义的方案层问题能挂起，`issueId` 对应条目的 state 或 files 要落在方案文件或术语表上，否则不采信、照常算确证 must，记进 rec。
- 正常放过：真实应用模式下不启用 deferred。

**T3 [must] 后端要求清单不能放在 workdir 里。**
- 现写法是 `<workdir>/backend_contract.md`。workdir 被 `.gitignore` 忽略，又在回滚的豁免名单里。
- 失败场景：某轮改了演示数据字段并同步更新了清单 → smoke 红 → 代码被退回，清单没退 → 清单描述的是已被撤销的字段。下一轮一致性角度对着「清单 ≠ 代码」立 must，implementer 再改回去，白跑一轮。
- 改法：清单放在原型旁边、不被忽略的位置（如 `<原型目录>/backend_contract.md`），随快照一起退回。export 和 SUMMARY 指向它。

**T4 [must] 「后端要求一致性」角度的 must 只能是「代码与清单不一致」。**
- 现写法让它挑两类：模拟逻辑悄悄变了；原型展示了后端拿不到的数据。后一类和「不做的事：不判断后端做不做得到」自相矛盾，而且 implementer 修不了。
- 失败场景：一致性角度每轮立几条「后端可能拿不到 X」的 must → 开着 → stalled（或在 T2 之下全部挂起）。
- 改法：
  - must 只限「本轮 diff 改了方案文件，清单没跟上」或「清单里有、代码里没有」。这两种 implementer 能修。
  - 「后端可能拿不到」一律进 directions。

**T5 [nice] 模式本身是主会话判断的，判错代价大，要显式化。**
- 真实应用被当成原型 → implementer 被禁止改数据和逻辑 → 真 bug 修不了。
- 改法：args 加 `mode: "app" | "prototype"`，init 校验；开跑前给用户点头的摘要里写明模式。

**T6 [nice] 原型模式默认角度去掉了 ux 和 rival，代价要写进 SKILL 说明。**
- ux 在两次 run 里的独有 must（视口截断、档位签互压），newbie 各有一条相近的，大体覆盖得到。
- rival 的两条独有 must 都是「同一概念两种说法」（`buy not_in n`、「正例」），别的角度没报成 must，而这恰是原型阶段最在意的术语问题。
- 建议 razor 或 newbie 的专节明确接下「同一个词在两处意思不同」这项检查，否则这类问题会没人管。

### lead 两条新事实带来的改动

**U1 [must] journal 定位不能按 label 认。**
- lead 的探针用「最近 10 分钟改过的 journal + grep 自己唯一的 label」定位成功。但 web-loop 的 label（`verify-r02` 等）在不同 run 之间是重复的。原型模式的节奏是「短跑 + 拍板 + 再跑」，两次 run 前后紧挨、甚至在不同 worktree 并行，都会撞上。
- 后果：复制、回放了别的 run 的 journal → SUMMARY 和 ledger 张冠李戴。
- 改法：按内容认——取 verify 结果里 manifest 路径以 `<W 的绝对路径>/shots/` 开头的那一份（J2 原文）。第 1 轮还没有 verify 结果，就从第 2 轮起复制；export 时再复制一次。

**U2 [nice] 评审若用 Explore，就不读 CLAUDE.md 和用户级 rules。**
- 两样都不进评审的上下文：界面文字风格、词表规范。第 26 条起草 rubric 时要把评审判法用到的规范原文收进 rubric.md，不能写「按 CLAUDE.md」。
- Explore 禁止建文件，所以评审 prompt 里「自裁图写到 `crops/<L>-rNN/`」要删掉，改成「只用 capture 产出的局部图」。配方里小字区域必须声明 crops，init 可以给没有 crops 的态一个提醒。

**N6 关闭（lead 实测）**：前台跑 240 秒的真命令，Bash 设 timeout:300000，正常完成，不会被判卡住。Bash 默认超时 2 分钟、上限 10 分钟，所以剩下的要求只有两条：
- verify 的 prompt 必须显式设 timeout（设计已写 600000）；
- init 若在某个项目上超过 10 分钟（smoke 基线加 r00 截图），要能分步跑，或者主会话改用后台运行。init 的分步记为 nice。

## 六、design.md 第 3 版复核

### 已解决（逐条对过 §1.6 与正文）

R1（按端口杀、detached 起、200 且进程号变了才算成功；W9）、R2（goneIgnored / metDowngraded；D31、D32）、R3（summary 只给 code）、R4（args 和 seed 注入 workflow.js，删 seed agent 与 argsHash）、R5(i)、R6（r00_contact.png）、J1 至 J4、N1 至 N10：处理都到位，测试也都配上了。

### 仍未处理的 must（第 2 轮与第五部分提的，§1.6 没有收录）

- **S1**：出口 a、b 仍不要求 sigOk。sig 不符时 okSet=null，R2 的两道新检查（goneIgnored、metDowngraded）都写着「okSet 已知时」才执行——也就是说，sig 一失配，它们和 accept() 一起失效，当轮仍可能 converged。改法：a、b 加 `rec.sigOk`。
- **S2**：verify 交回的那一行仍带 smoke 末尾 40 行、changed 列表（≤50 条）、失败态报错原文、刷新日志末尾。改法同第 2 轮：完整结果写 `snap/rNN.verify.json`，交回的行只留判定字段，detail 指向文件。
- **V1（新）verify 仍是 Explore。** lead 已转达：Explore 的系统提示明令只读、禁止创建任何文件，而 verify 跑的命令会写 `snap/`、`shots/`、复制 journal。可能的后果是模型拒跑，或只跑一部分——本轮跳过，连续两轮就 blocked。改法：verify 用默认类型加 `effort:'low'`；起步上下文多约 3.5 万，但 verify 只调一两次工具，代价有限。外-6、D26、§4 L4 第 9 项随之改。
- **V2（新）第 28 条「原型模式」还没进设计**（用户已同意并入）。并入时请一起处理 review_design.md 第五部分的 T1 至 T4：
  - 方案层按产物划界；
  - implementer 的 deferred 通道和 decision-gap 出口；
  - 后端要求清单放在会随快照退回的位置；
  - 一致性角度的 must 只限「代码与清单不一致」。
- **U1**：verify 第 0 步只在 run.json 存在时才复制 journal。run.json 要靠主会话手动 attach，忘了这一步，J1 的保护就整个落空。改法：run.json 不存在时，verify 用 findJournal 的第 3、4 步（按 runId 或按 `"<W>/shots/` 内容）去找，从第 2 轮起总能找到。

### nice

- **V3**：url 探测一次不通就 blocked。implementer 改了 dev server 配置会引起几秒重启，这种瞬断也会结束整个 run。建议用 node 定时器重试最多 30 秒再判。
- **V4**：连续两轮 noChange 的出口记成 blocked（「环境或代理一再失败」），名不副实；记成 stalled 更准，SUMMARY 的「需要你做的事」也会对。
- **S3、S4** 维持第 2 轮意见：smoke 红时先原样再跑一次再回滚；Q2 题面写明 rival 两次 run 各有一条独有 must。

## 七、design.md 第 4 版复核

### 已解决

S1（三个收尾出口都要求 sigOk，D38）、S2（短行 + `snap/rNN.verify.json`，约定路径由 CORE 算）、S3（先复测，flaky）、S5、V1（verify 用默认类型加 low）、V3（重试 30 秒）、V4（连续 noChange 走 stalled）、U1、U2、T1、T3、T4（另加的第三类 must「未经拍板改了方案」合理：implementer 退回或挂起都修得了）、T5、T6。第 1 轮的 R、J 系列此前已核对过。

### 剩 1 条 must（编号用 X，避免和 design.md 测试表的 W1～W14 撞名）

**X1 挂起（deferred）只凭 implementer 一方就能生效，而「标题和描述里出现术语表的词」这道防滥用条件在原型场景里几乎拦不住任何东西。**
- 数据：两次 run 的 21 条确证 must（不计脚本插入的条目）里，19 条的**标题**就含有界面标识符（`buy`、`app`、`compare`、`not_in`、`qualified_only`、`move`……）。这些词正是原型 rubric 术语表会收的词。加上 detail，几乎全部命中。其中不少是纯排版问题，例如「档位签互相压住」「move 落在第一张卡正下方」「虚线边压过 qualified_only 签的字」，按 T1 本该是界面层、implementer 自己改。
- 失败场景：implementer 碰到难修的排版 must，把它挂起 → 采信（标题里有 `qualified_only`）→ 本轮新增 needsDecision 还算「进展」→ 当轮 decision-gap 收尾。SUMMARY 把一堆界面层问题当作「等你拍板的方案题」交给用户，run 提前结束，结论失真；而且这条路对 implementer 是最省力的出口。
- 改法（结构性：被评方不能自己豁免 must，与「证据由被评方以外的人采集」同一原则）：
  - 挂起先记为「提议」（如 `needsDecision:'proposed'`）。本轮该条目的**负责角度**在 prompt 里看到这条提议（只给它这一条的标题、选项和理由，不给 implementer 的整份 summary），并在 known 里表态：新增 status `'decision'`（同意：这确实要用户拍板）或照常 `present`（不同意：界面层能修）。
  - 只有 `'decision'` 才置 `needsDecision=true`，才从 confirmedX 里扣除、才算进展；`present` 记进 `rec.deferRejected`（原因写「负责角度不同意」）。
  - 关键词或文件条件可以保留，作为「能不能提议」的前置筛选。
- 正常放过：真正的方案层问题，负责角度在**同一轮**里就会同意（applyImpl 在评审之前，评审当轮就能表态），decision-gap 照常当轮收尾，不多花一轮。

### nice

- **X2**：init 在 contractPath 不存在时生成骨架，只「提醒主会话补齐」。若主会话没补就开跑，第 1 轮 contract 角度会把每个字段都报成「代码里有、清单里没有」，第 1 轮的修改全花在补清单上。建议 init 检测到清单仍是原样骨架时直接拦下。
- **X3**：§2.15 表格「挂起怎么防滥用」一行，按 X1 改完后要同步改写，免得 docs 照旧文抄进 SKILL.md。

## 八、第 5 版复核：可定稿

- X1 已按方案落地：
  - 改动在 §2.6 applyImpl 第 6 步：提议记为 proposed，照常算确证 must、不算进展；负责角度回 `'decision'` 才变 agreed；只扣除 agreed；负责角度缺席时保持 proposed。
  - 出口 b2、§2.7、implementer prompt、§2.15 都已同步。
  - 测试 D36、D37、D40 覆盖了同意、否决、缺席三种情况。
- X2（init 拦下原样骨架）、X3（§2.15 表格同步）也已处理。
- 已同意的条目之后负责角度回 present 仍维持 agreed（不能撤回），这是有意为之：等用户拍板的事不该由评审再翻回去。不算问题。
- 剩下的意见全是 nice。**可以定稿。** 进入第三段（审实施）时，重点核对：回放与运行一致（D25）、回滚的真仓库测试（W4b、W4c）、后端重启（W9）、签名与短行（S1、S2）、挂起表态（D36、D37、D40）是否真跑控制流，而不是在源码里找字符串。
