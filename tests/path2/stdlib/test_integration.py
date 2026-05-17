from dataclasses import dataclass

from path2 import Chain, Dag, Kof, Neg, PatternMatch, run
from path2.core import Event, TemporalEdge


@dataclass(frozen=True)
class Spike(Event):
    pass


@dataclass(frozen=True)
class Drop(Event):
    pass


def _mk(cls, s):
    return cls(event_id=f"{cls.__name__}_{s}", start_idx=s, end_idx=s)


def test_public_exports_present():
    assert all(x is not None for x in (Chain, Dag, Kof, Neg, PatternMatch))


def test_classname_default_label_end_to_end():
    spikes = [_mk(Spike, 0), _mk(Spike, 10)]
    drops = [_mk(Drop, 2), _mk(Drop, 12)]
    d = Chain(
        spikes, drops,
        edges=[TemporalEdge("Spike", "Drop", min_gap=1)],
        label="sd",
    )
    ms = list(run(d))
    assert [(m.start_idx, m.end_idx) for m in ms] == [(0, 2), (10, 12)]


def test_key_escape_hatch_single_merged_stream():
    merged = [_mk(Spike, 0), _mk(Drop, 2), _mk(Spike, 10), _mk(Drop, 12)]
    d = Chain(
        merged,
        edges=[TemporalEdge("Spike", "Drop", min_gap=1)],
        key=lambda e: type(e).__name__,
        label="sd",
    )
    ms = list(run(d))
    assert [(m.start_idx, m.end_idx) for m in ms] == [(0, 2), (10, 12)]


def test_nested_patternmatch_uses_pattern_label():
    # 一层 Chain 的产出再喂给上层 Chain(类名默认失效,靠 pattern_label)
    spikes = [_mk(Spike, 0)]
    drops = [_mk(Drop, 2)]
    inner = list(run(Chain(
        spikes, drops,
        edges=[TemporalEdge("Spike", "Drop", min_gap=1)],
        label="L1",
    )))
    tail = [_mk(Drop, 9)]
    outer = Chain(
        inner, tail,
        edges=[TemporalEdge("L1", "Drop", min_gap=1)],
        label="L2",
    )
    ms = list(run(outer))
    assert len(ms) == 1 and ms[0].pattern_label == "L2"
    assert ms[0].role_index["L1"][0].pattern_label == "L1"


def test_run_invariants_across_all_four():
    edges = [TemporalEdge("A", "B", min_gap=1)]
    for D in (
        Chain(edges=edges, A=[_mk(Spike, 0)], B=[_mk(Drop, 2)], label="p"),
        Dag(edges=edges, A=[_mk(Spike, 0)], B=[_mk(Drop, 2)], label="p"),
    ):
        ms = list(run(D))
        ends = [m.end_idx for m in ms]
        ids = [m.event_id for m in ms]
        assert ends == sorted(ends)
        assert len(ids) == len(set(ids))
