# `scan` 档：把扫描结果从 `app` 按钮里拆出来，扫描专用的按键只在 `scan` 起作用

Status: ready-for-agent
Progress: done
Claimed: 2026-11-15 parallel-tickets ticket-13 @ worktree impl/13-scan-tier
Blocked by: none

## Purpose

用户在标注时要分得清「当前 pattern 的 app 在这只股票上现算」和「扫描文件里的结果」，扫描的按键也不能再在标注时抢键、把人踢出标注。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：
  - 1.17（全节）；1.3「三种模式」那条（现为四档）；
  - 5.1；
  - 5.2「顶栏」的 `mode`、「切档时股票怎么带」、`ref`；「左栏」的最后两条（只藏不拆、扫描专用的按键和控件只在 `scan` 档）；
  - 5.8 开头一段（`scan` 档同样适用）和「键位」那条；
  - 第 9 节「端到端」的最后两条；
  - 第 10 节「`scan` 档没加载扫描时」「进出 `scan` 时股票怎么带」两行。
- 研究报告 `docs/research/2026-11-11_annotation-scan-page-layout/final_report.md` 第 5 节（方案形状）、第 8 节（K1～K5 五处毛病），`inventory.md` 第 1、2 节（各区域在四种状态下长什么样）。只作参照，实施产出不得引用（共用边界第 4 条）。

## Inherited Direction

- 共用执行边界（[拆分总览](../ticket-breakdown.md)「各票共用的执行边界」），第 11 条「截图」改照用户现行规则：不调 `browser_resize`，截图一律 `scale="device"`，看整体布局用 `fullPage=True`，看单个组件用 `fullPage=False` 加 `target`；用完清空 `.playwright-mcp/`。
- **只在界面上拆按钮**（spec 5.2「顶栏」）：`scan` 按钮就是原来「`mode = app`、来源是扫描」那个状态，`app` 按钮是「来源是现算」。图表状态里 `mode` 和 app 来源这两样的表示不改。理由：读这两样状态的地方遍布顶栏、图表状态、K 线图和十几个测试文件；把 `scan` 做成 `mode` 真正的第四个取值，这些都得改，换来的行为一样。
- **扫描视图原样不动**（spec 1.17 第 1 条）：扫描文件里的产物、扫描窗口的 K 线、扫描的 active pattern、Working Copy、诊断侧栏、拓扑面板都不改。前提是扫描界面只是偶尔用的调试工具（用户确认过）。
- **不推翻 spec 5.1**：四档共用同一个图组件、同一份图表状态和同一套画法。防的是标注和显示两套画法，标完对不回来（票 01 第 1 节）。
- **不改 V-S1 验收的对象**：标注格式、`compare` 的画法、反馈、直达链接、改版报告里的链接都不动（研究报告第 6 节）。
- **扫描文件不做兼容**（`.claude/rules/scan-file-no-backcompat.md`）：测试用 e2e 自己造的小扫描（`path2_web_ui/e2e/smallScan.ts`），不为主目录里打不开的旧扫描写任何适配。

## What to build

- **顶栏 `mode` 四档**：`annotate` / `compare` / `app` │ `scan`，`scan` 和前三档之间隔一道竖线。
  - `app` 只进现算。当前 pattern 没有 app 时 `compare`、`app` 都变灰。
  - `scan` 进扫描视图，加载扫描后自动落在 `scan`（今天就是这样）。
  - 各按钮的悬停照界面文字规则写。
- **`no_scan` 空状态**：没加载扫描时 `scan` 也能点，左栏是扫描面板和空列表，图区空着、写 `no_scan`，股票不带过去。删掉当前扫描时也落在这里，不再踢回 `annotate`。
- **进出 `scan` 时股票怎么带**：照 spec 5.2「切档时股票怎么带」的三条做。前三档之间切换照旧不换图。
- **扫描专用的按键和控件只在 `scan` 档起作用**（spec 5.2「左栏」最后一条，对应研究报告的 K1～K5）：
  - 扫描列表的「敲字母搜股票」；
  - 扫描列表的 PageUp / PageDown 切股；
  - Shift+P 打开参数抽屉；
  - 扫描的休眠草稿横幅；
  - 另外，从扫描列表选股时清掉打开时给定的图窗。
  
  这几处在今天的代码里的位置以研究报告第 8 节为线索，开工时重新 grep 定位，行号已经变了。
