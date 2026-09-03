import pytest

from path2.atoms.breakout import BOEvent


def test_bo_event_defaults():
    e = BOEvent(start_idx=10, end_idx=10, confirm_idx=10)
    assert e.drought is None
    assert e.vol_ratio is None
    assert e.peak_vol_max == 0.0


def test_bo_event_frozen():
    e = BOEvent(start_idx=10, end_idx=10, confirm_idx=10, broken_refs=())
    with pytest.raises(Exception):
        e.broken_refs = (1,)


def test_bo_event_is_point_class_attr():
    """BOEvent.is_point 是 True (单点几何承诺,供 PatternSpec._validate_render_grid 反射)。"""
    assert BOEvent.is_point is True


def test_bo_event_broken_refs_default_empty_tuple():
    """新增字段 broken_refs 默认空元组,ref_slots() 空时返回 {}。"""
    e = BOEvent(start_idx=10, end_idx=10, confirm_idx=10)
    assert e.broken_refs == ()
    assert e.ref_slots() == {}
