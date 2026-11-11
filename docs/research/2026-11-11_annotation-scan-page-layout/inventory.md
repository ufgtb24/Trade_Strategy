层级：研究
作者：inventory（事实盘点）　状态：完成

# 页面区域盘点：标注与扫描在同一页面上各占了什么

本文件只列事实，不出方案。每条事实给出依据（组件文件 + 关键条件）。路径相对仓库根，前端在 `path2_web_ui/src/`。

**核实程度**：annotate、compare、现算 app 三列读代码 + 浏览器截图核对过。**「app 扫描」一列只读了代码**：盘上没有一份扫描能在网页里正常显示（见第 4.3 节），所以这一列没有正常状态的截图。浏览器里只看、没改任何标注；没有发起扫描。

## 先说结论（不含术语）

- 左边那一整条（约占屏宽一成）在标注时没有任何用处：它的三块全是旧扫描功能，四种状态下长得一模一样，没开扫描时只写两遍「未加载扫描结果」。打开过扫描以后它还会抢键盘：敲一个字母就把焦点拽进扫描搜索框（已在浏览器复现）；上下方向键在标注的文本框里按也会把你带去扫描列表的股票、并离开标注（读代码 + 隔离单测确认）。
- 右边一栏在标注时是标注侧栏，在 app 时是诊断侧栏，两者互斥；图区上方的深色档位条只在 compare 和 app 出现。
- 画图的代码只有一份：compare 的下半区和两种 app 是同一套画法，图组件一个管四种状态。真正只属于扫描的是左栏三块、几个扫描对话框、参数抽屉与参数 chip、诊断侧栏的一部分入口。
- 「标注工具的 app 只显示标过的股票」的推断成立，但要修正两点：反馈状态只跑「有反馈的股票」（不含只有样本的），而且只在 compare 下取；改版报告跑「有样本或有反馈的股票」，代码不在 skill 脚本目录而在后端 `path2_web/annotation/revision.py`。
- 扫描界面最近没人用：盘上没有一份扫描能正常显示，11-04 改名以后网页里没跑过一次扫描。依赖「扫描」的东西大多依赖的是扫描文件和后端模块，不依赖界面；真正挂在界面上的只有两处（诊断技能的探索态参数文件、e2e 借扫描入口测共用画法）。
- 从扫描结果进入同一张图接着标注的路径在代码里存在（点顶栏 annotate，股票不换），e2e 也测了一条类似的；但说明书的「找图」只列了大涨段清单、random、按代码打开三个入口，没写这种用法；也找不到用户这样用过的证据，标过的 7 只股票有 5 只在大涨段清单上，测这条路径的两条 e2e 从 11-04 起是红的（第 5.3 节）。用户 11-05 自己提过「把 rally 和 random 的结果放进左侧列表」（第 5.4 节）。

## 0. 四种状态怎么进来

| 状态 | 怎么进来（代码） | 图上画什么 |
|---|---|---|
| `annotate` | 页面打开默认（`stores/view.ts:269` `mode = 'annotate'`）；顶栏 symbol、rally、random、链接打开图（`openSymbol`，`view.ts:723`）；顶栏点 `annotate`（`enterAnnotate`） | 这只股票截到训练段末日的全部 K 线 + 成交量 + 用户的框和样本；不画任何 app 产物（`effectiveAnalysis` 在 annotate 恒为 null，`view.ts:504`） |
| `compare` | 顶栏点 `compare`（`stores/appLink.ts` `setMode` → `view.enterLinked('compare')`）；feedback 页点一行、落在 compare 的链接（`stores/landing.ts`）。要求：标注的「当前 pattern」恰好有一个能用的 mapping，且已打开一只股票（`appLink.available`） | 标注层 + 当前 pattern 的 app 对这一只股票**现算**的输出（`/preview`） |
| `app`（现算，appSource = linked） | 从 annotate / compare 在顶栏点 `app`（`enterLinked('app')`），条件同 compare | 只画 app 现算的输出，按 node 分轨 |
| `app`（扫描，appSource = scan） | 左栏「打开历史 …」打开扫描文件（`loadScanFile`，`view.ts:643`，会把 symbol 设成扫描第一只股票）；或在左栏扫描列表点一行 / 按 ↑↓（`selectSymbol`，`view.ts:710`） | 扫描文件里存好的产物，K 线只取扫描窗口那一段（`KlineChart.vue:652`） |

注意两件事（后面多处会用到）：
- 顶栏的 `app` 按钮在两种 `app` 之间不区分。在扫描的 `app` 下它是按下的、点了不动（`TopBar.vue:33-35`）；从扫描的 `app` 想看现算的 `app`，要先切 `compare` 再切 `app`。从现算的 `app` 回到扫描的 `app`，只能在左栏列表里点一行。
- 页面上同时存在**两个「当前 pattern」**：标注的当前 pattern（顶栏 `pattern` 一格，`stores/annotation.ts:284`，存在浏览器里；compare / 现算 app 用它找 mapping 和 app），和扫描的 active pattern（图区上方条里的下拉，`view.activePatternId`，只在扫描的 `app` 下出现；`path2_web/GLOSSARY.md:20`）。两者互不联动。