- **左栏内容本票不换**：前三档的左栏仍是扫描面板和扫描列表。在前三档点扫描列表的一行，照旧进到 `scan` 看那只。左栏换成找图清单是票 14 的事。
- **说明书** `.scratch/annotation-path2/manual.md`：
  - 「四、界面一览」顶栏表 `mode` 一行改成四档，写清 `app` 与 `scan` 的分别；
  - ⑤「对照」里「`mode` 切到 `app`」那段，以及「主视图的诊断侧栏」这几处，改成指 `app` / `scan` 档；
  - 照现有写法，只写现在的界面，不写开发历史。

## Scope and exclusions

- 不换左栏内容，不碰大涨段清单与 `random`（票 14）。
- 不改扫描视图本身，不改扫描的后端与扫描文件格式。
- 不改图表状态里 `mode`、app 来源的表示。
- 不做 `compare` 下左栏显示 app 与标注是否一致（spec 1.17 之外，研究报告 7.2 留给第二段）。
- 不修 diagnose-event 只认扫描文件的缺口（研究报告第 8 节，与本票无关）。
- 单字母快捷键不改，仍是 `Shift+B` / `Shift+F`。

## Blocked by

none

## Acceptance criteria

- 开工前在本票 worktree 里跑一遍前端单测和 e2e 全套，把失败清单存进 `evidence/13/` 作基线（研究报告说「扫描→标注」的两条 e2e 早就是红的，以实测为准）。完工后再跑：单测全过，e2e 比基线没有新增失败。
- 顶栏：四个按钮都在，`scan` 前有竖线；没有 app 时 `compare`、`app` 灰、`scan` 可点；有 app 时点 `app` 进的是现算（顶栏写着 app 名），点 `scan` 进的是扫描视图。组件测试各一条。
- `no_scan`：没加载扫描时点 `scan`，图区写 `no_scan`、股票不带过去；在 `scan` 里删掉当前扫描，同样落到 `no_scan`。各一条测试。
- 进出 `scan` 的股票规则，每种情形各一条测试：
  - 当前股票在扫描文件里，进 `scan` 后还是它；
  - 不在，落到扫描列表上次停的那只；
  - 在 `scan` 里点过扫描列表的行 B，回前三档是 B；
  - 没点过，回到进 `scan` 前的 A；
  - 从 `no_scan` 回去，也是 A。
- 扫描专用的五处，每处两条测试，一条拦、一条放：
  - 前三档里不起作用：敲字母不进搜索框，PageUp / PageDown 不切股、不离开当前档，Shift+P 不开抽屉，`compare` 里没有休眠草稿横幅；
  - `scan` 档里照旧：敲字母搜股票，PageUp / PageDown 切股，Shift+P 开关抽屉，横幅照常出现；
  - 从扫描列表选股后切回 `annotate`，图窗不再停在上一只股票的日期段上。
- 读 `mode`、app 来源的现有单测，不因本票改动而改写。如果必须改，在完成记录里逐个列出并说明为什么。
- 截图存进 `evidence/13/`：`annotate`、`app`、`scan`、`no_scan` 四种状态的整页截图各一张。
- 说明书改完，`grep -n '主视图' .scratch/annotation-path2/manual.md` 剩下的每一处，在完成记录里写明指整个页面还是哪一档。
- 改动的文件里 grep `docs/research` 结果为空。
- `未安排人审：四档的排法、no_scan 空状态、进出 scan 时股票怎么带顺不顺手；原因：这些只影响怎么切换，不改存下的标注，也不进任何成绩，没有 build-on point；用起来不顺就改 spec 第 10 节的默认`

