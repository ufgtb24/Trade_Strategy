# fold-interaction：折叠后的显示与操作、同 hit 联动选中

本文件中所有项目内路径均相对 repo root。示意图 `repro/mock_fold.png`（合成数据，脚本 `repro/mock_fold.py`，不读任何行情；图里所有 in_hit 都画成中蓝，真实界面是各 node 本色）。compare 下的样子见 compare-coexist 的 `images/c10_mock_compare_CRNC.png`，画法同本文。

词表出处：band `path2_web/GLOSSARY.md:39`、lane `:42`、bracket `:45`、tag `:48`、诊断侧栏 `:58`、显示档位 `:25`、detected / qualified / in_hit `:28`；hit `path2/GLOSSARY.md:95`、复合事件 `:62`、点事件 `:47`、买点 `:118`、样本日 `:167`。「族」「折叠行」「当前日」「当家行」是本轮新说法，词表里还没有（第十节第 1 条）。

折叠规则以 fold-rules 为准（`notes_fold-rules.md`）：同一条 band 里起点相同的 event 折成一族，只用 node 与起止下标，不要任何声明；起点不同的一律不折；bracket 上的 hit 按同一规则折。300 只随机股：plateau 检测档每股中位 192 行 → 5 行，new_plat 147 → 6，bracket（new_step）9 → 1；「同一天两族都有 hit」三个 app 都是 0；一格挤 ≥2 个成员约 15%（最多 5）。本方案只依赖规则的一个性质：族内成员只差终点，所以每个成员能用「它的终点在哪天」定位。

## 结论（先读）

1. **一族画成一行「梳子」**：每个成员一格，立在它的终点那天；族从哪天到哪天只由底下一根中性细线表达。**只有一个成员的族照旧画一根整条**（old_plat、87% 的阶跃）。于是图上两种样子对应两种东西：整条 = 一个事件，梳子 = 一族（同起点的一串实例），每一天的面积都一样大。bracket 上的 hit 用同一种画法（琥珀色），再叠上买入日 ▼。
2. **档位 = 高度 + 颜色**，用于所有条和格：in_hit 满高、node 本色；qualified 中高、深灰；detected 矮、浅灰。一行读下来就是「这一族哪几天进了 hit」。高度是主通道：new_step 现在的配色里 plateau 亮绿和 detected 浅灰深浅几乎一样，new_plat 深绿和 qualified 深灰也几乎一样（第七节）。user-proxy 走查确认「高的格 = 能买的天」一眼读得出，缩到 1～2px 宽时至少「高 / 不高」两档分得开。
3. **点与条按 node 的声明分**：声明为点事件的 node（today、bo、pk）画 ▼，其余一律画条或格，只有一根 K 线长的成员画成一根宽的格。▼ 只留给点事件 node 与 bracket 上的买入日。要后端在拓扑里多投影一个 `is_point`（纯投影，类型无关）。
4. **不做展开，不挂 tier tag，不标个数**：格子位置已是成员的全部几何信息；档位由高度和颜色表达；同一格几个成员只差子段，区别本来就显示在子段 band 上（step 哪个前缀加粗、new_plat 哪一行加框）和侧栏 hit 列表（同一天几行）。逐个核对成员用诊断侧栏候选表。
5. **联动选中**：选中一个 hit，每条 band 上属于它的成员画空心细框（族起点 → 它的终点）并把它那一格加粗框；一条**当前日竖线**从 K 线主图一直穿到副图最下面。图 15「一摞里找哪根加了框」变成「每条 band 一行，竖线经过、加了粗框的那一格」，竖线同时把各段对到 K 线上。
6. **反查**：点格就是选这个成员，沿用现有「属于 0 / 1 / ≥2 个 hit」三分支。≥2 在 new_step 里是常态（旧平台、阶跃、当天被多个 hit 共用），这时把它所属的 hit 在 bracket 行上加框，点其中一个，或用 ←/→ 在它们之间走。
7. **操作三样**：点格；←/→ 在当家行里逐个走（点过 bracket 就逐日翻 hit，点过 band 就逐个看成员）；Esc 清。当家行的底线加深加粗、所在 band 的表头名字加粗，看得见现在 ←/→ 动的是哪一行。compare 下点了样本，←/→ 就在样本之间走（a → b → c）。
8. **新元素只有三样**：折叠行、当前日竖线、当家行标记（底线 + 表头加粗，和 ←/→ 同进同退）；外加 ←/→ 两个键。hit 列表圈号改日期，候选提示条改文字。
9. **主视图与 compare 同一套**：compare 的 app 部分就是主视图那张副图（compare-coexist）。compare 下点样本，当前日落在样本日、竖线上「配对那一格」粗框；点框，当前日落在框终点。

---

## 一、叠层为什么难看、难选（事实）

- new_step 第二版（`docs/superpowers/specs/2026-11-05-new_step-design.md`「层② 判据」）：一次阶跃若有 k 个前缀、新平台走了 d 天，`plateau` 有约 k×d 个实例，起点全相同、终点逐天 +1；`new_plat` 每个前缀一组、组内起点相同；`step` 是 k 个同起点的前缀；`old_plat`、`today` 是共用对象。hit 每个前缀每天一个，跨度同 plateau，bracket 轨同样叠成一摞。
- 前端分行（`path2_web_ui/src/render/geometry.ts::packLanes`）按起点贪心：同起点的条每条另开一行。示意图左半边：一次两根 K 线的阶跃、新平台走 19 天，选中一个 hit 时边框散在 85 行里。
- 现有选中画法（`render/chart.ts::buildHlShape`）给被选的条画一个放大、带深边和阴影的实心复本。在一摞几乎一样的条里，被选那根和邻居只差右端一两根 K 线。
- 点与条现在按单个实例 `start_idx === end_idx` 分（`render/chart.ts::computeEventData` 分 lane 后的循环），于是同一族阶跃前缀里一根的画成 ▼、两根的画成小块（`images/c03_app_CRNC_full.png` 的 step 轨），条又是从起点中心画到终点中心，两根的条只有一根 K 线宽；user-proxy 第 0 版 d 条「step 在哪我没找到」就是这个。
- 根子：同起点的成员只差终点，信息全在终点上；画成整条就把公共段重复画 N 遍，把真正不同的那一点淹掉。

