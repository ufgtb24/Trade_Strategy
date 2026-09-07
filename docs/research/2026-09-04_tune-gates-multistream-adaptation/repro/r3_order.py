"""R3: 「兄弟流何时被标注」在三种产流循环下的差异——下游 detector 在 detect 期能否读到
兄弟流的 instance_id。current(现工具,逐 node)/ draft(草案 4.1)/ engine(run_streams)。"""
from dataclasses import dataclass, field
from typing import ClassVar, Tuple
from path2.core import Event
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag.engine import run_streams, annotate_stream
from path2.dag._graph import detector_topo_order
from path2.runner import run, run_bundle

SEEN = {}   # 模式名 -> 下游 detect 期看到的兄弟流 instance_id

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
    """产 a / b 两条流;a 事件引用同趟的 b 事件(跨流引用,多流的典型形状)。"""
    produces: ClassVar[dict] = {"a": A, "b": B}
    def detect(self, df):
        bs = [B(start_idx=i, end_idx=i, confirm_idx=i) for i in (2, 4)]
        for b in bs:
            yield ("b", b)
        for i in (5, 7):
            yield ("a", A(start_idx=i, end_idx=i, confirm_idx=i, peer=tuple(bs)))

class Downstream:
    """consumes_stream='a' 的下游:detect 期去读上游 a 事件所引用的 b 事件的 instance_id。"""
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
        NodeSpec("na", det, produces_stream="a"),
        NodeSpec("nb", det, produces_stream="b", solve=False),
        NodeSpec("nc", Downstream(tag), consumes_stream="na"),
    ), edges=())

def current_tool(spec):
    """现工具 multivar_core.py:300-315 的逐 node 循环(单流 run,按 nid 缓存)。"""
    by_id = {n.node_id: n for n in spec.nodes}
    children_of = {n.node_id: dict(n.children) for n in spec.nodes if n.children}
    streams, counts = {}, {}
    for nid in detector_topo_order(spec.nodes):
        node = by_id[nid]
        if node.detector is None:
            continue
        if node.consumes_stream is None:
            evs = list(run(node.detector, None))
        else:
            evs = list(run(node.detector, streams[node.consumes_stream], None))
        annotate_stream(counts, nid, evs, children_of)
        streams[nid] = evs
    return streams

def draft(spec):
    by_id = {n.node_id: n for n in spec.nodes}
    children_of = {n.node_id: dict(n.children) for n in spec.nodes if n.children}
    sib = {}
    for n in spec.nodes:
        if n.detector is not None:
            sib.setdefault((id(n.detector), n.consumes_stream), []).append(n)
    streams, counts = {}, {}
    for nid in detector_topo_order(spec.nodes):
        node = by_id[nid]
        if node.detector is None or nid in streams:
            continue
        g = (id(node.detector), node.consumes_stream)
        src = (None,) if node.consumes_stream is None else (streams[node.consumes_stream], None)
        bundle = run_bundle(node.detector, *src)
        for s in sib[g]:
            streams[s.node_id] = bundle[s.produces_stream]
            annotate_stream(counts, s.node_id, streams[s.node_id], children_of)
    return streams

print("detector_topo_order:", detector_topo_order(build("x").nodes))
try:
    current_tool(build("current"))
except Exception as e:
    print("current 抛错:", type(e).__name__, e)
draft(build("draft"))
run_streams(build("engine"), None)
for k in ("current", "draft", "engine"):
    print(f"{k:8s} 下游 detect 期看到的兄弟流 instance_id:", SEEN.get(k))
