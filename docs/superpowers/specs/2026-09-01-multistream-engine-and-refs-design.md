# 多流引擎扩展 + 引用协议（ref_slots）设计

> **日期**:2026-09-01 · **分支**:`pk_modify`(worktree `Trade_Strategy-tune_v1`)
> **状态**:设计定稿,待实施
> **触发背景**:pk 三态显示需求 → 三方案评估(研究 `docs/research/2026-08-31_pk-display-three-approaches/`)→ 用户倾向方案③(多流)→ 本 spec 定稿
> **参考**:`方案3_多stream引擎扩展.md`(17 处落点论证) · `docs/research/2026-09-01_multistream-tendency/多流引用翻译机制设计.md`(ref_slots 协议)

---

## 1 · 背景与动机

「一个 detector 只能产出一条流」是引擎现状的隐含等式:detector 实例 ≡ 一次 detect 调用 ≡ 一条流 ≡ 一个 node。

**该限制是实现产物,不是概念决策**(`方案3` §8.1 三条独立证据):

1. 物化键 `(id(detector), consumes_stream)` 与 `event_cls` 单值反射**随 `engine.py` 创建提交 `94e2193` 一起出生**,此后无任何 commit 论证或加固过它;
2. 全仓三条成文「铁律」里没有这一条;
3. 反向证据:`.claude/docs/modules/path2.md:47` 原文「**一个 detector 产多种事件、一个 attempt 因此自洽**」——框架架构文档早已认定多产出自洽。

**概念空间缺口**(`方案3` §8.2 四格分类):detector 副产物的四个格子——失败尝试→GateFailure、纯标量→事件字段、生命周期被主事件包含→children 嵌套、**有独立生命周期且无法被独立 detector 单独算出的**→❌缺失(第 4b 格)。本方案补这一格。

触发它的 pk 只是「发现」这个缺失的契机,不是这个能力的「证例」(格 4b 现有证例 = 0,连 pk 都不算)。**零证例不影响立项**(用户判据:「扩展性不是已有代码中被使用,而是理论上应该有」),但立项须写清,防止误读。

## 2 · 目标 / 非目标

**目标**:
- 允许一个 detector 在一个 detect 调用内产出**多条命名流**,各归各 node;
- 单流 detector 与现存全部 app **零改动、逐字等价**;
- 同源多流之间的事件引用,通过 `ref_slots` 协议在标注后精确解析成 instance_id;
- `NodeSpec.solve`(零边 pattern 的「只显示不参与匹配」声明)一并落地——见 §6;
- 关键性能属性:同一 detect 调用仍只跑一次(按需付费实测边际 **1.0156×**)。

**非目标**(明确不做,防 scope 膨胀):
- **pk 应用层**(三态显示、bo_only 的 eaten 空集、PeakEvent 几何)——后续 app 层独立 spec;
- **前端渲染改动**(精确 join、删 `/^pk(\d+)$/`)——属于「缺失 X」前端部分,延后;
- **`anchor_bo_id` 迁移**到引用协议——已核实它属「跨 detector 已解析引用」的 anchor_field 边协议,两类协议互补、不合并(见 §4.6.4)。

## 3 · 核心概念:流的身份单位下移一层

```
现状:detector 实例 ≡ 一次 detect 调用 ≡ 一条流 ≡ 一个 node(允许多 node 共享)

扩展:detector 实例 ─┬─ 调用 A: (det, consumes_stream=None) ─┬─ 流 "bo"   → node "bo"
                    │                                         └─ 流 "peak" → node "pk"
                    └─ 调用 B: (det, consumes_stream="x")   ─── 流 …
```

**三条不变量一条不动**:

| 不变量 | 说明 |
|---|---|
| 一个 node 恰好一条流 | 求解层/诊断层/渲染层全部假设建在这上面,零改动 |
| 一条流内事件同类型 | `NodeSpec.event_cls` 仍单值(从流 schema 反射) |
| 同一 detect 调用只跑一次 | 物化去重语义不变,仅缓存值形状变 |

**被打破的只有一条**:一次 detect 调用只能产一条流。

## 4 · 协议设计

### 4.1 Detector 侧:`produces` + `yield (流名, event)`

