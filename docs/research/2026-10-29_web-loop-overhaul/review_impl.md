# skeptic 实施审查（web-loop overhaul）

> 路径相对 worktree 根。对照 `design.md` 定稿版与 `review_design.md` 第八部分列的重点。
> 本地重跑：`node .claude/skills/web-loop/tests/run-all.mjs` 一次，加 `test-wl-tools.mjs` 单独三次。

## 测试是不是真跑控制流

抽查 D25（含 tester 加的「每个 debug 场景自动回放比对」）、D36/D37/D40/D42、D38、W4b、W4c、W9：
- 都是真跑外壳或真跑 `wl.mjs`。W 系列在临时 git 仓库里跑，W9 起真的 http 服务、断言端口上的进程号换了。
- 没有只在源码里找字符串的情况。P 系列是 prompt 文本断言，那本来就是它要测的东西。

## must

**I1 verify 在红的路径上会超过 Bash 的 10 分钟上限，被杀在回滚中途（`wl.mjs` cmdVerify）。**
- 现状：每次 smoke 的超时 `SMOKE_TIMEOUT = 6 分钟`。红的路径最多跑三遍 smoke（首跑 → 复测 → 退回后），中间还有后端重启（最多 90 秒）和截图。最坏情况远超 verify agent 那次 Bash 调用的 600000 毫秒上限（lead 实测：上限 10 分钟）。path2 的 smoke 是 pytest + vue-tsc + vitest，单遍几分钟是常态，三遍就会撞线。
- 失败场景：Bash 到点杀掉 node 时正处在 `restoreTo` 之后、「退回后」那遍 smoke 之中，于是：
  - 工作区停在「已退回」的样子，却没有任何结果行 → 这一轮按「verify 未交回」跳过，不立 wf-regress，下一轮 implementer 不知道自己的改动已被撤掉；
  - `rNN.restored.tree` 没写，下一轮的 `preTree` 取到被拒的那棵 `rNN.tree`，算出来的 changed 恰好是「被撤掉的那些路径」——code 评审看到一份反向 diff，再红就会退回到坏的那棵树；
  - `runShell` 起的 smoke 是 detached 进程组，node 被杀后它成了孤儿继续跑，可能和下一轮的 smoke 撞在一起。
  - 这属于「改动被悄悄撤掉、工作区被搞乱」。
- 改法（推荐）：verify 自己脱离 Bash 的生命周期——
  - 前台进程 detached 启动真正干活的子进程（`wl.mjs verify … --worker`），由子进程写 `snap/rNN.verify.json`，最后把短行写进 `snap/rNN.verify.out`；
  - 前台最多等约 9 分钟，等到就打印短行；没等到就打印 `{"pending":true,"round":N}` 并以 0 退出；
  - 新增 `wl.mjs wait <W> --round N`，同样最多等约 9 分钟后打印短行或 pending；
  - verify prompt 加一句「最后一行是 pending 就再跑 wait 命令，直到拿到带 sig 的那行」。
- 正常放过：几分钟内跑完的轮次行为不变，仍是一次工具调用。
- 测试：用一个 sleep 很久的假 smoke 加很小的等待上限（给 verify 和 wait 留一个只供测试用的上限参数），断言先返回 pending、后返回完整短行，且工作区与正常完成时一致。

**I2 截图器偶发「Page.captureScreenshot: Unable to capture screenshot」，没有重试（`capture.mjs` shootOne）。**
- 证据：本机单独跑 `test-wl-tools.mjs` 三次失败一次（W7），跑 run-all 一次失败一次（W4c），都是 init 截 r00 时第一个态的 `page.screenshot` 抛出这个协议错误；同一态重跑即过。按测试里约 34～70 次截图出一次估算，真实 run 每轮 21 个态，平均每 2～3 轮就会碰上一次。
- 失败场景：
  - init 截 r00 时撞上 → 「起点图有失败态」→ 拒绝开跑，主会话以为是配方错了，去修一个没错的配方；
  - 轮中撞上 → 该态记失败 → 立 `wf-state-<态>`（挡收敛），评审看不到这张图（挂在它上面的子项变 pending 或 unverifiable）；下一轮截成功又关掉，**关闭算进展**，停滞计数被假进展清零。
