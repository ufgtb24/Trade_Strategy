"""A2 出口过滤:被消费的孤立无边 node 产的残缺 match 被 analyze 出口丢弃,
res.events/topology 仍含该 node。

判据(2026-06-28 收紧):node_index ⊆ {孤立 AND 被消费} 才过滤——「被消费」=
被某 node 的 consumes_stream 引用。未被消费的孤立 node 是合法平凡 pattern,
不再误伤(参 test_a2_isolated_consumed.py)。
"""
from dataclasses import dataclass
from typing import Iterator
import pandas as pd

from path2.core import Event
from path2.dag.engine import analyze
from path2.dag.spec import PatternSpec, NodeSpec
from path2.dag.edges import TemporalEdge


@dataclass(frozen=True)
class _EvA(Event):
    pass

@dataclass(frozen=True)
class _EvB(Event):
    pass

@dataclass(frozen=True)
class _EvISO(Event):
    pass


class _DetA:
    """合成 detector A：发指定 start_idx 的 _EvA。带 event_cls 供 to_topology。"""
    event_cls = _EvA
    def __init__(self, idxs):
        self._idxs = idxs
    def detect(self, *source) -> Iterator[_EvA]:
        for i in self._idxs:
            yield _EvA(start_idx=i, end_idx=i, confirm_idx=i)


class _DetB:
    """合成 detector B：发指定 start_idx 的 _EvB。"""
    event_cls = _EvB
    def __init__(self, idxs):
        self._idxs = idxs
    def detect(self, *source) -> Iterator[_EvB]:
        for i in self._idxs:
            yield _EvB(start_idx=i, end_idx=i, confirm_idx=i)


class _DetISO:
    """合成 detector ISO：发指定 start_idx 的 _EvISO（孤立无边 node）。"""
    event_cls = _EvISO
    def __init__(self, idxs):
        self._idxs = idxs
    def detect(self, *source) -> Iterator[_EvISO]:
        for i in self._idxs:
            yield _EvISO(start_idx=i, end_idx=i, confirm_idx=i)


def _spec_with_isolated():
    # A→B 连通对 + ISO 孤立无边、被 B 的 consumes_stream 引用(模拟流源 node)
    return PatternSpec(
        pattern_id="t",
        nodes=(NodeSpec("A", _DetA([1])),
               NodeSpec("B", _DetB([3]), consumes_stream="ISO"),
               NodeSpec("ISO", _DetISO([5, 6, 7]))),
        edges=(TemporalEdge("A", "B", min_gap=1, max_gap=5),),
    )


def test_isolated_node_degenerate_matches_filtered():
    spec = _spec_with_isolated()
    df = pd.DataFrame({"close": range(20)})
    res = analyze(spec, df)
    # 过滤后只剩连通 {A,B} 的完整 match；3 个 ISO 残缺 match 被丢
    for m in res.matches:
        assert set((m.node_index or {}).keys()) != {"ISO"}
    assert any(set((m.node_index or {}).keys()) == {"A", "B"} for m in res.matches)
    # res.events 仍含 ISO 的 event（孤立 node 露面 events, design §8.1 接受）
    # instance_id(物化标注后):ISO 节点 span(i,i) 点事件 → "ISO_{i}#0"
    assert any(e.instance_id.startswith("ISO_5") for e in res.events)