```python
# path2/core.py Detector Protocol
@runtime_checkable
class Detector(Protocol):
    if TYPE_CHECKING:
        on_gate: Optional[Callable[["GateFailure"], None]]
        produces: ClassVar[Mapping[str, type]]   # ★ 多流声明;单流 detector 不写
    def detect(self, source: Any) -> Iterator[Event]: ...

# 多流 detector 写法(单趟扫描内 yield 带流名)
def detect(self, df):
    peak = PeakEvent(...)
    yield ("pk", peak)          # 进 pk 流
    ...
    yield ("bo", BOEvent(..., broken_refs=(peak,)))   # 进 bo 流,且引用 pk 流事件
```

**硬约束**:`produces` 必须放在 `TYPE_CHECKING` 内。`runtime_checkable` 的 isinstance 会把 Protocol 里任何属性(哪怕带默认值)纳入必须项,直接声明会让未显式带该属性的 conforming class 判定失败(`core.py` 自己踩过并留了注释,见 `方案3` 2.A/A1)。

**API 形态取舍**(`方案3` §5.1):选「`produces` + `yield (流名, event)`」,否决 dict-of-streams(eager 全物化或 tee 缓冲)与显式多方法(两趟 = 1.80×,且状态跨调用存活违反「状态不跨 detect 调用」协议)。

### 4.2 NodeSpec:`produces_stream`

```python
consumes_stream: Optional[str] = None    # 输入:上游 node_id(不变)
produces_stream: Optional[str] = None    # ★ 输出:取本 detector 的哪条命名流;None = 唯一流
```

`__post_init__` 归一化:从 `stream_schema(detector)` 反射 `event_cls` 到 node 上(见 4.3)。子结构 node(produced_by 非空)的 `produces_stream` 必须为 `None`(加入死字段清单)。

### 4.3 `stream_schema` 归一化 —— 向后兼容的总闸门

```python
DEFAULT_STREAM = None          # 「该 detector 的唯一流」的流名

def stream_schema(det) -> Mapping[Optional[str], type]:
    produces = getattr(det, "produces", None)
    if produces:
        return dict(produces)
    cls = getattr(det, "event_cls", None)
    if cls is None:
        raise ValueError("detector 必须声明 event_cls(单流)或 produces(多流)")
    return {DEFAULT_STREAM: cls}
```

**默认流名 `None` 是整个兼容机制的支点**:`NodeSpec.produces_stream` 默认 `None`,于是每个现存 NodeSpec **不写一个字**就已正确选中唯一那条流。只有 `stream_schema` 和 `run_bundle` 两处知道存在两种形态,其余代码只看到统一的 `{流名: [Event]}`。

### 4.4 物化:`run_bundle` + `run_streams` 兄弟一次填完

```python
def _tagged(detector, *source):
    """统一线格式:单流 detector 的裸 Event 归一化成 (None, ev)。"""
    multi = bool(getattr(detector, "produces", None))
    for item in detector.detect(*source):
        yield (item if multi else (DEFAULT_STREAM, item))

def run_bundle(detector, *source) -> Dict[Optional[str], List[Event]]:
    schema = stream_schema(detector)
    out = {name: [] for name in schema}      # ★ 空流也存在(声明驱动,非产出驱动)
    # RUNTIME_CHECKS 下:未声明流名硬错 + per-stream isinstance 校验
    #                   + end_idx 升序 / 同 instance_id 无全等对象 按流分桶
    return out

def run(detector, *source) -> Iterator[Event]:
    """公开单流入口(签名/行为不变)。多流 detector 显式拒绝,不静默拍平。"""
```

**`run_streams` 主循环**(`path2/dag/engine.py:127-138` 改造):

```python
siblings = {}   # (id(det), consumes) -> [NodeSpec] 按声明序
for n in spec.nodes:
    if n.detector is not None:
        siblings.setdefault((id(n.detector), n.consumes_stream), []).append(n)

for nid in detector_topo_order(spec.nodes):
    node = by_id[nid]
    if node.detector is None or nid in streams:
        continue
    key = (id(node.detector), node.consumes_stream)      # ★ 键不变:detect 调用的身份
    if key not in materialized:
        src = () if node.consumes_stream is None else (streams[node.consumes_stream],)
        materialized[key] = run_bundle(node.detector, *src, df)
    bundle = materialized[key]
    for sib in siblings[key]:                   # ★ 同一调用的全部兄弟一次填完 + 立刻标注
        if sib.node_id in streams:
            continue
        if sib.produces_stream not in bundle:
            raise ValueError(f"node {sib.node_id!r}: detector 无流 {sib.produces_stream!r}")
        streams[sib.node_id] = bundle[sib.produces_stream]
        annotate_stream(counts, sib.node_id, streams[sib.node_id], children_of)
```

