# Path 2 stdlib 使用文档 — Chain / Dag / Kof / Neg + PatternMatch

> 完成日期:2026-05-19
> 目标:看完能用 stdlib 标准 PatternDetector 声明"事件间时序形态",并正确读 `PatternMatch`
> 配套:协议层心智见 `path2_tutorial.md`;协议层 API 见 `path2_api_reference.md`(本文是其 stdlib 续篇);算法权威见 `docs/research/path2_algo_core_redesign.md`

---

## 0. 定位 — stdlib 解决什么,不解决什么

协议层教你**手写** Detector 把"串行依次发生的事件"串起来(tutorial §4/§5/§6)。当形态是**纯时序约束的多流匹配**(`a→b→c`、DAG、k 选 n、链中禁出现 X)时,这套样板高频且易错——stdlib 把它**沉淀成带最优实现的标准件**:

```mermaid
flowchart LR
    decl["你写:edges(TemporalEdge 列表)<br/>+ 每个标签一条事件流"]
    pd["stdlib PatternDetector<br/>Chain / Dag / Kof / Neg<br/>(LEF-DFS 核心)"]
    pm["统一产出 PatternMatch<br/>children / role_index / pattern_label"]
    decl -->|构造期绑定| pd -->|run(detector)| pm
```

**心智模型不变**:你仍然"想清楚事件分层 → **声明**事件间时序约束 → 让消费者跑"。区别只是**声明仍由你写,执行交给 stdlib**(协议层只定 schema,不绑实现)。

stdlib **不提供**:任何 Event 子类(领域字段使用方私有,不可预沉淀)、"窗口内 ≥N 个"这类滑动动态计数 detector(`Kof` 是 k-of-n 边松弛,成员数恒 = 标签数,**不覆盖**滑动计数;仍按 tutorial §6 / §8.3 手写)。

四者 + `PatternMatch` 经 `path2/__init__` 出口:

```python
from path2 import Chain, Dag, Kof, Neg, TemporalEdge, PatternMatch, run
```

---

## 1. 公共结构 — 四个 Detector 长一个样

```python
Chain(*positional_streams, edges, key=None, strict_key=False,
      label=None, anchoring="earliest-feasible", **named_streams)
```

- `edges`(**keyword-only,必填**):`List[TemporalEdge]`,声明标签间时序边。
- 流的三种给法(标签解析,见 §3):位置参 / `key` 函数 / 具名 kwarg。
- `label`:本次匹配的 `pattern_label`,默认 `"chain"/"dag"/"kof"/"neg"`;**不得含 `#`**(它是 event_id 消歧分隔符)→ 构造期 `ValueError`。
- `anchoring`:Chain/Dag/Neg 仅支持 `"earliest-feasible"`,Kof 仅支持 `"non-overlapping-greedy"`;传非默认值 → 构造期 `ValueError`(冻结面)。
- 流在**构造期绑定**;`detect(source=None)` 忽略 `source`。**驱动方式**:

```python
matches = list(run(detector))      # 推荐:run() 加跨事件安全网
# 或 matches = list(detector.detect())   # 裸驱动亦合法
```

`TemporalEdge`(协议层,见 api_reference §1.3)回顾:`gap = later.start_idx − earlier.end_idx`;命中要求 `min_gap ≤ gap ≤ max_gap`;`min_gap` 默认 `0`、`max_gap` 默认 `math.inf`;`min_gap<0` 或 `min_gap>max_gap` → `TemporalEdge` 构造期 `ValueError`。`earlier`/`later` 是**声明期端点标签,不是 event_id**。

---

## 2. Chain — 线性链 `a→b→c`

最常用:严格一条线,每个标签恰好一个成员,按序首尾相接。

```python
from path2 import Chain, TemporalEdge, run

edges = [
    TemporalEdge(earlier="bo",   later="pull", min_gap=1, max_gap=10),
    TemporalEdge(earlier="pull", later="relaunch", min_gap=1, max_gap=20),
]
chain = Chain(
    bo=bo_stream,             # 具名流:kwarg 名 = 标签名
    pull=pullback_stream,
    relaunch=relaunch_stream,
    edges=edges,
    label="bo_pull_relaunch",
)
for m in run(chain):          # m: PatternMatch
    print(m.event_id, m.role_index["bo"].start_idx)
```

**构造期校验**(`validate_chain`,违反即 `ValueError`):必须无环;每节点入度/出度 ≤ 1;恰好一个源、一个汇;全图连通。即 `edges` 必须真是一条线性路径。

复杂度:Chain 强制前沿割宽 `f=1` ⇒ **多项式 / 近线性**(headline)。

---

## 3. 标签解析三段优先级(四个 Detector 通用,易错)

`edges` 里的端点标签必须各自解析到一条事件流。优先级 **kwarg > key > 类名/pattern_label 默认**:

| 给法 | 写法 | 标签来源 |
|---|---|---|
| 具名流(最高优先) | `Chain(bo=s1, vol=s2, edges=...)` | kwarg 名 |
| `key` 函数 | `Chain(mixed_stream, edges=..., key=lambda e: e.kind)` | `key(ev)` 返回值,按端点集分桶 |
| 类名 / pattern_label 默认 | `Chain(bo_stream, vol_stream, edges=...)` | 流首个事件的类名(或其 `pattern_label`) |

硬规则(全部构造期 `ValueError`):

- `key` 与具名流(kwarg)**不可同时给**(互斥机制)。
- `key` 默认**宽松**:返回不在端点集的标签 → 丢弃该事件;`strict_key=True` → 改为报错。
- 位置参**空流**无法推断默认标签 → 报错。
- 两条位置参流类名相同 → 标签冲突,须改用 kwarg 显式命名。
- 任一端点标签解析不到来源流 → `edges 端点标签无法解析到事件流: [...]`。

> 嵌套复用(把上一层 `PatternMatch` 当下一层输入)时,**务必给 `label` 并用 kwarg 传**:`PatternMatch` 的默认标签取 `pattern_label`(非类名,因为四种都叫 `PatternMatch`,类名默认会全部撞一起)。

---

## 4. Dag — 任意 DAG(多入度 / 多出度 / 多分量)

链不够用时:`a→c, b→c`(汇合)、`a→b, a→c`(分叉),乃至多个互不连通的子 DAG(多弱连通分量 WCC)。

```python
edges = [
    TemporalEdge(earlier="a", later="c", max_gap=10),
    TemporalEdge(earlier="b", later="c", max_gap=10),   # a、b 都须先于 c
]
dag = Dag(a=sa, b=sb, c=sc, edges=edges, label="ab_then_c")
matches = list(run(dag))
```

**构造期校验**(`validate_dag`):无环;**拒绝度为 0 的孤立节点**(未被任何边引用);多 WCC 合法(逐 WCC 独立跑,按 `end_idx` 归并)。

复杂度(**诚实账**):Chain(`f=1`)近线性;**病态宽前沿 DAG 时间、空间同为指数**——这是 interval-CSP-over-DAG 的内在难度,显式承认,不是先前设想的"单调双指针 O(N) 永不回退"(那条已被实现轮证伪)。日常 DAG 通常远不到病态。

---

## 5. Kof — k 选 n 边松弛

`n = edges 条数`,`k = 至少须满足的边数`。**全标签必在场**(no partial),但只要 ≥ k 条边满足即命中。

```python
edges = [
    TemporalEdge(earlier="x", later="a", max_gap=5),
    TemporalEdge(earlier="x", later="b", max_gap=5),
    TemporalEdge(earlier="x", later="c", max_gap=5),
]
kof = Kof(x=sx, a=sa, b=sb, c=sc, edges=edges, k=2, label="x_then_2of3")
matches = list(run(kof))
```

**构造期校验**(`validate_kof`):端点标签数 ≥ 2;`1 ≤ k ≤ 边数`;**必须单 WCC**(跨 WCC 的 k-of-n 无明确语义)。

复杂度:时间在**标签数维度诚实指数**(松弛无窗口剪枝,**常态**如此,非仅病态)——这是 k-of-n 放松剪枝的内在代价。

锚定 `non-overlapping-greedy`:"greedy" 指**生产循环按全成员非重叠贪进**;成员选择本身是**枚举/回溯**,不是贪心单选。

---

## 6. Neg — 正向子图 + 否定窗口("中间不能出现 X")

`edges` 是正向子图(按 DAG 校验),`forbid`(**keyword,必填**)是若干否定边。

```python
forward = [TemporalEdge(earlier="bo", later="relaunch", max_gap=30)]
forbid  = [TemporalEdge(earlier="bo", later="bad", min_gap=1, max_gap=30)]
neg = Neg(
    bo=sbo, relaunch=srelaunch,
    bad=[],                       # 否定流:即使无事件也须显式传(可空列表)
    edges=forward, forbid=forbid,
    label="bo_relaunch_no_bad",
)
matches = list(run(neg))          # bo→relaunch 且其间无 bad 才产出
```

要点:

- **端点角色靠成员资格识别**(与 `earlier/later` 声明方向无关):forbid 边上 ∈ `forward.nodes` 的端点 = 正向锚,∉ 的 = 否定标签。每条 forbid 边须**恰好一端**∈正向子图(XOR);两端皆∈或皆∉ → 构造期 `ValueError`。
- 否定标签流**必须以 kwarg 显式传入**(可空 `bad=[]`);完全漏传 → 构造期 `missing` 报错(有意:打错 forbid 标签名当场暴露)。
- gap 按 forbid 边声明方向原样代入 §1.3.1。`never_before`(`min_gap=0`)含 `gap=0`;想严格"之前"用 `min_gap=1`。
- 同标签不可既是正向成员又是否定条件(`validate_neg` 拒绝)。
- **否定标签结构性不进 `children`/`role_index`**(N 不在正向 edges,LEF-DFS 定义域不含 N)。
- 多条 forbid **合取**;否定流为空 ⇒ 该 forbid 放行。
- 缓冲继承正向:Chain 正向 ⇒ 零缓冲;Dag(多 WCC)正向 ⇒ ≤(p−1)。

