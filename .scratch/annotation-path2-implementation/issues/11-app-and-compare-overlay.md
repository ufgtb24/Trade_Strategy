# `app` 模式与第一段的 `compare` 叠画

Status: ready-for-agent
Progress: done
Claimed: 2026-11-03 parallel-tickets ticket-11 @ worktree impl/11-app-and-compare-overlay
Blocked by: 07

## Purpose

第一段的验证，要把会话照标注写出来的 app 叠回用户的图上，让用户看出差在哪。本票让主视图能切到 `app` 模式，以及不带对照 tag 的 `compare` 模式。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：
  - 5.2：顶栏的 `mode` 和 `tiers`、`app` / `compare` 怎么分轨、「模式切换」；
  - 5.8 全节；
  - 4.4 档位色；
  - 第 7 节 V-S1 的第 3、4 步；
  - 6.1「mapping 随 app 进 git」；
  - 用户故事 24。
- 决策：[结构化标注](../annotation-path2/issues/01-structured-annotation.md)现行 Answer 第 3 节（换图不退出 `compare`）。
- 前置交付：[07](07-grouping-and-pattern-page.md)。

## Inherited Direction

- 共用执行边界。
- **`compare` 只叠画，不做对照**：只把 app 的 event 叠到用户框所在的轨上，并在 `bracket` 轨上画 hit。不挂第二段的对照 tag，不显示 mapping（spec 5.8）。第二段的对照规则要等 V-S1。
- `tiers` 默认开，只管 band 上的 `qualified_only` / `detected_only`（spec 5.2）。
- band 和档位签用档位色，不套琥珀（spec 4.4，用户 10-29 定）。
- 用 `symbol` 换图时不退出 `compare`（决策票 01）。
- 跑 app 走现有的 `/preview`，数据照 4.1 截断。

## What to build

- 顶栏的 `mode` 分三档。当前 pattern 没有 app 时，`compare` 变灰。
- `app` 模式照现有主视图的画法：按 node 分轨，带三档和 `tiers` 开关。
- `compare` 模式：按会话手工给出的「app 的 node → 用户的特征」对应，把 event 画到对应特征的轨上，并在 `bracket` 轨上画 hit。
- **这个对应怎么给，spec 没定**（见[拆分总览](../ticket-breakdown.md)「待定」第 2 条）。本票的暂行做法：
  - 用一个随 app 进 git 的小文件，写明这个 pattern 用哪个 app、哪个 node 对应哪个特征编号；
  - 「当前 pattern 有没有 app」就看有没有这个文件；
  - 文件格式写进模块文档，供 V-S1 的会话照着写；
  - 第二段的正式 mapping 会取代它。

## Blocked by

07

## Acceptance criteria

- 用一个现成的 app（例如 `bo_only`）加一份手写的对应小文件：`compare` 下，event 出现在对应特征的轨上，hit 出现在 `bracket` 轨上，没有任何对照 tag。用 e2e 验。
- `compare` 下换股票，不退出 `compare`。从 `rally`、`random`、代码输入和链接进来时，都落在 `annotate`。
- app 的全部输出，最后日期都不晚于 2025-12-31（数据墙测试）。
- 没有对应小文件的 pattern，`compare` 是灰的。
- 拍截图自查（共用执行边界第 5、6 条）。
- `未安排人审：叠回来能不能看出差在哪；原因：这正是 V-S1 第 4 步由用户判的，V-S1 就是这次审查（spec 第 7 节）`

## 完成记录

2026-11-03，parallel-tickets ticket-11。合并提交 60e1c87（`--no-ff` 合回 `annotation-path2`），测试与审查所在提交 1c2db9b，合并后的树与之相同。

