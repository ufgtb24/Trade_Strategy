"""A2 过滤判据回归:从「孤立无边 role」收紧到「孤立无边 AND 被消费 role」。

设计依据:A2 原意是拦截「流源 role 被回显的残缺 match」(bbb 的 bo 被 burst/tb
consumes_stream 消费,单 {bo} match 是噪声)。但旧判据只看「孤立」不看「被消费」,
误伤了「全孤立 pattern」(如 bo_only,单 BODetector 节点零边、无消费者)——这种
pattern 的平凡 match 是其唯一业务命中,本不该被过滤。

新判据:对 candidate match,iff role_index 的所有 key 都满足
  (k 不出现在任一 edge 端点) AND (k 被某 node 的 consumes_stream 引用)
则过滤。
"""
from tests.path2.dag._oracle import Ev
from path2.dag.edges import TemporalEdge
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag.engine import analyze


class FakeDetector:
    """合成 detector,detect(self, *source) 任意元数兼容。"""
    def __init__(self, evs): self._evs = evs
    def detect(self, *source): return iter(self._evs)


def _spec(nodes, edges, root):
    return PatternSpec(pattern_id="a2_test",
                       nodes=tuple(nodes), edges=tuple(edges), root=root)


def test_all_isolated_non_consumed_pattern_emits_trivial_matches():
    """全孤立 pattern(单节点零边、无消费者) → 每 event 一 match,role_index={node}.

    bo_only 形态:nodes=("bo",) edges=() consumes_stream 全 None。当前 A2 错误过滤、
    matches=()。修复后:matches 长度 = events 数,每个 role_index 只含 "bo" 键。
    """
    bo = NodeSpec("bo", detector=FakeDetector([
        Ev("bo0", 1, 1), Ev("bo1", 5, 5), Ev("bo2", 9, 9),
    ]))
    res = analyze(_spec([bo], edges=(), root="bo"), df=object())
    assert len(res.matches) == 3
    for m in res.matches:
        assert set(m.role_index.keys()) == {"bo"}


def test_mixed_pattern_keeps_non_consumed_isolated_role_matches():
    """混合 pattern:正常 A→B 链 + 孤立未消费 x_node → 两种 match 都出。

    spec:
      A → B 边(各自有边、不在 isolated)
      x_node 孤立、无 consumes_stream 引用
    预期:matches 含 {A,B} 完整 match (1 条) + {x_node} 单 role match (events 数条)。
    """
    A = NodeSpec("A", detector=FakeDetector([Ev("a0", 0, 0)]))
    B = NodeSpec("B", detector=FakeDetector([Ev("b0", 3, 3)]))
    X = NodeSpec("x_node", detector=FakeDetector([Ev("x0", 7, 7), Ev("x1", 8, 8)]))
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=100)]
    res = analyze(_spec([A, B, X], edges, root="A"), df=object())

    full = [m for m in res.matches if "A" in m.role_index and "B" in m.role_index]
    x_only = [m for m in res.matches
              if set(m.role_index.keys()) == {"x_node"}]
    assert len(full) == 1, f"完整 A→B match 应有 1 条,得 {len(full)}"
    assert len(x_only) == 2, f"x_node 单 role match 应有 2 条(每 event 一),得 {len(x_only)}"


def test_isolated_consumed_role_match_still_filtered_regression():
    """bbb 形态回归:bo 孤立无边 AND 被 burst 消费 → 单 {bo} match 仍被过滤。

    A2 的本意:流源 role 被回显是残缺,这条规则不能因修复而失效。
    """
    bo = NodeSpec("bo", detector=FakeDetector([Ev("bo0", 1, 1), Ev("bo1", 4, 4)]))
    burst = NodeSpec("burst", detector=FakeDetector([Ev("burst0", 5, 5)]),
                     consumes_stream="bo")
    # bo 不在 edges 端点,但被 burst.consumes_stream 引用
    # burst 在 edges 端点中
    tb = NodeSpec("tb", detector=FakeDetector([Ev("tb0", 6, 6)]),
                  consumes_stream="bo")
    edges = [TemporalEdge("burst", "tb", min_gap=0, max_gap=100)]
    res = analyze(_spec([bo, burst, tb], edges, root="burst"), df=object())

    bo_only_matches = [m for m in res.matches
                       if set(m.role_index.keys()) == {"bo"}]
    assert bo_only_matches == [], "{bo} 残缺单 role match 应被过滤(bo 被 consumes_stream 消费)"
