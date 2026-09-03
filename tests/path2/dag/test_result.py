"""匹配产物类型:EdgeWitness / PredicateTrace / PatternMatch(展平不变式) / AnalysisResult。"""
import pytest
from path2 import config
from path2.core import Event
from path2.dag.result import EdgeWitness, PredicateTrace, PatternMatch, AnalysisResult


class Ev(Event):
    pass

def ev(s, e):
    return Ev(start_idx=s, end_idx=e, confirm_idx=s)


def test_edge_witness_fields():
    a, b = ev(0, 5), ev(6, 6)
    w = EdgeWitness(satisfied=True, src_instance=a, dst_instance=b, measured=1.0)
    assert w.satisfied is True and w.src_instance is a and w.measured == 1.0


def test_pattern_match_flatten_invariant_ok():
    """node_index 值集合 == children 集合。"""
    a = ev(0, 0)
    b = ev(2, 4)
    m = PatternMatch(
        match_id="m1", start_idx=0, end_idx=4, confirm_idx=0, pattern_id="p",
        node_index={"down": a, "bo": b},
        children=(a, b),
        predicate_trace=PredicateTrace(where_results={}, edge_results={}),
    )
    assert m.node_index["bo"] is b


def test_pattern_match_flatten_invariant_violation_raises():
    a = ev(0, 0); b = ev(2, 2)
    config.set_runtime_checks(True)
    with pytest.raises(AssertionError):
        PatternMatch(
            match_id="m1", start_idx=0, end_idx=2, confirm_idx=0, pattern_id="p",
            node_index={"down": a, "bo": b},
            children=(a,),                               # 少了 b → 违反展平不变式
            predicate_trace=PredicateTrace(where_results={}, edge_results={}),
        )


def test_analysis_result_holds_events_matches():
    r = AnalysisResult(events=(ev(0, 0),), matches=(), spec=None)
    assert len(r.events) == 1 and r.matches == ()


def test_analysis_result_allows_same_identity_multi_instances():
    """实例流契约:同 instance_id 多实例(属性不同)合法;全属性全等对象仍非法。"""
    from path2.atoms.breakout import BOEvent
    e1 = BOEvent(start_idx=1, end_idx=1, confirm_idx=1, drought=5)
    e2 = BOEvent(start_idx=1, end_idx=1, confirm_idx=1, drought=8)   # 同身份(1,1),属性不同
    a = AnalysisResult(events=(e1, e2), matches=(), spec=None)
    assert a.events == (e1, e2)   # 同身份多实例不再抛断言


def test_analysis_result_rejects_identical_duplicate_objects():
    """同 instance_id 且全属性全等的对象仍非法(兜底防 detector 重复 evaluate)。"""
    from path2.atoms.breakout import BOEvent
    e1 = BOEvent(start_idx=1, end_idx=1, confirm_idx=1, drought=5)
    e2 = BOEvent(start_idx=1, end_idx=1, confirm_idx=1, drought=5)   # 全属性全等
    with pytest.raises(AssertionError):
        AnalysisResult(events=(e1, e2), matches=(), spec=None)


def test_match_id_uses_instance_ids():
    """match_id 的 node_bits 段用 instance_id(标注后),不再用 event_id。

    TDD(Task 3):analyze 最小 spec 的 match 须带 match_id、无 event_id,
    且 node_index 各实例的 instance_id 恒带 #idx(物化标注契约)。"""
    from path2.dag.edges import TemporalEdge
    from path2.dag.engine import analyze
    from path2.dag.nodes import NodeSpec
    from path2.dag.spec import PatternSpec
    from tests.path2.dag._oracle import Ev as OEv

    class _Fake:
        event_cls = OEv
        def __init__(self, evs): self._evs = evs
        def detect(self, *source): return iter(self._evs)

    spec = PatternSpec(pattern_id="p", nodes=(
        NodeSpec("A", _Fake([OEv("a", 0, 0)])),
        NodeSpec("B", _Fake([OEv("b", 5, 5)])),
    ), edges=(TemporalEdge("A", "B", min_gap=0, max_gap=100),))
    res = analyze(spec, df=object())
    assert res.matches, "平凡链应产出 match"
    for m in res.matches:
        assert hasattr(m, "match_id") and m.match_id
        assert not hasattr(m, "event_id")          # Event 无此字段,PatternMatch 也不该有
        bits = {e.instance_id for e in m.node_index.values()}
        for b in bits:
            assert b is not None and "#" in b      # instance_id 恒带 #idx
