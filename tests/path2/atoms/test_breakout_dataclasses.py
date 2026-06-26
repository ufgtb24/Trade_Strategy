import pytest

from path2.atoms.breakout import Peak, BOEvent


def test_peak_mutable_for_elevation():
    """Peak 非 frozen — elevation 机制需要原地抬升 peak.price 并记录 original_price。
    设计选择对齐 dev BreakoutStrategy/analysis/breakout_detector.py:Peak 是 BODetector
    私有内部状态、不出 stream、不进 Event 系统,无 frozen 协议要求。"""
    p = Peak(index=5, price=10.0, pk_id=0, volume_peak=1.5, relative_height=0.08)
    assert p.original_price is None     # 默认未抬升
    # 模拟 elevation: 首次抬升前记录 original_price 作 supersede 锚
    p.original_price = p.price
    p.price = 10.5
    assert p.price == 10.5 and p.original_price == 10.0


def test_bo_event_defaults():
    e = BOEvent(event_id="bo_10", start_idx=10, end_idx=10)
    assert e.drought is None
    assert e.pk_count == 0
    assert e.broken_peak_ids == ()
    assert e.vol_ratio is None
    assert e.peak_vol_max == 0.0


def test_bo_event_broken_peak_ids_is_tuple():
    # I4: 即便传 list 也应被强转为 tuple,防 in-place mutate
    e = BOEvent(event_id="bo_10", start_idx=10, end_idx=10,
                broken_peak_ids=[1, 2, 3])
    assert isinstance(e.broken_peak_ids, tuple)
    assert e.broken_peak_ids == (1, 2, 3)


def test_bo_event_frozen():
    e = BOEvent(event_id="bo_10", start_idx=10, end_idx=10, pk_count=2)
    with pytest.raises(Exception):
        e.pk_count = 5


def test_bo_event_is_point_class_attr():
    """BOEvent.is_point 是 True (单点几何承诺,供 PatternSpec._validate_render_grid 反射)。"""
    assert BOEvent.is_point is True


def test_bo_event_referenced_points_default_empty_tuple():
    """新增字段 referenced_points 默认空元组。"""
    e = BOEvent(event_id="bo_10", start_idx=10, end_idx=10)
    assert e.referenced_points == ()


def test_bo_event_referenced_points_accepts_tuple():
    """referenced_points 接受 (bar_idx, price, label) 三元组的元组。"""
    pts = ((5, 12.5, "pk0"), (7, 13.0, "pk1"))
    e = BOEvent(event_id="bo_10", start_idx=10, end_idx=10,
                referenced_points=pts)
    assert e.referenced_points == pts
    assert isinstance(e.referenced_points, tuple)


def test_bo_event_referenced_points_is_tuple_from_list():
    """传 list 时强转 tuple (与 broken_peak_ids 同型, 防 in-place mutate)。"""
    e = BOEvent(event_id="bo_10", start_idx=10, end_idx=10,
                referenced_points=[(5, 12.5, "pk0")])
    assert isinstance(e.referenced_points, tuple)
    assert e.referenced_points == ((5, 12.5, "pk0"),)