---

## 7. 读 `PatternMatch` — 四种 Detector 的统一产出

`PatternMatch` 是 frozen `Event` 子类,自带协议层 `event_id / start_idx / end_idx`,再加三字段:

| 字段 | 类型 | 含义 |
|---|---|---|
| `children` | `tuple[Event, ...]` | 全部命中成员,**按 `start_idx` 升序**(否定标签不在内) |
| `role_index` | `Mapping[str, Event] \| None` | `标签 → 该标签命中的唯一 `Event``(四个 Detector 结构性每标签单成员;否定标签不在内) |
| `pattern_label` | `str` | 你构造时给的 `label`(默认 `chain/dag/kof/neg`);解嵌套用它替代类名默认 |

不变式(`RUNTIME_CHECKS` 开时强制,违反 `ValueError`):`children` 按 `start_idx` 升序;`role_index` 值集合 == `children` 集合(两视图不漂移)。

```python
for m in run(chain):
    bo   = m.role_index["bo"]             # 标签取该标签命中的 Event
    span = (m.start_idx, m.end_idx)       # 匹配整体区间
    members = m.children                  # 按 start_idx 升序
```

`event_id`:无条件 `base = f"{label}_{start}_{end}"`,撞则 `base#<n>` 消歧——**单 run 内唯一**(协议 §1.1.1),但 `#<seq>` 使其**跨 run 不稳定**;`pattern_label` 不得含 `#`。

`run(detector)` 在产出上加跨事件网:必是 `Event`、`end_idx` 升序、`event_id` 单 run 唯一(`resolve_labels` 已把各流按 `end_idx` 升序物化,产出天然升序)。生产环境可用 `set_runtime_checks(False)` 整体关掉走零开销直通。

---

## 8. 选型速查

| 形态 | 用 | 关键参数 |
|---|---|---|
| 线性链 `a→b→c` | `Chain` | `edges` 须线性(单源单汇,度≤1) |
| 多入度/分叉/多分量 | `Dag` | `edges` 无环、无孤立节点 |
| n 条边里 ≥k 条满足 | `Kof` | `k`(1≤k≤n)、单 WCC |
| 正向 + "中间禁出现 X" | `Neg` | `forbid` 非空、否定流必传(可空) |
| **窗口内 ≥N 个同类**(滑动计数) | ❌ 无标准件 | 按 tutorial §6 / §8.3 手写 |

常见构造期 `ValueError` 速对:`anchoring` 非默认 / `label` 含 `#` / `key` 与 kwarg 同给 / 端点解析不到流 / Chain 非线性 / Dag 孤立节点 / Kof k 越界或多 WCC / Neg forbid 端点非 XOR 或否定流漏传。

---

## 9. 降级 escape hatch — 标准件不够用时

stdlib 覆盖不到时,**协议层永远是兜底**:

- **简单 `A→B→C`**:不必上 `Chain`,直接嵌套 `Before` 算子(无需 `TemporalEdge`),见 tutorial §4。
- **带内部状态的多阶段确认**(FSM、buffer):手写 Detector,顺序由 detect() 内状态机强制,见 tutorial §5。
- **窗口内滑动计数 / 聚合**:手写聚合 Detector,顺序 = 对 `start_idx/end_idx` 的算术,见 tutorial §6。
- **自定义按 edges 校验**:自写 Detector 接受 `edges: List[TemporalEdge]`,内部按 §1.3.1 gap 公式逐对校验后 yield。

理解协议层底盘是用好 stdlib 与必要时降级的前提——本文的标准件与 tutorial 的手写法**思维模型完全一致**,只是"执行"换了归属。

---

## 10. 指针

- 协议层心智 / 手写法:`docs/path2/path2_tutorial.md`
- 协议层 API(含 `TemporalEdge` 完整条目):`docs/path2/path2_api_reference.md`
- 算法权威(LEF-DFS §1-9 / Kof §10 / Neg §11,复杂度诚实账):`docs/research/path2_algo_core_redesign.md`
- stdlib 设计稿(含"Kof 不覆盖滑动计数"写回横幅):`docs/superpowers/specs/2026-05-17-path2-4-stdlib-templates-design.md`
- 规格:`docs/research/path2_spec.md` §7.1(stdlib 不允许用户自写 PatternDetector)
