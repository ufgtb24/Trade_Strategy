from path2.dag.gate_failure import GateFailure, MeasuredKindAware


def test_measured_kind_aware_dataclass():
    m = MeasuredKindAware(kind='gap', value=13, label='gap')
    assert m.kind == 'gap' and m.value == 13


def test_gate_failure_dataclass():
    m = MeasuredKindAware(kind='gap', value=13, label='gap')
    gf = GateFailure(
        failure_event_window=(90, 105),
        start_idx=90,
        gate_idx=105,
        anchor_bar=105,
        gate_name='chain_break',
        measured=m,
        threshold=10,
        op='<=', threshold_param='gap_max',
        evaluation_lookback=None,
        symbol='DGNX',
    )
    assert gf.gate_name == 'chain_break'
    assert gf.failure_event_window == (90, 105)


def test_gate_failure_is_frozen():
    import dataclasses
    m = MeasuredKindAware(kind='gap', value=13, label='gap')
    gf = GateFailure(failure_event_window=(0, 0), start_idx=0, gate_idx=0,
                     anchor_bar=0, gate_name='x', measured=m,
                     threshold=0, op=None, threshold_param=None,
                     evaluation_lookback=None, symbol='x')
    import pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        gf.symbol = "changed"


def test_detector_protocol_has_optional_on_gate():
    from path2.core import Detector
    # Protocol 有 on_gate optional 属性 · duck type
    class MyDetector:
        on_gate = None
    d: Detector = MyDetector()
    assert d.on_gate is None
