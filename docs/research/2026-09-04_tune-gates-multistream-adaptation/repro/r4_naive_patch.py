"""R4: 反例——「最小补丁」(仅把 run() 换成 run_bundle()、仍按 node 逐个物化)与引擎不等价。
构造:兄弟流 node_id 字典序排在下游 node 之后 → 逐 node 循环会在下游 detect 之后才标注兄弟流。"""
from dataclasses import dataclass
from typing import ClassVar, Tuple
from path2.core import Event
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag.engine import run_streams, annotate_stream
from path2.dag._graph import detector_topo_order
from path2.runner import run_bundle

SEEN = {}

@dataclass(frozen=True)
class A(Event):
    peer: Tuple[Event, ...] = ()
    is_point: ClassVar[bool] = True
@dataclass(frozen=True)
class B(Event):
    is_point: ClassVar[bool] = True
@dataclass(frozen=True)
class C(Event):
    seen: str = ""
    is_point: ClassVar[bool] = True

class TwoStream:
    produces: ClassVar[dict] = {"a": A, "b": B}
    def detect(self, df):
        bs = [B(start_idx=i, end_idx=i, confirm_idx=i) for i in (2, 4)]
        for b in bs:
            yield ("b", b)
        for i in (5, 7):
            yield ("a", A(start_idx=i, end_idx=i, confirm_idx=i, peer=tuple(bs)))

class Downstream:
    event_cls = C
    def __init__(self, tag): self.tag = tag
    def detect(self, aevs, df):
        for a in aevs:
            SEEN.setdefault(self.tag, []).append(tuple(p.instance_id for p in a.peer))
            yield C(start_idx=a.start_idx, end_idx=a.end_idx, confirm_idx=a.start_idx,
                    seen=str([p.instance_id for p in a.peer]))

def build(tag):
    det = TwoStream()
    return PatternSpec(pattern_id="t", nodes=(
        NodeSpec("a_node", det, produces_stream="a"),
        NodeSpec("z_node", det, produces_stream="b", solve=False),   # ← 字典序最后
        NodeSpec("m_node", Downstream(tag), consumes_stream="a_node"),
    ), edges=())

def naive_patch(spec):
    """最小补丁:run_bundle 取整包但仍逐 node 物化(每 node 一次 detect 调用)。"""
    by_id = {n.node_id: n for n in spec.nodes}
    children_of = {n.node_id: dict(n.children) for n in spec.nodes if n.children}
    streams, counts = {}, {}
    ncall = [0]
    for nid in detector_topo_order(spec.nodes):
        node = by_id[nid]
        if node.detector is None:
            continue
        src = (None,) if node.consumes_stream is None else (streams[node.consumes_stream], None)
        ncall[0] += 1
        evs = run_bundle(node.detector, *src)[node.produces_stream]
        annotate_stream(counts, nid, evs, children_of)
        streams[nid] = evs
    return streams, ncall[0]

print("detector_topo_order:", detector_topo_order(build("x").nodes))
st_n, ncall = naive_patch(build("naive"))
st_e = run_streams(build("engine"), None)
print(f"naive_patch detect 调用次数={ncall}(引擎=2)")
print("naive  下游 detect 期看到的兄弟流 instance_id:", SEEN.get("naive"))
print("engine 下游 detect 期看到的兄弟流 instance_id:", SEEN.get("engine"))
print("naive  m_node 事件 seen 字段:", [e.seen for e in st_n["m_node"]])
print("engine m_node 事件 seen 字段:", [e.seen for e in st_e["m_node"]])
print("等价?", [e.seen for e in st_n["m_node"]] == [e.seen for e in st_e["m_node"]])