## 二、显示方案

### 2.1 折叠行

- **格**：多成员族里每个成员一格（包括终点最早的那个），宽约 0.8 根 K 线，立在各自终点那天，高度、颜色按各自档位。
- **为什么第一个成员也只画一格**：草稿曾让终点最早的成员照常画成整条（族起点 → 它的终点），好让单成员族恰好退化成整条。compare-coexist 按它重画的 `images/c10_mock_compare_CRNC.png` 暴露了副作用（skeptic-2 指出）：plateau 族起点在阶跃前 15 根，这根「首条」至少 18 根宽、是一格的 18 倍以上，于是每族开头这一大段的样子由「新平台第一天那一个实例」的档位决定——第一天恰好 in_hit 的族开头是一大块满高蓝板，读成「整段都够格」；第一天只是 detected 的族开头是一根矮灰条。族内买入日 69%～80% 有断档（skeptic-2 实测），整块实心板正是要避免的读法。所以多成员族里每一天一样大，族跨度只交给中性底线。
- **底线**：1px 中灰细线（`#6b7280`，比 detected 浅灰格深，免得在浅底上整根消失——user-proxy 提醒），从族起点到最后一个终点，画在格下层，不表示档位。阶跃前那 15 根旧平台上只有这根细线，自然淡化（fold-rules 问的「要不要淡化」）。显示档位开到 in_hit 时格子之间有空（skeptic-2 实测：有 hit 的族里 69%～80% 的买入日中间有断档，中位 1～4 处），底线让后面的格仍看得出属于这一族。
- **只有一个成员**：照旧画一根整条（族起点 → 它的终点），高度、颜色按它的档位——old_plat、只有一个前缀的阶跃（约 87%）都是这样。整条表示「这一个事件」，不涉及「哪几天」，所以不会有上面那种以一天代整段的问题。
- **梳子还是整条，按档位筛选前的成员数定**：族里原本 ≥2 个成员就一直画梳子，哪怕显示档位开到 in_hit 后只剩一个 in_hit 成员也只画那一格——否则切一下档位，梳子就会变成一块从旧平台铺到那天的满色板，同一个毛病又回来，切档时样子也跟着跳。
- **档位高度**：in_hit 1.0、qualified 0.65、detected 0.4 倍 lane 高（待验证），底对齐，用于所有条与格。先例：诊断侧栏候选表左边的色条按档位分宽窄（`components/DetailSidebar.vue::leftWidth`，注释「色恒非唯一信道」）。
- **条的横向范围**：从起点那根 K 线中心 −0.4 根到终点那根中心 +0.4 根。现在从中心画到中心，一根的条只有 2px。
- **同一天几个成员**（跨度完全相同、只差子段，如几个阶跃前缀同一天被认出）：格子画其中最深的档位（一格里档位不一只占 0.3%），**不标个数**：这几个成员的区别在子段上，选中时子段 band 上就看得出（step 加粗的是哪个前缀的格、new_plat 加框的是哪一行），侧栏 hit 列表同一天会有几行；而一标个数，两根以上的阶跃会让新平台上几乎每一格都带数字。悬停逐个列，←/→ 逐个走。
- **点事件**：拓扑里声明为点的 node 画 ▼；同一根 K 线、同 node 的点并成一个 ▼，▼ 大小按档位三档。没声明为点、只是只占一根 K 线的成员，画成一根宽的格（step 一根的前缀、bottom_burst / bb_v1 里一根 bo 的 burst 约七成，都从 ▼ 变成格）。
- **和显示档位的关系**：认族、定梳子还是整条用全部成员；画哪些格、底线画到哪，用档位筛选后剩下的成员。这和 fold-rules 的「先筛后折」不冲突：认族键（node + start_idx）不受筛选影响，先筛后折与先折后筛得到同样的族；唯一要用全部成员的是「梳子还是整条」这一个判断。档位开到 in_hit 时只剩进了 hit 的格，底线只到最后一个 in_hit 成员——族看起来「变短」是档位筛掉了后面的成员，不是事件变短；悬停底线的摘要里写全族终点范围。
- **扫描窗之后**：照现有规则（`render/visible.ts::splitIntervalAtScanEnd`），整条跨过扫描末日的部分降为浅灰，终点在末日之后的格画浅灰，底线跨过末日的那段同样降为窗后灰（否则窗后的底线会被读成窗内还在）。
- **分行**：以族为单位分 lane（族的外包跨度 = 起点到最后一个终点），互不交叠的族放同一行。
- **父子族不一一对应**：plateau 同一次阶跃一行，new_plat 按阶跃前缀拆几行（fold-rules：CRNC 5 对 6）；联动选中时 new_plat 亮的是其中一行的一格。
- **tier tag**：副图条右端的 `qualified_only` / `detected_only` 不再画（高度已表达档位，图 14 的一大片小字就是它）。顶栏 `tiers` 勾选框和 `view.tiers` 状态随之删掉；compare 图上框旁只留琥珀 `missing`（框终点那天一个 event 都没有时），其余档位读数放 selection 页和悬停（compare-coexist 定）。

