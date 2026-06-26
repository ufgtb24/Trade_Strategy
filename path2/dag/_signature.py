# path2/dag/_signature.py
"""前沿割签名(INV-C 剪枝命脉)+ C1 等-end 塌缩。

签名(verdict §3.4 解 B):维度由每条「已绑前驱 -> 未绑后继」跨割边的 signature_fields()
自描述并取并集。纯 TemporalEdge 退化回 (u,(end_idx,)) = committed 逐字等价(零回归);
Containment/Overlap/Equals 自动升维到 (u,(start_idx,end_idx))。
进签名的只有 feasible_window 依赖的结构字段(单调);where(不单调)经候选预过滤排除在外
-> 「相同签名 => 相同结构剩余可行域」成立 => 剪枝健全。

C1(collapse_equal_end_keep_keymin):字段级定级塌缩(D3 升级)。
  - out_edges=None(无出边信息，或全无 selector):退化到原「按父 end_idx 分组，留 (start,end,pos) argmin」
    行为——与旧逻辑字节等价，保证点事件 match-preserving 命脉。
  - out_edges 含 selector 出边：分组键 = 所有出边依赖的 (selector_or_None, field) 组合向量，
    对每个候选按其 child(selector).field 的值构建复合分组键；
    完全相同分组键的候选才视为「等价」（留父 (start,end,pos) argmin）。
    健全充要条件：分组键 ⊇ 所有出边依赖的 child 字段并集（自动满足）。

对 EqualsEdge 的 SRC 节点不健全(window 把 start 钉死,非单调)-> 引擎对这些节点关闭 C1(见
_solve.compile_plan)。宽 child 多 selector 场景用复合键防对称压制（比「各 selector 各跑 argmin
取并集」保守、无条件健全）。
"""
from __future__ import annotations

from typing import List, Optional, Set, Tuple


def frontier_cut_signature(assign, pred, order, k) -> tuple:
    """k = 当前待绑节点在拓扑序的位置。order[k:] 为未赋值集。
    对每条「src 已绑、dst 未绑」的正向跨割边,按其 signature_fields() 取 src 的标量元组。"""
    unassigned = set(order[k:])
    sig: Set[Tuple] = set()
    for w in unassigned:
        for u, e in pred[w]:
            if u in assign:
                bound = assign[u]
                # src_selector 非 None 时,投影到 child(与生产 endpoint() / oracle _ep 同语义)
                proj = bound.child(e.src_selector) if e.src_selector is not None else bound
                sig.add((u, tuple(getattr(proj, f) for f in e.signature_fields())))
    # key=repr:签名元组跨边可能异构(Temporal 出 (end,)、Containment 出 (start,end)),
    # repr 给一个对任意字段类型都全序的稳定排序键;去重已由 set 完成,这里只为确定性。
    return tuple(sorted(sig, key=repr))


def _collect_dims(out_edges) -> List[Tuple]:
    """收集所有出边的 (src_selector, field) 有序对（去重 + 排序，保证确定性）。
    返回稳定排序后的列表，供 _project 据此对每个候选取值（提到候选循环外，一次性算）。"""
    dims: set = set()
    for e in out_edges:
        sel = e.src_selector  # None 或 key 字符串
        for f in e.signature_fields():
            dims.add((sel, f))
    return sorted(dims, key=repr)  # 稳定排序


def _project(event, dims) -> tuple:
    """按 dims（_collect_dims 产物）取 event 在各 (selector, field) 上的值向量（复合分组键）。

    selector 非 None → event.child(selector).field；selector=None → event.field。
    健全性：dims 恰好 = 所有出边 feasible_window 依赖的字段并集，
    「相同投影向量 ⇒ 对所有下游节点产生完全相同的可行窗口」→ 任留一个代表即可。
    """
    key_parts = []
    for sel, f in dims:
        proj = event.child(sel) if sel is not None else event
        key_parts.append(getattr(proj, f))
    return tuple(key_parts)


def _has_child_selector(out_edges) -> bool:
    """出边中是否存在 src_selector 非 None 的边（宽 child 路径）。"""
    return any(e.src_selector is not None for e in out_edges)


def collapse_equal_end_keep_keymin(
    cands: List[Tuple],
    out_edges: Optional[List] = None,
) -> List[Tuple]:
    """C1 字段级定级塌缩（D3 升级）。

    cands: [(event, stream_idx), ...]

    out_edges=None 或无 child selector 出边：
      退化到原逻辑——按父 event.end_idx 分组，每组留 (start_idx,end_idx,stream_idx) argmin。
      与旧实现字节等价（点事件 match-preserving 命脉）。

    out_edges 含 child selector 出边：
      复合键模式——分组键 = 所有出边 (src_selector, field) 向量并集的值向量；
      完全相同复合键才视为等价，留父 (start_idx,end_idx,stream_idx) argmin 代表。
      健全充要条件（机检：分组键 ⊇ 出边依赖字段并集）自动满足。
    """
    # 两分支共享同一 (start,end,pos) argmin tiebreak：先排序，同组首个即为代表
    sorted_cands = sorted(cands, key=lambda x: (x[0].start_idx, x[0].end_idx, x[1]))

    # ── 退化路径：无出边信息或全无 selector → 原始行为（字节等价）─────────────
    if not out_edges or not _has_child_selector(out_edges):
        out, seen_end = [], set()
        for e, i in sorted_cands:
            if e.end_idx in seen_end:
                continue
            seen_end.add(e.end_idx)
            out.append((e, i))
        return out

    # ── 复合键路径：按 (selector, field) 向量分组，留父 (start,end,pos) argmin ─
    dims = _collect_dims(out_edges)            # 维度集合一次性提取（候选循环外）
    seen_composite: set = set()
    out = []
    for e, i in sorted_cands:
        ck = _project(e, dims)
        if ck in seen_composite:
            continue
        seen_composite.add(ck)
        out.append((e, i))
    return out
