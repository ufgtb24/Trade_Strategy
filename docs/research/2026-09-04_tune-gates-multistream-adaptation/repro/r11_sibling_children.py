"""R11: 兄弟流之间若存在 children 持有关系(A 流事件把 B 流事件当 child),
逐 node 各调一次 run_bundle 会不会让 instance_idx / instance_id 与引擎不同?"""
from dataclasses import dataclass, field
from typing import ClassVar, Tuple
from path2 import config
from path2.core import Event
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.dag.engine import run_streams, annotate_stream
from path2.dag._graph import detector_topo_order
from path2.runner import run_bundle

config.set_runtime_checks(True)

@dataclass(frozen=True)
class Pk(Event):
    is_point: ClassVar[bool] = True
@dataclass(frozen=True)
class Bo(Event):
    peaks: Tuple[Event, ...] = ()
    is_point: ClassVar[bool] = True
    def child_slots(self): return {"peak": self.peaks} if self.peaks else {}

class TwoStream:
    """产 bo / pk 两流;bo 事件把同趟的 pk 事件当 child 持有(跨兄弟 children)。"""
    produces: ClassVar[dict] = {"bo": Bo, "pk": Pk}
    def detect(self, df):
        pks = [Pk(start_idx=i, end_idx=i, confirm_idx=i) for i in (2, 4)]
        for p in pks:
            yield ("pk", p)
        for i in (5, 7):
            yield ("bo", Bo(start_idx=i, end_idx=i, confirm_idx=i, peaks=tuple(pks)))

def build():
    det = TwoStream()
    return PatternSpec(pattern_id="t", nodes=(
        NodeSpec("bo", det, produces_stream="bo", children={"peak": "pk"}),
        NodeSpec("pk", det, produces_stream="pk", solve=False),
    ), edges=())

def naive(spec):
    by_id = {n.node_id: n for n in spec.nodes}
    children_of = {n.node_id: dict(n.children) for n in spec.nodes if n.children}
    streams, counts = {}, {}
    for nid in detector_topo_order(spec.nodes):
        node = by_id[nid]
        evs = run_bundle(node.detector, None)[node.produces_stream]
        annotate_stream(counts, nid, evs, children_of)
        streams[nid] = evs
    return streams

def show(st, tag):
    print(f"{tag:8s} pk 流:", [(e.instance_id) for e in st["pk"]])
    print(f"{'':8s} bo 持有的 child pk:", [[c.instance_id for c in e.peaks] for e in st["bo"]])

eng = run_streams(build(), None)
nv = naive(build())
show(eng, "engine"); show(nv, "naive")
same = ([e.instance_id for e in eng["pk"]] == [e.instance_id for e in nv["pk"]]
        and [[c.instance_id for c in e.peaks] for e in eng["bo"]]
            == [[c.instance_id for c in e.peaks] for e in nv["bo"]])
print("instance_id 逐字相同?", same)
