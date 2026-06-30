# 术语表（Glossary）

> 最后更新：2026-06-30
> **维护规则**：本文件仅在用户明确指定时追加/修改；`update-ai-context` skill 不维护本文件。
> 非必读；当沟通中出现某个项目上下文相关的术语、需确认其确切含义时，再查阅相应节。

## 1. 用语纪律

> 何时读：沟通/写码中涉及 where/edge/qualify/satisfies 等术语、需确认含义时。区分「约束」与「视图」，勿混。

- **where**（中文释义"定语"）= 单个 event 够不够格当某 role 的**一元**条件、**不看拓扑**（`NodeSpec.where` / `W.*`）；沟通统一用 **where**，"定语"只作释义、不再当独立叫法。
- **edge / 拓扑** = role 间的**二元**关系（边的 `satisfies`），与 where 正交。
- **动作动词（名词/动词分离）**：判断「event 够不够格当某 role」(一元) = **qualify**（资格判定）；判断「两个 event 关系成不成立」(二元) = **satisfies**（关系判定，`edge.satisfies` 真名）。名词用 where/edge，动词用 qualify/satisfies。
- **diagnose（role 诊断）/ trace（匹配 trace）** = 两个**调试视图**，**均同时含 where 与拓扑**（diagnose 的 `rel` 节、trace 的 `edge_results`），只指面板、勿用来指"条件"；diagnose 为 per-role 局部，trace 为 per-完整匹配。

## 2. 协议地基（path2/core.py · runner.py · stdlib/）

> 何时读：动 Event/Detector 协议、事件身份/去重、stdlib 便利层时。

| 术语 | 含义 |
|------|------|
| event | 多级不可变事件：`Event`（ABC，`@dataclass(frozen=True)`），公共字段 `event_id`/`start_idx`/`end_idx`，容器字段一律 tuple |
| 点事件 / point event | 几何上单 bar 锚定的 event：`start_idx == end_idx`。现役：bo / dist。**注**: 几何 isPoint 是 event runtime 派生属性, 同 detector 不同 event 实例可能跨 isPoint 与否(如 `BurstEvent` 单元素退化、`TrendSegment` 末段退化), 因此不宜直接当渲染分流键; 渲染分流靠 node 级声明 `NodeSpec.render_grid`(见第 7 节) |
| span 事件 / span event | 几何上跨多 bar 的 event：`start_idx < end_idx`。现役：burst / trend / platform / tb / match。语义上是"区间"事件(regime / 平台段 / 可买入窗口 / pattern 命中跨度等) |
| detector | 事件生产者：`Detector`（Protocol），`detect(source) -> Iterator[Event]`，由 `run()` 驱动 |
| class_id | 事件**类型**身份：`Event.class_id`（ClassVar），全局唯一、注册表查重；现值 `bo`/`burst`/`trend`/`platform`/`dist`/`tb`/`match` |
| event_id | 事件**实例**身份：经 `span_id(source_tag or class_id, start, end)` 生成，单 run 内唯一 |
| source_tag | detector **实例**身份（event_id 前缀）：同 class_id 多实例时引擎 `assign_auto_source_tags` 按 nodes 首现序自动编号（trend0/trend1）消歧；单实例/已显式命名的不动 |
| span_id | `span_id(kind, start, end)`：单点塌缩为 `kind_start`，区间为 `kind_start_end`（`path2/stdlib/`） |
| BarwiseDetector | 逐 bar 单点扫描模板（`path2/stdlib/`）：模板拥有扫描主循环，子类只实现 `emit` 领域判据 |

## 3. DAG 求解（path2/dag/）

> 何时读：动 pattern 声明（nodes/edges/where）、求解器、spec 校验时。

