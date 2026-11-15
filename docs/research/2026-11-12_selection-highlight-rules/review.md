# 审查：规格 1.15「选中后图上怎么画」的实施（主目录未提交改动）

审查人：skeptic。依据按优先级排：规格 1.15 与 5.8 的「点样本」「同一天的几次 hit」「图上」「app 侧栏 `hits` 列表」、4.4 末条；然后是 final_report.md 第 11 节、design.md 第 10 稿、challenge.md 的 A1–D4。我没有改任何代码和测试。

## 先说结论（白话）

**做了什么**

- 读了全部改动和新增的两个文件。
- 跑了单元测试、类型检查、后端序列化测试，以及 11 个相关的端到端测试文件。
- 用一个只读的无头脚本在 CRNC 上走了 15 个选中场景：前 13 个看 compare 模式的副图，后 2 个看 app 模式的侧栏。每个场景都把图上各系列的「淡 / 不淡 / 粗框」数出来，并截了图。脚本拦掉了所有写请求，不保存、不按 Enter。

**说明什么**

- 规律是照规格整套实现的。「同一天只亮 ↓ 第一个」和走动时 ↓ 落的那一个用的是同一份顺序，不是另排一遍。
- 旧的画法都删干净了。每个场景里当前日竖线上只有一个粗框。
- lead 点名的 CRNC 六个现场全部和规格对得上：event today 12-02、买点日 12-02、event step 11-21→11-22、一次 hit、样本 a、默认聚焦。

**不说明什么**

- 节点漏斗候选表的选中行，和主图价格区的粗框与画淡，没在真页面上看过，只读了代码和单元测试。CRNC 的 new_step 没有画在价格区的 node。
- 画淡的程度好不好看，要用户在 CRNC 上看过才算数。这不在本审查范围内。

**判定**

- **暂不通过**：有 2 条必修，都是小改。
- 修完后复审只需看这两处，再重跑 `npm test` 和 `e2e/feedback.spec.ts`，不必全审。

---

## 必修

### M1 反馈在外层时还画着竖带

**现象**

- 选中一条反馈后按 → 走进它装着的买点日，路径变成 `[feedback f-pc-74, buy 819]`。
- 这时反馈记号下已经画了外层底线，▼ 上也画了粗框。
- 但贯穿主副图、两侧深色实线的竖带还在。见 `repro/screenshots/review_13_feedback_into_buy.jpg`：两条深色竖边在 x≈1228 和 x≈1978。
- 竖带是「这条反馈被选中」的样子，所以图上同时出现了两处「选中」。

**依据**

- 规格 5.8「图上」写「粗框……全图只有一个」，反馈的粗框是「反馈带上那一块」。
- `spec.md:946` 写竖带属于「选中的那条」。
- `spec.md:940` 写「选中换成别的东西后，记号的粗边与竖带取消」。走进买点日后，选中的已经是买点日。
- design.md 有两处明写外层无竖带：
  - 第 84 行表格：「反馈记号下**底线**；无竖带（竖带是反馈被选中时的样子）」；
  - 第 192 行：「反馈在外层时不再画竖带」，并给了理由：底线已经横跨它的起止，再画竖带就是同一件事画两遍。
- final_report.md:53「改了口径」里也列了这一条。
- 规格 1.15 本身没写这句，见建议 S1。

**原因**

- 竖带由 `path2_web_ui/src/components/KlineChart.vue:312` 的 `selectedSpan` 决定。它读的是 `fb.selectedId`。
- `path2_web_ui/src/stores/feedback.ts:290` 的 watch 只要路径上**任何一节**是反馈，就把 `selectedId` 设成它。所以反馈退到外层后，`selectedId` 仍然有值。
- writer 交付时把这条列为自己取的默认：「竖带仍按 `fb.selectedId`」。

**复现**

无头脚本 `repro/review_steps.json` 第 12、13 步，在 compare 模式、CRNC 上：

