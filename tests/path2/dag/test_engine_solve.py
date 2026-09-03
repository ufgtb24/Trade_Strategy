# tests/path2/dag/test_engine_solve.py
"""verdict §7.3:solve 完备(SOLVE==BRUTE) + necessity(C1/NAIVE 必漏)。"""
from tests.path2.dag._oracle import E, keyset, brute_all
from path2.dag.edges import TemporalEdge
from path2.dag._solve import compile_plan, solve
from tests.path2.dag.test_engine_edges import _spec


def _solve(edges, streams, **kw):
    return solve(compile_plan(_spec(edges, streams)), streams, **kw)


def test_SOLVE_BOTH_SAMEEND():
    # 同 end 不同 start 的 B -> solve 给两个组合(C1 会丢一个)
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100)]
    streams = {"A": E("A", [(0, 0)]), "B": E("B", [(12, 14), (13, 14)])}
    assert keyset(_solve(edges, streams)) == keyset(brute_all(edges, streams))
    assert len(list(keyset(_solve(edges, streams)).elements())) == 2


def test_SOLVE_C1_DROPS():
    # 开 C1 -> 漏(只给一个) => 证 C1 必须关(对非叶子节点仍成立)
    # B2.2: B 是叶子时 c1_off 包含 B,C1 已关;改用 A→B→C 三节点链,B 非叶子,C1 仍塌缩 B 导致漏
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100),
             TemporalEdge("B", "C", min_gap=0, max_gap=100)]
    streams = {"A": E("A", [(0, 0)]), "B": E("B", [(12, 14), (13, 14)]), "C": E("C", [(20, 25)])}
    assert keyset(_solve(edges, streams, collapse=True)) != keyset(brute_all(edges, streams))


def test_SOLVE_NAIVE_DROPS():
    # naive memo 把成功前沿也记 FAILED -> 漏兄弟源组合 => 证 charitable 必须
    # B3 放宽:leaf 不再跨 match 独占 -> 两个 A 各配 B 一次,solve == brute_all
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100)]
    streams = {"A": E("A", [(0, 5), (1, 5)]), "B": E("B", [(7, 9)])}
    pr = keyset(_solve(edges, streams))
    ba = keyset(brute_all(edges, streams))
    assert pr == ba, "放宽后 solve 枚举所有合法绑定(无假阳无假阴)"
    assert keyset(_solve(edges, streams, memo_mode="naive")) != ba  # naive 仍漏


def test_SOLVE_NOMEMO_complete():
    # 关 memo 平凡完备(只是慢) —— B3 放宽后对共享-leaf 场景也成立
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100)]
    streams = {"A": E("A", [(0, 5), (1, 5)]), "B": E("B", [(7, 9)])}
    pr = keyset(_solve(edges, streams, memo_mode="off"))
    ba = keyset(brute_all(edges, streams))
    assert pr == ba, "memo=off: 枚举所有合法绑定"


def test_leaf_shared_all_matches_visible():
    """同一 leaf 被多个上游共享 -> 每个上游各产一个 match(不再独占)。"""
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100)]
    streams = {"A": E("A", [(0, 5), (1, 5)]), "B": E("B", [(7, 9)])}
    sols = _solve(edges, streams)
    assert len(sols) == 2
    assert {s.assign["A"].start_idx for s in sols} == {0, 1}
    assert {s.assign["B"].event_id for s in sols} == {sols[0].assign["B"].event_id}
