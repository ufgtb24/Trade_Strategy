# path2 漏检调查工具 · 设计 spec

**版本**:2026-07-07 · 承 v3 final_report + brainstorm 多轮追问精化
**基础文档**:`docs/research/2026-07-06_path2-miss-detection-v3-scenarios/final_report.md`
**范围**:Path B 完整 · 5 入口 + 5 硬伤 · subagent-driven 单 session 跑
**执行策略**:(a) 硬伤先 · UI 诚实优先 · 按 v3 sprint_plan 排期

---

## 1. 上下文与目标

### 1.1 主诉

用户在 web UI 里按 pattern(锚 bo)排序股票 → 打开某支(如 DGNX 2025-08-01)→ 认为该股这段时间应该出 `bottom_burst` pattern → UI 上没检测到。想能**快速精确**回答:

- 为什么没检测到?
- 决策是"改 detector 参数 / 改 dag_spec"还是"设计正确、不改"?

### 1.2 五入口清单(承 v3 §5 + 本轮 brainstorm 精化)

| 入口 | 用户操作 | 主体 | 覆盖通道 | 数据源 | Sprint |
|---|---|---|---|---|---|
| **A · 时段** | K 线区框选 + event 类型下拉 filter | 时段 [A, B] + event class | ① detector gate | Stage 3 on_gate 采集 | 1.5 首版 · 2 完整 |
| **B · 拓扑降级** | 拓扑面板静态图 + 点 role edge | (src_role, dst_role) edge | ③ satisfies + ④ anchor 分布 | RelRow.miss_reasons | 1 |
| **C · 候选级** | K 线单点 marker | 单个 event | ② qualify + ③④⑤⑥ pair + ⑦ combine tail(唯一)| SolveTrace + PruneRecord.chosen_idx | 3 |
| **D · pair** | K 线 shift+click 两 marker(跨图)| (src_event, dst_event) | ③④⑤ pair 4 通道(排除 negation)| RelRow + strict_clear + anchor · **不依赖 SolveTrace** | 2 |
| **E · workflow** | 命令行 or UI 按钮触发 | 全宇宙大涨榜 | 跨股聚合 | 复用 scope=time | 3 |

**核心原则**:5 入口按用户操作**入口**排列(不按通道排),通道 7 项均有唯一入口覆盖(附 A)。

### 1.3 五硬伤清单(承 v3 §5.2)

| 硬伤 | 内容 | 修法 |
|---|---|---|
| **A · role.rel 前端零渲染** | 后端 JSON 里有 rel 数据,前端从未渲染;候选表 role 徽标 "入边 K/N ✓" 看不到 | shared 层 `RelBadge` 组件,3 消费点(候选表 / PredicateTrace / marker tooltip)统一消费 |
| **B · anchor_ok 未复核** | diagnose 层未调 `_anchor_ok`,anchor 不匹会虚报通过 | `diagnose.py:91-95` 补 `_anchor_ok` + `RelRow.anchor_ok_count` |
| **C · 跨节点 clause 静默产错值** | 引用兄弟 role 属性的 clause 会静默 fallback 到错值 | `_TripWire` sentinel(引擎)+ `fn.meta.refs_other_role: bool`(stdlib · UI 提前诚实降级)· 缺一不可 |
| **D · multi-value where 扁平化** | 数组类型的 measured 显示成扁平数字 | shared `fmtValue` 加 Array 分支 |
| **E · reify measured 硬编码 gap** | `_reify.py:56` 硬编码 gap 值 + 前端硬编码 "gap=" 前缀 · 未来非-gap 判据会精确骗人 | `EdgeWitness.measured` 改 kind-aware dict;前端按 kind 分色 |

### 1.4 分层原则(元层 / 类层 / 对象层)

- **类层**(dag_spec):role / edge 关系是抽象类关系;拓扑面板节点 = role 类
- **对象层**(具体扫描结果):具体 event / pair 是对象;漏检调查主体永远在对象层
- **拓扑面板降级为类层入口** = 静态图 + 点 role edge 打开该类下**对象层** pair 表(不染色 · 染色属于批量筛选,归入口 E)
- **入口 A/C/D 直接在对象层**;入口 B 是"类作过滤器打开对象列表"

---

## 2. 引擎侧改动

### 2.1 Stage 0 · `path2/dag/diagnose.py` 四处补丁

| 项 | 位置 | 改法 | LOC |
|---|---|---|---|
| **0.1** anchor_ok 复核(硬伤 B) | `diagnose.py:91-95` `_rel_rows` 生成 rel 前 | 每候选 pair 生成前调 `_anchor_ok(u_event, v_event, edge_ok_map)`;不通过则不计入 `ok_src_ids` | ~4 |
| **0.2** `RelRow.anchor_ok_count` | `RelRow` 数据类 | 加 `anchor_ok_count: int` + `_rel_rows` 累计 | ~30 |
| **0.3** `_TripWire`(硬伤 C 兜底) | `diagnose.py:43` `ctx.bound` 换 `_TRIPWIRE` sentinel | 跨节点 clause 读到 sentinel 抛显式 `CrossNodePendingError`,不 fallback 到静默错值;调用方捕获后走 caveats | ~5 |
| **0.4** `RelRow.miss_reasons + example_failed_pairs`(入口 B 分布数据源) | `RelRow` 数据类 + `_rel_rows` 累计 | 加 `miss_reasons: dict[str, int]`(gap_out / anchor_mismatch / strict_fail / negation_violated)+ `example_failed_pairs: list[tuple]` 抽样 3-5 条 | ~120 |
| **0.5** `AnalysisResult.dropped_matches + DroppedMatch` | `path2/dag/result.py` | 记录被 `isolated_consumed` post-filter 淘汰的 match 快照(承接 v2 P3 撤后遗留 · UI 诚实提示)| ~15 |

**依赖**:0.1 是 0.4 的前置(anchor 先复核,`miss_reasons` 才诚实)。

### 2.2 Stage 1 · `path2/debug.py` · ContextVar `current_symbol`

```python
# path2/debug.py
from contextvars import ContextVar

current_symbol: ContextVar[str | None] = ContextVar('current_symbol', default=None)

def set_current_symbol(sym: str | None) -> None:
    current_symbol.set(sym)
```

**用途**:
- driver 里 `if current_symbol.get() == 'DGNX': breakpoint()` 条件断点
- Stage 3 on_gate 采集 `GateFailure.symbol` 字段
- 日志前缀

**path2_web ProcessPool worker 起始 set,任务结束 reset**(避免污染下个任务)。

**LOC**:~40 / 半天。

### 2.3 Stage 2 · `path2/dag/_solve.py` · SolveTrace + PruneRecord