| 术语 | 含义 |
|------|------|
| node / role | `NodeSpec`：形态的角色节点 = 角色唯一键 `node_id` + 生产者 detector + where + `consumes_stream` + label；所有节点绑单 Event（dag/ 是单 Event 引擎，无区间绑定） |
| edge | role 间类型化二元关系（`DependencyEdge` 六子类：`TemporalEdge`/`ContainmentEdge`/`StartContainmentEdge`/`OverlapEdge`/`EqualsEdge`/`NegationEdge`），引擎只经 `satisfies`/`feasible_window`/`signature_fields` 多态消费 |
| where | 节点一元谓词（`(clause_id, fn)` 列表 AND 合取）；签名严格 `(Event, MatchContext) -> bool`（无 tuple 形态）；铁律：严禁读 `ctx.bound`（跨节点） |
| W.* | where 便利层四工厂（`attr` / `all` / `child` / `children`），返回 `_Pred`（带 `.meta` + `.measure`，富诊断的机制源头）。`W.children(key, agg)` 的 `agg` 接受用户自定义 lambda（无内置 seq 聚合工厂） |
| satisfies | 边的二元关系判定（动词真名 `edge.satisfies`）；求解器复核口径为 `edge.satisfies(src_ep, dst_ep) and edge._anchor_ok(src_ep, dst_ep)` 复合 AND |
| qualify | 资格判定（动词）：event 过某 role 的 where |
| qualified | qualify 的状态形容词：event 在某 role 下已通过全部 where clause。前端 Level 三档中间档名（matched/qualified/detected）；集合 `qualifiedIds = ⋃_role {全 clause satisfied 的 event}`（详见 [path2_web.md](modules/path2_web.md) 前端） |
| anchor_field / anchor_src_field | `DependencyEdge` 基类字段：表达"dst 端 anchor_field 等于 src 端 anchor_src_field"的身份引用约束（典型 use case：dst 显式标注它绑回某个 src 实例）。`anchor_src_field=None` 默认 `'event_id'`；`anchor_field=None` 时 `_anchor_ok` 恒 True（字节等价旧行为）。`PatternSpec._validate_anchor` 校验字段名在两端 event_cls 上存在 + 拒 `anchor_src_field='start_idx'/'end_idx'`（引导改用 EqualsEdge 走结构剪枝） |
| Child selector | 边端点选择器 `Child(node, key)`：外层边连复合事件的内部端点（如 `Child("burst","first_bo")`），求值期经 `endpoint()` 投影到子事件；selector 不参与边身份（spec 校验/WCC 构图仍只看纯 str）。详见第 4 节 |
| 流源 | 只为产流给他人消费（被 `consumes_stream` 指向）的孤立无边 node（如 bo）；其单 role 残缺 match 被 `analyze` 出口过滤丢弃，判据从 `spec.edges` 自动推 |
| PatternSpec | 声明容器：`pattern_id` + nodes + edges + root + event_styles 等；`__post_init__` 五类校验（`_validate_node_ids`/`_validate_dag`/`_validate_detector_dag`/`_validate_where_clauses`/`_validate_anchor`）；`to_topology()` 零派生直投面板数据 |
| solve | `_solve.py::solve(plan, streams, ctx)` = 唯一求解函数。语义：枚举所有满足 dag 约束的绑定（`_dfs` 回溯）+ 按 leaf event 跨 prefix 去重（reachable-leaves always-on）。`use_memo / collapse / memo_mode` 是差分测试参数；production 默认 `collapse=False, memo_mode='charitable'`。历史命名/分发开关已归档（见第 8 节） |
| reachable-leaves | leaf event 跨 prefix 去重：`solve()` 顶层初始化 `emitted_leaves: dict[node_id, set[stream_idx]]`（跨 WCC 共享，因不同 WCC 的 leaf node_id 不重叠），`_dfs` 内 cands 过滤掉 `i ∈ emitted_leaves[v]`，emit 时把 `assign` 内所有 leaf 节点的 `chosen_idx` 入集。同一 leaf event 至多 emit 一次（不论多少 prefix 能绑到它）|
| plan.leaves | `Plan` 字段（`compile_plan` 计算）：所有"无正向出边"的节点集合（`NegationEdge` 不算正向）。供 c1_off 第 4 源 + `solve()` 初始化 `emitted_leaves` 双重复用 |
| WCC | 弱连通分量：约束图按边连通切块求解，跨 WCC 拼接而非笛卡尔展开 |
| INV-C | 剪枝健全命脉：求解期剪枝只能基于 `feasible_window` 的单调结构字段（进 `signature_fields`）；`satisfies` 里读的非单调/身份属性绝不能进剪枝，否则漏匹配。所有边设计、C1 塌缩、新边类型决策都受此红线约束（`path2/dag/edges.py`） |
| C1 塌缩 | 求解期候选合并剪枝（`_signature.py::collapse_equal_end_keep_keymin`）：把"对下游剩余可行域影响等价"的候选合并成 `(start_idx, end_idx, stream_pos)` 字典序最小的代表——无 selector 出边按父 `end_idx` 分组（退化路径，与历史字节等价）；含 selector 出边按所有出边 `(src_selector, signature_field)` 并集的值向量做复合分组键。健全充要条件 = 分组键 ⊇ 所有出边判定依赖字段 |
| c1_off | 节点级 C1 关闭名单（`compile_plan` 维护）。**5 源总表**：(1) `EqualsEdge.src`（window 把 start 钉死非单调）；(2) `dst_selector` 非 None 入边的 dst（satisfies 看 child 端点）；(3) 含 `src_selector` 的 `NegationEdge.src`（signature_fields 为空、C1 学不到 child 端点）；(4) `plan.leaves`（出边为空的叶子，同 end 桶不能塌缩、reachable-leaves 兜不住的局部丢点）；(5) `anchor_field` 非空边的 src（anchor 边 signature_fields 为空、C1 学不到 src 身份）。改 C1/c1_off 必须 fuzz |
| match / 物化 | 求解命中后 `reify` 物化为 `PatternMatch`（class_id=`match`，携 `role_index` + `children` + `predicate_trace`） |
| role_index | match 内 node_id → 绑定 Event（单 Event 一对一，无 tuple 形态）的映射；`children` 为其平铺镜像（按 start 升序） |