### 2.2 bracket 行

- 一族 hit（同起点）一行，画法同 2.1，颜色琥珀、一律满高（hit 没有档位）：多个 hit 的族每个 hit 一格立在 hit 终点、底线连起点到最后一个；只有一个 hit 的族照旧一根琥珀条。
- 买入日 ▼ 叠在上面（黑色，买入日按 app `eval_meta` 声明的买点 node 取，即现有 `render/compareOverlay.ts::buyDaysOf`）。new_step 的 hit 终点就是买入日，格与 ▼ 重合；bottom_burst 的 hit 终点是企稳收尾，▼ 可能落在底线上方没有格的地方，▼ 自己可点（3.1）。
- 圈号挂在族行尾，是族的序号（一行可含 5～42 个 hit，每个 hit 一个圈号已无意义）。

### 2.3 悬停

- **悬停格或整条**：提示同现有事件提示（`render/visible.ts::resolveTooltipData`），抬头加 `k/n`；同一格几个成员时逐个列。同时用细实线描出它的完整跨度作预览。
- **悬停底线**：族摘要：`start`（起点日期）、`end`（终点从哪天到哪天）、`members`、`in_hit`、`qualified`、`detected` 各几个。user-proxy：两行 new_plat 看不懂时，靠起点日期对上「这一行从 11-23 开始，那一行从 11-25 开始」。
- **悬停 ▼**：`buy` 日期、属于哪几次 hit。
- 描线一律实线：这个界面里虚线只表示用户画的（`render/annotateLanes.ts` 文件头）。

### 2.4 不做的

- 逐族展开、band 级 `fold` 开关：展开不带来新的几何信息；核对成员用侧栏候选表（`seg@起-止` 加各条 where 的 ✓/✗，点行即选）。
- 行尾 `k/n` 步进标：「第几个」在悬停提示与侧栏选中行。
- 格上标个数：见 2.1。
- 悬停时在 K 线上画它的起止两条细竖线（user-proxy 第 2 版提的可选项，曾写进方案，按 skeptic-2 意见撤掉）：现有鼠标十字线（`components/CrosshairOverlay.vue`）本来就一根到底穿过 K 线，把鼠标移到 old_plat 条的两端就能在 K 线上对出起止；再加就成了三种竖线（十字线、当前日竖线、悬停起止线），还要另想办法在色盲下分清。用户实际用下来若常要对整段起止，再加。
- 选中 hit 时在 K 线主图上铺一层淡底色标出 hit 跨度（user-proxy 提的可选项）：浅色铺在浅底上，按配色规则用户看不出；而且和现有扫描窗外的灰色遮罩（`render/chart.ts::buildShadingMarkArea`）同一种样子，会混。对位交给穿到主图的当前日竖线。

## 三、操作方案

### 3.1 点选

- **点格或整条 = 选这个成员**（band 行走 `focusEvent`，bracket 行走 `focusHit`）。一格几个成员时先选档位最深的，同档按事件数组里的原顺序（detector 产出顺序）。
- **点 ▼** = 选买入日在这天的 hit：一个就直接选中；几个就进待选（同 4.3）。
- 格子缩小后只有 1～3px 宽，但同族的格是挨着的，点进梳齿区总会落在某格上，差一两天用 ←/→ 修。
- **compare 下**：点 app 的格、条或 ▼ 时，顺带取消标注框的选中（`stores/annotation.ts::selectBox(null)`，只取消框、不动当前样本）。否则先点了框、再点 app 的格，框仍选中，按 Delete（`components/ChartArea.vue` 约 98 行）会删掉标注（compare-coexist 指出）。

### 3.2 步进

- **←/→ 在当家行里走到上 / 下一个**。当家行 = 最后一次点选落在的那一行（bracket 的某一族或某条 band 的某一族）。
- **当家行看得见**：它的底线加深加粗（深色 2.5px，同选中框的深色），单成员的族就在整条下面画这条线；同时这一行所在 band 的表头名字（`bracket`、`plateau`……）加粗。user-proxy 第 2 版：只有底线时它贴着选中框下沿，不说注意不到；表头加粗便宜又显眼。user-proxy 走查：「当前族 = 最后点的那一行」是看不见的状态，点完去别处悬停就不记得了。
- **bracket 行**：按终点走这一族的 hit（同一天几个按原顺序）。new_step 最常用的读法：看相邻两天为什么一天买、一天不买。
- **band 行**：按终点走这一族的成员（同一天「档位深的先、再原顺序」），包括没进 hit 的。走到没进 hit 的成员时 bracket 上的选中框消失——这正是「这天没买」的信号，和格子变矮同时出现；它的旧平台、阶跃、新平台、当天仍按现有「组成型组一选全选」（`stores/view.ts::compositionGroupIds`）一起亮，侧栏跳到它那一行看卡在哪条 where。不保留「上一个 hit 的淡框」：那会把这个成员和一个它不属于的 hit 连在一起。
- **同一天走到第 2 个**：竖线不动、只有子段 band 的框换位置，user-proxy 担心会以为按键没反应。处理：侧栏 hit 列表同一日期的几行里高亮换到下一行，并滚到可见处（不在图上加字）；compare 下右栏是 `selection` 页，其中的 diagnose 表同样要跟着换行（compare-coexist）。
- **待选（≥2 个 hit）时**：←/→ 在候选 hit 之间按终点走，当家行是 bracket 那一族。
- **compare 下点了样本 ▲**：当家行是 bracket 上用户样本那一行，←/→ 按样本日走到上 / 下一个样本（a → b → c），每走一步等于点一次那个样本（当前日 = 样本日、配对那一格粗框）。user-proxy 第 2 版提出；样本行经 `activeFamily` 的 `external` 口接到同一个 `stepFocus` 上，样本那部分由 compare-coexist 实现。
- 到两头停住，不绕回。
- **键位**：↑/↓ 已被左侧列表切股占用（`components/SidebarResultList.vue::onArrowKey`）；单个字母数字键会被股票搜索截走（同文件 `onGlobalCharKey`）；←/→ 现在没人用（compare-coexist 确认 compare 下也没人用）。焦点在输入框、输入法组字中、带修饰键时不响应。Esc 沿用现有：主视图 `clearFocus`，annotate / compare 下「取消正在拖的框 + 清标注选择 + 清 app 焦点」（`components/KlineChart.vue` 约 723～726 行）。

