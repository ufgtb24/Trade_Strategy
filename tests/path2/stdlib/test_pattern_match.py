from dataclasses import dataclass

import pytest

from path2.core import Event
from path2.stdlib.pattern_match import PatternMatch


@dataclass(frozen=True)
class _A(Event):
    pass


def _a(s, e=None):
    e = s if e is None else e
    return _A(event_id=f"a_{s}_{e}", start_idx=s, end_idx=e)


def test_construct_ok_and_role_index_single():
    a1, a2 = _a(1), _a(3)
    m = PatternMatch(
        event_id="chain_1_3",
        start_idx=1,
        end_idx=3,
        children=(a1, a2),
        role_index={"A": a1, "B": a2},
        pattern_label="chain",
    )
    assert m.role_index["A"] == a1
    assert m.role_index["B"] == a2
    assert m.children == (a1, a2)
    assert m.pattern_label == "chain"


def test_children_must_be_start_idx_ascending():
    a1, a2 = _a(1), _a(3)
    with pytest.raises(ValueError):
        PatternMatch(
            event_id="x", start_idx=1, end_idx=3,
            children=(a2, a1),  # 逆序
            role_index={"A": a1, "B": a2},
            pattern_label="chain",
        )


def test_role_index_values_must_equal_children():
    a1, a2 = _a(1), _a(3)
    with pytest.raises(ValueError):
        PatternMatch(
            event_id="x", start_idx=1, end_idx=3,
            children=(a1,),                       # 少了 a2
            role_index={"A": a1, "B": a2},
            pattern_label="chain",
        )


def test_role_index_none_with_nonempty_children_raises():
    """role_index=None 但 children 非空 → 两视图漂移,应抛 ValueError。"""
    a1 = _a(1)
    with pytest.raises(ValueError):
        PatternMatch(
            event_id="x", start_idx=1, end_idx=1,
            children=(a1,), role_index=None,
            pattern_label="chain",
        )

