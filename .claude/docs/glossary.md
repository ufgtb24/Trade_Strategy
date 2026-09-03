# 术语表（Glossary）

> 最后更新：2026-08-03
> **维护规则**：本文件仅在用户明确指定时追加/修改；`update-ai-context` skill 不维护本文件。
> 非必读；当沟通中出现某个项目上下文相关的术语、需确认其确切含义时，再查阅相应节。

## 1. 用语纪律

> 何时读：沟通/写码中涉及 where/edge/qualify/satisfies 等术语、需确认含义时。区分「约束」与「视图」，勿混。

- **where**（中文释义"定语"）= 单个 event 够不够格当某 node 的**一元**条件、**不看拓扑**（`NodeSpec.where` / `W.*`）；沟通统一用 **where**，"定语"只作释义、不再当独立叫法。
- **edge / 拓扑** = node 间的**二元**关系（边的 `satisfies`），与 where 正交。
- **动作动词（名词/动词分离）**：判断「event 够不够格当某 node」(一元) = **qualify**（资格判定）；判断「两个 event 关系成不成立」(二元) = **satisfies**（关系判定，`edge.satisfies` 真名）。名词用 where/edge，动词用 qualify/satisfies。
- **diagnose（node 诊断）/ trace（匹配 trace）** = 两个**调试视图**，**均同时含 where 与拓扑**（diagnose 的 `rel` 节、trace 的 `edge_results`），只指面板、勿用来指"条件"；diagnose 为 per-node 局部，trace 为 per-完整匹配。

## 2. 协议地基（path2/core.py · runner.py · stdlib/）

> 何时读：动 Event/Detector 协议、事件身份/去重、stdlib 便利层时。

