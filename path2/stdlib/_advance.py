"""约束推进核心(design §3)。

advance_dag:earliest-feasible + 非重叠贪心 + 区间剪枝,O(ΣN·d)。
Chain 复用 advance_dag(后续 Task 加严线性校验后调用)。
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
