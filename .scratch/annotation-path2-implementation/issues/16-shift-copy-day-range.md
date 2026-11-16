# 主图上按住 Shift 复制一天或一段

Status: ready-for-agent
Progress: done
Claimed: 2026-11-16 parallel-tickets session-16 @ worktree impl/16-shift-copy-day-range
Blocked by: none

## Purpose

用户想和会话说某段走势时，在主图上按住 Shift 点一根 K 线或拖出一段，就能把「股票 + 日期 / 时段」一行贴给会话，不用手打，也不用先选中什么。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：
  - 1.6「11-16（第三件）」那条；
  - 1.14「复制一天、一段」（全条）、拼法与表（行的写法）、「会话默认、待验证」那条；
  - 5.2 `tool` 那条的括注；
  - 第 8 节「前端」复制一天、一段那条；
  - 第 9 节「端到端」复制一天、一段那条；
  - 第 10 节「复制一天、一段的手势」「时段那一行的种类词」两行。
- 用户的原意（2026-11-16 会话）：增加一个主图选择复制功能，用来和 cc 交流特定时段走势——选中某根 K 线，复制股票名 + 日期；选中某个时段，复制股票名 + 时段。

## Inherited Direction

- 共用执行边界（[拆分总览](../ticket-breakdown.md)「各票共用的执行边界」第 1～10 条）；第 11 条「截图」照第二批的改法：不调 `browser_resize`，截图一律 `scale="device"`，看整体用 `fullPage=True`、看单个组件用 `fullPage=False` 加 `target`；用完清空 `.playwright-mcp/`。
- **一个手势管两件事、只在按着 Shift 时改剪贴板**（1.14）：按住 Shift 按下，拖开复制一段，没拖开复制这一天；松手直接复制，不再按 `Shift+C`。防的是：普通点 K 线是取消选中、点得很频繁，用普通点击复制会悄悄冲掉剪贴板。
- **只复制，不改图上的状态**（1.14）：选中、当前日竖线、视窗都不变，不平移。防的是：复制只是把日期指给会话，不该打断用户正在看的选中和走动位置。所以不能先改当前日、再借现有「当前日」那一行复制。
- **Shift 优先于工具**（1.14）：`box`、`point`、`feedback` 工具与 `app`、`scan` 的「框选」亮着时照样复制，工具不熄、不画框、不发起反馈、不发框选查询。理由：按住 Shift 的意思只有「复制日期」一种，不随工具变。
- **唯一例外：event 记号上的 Shift+点**（1.14）：照旧是跨图配对查询。防的是：那是已有的诊断入口。点和拖按同一口径分（相距超过 4 像素算拖），所以从记号上开始的 Shift+拖仍是复制一段。实现时注意：若在捕获阶段整个吞掉 Shift+按下，图表就收不到记号上的点击，配对查询会坏掉。
- **复制行沿用现有拼法与路径**（1.14 拼法与表）：`股票 pattern day 日期`、`股票 pattern range 起→止`；走现有复制与提示条那条路，不另写剪贴板代码；pattern 的取法同现有复制行。
- 四档都能用；只接主图（K 线区与成交量带），副图不接。
- 第 10 节那两行是会话默认，按 spec 第 10 节「detail」的规矩办：只本票用到时执行者可以改，在完成记录里写清原值、新值和理由。
- 竖带预览的配色照用户的色盲规则（和底色拉开深浅，不靠色相；如中蓝 RGB(26,128,186) 的半透明）；界面固定文字照共用边界第 6 条。

## What to build

- 主图上 `Shift+点` 一根 K 线 → 复制 `股票 pattern day 日期`，底部提示条显示这一行。
- 主图上 `Shift+拖` → 拖的过程中画竖带预览；松手复制 `股票 pattern range 起→止`，预览消失。从右往左拖一样；按下时按着 Shift 就算，途中松开 Shift 不影响；拖出图外按首尾 K 线截住，松手在图外也要收尾。
- 拦掉 `Shift+按下` 时浏览器扩展文字选区的默认行为。
- 现有复制行模块头注释里的行格式表补上 `range`。
- **说明书** `.scratch/annotation-path2/manual.md`「六、贯穿全程的几样」那段：加按住 Shift 点 / 拖复制一天、一段的说法与例子；照现有写法，只写现在的界面。

## Scope and exclusions

