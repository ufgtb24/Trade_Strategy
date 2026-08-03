# tests/path2/dag/_oracle.py
"""引擎差分测试基础设施。Ev 带 pos 字段(流内下标)用于 reify/key tiebreak;
生产引擎不依赖 Event.pos(用流下标),pos 仅测试断言便利。"""
from __future__ import annotations

import itertools
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from path2.core import Event
from path2.dag.edges import NegationEdge


@dataclass(frozen=True)
class Ev(Event):
    """测试用具体 Event:在 event_id/start_idx/end_idx 外加 pos(流内下标)。"""
    class_id = "test_oracle_ev"
    pos: int = 0
    confirm_idx: int = field(default=-1, kw_only=True)   # -1=未指定 → __post_init__ 填 start_idx

    def __post_init__(self):
        if self.confirm_idx < 0:
            object.__setattr__(self, 'confirm_idx', self.start_idx)
        super().__post_init__()


@dataclass(frozen=True)
class WideEv(Event):
    """携宽 child 的测试 event:本体跨 [start,end],但 child 是子区间(!=父端点),用于 D fuzz。

    kids 是 Ev 的元组,可通过 child("first_kid")/child("last_kid") 取首/尾,
    通过 children("kids") 取全组。本体区间故意比任一 kid 宽,
    使「用 child 投影」与「用父整体」在 satisfies 上产生不同结果。
    字段顺序镜像 Ev：Event 基类字段(event_id/start_idx/end_idx)在前,pos 随后,kids 最后。
    """
    class_id = "test_oracle_wide"
    pos: int = 0
    confirm_idx: int = field(default=-1, kw_only=True)   # -1=未指定 → __post_init__ 填 start_idx
    kids: Tuple[Ev, ...] = ()

    def __post_init__(self):
        if self.confirm_idx < 0:
            object.__setattr__(self, 'confirm_idx', self.start_idx)
        super().__post_init__()

    def child_slots(self):
        return {"kids": self.kids}

    def child(self, name: str) -> Ev:
        if name == "first_kid":
            return self.kids[0]
        if name == "last_kid":
            return self.kids[-1]
        raise KeyError(name)

    def children(self, name: str) -> Tuple[Ev, ...]:
        if name == "kids":
            return self.kids
        raise KeyError(name)


def E(node_id: str, segs) -> List[Ev]:
    """造一条流:segs=[(start,end),...],pos 按插入序。event_id=f'{node_id}{pos}'。"""
    return [Ev(f"{node_id}{p}", s, e, pos=p) for p, (s, e) in enumerate(segs)]


def _cell_key(node_id, binding):
    """ONCE -> (node_id,start,end,pos)。"""
    if isinstance(binding, tuple):
        return (node_id, binding[0].start_idx, binding[-1].end_idx, binding[0].pos, len(binding))
    return (node_id, binding.start_idx, binding.end_idx, binding.pos)


def match_key(assign: Dict) -> tuple:
    """一个匹配的规范键(可跨引擎/oracle 比较;用 Ev.pos 做 tiebreak)。
    assign: node_id -> Event | tuple[Event,...]。"""
    return tuple(sorted(_cell_key(nid, b) for nid, b in assign.items()))


def keyset(solutions) -> Counter:
    """solutions: 可迭代的「匹配」。每项要么是 dict(assign),要么有 .assign 属性。"""
    def _assign(s):
        return s.assign if hasattr(s, "assign") else s
    return Counter(match_key(_assign(s)) for s in solutions)


def _ep(binding, selector):
    """oracle 端点提取：与生产 endpoint() 同语义。

    selector=None → 返回 binding 整体（ONCE 无 selector）。
    selector=key  → 返回 binding.child(key)（Child 路径）。
    """
    return binding.child(selector) if selector is not None else binding


def _strict_clear_brute(edge, a, b, streams):
    """与库 strict 同规则的暴力版(O2 也须懂 strict)。仅 TemporalEdge.strict 生效。"""
    from path2.dag.edges import TemporalEdge
    if not getattr(edge, "strict", False) or not isinstance(edge, TemporalEdge):
        return True
    lo = a.end_idx + edge.min_gap
    hi = a.end_idx + edge.max_gap
    for other in streams.get(edge.dst, []):
        if other is b:
            continue
        if lo <= other.start_idx < b.start_idx and other.start_idx <= hi:
            return False
    return True


def brute_all(edges, streams, where=None):
    """O2 真值:itertools.product 全枚举 + 每正向边 satisfies + strict;否定边全称量词。
    where: dict[node_id, callable(event)->bool](一元,测试可选)。返回 list[dict assign]。"""
    node_ids = sorted({e.src for e in edges} | {e.dst for e in edges}
                      | (set(streams) if streams else set()))
    # 否定 dst 不进枚举(不绑定);仅供否定全称扫
    neg_dst = {e.dst for e in edges if isinstance(e, NegationEdge)}
    bound_ids = [n for n in node_ids if n not in neg_dst]
    lists = [streams.get(n, []) for n in bound_ids]
    out = []
    for combo in itertools.product(*lists):
        assign = {n: ev for n, ev in zip(bound_ids, combo)}
        if where and not all(where[n](assign[n]) for n in bound_ids if n in where):
            continue
        ok = True
        for e in edges:
            if isinstance(e, NegationEdge):
                a_raw = assign.get(e.src)
                if a_raw is None:
                    continue
                # NegationEdge 逐候选扫描；src 端可能携带 selector（Child 路径）
                a_ep = _ep(a_raw, e.src_selector)
                if any(e.satisfies(a_ep, x) for x in streams.get(e.dst, [])):  # 违禁
                    ok = False
                    break
                continue
            a_raw, b_raw = assign[e.src], assign[e.dst]
            # 按 src_selector/dst_selector 做端点投影，与生产 endpoint() 等语义
            a = _ep(a_raw, e.src_selector)
            b = _ep(b_raw, e.dst_selector)
            if not e.satisfies(a, b) or not e._anchor_ok(a, b) or not _strict_clear_brute(e, a, b, streams):
                ok = False
                break
        if ok:
            out.append(assign)
    return out