1. `v.setPath([{kind:'feedback',id:'f-pc-74'}])` → 竖带在，正确；
2. `v.stepPos(1)` → 路径变成 `[feedback, buy 819]`，`[data-testid=feedback-selected-band]` 仍在，`fb.selectedId === 'f-pc-74'`。

**修法要成对**

- 竖带只在两种情况下画：
  - 作答面板开着（画面板的范围），这一支保持不变；
  - 选中的那一个就是这条反馈，即 `highlight.focus` 是这条反馈。
- 同一判据也要用到 `KlineChart.vue:303` 的 `selectedFeedbackRange()`。它决定能不能拖竖带的边改起止，被 `:1239` 交给拖动逻辑。
- 只改竖带、不改它，会留下一条看不见却能拖的边。那段注释本身就在防这种情况。
- 反馈退到外层后不能拖边，这和规格「按住**选中**那条反馈的竖带」一致。
- `feedback.ts` 的 watch 可以不动：反馈在外层时，「对选中的那一个作答」仍要靠它。

**测试**

- 在 `e2e/feedback.spec.ts`，或 `tests/components.feedback-clicks.spec.ts` 里加一条：选中反馈后进到它的买点日，竖带消失、改起止不可用；Esc 退回反馈后竖带回来。

### M2 hits 行个数搬家时丢了三条仍然有效的断言

**现象**

- 个数原来在 `makeRenderBracket` 里画，现在搬进 `makeRenderSelection`，见 `path2_web_ui/src/render/chart.ts:1282-1290`。
- HEAD 的 `tests/chart.spec.ts:919` 那条测试断言了三件事：
  - 只有一次 hit 时不写个数；
  - 一根 K 线 3px、比数字还窄时不写个数（`size: () => [3, 0]`）；
  - 第二行的顶照 `laneTops` 取，`y = 30 - 1`。
- 新测试 `tests/chart.spec.ts:282-297` 只留了「没留个数行时不写」。
- 这三支代码都还在：`n < 2`、`api.size([1,0])[0] < digitsW - 1`、`laneTops?.[lane]`。全仓 `tests/` 里没有别处覆盖。
- 这是放宽了断言，不是画法变了。

**修法**

在 `makeRenderSelection` 那条测试里补三行：

- `n: 1` → 空 group；
- `api.size` 返回 `[3, 0]` → 空 group；
- `value: [10, 10, 1]` 加 `laneTops [4, 30]` → `y === 29`。

---