## 1. 区域 × 状态表

格子写法：**在用** / **空着**（占地方但没内容或没用处）/ **不出现**（不占地方）/ **灰掉**（出现但点不了）/ **副作用**（不该在这个状态起作用却起作用）。「有扫描」指本页之前打开过一份扫描文件、还没关（打开后一直留着，切模式不会清，`view.ts:671` 只有删掉当前扫描才清）。

### 1.1 顶栏（`components/TopBar.vue`，四种状态都在）

| 控件 | annotate | compare | app 现算 | app 扫描 | 依据 |
|---|---|---|---|---|---|
| `symbol` 输入框 | 在用 | 在用（换图留在 compare） | 在用（换图**落回 annotate**） | 在用（换图落到 annotate，扫描留着） | `openSymbol`：`mode !== 'compare'` 时一律设 annotate（`view.ts:724`） |
| `rally` / `random` | 在用 | 在用 | 在用（点后落回 annotate） | 在用（点后落回 annotate） | 同上；rally 清单是顶栏下方的浮层（`RallyList.vue`，`v-show` 保留排序与滚动位置） |
| `mode` 三按钮 | 在用 | 在用 | 在用 | 在用，但 `app` 按钮语义变成「扫描结果」 | `TopBar.vue:27-40`；`modeTitle` 在 app 扫描下悬停写 `scan results` |
| app 名 + `loading`/`load_failed` | 不出现 | 在用 | 在用 | 不出现 | `v-if="linkedView && …"` |
| `tiers` 复选框 | 灰掉 | 空着（能勾，但不起作用） | 空着（同左） | 空着（同左） | `tiersOn = mode === 'app' \|\| mode === 'compare'`；全前端只有这个复选框自己读 `view.tiers`（grep 无别的读者），小字已不画；规格 5.2 记为「拟删、待用户确认」 |
| `tool`（box / point / feedback） | 在用（box、point） | 在用（多 feedback） | 不出现 | 不出现 | `v-if="annotating"`；feedback 只在 compare |
| `pattern`（标注的当前 pattern） | 在用 | 在用 | 不出现 | 不出现 | `v-if="annotating"` |
| `ref` · `peaks` | 在用 | 在用 | 灰掉 | 灰掉 | `refLayers.available`：只在 annotate / compare（`stores/refLayers.ts:27`） |

### 1.2 左栏（`components/App.vue` 的 `aside.left`，四种状态**完全一样**，没有任何按模式的分支）

左栏宽度：`minmax(220px, max-content)`、最多半屏（`App.vue` 的 `.app` grid 与 `.left max-width: 50vw`）。没扫描时 220px；有扫描时按表格内容撑宽。

| 块 | annotate | compare | app 现算 | app 扫描 | 依据 |
|---|---|---|---|---|---|
| Patterns（扫描里各 app 的显隐勾选） | 没扫描：空着（写「未加载扫描结果」）；有扫描：空着（勾的是扫描列表的列，和这张图无关） | 同左 | 同左 | 在用 | `SidebarPatternPanel.vue`，只读 `scanFile` |
| 扫描按钮行（`扫描 ⚙`、`打开历史 …`、进度） | 空着（入口按钮，标注用不到）；扫描在跑时进度行照常显示 | 同左 | 同左 | 在用 | `SidebarScanPanel.vue`，无模式条件 |
| 扫描列表（搜索框 + 表格） | 没扫描：空着，整块只写「未加载扫描结果」；有扫描：空着 + **副作用**（见 1.6） | 同左 | 同左 | 在用 | `SidebarResultList.vue:3,17`，`v-if="scanFile"` |

左栏三块在 annotate / compare / 现算 app 下没有一处为标注或现算服务；它占着全页高度、至少 220px 宽。

截图量出的比例（视口 2192 CSS 像素宽，`repro/s1_annotate_noscan.png`）：左栏 220（10%）、图 1652（75%）、标注侧栏 320（15%）。刚打开页面、还没开图时（`repro/s0_fresh.png`）中间整块空白，左栏两处「未加载扫描结果」，右栏 `empty`——整页没有一处告诉你从哪开始。打开扫描后切回 annotate（`repro/s7_annotate_with_scan_letter_hijack.png`），左栏按扫描表格撑到约 264 宽。

rally 浮层（`repro/s9_rally_popover.png`）278×740，挂在顶栏左下，正好盖在左栏的位置上；当前配置下 300 段、242 只股票。

### 1.3 图区上方的条（`components/ChartArea.vue`）

