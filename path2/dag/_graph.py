# path2/dag/_graph.py
"""约束图骨架 —— 纯函数,零状态。节点全集由调用方(compile_plan)从 spec.nodes 给定,
不从 edges 反推(孤立节点/否定 dst 节点都可能不在 edges 的正向端点里)。

拓扑序破平按 node_id 字典序 -> 确定性(同一 spec 永远同一序),便于差分测试可复现。
正向边(Temporal/Containment/Overlap/Equals)进 pos_preds(窗口交/satisfies 复核);
否定边(NegationEdge)进 neg_out(挂在 src 上,src 绑定后全称消费),不进 pos_preds。
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from path2.dag.edges import DependencyEdge, NegationEdge
from path2.dag.nodes import NodeSpec


def _is_pos(e: DependencyEdge) -> bool:
    return not isinstance(e, NegationEdge)


def pos_preds(node_ids: Iterable[str], edges) -> Dict[str, List[Tuple[str, DependencyEdge]]]:
    """node_id -> [(src, 正向边)]。否定边排除。"""
    pred: Dict[str, List[Tuple[str, DependencyEdge]]] = {n: [] for n in node_ids}
    for e in edges:
        if _is_pos(e):
            pred[e.dst].append((e.src, e))
    return pred


def neg_out(edges) -> Dict[str, List[NegationEdge]]:
    """src -> [该 src 出发的否定边]。"""
    out: Dict[str, List[NegationEdge]] = {}
    for e in edges:
        if isinstance(e, NegationEdge):
            out.setdefault(e.src, []).append(e)
    return out


def topo_order(node_ids, edges) -> List[str]:
    """Kahn 拓扑序,只看正向边。破平按 node_id 字典序(确定性)。环则抛 ValueError。"""
    ids = set(node_ids)
    indeg = {n: 0 for n in ids}
    adj: Dict[str, List[str]] = {n: [] for n in ids}
    for e in edges:
        if not _is_pos(e):
            continue
        adj[e.src].append(e.dst)
        indeg[e.dst] += 1
    ready = sorted([n for n in ids if indeg[n] == 0])
    order: List[str] = []
    while ready:
        u = ready.pop(0)
        order.append(u)
        for v in sorted(adj[u]):
            indeg[v] -= 1
            if indeg[v] == 0:
                ready.append(v)
        ready.sort()
    if len(order) != len(ids):
        raise ValueError("cycle in pattern edges(拓扑非 DAG)")
    return order


def wccs(node_ids, edges) -> List[List[str]]:
    """弱连通分量(只看正向边,无向化)。每个分量内 node_id 排序;分量按首元素排序。
    孤立节点自成单元素分量。"""
    ids = set(node_ids)
    und: Dict[str, set] = {n: set() for n in ids}
    for e in edges:
        if not _is_pos(e):
            continue
        und[e.src].add(e.dst)
        und[e.dst].add(e.src)
    seen: set = set()
    comps: List[List[str]] = []
    for n in sorted(ids):
        if n in seen:
            continue
        stack, comp = [n], []
        seen.add(n)
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in und[u]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        comps.append(sorted(comp))
    return sorted(comps, key=lambda c: c[0])


def sub_nodes_edges(comp_ids, edges):
    """投影到一个分量:返回该分量内的节点集 + 两端都在分量内的边。"""
    s = set(comp_ids)
    return s, [e for e in edges if e.src in s and e.dst in s]


def detector_topo_order(nodes: Tuple[NodeSpec, ...]) -> List[str]:
    """detector 依赖排序(与 pattern 时序 DAG 无关):consumes_stream 指向的节点必先跑。
    破平按 node_id 字典序。"""
    by_id = {n.node_id: n for n in nodes}
    ids = set(by_id)
    indeg = {n: 0 for n in ids}
    adj: Dict[str, List[str]] = {n: [] for n in ids}
    for n in nodes:
        if n.consumes_stream is not None:
            adj[n.consumes_stream].append(n.node_id)
            indeg[n.node_id] += 1
    ready = sorted([n for n in ids if indeg[n] == 0])
    order: List[str] = []
    while ready:
        u = ready.pop(0)
        order.append(u)
        for v in sorted(adj[u]):
            indeg[v] -= 1
            if indeg[v] == 0:
                ready.append(v)
        ready.sort()
    if len(order) != len(ids):
        raise ValueError("cycle in detector consumes_stream graph")
    return order
