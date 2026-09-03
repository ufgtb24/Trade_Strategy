"""整改四 单测(Ruling H):PatternSpec._validate_anchor 校验。

Ruling H 后 anchor_src_field 退役:src 端身份由 _anchor_ok 按
span_id(type(src_ep).__name__, span) 计算、不再读 src 字段 → 原「src 字段存在性」
与「拒绝单调坐标」两闸已删,仅保留 dst 端 anchor_field 存在性校验。
"""
from dataclasses import dataclass
import pytest
from path2.core import Event
from path2.dag.spec import PatternSpec
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge


@dataclass(frozen=True)
class FakeEvent(Event):
    anchor_other_id: str = ""


class FakeDetector:
    event_cls = FakeEvent
    def detect(self, *args):
        return iter([])


def _build_spec_with_anchor(anchor_field=None):
    nodes = (
        NodeSpec(node_id="src", detector=FakeDetector()),
        NodeSpec(node_id="dst", detector=FakeDetector()),
    )
    edges = (TemporalEdge("src", "dst", min_gap=1, max_gap=5,
                          anchor_field=anchor_field),)
    return PatternSpec(pattern_id="anchor_test",
                       nodes=nodes, edges=edges)


def test_valid_anchor_passes():
    """合法 anchor:dst event_cls 上有 anchor_other_id 字段。"""
    spec = _build_spec_with_anchor(anchor_field="anchor_other_id")
    # PatternSpec.__post_init__ 不抛异常即视为通过
    assert spec.pattern_id == "anchor_test"


def test_invalid_dst_field_raises():
    """dst event_cls 上不存在 anchor_field → ValueError。"""
    with pytest.raises(ValueError, match="anchor_field"):
        _build_spec_with_anchor(anchor_field="nonexistent_field")