## 建议

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| S1 | `.scratch/annotation-path2/spec.md:940`、`:946`；1.15 | 第 940 行还写着「它收进来的 hit 的格加细实线框」，和 `:571`「不再有的画法：……`hits` 行细实线框」直接矛盾。另外 1.15 和 5.8「图上」都没写「反馈在外层时不画竖带」，只有 design 和 final_report 写了。 | 这是 lead 的文档活：把第 940 行改成「它收进来的 hit 照常、其余画淡（1.15）」；在 5.8「外层底线」那条补一句「反馈在外层时只画底线，不画竖带」。M1 修完后，规格和代码才对得上。manual 第 513 行「选中的那条……竖带」不用改。 |
| S2 | `path2_web_ui/e2e/sidebar-chart-focus.spec.ts`（不在 diff 里） | 它断言的东西大多被这次删了：`candidateHitIds`（:297、:422）、`highlight-price` 系列和 `pendingDisambig`（:434-440）、「group 黑框」「候选虚线」「闪烁」。另外 :298、:421 读的 `pendingDisambigEventId` 在 HEAD 的 src 里就已经不存在，所以它在 HEAD 已经是坏的。全仓 grep 这次删掉的名字，测试里只剩这个文件命中。 | 交 lead 定是重写还是退役，不算 writer 的必修，但它也不能算进「e2e 通过」。它是唯一一个端到端测「侧栏 ↔ 图」联动的文件，退役的话，侧栏 `hits` 列表的黑粗边与蓝条就只剩 vitest 覆盖。 |
| S3 | `path2_web_ui/src/stores/view.ts:1330`（`markedEventIds`）、`DetailSidebar.vue:103` | 路径上最里面的 event 会给候选表那一行挂 `attr-row--selected`，现在的样式是 2px 黑实线框。走进它的买点日或一次 hit 以后，它已经是外层，但候选表里仍像「选中的」。HEAD 的语义也差不多（`selectedInstanceId ?? focusedInstanceId`），不算回归。只是样式换成黑粗边以后，和规律「粗框只给选中的那一个」读起来冲突。 | 只在路径最里面一节是这个 event 时挂黑框；它是外层时不标，或改成底线。优先级低，可以等用户看过再定。 |
| S4 | `path2_web_ui/src/render/annotateLanes.ts:75-76` 与 `chart.ts:1025-1029` | 外层底线的粗细和颜色定义了两份：`UNDER_LINE_H = 2.5`、`UNDER_LINE_COLOR = '#1e293b'` 一份，`UNDER_H`、`FRAME_EDGE` 另一份。这些都是标了「待验证」、之后要调的值，两份会漂开。 | 让 annotateLanes 从 chart.ts（或一个共用常量文件）导入。 |
| S5 | `path2_web_ui/e2e/fold-rows.spec.ts` | 原来断言粗框落在指定成员上（`instance_id === one.member_ids[0]`），现在只比位置（`value.slice(0,2)`）。selection 系列的数据不带 `instance_id`，改成比位置可以理解，但比原来弱：同一格里换成别的成员也能过。 | 能接受。想补的话，让 frame 数据带上被框的 id。 |
| S6 | `path2_web_ui/tests/chart.spec.ts:118` | 注释里还写着已删的 `makeRenderHighlightWithGeom`。 | 顺手改掉。 |
| S7 | `chart.ts:1288` | 个数画淡时连白边一起乘 0.5，竖线从画淡的数字里透出来一半。见 `review_08_node_step.jpg` x≈1507。 | 只给数字本身画淡、白边不透明，或者就这样留着，等用户在 CRNC 上看。属于「待验证」的范围。 |

---

## 通过

### 规律实现完整、无例外

`path2_web_ui/src/render/selHighlight.ts` 是纯函数，`stores/view.ts:1325` 只接它的结果。下面逐条对规格核对，每条后面是在哪看到的。

- **粗框只有一个**：每个场景 selection 系列里的 `frame` 都只有 1 个，样本和框用的是用户那边原有的选中画法。截图 02–13 都在当前日竖线那一列，只有一个框。
  - node → 轨名框，`review_08`；
  - 一族 → 整行框，`review_07`；
  - 反馈 → 反馈带那一块，`review_12`。
- **外层底线**：
  - event 的外层 node 在轨名下画底线，见 `review_02`、`review_04`；
  - 一族在 `hits` 行那一行画底线，见 `review_03`、`review_05`；
  - 样本在 `user` 跨度下画底线，见 `review_10`；
  - event 在外层时在格下画底线，见 `review_06`；
  - 反馈在外层时在记号下画底线，见 `review_13`。
- **组成、牵出、牵出的组成照常，按边画淡**：
  - 选中 event 时，用户那边不动（`dimUser = false`）；
  - 选中样本时两边都淡，用户那边是非成员框淡（`review_09`）；
  - 选中框时只有 app 那边淡，因为框没有组成，用户那边原样（`review_11`）；
  - 什么都没选时都不淡，见 `tests/render.sel-highlight.spec.ts:77`。
- **同一层只亮记号本身**：
  - 选中 event → 整条 band 照常，见 `review_02` 的 today 行、`review_04` 的 step 行；
  - 选中一族 → 所有族照常、不带组成，见 `review_07` 的 new_plat 第二行是淡的；
  - 选中样本 → a、b、c 三个 ▲ 都照常，见 `review_09`。