## 4. 嵌套/复合事件

> 何时读：表达「一段子结构作为单元参与外层 DAG」时。dag/ 是单 Event 引擎，**复合事件是当前唯一现役的子结构聚合路径**。

| 术语 | 含义 |
|------|------|
| 复合事件 / composite | detector 把子结构聚合成的**一个宽事件**（如 `BurstDetector` 产 `BurstEvent`：start=首成员/end=尾成员，携 members + 预算标量）；在图里是一等宽事件，where 直读预算标量（与单实例同式、零特例） |
| members | 复合事件携带的子事件 tuple（如 `BurstEvent.members` = 串内各 bo）；不进图、不平铺进前端 event dict |
| child | 复合事件暴露内部结构的协议：`child(key)` / `children(key)` / `child_slots()` |
| Child selector | 边端点选择器 `Child(node, key)`：外层边连复合事件的内部端点（如 `Child("burst","first_bo")`），求值期经 `endpoint()` 投影到子事件；selector 不参与边身份（spec 校验/WCC 构图仍只看纯 str） |
| consumes_stream | `NodeSpec.consumes_stream`：None = 从 df 产流；填 node_id = 消费该上游流（如 burst/tb 吃 bo 流） |

## 5. 调试视图

> 何时读：排查「为什么没匹配上」、动 diagnose/trace 数据结构时。

| 术语 | 含义 |
|------|------|
| diagnose | per-role 健康检查（`diagnose() -> RoleDiagnostics`）：坐标轴是 **role 不是 event**（event 级失败归因 ill-defined）；含 `AttrRow`（where 各 clause）+ `RelRow`（关系伙伴）；单 role 局部视图，通过≠能凑成完整匹配 |
| trace | per-完整匹配的判定记录（`PredicateTrace`）：`where_results`（node_id → {clause_id: `ClauseWitness`}，satisfied+实测+阈值）+ `edge_results`（(src,dst) → `EdgeWitness`，两端实例+实测量）。`ClauseWitness` 4 字段（satisfied/measured/op/threshold），无 aggregate（B0 整改归档） |

## 6. 应用层（path2_apps/）

> 何时读：动具体走势声明（当前唯一应用 bottom_breakout_burst）时。

