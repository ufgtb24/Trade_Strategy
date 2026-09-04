"""R2: 草案 4.1 伪代码 vs 引擎 run_streams —— 逐事件对拍(含别名拓扑 + 真实 bb_v1)。"""
import sys, pandas as pd
from path2 import config
from path2.dag._graph import detector_topo_order
from path2.dag.engine import annotate_stream, run_streams
from path2.runner import run_bundle

def draft_41(spec0, win, combo=None, infl=None):
    """草案 4.1 的产流循环(单 combo 版:去掉跨 combo 缓存,只验产流+标注等价)。"""
    by_id = {n.node_id: n for n in spec0.nodes}
    children_of = {n.node_id: dict(n.children) for n in spec0.nodes if n.children}
    siblings = {}
    for n in spec0.nodes:
        if n.detector is not None:
            siblings.setdefault((id(n.detector), n.consumes_stream), []).append(n)
    streams, counts, stream_cache = {}, {}, {}
    for nid in detector_topo_order(spec0.nodes):
        node = by_id[nid]
        if node.detector is None or nid in streams:
            continue
        gkey = (id(node.detector), node.consumes_stream)
        ckey = (gkey, ())
        if ckey not in stream_cache:
            src = (win,) if node.consumes_stream is None else (streams[node.consumes_stream], win)
            bundle = run_bundle(node.detector, *src)
            got = {}
            for sib in siblings[gkey]:
                got[sib.node_id] = bundle[sib.produces_stream]
                annotate_stream(counts, sib.node_id, got[sib.node_id], children_of)
            stream_cache[ckey] = got
        streams.update(stream_cache[ckey])
    return streams

def sig(streams):
    return {nid: [(type(e).__name__, e.start_idx, e.end_idx, e.node_id, e.instance_idx,
                   e.instance_id, e.ref_ids) for e in evs] for nid, evs in streams.items()}

def cmp(name, spec, df):
    a = run_streams(spec, df)          # 引擎(含 _translate_refs / children 校验)
    b = draft_41(spec, df)             # 草案
    ka, kb = set(a), set(b)
    ok_keys = ka == kb
    sa, sb = sig(a), sig(b)
    # 别名折叠的 list 身份也要一致
    ida = {nid: id(v) for nid, v in a.items()}
    idb = {nid: id(v) for nid, v in b.items()}
    groups_a = sorted(sorted(k for k, v in ida.items() if v == g) for g in set(ida.values()))
    groups_b = sorted(sorted(k for k, v in idb.items() if v == g) for g in set(idb.values()))
    print(f"[{name}] keys equal={ok_keys} | per-event equal={sa == sb} | 共享分组 equal={groups_a == groups_b}")
    if sa != sb:
        for nid in sorted(ka & kb):
            if sa[nid] != sb[nid]:
                print("   差异 node:", nid, sa[nid][:3], "!=", sb[nid][:3])
    return sa == sb and ok_keys and groups_a == groups_b

if __name__ == '__main__':
    # --- 场景 1:别名拓扑 ---
    sys.path.insert(0, "docs/research/2026-09-04_tune-gates-multistream-adaptation/repro")
    import r1_alias as R
    from path2.dag.spec import PatternSpec
    from path2.dag.nodes import NodeSpec
    spec_alias = PatternSpec(pattern_id="t", nodes=(
        NodeSpec("n1", R.det, produces_stream="a"),
        NodeSpec("n2", R.det, produces_stream="a"),
        NodeSpec("nb", R.det, produces_stream="b", solve=False),
    ), edges=())
    ok1 = cmp("别名", spec_alias, None)

    # --- 场景 2:真实 bb_v1(多流 bo/pk + burst + tb) ---
    config.set_runtime_checks(True)
    import importlib, glob
    mod = importlib.import_module("path2_apps.bb_v1.dag_spec")
    P = importlib.import_module("path2_apps.bb_v1.params")
    from pathlib import Path
    ydir = Path("path2_apps/bb_v1")
    yml = sorted(ydir.glob("*.yaml")) + sorted(Path("configs/params").glob("bb_v1*.yaml"))
    print("candidate yaml:", [str(p) for p in yml])
    params = P.Params.from_yaml(yml[0]) if yml else P.Params()
    spec = mod.build_pattern(params)
    print("bb_v1 nodes:", [(n.node_id, n.consumes_stream, n.produces_stream, n.solve) for n in spec.nodes])
    oks = []
    for p in sorted(glob.glob("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/*.pkl"))[:5]:
        df = pd.read_pickle(p)
        oks.append(cmp(Path(p).stem, mod.build_pattern(params), df))
    print("ALL EQUAL:", ok1 and all(oks))
