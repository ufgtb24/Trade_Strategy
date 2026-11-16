# 标注三档的左栏：找图清单 `rally` / `random` / `charts`

Status: ready-for-agent
Progress: done
Claimed: 2026-11-15 parallel-tickets ticket-14 @ worktree impl/14-finder-list
Blocked by: 13

## Purpose

用户在标注时点一下就能打开下一张图，翻页键能挨个翻，一眼看得出哪些图已经标过、标的是哪个 pattern；不再先点顶栏 `rally`、再在浮层里点一行。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：
  - 1.17（全节）；1.3「找图有三个入口」那条；
  - 5.2「顶栏」的 `symbol`、「左栏」（全条）、「模式切换」；
  - 5.3「`rally`」「`random`」「`charts`」「看过什么一律不记」；
  - 5.8「键位」那条；
  - 第 9 节「端到端」的 `random` 与找图清单那条；
  - 第 10 节「找图清单的按法」「左栏的默认页与宽度」「大涨段清单的『标过』」三行。
- 用户的原意：`.scratch/annotation-path2-implementation/v-s1-notes.md`「界面改进」第 2 条（`rally` 清单看不出哪些已经标过），以及第 8、9 条（左栏在标注时空着、找图要点两下、上下键挨个翻）。
- 研究报告 `docs/research/2026-11-11_annotation-scan-page-layout/final_report.md` 第 5 节，`options.md`「方案 F」的线框图、第 4 节「内容轴：前三档左栏放什么」。只作参照，实施产出不得引用（共用边界第 4 条）。

## Inherited Direction

- 共用执行边界（[拆分总览](../ticket-breakdown.md)「各票共用的执行边界」），第 11 条「截图」照票 13 的改法：不调 `browser_resize`，截图一律 `scale="device"`。
- **三页只列用户自己存下的东西，加上这次 `random` 抽到的图**（spec 5.2「左栏」）：不出现 app 的任何结果，也不出现「看过 / 没看过」。防的是两件事：一是标注时被 app 的结果带偏（说明书「annotate 默认不看见 app 产物」）；二是「看过」变成限制看哪些图的账本（spec 5.3，票 01 写明记「看过」违背训练段随便看）。
- **`random` 页只在页面内存里**（spec 5.3）：不写文件，不写浏览器存储，刷新就清空。
- **清单不带「敲字母搜股票」**（spec 5.2「左栏」）：带过来就会重新抢走键盘。搜股票用顶栏 `symbol`。
- **翻页用 PageUp / PageDown，不用 ↑/↓**（spec 1.17「和研究原文不一样的一处」、5.8）：11-12 已把 ↑/↓ 给了图上「在同一天里换」。研究报告写的「↑/↓ 挨个翻」是在那之前写的，以 spec 为准。
- **后端不动**（spec 第 8 节「前端」）：清单从前端的标注状态和已有的大涨段清单路由现算。
- **切档时只藏不拆**（spec 5.2「左栏」）：找图清单和扫描列表在切档时都要保住滚动位置。
- 样式和按法照扫描列表（spec 5.2「左栏」）。界面文字照共用边界第 6 条：用户起的 pattern 名是业务内容，用正常字体加浅灰底；页签名、表头用等宽的标识符风格。

## What to build

- **前三档的左栏换成找图清单**，分三页 `rally` / `random` / `charts`。`scan` 档仍是扫描面板和扫描列表（票 13 已把两者按档分开）。
  - `rally`：沿用现有大涨段清单的数据和排序，每行加标过的 pattern 名和框数。「标过」按这一行的图窗算，悬停列出具体样本（spec 5.3）。
  - `random`：按抽的先后列出这次抽过的图。顶栏 `random` 每抽一张，就加进这一页。
  - `charts`：全部标过的股票，一只一行，写 pattern 名、正负样本数、框数，只画了框的也列（spec 5.3）。只有反馈、没有框和样本的股票列不列，执行者照「标过」的意思定，写进完成记录。