### 3.3 成员的诊断去哪看

- **主视图**：诊断侧栏现成的两块。选中成员时 `focusEvent` 会展开它所在 node 的候选表、标出它那一行（`markedEventIds`）；选中 hit 时 `hit_trace` 列出各 node 绑定的实例与每条 where、边是否成立。要补：标出的候选表行滚到可见处。
- **compare**：`selection` 页（compare-coexist）；选中状态共用 `focusEvent` / `focusHit`。
- user-proxy 提：候选表里卡住的 where 显示的是 where 名（如 `no_chase`），用户读不懂。where 名换成用户的词是 mapping 的事（上一轮报告方案 B「属性对一条 where，clause 名用用户的词」），不归折叠。

## 四、同 hit 联动选中

### 4.1 选 hit → 各 band 上它的成员

- **高亮集合不变**：现有 `highlightedEventIds`（hit 绑定的各实例加它们 `child_refs` 里的子事件，不沿 anchor 展开）。
- **每个高亮成员**：空心细框，从族起点到它的终点（深色 `#1e293b`、1.5px，同现有 group 档）；它那一格（单成员族是整条）再加粗框。被点的那一个两处都用 2.5px（同现有 focus 档）。现有高亮是放大的实心复本（fill = 本色），在折叠行上会盖住后面的格子，改为只描边；投影沿用。族里别的格不压暗，免得「压暗」和「detected 浅灰」混。
- **当前日竖线**：1px 深色（同选中框）、两侧各 1px 白边，从 K 线主图顶一直穿到副图最下面。副图里画在条和格的上层：缩小后 in_hit 连续几天的格之间没有空隙，画在下层会被整段盖住（skeptic-2 指出）；白边让它压在任何颜色的格上都和底下拉开深浅。主图里画在 K 线下层，不遮当天那根 K 线。
- **竖线落点**：点 ▼ 是那个 ▼ 那天；点格是那一格那天；点整条是它的终点；从侧栏 hit 列表选 hit 取它的第一个买入日；compare 下点样本是样本日、点框是框终点；待选时不画。
- 示意图右半边：选中「前缀 e=21、当天 t=31」这次 hit——bracket 行那一格粗框、plateau 一格、step 一格、new_plat 第二行一格、today 一个，都在竖线上或紧挨着它（new_plat 截到当天前一天，在竖线左边一格）；bracket 行底下的粗黑线是当家行。

### 4.2 同一天几个成员时，联动亮哪根

- 点那一格先选最深的；都是 in_hit（分属几次 hit）时选原顺序第一个，→ 换下一个。
- 区别显示在其余 band：plateau 那一格几次一样；step 行加粗的是哪个前缀的格、new_plat 加框的是哪一行；old_plat、today 共用。侧栏 hit 列表这一天几行，选中的那行有底色。

### 4.3 反查：点一个成员 → 它所在的 hit

- **三分支保留**（`stores/view.ts::focusEvent`）：0 个 hit 只选中成员（加它的组成组一起亮）；1 个直接选中那次 hit；≥2 进入待选。
- **new_step 里谁会 ≥2**：`old_plat`（同一次阶跃所有前缀、所有天）、`step`（一个前缀所有天）、`today`（同一天几个前缀）。`plateau`、`new_plat` 成员各只属于一个 hit。
- **待选的画法**：被点的成员粗框；它所属的 hit 在 bracket 行上那些格加细实线框；侧栏 hit 列表照现有 `markedHitIds` 标出全部候选；竖线不画。去掉闪烁（几十个同时闪很吵，候选恰好是同一行里的一串格，加框已醒目）；现有候选 bracket 的琥珀虚线边改成实线（虚线只留给用户画的）。
- **候选提示条**（`components/CandidateStatusBar.vue`，现为「候选: ①③ — click 任一 bracket 高亮 / Esc 取消」，圈号已无意义）：改为 `candidates 23` `←/→` `Esc` 三段等宽标识，解释放悬停。
- 选定：点其中一格，或 ←/→。顺带回答「这个旧平台被哪几天的买点用到」。

### 4.4 compare 下点样本、点框（与 compare-coexist 共定）

