"""匹配产物类型:EdgeWitness / PredicateTrace / PatternMatch(展平不变式) / AnalysisResult。"""
import pytest
from path2 import config
from path2.core import Event
from path2.dag.result import EdgeWitness, PredicateTrace, PatternMatch, AnalysisResult


class Ev(Event):
    class_id = "test_result_ev"

def ev(s, e):
    return Ev(event_id=f"e_{s}_{e}", start_idx=s, end_idx=e, confirm_idx=s)


def test_edge_witness_fields():
    a, b = ev(0, 5), ev(6, 6)
    w = EdgeWitness(satisfied=True, src_instance=a, dst_instance=b, measured=1.0)
    assert w.satisfied is True and w.src_instance is a and w.measured == 1.0


def test_pattern_match_flatten_invariant_ok():
    """node_index 值集合 == children 集合。"""
    a = ev(0, 0)
    b = ev(2, 4)
    m = PatternMatch(
        event_id="m1", start_idx=0, end_idx=4, confirm_idx=0, pattern_id="p",
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
            event_id="m1", start_idx=0, end_idx=2, confirm_idx=0, pattern_id="p",
            node_index={"down": a, "bo": b},
            children=(a,),                               # 少了 b → 违反展平不变式
            predicate_trace=PredicateTrace(where_results={}, edge_results={}),
        )


def test_analysis_result_holds_events_matches():
    r = AnalysisResult(events=(ev(0, 0),), matches=(), spec=None)
    assert len(r.events) == 1 and r.matches == ()