- **按法**：
  - 点一行，或在当前页签上按 PageUp / PageDown，换到那张图；
  - 换图不换档，`annotate`、`compare`、`app` 都留在原档；
  - 焦点在任何输入框（单行、多行）或下拉框里时，翻页键不切。
- 打开、刷新页面时默认落在 `rally` 页。宽度沿用「最少 220px、按内容撑、最多半屏」，不加收起开关（spec 第 10 节）。
- **顶栏去掉 `rally` 按钮和它的浮层**。`random` 按钮留在顶栏。
- **e2e**：
  - 原来打开首页就直接点左栏「打开历史」「扫描 ⚙」的 spec，改成先点 `scan`。这一步收进 `path2_web_ui/e2e/` 里的一个辅助函数。
  - `annotate-rally-random` 里点 `rally-button` 的步骤，改成点左栏的 `rally` 页。
  - 「先在扫描视图、再进标注」的用例照新的进出 `scan` 规则改写。
  - `dev-ui-replication` 的视觉快照按新左栏重拍。
- **说明书** `.scratch/annotation-path2/manual.md`：
  - 「四、界面一览」加左栏一项（三页各列什么、怎么翻、`scan` 档是扫描列表）；
  - 「① 找图」改成从左栏三页进；
  - 照现有写法，只写现在的界面。

## Scope and exclusions

- 不改后端，不改大涨段清单的定义与缓存（票 08 的产物，经现有路由用）。
- 不改扫描列表本身的按法（`scan` 档里照旧）。
- 不做 `compare` 下左栏显示 app 与标注是否一致，也不把盲看清单放进左栏（研究报告 7.2 留给第二段）。
- 不加左栏收起开关。
- 不记任何「看过」。

## Blocked by

13

## Acceptance criteria

- 开工前以票 13 完工后的状态跑一遍前端单测和 e2e 全套，存基线进 `evidence/14/`。完工后再跑：单测全过，e2e 比基线没有新增失败，改写和重拍的用例在完成记录里逐个列出。
- 三页内容各有单元测试，例子直接写进测试：
  - `rally` 的「标过」按图窗算：样本日在图窗外的不计 pattern 名；只画了框的行有框数、没有 pattern 名；
  - `charts` 列出全部标过的股票，只画了框的也在；
  - `random` 按抽的先后排，刷新后为空。
- `random` 页不落盘：抽几张前后对比 `git status --porcelain --ignored`，没有新文件；浏览器存储里没有新键。
- 按法各一条测试：
  - PageUp / PageDown 在当前页签里换图，`annotate`、`compare`、`app` 下各自留在原档；
  - 焦点在单行输入框、多行输入框、下拉框里时不切；
  - 点一行换图。
- 切到 `scan` 再切回来，找图清单的页签和滚动位置都还在。e2e 一条。
- `compare` 下左栏没有 app 的任何结果（命中、收益列都不出现）。组件测试一条。
- 顶栏没有 `rally` 按钮。
- 截图存进 `evidence/14/`：`annotate` 下三个页签各一张整页截图，`rally` 页的一行加悬停一张元素截图。
- 改动的文件里 grep `docs/research` 结果为空。
- `未安排人审：清单的样子和按法顺不顺手、「标过」按图窗算合不合用、默认页与宽度；原因：清单只决定给用户看哪些图，不进任何成绩，也不改存下的标注，没有 build-on point；用起来不顺就改 spec 第 10 节的默认`

## 完成记录

2026-11-16，parallel-tickets ticket-14。合并提交 ae156c2（`--no-ff` 合回 `annotation-path2`）。
- 独立审查在提交 1902a86 上做，审查后的修改在 1cc3b32，18b08d5 又把其中一条单测换成挂真组件；
- 9d20e13 是全套 e2e 第一遍跑出来的修复（见「e2e 对照」）；
- e2e 全套跑在 9d20e13 上；之后的提交在 `path2_web_ui/` 下只改了 `tests/components/FinderList.spec.ts` 的一条单测，没有重跑 e2e。

