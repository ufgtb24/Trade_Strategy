# 放样本与成员框（含因果性、冻结与 M12）

Status: ready-for-agent
Progress: done
Claimed: 2026-11-03 parallel-tickets ticket-06 @ worktree impl/06-samples-and-members
Blocked by: 05

## Purpose

样本是用户「这天会不会买、凭什么」的判断。本票让用户放样本、看清依据是哪几个框，并保证两件事：依据里混不进样本日之后的东西；旧样本的依据不会被后来的改动悄悄改掉。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：
  - 5.2：样本三角、`bracket` 轨上样本的虚线、选中时暗一档、`pattern` 下拉；
  - 5.5 全节；
  - 用户故事 12～18。
- 决策：[结构化标注](../annotation-path2/issues/01-structured-annotation.md)、[命名](../annotation-path2/issues/14-naming.md)。
- 前置交付：[05](05-boxes-and-vocabulary.md)。

## Inherited Direction

- 共用执行边界。
- 正样本只按当天看得到的判（spec 1.3）。
- **成员框必须在样本日当天或之前结束**；换掉当前样本时，冻结旧样本的成员。防的是：后来补画的框改掉旧判断（决策票 01、14）。
- **M12**：拖框边时停在会被波及的那个样本日；`member_of` 列出收了它的全部样本，包括别的 pattern 的（变淡、只读）。防的是：删改共用的框时，在不知情中改掉旧样本的依据。这是已经实测到的漏洞（说明书报告 M12）。
- 前端的成员推断，必须过 03 的例子。
- `GAP`、`NEAR` 读同一处默认值（V-01-1）。

## What to build

- **放样本**：
  - `tool` 里的 `point`，放完自动回到 `box`；
  - 样本默认 `pos`，归当前 pattern；同一 pattern 同一天已经有样本，点下去就是选中它；
  - 顶栏的 `pattern` 下拉，含 `unsorted · n` 和 `+ new`；
  - `selection` 页可以改样本的 pattern、judgment、note，也可以 delete。
- **成员**：
  - 自动推断成员；
  - 手动点进点出：从样本这边的成员链、`others` 一排，或者从框那边的 `member_of` 一行；
  - 当前样本与冻结。
- **跨样本日的框**：变灰，悬停写 `crosses sample date`；成员链上的空槽注明原因。
- **M12 三条**：
  - 拖框边停在会被波及的样本日；
  - `member_of` 一行；
  - 02 拒绝保存时，在界面上显示原因。
- **辅助提示**：画了没收的空槽和 `◂`、`dup`、样本字母。
- **图上**：
  - 样本日画三角，正样本实心 ▲，负样本空心 △；
  - `bracket` 轨上画样本跨度的虚线；
  - 选中样本时，样本日之后的 K 线暗一档；
  - 不画两条竖虚线。

## Scope and exclusions

不做 unsorted 页和 pattern 页，这些在 07。

## Blocked by

05

## Acceptance criteria

- e2e 覆盖以下流程：
  - 放样本，它自动收进之前的框，刷新后成员不变；
  - 跨过样本日的框收不进，并且有提示；
  - 拖框边会停在样本日；
  - 换掉当前样本以后，再补画的框不会并进旧样本。
- 前端的成员推断过 03 的全部例子（vitest 读同一份 JSON）。
- 后端拒绝保存时，界面显示原因，改动不会悄悄丢掉。正常操作（不越界地改起止、删样本）照常保存。
- 拍截图自查（共用执行边界第 5、6 条）：实心和空心的三角分得清；暗一档以后，K 线仍然看得清形状。
- `未安排人审：界面是否顺手、颜色是否分得开；原因：第一次真实使用就是 V-S1，它本身是用户的审查，那批标注只当试用（spec 第 7 节 V-S1）`

## Validation responsibility

为 V-01-1 里的 `GAP`、`NEAR` 提供「只在一处设定的默认值」。V-01-1 不在票里收口，见[拆分总览](../ticket-breakdown.md)「验证责任」。

## 完成记录

2026-11-03，parallel-tickets ticket-06。合并提交 ef3c00c（`--no-ff` 合回 `annotation-path2`）。测试、审查修改与证据所在提交 84f9172；认领以来调度分支没有前进，合并后的树与它相同。

