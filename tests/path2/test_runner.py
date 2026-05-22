from dataclasses import dataclass

import pytest

from path2 import config
from path2.core import Event
from path2.runner import run


@dataclass(frozen=True)
class _E(Event):
    pass


def _e(i, eid=None):
    return _E(event_id=eid or f"e{i}", start_idx=i, end_idx=i)


def test_forwards_multiple_source_args():
    class TwoArg:
        def detect(self, stream, df):
            for x in stream:
                yield _e(x + df)

    out = list(run(TwoArg(), [1, 2], 10))
    assert [e.end_idx for e in out] == [11, 12]


def test_streaming_is_lazy():
    class Boom:
        def detect(self, _):
            yield _e(1)
            yield _e(2)
            raise RuntimeError("boom")

    g = run(Boom(), None)
    assert next(g).end_idx == 1
    assert next(g).end_idx == 2
    with pytest.raises(RuntimeError):
        next(g)


def test_ascending_equal_ok_decreasing_raises():
    class Eq:
        def detect(self, _):
            yield _e(5, "a")
            yield _e(5, "b")  # 等值允许

    assert len(list(run(Eq(), None))) == 2

    class Desc:
        def detect(self, _):
            yield _e(5, "a")
            yield _e(3, "b")  # 递减违规

    with pytest.raises(ValueError):
        list(run(Desc(), None))


def test_duplicate_event_id_within_run_raises():
    class Dup:
        def detect(self, _):
            yield _e(1, "same")
            yield _e(2, "same")

    with pytest.raises(ValueError):
        list(run(Dup(), None))


def test_non_event_yield_raises():
    class NotEvent:
        def detect(self, _):
            yield "not-an-event"

    with pytest.raises(TypeError):
        list(run(NotEvent(), None))


def test_seen_ids_scope_independent_across_runs():
    class Same:
        def detect(self, _):
            yield _e(1, "x")

    d = Same()
    assert len(list(run(d, None))) == 1
    assert len(list(run(d, None))) == 1  # 第二次 run 不因 "x" 已见而报错


def test_checks_off_passthrough_allows_decreasing():
    config.set_runtime_checks(False)

    class Desc:
        def detect(self, _):
            yield _e(5, "a")
            yield _e(3, "a")  # 递减 + 重复 id,关检查时应放行

    assert len(list(run(Desc(), None))) == 2
