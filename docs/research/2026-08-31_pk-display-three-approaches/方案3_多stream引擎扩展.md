# 方案③ · 打破「一 detector 一 stream」的引擎扩展设计

> 角色:方案③设计者(纯设计,不碰正式代码)。所有代码事实经本轮独立核实,行号基于工作树当前状态。
> 未核实的推断一律显式标注「**未核实**」;引用队友实证时标注来源。
> **三稿**(2026-08-31):按用户「扩展性 = 抽象本身的通用性,不是现有代码是否使用」的标准重写论证重心;并纳入 lead 补充的三态正交解法、skeptic 与 stream-consumer 的实证。

---

## 0 · TL;DR(四稿 · **我撤回方案③对 pk 需求的必要性主张**)

> **本稿推翻了三稿的核心结论。** stream-consumer 第二轮实证 + 一条四步结构性证明,我逐步核实后**全部认下**:方案①能精确复刻 eaten(80/80 股对称差 0、0/1998 逐 pk 不一致)。三稿里我给的「唯一决定性优势」不成立。
>
> **对 pk 这个需求:① 够了,③ 不必要。** 我不为自己的方案硬撑。
> **对框架:多流这一格仍然该存在**(§8 的溯源与四格分类不依赖 pk),**但 pk 不是它的有效证例** —— 严格判定后 pk 属格 4a 而非 4b,格 4b 的现有证例因此从 1 变成 **0**。
> **所以建议:方案③不搭 pk 这趟车。** 若要做多流,独立立项,并公开承认它目前零证例、价值全部押在概念完备上。
>
> §1–§7 的设计本身仍然成立且可直接使用(如果将来独立立项)。§9 是优势撤回,§13 是三条候选缺失的收敛判断。

**一句话设计**:把「流」的身份单位从 **detector 实例** 下移到 **(detect 调用) × (命名流)**;node 依旧一对一绑定一条流。detector 侧 `produces = {流名: event_cls}` + `yield (流名, event)`;NodeSpec 侧 `produces_stream: Optional[str] = None`。**默认流名取 `None`**,让所有现存单流 detector / app / 测试**零改动**继续工作。

**三条结论,按重要性排序:**

1. **「一 detector 一 stream」在这个 codebase 里从来不是一条被写下来的规矩。** git 考古:物化键 `(id(node.detector), consumes_stream)` 与 `event_cls` 单值反射**诞生于同一个 commit `94e2193`**(engine.py 的创建提交),此后无任何 commit 讨论过它。全仓 grep「铁律」只找到三条成文铁律(`eval_meta` / 组合子 / scan buffered),**没有一条是「一 detector 一 stream」**。相反,`.claude/docs/modules/path2.md:47` 白纸黑字写着「**"一个 detector 产多种事件、一个 attempt"因此自洽**」—— 框架自己的架构文档早已认定多产出与诊断层级自洽。而被真正写下来的不变量是 `docs/research/2026-08-13_instance-id-design.md:28`「一个 node 绑定一个 detector,一次物化内只产出一种 class」——那是 **node 级**的,**本设计逐字保留**。
   ⟹ **单流限制是实现产物,不是概念约束。** 这正是用户判据(「ref 是当时专门为 bo detector 开发的,通用性远不如 event」)的同款溯源结论,只是方向相反:ref 出身专用,而单流限制根本没有出身——它是键的形状顺带带来的。

2. **多流在概念空间里占据一个现有机制结构上覆盖不到的格子。** path2 的 detector 副产物出口现有三格 —— 标量→事件字段、被主事件拥有的结构→`children` 嵌套、失败尝试→`GateFailure` 通道。缺的第四格是:**有独立生命周期、且无法脱离主事件的计算过程被单独算出来**的结构。四格判据可判定(§8.2),灰区只有一处且有明确裁定(性能理由不足以进这一格)。

3. **~~方案③相对方案①的优势~~ —— 已撤回,见 §9。** 三稿我主张「eaten 的施动集合不同、无法靠约定修补」;stream-consumer 的四步证明我逐条核实**全部成立**(承重步骤 `breakout.py:533-538`:supersede 对每个 `old_peak` 的裁决只读 `(max_measure, old_peak.price)`,**与 active 集里还有谁无关**)。差异整个落在 broken 桶里,而 broken > eaten 的优先级是**用户对 eaten 的定义自带的**("被其他 pk 吃掉、**未被突破**的 pk"),不是补丁。残差 = 0。

**代价实测**:运行期边际成本 **1.0156×**(20 只真股 / 21766 bar / 560 个 pk 事件,每个 pk 均摊 13.2 µs;`repro/multistream_paygo_cost.py`),对照背景 §四「峰检测跑两遍 = 1.80×」。代码面 9 处必改 + 4 处潜伏点,`_solve` / `_reify` / `_graph` / `diagnose` / 前端零改动。

**最终评级(四稿修订):**
- **作为 pk 需求的解法:C。** 不推荐 —— ① 能做到的它都能做到,而 ① 不动引擎协议。
- **作为独立的框架补完:B。** §8 的溯源(单流限制是实现产物、无出身、框架文档反而已认定多产出自洽)与四格分类论证依然成立;但格 4b **现有证例 = 0**,价值全部押在概念完备上。这个评级不该由 pk 需求来兑现。

---

## 1 · 核心概念:流的身份单位下移一层

现状的隐含等式:

```
detector 实例  ≡  一次 detect 调用  ≡  一条流  ≡  一个 node(允许多 node 共享)
```

扩展后:

```
detector 实例  ─┬─ 调用 A: (det, consumes_stream=None)  ─┬─ 流 "bo"   ─→ node "bo"
                │                                        └─ 流 "peak" ─→ node "pk"
                └─ 调用 B: (det, consumes_stream="x")   ─── 流 …
```

三条不变量一条不动:

| 不变量 | 说明 |
|---|---|
| **一个 node 恰好一条流** | 求解层、诊断层、渲染层的全部假设都建在这上面,一行不用改 |
| **一条流内事件同类型** | `NodeSpec.event_cls` 仍是单值(从流 schema 反射而来);= `instance-id-design.md:28` 那条成文不变量 |
| **同一 detect 调用只跑一次** | 物化去重的语义不变,只是缓存值形状变了 |

被打破的只有一条:**一次 detect 调用只能产一条流**。

---

## 2 · 约束落点全清单(独立扫描)

背景.md §3.3 列了 4 条线索。本轮独立扫描找到 **17 处**:9 处必改、4 处潜伏点(今天对、多流下变错)、4 处查证免疫。

### 2.A 必须改(9)

