# 按代码打开任一只股票：标注模式的外壳与成交量

Status: ready-for-agent
Progress: done
Claimed: 2026-11-03 parallel-tickets ticket-04 @ worktree impl/04-open-by-symbol-shell
Blocked by: none

## Purpose

用户找图的第一条路，是直接打开「心里想到的那只」。本票让主视图不经扫描就能按代码打开训练段里的任一只股票，并且只画 K 线、成交量和用户自己的东西。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：5.2 顶栏的 `symbol`、侧栏三页、「图」里的成交量（M7）和 `annotate` 画什么；5.3「按代码打开」；4.1；1.8 的前两行；用户故事 1、5、27。
- 决策：[结构化标注：存什么、界面和主视图怎么合](../annotation-path2/issues/01-structured-annotation.md)的 Answer 第 1 节。

## Inherited Direction

- 共用执行边界。
- 标注时图上不画任何 app 认出的东西（决策票 01；说明书报告第 7 节第 4 条）。防的是：用户被现成的 detector 结果带偏。
- 股票列表就是训练段副本里有的股票，2026 年才上市的不出现。
- 不要 `json` 页（用户 10-31 定删）。
- K 线和成交量沿用现有渲染（spec 第 8 节）。

## What to build

- **后端**：
  - 加一个股票列表路由：读训练段副本目录，排除 01 写的指纹清单；
  - 按代码打开沿用现有的 `/ohlc`（已经截断）：代码不合法回 400，不存在回 404（`check_symbol`）。
- **前端**：
  - 顶栏加 `symbol` 输入框，回车就打开，不需要先扫描；
  - 侧栏建好 `selection` / `features` / `pattern` 三页的空架子，内容由后面的票填；
  - `annotate` 模式下只画 K 线、成交量，以及后面才有的用户的框和样本；
  - 成交量在三种模式下都画，高度默认约为主图的四分之一（待验证，spec 第 10 节）；
  - 现有的扫描入口照旧能用。

## Scope and exclusions

- 不做 `mode` 的 `compare` 和 `app`，这在 11。
- 不做画框，这在 05。
- 不改现有的扫描流程。

## Blocked by

none

## Acceptance criteria

- 在顶栏输入训练段副本里的任一个代码、回车：图打开，最后一根 K 线的日期不晚于 2025-12-31。2026 年才上市的代码不在列表里，输入后有明确的「不存在」提示。用 e2e 和 API 测试各验一遍。
- 非法代码回 400，不存在的代码回 404。用 API 测试验。
- `annotate` 模式下，图上没有 band、bo 方框这类 app 的产物。用 e2e 截图加 DOM 断言验。
- 成交量画在图的下方。
- 拍整页截图，照共用执行边界第 5、6 条自查配色和文字，截图放进 `evidence/04/`。
- `未安排人审：界面是否顺手、颜色是否分得开；原因：第一次真实使用就是 V-S1，它本身是用户的审查，那批标注只当试用（spec 第 7 节 V-S1）`

## 完成记录

2026-11-03，parallel-tickets ticket-04。合并提交 1db4ae1（`--no-ff` 合回 `annotation-path2`），测试与审查所在提交 cdd80e3，合并后的树与之相同。

**做了什么**
- 后端（`path2_web/`）：
  - 新路由 `/symbols`：列训练段副本目录里的 `*.pkl`，取文件名去后缀，只留过得了 `check_symbol` 的，按字母序返回。不读文件内容。实现是 `data.list_symbols`，只追加、没动已有函数。指纹清单 `FINGERPRINT.json`、`SNAPSHOT.json` 都不是 `.pkl`，不算股票。
  - `/ohlc` 的 `start` / `end` 改成可选。两个都不给时，返回这只股票截到 2025-12-31 的全部 K 线，按代码打开用的就是这条路。只给一个回 400。不给区间时，如果截完一根不剩，也回 404。这样配置的目录即使误指到完整行情，2026 年才上市的股票也打不开。带区间的老调用行为不变。