**做了什么**
- 放样本（`path2_web_ui/`，annotate 下）：
  - 顶栏 `tool` 加 `point`：点 K 线区某一根，在那天放样本，默认 `pos`，归当前 pattern；同一张图上当前 pattern 那天已有样本，就是选中它。放完工具自动回到 `box`。
  - 顶栏加 `pattern` 下拉：已有的 pattern、`unsorted · n`（全部图上 unsorted 的样本数）、`+ new`（输入名字回车新建并选中）。
  - `selection` 页选中样本时（`SamplePanel.vue`）：页头「字母 · 样本日」、三角、`delete`（框留在图上）；`pattern`、`judgment`（pos / neg）、`note`；`members` 成员链；`others` 一排。
- 成员框：
  - 放下时按推断定成员框，推断在前端本地算（`annotate/membership.ts`，规则同 03 的参照实现）。
  - 当前样本：这张图上最后一次放下或选中的样本。画框、选中框都不换掉它；选中另一个样本换成它；点空白处、Esc、换图清掉。当前样本期间新画的框，推断会收的就和这个框同一批并进它，只加不踢。换掉当前样本，它的成员框就此冻结，以后补画的框不会并进去。
  - 手动点进点出永远算数：样本页的成员链（点成员框拿掉、点画了没收的空槽收进）、`others`（点一下收进），框页的 `member_of` 一行（点上、点掉），以及图上框右侧的 ◂。改的是存下的成员框，并记 `members_edited`。
  - 框页顶上：这张图有当前样本时，显示一条它的成员链（只显示），点样本回到它。
- 跨过样本日的框：收不进，手动也点不进。`others` 里变淡、悬停写 `crosses sample date`；成员链上留一个空槽，变淡、带 ⇥，悬停写明原因；选中样本时，图上那个框画淡、右侧挂 ⇥。
- M12：
  - 拖框右边越过收了它的任一样本的样本日时，边停在其中最早的那个样本日，鼠标旁写 `member box of a ▲ 2025-11-18`。
  - 框页 `member_of` 一行列出收了它的全部样本，含别的 pattern 的（变淡、只读）；当前 pattern 里样本日不早于框起点的样本也列上，可点上；框跨过样本日的那个变淡、点不了。删框前在这里看得见会波及谁。
  - 后端拒绝保存时，提示条写 `save rejected`，每条原因写出 code、涉及的框（特征名、起止）和样本（字母、三角、样本日），悬停看后端原话，点 `ok` 才收起。同时重读一次标注，显示后端眼下的状态。被拒多半是另一台机器同步来的修改改变了前提，重读后拖框就会停在样本日。
- 辅助提示：
  - 画了没收：成员链上的空槽是短虚线、带 ◂，点一下收进；图上那个框换短虚线，右侧挂 ◂，点 ◂ 也收进。
  - `dup`：成员链上顶层同一特征两段时挂 `dup`。
  - 字母：同一张图上当前 pattern 的样本按日期标 a、b、c（只有一个也标 a），写在三角旁、bracket 上、样本页页头；框左侧的小字母写它是哪几个样本的成员框。
- 图上（`render/annotateLanes.ts`、`KlineChart.vue`、`components/annotateGestures.ts`）：
  - 样本日画三角：正样本实心 ▲，负样本空心 △（白底黑边）；选中的线加粗。点三角选中样本。
  - 副图最上面是 `bracket` 轨：每个样本的跨度（成员框最早的起点到样本日）画虚线，右端是三角和字母；选中的加粗、填浅灰，当前样本加粗。点它选中样本。特征轨接在它下面。
  - 选中样本时，样本日之后的 K 线区盖一层 7% 的黑，即暗一档。没有画两条竖虚线。
  - 选中样本时，它的成员框线加粗、虚线拉长；不相干的框画淡。
  - 别的 pattern 的样本（三角、bracket）以及只被它们收进的框画淡（不透明度 0.4）。
- `GAP`、`NEAR` 只在一处设定：仍是参照实现 `path2_web/annotation/membership.py` 的 `GAP`、`NEAR`。`GET /annotations` 和保存后的读结果多带一个 `membership: {gap, near}`，前端只用它，不另写默认值（V-01-1 的「只在一处设定的默认值」）。
- 数据层：
  - 纯函数在 `annotate/samples.ts`：字母、跨度、成员链、`others`、`member_of`、改起止的上限、框的标记；
  - 前端的成员框推断、成员框树、骨架、dup、空槽在 `annotate/membership.ts`；
  - store 在 `stores/annotation.ts`。

