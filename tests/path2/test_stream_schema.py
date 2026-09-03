from dataclasses import dataclass
import pytest
from path2.core import DEFAULT_STREAM, Event, stream_schema


@dataclass(frozen=True)
class _E(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


def test_single_flow_normalizes_to_default_stream():
    class D:
        event_cls = _E
        def detect(self, source): ...
    assert stream_schema(D()) == {DEFAULT_STREAM: _E}


def test_multi_flow_returns_produces():
    class D:
        produces = {"a": _E, "b": _E}
        def detect(self, source): ...
    assert stream_schema(D()) == {"a": _E, "b": _E}


def test_missing_both_raises():
    class D:
        def detect(self, source): ...
    with pytest.raises(ValueError, match="event_cls"):
        stream_schema(D())


def test_ref_slots_default_empty():
    assert _E().ref_slots() == {}
