"""gate_collector per-node wrapper 注入 node_id + 挂雷式共享防护(spec 2026-08-14 §2.2)。

- wrapper 注入:非共享 detector 的 gf 进 collector 后 node_id == 所属 node
- 非法共享:同一产 gate detector 挂 2 node,首条 gf 到达即 raise(文案含修法关键词)
- 合法共享:不 emit gf 的 detector(如 TrendSegmentDetector 场景)挂 2 node,雷永不动零差异
"""
from dataclasses import dataclass
from typing import Callable, Optional

import pytest

from path2.dag.gate_failure import GateFailure, MeasuredKindAware
from path2_web.gate_collector import attach_and_collect


@dataclass
class _FakeNode:
    node_id: str
    detector: object = None


class _FakeSpec:
    def __init__(self, nodes):
        self.nodes = nodes


def _mk_gf() -> GateFailure:
    # 最小合法 gf(measured 用生产形态 MeasuredKindAware,参考既有 gate_failure 测试)
    return GateFailure(
        failure_event_window=(1, 2), start_idx=1, gate_idx=2, anchor_bar=1,
        gate_name='g', measured=MeasuredKindAware(kind='count', value=1.0, label='x'),
        threshold=1, op='>=',
        threshold_param=None, evaluation_lookback=None, symbol='TEST')


class _GateDetector:
    """产 gate failure 的假 detector(on_gate 由 attach 挂载)。"""
    def __init__(self):
        self.on_gate: Optional[Callable] = None

    def emit(self):
        self.on_gate(_mk_gf())


class _SilentDetector:
    """不产 gate failure 的假 detector(合法共享场景,如 Trend)。"""
    def __init__(self):
        self.on_gate: Optional[Callable] = None


def test_wrapper_injects_node_id():
    det_a, det_b = _GateDetector(), _GateDetector()
    spec = _FakeSpec([_FakeNode('bo', det_a), _FakeNode('tb', det_b)])
    collector = attach_and_collect(spec)
    det_a.emit(); det_b.emit(); det_b.emit()
    assert [g.node_id for g in collector.snapshot()] == ['bo', 'tb', 'tb']


def test_shared_gate_detector_raises_on_first_gf():
    det = _GateDetector()
    spec = _FakeSpec([_FakeNode('down', det), _FakeNode('side', det)])
    attach_and_collect(spec)
    with pytest.raises(RuntimeError, match='一 node 一实例'):
        det.emit()


def test_shared_silent_detector_zero_behavior_diff():
    det = _SilentDetector()
    spec = _FakeSpec([_FakeNode('down', det), _FakeNode('side', det)])
    collector = attach_and_collect(spec)
    assert collector.snapshot() == ()   # 不 emit gf → 雷永不动
