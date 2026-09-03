"""端到端:any 作 where clause 参与求解过滤;reify/diagnose 落 witness 树。"""
from dataclasses import dataclass

import pandas as pd

from path2.core import Event
from path2.dag import where as W
from path2.dag.engine import analyze
from path2.dag.diagnose import diagnose
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec


@dataclass(frozen=True)
class _SoloEvent(Event):
    pk: int = 0
    vol: float = 0.0


class _FakeDet:
    """合成 detector:忽略输入源,直接吐 canned 事件(同 test_tripwire 旧套路)。"""

    def __init__(self, evs):
        self._evs = evs
        self.event_cls = _SoloEvent

    def detect(self, *source):
        return iter(self._evs)


def _spec(evs):
    nodes = (NodeSpec("solo", _FakeDet(evs),
                      where=(("pk_or_vol", W.any(W.attr("pk", ">=", 4),
                                                    W.attr("vol", ">=", 8.0))),)),)
    return PatternSpec(pattern_id="combo_e2e", nodes=nodes, edges=())


def test_or_clause_filters_candidates():
    hit = _SoloEvent(start_idx=0, end_idx=1, confirm_idx=0, pk=5, vol=0.0)
    miss = _SoloEvent(start_idx=2, end_idx=3, confirm_idx=2, pk=1, vol=1.0)
    res = analyze(_spec([hit, miss]), pd.DataFrame())
    # node_index 里是物化标注后的事件:instance_id = span_id("solo", span)#idx
    assert [m.node_index["solo"].instance_id for m in res.matches] == ["solo_0_1#0"]


def test_reify_trace_carries_witness_tree():
    hit = _SoloEvent(start_idx=0, end_idx=1, confirm_idx=0, pk=5, vol=0.0)
    res = analyze(_spec([hit]), pd.DataFrame())
    w = res.matches[0].predicate_trace.where_results["solo"]["pk_or_vol"]
    assert w.satisfied is True and w.label == "or"
    assert [c.measured for c in w.children] == [5, 0.0]     # 全量求值:第二支也有实测值


def test_diagnose_attr_rows_carry_witness_tree():
    miss = _SoloEvent(start_idx=0, end_idx=1, confirm_idx=0, pk=1, vol=1.0)
    d = diagnose(_spec([miss]), pd.DataFrame())
    w = d.nodes["solo"].attr[0].clauses["pk_or_vol"]
    assert w.satisfied is False
    assert [c.satisfied for c in w.children] == [False, False]
    assert [c.measured for c in w.children] == [1, 1.0]