**要点**:
- **物化键形状不变**——「键管跑几次、下标管取哪条」。**不得**把 `produces_stream` 加进键(会让同一 detector 完整扫两遍 = 1.80×,毁掉方案理由)。
- **兄弟一次填完 + 按声明序标注**(B2 时序修复):兄弟之间无拓扑序,一次填完把顺序从「node_id 字典序偶然」变成「作者显式声明」,与 `children` 声明机制对齐。
- **对单流 app 观测等价**(论证 + 全量测试确证):单流下 `siblings[key]` 单元素或「多 node 共享同一 detector」,后者第二个 `annotate_stream` 因「已标注跳过」为 no-op,`streams[nid2]` 赋值时刻提前但不影响任何读点。

### 4.5 `on_gate` 归属协议

`GateFailure` 记录的是「一次没能诞生的事件」,它属于「那个事件本该进入的流」——发射点知道,引擎不猜。

**(a)** `GateFailure` 加带默认值字段 `stream: Optional[str] = None`(既有做法:追加字段带默认值 → 既有 kwargs 构造点全兼容,先例 `code_location`)。**现存所有构造点一行不改。**

**(b)** `attach_and_collect` 从 per-detector wrapper 改为 `(detector, 流名) → node_id` 路由表:

```python
routes.setdefault(id(node.detector), {}).setdefault(node.produces_stream, []).append(node.node_id)
# 收到 gf:nids = table.get(gf.stream)
#   None      → 该流未被本 pattern 绑定 → 丢弃
#   len > 1   → raise(挂雷保留,但收窄到「同一条流被多 node 绑定」)
#   否则      → collector.add(replace(gf, node_id=nids[0]))
```

**(c) 单流零影响**:`gf.stream` 恒 `None`、node 的 `produces_stream` 恒 `None` → 路由表 == `{None:[node]}` → 与今天 `make_wrapper(node.node_id)` 逐字相同。

**(d) 挂雷是严格放宽**:今天炸的条件「同一 detector 被 ≥2 node 引用」⊃ 改后「同一流被 ≥2 node 绑定」。原来会炸的照样炸,新放行的只有「绑同一 detector 的**不同**流」——那正是归属明确的情形。

**(e) 未绑流的 gf —— 挂载期校验,不静默丢弃**:生产扫描路径 `on_gate=None` 零开销零约束(按需付费不受影响);`attach_and_collect(spec)` 时(诊断路径)检查该 detector 声明的流里有没有未被任何 node 绑定的,有则立刻报错;兜底:若仍有 gf 携带未绑流名到达 router,`RUNTIME_CHECKS` 下 raise 而非 return。**理由**:静默的根源不是「允许不绑流」,而是「允许不绑流的同时还挂着 collector」,校验挂在两者同时成立那一刻。

**(f) 否决的替代**:`on_gate` 改成 per-stream 回调字典——要改 4 个 atom、20+ 处调用点和零开销默认值,而「哪条流」的信息无论如何都得从发射点来,加带默认值字段是承载它的最小载体。

### 4.6 引用协议 `ref_slots`(同源多流引用翻译)

**4.6.1 问题**:instance_id 在整条流 run 结束、`annotate_stream` 之后才分配。跨 detector 引用(不同 run)上游已标注,detect 期直接读(例 `tb_v1.anchor_bo_id = last_bo.instance_id`);**同源多流引用(同 run)谁都没标注,detect 期读不到**。

**4.6.2 机制**:detect 内部用**事件对象引用**作临时索引,引擎在全部流标注完成后统一翻译成 instance_id。

```python
# core.py —— Event 基类,与 child_slots() 同构
def child_slots(self) -> Mapping[str, Event | Tuple[Event, ...]]:
    """子事件槽位(标注归属)。默认空。"""
    return {}

def ref_slots(self) -> Mapping[str, Tuple[Event, ...]]:
    """引用槽位(翻译身份)。默认空。"""
    return {}

class BOEvent(Event):
    broken_refs: Tuple[Event, ...] = ()
    def ref_slots(self):
        return {"broken": self.broken_refs} if self.broken_refs else {}

class PeakEvent(Event):
    eaten_refs: Tuple[Event, ...] = ()
    def ref_slots(self):
        return {"eaten": self.eaten_refs} if self.eaten_refs else {}
```