| 术语 | 含义 |
|------|------|
| event | 多级不可变事件：`Event`（ABC，`@dataclass(frozen=True)`），公共字段 `event_id`/`start_idx`/`end_idx`，容器字段一律 tuple |
| 点事件 / point event / spot | 几何上单 bar 锚定的 event：`start_idx == end_idx`。现役：bo / dist。沟通口头亦称 **spot**（前端渲染语境常用；等价于 point event）。**注**: 几何 isPoint 是 event runtime 派生属性, 同 detector 不同 event 实例可能跨 isPoint 与否(如 `BurstEvent` 单元素退化、`TrendSegment` 末段退化), 因此不宜直接当渲染分流键; 渲染分流靠 node 级声明 `NodeSpec.render_grid`(见第 7 节) |
| span 事件 / span event / span | 几何上跨多 bar 的 event：`start_idx < end_idx`。现役：burst / trend / platform / tb / match。语义上是"区间"事件(regime / 平台段 / 可买入窗口 / pattern 命中跨度等)。沟通口头简称 **span** |
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
| node | `NodeSpec`：形态的节点 = node 唯一键 `node_id` + 生产者 detector + where + `consumes_stream` + label；所有节点绑单 Event（dag/ 是单 Event 引擎，无区间绑定） |
| edge | node 间类型化二元关系（`DependencyEdge` 六子类：`TemporalEdge`/`ContainmentEdge`/`StartContainmentEdge`/`OverlapEdge`/`EqualsEdge`/`NegationEdge`），引擎只经 `satisfies`/`feasible_window`/`signature_fields` 多态消费 |
| where | 节点一元谓词（`(clause_id, fn)` 列表，**列表项间恒 AND**）；签名 `(Event) -> bool`（纯一元、无运行时上下文对象，`MatchContext`/`ctx` 已删）；跨节点/二元约束不走 where、归边的 `satisfies`；OR 写进单条 clause 内部（`W.any`），绝不拆成平级 clause |
| W.* | where 便利层工厂：**叶子** `attr` / `child` / `children` + **组合子** `all` / `any` / `not_`（可任意嵌套布尔式，如 `all(any(A,B), C)` = `(A\|B)&C`）。均返回 `_Pred`（带 `.meta` 递归携子结构 + `.measure` + `.children` + `.witness` 递归产 `ClauseWitness` 树，富诊断的机制源头）；`all`/`any` 遮蔽内置（`# noqa: A001`）、`not_` 尾下划线因 `not` 是关键字。`W.children(key, agg)` 的 `agg` 接受用户自定义 lambda（无内置 seq 聚合工厂；与组合子 `W.any` 无关的旧同名 seq `any` 已归档） |
| satisfies | 边的二元关系判定（动词真名 `edge.satisfies`）；求解器复核口径为 `edge.satisfies(src_ep, dst_ep) and edge._anchor_ok(src_ep, dst_ep)` 复合 AND |
| qualify | 资格判定（动词）：event 过某 node 的 where |
| qualified | qualify 的状态形容词：event 在某 node 下已通过全部 where clause。前端 Level 三档中间档名（matched/qualified/detected）；集合 `qualifiedIds = ⋃_node {全 clause satisfied 的 event}`（详见 [path2_web.md](modules/path2_web.md) 前端） |
| anchor_field / anchor_src_field | `DependencyEdge` 基类字段：表达"dst 端 anchor_field 等于 src 端 anchor_src_field"的身份引用约束（典型 use case：dst 显式标注它绑回某个 src 实例）。`anchor_src_field=None` 默认 `'event_id'`；`anchor_field=None` 时 `_anchor_ok` 恒 True（字节等价旧行为）。`PatternSpec._validate_anchor` 校验字段名在两端 event_cls 上存在 + 拒 `anchor_src_field='start_idx'/'end_idx'`（引导改用 EqualsEdge 走结构剪枝） |
| Child selector | 边端点选择器 `Child(node, key)`：外层边连复合事件的内部端点（如 `Child("burst","first_bo")`），求值期经 `endpoint()` 投影到子事件；selector 不参与边身份（spec 校验/WCC 构图仍只看纯 str）。详见第 4 节 |
| 流源 | 只为产流给他人消费（被 `consumes_stream` 指向）的孤立无边 node（如 bo）；其单 node 残缺 match 被 `analyze` 出口过滤丢弃，判据从 `spec.edges` 自动推 |
| PatternSpec | 声明容器：`pattern_id` + nodes + edges + root + event_styles 等；`__post_init__` 五类校验（`_validate_node_ids`/`_validate_dag`/`_validate_detector_dag`/`_validate_where_clauses`/`_validate_anchor`）；`to_topology()` 零派生直投面板数据 |
| solve | `_solve.py::solve(plan, streams)` = 唯一求解函数。语义：枚举所有满足 dag 约束的绑定（`_dfs` 回溯）+ 按 leaf event 跨 prefix 去重（reachable-leaves always-on）。`use_memo / collapse / memo_mode` 是差分测试参数；production 默认 `collapse=False, memo_mode='charitable'`。历史命名/分发开关已归档（见第 8 节） |
| reachable-leaves | leaf event 跨 prefix 去重：`solve()` 顶层初始化 `emitted_leaves: dict[node_id, set[stream_idx]]`（跨 WCC 共享，因不同 WCC 的 leaf node_id 不重叠），`_dfs` 内 cands 过滤掉 `i ∈ emitted_leaves[v]`，emit 时把 `assign` 内所有 leaf 节点的 `chosen_idx` 入集。同一 leaf event 至多 emit 一次（不论多少 prefix 能绑到它）|
| plan.leaves | `Plan` 字段（`compile_plan` 计算）：所有"无正向出边"的节点集合（`NegationEdge` 不算正向）。供 c1_off 第 4 源 + `solve()` 初始化 `emitted_leaves` 双重复用 |
| WCC | 弱连通分量：约束图按边连通切块求解，跨 WCC 拼接而非笛卡尔展开 |
| INV-C | 剪枝健全命脉：求解期剪枝只能基于 `feasible_window` 的单调结构字段（进 `signature_fields`）；`satisfies` 里读的非单调/身份属性绝不能进剪枝，否则漏匹配。所有边设计、C1 塌缩、新边类型决策都受此红线约束（`path2/dag/edges.py`） |
| C1 塌缩 | 求解期候选合并剪枝（`_signature.py::collapse_equal_end_keep_keymin`）：把"对下游剩余可行域影响等价"的候选合并成 `(start_idx, end_idx, stream_pos)` 字典序最小的代表——无 selector 出边按父 `end_idx` 分组（退化路径，与历史字节等价）；含 selector 出边按所有出边 `(src_selector, signature_field)` 并集的值向量做复合分组键。健全充要条件 = 分组键 ⊇ 所有出边判定依赖字段 |
| c1_off | 节点级 C1 关闭名单（`compile_plan` 维护）。**5 源总表**：(1) `EqualsEdge.src`（window 把 start 钉死非单调）；(2) `dst_selector` 非 None 入边的 dst（satisfies 看 child 端点）；(3) 含 `src_selector` 的 `NegationEdge.src`（signature_fields 为空、C1 学不到 child 端点）；(4) `plan.leaves`（出边为空的叶子，同 end 桶不能塌缩、reachable-leaves 兜不住的局部丢点）；(5) `anchor_field` 非空边的 src（anchor 边 signature_fields 为空、C1 学不到 src 身份）。改 C1/c1_off 必须 fuzz |
| match / 物化 | 求解命中后 `reify` 物化为 `PatternMatch`（class_id=`match`，携 `node_index` + `children` + `predicate_trace`） |
| node_index | match 内 node_id → 绑定 Event（单 Event 一对一，无 tuple 形态）的映射；`children` 为其平铺镜像（按 start 升序） |

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
| diagnose | per-node 健康检查（`diagnose() -> NodeDiagnostics`）：坐标轴是 **node 不是 event**（event 级失败归因 ill-defined）；含 `AttrRow`（where 各 clause）+ `RelRow`（关系伙伴）；单 node 局部视图，通过≠能凑成完整匹配 |
| trace | per-完整匹配的判定记录（`PredicateTrace`）：`where_results`（node_id → {clause_id: `ClauseWitness`}，satisfied+实测+阈值）+ `edge_results`（(src,dst) → `EdgeWitness`，两端实例+实测量）。`ClauseWitness` 6 字段（satisfied/measured/op/threshold/`label`/`children`）；组合子 witness 递归成树（`children` = 子 witness 元组），产 witness 时全量求值不短路（`or` 首支已真也算第二支实测值）；无 aggregate（B0 整改归档） |

