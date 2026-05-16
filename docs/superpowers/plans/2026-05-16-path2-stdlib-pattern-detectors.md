# Path 2 #3 stdlib PatternDetector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `path2/stdlib/` 落地消费 `TemporalEdge` 声明的四个标准 PatternDetector(`Chain`/`Dag`/`Kof`/`Neg`)+ 统一产出类 `PatternMatch`,用户只写声明。

**Architecture:** 四 Detector = 一个核心(标签解析 → edges 拓扑构建 → 约束推进)的四种约束形态。约束推进核心 = **LEF-DFS**(`docs/research/path2_algo_core_redesign.md` 权威;INV-A/B/C 三态分离 + 前沿割记忆 + start-first key;**取代原失实的"单调双指针 O(ΣN) 永不回退"**)。Chain = Dag 加严线性校验的退化特例(结构 `f=1` ⇒ 多项式/近线性),二者共用 LEF-DFS 核心;Kof = 滑窗计数 + 有界缓冲;Neg = 正向子图(复用 LEF-DFS)+ forbid 谓词过滤。复杂度诚实账:有界前沿多项式,病态宽前沿 DAG 时间空间同指数(redesign §5)。协议层(`path2/`)与 spec 零改动。

**Tech Stack:** Python 3 stdlib(`dataclasses`),`pytest`,`uv run`。无第三方依赖。

