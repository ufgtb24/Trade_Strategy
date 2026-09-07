"""运行期 C1/C2/C3: 声明 children vs 实例 child_slots 双向对照 + 类型核对(RUNTIME_CHECKS 门控)。"""
from dataclasses import dataclass

import pytest

from path2.core import Event
from path2.dag.engine import analyze
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from tests.path2.dag._oracle import Ev


@dataclass(frozen=True)
class Box(Event):
    """容器: 声明 child_slots={'members'} 的测试事件。"""
    members: tuple = ()

    def child_slots(self):
        return {"members": self.members}


@dataclass(frozen=True)
class Inner(Event):
    pass


@dataclass(frozen=True)
class OtherInner(Event):
    pass


class BoxDetector:
    event_cls = Box

    def detect(self, df):
        yield Box(start_idx=0, end_idx=1, confirm_idx=1,
                  members=(Inner(start_idx=0, end_idx=0, confirm_idx=0),))


def _spec(children, box_detector=None):
    return PatternSpec(
        pattern_id="t",
        nodes=(NodeSpec("box", box_detector or BoxDetector(), children=children),
               NodeSpec("inner", event_cls=Inner)),   # 子结构 node 显式 event_cls
        edges=(),
    )


def test_c1_declared_missing_from_instance_raises():
    @dataclass(frozen=True)
    class NoMembersBox(Event):
        def child_slots(self):
            return {}

    class NoMembersDetector:
        event_cls = NoMembersBox

        def detect(self, df):
            yield NoMembersBox(start_idx=0, end_idx=1, confirm_idx=1)

    spec = PatternSpec(pattern_id="t", nodes=(
        NodeSpec("box", NoMembersDetector(), children={"members": "inner"}),
        NodeSpec("inner", event_cls=Inner)), edges=())
    with pytest.raises(RuntimeError, match="未物化"):
        analyze(spec, df=object())


def test_undeclared_instance_slot_raises_at_annotate():
    """正常路径:实例有未声明槽 → 标注期 ValueError(早于出口 C2)。"""
    @dataclass(frozen=True)
    class ExtraBox(Event):
        def child_slots(self):
            return {"members": (), "extra": ()}

    class ExtraDetector:
        event_cls = ExtraBox

        def detect(self, df):
            yield ExtraBox(start_idx=0, end_idx=1, confirm_idx=1)

    spec = PatternSpec(pattern_id="t", nodes=(
        NodeSpec("box", ExtraDetector(), children={"members": "inner"}),
        NodeSpec("inner", event_cls=Inner)), edges=())
    with pytest.raises(ValueError, match="未在 children 声明中"):
        analyze(spec, df=object())


def test_c2_undeclared_instance_slot_raises_on_preset():
    """preset 路径:预置流跳过检测与标注,出口 C2 是唯一防线 → RuntimeError。"""
    from path2.dag.engine import run_streams

    @dataclass(frozen=True)
    class ExtraBox(Event):
        def child_slots(self):
            return {"members": (), "extra": ()}

    class ExtraDetector:
        event_cls = ExtraBox

        def detect(self, df):
            yield ExtraBox(start_idx=0, end_idx=1, confirm_idx=1)

    spec = PatternSpec(pattern_id="t", nodes=(
        NodeSpec("box", ExtraDetector(), children={"members": "inner"}),
        NodeSpec("inner", event_cls=Inner)), edges=())
    # 预置一个已带身份的容器实例(模拟上一次 run_streams 的返回值)
    preset_box = ExtraBox(start_idx=0, end_idx=1, confirm_idx=1)
    object.__setattr__(preset_box, "node_id", "box")
    object.__setattr__(preset_box, "instance_idx", 0)
    object.__setattr__(preset_box, "instance_id", "box_0_1#0")
    with pytest.raises(RuntimeError, match="未声明"):
        run_streams(spec, df=object(), preset={"box": [preset_box]})


def test_c3_slot_element_type_mismatch_raises():
    class WrongDetector:
        event_cls = Box

        def detect(self, df):
            yield Box(start_idx=0, end_idx=1, confirm_idx=1,
                      members=(OtherInner(start_idx=0, end_idx=0, confirm_idx=0),))   # 物化错类型

    spec = _spec({"members": "inner"}, box_detector=WrongDetector())
    with pytest.raises(RuntimeError, match="期望"):
        analyze(spec, df=object())


def test_c1c2c3_pass_when_declaration_matches_instance():
    spec = _spec({"members": "inner"})
    res = analyze(spec, df=object())
    assert res.matches          # 无报错即通过
