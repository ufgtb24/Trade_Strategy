from dataclasses import dataclass
import pytest
from path2.core import Event
from path2.dag.edges import TemporalEdge
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec


@dataclass(frozen=True)
class _Pt(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0
    is_point = True


class _Dual:
    produces = {"a": _Pt, "b": _Pt}
    def detect(self, source): ...


def test_render_grid_price_validates_node_event_cls():
    # 多流 detector 无 event_cls 属性;若不改读 node 级,此 spec 会被误判 event_cls 缺失
    # 校验在 PatternSpec.__post_init__ 触发;不抛错即通过
    # 两个 node 须共享同一 detector 实例(而非各 new 一个),否则各自声明的
    # {a,b} 只认领一条流,会被 Task 3 新增的全绑定校验(契约 C3)拒绝。
    det = _Dual()
    PatternSpec("p", edges=(), nodes=[
        NodeSpec("a", det, produces_stream="a", render_grid="price"),
        NodeSpec("b", det, produces_stream="b"),
    ])


def test_anchor_validates_node_event_cls():
    # 多流 detector 无 event_cls 属性;锚边校验若不改读 node 级,构造会因
    # AttributeError 崩溃(而非干净报错)。校验在 __post_init__ 触发;不抛错即通过
    # 两个 node 须共享同一 detector 实例,理由同上(契约 C3 全绑定校验)。
    det = _Dual()
    PatternSpec("p", edges=(
        TemporalEdge("a", "b", min_gap=0, max_gap=10, anchor_field="start_idx"),
    ), nodes=[
        NodeSpec("a", det, produces_stream="a"),
        NodeSpec("b", det, produces_stream="b"),
    ])


def test_self_feed_rejected():
    # 自喂:node b 的 consumes_stream 指向与它共享同一 detector 的 node a。
    # 多流下最可能的误写是「让 bo 节点 consumes_stream='pk' 以为读同趟 pk 流」,
    # 实际那是 (id(det),'pk') 的第二次 detect 调用,白跑一整趟 → 构造即拒绝
    det = _Dual()
    with pytest.raises(ValueError, match="自喂|同一 detector"):
        PatternSpec("p", edges=(), nodes=[
            NodeSpec("a", det, produces_stream="a"),
            NodeSpec("b", det, produces_stream="b", consumes_stream="a"),   # 共享同一 detector → 自喂
        ])