**目的**:入口 C 候选级 rejection_chain 数据源;唯一暴露通道 ⑦ combine tail。

**核心结构**:
```python
@dataclass(frozen=True)
class PruneRecord:
    assign_snapshot: dict[str, str]      # 当前 DFS 上下文 · role_id → event_id
    chosen_idx: str                       # ★ 反查关键 · 当前决策的 event_id;后端按此过滤 · <5 LOC
    pair: Optional[tuple[str, str]]      # (src_event_id, dst_event_id);combine tail 时 None
    edge_id: Optional[str]               # combine tail 时 None
    prune_reason: str                    # PruneReason 枚举
    stage: str                           # 'qualify' / 'satisfies' / 'anchor' / 'strict' / 'negation' / 'combine'
    measured: MeasuredKindAware | None
    threshold: Any | None

@dataclass
class SolveTrace:
    records: list[PruneRecord]           # DFS 时序追加
```

**埋点**:`_solve.py:216-278` 9 处(每次 pair 判定 / 每次剪枝 / 每次组合失败)· 短路时唯一责任 stage 记录。

**PruneReason 枚举**:9 种 · `gap_out` / `anchor_mismatch` / `strict_fail` / `negation_violated` / `window_infeasible` / `no_downstream_candidate` / `all_branches_fail_combine` / `qualify_where_fail` / ...

**memo 强制关**:diagnose 请求走 no-memo 路径(避免 trace 有缝);常规 analyze 保持 memo。

**chosen_idx 反查**(engine Q2 · <5 LOC 增量):后端拿 `candidate_event_id`,O(1) 过滤 `[r for r in trace.records if r.chosen_idx == candidate_event_id or (r.pair and candidate_event_id in r.pair)]`;支撑入口 C 与入口 D。

**LOC**:~200(SolveTrace + PruneRecord)+ 5(chosen_idx)+ ~30(memo 关的 no-memo 分支) = ~235 / 2-3 天。

### 2.4 Stage 3 · Detector `on_gate` hook · GateFailure 契约

**目的**:入口 A · 时段查询数据源。

#### 2.4.1 GateFailure 结构(核心契约)

```python
@dataclass(frozen=True)
class GateFailure:
    failure_event_window: tuple[int, int]   # attempt 判据评估的实测时序区间 (start_idx, gate_idx)
                                            # 点事件 = (i, i);span 事件 = (start_idx, gate_idx)
    start_idx: int                          # attempt 扫描起点(判据评估起点,不含内部回望窗)
    gate_idx: int                           # gate 触发所在 bar(= failure event end 兜底)
    anchor_bar: int                         # class_id 语义锚
    class_id: str                           # 'bo' / 'burst' / 'tb'
    gate_name: str                          # 精确 gate 名(见 2.4.3 全枚举)
    measured: MeasuredKindAware             # kind-aware 结构(硬伤 E)
    threshold: Any
    evaluation_lookback: Optional[tuple[int, int]]   # 判据内部依赖的历史窗;不参与 ⊆ 判据 · tooltip 显示
    symbol: str                             # 从 Stage 1 ContextVar 读
```

**语义**:`failure_event_window` = "**attempt 判据评估从 start_idx 起、到 gate_idx 失败停,实际扫过的 bar 范围**" · 是**实测轨迹**,不是"若成功会覆盖"的估算。

**事件类型对齐**:点事件的 window 是点、span 事件的 window 是 span,与 detector 产 event 的类型严格一致。

#### 2.4.2 三 detector 具体填法

| Detector | 事件类型 | attempt 定义 | start_idx | gate_idx | anchor_bar | failure_event_window | evaluation_lookback |
|---|---|---|---|---|---|---|---|
| **BODetector** | 点 | 每 bar 一次 `emit(df, i)` | `i` | `i`(peak/breakout 判据触发所在 bar) | `peak_bar` 或 `i` | `(i, i)` 单点 | `(i - total_window, i - 1)` |
| **BurstDetector** | span | **一簇一次 attempt**(定义 A · 簇断链 or 流末尾结束时算一次;每 k 步不算) | `seq[head].start_idx` | 断链:`seq[k].start_idx`;min_bos:簇末 `seq[end].end_idx` | `seq[end].end_idx`(chain 尾) | `(start_idx, gate_idx)` span | None(判据只看簇内 bo) |
| **ThrowbackDetector** | span | 每 bo 一次 `evaluate_throwback(bo, df)`(不分阶段一/二 · 采解读 X 松对齐) | `bo.end_idx + 1` | 破位/timeout bar | `bo.end_idx`(触发 bo) | `(bo.end_idx + 1, gate_idx)` span | `(bo.end_idx - atr_window, bo.end_idx)`(ATR 依赖) |

**BurstDetector 关键**:代码原为流式扫描 · 无 per-attempt 边界 · spec 定义**一簇一次 attempt**(断链或流末尾结束时算);on_gate 埋点在断链和流末尾两处。

**ThrowbackDetector 关键**:采解读 X 松对齐 —— 一次 evaluate_throwback 调用 = 一次 attempt · 阶段一/二失败都用整个 attempt 的 window `(bo.end_idx + 1, gate_idx)`;不拆两 attempt phase。

#### 2.4.3 三 detector 的 gate name 全枚举

| Detector | gate_name | 触发条件 |
|---|---|---|
| BODetector | `peak_no_local_max` | 窗口内非最高实体上界 |
| BODetector | `peak_side_bars_insufficient` | peak 在前/后 min_side_bars 内 |
| BODetector | `peak_relative_height_insufficient` | 相对高度 < min_relative_height |
| BODetector | `peak_already_active` | peak 索引已在 active_peaks |
| BODetector | `no_active_peak_broken` | active_peaks 无一被突破 |
| BurstDetector | `chain_break` | 相邻 bo `start_idx - prev.start_idx > gap_max` |
| BurstDetector | `min_bos_insufficient` | 簇末 `k - head + 1 < min_bos` |
| ThrowbackDetector | `phase1_break` | 找止跌途中 `measure_at(i, support) < anchor` 破位 |
| ThrowbackDetector | `phase1_pullback_shortage` | 止跌确认但回落深度不达 |
| ThrowbackDetector | `phase1_no_trough_timeout` | 扫满未找到止跌确认 |
| ThrowbackDetector | `phase2_break` | 事件本体扫描破位 |

**注**:阶段二 timeout 是**成功产 tb**(end = start + max_window),不算失败,不吐 GateFailure。

#### 2.4.4 三 atom 埋点位置 + LOC