- 点样本：当前日 = 样本日。竖线经过的往往是 plateau 轨上好几行各一格（样本日那天有 1～6 个实例结束、来自 1～5 次阶跃；RGTI 11-29 六个实例五次阶跃，只有最后一次成 hit）。「配对那一格」粗框：那天有 hit 就选那次 hit；否则选竖线上档位最深的格；同档取起点最晚的族（最近一次阶跃）——skeptic-2 核过 7 个多族样本日都对，仍标待验证。同一格的几个前缀不再挑，区别留给子段 band。想看别的阶跃，点竖线上另一行的格。
- 点框：当前日落在框终点，亮框终点那一格。

### 4.5 hit 列表（诊断侧栏）

- 现状（`components/DetailSidebar.vue` 的 `hits` 区）：一行一个 hit，序号 ①～⑨ 循环、第 10 个起重号。
- 必改：每行标买入日期取代圈号；选中行滚到可见处（3.2 的同日第 2 个靠它）。可选：按族分组（组头 = 族起点日期 + hit 个数，可收起）。

## 五、点几下（对照 `notes_user-proxy.md` 第 0 版）

只数「点、切换、展开」；悬停、滚动另记。

| 任务 | 第 0 版 | 折叠后 |
|---|---|---|
| a 样本 a / b / c 那天认没认出 | 1 下（切 compare）+ 大量滚动与目测，答不出 | 点 ▲（1 下）：竖线落在样本日，plateau 轨竖线上那几格的高低就是答案；不点也能看 ▲ 正下方的格 |
| b 某个样本没买、哪条没过 | ≥4 下，路不明 | 点 ▲（1 下），selection 页列出（compare-coexist）；主视图里点那天那一格（1 下），候选表滚到它那行，读 ✗ |
| c 一次阶跃后哪些天买了 | 1 下 + 滚动，读不出哪天 | 0 下：plateau 那一行里高的格就是买了的天；看日期悬停；逐天看 ←/→ |
| d 点一个 hit 看由哪几段组成 | 1 下，认不出选中的那根，找不到 step | 点那天的格或 ▼（1 下）：每条 band 一行，竖线上的粗框格 + 细框跨度就是各段，竖线穿到 K 线 |
| e 轨对应哪个框 | 无路 | compare-coexist |
| f 主视图与 compare 来回切 | 1 下，切过去要重新找方位 | 1 下，同一张副图、同一套点法 |

## 六、每个元素去掉会失去什么

| 元素 | 去掉后失去什么 | 能否用已有元素表达 | 结论 |
|---|---|---|---|
| 折叠行（格 + 底线；单成员族整条） | 回到几十行嵌套条 | 不能 | 必加 |
| 档位按高度分三档 | 色盲下 plateau、new_plat 的 in_hit 与灰分不开 | 不能（对比度 1.03 / 1.10） | 必加 |
| 点 / 条按 node 声明分 | 一根的阶跃前缀继续画成 ▼，和买入日 ▼ 撞形 | 不能 | 必改（后端加一个投影字段） |
| 选中跨度细框 | 看不见被选成员从哪到哪（d 任务） | 现有高亮的边宽、深色、投影沿用，族行上改空心 | 必加（现有高亮的小改） |
| 选中格加粗 | 看不出选中的是哪一天 | 不能 | 必加 |
| 当前日竖线（穿到主图） | 跨 band、对 K 线全靠眼睛；compare 下样本日在副图没有落点 | 鼠标十字线移开就没了 | 必加（user-proxy 最想要的一处） |
| 当家行标记（底线 + 表头加粗） | ←/→ 动哪一行看不见 | 选中格的粗细差（2.5 对 1.5px）太细，走查认不出；只有底线时也注意不到 | 建议，和 ←/→ 同进同退 |
| ←/→ 步进 | 同一格的第 2、3 个成员只能去侧栏点；逐日对比要来回点窄格 | 侧栏候选表能选任一成员，但要离开图 | 建议 |
| hit 列表日期标签、选中行滚动 | 序号重号；同日第 2 个 hit 没有看得见的反馈 | 不能 | 必改 |
| 候选提示条改文字 | 提示里的圈号与「click 任一 bracket」都已不对 | — | 必改 |
| hit 列表按族分组 | 列表长一些 | 日期排序已够用 | 可选 |
| 行尾 `k/n`、band 级展开开关、行尾 tier tag、格上个数、主图 hit 淡底色、悬停 K 线起止线 | — | 悬停 / 侧栏 / 格子高度 / 子段 band / 竖线 / 鼠标十字线 | 不做 |

## 七、色盲与界面文字

- **new_step 现在 node 色和档位灰的深浅对比**（WCAG 对比度，1 = 一样深；node 色由 `path2_web/serialize.py` 的默认调色板 `_PALETTE` 按 node 首现序分配，new_step 没有自己声明）：

  | node | 色 | 对 detected 浅灰 `#d1d5db` | 对 qualified 深灰 `#9ca3af` |
  |---|---|---|---|
  | plateau | `#16f943` 亮绿 | 1.03 | 1.77 |
  | old_plat | `#2563eb` 蓝 | 3.51 | 2.04 |
  | step | `#FF1500` 红 | 2.66 | 1.54 |
  | new_plat | `#14b24e` 深绿 | 1.90 | 1.10 |
  | today | `#7c3aed` 紫 | 3.87 | 2.24 |
  | 参照：中蓝 26,128,186 | `#1a80ba` | 2.94 | 1.71 |

  plateau 的 in_hit 对 detected、new_plat 的 in_hit 对 qualified 深浅几乎一样，恰是这两条 band 上最常并排的两档。所以高度是主通道。
