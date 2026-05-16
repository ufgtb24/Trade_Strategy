from dataclasses import dataclass

from path2.core import Event, TemporalEdge
from path2.stdlib._graph import build_graph
from path2.stdlib._advance import advance_dag


@dataclass(frozen=True)
class _E(Event):
    pass


def ev(s, e=None):
    e = s if e is None else e
    return _E(event_id=f"e_{s}_{e}", start_idx=s, end_idx=e)


def test_linear_chain_earliest_feasible():
    # A->B->C, gap=later.start - earlier.end, min_gap=1
    edges = [TemporalEdge("A", "B", min_gap=1), TemporalEdge("B", "C", min_gap=1)]
    g = build_graph(edges)
    streams = {
        "A": [ev(0)],
        "B": [ev(2)],          # 2-0=2 >=1 ok
        "C": [ev(5)],          # 5-2=3 >=1 ok
    }
    matches = list(advance_dag(g, streams, label="chain"))
    assert len(matches) == 1
    m = matches[0]
    assert m.start_idx == 0 and m.end_idx == 5
    assert [c.start_idx for c in m.children] == [0, 2, 5]
    assert m.role_index["A"][0].start_idx == 0


def test_max_gap_violation_no_match():
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=2)]
    g = build_graph(edges)
    streams = {"A": [ev(0)], "B": [ev(10)]}  # 10-0=10 > 2
    assert list(advance_dag(g, streams, label="x")) == []


def test_non_overlapping_greedy_two_matches():
    edges = [TemporalEdge("A", "B", min_gap=1)]
    g = build_graph(edges)
    streams = {
        "A": [ev(0), ev(10)],
        "B": [ev(2), ev(12)],
    }
    ms = list(advance_dag(g, streams, label="p"))
    assert [(m.start_idx, m.end_idx) for m in ms] == [(0, 2), (10, 12)]


def test_multi_indegree_intersection():
    # A->C, B->C ; C 须同时满足两前驱 gap
    edges = [
        TemporalEdge("A", "C", min_gap=1, max_gap=10),
        TemporalEdge("B", "C", min_gap=1, max_gap=3),
    ]
    g = build_graph(edges)
    streams = {
        "A": [ev(0)],          # C.start - 0 in [1,10]
        "B": [ev(5)],          # C.start - 5 in [1,3] -> C.start in [6,8]
        "C": [ev(7)],          # 7 in [1,10] and 7-5=2 in [1,3] ok
    }
    ms = list(advance_dag(g, streams, label="dag"))
    assert len(ms) == 1 and ms[0].end_idx == 7


def test_yield_order_end_idx_ascending():
    edges = [TemporalEdge("A", "B", min_gap=1)]
    g = build_graph(edges)
    streams = {"A": [ev(0), ev(3)], "B": [ev(1), ev(4)]}
    ms = list(advance_dag(g, streams, label="p"))
    ends = [m.end_idx for m in ms]
    assert ends == sorted(ends)