| 条 | annotate | compare | app 现算 | app 扫描 | 依据 |
|---|---|---|---|---|---|
| 档位条（深色底，`in_hit / qualified / detected`） | 不出现 | 在用 | 在用 | 在用 | `v-if="mode !== 'annotate'"`（`ChartArea.vue:9`） |
| 　其中：扫描的 active pattern 下拉 + 参数 chip（Working Copy） | 不出现 | 不出现 | 不出现 | 在用 | `v-if="!linkedView"`；参数 chip 还要求 `scanFile && activePatternId && hasSnapshot`（`ParamsChip.vue`） |
| 　其中：副图竖直缩放 −/+/↺ | 不出现 | 在用（compare 自己一份，默认 2.0×） | 在用（与扫描 app 共用一份） | 在用 | `KlineChart.vue:10` Teleport 到 `#band-zoom-slot`；`bandZoomCmp` / `bandZoomApp` |
| 　其中：面板开关 Topology / Sidebar / Slider | 不出现 | 只有 Topology | 三个都有 | 三个都有 | `panelToggles`（`ChartArea.vue:142`） |
| 休眠草稿横幅（Working Copy 遗留草稿） | 不出现 | 有扫描且有遗留草稿时出现（扫描的东西出现在 compare 里） | 同 compare | 在用 | `DormantDraftBanner.vue`，挂在档位条下；草稿由 `loadScanFile` 扫出 |
| 拓扑面板 | 不出现 | 开关打开时在用 | 开关打开时在用 | 开关打开时在用 | `v-if="mode !== 'annotate' && showTopology"`；打开时横跨整行、约 390 高，节点只占左边约五分之一宽（`repro/s4_app_linked_panels_on.png`） |
| 标注提示条（指纹不符、冲突、保存被拒、链接没跟成） | 有事才出现 | 有事才出现 | 不出现 | 不出现 | `AnnotationNotices`，`v-if="annotating"` |

### 1.4 图区（`components/KlineChart.vue`，四种状态共用同一个组件）

| 部件 | annotate | compare | app 现算 | app 扫描 | 依据 |
|---|---|---|---|---|---|
| K 线主图 + 成交量 | 全部 K 线 | 全部 K 线 | 全部 K 线 | 扫描窗口那段 | `wholeChart = mode !== 'app' \|\| linkedView`（`:158`），`reloadBars`（`:640`） |
| 主图上方居中的股票代码 + 复制按钮 | 在用 | 在用 | 在用 | 在用 | `v-if="symbol"` |
| 主图上的价格区 node 记号（如 bo） | 不画 | 画 | 画 | 画 | annotate 走 `renderBarsOnly` |
| 主副图之间的拖动分隔条 | 在用 | 在用 | 在用 | 在用 | `ResizableDivider` 无条件 |
| 多归属待选横幅 `candidates n` | 不出现 | 有待选时出现 | 有待选时出现 | 有待选时出现 | `CandidateStatusBar.vue` `v-if="count > 0"` |
| shift 选两个 event 横幅（漏检入口 D） | 不出现 | 理论上可出现 | 有时出现 | 有时出现 | `ShiftPairBanner.vue` |
| 副图 | 特征轨（用户的） | 上区用户轨 + 粗蓝线 + 下区 app 的 hits 行与 band | app 的 band | app 的 band | `renderBarsOnly` / `renderCompareSub` / `render` |
| 反馈带、反馈作答面板（浮层） | 不出现 | 在用 | 不出现 | 不出现 | `v-if="comparing && fb.panel"` 等 |
| 右上「框选」按钮（漏检入口 A，Shift+,） | 不出现 | 不出现 | 在用 | 在用 | `v-if="!annotating"`（`:44`） |
| 右键调试菜单（driver / event debug） | 不出现 | 不出现 | 在用 | 在用 | `if (annotating.value) return`（`:504`） |
| 缩放滑块 | 常显 | 常显 | 跟 Slider 开关 | 跟 Slider 开关 | `sliderShow: true`（annotate、compare），否则 `showSlider` |

### 1.5 右栏（`components/ChartArea.vue` 第二列）

| 块 | annotate | compare | app 现算 | app 扫描 | 依据 |
|---|---|---|---|---|---|
| 标注侧栏（320px，`selection / features / pattern`，compare 多 `feedback`） | 在用 | 在用 | 不出现 | 不出现 | `AnnotationSidebar v-if="annotating"` |
| 诊断侧栏（280px，漏斗总览、hit 列表、留痕） | 不出现 | 不出现 | Sidebar 开关打开时在用 | Sidebar 开关打开时在用 | `DetailSidebar v-else-if="showSidebar"`；Sidebar 关掉时右栏整列不占（`.no-sidebar`） |

说明书 `.scratch/annotation-path2/manual.md` 第 443、706、780 行三处把「想看数字」引到「主视图的诊断侧栏」——它只在 `app` 下出现（现算或扫描都行）。

### 1.6 浮层、对话框、键盘（看不见但起作用的部分）