- 前端（`path2_web_ui/`）：
  - 顶栏 `TopBar.vue`：`symbol` 输入框，输入提示来自 `/symbols`，去空白、转大写后回车打开。
    - 不在股票列表里，旁边显示 `not_found`，当前的图不动。
    - 列表没拿到时交给后端判：404 弹 `not_found`，其他失败弹 `load_failed`。
    - 输入框平时显示当前打开的股票。
  - `view` store 加 `mode`（`annotate` / `app`）、`annotating`、`openSymbol()`：
    - 按代码打开落在 `annotate`。这时 `effectiveAnalysis` 恒为 `null`，也不跑 app 的预览，图、侧栏、状态条都拿不到 app 的产物。
    - 加载扫描、从扫描列表选股是 `app`，也就是原来的扫描视图。
    - 页面启动时默认 `annotate`。
  - `annotate` 下的外壳：
    - 隐藏原来的档位条、pattern 下拉、参数、拓扑面板、诊断侧栏、框选、driver 右键菜单和副图缩放钮；
    - 右侧换成 `AnnotationSidebar.vue`，三页 `selection` / `features` / `pattern`，目前都是空页，没有 `json` 页；
    - 主图只画 K 线和成交量，副图清空。
  - 成交量（三种模式共用 `render/chart.ts`）：
    - 从「叠在价格区底部 20% 的灰柱」改成 K 线区正下方单独一块，高度是 K 线区的 `VOLUME_HEIGHT_RATIO = 0.25`；
    - 柱色同 K 线涨跌（`#47b262` / `#eb5454`）；
    - 两块共用 x 轴缩放，日期刻度只画在成交量带下面，成交量带悬停也出 K 线 tooltip；
    - 因为单独成块，后面的票可以只在 K 线区里画框。
  - 连续换股时只认最后一次请求的 K 线，免得标题和 K 线对不上。
  - 新界面的字体和中性灰收成 `App.vue` 里的 `:root` 变量，灰都取自安全色板。
- 已有测试里五个直接往 store 里塞扫描状态的（`stores.triggerEventDebug`、`stores.anchor-kind-mapping`、`ChartArea.spec`、`ChartArea.panels`、`KlineChart.driver-menu` 的假 chart 补 `getHeight` / `clear`），改成先设 `mode = 'app'`。它们测的本来就是扫描视图。成交量相关的老断言按新画法重写。

**验收**
- 按代码打开、最晚日期、2026 年才上市的情形：
  - API 测试：`tests/path2_web/test_symbols.py`（新，7 条）、`test_data_wall.py`（新增 4 条，覆盖 spec 1.8 前两行和误配目录的兜底）。
  - e2e：`path2_web_ui/e2e/annotate-open-by-symbol.spec.ts` 第 1 条。代码从 `/symbols` 现取；输入后图的最后日期不晚于 2025-12-31；副本里没有的代码报 `not_found`。
  - 真实副本生成时跳过的股票数是 0（`SNAPSHOT.json` 的 `n_skipped_empty`），所以没有真实的「2026 年才上市」代码可用。e2e 用一个副本里没有的代码代表这一类，API 测试用合成数据。
- 非法代码 400、不存在 404：API 测试，加 e2e 第 3 条对真后端各打一次。
- `annotate` 下没有 app 的产物：e2e 第 2 条。先加载扫描，同一只扫描过的股票在 `app` 下副图有产物；按代码打开后：
  - 主图的 app 系列全空；
  - 副图没有任何系列；
  - 档位条和诊断侧栏消失；
  - 再从扫描列表选股回到 `app`。
  
  环境里没有扫描结果时，这条会先对 `^AA` 几只股票跑一次小扫描。截图见 `evidence/04/06-e2e-annotate-after-scan.png`。单元测试 `KlineChart.annotate.spec.ts` 另外验了这些。
