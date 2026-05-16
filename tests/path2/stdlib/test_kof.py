"""Kof 滑窗计数 Detector 测试套件。

5 个计划 Task-8 基础测试(verbatim) + 2 个守卫测试
(pattern_label '#' 拒绝 + key/kwarg 互斥拒绝)。
"""
from dataclasses import dataclass

import pytest

from path2 import run
from path2.core import Event, TemporalEdge
from path2.stdlib.detectors import Kof


@dataclass(frozen=True)
class _E(Event):
    pass


def ev(s, e=None):
    e = s if e is None else e
    return _E(event_id=f"e_{s}_{e}", start_idx=s, end_idx=e)


# ---------------------------------------------------------------------------
# 计划 Task-8 五个基础测试(verbatim)
# ---------------------------------------------------------------------------

def test_kof_2_of_3_satisfied():
    # 3 条 edge,要求 >=2 满足
    edges = [
        TemporalEdge("A", "B", min_gap=1, max_gap=5),
        TemporalEdge("B", "C", min_gap=1, max_gap=5),
        TemporalEdge("A", "C", min_gap=1, max_gap=2),  # 这条会被违反
    ]
    d = Kof(
        edges=edges, k=2,
        A=[ev(0)], B=[ev(3)], C=[ev(6)],
        label="kof",
    )
    ms = list(run(d))
    assert len(ms) == 1
    # A->B: 3-0=3 ok ; B->C: 6-3=3 ok ; A->C: 6-0=6 >2 违反 → 2/3 满足 >=k
    assert set(ms[0].role_index) == {"A", "B", "C"}


def test_kof_below_k_no_match():
    edges = [
        TemporalEdge("A", "B", min_gap=1, max_gap=2),
        TemporalEdge("B", "C", min_gap=1, max_gap=2),
    ]
    d = Kof(
        edges=edges, k=2,
        A=[ev(0)], B=[ev(10)], C=[ev(20)],  # 两条都违反
        label="kof",
    )
    assert list(run(d)) == []


def test_kof_k_out_of_range_rejected():
    with pytest.raises(ValueError, match="k"):
        Kof(
            edges=[TemporalEdge("A", "B")], k=5,
            A=[ev(0)], B=[ev(1)],
        )


def test_kof_event_id_disambiguator_on_collision():
    # 构造同 (label,s,e) 撞:两组不同成员但区间相同
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100)]
    d = Kof(
        edges=edges, k=1,
        A=[ev(0, 0), ev(0, 0)],   # 两个区间相同的 A(不同实例)
        B=[ev(1, 1), ev(1, 1)],
        label="kof",
    )
    ms = list(run(d))
    ids = [m.event_id for m in ms]
    assert len(ids) == len(set(ids)), f"event_id 应单 run 唯一: {ids}"
    assert any("#" in i for i in ids)


def test_kof_yield_end_idx_ascending():
    edges = [TemporalEdge("A", "B", min_gap=1, max_gap=5)]
    d = Kof(
        edges=edges, k=1,
        A=[ev(0), ev(20)],
        B=[ev(2), ev(22)],
        label="kof",
    )
    ms = list(run(d))
    ends = [m.end_idx for m in ms]
    assert ends == sorted(ends)


# ---------------------------------------------------------------------------
# 守卫测试
# ---------------------------------------------------------------------------

def test_kof_pattern_label_hash_rejected():
    with pytest.raises(ValueError, match="#"):
        Kof(
            edges=[TemporalEdge("A", "B")],
            k=1,
            label="x#y",
            A=[ev(0)], B=[ev(1)],
        )


def test_kof_key_and_named_rejected():
    with pytest.raises(ValueError, match="不可同时使用"):
        Kof(
            edges=[TemporalEdge("A", "B")],
            k=1,
            key=lambda e: "A",
            A=[ev(0)], B=[ev(1)],
        )