**可以开始 V-S1。** 01～11 都已 done 并合进 `annotation-path2`，12 不是前置。照拆分总览「第一段完成之后：V-S1」和 spec 第 7 节「V-S1 第一段验证」原文走。会话在第 3 步写 app 时，要同时手写一份 mapping，第 4 步才叠得回去：
- 位置：`path2_apps/<app>/mapping.yaml`，和这个 app 的 `dag_spec.py` 在同一个目录，随 app 进 git。有这个文件，这个 app 就是文件里那个 pattern 的 app。
- 格式（`path2_web/mapping.py` 的模块文档有全文）：
  ```yaml
  # compare 用的 mapping(暂行)
  pattern: 放量突破          # 标注里的 pattern 名，和顶栏 pattern 下拉里的一字不差
  features:                 # 特征编号: 认它的 node(app 的 node_id)
    w-pc-3: bo
    w-pc-7: tb_seg
  ```
- 键写特征编号（`w-<机器名>-<n>`），不写特征名，用户改名不影响。编号从 `path2_web.annotation.store.read_annotations(load_config())["state"]["features"]` 查。
- 一个特征只对一个 node，几个特征可以对同一个 node；没写进 `features` 的 node，compare 里不画。一个 app 只对一个 pattern；两个 app 写了同一个 pattern，两个都不能用。
- app 要在注册表里：后端启动之后新写的 app，要重启后端才认得。mapping 文件每次请求都重读，网页窗口拿回焦点时会再要一次。
- 写错了，顶栏 `compare`、`app` 变灰，悬停写出原因：文件读不懂、node 不在 app 里、两个 app 写了同一个 pattern。
- 第 4 步：打开标过的图，顶栏选这个 pattern，点 `compare`（event 叠到用户框所在的轨，hit 叠到 `bracket` 轨）或 `app`（主视图原有的画法，按 node 分轨）。两档都对这只股票的整段训练数据跑 app，截到 2025-12-31。

**做了什么**
- 后端（`path2_web/`）：
  - 新模块 `mapping.py` 读各 app 目录下的 `mapping.yaml`，查出问题：读不懂、形状不对、node 不在 app 的 dag 里、两个 app 写了同一个 pattern。
  - 新路由 `GET /mappings`：每次请求都重读，不返回日期。
  - `/preview` 回给前端的窗口终点截到 2025-12-31。读数本来就截断了，这里是让带缓冲的窗口终点也不越过训练段末日。
- 前端（`path2_web_ui/`）：
  - view store：
    - `ViewMode` 加 `compare`，`annotating` 在 annotate、compare 下都成立；
    - app 的来源分两种：扫描结果（原有）和当前 pattern 的 app 现算（新）。现算时 `effectivePattern`、`effectiveAnalysis`、`effectiveScan`、`appId`、`endNode` 都取现算结果；
    - app 的图窗改由 `appWindowOf()` 按需算；
    - 新增 `tiers` 开关。
  - 新 store `stores/appLink.ts`：
    - 读 `/mappings`，判当前 pattern 有没有能用的 app；
    - 切到 compare 或 app 时调 `/preview` 跑整段训练数据，只认最后一次请求；
    - 换股票、换 pattern 重跑，compare 与 app 互切不重跑；当前 pattern 没 app 了就退回 annotate。
  - 新 `render/compareOverlay.ts`：按 mapping 把 event 归到特征轨、分行；hit 排到 `bracket` 轨样本跨度那几行下面。
  - 新 `render/tierTags.ts`：tier tag 的形状、底色和让位规则（压到同一行下一个条、伸出图右缘时不挂），app 模式的副图和 compare 共用。
  - `render/annotateLanes.ts` 加 compare 的三个系列：event 条、tier tag、hit。`render/chart.ts` 给 app 模式的副图加 tier tag 系列。
  - `TopBar.vue`：`mode` 三档与灰态原因、app 名、`app-status`、`tiers`。
  - `KlineChart.vue`：compare 用全部 K 线再叠画；现算的 app 下也看整段。`ChartArea.vue`：现算时不显示扫描的 pattern 下拉和参数片。

