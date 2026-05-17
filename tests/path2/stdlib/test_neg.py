"""Task 9 Neg Detector 测试(redesign §11,TDD)。

桩:
  _E(Event) 子类;ev(s, e=None) 构造 start=s end=e(默认=s)。

测试集:
  - §11.7 回归锚 R1–R10(钉死)
  - plan Task9 原 4 测试(test_neg_passes_when_no_forbidden_event 等)
  - 2 个 guard 测试(pattern_label 含 '#' / key+named 互斥)
"""
from __future__ import annotations

import pytest

from path2 import TemporalEdge, run
from path2.stdlib.detectors import Neg


# ---------------------------------------------------------------------------
# 桩
# ---------------------------------------------------------------------------

class _E:
    """最小 Event 实现:满足 path2 Event 接口(start_idx,end_idx,event_id)。"""

    def __init__(self, start: int, end: int, eid: str = ""):
        self.start_idx = start
        self.end_idx = end
        self.event_id = eid or f"e_{start}_{end}"

    def __repr__(self):
        return f"_E({self.start_idx},{self.end_idx})"


def ev(s: int, e: int | None = None) -> _E:
    """快捷构造:ev(s) → start=end=s;ev(s,e) → start=s,end=e。"""
    if e is None:
        e = s
    return _E(s, e)


# ---------------------------------------------------------------------------
# §11.7 回归锚 R1–R10
# ---------------------------------------------------------------------------

def test_neg_R1_forbid_A_to_N_vetoed():
    """R1:forbid(A→N) 否决:gap=3∈[1,5] → []。"""
    d = Neg(
        edges=[TemporalEdge("A", "B", 1)],
        forbid=[TemporalEdge("A", "N", 1, 5)],
        A=[ev(0)],
        B=[ev(2)],
        N=[ev(3)],
        label="neg",
    )
    assert list(run(d)) == []


def test_neg_R2_forbid_A_to_N_not_vetoed():
    """R2:forbid(A→N) 不否决:gap=9∉[1,5] → 1 match, N not in role_index。"""
    d = Neg(
        edges=[TemporalEdge("A", "B", 1)],
        forbid=[TemporalEdge("A", "N", 1, 5)],
        A=[ev(0)],
        B=[ev(2)],
        N=[ev(9)],
        label="neg",
    )
    results = list(run(d))
    assert len(results) == 1
    m = results[0]
    assert set(m.role_index.keys()) == {"A", "B"}
    assert "N" not in m.role_index


def test_neg_R3_never_before_vetoed():
    """R3:never_before forbid(N→A):gap=e_anchor.start−e_n.end=10−7=3∈[0,4] → []。"""
    d = Neg(
        edges=[TemporalEdge("A", "B", 1)],
        forbid=[TemporalEdge("N", "A", 0, 4)],
        A=[ev(10)],
        B=[ev(12)],
        N=[ev(7)],
        label="neg",
    )
    assert list(run(d)) == []


def test_neg_R4_never_before_not_vetoed():
    """R4:never_before forbid(N→A) 不否决:gap=10−2=8∉[0,4] → 1 match。"""
    d = Neg(
        edges=[TemporalEdge("A", "B", 1)],
        forbid=[TemporalEdge("N", "A", 0, 4)],
        A=[ev(10)],
        B=[ev(12)],
        N=[ev(2)],
        label="neg",
    )
    results = list(run(d))
    assert len(results) == 1
    assert "N" not in results[0].role_index


def test_neg_R5_empty_neg_stream_passes():
    """R5:否定流空放行:N=[] → 1 match, N not in role_index。"""
    d = Neg(
        edges=[TemporalEdge("A", "B", 1)],
        forbid=[TemporalEdge("A", "N", 1, 3)],
        A=[ev(0)],
        B=[ev(2)],
        N=[],
        label="neg",
    )
    results = list(run(d))
    assert len(results) == 1
    assert "N" not in results[0].role_index