### 5.1 漏检 4 入口

> 何时读：讨论"为啥这个 event / 这条关系没匹配上"、动 `/diagnose?scope=` 或 `DetailSidebar` 里 4 张 miss cards 时。

| 术语 | 含义 |
|------|------|
| attempt | detector 一次"试图产 event"的判据评估单位，三档边界：**点事件** = 一个 bar 一次（BODetector 逐 bar）；**簇事件** = 一个簇一次（BurstDetector chain_break + 尾部收束）；**触发式** = 一次外部触发一次（ThrowbackDetector 每次 `evaluate_throwback` 调用）。"attempt 数"不是"event 数" —— 大部分 attempt 都短路失败 |
| failure_event_window | attempt 判据评估**实测轨迹**的 `(start_idx, gate_idx)`：点事件 = `(i, i)`（start==end）；跨度事件 = `(attempt_start, gate 触发所在 bar)`。**不是**"若成功会覆盖的窗口"、**不是**"detector 内部 lookback"。入口 A 用这个字段判定 attempt 是否"完全落在用户框内" |
| evaluation_lookback | detector 内部判据依赖的历史窗（如 ATR / rolling 极值窗）：仅 tooltip 展示，**不**参与"框内"判定。判据只看当前 bar / attempt 内部数据时填 None |
| outside_frame_attempts_count | 跨界 attempt（一头进框一头出框、或 attempt 反过来包住整个框）不进入口 A 主列表，只报个总数，供"要不要扩时段"判断 |
| 入口 A / B / D / E | 漏检 4 入口固定索引 —— A=时段 brush 查失败 attempts（`scope=time`）/ B=拓扑点边查 miss_reasons 分布（`scope=nodes`）/ D=shift+click 两个 event 查为啥没连（`scope=pair`）/ E=CLI workflow `scripts/path2/scan-top-miss.py` 批量 markdown 排序 |
| Caveat | Response 上挂的诚实降级提示：`{code, message, affected_fields}` 明示"哪块数据没接上、为什么"。前端顶部显示提示条,不 crash |
| stub | 入口 D 非法 pair（无边 / 只 negation / 同 node 等 5 因）时 payload 落 `{stub:true}`；前端据此显示"这对不合法"提示，不走 subcheck 展示 |

## 6. 应用层（path2_apps/）

> 何时读：动具体走势声明（当前唯一应用 bottom_burst）时。

