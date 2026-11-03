# 归组与 pattern 页（unsorted、M9、计数）

Status: ready-for-agent
Progress: done
Claimed: 2026-11-03 parallel-tickets ticket-07 @ worktree impl/07-grouping-and-pattern-page
Blocked by: 06

## Purpose

用户先看特征、后定目标。本票让未归类的样本按骨架成行地挪进某个 pattern；还没有 app 时，用户也能从 pattern 页的计数里发现混进来的别的东西。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：5.2「淡化」；5.6 全节；用户故事 19～22。
- 决策：[界面显示的对称与统一](../annotation-path2/issues/15-display-consistency.md)的 Answer；说明书报告 M9。
- 前置交付：[06](06-samples-and-members.md)。

## Inherited Direction

- 共用执行边界。
- **计数照决策票 15**：
  - 一律数样本，写成 `pos k/N · neg m/M`；
  - 点开后就地分排，各排之和等于分母；
  - 是 0 也显示；
  - 凡是数样本的数都能点开。
  - 防的是：同一个数在不同地方意思不同，被读错。
- **负样本的「像」必须有对象**：挂在 `unsorted` 的负样本算没填完（说明书 ③；M9）。
- 同一样本收了几个同名框时，按「任一个」算（V-15-1 的默认，待验证）。
- 骨架用 03 的实现。

## What to build

- **unsorted 页**：
  - 按骨架分行；
  - 一整行可以 `move` 进已有 pattern，或者 `+ new`；
  - 负样本那一行加灰字 `pattern?`，带悬停提示；
  - 一行 `samples` 计数。
- **pattern 页**：
  - `definition` 输入框；
  - 页头计数；
  - features 区平铺，每块带 `in` 计数和属性的 `true` 计数，块之间画 `↓`，父子写成 `横盘 ⊃ 缩量`；
  - samples 表按 judgment 折行。
- **计数**：点开后就地分排。
- **淡化**：别的 pattern 的样本、它们的 bracket，以及只被它们收进的框，都画淡一些。
- **轨序**：`annotate` 的轨序改成按当前 pattern 里各段的先后。

## Blocked by

06

## Acceptance criteria

- 用一份固定的例子标注（存成 02 格式的批次文件）断言：各处计数正确，点开分排后各排之和等于分母，0 也显示。
- 骨架分行和 03 的例子一致。整行 `move` 以后样本的归属改变，刷新后还在。
- 挂在 unsorted 的负样本显示 `pattern?`。
- 拍截图自查（共用执行边界第 5、6 条）。
- `未安排人审：界面是否顺手、颜色是否分得开；原因：第一次真实使用就是 V-S1，它本身是用户的审查，那批标注只当试用（spec 第 7 节 V-S1）`

## Validation responsibility

为 V-15-1 实现默认规则。V-15-1 不在票里收口，见[拆分总览](../ticket-breakdown.md)「验证责任」。

## 完成记录

2026-11-03，parallel-tickets ticket-07。合并提交 5bb4304（`--no-ff` 合回 `annotation-path2`）。代码与测试的最后一个提交是 14a14f7，之后的 1a105f6 只更新证据；认领以来调度分支没有前进，合并后的树与 1a105f6 相同。

**做了什么**
- 侧栏 `pattern` 页（`PatternPanel.vue`）。当前 pattern 是 unsorted 时，它就是 unsorted 页：
  - 页头一行 `samples pos n · neg m`；
  - 未归类的样本按（judgment、骨架）分行。骨架用 06 的 `annotate/membership.ts` 的 `skeleton`，即成员框树顶层的特征按先后排，子框和属性不进骨架；
  - 每行写 judgment、骨架（特征名用 `→` 连起来）、`×n`，下面是这一行的样本卡。卡片右边单占一栏的是 `move`：下拉里列已有的 pattern 和 `+ new`，整行同一批改归属；
  - 负样本那一行在 judgment 后面写灰字 `pattern?`，悬停 `pick the pattern it looks like`（M9）。
- 当前 pattern 不是 unsorted 时是 pattern 页：
  - `definition` 输入框，写进这个 pattern，清空就拿掉定义；
  - 页头一行 `samples pos n · neg m`；
  - features 区：平铺全部样本（正、负都算）成员框树里出现过的顶层特征，块之间一律画 `↓`。在某特征的框里当过子框的特征，挂在那一块里面，写成 `横盘 ⊃ 缩量`。每块带 `in pos k/N · neg m/M`；这个特征的框判过的属性一个一行，带 `true pos k/N · neg m/M`；
  - samples 表按 judgment 折成 pos、neg 两行，没有样本的那行也在。