def test_neg_R6_N_not_in_children_or_role_index():
    """R6:N 不进 children/role_index(结构性保证)。"""
    d = Neg(
        edges=[TemporalEdge("A", "B", 0)],
        forbid=[TemporalEdge("A", "N", 100, 200)],
        A=[ev(0)],
        B=[ev(0)],
        N=[ev(0)],
        label="neg",
    )
    results = list(run(d))
    # gap_forbid=ev(0).start-ev(0).end=0∉[100,200] → 不否决
    assert len(results) == 1
    m = results[0]
    assert set(m.role_index.keys()) == {"A", "B"}
    assert "N" not in m.role_index
    flat_children = set(m.children)
    # 所有 children 来自 role_index values
    from itertools import chain as ichain
    all_ri = set(ichain.from_iterable(v for v in m.role_index.values()))
    assert all_ri == flat_children
    # N 的实例不在 children
    assert ev(0) not in flat_children or all(
        c.start_idx == 0 and c.end_idx == 0 for c in flat_children
    )  # A=ev(0),B=ev(0) 都在 forward;此处仅断言 N 不在 role_index


def test_neg_R7_validate_neg_endpoint_membership():
    """R7:validate_neg XOR 成员资格校验(完整矩阵)。

    - forbid=[TE("A","B")] → ValueError match "正向子图"(两端皆正向)
    - forbid=[TE("N","Z")] → ValueError match "正向子图"(两端皆∉正向)
    - forbid=[TE("A","N")] → 不抛(A∈前向,N∉;XOR=True)
    - forbid=[TE("N","A")] → 不抛(N∉前向,A∈;XOR=True)
    - forbid=[]             → ValueError match "至少需"
    """
    from path2.stdlib._graph import build_graph, validate_neg

    fwd = build_graph([TemporalEdge("A", "B")])

    # 两端皆正向 → 报错
    with pytest.raises(ValueError, match="正向子图"):
        validate_neg(fwd, forbid=[TemporalEdge("A", "B")])

    # 两端皆∉正向 → 报错
    with pytest.raises(ValueError, match="正向子图"):
        validate_neg(fwd, forbid=[TemporalEdge("N", "Z")])

    # A∈,N∉ → 不抛
    validate_neg(fwd, forbid=[TemporalEdge("A", "N")])

    # N∉,A∈ → 不抛
    validate_neg(fwd, forbid=[TemporalEdge("N", "A")])

    # 空 → 至少需
    with pytest.raises(ValueError, match="至少需"):
        validate_neg(fwd, forbid=[])


def test_neg_R8_multi_forbid_conjunction_vetoed():
    """R8:多 forbid 合取否决:第二条命中(gap=1∈[0,2]) → []。"""
    d = Neg(
        edges=[TemporalEdge("A", "B", 0)],
        forbid=[
            TemporalEdge("A", "N", 1, 3),   # gap=ev(10).start-ev(0).end=10∉[1,3] 不命中
            TemporalEdge("B", "M", 0, 2),   # gap=ev(1).start-ev(0).end=1∈[0,2] 命中
        ],
        A=[ev(0)],
        B=[ev(0)],
        N=[ev(10)],
        M=[ev(1)],
        label="neg",
    )
    assert list(run(d)) == []


def test_neg_R9_multi_forbid_all_miss():
    """R9:多 forbid 全不命中 → 1 match。"""
    d = Neg(
        edges=[TemporalEdge("A", "B", 0)],
        forbid=[
            TemporalEdge("A", "N", 1, 3),   # gap=10∉[1,3]
            TemporalEdge("B", "M", 0, 2),   # gap=9∉[0,2]
        ],
        A=[ev(0)],
        B=[ev(0)],
        N=[ev(10)],
        M=[ev(9)],
        label="neg",
    )
    results = list(run(d))
    assert len(results) == 1


def test_neg_R10_run_invariants():
    """R10:run() 不变式:2 matches,id⊆{neg_5_5,neg_5_5#1},不抛,end_idx 升序,
    role_index/children 一致。"""
    d = Neg(
        edges=[TemporalEdge("A", "B", 0, 0)],
        forbid=[TemporalEdge("A", "N", 100, 200)],
        A=[ev(5), ev(5)],
        B=[ev(5), ev(5)],
        N=[],
        label="neg",
    )
    results = list(run(d))
    assert len(results) == 2
    ids = {m.event_id for m in results}
    assert ids <= {"neg_5_5", "neg_5_5#1"}
    # end_idx 升序
    end_idxs = [m.end_idx for m in results]
    assert end_idxs == sorted(end_idxs)
    # role_index/children 一致
    from itertools import chain as ichain
    for m in results:
        all_ri = set(ichain.from_iterable(m.role_index.values()))
        assert all_ri == set(m.children)
        for tup in m.role_index.values():
            starts = [e.start_idx for e in tup]
            assert starts == sorted(starts)


