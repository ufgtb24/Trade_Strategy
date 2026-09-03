# tests/path2/dag/test_engine_negation.py
"""NegationEdge:src 锚定窗口内禁止满足条件的 dst;dst 不进匹配。"""
from tests.path2.dag._oracle import E, Ev, keyset, brute_all
from path2.dag.edges import TemporalEdge, NegationEdge
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag._solve import compile_plan, solve


class _StubDetector:
    """占位 detector:只声明 event_cls(引擎测试不真跑 detect,streams 直给 solve)。"""
    event_cls = Ev


def _nspec(nodes, edges):
    return PatternSpec(pattern_id="n", nodes=tuple(nodes),
                       edges=tuple(edges))


def _nodes(ids):
    return [NodeSpec(node_id=n, detector=_StubDetector()) for n in ids]


def test_negation_blocks_when_forbidden_present():
    # A->B chain,且 A 之后 [1,10] 内禁止 X。X=(5,5) 在禁区 -> 整体无匹配。
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100),
             NegationEdge("A", "X", min_gap=1, max_gap=10)]
    streams = {"A": E("A", [(0, 0)]), "B": E("B", [(20, 20)]), "X": E("X", [(5, 5)])}
    sols = solve(compile_plan(_nspec(_nodes(["A", "B", "X"]), edges)), streams)
    assert sols == []


def test_negation_passes_when_clear():
    # X=(50,50) 落在禁区 [1,10] 外 -> 不违禁 -> 匹配成立,且 X 不进 assign。
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100),
             NegationEdge("A", "X", min_gap=1, max_gap=10)]
    streams = {"A": E("A", [(0, 0)]), "B": E("B", [(20, 20)]), "X": E("X", [(50, 50)])}
    sols = solve(compile_plan(_nspec(_nodes(["A", "B", "X"]), edges)), streams)
    assert len(sols) >= 1
    assert "X" not in sols[0].assign          # 否定 dst 不进匹配
    assert set(sols[0].assign) == {"A", "B"}


def test_negation_matches_brute():
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100),
             NegationEdge("A", "X", min_gap=1, max_gap=10)]
    streams = {"A": E("A", [(0, 0)]), "B": E("B", [(20, 20)]), "X": E("X", [(50, 50)])}
    pr = keyset(solve(compile_plan(_nspec(_nodes(["A", "B", "X"]), edges)), streams))
    assert pr == keyset(brute_all(edges, streams))