- **合并记号有一个照常就照常**：`hits` 行同一天共用一格，个数照写。粗框和个数压在竖线上面（z:31 高于 z:30）。
- **`hidden`**：选中的东西在当前档位下画不出时，轨名旁挂 `hidden` 并框住。判断在 `selHighlight.ts:235-240`，画法用等宽字、黑色。vitest 有覆盖。
- **默认聚焦的样本算选中**：`review_01` 一打开两边就按它画淡。「默认聚焦不设为标注当前样本」那条没动，见 `stores/compare.ts` 的 watch。
- **app 侧栏 `hits` 列表**，在真页面上看过：
  - 选中买点日 12-02 → 这天两行连成一块黑粗边，↓ 第一个那行挂蓝条，见 `review_14_app_sidebar_buy_1202.jpg`；
  - 选中 event step 11-21→11-22 → 每个买点日用到它的那一行挂蓝条，没有黑粗边，见 `review_15_app_sidebar_event_step.jpg`。

### 「↓ 第一个」和走动同源

- 牵出 hit 的取法在 `selHighlight.ts:148-158`：
  - 买点日、样本、框取 `world.members(path)[0]`；
  - 一族、event、反馈对 `world.inside(path,'day')` 的每个买点日 `b`，取 `world.members([...path, b])[0]`。
- ↓ 用的是 `stores/view.ts:1095` 的 `world.inside(selPath,'stack')`。同一个 world、同一份顺序，没有另排。
- 真页面上的对照：

| CRNC 现场 | 路径 | 结果 |
|---|---|---|
| event today 12-02 | `[node today, event today_795#0]` | 12-02 那天亮的是第 1 次（`#0`），也就是 ↓ 落的那次 |
| 买点日 12-02 | `[family hits@774, buy 795]` | ▼ 有粗框；只亮第 1 次的组成（new_plat 第一行的那格），第 2 次的组成是淡的 |
| event step 11-21→11-22 | `[node step, event step_789_790#0]` | 每个买点日亮的都是用到这个阶跃的那次（new_plat 第二行），侧栏蓝条同样落在 step→11-22 那几行 |
| 从 event step 走进 12-02 | `[node step, event step, buy 795]` | 亮的是第 2 次，也就是用到 step 的那次，和走动顺序「用到它的排前面」一致；从一族走进同一天时亮的是第 1 次 |
| 一次 hit | `[family, buy 795, hit #0]` | 只亮它自己的组成，外层一族画底线 |
| 样本 a | `[sample s-pc-44]` | 亮的是配对那次，同一天另一次的组成画淡；↓ 进去落在同一次（`review_10`） |
| 默认聚焦 | 打开 compare 时的样本 | 一打开两边就按它画淡（`review_01`） |

### 旧画法全部删除

- `src/` 里 grep 这些名字为空：`highlightedEventIds`、`compositionGroupIds`、`candidateHitIds`、`pendingDisambig*`、`markedHitIds`、`activeFamilyKey`、`SAMPLES_ROW_KEY`、`highlight-price`、`MEMBER_DASH`、`makeRenderHighlight*`、`buildHlShape`、`HL_SHADOW`、`pendingBlink*`。
- 真页面的系列清单里也没有这些。一族被选中时 `hits` / `user` 不再加粗，样本的成员框不再加粗。

### 调色板

`path2_web/serialize.py` 的 `_PALETTE` 改成 `["#1a80ba", "#d7000f"]`，注释和测试同步改了，`_palette_problems` 校验通过。

### 测试

