# path2 框架架构意图

> 最后更新：2026-07-10
> 覆盖：`path2/`（协议地基 + dag 引擎 + atoms + calc + stdlib + eval + 漏检诊断底座）。
> 应用层见 [path2_apps.md](path2_apps.md)；web 调试/可视化见 [path2_web.md](path2_web.md)。
> **codebase 的主线功能**；独立事件表达框架，与 `BreakoutStrategy/` 零耦合。

---

## 定位

path2 把"股票形态"建模为**多级不可变事件**：事件是有类型的冻结数据行（frozen dataclass）；形态由"声明节点 + 声明类型化边"两步表达，不写命令式编排。引擎负责跑 detector、求解约束图、物化匹配；app 只 `build_pattern(params)` 后交 `analyze`。

设计脊梁是 **where（一元，节点）vs satisfies（二元，边）的正交分工**：where 读单实例自身属性（`drought>=THR`、`regime=="sideways"`），satisfies 读一对实例间关系（gap、包含、否定）。声明作者根本看不到命令式循环。

---

## 层次结构

```
path2/core.py    协议地基:Event(ABC,frozen) / Detector(Protocol) / class_id 注册表
path2/runner.py  run() 驱动 + 跨事件安全网(end_idx 升序 / event_id 单 run 唯一)
path2/config.py  RUNTIME_CHECKS 开关(set_runtime_checks)
path2/dag/       go-forward 唯一引擎:DAG 声明 + 约束求解 + 匹配物化 + per-node 诊断
path2/atoms/     走势-无关 L1 Detector 库(BO/Trend/Platform/Distribution/Throwback)
path2/calc/      纯数值函数(无 Event/Detector)
path2/stdlib/    span_id + BarwiseDetector 便利层(atoms 依赖)
path2/eval.py    走势-无关 match 买点 N 日前瞻收益(pattern 质量度量)
```

---

## 协议地基（core.py / runner.py）

`Event`（ABC，`@dataclass(frozen=True)`）：公共字段 `event_id` / `start_idx` / `end_idx`。frozen 容器字段一律 tuple（防 list in-place mutate 突破 frozen），`__post_init__` 在 RUNTIME_CHECKS 下校验区间合法 + 禁 NaN（"Row 落地 = 字段完成"）。

`Detector`（Protocol）：`detect(source) -> Iterator[Event]`。`run(detector, *source)` 透传给 detect——按调用处传 1 个（df）或 2 个（上游流, df）source。可选 `on_gate: Optional[Callable[[GateFailure], None]]` 属性作 attempt 短路失败上报钩子（漏检诊断底座）；声明置于 `TYPE_CHECKING` 守卫内避免破坏 `runtime_checkable` 结构检查（现有 conforming class 无需显式带 on_gate），生产路径默认 None 零开销，诊断层挂 collector 时在实例上覆盖。

### 身份与去重（取代旧 event_type，三处正交机制）

1. **class_id（类型身份）**：`Event.class_id` 是 `ClassVar[str]`，子类必须覆盖为非空全局唯一值。`__init_subclass__` 在类定义期校验非空 + 入 `_CLASS_ID_REGISTRY` 查重（冲突即抛）。class_id 是面板上色、`to_topology`、summary 计数、序列化的唯一类型键。值：`bo` / `burst` / `trend` / `platform` / `dist` / `tb` / `match`。
2. **source_tag（实例身份）**：event_id 前缀，默认 None → 回退 class_id；event_id 经 `span_id(source_tag or class_id, start, end)` 生成。当同一 class_id 有 **≥2 个独立 detector 实例**（如某走势让 down / side 各持一个 `TrendSegmentDetector`）时，引擎 `assign_auto_source_tags`（`run_streams` 顶部，analyze 与 diagnose 共用）按 nodes 首现序给未显式命名者自动填 `f"{class_id}{i}"`（trend0 / trend1），使前缀不撞。单实例 / 共享实例 / 已显式命名的**不动** → event_id 向后兼容、幂等。多实例化要求该 detector 暴露 `source_tag` 钩子（无钩子又多实例 = 抛）。
3. **双层去重（流共享）**：同一 detector **实例**喂多个 node_id（共享一个对象、非多实例化）时，引擎按两键去重保证 event_id 全局唯一——`run_streams` 按 `(id(detector), consumes_stream)` 只物化一遍流（多 node_id 指向同一 list）；`AnalysisResult.events` 按 `id(stream)` 去重平铺。`AnalysisResult.__post_init__` 断言 events 的 event_id 无重复。

