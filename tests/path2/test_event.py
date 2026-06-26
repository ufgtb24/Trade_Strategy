import math
from dataclasses import dataclass

import pytest

from path2 import config
from path2.core import Event


@dataclass(frozen=True)
class _Vol(Event):
    class_id = "test_event_vol"
    ratio: float = 0.0
    flag: bool = False


def test_valid_construction():
    e = _Vol(event_id="v_1", start_idx=5, end_idx=5, ratio=2.3)
    assert e.event_id == "v_1"
    assert e.start_idx == 5 and e.end_idx == 5
    assert e.ratio == 2.3


def test_non_frozen_subclass_raises():
    # Python @dataclass 在装饰期就拒绝"非 frozen 子类继承 frozen 父类",
    # 此处验证该行为保证(由 Python 原生强制,而非 Event.__post_init__)。
    with pytest.raises(TypeError, match="non-frozen"):
        @dataclass  # 缺 frozen=True —— 这正是本测试要验证的 Python 原生约束
        class _Bad(Event):
            class_id = "test_event_bad_frozen"  # 先过 class_id guard,使 frozen 守卫成为抛错点
            x: int = 0


def test_start_gt_end_raises():
    with pytest.raises(ValueError):
        _Vol(event_id="v", start_idx=9, end_idx=3)


def test_negative_start_raises():
    with pytest.raises(ValueError):
        _Vol(event_id="v", start_idx=-1, end_idx=0)


def test_non_int_idx_raises():
    with pytest.raises(TypeError):
        _Vol(event_id="v", start_idx=1.5, end_idx=2)


def test_nan_float_field_raises():
    with pytest.raises(ValueError):
        _Vol(event_id="v", start_idx=0, end_idx=0, ratio=math.nan)


def test_subclass_post_init_calling_super_still_enforces():
    @dataclass(frozen=True)
    class _Checked(Event):
        class_id = "test_event_checked"
        ratio: float = 0.0

        def __post_init__(self):
            super().__post_init__()

    with pytest.raises(ValueError):
        _Checked(event_id="c", start_idx=5, end_idx=1)


def test_checks_off_allows_invalid():
    config.set_runtime_checks(False)
    e = _Vol(event_id="v", start_idx=9, end_idx=3, ratio=math.nan)
    assert e.start_idx == 9 and e.end_idx == 3   # 未抛错


def test_bool_start_idx_rejected():
    with pytest.raises(TypeError):
        _Vol(event_id="b", start_idx=True, end_idx=1)


def test_bool_end_idx_rejected():
    with pytest.raises(TypeError):
        _Vol(event_id="b", start_idx=0, end_idx=False)


def test_leaf_event_child_api_defaults():
    """叶子 event：child_slots 空、child/children raise、descendant_leaves 空。"""
    from path2.core import Event
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _Leaf(Event):
        class_id = "test_event_leaf_childapi"

    e = _Leaf(event_id="x", start_idx=1, end_idx=2)
    assert e.child_slots() == {}
    assert e.descendant_leaves == ()
    import pytest
    with pytest.raises(KeyError):
        e.child("nope")
    with pytest.raises(KeyError):
        e.children("nope")


def test_descendant_leaves_recursion_and_termination():
    """2 层嵌套：descendant_leaves 精确展平到叶子、零重复；终止不变式 is_leaf ⟺ child_slots()=={}。"""
    from path2.core import Event
    from dataclasses import dataclass
    from typing import Tuple

    @dataclass(frozen=True)
    class _Leaf2(Event):
        class_id = "test_event_leaf2"

    @dataclass(frozen=True)
    class _Mid(Event):
        class_id = "test_event_mid"
        kids: Tuple[_Leaf2, ...] = ()
        def child_slots(self):
            return {"kids": self.kids}

    leaves = (_Leaf2(event_id="a", start_idx=1, end_idx=1),
              _Leaf2(event_id="b", start_idx=2, end_idx=2))
    mid = _Mid(event_id="m", start_idx=1, end_idx=2, kids=leaves)
    assert mid.descendant_leaves == leaves          # 精确 2 叶、有序、零重复
    assert all(l.child_slots() == {} for l in mid.descendant_leaves)