| 术语 | 含义 |
|------|------|
| bo / breakout | 突破事件（class_id=`bo`）：滑窗 peak 识别 + 单点突破；在 bottom_breakout_burst 中是孤立流源 node，喂 burst（聚合）与 tb（回踩锚点） |
| drought | bo 属性：距上次 BO 的 bar 间距（稀疏度），首 BO 为 None（语义"无前序"，非"未知"） |
| burst | 连续突破串（class_id=`burst`）：`BurstDetector` 消费 bo 流、按"段首+span 内吸纳+极大段贪心"切串，每段聚合成复合宽事件 `BurstEvent`（携 members + 预算标量 count/distinct_pk/max_vol_ratio/first_drought） |
| tb / throwback | 回踩确认（class_id=`tb`）：只能以 BO 锚点推断（核心是谓词 `evaluate_throwback(bo, df, ...)`），`ThrowbackDetector` 是事件壳（`consumes_stream='bo'`）；**事件存在 ⟺ 回踩成功** |
| trend segment | 三态走势区段（class_id=`trend`）：`TrendSegmentDetector`（SMA per-bar 变化 + hysteresis）切 df 为 down/sideways/up 连续区间流；`regime` = 三态标签、`drawdown` = 区段振幅 |
| platform | 窄幅震荡平台段（class_id=`platform`）：非重叠贪心扫窗 |
| distribution / dist | 高位派发单 bar（class_id=`dist`）：放量阴线 + 长上影 |

## 7. Web UI（path2_web/ · path2_web_ui/）

> 何时读：动后端投影/前端渲染、讨论 K 线/拓扑面板/诊断侧栏的显示行为时。

| 术语                             | 含义 |
|--------------------------------|------|
| web ui                         | 沟通简称：指 `path2_web/`（FastAPI 后端）+ `path2_web_ui/`（Vue3 前端）合起来的 web 模块；单说"web"不区分前后端 |
| 主图 / K 线主图                     | ECharts grid 0：K 线蜡烛 + 按 `NodeSpec.render_grid='price'` 钉到价格轴的事件 marker（如 bo 主三角钉 bar 顶 + pk 卫星 dot 钉 `referenced_points` 中的 peak 价格）。yAxis 是价格轴；卫星 marker 用隐藏的 axisIndex=2 副 yAxis 避免污染主价格轴 |
| 副图 / marker 副图                 | ECharts grid 2（事件区）：`render_grid='time'`（默认）的事件按 band × lane 几何排列的 marker 通道；yAxis 是 band 序（无价格语义），仅用于"哪根 K 线发生了什么事件"的时间对齐查看。与 K 线主图共享 xAxis（时间轴） |
| render_grid                    | `NodeSpec.render_grid: 'price' \| 'time'`（默认 `'time'`）。node 级**渲染分流键**（与匹配/求解语义正交）：`'price'` 入主图、要求 `event_cls.is_point=True`（`PatternSpec._validate_render_grid` 拒 span event × price grid 组合）；`'time'` 入副图。前端 `renderGridOf(node)` 纯函数读此字段路由 marker 系列 |
| referenced_points              | 点事件可选携带的 satellite marker 几何载体：`Tuple[Tuple[bar_idx:int, price:float, label:str], ...]`（默认空 tuple）。**当前唯一消费者**：bo event 在突破时填入被突破的 peak（label `pk<id>`），前端在 'price' 主图额外渲染同色卫星 dot；不影响匹配语义 |
| band                           | marker 副图的分轨：每 detector 实例（source_tag）一 band；前端经 `tagMap`（source_tag → band 序）派生，不解析 event_id 前缀 |
| lane                           | band 内重叠事件的泳道再分层（`packLanes` / `packByBand`，仅依赖 start/end，无类型特判） |
| bracket / matched marker       | match（pattern 命中）的时间跨度可视化：每个 match 一条灰色横带 + 圆圈序号 `①..⑨`（`renderBracket` chart.ts），`bracketData[i]` 携带 `match_id`(=match.event_id) + `value=[start_idx, end_idx, lane, ordinal]`；lane 由 `packBrackets`(geometry.ts) 按 start 全局排序后 packLanes 跨 match 防重叠；ordinal ①..⑨ 全局唯一作为 match 的 join key（多 match 重叠时消歧）。当前渲染在 grid0 顶部、`yAxisIndex:1`（隐藏 bracket 轴）；2026-06-30 agent team 调研已规划移到 grid1 顶部与 role band 行垂直对齐（见 `docs/research/2026-06-30_path2-web-match-event-correlation/`） |
| level                          | 全局显示档位旋钮：matched/qualified/detected 三档，统一控 K 线 + sidebar 的显示天花板（与 role 显隐正交） |
| detected ⊇ qualified ⊇ matched | 事件三档可追溯深度（tier）：detected = 全集（浅灰）⊇ qualified = 过该 role 一元 where（深灰，数据自预取 diagnose）⊇ matched = 进 match（role 本色） |
| 拓扑图/拓扑面板                       | `TopologyControl`：pattern 的 DAG 图 = role 控制器（单击节点 toggle 该 role 显隐、双击拉 per-role 诊断） |
| 诊断侧栏/Sidebar                          | `DetailSidebar`：漏斗总览（每 role 一行 detected▸qualified▸matched 计数 + 候选对比表）+ per-match trace；流源 role 渲染独立密度徽标、移出漏斗 |
| 双向高亮                           | K 线 marker ↔ sidebar 候选行点击互选联动（`selectedEventId` 跨视图） |
| 临时计算                           | path2_web 单股侧链路：用当前 `params.yaml` 即时算一只选中股，**不落盘**、不入扫描结果文件，专为"改 yaml 立刻看效果"的调参循环。代码层 = `preview` / `previewEnabled` / `runPreview` / `/preview`；UI 中文统一**临时计算**——模式名「临时计算模式」/「临时计算已启用」，动作「临时计算一次」/「重算当前股」，数据「临时计算结果」。与"扫描结果"(`scanFile.results`，落盘、全集)对照；K 线/拓扑/where 阈值勾选时优先取临时计算结果（`effectiveAnalysis` / `effectivePattern` / `effectiveScan`），取消勾选回退到扫描结果。复选框 UI label = "用 yaml 临时计算"；刷新按钮 ↻ tooltip = "重算当前股(yaml 改过后用)" |

