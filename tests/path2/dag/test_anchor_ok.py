"""整改四 单测:DependencyEdge._anchor_ok。

覆盖:
  1. anchor_field=None → 恒 True(无 anchor 约束)
  2. anchor_field 非空 → src 端身份 = src.instance_id(交错标注后 detect 期即非 None),
     dst 端 anchor_field 值与该 instance_id 标量相等(anchor_src_field 已退役、不再读取)
  3. anchor 字段为集合 → 包含语义
"""
from dataclasses import dataclass
from path2.core import Event
from path2.dag.edges import TemporalEdge


@dataclass(frozen=True)
class FakeEvent(Event):
    """带 anchor 字段的 mock 事件类。"""
    anchor_other_id: str = ""


def test_anchor_ok_no_anchor_field_always_true():
    """anchor_field=None 时 _anchor_ok 恒 True。"""
    edge = TemporalEdge("a", "b", min_gap=1, max_gap=5)  # 无 anchor_field
    src = FakeEvent(start_idx=0, end_idx=0, confirm_idx=0)
    dst = FakeEvent(start_idx=2, end_idx=2, confirm_idx=2)
    assert edge._anchor_ok(src, dst) is True


def test_anchor_ok_instance_id_identity_point():
    """anchor_field 非空 → src 身份 = src.instance_id;dst anchor 与之标量相等才放行。"""
    edge = TemporalEdge("a", "b", min_gap=1, max_gap=5, anchor_field="anchor_other_id")
    src = FakeEvent(start_idx=0, end_idx=0, confirm_idx=0, instance_id="FakeEvent_0")
    dst_ok = FakeEvent(start_idx=2, end_idx=2, confirm_idx=2, anchor_other_id="FakeEvent_0")
    dst_wrong = FakeEvent(start_idx=2, end_idx=2, confirm_idx=2, anchor_other_id="FakeEvent_99")
    assert edge._anchor_ok(src, dst_ok) is True
    assert edge._anchor_ok(src, dst_wrong) is False


def test_anchor_ok_instance_id_identity_interval():
    """区间 src 的 instance_id 带 start_end 形态。"""
    edge = TemporalEdge("a", "b", min_gap=1, max_gap=5, anchor_field="anchor_other_id")
    src = FakeEvent(start_idx=0, end_idx=5, confirm_idx=0, instance_id="FakeEvent_0_5")
    dst_ok = FakeEvent(start_idx=6, end_idx=6, confirm_idx=6, anchor_other_id="FakeEvent_0_5")
    dst_wrong = FakeEvent(start_idx=6, end_idx=6, confirm_idx=6, anchor_other_id="FakeEvent_0_4")
    assert edge._anchor_ok(src, dst_ok) is True
    assert edge._anchor_ok(src, dst_wrong) is False


def test_anchor_ok_set_field_containment():
    """anchor 字段为集合(tuple)时 -> 包含语义(src instance_id ∈ 集合)。"""
    edge = TemporalEdge("a", "b", min_gap=1, max_gap=5, anchor_field="anchor_other_id")
    src = FakeEvent(start_idx=0, end_idx=0, confirm_idx=0, instance_id="FakeEvent_0")
    dst_ok = FakeEvent(start_idx=2, end_idx=2, confirm_idx=2,
                       anchor_other_id=("FakeEvent_0", "FakeEvent_99"))
    dst_wrong = FakeEvent(start_idx=2, end_idx=2, confirm_idx=2,
                          anchor_other_id=("FakeEvent_1", "FakeEvent_99"))
    assert edge._anchor_ok(src, dst_ok) is True
    assert edge._anchor_ok(src, dst_wrong) is False