---

## dag 引擎（path2/dag/）

dag/ 是 **Kleene-free 单 Event 引擎**：所有节点绑单 Event，求解期无区间绑定 / 串聚合 / 双端点签名。子结构聚合统一走"复合事件"路径（detector 直接把子序列封成宽事件）。Kleene 历史代码完整归档至 `docs/legacy/kleene/`，供未来"段聚合判据需读外层 node 字段"场景参考复活。

### 节点：NodeSpec（nodes.py）

`NodeSpec` = node 唯一键 `node_id` + 生产者 `detector` + 节点级一元谓词 `where`（`(clause_id, fn)` 列表 AND 合取）+ `consumes_stream`（None = 从 df 产流；填 node_id = 消费该上游流，如 throwback 吃 bo 流）。同一 detector 类型可用不同 node_id 承担不同 node。class_id 由 `detector.event_cls.class_id` 取。`WherePredicate` 签名严格 `(Event, MatchContext) -> bool`（无 tuple 形态）。node_id 即前端显示名（无独立 display label 字段）——起名按"用户面板上要看到的英文标签"定（短、可读：`bo` / `burst` / `tb`）。

**铁律**：where 谓词严禁读 `ctx.bound`（跨节点）。引擎剪枝期用 `_TRIPWIRE` 哨兵替换 bound，违规立即抛。

### 复合事件（嵌套，表达"段聚合"的唯一现役路径）

把"一段子结构"绑成单元参与外层 DAG 的方式：让 detector 直接把子结构聚合成**一个复合宽事件**。例：`BurstDetector` 消费 bo 流、切极大段、产 `BurstEvent`（`start=首成员 / end=尾成员`，携 `members` tuple + 预算标量 `count/distinct_pk/max_vol_ratio/first_drought`）。复合事件实现 `child(key)` / `children(key)` / `child_slots()` 暴露内部结构。这样"一串 bo"在图里就是**一等宽事件**：where 读预算标量（聚合属性，与单实例同式、零特例）；外层边经 `Child` selector 连其串首 / 尾 bo。收益＝把"相对子成员的代价"类约束表达成普通边、绕开 node 展开（指数爆炸）。

### 类型化边（edges.py）

边是 DAG 骨架，src→dst 同时定义拓扑序 + 引擎前沿推进 + 面板箭头方向。六个子类，引擎只通过 `satisfies / feasible_window / signature_fields` 多态消费（零边类型分支，新增关系 = 加子类）：

- `TemporalEdge`：dst 在 src 结束后 `gap∈[min,max]` 内开始（`strict=True` ⇒ next 语义：窗内无更早同类 dst，bind-time 校验）
- `ContainmentEdge`：src ⊇ dst（大→小规范方向，dst 整体被包含）
- `StartContainmentEdge`：只约束 dst.start ∈ src 区间（dst.end 不限）——宽 dst 落入 src 的 match-preserving 包含（如 side ⊇ burst.start）
- `OverlapEdge`：dst 从 src 内部起、延伸到 src 之后
- `EqualsEdge`：区间完全相等（引擎对其 src 关 C1 等-end 塌缩，否则漏匹配）
- `NegationEdge`：src 锚定窗口内禁止满足条件的 dst（satisfies 语义反转，全称量词消费；dst 不进 node_index，只作约束）