- 改法：只对截图这一步重试（`page.screenshot`、crop 的 `locator.screenshot` 和 clip 截图），最多再试 2 次，每次间隔约 300 毫秒（用 node 定时器），重试次数记进 manifest。步骤、探针、expect 的失败照旧立即判失败，不重试——那是数据，不是抖动。
- 正常放过：第一次就成功时完全不变。
- 测试：tester 那边的 init 类测试目前也会偶发红，修好后跑 10 遍 test-wl-tools 确认不再抖。

## nice

- **I3（docs，`.web-loop-refresh.md`）**：
  - 第 3 步 `curl --max-time 900` 比 Bash 上限 600 秒还长，扫描超过 10 分钟时 curl 会被工具杀掉。改成 `--max-time 540`，并写明超时后回到第 3 步重连（SSE 断开不影响服务端扫描）。
  - 第 1 步「轮询 curl 到 200」容易被写成带 `sleep` 的 shell 循环，而前台 sleep 会被拦。改写成 `curl -sf --retry 60 --retry-delay 1 --retry-connrefused …`。
- **I4（实现）**：kind=data 且用 .md 说明文件刷新时，verify agent 是先刷新数据、再跑命令（快照 → smoke → 可能退回）。若本轮被退回，数据是用被拒的代码生成的，下一轮如果是 frontend 档就不会重刷，评审看到的是旧代码留下的数据。可以在 rolledBack 时把 S.lastKind 记为 data，让下一轮强制重刷一次。
- **I5（实现）**：`journalsByContent` 在没有 run.json 时每轮全量读 `~/.claude/projects` 下 24 小时内的所有 journal。文件大时会慢，可以先按文件尾部几 KB 过滤再整读。

## lead 追加的两项

**(1) 「重启成功 = healthUrl 回 200 且监听进程号换了」够不够。** 结论是 nice：在 SKILL.md 里提醒一句即可，不用改代码。
- 进程号换了，能挡住「旧进程顶着端口」这个真问题（R1）。业务是否就绪，确实取决于 healthUrl 选的是哪个接口。如果选的是只报「进程活着」的 `/health`，而应用启动后还要异步加载数据，截图就可能截到空数据，评审会对着空页面立 must。
- 已有两道兜底：
  - 配方里带 `expect` 的态，在数据没加载时探针对不上，会记为截图失败，这个失败看得见、不会混进评审；
  - path2 示例用的 `/patterns` 本身就要等 pattern 发现完成，才返回数据，属于业务就绪的语义。
- 建议 docs 在 SKILL.md 的 args 表 `restartCmd、healthUrl` 那一行补一句：healthUrl 选「业务就绪后才回 200」的接口，例如返回实际数据的列表接口，不要用只报进程存活的健康检查。

**(2) SKILL.md 写死的命令与源码是否一致。** 逐条核对，全部一致：
- `wl.mjs` 部分：init、attach（三个位置参数）、status、export、`export --from-ledger`、`restore --to green|rNN|r00|before-restore --dry-run`。
- `capture.mjs shoot --workdir --round 99 --only --out` 一条。
- 模板里 implementer 的 intake、自查截图命令，verify 命令（`--no-change-hint`、`--refreshed`），code 评审的 diff 命令，参数名都与 `wl.mjs`、`capture.mjs` 的 parseArgs 对得上。
- 唯一过时的一处：`examples/path2.md` 第 121 行还写着「`impl.md` 首行 `kind`」，impl.md 已经删了，kind 现在由 implementer 的返回值交回（nice，归 docs）。

## 复审 I1、I2、I4、I5（2026-10-30，修复落在 15:17～15:22 之后）

### 已解决

