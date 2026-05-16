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


def test_construct_ok_and_role_index_tuple():
    a1, a2 = _a(1), _a(3)
    m = PatternMatch(
        event_id="chain_1_3",
        start_idx=1,
        end_idx=3,
        children=(a1, a2),
        role_index={"A": (a1,), "B": (a2,)},
        pattern_label="chain",
    )
    assert m.role_index["A"] == (a1,)
    assert m.children == (a1, a2)
    assert m.pattern_label == "chain"


def test_children_must_be_start_idx_ascending():
    a1, a2 = _a(1), _a(3)
    with pytest.raises(ValueError):
        PatternMatch(
            event_id="x", start_idx=1, end_idx=3,
            children=(a2, a1),  # 逆序
            role_index={"A": (a1,), "B": (a2,)},
            pattern_label="chain",
        )


def test_role_index_flatten_must_equal_children():
    a1, a2 = _a(1), _a(3)
    with pytest.raises(ValueError):
        PatternMatch(
            event_id="x", start_idx=1, end_idx=3,
            children=(a1,),                       # 少了 a2
            role_index={"A": (a1,), "B": (a2,)},
            pattern_label="chain",
        )


def test_each_role_tuple_internally_ascending():
    a1, a2 = _a(1), _a(3)
    with pytest.raises(ValueError):
        PatternMatch(
            event_id="x", start_idx=1, end_idx=3,
            children=(a1, a2),
            # flatten 集合刻意满足({id(a2),id(a1)} == {id(a1),id(a2)}),
            # 故触发的是各 role tuple 内升序检查
            role_index={"A": (a2, a1)},           # tuple 内逆序
            pattern_label="chain",
        )
