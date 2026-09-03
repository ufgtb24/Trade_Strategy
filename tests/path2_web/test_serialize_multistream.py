"""serialize_pattern 的 debug_enabled_nodes 对多流 detector 的契约(B1)。

背景:多流 detector 不声明 detector 级 event_cls(用 produces 声明命名流),
旧判据 `hasattr(n.detector, "event_cls")` 会让多流 node 静默掉出 debug 列表。
Task 3 已把 event_cls 反射到 node 上(NodeSpec.__post_init__),判据改读
`n.event_cls is not None`——多流 node 也正确进 debug 列表。
"""
from dataclasses import dataclass

from path2.core import Event
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2_web.serialize import serialize_pattern


@dataclass(frozen=True)
class _E(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


class _Multi:
    produces = {"a": _E, "b": _E}
    has_debug_hooks = True

    def detect(self, source): ...


def test_multistream_node_in_debug_list():
    """多流 detector 的 node(produces_stream 选中命名流)不进 debug 列表 = 静默丢。

    回归锚:单流等价由既有 test_serialize_debug_enabled_nodes.py 覆盖。
    """
    # 两个 node 须共享同一 detector 实例(而非各 new 一个),否则各自声明的 {a,b}
    # 只认领一条流,会被 Task 3 新增的全绑定校验(契约 C3)拒绝。
    det = _Multi()
    spec = PatternSpec("p", edges=(), nodes=[
        NodeSpec("a", det, produces_stream="a"),
        NodeSpec("b", det, produces_stream="b"),
    ])
    assert "a" in serialize_pattern(spec)["debug_enabled_nodes"]
