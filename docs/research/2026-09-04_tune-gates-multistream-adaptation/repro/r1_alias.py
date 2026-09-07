"""R1: 别名(两 node 认领同一 (det, consumes, produces))在引擎里的真实行为 + spec 是否允许。"""
from dataclasses import dataclass
from typing import ClassVar
from path2.core import Event
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag.engine import run_streams

@dataclass(frozen=True)
class A(Event):
    is_point: ClassVar[bool] = True
@dataclass(frozen=True)
class B(Event):
    is_point: ClassVar[bool] = True

class TwoStream:
    produces: ClassVar[dict] = {"a": A, "b": B}
    def detect(self, df):
        for i in (1, 3, 5):
            yield ("a", A(start_idx=i, end_idx=i, confirm_idx=i))
        for i in (2, 4):
            yield ("b", B(start_idx=i, end_idx=i, confirm_idx=i))

det = TwoStream()

if __name__ == '__main__':


    # 1) spec 是否允许别名?
    try:
        spec = PatternSpec(pattern_id="t", nodes=(
            NodeSpec("n1", det, produces_stream="a"),
            NodeSpec("n2", det, produces_stream="a"),   # ← 别名
            NodeSpec("nb", det, produces_stream="b", solve=False),
        ), edges=())
        print("PatternSpec 接受别名: YES")
    except Exception as e:
        print("PatternSpec 拒绝别名:", type(e).__name__, e)
        spec = None

    if spec is not None:
        st = run_streams(spec, None)
        print("streams keys:", list(st))
        print("n1 is n2 (同一 list 对象):", st["n1"] is st["n2"])
        print("n1 事件 node_id:", [e.node_id for e in st["n1"]])
        print("n2 事件 node_id:", [e.node_id for e in st["n2"]])
        print("n2 事件 instance_id:", [e.instance_id for e in st["n2"]])
        print("nb 事件 node_id:", [e.node_id for e in st["nb"]])

    # 2) 声明序反转:别名先声明 n2 会怎样?
    spec2 = PatternSpec(pattern_id="t", nodes=(
        NodeSpec("n2", det, produces_stream="a"),
        NodeSpec("n1", det, produces_stream="a"),
        NodeSpec("nb", det, produces_stream="b", solve=False),
    ), edges=())
    st2 = run_streams(spec2, None)
    print("--- 声明序反转 ---")
    print("n1 事件 node_id:", [e.node_id for e in st2["n1"]])
    print("n2 事件 node_id:", [e.node_id for e in st2["n2"]])
