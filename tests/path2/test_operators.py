from dataclasses import dataclass, field
from typing import List

import pytest

from path2.core import Event
from path2.operators import After, Any, At, Before, Over


@dataclass(frozen=True)
class _E(Event):
    ratio: float = 0.0
    broken_peaks: List[int] = field(default_factory=list)


def _anchor(s, e):
    return _E(event_id=f"a_{s}_{e}", start_idx=s, end_idx=e)


# ---- Before ----
def test_before_idx_window_left_closed_right_open():
    a = _anchor(10, 10)
    # 窗口 [7,10):7,8,9 命中,10(anchor 自身)不含
    assert Before(a, lambda x: x == 9, window=3) is True
    assert Before(a, lambda x: x == 10, window=3) is False  # 排除 anchor
    assert Before(a, lambda x: x == 7, window=3) is True
    assert Before(a, lambda x: x == 6, window=3) is False


def test_before_window_zero_is_false():
    a = _anchor(10, 10)
    assert Before(a, lambda x: True, window=0) is False


def test_before_idx_clamped_to_zero():
    a = _anchor(2, 2)
    # 窗口本应 [-3,2),clamp 到 [0,2):0,1
    assert Before(a, lambda x: x == 0, window=5) is True
    assert Before(a, lambda x: x == -1, window=5) is False


def test_before_stream_form():
    a = _anchor(10, 10)
    stream = [_E(event_id="s8", start_idx=8, end_idx=8, ratio=2.0),
              _E(event_id="s10", start_idx=10, end_idx=10, ratio=9.0)]
    # s8.end_idx=8 ∈ [10-3,10)=[7,10) 且 ratio>=2 → True
    assert Before(a, lambda ev: ev.ratio >= 2.0, window=3, stream=stream) is True
    # s10.end_idx=10 不 < 10 → 不计
    assert Before(a, lambda ev: ev.ratio >= 9.0, window=3, stream=stream) is False


# ---- At ----
def test_at_is_predicate_on_anchor():
    a = _E(event_id="a", start_idx=1, end_idx=1, ratio=5.0)
    assert At(a, lambda e: e.ratio == 5.0) is True
    assert At(a, lambda e: e.ratio == 1.0) is False


# ---- After ----
def test_after_idx_window_left_open_right_closed():
    a = _anchor(10, 10)
    # 窗口 (10,10+3]=11,12,13
    assert After(a, lambda x: x == 11, window=3) is True
    assert After(a, lambda x: x == 13, window=3) is True
    assert After(a, lambda x: x == 10, window=3) is False  # 排除 anchor
    assert After(a, lambda x: x == 14, window=3) is False


def test_after_window_zero_is_false():
    a = _anchor(10, 10)
    assert After(a, lambda x: True, window=0) is False


def test_after_stream_form():
    a = _anchor(10, 10)
    stream = [_E(event_id="s12", start_idx=12, end_idx=12, ratio=3.0),
              _E(event_id="s10", start_idx=10, end_idx=10, ratio=3.0)]
    # s12.end_idx=12 ∈ (10,15] 且 ratio>=3 → True
    assert After(a, lambda ev: ev.ratio >= 3.0, window=5, stream=stream) is True
    # s10.end_idx=10 不 > 10 → 不计
    assert After(a, lambda ev: ev.ratio >= 99.0, window=5, stream=stream) is False


# ---- Over ----
def test_over_all_six_ops():
    es = [_E(event_id=f"e{i}", start_idx=i, end_idx=i, ratio=float(i))
          for i in (1, 2, 3)]
    assert Over(es, "ratio", reduce=sum, op=">=", thr=6) is True
    assert Over(es, "ratio", reduce=sum, op=">", thr=6) is False
    assert Over(es, "ratio", reduce=sum, op="<=", thr=6) is True
    assert Over(es, "ratio", reduce=sum, op="<", thr=7) is True
    assert Over(es, "ratio", reduce=sum, op="==", thr=6) is True
    assert Over(es, "ratio", reduce=sum, op="!=", thr=5) is True


def test_over_list_attribute_reduce_idiom():
    es = [_E(event_id="e1", start_idx=1, end_idx=1, broken_peaks=[1, 2]),
          _E(event_id="e2", start_idx=2, end_idx=2, broken_peaks=[3, 4, 5])]
    assert Over(es, "broken_peaks",
                reduce=lambda xs: sum(len(x) for x in xs),
                op=">=", thr=5) is True


def test_over_unknown_op_raises():
    es = [_E(event_id="e1", start_idx=1, end_idx=1, ratio=1.0)]
    with pytest.raises(ValueError):
        Over(es, "ratio", reduce=sum, op="≈", thr=1)


# ---- Any ----
def test_any_at_least_one():
    es = [_E(event_id="e1", start_idx=1, end_idx=1, ratio=1.0),
          _E(event_id="e2", start_idx=2, end_idx=2, ratio=5.0)]
    assert Any(es, lambda e: e.ratio >= 5.0) is True
    assert Any(es, lambda e: e.ratio >= 9.0) is False


def test_any_empty_is_false():
    assert Any([], lambda e: True) is False