| # | 位置 | 现状 | 为什么挡路 |
|---|---|---|---|
| A1 | `path2/core.py:139-155` `Detector` Protocol | 只声明 `detect(source)`,`on_gate` 藏在 `TYPE_CHECKING` 里 | 加 `produces` 声明;**必须同样放进 `TYPE_CHECKING` 守卫**——core.py 自己的注释写明:`runtime_checkable` 的 isinstance 会把 Protocol 里任何属性(哪怕带默认值)纳入必须项,直接声明会让所有未显式带该属性的 conforming class(如 `tests/path2/test_detector_protocol.py::Good`)判定失败 |
| A2 | `path2/runner.py:9-38` `run()` | 跨事件检查(end_idx 升序 + 同 instance_id 无全等对象)跨整条产出序列;返回 `Iterator[Event]` | 检查须**按流分桶**;需要返回 bundle 的新入口 |
| A3 | `path2/dag/engine.py:127-138` `run_streams` 主循环 | `materialized[key] = list(run(...))`;`streams[nid] = materialized[key]` | 缓存值变 bundle,按 `produces_stream` 取下标 |
| A4 | `path2/dag/nodes.py:53-66` `NodeSpec.__post_init__` | `cls = getattr(self.detector, "event_cls", None)` 单值反射 | 改为按流 schema 反射 |
| A5 | `path2/dag/nodes.py` `NodeSpec` 字段 | 无「取哪条流」的字段 | 新增 `produces_stream` |
| A6 | `path2/dag/spec.py:185-204` `_validate_anchor` | `dst_cls = dst_node.detector.event_cls` ← **绕过 node 直接读 detector** | 多流下 `detector.event_cls` 无意义 |
| A7 | `path2/dag/spec.py:206-225` `_validate_render_grid` | `getattr(n.detector, "event_cls", None)` ← 同上 | 同上 |
| A8 | `path2_web/gate_collector.py:39-73` `attach_and_collect` | 共享 detector → 挂雷 `_boom` | 多流 detector 天然被 ≥2 node 引用,雷必炸(§4) |
| A9 | `.claude/skills/tune-gates/multivar_core.py:266-274 / 300-313` | ① 硬拒「多 node 共享 detector 实例」;② 自己复刻了一遍 `run_streams` 物化循环 | 不同步 = **任何多流 app 无法调参**,或静默算出与生产不同的流 |

> A9 不是可选项。`multivar_core.py` 是 tune-gates skill 的执行核心,它**重新实现**了 `run_streams`(反转循环)。引擎改了它不改 = 调参工具与生产口径**静默**分裂 —— 它自己的注释里已为同类风险写过一次「拒绝而非静默给出不同答案」。

### 2.B 潜伏点:今天对,多流下变错(4)

| # | 位置 | 风险 |
|---|---|---|
| B1 | `path2_web/serialize.py:275-282` `debug_enabled_nodes` | 判据含 `hasattr(n.detector,'event_cls')`。多流 detector 若不再声明 `event_cls` → **静默**掉出 debug 列表。改读 node 级 `n.event_cls is not None` |
| B2 | `path2/dag/engine.py:22-68` `annotate_stream` 兄弟标注时序 | 「首现 node 获胜」。兄弟节点之间**无拓扑序**(同 `consumes_stream`,只能按 node_id 字典序破平)。若多流 detector 把 A 流事件嵌套进 B 流事件的 child slot,谁先标注谁抢走命名权。单流下不存在"无序兄弟",故今天安全。修法见 §3.4 |
| B3 | `path2/dag/_solve.py:100-105` `bound_ids` + `all_solve` 例外 | 含边 pattern:孤立 pk 不进 WCC、不产 match(正是想要的);**零边 pattern(`bo_only`)**:全求解例外让 pk 也产 match。已核实 `solve()` 逐 WCC 向同一 `out` 追加(**非笛卡尔**),故是"多一批"不是"爆炸"——stream-consumer 实测 100 股 1266 → 3613(≈2.9×)。但 `serialize.py:350-364` 对每个 match 取 `node_index[end_node]` → **KeyError**。见 §7.3 |
| B4 | `_solve.py` `c1_off` 第 6 源(`solve()` 入口 `dup_nodes`) | 「流内有 `instance_idx>0`」即关 C1 剪枝。pk 若「一 bar 至多一个点事件」则 `instance_idx` 恒 0,不触发。若设计成同 bar 可多实例,pk 节点关 C1、剪枝变弱。量级**未核实**,且只在 pk 真参与求解时才相关 |

### 2.C 查证免疫(4)

| # | 位置 | 为什么不用改 |
|---|---|---|
| C1 | `_graph.py:98-121` `detector_topo_order` | 排序依据是 `consumes_stream` 指向的 **node_id**,与 detector 身份无关。兄弟节点共享同一 `consumes_stream` ⟹ 入边完全相同 ⟹ **把兄弟收缩成超级节点不可能造出新环**(要成环需 node 图里已有环,已被 Kahn 拦下)。call-level 无环性由现有 node-level Kahn 已保证 |
| C2 | `engine.py:159-164` `res.events` 按 `id(stream)` 去重 | 兄弟流是两个**不同 list 对象** → 都进 events;共享同一条流的多 node 仍指向同一 list → 仍正确去重。语义恰好对 |
| C3 | `path2/dag/diagnose.py` 全文 | 一切按 `streams.get(node.node_id, [])`,每个 node_id 都是取过下标的 key。零改动 |
| C4 | 前端(`bandKeyOf(e)=e.node_id`、`_event_styles` 键=node_id、`render_grid` per-node) | 全部按 node 分轨/配色/分流,与 detector 身份无关。pk 节点自动获得独立 band / 配色 / render_grid |

> `serialize.py:259` 的 `_materialize_keys_of(n.detector)`(反射 ctor 形参名)在多流下让两个兄弟报出相同参数键集。语义是"改这些参数会让本 node 重新物化",对两个兄弟**都为真**,不算 bug,但精度下降。建议保留 + 文档写明,不为它加 per-stream 参数子集声明(过度设计)。

---

## 3 · 逐落点扩展设计

### 3.1 归一化函数(向后兼容的总闸门)

```python
DEFAULT_STREAM = None          # 「该 detector 的唯一流」的流名

def stream_schema(det) -> Mapping[Optional[str], type]:
    """detector → {流名: event_cls}。单流 detector 归一化成 {None: det.event_cls}。"""
    produces = getattr(det, "produces", None)
    if produces:
        return dict(produces)
    cls = getattr(det, "event_cls", None)
    if cls is None:
        raise ValueError("detector 必须声明 event_cls(单流)或 produces(多流)")
    return {DEFAULT_STREAM: cls}
```

**默认流名取 `None` 是整个兼容机制的支点**:`NodeSpec.produces_stream` 的默认值就是 `None`,于是每个现存 NodeSpec **不写一个字**就已经正确选中了唯一那条流。不需要适配层、不需要在各处散布双路径 —— 只有 `stream_schema` 和 `run_bundle` 两处知道有两种形态,其余代码只看到统一的 `{流名: [Event]}`。

### 3.2 A1 · Detector Protocol

```python
@runtime_checkable
class Detector(Protocol):
    if TYPE_CHECKING:
        on_gate: Optional[Callable[["GateFailure"], None]]
        produces: ClassVar[Mapping[str, type]]   # ★ 多流声明;单流 detector 不写
    def detect(self, source: Any) -> Iterator[Event]: ...
```
`produces` **必须**在 `TYPE_CHECKING` 内(理由见 2.A/A1,core.py 自己踩过并留了注释)。运行时零影响。

### 3.3 A2 · `runner.run` / 新增 `run_bundle`

```python
def _tagged(detector, *source):
    """统一线格式:单流 detector 的裸 Event 归一化成 (None, ev)。"""
    multi = bool(getattr(detector, "produces", None))
    for item in detector.detect(*source):
        yield (item if multi else (DEFAULT_STREAM, item))

def run_bundle(detector, *source) -> Dict[Optional[str], List[Event]]:
    schema = stream_schema(detector)
    out = {name: [] for name in schema}      # ★ 空流也存在(声明驱动,非产出驱动)
    ...  # RUNTIME_CHECKS 下:未声明流名硬错 + per-stream isinstance 校验
         #                   + end_idx 升序 / 同 instance_id 无全等对象 按流分桶
    return out

def run(detector, *source) -> Iterator[Event]:
    """公开单流入口(签名/行为不变)。多流 detector 显式拒绝,不静默拍平。"""
```

