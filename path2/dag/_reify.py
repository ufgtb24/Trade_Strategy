# path2/dag/_reify.py
"""Solution -> PatternMatch 物化。node_index = node_id -> 单 Event;children 按 start 升序;
PredicateTrace 重算 where(实证) + 每正向边 EdgeWitness。measured 为 kind-aware(硬伤 E · Task 13):
按 edge 类型产出 MeasuredKindAware(kind/value/label),而非笼统 gap 语义。
"""
from __future__ import annotations

from path2.dag.edges import (NegationEdge, TemporalEdge, ContainmentEdge, OverlapEdge,
                             EqualsEdge, StartContainmentEdge)
from path2.dag.gate_failure import MeasuredKindAware
from path2.dag.result import (PatternMatch, PredicateTrace, EdgeWitness)
from path2.dag.where import witness_of
from path2.dag._solve import endpoint


def _flat(binding):
    return [binding]


def _make_measured(edge, u, v) -> MeasuredKindAware:
    """kind-aware · 硬伤 E · 按 edge kind 生成 measured,取代旧的笼统 gap = dst.start - src.end。
    u/v 已经过 endpoint() 端点投影(Child selector 已展开)。"""
    if isinstance(edge, TemporalEdge):
        return MeasuredKindAware(kind='gap',
                                 value=v.start_idx - u.end_idx,
                                 label='gap')
    if isinstance(edge, (ContainmentEdge, OverlapEdge, EqualsEdge)):
        return MeasuredKindAware(kind='window_offset',
                                 value=v.start_idx - u.start_idx,
                                 label='起点偏移')
    if isinstance(edge, StartContainmentEdge):
        return MeasuredKindAware(kind='anchor_delta',
                                 value=v.start_idx - u.start_idx,
                                 label='起点包含')
    if isinstance(edge, NegationEdge):
        return MeasuredKindAware(kind='negation_bars',
                                 value=v.start_idx - u.end_idx,
                                 label='禁区bars')
    return MeasuredKindAware(kind='unknown', value=None, label='?')


def reify(sol, streams, plan) -> PatternMatch:
    assign = sol.assign
    children = sorted((c for b in assign.values() for c in _flat(b)),
                      key=lambda e: (e.start_idx, e.end_idx))
    start = min(c.start_idx for c in children)
    end = max(c.end_idx for c in children)

    # where 实证:逐节点逐 clause 重算,产 ClauseWitness(组合子递归成树,全量求值)。
    where_results = {}
    for nid, binding in assign.items():
        node = plan.nodes.get(nid)
        if node is None:
            continue
        clauses = {cid: witness_of(fn, binding) for cid, fn in node.where}
        if clauses:
            where_results[nid] = clauses

    # 每条正向边 EdgeWitness。src 端 child-aware(endpoint());dst 端见行内注释。
    edge_results = {}
    for e in plan.edges:
        if isinstance(e, NegationEdge):
            continue
        if e.src not in assign or e.dst not in assign:
            continue
        a = endpoint(assign[e.src], e)
        b = endpoint(assign[e.dst], e, "dst")
        edge_results[(e.src, e.dst)] = EdgeWitness(
            satisfied=bool(e.satisfies(a, b)),
            src_instance=a, dst_instance=b,
            measured=_make_measured(e, a, b))

    return PatternMatch(
        event_id=f"{plan.pattern_id}@{start}-{end}",
        start_idx=start, end_idx=end,
        confirm_idx=end,   # 聚合体:所有 constituent event 物化后整个 match 才确认
        pattern_id=plan.pattern_id,
        node_index=dict(assign),
        children=tuple(children),
        predicate_trace=PredicateTrace(where_results=where_results, edge_results=edge_results))