- **建议（影响所有 app，待队长确认）**：默认调色板换成中等深度（亮度向中蓝那一档靠），并让拓扑顺序上相邻的 node 冷暖交替，具体色值待验证。user-proxy：「plateau 亮绿和 new_plat 深绿对我是同一种颜色」，就是相邻两 node 同为暖色、深浅又近。band 之间有表头分开，这条是减少误读，不是必需。
- **线与色块**：当前日竖线带白边，压在任何色块上都拉开深浅；选中框、跨度框、当家行底线是深色实线，压在中等深度的色块上靠深浅分开（深边对亮绿 10.2、对蓝 2.8、对紫 2.6，蓝紫格上靠线宽与投影补；调色板换中等深度后同步变好）。
- **界面文字**：新出现的固定文字只有悬停里的 `k/n`、`start`、`end`、`members`、`in_hit` / `qualified` / `detected`、`buy`，候选提示条的 `candidates n` `←/→` `Esc`，hit 列表日期；全部等宽、黑字，无说明句。

## 八、实施清单（按「马上要实现」的精度）

### 8.1 后端（纯投影）

- `path2_web/serialize.py` 拓扑 node 的 dict（约 305～316 行，`solve` / `render_grid` / `produced_by` 那几项旁边）：加 `"is_point": bool(getattr(n.event_cls, "is_point", False))`。子结构 node 的 `event_cls` 必填（`path2/dag/nodes.py` 构造期校验），所以每个 node 都拿得到。与 fold-rules 第 7 节同一个契约。
- （待队长确认后再做）同文件 `_PALETTE` 换中等深度、相邻冷暖交替的一组色。
- 测试：`tests/path2_web/test_serialize.py` 加一条：声明 `is_point = True` 的事件类（如 `path2_apps/new_step/plateau.py` 的 `Today`）对应 node 投影出 `true`，`Step` 投影出 `false`。

### 8.2 前端：折叠的纯函数（新文件 `path2_web_ui/src/render/fold.ts`）

只读 `node`、`start_idx`、`end_idx`、拓扑 `is_point`、档位、事件数组原顺序；不认任何事件类型。与 fold-rules 第 7 节的数据契约对齐（族的数据形状、先筛后折、反查索引）。

- `foldBand(events, bandKeyOf, tierOf)` → `Family[]`：按 (band, start_idx) 分族；族内成员按 (end_idx, 档位深→浅, 原顺序) 排；认族用全部成员，记 `multi = 成员数 ≥ 2`；再按档位筛掉成员（筛空的族丢掉）；`multi` 的族每个不同终点一个 `cell` mark，非 `multi` 的族一个 `bar` mark（跨度 [start, end]）；每个 mark 带 `memberIds`（已排序）、`tier`（成员里最深的）、`kind: 'bar' | 'cell'`。点 node 的族只有一个 mark。注意：档位筛选移进 `foldBand` 内部（要先拿到筛选前的成员数），`computeEventData` 只传入档位判定函数与当前档位。
- `familyMembers(family)`：步进顺序的成员 id 列表。
- `memberLabels(memberIds, byId, anchorFields)` → 每个成员 `{ via, ref_id, idx }`，给同一格几个成员做区分标签（规格见 `notes_fold-rules.md` 7.3b）：① 按 `child_refs` 的键顺序找第一个「成员之间子段跨度不全相同」的槽，`via` = 槽名、`ref_id` = 该成员在这个槽里的子事件、`idx` = 子事件终点；② 没有就看拓扑 edges 上的 `anchor_field`，取第一个值不全相同的，`idx` = 被锚事件起点；③ 还分不开用 `instance_id`。bracket 的 ▼：按拓扑 node 顺序找第一个「这几个 hit 绑定的实例不全相同」的 node，对那几个实例调同一个函数。三处共用：band 格悬停、bracket ▼ 悬停、compare `selection` 页诊断。界面按文字风格渲染，如 `step → 11-22`（`via` 等宽、日期由 `idx` 换算）。
- `foldHits(hits, events, endNode)`：hit 按 start_idx 分族，mark 规则同上（按 hit 的 end_idx），另给每族 `buys: { day, hitIds }[]`；`buyDaysOf` 连同它的单测从 `render/compareOverlay.ts` 挪进本文件（compare-coexist 定：`compareOverlay.ts` 整个删掉，`compareLanes`、`laneRowsFor`、`packHits` 退役）。
- `render/geometry.ts`：`packLanes` 原样复用（输入换成族的外包跨度）；`packBrackets(hits)` 改为对 `foldHits` 的结果分行并给族序号。

### 8.3 前端：数据与渲染（`path2_web_ui/src/render/chart.ts`）