三点:
- **`out` 用 schema 预填空 list** —— 声明驱动。保证「某条流本次零事件」时 `streams[nid]` 是 `[]` 而非 KeyError,与今天一致。
- **`end_idx` 升序检查从全局降为按流** —— 这是**放松**;单流逐字等价;多流下"两条流合起来也单调"本无语义。
- **保留 `run()` 原签名** —— 它被 tune-gates skill、repro 脚本、`temp_code/` 直接调用。对多流 detector 显式 raise,不猜。

### 3.4 A3 · `run_streams`(含 B2 时序修复)

```python
siblings = {}                                   # (id(det), consumes) -> [NodeSpec] 按声明序
for n in spec.nodes:
    if n.detector is not None:
        siblings.setdefault((id(n.detector), n.consumes_stream), []).append(n)

for nid in detector_topo_order(spec.nodes):
    node = by_id[nid]
    if node.detector is None or nid in streams:
        continue                                # 后者:已被兄弟那一趟填好
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

**为什么兄弟要一次填完**(B2):兄弟之间没有拓扑序。一次填完 + 按 `spec.nodes` 声明序标注,把顺序从"字典序偶然"变成"作者显式声明",与 `children` 声明机制(`burst.members → bo`)对齐。

**对单流 app 的影响:观测等价(论证,未跑测试)**。单流下 `siblings[key]` 要么单元素,要么是"多 node 共享同一 detector 同一输入":两个 node_id 拿到**同一 list 对象**(同今天),第二个 `annotate_stream` 因"已标注跳过"为 no-op(同今天),唯一变化是 `streams[nid2]` **赋值时刻提前**。迭代间唯一读 `streams` 的地方是 `streams[node.consumes_stream]`,其存在性由拓扑序保证 —— 提前赋值只会更早就位,不可能变缺。**必须用现有全量测试确证。**

### 3.5 A4 / A5 · `NodeSpec`

```python
consumes_stream: Optional[str] = None    # 输入:上游 node_id(不变)
produces_stream: Optional[str] = None    # ★ 输出:取本 detector 的哪条命名流;None = 唯一流

# __post_init__:
schema = stream_schema(self.detector)                # 单流 → {None: event_cls}
if self.produces_stream not in schema:
    raise ValueError(f"NodeSpec({self.node_id!r}): detector 无流 {self.produces_stream!r}")
object.__setattr__(self, "event_cls", schema[self.produces_stream])
```
单流路径逐字等价。`_validate_substructure` 的死字段清单加一条:子结构 node 的 `produces_stream` 必须是 `None`。

### 3.6 A6 / A7 · spec 校验改读 node 级 `event_cls`

`dst_node.detector.event_cls` → `dst_node.event_cls`;`getattr(n.detector,'event_cls')` → `n.event_cls`。因为 `NodeSpec.__post_init__` 已把 `event_cls` 归一化到 node 上,这两处**今天就等价** —— 改动只是拆掉"绕过 node 直接问 detector"这个多流下会崩的习惯。

### 3.7 新增校验:禁止「自喂」

若 node X 的 `consumes_stream` 指向的 node 与 X 共享同一 detector 对象 → raise。理由:多流出现后最可能的误写就是「让 bo 节点 `consumes_stream="pk"`,以为读的是同一趟扫描的 pk 流」;实际那是 `(id(det),"pk")` 这个**第二次**detect 调用,白跑一整趟。核实过现存 6 个 app 无人这么写,零误杀。

### 3.8 B1 · `debug_enabled_nodes`

`getattr(det_cls,'has_debug_hooks',False) and n.event_cls is not None`。

### 3.9 A9 · tune-gates 工具链(必做)

1. 共享 detector 的硬拒判据从「同一 detector 实例」收窄为「同一 **(det, consumes, produces)** 三元组」——多流兄弟三元组不同,合法放行。
2. 反转循环缓存键 `(nid, 影响维取值)` → `(call_key, 影响维取值)` 存 bundle,再取下标;`run` → `run_bundle`。
   `influence_dims` / `upstream_closure` 走 `consumes_stream` 单链,**不用改**;`probe_dim` 用 `_det_state` 比对,一个参数变化会同时标记两个兄弟为 D 维受影响 —— **恰好是对的**(改 `min_relative_height` 确实同时改了两条流)。

---

## 4 · `on_gate` 归属协议(用户点名)

### 4.1 先更正一条事实(回应 skeptic)

skeptic 称「两个 node 指向同一 detector → 后挂的 wrapper 覆盖先挂的,`gf.node_id` 会被写成其中一个 node」。**核实后不成立**:`gate_collector.py:63-72` 有 `seen: set[int]`,第一个 node 挂 `make_wrapper(nid)`,**第二个及以后挂 `make_boom`**;由于是同一个 detector 对象的同一个属性,最终值是 `_boom`。所以现状不是"静默错归属",而是**该 detector 的第一条 gate failure 到达即 `raise RuntimeError`**。
结论不变(多流下这颗雷必炸,A8 必改),但性质从"静默错误"更正为"硬失败"。

### 4.2 归属的第一性回答

`GateFailure` 记录的是**一次没能诞生的事件**,所以它属于「那个事件本该进入的流」。这不需要引擎猜 —— 发射点知道。核实 `BODetector` 现有 7 处 `on_gate` 调用,划分干净:

| `measured.kind` | 判据 | 归属 |
|---|---|---|
| `window_start` / `side_bars_offset` / `peak_idx` / `window_min_low` / `relative_height` | `_detect_peak_in_window` 四道闸 | **pk 流** |
| `breakout_price` / `gap` / `count` | 突破判定 | **bo 流** |

顺带一个真实收益:今天这 7 条**全挂在 `bo` 这一个 node 上**,其中 5 条说的是"峰没登起来"、与 bo 无关。多流后归属**变准**。

### 4.3 协议

**(a)** `GateFailure` 加带默认值字段 `stream: Optional[str] = None`。该类既定做法(源码注释:「追加字段, 带默认值 → 既有 kwargs 构造点全兼容(先例:code_location)」)。**现存所有构造点一行不改。**

**(b)** `attach_and_collect` 从 per-detector wrapper 改为 `(detector, 流名) → node_id` 路由表:

```python
routes.setdefault(id(node.detector), {}).setdefault(node.produces_stream, []).append(node.node_id)
# 收到 gf:nids = table.get(gf.stream)
#   None      → 该流未被本 pattern 绑定 → 丢弃
#   len > 1   → raise(挂雷保留,但收窄到「同一条流被多 node 绑定」)
#   否则      → collector.add(replace(gf, node_id=nids[0]))
```

**(c) 单流零影响**:`gf.stream` 恒 `None`、其 node 的 `produces_stream` 恒 `None` → `table == {None:['bo']}` → 与今天 `make_wrapper(node.node_id)` **逐字相同**。

**(d) 挂雷是严格放宽**:今天炸的条件「同一 detector 被 ≥2 node 引用」⊃ 改后「同一**流**被 ≥2 node 绑定」。原来会炸的场景照样炸,新放行的只有"绑同一 detector 的**不同**流",而那正是归属明确的情形。

**(e) 未绑流的 gf —— 不能静默丢弃,但也不能按 skeptic 的原方案校验。**

一稿把"静默丢弃 + 文档兜底"当作已知粗糙面。skeptic 提出应升级为**spec 期校验:detector `produces` 声明的每条流必须恰好被一个 node 绑定,否则构建报错**。理由(该改动一口气放松了三张安全网,唯独这张是静默的)我接受;**但这个具体形态与 §7.2 的按需付费直接冲突** —— 它等于强制"任何 pattern 只要用了 `BODetector` 就必须同时声明 pk 节点",而 pattern 只绑一条流是本设计明确支持的用法。

**改成挂载期校验(推荐):**
- 生产扫描路径 `on_gate=None`,零开销、零约束 —— 按需付费不受影响;
- `attach_and_collect(spec)` 时(即诊断路径)检查:该 detector 声明的流里,有没有**未被任何 node 绑定**的。有 → 立刻报错,消息指明"流 X 未绑定,其 gate failure 将无处归属;请为它建 node 或改用不产 gf 的配置"。
- 兜底:若仍有 gf 携带未绑流名到达 router,在 `RUNTIME_CHECKS` 下 raise 而非 return。

**理由**:静默的根源不是"允许不绑流",而是"允许不绑流的同时还挂着 collector"。把校验挂在**两者同时成立**的那一刻,既堵住静默,又不牺牲按需付费。

**(f) 被否决的替代**:把 `on_gate` 改成 per-stream 回调字典。要改 4 个 atom、20+ 处调用点和零开销默认值,而"哪条流"这个信息无论如何都得从发射点来 —— 加一个带默认值的字段是承载它的最小载体。

---

## 5 · detector 侧 API 形态

### 5.1 三候选

| | 候选 1(推荐)`produces` + `yield (流名, event)` | 候选 2 `detect()` 返回 dict-of-streams | 候选 3 显式多方法 |
|---|---|---|---|
| 单趟扫描 | ✅ 天然一趟 | ⚠️ 要么 eager 全物化,要么两个 iterator 从一个生成器 tee(消费一个强制缓冲另一个) | ❌ **两趟**,背景 §四实证 1.80× |
| 「状态不跨 detect 调用」协议 | ✅ | ✅ | ❌ 两方法必须共享 `_active_peaks`,状态跨调用存活,直接违反 spec §1.2.4 |
| `run()` 逐事件检查 | ✅ 仍流式 | ⚠️ 从"边产边查"退化为"产完再查" | ✅ |
| 空流可见 | ✅ 靠声明 | ✅ | ✅ |
| 两条流同 event_cls | ✅ 流名是身份 | ✅ | ✅ |
| 模板侵入 / diff | 小 | 中 | 大 |

**推荐候选 1**,硬规矩:一个 detector 要么单流(裸 Event + `event_cls`),要么多流(`(流名, event)` + `produces`),不混用。引擎按**声明**决定读法,**不做逐 yield 的类型嗅探**。

### 5.2 为什么不用「靠 `event_cls` 隐式类型路由」——在新标准下这条理由变强了

一稿里我把"靠类型认身份是本项目消灭 `event_type` 时否决过的路子"列为**纪律论证**并自曝可被打。按用户新判据重审后,**它不是纪律,是抽象层级**:

用户区分 event 与 ref 的判据是「这个抽象是为通用概念而生,还是为某个具体 detector 而生」。同理:
- **显式命名流**是一个**一等概念** —— 流有名字、有 schema、可为空、可校验、可被 NodeSpec 引用。它独立于任何具体 detector 存在。
- **靠类型推断流**是一条**隐式约定** —— 流没有独立身份,身份寄生在 event 类上。于是:两条流不能同类型(身份冲突)、空流不可见(没有产出就没有 schema)、流名拼错无法校验(没有名字可拼错,只有类可写错)。

这正是 event(一等概念)与 ref(寄生在 BOEvent 字段上的专用结构)的同款层级差。**所以隐式路由的 diff 虽然更小,但它造出的是第二个 ref —— 一个寄生的、不能独立存在的抽象。** 在「抽象本身的通用性」这条判据下,它应当被否决,而不只是"不符合纪律"。

### 5.3 与 `BarwiseDetector` 的关系

```python
def detect(self, df):
    multi = bool(getattr(type(self), "produces", None))      # 循环外求值
    for i in range(len(df)):
        if multi:
            yield from self.emit_multi(df, i)                # 多流子类实现
        else:
            ev = self.emit(df, i)                            # ← 现存全部子类走这条,逐字不变
            if ev is not None:
                yield ev