**暂停与恢复**
- 第一次准备合回时，主目录有别处没提交的改动（annotation-round 的出局核对：技能文件、`spec.md`、`manual.md`、`CLAUDE.md`、`path2/GLOSSARY.md`、`path2_apps/new_step/mapping.yaml`），其中 `manual.md` 两边都改了，所以暂停，提了 [Q02](../questions/Q02-main-dir-blocks-merge-14.md)。
- 用户选 A；那批改动提交为 4cf856c 后恢复。
- 把调度分支（4cf856c）合进票分支（c655b1c），git 自动合并，没有冲突：
  - `manual.md` 两边改的是不同的节（本票「四、界面一览」「① 找图」，那边 ⑤）；
  - 那边改的 spec 条文是 1.6 的 11-16 一条和 6.14 第 3、7 步，不在本票引用的条款里，本票条款没变。
- 合并后在 c655b1c 上重跑：`npx vitest run` 1701 条全过，`npx vue-tsc -b` 通过。
- 合回前最后一次提交 f06f0bd 只删了完成记录草稿，代码与 c655b1c 相同。

**做了什么**
- 前三档（annotate / compare / app）的左栏换成找图清单，三页 `rally` / `random` / `charts`（`FinderList.vue`）；`scan` 档仍是扫描的 Patterns 面板、扫描面板和扫描列表。两份都放在新的 `LeftPanel.vue` 里，切档只藏不拆。
  - `rally`：沿用 `/rally` 的数据和排序（点表头换序），每行加 `patterns`、`boxes` 两列；悬停 `patterns` 一格列出算进来的样本（日期、`pos` / `neg`、pattern）。
  - `random`：顶栏 `random` 每抽一张，按先后加一行（`stores/finder.ts`，只在页面内存里）。
  - `charts`：全部标过的股票，一只一行，写 pattern 名、`pos`、`neg`、`boxes`。
  - 「标过」的算法是纯函数 `annotate/finderList.ts`，从标注状态（含还没存完的动作）现算，后端没动。
- 按法：点一行，或在当前页签按 PageUp / PageDown 换图（`view.openFromFinder`），annotate、compare、现算的 app 都留在原档；当前图不在这一页时从第一行起，到头停住；翻完把那行滚进视野。焦点在单行、多行输入框、下拉框里时不切（守卫同 Delete 删框），另加：自绘下拉（顶栏 `pattern` 的 PatternPicker）菜单开着时也不切；scan 档里不接。
- 打开、刷新默认落在 `rally` 页；三页叠在同一格里，没选上的只是看不见、照样撑宽度，所以左栏宽度按最宽的一页定，切页签时图不跟着变宽变窄（仍是「最少 220px、按内容撑、最多半屏」）。不加收起开关。
- 顶栏去掉 `rally` 按钮和浮层（`RallyList.vue` 删掉，内容并进 `FinderList.vue`）；`random` 留在顶栏。
- 现算的 app 档换图（左栏清单换图不换档）时图也停在给的图窗上：`KlineChart.vue` 有产物时的那条画法，换图时也按 `viewWindow` 定缩放；scan 档照旧按扫描窗口。
- 说明书 `.scratch/annotation-path2/manual.md`：「四、界面一览」加左栏一项和顶栏 `random` 一行；「① 找图」改成从左栏三页进。

**验收**
- 单测：开工前 ca2366e 上 1671 条全过（`evidence/14/vitest-baseline.txt`）；完工后 18b08d5、合并后 c655b1c 上 `npx vitest run` 都是 1701 条全过，`npx vue-tsc -b` 通过。
- 三页内容的单元测试（`tests/annotate.finder-list.spec.ts`，12 条，例子写在测试里）：
  - rally 按图窗算：样本日在图窗外的不计 pattern 名；只画了框的行有框数、没有 pattern 名；框跨进图窗一端也算、完全在窗外不算；端点上的样本日也算；
  - charts 列出全部标过的股票，只画了框的也在，只有反馈的不在；
  - 翻页落点三条。
