"""Chain 公开类测试套件。

4 个计划基础测试 + 2 个守卫测试(pattern_label '#' 拒绝 + key/kwarg 互斥拒绝)。
"""
from dataclasses import dataclass

import pytest

from path2 import run
from path2.core import Event, TemporalEdge
from path2.stdlib.detectors import Chain


@dataclass(frozen=True)
class _E(Event):
    pass


def ev(s, e=None):
    e = s if e is None else e
    return _E(event_id=f"e_{s}_{e}", start_idx=s, end_idx=e)


# ---------------------------------------------------------------------------
# 计划 Task-6 四个基础测试(verbatim)
# ---------------------------------------------------------------------------

def test_chain_basic_named_streams():
    d = Chain(
        edges=[TemporalEdge("A", "B", min_gap=1)],
        A=[ev(0), ev(10)],
        B=[ev(2), ev(12)],
        label="ab",
    )
    ms = list(run(d))
    assert [(m.start_idx, m.end_idx) for m in ms] == [(0, 2), (10, 12)]
    assert all(m.pattern_label == "ab" for m in ms)
    assert ms[0].event_id == "ab_0_2"


def test_chain_branching_edges_rejected_at_construction():
    with pytest.raises(ValueError, match="线性路径"):
        Chain(
            edges=[TemporalEdge("A", "B"), TemporalEdge("A", "C")],
            A=[ev(0)], B=[ev(1)], C=[ev(2)],
        )


def test_chain_non_default_anchoring_rejected():
    with pytest.raises(ValueError, match="anchoring"):
        Chain(
            edges=[TemporalEdge("A", "B")],
            A=[ev(0)], B=[ev(1)],
            anchoring="latest-feasible",
        )


def test_chain_run_invariants_id_unique_and_ascending():
    d = Chain(
        edges=[TemporalEdge("A", "B", min_gap=1)],
        A=[ev(0), ev(5)],
        B=[ev(2), ev(7)],
        label="p",
    )
    ms = list(run(d))
    ids = [m.event_id for m in ms]
    assert len(ids) == len(set(ids))
    assert [m.end_idx for m in ms] == sorted(m.end_idx for m in ms)


# ---------------------------------------------------------------------------
# 守卫测试 1:pattern_label 含 '#' 被拒绝(redesign §7)
# ---------------------------------------------------------------------------

def test_chain_pattern_label_with_hash_rejected():
    with pytest.raises(ValueError, match="#"):
        Chain(
            edges=[TemporalEdge("A", "B")],
            A=[ev(0)], B=[ev(1)],
            label="a#b",
        )


# ---------------------------------------------------------------------------
# 守卫测试 2:key 与具名流(kwarg)不可同时使用(互斥)
# ---------------------------------------------------------------------------

def test_chain_key_and_named_together_rejected():
    with pytest.raises(ValueError, match="不可同时使用"):
        Chain(
            edges=[TemporalEdge("A", "B")],
            key=lambda e: "A",
            A=[ev(0)], B=[ev(1)],
        )


# ---------------------------------------------------------------------------
# 边界:无可行匹配时产出空(不抛异常)
# ---------------------------------------------------------------------------

def test_chain_no_match_yields_empty():
    d = Chain(
        edges=[TemporalEdge("A", "B", max_gap=5)],
        A=[ev(0)], B=[ev(100)],
        label="z",
    )
    assert list(run(d)) == []