- `BandRenderInput` 加 `currentDay?: number | null`、`activeFamily?: string | null`（当家行的族键）。
- `computeEventData`：
  - 顺序固定为：显隐筛选 → 认族（键用序列化下来的 `start_idx` 原值，用全部成员定 `multi`）→ 档位筛选 → 点 / 条分流 → 窗末拆段。拆段不能挪到认族前面，否则整条被拆成两段会认成两族。与 fold-rules 写的「先筛后折」结果相同（族只是成员子集），差别只在 `multi` 要用筛选前的成员数。
  - 点 / 条分流改读拓扑 node 的 `is_point`，不再用 `start_idx === end_idx`。
  - 对 `timeAnchored` 调 `foldBand`，按族 `packLanes`，每个 mark 展开成一条记录：`{ value: [x0, x1, lane, band, nBands], instance_id: memberIds[0], member_ids, family_key, mark_kind, tier, itemStyle }`，条进 `intervalData`、点进 `pointData`。value 形状不变，`components/KlineChart.vue::deriveSubGeometry` 的 lane 计数不用改。
  - 新产 `familyLineData`：每个族一条 `[族起点, 族终点, lane, band]`，带 `active`（是否当家行）。
  - 扫描窗拆段沿用 `splitIntervalAtScanEnd`，作用在整条和底线上；格整格判前后。
  - 副图不再产 tier tag：删 `tierTagData`、`tier-tags` series 与 `makeRenderTierTag`；`render/tierTags.ts` 若 compare 的 `missing` 不复用就整份删除（compare-coexist 定）。`view.tiers` 与顶栏勾选框由 compare-coexist 一并删。
  - `bracketData`：每个 hit 族的 mark 记录（`hit_ids`、`hit_id: hitIds[0]`、`family_key`）+ 每个买入日一条 ▼ 记录（`buy_day`、`hit_ids`）。
  - 高亮：对 `highlightedEventIds` 里每个成员找到它的 mark 与族，产出 `kind: 'extent'`（[族起点, 成员终点]，空心）与 `kind: 'mark'`（那个 mark，空心粗框）；被点成员两条都用 focus 线宽；`pendingDisambig` 是被点 mark 粗框。shift-veil 按 mark 产出。
  - 新产 `cursorData`：`currentDay` 非空时一条。
- 渲染器：
  - `renderIntervalWithGeom`：横向 `coord(start) − 0.4·unitW` 到 `coord(end) + 0.4·unitW`；高 = laneH × 档位比例，底对齐。比例常量放 `render/subGeometry.ts`（`TIER_H = { in_hit: 1, qualified: 0.65, detected: 0.4 }`，待验证）。
  - `renderPointWithGeom`：▼ 尺寸按档位三档。
  - 新 series `family-lines`（z 低于条）：1px 中灰底线；`active` 的画 2.5px 深色。悬停给族摘要（底线另画一条透明的加宽命中区，或并入格的提示，实施时定）。
  - `makeRenderHighlightWithGeom`：新增 `extent`、`mark` 两种画法（空心、深边、投影；group 1.5px / focus 2.5px），副图不再画实心放大复本。
  - `makeRenderBracket`：按 mark 画琥珀格或整条（满高）+ 底线 + ▼；选中 hit 画 [族起点, hit 终点] 空心框与它那一格粗框；候选 hit 的格细实线框，去掉虚线；圈号换族序号、挂行尾。`pendingBlinkAnimation` 只留给副图被点的那个 mark（是否保留实施时看效果定）。
  - 新 series `current-day`：副图在最上层，1px 深色加两侧白边；`buildMainOption` 里同一条画在 K 线下层（markLine 或 custom series，实施时定）。
  - `buildSubDecorGraphics`：当家行所在 band 的表头名字加粗（入参加当家 band 下标）；bracket 区表头同理。
  - `buildMarkerTooltipFormatter`：mark 有多个 `member_ids` 时逐个列，每个成员前挂 `memberLabels` 给的区分标签，抬头 `k/n`；▼ 的提示 `buy` 与所属 hit，几个 hit 时同样挂区分标签。

### 8.3a compare 共用同一份折叠

- 折叠只有一份实现（`render/fold.ts` + `render/chart.ts::computeEventData`），两个模式共用。compare 现在另有一套：`render/compareOverlay.ts::compareLanes` 把 mapping 对到的 node 的 event 按单个事件分行塞进特征轨，`render/annotateLanes.ts` 画。compare-coexist 已定：compare 的 band 直接走主视图副图那一路（`computeEventData` → `computeSubGeometry` → `buildSubOption`），这套「event 塞进特征轨」整体退役，`render/compareOverlay.ts` 整个删除，bracket 上的用户样本行、▲ 与 ▼ 并排由 compare-coexist 在 `render/annotateLanes.ts` 的用户层画；它只在主视图副图里插用户轨（`computeSubGeometry` 加可选 slots、`buildSubOption` 加可选 extra、`makeRenderBracket` 加 app 行竖直偏移让出 user 行，不传时逐字节不变）。这些改动归 compare-coexist（`notes_compare-coexist.md` 第三、八节），与本节的改动落在同几个函数上，实施时要排先后或由同一人做。

### 8.4 前端：状态与操作

- `stores/view.ts`：
  - 新 ref `currentDay: number | null`、`activeFamily: { kind: 'band' | 'bracket'; key: string } | { kind: 'external'; key: string; step: (dir: -1 | 1) => void } | null`。`external` 是留给非 band 行的口：任何一行（compare 的用户样本行）在被点时把自己设成当家行并带上自己的上一个 / 下一个回调，本方案不实现样本那部分（compare-coexist 按样本日走、走一步等于点那个样本，再按配对规则调 `setCurrentDay` + `focusHit` / `focusEvent`）。
  - `focusHit(hitId, opts?: { day?: number; family?: string })`、`focusEvent(instanceId, opts?: …)` 加可选参数，设当前日与当家行；缺省时 hit 取第一个买入日、事件取 `end_idx`（点取 `start_idx`）、当家行取它所在的族；待选分支清当前日、当家行设为候选所在的 bracket 族。
  - 新 action `focusBuyDay(day, hitIds)`：一个 hit 直接 `focusHit`，几个进待选。
  - 新 action `stepFocus(dir: -1 | 1)`：待选时在 `candidateHitIds` 里按终点走；当家行是 bracket 族时在该族 hit 里走并 `focusHit`；是 band 族时按 `familyMembers` 走并 `focusEvent`；是 `external` 时调它带的 `step(dir)`；到头停住。族成员按当前档位、显隐筛选后计算（和画出来的一致）。
  - `clearFocus` 同时清 `currentDay`、`activeFamily`。
  - 给 compare 用的 `setCurrentDay(day)`（点样本、点框时由 compare-coexist 的代码调）。