- 成交量画在下方：截图 01（annotate）、05（app），以及 `render.chart.mainoption.spec.ts` 的布局断言。
- 整页截图与配色、文字自查：截图在 `evidence/04/00`～`07`，2560×1440，用 `evidence/04/shot_*.cjs` 生成。
  - 新加的文字都是黑色；程序固定文字（`symbol`、三个页签、`not_found`、`empty`）用等宽字体；灰字只用在空页的 `empty` 和没选上的页签。
  - 没有引入新色相，K 线与成交量的红绿是用户指定保留的例外。
  - 自查未覆盖的老部件：原来的 toast 是深底白字，左侧扫描面板有灰字中文提示。它们都是老部件，本票没改。
- 现有扫描入口照旧能用：e2e 第 2 条，加上老的 `e2e/symbol-search.spec.ts` 2 条通过。
- 测试结果：
  - `uv run pytest tests/path2_web tests/scripts`：380 个通过、2 个跳过、1 个失败。失败的 `test_serialize_tbseg.py::test_serialize_tbseg_walked_from_container` 在本票动手前的基线上就失败（读 `datasets/pkls/ACUT.pkl`，见票 01 记录）。
  - `npx vitest run`：919 个通过、4 个失败，都在 `components.sidebar-result-list.spec.ts`，基线上同样失败。
  - `npx vue-tsc -b` 通过。
  - `e2e/flow.spec.ts` 的 4 条失败：开头要求页面上有一个含「底部反转突破爆发」的下拉框，这个名字在代码里已经不存在，和本票无关。
  - 两个 e2e 文件在没有扫描结果的环境里并行跑时，`symbol-search` 有一次因为两边同时起扫描而失败，重跑通过。
- 独立审查：`evidence/04/review-standards.md`、`review-spec.md`。规范违反和需求问题都已修掉：
  - 注释只写现状；
  - 去掉和 `symbol` 重名的占位提示；
  - 灰色改用安全色板并做成变量；
  - 列表拿不到时 404 也报 `not_found`；
  - e2e 自备扫描并截图。
  
  采纳的坏味道：换图清理抽成 `resetChartState`，store 统一提供 `annotating`，字体栈收成变量，`/ohlc` 多余的分支删掉，边距数字改成命名常量。没改的一条：两个测试文件各有一个造合成 pkl 的小函数，日期默认值不同，测试文件照惯例各自独立，不抽公共函数。

**界面名**（新起的，照 `GLOSSARY-MAP.md` 命名规则，都是状态词）：`not_found`、`load_failed`、`empty`。`symbol`、`selection`、`features`、`pattern`、`annotate`、`app` 是 spec 5.2 已定的。不需要进词表。

**改了的共享机制**（05～11 会用到）
- `view.mode`、`view.annotating`、`view.openSymbol()`，以及 `effectiveAnalysis` 在 `annotate` 下恒为 `null`。
- 顶栏组件 `TopBar.vue`、右侧栏 `AnnotationSidebar.vue`、`App.vue` 的 `:root` 变量。
- 主图从一个 grid 改成两个（K 线区 grid0 + 成交量带 grid1），`mainGridLayout`、`emptyEventBundle`、`buildMainOption` 的入参收窄成 `MainOptionInput`。
- `/ohlc` 不带区间、`/symbols`。

已逐张核对未开始的 05～11，没有条文因此变假，未改票。给 11 的提示：`openSymbol` 现在一律切到 `annotate`。spec 5.2 要求「用 `symbol` 换图时不退出 `compare`」，11 做 `compare` 时要在这里分开处理。

**写了共享数据**：无。只读了主目录的训练段副本；测试扫描写在本票 worktree 的 `outputs/`，随 worktree 删除。

`未安排人审：打开时显示这只股票截到 2025-12-31 的全部 K 线（约 4 年）、成交量带高度取 spec 第 10 节默认（K 线区的四分之一）、右侧栏宽 320px；原因：都只有用户看图才判得了，build-on 就是 V-S1，它本身就是这次审查（spec 第 7 节 V-S1、第 10 节）`