设计依据:`docs/superpowers/specs/2026-05-16-path2-stdlib-pattern-detectors-design.md`(下称 design)。读 design §1~§6 即可理解每个任务的为什么。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `path2/stdlib/__init__.py` | stdlib 公开出口(`Chain`/`Dag`/`Kof`/`Neg`/`PatternMatch`) |
| `path2/stdlib/_ids.py` | `default_event_id(kind,s,e)` 内联桩(契约 `(str,int,int)->str`;#4 落地后替换,签名冻结) |
| `path2/stdlib/pattern_match.py` | `PatternMatch(Event)` 产出类 + 构造期一致性校验 |
| `path2/stdlib/_labels.py` | 三段标签解析(kwarg > key > 类名/pattern_label 默认)+ 冲突报错 |
| `path2/stdlib/_graph.py` | edges → 有向图 + 逐 Detector 拓扑静态校验(Chain 线性 / Dag 环检测 / Kof k 范围 / Neg forbid) |
| `path2/stdlib/_advance.py` | earliest-feasible Dag 推进核心 + Kof 滑窗 + Neg forbid 过滤 |
| `path2/stdlib/detectors.py` | `Chain`/`Dag`/`Kof`/`Neg` 公开类,拼装上述件 |
| `path2/__init__.py` | 追加 stdlib 出口 |
| `tests/path2/stdlib/` | 各件单测 + 集成 |

**已锁定的 plan 决策**(design §8 留给 plan 的项):
- 模块按职责切分如上(非单文件)。
- `anchoring` 参数:#3 **只实现各 Detector 的 design 默认锚定**;参数存在用于前向兼容,传入非默认值 → `ValueError`(YAGNI,API 形状稳定)。
- key 严格/宽松:参数名 `strict_key: bool = False`(默认宽松,design §1.2)。
- 异常文案:各任务给出确切字符串。
- `detect(self, source=None)`:流在构造期绑定,`detect` 忽略 `source`;由 `run(detector)`(无 source)驱动。这与 `runner.run(detector, *source)` 兼容(`*source` 为空)。

---

## Task 0: 准备 stdlib 包骨架

**Files:**
- Create: `path2/stdlib/__init__.py`
- Create: `tests/path2/stdlib/__init__.py`

- [ ] **Step 1: 建空包**

`path2/stdlib/__init__.py`:

```python
"""Path 2 stdlib:消费 TemporalEdge 声明的标准 PatternDetector。

用户只写声明(edges + 每标签一条事件流),stdlib 跑最优实现。
公开符号在各件实现后于本文件末尾追加导出。
"""
```

`tests/path2/stdlib/__init__.py`:(空文件)

- [ ] **Step 2: 验证可导入**

Run: `uv run python -c "import path2.stdlib"`
Expected: 无输出,退出码 0

- [ ] **Step 3: Commit**

```bash
git add path2/stdlib/__init__.py tests/path2/stdlib/__init__.py
git commit -m "feat(path2-stdlib): 包骨架"
```

---

## Task 1: `default_event_id` 内联桩

**Files:**
- Create: `path2/stdlib/_ids.py`
- Test: `tests/path2/stdlib/test_ids.py`

- [ ] **Step 1: 写失败测试**

`tests/path2/stdlib/test_ids.py`:

```python
from path2.stdlib._ids import default_event_id


def test_format_kind_start_end():
    assert default_event_id("chain", 3, 7) == "chain_3_7"


def test_single_bar():
    assert default_event_id("vc", 5, 5) == "vc_5_5"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/stdlib/test_ids.py -q`
Expected: FAIL(`ModuleNotFoundError: path2.stdlib._ids`)

- [ ] **Step 3: 实现**

`path2/stdlib/_ids.py`:

```python
"""默认 event_id 生成器(#3/#4 共享件的 #3 内联桩)。

契约:(kind:str, start_idx:int, end_idx:int) -> str,返回 f"{kind}_{start}_{end}"。
#4 落地共享件后替换本桩,签名冻结不变 → 零改 #3。
"""
from __future__ import annotations


def default_event_id(kind: str, start_idx: int, end_idx: int) -> str:
    return f"{kind}_{start_idx}_{end_idx}"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/path2/stdlib/test_ids.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add path2/stdlib/_ids.py tests/path2/stdlib/test_ids.py
git commit -m "feat(path2-stdlib): default_event_id 内联桩"
```

---

## Task 2: `PatternMatch` 产出类

design §2。frozen Event 子类,字段 `children`/`role_index`/`pattern_label`;构造期一致性校验(role_index 扁平化集合 == children 集合;children 与各 tuple 按 start_idx 升序)。

**Files:**
- Create: `path2/stdlib/pattern_match.py`
- Test: `tests/path2/stdlib/test_pattern_match.py`

- [ ] **Step 1: 写失败测试**

`tests/path2/stdlib/test_pattern_match.py`:

```python
from dataclasses import dataclass

import pytest

from path2.core import Event
from path2.stdlib.pattern_match import PatternMatch


@dataclass(frozen=True)
class _A(Event):
    pass


def _a(s, e=None):
    e = s if e is None else e
    return _A(event_id=f"a_{s}_{e}", start_idx=s, end_idx=e)


def test_construct_ok_and_role_index_tuple():
    a1, a2 = _a(1), _a(3)
    m = PatternMatch(
        event_id="chain_1_3",
        start_idx=1,
        end_idx=3,
        children=(a1, a2),
        role_index={"A": (a1,), "B": (a2,)},
        pattern_label="chain",
    )
    assert m.role_index["A"] == (a1,)
    assert m.children == (a1, a2)
    assert m.pattern_label == "chain"


def test_children_must_be_start_idx_ascending():
    a1, a2 = _a(1), _a(3)
    with pytest.raises(ValueError):
        PatternMatch(
            event_id="x", start_idx=1, end_idx=3,
            children=(a2, a1),  # 逆序
            role_index={"A": (a1,), "B": (a2,)},
            pattern_label="chain",
        )


def test_role_index_flatten_must_equal_children():
    a1, a2 = _a(1), _a(3)
    with pytest.raises(ValueError):
        PatternMatch(
            event_id="x", start_idx=1, end_idx=3,
            children=(a1,),                       # 少了 a2
            role_index={"A": (a1,), "B": (a2,)},
            pattern_label="chain",
        )


def test_each_role_tuple_internally_ascending():
    a1, a2 = _a(1), _a(3)
    with pytest.raises(ValueError):
        PatternMatch(
            event_id="x", start_idx=1, end_idx=3,
            children=(a1, a2),
            role_index={"A": (a2, a1)},           # tuple 内逆序
            pattern_label="chain",
        )
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/stdlib/test_pattern_match.py -q`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 实现**

`path2/stdlib/pattern_match.py`:

```python
"""PatternMatch:4 种 PatternDetector 的统一产出 Event 子类(design §2)。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Tuple

from path2 import config
from path2.core import Event


@dataclass(frozen=True)
class PatternMatch(Event):
    # 协议层继承:event_id, start_idx, end_idx
    children: Tuple[Event, ...] = ()
    role_index: Mapping[str, Tuple[Event, ...]] = None  # 标签 -> 命中实例(恒 tuple)
    pattern_label: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not config.RUNTIME_CHECKS:
            return
        ri = self.role_index or {}
        # 各 role tuple 必须按 start_idx 升序
        for label, tup in ri.items():
            if list(tup) != sorted(tup, key=lambda e: e.start_idx):
                raise ValueError(
                    f"role_index['{label}'] 未按 start_idx 升序"
                )
        # children 必须按 start_idx 升序(§3.3)
        if list(self.children) != sorted(
            self.children, key=lambda e: e.start_idx
        ):
            raise ValueError("children 未按 start_idx 升序")
        # role_index 扁平化集合 == children 集合(两视图不漂移)
        flat = {id(e) for tup in ri.values() for e in tup}
        if flat != {id(e) for e in self.children}:
            raise ValueError(
                "role_index 扁平化集合 != children 集合"
            )
```

注:`role_index` 默认 `None` 仅为满足 dataclass 默认值要求;`__post_init__` 用 `self.role_index or {}` 归一。frozen Event 已由协议层在装饰期强制。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/path2/stdlib/test_pattern_match.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add path2/stdlib/pattern_match.py tests/path2/stdlib/test_pattern_match.py
git commit -m "feat(path2-stdlib): PatternMatch 产出类 + 一致性校验"
```

---

## Task 3: 三段标签解析

design §1.2。优先级:具名流(kwarg)> key 函数 > 类名/pattern_label 默认。冲突构造期 `ValueError`。

**Files:**
- Create: `path2/stdlib/_labels.py`
- Test: `tests/path2/stdlib/test_labels.py`

- [ ] **Step 1: 写失败测试**

`tests/path2/stdlib/test_labels.py`:

```python
from dataclasses import dataclass

import pytest

from path2.core import Event
from path2.stdlib._labels import resolve_labels


@dataclass(frozen=True)
class A(Event):
    pass


@dataclass(frozen=True)
class B(Event):
    pass


def _mk(cls, s):
    return cls(event_id=f"{cls.__name__}_{s}", start_idx=s, end_idx=s)


def test_named_streams_bind_by_kwarg():
    sa = [_mk(A, 1), _mk(A, 2)]
    sb = [_mk(B, 3)]
    out = resolve_labels(
        positional=(), named={"X": sa, "Y": sb},
        key=None, strict_key=False, endpoint_labels={"X", "Y"},
    )
    assert [e.start_idx for e in out["X"]] == [1, 2]
    assert [e.start_idx for e in out["Y"]] == [3]


def test_positional_default_label_is_classname():
    out = resolve_labels(
        positional=([_mk(A, 1)], [_mk(B, 2)]), named={},
        key=None, strict_key=False, endpoint_labels={"A", "B"},
    )
    assert out["A"][0].start_idx == 1
    assert out["B"][0].start_idx == 2


def test_positional_same_classname_conflict_raises():
    with pytest.raises(ValueError, match="同类名"):
        resolve_labels(
            positional=([_mk(A, 1)], [_mk(A, 2)]), named={},
            key=None, strict_key=False, endpoint_labels={"A"},
        )


def test_key_function_buckets_merged_stream():
    merged = [_mk(A, 1), _mk(B, 2), _mk(A, 3)]
    out = resolve_labels(
        positional=(merged,), named={},
        key=lambda e: type(e).__name__, strict_key=False,
        endpoint_labels={"A", "B"},
    )
    assert [e.start_idx for e in out["A"]] == [1, 3]
    assert [e.start_idx for e in out["B"]] == [2]


def test_key_loose_drops_unknown_label():
    merged = [_mk(A, 1), _mk(B, 2)]
    out = resolve_labels(
        positional=(merged,), named={},
        key=lambda e: type(e).__name__, strict_key=False,
        endpoint_labels={"A"},          # B 不在端点集
    )
    assert "B" not in out and [e.start_idx for e in out["A"]] == [1]


def test_key_strict_unknown_label_raises():
    merged = [_mk(A, 1), _mk(B, 2)]
    with pytest.raises(ValueError, match="未知标签"):
        resolve_labels(
            positional=(merged,), named={},
            key=lambda e: type(e).__name__, strict_key=True,
            endpoint_labels={"A"},
        )


def test_endpoint_label_unresolved_raises():
    with pytest.raises(ValueError, match="无法解析"):
        resolve_labels(
            positional=(), named={"X": [_mk(A, 1)]},
            key=None, strict_key=False, endpoint_labels={"X", "Y"},
        )


def test_patternmatch_default_label_uses_pattern_label():
    from path2.stdlib.pattern_match import PatternMatch

    pm = PatternMatch(
        event_id="chain_1_1", start_idx=1, end_idx=1,
        children=(_mk(A, 1),), role_index={"A": (_mk(A, 1),)},
        pattern_label="vol_buildup",
    )
    out = resolve_labels(
        positional=([pm],), named={},
        key=None, strict_key=False, endpoint_labels={"vol_buildup"},
    )
    assert out["vol_buildup"][0] is pm
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/stdlib/test_labels.py -q`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 实现**

`path2/stdlib/_labels.py`:

```python
"""三段标签解析(design §1.2)。kwarg > key > 类名/pattern_label 默认。"""
from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional, Set

from path2.core import Event


def _default_label(ev: Event) -> str:
    # PatternMatch 用 pattern_label 替代类名默认(design §2.2,解嵌套硬伤)
    pl = getattr(ev, "pattern_label", None)
    return pl if pl else type(ev).__name__


def resolve_labels(
    positional: Iterable[Iterable[Event]],
    named: Dict[str, Iterable[Event]],
    key: Optional[Callable[[Event], str]],
    strict_key: bool,
    endpoint_labels: Set[str],
) -> Dict[str, List[Event]]:
    """返回 {label: 物化列表(按 end_idx 升序)}。

    输入流本就 §1.2.2 end_idx 升序;此处物化并稳定排序兜底。
    """
    out: Dict[str, List[Event]] = {}

    # 1) 具名流(kwarg)最高优先
    for label, stream in named.items():
        out[label] = list(stream)

    pos = [list(s) for s in positional]

    if key is not None:
        # 2) key 函数:把所有 positional 事件按 key 分桶
        for stream in pos:
            for ev in stream:
                lab = key(ev)
                if lab not in endpoint_labels:
                    if strict_key:
                        raise ValueError(
                            f"key 返回未知标签 {lab!r}(不在 edges 端点集)"
                        )
                    continue  # 宽松:丢弃杂事件
                out.setdefault(lab, []).append(ev)
    else:
        # 3) 类名 / pattern_label 默认
        for stream in pos:
            if not stream:
                raise ValueError("positional 空流无法推断默认标签")
            lab = _default_label(stream[0])
            if lab in out:
                raise ValueError(
                    f"positional 流出现同类名标签 {lab!r} 冲突,"
                    f"请改用 kwarg 显式命名"
                )
            out[lab] = list(stream)

    # 端点必须全部解析到来源
    missing = endpoint_labels - set(out)
    if missing:
        raise ValueError(
            f"edges 端点标签无法解析到事件流: {sorted(missing)}"
        )

    # 稳定排序兜底(end_idx 升序)
    for lab in out:
        out[lab].sort(key=lambda e: e.end_idx)
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/path2/stdlib/test_labels.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add path2/stdlib/_labels.py tests/path2/stdlib/test_labels.py
git commit -m "feat(path2-stdlib): 三段标签解析"
```

---

## Task 4: edges 拓扑构建 + 逐 Detector 静态校验

design §3.0.1。

**Files:**
- Create: `path2/stdlib/_graph.py`
- Test: `tests/path2/stdlib/test_graph.py`

- [ ] **Step 1: 写失败测试**

`tests/path2/stdlib/test_graph.py`:

```python
import pytest

from path2.core import TemporalEdge
from path2.stdlib._graph import (
    build_graph,
    validate_chain,
    validate_dag,
    validate_kof,
    validate_neg,
    topo_order,
)


def test_build_graph_collects_nodes_and_adj():
    edges = [TemporalEdge("A", "B"), TemporalEdge("B", "C")]
    g = build_graph(edges)
    assert g.nodes == {"A", "B", "C"}
    assert g.indeg["A"] == 0 and g.indeg["C"] == 1
    assert g.outdeg["C"] == 0


def test_topo_order_linear():
    g = build_graph([TemporalEdge("A", "B"), TemporalEdge("B", "C")])
    assert topo_order(g) == ["A", "B", "C"]


def test_validate_chain_ok():
    validate_chain(build_graph([TemporalEdge("A", "B"), TemporalEdge("B", "C")]))


def test_validate_chain_branching_raises():
    g = build_graph([TemporalEdge("A", "B"), TemporalEdge("A", "C")])
    with pytest.raises(ValueError, match="线性路径"):
        validate_chain(g)


def test_validate_chain_cycle_raises():
    g = build_graph([TemporalEdge("A", "B"), TemporalEdge("B", "A")])
    with pytest.raises(ValueError, match="环"):
        validate_chain(g)


def test_validate_dag_ok_multi_indegree():
    g = build_graph([TemporalEdge("A", "C"), TemporalEdge("B", "C")])
    validate_dag(g)


def test_validate_dag_cycle_raises():
    g = build_graph([TemporalEdge("A", "B"), TemporalEdge("B", "A")])
    with pytest.raises(ValueError, match="环"):
        validate_dag(g)


def test_validate_kof_k_range():
    edges = [TemporalEdge("A", "B"), TemporalEdge("B", "C")]
    validate_kof(build_graph(edges), k=1, n_edges=2)
    with pytest.raises(ValueError, match="k"):
        validate_kof(build_graph(edges), k=3, n_edges=2)
    with pytest.raises(ValueError, match="k"):
        validate_kof(build_graph(edges), k=0, n_edges=2)


def test_validate_neg_requires_forbid_and_later_in_forward():
    fwd = build_graph([TemporalEdge("A", "B")])
    validate_neg(fwd, forbid=[TemporalEdge("N", "A")])  # later=A 在正向
    with pytest.raises(ValueError, match="至少需"):
        validate_neg(fwd, forbid=[])
    with pytest.raises(ValueError, match="正向子图"):
        validate_neg(fwd, forbid=[TemporalEdge("N", "Z")])  # Z 不在正向
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/stdlib/test_graph.py -q`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 实现**

`path2/stdlib/_graph.py`:

```python
"""edges → 有向图 + 逐 Detector 拓扑静态校验(design §3.0.1)。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set

from path2.core import TemporalEdge


@dataclass
class Graph:
    nodes: Set[str] = field(default_factory=set)
    adj: Dict[str, List[tuple]] = field(default_factory=dict)  # u -> [(v, edge)]
    indeg: Dict[str, int] = field(default_factory=dict)
    outdeg: Dict[str, int] = field(default_factory=dict)
    edges: List[TemporalEdge] = field(default_factory=list)


def build_graph(edges: List[TemporalEdge]) -> Graph:
    g = Graph(edges=list(edges))
    for e in edges:
        g.nodes.add(e.earlier)
        g.nodes.add(e.later)
    for n in g.nodes:
        g.adj.setdefault(n, [])
        g.indeg.setdefault(n, 0)
        g.outdeg.setdefault(n, 0)
    for e in edges:
        g.adj[e.earlier].append((e.later, e))
        g.outdeg[e.earlier] += 1
        g.indeg[e.later] += 1
    return g


def _has_cycle(g: Graph) -> bool:
    # Kahn 拓扑;无法削平则有环
    indeg = dict(g.indeg)
    q = [n for n in g.nodes if indeg[n] == 0]
    seen = 0
    while q:
        u = q.pop()
        seen += 1
        for v, _ in g.adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    return seen != len(g.nodes)


def topo_order(g: Graph) -> List[str]:
    if _has_cycle(g):
        raise ValueError("edges 检测到环,无法拓扑排序")
    indeg = dict(g.indeg)
    # 稳定:按字典序出队,保证可复现
    ready = sorted([n for n in g.nodes if indeg[n] == 0])
    order: List[str] = []
    while ready:
        u = ready.pop(0)
        order.append(u)
        for v, _ in sorted(g.adj[u]):
            indeg[v] -= 1
            if indeg[v] == 0:
                ready.append(v)
        ready.sort()
    return order


def _connected(g: Graph) -> bool:
    if not g.nodes:
        return True
    undirected: Dict[str, Set[str]] = {n: set() for n in g.nodes}
    for u in g.nodes:
        for v, _ in g.adj[u]:
            undirected[u].add(v)
            undirected[v].add(u)
    start = next(iter(g.nodes))
    stack, seen = [start], {start}
    while stack:
        x = stack.pop()
        for y in undirected[x]:
            if y not in seen:
                seen.add(y)
                stack.append(y)
    return len(seen) == len(g.nodes)


def validate_chain(g: Graph) -> None:
    if _has_cycle(g):
        raise ValueError("Chain edges 含环")
    for n in g.nodes:
        if g.indeg[n] > 1 or g.outdeg[n] > 1:
            raise ValueError(
                f"Chain 要求线性路径,节点 {n!r} 入/出度 >1"
            )
    sources = [n for n in g.nodes if g.indeg[n] == 0]
    sinks = [n for n in g.nodes if g.outdeg[n] == 0]
    if len(sources) != 1 or len(sinks) != 1:
        raise ValueError("Chain 要求线性路径,须恰好一个源一个汇")
    if not _connected(g):
        raise ValueError("Chain edges 不连通")


def validate_dag(g: Graph) -> None:
    if _has_cycle(g):
        raise ValueError("Dag 检测到环")


def validate_kof(g: Graph, k: int, n_edges: int) -> None:
    if len(g.nodes) < 2:
        raise ValueError("Kof edges 端点 label 数须 >= 2")
    if k < 1 or k > n_edges:
        raise ValueError(
            f"Kof k={k} 越界,须 1 <= k <= 边数({n_edges})"
        )


def validate_neg(forward: Graph, forbid: List[TemporalEdge]) -> None:
    if not forbid:
        raise ValueError(
            "Neg 至少需 1 条否定约束,否则等价 Chain/Dag"
        )
    for fe in forbid:
        if fe.later not in forward.nodes:
            raise ValueError(
                f"Neg 否定 edge 的 later={fe.later!r} 不在正向子图"
            )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/path2/stdlib/test_graph.py -q`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add path2/stdlib/_graph.py tests/path2/stdlib/test_graph.py
git commit -m "feat(path2-stdlib): edges 拓扑构建 + 逐 Detector 静态校验"
```

---

## Task 5: 约束推进核心 —— LEF-DFS(已按 redesign 重写)

> **⚠️ 本 Task 已被 `docs/research/path2_algo_core_redesign.md`(redesign)取代为权威。下方 Step 1–5 的"拓扑序+区间剪枝+源指针回溯"参考实现含 5 个根缺陷(C1 源-only 回溯不完整 / C2 多源只回溯首源 / C3 单 run event_id 重复 / C4 不健全 start_idx 单调假设 / I1 `.index` 值相等错位),经 agent team 3 轮对抗证伪推翻,SUPERSEDED —— 不得照抄。** 实现以本 OVERRIDE 块为准。

**目标**:把 `path2/stdlib/_advance.py` 实现为 redesign §3 的 **LEF-DFS** 核心(Dag 形态;Chain 是 `f=1` 退化特例,Task 6 复用)。

**权威算法**:redesign §3.1 散文 + §3.3 设计级伪代码 + §3.2 五步规范节点访问(C-ORDER / C-SCAN / C-KEY,**MUST**)。`gap = later.start_idx - earlier.end_idx`(协议 §1.3.1,不变)。`earliest-feasible := key=(start_idx, end_idx, position_in_S[L])` 字典序最小可行赋值(redesign §2.2)。

**实现必须遵守的不变式(redesign §3.4,三态分离,永不混淆)**:
- **INV-A** 逐节点访问的 scan 指针:每次节点访问对**当前消费前沿后缀做新鲜全后缀扫描**;**无 `start_idx` 早停**;**不跨 anchor / 不跨回溯携带**(修 C4 mode-i)。
- **INV-B** 持久消费指针 `ptr[L]`:整个 `detect()` 携带;产出后对**每个**用到标签 `ptr[L] = 被选实例的真实整数下标 + 1`(**全成员非重叠消费**);**绝不用 `.index()` / `__eq__`**——下标在搜索时即已知,直接携带(修 I1)。
- **INV-C** FAILED 前沿割记忆:**每个 LEF 调用内**有效,LEF 调用间**重置**,**不跨生产循环相继 LEF 携带**;签名 = 跨"已赋值→未赋值后缀"边的尾端 `end_idx` 集合;同签名 ⇒ 剩余可行域相同 ⇒ 健全剪。等-`end` 簇塌缩保留代表 = 簇内 `key`(start,end,position)argmin,**且 admissibility 过滤 MUST 严格先于塌缩(C-ORDER)**。
- 回溯**到任意有 key-序后续 admissible 候选的节点**(不限源),修 C1/C2。
- `event_id`:**无条件、四 Detector 共享**的 `detect()`-局部 `seen_ids`;`base=f"{label}_{s}_{e}"`,撞则 `base#<n>`(n 从 1)。`pattern_label` 含 `#` → 构造期 `ValueError`(Task 6/7/8/9 各 `__init__`)。修 C3。

**Files:** Create/overwrite `path2/stdlib/_advance.py`;Test `tests/path2/stdlib/test_advance_dag.py`。

**TDD 验收锚(全部 pin 死,必须新增并通过;期望值取自 redesign §1 各 CRITICAL 的"修正后期望"+ §8.4 的 C1/A3 锚)**:

- [ ] **A-C1**(redesign §1 CRITICAL-1):`edges=[A→B(0,0), B→C(0,0)]`,`A=[ev(0,0)]`,`B=[ev(0,1),ev(0,3)]`,`C=[ev(3,4)]` → 产出 1 个 `PatternMatch`,`children=(A(0,0),B(0,3),C(3,4))`,`start_idx=0,end_idx=4`(旧码返回 `[]`)。
- [ ] **A-C2**(redesign §1 CRITICAL-2,**期望已修正**):`edges=[A→C(1,3), B→C(0,0)]`,`A=[ev(0,1),ev(1,3),ev(4,5)]`,`B=[ev(0,1),ev(1,1),ev(5,6)]`,`C=[ev(3,3),ev(3,6),ev(6,7)]` → 产出**恰 1 个** `PatternMatch`,`children=(A(1,3),B(5,6),C(6,7))`,`start=1,end=7`(旧码返回 `[]`;两个"地面真值赋值"共用 B(5,6)/C(6,7) 两成员,在 §3.4 INV-B / §6 Part D 全成员非重叠语义下仅产出 lex-min 那个——CHECK-3 的"2 个"是忽略非重叠的枚举隔离实验值,非生产序列;裁定见 redesign §1 CRITICAL-2 "修正后期望")。
- [ ] **A-C3**(redesign §1 CRITICAL-3):构造两个 `(s,e)` 相同但成员不同的匹配,经 `run(detector)` 不抛 `ValueError`,两 `event_id` 为 `{label}_{s}_{e}` 与 `{label}_{s}_{e}#1`。
- [ ] **A-C4**(redesign §1 CRITICAL-4 mode-i):`edges=[A→B(0,0)]`,`A=[ev(0,0)]`,`B=[ev(5,6),ev(0,7)]`(B 按 end_idx 升序 6,7;start 非单调 5,0)→ 产出 1 个,`children=(A(0,0),B(0,7))`,`start=0,end=7`(旧码 scan 早停返回 `[]`)。
- [ ] **A-I1**(redesign §1 IMPORTANT-1):某标签流含两个值相等事件、被选靠后那个 → 消费按真实下标推进,匹配集与不重复时结构一致(无重复/漏选)。
- [ ] **A-A3**(redesign §8.4 C-ORDER 锚):窗口 `[10,12]`,候选 `e1=(s5,e20)`(start 5∉[10,12])、`e2=(s11,e20)`(start 11∈[10,12]),等-end 簇。过滤先于塌缩 ⇒ 命中 `e2`;塌缩先于过滤会保留 `e1` 再被丢弃 ⇒ 丢匹配。断言命中 `e2`(同时鉴别 C-ORDER + C-KEY)。
- [ ] **A-C1key**(redesign §8.4 C1 锚):等-`end_idx` 簇内"输入序先遇者"≠"start-first key argmin",断言塌缩保留代表 = key argmin。
- [ ] **保留原 5 个 Dag 行为测试**(linear chain / max_gap violation / non-overlapping greedy 2 matches / multi-indegree intersection / yield end_idx ascending)——语义不变,仍须通过。

**实现步骤**:(1) 写上述全部验收锚 + 保留原 5 测为失败/回归测试;(2) 跑确认新锚失败(旧码 / 空实现);(3) 按 redesign §3 实现 LEF-DFS(伪代码见 redesign §3.3;`PRODUCE` 生产循环 + `LEF_DFS` 递归 + `FRONTIER_CUT_SIGNATURE` + `COLLAPSE_EQUAL_END_KEEP_KEYMIN`;`_emit` 用共享 `seen_ids`+`#seq`;消费携带整数下标);(4) 跑 `uv run pytest tests/path2/stdlib/test_advance_dag.py -q` 全绿,再 `uv run pytest tests/path2/ -q` 无回归;(5) Commit:`fix(path2-stdlib): Task 5 约束推进核心重写为 LEF-DFS(修 C1-4/I1,redesign §3)`。

**复杂度自检**(redesign §5,写入实现 docstring):Chain `f=1` 多项式/近线性;病态宽前沿 DAG 时间空间同指数(诚实承认,非旧失实 O(ΣN))。

**以下 Step 1–5 为 SUPERSEDED 历史参考(旧缺陷算法),实现时忽略,仅供对照"为何被推翻":**

---

design §3.2 + §3.1(已作废)。核心算法:拓扑序 + 区间剪枝 + earliest-feasible + 非重叠贪心;`gap = later.start_idx - earlier.end_idx`(协议 §1.3.1)。Chain 复用此核心(Task 6)。

**Files:**
- Create: `path2/stdlib/_advance.py`
- Test: `tests/path2/stdlib/test_advance_dag.py`

- [ ] **Step 1: 写失败测试**

`tests/path2/stdlib/test_advance_dag.py`:

```python
from dataclasses import dataclass

from path2.core import Event, TemporalEdge
from path2.stdlib._graph import build_graph
from path2.stdlib._advance import advance_dag


@dataclass(frozen=True)
class _E(Event):
    pass


def ev(s, e=None):
    e = s if e is None else e
    return _E(event_id=f"e_{s}_{e}", start_idx=s, end_idx=e)


def test_linear_chain_earliest_feasible():
    # A->B->C, gap=later.start - earlier.end, min_gap=1
    edges = [TemporalEdge("A", "B", min_gap=1), TemporalEdge("B", "C", min_gap=1)]
    g = build_graph(edges)
    streams = {
        "A": [ev(0)],
        "B": [ev(2)],          # 2-0=2 >=1 ok
        "C": [ev(5)],          # 5-2=3 >=1 ok
    }
    matches = list(advance_dag(g, streams, label="chain"))
    assert len(matches) == 1
    m = matches[0]
    assert m.start_idx == 0 and m.end_idx == 5
    assert [c.start_idx for c in m.children] == [0, 2, 5]
    assert m.role_index["A"][0].start_idx == 0


def test_max_gap_violation_no_match():
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=2)]
    g = build_graph(edges)
    streams = {"A": [ev(0)], "B": [ev(10)]}  # 10-0=10 > 2
    assert list(advance_dag(g, streams, label="x")) == []


def test_non_overlapping_greedy_two_matches():
    edges = [TemporalEdge("A", "B", min_gap=1)]
    g = build_graph(edges)
    streams = {
        "A": [ev(0), ev(10)],
        "B": [ev(2), ev(12)],
    }
    ms = list(advance_dag(g, streams, label="p"))
    assert [(m.start_idx, m.end_idx) for m in ms] == [(0, 2), (10, 12)]


def test_multi_indegree_intersection():
    # A->C, B->C ; C 须同时满足两前驱 gap
    edges = [
        TemporalEdge("A", "C", min_gap=1, max_gap=10),
        TemporalEdge("B", "C", min_gap=1, max_gap=3),
    ]
    g = build_graph(edges)
    streams = {
        "A": [ev(0)],          # C.start - 0 in [1,10]
        "B": [ev(5)],          # C.start - 5 in [1,3] -> C.start in [6,8]
        "C": [ev(7)],          # 7 in [1,10] and 7-5=2 in [1,3] ok
    }
    ms = list(advance_dag(g, streams, label="dag"))
    assert len(ms) == 1 and ms[0].end_idx == 7


def test_yield_order_end_idx_ascending():
    edges = [TemporalEdge("A", "B", min_gap=1)]
    g = build_graph(edges)
    streams = {"A": [ev(0), ev(3)], "B": [ev(1), ev(4)]}
    ms = list(advance_dag(g, streams, label="p"))
    ends = [m.end_idx for m in ms]
    assert ends == sorted(ends)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/stdlib/test_advance_dag.py -q`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 实现**

`path2/stdlib/_advance.py`:

```python
"""约束推进核心(design §3)。

advance_dag:earliest-feasible + 非重叠贪心 + 区间剪枝,O(ΣN·d)。
Chain 复用 advance_dag(Task 6 加严线性校验后调用)。
Kof / Neg 在后续 Task 追加。
"""
from __future__ import annotations

from typing import Dict, Iterator, List

from path2.core import Event, TemporalEdge
from path2.stdlib._graph import Graph, topo_order
from path2.stdlib._ids import default_event_id
from path2.stdlib.pattern_match import PatternMatch


def _preds(g: Graph) -> Dict[str, List[tuple]]:
    """label -> [(pred_label, edge)]。"""
    pred: Dict[str, List[tuple]] = {n: [] for n in g.nodes}
    for u in g.nodes:
        for v, e in g.adj[u]:
            pred[v].append((u, e))
    return pred


def _emit(assign: Dict[str, Event], label: str) -> PatternMatch:
    members = sorted(assign.values(), key=lambda e: e.start_idx)
    s = members[0].start_idx
    end = max(e.end_idx for e in members)
    return PatternMatch(
        event_id=default_event_id(label, s, end),
        start_idx=s,
        end_idx=end,
        children=tuple(members),
        role_index={lab: (assign[lab],) for lab in assign},
        pattern_label=label,
    )


def advance_dag(
    g: Graph,
    streams: Dict[str, List[Event]],
    label: str,
) -> Iterator[PatternMatch]:
    order = topo_order(g)
    pred = _preds(g)
    ptr: Dict[str, int] = {n: 0 for n in g.nodes}
    sources = [n for n in order if g.indeg[n] == 0]

    while True:
        # 起锚:所有 source 取各自 ptr 处实例;任一耗尽则结束
        if any(ptr[s] >= len(streams[s]) for s in sources):
            return
        assign: Dict[str, Event] = {}
        failed = False
        for v in order:
            lst = streams[v]
            ps = pred[v]
            if not ps:  # 源节点:取当前指针实例
                if ptr[v] >= len(lst):
                    failed = True
                    break
                assign[v] = lst[ptr[v]]
                continue
            # 多入度:start 下界 = max(pred.end + min_gap),上界 = min(pred.end + max_gap)
            lo = max(assign[u].end_idx + e.min_gap for u, e in ps)
            hi = min(assign[u].end_idx + e.max_gap for u, e in ps)
            if lo > hi:
                failed = True
                break
            i = ptr[v]
            while i < len(lst) and lst[i].start_idx < lo:  # 单调右移
                i += 1
            ptr[v] = i  # 指针永不回退(earliest-feasible + min_gap 单调)
            if i >= len(lst) or lst[i].start_idx > hi:
                failed = True
                break
            assign[v] = lst[i]

        if not failed:
            yield _emit(assign, label)
            # 非重叠:所有用到的标签指针跳到已用实例之后
            for lab, e in assign.items():
                used = streams[lab].index(e, ptr[lab])
                ptr[lab] = used + 1
        else:
            # earliest-feasible 回溯:推进最早的仍有备选的源指针 +1,重试
            advanced = False
            for s in sources:
                if ptr[s] + 1 <= len(streams[s]):
                    ptr[s] += 1
                    advanced = True
                    break
            if not advanced:
                return
```

注:`ptr[lab] = used + 1` 用 `index(e, ptr[lab])` 定位已用实例的真实下标(指针推进后 `ptr[lab]` ≤ 该下标)。源节点匹配成功后也在此统一跳过(`assign` 含所有 label)。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/path2/stdlib/test_advance_dag.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add path2/stdlib/_advance.py tests/path2/stdlib/test_advance_dag.py
git commit -m "feat(path2-stdlib): Dag earliest-feasible 推进核心"
```

---

## Task 6: `Chain` 公开类(Dag + 线性加严)

> **redesign 修正注**:Chain 复用 Task 5 的 **LEF-DFS** 核心(非旧"单调双指针")。`validate_chain` 强制 `p=1`(单源单汇连通)⇒ 结构 `f=1` ⇒ 多项式/近线性 + literally 零缓冲(redesign §6)。构造期新增:`pattern_label` 含 `#` → `ValueError`(`#` 是 §1.2.4 消歧分隔符,redesign §7)。`anchoring` 非默认值 → `ValueError`(原 plan 决策不变)。下方 Step 参考代码若调用 `advance_dag`,以 Task 5 重写后的 LEF-DFS 签名为准。

design §3.1 + §4。Chain = Dag 推进(LEF-DFS)+ 构造期 `validate_chain` + `pattern_label` `#` 校验。

**Files:**
- Create: `path2/stdlib/detectors.py`
- Test: `tests/path2/stdlib/test_chain.py`

- [ ] **Step 1: 写失败测试**

`tests/path2/stdlib/test_chain.py`:

```python
from dataclasses import dataclass

import pytest

from path2 import run
from path2.core import Event, TemporalEdge
from path2.stdlib.detectors import Chain


@dataclass(frozen=True)
class _E(Event):
    pass


def ev(s, e=None):
    e = s if e is None else e
    return _E(event_id=f"e_{s}_{e}", start_idx=s, end_idx=e)


def test_chain_basic_named_streams():
    d = Chain(
        edges=[TemporalEdge("A", "B", min_gap=1)],
        A=[ev(0), ev(10)],
        B=[ev(2), ev(12)],
        label="ab",
    )
    ms = list(run(d))
    assert [(m.start_idx, m.end_idx) for m in ms] == [(0, 2), (10, 12)]
    assert all(m.pattern_label == "ab" for m in ms)
    assert ms[0].event_id == "ab_0_2"


def test_chain_branching_edges_rejected_at_construction():
    with pytest.raises(ValueError, match="线性路径"):
        Chain(
            edges=[TemporalEdge("A", "B"), TemporalEdge("A", "C")],
            A=[ev(0)], B=[ev(1)], C=[ev(2)],
        )


def test_chain_non_default_anchoring_rejected():
    with pytest.raises(ValueError, match="anchoring"):
        Chain(
            edges=[TemporalEdge("A", "B")],
            A=[ev(0)], B=[ev(1)],
            anchoring="latest-feasible",
        )


def test_chain_run_invariants_id_unique_and_ascending():
    d = Chain(
        edges=[TemporalEdge("A", "B", min_gap=1)],
        A=[ev(0), ev(5)],
        B=[ev(2), ev(7)],
        label="p",
    )
    ms = list(run(d))
    ids = [m.event_id for m in ms]
    assert len(ids) == len(set(ids))
    assert [m.end_idx for m in ms] == sorted(m.end_idx for m in ms)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/stdlib/test_chain.py -q`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 实现**

`path2/stdlib/detectors.py`:

```python
"""四个标准 PatternDetector 公开类(design §4)。

流在构造期绑定;detect(source=None) 忽略 source,由 run(detector) 驱动。
#3 只实现各 Detector 的 design 默认锚定;非默认 anchoring -> ValueError。
"""
from __future__ import annotations

from typing import Callable, Iterator, Optional

from path2.core import Event, TemporalEdge
from path2.stdlib._advance import advance_dag
from path2.stdlib._graph import build_graph, validate_chain, validate_dag
from path2.stdlib._labels import resolve_labels
from path2.stdlib.pattern_match import PatternMatch


def _endpoint_labels(edges, forbid=()):
    s = set()
    for e in list(edges) + list(forbid):
        s.add(e.earlier)
        s.add(e.later)
    return s


class Chain:
    """线性链 a→b→c。最优实现 = 单调双指针 O(ΣN)(复用 advance_dag)。"""

    def __init__(
        self,
        *positional_streams,
        edges,
        key: Optional[Callable[[Event], str]] = None,
        strict_key: bool = False,
        label: Optional[str] = None,
        anchoring: str = "earliest-feasible",
        **named_streams,
    ):
        if anchoring != "earliest-feasible":
            raise ValueError(
                f"Chain #3 仅支持默认 anchoring='earliest-feasible',"
                f"收到 {anchoring!r}"
            )
        self._edges = list(edges)
        self._label = label or "chain"
        self._graph = build_graph(self._edges)
        validate_chain(self._graph)
        self._streams = resolve_labels(
            positional=positional_streams,
            named=named_streams,
            key=key,
            strict_key=strict_key,
            endpoint_labels=_endpoint_labels(self._edges),
        )

    def detect(self, source=None) -> Iterator[PatternMatch]:
        yield from advance_dag(self._graph, self._streams, self._label)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/path2/stdlib/test_chain.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add path2/stdlib/detectors.py tests/path2/stdlib/test_chain.py
git commit -m "feat(path2-stdlib): Chain 公开类(Dag+线性加严)"
```

---

## Task 7: `Dag` 公开类

> **redesign 修正注**:Dag 用 Task 5 的 LEF-DFS 核心。**新增工作项(关闭既有 `_graph.py` 缺口,redesign §8.3)**:`validate_dag` 除环检测外**必须新增"度为 0 的未引用孤立节点"拒绝**(`ValueError`),并加注释"**多弱连通分量(多个各节点度≥1 的不连通子 DAG)合法**,仅拒绝度为 0 未引用节点"。多 WCC 输出 = 各分量独立 LEF 序列按 end_idx 的 p 路归并;缓冲 ≤(p−1) 数据无关结构常数(非"零",redesign §6)。新增测试:多 WCC 合法且正确归并;度为 0 节点 `ValueError`;`pattern_label` 含 `#` `ValueError`。`anchoring` 非默认 → `ValueError`。

design §3.2。多入度 + 多 WCC;构造期 `validate_dag`(环检测 + 度为 0 孤立节点拒绝)。

**Files:**
- Modify: `path2/stdlib/detectors.py`(追加 `Dag` 类)
- Test: `tests/path2/stdlib/test_dag.py`

- [ ] **Step 1: 写失败测试**

`tests/path2/stdlib/test_dag.py`:

```python
from dataclasses import dataclass

import pytest

from path2 import run
from path2.core import Event, TemporalEdge
from path2.stdlib.detectors import Dag


@dataclass(frozen=True)
class _E(Event):
    pass


def ev(s, e=None):
    e = s if e is None else e
    return _E(event_id=f"e_{s}_{e}", start_idx=s, end_idx=e)


def test_dag_multi_indegree_convergence():
    d = Dag(
        edges=[
            TemporalEdge("A", "C", min_gap=1, max_gap=10),
            TemporalEdge("B", "C", min_gap=1, max_gap=3),
        ],
        A=[ev(0)], B=[ev(5)], C=[ev(7)],
        label="conv",
    )
    ms = list(run(d))
    assert len(ms) == 1
    assert set(ms[0].role_index) == {"A", "B", "C"}
    assert ms[0].end_idx == 7


def test_dag_cycle_rejected_at_construction():
    with pytest.raises(ValueError, match="环"):
        Dag(
            edges=[TemporalEdge("A", "B"), TemporalEdge("B", "A")],
            A=[ev(0)], B=[ev(1)],
        )


def test_dag_default_label():
    d = Dag(
        edges=[TemporalEdge("A", "B", min_gap=1)],
        A=[ev(0)], B=[ev(2)],
    )
    ms = list(run(d))
    assert ms[0].pattern_label == "dag"
    assert ms[0].event_id == "dag_0_2"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/stdlib/test_dag.py -q`
Expected: FAIL(`ImportError: cannot import name 'Dag'`)

- [ ] **Step 3: 实现(追加到 `path2/stdlib/detectors.py` 末尾)**

```python
class Dag:
    """任意 DAG(多入度多出度)。拓扑序 + 区间剪枝 O(ΣN·d)。"""

    def __init__(
        self,
        *positional_streams,
        edges,
        key=None,
        strict_key: bool = False,
        label: Optional[str] = None,
        anchoring: str = "earliest-feasible",
        **named_streams,
    ):
        if anchoring != "earliest-feasible":
            raise ValueError(
                f"Dag #3 仅支持默认 anchoring='earliest-feasible',"
                f"收到 {anchoring!r}"
            )
        self._edges = list(edges)
        self._label = label or "dag"
        self._graph = build_graph(self._edges)
        validate_dag(self._graph)
        self._streams = resolve_labels(
            positional=positional_streams,
            named=named_streams,
            key=key,
            strict_key=strict_key,
            endpoint_labels=_endpoint_labels(self._edges),
        )

    def detect(self, source=None) -> Iterator[PatternMatch]:
        yield from advance_dag(self._graph, self._streams, self._label)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/path2/stdlib/test_dag.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add path2/stdlib/detectors.py tests/path2/stdlib/test_dag.py
git commit -m "feat(path2-stdlib): Dag 公开类"
```

---

## Task 8: `Kof` — 滑窗计数 + 有界缓冲 + `#<seq>` 去重

> **redesign 修正注**:`#<seq>` 去重改用 Task 5 建立的**无条件、四 Detector 共享的 `detect()`-局部 `seen_ids`** 机制(不再 Kof 专属;redesign §7)。`earliest-feasible` 用 start-first key(redesign §2.2)。`pattern_label` 含 `#` → 构造期 `ValueError`。其余(n=边数、k 阈值、滑窗计数、max_gap 视界有界缓冲、枚举仅 Kof)不变。

design §3.3。n = edges 条数,k = 至少满足条数;earliest-feasible(start-first key)+ 非重叠贪心;封口=锚 max_gap 视界过后,有界缓冲按 end_idx 排序弹出;同 (label,s,e) 撞 → 共享 `seen_ids` `#<seq>`。

**Files:**
- Modify: `path2/stdlib/_advance.py`(追加 `advance_kof`)
- Modify: `path2/stdlib/detectors.py`(追加 `Kof`)
- Test: `tests/path2/stdlib/test_kof.py`

- [ ] **Step 1: 写失败测试**

`tests/path2/stdlib/test_kof.py`:

```python
from dataclasses import dataclass

import pytest

from path2 import run
from path2.core import Event, TemporalEdge
from path2.stdlib.detectors import Kof


@dataclass(frozen=True)
class _E(Event):
    pass


def ev(s, e=None):
    e = s if e is None else e
    return _E(event_id=f"e_{s}_{e}", start_idx=s, end_idx=e)


def test_kof_2_of_3_satisfied():
    # 3 条 edge,要求 >=2 满足
    edges = [
        TemporalEdge("A", "B", min_gap=1, max_gap=5),
        TemporalEdge("B", "C", min_gap=1, max_gap=5),
        TemporalEdge("A", "C", min_gap=1, max_gap=2),  # 这条会被违反
    ]
    d = Kof(
        edges=edges, k=2,
        A=[ev(0)], B=[ev(3)], C=[ev(6)],
        label="kof",
    )
    ms = list(run(d))
    assert len(ms) == 1
    # A->B: 3-0=3 ok ; B->C: 6-3=3 ok ; A->C: 6-0=6 >2 违反 → 2/3 满足 >=k
    assert set(ms[0].role_index) == {"A", "B", "C"}


def test_kof_below_k_no_match():
    edges = [
        TemporalEdge("A", "B", min_gap=1, max_gap=2),
        TemporalEdge("B", "C", min_gap=1, max_gap=2),
    ]
    d = Kof(
        edges=edges, k=2,
        A=[ev(0)], B=[ev(10)], C=[ev(20)],  # 两条都违反
        label="kof",
    )
    assert list(run(d)) == []


def test_kof_k_out_of_range_rejected():
    with pytest.raises(ValueError, match="k"):
        Kof(
            edges=[TemporalEdge("A", "B")], k=5,
            A=[ev(0)], B=[ev(1)],
        )


def test_kof_event_id_disambiguator_on_collision():
    # 构造同 (label,s,e) 撞:两组不同成员但区间相同
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100)]
    d = Kof(
        edges=edges, k=1,
        A=[ev(0, 0), ev(0, 0)],   # 两个区间相同的 A(不同实例)
        B=[ev(1, 1), ev(1, 1)],
        label="kof",
    )
    ms = list(run(d))
    ids = [m.event_id for m in ms]
    assert len(ids) == len(set(ids)), f"event_id 应单 run 唯一: {ids}"
    assert any("#" in i for i in ids)


def test_kof_yield_end_idx_ascending():
    edges = [TemporalEdge("A", "B", min_gap=1, max_gap=5)]
    d = Kof(
        edges=edges, k=1,
        A=[ev(0), ev(20)],
        B=[ev(2), ev(22)],
        label="kof",
    )
    ms = list(run(d))
    ends = [m.end_idx for m in ms]
    assert ends == sorted(ends)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/stdlib/test_kof.py -q`
Expected: FAIL(`ImportError: cannot import name 'Kof'`)

- [ ] **Step 3: 实现 `advance_kof`(追加到 `path2/stdlib/_advance.py` 末尾)**

```python
def advance_kof(
    g: Graph,
    streams: Dict[str, List[Event]],
    edges: List[TemporalEdge],
    k: int,
    label: str,
) -> Iterator[PatternMatch]:
    """k-of-n 边松弛:任意 >=k 条 edge gap 满足即命中。

    earliest-feasible 选实例 + 非重叠贪心;按锚 max_gap 视界封口,
    有界缓冲按 end_idx 排序弹出;同 (label,s,e) 撞追加 #<seq>。
    复杂度 O(ΣN·n),n=边数。
    """
    order = topo_order(g)
    ptr: Dict[str, int] = {n: 0 for n in g.nodes}
    finite_max = [e.max_gap for e in edges if e.max_gap != float("inf")]
    horizon = max(finite_max) if finite_max else None

    buffer: List[PatternMatch] = []
    seen_ids: Dict[str, int] = {}

    def _mk(assign: Dict[str, Event]) -> PatternMatch:
        members = sorted(assign.values(), key=lambda e: e.start_idx)
        s = members[0].start_idx
        end = max(e.end_idx for e in members)
        base = default_event_id(label, s, end)
        if base in seen_ids:
            seen_ids[base] += 1
            eid = f"{base}#{seen_ids[base]}"
        else:
            seen_ids[base] = 0
            eid = base
        return PatternMatch(
            event_id=eid, start_idx=s, end_idx=end,
            children=tuple(members),
            role_index={lab: (assign[lab],) for lab in assign},
            pattern_label=label,
        )

    def _flush(upto_start: int) -> Iterator[PatternMatch]:
        buffer.sort(key=lambda m: m.end_idx)
        keep: List[PatternMatch] = []
        for m in buffer:
            if upto_start is None or m.end_idx <= upto_start:
                yield m
            else:
                keep.append(m)
        buffer[:] = keep

    # 锚 = 最早 source 标签的每个实例(按 end_idx 升序物化)
    anchor_label = order[0]
    for a in streams[anchor_label]:
        assign: Dict[str, Event] = {anchor_label: a}
        win_lo = a.start_idx
        win_hi = (a.start_idx + horizon) if horizon is not None else None
        # 每个非锚标签取窗口内最早实例
        for lab in order:
            if lab == anchor_label:
                continue
            chosen = None
            for cand in streams[lab]:
                if cand.start_idx < win_lo:
                    continue
                if win_hi is not None and cand.start_idx > win_hi:
                    break
                chosen = cand
                break
            if chosen is not None:
                assign[lab] = chosen
        # 计满足边数(两端点都已选且 gap 满足)
        sat = 0
        for e in edges:
            if e.earlier in assign and e.later in assign:
                gap = assign[e.later].start_idx - assign[e.earlier].end_idx
                if e.min_gap <= gap <= e.max_gap:
                    sat += 1
        if sat >= k:
            buffer.append(_mk(assign))
        # 锚前移后,end_idx <= 本锚 start 的匹配已封口可弹出
        yield from _flush(a.start_idx)
    yield from _flush(None)  # 收尾全部弹出
```

注:`#3` 的 Kof 锚定取"最早 source 标签每个实例",非重叠由"锚遍历各实例 + 窗口内取最早"隐式保证;`horizon` 用所有有限 `max_gap` 的最大值近似视界,无有限 max_gap 时退化为单次全量(可接受,design §3.5 缓冲被 max_gap 限界的边界情形)。

- [ ] **Step 4: 实现 `Kof`(追加到 `path2/stdlib/detectors.py` 末尾)**

先在 `detectors.py` 顶部 import 处补 `advance_kof`、`validate_kof`:

```python
from path2.stdlib._advance import advance_dag, advance_kof
from path2.stdlib._graph import (
    build_graph,
    validate_chain,
    validate_dag,
    validate_kof,
)
```

追加类:

```python
class Kof:
    """k-of-n 边松弛。n=edges 条数,k=至少满足条数。滑窗计数 O(ΣN·n)。"""

    def __init__(
        self,
        *positional_streams,
        edges,
        k: int,
        key=None,
        strict_key: bool = False,
        label: Optional[str] = None,
        anchoring: str = "non-overlapping-greedy",
        **named_streams,
    ):
        if anchoring != "non-overlapping-greedy":
            raise ValueError(
                f"Kof #3 仅支持默认 anchoring='non-overlapping-greedy',"
                f"收到 {anchoring!r}"
            )
        self._edges = list(edges)
        self._k = k
        self._label = label or "kof"
        self._graph = build_graph(self._edges)
        validate_kof(self._graph, k=k, n_edges=len(self._edges))
        self._streams = resolve_labels(
            positional=positional_streams,
            named=named_streams,
            key=key,
            strict_key=strict_key,
            endpoint_labels=_endpoint_labels(self._edges),
        )

    def detect(self, source=None) -> Iterator[PatternMatch]:
        yield from advance_kof(
            self._graph, self._streams, self._edges, self._k, self._label
        )
```

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/path2/stdlib/test_kof.py -q`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add path2/stdlib/_advance.py path2/stdlib/detectors.py tests/path2/stdlib/test_kof.py
git commit -m "feat(path2-stdlib): Kof 滑窗计数 + 有界缓冲 + #seq 去重"
```

---

## Task 9: `Neg` — 正向子图 + forbid 谓词过滤

> **redesign 修正注**:正向子图复用 Task 5 的 **LEF-DFS** 核心(非旧 O(ΣN) 描述)。缓冲**继承正向**(正向=Chain⇒零;正向=Dag⇒≤(p−1);redesign §6),非无条件零。`pattern_label` 含 `#` → 构造期 `ValueError`。forbid 语义 / never_before / 否定标签不进 children-role_index 不变。

design §3.4。`Neg(edges=[...正向...], forbid=[...否定 TemporalEdge...])`;forbid 一条 `(earlier=A, later=N, min_gap, max_gap)` = "扮演 A 的实例定后不存在 N 实例满足 gap";命中即作废。N 不进 children/role_index。

**Files:**
- Modify: `path2/stdlib/_advance.py`(追加 `advance_neg`)
- Modify: `path2/stdlib/detectors.py`(追加 `Neg`)
- Test: `tests/path2/stdlib/test_neg.py`

- [ ] **Step 1: 写失败测试**

`tests/path2/stdlib/test_neg.py`:

```python
from dataclasses import dataclass

import pytest

from path2 import run
from path2.core import Event, TemporalEdge
from path2.stdlib.detectors import Neg


@dataclass(frozen=True)
class _E(Event):
    pass


def ev(s, e=None):
    e = s if e is None else e
    return _E(event_id=f"e_{s}_{e}", start_idx=s, end_idx=e)


def test_neg_passes_when_no_forbidden_event():
    d = Neg(
        edges=[TemporalEdge("A", "B", min_gap=1)],
        forbid=[TemporalEdge("A", "N", min_gap=1, max_gap=3)],
        A=[ev(0)], B=[ev(2)], N=[],          # N 无事件 → 不否决
        label="neg",
    )
    ms = list(run(d))
    assert len(ms) == 1
    assert "N" not in ms[0].role_index    # 否定标签不进 role_index
    assert set(ms[0].role_index) == {"A", "B"}


def test_neg_vetoed_when_forbidden_event_present():
    d = Neg(
        edges=[TemporalEdge("A", "B", min_gap=1)],
        forbid=[TemporalEdge("A", "N", min_gap=1, max_gap=5)],
        A=[ev(0)], B=[ev(2)],
        N=[ev(3)],            # 3-0=3 in [1,5] → 否决该匹配
        label="neg",
    )
    assert list(run(d)) == []


def test_neg_never_before():
    # "A 之前 W=4 内不得有 N" = forbid TemporalEdge(N, A, 0, 4)
    d = Neg(
        edges=[TemporalEdge("A", "B", min_gap=1)],
        forbid=[TemporalEdge("N", "A", min_gap=0, max_gap=4)],
        A=[ev(10)], B=[ev(12)],
        N=[ev(7)],            # A.start - N.end = 10-7 = 3 in [0,4] → 否决
        label="nb",
    )
    assert list(run(d)) == []


def test_neg_requires_forbid():
    with pytest.raises(ValueError, match="至少需"):
        Neg(
            edges=[TemporalEdge("A", "B")],
            forbid=[],
            A=[ev(0)], B=[ev(1)],
        )
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/stdlib/test_neg.py -q`
Expected: FAIL(`ImportError: cannot import name 'Neg'`)

- [ ] **Step 3: 实现 `advance_neg`(追加到 `path2/stdlib/_advance.py` 末尾)**

```python
def advance_neg(
    forward_graph: Graph,
    streams: Dict[str, List[Event]],
    forbid: List[TemporalEdge],
    label: str,
) -> Iterator[PatternMatch]:
    """正向子图(Dag/Chain)跑候选,逐 forbid edge 过滤。

    forbid 一条 (earlier, later, min_gap, max_gap):正向匹配里扮演
    `earlier` 的实例 e_A 定后,若存在 `later` 标签实例 e_N 满足
    min_gap <= e_N.start_idx - e_A.end_idx <= max_gap,则该匹配作废。
    复杂度 = 正向 O(ΣN) + 否定检查 O(ΣN_neg)。
    """
    for m in advance_dag(forward_graph, streams, label):
        vetoed = False
        for fe in forbid:
            e_a = m.role_index.get(fe.earlier)
            if not e_a:
                continue
            anchor = e_a[0]
            neg_list = streams.get(fe.later, [])
            for n in neg_list:  # neg_list 按 end_idx 升序;朴素扫描即可
                gap = n.start_idx - anchor.end_idx
                if fe.min_gap <= gap <= fe.max_gap:
                    vetoed = True
                    break
            if vetoed:
                break
        if not vetoed:
            yield m
```

注:design §3.4 的"指针随候选 end_idx 单调前移 O(ΣN_neg)"是最优形态;#3 先用朴素扫描(正确性优先,复杂度仍线性于 neg 流且候选已 earliest-feasible),单调指针优化留作后续(不影响语义,不阻塞)。

- [ ] **Step 4: 实现 `Neg`(追加到 `path2/stdlib/detectors.py` 末尾)**

`detectors.py` import 处补 `advance_neg`、`validate_neg`:

```python
from path2.stdlib._advance import advance_dag, advance_kof, advance_neg
from path2.stdlib._graph import (
    build_graph,
    validate_chain,
    validate_dag,
    validate_kof,
    validate_neg,
)
```

追加类:

```python
class Neg:
    """正向子图 + forbid 谓词过滤(否定性由 forbid 参数位承载)。O(ΣN)。"""

    def __init__(
        self,
        *positional_streams,
        edges,
        forbid,
        key=None,
        strict_key: bool = False,
        label: Optional[str] = None,
        anchoring: str = "earliest-feasible",
        **named_streams,
    ):
        if anchoring != "earliest-feasible":
            raise ValueError(
                f"Neg #3 仅支持默认 anchoring='earliest-feasible',"
                f"收到 {anchoring!r}"
            )
        self._edges = list(edges)
        self._forbid = list(forbid)
        self._label = label or "neg"
        self._graph = build_graph(self._edges)
        validate_dag(self._graph)  # 正向子图按 Dag 形态校验(Chain 是其特例)
        validate_neg(self._graph, self._forbid)
        self._streams = resolve_labels(
            positional=positional_streams,
            named=named_streams,
            key=key,
            strict_key=strict_key,
            endpoint_labels=_endpoint_labels(self._edges, self._forbid),
        )

    def detect(self, source=None) -> Iterator[PatternMatch]:
        yield from advance_neg(
            self._graph, self._streams, self._forbid, self._label
        )
```

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/path2/stdlib/test_neg.py -q`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add path2/stdlib/_advance.py path2/stdlib/detectors.py tests/path2/stdlib/test_neg.py
git commit -m "feat(path2-stdlib): Neg 正向子图 + forbid 谓词过滤"
```

---

## Task 10: 公开出口 + 端到端集成

design §6。统一出口 + run() 不变式 + 类名默认 / key 逃生舱端到端。

**Files:**
- Modify: `path2/stdlib/__init__.py`
- Modify: `path2/__init__.py`
- Test: `tests/path2/stdlib/test_integration.py`

- [ ] **Step 1: 写失败测试**

`tests/path2/stdlib/test_integration.py`:

```python
from dataclasses import dataclass

from path2 import Chain, Dag, Kof, Neg, PatternMatch, run
from path2.core import Event, TemporalEdge


@dataclass(frozen=True)
class Spike(Event):
    pass


@dataclass(frozen=True)
class Drop(Event):
    pass


def _mk(cls, s):
    return cls(event_id=f"{cls.__name__}_{s}", start_idx=s, end_idx=s)


def test_public_exports_present():
    assert all(x is not None for x in (Chain, Dag, Kof, Neg, PatternMatch))


def test_classname_default_label_end_to_end():
    spikes = [_mk(Spike, 0), _mk(Spike, 10)]
    drops = [_mk(Drop, 2), _mk(Drop, 12)]
    d = Chain(
        spikes, drops,
        edges=[TemporalEdge("Spike", "Drop", min_gap=1)],
        label="sd",
    )
    ms = list(run(d))
    assert [(m.start_idx, m.end_idx) for m in ms] == [(0, 2), (10, 12)]


def test_key_escape_hatch_single_merged_stream():
    merged = [_mk(Spike, 0), _mk(Drop, 2), _mk(Spike, 10), _mk(Drop, 12)]
    d = Chain(
        merged,
        edges=[TemporalEdge("Spike", "Drop", min_gap=1)],
        key=lambda e: type(e).__name__,
        label="sd",
    )
    ms = list(run(d))
    assert [(m.start_idx, m.end_idx) for m in ms] == [(0, 2), (10, 12)]


def test_nested_patternmatch_uses_pattern_label():
    # 一层 Chain 的产出再喂给上层 Chain(类名默认失效,靠 pattern_label)
    spikes = [_mk(Spike, 0)]
    drops = [_mk(Drop, 2)]
    inner = list(run(Chain(
        spikes, drops,
        edges=[TemporalEdge("Spike", "Drop", min_gap=1)],
        label="L1",
    )))
    tail = [_mk(Drop, 9)]
    outer = Chain(
        inner, tail,
        edges=[TemporalEdge("L1", "Drop", min_gap=1)],
        label="L2",
    )
    ms = list(run(outer))
    assert len(ms) == 1 and ms[0].pattern_label == "L2"
    assert ms[0].role_index["L1"][0].pattern_label == "L1"


def test_run_invariants_across_all_four():
    edges = [TemporalEdge("A", "B", min_gap=1)]
    for D in (
        Chain(edges=edges, A=[_mk(Spike, 0)], B=[_mk(Drop, 2)], label="p"),
        Dag(edges=edges, A=[_mk(Spike, 0)], B=[_mk(Drop, 2)], label="p"),
    ):
        ms = list(run(D))
        ends = [m.end_idx for m in ms]
        ids = [m.event_id for m in ms]
        assert ends == sorted(ends)
        assert len(ids) == len(set(ids))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/path2/stdlib/test_integration.py -q`
Expected: FAIL(`ImportError: cannot import name 'Chain' from 'path2'`)

- [ ] **Step 3: 实现出口**

`path2/stdlib/__init__.py`(替换为):

```python
"""Path 2 stdlib:消费 TemporalEdge 声明的标准 PatternDetector。

用户只写声明(edges + 每标签一条事件流),stdlib 跑最优实现。
"""
from path2.stdlib.detectors import Chain, Dag, Kof, Neg
from path2.stdlib.pattern_match import PatternMatch

__all__ = ["Chain", "Dag", "Kof", "Neg", "PatternMatch"]
```

`path2/__init__.py`(在现有 import 后追加,并扩 `__all__`):

```python
from path2.stdlib import Chain, Dag, Kof, Neg, PatternMatch
```

并在 `__all__` 列表追加:`"Chain", "Dag", "Kof", "Neg", "PatternMatch"`。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/path2/stdlib/test_integration.py -q`
Expected: 5 passed

- [ ] **Step 5: 全量回归**

Run: `uv run pytest tests/path2/ -q`
Expected: 全部 passed(协议层 + dogfood 既有 63 + 本次新增,无回归)

- [ ] **Step 6: Commit**

```bash
git add path2/stdlib/__init__.py path2/__init__.py tests/path2/stdlib/test_integration.py
git commit -m "feat(path2-stdlib): 公开出口 + 端到端集成(Chain/Dag/Kof/Neg/PatternMatch)"
```

---

## Self-Review(plan vs design 覆盖核对)

| design 节 | 覆盖任务 |
|---|---|
| §1.1 earlier/later=标签裁定 | 整体语义前提(Task 3 解析体现);§7 spec 回写属 roadmap #2,**不在 #3 plan** |
| §1.2 三段标签解析 + 冲突报错 | Task 3 |
| §2.1/§2.2 PatternMatch 字段 + 一致性 + role_index 恒 tuple + pattern_label 解嵌套 | Task 2、Task 10(嵌套用例) |
| §2.3 default_event_id + Kof #seq | Task 1、Task 8 |
| §3.0/§3.0.1 通用前置 + 逐 Detector 拓扑校验 | Task 4 |
| §3.1 Chain 单调双指针 | Task 5(核心)+ Task 6 |
| §3.2 Dag 拓扑序+区间剪枝 | Task 5 + Task 7 |
| §3.3 Kof 滑窗计数 + n=边数 + 有界缓冲封口 | Task 8 |
| §3.4 Neg forbid 参数位 + never_before | Task 9 |
| §3.5 输入物化输出有序 + yield 升序 | Task 5/6/7(升序断言)、Task 8(Kof 缓冲)、Task 10(run 不变式) |
| §4 公开 API 形状 + anchoring 默认/非默认拒绝 | Task 6/7/8/9 |
| §5 #3/#4 边界 + default_event_id 内联桩 | Task 1 + 范围内全部任务 |
| §6 测试策略 | 各任务 TDD + Task 10 集成/回归 |
| §8 plan 决策项(模块切分/anchoring 策略/strict_key/文案/detect 签名) | File Structure 段已锁定 |

无占位符;类型/签名跨任务一致(`resolve_labels`/`advance_dag`/`PatternMatch` 字段/`default_event_id` 契约在引用前均已定义);Chain/Dag 复用 `advance_dag` 命名一致。

---

## Execution Handoff

> **roadmap 要求 #3 走独立 worktree**(`docs/research/path2_roadmap.md` §2 工作模式)。执行前在 worktree 中进行。

Plan complete and saved to `docs/superpowers/plans/2026-05-16-path2-stdlib-pattern-detectors.md`. Two execution options:

1. **Subagent-Driven (recommended)** — 每任务派新 subagent,任务间两阶段 review,快速迭代。
2. **Inline Execution** — 本 session 内 executing-plans,批量执行 + 检查点。

Which approach?