| 命令 | 结果 |
|---|---|
| `cd path2_web_ui && npm test` | 1624 过、4 败。4 个失败全在 `tests/components.sidebar-result-list.spec.ts`（75% 格式、全局按键转发）。我在 HEAD 的临时 worktree 里跑，同样是这 4 个失败；这个测试文件和它测的组件都不在 diff 里，所以是本来就有的 |
| `npx vue-tsc -b` | 退出码 0 |
| `uv run pytest tests/path2_web/test_serialize.py -q` | 31 过 |
| e2e：fold-rows / hit-event-disambig / annotate-compare / feedback / annotate-samples / annotate-boxes / annotate-grouping / annotate-direct-links / annotate-ref-peaks | 3 / 3 / 2 / 8 / 2 / 4 / 1 / 2 / 2，全过 |
| e2e：annotate-open-by-symbol | 3 条里 2 条过。没过的第 95 行那条，打开的是真实后端 8001 里最新一条扫描：20261103 的 bo_only，`hits: 0`。结果列表是空的，等不到 `td.sym[data-symbol]`。这一步在任何选中或画法断言之前，和本次改动无关 |
| e2e：sidebar-chart-focus | 5 条全败。卡在第 86 行准备阶段：同样是最新一条扫描为空，没选中股票，DetailSidebar 没挂出来。另外这个 spec 本身已经过时，见 S2 |

**HEAD 对照的说明**：上面两个 e2e 失败我没在 HEAD 上跑，因为 5171 服务的是工作区。「和改动无关」是从失败位置推出来的：失败发生在依赖真实扫描数据的准备步骤，先于任何选中断言。

**断言有没有放宽**：

- M2 那三条是放宽了；
- S5 是变弱，但可以接受；
- 其余测试的改动是把旧集合换成 `highlight` 的对应字段，同时改了说明文字，没有删掉仍然有效的行为。具体看过的文件：kline-click、kline-click-fold、fold-rows e2e、hit-event-disambig e2e、compare-layer、feedback e2e、annotate-compare e2e，以及各个 store 测试。

### 实施产出不引用研究目录

在 diff 新增的行和两个新文件里 grep `docs/research`、cmp、Q 编号、sk、inv、W 编号，都为空。`view.ts` 第 8、328、1184 行是旧有内容，不算。

### lead 改的 spec / manual

- 1.15、5.8「图上」、`hits` 列表、4.4 调色板这几处，和代码一致。
- manual 新加的「三样画法各答一个问题」和代码一致。
- 只有两处不一致，见 S1：第 940 行的旧文字，和「外层不画竖带」没写进规格。

---

## writer 三处需定的看法

1. **路径最外一节是一族时，`hits` 行整行照常。** 同意。按规律，一族的同一层就是所有族，design 表「一族」那一行也是这样写的。可见的后果：从一族点 ▼ 走进来时，`hits` 行一格都不淡，见 `review_03`、`05`、`07`。这是规律推出来的，不是漏画。正是用户要在 CRNC 上确认的那类地方，建议 lead 汇报时点出来。
2. **没算进牵出的 hit，它的终点格只在和 ▼ 共格时照常。** 同意。这是「合并记号有一个照常就照常」的直接结果。不共格时它就是普通的「其余」，该淡。
3. **选中 event 时，同一层是整条 band 的格，所以整条 band 照常。** 同意。← / → 在这条 band 的格之间走，正是同一层的定义。`review_02` 的 today 行、`review_04` 的 step 行都是这样。

writer 自己取的两个默认：

- **annotate 模式下，「当前标注样本」不在路径上时仍保留强调**：可以。它是「正在标哪个」的提示，不是选中的画法，代价小。
- **竖带按 `fb.selectedId` 画**：要改，见 M1。

---

## 附：本次审查新增或改动的研究目录文件

- `repro/sk_run.cjs`：拦掉一切非 GET 请求，预置 compare 用的 pattern，支持 jpg 截图和 `DSF` 环境变量。
- `repro/review_steps.json`：场景 01–13。
- `repro/review_sidebar_steps.json`：场景 14–15，切到 app 模式、打开侧栏。
- `repro/screenshots/review_01…15_*.jpg`：每张都在 150KB 以内。
- 验证 HEAD 用的临时 worktree 已删，主目录的 `node_modules` 完好。这次没用 playwright MCP，不需要清 `.playwright-mcp`。


---

## 复审（第二轮，11-13）

### 先说结论（白话）

**做了什么**