## 完成记录

2026-11-15，parallel-tickets ticket-13。合并提交 c833c29（`--no-ff` 合回 `annotation-path2`）。
- 独立审查在提交 105d280 上做；
- 合进新的调度分支后，在 ab008ac 上重跑了单测和 e2e；
- 合回前最后一次提交 e4dacb6 只删了完成记录草稿，代码与 ab008ac 相同；
- 合并后的树与 e4dacb6 相同。

**暂停与恢复**
- 第一次准备合回时，主目录有别处没提交的「Delete 删反馈」改动，其中 `ChartArea.vue`、`manual.md` 两边都改了，所以暂停，提了 [Q01](../questions/Q01-main-dir-blocks-merge.md)。
- 用户选 A；那批改动提交为 7c912cf 后恢复。
- 把调度分支（9caa577）合进票分支（ab008ac），git 自动合并，没有冲突：
  - 两处 `ChartArea.vue` 的改动一个在 Shift+P、一个在 Delete，互不相干；
  - 7c912cf 改的 spec 条文是 5.8「副图有高度上限」那条和 6.13 的删反馈，不在本票引用的条款里，本票条款没变。

**做了什么**
- 顶栏 `mode` 四档 `annotate` / `compare` / `app` │ `scan`，`scan` 前一道竖线（`TopBar.vue`）。
  - `app` 只进现算；当前 pattern 没有 app 时 `compare`、`app` 都灰，`scan` 随时能点。
  - 悬停：`app` 写「现算、不是扫描文件」；`scan` 写扫描文件名，没加载扫描时写怎么加载。
- 图表状态的表示没改（照票的方向「只在界面上拆按钮」）：`scan` 档就是 `mode = app`、来源是扫描。view store 新增派生量 `scanView`（是不是 scan 档）、`noScan`（scan 档但没加载扫描），新增动作 `enterScan`。
- 进出 `scan` 时股票怎么带（view store）：
  - 进：当前股票在扫描文件里就留着，不在就回到扫描列表上次停的那只；
  - 出（`enterAnnotate`、`enterLinked` 从 scan 档出来时）：在 scan 档里从扫描列表选过股就带着那只，否则回到进 scan 前那只；
  - 按代码打开、`random`、`rally`、链接离开 scan 档时，落在给的那只，记账清零。
- `no_scan`：没加载扫描时点 `scan`，图区盖一层写 `no_scan`，股票置空；在 scan 档里删掉当前扫描也落在这里（原来是踢回 `annotate`）。档位条、拓扑、诊断侧栏照扫描视图原样出现（空的）；K 线图在没有股票时清掉上一只的图。
- 扫描专用的五处只在 `scan` 档起作用：
  - 扫描列表的敲字母搜股票、PageUp / PageDown 切股（`SidebarResultList.vue`）；
  - Shift+P 参数抽屉，离开 scan 档时抽屉关上（`ChartArea.vue`）；
  - 休眠草稿横幅（`ChartArea.vue`）；
  - 从扫描列表选股时清掉打开时给定的图窗（view store `selectSymbol`）。
- 左栏内容没换：前三档仍是扫描面板和扫描列表，在前三档点列表的行照旧进到 scan 档看那只。
- 说明书 `.scratch/annotation-path2/manual.md`：
  - 「四、界面一览」`mode` 一行改成四档，写清 `app` 与 `scan` 的分别、进出 `scan` 怎么带股票、扫描专用按键只在 `scan`；
  - ⑤「`mode` 切到 `app`」那段、反馈「在哪做」、选中与按键、显示栏、侧栏 `hits` 列表、档位按钮出现在哪几档，改成指 `app` / `scan` 档；
  - 「为什么带 Shift」改成 `scan` 档的扫描列表会接走单个字母。

