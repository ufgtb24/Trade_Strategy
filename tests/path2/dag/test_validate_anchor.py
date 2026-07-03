"""整改四 单测:PatternSpec._validate_anchor 校验。

校验项:
  1. anchor_field 在 dst node 的 detector.event_cls 上存在
  2. anchor_src_field or 'event_id' 在 src node 的 detector.event_cls 上存在
  3. 拒绝 anchor_src_field in ('start_idx', 'end_idx')
"""
from dataclasses import dataclass, field
import pytest
from path2.core import Event
from path2.dag.spec import PatternSpec
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge


@dataclass(frozen=True)
class FakeEvent(Event):
    class_id = "fake_va"  # 唯一 id,避免与其他测试文件 class_id 冲突
    anchor_other_id: str = ""
    custom_key: str = ""


class FakeDetector:
    event_cls = FakeEvent
    def detect(self, *args):
        return iter([])


def _build_spec_with_anchor(anchor_field=None, anchor_src_field=None):
    nodes = (
        NodeSpec(node_id="src", detector=FakeDetector()),
        NodeSpec(node_id="dst", detector=FakeDetector()),
    )
    edges = (TemporalEdge("src", "dst", min_gap=1, max_gap=5,
                          anchor_field=anchor_field,
                          anchor_src_field=anchor_src_field),)
    return PatternSpec(pattern_id="anchor_test",
                       nodes=nodes, edges=edges)


def test_valid_anchor_passes():
    """合法 anchor:dst 有 anchor_other_id 字段,src 默认 event_id 字段(Event 基类有)。"""
    spec = _build_spec_with_anchor(anchor_field="anchor_other_id")
    # PatternSpec.__post_init__ 不抛异常即视为通过
    assert spec.pattern_id == "anchor_test"


def test_invalid_dst_field_raises():
    """dst event_cls 上不存在 anchor_field → ValueError。"""
    with pytest.raises(ValueError, match="anchor_field"):
        _build_spec_with_anchor(anchor_field="nonexistent_field")


def test_invalid_src_field_raises():
    """src event_cls 上不存在 anchor_src_field → ValueError。"""
    with pytest.raises(ValueError, match="anchor_src_field"):
        _build_spec_with_anchor(anchor_field="anchor_other_id",
                                anchor_src_field="nonexistent_key")


@pytest.mark.parametrize("bad_field", ["start_idx", "end_idx"])
def test_reject_monotone_coord_src_field(bad_field):
    """anchor_src_field 不允许指向单调坐标字段 → ValueError。"""
    with pytest.raises(ValueError, match=f"{bad_field}.*EqualsEdge"):
        _build_spec_with_anchor(anchor_field="anchor_other_id", anchor_src_field=bad_field)
