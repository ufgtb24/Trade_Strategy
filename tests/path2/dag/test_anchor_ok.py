"""整改四 单测:DependencyEdge._anchor_ok。

三路径覆盖:
  1. anchor_field=None → 恒 True(无 anchor 约束,字节等价旧行为)
  2. anchor_field 非空 + anchor_src_field=None → 默认 src.event_id 路径(等价 C1 设想)
  3. anchor_field 非空 + anchor_src_field 显式 → 通用 C2 键对键等值
"""
from dataclasses import dataclass, field
import pytest
from path2.core import Event
from path2.dag.edges import TemporalEdge


@dataclass(frozen=True)
class FakeEvent(Event):
    """带 anchor 字段的 mock 事件类。"""
    class_id = "fake"
    anchor_other_id: str = ""
    custom_key: str = ""


def test_anchor_ok_no_anchor_field_always_true():
    """anchor_field=None 时 _anchor_ok 恒 True。"""
    edge = TemporalEdge("a", "b", min_gap=1, max_gap=5)  # 无 anchor_field
    src = FakeEvent(event_id="s_0", start_idx=0, end_idx=0)
    dst = FakeEvent(event_id="d_0", start_idx=2, end_idx=2)
    assert edge._anchor_ok(src, dst) is True


def test_anchor_ok_default_src_field_is_event_id():
    """anchor_field 非空 + anchor_src_field=None → src.event_id。"""
    edge = TemporalEdge("a", "b", min_gap=1, max_gap=5, anchor_field="anchor_other_id")
    src = FakeEvent(event_id="s_42", start_idx=0, end_idx=0)
    dst_ok = FakeEvent(event_id="d_0", start_idx=2, end_idx=2, anchor_other_id="s_42")
    dst_wrong = FakeEvent(event_id="d_1", start_idx=2, end_idx=2, anchor_other_id="s_99")
    assert edge._anchor_ok(src, dst_ok) is True
    assert edge._anchor_ok(src, dst_wrong) is False


def test_anchor_ok_explicit_src_field():
    """anchor_field + anchor_src_field 显式 → 任意键对键等值。"""
    edge = TemporalEdge("a", "b", min_gap=1, max_gap=5,
                        anchor_field="anchor_other_id", anchor_src_field="custom_key")
    src = FakeEvent(event_id="s_0", start_idx=0, end_idx=0, custom_key="cust_42")
    dst_ok = FakeEvent(event_id="d_0", start_idx=2, end_idx=2, anchor_other_id="cust_42")
    dst_wrong = FakeEvent(event_id="d_1", start_idx=2, end_idx=2, anchor_other_id="cust_99")
    assert edge._anchor_ok(src, dst_ok) is True
    assert edge._anchor_ok(src, dst_wrong) is False