**验收**
- e2e `e2e/annotate-compare.spec.ts`，用 `bo_only` 加一份写在临时目录里的 mapping（pattern `W底`，`w-pc-3: bo`、`w-pc-1: pk`）：
  - 第 1 条：
    - compare 下 event 条出现在对应特征的轨上，条数和起止与 `/preview` 给的逐个相同；
    - hit 在 `bracket` 轨上，个数与 matches 相同；
    - 副图上没有任何对照 tag 的字样（`missing`、`matched` 等 12 个词）；
    - 叠画的最晚日期不晚于 2025-12-31；
    - `peaks` 在 compare 下可用，切到 app 自动关；app 档按 node 分轨。
  - 第 2 条：compare 下用样本卡、代码输入、`random`、`rally` 换图，都留在 compare；从链接进来，落在 annotate。
  - 从 annotate 或扫描结果的 app 出发，代码输入、`rally`、`random` 都落在 annotate：`tests/components/TopBar.mode.spec.ts`、`tests/stores.view-mode.spec.ts`，以及原有的 `annotate-rally-random.spec.ts`。
- 数据墙：`tests/path2_web/test_data_wall.py::test_app_run_for_compare_stops_at_train_end`。
  - 合成股票的行情跨进 2026 年，照前端的方式请求 `/preview`（start 1900-01-01、end 2025-12-31）。
  - 所有下标都落在截断后的 K 线里，买点日期不晚于 2025-12-31，输出和直接拿截断的 K 线跑 app 逐个相同。
  - 作为对照，用完整行情跑，2026 年有事件，说明这组数据测得出泄漏。
- 没有 mapping 的 pattern，`compare` 是灰的：`TopBar.mode.spec.ts`，截图 01。mapping 的读取与查错：`tests/path2_web/test_mapping.py`。
- 拍截图自查：`evidence/11/`，2560×1440，scale=device。
  - `01-annotate-no-app.png`：pattern 是 unsorted，没有 app，`compare`、`app`、`tiers` 都灰。
  - `02-compare-page.png`、`03-compare-lanes.png`：NVDA，pattern 旗形，用会话 scratch 里给 `bb_v1` 手写的 mapping，compare 档，`peaks` 开。
    - event 条落在横盘、突破、回踩三条特征轨上；
    - qualified 深灰、detected 浅灰，tag 与条同色、细黑实线边，和用户的虚线框分得开。
  - `04-app-linked.png`：同一只股票切到 app，按 node 分轨，`peaks` 自动关，app 名只在顶栏写一处。
  - `05-compare-hits.png`、`06-compare-hits-lanes.png`：pattern W底（`bo_only`）。
    - hit 是琥珀底、细黑实线边，排在 `bracket` 轨样本那一行下面；
    - 进了 hit 的 bo 画 node 本色（亮绿），不挂 tag；
    - 琥珀和绿同是暖色，但分在两条轨上，不靠颜色区分。
  - 自查时发现并修了一处：缩放之后，放不下的 tier tag 还留在上次画的位置上。原因是 renderItem 不挂时返回了空 group，ECharts 不删上次的子元素；改成返回 null（提交 7da451d），单测改为断言返回 null。
- 测试结果（提交 1c2db9b，代码与 7da451d 相同）：
  - `pytest tests/path2_web tests/scripts`：515 个通过、2 个跳过、1 个失败。失败的是 `test_serialize_tbseg.py::test_serialize_tbseg_walked_from_container`，基线上就失败（同票 01、04、10 的记录）。
  - `npx vitest run`：1086 个通过、4 个失败，都在 `components.sidebar-result-list.spec.ts`，基线上同样失败。
  - `npx vue-tsc -b` 通过。
  - 标注 e2e 回归 19 条全过：`annotate-*.spec.ts` 加 `symbol-search.spec.ts`，日志在 `evidence/11/e2e-annotate.log`。