**4.6.3 翻译时机:统一标注 + 统一翻译(两阶段)**,否决「标注过程中翻译」(同次 run 产所有流,run 结束前一条没标注,不存在边标边翻起点;且隐含「被引用对象先标」顺序约定,双向/同流引用无解)与「逐流分别标注再翻译」(同流/双向引用有先手问题)。

```
阶段1(标注):对 {流名: [events]} 逐流 annotate_stream(现状逻辑,不翻译)——即 §4.4 run_streams
            的兄弟一次填完 + 立刻标注,分散在循环内
阶段2(翻译):循环结束后统一扫描所有流的 ref_slots(),obj → obj.instance_id;写入 {槽名}_ref_ids
```

**挂载点**:阶段2 是 `run_streams` 全部循环之后、`_check_children_declarations` 之前的一个独立步骤;单流 detector 的 `ref_slots()` 恒空 → 无操作、零行为变化。

- **零 dag_spec 声明**:翻译惰性,`ref_slots()` 为空则无操作。比 children 更纯粹——被引用事件自己就是流里的独立事件、身份已存在,引用只是「A 指回 B」,不需要配任何新归属。
- **健壮性**:引用到事件池外对象(`ref.instance_id is None`)→ 报错(detect bug,不静默);空引用 → 无操作;同流/双向引用 → 统一翻译覆盖。

**4.6.4 与现有引用协议的关系(两类,互补不合并)**:

| | anchor_field 边协议(现状) | ref_slots 事件协议(本设计) |
|---|---|---|
| 层级 | 边级(TemporalEdge + `_solve` B4) | 事件级(事件类声明 + 引擎翻译) |
| 被引用物物化状态 | 已解析(跨 detector,交错标注已给) | 待解析(同源未标注) |
| 语义 | 校验边的两端身份一致 | 表达引用并解析身份 |
| 例子 | `tb.anchor_bo_id` | `bo.broken_refs` / `pk.eaten_refs` |

**`anchor_bo_id` 不迁移**:ref_slots 的核心价值(同源未标注翻译)对它无用(交错标注已给),且消费侧不同(边校验 vs 引用表达),迁移要改 4 个 tb 版本 + TemporalEdge 消费侧,收益只有统一性。

## 5 · 逐落点改动清单

### 5.A 必须改(9)

| # | 位置 | 改动 |
|---|---|---|
| A1 | `path2/core.py` Detector Protocol | 加 `produces`(TYPE_CHECKING 内) |
| A2 | `path2/runner.py` `run()` | 检查按流分桶;新增 `run_bundle`(§4.4) |
| A3 | `path2/dag/engine.py` `run_streams` | 缓存值变 bundle,按 `produces_stream` 取下标;兄弟一次填完(§4.4) |
| A4 | `path2/dag/nodes.py` `NodeSpec.__post_init__` | 按流 schema 反射 event_cls(§4.2) |
| A5 | `path2/dag/nodes.py` NodeSpec 字段 | 新增 `produces_stream` |
| A6 | `path2/dag/spec.py:185-204` `_validate_anchor` | `dst_node.detector.event_cls` → `dst_node.event_cls`(node 级已归一化) |
| A7 | `path2/dag/spec.py:206-225` `_validate_render_grid` | `getattr(n.detector,'event_cls',None)` → `n.event_cls` |
| A8 | `path2_web/gate_collector.py:39-73` | per-detector wrapper → `(detector, 流名) → node_id` 路由表(§4.5) |
| A9 | `.claude/skills/tune-gates/multivar_core.py:266-274 / 300-313` | ①共享 detector 硬拒收窄为「同一 (det, consumes, produces) 三元组」;②反转循环缓存键改 `(call_key, 影响维取值)` 存 bundle 再取下标;③`run` → `run_bundle` |

> **A9 实施已延期（2026-09-01 用户指示）**:`multivar_core.py` 是 tune-gates skill 执行核心,它**重新实现**了 `run_streams`。引擎改了它不改 = 调参工具与生产口径**静默**分裂。**但本期不实施**——另一 worktree 正在优化 tune-gates,双写会错乱。缓解:本期无多流真实 app(见研究目录待办「真实 app 践行」),缺口在无消费者时无实际影响;**开始任何多流 app 前必须先补 A9**(触发条件见 plan 的延期项段)。