- 不改 `Shift+C` 和它复制的内容；不改普通点击、普通拖动、`Ctrl+滚轮`、`Shift+滚轮`。
- 不改「框选」本身的行为。
- 不把复制的一天 / 一段变成「选中的」东西（不进显示栏、选中卡）。
- 不改后端，不进标注文件，不进任何成绩。
- 副图不接。

## Blocked by

none

## Acceptance criteria

- 开工前在本票 worktree 里跑一遍前端单测和 e2e 全套，把失败清单存进 `evidence/16/` 作基线。完工后再跑：单测全过，e2e 比基线没有新增失败，改写的用例在完成记录里逐个列出。
- 单测：复制行的拼法（`day`；`range` 含从右往左、起止同一天；没归组时没有 pattern）；点 / 拖按 4 像素的分法。
- e2e，`annotate`、`compare`、`app`、`scan` 四档各一条 `Shift+点`、一条 `Shift+拖`：复制出的行对（可读 `window.__e2e.copyRef().lastText` 或剪贴板）；之后选中的路径、当前日、视窗的起止都和之前一样。
- e2e：`app` 档 `Shift+点` event 记号仍触发配对查询，复制出的行没变。
- e2e：`annotate` 下 `box` 工具亮着时 `Shift+拖`：复制了一段、工具仍亮、没有新框；`compare` 下 `feedback` 工具亮着时同样，没弹反馈面板；`app` 档「框选」亮着时 `Shift+拖` 不发框选查询。
- e2e 回归：普通拖动仍平移，普通点 K 线仍取消选中。
- 截图存进 `evidence/16/`：`Shift+拖` 途中竖带预览一张元素截图；复制后提示条一张元素截图。
- 改动的文件里 grep `docs/research` 结果为空。
- `未安排人审：按住 Shift 点 / 拖的手势、竖带预览的样子、range 这个词顺不顺手；原因：只决定怎么把日期复制给会话，不改存下的标注，也不进任何成绩，没有 build-on point；用起来不顺就改 spec 第 10 节的默认`

## 完成记录

- **合回**：`92032ed`（`--no-ff` 合回 annotation-path2）；票分支最后一次提交 `79d10ef`（已合进 3b4c3ca 的票 15）。
- **做出的行为**（spec 1.14「复制一天、一段」）：
  - 四档主图（K 线区、成交量带；annotate 下样本三角伸出 K 线区的部分也算）按住 Shift 按下：没拖开复制 `股票 pattern day 日期`，拖开时只在主图上画中蓝竖带预览（盖到成交量带底边），松手复制 `股票 pattern range 起→止`；从右往左一样，途中松开 Shift 不影响，拖出图区按图窗首尾 K 线截住。底部提示条照常显示 `copied  …`，剪贴板里是同一行。
  - 只复制：按下在 window 的捕获阶段截下，跟着的 click 也截下；选中、当前日、视窗、亮着的 `box` / `point` / `feedback` 工具、「框选」都不受影响，开着的作答面板也不关。
  - 在 event 记号上 Shift+点：仍是跨图配对查询（由手势按下时记下停着的记号、松手转交 `handleShiftClick`）；从记号上拖开仍是复制一段。
  - 代码：`path2_web_ui/src/components/shiftCopyGesture.ts`（新）、`annotate/copyRef.ts` 加 `dateLine`、`stores/copyRef.ts` 加 `copyDates`、`KlineChart.vue` 接线与竖带、`KlineChart.ts` 加 `markerIdOf`；说明书「六、贯穿全程的几样」加一段。
- **改了的共享机制与先前结论**：
  1. `stores/copyRef.ts` 的 pattern 取法：从顶栏切进的 app 档（现算）里改取顶栏的当前 pattern（同 compare）。以前那里取 `activePatternId`，现算时主视图不设它，`Shift+C` 与选中卡的 `copy` 行会写成换档前扫描的 pattern 或空着。scan 档不变。这一条越出了票面「不改 `Shift+C` 和它复制的内容」：本票的行必须带 pattern，不修就同样写错，所以一起修了（顺手修，用户定过不限制）。
  2. 主图上的 Shift+点记号不再走图表的点击，改由本手势转交配对；副图照旧。停着的记号靠图表的 mouseover / mouseout 记下，换股、换模式时清掉。
  3. `KlineChart.vue` 的反馈拖选竖带与本票的预览竖带共用 `mainBandPx`；dev 的 e2e 钩子多一个 `hoverMarker`。
  - 未开始的票里没有用到这些机制的（只剩 12「两台机器」，不碰前端），无条文要改。