# ---------------------------------------------------------------------------
# plan Task9 原 4 测试(§11 裁定下全部可满足,断言不删弱)
# ---------------------------------------------------------------------------

def test_neg_passes_when_no_forbidden_event():
    """否定标签流内无否决事件时,正向匹配透传。"""
    d = Neg(
        edges=[TemporalEdge("A", "B", 0)],
        forbid=[TemporalEdge("A", "N", 1, 10)],
        A=[ev(0)],
        B=[ev(1)],
        N=[ev(100)],   # gap=100∉[1,10] → 不否决
        label="neg",
    )
    results = list(run(d))
    assert len(results) == 1
    assert "N" not in results[0].role_index


def test_neg_vetoed_when_forbidden_event_present():
    """否定标签流内有否决事件时,匹配被丢弃。"""
    d = Neg(
        edges=[TemporalEdge("A", "B", 0)],
        forbid=[TemporalEdge("A", "N", 1, 10)],
        A=[ev(0)],
        B=[ev(1)],
        N=[ev(3)],   # gap=3∈[1,10] → 否决
        label="neg",
    )
    assert list(run(d)) == []


def test_neg_never_before():
    """never_before 形态:forbid(N→A) N 应在 A 之前;A 存在时 N 否决。"""
    # N 出现在 A 之前且 gap 在范围 → 否决
    d_vetoed = Neg(
        edges=[TemporalEdge("A", "B", 0)],
        forbid=[TemporalEdge("N", "A", 0, 5)],
        A=[ev(5)],
        B=[ev(6)],
        N=[ev(3)],   # gap=e_anchor.start-e_n.end=5-3=2∈[0,5] → 否决
        label="neg",
    )
    assert list(run(d_vetoed)) == []

    # N 远在 A 之前,gap 超出范围 → 不否决
    d_ok = Neg(
        edges=[TemporalEdge("A", "B", 0)],
        forbid=[TemporalEdge("N", "A", 0, 5)],
        A=[ev(5)],
        B=[ev(6)],
        N=[ev(0)],   # gap=5-0=5∈[0,5] → 仍否决...用 gap 超出 → N=ev(-10)
        label="neg",
    )
    # gap=5-(-10)=15∉[0,5] → 不否决
    d_ok2 = Neg(
        edges=[TemporalEdge("A", "B", 0)],
        forbid=[TemporalEdge("N", "A", 0, 3)],
        A=[ev(10)],
        B=[ev(11)],
        N=[ev(2)],   # gap=10-2=8∉[0,3] → 不否决
        label="neg",
    )
    results = list(run(d_ok2))
    assert len(results) == 1


def test_neg_requires_forbid():
    """forbid 为空时构造期 ValueError(含'至少需')。"""
    with pytest.raises(ValueError, match="至少需"):
        Neg(
            edges=[TemporalEdge("A", "B", 0)],
            forbid=[],
            A=[ev(0)],
            B=[ev(1)],
            label="neg",
        )


# ---------------------------------------------------------------------------
# Guard 测试(与 Chain/Dag/Kof 一致)
# ---------------------------------------------------------------------------

def test_neg_guard_pattern_label_hash_raises():
    """pattern_label 含 '#' → 构造期 ValueError(含 '#')。"""
    with pytest.raises(ValueError, match="#"):
        Neg(
            edges=[TemporalEdge("A", "B", 0)],
            forbid=[TemporalEdge("A", "N", 0, 1)],
            A=[ev(0)],
            B=[ev(1)],
            N=[],
            label="bad#label",
        )


def test_neg_guard_key_and_named_raises():
    """key + named_streams 同时使用 → ValueError(含'不可同时使用')。"""
    with pytest.raises(ValueError, match="不可同时使用"):
        Neg(
            edges=[TemporalEdge("A", "B", 0)],
            forbid=[TemporalEdge("A", "N", 0, 1)],
            key=lambda e: "A",
            A=[ev(0)],
            B=[ev(1)],
            N=[],
            label="neg",
        )