- 独立审查：`evidence/11/review-standards.md`、`review-spec.md`，修改在提交 45b8d90。
  - 需求问题，已修：
    - 不显示 mapping：去掉 app 名悬停里逐行列出的「特征 → node」；compare 下 event 的悬停只写档位和日期，不写 node。
    - compare 下换图的规则：见下面「交给用户的取舍」第 1 条。
  - 规范违反，已修：
    - 「签」一律改称 tag；
    - 注释只写现状，去掉「第二段会取代它」「第一段只叠画」这类话；
    - 撤掉给缺 `win_*` 的扫描文件留的兼容口：图窗改成 `appWindowOf()` 按需算，`windowOf` 照旧对残缺文件报错；
    - app 名只在顶栏写一处，图区上方白字的那处删掉。
  - 规范违反，没改的一条：悬停里 matched 档写作 `bound`。审查依据 `path2_web/GLOSSARY.md:28`，说三档只叫 detected、qualified、matched；但 spec 4.3（`spec.md:248`）定了标注工具里事件三档叫 detected / qualified / `bound`，主视图沿用 matched。照 spec。
  - 坏味道，已改：
    - 贪心分行改用 `geometry.ts` 的 `packLanes`，不再另写一份；
    - tag 右边界的算法收进 `tierTagLimit`；
    - 五处「现算时取现算结果」收成一个 `shownRun`；
    - `setMode` 的参数改用 `ViewMode`；
    - 名字 `link`、`links`、`CmpLane` 改为 `mapping`、`appLink`、`OverlayLane`。
  - 坏味道，没改：
    - `mapping._node_ids` 里「有 `load_params` 就按参数建 dag」是 `api.py` 两处之后的第三份。收成共用函数要动 `api.py` 两个现有路由，本票不碰。
    - `annotateLanes.ts` 里一个局部变量叫 `cmp`：它就在 `buildCompareSeries` 的调用旁边，读得出是 compare 的系列。
    - 用 band 指单个 event 的条：spec 4.4 本身这么用。

**交给用户的取舍**（都由测试守着，用户判断的部分写在末尾的「未安排人审」里）
1. compare 下换图的落点。
   - spec 5.2 写「用 `symbol` 换图时，不退出 `compare`」，票的验收又写「从 `rally`、`random`、代码输入和链接进来时，都落在 `annotate`」，字面冲突。
   - 现在的读法：已经在 compare 里时，代码输入、`rally`、`random`、样本卡换图都留在 compare；链接一律落在 annotate；从 annotate 或扫描结果的 app 出发，都落在 annotate。
   - 理由：决策票 01 的理由是「训练段上看着 app 标是用户的自由」，指向不关；验收那句管的是从别处进来时的默认落点；链接是从外面带进来的，按「进来」算。
2. 当前 pattern 没有 app 时，`app` 按钮也变灰（spec 只说 `compare` 变灰）。正在看扫描结果的 app 时（从扫描列表选了股），`app` 照常可点。
3. 另起特征轨：mapping 写到了、但这张图上用户没框过的特征，有 event 时另起一条轨，排在 unnamed 轨前面，看得出 app 认出了用户没框的段。spec 只说画在用户框所在的轨上。
4. compare 下，tier tag 横跨用户框的竖边时不挂（条的灰色还在），免得盖住用户画的框边。
5. 现算的 app 跑整段训练数据，不只跑看得见的这一段：拖动图窗不用重跑。`bo_only` 跑 NVDA 约半秒。
6. `tiers` 默认开是 spec 5.2 定的，所以原有的扫描结果 app 视图，副图现在也默认挂 tier tag。