- `path2/atoms/breakout.py::BurstDetector.detect` L124-135(chain 断链 + min_bos 失败两处埋点)· ~80 LOC
- `path2/atoms/breakout.py::BODetector.detect + emit` L216-289(4 peak gate + no_active_peak_broken 埋点)· ~150 LOC
- `path2/atoms/throwback.py::ThrowbackDetector.detect + evaluate_throwback` L83-244(4 gate 埋点)· ~100 LOC

**总**:~330 LOC / 2-3 天。

#### 2.4.5 on_gate hook 协议

`path2/core.py::Detector` Protocol 加 optional attribute:

```python
class Detector(Protocol):
    on_gate: Optional[Callable[[GateFailure], None]]   # 默认 None
```

Detector 内部检测到 attempt 短路失败时:

```python
if getattr(self, 'on_gate', None) is not None:
    self.on_gate(GateFailure(...))
```

**默认 None** · 生产路径无开销;diagnose 层挂一个 collector 收集 buffer。

### 2.5 kind-aware `EdgeWitness.measured`(硬伤 E)

**改点**:`path2/dag/_reify.py:56` `measured` 字段生成。

```python
@dataclass(frozen=True)
class MeasuredKindAware:
    kind: str          # 'gap' / 'anchor_delta' / 'strict_clear' / 'negation_bars' / ...
    value: Any
    label: str         # 前端显示前缀 · 与 kind 一致

# 生成
def _make_measured(edge, u, v) -> MeasuredKindAware:
    if isinstance(edge, TemporalEdge):
        return MeasuredKindAware(kind='gap', value=v.start_idx - u.end_idx, label='gap')
    elif ... # anchor / strict / negation 分别处理
```

**净变化**:`EdgeWitness.measured` 从标量 → dict 结构;前端 3 消费点(候选表 / PredicateTrace / marker tooltip)按 `label` 显示,不再硬编码 `"gap="`。

**LOC**:~40 后端 + ~30 前端。

### 2.6 `fn.meta.refs_other_role`(硬伤 C 双落)

**stdlib 侧**:`path2/stdlib/where.py` fn.meta 加 bool:

```python
@dataclass
class WhereFnMeta:
    refs_other_role: bool = False
```

若 clause 引用兄弟 role 属性(未来 spec 可能引入),编译期标注为 True。

**作用**:与 Stage 0.3 tripwire **双落**:
- refs_other_role(编译期标注)· UI 提前诚实降级(候选表 cell 显 `⚠ pending` 图标)· 不等 tripwire 抛错
- tripwire(运行期兜底)· 防未来 spec 静默错值 · 抛 `CrossNodePendingError`

**LOC**:~10 stdlib + ~10 前端 tooltip。

### 2.7 strict / negation diagnose helper(pair 层独立评估)

**目的**:入口 D pair 查询 Sprint 2 完成 100% pair 层(不必等 Sprint 3 SolveTrace)。

**strict_clear**:代码已在 `_solve.py:137`,signature `(edge, a, e_dst, streams)` 无 assign 依赖 · **直接复用**。

**negation_clear**:代码已在 `_solve.py:153`,signature `(neg_edges, src_id, assign, streams)` 有 assign 但只用于查 src event · pair 查询直接传入 src_event 对象绕过 assign。

**新 helper**(`path2_web/diagnose.py`):
```python
def _check_feasible_window(edge, u, v) -> SubCheck: ...
def _check_satisfies(edge, u, v) -> SubCheck: ...
def _check_anchor(edge, u, v, edge_ok_map) -> SubCheck: ...   # 依 Stage 0.1
def _check_strict(edge, u, v, streams) -> SubCheck: ...        # 复用 strict_clear 逻辑
```

- 入口 D pair 查询直接调这 4 个 helper
- 入口 C rejection_chain 构造时也共用这 4 个 helper(避免代码重复)
- **negation 独立性技术上成立,但语义与 pair 结构错位**(§B 决定)· pair 层不做 negation
- ⑦ combine 只能靠 SolveTrace,pair 层不涉及

**LOC**:~80(4 helper + subcheck 结构)。

### 2.8 auto source_tag(承接)

- `path2/dag/roles.py::assign_auto_source_tags` 已在 run_streams 顶部按 class_id 派 · v3 不动
- 与本 spec 交互:`gate_events` / `pair_failures` / `rejection_chain` 都携带 `class_id`(非 `event_type`)· 前端按类分色

### 2.9 引擎侧汇总

| 阶段 | LOC | 天数 |
|---|---|---|
| 2.1 Stage 0 diagnose 补丁(4 项)| ~174 | 1 |
| 2.2 Stage 1 ContextVar | ~40 | 0.5 |
| 2.3 Stage 2 SolveTrace + PruneRecord | ~235 | 2-3 |
| 2.4 Stage 3 on_gate 三 atom + GateFailure | ~330 | 2-3 |
| 2.5 kind-aware measured | ~40(后端)| 0.5 |
| 2.6 fn.meta.refs_other_role | ~10 | 0.2 |
| 2.7 pair helper(subcheck)| ~80 | 0.5 |
| **合计** | **~909** | **6-8 天** |

---

## 3. 后端 · `path2_web/diagnose.py` 分派层

### 3.1 `derive_response(query)` 一入口

```python
def derive_response(query: Query) -> Response:
    """按 query.scope 分派;不新增 endpoint,继承 v2 /diagnose"""
    if query.scope == 'time':
        return _derive_time_response(query)
    if query.scope == 'roles':
        return _derive_roles_response(query)
    if query.scope == 'candidate':
        return _derive_candidate_response(query)
    if query.scope == 'pair':
        return _derive_pair_response(query)
    raise ValueError(f"unknown scope: {query.scope}")
```

**端点**:`GET /diagnose?scope=<time|roles|candidate|pair>&symbol=<sym>&...`(继承 v2 · 无新 endpoint)

### 3.2 四 scope 契约

#### 3.2.1 Query / Response 基础

```python
@dataclass
class Query:
    symbol: str
    scope: Literal['time', 'roles', 'candidate', 'pair']
    # time:
    start_bar: Optional[int]
    end_bar: Optional[int]
    event_class: Optional[str]        # 'bo' / 'burst' / 'tb' · filter · 缺省全返
    # roles:
    src_role: Optional[str]
    dst_role: Optional[str]
    # candidate:
    event_id: Optional[str]
    # pair:
    src_event_id: Optional[str]
    dst_event_id: Optional[str]
    edge_id: Optional[str]            # multiple_edges 场景选定 · 缺省时后端按第一条 edge 走

@dataclass
class Response:
    scope: str
    payload: Any                       # 每 scope 的 payload 结构不同
    caveats: list[Caveat]
```

#### 3.2.2 scope=time(入口 A)

