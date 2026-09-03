# tests/path2/test_runner_bundle.py
from dataclasses import dataclass
import pytest
from path2 import config
from path2.core import DEFAULT_STREAM, Event
from path2.runner import run, run_bundle


@dataclass(frozen=True)
class _E(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


class _Single:
    event_cls = _E
    def __init__(self): self.calls = 0
    def detect(self, df):
        self.calls += 1
        yield _E(start_idx=0, end_idx=0, confirm_idx=0)


class _Dual:
    produces = {"a": _E, "b": _E}
    def __init__(self): self.calls = 0
    def detect(self, df):
        self.calls += 1
        yield ("a", _E(start_idx=0, end_idx=0, confirm_idx=0))
        yield ("b", _E(start_idx=1, end_idx=1, confirm_idx=1))


def test_run_bundle_single_flow_normalizes():
    d = _Single()
    out = run_bundle(d, object())
    assert set(out) == {DEFAULT_STREAM}
    assert len(out[DEFAULT_STREAM]) == 1


def test_run_bundle_multi_flow_separates():
    d = _Dual()
    out = run_bundle(d, object())
    assert set(out) == {"a", "b"}
    assert len(out["a"]) == 1 and len(out["b"]) == 1


def test_run_bundle_unknown_stream_raises():
    class Bad:
        produces = {"a": _E}
        def detect(self, df):
            yield ("zz", _E(start_idx=0, end_idx=0, confirm_idx=0))
    with pytest.raises(ValueError, match="zz"):
        run_bundle(Bad(), object())


def test_run_multi_flow_rejected():
    with pytest.raises(ValueError, match="多流"):
        list(run(_Dual(), object()))
