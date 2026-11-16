## 完成记录

2026-11-15，parallel-tickets ticket-13。合并提交 MERGE_SHA（`--no-ff` 合回 `annotation-path2`），测试与审查所在提交 105d280，合并后的树与之相同。

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
  - 改了那条断言后，提交 105d280 上 `npx vitest run` 1665 条全过，`npx vue-tsc -b` 通过。
- e2e 全套对照，基线和完工后用同一种跑法：
  - 跑在分离的干净 checkout 里，端口另开；
  - 去掉 miss-detection-walkthrough，它读 `datasets/pkls`，越过数据墙；
  - 依赖已不存在的旧扫描（2026-06-30、BTMWW）的 6 个 spec 另跑一轮，单条超时 30 秒，不然要白等 5 个多小时；
  - 脚本 `evidence/13/e2e_run.sh`，清单 `evidence/13/e2e-baseline.txt`、`e2e-after.txt`。
  - 主体：基线 51 条 38 过 13 红；完工后 53 条 40 过 13 红。红的 13 条逐条相同，都卡在开头等一个现在已不存在的「底部反转突破爆发」下拉；多出的 2 条是本票新加的，都过。
  - 旧扫描那组：基线 27 红 4 没跑；完工后同样 27 红 4 没跑，失败清单逐条相同，都是点不到历史里那份扫描而超时。
  - **没有新增失败。**
- 截图：`evidence/13/01-annotate.png`、`02-app.png`、`03-scan.png`、`04-no-scan.png`。
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
- 基线和完工后的 e2e 各在一个分离 checkout 里跑（`git worktree add --detach`，放在会话 scratch），跑完已用 `git worktree remove --force` 删掉。
- 截图用的测试后端（标注在会话 scratch）和 vite，已按进程号停掉；`.playwright-mcp/` 已清空。

`未安排人审：四档的排法、no_scan 空状态、进出 scan 时股票怎么带顺不顺手；原因：这些只影响怎么切换，不改存下的标注，也不进任何成绩，没有 build-on point；用起来不顺就改 spec 第 10 节的默认`
