# path2_web 调试可视化架构意图

> 最后更新：2026-09-02

覆盖 `path2_web/`（FastAPI 后端）+ `path2_web_ui/`（Vue3 前端）。框架见 [path2.md](path2.md)，应用层见 [path2_apps.md](path2_apps.md)。

---

## 定位与边界

path2 dag pattern 的 **web 调试 / 可视化工具**：选 pattern → 全市场扫描 → K 线叠事件 markers + 拓扑面板 + 漏检诊断侧栏 + 参数探索。

管：把 path2 的分析结果投影成 JSON、并把它渲染成可交互的调试界面。
不管：任何走势语义。检测逻辑在 `path2/`，pattern 结构与阈值在 `path2_apps/`。

对外依赖（改动它们的形状要同步 web）：
- `path2.dag` 的只读结果结构（`path2_web/serialize.py` 顶部 docstring 列了消费的类型）
- `path2.eval` 的前瞻收益计算（label 注入）
- app 包对外暴露的模块级契约（pattern 构建 / 分析入口 / 参数加载 / `eval_meta`），注册闸的校验口径见 `path2_web/discovery.py`
- 成对 event 的诊断复刻边检查时，复用了 `path2.dag` 求解层的内部函数（含私有模块）：path2 改求解语义，这里的诊断口径会跟着变、且不会报错

---

## 两条红线

1. **后端纯投影层**：`path2` 本身零 web 依赖（不引入 JSON / HTTP）；序列化只在 `serialize.py` 发生，且是纯函数——不读文件、不起服务。
2. **前端类型无关渲染器**：渲染只吃后端下发的 `node_id` / `instance_id` / `topology` / `event_styles`（身份双轴契约，见 [path2.md](path2.md)），**产品代码零具体事件类型、零 pattern 名硬编码**。

合起来的收益：新增 pattern（新建 path2_apps 子包）时，前后端都零改动。这条收益是这两条红线存在的**全部理由**——任何要求"给某类事件开个特例分支"的改动都在偷走它。

---

## 关键决策与理由

**eval_meta 是 app 的必需协议，不是可选优化。** app 必须交出买点 node 与指标 warm-up 深度，web 才能算缓冲窗与 label。若允许 fallback（猜一个 node、写死一个天数），web 产品代码就得知道具体 app 的常量，红线 2 立刻破。所以在 pattern 注册时就设闸：不合规的 app 直接不入 registry、进 errors 列表，下游因此可以无条件取用、不做兜底。

**双端缓冲切窗。** 起点前推供指标 warm-up、终点后延供前瞻收益；缓冲段事件照旧序列化（K 线上以灰色层可见），但 match 要按买点日期落在严格窗内才算命中。**样本消费窗双边截取**（tb v4 起）：机器照常跑满含缓冲区的切窗（跨界段拿到真实 outcome、轨迹可见），但一切逐日统计消费（forward_returns / first_passage / drawdowns / 买点日计数）在 worker 层统一截到 [start_ts, end_ts]——样本日 ≤ end_date 保证 label 前瞻窗 ⊆ 尾缓冲区、label 永不残废；matches 过滤口径不变，前端副图 band 在 end_date 处彩/灰分色（灰 = 机器轨迹非样本）。交易日→日历日的换算比例与 `scripts/path2_eval_bottom_burst.py` 同源，两边口径必须对得上。

**label 叠在投影产物之上**：先投影出 match，再往产物 dict 上补前瞻收益字段；收益本身复用 `path2.eval`，web 不另起一套收益口径。这样投影仍是纯函数，"纯投影"边界不破。

**买点锚定 = eval_meta 的 end_node 路径声明**：窗口过滤与价格过滤共用 `path2.eval::_resolve_end_events` 解析出的买点事件——路径场景（`"tb.segments"`）下过滤 = **任一 OR**（任一解析事件命中即保留）；leaf 锚定容器 `node_index[路径首段]`；容器 `sample_bar_indices` 的 override 已删（统一由解析层锚定）。声明是唯一事实源，eval 统计与 serialize 过滤同源不漂移。

