# tests/path2/dag/test_engine_oracle.py
"""自测 oracle:brute_all 全枚举 + key 规范化可信。"""
from tests.path2.dag._oracle import E, keyset, brute_all
from path2.dag.edges import TemporalEdge


def test_brute_enumerates_all_satisfying():
    # A->B,A=[(0,0)],B=[(5,5),(8,8)] 都满足 gap>=0 -> 两个组合
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100)]
    streams = {"A": E("A", [(0, 0)]), "B": E("B", [(5, 5), (8, 8)])}
    ks = keyset(brute_all(edges, streams))
    assert len(list(ks.elements())) == 2


def test_brute_filters_by_satisfies():
    # max_gap=2 -> B(8,8) 够不到(gap=8) -> 只 B(5,5)
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=2)]
    streams = {"A": E("A", [(0, 3)]), "B": E("B", [(5, 5), (8, 8)])}
    ks = keyset(brute_all(edges, streams))
    keys = sorted(ks.elements())
    assert len(keys) == 1
    assert keys[0] == (("A", 0, 3, 0), ("B", 5, 5, 0))   # 规范 key


def test_keyset_is_multiset():
    edges = [TemporalEdge("A", "B")]
    streams = {"A": E("A", [(0, 0)]), "B": E("B", [(1, 1)])}
    ks = keyset(brute_all(edges, streams))
    assert ks[(("A", 0, 0, 0), ("B", 1, 1, 0))] == 1