**验收**
- 顶栏、`no_scan`、股票规则、五处按键与控件：
  - 组件测试 `path2_web_ui/tests/components/scan-tier.spec.ts`，13 条：
    - 四个按钮与竖线；
    - 没 app 时灰、`scan` 可点；有 app 时 `app` 是现算、`scan` 是扫描；
    - `no_scan` 两条（点 `scan`、删掉当前扫描）；
    - 五处按键与控件中前四处各拦、放一条（敲字母、PageUp / PageDown、Shift+P、横幅）。
  - store 测试 `path2_web_ui/tests/stores.scan-tier.spec.ts`，17 条：
    - scan 档的表示一条；
    - 票列的五种进出情形各一条，另加前三档点行、进 scan 前没开着股票、加载扫描、前三档互切、按代码打开离开 scan；
    - `no_scan` 四条；
    - 图窗的拦、放各一条，即第五处。
  - 拦的四条做过反向核对：去掉门控后，四条都变红。
- e2e `path2_web_ui/e2e/scan-tier.spec.ts`，2 条（spec 第 9 节「端到端」最后两条）：
  - 四档切换与进出 scan 的股票规则、没加载扫描落在 `no_scan`；
  - 扫描专用按键在前三档不起作用、scan 档照旧，横幅不出现在 `compare`。
  - 扫描在测试后端上现跑：bo_only，AAPL / NVDA / AMD 三只。
- 单测：开工前 1635 条里 4 条红，都在 `components.sidebar-result-list.spec.ts`：
  - 真坏的只有一条：tooltip 那条断言 `75%`，组件现行写法是保留一位小数（`75.0%`），组件自己的测试 `components.pattern-stats-tooltip.spec.ts` 就断言 `75.0%`。
  - 另三条「global char forwarding」是它没卸载留下的实例连带红的，单跑都过。
  - 改了那条断言后，提交 105d280 上 `npx vitest run` 1665 条全过；合进调度分支后在 ab008ac 上 1671 条全过（多出的 6 条是 7c912cf 带来的）；两次 `npx vue-tsc -b` 都通过。
- e2e 全套对照，基线和完工后用同一种跑法：
  - 跑在分离的干净 checkout 里，端口另开；
  - 去掉 miss-detection-walkthrough，它读 `datasets/pkls`，越过数据墙；
  - 依赖已不存在的旧扫描（2026-06-30、BTMWW）的 6 个 spec 另跑一轮，单条超时 30 秒，不然要白等 5 个多小时；
  - 脚本 `evidence/13/e2e_run.sh`，清单 `evidence/13/e2e-baseline.txt`、`e2e-after.txt`（105d280）、`e2e-merged.txt`（ab008ac）。
  - 主体：
    - 基线 51 条，38 过 13 红；
    - 105d280 上 53 条，40 过 13 红。红的 13 条与基线逐条相同，都卡在开头等一个现在已不存在的「底部反转突破爆发」下拉；多出的 2 条是本票新加的，都过。
    - 合并后 ab008ac 上第一遍 14 红：多出的是 7c912cf 改过的 `feedback.spec.ts:585`。它在「面板开着时点另一个 ▼，面板应关掉」那一步红了，面板仍开着。单跑 5 遍都过；整套再跑一遍，回到 13 红，与基线逐条相同，这条也过了。这一步点的是 compare 图上的 ▼，本票没动 compare 的画法和点击，判为偶发。
  - 旧扫描那组：基线、105d280、ab008ac 三次都是 27 红 4 没跑，失败清单逐条相同，都是点不到历史里那份扫描而超时。
  - **没有新增失败。**
- 截图：`evidence/13/01-annotate.png`、`02-app.png`、`03-scan.png`、`04-no-scan.png`。合并后又在 scan、app 档打开 Topology 和 Sidebar 各拍一张（`05-scan-panels.png`、`06-app-panels.png`），核对 K 线显式放第一列后，诊断侧栏仍在第二列、拓扑横跨整行。
  - 整页截图，`scale=device`，没调窗口尺寸。
  - 画面：KO / NVDA，pattern W底，测试后端，mapping 手写为 bo_only。
  - 自查发现并修了一处：`no_scan` 那层显式放进图区那一格后，K 线被自动挤到新开的第二列，图区变窄；改成 K 线也显式放第一列。