| 项 | annotate | compare | app 现算 | app 扫描 | 依据 |
|---|---|---|---|---|---|
| 扫描对话框、历史对话框、停止扫描对话框 | 能从左栏打开 | 同 | 同 | 在用 | `SidebarScanPanel.vue` |
| 参数抽屉（Working Copy，Shift+P） | **副作用**：Shift+P 照样打开，内容是扫描的 active pattern 的参数，浮在右上、盖住标注侧栏；没扫描时标题为空。**已复现**（`repro/s8_annotate_shiftP_drawer.png`：annotate 下弹出「bo_only 参数」抽屉；再按 Shift+P 关掉，没点任何按钮，盘上没有留下 `outputs/path2_web/wc.json`） | 同 annotate | 同 annotate | 在用 | `ChartArea.vue:116` 的 Shift+P 不看模式；抽屉在所有模式都挂着（`:57`） |
| 左栏「敲字母搜股票」 | 没扫描：不起作用；**有扫描：副作用**——焦点在页面空白处（点过 K 线后焦点就在这里）时，敲任何不带修饰键的字母或数字都被抢进扫描搜索框；之后焦点留在搜索框里，Delete（删框）、Shift+B、Esc 等快捷键都因「焦点在输入框」而失效，直到焦点离开。**已复现**：打开扫描、切 annotate、焦点在空白处敲 `x`，焦点跳进 `symbol-search`、框里写上 `x`（`repro/s7_…png` 左上） | 同 annotate | 同 annotate | 在用 | `SidebarResultList.vue:272-287`，第一行 `if (!scanFile.value) return` |
| 左栏 ↑/↓ 切股票 | 没扫描：不起作用；**有扫描且列表非空：副作用**——不检查焦点在哪，在标注侧栏的文本框（定义、属性、反馈理由）里按 ↑/↓ 也会跳到扫描列表的下一只股票，并把模式切成扫描的 `app`（离开 annotate / compare，反馈面板随之关掉）；当前图不在扫描列表里时跳到列表第一行。**读代码 + 隔离单测确认**（`repro/arrow-key-annotate.spec.ts`，在 scratchpad 的前端副本里跑，5 条全过：annotate、compare 下焦点在文本框里按 ↓ → 跳到第一行、切成扫描 app；当前图在列表里 → 跳到下一行；没扫描、输入法组字中 → 不动）。用户的网页上没有按键试；现存扫描列表 0 行，网页上本来也复现不了 | 同 annotate | 同 annotate | 在用 | `SidebarResultList.vue:301-322`：只看修饰键、组字、字段菜单和列表是否为空，不看焦点；`selectSymbol` 强制 `mode='app'、appSource='scan'`（`view.ts:710`）。顶栏 symbol 输入框自己挡了 ↑↓（`TopBar.vue:14-15`），标注侧栏的输入框都没挡（只有反馈面板截了 Enter / Esc，`FeedbackPanel.vue:279`） |
| ←/→ 在当家行里走 | 在 compare 用于样本间走；annotate 下无当家行时不起作用 | 在用 | 在用 | 在用 | `KlineChart.vue:1032` |

规格 `.scratch/annotation-path2/spec.md:341` 写「单个字母会被左侧列表的『敲字母搜股票』抢走」——核实：**只在本页打开过扫描时成立**；没扫描时字母不会被抢。

### 1.7 顺手看到的两处显示问题（与布局无直接关系，原因未查）

- 从 compare 切到现算 app 后，副图每一行的底色（hits 行的浅黄、band 行的灰白条纹）停在旧宽度，没有随右栏消失而伸到右边；格子本身的位置和主图是对齐的。等了几秒、开关诊断侧栏后仍是这样（`repro/s3_app_linked_noscan.png`、`repro/s3b_app_linked_sub_after_wait.png`）。
- 在现算 app 下打开那份旧格式扫描（第 4.3 节）后：顶栏 symbol 变成 AA，图上还是上一只 CRNC 和它的 new_step 副图，控制台报 `computeEventData` 读不到 `map`；再切 annotate，图画的是 AA，但只从 2023-09-19 画起（悬停 2024-07-19 显示第 209 根），而 AA 的全部 K 线从 2021-10-04 起、共 1066 根——像是还停在扫描窗口那段 K 线上。这是坏扫描留下的脏状态，照代码正常扫描下切 annotate 会重读全部 K 线（`KlineChart.vue:1408`），**未用正常扫描验证**；`repro/s6`～`s9` 这几张图的图面内容不作别的证据。

## 2. 共用与独占

### 2.1 代码层：哪些组件、渲染函数两边都用

两边都用（标注的 compare、扫描的 app、现算的 app 走同一份代码）：
- `components/KlineChart.vue`：同一个图组件承担四种状态，内部按 `annotating` / `comparing` / `linkedView` 分支。
- `render/chart.ts` 的 `computeEventData`、`buildSubOption`、`buildMainOption`：app（扫描或现算）的副图与主图记号；compare 的下区（app 部分）调的是同一个 `computeEventData` + `buildSubOption`（`KlineChart.vue` 的 `renderCompareSub`，在顶上给用户区让出位置）。「按 node 分轨、同起点折成一行」的画法只此一份。
- `render/subGeometry.ts`（副图几何、竖直缩放）、`render/visible.ts`（档位、band 键）、`components/KlineChart.ts` 的点击处理（`handleAppClick` 等）、焦点与当家行（`view.ts` 的 `focusHit` / `stepFocus`）、档位按钮、拓扑面板 `TopologyControl.vue`。
- 顶栏 `TopBar.vue` 整条（symbol、rally、random、mode 在四种状态都在）。
- 后端 `/preview`（单股现算）：扫描侧的「临时计算」（Working Copy 探索态，`view.runPreview`）和标注侧的现算 app（`stores/appLink.ts`）都打这一个接口，口径不同（前者用扫描窗口和参数副本，后者用全部 K 线和 app 的参数文件）。
- 后端 `path2_web/app_run.py` 的 `run_app`：单股预览、反馈状态接口、会话改版报告、`look.py` 共用。