**端点 selector `Child(node, key)`**（服务复合事件）：边的 src/dst 可填 `Child("burst","first_bo")` 而非裸 node_id，表示"取该节点所绑复合事件的 `child(key)`"参与 satisfies。`__post_init__` 把 Child 归一化为 `(dst="burst", dst_selector="first_bo")`——spec 校验 / WCC 图构建仍只看纯 str（selector 不参与边身份），求值期才经 `endpoint()` 投影到子事件。让外层边连复合事件的内部端点（串首 / 尾 bo），无需展开成员为 node。

**anchor 字段**（基类 `DependencyEdge` 持有）：`anchor_field` / `anchor_src_field` 表达"dst 端某身份字段 == src 端某身份字段"的引用约束（典型 use case：`anchor_field="anchor_to_src"` 让 dst 必须显式指回某个 src 实例）。`_anchor_ok(src_ep, e_dst)` 在求解器 satisfies 复核处与几何 `satisfies` 复合 AND；`anchor_field=None` 时恒 True（字节等价无 anchor 旧行为）。`anchor_src_field=None` 默认 `'event_id'`。

### where 便利层 W.*（where.py）

四个工厂（`attr` / `all` / `child` / `children`），均返回 `_Pred`——一个 callable `(x, ctx) -> bool`，**额外带 `.meta`（kind/field/op/threshold）+ `.measure(x, ctx)`（实测值）**。这是富诊断的机制源头：`_solve`/`_reify` 把它当普通 lambda 调（零感知），但 reify 与 diagnose 读 `.measure` 产实测对照、serialize 读 `.meta` 产静态规则串。None 属性安全返回 False（与旧 app `x is not None and x op thr` 同短路语义）。组合子 `all` 无单一阈值，`meta=None`。

`W.children(key, agg)` 把 `event.children(key)`（tuple of child Events）传给 `agg` 谓词——`agg` 可以是用户自定义 lambda（path2 不再提供 seq 聚合工厂，原 `W.distinct/W.any/W.count` 等已归档；如需 children 聚合判据请用自定义 lambda 或在 detector 阶段算成预算标量）。

### 声明容器 PatternSpec（spec.py）

`PatternSpec` = `pattern_id` + `nodes` + `edges` + `root` + `event_styles` + `stock_list_columns`。`__post_init__` 五类校验：DAG（root/边端点在 nodes、Kahn 无环）、`consumes_stream` 引用合法、where `clause_id` 同 node 内唯一（跨 node 可重名）、`_validate_anchor`（anchor_field 在 dst event_cls 上、anchor_src_field 在 src event_cls 上 + 拒单调坐标 start_idx/end_idx，引导改用 EqualsEdge 走结构剪枝）。pattern_id 即前端显示名（无独立 display_name 字段）。

`to_topology()` 零派生直投 nodes/edges 为 `PatternTopology`（`TopoNode` 字段 `node_id/class_id` 两项；`TopoEdge.kind` = 边子类名）。面板与 serialize 据此渲染。`eq_src_nodes()` 供引擎对 EqualsEdge 的 src 关闭 C1 塌缩。

### 引擎入口（engine.py）

`analyze(spec, df, params) -> AnalysisResult` 四阶段：① detector 编排（`run_streams`：顶部 `assign_auto_source_tags` 自动消歧 + 按 `consumes_stream` 拓扑序跑流，含上述双层去重）② `compile_plan` 编约束图 ③ `solve(plan, streams, ctx)` 求解（单函数,无 next/any 二选一）④ `reify` 物化 PatternMatch。**出口过滤**：丢弃"node_index 只含孤立无边 node"的残缺 match——孤立 node（无任何边、自成单元素 WCC、每候选一解）通常只为产流给他人消费的**流源**（如 bo 喂 burst / tb），不该自成匹配；判据从 `spec.edges` 自动推（无需流源标记）。`matches()` = 命中数 > 0。

### 求解器（_solve.py）

`solve(plan, streams, ctx)` = 唯一求解入口。语义：枚举所有满足 dag 约束的绑定（`_dfs` 回溯）+ 按 leaf event 跨 prefix 去重（reachable-leaves always-on：`emitted_leaves: dict[node_id, set[stream_idx]]` 跨 WCC 共享）。`use_memo / collapse / memo_mode` 是差分测试参数；production 默认 `collapse=False, memo_mode='charitable'`。