**请求**:`GET /diagnose?scope=time&symbol=<sym>&start_bar=<A>&end_bar=<B>[&event_class=<cls>]`

**响应**:
```python
@dataclass
class TimePayload:
    frame: tuple[int, int]                      # (A, B)
    failed_attempts: list[GateFailure]           # 严格 ⊆ 判据通过的
    outside_frame_attempts_count: int            # gate_idx ∈ [A,B] 但 start_idx < A 的 attempt 数(span 事件才可能)
```

**筛选逻辑**:
```python
def _derive_time_response(query):
    all_fails = collect_gate_failures(query.symbol)
    filtered = [f for f in all_fails
                if _in_frame_strict(f.failure_event_window, (query.start_bar, query.end_bar))
                and (query.event_class is None or f.class_id == query.event_class)]
    outside = sum(1 for f in all_fails
                  if _has_outside_frame(f.failure_event_window, (query.start_bar, query.end_bar))
                  and (query.event_class is None or f.class_id == query.event_class))
    return Response(scope='time',
                    payload=TimePayload(frame=..., failed_attempts=filtered,
                                        outside_frame_attempts_count=outside),
                    caveats=collect_caveats(query))

def _in_frame_strict(fw, frame):
    ws, we = fw; fs, fe = frame
    return ws >= fs and we <= fe   # ⊆ 严格包含

def _has_outside_frame(fw, frame):
    ws, we = fw; fs, fe = frame
    return we <= fe and ws < fs   # gate_idx 在框内 · start_idx 溢出
```

**Caveat 触发**:
- Stage 3 未落 → `on_gate_hook_not_landed`(空 failed_attempts + 警示"检测器未接 hook · 等 Sprint 1.5")
- `outside_frame_attempts_count > 0` → `outside_frame_attempts_present`(前端 UI caveat 展示补救提示)

#### 3.2.3 scope=roles(入口 B)

**请求**:`GET /diagnose?scope=roles&symbol=<sym>&src=<src_role>&dst=<dst_role>`

**响应**:
```python
@dataclass
class RolesPayload:
    edge_id: str
    total_pair: int
    ok_pair: int
    miss_reasons: dict[str, int]                 # {gap_out, anchor_mismatch, strict_fail, negation_violated}
    example_failed_pairs: list[PairFailure]      # 3-5 条抽样
    per_pair: Optional[list[PairFailure]]        # 点边过滤时全量;拓扑默认 None
```

**依赖**:Stage 0.1 anchor_ok + Stage 0.4 miss_reasons + Stage 0.3 tripwire。
**Caveat**:
- 硬伤 B 未落 → `anchor_ok_not_complete`(miss_reasons.anchor_mismatch 显 `?`)
- 硬伤 E 未落 → `measured_not_kind_aware`

#### 3.2.4 scope=candidate(入口 C)

**请求**:`GET /diagnose?scope=candidate&symbol=<sym>&event_id=<eid>`

**响应**:
```python
@dataclass
class CandidatePayload:
    event_id: str
    class_id: str
    rejection_chain: list[RejectionStep]         # DFS 时序 · combine 若存在,尾部至多一条

@dataclass
class RejectionStep:
    stage: Literal['qualify', 'satisfies', 'anchor', 'strict', 'negation', 'combine']
    edge_id: Optional[str]                        # combine 时 None
    counterpart_event_id: Optional[str]          # combine 时 None
    measured: Optional[MeasuredKindAware]
    threshold: Any
    prune_reason: str
    # combine step 专属:
    attempts: Optional[int]                       # 累计 DFS 分支尝试次数
```

**combine tail 语义**:
- 不是"某次判据 fail",而是"该 candidate 所有 DFS 分支组合零解"
- 若 candidate 有其他判据 step,combine 仍可追加(表示"该判据 fail 之外还有别的分支也全 fail")
- 若 candidate 没任何判据 step 但组合零解 → rejection_chain 只有 combine 一条

**依赖**:Stage 2 SolveTrace + PruneRecord.chosen_idx。
**Caveat**:Stage 2 未落 → `solvetrace_not_landed`(rejection_chain 返 stub · 仅 qualify + rel-based satisfies/anchor;strict/negation/combine 缺席)。

#### 3.2.5 scope=pair(入口 D)

**请求**:`GET /diagnose?scope=pair&symbol=<sym>&src_event_id=<u>&dst_event_id=<v>[&edge_id=<eid>]`

**响应**:
```python
@dataclass
class PairPayload:
    src_event_id: str                             # 实际被当作 src 的 event(可能与用户第 1 击不同 · auto swap)
    dst_event_id: str
    applied_swap: bool                            # 若 True · 前端明示"顺序已自动切换"
    original_first_click: str                     # 用户第 1 击的 event_id · 撤回用
    original_second_click: str
    valid: bool
    invalid_reason: Optional[str]                  # 'same_role' / 'no_edge_between_roles' / 'only_negation_edge' / 'direction_mismatch_with_hint' / 'multiple_edges' / None
    edge_id: Optional[str]
    edge_kind: Optional[str]
    subchecks: Optional[list[SubCheck]]          # 合法时 4 通道 short-circuit
    hint: Optional[Hint]                          # direction_mismatch_with_hint / multiple_edges 时的引导

@dataclass
class SubCheck:
    channel: Literal['feasible_window', 'satisfies', 'anchor', 'strict']
    passed: bool
    measured: Optional[MeasuredKindAware]
    threshold: Any
    reason: Optional[str]                         # e.g. 'gap 超出 max'
```

**auto swap 逻辑**:
```python
def _derive_pair_response(query):
    u = load_event(query.src_event_id)
    v = load_event(query.dst_event_id)
    if u.role == v.role:
        return _invalid_pair(query, 'same_role')
    forward = find_edge(u.role, v.role, exclude_negation=True)
    reverse = find_edge(v.role, u.role, exclude_negation=True)
    if forward:
        return _check_pair(forward, u, v, applied_swap=False, original=(query.src_event_id, query.dst_event_id))
    if reverse:
        return _check_pair(reverse, v, u, applied_swap=True, original=(query.src_event_id, query.dst_event_id))
    if _only_negation_between(u.role, v.role):
        return _invalid_pair(query, 'only_negation_edge')
    return _invalid_pair(query, 'no_edge_between_roles')
```

**subcheck 短路语义**:合法 pair 跑 4 通道逐一判据,遇第一 fail 立即停,后续 subcheck 不评估(与 detector on_gate 一致)。前端呈现"栽在 X · 其余未评估"。

**依赖**:Stage 0.1 anchor_ok + strict_clear helper。全部 Sprint 2 完。

#### 3.2.6 Caveats 全枚举