只属于扫描：`SidebarPatternPanel` / `SidebarScanPanel` / `SidebarResultList` / `ScanConfigDialog` / `ScanResultDialog` / `StopScanDialog` / `PatternStatsTooltip` / `ParamsChip` / `WorkingCopyDrawer` / `DormantDraftBanner`、`stores/scan.ts`、`view.ts` 里的 `scanFile`、排序、列显隐、搜索、Working Copy、探索态预览（`runPreview` 在 annotate、compare、现算 app 下直接返回，`view.ts:1190`）。

只属于扫描或现算的 app（标注两模式不用）：`DetailSidebar.vue`（诊断侧栏）、框选 / 右键调试菜单 / shift 两选（漏检入口 A、B、D）。

只属于标注：`AnnotationSidebar` 及其各页、`AnnotationNotices`、`RallyList`、`PatternPicker`、`render/annotateLanes.ts`、`render/compareLayout.ts`、`render/feedbackStrip.ts`、`annotate/` 整个目录、`stores/annotation.ts` / `compare.ts` / `feedback.ts` / `appLink.ts` / `landing.ts` / `directLinks.ts` / `refLayers.ts`。

### 2.2 运行时：切换时哪些状态被带过去、哪些被重置

全部在一个 `view` store 里（单实例），切模式不换 store。

| 状态 | 切模式时 | 依据 |
|---|---|---|
| `symbol`（当前股票） | **带过去**。顶栏切 annotate / compare / app 都不换股票；从扫描列表选股会把模式强制改成扫描的 app；按代码 / rally / random 打开会把模式改成 annotate（compare 下除外） | `enterAnnotate`、`enterLinked`、`selectSymbol`、`openSymbol` |
| 图窗（缩放到哪段） | 只在「画全部 K 线」的三档（annotate、compare、现算 app）之间互切时保留；进出扫描的 app 时重置（K 线范围本身变了） | `KlineChart.vue:1408` |
| `viewWindow`（打开时给定的图窗） | **不随扫描选股清空**：从扫描列表选股不碰它，之后切回 annotate 会按它重置图窗——它可能是上一只股票（rally / random / 链接打开的那只）的日期段。疑似小毛病，未在浏览器复现 | `selectSymbol` 不设 `viewWindow`（`view.ts:710`）；`renderBarsOnly(true)` 用它（`KlineChart.vue:852`） |
| 档位 `level` | 带过去，compare、两种 app 共用一份，存浏览器 | `view.ts:306` |
| `tiers` | 带过去 | `view.ts:278` |
| node 显隐 `nodeVisible` | 切模式不清；只在打开 / 关闭扫描时清。在扫描的 app 里关掉某个 node 的显示，到 compare 里同名 node 也是关的 | `loadScanFile` / `clearScanFile` 清；`resetChartState` 不清 |
| 副图竖直缩放 | compare 一份，两种 app 共用另一份 | `KlineChart.vue:613` |
| 面板开关（拓扑、诊断侧栏、滑块） | 带过去，存浏览器 | `stores/panels.ts` |
| 焦点、展开、候选、诊断卡片、探索态预览 | 每次切模式、换图都清 | `resetChartState`（`view.ts:700`） |
| 工具（box / point / feedback） | 换图、换模式都熄 | `KlineChart.vue:1141` |
| 反馈作答面板、redraw 带过来的内容 | 换图、换模式都关 / 放弃 | `stores/feedback.ts` 模块说明 |
| 标注侧栏页签 | 带过去；离开 compare 时停在 feedback 页就退回 selection | `AnnotationSidebar.vue` |
| 标注的当前 pattern | 带过去，存浏览器；决定 compare / 现算 app 用哪个 app | `annotation.ts:284`、`appLink.ts` |
| 扫描文件、扫描列表排序 / 搜索 / 列显隐、扫描的 active pattern、Working Copy | **一直留着**，不受切模式影响；只有打开另一份扫描或删掉当前扫描才变 | `loadScanFile` / `clearScanFile` |
| 现算结果 `linkedRun` | 进 compare / 现算 app、换股票、换 app 时重跑；compare 与现算 app 互切不重跑 | `appLink.ts` 的 watch |
| rally 清单（排序、滚动位置） | 留着（组件里的状态） | `TopBar.vue` 的 `v-show` |

## 3. 标注工具里的 app 结果：从哪来、覆盖哪些股票（逐行核实）

`原始问题.md` 背景里的推断：「反馈状态、会话改版报告只对有反馈 / 有样本的股票跑」。**结论：成立，修正两点**（反馈状态只看有反馈的、不看只有样本的；改版报告的代码在后端，不在 skill 脚本目录）。