**副图分轨（band）= node_id 分组**（`render/visible.ts::bandKeyOf`，函数名沿袭旧称——分组键已是 node_id）。node 维度蕴含类型维度：每个 node 天然独立轨道、拓扑 node 独立显隐，作者零声明。子事件的 node_id 由引擎 children 声明命名表直标（tb 段 = `tb_seg`，见 [path2.md](path2.md)），band 天然分轨、零前端路由（childBandMap 已随命名表退役）；未声明 app 的段继承容器 node_id 落同泳道。前端**不得解析 instance_id 字符串猜归属**（那是引擎内部编码，不是契约；tb 变体细分走 node_id/child_refs 结构信号，见负知识·右键菜单）。

**评估单元 = match（两边一致）。** scan 与 eval_runner 都按 match 计——match 是 dag_spec 实例，每个都该当统计样本；按买点去重会切断上游反馈（被独占的上游永远零样本）。买点维度作**双口径补充**（`buy_windows` / `leaf_count`）保留、不替代 match 主口径；`shared_leaf_stats` 进一步描述"多对一确认"规模（被 ≥2 match 共享的买点数、共享 vs 独占胜率），支撑"多确认是否增信"研究。多对一的引擎机制见 [path2.md](path2.md) 多对一确认节。
**日级去重视图（dedup_daily，tb v4 起）**：match 主口径保留为诊断视角；用于交易决策的统计另按 (symbol, date) 去重——前缀族重叠机的重叠日 forward return 是同一物理观测，重复计数 = 伪复制（置信度虚增），实盘触发 = 一股一天一动作，统计单元对齐交易单元。去重序列过同一套 flat 汇总，`consensus_days`（被多 match 覆盖的日数）作显式中间量保留。

**排序锚 pattern 与 active pattern 解耦。** 多 pattern 扫描下，左侧列表按哪个 pattern 排序、与右侧渲染哪个 pattern 是两件事：列表单元格点击只切股票，active pattern 只由图表区下拉显式切换。混在一起会让"找漏检场景"这个动作不断打断当前观察对象。

**参数探索的两轴正交模型**（`ParamsChip` + `WorkingCopyDrawer` + 纯函数层 `paramsEditorState.ts`）：
- **内容轴** = 改副本；**视图轴** = 图表用不用副本重算。
- `enabled`（视图轴）的**唯一写者是 chip**；一切内容轴操作绝不碰它。
- 收益：「改副本内容」与「是否在看副本」各留恰好一个入口，不会互相触发。

**三档 level（detected ⊇ qualified ⊇ matched）由一组共享 computed 派生**（`stores/view.ts` + `render/visible.ts`）。K 线与 sidebar **共读同一批派生量**，着色与计数因此不会漂移；任何组件自己重算一份 tier 都会引入不一致。qualified 档数据源 = 后端 diagnose per-node attr 表"全 clause satisfied"行——空 clauses vacuous 真（tb/bo 等无 where node 恒深灰，无判别力；有判别力的只有声明了 where 的 node，bb 里是 burst；子结构段经 diagnose 挖 child 产行，见 path2.md 诊断节）。

**选中语义按父子关系分型**：children 声明两形态——**引用型**（槽引用独立 node，如 burst.members→bo：公共资源、可无父、可多父）与**组成型**（槽引用子结构 node，判别 = `topology.nodes[].produced_by` 非空：容器内部产物、专属单容器）。组成型组做**一选全选**（`stores/view.ts::compositionGroupIds`，并入 `highlightedEventIds` 传参）：0 归属（非 match）点容器或任一段 → 整组 group 边框，点击者仍走 focus 框；match 存在时空集、由 matchedIds 闭包覆盖（一选全选只服务无 match 的灰色组）；引用型与旧形态段（node_id 继承父）不触发、维持单点。