- **与票面、默认值的出入**（都是实现层，不改 spec）：
  - 拖开了但首尾落在同一根 K 线上时写 `day`，不写 `range X→X`（一根就是一天）。
  - 点、拖的分法沿用 `annotate/boxGeometry.ts` 的 `DRAG_PX`（4 像素，同画框与反馈拖选）。
  - 竖带配色：底 rgba(26,128,186,0.16)、两侧中蓝虚线，同反馈拖选草稿的虚线边写法。
- **命令与结果**：
  - 单测：开工前 `npx vitest run` 1701 全过（`evidence/16/vitest-baseline.txt`）；合进票 15 后 1758 全过（含本票新增 18 条：`tests/components.shift-copy-gesture.spec.ts` 14 条、`tests/annotate.copy-ref.spec.ts` 新增的 `dateLine` 4 条）；`vue-tsc -p tsconfig.json --noEmit` 0。
  - e2e：开工前基线见 `evidence/16/e2e-baseline.txt`（主体 10 红 45 过、旧扫描组 27 红 4 没跑，与票 15 基线逐条相同）；完工后对照见 `evidence/16/e2e-after.txt`。新增 `e2e/shift-copy-dates.spec.ts` 2 条全过。没有改写或重拍现有用例。
  - 票 worktree 里跑全套时 `annotate-rally-random.spec.ts:198` 报 `spawnSync /bin/sh ENOBUFS`：它对整个 checkout 跑 `git status --ignored`，worktree 自己的 `.venv` 让输出到 3.4 MB、超过 execSync 的缓冲；干净 checkout（不建 `.venv`、借解释器）只有 0.57 MB。所以完工对照照基线的跑法在分离的干净 checkout 里跑。
- **独立审查**（`evidence/16/review-standards.md`、`review-spec.md`）：
  - 改了：按下改挂 window 捕获阶段（作答面板不再被 Shift+点关掉）；换股、换模式清掉停着的记号；pattern 取法改为顶栏 pattern（app 档与 compare 一致）；补 `createShiftCopyGesture`、`pairPick` 的函数说明；`put` 改名 `toClipboard`；竖带共用 `mainBandPx`；e2e 补 point 工具、作答面板开着、两击配对发出 scope=pair、框选的正向对照、scan 档框选、app 档普通点击回归，配对两击改用 `shiftClick`。
  - 没改（坏味道，判断级）：`local()` 三行与 `annotateGestures.ts` 重复——两个手势模块互不依赖，为三行引一条依赖不划算；`.copy-range-band` 的色值写 CSS 字面量——同 `.feedback-range-band` 的写法；e2e 的 `putFixture` / `pickPattern` / `waitChart` 各 spec 一份是现有惯例，不在本票收拢；成交量带底边读渲染后的 `getOption().grid`——读的是实际布局，比按参数重算更不容易错；下标对在预览里用元组、在复制里拆开——各自调用处自然的写法。
- **证据**（`evidence/16/`）：`vitest-baseline.txt`、`e2e-baseline.txt`、`e2e-after.txt`、`review-standards.md`、`review-spec.md`、`copy-band.png`（Shift+拖途中的竖带，元素截图）、`copy-toast.png`（复制后的提示条）。截图拍于 171c752（合进票 15 之前；票 15 只改左右栏，不影响这两处的样子）。
- **未安排人审**：票面那一行照旧（按住 Shift 点 / 拖的手势、竖带的样子、`range` 这个词顺不顺手；没有 build-on point）。另：app 档现算时复制行写顶栏 pattern（`W底`）而不是 app 名（`bo_only`），与 compare 一致；这是本票定的，用起来觉得该写 app 名再改。
- **改动文件里 grep `docs/research`**：代码、测试、说明书为空；只有两份审查报告里提到「grep docs/research 为空」这句话本身。

## Comments

- 2026-11-16 拆票：需求来自用户在会话里的访谈（并进复制指代那套写法；Shift+拖选时段、Shift+点选单根，松手直接复制、不再按 Shift+C；行沿用现有写法带 pattern；只复制不改状态；Shift 优先于工具；event 记号上的 Shift+点照旧配对；不进词表），用户确认共识后选「写 spec + 发票 16」。人审行按 `docs/agents/review-planning.md` 由会话推荐写入，同一轮请用户确认。