```
显式二分支(而非"默认 `emit_multi` 委托 `emit`")是为了保证**直接调 `det.detect(df)` 的现存测试**拿到的仍是裸 Event 而非元组。

---

## 6 · NodeSpec 声明与物化键

```python
det = BODetector(**params.bo_kwargs())         # ★ 一个实例,两个 node
NodeSpec("bo", det, produces_stream="bo",   render_grid="price"),
NodeSpec("pk", det, produces_stream="peak", render_grid="price"),
```

**「物化键怎么改才不串错流」的正面回答:键不改。**
`key = (id(detector), consumes_stream)` 是 **detect 调用的身份**;`bundle = materialized[key]`;`streams[nid] = bundle[node.produces_stream]` —— 取下标发生在**缓存命中之后**。把 `produces_stream` 加进键会让同一 detector 扫两遍,**明确是错的**。

> **对「键必须加输出流名维度」这一提议的反驳**(skeptic 复审提出)。提议的依据是:现状下 bo 与 pk 两个 node 的 key 完全相同 ⟹ `streams['pk'] = materialized[key] = streams['bo']`,pk 拿到 bo 流且 `annotate_stream` 因"已标注"整体跳过、pk band 一个事件都标不上。
> **这个描述准确,但它描述的是「只加 `produces_stream` 字段、不改 `run_streams`」的半截状态**——即本设计 A3 尚未实施时的样子。A3 正是为此存在:缓存值从 `list` 变 `bundle`,并新增取下标一步。
> **而提议的修法本身是错的**:若把 `produces_stream` 并入键,`(id(det),None,'bo')` 与 `(id(det),None,'peak')` 成为两个独立缓存条目,各自触发一次 `run_bundle` ⟹ **同一个 detector 被完整扫两遍**(实测对照:峰检测两遍 = 1.80×),而这正是本方案存在的理由所要消除的东西。
> **正确的分工是**:键管"跑几次"(按 detect 调用去重),下标管"取哪条"(按流名区分)。两件事不该挤进同一个键。

串流的真实风险不在键上,三处各有一道闸:
1. 声明流名与实际 yield 标签漂移 → `NodeSpec.__post_init__` schema 校验(构造期)+ `run_bundle` 未知标签硬错(运行期);
2. 流名对、事件类型错 → `run_bundle` 的 per-stream `isinstance` 校验(**新增保护**,单流时代没有);
3. 有人忘了取下标 → 取下标只有 `run_streams` 一个点,单点收口,类型立刻炸。

**两个 node 绑同一条流**(一身多角,如 down/side 共享 `TrendSegmentDetector`)仍合法:三元组相同 → 同一 list 对象 → `res.events` 按 `id(list)` 去重仍正确。既有能力不被削减。

---

## 7 · 时序 / 按需付费 / 求解判据

### 7.1 多流之间的物化时序
- **调用内**:两条流由同一趟逐 bar 扫描交错产出,无"谁先算"问题 —— 这正是本方案相对方案①的价值所在(`_active_peaks` 被峰检测与突破检测**双向**读写)。
- **兄弟间**:§3.4 的"一次填完 + 声明序标注"。
- **交错标注不变量保持**:"上游流在下游 detect 期已标注"仍成立(要读某条流就得 `consumes_stream` 它,那就有拓扑序);兄弟之间无消费关系,无需序。

### 7.2 按需付费 —— 实测 **1.0156×**

pattern 只声明 `bo`、不声明 `pk` 时,峰检测**照样要跑**(bo 判据依赖它),多出来的只有 `PeakEvent` 的构造与 append。

实测(`repro/multistream_paygo_cost.py`,20 只真股 / 21766 bar / bb_v1 params.yaml,peak=high、breakout=close):

| | 耗时 | 倍率 |
|---|---|---|
| A 基线(原生 `BODetector`) | 473.5 ms | 1.0000× |
| B 多流模拟(额外构造 560 个 `PkEvent`) | 480.9 ms | **1.0156×** |
| 对照:峰检测跑两遍(背景 §四) | — | 1.80× |

每个 pk 事件均摊 **13.2 µs**。**明确建议不做**"把需求流集合传进 `detect()` 让 detector 跳过构造" —— 为 1.6% 给 detect 签名加参数,协议成本远大于收益。

### 7.3 `bound_ids` / 求解判据 ★需配套一条改动

- **含边 pattern**(bb_v1 / bottom_burst / bb_v3):pk 是孤立 node,K2 三要素判据把它排除出求解集 → 不进 `node_index`、不产 match、不影响现有匹配数,但仍进 `res.events` → **照常渲染**。这正是想要的,且**引擎一行不用改**(与 bb_v1 里 `bo` 今天的处境完全同构)。
- **零边 pattern**(`bo_only`):`all_solve = not edges` 让每个 node 自成 WCC 都产 match(逐 WCC 追加、非笛卡尔)。stream-consumer 实测 100 股 **1266 → 3613(≈2.9×)**,且 `serialize.py:350-364` 对每个 match 取 `node_index[end_node]` → **KeyError**。

  **两级修法,推荐后者:**
  - **止血级(1 行)**:`serialize_per_pattern_result` 的 match 循环加 `if end_node.split(".")[0] not in m.node_index: continue`(语义:不含买点 node 的 match 不进评估)。
  - **根治级(推荐,独立价值)**:`NodeSpec.solve: bool = True`,`bound_ids` 判据加 `and nodes[nid].solve`。这把今天"孤立即不属 pattern"的**巧合**变成**声明** —— 今天作者根本无法表达"这个 node 只显示不参与匹配"的意图,只能靠"恰好没给它连边"来间接实现,而这个间接实现在零边 pattern 下失效。这条改动**独立于 pk 需求**、独立于多流,是一条纯引擎概念补完,建议单独立项。

  > **★ 它不是"零住户的新概念",是"把已在承重的隐式规则显式化"**(stream-consumer 提出,我用 AST 独立复核):对 5 个 app 的 `dag_spec.py` 解析 NodeSpec 与全部边端点(含 `Child(...)` 展开),`bo` 节点在 **bb_v0 / bb_v1 / bb_v3 / bottom_burst / try_conplex_where 全部 5 个** app 里都不是任何边的端点 —— 唯一的边是 `TemporalEdge(Child("burst","last_bo"), "tb")`,端点并集只有 `{burst, tb}`。
  > **⟹ 这 5 个 node 今天就靠 K2 判据不参与求解,而它们的正确性完全依赖"作者恰好没给 bo 连边"。** 给 `bo` 随手连一条边就会静默改变语义,而框架里没有任何地方能表达"这是有意的"。`solve=False` 是把这条已经在承重的规则写出来。
  > (`tb_seg` / `tb_seg_v3` 也孤立,但它们是子结构 node、`detector is None`,由另一条守卫排除,不属同一机制。)

  **这条风险跨方案通用**:方案①的 `PeakDetector` 在 `bo_only` 里同样是孤立节点、同样触发。

  ⚠️ 配套的前端问题(recursive-ref 发现,已核实 `chart.ts:143-145`):`RANK[eventTier(e)] >= RANK[level]` 过滤;孤立/不求解的 node 其事件 tier 恒为 `detected`(rank 0),`level=matched` 时被整体滤掉(实测 pk 卫星只剩 5.60%)。`solve=False` 的 node 应当**免疫 level 门控**——这是前端一处小改,且判据按 node 的 `solve` 标志,类型无关。

### 7.4 诊断归属
per-node 诊断(`path2/dag/diagnose.py`)自动给 pk 独立的 attr 行(逐候选峰 × 逐 where clause)与 rel 行,**零改动**。今天完全看不到"哪些峰被哪道闸拦了"。

---

## 8 · 理论性论证:概念空间里该不该有这一格

> 用户判据:「扩展性不是已有代码中被使用,而是理论上应该有」+「ref 虽正被使用,但它本来就是当时专门为 bo detector 开发的,通用性远不如 event」。
> 所以下面论证的是**抽象本身的层级**,不是使用人数。**「本 codebase 里多流的现有需求量 = 1」这条事实我不软化**(§8.4),但它不再是减分项。

### 8.1 溯源:单流限制是实现产物,不是概念约束

三条互相独立的证据:

1. **它诞生于键的形状,没有独立出身。** `git log --diff-filter=A -- path2/dag/engine.py` → `94e2193`(engine.py 的**创建**提交);`git log -S "id(node.detector)" -- path2/dag/engine.py` → **同一个** `94e2193`;`git log -S "detector.event_cls" -- path2/dag/nodes.py` → **同一个** `94e2193`。物化键与 `event_cls` 单值反射是**随引擎一起出生**的,此后**无任何 commit 讨论、加固或论证过它**。对比用户对 ref 的溯源(「当时专门为 bo detector 开发」):ref 至少还有一个"为谁而生"的出身;单流限制连出身都没有 —— 它是 `(id(detector), consumes_stream)` 这个键顺带带来的,当时只有单流需求,所以键就长成了那样。

2. **codebase 从来没把它写成规矩。** 全仓 grep「铁律」只有三条成文铁律:`eval_meta` 必须声明(`.claude/docs/modules/path2_apps.md:27`)、组合子铁律(`authoring-path2-app/design-heuristics.md:143`)、scan 必走 buffered(`path2_web/scan.py:3`)。**没有一条是「一 detector 一 stream」。** 这个说法是本轮讨论里出现的,不是框架的自我声明。

3. **框架的架构文档反而已经认定多产出自洽。** `.claude/docs/modules/path2.md:47` 原文:

   > **「一个 detector 产多种事件、一个 attempt」因此自洽**:次级产物(子结构段如 tb_seg)无独立 attempt、只有事件层 start/end——不是例外,是 entry 本就不属于事件档位。

   诊断层级(attempt/entry/gate 属检测过程、start/end 属事件协议)**已经**为"一个 detector 产多种事件"留好了位置。真正被写下来的不变量是 `docs/research/2026-08-13_instance-id-design.md:28`:「一个 node 绑定一个 detector,一次物化内只产出一种 class」—— 那是 **node 级**的,而本设计**逐字保留**它。

**结论:限制在实现里,概念体系里没有它。移除它不是引入新概念,是让实现追上已有的概念体系。**

### 8.2 概念空间:detector 副产物的四格分类(可判定)

一个 detector 在计算主事件时会产生别的东西。path2 现有三个出口,缺第四个:

```
                       它是"没能成为事件的失败尝试"吗?
                        ├─ 是 → 【格1】GateFailure 诊断通道   ✅ 已有
                        └─ 否 ↓
                       它是纯标量派生量吗?
                        ├─ 是 → 【格2】事件字段(where 可读)   ✅ 已有
                        └─ 否 ↓
                       它的生命周期被某个主事件包含吗?
                       (主事件不发生它就不存在)
                        ├─ 是 → 【格3】children 嵌套          ✅ 已有(tb.segments)
                        └─ 否 ↓  (= 它有独立生命周期)
                       它能被一个独立 detector 单独算出来吗?
                       (不需要主事件计算过程的中间状态)
                        ├─ 能 → 【格4a】独立 detector + consumes_stream  ✅ 已有
                        └─ 不能 → 【格4b】同一趟扫描的第二条流           ❌ 缺失 ← 本方案