**pk 三态在前端合成，事件本身只留原始引用**：pk（峰）的 alive/broken/eaten 不是下发字段，`render/peakState.ts::derivePeakStates` 按本股全部 events（level/nodeVisible 过滤之前）的 `ref_ids` 关系合成——某 pk 的 instance_id 出现在别的事件 `ref_ids.broken` 里 → broken；出现在别的 peak 的 `ref_ids.superseded` 里 → eaten；否则 alive（broken 优先于 eaten）。**必须在过滤之前算**：被过滤掉的 bo 依然要能"突破"一个仍然可见的 pk，用过滤后的子集合成会漏判。pk 事件的判别子 = 带 `peak_idx`（数字）。pk/bo 特有语义（槽名 broken/superseded、字段 peak_idx/pk_id）的落点被限死在**两处**：`peakState.ts`（三态合成 + pk_id 反查的纯函数）与 `chart.ts` 的 pk/bo 分支（判别子、渲染锚点取 peak_idx、盒文本读 ref_ids.broken）——红线的实际边界是**其他 event 的渲染路径零特例**（`makeRenderPricePoint` / highlight / veil 一律只按 `item.state` 有无分派，不认识 pk），不是"chart.ts 不碰这些字段"。bo 盒文本（列出被突破的 pk 编号）同理是前端派生：查 `ref_ids.broken` 每个 id 在 `peakIdIndex`（instance_id→pk_id 反查表）里对应的数字，查不到（引用的 pk 不在本次 events 里）的静默丢弃。

**`solve=False` 的 node 免疫 level 门控**：pk 这类只显示不参与匹配的 node 恒为 detected tier（求解层就没绑它，没有"升到 matched"这回事），按常规 tier 排序过滤会在 `level=matched` 时被整段滤掉；`chart.ts` 按后端下发的 `topology.nodes[].solve` 单独放行——这是"类型无关渲染器"里少数几处允许绕开三档 tier 排序的地方之一，判据是结构标志（solve）而非事件类型。

**拓扑图两轴正交布局**（`render/topology.ts::layoutTopology`）：业务边做 left→right 最长路径分层（水平轴），父子关系（`parent_refs`）垂直挂靠（垂直轴）——业务流水平读、结构包含垂直读，两轴视觉上天然分离（曾有"burst→tb 双向箭头"误读，根因是父子虚线（子右父左）与业务实线同走廊反向交叉；垂直挂靠是结构性解法而非绕行补丁）。挂靠条件：恰一父 + 父在图中 + 非业务边端点 + 父非挂靠节点（两遍分类防嵌套，零实例仅防护）；不满足（业务端点 / 多父 / 嵌套）→ 回退水平流（父后列 + 水平虚线含 VBEND）。父非其层末位 → 降级守卫（防虚线穿兄弟节点）。高度预算闭式解（挂靠组放层栈之下，`contentH = max(effectiveStackH)`，无迭代）。挂靠虚线 = 垂直直线（子顶缘 → 同 x 父底缘），槽名 label 放虚线右侧（+8px，左对齐）——白底文字不得居中锚在虚线上（会盖断虚线）。

**漏检诊断按 scope 分派、只跑需要的那一 pass。** 各 scope 的数据依赖彼此正交（有的只要诊断产物、有的只要带 gate_failures 的分析结果），分开跑是为了避免在调试断点场景下被暂停两次。单股即时诊断可以接受重算成本。

**诊断响应允许"部分数据"**：接不上的那块以 caveat（原因码 + 说明）挂在响应上，前端据此显示提示条而不是崩或假装有数据。

**断点通道走进程 env**：`/diagnose` 写 `DEBUG_*` 环境变量供 `path2.debug_ctx` 消费，让 detector 在指定 bar / 锚点处停下。这是有意的单向注入，避免为调试在 path2 的函数签名里开洞。

---

## 不变式

