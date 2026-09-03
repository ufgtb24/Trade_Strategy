"""NodeSpec event_cls 归一化(2026-08-06 agent team 定稿,class_id 注册表已消灭):
独立 node 反射自 detector.event_cls;子结构 node(无 detector)必须显式声明 event_cls;
detector 与 produced_by 互斥。"""
import pytest

from path2.core import Event
from path2.dag.nodes import NodeSpec
from path2.atoms.throwback import ThrowbackSegment


class FakeDetector:
    event_cls = ThrowbackSegment


def test_independent_node_reflects_detector_event_cls():
    n = NodeSpec("seg", FakeDetector())
    assert n.event_cls is ThrowbackSegment


def test_detector_and_produced_by_mutually_exclusive():
    with pytest.raises(ValueError, match="互斥"):
        NodeSpec("tb_seg", FakeDetector(), produced_by="tb")


def test_substructure_node_requires_explicit_event_cls():
    """子结构 node(无 detector)必须显式声明 event_cls——注册表反查已消灭。"""
    with pytest.raises(ValueError, match="event_cls"):
        NodeSpec("tb_seg")


def test_explicit_event_cls_consistent_passes():
    n = NodeSpec("tb_seg", event_cls=ThrowbackSegment)
    assert n.event_cls is ThrowbackSegment


def test_explicit_event_cls_escape_hatch_for_arbitrary_node_id():
    """显式 event_cls 在任意 node_id 上直接保持(不再有注册表校验)。"""
    n = NodeSpec("seg1", event_cls=ThrowbackSegment)
    assert n.event_cls is ThrowbackSegment


def test_detector_without_event_cls_rejected():
    class NoClsDetector:
        pass
    with pytest.raises(ValueError, match="event_cls"):
        NodeSpec("x", NoClsDetector())