**实现上的选择**（都由测试守着；只有用户判断得了的，写在末尾的「未安排人审」里）
- **改起止与当前样本**：只有当前样本期间新画的框会自动并进；新画的框又被拖进推断范围也并进。拖一下旧框不会把它收进来，手动点掉的旧框不会因此回来。审查前一度把改了起止的旧框也算进来，按审查改掉。
- **点空白处、Esc、换图**清掉当前样本，照原型。选中样本不换顶栏的当前 pattern，也照原型。
- **字母只给当前 pattern 的样本标**：几个 pattern 都标的话，同一张图上会有两个 a，框旁的字母就说不清是哪个样本。别的 pattern 的样本画淡、只读，换到那个 pattern 就有字母。
- **样本页的 pattern 一格**：负样本挂在 unsorted 时显示灰字 `pattern?`，悬停写 `pick the pattern it looks like`（spec 1.3「挂在 unsorted 时，显示『待选』」）。unsorted 页那一行仍由 07 做。
- **当前 pattern 记在浏览器里**：刷新后还在。不记的话，新放的样本会悄悄落进 unsorted。记的名字已不在标注里时，退回 unsorted。
- **淡化在本票做了**：spec 5.2 要求别的 pattern 的样本、它们的 bracket、只被它们收进的框画淡。拆分总览把它列在 07，但本票画三角、bracket 和 member_of 的「变淡、只读」时离不开它，所以一并做了，有单测守着。07 只需核对。
- **保存被拒后重读一次标注**：05 原来是丢掉这次改动、显示退回保存前的状态。现在多重读一次，本页才知道另一台机器的修改。原因的显示照 05 的提示条，一直显示到点 `ok`，或下一次动作。
- **数值**（spec 第 10 节没有列的界面细节，都是 detail）：三角高 12 像素、底宽 14 像素，顶点在最低价下方 6 像素；暗一档是 7% 的黑（原型的值）；画淡分两档，选中样本时不相干的框 0.28，别的 pattern 0.4；bracket 一行 13 像素高。

**验收**
- e2e：`path2_web_ui/e2e/annotate-samples.spec.ts`，2 条，在 2560×1440 下跑，都过。
  - 第 1 条：
    - 先画三个框：横盘、突破，以及跨过样本日的第二个横盘。新起 pattern「W底」，point 在 n-30 放样本。它自动收进之前的两个框；跨过样本日的那个收不进（`others` 里变淡、成员链上有注明原因的空槽，点了也收不进）。主图有三角和暗一档，副图有 bracket 轨。
    - 刷新后成员框不变，当前 pattern 还在。点三角选中样本。
    - 拖「突破」右边越过样本日：鼠标旁出现 `member box of a ▲ 日期`，存下的终点等于样本日。再不越界地拖回去，照常保存。
    - 当前样本期间新画的框并进它，框页顶上出现当前样本的成员链。点空白处换掉当前样本后，再补画的框不并进它。
    - 样本页 `others` 点进、成员链点出，记 `members_edited`。
    - 框页 `member_of` 点掉、点上。跨过样本日的那行变灰、点不了；被 unsorted 样本收进的那行只读。
    - 改成负样本后显示空心三角和 `pattern?`；删样本照常保存。
  - 第 2 条：
    - 测试往标注目录里写一个 upc 的批次，把一个框收进样本。本页不知道这件事，把这个框拖过了样本日。
    - 后端拒绝，提示条写出 `box_crosses_sample_date`、框的特征名与起止、样本 `a ▲ 日期`。
    - 重读后，框还在、没被改，成员框里有它。点 `ok` 后再拖，就停在样本日并保存。
  - 标注 e2e 不碰用户的标注目录：沿用 05 的临时目录后端。主目录的 `annotations/` 跑完仍是空的。