- 计数照决策票 15：
  - 一律数样本，写成 `pos k/N · neg m/M`，0 也显示；页头写 `pos n`、`neg m`；
  - 每个数都能点开，就地在它下面分排，排头写这一排的名字和个数。分法是：`in` / `not_in`；属性 `true` / `false` / `null`；页头是那一排样本。各排之和等于分母，空的排也写排头；
  - 同一页同时只点开一个，再点收起，换当前 pattern 时收起；
  - 悬停只说怎么数，挂在数上；特征名、属性名上的悬停只放定义；
  - 同一样本收了几个同名框时，属性按「任一个 `true` 就算 `true`、都没判算 `null`、其余算 `false`」（V-15-1 的默认）。
- 样本卡写三角、股票代码、样本日。点一下在主图打开那张图，图窗停在样本的跨度上、前后各留约两个月，同时选中这个样本；侧栏留在 pattern 页，方便挨个看。主图上选中的那个样本，卡的边加粗。
- 轨序：annotate 的特征轨先按当前 pattern 里各段的先后排，不在其中的特征排在后面、按这张图上首次出现排；子框轨仍紧跟父轨。当前 pattern 是 unsorted 时，按 unsorted 的样本排。
- 淡化：06 已经做了。本票核对时发现，起点在图窗外的框、bracket 会整条不画，于是别的 pattern 的样本跨度一切到图窗边就看不见；06 的「样本日之后暗一档」在图窗没拉到最后一根时也整条消失。原因是 ECharts 图窗的默认筛法要一段的两端都在图窗里。标注图的主图和副图改用 `weakFilter`：一段只要有一端在图窗里、或横跨整个图窗就照画。K 线、成交量只有一个 x，两种筛法结果一样。
- 数据层：纯函数在新文件 `annotate/grouping.ts`，包括一个 pattern 的全部样本、unsorted 分行、各段先后、features 区的块、计数与分排、打开样本的图窗。store 新增 `moveSamples`、`setPatternDefinition`、`openCount`、`definitionOf`，`selectSample` 多一个 `keepTab`。

**实现上的选择**（都由测试守着；只有用户判断得了的，写在末尾的「未安排人审」里）
- **各段的先后**：两两比先后。两个特征同在一个样本的成员框里时，谁在前的次数多谁排前；从没一起出现过的，按在样本里的平均位置排；还一样按特征编号排。没有直接按平均位置排，是因为骨架长短不一时平均位置会被拉偏。features 区和轨序共用这一个先后。
- **没打开过的图算骨架**：要知道框套框的长短，就要这张图的交易日。打开过的图用真的交易日，没打开过的用周一到周五代替（沿用 05 的 `kidWordsOf` 的做法）。只在 attach 的两个框长短只差节假日时，才可能让一个框换成顶层。
- **unsorted 的行序**：骨架按特征名逐个比，短的前缀在前，只差尾巴的几行挨着；没有成员框的（`∅`）排最后；同骨架 pos 在 neg 前。
- **属性一行只列在本 pattern 的样本里判过的属性**（判过 `false` 的也列，分子是 0 照写）。别的 pattern 里加的属性不带进来。
- **`×n` 只在 unsorted 的行上写**：pattern 页表的每行个数就是页头的数，不再写一遍。unsorted 行上的 `×n` 不做成能点开：它数的就是紧挨着列在下面的那几张卡。
- **pattern 的 definition 随时能改**：spec 只规定特征的定义「定下不改」，没规定 pattern。
- **整行 move 只改归属，不换当前 pattern**；`setSamplePattern` 改为走同一个 `moveSamples`。
- **样本卡不画缩略图**：spec 第一段没要求。卡上写股票代码和样本日，点开就是主图。

