"""整改二 fuzz:c1_off 加叶子健全性(TDD red,B2.2 实施 c1_off 第 4 源后 pass)。

构造场景:出边为空叶子 + 同 end_idx 桶内多个 event_id 不同的 dst 候选(start 不同)。
关 C1 后,所有 event_id 都进入候选(整改二);跑 solve 应 emit 全部合法 leaf。
若未关 C1,C1 塌缩按父 end_idx 桶留 (start, end, pos) argmin → 漏匹配。

复用 tests/path2/dag/_oracle.py 的 Ev 事件类 + 引入 FakeDetector(同 test_engine_analyze)。
"""
from __future__ import annotations
import random
import pytest
from path2.dag._solve import compile_plan, solve
from path2.dag.spec import PatternSpec
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge

from tests.path2.dag._oracle import Ev


class _FakeDet:
    """合成 detector,只为 PatternSpec 校验通过(compile_plan/solve 不调 detect)。"""
    event_cls = Ev
    def __init__(self, evs):
        self._evs = evs
    def detect(self, *source):
        return iter(self._evs)


def _spec_with_leaf_bucket(n_dst=4):
    """构造 src(单 event) → dst(叶子,n 个 event 同 end_idx 不同 start_idx)的 spec。"""
    src_event = Ev("s_0", 0, 0, pos=0)
    # 同 end_idx=10 的 n 个 dst,start_idx 各异;event_id/pos 不同
    dst_events = [Ev(f"d_{i}", 5 + i, 10, pos=i) for i in range(n_dst)]

    nodes = (
        NodeSpec(node_id="src", detector=_FakeDet([src_event])),
        NodeSpec(node_id="dst", detector=_FakeDet(dst_events)),
    )
    edges = (TemporalEdge("src", "dst", min_gap=1, max_gap=20),)
    spec = PatternSpec(pattern_id="leaf_fuzz",
                       nodes=nodes, edges=edges)
    return spec, src_event, dst_events


@pytest.mark.parametrize("seed", range(10))
def test_c1_off_leaf_releases_same_end_bucket(seed):
    """同 end 桶内每个 dst event 都该作为合法 leaf 命中(B2 关叶子 C1)。"""
    spec, src_event, dst_events = _spec_with_leaf_bucket(n_dst=4)
    plan = compile_plan(spec)

    # 关键:dst 是叶子(无 outgoing),compile_plan 应把 dst 并入 c1_off
    assert "dst" in plan.leaves, "Plan.leaves should contain 'dst' (no outgoing edges)"
    assert "dst" in plan.c1_off, "c1_off should contain 'dst' (leaves source, B2.2)"

    streams = {"src": [src_event], "dst": dst_events}
    solutions = solve(plan, streams)

    # 期望:n_dst 个 Solution,每个 dst event 一个
    emitted_dst_ids = {sol.assign["dst"].event_id for sol in solutions}
    expected_dst_ids = {d.event_id for d in dst_events}
    assert emitted_dst_ids == expected_dst_ids, \
        f"seed={seed}: Expected all {len(dst_events)} dst leaves, got {emitted_dst_ids}"


# 不在 seed 循环里的额外结构性验证:plan.leaves 字段存在
def test_plan_has_leaves_field():
    """整改二 B2.2 前置:Plan dataclass 必须有 leaves 字段(frozenset)。"""
    spec, _, _ = _spec_with_leaf_bucket(n_dst=2)
    plan = compile_plan(spec)
    assert hasattr(plan, "leaves"), "Plan must have 'leaves' field after B2.2"
    assert isinstance(plan.leaves, frozenset), f"Plan.leaves must be frozenset, got {type(plan.leaves)}"
    assert "dst" in plan.leaves and "src" not in plan.leaves