- 前端的成员推断过 03 的全部例子：`tests/annotate.membership.spec.ts` 读 `tests/path2_web/fixtures/membership_examples.json`，四种（parents、members、tree、slots）共 20 例逐例通过，另加坏输入 1 例、例子种类齐全 1 例。
- 单测：
  - `annotate.samples.spec.ts`：9 条，字母、跨度、成员链、`others`、`member_of`、改起止上限、框的标记；
  - `stores.annotation.spec.ts`：新增 10 条，覆盖：
    - 放样本、同日选中、当前样本期间并进、两种换法后冻结、拖旧框不并进；
    - 手动点进点出（含跨过样本日点不进）、改 judgment / note / pattern、删样本；
    - 当前 pattern 记住与退回、保存被拒后重读；
  - `annotate.box-geometry.spec.ts`：新增 3 条，框的标记、bracket 轨、三角与暗一档。
- 后端：`tests/path2_web/test_annotation_api.py` 新增 1 条，读与保存后的读结果都带 `membership`，值就是参照实现模块里的 `GAP`、`NEAR`。
- 截图自查（共用执行边界第 5、6 条），截图在 `evidence/06/01`～`06`：
  - 实心和空心的三角分得清：`05-neg-sample` 里，当前 pattern 的空心 △ 黑边白底，别的 pattern 的实心 ▲ 画淡成灰色实心；`01` 里实心 ▲ 黑色。
  - 暗一档以后 K 线形状看得清：`01`、`05` 中样本日之后的 K 线涨跌色和影线都清楚。
  - 没有新色相，只用黑、白、灰；K 线与成交量的红绿是用户定的例外。虚线只用在用户画的框、bracket 上样本的跨度，以及代表画了没收的框的块上；提示条、停住时的提示一律实线。
  - 程序固定文字用等宽字体，特征名、pattern 名用正常字体、浅灰底；文字一律黑，灰字只给 `pattern?` 和没选上的页签。
- 测试结果（在 84f9172 上）：
  - `npx vitest run`：1014 个通过，4 个失败，都在 `components.sidebar-result-list.spec.ts`，票 04、05 记过，基线上就失败；
  - `npx vue-tsc -b` 通过；
  - `python -m pytest tests/path2_web tests/scripts`：497 个通过，2 个跳过，1 个失败；失败的仍是票 01～05 记过的 `test_serialize_tbseg_walked_from_container`，它读本机没有的 `datasets/pkls/ACUT.pkl`。这次在 307891d 上跑，之后后端没再改；
  - e2e：`annotate-boxes`、`annotate-samples`、`annotate-open-by-symbol`、`annotate-rally-random`、`symbol-search` 共 12 条全过，日志在 `evidence/06/e2e-annotate.log`。04 的 e2e 原来只把 `annotation-boxes` 当作用户的系列，现在副图多了样本跨度 `annotation-brackets`，一并排除。05 的 e2e 里共用的小工具挪到了 `e2e/annotateHelpers.ts`。
- 在本票的 diff 里 grep `docs/research`，结果为空。改动过的 `path2_web/api.py` 第 404 行有一处更早的、与本票无关的引用，没有动。
- **运行环境**：
  - worktree 的 `uv sync` 下载 torch 卡住，已按进程号停掉。pytest 和 e2e 用主目录 `.venv` 的解释器，在 worktree 根目录用 `python -m` 跑；已核对导入的是 worktree 的代码。e2e 用 `PATH2_E2E_PYTHON` 指定这个解释器。
  - worktree 的端口临时改成 8086 / 5186（skip-worktree，没提交）。
  - 04、08 的 e2e 要真后端：在 8086 起过一个，跑完已按进程号停掉。

**审查**：两份报告和逐条处理在 `evidence/06/review-standards.md`、`review-spec.md`。
- 已修：
  - 改起止把旧框也并进当前样本，改成只并新画的框；
  - 补「选另一个样本后冻结」「拖旧框不并进」两条单测；
  - 注释里的研究编号改成写要求本身；
  - 提示条去掉重复的悬停；
  - 样本排序复用 `sampleOrder`，框的先后改名 `precedence`；
  - 状态统一叫 `unclaimed` / `crosses_sample_date`；
  - 侧栏块的样式收进 `annotationPanel.css`，`PatternPicker` 用共用类，bracket 悬停用 `triOf`；
  - 截图进 `evidence/06/`。