- 组件测试（`tests/components/FinderList.spec.ts`，19 条）：
  - 默认 rally 页、表头、点表头换序、empty / load_failed；rally 的「标过」与悬停；charts 的行；
  - random 按抽的先后、刚抽的是当前行；刷新（新的页面状态）后为空、回到 rally 页；localStorage、sessionStorage 不变；
  - 点一行换图不换档、PageUp / PageDown 在当前页签里翻、换页签后在新页签里翻：annotate、compare、app 各一条；
  - 带修饰键不接；单行、多行输入框、下拉框里不切（反向核对过：去掉守卫后这三条变红）；
  - 顶栏 `pattern` 的自绘下拉（挂真的 PatternPicker）开着时不切、点别处关上后照常翻（反向核对过）；
  - scan 档不接（反向核对过）；
  - `LeftPanel`：compare 下看得见的部分没有扫描列表的命中、收益列和行，切 scan 再回来页签还在。
- `random` 不落盘：e2e `annotate-rally-random`「看过什么一律不记、random 页不落盘」——连点三行 rally、翻页、抽三次 random、点回 random 页的一行，前后对比 `git status --porcelain --ignored --untracked-files=all`、标注目录、localStorage、sessionStorage、IndexedDB 库名，都不变；刷新后 random 页为空、回到 rally 页。
- 切到 scan 再切回来，找图清单的页签和滚动位置都还在：e2e 一条；另加一条反方向的——从前三档回 scan 档，扫描列表的滚动位置还在。
- 顶栏没有 `rally` 按钮：`tests/components/TopBar.spec.ts` 一条。
- 截图（`evidence/14/`，测试后端、标注在会话 scratch，整页 `scale=device`，没调窗口尺寸）：
  - `01-annotate-rally.png`、`02-annotate-random.png`、`03-annotate-charts.png`：annotate 下三个页签；
  - `04-rally-row-hover.png`：rally 页 RGC 那一行加悬停（左栏的元素截图，裁到表头、那一行和浮层）。
  - 画面里的标注：夹具 `annotation_grouping_v1`（AAPL / MSFT / NVDA），另在 RGC 的 rally 图窗里放了 W底 正样本、旗形 负样本和一个框，在 COSM 上只画了一个框。
- 改动的文件里 grep `docs/research`：代码、测试、说明书里为空。`stores/view.ts` 原有的三处引用（更早的 event-debug、Working Copy 两次开发留下的出处注释）本票去掉了，只留结论。`evidence/14/review-*.md` 两份审查报告原文提到这条检查本身。
- e2e 全套（见下节），没有新增失败。

**e2e 对照**
- 跑法同基线：`evidence/13/e2e_run.sh`，分离的干净 checkout（会话 scratch），端口 8145 / 5145，解释器借票 worktree 的 `.venv`；不跑 miss-detection-walkthrough；依赖旧扫描的 6 个 spec 另跑一轮、单条超时 30 秒。清单 `evidence/14/e2e-baseline.txt`、`e2e-after.txt`。
- 主体：55 条，45 过 10 红（基线 53 条，40 过 13 红）。
  - 红的 10 条都在基线里：flow 4 条、scan-dialog 5 条照旧红在开头等「底部反转突破爆发」下拉那一步（行号因加了一行 import 后移一行），dev-ui-replication 第 4 条照旧红在已退役的 `class_id` / `event_id` 字段上；
  - dev-ui-replication 第 1～3 条从红变绿（见下「改写和重拍」）；
  - 多出的 2 条是 annotate-rally-random 新增的两条，都过。