**验收**
- **用例子标注断言计数**：例子标注是 `tests/path2_web/fixtures/annotation_grouping_v1/batches/pc-20261103T120000.000Z-1.json`，02 格式，3 只股票、4 个 W底 样本、5 个 unsorted 样本、一个空 pattern。
  - `tests/path2_web/test_annotation_grouping_fixture.py` 2 条：重放没有冲突、越界和被跳过的文件；框的起止和样本日都是训练段副本里的交易日。
  - `path2_web_ui/tests/annotate.grouping.spec.ts` 9 条：把这份批次套到空状态上，断言各处计数。其中有 `0/0`、`pos 0/3`、空 pattern 全 0；有点开分排后各排之和等于分母、空排也在；还有「任一个」规则和界面写法。
  - e2e 在页面上核对同样的数：点开 `窄幅`、`放量`、`派发`、页头两个数，排头的个数之和、卡数之和都等于分母。
- **骨架分行与 03 的例子一致**：单测从 03 的例子文件 `membership_examples.json` 取全部 `tree` 例子，每个放成一个 unsorted 样本，各行骨架等于例子答案。同骨架的两张图并成一行，neg 另起一行。
- **整行 move、刷新后还在**：e2e 把 pos 的「横盘 → 突破」一行 `move` 进 W底，把 neg 那行 `+ new` 新起「头肩底」。刷新后状态里归属不变，unsorted 页剩两行；W底 变成 `pos 5`、`neg 1`。store 单测守着「一批送出、新名字同一批新建」。
- **`pattern?`**：e2e 断言 neg 那一行有灰字 `pattern?` 和悬停原文；挪走以后消失。
- **轨序**：单测和 e2e 都核对 MSFT 那张图的轨序。
  - 那张图上最早画的是一个不属于任何样本的 派发 框。
  - 当前 pattern 是 W底 时，轨序是 横盘、缩量 ⊂ 横盘、突破、派发、回踩；换成 unsorted 后变成 横盘、缩量 ⊂ 横盘、回踩、突破、派发。
- **截图自查**（共用执行边界第 5、6 条），截图在 `evidence/07/`：
  - 01：pattern 页点开属性；
  - 02：点卡片打开样本；
  - 03、03b：unsorted 页，以及别的 pattern 的样本画淡；
  - 04：空 pattern。

  自查结论：
  - 没有新颜色，只用黑、白、灰；K 线与成交量的红绿是用户定的例外；
  - 灰字只给 `pattern?`、`null`、`∅`、`empty` 和没选上的页签；
  - 程序固定文字等宽；特征名、pattern 名、股票代码用正常字体、浅灰底；
  - 虚线只出现在用户画的框和样本跨度上；
  - 03 里 W底 负样本的跨度切过图窗左边，画成淡灰虚线。
- **测试结果**：
  - `npx vitest run`：1026 个通过，4 个失败，都在 `components.sidebar-result-list.spec.ts`，票 04～06 记过，基线上就失败；
  - `npx vue-tsc -b` 通过；
  - `python -m pytest tests/path2_web tests/scripts`：499 个通过，2 个跳过，1 个失败。失败的仍是票 01～06 记过的 `test_serialize_tbseg_walked_from_container`，它读本机没有的 `datasets/pkls/ACUT.pkl`；
  - 以上都在 14a14f7 上跑。
  - e2e：`annotate-grouping`、`annotate-boxes`、`annotate-samples`、`annotate-open-by-symbol`、`annotate-rally-random`、`symbol-search` 共 13 条全过，日志在 `evidence/07/e2e-annotate.log`。
  - 标注 e2e 沿用 05 的临时目录后端，不碰用户的标注目录。
- 在本票的 diff 里 grep `docs/research`，结果为空。

**审查**：两份报告和逐条处理在 `evidence/07/review-standards.md`、`review-spec.md`。
- 已修：
  - 图窗筛法：起点在图窗外的框、bracket 和「暗一档」整条消失，改用 `weakFilter`，先在 e2e 里复现再修；
  - 界面名 `sequence` 改成 `skeleton`，和代码、spec 的「骨架」同名；
  - pattern 页表去掉重复的 `×n`；
  - 子块写成 `横盘 ⊃ 缩量`；
  - 计数写法收进 `grouping.ts`；
  - 复用 `precedence`、`sampleRange`，`definitionOf` 进 store；
  - 删掉 `PatternPicker` 里永远不起作用的过滤；
  - 改名 `ChartSample`、`CountButton`。