- 没改的，及理由：
  - **侧栏里画了没收的块用短虚线**：它代表的就是用户画的那个框，和图上那个框是同一种短虚线，合「虚线只表示用户画的」。它不是 tag。
  - **store 里写 `box.end > date`**：问的是「能不能收进」。整段在样本日之后的框也收不进，和「跨过样本日」不是同一个判断。
  - **`emptySlots` 在图、样本页、成员链各算一次**：一张图的框只有几十个，重算不费事；收进 store 会让 store 为界面缓存派生量。
  - **字母拼样本称呼写了几处**：每处本来就要用字母表，拼起来只有一行。
  - **focus 的分支有三处**：三处分别回答怎么画、悬停写什么、点哪里算点到 ◂。
  - **字母只标当前 pattern、`pattern?`、当前 pattern 记在浏览器里**：理由见「实现上的选择」。

**新起的界面名**（照 `GLOSSARY-MAP.md` 命名规则）
- 字段名：`members`（样本页成员链的表头）、`others`。
- 停住时的提示：`member box of <样本>`。
- 提示条里指明对象：`box`、`sample`。
- 标记：跨过样本日收不进的 ⇥。

`point`、`pattern`、`unsorted · n`、`+ new`、`judgment`、`pos`、`neg`、`member_of`、`dup`、`◂`、`crosses sample date`、`pattern?`、`bracket` 是 spec 或词表已定的。

**给后续票的接口**（07、09、11、12）
- 标注 store：
  - `placeSample(symbol, date)`、`selectSample(id)`、`clearSelection()`、`toggleMember(sampleId, boxId)`；
  - `setJudgment`、`setSampleNote`、`setSamplePattern(id, name|null)`（名字是新的会同一批新建 pattern）、`deleteSample`；
  - `setCurrentPattern(name|null)`（名字是新的会新建）；
  - `selectedSample`、`currentSample`、`currentPattern`、`membership`（`{gap, near}`）。
  - `selectBox(null)` 现在只取消选中框；要「什么都不选、当前样本也清掉」用 `clearSelection()`。
- 09：「样本编号」链接打开那张图后，调 `selectSample(id)`。
- 07：
  - 骨架用 `annotate/membership.ts` 的 `skeleton`，给的是特征编号；
  - 成员框一律经 `annotate/samples.ts` 的 `memberIds` 取，即存下的、还在图上、在样本日当天或之前结束的；
  - 淡化已经做了（见上）；
  - `PatternPicker.vue` 可以给 unsorted 页的 `move` / `+ new` 复用。
- 11：
  - 副图第一条是 `bracket` 轨（`render/annotateLanes.ts` 的 `bracketGeometry`、`packBrackets`），app 的 hit 画在这条轨上时，在它的排法里加行；
  - 特征轨从 `laneGeometry(lanes, top)` 的 `top` 往下排。
- e2e：共用小工具在 `e2e/annotateHelpers.ts`（起临时目录后端、转发、打开股票、拖框起名、读状态与坐标）。

**共享机制与复核**
- 改了：
  - `path2_web/api.py` 的两个标注路由，读结果加 `membership`，原有字段不变；
  - `path2_web/annotation/membership.py` 的模块说明，加一句界面从哪读默认值；
  - 前端：`AnnRead` 多了必填的 `membership`；`laneGeometry` 加了 `top` 参数，默认值照旧；副图多了 bracket 轨；`selectBox(null)` 的含义见上；
  - 04、05 的 e2e 各一处。
- 复核了还没开始的 07、09、10、11、12，条文都仍然成立，没有改动。07 的「淡化」本票已做，07 核对即可。spec 自认领以来没有变化。

**写了共享数据**：没有。测试只写系统临时目录和 scratchpad；主目录 `annotations/` 仍是空的。

`未安排人审：界面是否顺手、颜色是否分得开；原因：第一次真实使用就是 V-S1，它本身是用户的审查，那批标注只当试用（spec 第 7 节 V-S1）`

`未安排人审：点空白处、Esc、换图会清掉当前样本（之后新画的框不再并进它）；选中样本不换顶栏的当前 pattern；字母只给当前 pattern 的样本标；当前 pattern 记在浏览器里；跨过样本日收不进的空槽在图上用 ⇥ 标出；暗一档取 7% 的黑。原因：都只有用户实际标注时判断得了，build-on 就是 V-S1，它本身就是这次审查（spec 第 7 节 V-S1、第 10 节）`