**运行环境**
- worktree 的 `uv sync` 卡住，已按进程号停掉。pytest 和 e2e 后端改用主目录 `.venv` 的解释器（e2e 经 `PATH2_E2E_PYTHON`），已核对导入的是 worktree 的代码。
- 有一次 e2e 漏设 `PATH2_E2E_PYTHON`，`uv run` 卡住，每条测试等后端两分钟超时。留下 5 个还没起 Python 的 `uv run` 进程和 6 个 `/tmp/path2-annotate-e2e-*` 临时目录，已按进程号停掉、删掉；那次结果作废。
- worktree 的端口临时改成 8090 / 5190（skip-worktree，没提交），合回前已改回。`annotate-rally-random.spec.ts` 要求后端已在配置的端口上起好，回归时在 8090 上起了 `annotationBackend.py`（读训练段副本，标注写会话 scratch 目录），跑完已按进程号停掉。
- 自查时浏览器控制台出现过 ECharts 报错：
  - 改源码时 Vite 热更新引起的 `xAxis "0" not found` 等，刷新后不再出现。
  - 手工自查时连续三次进 compare，各报一次 `Cannot set properties of null (setting 'innerHTML')`，栈在 ECharts tooltip 的延时刷新里：tooltip 显示过之后，整图重设把 tooltip 换掉，旧的延时刷新还会跑一次。
  - 之后 14 次（含冷启动的后端、重启的 Vite、先在图上悬停再点）都没再现，画面不受影响，没改。

**界面名**
- 新起的：mapping 文件名 `mapping.yaml` 及其键 `pattern`、`features`；顶栏悬停与问题提示（`the app of the current pattern`、`the current pattern has no app`、`open a symbol first`、mapping 的几种问题句）。
- spec 已定的：`compare`、`tiers`、`qualified_only`、`detected_only`、`hit`（spec 5.2）、`bound`（spec 4.3）。状态复用 `loading`、`load_failed`。
- `compare`、`hit`、`bound` 和暂行的 `mapping.yaml` 不在 `path2_web/GLOSSARY.md` 的词头里（`mapping` 在 :144），要不要进词表由用户定。

**共享机制与复核**
- 改了：
  - view store：`ViewMode` 加 `compare`，`annotating` 涵盖 compare；`openSymbol` 在 compare 下不切模式；新 `appSource`、`linkedRun`、`tiers`、`appWindowOf()`；三个诊断触发和 `TopologyControl.vue` 改用 `appId`、`appWindowOf()`。
  - `stores/refLayers.ts` 的 `REF_MODES` 收紧成 `ViewMode[]`。
  - `/preview` 的窗口终点截断；新路由 `/mappings`。
  - `render/chart.ts`：`BandRenderInput.tiers` 和 tier tag 系列，作用于全部 app 视图，含扫描结果的。
  - e2e：`annotationBackend.py` 可选第 4 个参数（mapping 目录），`annotateHelpers.ts` 的 `startBackend(fill?, mappings?)`；票 10 的 `annotate-ref-peaks.spec.ts` 第 2 条结束前撤掉转发，消掉在途 `/peaks` 引起的偶发失败。
- 复核了还没开始的 12：只用到 01～05 的界面和指纹，条文都仍然成立，没有改动。spec 自认领以来没有变化。
- 本票代码改动的新增行里 grep `docs/research` 为空，只有审查报告把它当核对项提了一句。`api.py`、`view.ts`、`types.ts` 里有更早的引用，本票没动。

**写了共享数据**：无。只读了主目录的训练段副本。e2e 的标注与 mapping 写在系统临时目录，手工自查的写在会话 scratch 目录，没往 `path2_apps/` 里写 mapping 文件。已核对主目录的 `annotations/`、`datasets/` 在本票期间没有新改动的文件。

`未安排人审：叠回来能不能看出差在哪；原因：这正是 V-S1 第 4 步由用户判的，V-S1 就是这次审查（spec 第 7 节）`

`未安排人审：compare 下换图的落点读法、没有 app 时 app 也变灰、mapping 里有但图上没框的特征另起一条轨、tier tag 横跨用户框边时不挂（上面「交给用户的取舍」第 1～4 条）；原因：都只有用户实际用 compare 叠图时判断得了，build-on 是 V-S1，它本身就是这次审查（spec 第 7 节）`