**`compile_plan` 的 `c1_off` 5 源总表**（在这些节点上禁用 C1 等-end 塌缩，否则漏匹配）：
1. `EqualsEdge.src`：window 把 start 钉死、非单调（漏匹配 reviewer §6.2 验证）
2. `dst_selector` 非 None 入边的 dst 节点：satisfies 看 child 端点而非父端点
3. `NegationEdge.src` 且 `src_selector` 非 None：negation 读 child 端点但 signature_fields 为空、C1 学不到
4. 出边为空的叶子节点（`plan.leaves`）：同 end 桶内多 leaf 候选不能被 C1 塌缩（reachable-leaves 兜不住的局部丢点）
5. `anchor_field` 非空边的 src 节点：anchor 边 signature_fields 为空、C1 学不到 src 身份在 satisfies 中参与（机理同 NegationEdge.src_selector 关 C1）

`_dfs` 内 satisfies 复核 = `edge.satisfies(src_ep, dst_ep) and edge._anchor_ok(src_ep, dst_ep)`（几何 + anchor 身份合取）。

### 结果与诊断（result.py / diagnose.py）

`AnalysisResult`：`events`（所有节点流去重平铺，含未命中中间事件）+ `matches` + `spec`（供面板）。

`PatternMatch`（继承 Event，class_id="match"）：`node_index`（`node_id → Event`，单 Event 一对一）+ `children`（node_index 平铺、start 升序，node_index 的冗余镜像）+ `predicate_trace`。`__post_init__` 断言 `list(node_index.values())` 集合 == `children` 集合。

`PredicateTrace` 富诊断：`where_results`（node_id → {clause_id: `ClauseWitness`}）+ `edge_results`（(src,dst) → `EdgeWitness`）。`ClauseWitness` 字段 satisfied/measured/op/threshold，`__bool__` == satisfied（向后兼容旧 `if where_results[nid][cid]`）。`EdgeWitness` 留两端实例 + 实测量。

`diagnose(spec, df, params) -> NodeDiagnostics`（per-node 健康检查，web 调试用）：坐标轴是 **node 不是 event**——event 级"失败归因"因 where 多值 + 求解短路 path-dependent 而 ill-defined，故按 node 独立诊断"哪些候选能当这个 node、卡在哪条 where"（`AttrRow` 属性）+ "找不找得到关系伙伴"（`RelRow` 关系）。复用 `run_streams` 产流，**不碰 _solve 求解核心**；单 node 局部，通过不代表能凑成完整匹配。

`_rel_rows` 逐正向入边跑 `satisfies + anchor + strict` 三关复核（承硬伤 B：单看 satisfies 不够，dst 还须真锚定该 src；strict=True 时还须为窗口内第一个同类候选）；未通过 src 按 `_worst_gate` 由近及远（`gap_out → anchor_mismatch → strict_fail`）取代表原因 + 抽样 ≤5 条 `example_failed_pairs`。NegationEdge 跳过（全称量词、单点视角无独立诊断入口）。

### 漏检诊断底座（gate_failure.py）

per-node 诊断的补充数据源，供 [path2_web.md](path2_web.md) 时段入口消费；**只在诊断路径挂 collector 时启用**，生产路径零开销。

- **`GateFailure`**（`dag/gate_failure.py`）：detector `on_gate` hook 上报的 attempt 短路记录。核心字段 `failure_event_window: (start_idx, gate_idx)`——**attempt 从起点到 gate 触发的实测轨迹**（点事件 `(i,i)`，跨度事件真实扫描到的 window）；入口 A 用它判定 attempt 是否完全落在用户框内。伴生 `evaluation_lookback` 仅 tooltip 展示，**不**参与该判定。`measured: MeasuredKindAware(kind, value, label)` 用 kind 字符串标签给前端 formatters 分派格式化，kind 为自由字符串（新 detector 可自造，前端无对应 case 走 default，不报错）。文件顶部 module docstring 附「on_gate 编写指南」，是新写 L1 Detector 时的入口。

