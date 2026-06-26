# tests/path2/dag/test_engine_strict.py
"""verdict §7.4:strict next = 窗口内第一个;数据依赖,不可折进 feasible_window。"""
from tests.path2.dag._oracle import E, keyset, brute_all
from path2.dag.edges import TemporalEdge
from path2.dag._solve import compile_plan, solve
from tests.path2.dag.test_engine_edges import _spec, _noprune


def _pruned(edges, streams):
    return solve(compile_plan(_spec(edges, streams)), streams)


def test_STRICT_FIRST_ONLY():
    # A->B strict:只 B(5,5) 可绑;B(8,8) 被 B(5,5) 挡。NEXT 给唯一解。
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100, strict=True)]
    streams = {"A": E("A", [(0, 0)]), "B": E("B", [(5, 5), (8, 8)])}
    pr = keyset(_pruned(edges, streams))
    assert sorted(pr.elements()) == [(("A", 0, 0, 0), ("B", 5, 5, 0))]
    # 同 strict 下 PRUNED==NOPRUNE(strict 不破坏 next-mode 剪枝等价)
    assert pr == keyset(_noprune(edges, streams))


def test_STRICT_RELAXED_DIFF():
    # 同数据 strict=False:两个解都给(B(5,5) 和 B(8,8))
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100, strict=False)]
    streams = {"A": E("A", [(0, 0)]), "B": E("B", [(5, 5), (8, 8)])}
    ba = keyset(brute_all(edges, streams))
    assert len(list(ba.elements())) == 2


def test_STRICT_NOT_WINDOW():
    # 数据依赖 blocker:b0=(5,5) 挡 b1=(8,8),但 b0 够不到 C,b1 够 -> strict 整体空;
    # relaxed 能绕过 b0 绑 b1 完成 -> 二者分歧 => strict 非静态窗口。
    edges_s = [TemporalEdge("A", "B", min_gap=0, max_gap=100, strict=True),
               TemporalEdge("B", "C", min_gap=1, max_gap=3)]
    edges_r = [TemporalEdge("A", "B", min_gap=0, max_gap=100, strict=False),
               TemporalEdge("B", "C", min_gap=1, max_gap=3)]
    streams = {"A": E("A", [(0, 0)]), "B": E("B", [(5, 5), (8, 8)]), "C": E("C", [(10, 10)])}
    s = keyset(brute_all(edges_s, streams))
    r = keyset(brute_all(edges_r, streams))
    assert list(s.elements()) == []                       # strict 空
    assert sorted(r.elements()) == [(("A", 0, 0, 0), ("B", 8, 8, 1), ("C", 10, 10, 0))]
    assert s != r                                          # DISAGREE
    # 剪枝端与暴力端用同一 blocker 规则
    assert keyset(_pruned(edges_s, streams)) == s
