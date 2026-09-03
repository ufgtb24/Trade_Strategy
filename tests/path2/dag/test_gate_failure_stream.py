from path2.dag.gate_failure import GateFailure
from path2.dag.gate_failure import MeasuredKindAware


def _gf(**kw):
    base = dict(
        failure_event_window=(0, 0), start_idx=0, gate_idx=0, anchor_bar=0,
        gate_name="g", measured=MeasuredKindAware(kind="count", value=1, label="x"),
        threshold=1, op=None, threshold_param=None,
        evaluation_lookback=None, symbol="SYM",
    )
    base.update(kw)
    return GateFailure(**base)


def test_stream_default_none():
    assert _gf().stream is None       # 既有构造点不传 stream → 兼容


def test_stream_explicit():
    assert _gf(stream="pk").stream == "pk"