- 读了 writer 第二轮的改动。
- 重跑了单元测试、类型检查和 5 个端到端测试文件。
- 在 CRNC 真页面上用无头脚本把「选中一条反馈」之后的各种走法过了一遍：
  - 进去、退出来；
  - 点副图空白、点主图空白；
  - 换股票、换 pattern 再换回来；
  - 跟一个落在同一张图的直达链接；
  - 从侧栏点行跳到另一张图。
- 测试有没有约束力，用的办法是「拔掉被测的那段代码，看测试会不会失败」，都在 scratchpad 里的前端副本上做，验完副本已删，主目录代码没碰：
  - M2 补回的三条断言、S7、M1 的 vitest，这样拔过；
  - M1 的 e2e 和 S5，只读了代码。

**说明什么**

- 两条必修都修好了，补的测试拔掉被测代码就会失败。第一轮的 7 条建议都落实了。
- 重写的「侧栏 ↔ 图」联动测试能跑通。它起的临时扫描只删自己那一份，跑完 8001 的扫描历史和跑前一样。
- 选中一条反馈后往里走，图上不会同时出现两处选中。

**还剩一处**

- 有一种情况是「什么都没选，那条反馈却还挂着粗边和竖带」：先选中一条反馈，再跟一个落在同一张图的直达链接。这能稳定复现（R1）。
- 它在 HEAD 上就有，不是这一轮新开的口子。但 lead 刚改的 `spec.md:946` 写的是「竖带只在这条反馈就是选中的那一个、或它的面板开着时画」，它和这句冲突。
- 修法很小。

**判定**

- 两条必修已修好，第二轮本身通过。
- R1 建议本轮顺手修。挡不挡合并由 lead 定：它是 HEAD 的既有行为，触发路径也不常见。

### 必修复核

**M1 反馈在外层时不再画竖带：已修**

- 改法：`KlineChart.vue:226` 新增 `focusedFeedbackId`。竖带（`selectedSpan`，:318）、拖边（`selectedFeedbackRange`，:309）、记号粗边（`cmpFeedbackMarks`，:232）三处都只认它。
- 真页面 CRNC 上的结果（`repro/review2_fb_steps.json`）：

| 步骤 | 路径 | 竖带 | 记号 |
|---|---|---|---|
| 选中 f-pc-74 | `[feedback]` | 有 | 粗边 |
| 按 → | `[feedback, buy 819]` | **无** | 只有底线（`review2_01_fb_outer_no_band.jpg`） |
| Esc | `[feedback]` | 回来 | 粗边 |
| 再 Esc | `[]`，`fb.selectedId = null` | 无 | — |
| 选中反馈后点副图空白 | `[]`，`selectedId` 清掉 | 无 | — |
| 在外层时点副图空白 | `[]` | 无 | — |
| 侧栏点 f-pc-72 那一行，跳到 INDO | `[feedback f-pc-72]` | 有 | 粗边（`review2_05_sidebar_jump_INDO.jpg`） |

- 测试有约束力：
  - 在副本里把 `focusedFeedbackId` 改回 `fb.selectedId`，`KlineChart.feedback-open.spec.ts` 的「退到外层」那条会失败（21 条里失败 1 条）。
  - e2e `feedback.spec.ts` 新加的那段进去、退出、看光标，本轮跑通了。

**M2 补回个数的三条断言：已修，而且有约束力**

在副本里逐条拔掉 `chart.ts` 中被测的分支，再跑 `tests/chart.spec.ts`：

| 拔掉什么 | 结果 |
|---|---|
| `n < 2` | 失败（`expected undefined to deeply equal []`） |
| 「一根比数字窄」那支 | 失败 |
| 行顶按 `laneTops[lane]` 取，改成恒取第 0 行 | 失败：新测试第二行断言 `29`，旧的 `makeRenderBracket` 那条也失败 |
| S7 改回整体画淡（白边一起透明） | 失败（`expected 1 to be undefined`） |

### 建议复核

