"""Kof = LEF-DFS 结构姊妹 测试套件(redesign §10,重实现 TDD)。

含:
- 6 个 redesign §10.8 回归锚(A-KOF-C1/C2/OV/NP/WCC/ID,钉死);
- plan 原 5 个 Kof 基础测试(verbatim,断言不删弱);
- 2 个守卫测试(pattern_label '#' 拒绝 + key/kwarg 互斥)。
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
# redesign §10.8 回归锚
# ---------------------------------------------------------------------------

def test_a_kof_c1_member_enumeration_backtracks():
    """A-KOF-C1(修 CRITICAL-1):盲取 argmin 会漏掉合法成员组合。

    edges=[A→B(10,10)],k=1,A=[ev(0,0)],B=[ev(1,1),ev(10,10)]
    → 恰 1 命中:B 须回溯到 ev(10,10)(gap=10∈[10,10]),
      非盲取 start-first argmin 的 ev(1,1)(gap=1∉[10,10])。
    旧滑窗实现产出 []。
    """
    edges = [TemporalEdge("A", "B", min_gap=10, max_gap=10)]
    d = Kof(edges=edges, k=1, A=[ev(0, 0)], B=[ev(1, 1), ev(10, 10)],
            label="kof")
    ms = list(run(d))
    assert len(ms) == 1
    m = ms[0]
    assert set(m.role_index) == {"A", "B"}
    assert m.role_index["A"] == (ev(0, 0),)
    assert m.role_index["B"] == (ev(10, 10),)
    assert m.children == (ev(0, 0), ev(10, 10))
    assert m.start_idx == 0
    assert m.end_idx == 10


def test_a_kof_c2_zero_buffer_large_n():
    """A-KOF-C2(修 CRITICAL-2,零缓冲):

    edges=[A→B(0,inf)],k=1,A=[ev(i,i)],B=[ev(i,1e9+i)],N=3000
    → 产出 N 个,emitted end_idx 单调不减,run(d) 不抛/不 OOM。
    单 WCC ⇒ 缓冲恒为零(advance_kof 单 WCC 分支直接透传 _kof_produce_wcc
    生成器,任意时刻未 yield 的物化匹配数 = 0)。
    """
    N = 3000
    base = 1_000_000_000
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=float("inf"))]
    d = Kof(
        edges=edges, k=1,
        A=[ev(i, i) for i in range(N)],
        B=[ev(i, base + i) for i in range(N)],
        label="kof",
    )
    ms = list(run(d))
    assert len(ms) == N
    ends = [m.end_idx for m in ms]
    assert ends == sorted(ends)


def test_a_kof_ov_non_overlapping_consumption():
    """A-KOF-OV(修 IMPORTANT-2 非重叠):

    edges=[A→B(0,5)],k=1,A=[ev(0,0),ev(1,1)],B=[ev(2,2)]
    → 恰 1 命中(B(2,2) 被首命中全成员非重叠消费后耗尽)。
    旧实现每锚从整流重选 ⇒ 2 个重叠命中。
    """
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=5)]
    d = Kof(edges=edges, k=1, A=[ev(0, 0), ev(1, 1)], B=[ev(2, 2)],
            label="kof")
    ms = list(run(d))
    assert len(ms) == 1


def test_a_kof_np_no_partial_match():
    """A-KOF-NP(no partial,redesign §10.4):

    edges=[A→B(0,5),B→C(0,5),A→C(0,2)],k=1。
    C=[] → 无命中(标签 C 后缀无候选 ⇒ 不产出缺标签部分命中);
    C=[ev(3,3)] → 恰 1 命中,全标签在场。
    """
    edges = [
        TemporalEdge("A", "B", min_gap=0, max_gap=5),
        TemporalEdge("B", "C", min_gap=0, max_gap=5),
        TemporalEdge("A", "C", min_gap=0, max_gap=2),
    ]
    d_empty = Kof(edges=edges, k=1, A=[ev(0, 0)], B=[ev(1, 1)], C=[],
                  label="kof")
    assert list(run(d_empty)) == []

    d_ok = Kof(edges=edges, k=1, A=[ev(0, 0)], B=[ev(1, 1)], C=[ev(3, 3)],
               label="kof")
    ms = list(run(d_ok))
    assert len(ms) == 1
    assert set(ms[0].role_index) == {"A", "B", "C"}


def test_a_kof_wcc_single_wcc_required():
    """A-KOF-WCC(redesign §10.7):多 WCC 构造期 ValueError(不连通)。

    edges=[A→B, C→D] 两个不连通分量 ⇒ k-of-n 无明确语义。
    """
    with pytest.raises(ValueError, match="连通"):
        Kof(
            edges=[TemporalEdge("A", "B"), TemporalEdge("C", "D")],
            k=1,
            A=[ev(0)], B=[ev(1)], C=[ev(2)], D=[ev(3)],
        )


def test_a_kof_id_shared_seq_byte_identical():
    """A-KOF-ID(共享 #seq 字节一致,redesign §7):

    edges=[A→B(0,0)],k=1,A=[ev(5,5),ev(5,5)],B=[ev(5,5),ev(5,5)]
    → ids ⊆ {"kof_5_5","kof_5_5#1"};run() 不抛;end_idx 升序;
      flatten(role_index.values()) == children。
    """
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=0)]
    d = Kof(edges=edges, k=1,
            A=[ev(5, 5), ev(5, 5)], B=[ev(5, 5), ev(5, 5)],
            label="kof")
    ms = list(run(d))
    ids = {m.event_id for m in ms}
    assert ids <= {"kof_5_5", "kof_5_5#1"}
    ends = [m.end_idx for m in ms]
    assert ends == sorted(ends)
    for m in ms:
        flat = set()
        for vals in m.role_index.values():
            flat.update(vals)
        assert flat == set(m.children)


# ---------------------------------------------------------------------------
# plan 原 5 个 Kof 基础测试(verbatim,断言不删弱)
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