| code | 触发条件 | UI 呈现 |
|---|---|---|
| `on_gate_hook_not_landed` | Stage 3 未落(Sprint 1 期)| 侧栏顶部黄条 "检测器未接 hook" |
| `anchor_ok_not_complete` | Stage 0.1 未落(硬伤 B)| 侧栏顶部黄条 + anchor 字段显 `?` |
| `cross_node_pending` | tripwire 抛 `CrossNodePendingError` 被后端捕 | 涉及 clause cell 显 `⚠ pending` 图标 |
| `measured_not_kind_aware` | Stage 2.5 未落(硬伤 E)| measured 显示回退 `"gap="` 前缀(过渡期)|
| `solvetrace_not_landed` | scope=candidate 但 Stage 2 未落 | rejection_chain 顶部黄条 "只显 stub · 完整依 Sprint 3" |
| `outside_frame_attempts_present` | 入口 A · span attempt gate 在框内 start_idx 溢出 | 卡片列表顶部条 "另有 N 个 span attempt 溢出 · 建议扩大框" |
| `evaluation_lookback_missing` | 入口 A · detector 未吐 lookback(P3 前默认)| tooltip 显 "参照历史 · 未记录" |

### 3.3 后端 subcheck helper 共用

见 §2.7 · `_check_feasible_window` / `_check_satisfies` / `_check_anchor` / `_check_strict` 四 helper 是 scope=candidate 和 scope=pair 共用:

- **scope=pair** 直接调 4 helper 产 subchecks[]
- **scope=candidate** 构造 rejection_chain 时,遍历该 candidate 涉及的所有 pair,调 4 helper 产 stage(satisfies / anchor / strict);qualify / negation / combine 另外拿(qualify 从 node.where 拿 · negation 从 SolveTrace 拿 · combine 从 DFS tail 拿)

### 3.4 后端汇总

| 项 | LOC | 天数 |
|---|---|---|
| `derive_response` + 4 _derive_*_response + Query/Response dataclasses | ~250 | 1 |
| subcheck helper(4 个)| ~80(§2.7 已算)| — |
| 现有 `/diagnose` endpoint 转调 | ~30 | 0.2 |
| **合计** | **~280** | **1.2 天** |

---

## 4. 前端 · `path2_web_ui/src/`

### 4.1 shared 层 · `formatters.ts` + 组件

**新增**:
```typescript
// path2_web_ui/src/shared/formatters.ts
export function fmt(val: any, kind: string): string {
    // 硬伤 E · kind-aware
    switch (kind) {
        case 'gap': return `gap=${val}`
        case 'anchor_delta': return `Δanchor=${val.toFixed(3)}`
        case 'strict_clear': return `strict候选=${val}`
        case 'negation_bars': return `禁区bars=${val}`
        default: return String(val)
    }
}

export function fmtValue(val: any): string {
    // 硬伤 D · 数组分支
    if (Array.isArray(val)) return `[${val.map(fmtValue).join(', ')}]`
    if (typeof val === 'number') return val.toFixed(3)
    return String(val)
}
```

**新组件 · `RelBadge.vue`**(硬伤 A · 消费 `role.rel`):
- 显示 "入边 K/N ✓" 徽标
- 3 消费点:候选表 cell · PredicateTrace row · marker tooltip

**新组件 · `PendingIcon.vue`**(硬伤 C · UI 呈现):
- 显示 `⚠ pending` 图标 + hover title
- 触发:where clause 有 `refs_other_role: true` 或响应 caveat `cross_node_pending`

**LOC**:~40 前端。

### 4.2 `KlineChart.vue` 增强

四种交互 · 承接 memory `KlineChart.vue:181-198` shift+wheel 已占用 · shift+click 未占用:

| 交互 | 触发 | 目标 endpoint |
|---|---|---|
| **入口 A** · 框选时段 | 主图 brush 拖出矩形 · 释放 | `GET /diagnose?scope=time&start_bar&end_bar[&event_class]` |
| **入口 C** · 点 marker | 主图 bo 三角 or 副图 burst/tb band 单击 · 无 shift | `GET /diagnose?scope=candidate&event_id` |
| **入口 D** · shift+click 两 marker | 主图/副图 marker + `shiftKey` 累积 2 击(跨图统一) | `GET /diagnose?scope=pair&src_event_id&dst_event_id` |
| **V1 D0 driver** · 右键 | 主图 contextmenu | 弹菜单 → 复制 driver 脚本 |

**统一 shift+click 累积逻辑**:
```typescript
const shiftSelectedEvents = ref<Array<{event_id: string, class_id: string, source: 'main' | 'sub'}>>([])

function handleShiftClick(event_id: string, class_id: string, source: 'main' | 'sub') {
    if (shiftSelectedEvents.value.length < 2) {
        shiftSelectedEvents.value.push({event_id, class_id, source})
        if (shiftSelectedEvents.value.length === 2) {
            const [src, dst] = shiftSelectedEvents.value
            triggerPairQuery(src.event_id, dst.event_id)
        }
    } else {
        shiftSelectedEvents.value = [{event_id, class_id, source}]  // 第 3 击清空重来
    }
}
```

**跨图**:主图 bo marker click + 副图 span band click 都调 `handleShiftClick` · 无主/副之分。

**视觉反馈**:选中 event(不管主/副图)统一以金色 stroke 2px 高亮描边;第 2 击触发请求前视觉切换 loading 状态。

**乐观预判**(入口 D):shift 累积到 2 个后,前端**本地判合法性**(读 dag_spec 副本):
- 若 `same_role` → 直接弹提示、不发请求
- 若 `no_edge_between_roles` + 有反向 edge → 直接发反向请求(略去 auto swap 后端逻辑)· 更快
- 若合法 → 发正向请求

**LOC**:~200 前端。

### 4.3 `TopologyControl.vue` 降级

**保留**:静态类关系图 · 点节点 selectRole(现有)
**新增**:点 role edge → 调 `GET /diagnose?scope=roles&src&dst` → 侧边 `PairListCard`(入口 B)
**不做**:染色 / 失败率视觉(fork 决定撤;染色错位到单股 UI)

**LOC**:~40 前端。

### 4.4 `DetailSidebar.vue` · 5 卡片壳

**候选表 cell 消费**:`fmt` / `fmtValue` / `RelBadge` / `PendingIcon`(shared 层)

**5 张卡片切换 slot**(以 activeCard state 控制):

