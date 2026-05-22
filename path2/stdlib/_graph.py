"""edges → 有向图 + 逐 Detector 拓扑静态校验(design §3.0.1)。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from path2.core import TemporalEdge


@dataclass
class Graph:
    nodes: Set[str] = field(default_factory=set)
    adj: Dict[str, List[Tuple[str, TemporalEdge]]] = field(default_factory=dict)  # u -> [(v, edge)]
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
        for v, _ in sorted(g.adj[u], key=lambda t: t[0]):
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
    # 多弱连通分量(多个各节点度≥1 的不连通子 DAG)合法,仅拒绝度为 0 的未引用孤立节点
    if _has_cycle(g):
        raise ValueError("Dag 检测到环")
    for n in g.nodes:
        if g.indeg[n] == 0 and g.outdeg[n] == 0:
            raise ValueError(
                f"validate_dag 拒绝度为 0 的孤立节点 {n!r}(design §3.0.1)"
            )


def validate_kof(g: Graph, k: int, n_edges: int) -> None:
    if len(g.nodes) < 2:
        raise ValueError("Kof edges 端点 label 数须 >= 2")
    if k < 1 or k > n_edges:
        raise ValueError(
            f"Kof k={k} 越界,须 1 <= k <= 边数({n_edges})"
        )
    # redesign §10.7:跨 WCC 的 k-of-n 与逐 WCC 分解(缓冲/产出顺序所需)
    # 冲突且无明确表达意义 ⇒ Kof edges 必须弱连通(单 WCC)。
    if not _connected(g):
        raise ValueError(
            "Kof edges 必须弱连通(单 WCC):多个不连通分量的 k-of-n "
            "无明确语义(redesign §10.7)"
        )


def validate_neg(forward: Graph, forbid: List[TemporalEdge]) -> None:
    """校验 Neg forbid 列表(redesign §11.3)。

    C1:forbid 非空(含"至少需")。
    C2:每条 fe 的两端点对 forward.nodes 的成员资格必须 XOR 为真:
        - 两端皆∈正向子图 → ValueError(含"正向子图"):无否定标签。
        - 两端皆∉正向子图 → ValueError(含"正向子图"):无正向锚点。
        - 恰好一端∈ → 合法(anchor=∈端,neg=∉端),不抛。
    """
    if not forbid:
        raise ValueError(
            "Neg 至少需 1 条否定约束,否则等价 Chain/Dag"
        )
    for fe in forbid:
        a_in = fe.earlier in forward.nodes
        b_in = fe.later in forward.nodes
        if a_in and b_in:
            raise ValueError(
                f"Neg forbid 边 ({fe.earlier!r}→{fe.later!r}) 两端均在正向子图中,"
                "无否定标签:每条 forbid 边须恰好一端属于正向子图(XOR)(redesign §11.3)"
            )
        if not a_in and not b_in:
            raise ValueError(
                f"Neg forbid 边 ({fe.earlier!r}→{fe.later!r}) 两端均不在正向子图中,"
                "无正向锚点:每条 forbid 边须恰好一端属于正向子图(XOR)(redesign §11.3)"
            )