- 说明书 `grep -n '主视图'` 已无剩余，原来四处都改成指 `app` / `scan` 档。
- 本票 diff 里 grep `docs/research` 为空。改动过的 `view.ts` 第 8、343、1238 行有更早的引用，本票没动（同票 06、11 的处理）。

**改写的现有测试**（都是行为按 spec 改了，不是放宽）
- `tests/components/TopBar.mode.spec.ts` 最后一条：原来断言扫描结果下 `app` 按下、点它不换来源。现在是 `scan` 按下、`app` 不按下；没有 app 时 `app` 灰；再点 `scan` 不换来源。
- `tests/stores.view-mode.spec.ts`「app 下删掉当前扫描:清空图并回到 annotate」：改成留在 scan 档的 `no_scan`、图清空（spec 5.2：删掉当前扫描也落在 `no_scan`）。
- `tests/components/ChartArea.shift-p.spec.ts`：挂载前切到 scan 档，因为 Shift+P 只在 scan 档起作用了。
- `tests/components.sidebar-result-list.spec.ts` 的 tooltip 断言 `75%`→`75.0%`：开工前就红、与 mode 无关，见上。
- 新增：`tests/fixtures.ts` 的 `scanOf`，供两个新测试文件共用。

**独立审查**：报告在 `evidence/13/review-standards.md`、`review-spec.md`，修改在提交 105d280。
- Standards，硬违规 0 条；判断题已改的：
  - 记账的三个状态改名为 `scanListSymbol`、`preScanSymbol`、`frontTierSymbol`；
  - `scanOf` 收进测试夹具；
  - K 线图注释和 `no_scan` 两处悬停统一写法。
- Standards，判断题没改的：
  - 「进 scan 档」三个动作里重复设 `mode` / 来源：三处各自还做不同的事（选过股、清图窗、挑股票、整套重置），抽出来只省两行；
  - 三个记账状态没合成一个对象：它们在同一个 store 里，合起来不更好读；
  - `stores.view-mode.spec.ts` 等处的旧叫法：现有测试，不为改注释动它。
- Spec：
  - (a) e2e 基线清单已存；跑法见上。
  - (b)(c) 是会话自定的默认，列在下一段。
  - 75% 那条是为了「单测全过」。

**会话定的默认**（`detail`，只本票用到，待用户用起来再看；没改 spec）
1. 从前三档加载扫描（含扫描跑完、停止时保存后自动打开），也按「前三档 → scan」的规矩：当前股票在这份扫描里就留着，不在就落在扫描文件里第一只。原来恒落在第一只。已在 scan 档里换一份扫描，仍落在第一只。
2. 进 scan 前没开着股票（如刚打开页面就加载扫描），回前三档时留着扫描里看的那只，不落空图。
3. 「点过扫描列表的行」包括 PageUp / PageDown 切股，也包括在前三档点列表的行进来。票 14 换掉前三档左栏后，后一种情形不再有。
4. 在 scan 档里删掉当前扫描后，回前三档落在进 scan 前那只，之前点过的行不算。
5. 离开 scan 档时参数抽屉关上：未存盘的编辑留在共享 model 里，重开不丢。
6. `no_scan` 只盖图区；档位条、拓扑、诊断侧栏照扫描视图原样。
7. scan 档里顶栏 `compare` / `app` 能不能点，按回前三档时会落的那只股票判。所以 `no_scan` 里只要进来前开着一只股票、pattern 有 app，就能直接点 `compare`。

**界面名**：`scan`、`no_scan` 是 spec 第 10 节列的待认的名字，本票照用，没进词表（等用户认）。新起的只有悬停文字：
- `app`：`output of app … run now on this symbol (not the scan file), lanes by node`
- `scan`：`results saved in the scan file …` / `scan results; no scan loaded; open or run one in the left panel`
- `no_scan` 的悬停：`no scan loaded; open or run one in the left panel`

