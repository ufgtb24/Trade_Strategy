# path2/dag/_reify.py
"""Solution -> PatternMatch 物化。role_index = 节点角色 -> 单 Event;children 按 start 升序;
PredicateTrace 重算 where(实证) + 每正向边 EdgeWitness。measured = dst.start - src.end(gap 语义)。
"""
from __future__ import annotations

from dataclasses import replace

from path2.dag.edges import NegationEdge
from path2.dag.result import (PatternMatch, PredicateTrace, EdgeWitness, ClauseWitness)
from path2.dag._solve import endpoint


def _flat(binding):
    return [binding]


def reify(sol, streams, plan, ctx) -> PatternMatch:
    assign = sol.assign
    children = sorted((c for b in assign.values() for c in _flat(b)),
                      key=lambda e: (e.start_idx, e.end_idx))
    start = min(c.start_idx for c in children)
    end = max(c.end_idx for c in children)

    # where 实证:逐节点逐 clause 重算,产 ClauseWitness。
    where_results = {}
    for nid, binding in assign.items():
        node = plan.nodes.get(nid)
        if node is None:
            continue
        ctx_v = replace(ctx, bound=assign) if ctx is not None else None
        target = binding  # 单 Event
        clauses = {}
        for cid, fn in node.where:
            sat = bool(fn(target, ctx_v))
            meta = getattr(fn, "meta", None)
            measured = fn.measure(target, ctx_v) if hasattr(fn, "measure") else None
            clauses[cid] = ClauseWitness(satisfied=sat, measured=measured,
                                         op=(meta or {}).get("op"),
                                         threshold=(meta or {}).get("threshold"))
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
            measured=float(b.start_idx - a.end_idx))

    return PatternMatch(
        event_id=f"{plan.pattern_id}@{start}-{end}",
        start_idx=start, end_idx=end,
        pattern_id=plan.pattern_id,
        role_index=dict(assign),
        children=tuple(children),
        predicate_trace=PredicateTrace(where_results=where_results, edge_results=edge_results))