| 卡片 | 入口 | 数据源 | 呈现 |
|---|---|---|---|
| `FailedAttemptsCard` | A | scope=time payload | 每 attempt 一张子卡 · header 显 `[class_id · failure_event_window · overlap 徽标]` + 栽在 gate + measured / threshold + trigger_bar 逃逸副标;顶部 outside_frame 提示条 |
| `PairListCard` | B | scope=roles payload | miss_reasons 分类图 + example_failed_pairs 点击深钻(链路 2) |
| `RejectionChainCard` | C | scope=candidate payload | 按 stage 分组渲染(qualify / satisfies / anchor / strict / negation / combine);combine 灰色卡尾部 · 显 "尝试 N 次全 fail" |
| `PairDetailCard` | D | scope=pair payload | 4 subcheck 逐条 + edge kind 头 + valid/invalid_reason + hint(direction_mismatch 切换按钮 / multiple_edges 下拉)+ applied_swap 提示条 + 撤回 |
| `PredicateTrace` | 现有 | 未改 | — |

**caveats 顶部条**:遍历 `response.caveats` 渲染警示行(黄条 + code 图标)

**dropped_matches 提示区**(承接 v2 P3 撤后):"这些 marker 属于被消费的 role · 当前 pattern 未触发"

**LOC**:~450 前端(5 卡片 + caveats + dropped_matches)

### 4.5 前端汇总

| 层 | LOC |
|---|---|
| shared/formatters + RelBadge + PendingIcon | ~40 |
| KlineChart.vue 增强(brush + shift+click 跨图 + click marker + 右键)| ~200 |
| TopologyControl.vue 降级 | ~40 |
| DetailSidebar.vue 5 卡片 + caveats + dropped_matches | ~450 |
| **合计** | **~730 前端 LOC / 4-5 天** |

### 4.6 交互一致性(硬性 · 承 memory 教训)

- **主图不横向滚动**:各卡片用 `overflow-x: auto` 局部滚(承 web-loop v2 教训)
- **min-width: 0 + ResizeObserver**:避免宽表撑坏 grid 列(承端到端实证 df0799d 教训)
- **class_id 分色一致**:tooltip / marker / rel 徽标 / rejection chain 卡片头共用 `getColorByClassId(class_id)` helper

---

## 5. 契约汇总(承 §3.2)

见 §3.2.2 - 3.2.6 · 已展开每 scope Query/Response schema · 此处仅索引。

**Endpoint**:
- `GET /diagnose?scope=time&symbol&start_bar&end_bar[&event_class]`(A)
- `GET /diagnose?scope=roles&symbol&src&dst`(B)
- `GET /diagnose?scope=candidate&symbol&event_id`(C)
- `GET /diagnose?scope=pair&symbol&src_event_id&dst_event_id[&edge_id]`(D)

**Workflow(E)**:命令行 `python scripts/scan-top-miss.py --start=YYYY-MM-DD --end=YYYY-MM-DD --min-pct=30` 触发,内部复用 scope=time · 输出 markdown 榜。

---

## 6. 测试策略

### 6.1 引擎侧 golden

- **Stage 0.1 anchor_ok**:选 bottom_breakout_burst spec + 已知股 · 手工标 5-10 组 pair 的 anchor 判定 · 引擎侧改后 golden 断言 anchor_ok_count 与手工一致
- **Stage 0.4 miss_reasons**:单元 · mock RelRow 输入 · 断言分类计数正确
- **Stage 3 GateFailure**(三 atom):每 detector 每 gate name 至少一条 golden pytest,e.g.:
  ```python
  def test_burstdetector_chain_break_emits_gate_failure():
      bos = [make_bo(90), make_bo(105)]   # gap=15 > gap_max=10
      detector = BurstDetector(gap_max=10, min_bos=2)
      captured = []
      detector.on_gate = captured.append
      list(detector.detect(bos, df=...))
      assert len(captured) == 1
      assert captured[0].gate_name == 'chain_break'
      assert captured[0].failure_event_window == (90, 105)
      assert captured[0].start_idx == 90
      assert captured[0].gate_idx == 105
  ```
- **Stage 2 SolveTrace + PruneRecord**:memo 关的对拍 · 单元 · 已知 DFS 路径的 assign 序列 golden

### 6.2 后端单元 + 契约

- `derive_response` 四 scope 分派 · 每 scope 至少 2 case(正常 + caveat 触发)
- `_in_frame_strict` / `_has_outside_frame` 边界 case:`fw = (A, A)` 单点在框首 / `fw = (B, B)` 单点在框尾 / `fw = (A-1, B)` outside / `fw = (A, B+1)` overflow
- `outside_frame_attempts_count` 计数正确
- 4 subcheck helper 独立单元:每 helper 至少 3 case(pass / fail / edge case)
- `_derive_pair_response` auto swap 逻辑:正向 / 反向 / 双向 / no edge / same role · 至少 5 case

### 6.3 前端单元 + 交互

- `shared/formatters` · `fmt(val, kind)` 4 kind × 3 case = 12 case;`fmtValue` 标量 / 数组分支
- `FailedAttemptsCard` render · 每 attempt 一张 · overlap 徽标 3 色 · outside 提示条 · evaluation_lookback tooltip
- `PairListCard` render · miss_reasons 分类图 + example_failed_pairs 点击触发 pair 深钻
- `RejectionChainCard` render · 6 stage 分组渲染 · combine 灰色卡尾部
- `PairDetailCard` render · 4 subcheck · applied_swap 提示 · 撤回按钮
- shift+click 累积 · Vue Test Utils · 第 1 击 → src 高亮 · 第 2 击 → 触发请求 · 第 3 击 → 清空 · 跨图(主图 marker + 副图 marker 交叉)
- caveats 顶部条 · 每 code 至少一 render 单元

### 6.4 e2e(承 memory df0799d 教训 · playwright 系统 chromium + 主分支数据)

- **DGNX 走通**:开 web UI → 加载 DGNX → 框 2025-08-01 前后 30 bar → 侧栏 `FailedAttemptsCard` 出 BurstDetector chain_break attempt · 截图存 `docs/superpowers/e2e_screenshots/`
- **入口 B 点边**:选 pattern → 拓扑图静态渲染 → 点 `burst→tb` edge → 侧栏 `PairListCard` 出 miss_reasons 分布
- **入口 C 单点**:点 burst band → `RejectionChainCard` 全命运
- **入口 D shift+click**:shift+主图 bo marker + shift+副图 burst band → `PairDetailCard` 4 subcheck
- **入口 D auto swap**:蓄意点反顺序 → 卡片提示"已切换"+ 撤回按钮
- **入口 E workflow**:命令行 `python scripts/scan-top-miss.py` → 输出 markdown 榜 → 手工核对含至少 3 支已知漏检股(如 DGNX)
- **playwright --workers=1**(承 memory subchart e2e 教训 · 避免 race)

### 6.5 硬伤修补验证(每硬伤 pass/fail 双 case)