- 旧扫描组：27 红 4 没跑，失败清单与基线逐条相同（不计行号），都是点不到历史里那份扫描而超时。这 6 个 spec 和不跑的 miss-detection-walkthrough 的改动（先进 scan 档）跑不到通过，只过了 `playwright test --list` 的编译。
- 第一遍全套（1cc3b32）多红了 9 条：annotate-boxes 4 条、annotate-grouping、annotate-ref-peaks、annotate-samples 2 条、feedback.spec.ts:431。原因是左栏 rally 页一打开就要大涨段清单，各组新起的测试后端首次要整池算约半分钟，测试结束、页面关掉时这个请求还在路上，转发请求的 `route.fetch` 报「页面已关」被算成失败。`e2e/annotateHelpers.ts` 的 `routeTo` 改成页面已关时不抛（9d20e13），这 9 条单跑全过，全套重跑见上。

**改写和重拍的用例**（都是界面按 spec 改了，不是放宽）
- 新增辅助函数 `e2e/scanTier.ts`：`gotoScanTier`（打开首页再点 `scan`）、`enterScanTier`。原来打开首页就直接点左栏「打开历史」「扫描 ⚙」的都改成先进 scan 档：
  - `smallScan.ts` 的 `openSmallScan`（hit-event-disambig、fold-rows、sidebar-chart-focus 共用）、`symbol-search`、`scan-tier` 的 `openScan`、`flow`、`scan-dialog`、`dev-ui-replication`；
  - 旧扫描组的 `kline-ctrl-wheel-right-anchor`、`subchart-tooltip-crosshair`、`subchart-scroll-drag`、`shift-pair-feedback`、`subchart-band-zoom`、`subchart-blankclick-yaxis`，和不跑的 `miss-detection-walkthrough`。
- `symbol-search`、`flow`、`dev-ui-replication` 里不带范围的 `[data-symbol]` 改成限定在 scan 档那一份：找图清单的行也带 `data-symbol`，又排在 DOM 前面，`first()` 会落到藏着的清单行上。
- `annotate-rally-random` 整份改写：
  - rally 从左栏点（打开页面就在 rally 页），留在 annotate、图窗不变，另加 PageDown 换到下一行；
  - random 改成从 scan 档出发，再验 random 页的先后、点回去、翻页；
  - 「看过什么一律不记」改成点左栏的行，并加上 random 页不落盘、sessionStorage、IndexedDB、刷新后为空；
  - 新增两条：切档保留找图清单的页签与滚动；回 scan 档保留扫描列表的滚动。
- `annotate-compare` 第 2 条：点 `rally-button` 的步骤改成点左栏 rally 页的一行；另加 app 档点一行留在 app、app 跑完后图窗起点等于清单的 `view_start`。
- `annotate-open-by-symbol`：
  - 第 1 条的 `getByRole('tab')` 限定在右侧栏（左栏页签也是 tab）；
  - 「先在扫描视图、再进标注」那条照新规则改写：在 scan 档打开扫描 → 按代码打开切到 annotate（左栏是找图清单、扫描列表藏着）→ 点 `scan` 回扫描视图仍是那只 → 从扫描列表选股留在 scan 档。
- `scan-tier` 第 2 条：前三档的 PageUp / PageDown 现在归找图清单，这一步先切到这次还空着的 random 页，原断言（不切扫描股、不离开前三档）照旧成立。
- `dev-ui-replication`：
  - 去掉开头等「底部反转突破爆发」下拉的过时断言（换成进 scan 档），等历史列表加载完再数行——原来读到加载中的 0 行，会误判成没有扫描、每条去整池现扫一遍（4.6 分钟）；
  - 快照 `initial-viewport-linux.png`、`after-pan-left-linux.png` 按现在的 scan 档重拍（`evidence/14/run_specs.sh`，新的空临时目录、历史里只有和 `e2e_run.sh` 相同的种子扫描，`--update-snapshots=changed`）；第 1～3 条从基线的红变绿。这两张图只在这份种子扫描下成立：种子、detector 或画法一变就会红，到时按同样的办法重拍，不是那张票的回归；
  - `hover-marker-linux.png` 没能重拍：第 4 条在截图前就红在断言已退役的 `class_id` / `event_id` 字段上，和本票无关，没有深挖。scan 档的左栏本票没改，这几张图的变化主要是顶栏少了 `rally`。
