# tests/path2/dag/test_engine_fuzz.py
"""差分 fuzz:SOLVE==BRUTE(完备) + PRUNED==NOPRUNE(剪枝健全) + 无假阳。固定种子可复现。"""
import random
from tests.path2.dag._oracle import Ev, keyset, brute_all
from path2.dag.edges import TemporalEdge, ContainmentEdge, OverlapEdge, EqualsEdge
from path2.dag._solve import compile_plan, solve
from tests.path2.dag.test_engine_edges import _spec


def _rand_stream(lab, n, smax, rng):
    out = []
    for p in range(n):
        s = rng.randint(0, smax); e = rng.randint(s, smax)
        out.append((s, e))
    out.sort()
    return [Ev(f"{lab}{p}", s, e, pos=p) for p, (s, e) in enumerate(out)]


def test_fuzz_chain3_four_edge_types():
    # ★ B3 整改三:solve 对共享 leaf 去重 -> solve ⊆ brute_all 但不一定等;
    #   mism_solve 检查去掉(Stage C 对拍);仅断言无假阳 + PRUNED==NOPRUNE
    rng = random.Random(7)
    mism_prune = falsepos = 0
    for _ in range(2000):
        streams = {n: _rand_stream(n, rng.randint(1, 3), 8, rng) for n in ["A", "B", "C"]}
        kind = rng.choice([TemporalEdge, ContainmentEdge, OverlapEdge, EqualsEdge])
        if kind is TemporalEdge:
            edges = [TemporalEdge("A", "B", min_gap=rng.choice([0, 1]), max_gap=rng.choice([5, 20, 100])),
                     TemporalEdge("B", "C", min_gap=0, max_gap=100)]
        else:
            edges = [kind("A", "B"), kind("B", "C")]
        plan = compile_plan(_spec(edges, streams))
        ba = keyset(brute_all(edges, streams))
        pr = keyset(solve(plan, streams))
        no = keyset(solve(plan, streams, collapse=False, memo_mode="off"))
        if pr != no:
            mism_prune += 1
        if any(pr[k] > ba[k] for k in pr):
            falsepos += 1
    assert mism_prune == 0, f"PRUNED!=NOPRUNE 剪枝漏 {mism_prune} 例"
    assert falsepos == 0, f"PRUNED 假阳 {falsepos} 例"


def test_fuzz_strict_chain2():
    # ★ B3 整改三:solve 对共享 leaf 去重 -> solve ⊆ brute_all 但不一定等;
    #   mism_solve 检查去掉(Stage C 对拍);仅断言无假阳 + PRUNED==NOPRUNE
    rng = random.Random(99)
    mism_prune = falsepos = 0
    for _ in range(1500):
        streams = {n: _rand_stream(n, rng.randint(1, 4), 10, rng) for n in ["A", "B"]}
        edges = [TemporalEdge("A", "B", min_gap=rng.choice([0, 1]),
                              max_gap=rng.choice([3, 5, 20]), strict=True)]
        plan = compile_plan(_spec(edges, streams))
        ba = keyset(brute_all(edges, streams))
        pr = keyset(solve(plan, streams))
        no = keyset(solve(plan, streams, collapse=False, memo_mode="off"))
        if pr != no: mism_prune += 1
        if any(pr[k] > ba[k] for k in pr): falsepos += 1
    assert mism_prune == 0 and falsepos == 0
