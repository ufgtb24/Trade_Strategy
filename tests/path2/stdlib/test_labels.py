from dataclasses import dataclass

import pytest

from path2.core import Event
from path2.stdlib._labels import resolve_labels


@dataclass(frozen=True)
class A(Event):
    pass


@dataclass(frozen=True)
class B(Event):
    pass


def _mk(cls, s):
    return cls(event_id=f"{cls.__name__}_{s}", start_idx=s, end_idx=s)


def test_named_streams_bind_by_kwarg():
    sa = [_mk(A, 1), _mk(A, 2)]
    sb = [_mk(B, 3)]
    out = resolve_labels(
        positional=(), named={"X": sa, "Y": sb},
        key=None, strict_key=False, endpoint_labels={"X", "Y"},
    )
    assert [e.start_idx for e in out["X"]] == [1, 2]
    assert [e.start_idx for e in out["Y"]] == [3]


def test_positional_default_label_is_classname():
    out = resolve_labels(
        positional=([_mk(A, 1)], [_mk(B, 2)]), named={},
        key=None, strict_key=False, endpoint_labels={"A", "B"},
    )
    assert out["A"][0].start_idx == 1
    assert out["B"][0].start_idx == 2


def test_positional_same_classname_conflict_raises():
    with pytest.raises(ValueError, match="同类名"):
        resolve_labels(
            positional=([_mk(A, 1)], [_mk(A, 2)]), named={},
            key=None, strict_key=False, endpoint_labels={"A"},
        )


def test_key_function_buckets_merged_stream():
    merged = [_mk(A, 1), _mk(B, 2), _mk(A, 3)]
    out = resolve_labels(
        positional=(merged,), named={},
        key=lambda e: type(e).__name__, strict_key=False,
        endpoint_labels={"A", "B"},
    )
    assert [e.start_idx for e in out["A"]] == [1, 3]
    assert [e.start_idx for e in out["B"]] == [2]


def test_key_loose_drops_unknown_label():
    merged = [_mk(A, 1), _mk(B, 2)]
    out = resolve_labels(
        positional=(merged,), named={},
        key=lambda e: type(e).__name__, strict_key=False,
        endpoint_labels={"A"},          # B 不在端点集
    )
    assert "B" not in out and [e.start_idx for e in out["A"]] == [1]


def test_key_strict_unknown_label_raises():
    merged = [_mk(A, 1), _mk(B, 2)]
    with pytest.raises(ValueError, match="未知标签"):
        resolve_labels(
            positional=(merged,), named={},
            key=lambda e: type(e).__name__, strict_key=True,
            endpoint_labels={"A"},
        )


def test_endpoint_label_unresolved_raises():
    with pytest.raises(ValueError, match="无法解析"):
        resolve_labels(
            positional=(), named={"X": [_mk(A, 1)]},
            key=None, strict_key=False, endpoint_labels={"X", "Y"},
        )


def test_patternmatch_default_label_uses_pattern_label():
    from path2.stdlib.pattern_match import PatternMatch

    child = _mk(A, 1)
    pm = PatternMatch(
        event_id="chain_1_1", start_idx=1, end_idx=1,
        children=(child,), role_index={"A": (child,)},
        pattern_label="vol_buildup",
    )
    out = resolve_labels(
        positional=([pm],), named={},
        key=None, strict_key=False, endpoint_labels={"vol_buildup"},
    )
    assert out["vol_buildup"][0] is pm