## 8. 历史归档（`docs/legacy/`）

> 何时读：维护过程中遇到"为什么这块代码没了"的考古问题时。归档代码不可被任何活跃模块 import，仅作算法存档。

| 术语 | 含义 |
|------|------|
| Kleene | 区间绑定算法（`KleeneSpec` + `kleene_bind` + `_kleene_indeg_ok` + 6 个 seq where 工厂 `W.first/last/count/any/distinct/reduce`），2026-06 归档至 `docs/legacy/kleene/`。归档原因：现役业务全部用复合事件路径表达"段聚合"；Kleene 的求解期"段聚合判据可读外层 role 字段"能力当前无业务消费者，留在 `path2/dag/` 会污染引擎核心（endpoint 三态、双端点签名、Solution union 类型、_reify tuple 兼容等 14 个适配点）。复活路径见 `docs/legacy/kleene/README.md` |
| solve_next / solve_any / SelectionStrategy | 旧引擎的"贪心非重叠 / 全枚举"二选一求解机制。`PatternSpec.selection: SelectionStrategy` 字段曾在 `compile_plan` 处分发 `solve_next` / `solve_any`。2026-06 合一重命名为 `solve`（B1 stage，语义 = 旧 `solve_any` + reachable-leaves 去重）。2026-06-16 起 `SelectionStrategy` 类与 `selection` 字段也物理删除，不再有"模式"概念 |
| RoleBinding | 旧 `Union[Event, Tuple[Event,...]]` 类型别名（兼容 Kleene tuple 绑定），2026-06 删（`role_index` 类型收紧为 `Mapping[str, Event]`） |
| ClauseWitness.aggregate | 旧 ClauseWitness 字段（标记"来自 KleeneSpec.aggregate_where 的整串聚合谓词"），2026-06 删（B0 整改） |
| NodeSpec.kleene / TopoNode.kleene | 旧字段（绑 Kleene 串），2026-06 删 |

## 9. BreakoutStrategy

> 何时读：参考前身突破选股流水线（基本不用）时。本节不细分。

| 术语 | 含义 |
|------|------|
| breakout / bo | 突破点（价格有效穿越阻力位的 K 线） |
| peak / pk | 凸点，即被识别的阻力位 |
| factor / level | 评分因子（`FACTOR_REGISTRY` 注册）/ 因子离散化档位 |
| trial | 挖掘流水线的一次参数组合实验 |