- `components/KlineChart.ts::handleChartClick`：`brackets` 系列分两种记录——mark 记录 → `focusHit(hit_id, { day: mark 终点, family })`；▼ 记录 → `focusBuyDay(buy_day, hit_ids)`。marker 系列 → `focusEvent(member_ids[0], { day: mark 终点, family })`。compare 下以上任一分支先调 `ann.selectBox(null)`。
- `components/KlineChart.vue::onKeyDown`：ArrowLeft / ArrowRight（无修饰键、非组字、焦点不在 input / textarea / contenteditable）→ `view.stepFocus(∓1)`、`preventDefault`；`buildRenderInput` 传 `currentDay`、`activeFamily`。
- `components/DetailSidebar.vue`：hit 列表行标买入日期（K 线日期现在只在 `KlineChart.vue` 的 `bars` 里，要放进 view store 或经 props 传，实施时定）；选中的 hit 行、标出的候选表行变化时滚到可见处。
- `components/CandidateStatusBar.vue`：改为 `candidates n` `←/→` `Esc`，不再按圈号列。

### 8.5 测试

- vitest 新增 `path2_web_ui/tests/render/fold.spec.ts`：同起点折一族、起点不同不折；多成员族每个终点一格、单成员族一根整条；只剩一个 in_hit 成员的多成员族仍是一格不是整条；同跨度成员并成一个 mark 且深档在前；档位筛选后底线缩短到最后一个剩下的成员；`is_point=false` node 的单根成员进条、`is_point=true` 的进点且同一根并成一个；`foldHits` 的 mark 与 `buys`，同一天几个 hit 并在一个 ▼ 上；`memberLabels` 三步（子段槽能分开时取第一个不同的槽；子段全同、anchor 字段能分开时取 anchor；都不能时回落 `instance_id`），以及 bracket ▼ 按 node 顺序找第一个绑定实例不同的 node。
- `tests/chart.spec.ts`：k 个同起点嵌套事件 → 一个 band 只占 1 个 lane；选中 hit 产出 `extent` + `mark` 且不再有实心复本；`currentDay` 产出竖线数据；`activeFamily` 让对应族的底线 `active`；整条与底线跨扫描末日时拆段；不再有 tier tag series；条宽一根 K 线时不再是 2px。
- `tests/render.chart.mainoption.spec.ts`：主图有当前日竖线且在 K 线下层。
- `tests/geometry.spec.ts`：`packBrackets` 按族分行、族序号。
- `tests/stores.focus-actions.spec.ts`（或新 `stores.step-focus.spec.ts`）：band 族内 ←/→ 顺序（含同一天两个成员）、bracket 族内按终点、待选时在候选间走、到头停住、`focusBuyDay` 的 1 / 多分支、`clearFocus` 清当前日与当家行；`tests/stores.disambig.spec.ts` 补「待选时当前日为空」。
- `tests/components.kline-click.spec.ts`：点 bracket 的 mark 调 `focusHit` 带终点与族；点 ▼ 调 `focusBuyDay`；点格调 `focusEvent` 带 `member_ids[0]`；compare 下点 app 元素取消框选中、不动样本。
- `tests/components.detail-sidebar.spec.ts`：hit 列表显示日期；选中行与标出行滚动。
- `tests/components.candidate-status-bar.spec.ts`：新文字。
- 后端见 8.1。
- e2e：更新 `path2_web_ui/e2e/marker-click-focus-highlight.spec.ts`、`hit-event-disambig.spec.ts`、`sidebar-chart-focus.spec.ts`、`subchart-band-zoom.spec.ts` 的断言；`dev-ui-replication.spec.ts` 截图基线会整体变（条宽、档位高度、tier tag 消失），重出基线并人工过目；新增 `e2e/fold-rows.spec.ts`：用带同起点嵌套事件的夹具（new_step 一只股票），断言副图 plateau band 行数 ≤ 族数、点 bracket 一格后出现两张图上的竖线与各 band 高亮、按 → 焦点换到下一次 hit 且当家行底线在 bracket 行、Esc 清空。

## 九、影响到 new_step 以外的地方

- 所有 app 的副图条：左右各多出约半根 K 线、高度按档位分三档、tier tag 不再画；bottom_burst 的 burst 前缀族、bb_v1 的同锚企稳段同样被折。
- 没声明为点、只占一根 K 线的事件（单 bo 的 burst、单日企稳段）从 ▼ 变成一根宽的格。
- bracket 从「一个 hit 一根条」变成「一族 hit 一行」，候选从琥珀虚线闪烁改为实线框，候选提示条改文字。

## 十、未决问题

1. 「族」「折叠行」「当前日」「当家行」要不要进 `path2_web/GLOSSARY.md`（用户还没定名）。
2. 档位三档的高度比例、lane 高够不够（7px 下 detected 约 3px）：待验证；不够就整体调高 `BAND_MARKER_H` 一个常量。
3. 默认调色板换中等深度、相邻冷暖交替：影响所有 app，待队长确认。
4. 候选改实线、去闪烁：影响所有 app，待队长确认。
5. compare 下点样本「同档取起点最晚的族」：待验证。
6. 本方案与 compare-coexist 的改动落在同几个函数上（`computeEventData`、`computeSubGeometry`、`buildSubOption`、`makeRenderBracket`、`stores/view.ts` 的焦点 action），实施分工时要排先后或交同一人。
