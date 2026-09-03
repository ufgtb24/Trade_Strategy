# path2/dag/diagnose.py
"""per-node 诊断 pass(web UI 调试用)。坐标轴是 node 不是 event:
event 级"失败归因"因求解短路 path-dependent 而 ill-defined,
故按 node 独立诊断——"哪些候选能当这个 node/卡在哪条 where"(属性) + "找不找得到关系伙伴"(关系)。
解耦的单 node 局部健康检查,不保证全局可满足性。不碰 _solve 求解核心。
"""
from __future__ import annotations

from path2.dag.edges import NegationEdge
from path2.dag.engine import run_streams
from path2.dag._graph import pos_preds
from path2.dag.result import (AttrRow, RelRow, NodeDiagnostic, NodeDiagnostics)
from path2.dag.where import witness_of
from path2.dag._solve import strict_clear

_MISS_GATE_RANK = {"gap_out": 0, "anchor_mismatch": 1, "strict_fail": 2}  # 由近及远(离成功最近排最高)


def _attr_rows(node, stream):
    rows = []
    for e in stream:
        clauses = {}
        for cid, fn in node.where:
            clauses[cid] = witness_of(fn, e)
        rows.append(AttrRow(event=e, clauses=clauses))
    return tuple(rows)


def _child_stream(spec, streams, node):
    """子结构 node 的"流":父容器流逐事件挖 child_slots 中该槽 child,平铺保序。

    子结构 node 无 detector、无独立流(streams[node_id] 恒空),其 attr 判定的
    数据源 = 父容器物化的槽内事件(与 serialize_analysis 挖 child 同源)。槽名由
    children 声明逆映射定位(node_id → (父 node_id, 槽));未声明/槽不存在 → 空。"""
    for n in spec.nodes:
        for slot, child_id in (n.children or {}).items():
            if child_id != node.node_id:
                continue
            out = []
            for e in streams.get(n.node_id, []):
                v = e.child_slots().get(slot)
                if v is None:
                    continue
                out.extend(v if isinstance(v, tuple) else (v,))
            return out
    return []


def diagnose(spec, df, params=None) -> NodeDiagnostics:
    """对每个 NodeSpec 独立做属性诊断(+ 关系诊断,Task 7)。复用 run_streams 产流。"""
    streams = run_streams(spec, df, params)
    nodes = {}
    for node in spec.nodes:
        if node.produced_by is None:
            stream = streams.get(node.node_id, [])
        else:
            # 子结构 node:attr 行数据源 = 父容器槽内事件(段级 where 判定载体;
            # 无 where 时行 vacuous 真 → 段 tier 升 qualified 深灰,与容器同档)
            stream = _child_stream(spec, streams, node)
        attr = _attr_rows(node, stream)
        rel = _rel_rows(node, spec, streams)               # Task 7
        # produced_by 透传供前端显示「由父容器 {produced_by} 物化」提示;
        # 子结构 rel 恒空(无边指向子结构 node,其流槽位为空)
        nodes[node.node_id] = NodeDiagnostic(
            node_id=node.node_id, attr=attr, rel=rel, produced_by=node.produced_by)
    return NodeDiagnostics(nodes=nodes)


def _endpoint(binding, node, selector=None):
    """端点选择(自带,语义同 _solve.endpoint 但不依赖模块级 _CUR_NODES):
    selector 非 None → Child 路径,返回 binding.child(selector)。
    selector=None → 直接返回 binding(单 Event)。"""
    if selector is not None:
        return binding.child(selector)
    return binding


def _passes_where(node, e) -> bool:
    """上游 event 自身是否过它那个 node 的(一元)where。"""
    for _, fn in node.where:
        if not bool(fn(e)):
            return False
    return True


def _pair_gate(edge, a, b, e_r, lo, hi, streams):
    """(a,b) 这一对候选卡在哪个 gate:由近及远 gap_out → anchor_mismatch → strict_fail。
    三关全过返回 None(调用方只在"已知该 src 无法通过"的前提下用它找代表性失败原因)。"""
    if not (edge.satisfies(a, b) and lo <= e_r.start_idx <= hi):
        return "gap_out"
    if not edge._anchor_ok(a, b):
        return "anchor_mismatch"
    if not strict_clear(edge, a, e_r, streams):
        return "strict_fail"
    return None


def _worst_gate(edge, a, lo, hi, stream_r, dst_node, streams):
    """在 dst 流里找"离成功最近"的失败原因 + 代表性 dst,供 example_failed_pairs 抽样。
    stream_r 为空(无任何 dst 候选可比对)时无代表 pair,归 gap_out / 无 example。"""
    best_reason, best_v, best_rank = "gap_out", None, -1
    for e_r in stream_r:
        b = _endpoint(e_r, dst_node, edge.dst_selector)
        reason = _pair_gate(edge, a, b, e_r, lo, hi, streams)
        if reason is None:
            continue   # 理论不该出现:调用方已确认该 src 找不到任何通过全部 gate 的 dst
        rank = _MISS_GATE_RANK[reason]
        if rank > best_rank:
            best_rank, best_reason, best_v = rank, reason, e_r
    return best_reason, best_v


def _rel_rows(node, spec, streams):
    """本 node 作 dst:逐正向入边检查上游伙伴存在性 + 未通过的 src 候选按 miss_reasons 归因
    (Sprint 1 Task 3:gap_out / anchor_mismatch / strict_fail,由近及远取代表性失败 pair 抽样
    ≤5 条存 example_failed_pairs;negation 是全称量词、归 node 级入口 C,本函数恒不产出)。"""
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
        miss = {"gap_out": 0, "anchor_mismatch": 0, "strict_fail": 0, "negation_violated": 0}
        examples = []
        for e_u in u_stream:
            if not _passes_where(u_node, e_u):
                continue
            # src 端：按 edge.src_selector 投影（无 selector → 返回整体）
            a = _endpoint(e_u, u_node, edge.src_selector)
            lo, hi = edge.feasible_window(a)
            # dst 端：按 edge.dst_selector 投影后再做 satisfies + anchor 复核 + strict(next)复核
            # (硬伤 B:窗口内存在满足 satisfies 的 dst 不够——那个 dst 还必须真的锚定
            #  这个 src,否则只是"窗口内碰巧撞上的别人的伙伴",不能算通过;strict=True 的边
            #  还要求这个 dst 是窗口内【第一个】同类候选,否则被更早的候选抢占)
            passed_v = None
            for e_r in stream_r:
                b = _endpoint(e_r, node, edge.dst_selector)
                if (edge.satisfies(a, b) and lo <= e_r.start_idx <= hi
                        and edge._anchor_ok(a, b) and strict_clear(edge, a, e_r, streams)):
                    passed_v = e_r
                    break
            if passed_v is not None:
                ok_src.append(e_u)
                continue
            reason, rep_v = _worst_gate(edge, a, lo, hi, stream_r, node, streams)
            miss[reason] += 1
            if rep_v is not None and len(examples) < 5:
                examples.append((e_u.instance_id, rep_v.instance_id, reason))
        rows.append(RelRow(src=u, kind=type(edge).__name__,
                           total_src=len(u_stream), ok_src=tuple(ok_src),
                           anchor_ok_count=len(ok_src),
                           miss_reasons=miss, example_failed_pairs=tuple(examples)))
    return tuple(rows)