```

**四格互斥且穷尽**(在"detector 产出的东西"这个论域内):失败/成功二分穷尽;成功物中标量/结构二分穷尽;结构中生命周期是否被包含二分穷尽;独立结构中可否独立计算二分穷尽。

**pk 落在 4b:** 生命周期独立(28.3% 的峰从未被突破,不属于任何 BOEvent —— 背景实证;recursive-ref 复测 alive 29.27%),排除格 3;而它的**死因**无法被独立算出来(§9.1),排除格 4a。

**这一格的缺失曾经把使用者逼进扭曲的表达**(用户判据第 2 条):想让同一趟扫描产出两种事件,现有唯一出路是"写两个 detector 类 + 让它们共享一个纯函数"(即被否决的 B′)。那个"两个类一个函数、参数一致性只能靠纪律"的形态,就是这一格缺失留下的疤。

### 8.3 边界的可判定性与灰区

**判据是可执行的**,四道题都能在设计阶段回答:
- 格 1/2 的判定是定义级的(失败 vs 成功、标量 vs 结构),无争议。
- 格 3 vs 格 4 的判定 = **"主事件不发生时它还在吗"**,可用数据回答:pk 有 28.3~29.3% 的实例没有宿主 → 独立;tb 段 100% 有宿主 → 被包含。
- 格 4a vs 4b 的判定 = **"能不能写出一个只吃 df 的纯函数把它算出来"**,可用对拍回答(队友已做:登记集 Jaccard=1.0 → 登记**能**独立算;eaten 标签 645→3714 → 死因**不能**)。

**唯一灰区:同一个结构的不同侧面可能落在不同格。** pk 就是活例 —— 它的**诞生**在 4a(可独立算),它的**死因**在 4b(不可独立算)。裁定规则:**取最严格的那一格**;只要有任一必需侧面落 4b,整体就得走 4b。理由:格 4a 无法表达"我需要主事件计算过程的中间状态",无论那个需求只占该结构的多少比例。

**一条明确的负面裁定(防止这一格被滥用):性能理由不足以进 4b。** 若某结构**能**被独立算出来、只是重算贵(如峰检测两遍 1.80×),那它属于 4a,应该老老实实用两个 detector;多流不是为省 CPU 存在的机制。这条裁定同时解释了为什么"避免重复计算"在我的论证里从头到尾**不是**主论据 —— 主论据只有一条:**不可独立计算**。

### 8.4 现有需求量 = 1(不软化)

把 `path2/atoms/` 6 个 detector 全扫了一遍,找"带生命周期、有状态演化、却不出流的私有结构":

| 内部结构 | 位置 | 落格 |
|---|---|---|
| `Peak` | `breakout.py:19` | **4b** ← 唯一 |
| `FirstSegment` | `throwback_v1.py:94` | 状态机中间量,格 2/非结构 |
| `TbV4Seg` / `TbV4MachineResult` | `throwback_v4.py:32/39` | **格 3**,已通过 `tb.segments` 嵌套出流 |
| `ThrowbackResult` | `throwback_v0.py:43` | 返回值容器 |
| `TrendSegmentDetector` 的 `seg_start/seg_regime` | `trend.py:53-103` | 局部循环变量,产出即 yield |
| `PlatformDetector` / `DistributionDetector` | — | 无跨 bar 可变状态(仅 vol_ratio 序列缓存) |

**结论:格 4b 在本 codebase 的现有实例 = 1。** 按用户新判据这不构成减分,但它确实意味着:**这一格的价值目前全部押在"概念完备"上,没有经验冗余。** 我认为这是本设计最诚实的一句话。

---
## 9 · 相对方案①/②的优势 —— 逐条撤回后剩下什么

> 四稿全面修订。三稿在此处给出的「唯一决定性优势」已被 stream-consumer 的实证 + 结构性证明推翻,本节记录我的核实过程与最终结论。**我不为自己的方案硬撑。**

### 9.1 ★ 撤回:eaten 语义可以被方案①精确复刻

三稿我主张:eaten 由 supersede 的施动者记录,而施动集合 `_active_peaks` 在方案①下是超集(纯峰域没有"大幅突破移除"这条退场出口)⟹ 施动集合本身不同 ⟹ 无法靠约定修补。

stream-consumer 给了四步证明,我逐步核实,**全部成立**:

| 步 | 命题 | 我的核实 |
|---|---|---|
| (i) | 从未被突破的峰**从未被 elevated** ⟹ 两域价格恒等 | ✅ elevation 只在 `breakout.py:325-328` 的 `if breakout_price > exceed_price` 分支内发生 |
| (ii) | 从未被突破的峰**只能走 supersede 离场** | ✅ 突破循环(`:310-331`)重建 `remaining_peaks` 时保留每个未被突破的峰;唯一另一条移除路径就是 peak-peak supersede |
| (iii) | supersede 判据**只依赖新峰价与老峰价,与 active 集里还有谁无关** | ✅ **承重步骤,已逐字核实** `breakout.py:533-538`:`exceed_pct = (max_measure - old_peak.price)/old_peak.price`,逐 old_peak 独立裁决,无任何集合级依赖 |
| (iv) | 登记集与登记时刻两域相同 ⟹ 裁决相同 | ✅ 在 `breakout ⪯ peak` 安全区内成立(C1 不触发),现有 8 个 app 全在区内 |

推论我也核实了:**那个 5.24×/5.76× 的差整个落在 broken 桶里** —— 纯峰域把"现实中已被突破移除"的峰留到后来被吃,于是标 eaten;而 broken > eaten 的优先级**是用户对 eaten 的定义自带的**(原话:"被其他 pk 吃掉、**未被突破**的 pk"),不是事后打的补丁。

实证(stream-consumer,80 股 seed=20260831,参数直读 yaml):①a 的 supersede 移除集与现状真值**对称差 0(80/80 股)**;bo 集逐字相同;施加优先级后现状 / ①a / 纯峰域**三方逐 pk 全等,0/1998 不一致**。

**⟹ 三稿的「决定性优势」不成立,撤回。lead 转达给我的「①需要约定 + 1.4% 残差」也随之作废(残差是 0)。**

### 9.2 已撤回的另外两条

- ❌ **「bo 流保真」** —— 三个安全象限下登记集与 bo 集逐字全等(0/100 股有差)。不再独有。
- ❌ **「避免重算 1.80×」** —— §8.3 的负面裁定:性能理由不足以进格 4b。从头到尾不是我的主论据,此处正式钉死。

### 9.3 C1 —— 正面回答:它对①③都是中性的,不构成任何一方的论据

C1(大幅突破移除 → 放开去重闸 → 同位重登记)在方案①里**结构上不可复刻**(要复刻就得让 bo 域回灌 peak 域 = 成环,而 `detector_topo_order` 见环即 raise);但它在 `breakout_measure ⪯ peak_measure` 时**可证明恒不触发**,现有 8 个 app 全在安全区。

lead 问:按新标准(理论上该有、不看现在用不用),「当前不可观测」还算不算①的免责理由?

**我的判断:这个问题问错了对象 —— C1 根本不该被当作论据,对哪一方都是。** 理由:

用户的新标准衡量的是**抽象本身的通用性**("一个计算过程可以产出多种事件"是不是概念体系里该有的一格)。而 C1 不是抽象,它是**一个具体 detector 的一处行为角落**。拿 C1 论证多流的必要性,恰恰就是用户点名要避免的那种事 —— 为一个具体需求(而且是一个在所有现存参数象限里都观测不到的具体需求)立一套机制。

所以:
- C1 **不是**③的现实优势(恒不触发);
- C1 **也不是**③的理论优势(它是行为角落,不是抽象层级的缺失);
- 反过来,C1 **也不构成**①的减分(同理)。

**它对两边都中性。我不用它。**

### 9.4 剩下的东西 —— 诚实清点

| 候选优势 | 判定 |
|---|---|
| eaten 语义正确 | ❌ 撤回(§9.1) |
| bo 流保真 | ❌ 撤回(§9.2) |
| 避免重算 | ❌ 撤回(§9.2) |
| C1 无条件保真 | ❌ 中性,不用(§9.3) |
| **参数单一来源** | ⚠️ **真实但很弱**。①里 elevation 在突破那根按 `peak_measure` 取值,故 bo 域必须持有 `peak_measure`,与 PeakDetector 重复。但**在 app 声明层它仍是单一来源**(`params.bo.peak_measure` 同时喂两个 `*_kwargs()`),重复只发生在 detector 实例层。B′ 的"参数一致性只能靠纪律"这个病,在 ① 下已经被 Params 结构性治住了大半。**我不把它当作支撑整套协议改动的理由。** |
| **gate failure 归属变准** | ⚠️ 真实但①也能拿到 —— ①里峰的 5 条 gate 自然归 `PeakDetector`/pk node。**不是③独有。** |

**⟹ 方案③相对方案①,没有剩下任何足以支撑引擎协议改动的优势。**

### 9.5 我接受「双向耦合 vs 单向流 + 记账副本」这个刻画

stream-consumer 说:pk「看着像双向耦合,实际是单向流 + 消费端一份记账副本」。**我同意,并且认为它的穷举没有漏**:跨域通道确实只有 C1(移除→去重闸)与 C2(elevation→supersede 锚)两条,C2 在消费端可完整复原(80/80 对称差 0 实证),C1 恒不触发。

**我还要补一条对它有利、它自己没提的**:方案①顺带**结构性消除**了背景 §2.6 记录的那个已知脆弱性 —— "登记集原则上不是 df 的纯函数"(因为去重闸读的 `_active_peaks` 会被突破逻辑改写)。在①里峰域独立,登记集**天然**是 df 的纯函数,不再需要靠"`breakout ⪯ peak` 才不分叉"这个参数条件来保证。这是①的一条真实结构收益,应当计入。

由此我接受它的结论:**拿 pk 这个实际可解耦的 case 去论证「框架缺少表达双向耦合的机制」,是不成立的。**

### 9.6 与方案②的关系(不变)
recursive-ref 实证:②覆盖 65.25%,漏 34.75%,其中 alive 是**公理级**不可覆盖(②要求"显示物必挂在出流 event 上",而 alive 的定义就是"没有 event 引用它")。这与 §8.2 的格 3/格 4 边界是同一件事。**②与③不是竞争关系**:lead 的三态方案里 broken 由 bo 的 `referenced_points` 记,那正是②的机制;需要补的是 alive 与 eaten 那两条记录的**载体**(pk 自己得出流)—— 而这个载体 ① 就能给。

### 9.7 数字更正(采纳 recursive-ref)
背景.md §一的「bb_v1 上 28.3% 的峰从未被突破」归属错了:28.21% 是 **bo_only(high/high)** 的 scan 窗口口径;bb_v1 真值是 **36.70%(全历史)/ 40.93%(scan 窗)**。
**对 §8.2 的判据只有加强**:既然 28.3% 出自 high/high 象限而该象限 eaten ≡ 0(定理 T1,skeptic 与 recursive-ref 独立同得),那么背景.md 里"图上完全不存在"的那批峰**成分是 100% 的 alive、一个 eaten 都不掺** —— "孤儿峰没有任何宿主可挂"这条判得比原以为的更干净。

### 9.8 一条我不越界、留给 lead 的渲染层问题
lead 的三态判据「含 bo owner → broken;≥2 个 pk owner → eaten」需要渲染层区分 owner 是哪个节点,而**节点名是 app 私有的**,这可能撞"渲染层类型无关"红线。recursive-ref 主张的四元 `(bar, price, label, style)` 没有这个问题但多一个协议字段。两种编码对引擎设计**无差别**,我只标出,不裁定。

## 10 · 更小的替代改动(诚实列出)

- **(S1) 用 `event_cls` 隐式类型路由,不加 `produces_stream`** —— diff 确实更小。**在新判据下否决理由变强了**:它造出的是第二个 ref(寄生的、不能独立存在的抽象),详见 §5.2。
- **(S2) 零引擎改动:两个 detector 共享一个显式"峰登记表"对象** —— 判死。① 是已被用户否决的 B′ 的变体;② **比 B′ 更糟**:两个 detector 之间无 `consumes_stream` 关系,执行顺序由 `detector_topo_order` 的 **node_id 字典序**破平决定(`_graph.py:109`),把正确性挂在节点命名上;③ 共享对象必然跨 `detect()` 调用存活,违反"状态不跨 detect 调用"(spec §1.2.4),多股连扫会串状态。

**结论:没有既更小又不倒退的改动。**

---

## 11 · 未核实清单

1. §3.4「兄弟一次填完对单流 app 观测等价」—— **论证充分但未跑测试**,实施时必须用现有全量测试确证。
2. §7.3 pk 节点关 C1(`c1_off` 第 6 源)后的剪枝损失量级 —— 未核实;仅在 pk 真参与求解时相关。
3. `_materialize_keys_of` 精度下降对前端参数面板的实际影响 —— 未核实(推测无害)。
4. §9.5 的渲染层类型无关性冲突 —— 我只标出,未裁定。
5. 队友数据(645→3714、72.9% vs 14.3%、1.4% 残差、1266→3613、alive 29.27%、卫星 5.60%)均**引用其实证,我未复跑**;§9.1 的机理我从代码独立核实(`breakout.py:300 / 317-320`)。

---

## 12 · 实施范围清单(不是 plan)

按依赖序:

1. `path2/core.py` —— Protocol 加 `produces`(TYPE_CHECKING 内);`stream_schema()`
2. `path2/runner.py` —— `_tagged` / `run_bundle`;`run()` 保签名 + 多流显式拒绝;检查按流分桶
3. `path2/dag/nodes.py` —— `produces_stream` + 按 schema 反射 `event_cls`
4. `path2/dag/spec.py` —— 两处校验改读 node 级 `event_cls`;子结构死字段;禁自喂
5. `path2/dag/engine.py` —— `run_streams`(bundle + 兄弟一次填完 + 声明序标注)
6. `path2/stdlib/templates.py` —— `emit_multi` + `detect` 二分支
7. `path2/dag/gate_failure.py` —— `GateFailure.stream`
8. `path2_web/gate_collector.py` —— 路由表版 `attach_and_collect`
9. `path2_web/serialize.py` —— `debug_enabled_nodes` 改 node 级判据
10. `.claude/skills/tune-gates/multivar_core.py` —— 共享判据收窄 + 反转循环走 bundle(**必做**)

**建议单独立项(独立于 pk 与多流,自身有价值)**:`NodeSpec.solve: bool = True` + `bound_ids` 加判据 + 前端 level 门控对 `solve=False` 免疫(§7.3 根治级)。

`path2/dag/_solve.py`(除上面那条独立立项外)、`_reify.py`、`_graph.py`、`diagnose.py`、`result.py` —— **零改动**。

---

## 13 · 收敛判断:三条「框架缺失」候选,其实是两条

lead 列了三条候选,并问:补上第三条(一对多引用一等化)之后,pk 需求是不是就被覆盖了、多流和第三出口都不必做?

### 13.1 先合并:候选二与候选三是同一条

| 提出者 | 表述 | 落地形态 |
|---|---|---|
| recursive-ref | 「成功产生的非事件结构中间物无可渲染通道」(`GateFailure` 只能表达失败且只上侧栏) | 让 `TrendSegment` 的 `seg_high/seg_low`、`Platform` 的 `max_high/min_low`、`ThrowbackEventV1` 的 `global_bottom`、`BurstEvent` 的 `max_bar_vol_ratio` argmax bar **带着坐标**出现在图上 |
| stream-consumer | 「一对多跨流 event 引用没有一等表达」(单值版已一等:`anchor_bo_id` + `TemporalEdge(anchor_field=)` + `spec.py:195-204` 校验;一对多退化成裸三元组,label 被 `chart.ts:187` 的 `/^pk(\d+)$/` 硬解析) | 把 `referenced_points` 从裸三元组升格为一等的「一对多引用」 |

**两者是同一条的两个说法**:它们指的都是「事件想指向若干个(坐标 / 别的事件),现在只能塞进一个裸元组字段,没有 schema、没有校验、label 被正则硬解析」。recursive-ref 从**谁想用**的角度描述,stream-consumer 从**抽象层级**的角度描述。合并后:

> **缺失 X:事件的「一对多外部引用」没有一等表达。**
> 现有消费者:BOEvent(唯一在用,且已破坏"前端不读 label"的约定)+ 至少 4 个想用而丢弃了坐标的(Trend/Platform/Throwback/Burst)。

### 13.2 正面回答 lead 的问题:补上 X **不能**覆盖 pk 需求

关键在 **alive**。

- broken:施动者是 bo,它引用被突破的峰 —— 只要 X 到位,**不需要峰是 event**(引用坐标即可)。
- eaten:施动者是吃掉它的那个 pk。**这一步就已经要求 pk 是 event 了** —— 除非引用的只是坐标,那"吃掉者"本身也得是个能挂引用的出流对象。
- alive:**没有任何施动者**。一个从未被突破、也没被吃掉的峰,在整个扫描期内不参与任何关系。X 是「引用」机制,而引用必须有 owner;alive 峰**没有 owner**。

recursive-ref 已经把这条证成公理级:②漏掉的 34.75% 里,alive(bb_v1 全历史 23.72% / scan 窗更高)是**结构上**不可能靠"挂在别人身上"显示的。

**⟹ pk 必须自己出流。X 不能替代这一步。**

### 13.3 那么 pk 出流走哪条?—— ①,不是③

pk 出流有两条路:①(独立 `PeakDetector` + `consumes_stream`)或 ③(多流)。§9 已经逐条撤回了③相对①的全部优势。**所以走①。**

### 13.4 收敛结论

> **pk 这个需求真正暴露的框架缺失是 X(事件的一对多外部引用没有一等表达),外加一步「pk 出流」——而出流用现有能力(方案①)就能做到,不需要新机制。**
>
> **多流(我的候选)不是 pk 暴露的缺失。** 它是一条真实的、可论证的概念空间空缺(§8:溯源证明它是实现产物、框架文档反而已认定多产出自洽、四格分类里 4b 确实空着),但它的**现有证例 = 0** —— 连 pk 都不是(§13.5)。

### 13.5 ★ 诚实更新:pk 自己也不属于格 4b

§8.2 的四格判据,最后一道题是「能不能被一个独立 detector 单独算出来」。三稿我把 pk 判进 4b(不能)。按 §9.1 核实后的结论,**这个判定是错的**:

- 登记集:能(Jaccard 1.0)
- broken:能(bo 集 80/80 全等)
- eaten:能(施加用户定义自带的优先级后 0/1998 不一致)
- 唯一不能的是 C1,而它在全部现有参数象限恒不触发

**⟹ pk 属格 4a(参数依赖的边界案例:只有 `breakout ≻ peak` 象限才落 4b),不是干净的 4b 证例。格 4b 的现有证例从 1 变成 0。**

这条更新让 §8.4「现有需求量 = 1」变成「**= 0**」。我在三稿里写过"这一格的价值全部押在概念完备上,没有经验冗余";四稿要把话说得更重:**它连一个边界证例都没有。**

### 13.5b ★ 五稿更正:我撤回得过头了 —— §六·五 给出的「单一真源」是一条我没找到的、更硬的优势

四稿我把③相对①的优势清成了零。读 `final_report.md` §六·五 后复核,**我漏了一条,而且它比我提出又撤回的那条更硬**:

我撤回的是「① 下 eaten 会显示错」——那条**确实是假的**(混淆矩阵 off-diagonal 0/1998),撤回正确,不反悔。
但真正的代价不在显示层,在**架构层**:**方案①-a 下,peak-peak supersede 判据必须在两个地方各存在一份。**

我核实了这条机制(代码 + skeptic 实证双证):
- **pk 域需要一份** —— 否则 eaten 关系没有载体(吃掉者得知道自己吃了谁)。
- **bo 域也必须有一份** —— 因为 `_active_peaks` 的内容直接决定突破循环遍历谁,进而决定 `pk_count` / `broken_peak_ids` / `peak_vol_max` / `peak_age_max` 四个 `BOEvent` 字段。bo 域若不做 peak-peak supersede,active 集是超集 ⟹ 同一根 bo 会突破更多峰 ⟹ bo 流不逐字等价。
  **skeptic 的 ①-c 实证正是这一条**:不重算 supersede 时 bo 流只有 **35/99** 逐字同(1546→1644);重算(①-a)才 99/99。
- 而且两份的**锚不同**(pk 域只有登记价,bo 域有 elevated 副本),不是简单复制 —— 是同一条语义判据的两个变体,必须永久同步演化。

**这正是用户当初否决 B′ 时点名的那类病**(判据一致性只能靠纪律维持),只是从"整套峰检测 + 全部参数"缩小到"一条 supersede 判据 + 一个阈值"。缩小了,没归零。

**⟹ 我在 §9.4 写的「没有剩下任何足以支撑引擎协议改动的优势」需要更正为:剩下一条 —— 单一真源(一份 supersede、一份参数、一份精确语义)。** 它比我原先主张的那条(语义正确性)弱,但它证伪不了 —— 因为它不是行为差异,是代码结构差异。

### 13.6 我的最终建议(五稿修订)

1. ~~**pk 需求:走方案①**~~ → **不再坚持。** 我接受 `final_report.md` 的③定案,理由有二:(a) 定案依据是 §2 的概念层论证 —— 那正是我自己的 §8(git 溯源 + 四格分类),我完整站在它后面;(b) §13.5b 那条「两份 supersede」是我漏掉的真实代价,补上后①③的天平不再是我四稿以为的一边倒。
   **但我要求把 §13.5 的诚实标注一并带进立项书**:pk 严格判定属格 4a、格 4b 现有证例 = 0。定案可以成立(用户明确说"没被使用 ≠ 不通用"),但立项书不该让读者以为 pk 是这个能力的证例 —— 它不是,它是**发现**这个缺失的契机。这两件事必须分开写。
2. **多流:若要做,独立立项**,论证只能建立在 §8(溯源 + 四格分类 + 抽象层级)之上,并在立项书里公开写明"现有证例 0"。我认为这样的立项是**可以成立**的(用户的判据明确说"没被使用 ≠ 不通用"),但它必须自己站着,不能靠 pk 抬。
3. **`NodeSpec.solve: bool = False` 仍然建议单独做**(§7.3):它跟多流、跟 pk 都无关,是纯引擎概念补完,并且立刻修掉 `bo_only` 加任何新孤立 node 就打穿评估路径(`serialize.py:363` 裸下标 KeyError)这个现存缺陷。
   采纳 stream-consumer 的意见:**不要**用 serialize 加一行 `continue` 止血 —— 那会静默吞 match、把将来真正的 bug 一起吞掉;从源头不产生这种 match 才对。