| 谁 | 对哪些股票跑 app | 什么时候跑 | 依据 |
|---|---|---|---|
| compare / 现算 app 的图 | **只有当前打开的这一只** | 进 compare / 现算 app、换股票、换 app 时（compare 与现算 app 互切不重跑） | 前端 `stores/appLink.ts` 的 `run()` 只对 `view.symbol` 调 `/preview`，区间 1900-01-01 到训练段末日；后端 `path2_web/api.py:445` `get_preview` 调 `run_app` |
| 图上 ▲ 旁的 ✓ / ✗、selection 页的 `match` / `diagnose` | 只有当前这只（读的是上面那份现算结果） | 同上 | `stores/compare.ts` 模块说明 |
| 反馈状态（图上反馈记号的状态、侧栏 `feedback` 页） | **这个 pattern 下有 picked 反馈的股票**；只有样本、没有反馈的股票不跑 | 只在 compare 下取：进 compare、换 pattern、存删反馈后、app 重跑后、窗口重新拿到焦点 | `path2_web/api.py:869` `get_feedback_status`：`fbs = [(symbol, fb) for c in charts for fb in c["feedback"] if fb["pattern"] == pattern and fb["source"] == "picked"]`，逐条调 `_buys_of`（`api.py:855`，按 app 版本 × 股票缓存）；前端 `stores/feedback.ts` 模块说明「只在 compare 下去取」 |
| 会话改版报告 · 开头定格 | 这个 pattern 下**有样本或有反馈**的股票（现在的 ∪ 上一轮定格时的） | 会话调 `start_round` | `path2_web/annotation/revision.py:297-305`：`symbols = _symbols(samples, feedback)`，再并上上一轮定格时的；`_run_all`（`:221`）逐只 `run_app` |
| 会话改版报告 · 改完之后 | 旧标注 ∪ 新标注里有样本或反馈的股票，再并上定格时跑过的 | 会话调 `revision_report` | `revision.py:757-762` |
| 会话改版报告 · 第一版 app | 定格时**有样本**的股票 | 同上（没有旧版可比的那一轮） | `revision.py:700-701` |
| `annotation-round` 的 `look.py` | 会话指定的一只股票、一段日期 | 会话按需调 | `.claude/skills/annotation-round/scripts/look.py:194` |
| `annotation-round` 的 `round_state.py` | 不跑 app | — | 只读标注和 mapping 打印事实 |

所以：网页上能看到 app 结果的股票 = 你正打开的那一只（compare / 现算 app），外加 feedback 页列出的「有反馈的那几只」的状态；pattern 页上没有跨股票的 app 对照（规格把它留在第二段）。整池跑 app 的只有扫描（第 4 节）。

当前标注规模（`repro/annotation_overview.py`，经 `read_annotations` 只读）：7 张图，全部属于 pattern `new_step`；7 只股票有样本，其中 2 只（CRNC、INDO）有反馈。

## 4. 谁还依赖扫描

### 4.1 分两种依赖

| 依赖什么 | 谁 | 说明 |
|---|---|---|
| **扫描界面**（左栏、扫描对话框、参数抽屉） | `diagnose-event` 的探索态 | 环境探测读 `outputs/path2_web/wc.json`（参数抽屉「Write Copy」时由前端落盘）。不开参数抽屉就没有这个文件，技能回落到扫描文件里的参数快照（`.claude/skills/diagnose-event/path2_diag_env.py:101-119`、`reference.md` 红线第 6 条） |
| 同上 | e2e：`scan-dialog`、`symbol-search`、`flow`、`dev-ui-replication`、`miss-detection-walkthrough`、`shift-pair-feedback` 等 | 入口都是扫描：测扫描界面本身，或扫描 app 下的诊断 / 漏检入口（按文件里 scan 字样计数与改动日期归类，未逐条读用例） |
| 同上（借道） | e2e：`fold-rows`、`hit-event-disambig`、`sidebar-chart-focus`、`subchart-scroll-drag` 等 | 测的是 compare 也在用的共用画法（同起点折行、待选、焦点、副图滚动），但入口是「现扫一份 new_step 小扫描 → 在扫描列表打开」（`e2e/smallScan.ts`，用完自删）。这几条 11-06 / 11-08 还在改 |
| 同上（借道） | e2e：`annotate-open-by-symbol.spec.ts:95`、`annotate-rally-random.spec.ts:101` | 测「扫描结果是 app → 按代码打开 / rally 切到 annotate → 再点扫描列表回到 app」 |
| **扫描文件 + 后端扫描模块**，不要界面 | `diagnose-event` 的常规路径 | 自动取 `outputs/path2_web/scans/` 下最新的一份扫描，读其中的事件、hit 和参数快照（`path2_diag_env.py:82,116-120`）。注意它按文件名取最新、不看 pattern |
| 同上 | `feature-study` | 从扫描文件重放出新特征，两道自检门对拍扫描文件里的 hit 集（`.claude/skills/feature-study/SKILL.md:96-127`） |
| 同上 | 旧版 `tune-gates` + `scripts/path2/scan-wide.py` | `scan-wide` 调 `path2_web.scan.run_scan_multi` 落盘一份宽进扫描，作为 feature-study 的底座；`tune-gates` 另借 `path2_web.scan` 的两个工具函数 |
| **只要后端模块，连扫描文件都不要** | `write-detector`、`scripts/path2/path2_eval_scan.py` | 调 `path2_web.eval_runner`（`run_eval` / `run_healthcheck` / `run_regress`），自己跑全宇宙、结果写 `outputs/path2_eval/` |
| 同上 | `scripts/path2/scan-top-miss.py` | 调 `path2_web.diagnose` + `gate_collector`，自己逐股跑 |
| 不依赖 | `tune-gates-v3`、`annotation-round` | grep 无扫描文件、扫描模块、网页地址的引用 |