- 硬伤 A:一 case 前端 rel 徽标渲染 · 一 case 后端 rel 数据缺失时 fallback
- 硬伤 B:一 case anchor 破位被过滤 · 一 case anchor 正常通过
- 硬伤 C:一 case tripwire 抛错 · 一 case refs_other_role 前端降级图标
- 硬伤 D:一 case 数组 measured 完整展示 · 一 case 标量 measured 兼容
- 硬伤 E:一 case gap 判据 label 显 "gap=" · 一 case anchor 判据 label 显 "Δanchor="

---

## 7. Sprint 排期与 task 顺序

按 (a) 硬伤先 · UI 诚实优先 · 与 sprint_plan.md 对齐:

### 7.1 Sprint 1 · 短期 1-2 天(~75% 覆盖率)

**shared 层硬伤修补**:
- 抽 `shared/formatters.ts` + `RelBadge` + `PendingIcon`(硬伤 A/D + 骨架 C)
- DetailSidebar 候选表消费 shared 层(硬伤 A/D 生效)
- caveats 顶部条渲染骨架 + dropped_matches 提示区

**引擎地基**:
- Stage 0.1 anchor_ok(硬伤 B · 4 LOC)
- Stage 0.2 RelRow.anchor_ok_count(30 LOC)
- Stage 0.3 _TripWire(硬伤 C 兜底 · 5 LOC)
- Stage 0.4 RelRow.miss_reasons + example_failed_pairs(120 LOC)
- Stage 0.5 AnalysisResult.dropped_matches(15 LOC)
- Stage 1 ContextVar current_symbol(40 LOC)

**入口 B 降级**:
- TopologyControl 点 role edge → PairListCard(40 前端)
- 后端 `derive_response` 骨架 + `_derive_roles_response`(60 后端)

**里程碑**:硬伤 A/D 消除 · anchor_ok 完成 · role-subset 查询上线

**覆盖率**:~75%(硬伤 A/B/D 修 + 入口 B 降级完成)

### 7.2 Sprint 1.5 · 可选插队 1-2 天(~80%)

若 BurstDetector 静默是主诉(DGNX 类):
- Stage 3 BurstDetector on_gate 首版(80 LOC 引擎 + GateFailure 结构)
- 入口 A 首版(仅 BurstDetector · 100 前端 + 60 后端 scope=time 分派)

**退出条件**:K 线框选 → 立刻看到 BurstDetector 在哪根 bar 哪条 gate 失败

### 7.3 Sprint 2 · 中期 3-5 天(~90%)

**Stage 3 三 atom on_gate 完整**:
- BurstDetector(若 Sprint 1.5 未做)+ BODetector + ThrowbackDetector = 3 atom
- GateFailure 结构收敛(failure_event_window / anchor_bar / evaluation_lookback / gate_name 全枚举)
- ~250 LOC 引擎(增量)

**入口 A 完整**:
- 三 detector 混合响应 + severe filter(event_class 下拉)
- outside_frame_attempts_count 补救 UI
- ~150 前端 + ~80 后端 增量

**入口 D 完整**(Sprint 2 100% pair 层):
- Stage 2.5 kind-aware measured(硬伤 E · 40 后端 + 30 前端)
- fn.meta.refs_other_role(硬伤 C stdlib · 10 + 10 前端)
- strict/negation diagnose helper 之 strict(80 LOC · 复用 `_solve.py:137 strict_clear`)
- 后端 `_derive_pair_response` + auto swap + subcheck 4 helper(150 后端)
- 前端 KlineChart shift+click 跨图 + PairDetailCard(200 前端)
- 前端乐观预判(dag_spec 副本 + 本地合法性判)

**候选级 stub**(为 Sprint 3 准备):
- 后端 `_derive_candidate_response` stub(仅 qualify + rel-based · 无 SolveTrace)
- 前端 RejectionChainCard render(空 stage 时 caveat 提示)

**里程碑**:入口 A + D 完整 · 主诉核心场景全覆盖 · 硬伤 A/B/C/D/E 五项全修

**覆盖率**:~90%

### 7.4 Sprint 3 · 长期周级(~95%)

**Stage 2 SolveTrace + PruneRecord + chosen_idx**:
- 9 处埋点 · memo 强制关 no-memo 分支 · 235 LOC 引擎

**入口 C 完整**:
- rejection_chain 6 stage(qualify / satisfies / anchor / strict / negation / combine)
- combine tail meta-step 渲染
- PairListCard 内 example_failed_pairs 点击深钻链路 2

**入口 E workflow**:
- `scripts/scan-top-miss.py`(120 LOC)
- 遍历 pkls + 筛大涨无 match + 每候选跑 scope=time 聚合 + 输出 markdown 榜

**入口 C step 深钻链路 3**(可选):
- RejectionChainCard step 挑 counterpart → scope=pair 深钻

**里程碑**:5 入口全上 · 通道 ⑦ combine tail 可见 · workflow 每周挖矿

**覆盖率**:~95%

### 7.5 总投入估算

| 层 | LOC | 天数 |
|---|---|---|
| 引擎侧 | ~909 | 6-8 |
| 后端 | ~280 | 1.2 |
| 前端 | ~730 | 4-5 |
| Workflow (E) | ~120 | 0.5 |
| **合计** | **~2039** | **12-15 天** |

**subagent-driven task 数**:预计 28-35 task(每 task 60-80 LOC bite-sized 切,按 sprint 分节)

---

## 8. 硬性/弱依赖决策记录

### 8.1 硬性决策(brainstorm 已定 · 不可回退)

