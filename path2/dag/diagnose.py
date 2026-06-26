# path2/dag/diagnose.py
"""per-role 诊断 pass(web UI 调试用)。坐标轴是 role 不是 event:
event 级"失败归因"因 where=f(event,role,bound) 多值 + 求解短路 path-dependent 而 ill-defined,
故按 role 独立诊断——"哪些候选能当这个 role/卡在哪条 where"(属性) + "找不找得到关系伙伴"(关系)。
解耦的单 role 局部健康检查,不保证全局可满足性。不碰 _solve 求解核心。
"""
from __future__ import annotations

import builtins

from path2.dag.edges import NegationEdge
from path2.dag.engine import run_streams
from path2.dag._graph import pos_preds
from path2.dag.nodes import MatchContext
from path2.dag.result import (ClauseWitness, AttrRow, RelRow, RoleDiagnostic, RoleDiagnostics)


def _witness(fn, target, ctx) -> ClauseWitness:
    """对一条 where clause 产 ClauseWitness(与 _reify 同口径)。"""
    sat = bool(fn(target, ctx))
    meta = getattr(fn, "meta", None)
    measured = fn.measure(target, ctx) if hasattr(fn, "measure") else None
    return ClauseWitness(satisfied=sat, measured=measured,
                         op=(meta or {}).get("op"),
                         threshold=(meta or {}).get("threshold"))



def _attr_rows(node, stream, ctx):
    rows = []
    for e in stream:
        target = e
        clauses = {}
        for cid, fn in node.where:
            clauses[cid] = _witness(fn, target, ctx)
        rows.append(AttrRow(event=e, clauses=clauses))
    return tuple(rows)


def diagnose(spec, df, params=None) -> RoleDiagnostics:
    """对每个 NodeSpec 独立做属性诊断(+ 关系诊断,Task 7)。复用 run_streams 产流。"""
    streams = run_streams(spec, df, params)
    ctx = MatchContext(df=df, params=params, bound=None)   # 一元 where 安全(bound 不读)
    roles = {}
    for node in spec.nodes:
        stream = streams.get(node.node_id, [])
        attr = _attr_rows(node, stream, ctx)
        rel = _rel_rows(node, spec, streams)               # Task 7
        roles[node.node_id] = RoleDiagnostic(node_id=node.node_id, attr=attr, rel=rel)
    return RoleDiagnostics(roles=roles)


def _endpoint(binding, node, selector=None):
    """端点选择(自带,语义同 _solve.endpoint 但不依赖模块级 _CUR_NODES):
    selector 非 None → Child 路径,返回 binding.child(selector)。
    selector=None → 直接返回 binding(单 Event)。"""
    if selector is not None:
        return binding.child(selector)
    return binding


def _passes_where(node, e, ctx) -> bool:
    """上游 event 自身是否过它那个 role 的(一元)where。"""
    target = e
    for _, fn in node.where:
        if not bool(fn(target, ctx)):
            return False
    return True


def _rel_rows(node, spec, streams):
    """本 role 作 dst:逐正向入边检查上游伙伴存在性。"""
    ctx = MatchContext(df=None, params=None, bound=None)   # 一元 where 不读 df/bound
    by_id = {n.node_id: n for n in spec.nodes}
    pred = pos_preds([n.node_id for n in spec.nodes], spec.edges)   # {dst:[(src,edge)]}
    stream_r = streams.get(node.node_id, [])
    rows = []
    for (u, edge) in pred.get(node.node_id, []):
        if isinstance(edge, NegationEdge):
            continue
        u_node = by_id[u]
        u_stream = streams.get(u, [])
        ok_src = []
        for e_u in u_stream:
            if not _passes_where(u_node, e_u, ctx):
                continue
            # src 端：按 edge.src_selector 投影（无 selector → 返回整体）
            a = _endpoint(e_u, u_node, edge.src_selector)
            lo, hi = edge.feasible_window(a)
            # dst 端：按 edge.dst_selector 投影后再做 satisfies 判定
            if builtins.any(
                edge.satisfies(a, _endpoint(e_r, by_id[node.node_id], edge.dst_selector))
                and lo <= e_r.start_idx <= hi
                for e_r in stream_r
            ):
                ok_src.append(e_u)
        rows.append(RelRow(src=u, kind=type(edge).__name__,
                           total_src=len(u_stream), ok_src=tuple(ok_src)))
    return tuple(rows)
