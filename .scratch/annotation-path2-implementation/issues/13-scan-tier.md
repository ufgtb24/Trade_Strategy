# `scan` 档：把扫描结果从 `app` 按钮里拆出来，扫描专用的按键只在 `scan` 起作用

Status: ready-for-agent
Progress: in-progress
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

## Comments

- 2026-11-15 拆票：人审行按 `docs/agents/review-planning.md` 由会话推荐写入；同日拆票那一轮，用户选「照列的发布」确认（两张票都是 `ready-for-agent`，不设人审闸）。