- **`slice_window` 是唯一切片入口**（`path2_web/data.py`）。所有取窗路径（扫描 worker、各取数 / 诊断端点、设计期评估器）都经它，且同一次渲染涉及的路径共用**同一个窗**（缓冲扫描下即缓冲窗），才能保证 `bars[i] ↔ detector 的 start_idx == i`。破了它，前端 markers 就整体错位——而且是"看起来像检测逻辑出错"的那种错位。
- **身份契约面 = 引擎物化标注三字段**（instance_id / node_id / instance_idx，serialize 原样投影）：前端任何分组 / 过滤 / 归属键只能用这三个下发字段，不得自行构造 id 字符串。
- **复合事件的子 event 只以 id 引用下发**（由 event 自己声明的 child 槽位驱动，不硬编码字段名），子对象不内联进父 event——要下钻就按 id 回查 events 全集。
- **引用型槽同理只以 id 下发（`ref_ids`）**：`ref_slots()` 协议持有的原始事件字段（如 `broken_refs`/`superseded_refs`）按类型结构性排除出 payload，只有翻译后的 `ref_ids`（`{槽名: [instance_id,...]}`）出境；`state` 已删，`broken_peak_ids`/`pk_count` 退为 `BOEvent` 的 `@property`（Python 侧派生仍在用，只是不进 payload——`serialize` 只平铺 dataclass field，property 天然被排除），三态/计数类信息一律由前端按 `ref_ids` 关系现算，不下发预计算值。
- **单股失败不中断整批**：扫描 worker 的异常转成该股的错误计数，空窗直接跳过；一只票的脏数据不该让全市场扫描白跑。
- **进度流对晚连订阅者补发末态**：扫描已结束后才连上的页面必须立刻收到终态，否则前端永远停在"进行中"。
- **日期串恒为零填充 ISO**（`YYYY-MM-DD`）：前端直接用字符串比较取窗。
- **前瞻收益字段是三态**：键缺失 = 该结果文件根本没有 label（不显示该行）／null = 尾部数据不足（显示占位）／数值 = 真实收益。前端靠"键在不在"判别，**别改成"总是注入 null"**。
- **结果文件自包含**：pattern spec 快照与参数快照都写进文件，离线可独立渲染、也是参数 diff 的锚。**唯一例外是配色**——它是纯 UI 关注点，加载历史扫描时用当前调色板覆盖文件里冻结的那份，调色不必重扫。
- **`path2_web_ui/src/types.ts` 是后端 JSON 的镜像**，是前后端唯一对接面：后端改字段必须同步它（投影之后追加的字段同理）。
- 副图高度合成恒满足 `有效高度 ≤ 画布高度`（`render/subGeometry.ts`），即"永不留白"。

---

## 负知识（改这些地方会静默出错）

- **别复用 `mod.PATTERN_DAG` 去跑扫描或诊断**：它是 import 时一次性 build 的，会与磁盘上的 yaml 漂移。一律 `build_pattern(load_params())`，yaml 是参数 SSoT。
- **worker 里别直接调 `mod.analyze(...)`**：它内部自建 spec，外面拿不到 spec 就挂不上 `on_gate` 收集器（必须在 analyze 之前挂）。所以 worker 有意复刻其内部两步。
- **`attach_and_collect` 之后必须 `detach`**：ProcessPool 会复用进程，残留的 on_gate 会让下一个 symbol / pattern 串扰。attach 侧同时做两件事：给每个 detector 挂一个 per-call wrapper，按 `(detector, gf.stream)` 路由表把所属 node_id `replace` 注入 gf（detector 阶段读不到 node 归属，这是唯一注入点）；**同一条流**被 ≥2 node 绑定时挂雷式防护——那条流首条 gf 到达才 raise（node 归属在同流共享下无真值）。判据是流不是 detector：一个 detector 的不同流各绑一个 node（`BODetector` 的 bo/pk）合法，靠 `gf.stream` 分流。

- **scan 文件的标识符是 `scan.name`，不是 `scan_ts`**：落盘名 = `name or scan_ts`，`name` 来自扫描对话框「名称(可选)」，未命名时后端把 scan_ts 也写进 `name`。所以命名过的扫描文件名 ≠ 时间戳，凡是"按标识符找文件"的地方一律取 `scan.name`；`scan_ts` 只是创建时间（排序用）。`/params_diff` 的查询参数虽然叫 `scan_ts`，消费的却是标识符——名字骗人，别照名字传值（照传会 404 且只在 console 留 warning，静默失效）。