| 术语 | 含义 |
|------|------|
| bo / breakout | 突破事件（class_id=`bo`）：滑窗 peak 识别 + 单点突破；在 bottom_burst 中是孤立流源 node，喂 burst（聚合）与 tb（回踩锚点） |
| drought | bo 属性：距上次 BO 的 bar 间距（稀疏度），首 BO 为 None（语义"无前序"，非"未知"） |
| burst | 连续突破串（class_id=`burst`）：`BurstDetector` 消费 bo 流、按"段首+span 内吸纳+极大段贪心"切串，每段聚合成复合宽事件 `BurstEvent`（携 members + 预算标量 count/distinct_pk/max_vol_ratio/first_drought） |
| tb / throwback | 突破后可执行整理买窗(class_id=`tb`):Phase 1 confirm(K-bar trough-age + stop signal)+ Phase 2 outcome ∈ {rise, break, timeout};`ThrowbackDetector` 是事件壳(`consumes_stream='bo'`);**事件存在 ⟺ Phase 1 confirm 成功**(confirm 前 anchor break / rise-before-confirm 不产) |
| trend segment | 三态走势区段（class_id=`trend`）：`TrendSegmentDetector`（SMA per-bar 变化 + hysteresis）切 df 为 down/sideways/up 连续区间流；`regime` = 三态标签、`drawdown` = 区段振幅 |
| platform | 窄幅震荡平台段（class_id=`platform`）：非重叠贪心扫窗 |
| distribution / dist | 高位派发单 bar（class_id=`dist`）：放量阴线 + 长上影 |

## 7. path2 度量（path2/eval.py）

> 何时读：讨论 match 买点的收益/方向指标（forward_return / 首次穿越）时。

| 术语 | 含义 |
|------|------|
| 前瞻收益 / forward_return / mfr | match 买点后窗口的**最大上行幅度**（max forward return；scan 的 `forward_return` 字段即此）。含波动率（幅度里含风险）→ 量的是盈利潜力。与「首次穿越」正交：一个量幅度、一个量方向 |
| 首次穿越 / first_passage / FP | 简称 **FP = first passage**，**勿与 false positive（假阳性）混淆**——「median 和 FP」指收益中位数与首次穿越方向指标，不是假阳性占比。match 买点后窗口内价格**先触上行线还是下行线**的方向度量（剥离波动率）。几何对称阈值：上行 `P(1+kM)` / 下行 `P/(1+kM)`（对数距离相等 → 无方向波动 ratio 钉 0.5、偏离即真 drift，不是阈值偏置）；波动率尺度 `M = ATR/close 的 nanmedian`（中位数扛异动，内算与判定同 bar 口径、无前瞻）。`ratio = up/(up+down)`，分母**不含** none（未触任一线）/ both（同根双向）。单参数 k，scan 链路可调，默认值见 `path2/eval.py::DEFAULT_FP_K`。机制 why 详见 [modules/path2.md](modules/path2.md)「first_passage」节 |

