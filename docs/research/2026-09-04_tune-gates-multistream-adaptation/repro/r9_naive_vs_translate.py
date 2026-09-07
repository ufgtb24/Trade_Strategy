"""R9: 决定性实验——「逐 node 各调一次 run_bundle」(不做兄弟分组)在真实 bb_v1 上:
(a) 每条流自己的 node_id/instance_idx/instance_id 是否与引擎逐字相同?
(b) 加回 _translate_refs(等价性所必需)之后会发生什么?
另核实 tool-mech 的层一:build_pattern 每次 new detector,id() 跨 spec 不稳定。"""
import glob, importlib
from pathlib import Path
import pandas as pd
from path2 import config
from path2.dag.engine import run_streams, annotate_stream, _translate_refs
from path2.dag._graph import detector_topo_order
from path2.runner import run_bundle

config.set_runtime_checks(True)
mod = importlib.import_module("path2_apps.bb_v1.dag_spec")
P = importlib.import_module("path2_apps.bb_v1.params")
params = P.Params.from_yaml(Path("path2_apps/bb_v1/params.yaml"))

# --- 核实 tool-mech 层一:id(detector) 跨 build_pattern 是否稳定 ---
ids = [tuple(sorted((n.node_id, id(n.detector)) for n in mod.build_pattern(params).nodes
                    if n.detector is not None)) for _ in range(3)]
print("id(detector) 跨三次 build_pattern 相同?", ids[0] == ids[1] == ids[2])
s0 = mod.build_pattern(params); s1 = mod.build_pattern(params)   # 两份同时活着
d0 = {n.node_id: id(n.detector) for n in s0.nodes if n.detector is not None}
d1 = {n.node_id: id(n.detector) for n in s1.nodes if n.detector is not None}
print("同时存活的两份 spec 的 id 有交集?", set(d0.values()) & set(d1.values()))

def naive(spec, df, translate: bool):
    """逐 node 各调一次 run_bundle,不做兄弟分组。"""
    by_id = {n.node_id: n for n in spec.nodes}
    children_of = {n.node_id: dict(n.children) for n in spec.nodes if n.children}
    streams, counts, ncall = {}, {}, 0
    for nid in detector_topo_order(spec.nodes):
        node = by_id[nid]
        if node.detector is None:
            continue
        src = (df,) if node.consumes_stream is None else (streams[node.consumes_stream], df)
        ncall += 1
        evs = run_bundle(node.detector, *src)[node.produces_stream]
        annotate_stream(counts, nid, evs, children_of)
        streams[nid] = evs
    if translate:
        _translate_refs(streams)
    return streams, ncall

def ann(streams):    # 只比标注三元组,不含 ref_ids
    return {nid: [(type(e).__name__, e.start_idx, e.end_idx, e.node_id, e.instance_idx, e.instance_id)
                  for e in evs] for nid, evs in streams.items()}

same, raised, calls = 0, 0, set()
for p in sorted(glob.glob("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/*.pkl"))[:12]:
    df = pd.read_pickle(p)
    eng = run_streams(mod.build_pattern(params), df)
    nv, nc = naive(mod.build_pattern(params), df, translate=False)
    calls.add(nc)
    same += (ann(eng) == ann(nv))
    try:
        naive(mod.build_pattern(params), df, translate=True)
    except Exception as e:
        raised += 1
        msg = f"{type(e).__name__}: {str(e)[:110]}"
print(f"(a) 12 只: 标注三元组与引擎逐字相同 = {same}/12   (naive detect 调用次数={calls}, 引擎=3)")
print(f"(b) 12 只: 加回 _translate_refs 后抛错 = {raised}/12")
print("    抛错样本:", msg if raised else "无")