另：`write-detector/reference.md:218-` 的「debug 菜单契约」要求前端 `stores/view.ts::anchorsOf` 配合 detector 的 `debug_break`——这个右键调试菜单在两种 app 下都能用（`KlineChart.vue:504` 只挡 annotate / compare），不依赖扫描。

### 4.2 诊断与漏检入口在现算 app 下也能用

诊断侧栏、拓扑面板、框选（入口 A）、右键调试菜单、shift 两选（入口 D）都按 `appId` / `appWindowOf()` 取 app 与区间：现算 app 下取现算结果的 app 和区间，扫描 app 下取 active pattern 和扫描窗口（`view.ts:516-525`，`triggerTimeQuery` 等）。只有「临时计算 / Working Copy 探索态」只在扫描 app 下有（`view.ts:1190` 在 annotate、compare、现算 app 下直接返回；`appParamsOverride` 在现算下恒为 undefined）。说明书三处把「想看数字」引到的诊断侧栏，现算 app 下也有（`repro/s4_app_linked_panels_on.png`）。

### 4.3 扫描界面最近有没有被用

- `outputs/path2_web/scans/` 现有 5 份（`repro/scan_files_wall.py`）：4 份（9-06～10-28，bb_pk / bb_v1）没记 `data_until`，过不了数据墙，网页打开报 409；唯一过得了墙的 `20261103T010617`（11-03 01:06，bo_only，3144 只）是 11-04 match→hit 改名**之前**扫的，文件里是 `matches`、前端读 `hits`——打得开、显示不了：列表 0/3144 行，图报错（`repro/scan_bo_only_peek.py`、`repro/s6_app_scan.png`）。照 `.claude/rules/scan-file-no-backcompat.md` 这是预期行为。
- 所以**盘上没有一份扫描能在网页里正常显示**，11-04 以后网页里没有留下过一次扫描（e2e 的小扫描自建自删）。
- git：扫描侧组件 11-03 / 11-04 的改动全是全仓改名（matches→hits、hits→hit_stocks、固定文字黑字等），实质功能改动停在 9 月（`ParamsChip`、`WorkingCopyDrawer`、`PatternStatsTooltip` 最后改于 09-03）；`SidebarPatternPanel` 最后改于 07-03。

## 5. 有没有「从扫描结果进入同一张图接着标注、状态要保留」的路径

### 5.1 代码里

- **有，且只有一条直接的**：在扫描的 app 下点顶栏 `annotate` → `enterAnnotate`（`view.ts:730`）：股票不换，清焦点 / 候选，K 线从扫描窗口换成全部 K 线、图窗重置（`KlineChart.vue:1408`，`wholeChart` 由假变真）。也可点 `compare`（标注的当前 pattern 有 app 时），同样股票不换、换成现算结果。
- 另两条间接的：在扫描 app 下用顶栏 symbol / rally / random 打开图 → 落在 annotate（`openSymbol`），扫描留着；从 annotate 回扫描只能在左栏点一行（`selectSymbol`，强制回扫描 app）。
- 带过去的状态见 2.2：股票、档位、node 显隐、面板开关、标注当前 pattern；不带的：焦点、候选、图窗。扫描自己的状态（列表、排序、搜索、active pattern）一直留着，回来时还在。
- 一处疑点：`viewWindow` 不随扫描选股清空（2.2），扫描 app → annotate 时可能按上一只股票的日期段定图窗。读代码得出，未复现。
- 直达链接（`stores/directLinks.ts`）、落到 compare（`stores/landing.ts`）都不经扫描；三种链接要么落 annotate、要么落 compare。

### 5.2 规格与说明书里

- 说明书 `.scratch/annotation-path2/manual.md` ①「找图」（第 219 行起）只列三个入口：大涨段清单、`random`、按代码打开；**没有提扫描列表**。同节的原则：「默认干净 K 线：标注时不画任何现成 detector 的结果。现成的画法会把你的眼睛往已有种类上带」。扫描列表每行带的是现成 app 的命中数和前瞻收益。
- 说明书第 459 行、规格第 179、805 行：反馈只在 compare 做，「`app` 模式没有标注侧栏和工具，图还可能来自旧的扫描结果」。
- 规格第 139 行只说「path2_web 的普通扫描」不受数据墙影响；规格其余地方不描述扫描与标注之间的跳转。
- 唯一写到「扫描结果的 app → annotate」的是实施审查记录 `.scratch/annotation-path2-implementation/evidence/11/review-spec.md:15`（把它当作「从非 compare 状态进来时的默认落点」的例子），以及 5.1 那两条 e2e。

### 5.3 用户实际有没有这样用过（证据）