- **I1**：verify 的真活由脱离的 worker 做（`--worker`），结果先写临时文件再改名成 `rNN.verify.out`，最后删锁。前台和 `wait` 最多各等 9 分钟，没等到打印 pending。同一轮已有结果或 worker 还活着时，不会再起第二个。intake 开头会等上一轮还没跑完的 worker，输出里给出 `verifyRunning`。verify prompt 写明「pending 就跑 wait、拿到带 sig 的行之前不要交回」。W16（先 pending、再 wait 拿到完整行、重复 verify 幂等）和 W17（红路径加很小的等待上限：worker 跑完后 rolledBack 结果和 restored.tree 都在、工作区已退回）都是真跑。
- **I2**：`withShotRetry` 只包住截图调用（整页、crop 的 locator 与 clip、失败态留证图、总览图），最多再试 2 次、间隔 300 毫秒，超时类错误不重试，次数记进 manifest 的 `shotRetries`。步骤、探针、expect 的失败不经过它。本地单独跑 `test-wl-tools.mjs` 4 次，20/20 全过；修复前 4 次里有 2 次撞上截图错误。tester 的 10 遍结果还在等。
- **I4**：data 档用 .md 刷新的轮次若被退回，下一轮强制按 data 档重刷（`forceDataRefresh`）。
- **I5**：按内容找 journal 时只读文件开头 256 KB。verify-r01 的结果行在 journal 很靠前的位置，够用。

### 新发现

**M1 [must，tester] `run-all.mjs` 给每个测试文件的超时只有 120 秒，而 `test-wl-tools.mjs` 现在要跑约 140 秒（加了 W16、W17 等真实等待）。**
- 现象：本地跑 run-all，`test-wl-tools.mjs` 跑到 W4c 之后被 spawnSync 杀掉，报「3 通过、1 失败」。单独跑这个文件是 20/20 全过。
- 后果：总入口每次都是红的，而且失败原因看不出来（只打印了已经 PASS 的那几行）。以后真回归和这个假红就分不开了，总入口失去做闸门的作用。
- 改法：把每个文件的超时提到 600 秒（或者按文件名给 test-wl-tools 单独放宽）。超时被杀时，打印一行「超时被杀」。

### nice

- **M2**：implementer prompt 的 intake 那一步没要求 Bash timeout 设 600000。intake 最多会等 9 分钟，可 Bash 默认 2 分钟就超时，所以「等上一轮 worker 结束」实际只等得了 2 分钟。超时后 implementer 可能直接开工，和还在退回工作区的 worker 撞车。只有 verify 代理没等到结果就交回时才会走到这条路，很少见。改法二选一：
  - prompt 里给 intake 也写上 timeout 600000；
  - 或者 intake 自己只等约 100 秒，然后打印 verifyRunning，由 prompt 里已有的「不为 null 就再跑一次 intake」接着等。

### 结论

剩 1 条 must（M1，改一个数字）。它改完、tester 的 10 遍稳定性结果没再出现截图错误，就可以收尾。

## 最终复核：可以收尾

- **M1 已解决**：run-all 的单文件超时改为 900 秒。本地重跑 run-all：4 个文件全过，87 个场景 0 失败，约 147 秒。
- **M2 已解决**：intake 默认只等 100 秒（INTAKE_WAIT_MS，在 Bash 默认 2 分钟以内），没等到就打印 verifyRunning；prompt 里已有「不为 null 就再跑一次」，会接着等。
- **截图抖动**：修复前单独跑 test-wl-tools 4 次，2 次撞上截图错误。修复后 10 次全过、0 次截图错误——我单独跑 4 次、run-all 1 次，implementer 后台连跑 5 次。如果抖动没修好，按原先约一半的出错率，10 次全过的概率约千分之一。tester 的 10 遍结果出来后再补记一句即可，不影响结论。
- 剩余意见全是 nice：I3、M1 里「超时被杀时打印一行」这半句，以及 docs 那两处小改。
- **补记（tester 10 遍结果）**：test-wl-tools 连跑 10 遍，每遍 20/20，没有一次截图错误；run-all 一遍，4 个文件、87 个场景全过。M1 的「超时被杀时标注」也已补上。收尾结论不变。
- **补记（L4 缺陷与轮号核对）**：
  - verify 结果改成字符串，由 CORE 的 verifyLine 解析，签名按解析出的对象核对，复审通过。
  - reviewGate 新增本轮轮号参数，结果行轮号不符时 sigOk=false；SHELL、reduceRound、reviewerPrompt、replay 四处都传了。
  - 本地重跑 run-all：4 个文件、91 个场景全过。
  - 没有新的 must，收尾结论不变。
