"""整改三 fuzz:reachable-leaves 跨 prefix 去重 + 不丢点(TDD red,B3.2 实施后 pass)。

构造场景:两个不同 prefix event(src_a, src_b)处于同一 src 节点的流,都能绑同一个
leaf event(leaf_0)。当前 solve() 枚举两个 Solution:
  {src: a_0, leaf: leaf_0} 和 {src: a_1, leaf: leaf_0}
→ leaf_0 被 emit 两次(prefix 各一次)。

启用 reachable-leaves 后,同一 leaf event 只被 emit 一次(去重),但其中一条
(src_*, leaf) Solution 必须出现(不丢点)。

复用 tests/path2/dag/_oracle.py 的 Ev + FakeDet 模式。
"""
from __future__ import annotations
import pytest
from path2.dag._solve import compile_plan, solve
from path2.dag.spec import PatternSpec
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge
from tests.path2.dag._oracle import Ev


class _FakeDet:
    """合成 detector,只为 PatternSpec 校验通过。"""
    def __init__(self, evs):
        self._evs = evs
    def detect(self, *source):
        return iter(self._evs)


def _spec_two_src_shared_leaf():
    """src 节点有两个 event(a_0, a_1),两者都能绑到同一个 leaf_0。"""
    src_a = Ev("a_0", 0, 0, pos=0)   # 第一个 prefix event
    src_b = Ev("a_1", 2, 2, pos=1)   # 第二个 prefix event
    leaf_x = Ev("leaf_0", 5, 5, pos=0)

    nodes = (
        NodeSpec(node_id="src", detector=_FakeDet([src_a, src_b])),
        NodeSpec(node_id="leaf", detector=_FakeDet([leaf_x])),
    )
    edges = (
        TemporalEdge("src", "leaf", min_gap=1, max_gap=10),
    )
    spec = PatternSpec(pattern_id="shared_leaf_fuzz", display_name="shared_leaf_fuzz",
                       nodes=nodes, edges=edges, root="src")
    return spec, src_a, src_b, leaf_x


def test_reachable_leaves_dedup_shared_leaf():
    """共享 leaf 只被 emit 一次(reachable-leaves always-on)。

    当前行为(B3.2 前):leaf_0 被 emit 两次(src=a_0 和 src=a_1 各一次)→ 测试 FAIL。
    B3.2 实施 emitted_leaves 后:leaf_0 至多 emit 一次,测试 PASS。
    """
    spec, src_a, src_b, leaf_x = _spec_two_src_shared_leaf()
    plan = compile_plan(spec)
    streams = {"src": [src_a, src_b], "leaf": [leaf_x]}
    solutions = solve(plan, streams)

    # 期望:leaf_0 至多 emit 一次
    leaf_ids = [sol.assign["leaf"].event_id for sol in solutions]
    assert leaf_ids.count("leaf_0") <= 1, \
        f"reachable-leaves dedup failed: leaf_0 emitted {leaf_ids.count('leaf_0')} times"
    # 但至少 emit 一次(不丢点)
    assert "leaf_0" in leaf_ids, "leaf_0 should be emitted at least once (no dropping)"