## 8. Web UI（path2_web/ · path2_web_ui/）

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
| bracket / matched marker       | match（pattern 命中）的时间跨度可视化：每个 match 一条灰色横带 + 圆圈序号 `①..⑨`（`renderBracket` chart.ts），`bracketData[i]` 携带 `match_id`(=match.event_id) + `value=[start_idx, end_idx, lane, ordinal]`；lane 由 `packBrackets`(geometry.ts) 按 start 全局排序后 packLanes 跨 match 防重叠；ordinal ①..⑨ 全局唯一作为 match 的 join key（多 match 重叠时消歧）。当前渲染在 grid0 顶部、`yAxisIndex:1`（隐藏 bracket 轴）；2026-06-30 agent team 调研已规划移到 grid1 顶部与 node band 行垂直对齐（见 `docs/research/2026-06-30_path2-web-match-event-correlation/`） |
| level                          | 全局显示档位旋钮：matched/qualified/detected 三档，统一控 K 线 + sidebar 的显示天花板（与 node 显隐正交） |
| detected ⊇ qualified ⊇ matched | 事件三档可追溯深度（tier）：detected = 全集（浅灰）⊇ qualified = 过该 node 一元 where（深灰，数据自预取 diagnose）⊇ matched = 进 match（node 本色） |
| 拓扑图/拓扑面板                       | `TopologyControl`：pattern 的 DAG 图 = node 控制器（单击节点 toggle 该 node 显隐、双击拉 per-node 诊断） |
| 诊断侧栏/Sidebar                   | `DetailSidebar`：漏斗总览（每 node 一行 detected▸qualified▸matched 计数 + 候选对比表）+ per-match trace；流源 node 渲染独立密度徽标、移出漏斗 |
| 漏斗行 / funnel row               | sidebar 里每 node 一行的三档计数条（detected▸qualified▸matched）+ 展开箭头；click 走 `toggleExpandedNode`（add/remove、不折叠其他）；流源 node（`isolated`）独立渲染"原始检测 N"密度徽标、不进漏斗、不可展开 |
| 候选对比表 / node table             | 某 node 漏斗行展开后就地显示的详情表：每 event 一行、每 where clause 一列（叶子单元格 = `实测 (op 阈值) ✓/✗`；组合子单元格 = `n/m(kind) ✓/✗` + 悬停 title 递归明细）；行按 tier 着色；与 K 线 marker 双向选中联动 |
| manualExpandedNodes            | `view` store 里的 `Set<string>` 状态：记录哪些 node 被手动展开（可同时多 node、语义分层）；切数据源清空；手动展开入口 = sidebar 漏斗行 click / `TopologyControl` 节点双击 |
| 双向高亮                           | K 线 marker ↔ sidebar 候选行点击互选联动（`selectedEventId` 跨视图） |
| 锚 pattern vs `activePatternId` | 多 pattern UI 的两个正交状态：**锚 pattern** = `SidebarResultList` 排序 / 命中股筛选的键（例如"按 bo 命中数排"），只影响左栏列表；**`activePatternId`** = 右侧 `ChartArea` 当前渲染的 pattern（例如 `bbb`），只由 `ChartArea` dropdown 显式切换。命名极像但语义正交 —— 单元格点击**只切股不切 active pattern** |
| 临时计算                           | path2_web 单股侧链路：用当前 `params.yaml` 即时算一只选中股，**不落盘**、不入扫描结果文件，专为"改 yaml 立刻看效果"的调参循环。代码层 = `preview` / `previewEnabled` / `runPreview` / `/preview`；UI 中文统一**临时计算**——模式名「临时计算模式」/「临时计算已启用」，动作「临时计算一次」/「重算当前股」，数据「临时计算结果」。与"扫描结果"(`scanFile.results`，落盘、全集)对照；K 线/拓扑/where 阈值勾选时优先取临时计算结果（`effectiveAnalysis` / `effectivePattern` / `effectiveScan`），取消勾选回退到扫描结果。复选框 UI label = "用 yaml 临时计算"；刷新按钮 ↻ tooltip = "重算当前股(yaml 改过后用)" |
| chip / 参数模式 chip | `ParamsChip`：参数模式的两态指示 + 开关，是**视图轴**入口（A/B toggle）。灰 = 浏览 snapshot / 绿 = 探索 Working Copy + 白点 ●（副本≠snapshot）；点文本切换"图表用不用副本重算"（`wc.enabled` 的唯一写者）；内嵌 ✎ 开/关**参数面板**（填充蓝随抽屉开关、与灰/绿模式色正交）。详见 [path2_web.md](modules/path2_web.md)「参数探索」节 |
| 参数面板 / 参数编辑抽屉 | `WorkingCopyDrawer`：编辑某 pattern 参数的抽屉（monaco diff：锚只读 vs 编辑区可编辑 + 六按钮 Write Copy / Reset / Save / Save As / Load Copy / Clear Copy）。是**内容轴**入口——只改 Working Copy 副本、绝不碰 chip 的 `enabled`；由 chip 的 ✎ 开关。按钮 enable 判据在纯函数层 `paramsEditorState.ts`（monaco 无关、可测） |
| Working Copy / WC | 某 pattern 参数的可编辑副本（`currentDict`）；两轴解耦的核心对象——**内容轴**（参数面板 Write Copy 改副本内容）与**视图轴**（chip 决定图表用不用副本）正交。副本落 localStorage，刷新后不自动激活、以「休眠草稿」banner 提供恢复。**未 Write Copy 的编辑区缓冲不持久化。** 详见 [path2_web.md](modules/path2_web.md)「参数探索」节 |

## 9. BreakoutStrategy

> 何时读：参考前身突破选股流水线（基本不用）时。本节不细分。

| 术语 | 含义 |
|------|------|
| breakout / bo | 突破点（价格有效穿越阻力位的 K 线） |
| peak / pk | 凸点，即被识别的阻力位 |
| factor / level | 评分因子（`FACTOR_REGISTRY` 注册）/ 因子离散化档位 |
| trial | 挖掘流水线的一次参数组合实验 |