| # | 结果 |
|---|---|
| S1 | lead 改的规格和代码基本一致：`spec.md:567` 外层底线那条写了「反馈在外层只画底线、不画竖带；外层的 event 在候选表不挂黑粗边」；`:940` 改成「照常、其余画淡」；`:946` 写了竖带什么时候画。唯一出入是 R1 |
| S2 | `e2e/sidebar-chart-focus.spec.ts` 整份重写成 3 条，测的是这次的新画法（侧栏行黑粗边连块、蓝条只挂 ↓ 第一个、点格后进买点日外层不再挂黑框），3 条都过。夹具见下面「smallScan 夹具」 |
| S3 | `view.ts:1331`：只有选中的就是这个 event 时才标。`stores.focus-derivations.spec.ts:113` 断言它退到外层后不再标 |
| S4 | 底线的粗细和颜色统一到 `subGeometry.ts:40-41`（`SEL_EDGE_COLOR`、`UNDER_LINE_H`），annotateLanes 和 chart 都从这里取 |
| S5 | selection 系列的数据带上了 `instance_id`，`e2e/fold-rows.spec.ts:200` 恢复按成员断言。但 `chart.ts` 是把选中 event 的 id 原样写进去的，:191 已经断言过同一个 id，挑的又是只有一个成员的格，所以 :200 几乎不加约束；真正管事的是 :201 按位置断言，那条第一轮就有。结论仍是可以接受 |
| S6 | 注释已删 |
| S7 | 个数画淡时只淡数字（`rgba(17,17,17,0.5)`），白边不透明，有测试且拔过（见上表最后一行） |

### smallScan 夹具（lead 第 3 问）

- `e2e/smallScan.ts` 是现成的夹具，fold-rows 一直在用，这次 sidebar-chart-focus 也改用它。
- 起扫描时把 `note` 设成 `e2e_<tag>_<毫秒时间戳>`。后端把 `note` 当文件名，同名已存在时直接回 409、不写（`path2_web/api.py:777-780`），不会覆盖用户的扫描。
- 删的时候只 `DELETE /scans/{这个名字}`，后端只删 `scans/{name}.json` 这一个文件（`scan.py:528-531`）。
- 实测：
  - 跑前跑后 `/scans/` 都是同样 5 条（20261103T010617、20261028T063406、20260908T113225、20260907T051628、20260906T231146）；
  - `outputs/path2_web/scans/` 里没留下 `e2e_*`；
  - `annotations/` 里今天 03:00 以后没有任何文件被改。
- 小代价，不挡合并：
  - 跑的过程中，用户在「打开历史」里会短暂看到一条 `e2e_…`；
  - 有两种情况会留下一条要手动删的扫描：
    - e2e 进程被强杀，`afterAll` 跑不到；
    - `runSmallScan` 等 4 分钟超时抛错时，后端扫描其实还在跑，`afterAll` 的删除打在还不存在的文件上、错误被吞掉，文件之后才落盘。

### 测试

| 命令 | 结果 |
|---|---|
| `npm test` | 1624 过、4 败。还是 `components.sidebar-result-list.spec.ts` 那 4 个老失败 |
| `npx vue-tsc -b` | 0 |
| `uv run pytest tests/path2_web/test_serialize.py -q` | 31 过 |
| e2e（`--workers=1`）：feedback / fold-rows / annotate-compare / hit-event-disambig / sidebar-chart-focus | 8 / 3 / 2 / 3 / 3，全过 |

注：S4 动了 `annotateLanes` 的常量来源（数值没变），annotate-samples、boxes、grouping、direct-links、ref-peaks 这 5 份 e2e 本轮没重跑。第一轮它们全过。

### 新建议

**R1 「什么都没选，反馈却还挂着粗边和竖带」：可复现，HEAD 就有，和规格 946 冲突**