**给票 14 的环境提示**
- 在建了 `.venv` 的 worktree 里跑 `annotate-rally-random.spec.ts:145`（看过什么一律不记），会报 `spawnSync /bin/sh ENOBUFS`：
  - 它读 `git status --porcelain --ignored --untracked-files=all`，`.venv` 里逐个列出的被忽略文件撑破了 execSync 的默认 1 MB 缓冲；
  - 本票在票 worktree 里跑过两次，都这样红；在没有 `.venv` 的分离 checkout 里，基线和完工后都过。
  - 这是测试环境的问题，与界面无关。票 14 要比对 e2e，宜照 `evidence/13/e2e_run.sh` 在分离 checkout 里跑。
- 主目录的网页一直开在 8001 / 5171，e2e 的 `reuseExistingServer` 会直接用上它。所以 worktree 里跑 e2e 前要把端口临时改掉（skip-worktree，不提交）。
- 扫描视图里打开扫描时，浏览器控制台出过一次 ECharts 警告 `z / z2 / zlevel of displayable is invalid`。扫描视图本票没动，来源没查。

**共享机制与复核**
- 改了 view store 的几处动作语义：
  - `clearScanFile` 在 scan 档里不再回 `annotate`；
  - `loadScanFile` 可能留着当前股票；
  - `selectSymbol` 清图窗；
  - `enterAnnotate` / `enterLinked` 从 scan 档出来会换回股票；
  - `appLink.available` 改按 `frontTierSymbol` 判。
- 新增 `scanView` / `noScan` / `frontTierSymbol` / `enterScan`。
- 用到它们的未开始票只有 14，复核过条文：14 要用的「是不是扫描视图」就是 `view.scanView`，它写的「票 13 已把两者按档分开」成立。没有条文因此变假，没改票 14。

**运行环境**
- worktree 的 `uv sync` 正常，pytest 没跑，本票没改后端。
- worktree 端口临时改成 8093 / 5193（skip-worktree，没提交），合回前已改回。
- 基线、完工后、合并后的 e2e 各在一个分离 checkout 里跑（`git worktree add --detach`，放在会话 scratch），跑完已用 `git worktree remove --force` 删掉。
- 截图用的测试后端（标注在会话 scratch）和 vite，已按进程号停掉；`.playwright-mcp/` 已清空。

`未安排人审：四档的排法、no_scan 空状态、进出 scan 时股票怎么带顺不顺手；原因：这些只影响怎么切换，不改存下的标注，也不进任何成绩，没有 build-on point；用起来不顺就改 spec 第 10 节的默认`

## Comments

- 2026-11-15 拆票：人审行按 `docs/agents/review-planning.md` 由会话推荐写入；同日拆票那一轮，用户选「照列的发布」确认（两张票都是 `ready-for-agent`，不设人审闸）。
- 暂停 2026-11-15（parallel-tickets，等用户）：实现、测试、独立审查、截图都已完成（分支 impl/13-scan-tier 尖 449aace，测试与审查所在提交 105d280；单测 1665 条全过，e2e 与基线比无新增失败），合回被主目录未提交的改动挡住——`.scratch/annotation-path2/manual.md`、`path2_web_ui/src/components/ChartArea.vue` 两边都改了（同批还有 spec.md、FeedbackPanel.vue、stores/feedback.ts 等，看着是「Delete 删反馈」的开发），git 拒绝合并，本票不碰别人的改动；见 [Q01](../questions/Q01-main-dir-blocks-merge.md)。恢复：那批改动提交后说「继续 13」——先把调度分支合进票分支（ChartArea.vue 预计要手解），重核票 13 引用的 spec 条款，重跑单测、在分离 checkout 里照 evidence/13/e2e_run.sh 重跑 e2e，在 scan / app 档打开 Sidebar 与 Topology 看一眼布局，删掉 evidence/13/completion-draft.md、按它改提交号与数字写完成记录，再 --no-ff 合回。
- 恢复 2026-11-15（parallel-tickets）：ticket-13 继续
