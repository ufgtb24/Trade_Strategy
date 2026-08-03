# tests/path2/dag/test_reify_kind_aware.py
"""硬伤 E · Sprint 2 Task 13:_make_measured 按 edge kind 生成 MeasuredKindAware。"""
from path2.dag._reify import _make_measured
from path2.dag.edges import (TemporalEdge, ContainmentEdge, OverlapEdge, EqualsEdge,
                             StartContainmentEdge, NegationEdge)
from path2.dag.gate_failure import MeasuredKindAware


def make_bo_event(idx):
    from path2.atoms.breakout import BOEvent
    return BOEvent(event_id=f"bo_{idx}", start_idx=idx, end_idx=idx, confirm_idx=idx,
                   drought=None, pk_count=1, broken_peak_ids=(), vol_ratio=None,
                   peak_vol_max=0.0, referenced_points=())


def make_wide_event(start, end, idx=0):
    from path2.atoms.breakout import BOEvent
    # 复用 BOEvent 仅为拿现成 Event 子类;start != end 打破"点事件"假设,够用于纯几何 measured 计算
    return BOEvent(event_id=f"w_{idx}", start_idx=start, end_idx=end, confirm_idx=start,
                   drought=None, pk_count=1, broken_peak_ids=(), vol_ratio=None,
                   peak_vol_max=0.0, referenced_points=())


def test_temporal_edge_kind_gap():
    u, v = make_bo_event(10), make_bo_event(15)
    edge = TemporalEdge(src="a", dst="b", min_gap=0, max_gap=10)
    m = _make_measured(edge, u, v)
    assert isinstance(m, MeasuredKindAware)
    assert m.kind == 'gap'
    assert m.value == 5
    assert m.label == 'gap'


def test_start_containment_edge_kind_anchor_delta():
    u, v = make_bo_event(10), make_bo_event(12)
    edge = StartContainmentEdge(src="a", dst="b")
    m = _make_measured(edge, u, v)
    assert m.kind in ('anchor_delta', 'start_offset')


def test_containment_edge_kind_window_offset():
    u = make_wide_event(0, 20)
    v = make_wide_event(3, 8)
    edge = ContainmentEdge(src="a", dst="b")
    m = _make_measured(edge, u, v)
    assert isinstance(m, MeasuredKindAware)
    assert m.kind == 'window_offset'
    assert m.value == 3 - 0
    assert m.label == '起点偏移'


def test_overlap_edge_kind_window_offset():
    u = make_wide_event(0, 10)
    v = make_wide_event(5, 15)
    edge = OverlapEdge(src="a", dst="b")
    m = _make_measured(edge, u, v)
    assert m.kind == 'window_offset'
    assert m.value == 5


def test_equals_edge_kind_window_offset():
    u = make_wide_event(0, 10)
    v = make_wide_event(0, 10)
    edge = EqualsEdge(src="a", dst="b")
    m = _make_measured(edge, u, v)
    assert m.kind == 'window_offset'
    assert m.value == 0


def test_negation_edge_kind_negation_bars():
    u, v = make_bo_event(10), make_bo_event(15)
    edge = NegationEdge(src="a", dst="b", min_gap=0, max_gap=10)
    m = _make_measured(edge, u, v)
    assert m.kind == 'negation_bars'
    assert m.value == 5
    assert m.label == '禁区bars'


def test_unknown_edge_kind_fallback():
    class _FakeEdge:
        """非 DependencyEdge 子类的哨兵对象,验证 _make_measured 的兜底分支。"""
        pass

    u, v = make_bo_event(10), make_bo_event(15)
    m = _make_measured(_FakeEdge(), u, v)
    assert m.kind == 'unknown'
    assert m.value is None
    assert m.label == '?'