- 回答 lead 第 1 问：
  - 新加的「路径清空而反馈仍选中」这一支，不会造成两处选中，因为路径非空时它不起作用。
  - 但它把 HEAD 就有的一种残留原样保留了：`stores/feedback.ts:290` 的 watch 在路径清空时不清 `fb.selectedId`（不在 diff 里）。
- 复现（`repro/review2_land_steps.json`，截图 `review2_04_direct_link_same_chart.jpg`）：
  1. CRNC、compare，选中 f-pc-74，路径是 `[feedback]`；
  2. 地址栏换成 `#symbol=CRNC&date=2024-12-02&pattern=new_step&mode=compare`（落在同一张图的直达链接）；
  3. 落下后路径 `[]`，显示栏九格全是 `—`，什么都没画淡；但 `fb.selectedId` 仍是 f-pc-74，那条反馈挂着粗边和竖带，拖它的边也照样能改起止。
- 原因：`landing.ts:54` 落下时先 `clearFocus()`，这一步不清 `fb.selectedId`。直达链接的落下（`directLinks.ts:81`）没有回调，路径就停在空的。
- 没复现出来的路：
  - 换股票（AA）再换回 CRNC、换 pattern 再换回来，`selectedId` 都留着，但回到 compare 时默认聚焦的样本把路径占成 `[sample]`，它被清掉了；
  - 从侧栏点行跳图，落下的回调会 `fb.select` 一次，路径正确地变成 `[feedback]`（上面 M1 表最后一行）。
- 改法，只写目标，未验证：路径被清空时，反馈不再显得被选中。两种做法任选：
  - **去掉 `focusedFeedbackId` 里「路径空」那一支（:229）。** 在副本里试过：`KlineChart.feedback-open.spec.ts` 和 `components.feedback-clicks.spec.ts` 照过（37/37）。全量 vitest 在副本里跑不了，因为有测试会读仓库里 `path2_web_ui` 以外的文件。侧栏跳图的 e2e（`feedback.spec.ts:987`）去掉这一支后还过不过，没有在副本里跑。
  - **在落下时把 `fb.selectedId` 一起清掉。** 侧栏点行跳图的流程，落下后回调会再 `fb.select` 一次。

**R2 （观察到，未确认是不是问题）compare 下点主图 K 线区的空白，不清选中**

- 复现：选中 f-pc-74 后，点主图 K 线区空白处，试了两处，都落在主图画布上。路径仍是 `[feedback]`，竖带仍在。
- 竖带和选中是一致的，所以不算竖带残留。但它和规格「点空白一下全清」（5.8 Esc 那条）、「点图上空白……取消选中」（:946）对不上。
- 原因：compare 下主图 K 线区的点击归标注手势，`KlineChart.vue:1251` 的 `select(null)` 只清标注的选中。
- 这段代码和 `annotateGestures.ts` 都不在 diff 里，但我没在 HEAD 上实跑。现有 e2e 只测了「点主图网格外的左上角」（`shift-pair-feedback.spec.ts:163`）和「annotate 下点 K 线区空白清当前样本」（`annotate-samples.spec.ts:64`）。
- 要不要管，由 lead 看。

### 其他

- 仓库根目录有一个未跟踪的 `.playwright-mcp/`，里面是今天 04:06 的 console log。不是我留下的，我两轮都没用 playwright MCP。按用户规则，应该由用过它的那位清空（`find .playwright-mcp -mindepth 1 -delete`）。
- 本轮新增的研究目录文件：
  - `repro/sk_run.cjs` 加了 `key`（禁止 Enter）、`mouse`、`symbol` 三种步骤，仍然拦掉一切非 GET 请求；
  - 场景文件 `repro/review2_fb_steps.json`、`review2_pat_steps.json`、`review2_land_steps.json`、`review2_blank_steps.json`、`review2_find_steps.json`；
  - 截图 `repro/screenshots/review2_01…05_*.jpg`。
- 换 pattern 只在现有的 `new_step` 和「不选 pattern」之间切，不建新 pattern。
- 直达链接和侧栏点行只是打开图，不写任何东西。