---

## atoms 层（path2/atoms/）

走势-无关 L1 Detector 库。入库门槛：至少两条不相关走势会用，或表达单一通用物理事件。**形状偏见命名拒入**（`RoundedBottom` 等退到 path2_apps）。所有 Detector 内部状态不跨 detect 调用；Event frozen + 容器字段 tuple。BO / Burst / Throwback 三个 detector 内部 attempt 短路点已埋 `on_gate` hook（默认 None、生产零开销），供 web 漏检时段查询消费——三档 attempt 边界作参考：BO 逐 bar / Burst 每簇 chain_break + 尾部收束 / Throwback 每次 `evaluate_throwback` 触发。

- **BO**（class_id=`bo`，breakout.py）：滑窗 peak 识别 + 单点突破。`drought` = 距上次 BO 的 bar 间距，**首 BO 为 None**（语义即"无前序"，非"未知"）；`broken_peak_ids`(tuple) 供 distinct 计数；`vol_ratio` 基线不足时 None。继承 BarwiseDetector。
- **Burst**（class_id=`burst`，breakout.py）：`BurstDetector` 消费 bo 流（独立性原则：不 new BODetector），按"段首 + span 内吸纳 + 极大段贪心不回头"切串，每段聚合成一个 `BurstEvent`（复合宽事件，见上）。只切串 + detect 期算一次预算标量，阈值过滤交 burst 节点的 where。
- **Trend**（class_id=`trend`，trend.py）：SMA per-bar 变化 + hysteresis 平滑，切 df 为连续三态区间流（down/sideways/up），末段必 yield。`drawdown` = 区段振幅。唯一暴露 `source_tag` 的 detector。
- **Platform**（class_id=`platform`，platform.py）：非重叠贪心扫窗，窄幅震荡平台段。
- **Distribution**（class_id=`dist`，distribution.py）：高位派发单 bar（放量阴线 + 长上影）。
- **Throwback**（class_id=`tb`，throwback.py）：**设计判据**——throwback 只能以 BO 锚点推断、无法独立枚举，故核心是锚点谓词函数 `evaluate_throwback(bo, df, ...)`；`ThrowbackDetector` 是事件壳（`consumes_stream='bo'`，逐 BO 调用，仅 confirmed 产 `ThrowbackEvent`）。

---

## calc 层（path2/calc/）

纯函数计算库，无 Event/Detector，仅依赖 pandas/numpy，可被任意 atom/app 调用。覆盖：ATR（Wilder RMA）、MA 全家（均线/相对位置/ATR 归一 z 值/曲率/斜率）、单 K 线几何比例（上下影/实体）、量比、回撤恢复度、滚动振幅/标准差占比、突破后稳定性。

---

## stdlib 层（path2/stdlib/）

atoms 依赖的便利层：`span_id(kind, start, end)`（单点塌缩为 `kind_start`，区间为 `kind_start_end`）+ `BarwiseDetector`（逐 bar 单点扫描模板：模板拥有扫描主循环，子类只实现 `emit` 领域判据；lookback 子类自管，跨事件校验全留协议层 `run`）。

---

## 评估层（path2/eval.py）

走势-无关的 pattern 质量度量：`match_forward_returns(match, end_node, df, horizons) -> {n: 均值}` 按 end_node event 内逐买点日算 `close[t+n]/close[t]-1`，每 horizon 一项均值。**为什么放在 path2 层而不是 calc/**：calc/ 约定纯数值无 Event 依赖，本模块要碰 `PatternMatch.node_index`，故独立成模块。end_node / horizons 由调用方提供，path2 不知道任何具体走势。复用方：`path2_web/eval_runner.py`（设计期评估器三 mode）+ `path2_web/scan.py`（web UI 缓冲扫描的 label 注入）。

---

## 隔离约束

`path2/` 内任何文件零 `from BreakoutStrategy`（`tests/path2/test_self_contained.py` grep 强制）。