找不到用户「从扫描结果点进一只股票、再切 annotate / compare 接着标」的证据；能找到的证据都指向别的入口：
- **标注过的股票与扫描文件**（`repro/annotated_vs_scan_rally.py`）：7 张图 = CRNC、GEVO、INDO、KULR、QBTS、RGTI、SMX，全属 pattern `new_step`；盘上没有一份 new_step 的扫描。9 月～10-28 的四份 bb_pk / bb_v1 扫描里只碰上 INDO（1 份）和 RGTI（3 份），且这四份在标注开始前（11-02 起数据墙）就打不开了。11-03 的 bo_only 几乎收了全池 3144 只，和谁都重合，不能当证据。
- **标注过的股票与大涨段清单**：7 只里 5 只在 rally 清单上（CRNC 11-15、INDO 02-16、KULR 11-22、QBTS 10-22、RGTI 10-22 / 11-20），样本日都落在那段涨开始后不久；GEVO、SMX 不在清单上（来自 random 或按代码打开，无法区分——看过什么一律不记）。
- **用户原话**（会话记录 `bb41a4fd…jsonl`，2026-11-05 02:49 UTC，`/grill-me` 的参数）：「左侧的股票列表一直显示 '未加载扫描结果'，能不能让标注的候选图 rally 或者 random 也使用非标注页面的左侧股票列表，免得我每次先点击 rally 再选股票(两次点击)。 更广泛的说，我觉得标注和主试图非常割裂，感觉就是两个界面。每次点击 app，都会觉得和 annotate compare 完全不同。」——想要的是「左侧列表装找图候选」，不是「从扫描进标注」。
- **那两条测「扫描 → 标注」的 e2e 11-04 起就是红的**：同一会话记录里，实施汇报写着 `annotate-open-by-symbol:95`、`annotate-rally-random:104 / :130` 失败，原因「打开扫描列表里最新的那份结果（20261103T010617），那份结果 bo_only 的命中数是 0，表格一行都没有」。
- 11-03 那份 bo_only 扫描是谁跑的：不是 e2e 的 `ensureScan`（参数对不上：它只扫 `^AA`、从 2025-01-01 起），会话记录里也没找到出处，来源不明。

### 5.4 用户提过、还开着的相关条目（`.scratch/annotation-path2-implementation/v-s1-notes.md`「界面改进」）

- 第 9 条（用户 11-05 提）**「左侧股票列表在标注时空着」**：现状「annotate 下左侧股票列表一直写『未加载扫描结果』；`rally`、`random` 另起一个弹出清单，每次要先点 `rally` 再选股票」；改法待定：「`rally` 清单和 `random` 的结果都放进左侧那个列表，点一下就切股，上下键挨个翻（主视图列表已有）」。
- 第 2 条 **「`rally` 清单看不出哪些已经标过」**：改法待定：「清单每行标出这只股票、这段涨附近有没有标注（例如框数、样本数），并能按『已标 / 未标』筛选或排序。注意 spec 5.3『看过什么一律不记』：这里只显示用户存下的标注，不记看图记录」。
- 第 8 条 **「标注模式和主视图割裂（原则）」**：用户感受「annotate / compare 和 app、主视图像两个界面，主视图的拖拽、缩放、分档这些习惯到了标注模式都不一样」；会话当时建议的原则「标注只往主视图上加东西（框、样本、bracket 轨），主视图原有的操作和控件在每个模式下保持一致……不做整体合并重写」。
- 第 10 条（tiers 换成三档按钮）：compare / app 现在已有三档按钮；`tiers` 复选框仍在、没有读者（1.1）。

## 6. 产物索引（`repro/`）

| 文件 | 内容 |
|---|---|
| `s0_fresh.png` | 刚打开、没开图 |
| `s1_annotate_noscan.png` | annotate（CRNC，没开扫描） |
| `s2_compare_noscan.png` | compare（CRNC） |
| `s3_app_linked_noscan.png`、`s3b_app_linked_sub_after_wait.png` | 现算 app；后者是副图行底色停在旧宽度 |
| `s4_app_linked_panels_on.png` | 现算 app + 拓扑面板 + 诊断侧栏 |
| `s5_history_dialog.png` | 扫描历史对话框（5 份，4 份标「旧扫描」） |
| `s6_app_scan.png` | 打开旧格式 bo_only 扫描后（列表 0 行、图未刷新、报错）——不是正常的扫描 app |
| `s7_annotate_with_scan_letter_hijack.png` | 有扫描时 annotate，敲 `x` 被抢进扫描搜索框（左上）；图面受坏扫描影响，见 1.7 |
| `s8_annotate_shiftP_drawer.png` | annotate 下 Shift+P 弹出扫描的参数抽屉 |
| `s9_rally_popover.png` | rally 浮层盖在左栏位置 |
| `scan_files_wall.py`、`scan_bo_only_peek.py` | 扫描文件能否过数据墙、旧格式核对（只读） |
| `annotation_overview.py` | 标注规模（经 `read_annotations` 只读） |
| `annotated_vs_scan_rally.py` | 标过的股票与扫描命中、大涨段清单的重合（只读；rally 走后端 GET） |
| `arrow-key-annotate.spec.ts` | ↑/↓ 抢键的隔离单测（复制到 scratchpad 的前端副本 `tests/` 下用 vitest 跑，5 条全过；不进仓库测试） |

截图的浏览器是 playwright 自己起的一个，和用户的浏览器不共享页面状态；只做了导航、切模式、换股票、开关面板与浮层、打开一份扫描，没有画框、放样本、保存或删除。