- `flow`、`scan-dialog` 开头那句等「底部反转突破爆发」下拉的过时断言没动：去掉后 `scan-dialog` 会触发整池现扫；它们在基线里就红在这一步，现在照旧。
- `e2e/annotateHelpers.ts` 的 `routeTo`：见上节。
- 单测改写：`tests/components/TopBar.spec.ts` 的 rally 两条（点开浮层、empty / load_failed）移到 `FinderList.spec.ts`，原处换成「顶栏没有 rally 按钮」；random 那条加断言「抽到的记进左栏 random 页、没抽到不记」。

**独立审查**：报告在 `evidence/14/review-standards.md`、`review-spec.md`，修改在 1cc3b32。
- Standards，硬违规 1 条：`view.ts` 原有的三处 `docs/research` 引用，已去掉。判断题已改的：
  - 四处重复的 pattern 名模板收进 `PatternNames.vue`；rally 行的图窗只拼一次；
  - random 页的 `#` 列去掉（行的先后就是抽的先后）；rally 的 `empty` 与另两页同用灰字。
- Standards，判断题没改的：
  - `scan-side` 选择器在三份 e2e 里各写一次：每处一行，收进辅助函数省不了什么；
  - 三页各一组 `*El` / `*Cur` 加 `currentPage()` 的分支：三页的行形状不同，收成一张表要先造一个通用行类型，反而难读；
  - `#fff`、阴影色是从删掉的 `RallyList.vue` 原样搬来的，不是新色。
- Spec：
  - 扫描列表切档后的滚动位置没测：补了一条 e2e；
  - 悬停截图是整个左栏：裁到那一行和浮层；
  - 自绘下拉开着时按 PageDown 照样换图：守卫补上，加一条单测（Delete 删框有同样的缺口，不在本票范围，没动）；
  - app 档按图窗缩放没测：`annotate-compare` 补一段；
  - 左栏 random 页的状态与顶栏 `random-status` 重名：改成 `random-page-status`；
  - 字号与留白照扫描列表改成 12px、左右 6px，左栏窄一些。
  - 保留没改的两条（理由见下一段第 1、4 条）：框按「有重叠」算；random 页每行也写标过什么。
  - 左栏宽度：spec 1.17 的代价估的是约 278px，这台机器上 rally 页撑到约 358px（CSS 像素），原因是多了 `patterns`、`boxes` 两列，涨幅也宽（最大一行 +10996.0%）。仍在「最多半屏」之内，列进下面的未安排人审。

**会话定的默认**（`detail`，只本票用到；没改 spec）
1. 框「落在图窗里」取「和图窗有重叠」：打开这张图看得见它的一部分就计进框数。理由：框数是为了分出「只画了框」和「完全没碰」，在这张图上画的长框常会跨出图窗一端，按「完全在里面」算会把它当成没碰。
2. 没归 pattern 的样本在 `patterns` 一格写 `unsorted`（程序的词，等宽、不加底），悬停也照列。
3. charts 页只列有框或有样本的股票，只有反馈的不列：反馈是在 compare 里对 app 买点的作答，列进来等于把「app 在这买过」带进了标注三档的左栏。
4. random 页每行也写 `patterns`、`boxes`（票只对 rally 要求了）：同一个用途——抽过的几张里哪些已经标过，一眼看得出；算法与 rally 同一个函数。
5. charts 页点一行按默认缩放打开（整只股票）。
6. 悬停只在 `patterns` 一格触发，`date` 一格的悬停照旧写最高点那天与相对涨幅。
7. random 页按抽的先后从上往下排（最早的在最上）。
8. 大涨段清单页面一打开就取（原来是第一次点开浮层才取）：默认页就是 rally。
9. 三页叠在同一格、左栏按最宽的一页定宽（上面「做了什么」）。

