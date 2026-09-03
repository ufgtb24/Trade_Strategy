"""实例流 Task 3:match_id 的 node_bits 段用 instance_id(标注后恒含 #idx),
多实例流内 match_id 天然唯一。analyze 出口仍保留惰性 #idx 消歧(防御性):
若未来某组合产出同 id 的 match,按 (start, end, node_bits) 排序附 #idx。

场景:src → dst 链。
  - 同 span 两实例(#0/#1)→ node_bits 含不同 instance_id → match_id 天然不同
  - 不同 span 两事件 → match 聚合 span 不同 → match_id 不同,无 #idx
"""
from __future__ import annotations

from path2.dag.engine import analyze
from path2.dag.spec import PatternSpec
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge

from tests.path2.dag._oracle import Ev


class _FakeDet:
    """合成 detector:忽略输入源,直接吐已构造好的 canned 事件序列。"""
    event_cls = Ev

    def __init__(self, evs):
        self._evs = evs

    def detect(self, *source):
        return iter(self._evs)


def _analyze_spec(src_evs):
    spec = PatternSpec(pattern_id="dup_match", nodes=(
        NodeSpec(node_id="src", detector=_FakeDet(src_evs)),
        NodeSpec(node_id="dst", detector=_FakeDet([Ev("d0", 20, 20)])),
    ), edges=(TemporalEdge("src", "dst", min_gap=0, max_gap=100),))
    return analyze(spec, None)


def test_analyze_match_id_distinct_for_multi_instances():
    """同 span 两实例(instance_idx 0/1)→ node_bits 段含不同 instance_id → match_id 天然不同。"""
    res = _analyze_spec([Ev("s0", 5, 10, pos=0), Ev("s0", 5, 10, pos=1)])
    mids = [m.match_id for m in res.matches]
    assert len(mids) == len(set(mids)), f"match_id 仍重复: {mids}"
    assert len(mids) == 2, f"应有 2 个 match,got {len(mids)}"
    # 物化标注后:src 同 span 多实例 → src_5_10#0/#1;dst → dst_20#0
    assert sorted(mids) == [
        "dup_match@5-20#dst:dst_20#0|src:src_5_10#0",
        "dup_match@5-20#dst:dst_20#0|src:src_5_10#1",
    ], f"got {mids}"


def test_analyze_match_id_unchanged_without_collision():
    """不同 start 的实例 → match 聚合 span 不同 → id 不同,无 #idx。"""
    res = _analyze_spec([Ev("s0", 0, 10, pos=0), Ev("s0", 5, 10, pos=1)])
    mids = [m.match_id for m in res.matches]
    assert len(mids) == 2, f"应有 2 个 match,got {len(mids)}"
    assert sorted(mids) == [
        "dup_match@0-20#dst:dst_20#0|src:src_0_10#0",
        "dup_match@5-20#dst:dst_20#0|src:src_5_10#0",
    ], f"got {mids}"