### 5.B 潜伏点(今天对,多流下变错,4)

| # | 位置 | 风险与修法 |
|---|---|---|
| B1 | `path2_web/serialize.py:275-282` `debug_enabled_nodes` | 判据含 `hasattr(n.detector,'event_cls')`;多流 detector 不声明 event_cls → 静默掉出 debug 列表。改读 `n.event_cls is not None` |
| B2 | `path2/dag/engine.py:22-68` `annotate_stream` 兄弟标注时序 | 「首现 node 获胜」在兄弟间无拓扑序 → 按声明序一次填完(§4.4) |
| B3 | `path2/dag/_solve.py:100-105` + `path2_web/serialize.py:350-364` | 零边 pattern 全求解让 pk 也产 match → `node_index[end_node]` KeyError。**配套 `NodeSpec.solve`**(§6) |
| B4 | `_solve.py` `c1_off` 第 6 源 | 同 bar 多实例时 pk 节点关 C1、剪枝变弱。量级未核实,且仅 pk 参与求解才相关——记录待观察 |

### 5.C 查证免疫(不改,4)

| # | 位置 | 为什么不用改 |
|---|---|---|
| C1 | `_graph.py:98-121` `detector_topo_order` | 排序依据是 `consumes_stream` 指向的 node_id;兄弟共享入边 ⟹ 收缩成超级节点不可能造新环(被 Kahn 保证) |
| C2 | `engine.py:159-164` `res.events` 按 `id(stream)` 去重 | 兄弟流是两个不同 list → 都进 events;共享同流的多 node 仍指同一 list → 仍正确 |
| C3 | `path2/dag/diagnose.py` 全文 | 按 `streams.get(node.node_id, [])`,每个 node_id 都是取过下标的 key |
| C4 | 前端 | 全部按 node 分轨/配色/分流,与 detector 身份无关;pk 节点自动获得独立 band |

### 5.D 新增校验:禁止「自喂」

若 node X 的 `consumes_stream` 指向的 node 与 X 共享同一 detector 对象 → raise。理由:多流后最可能的误写是「让 bo 节点 `consumes_stream="pk"`,以为读的是同一趟扫描的 pk 流」;实际那是 `(id(det),"pk")` 这个**第二次** detect 调用,白跑一整趟。已核实现存 6 个 app 无人这么写,零误杀。

## 6 · 求解层配套(`NodeSpec.solve`)

- **含边 pattern**(bb_v1 / bottom_burst / bb_v3):pk 是孤立 node,K2 判据排除出求解集 → 不进 `node_index`、不产 match、不影响现有匹配,但仍进 `res.events` 照常渲染。**引擎一行不用改**(与 bb_v1 里 `bo` 今天的处境完全同构)。
- **零边 pattern**(`bo_only`):`all_solve = not edges` 让每个 node 自成 WCC 都产 match → `serialize.py:350-364` 对每个 match 取 `node_index[end_node]` → **KeyError**(实测 100 股 matches 1266 → 3613 ≈2.9×)。

**修法 = `NodeSpec.solve: bool = True` + `bound_ids` 判据加 `and nodes[nid].solve`**。这不是为 pk 开的新口子:AST 复核确认 `bo` 节点在 **bb_v0 / bb_v1 / bb_v3 / bottom_burst / try_conplex_where 全部 5 个 app** 里都不是任何边的端点——**这 5 个 node 今天的正确性完全依赖「作者恰好没给 bo 连边」**,`solve=False` 是把已在承重的隐式规则显式化。**本 spec 纳入实施,否则 `bo_only` 加 pk 节点即崩(§5.B B3)。**

配套前端:`chart.ts:143-145` 的 level 门控需对 `solve=False` 的 node 免疫(否则 level=matched 时其卫星被整体滤掉,实测只剩 5.60%)。这是前端一处小改,判据按 node 的 `solve` 标志、类型无关。

## 7 · 关键坑(实施必须避开)

