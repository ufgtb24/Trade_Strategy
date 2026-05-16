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