- 没改的，及理由：
  - `samples` 在页上出现两次：页头的数和样本表，spec 5.6 原文两处都叫 samples；
  - rank 排序在两个文件各一处：次序键不同，而且 `model.ts` 不能依赖 `grouping.ts`；
  - `samples` 与 `countKey` 一起传：两个 prop 本身就是「哪组样本的哪个数」；
  - unsorted 行的 `×n` 不能点开、本 pattern 没判过的属性不列：理由见「实现上的选择」。

**新起的界面名**（照 `GLOSSARY-MAP.md` 命名规则）
- 表头：`skeleton`（unsorted 页的骨架一列）。
- 行上的个数：`×n`。
- 没有成员框的骨架：`∅`。

`samples`、`definition`、`features`、`judgment`、`move`、`+ new`、`pattern?`、`in`、`not_in`、`true`、`false`、`null`、`↓`、`⊃` 是 spec 或决策票 15 已定的；`unnamed` 是 05 起的。

**给后续票的接口**（09、11）
- 09：
  - 「样本编号」链接打开那张图后选中样本，可以照 `SampleCard.vue` 的做法：先 `view.openSymbol(symbol, sampleWindow(x))`，等一个 `nextTick`（换图会清掉选中），再 `ann.selectSample(id)`；
  - `sampleWindow` 在 `annotate/grouping.ts`。
- 11：
  - 轨序：`computeLanes` 第四个参数是特征的名次，KlineChart 传 `featureOrder(patternSamples(state, currentPattern))`。compare 下 app 的 event 叠到用户的轨上，轨序不用另算；
  - 标注图的主图、副图都用 `weakFilter`，叠上去的 event 一端在图窗外也照画；
  - pattern 页现在只有「没有 app」的样子，有 app 时的分层属于第二段。

**共享机制与复核**
- 改了：
  - `annotate/model.ts`：`computeLanes` 加第四个参数，不给时照旧；`daysFor` 导出；
  - `annotate/samples.ts`：`precedence` 导出；
  - 标注 store：`selectSample(id, {keepTab})`，不给时照旧翻到 selection；`setSamplePattern` 改走 `moveSamples`，行为不变；
  - `PatternPicker.vue` 加 `move`；
  - 标注图主图、副图的图窗筛法改成 `weakFilter`。app 模式的画法不动。
- 复核了还没开始的 09、10、11、12，条文都仍然成立，没有改动。spec 自认领以来没有变化。

**V-15-1**：「任一个」规则按默认实现在 `grouping.ts` 的 `attrOf`，有单测。照拆分总览，V-15-1 不在票里收口：第一批真实标注出现「一个样本收了两个同名框、两框判法不同」时，由会话列给用户。

**写了共享数据和主目录**
- 标注目录、`datasets/` 都没写。测试只写系统临时目录和 scratchpad；主目录 `annotations/` 仍是空的。
- 有一次 e2e 回归误在主目录的 `path2_web_ui/` 里跑了（后台命令把 `cd` 带进了子 shell）。那次跑的是主目录的代码和端口：
  - 主目录被 git 忽略的 `path2_web_ui/test-results/` 被清掉、写进那次的结果，Playwright 每次跑本来也会先清这个目录；
  - vite 在 5171 起过，跑完自己停了；
  - 没写标注、没写 `outputs/`。
  - 那次的输出已删掉，主目录 `git status` 干净。随后在 worktree 里重跑，13 条全过。

**运行环境**
- worktree 的 `uv sync` 下载 torch 卡住，已按进程号停掉。pytest 和 e2e 用主目录 `.venv` 的解释器，在 worktree 根目录跑；已核对导入的是 worktree 的代码。e2e 用 `PATH2_E2E_PYTHON` 指定这个解释器。
- worktree 的端口临时改成 8087 / 5187（skip-worktree，没提交），合回前已改回。
- 04、08 的 e2e 要真后端：在 8087 起过一个，跑完已按进程号停掉。

`未安排人审：界面是否顺手、颜色是否分得开；原因：第一次真实使用就是 V-S1，它本身是用户的审查，那批标注只当试用（spec 第 7 节 V-S1）`

`未安排人审：各段先后的排法（两两比先后，同时决定 features 区和轨序）、unsorted 的行序、属性一行只列本 pattern 判过的属性、×n 只在 unsorted 行上写、点样本卡时图窗前后各留约两个月且侧栏留在 pattern 页、样本卡不画缩略图；原因：都只有用户实际归组时判断得了，build-on 就是 V-S1，它本身就是这次审查（spec 第 7 节 V-S1、第 10 节）`
