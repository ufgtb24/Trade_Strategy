from dataclasses import dataclass
import pytest
from path2.core import Event
from path2.dag.nodes import NodeSpec


@dataclass(frozen=True)
class _E(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


class _Dual:
    produces = {"a": _E, "b": _E}
    def detect(self, source): ...


class _Single:
    event_cls = _E
    def detect(self, source): ...


def test_single_flow_event_cls_unchanged():
    n = NodeSpec("x", _Single())
    assert n.event_cls is _E


def test_multi_flow_selects_stream():
    n = NodeSpec("pk", _Dual(), produces_stream="a")
    assert n.event_cls is _E


def test_multi_flow_unknown_stream_raises():
    with pytest.raises(ValueError, match="无流"):
        NodeSpec("pk", _Dual(), produces_stream="zz")


def test_substructure_produces_stream_must_be_none():
    with pytest.raises(ValueError, match="produces_stream"):
        NodeSpec("seg", event_cls=_E, produced_by="p", produces_stream="a")