**界面名**：页签 `rally` / `random` / `charts` 是 spec 第 10 节列的待认的名字，本票照用，没进词表。新起的固定文字：表头 `patterns`、`boxes`、`start`、`end`、`pos`、`neg`（另沿用 `symbol`、`date`、`rise`），状态沿用 `loading`、`load_failed`、`empty`。悬停说明写中文（同原来的大涨段清单）。

**共享机制与复核**
- view store 新增 `openFromFinder`（换图不换档；scan 档里什么都不做），`openSymbol` 的换图部分抽成 `showChart`，行为不变。
- `KlineChart.vue`：现算的 app 档换图时按 `viewWindow` 定缩放。
- 左栏改由 `LeftPanel.vue` 装配；找图清单的行带 `data-symbol`，以后 e2e 找扫描列表的行要限定在 `scan-side`。
- e2e：`openSmallScan` 先进 scan 档；`routeTo` 容忍页面关掉后还在路上的请求。
- 未开始的票只剩 12（两台机器的设置，人来做），不用这些机制，没有条文因此变假。

**运行环境**
- 没写进共享位置：`datasets/`、用户的 `annotations/` 自开工（2026-11-15 23:40）以来没有文件变动（`find -newermt` 核过）；测试后端的标注与扫描输出都在会话 scratch。主目录的 `.playwright-mcp/` 用过、已清空。
- worktree 的 `uv sync` 正常；没改后端，pytest 没跑。
- worktree 端口临时改成 8143 / 5143（skip-worktree，没提交），暂停前已改回。
- 基线和完工后的 e2e 各在一个分离 checkout 里跑，跑完用 `git worktree remove --force` 删掉；截图用的测试后端（8144）和 vite（5144）按进程号停掉；`.playwright-mcp/` 已清空。

`未安排人审：找图清单的样子和按法顺不顺手、「标过」按图窗算（含框按有重叠计、unsorted 的写法、只有反馈的股票不进 charts、random 页也写标过什么）合不合用、默认页与宽度（这台机器上约 358px）；原因：清单只决定给用户看哪些图，不进任何成绩，也不改存下的标注，没有 build-on point；用起来不顺就改 spec 第 10 节的默认`

## Comments

- 2026-11-15 拆票：人审行按 `docs/agents/review-planning.md` 由会话推荐写入；同日拆票那一轮，用户选「照列的发布」确认（两张票都是 `ready-for-agent`，不设人审闸）。
- 暂停 2026-11-16（parallel-tickets，等用户）：实现、测试、独立审查、截图都已完成（分支 impl/14-finder-list 尖 84b21e8；单测 1701 条全过，e2e 全套在 9d20e13 上与基线比无新增失败），合回被主目录未提交的改动挡住——`.scratch/annotation-path2/manual.md` 两边都改了（同批还有 spec.md、CLAUDE.md、path2/GLOSSARY.md、annotation-round 技能文件、path2_apps/new_step/mapping.yaml，看着是 annotation-round 的出局核对改动），本票不碰别人的改动；见 [Q02](../questions/Q02-main-dir-blocks-merge-14.md)。恢复：那批改动提交后说「继续 14」——把调度分支合进票分支，重核票 14 引用的 spec 条款（那边改了 spec.md），重跑单测（合并后的树在 path2_web_ui/ 下与 9d20e13 不同时再照 evidence/13/e2e_run.sh 在分离 checkout 里重跑 e2e），按 evidence/14/completion-draft.md 写完成记录、删掉草稿，再 --no-ff 合回。
- 恢复 2026-11-16（parallel-tickets）：ticket-14 继续
