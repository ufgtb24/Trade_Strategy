"""C：W.child/W.children 复用现有谓词作用于 event 的 child（依赖阶段 A 的 child API）。"""
from dataclasses import dataclass
from typing import Tuple
from path2.core import Event
from path2.dag import where as W


@dataclass(frozen=True)
class _Bo(Event):
    class_id = "test_childcomb_bo"
    drought: int = 0
    peaks: Tuple[int, ...] = ()


@dataclass(frozen=True)
class _Burst(Event):
    class_id = "test_childcomb_burst"
    members: Tuple[_Bo, ...] = ()
    def child_slots(self):
        return {"members": self.members}
    def child(self, name):
        if name == "first_bo":
            return self.members[0]
        raise KeyError(name)
    def children(self, name):
        if name == "members":
            return self.members
        raise KeyError(name)


def test_w_child_reads_single_child_attr():
    b = _Burst(event_id="b", start_idx=1, end_idx=3,
               members=(_Bo(event_id="x", start_idx=1, end_idx=1, drought=70),))
    pred = W.child("first_bo", W.attr("drought", ">=", 60))
    assert pred(b, None) is True
    pred_fail = W.child("first_bo", W.attr("drought", ">=", 80))
    assert pred_fail(b, None) is False


def test_w_children_aggregates_child_group():
    b = _Burst(event_id="b", start_idx=1, end_idx=3, members=(
        _Bo(event_id="x", start_idx=1, end_idx=1, peaks=(1, 2)),
        _Bo(event_id="y", start_idx=2, end_idx=2, peaks=(2, 3)),
    ))
    # 用 lambda 聚合:members 中所有 peaks 的并集大小 >= N
    def distinct_peaks_ge(n):
        return lambda seq, ctx: len({p for ev in seq for p in ev.peaks}) >= n
    pred = W.children("members", distinct_peaks_ge(3))
    assert pred(b, None) is True
    assert W.children("members", distinct_peaks_ge(4))(b, None) is False