- **参数 dict 由主进程一次读好、直达 worker**：让 worker 各自去读 yaml，会与扫描期间的手工改动竞态。
- **存参数用 round-trip 写法，不要整文件 dump**：`params.yaml` 的注释是字段语义的 SSoT，整文件覆盖会把注释杀光。
- **`DEBUG_*` env 是进程级的**：`/diagnose` handler 的 finally 无条件清空它们，否则会跨 request 污染、甚至让扫描进程池继承后挂死。并发下这套行为未定义——这是单人调试工具的自觉取舍。
- **跨结构对拍别拿 `instance_id` 当锚**：pattern 结构一改 instance_id 就变，前后两次结果会全判成"新增+删除"。设计期回归对拍锚在 (股票, 买点日期) 这类语义键上。
- **扫描输出根目录锚在 repo root**，不跟随启动时的 CWD。
- 无参数快照的旧扫描文件：参数 chip 整体不渲染（没有锚就没有可信的 diff，宁可不给假 affordance）。
- 休眠草稿**只持久化副本内容**，编辑区里未写入副本的缓冲从不落盘；且刷新后**不自动激活**，需用户显式恢复。
- **leaf 维度统计必须按 `(symbol, leaf_event_id)` 聚合**：`leaf_event_id` 是买点的 instance_id、不含股票，跨股票同 id 是不同物理买点。按裸 `leaf_event_id` 跨股票统计会把不同股票的同 id 当同一 leaf → `leaf_count` 低估、`shared_leaf_stats` 高估（曾出过 bug）。reuse leaf 语义 = **同股票内**多 match 共享。
- **入口 A 的 brush 配置禁用 throttle debounce**：`KlineChart.vue::BRUSH_OPTION` 曾配 `throttleType:'debounce', throttleDelay:300`，拖动（约 100ms）结束时 brushSelect 还在 debounce 中、brushEnd 读到 null → **首次框选请求静默丢失**（2026-08-10 修复，改回默认 fixRate 0 即时派发）。请求只在 brushEnd 发一次，拖动中的高频 brushSelect 仅更新 latestRange——debounce 没有收益只有坑。
- **前端任何 node 过滤 / 选项必须从数据动态提取，禁止硬编码**：`FailedAttemptsCard` 下拉选项 = 后端 `TimePayload.all_nodes` 全集 ∪ 实际失败集（`gf.node_id`，gate_collector 注入），本区间无失败的 node 置灰 disabled——区分"node 存在但没失败"与"node 不存在"；残留过滤态按失败集 watch 自动回退"全部"（切区间后失败集必变、全集可能不变，watch 全集会漏触发）。曾因硬编码 + 类型漂移出过"诊断卡片无声缺失条目"的 bug，node 命名同样会漂移，教训同源。
- **入口 A 的 node 过滤是纯前端显示层，请求恒不带 `node`**：曾设计为"切换过滤 → 带 node 重新请求"，后端严格过滤返回子集 → 前端失败集坍缩 → **下拉其他 node 全部置灰、想切换必须先回"全部"**（2026-08-10 实测，已改为前端本地过滤 + 请求全量）。后端的 `node` 查询参数保留但前端不消费——任何"过滤器驱动重新请求"的改动都会让选项态与数据源耦合。
- **右键调试菜单契约（anchorsOf / debug_break 对齐）** 见 `.claude/skills/authoring-path2-detector/reference.md` §debug 菜单契约：anchorsOf 按 node_id 键控、埋点白名单（`debug_enabled_nodes`）由 anchorsOf 派生自动同步；anchor.bar 与 debug_break 第一参严格相等；debug 断点三门（mode / bar 区间 / anchor_kind，无类型维度）。子结构段（tb_seg / tb_seg_v3）anchorsOf 直挂键、断点落在 produced_by detector 的埋点；node_id 仍为 'tb' 的段（未声明 app）走 `tbAnchorProfile` child_refs 三档细分（容器 / 子段 / V1）——违背任一条都是"菜单/卡片存在但不 hit"的无声失败。

---

## 核心流程

```mermaid
flowchart LR
    A[path2_apps 各 app] -->|注册闸: PATTERN_DAG + eval_meta| B[PatternRegistry]
    B --> C[扫描 worker]
    C -->|缓冲切窗| D[analyze]
    D -->|窗内过滤 + label 注入| E[自包含结果文件]
    E --> F[前端加载]
    F --> G[view store 派生]
    G --> H[K 线 / 拓扑 / 侧栏]
    H -->|漏检查询 scope| I[/diagnose]
    I --> D
    H -->|参数副本| J[/preview]
    J --> D
```

前端永不直连 path2，只吃后端 JSON。
