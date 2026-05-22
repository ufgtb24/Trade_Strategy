"""Dag 公开类测试套件。

3 个计划 Task-7 基础测试 + 4 个补充测试(多 WCC 归并 / '#' 拒绝 / key+kwarg 互斥)。
"""
from dataclasses import dataclass

import pytest

from path2 import run
from path2.core import Event, TemporalEdge
from path2.stdlib.detectors import Dag


@dataclass(frozen=True)
class _E(Event):
    pass


def ev(s, e=None):
    e = s if e is None else e
    return _E(event_id=f"e_{s}_{e}", start_idx=s, end_idx=e)


# ---------------------------------------------------------------------------
# 计划 Task-7 三个基础测试(verbatim)
# ---------------------------------------------------------------------------

def test_dag_multi_indegree_convergence():
    """A→C(1,10) + B→C(1,3):C.start=7,7-0=7∈[1,10] ok,7-5=2∈[1,3] ok → 1 match end=7。"""
    d = Dag(
        edges=[
            TemporalEdge("A", "C", min_gap=1, max_gap=10),
            TemporalEdge("B", "C", min_gap=1, max_gap=3),
        ],
        A=[ev(0)],
        B=[ev(5)],
        C=[ev(7)],
        label="conv",
    )
    ms = list(run(d))
    assert len(ms) == 1
    assert ms[0].end_idx == 7
    assert set(ms[0].role_index) == {"A", "B", "C"}


def test_dag_cycle_rejected_at_construction():
    """含环的 edges 应在 Dag 构造期抛出 ValueError 含"环"。"""
    with pytest.raises(ValueError, match="环"):
        Dag(
            edges=[TemporalEdge("A", "B"), TemporalEdge("B", "A")],
            A=[ev(0)],
            B=[ev(1)],
        )


def test_dag_default_label():
    """未传 label 时 pattern_label 默认为 "dag"。"""
    d = Dag(
        edges=[TemporalEdge("A", "B", min_gap=1)],
        A=[ev(0)],
        B=[ev(2)],
    )
    ms = list(run(d))
    assert len(ms) == 1
    assert ms[0].pattern_label == "dag"
    assert ms[0].event_id == "dag_0_2"


def test_dag_non_default_anchoring_rejected():
    """非默认 anchoring 应在构造期抛出 ValueError 含 "anchoring"。"""
    with pytest.raises(ValueError, match="anchoring"):
        Dag(
            edges=[TemporalEdge("A", "B")],
            A=[ev(0)],
            B=[ev(1)],
            anchoring="latest-feasible",
        )


# ---------------------------------------------------------------------------
# 补充测试
# ---------------------------------------------------------------------------

def test_dag_multi_wcc_merged():
    """两个独立 WCC(A→B, C→D)的匹配按 end_idx 升序 p 路归并。"""
    d = Dag(
        edges=[
            TemporalEdge("A", "B", min_gap=1),
            TemporalEdge("C", "D", min_gap=1),
        ],
        A=[ev(0)],
        B=[ev(2)],
        C=[ev(1)],
        D=[ev(3)],
        label="m",
    )
    ms = list(run(d))
    assert len(ms) == 2
    end_idxs = [m.end_idx for m in ms]
    assert end_idxs == sorted(end_idxs), "end_idx 须升序(p 路归并正确性)"
    assert end_idxs == [2, 3]
    assert set(ms[0].role_index) == {"A", "B"}
    assert set(ms[1].role_index) == {"C", "D"}


def test_dag_pattern_label_hash_rejected():
    """pattern_label 含 '#' 应在构造期抛出 ValueError 含 '#'。"""
    with pytest.raises(ValueError, match="#"):
        Dag(
            edges=[TemporalEdge("A", "B")],
            A=[ev(0)],
            B=[ev(1)],
            label="x#y",
        )


def test_dag_key_and_named_rejected():
    """key 与具名流(kwarg)同时传入应抛出 ValueError 含 '不可同时使用'。"""
    with pytest.raises(ValueError, match="不可同时使用"):
        Dag(
            edges=[TemporalEdge("A", "B")],
            key=lambda e: "A",
            A=[ev(0)],
            B=[ev(1)],
        )