1. **物化键不得加 `produces_stream`**——那会让 `(id(det),None,'bo')` 与 `(id(det),None,'peak')` 成两个缓存条目、各自触发一次 detect = 1.80× 双跑。键管跑几次,下标管取哪条。
2. **`_validate_anchor` / `_validate_render_grid` 直读 `detector.event_cls`**——多流下 `detector.event_cls` 无意义,必须改读 node 级 `event_cls`。
3. **`multivar_core.py` 未同步(A9 已延期)**——多流 app 将无法调参或静默口径分裂。本期接受(无多流真实 app);**开始 pk 应用层前必须补**,否则多流 app 的调参不可信。
4. **`produces` 必须放 TYPE_CHECKING 内**——否则 runtime_checkable isinstance 判定失败。
5. **`debug_enabled_nodes` 的 `hasattr(n.detector,'event_cls')`**——多流 detector 静默掉出 debug 列表。

## 8 · 测试策略

1. **单流回归(硬门槛)**:现有全量测试零回归。重点:多 node 共享同一 detector 的用例(确认 `streams[nid2]` 赋值提前无影响)、`res.events` 去重、诊断、序列化。
2. **多流新测试**:
   - 同一 detector 产两条流,各 node 拿到正确子集;
   - 空流(声明了但本次零事件)→ `streams[nid]` 是 `[]` 而非 KeyError;
   - 未声明流名(node 的 `produces_stream` 不在 schema)→ 报错;
   - 自喂(consumes_stream 指向共享 detector 的 node)→ 报错;
   - 未绑流 + 挂 collector → 挂载期报错;
   - 物化键不变(同一调用只跑一次,`id(det)` spy)。
3. **on_gate 归属**:多流 detector 的 gate failure 路由到正确 node;单流路径逐字等价。
4. **ref_slots 翻译**:同源跨流引用(bo→pk)、同流引用(pk→pk)、空引用无操作、引用事件池外对象报错。翻译正确性判据:`{槽名}_ref_ids` 里的 instance_id 与被引用事件对象上标注的 instance_id 逐字一致(前端按 instance_id 精确 join 的消费属于缺失 X 前端部分,本 spec 只保证字段正确性)。
5. **求解配套**:零边 pattern 加孤立 pk node 不 KeyError、matches 不含 pk;含边 pattern 不受影响。
6. **性能**:按需付费实测(只绑一条流时另一条不产生额外 detect 调用)。

## 9 · 性能预期

- 按需付费实测边际 **1.0156×**(20 只真股 / 21766 bar,多产 560 个 pk 事件,每事件 13.2 µs)——多流不重复计算,只是把已算出的东西顺带 yield。
- 翻译阶段 O(总事件数 + 引用数),一次遍历,空引用无操作。
- `run()` 对多流 detector 显式拒绝(不静默拍平),防误用。

## 10 · 风险与已知边界

1. **格 4b 现有证例 = 0**(连 pk 都不算):本能力「全部押在概念完备上,没有经验冗余」。实施后应尽快用 pk 或某 app 实证一次。
2. **兄弟标注时序**:依赖「按声明序一次填完」,与 children 声明机制对齐;单流观测等价是论证 + 需全量测试确证。
3. **`serialize.py:259` `_materialize_keys_of`** 在多流下让两兄弟报相同参数键集——语义正确(改这些参数确实同时影响两流),精度不损失,保留 + 文档写明,不为它加 per-stream 参数子集声明(过度设计)。
4. **`end_idx` 升序检查从全局降为按流**是放松——单流逐字等价;多流下「两流合起来单调」本无语义。
5. 若 pk 被设计成同 bar 可多实例,`c1_off` 第 6 源会让 pk 节点关 C1 剪枝(B4)——当前设计一 bar 至多一个点事件,不触发,记录待观察。

## 11 · 范围外的后续(独立立项)

- **pk 应用层**:三态显示(需要时基于本引擎 + ref_slots 实施);
- **缺失 X 前端部分**:referenced_points 升级、精确 join、删 `/^pk(\d+)$/`;
- **`anchor_bo_id` 的公共基类字段**(消除 4 个 tb 版本重复声明)——可选,低优先级。

## 12 · 验收标准

1. 现有全量测试通过,单流 app 零行为变化(逐字等价)。
2. 一个多流 detector 样例(可用 pk 或更小 fixture)端到端:两条流各归各 node、on_gate 归属正确、ref_slots 翻译成真 instance_id。
3. 零边 pattern 加孤立 node 不 KeyError(依赖 `NodeSpec.solve` 一并落地)。
4. 按需付费确认:绑定单流的 pattern 不触发多余 detect。