| # | 决策 | 依据 |
|---|---|---|
| **1** | 场景 2.5 独立为**入口 D**(pair 查询) · 不合并入 C 下钻 | 用户明确;shift+click 是核心痛点 |
| **2** | 入口 B 降级 = 静态图 + 点边过滤 · **染色撤销** | fork 结论 · 染色错位到单股 UI 无处发力;归入口 E 但 E 用 markdown 榜替代 |
| **3** | 入口 A 判据 = **failure_event_window 严格 ⊆ 用户框** | 用户论点 · 精确无估算 · 压缩搜索空间 · 对齐 band marker 直觉 |
| **4** | `failure_event_window` = "attempt 判据评估从 start_idx 起、到 gate_idx 失败停,实测扫过的 bar 范围" | 用户精化 · 实测而非估算 |
| **5** | 点事件 window 是点(BO)· span 事件 window 是 span(burst/tb) | 用户 · 类型对齐 |
| **6** | BurstDetector attempt = **一簇一次**(定义 A);Tb attempt = **一次 evaluate_throwback 整体**(解读 X 松对齐)| 用户 · 完整扫描视角调查漏检 |
| **7** | ~~`outside_frame_attempts_count` 补救 span 事件框窄场景~~ **⚠ REVOKED 2026-07-08** | fork · 避免"看似零 attempt"误导 · **与决策 #3 精准语义直接冲突,见 §8.1 尾追加说明** |
| **8** | shift+click 跨图统一(主图 bo marker + 副图 span band 都支持) | pair 常跨图 · 用户直觉 |
| **9** | 入口 D 方向:严格 src→dst 顺序 + 后端 auto swap + 前端明示 + 撤回 | UX 最省心 · 双向 edge 极罕见 |
| **10** | 入口 D pair 层判据 = ③④⑤ 三通道(不含 negation)| negation 语义与 pair 结构错位 · 归入口 C |
| **11** | 入口 D 数据源 = RelRow + Stage 0.1 + strict_clear helper · **不依赖 SolveTrace** | grep 代码验证 · Sprint 2 完可上 |
| **12** | 入口 C 保留完整版 · Sprint 3 与 SolveTrace 一起 | 用户选 (a) · 通道 ⑦ combine 唯一入口 |
| **13** | rejection_chain stage = 6 值(qualify/satisfies/anchor/strict/negation/combine) | v3 · combine tail 明标 |
| **14** | 三入口(A/C/D)独立 endpoint(scope=time/candidate/pair) · 不复用 | 契约清晰 · 内部 subcheck helper 共用 |
| **15** | (a) 硬伤先 · UI 诚实优先 · 按 sprint_plan 排 | CLAUDE.md · plan-execution.md · TDD |

> **⚠ 2026-07-08 · 决策 #7 REVOKED**:补救 caveat 把「设计上排除」标成「漏检 + 建议扩大框」,与决策 #3 精准语义直接冲突;另 `_has_outside_frame` 仅抓左溢出、不抓右溢出与两端全溢出,补救逻辑本身不对称。已删产品代码(`path2_web/diagnose.py::_has_outside_frame` + `TimePayload.outside_frame_attempts_count` + caveat emit + 前端 `outside-notice` UI)· 用户可见文档(`.claude/docs/modules/path2_web.md` / `docs/path2/miss-detection-guide.md`)同步。以下 10 处 spec 引用一并作废、不逐处编辑:L342 / L352-354 / L357 / L364-367 / L371 / L486 / L598 / L667(仅 `_has_outside_frame` 半句) / L668 / L675(仅 outside 半句) / L746。已完成 plan 文档(20 处 outside_frame 引用)是实施历史 · 不动。

### 8.2 弱依赖(可 P3+ 缓做)

- U-5 · K 线 near-miss marker(灰色三角)· 依 SolveTrace 收益边际 · P3+
- 跨节点 where 完整支持 · verdict §3.4 有意未支持 · 只加 tripwire + refs_other_role
- 入口 C 深钻链路 3(RejectionChainCard step → pair)· Sprint 3 或 P3
- 入口 E workflow UI 按钮(命令行首版 · UI 按钮 P3)
- `evaluation_lookback` tooltip 显示 · P3 补
- 入口 D `strict_direction_mode` 设置项(禁 auto swap)· P3+

### 8.3 明确不做(承 v2/v3)

- N1 · 全局摘要 banner · 无 actionable 价值
- N4 · 独立 `/diagnose_miss` endpoint · 扩现有 `/diagnose?scope=` 即可
- 拓扑面板染色(fork 决定撤 · §8.1 #2)
- pair 查询 negation 通道(归入口 C · §8.1 #10)

---

## 附 A · 通道 → 入口映射矩阵

| 通道 | A 时段 | B 拓扑降级 | C 候选级 | D pair | E workflow | shared 硬伤修补 |
|---|---|---|---|---|---|---|
| ① detect gate(S2b)| ✅ **唯一** | | | | 复用 A | |
| ② node.where(S4c) | | | ✅ | | | 硬伤 D / C |
| ③ satisfies(S4f.1)| | ✅ 分布 | ✅ 单 event | ✅ 单 pair | | 硬伤 A + E |
| ④ _anchor_ok(S4f.2)| | ✅ 分布 | ✅ 单 event | ✅ 单 pair | | 硬伤 B + E |
| ⑤ strict_clear(S4f.3)| | ✅ 分布(Sprint 3)| ✅ | ✅ 单 pair | | 硬伤 E |
| ⑥ negation_clear(S4g)| | ✅ 分布(Sprint 3)| ✅ | ❌ 归 C | | 硬伤 E |
| ⑦ DFS 组合级(S4h)| | | ✅ **唯一**(combine tail)| | | |

**验证**:7 通道均被至少一个入口覆盖;通道 ① 和 ⑦ 各有唯一入口 · 三阶段的两个盲区在 v3.1 场景清单中的落实。

---

## 附 B · 关键代码位置速查

| 主题 | 位置 |
|---|---|
| 引擎 6 阶段主线 | `path2/dag/engine.py::analyze` |
| Stage 3 on_gate 埋点 | `path2/atoms/breakout.py`(BurstDetector L124-135 + BODetector L216-289)+ `path2/atoms/throwback.py:83-244` |
| Stage 0 硬伤 B 修补 | `path2/dag/diagnose.py:91-95` 补 `_anchor_ok` |
| Stage 0 硬伤 C tripwire | `path2/dag/diagnose.py:43` `ctx.bound` 换 `_TRIPWIRE` |
| Stage 2 SolveTrace 埋点 | `path2/dag/_solve.py:216-278` 9 处 |
| Strict / Negation helper | `path2/dag/_solve.py:137 strict_clear` + `:153 negation_clear` |
| `derive_response(query)` 分派 | 新增 `path2_web/diagnose.py::derive_response` |
| shared 层硬伤修补 | `path2_web_ui/src/shared/formatters.ts` + `RelBadge.vue` + `PendingIcon.vue` |
| KlineChart shift+click | `path2_web_ui/src/components/KlineChart.vue:181-198`(shift+wheel 已占 · shift+click 未占) |

---

## 附 C · 引用文档

- `docs/research/2026-07-06_path2-miss-detection-v3-scenarios/final_report.md` — v3 三方 agent team 综合裁定
- `docs/research/2026-07-05_path2-miss-detection-v2-break-limits/final_report.md` — v2 · 五分类 P0-P4
- `docs/research/2026-07-05_path2-miss-detection-v2-break-limits/sprint_plan.md` — Path A/B 排期
- `.claude/docs/modules/path2.md` — path2 系统概览
- `.claude/docs/modules/path2_web.md` — path2_web 后端投影层
- `.claude/docs/modules/path2_web_ui.md` — path2_web_ui 前端渲染器
