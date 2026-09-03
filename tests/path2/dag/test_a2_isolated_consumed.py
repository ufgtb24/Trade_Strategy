"""K2 三要素判据回归:求解 = edge 连通分量(端点并集) ∩ 非 neg_dst ∩ detector 非空。

设计依据(P1 拍板):含边 pattern 的孤立未消费 node 平凡解从保留变不产——
孤立即不属 pattern,独立信号用独立 pattern 表达。零边全孤立形态除外
(edges 空 → all_solve → 全求解,如 bo_only,其平凡 match 是唯一业务命中)。
A2 出口过滤已删(机制取消,行为由三要素判据在求解期保证)。
"""
from tests.path2.dag._oracle import Ev
from path2.dag.edges import TemporalEdge
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag.engine import analyze


class FakeDetector:
    """合成 detector,detect(self, *source) 任意元数兼容。"""
    event_cls = Ev
    def __init__(self, evs): self._evs = evs
    def detect(self, *source): return iter(self._evs)


def _spec(nodes, edges):
    return PatternSpec(pattern_id="a2_test",
                       nodes=tuple(nodes), edges=tuple(edges))


def test_all_isolated_non_consumed_pattern_emits_trivial_matches():
    """全孤立 pattern(单节点零边) → 每 event 一 match,node_index={node}。

    K2 例外:整个 pattern 无任何 edge 时 all_solve → 全求解(bo_only 形态
    nodes=("bo",) edges=() 的平凡 match 是唯一业务命中,保留)。
    """
    bo = NodeSpec("bo", detector=FakeDetector([
        Ev("bo0", 1, 1), Ev("bo1", 5, 5), Ev("bo2", 9, 9),
    ]))
    res = analyze(_spec([bo], edges=()), df=object())
    assert len(res.matches) == 3
    for m in res.matches:
        assert set(m.node_index.keys()) == {"bo"}


def test_mixed_pattern_drops_non_consumed_isolated_node_matches():
    """混合 pattern:正常 A→B 链 + 孤立未消费 x_node → 只产完整 match。

    K2 三要素判据: 求解 = edge 连通分量(端点并集) ∩ 非 neg_dst ∩ detector 非空;
    孤立 x_node 不在边端点 → 不求解、不产平凡解(P1 已拍板)。
    """
    A = NodeSpec("A", detector=FakeDetector([Ev("a0", 0, 0)]))
    B = NodeSpec("B", detector=FakeDetector([Ev("b0", 3, 3)]))
    X = NodeSpec("x_node", detector=FakeDetector([Ev("x0", 7, 7), Ev("x1", 8, 8)]))
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100)]
    res = analyze(_spec([A, B, X], edges), df=object())

    full = [m for m in res.matches if "A" in m.node_index and "B" in m.node_index]
    x_only = [m for m in res.matches
              if set(m.node_index.keys()) == {"x_node"}]
    assert len(full) >= 1
    assert x_only == []          # ★ 改: P1 后孤立平凡解不产(原断言 x_only 非空)


def test_isolated_consumed_node_match_still_not_emitted_regression():
    """bbb 形态回归:bo 孤立无边(被 burst/tb consumes_stream 引用) → 单 {bo} match 不产。

    K2 判据下 bo 不在边端点 → 不求解、无平凡解;可观察行为与旧 A2 过滤一致
    (A2 机制已删,此测试保住行为不变)。
    """
    bo = NodeSpec("bo", detector=FakeDetector([Ev("bo0", 1, 1), Ev("bo1", 4, 4)]))
    burst = NodeSpec("burst", detector=FakeDetector([Ev("burst0", 5, 5)]),
                     consumes_stream="bo")
    # bo 不在 edges 端点,但被 burst.consumes_stream 引用
    # burst 在 edges 端点中
    tb = NodeSpec("tb", detector=FakeDetector([Ev("tb0", 6, 6)]),
                  consumes_stream="bo")
    edges = [TemporalEdge("burst", "tb", min_gap=0, max_gap=100)]
    res = analyze(_spec([bo, burst, tb], edges), df=object())

    bo_only_matches = [m for m in res.matches
                       if set(m.node_index.keys()) == {"bo"}]
    assert bo_only_matches == [], "{bo} 孤立平凡解不产(bo 被 consumes_stream 消费、不在边端点)"


def test_zero_edge_consumed_node_still_emits_trivial_matches():
    """零边 + consumes_stream:all_solve 例外下,被消费节点也产平凡解(旧 A2 会滤)。

    K2 例外边界:edges 空 → all_solve → 全求解(与上方有边形态相反——含边时孤立被消费
    节点不产)。零边 pattern 的平凡 match 是唯一业务命中(bo_only 形态),consumes_stream
    引用不影响求解集合。
    """
    A = NodeSpec("A", detector=FakeDetector([Ev("a0", 1, 1), Ev("a1", 5, 5)]))
    B = NodeSpec("B", detector=FakeDetector([Ev("b0", 7, 7)]), consumes_stream="A")
    res = analyze(_spec([A, B], edges=()), df=object())

    a_only = [m for m in res.matches if set(m.node_index.keys()) == {"A"}]
    assert len(a_only) == 2          # A 平凡解存在(零边全求解,与有边形态不产相反)
    b_only = [m for m in res.matches if set(m.node_index.keys()) == {"B"}]
    assert len(b_only) == 1
