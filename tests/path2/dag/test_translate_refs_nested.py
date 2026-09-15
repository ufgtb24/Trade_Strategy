"""_translate_refs 递归下钻 child_slots:子结构事件的引用槽也被翻译。

背景:标注(_annotate_children)是递归的,翻译原先只遍历 streams 里的顶层事件。
这个不对称让子结构事件的 ref_slots() 静默失效——ref_ids 恒为空,where 读出来
就是「没有引用」,与引用池外对象那条响亮报错的待遇相反。
"""
from dataclasses import dataclass
from typing import Tuple

from path2.core import Event
from path2.dag.engine import analyze
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec


@dataclass(frozen=True)
class Anchor(Event):
    """被引用的独立事件。"""
    pass


@dataclass(frozen=True)
class Seg(Event):
    """子结构事件:自己带引用槽,指向 Anchor。"""
    cites: Tuple[Event, ...] = ()

    def ref_slots(self):
        return {"cites": self.cites} if self.cites else {}


@dataclass(frozen=True)
class Container(Event):
    """复合事件容器:segments 槽装 Seg。"""
    segments: Tuple[Seg, ...] = ()

    def child_slots(self):
        return {"segments": self.segments}


class AnchorDetector:
    event_cls = Anchor

    def detect(self, df):
        yield Anchor(start_idx=0, end_idx=0, confirm_idx=0)


class ContainerDetector:
    """消费 anchor 流,产一个容器,容器内的段引用那个 anchor。"""
    event_cls = Container

    def detect(self, anchor_stream, df):
        anchors = tuple(anchor_stream)
        seg = Seg(start_idx=2, end_idx=4, confirm_idx=2, cites=anchors)
        yield Container(start_idx=2, end_idx=4, confirm_idx=2, segments=(seg,))


def _spec():
    return PatternSpec(
        pattern_id="t_nested_refs",
        nodes=(
            NodeSpec("anchor", AnchorDetector()),
            NodeSpec("box", ContainerDetector(), consumes_stream="anchor",
                     children={"segments": "seg"}),
            NodeSpec("seg", event_cls=Seg),
        ),
        edges=(),
    )


def test_nested_child_ref_slots_translated():
    """子结构事件的引用槽被翻译成 instance_id(递归下钻)。"""
    res = analyze(_spec(), df=object())
    boxes = [e for e in res.events if isinstance(e, Container)]
    assert len(boxes) == 1, f"应有 1 个容器,got {len(boxes)}"
    seg = boxes[0].segments[0]
    # 段自身已被标注(标注本来就递归)
    assert seg.node_id == "seg"
    # ★ 核心断言:段的引用槽被翻译(改动前恒为空元组)
    assert seg.ref_ids_of("cites") == ("anchor_0#0",), (
        f"子结构事件的 ref_slots 未被翻译,got {seg.ref_ids_of('cites')!r}")


def test_toplevel_ref_slots_still_translated():
    """回归:顶层事件的引用槽照常翻译(递归不能把原路径弄坏)。"""

    @dataclass(frozen=True)
    class Citer(Event):
        cites: Tuple[Event, ...] = ()

        def ref_slots(self):
            return {"cites": self.cites} if self.cites else {}

    class CiterDetector:
        event_cls = Citer

        def detect(self, anchor_stream, df):
            yield Citer(start_idx=3, end_idx=3, confirm_idx=3,
                        cites=tuple(anchor_stream))

    spec = PatternSpec(
        pattern_id="t_toplevel_refs",
        nodes=(NodeSpec("anchor", AnchorDetector()),
               NodeSpec("citer", CiterDetector(), consumes_stream="anchor")),
        edges=(),
    )
    res = analyze(spec, df=object())
    citers = [e for e in res.events if isinstance(e, Citer)]
    assert citers[0].ref_ids_of("cites") == ("anchor_0#0",)
