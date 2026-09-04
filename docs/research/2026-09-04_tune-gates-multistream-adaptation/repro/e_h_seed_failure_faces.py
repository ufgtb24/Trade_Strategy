"""方案 H 对抗性复核:测 skeptic 没覆盖的失败面。
H = run_streams 的 `streams = {}` 改成 `streams = dict(seed or {})`,其余不动。"""
import glob, importlib
from pathlib import Path
import pandas as pd
from path2 import config
from path2.core import Event
from path2.dag.result import AnalysisResult
from path2.dag._graph import detector_topo_order
from path2.dag.engine import annotate_stream, _translate_refs, _check_children_declarations

config.set_runtime_checks(True)

def run_streams_seeded(spec, df, params=None, seed=None):
    """逐字复制 engine.run_streams,唯一改动:streams 初值。"""
    by_id = {n.node_id: n for n in spec.nodes}
    children_of = {n.node_id: dict(n.children) for n in spec.nodes if n.children}
    streams = dict(seed or {})                      # ★ H 的唯一改动
    materialized, counts, siblings, ncall = {}, {}, {}, [0]
    for n in spec.nodes:
        if n.detector is not None:
            siblings.setdefault((id(n.detector), n.consumes_stream), []).append(n)
    for nid in detector_topo_order(spec.nodes):
        node = by_id[nid]
        if node.detector is None or nid in streams:
            continue
        key = (id(node.detector), node.consumes_stream)
        if key not in materialized:
            from path2.runner import run_bundle
            ncall[0] += 1
            src = (df,) if node.consumes_stream is None else (streams[node.consumes_stream], df)
            materialized[key] = run_bundle(node.detector, *src)
        bundle = materialized[key]
        for sib in siblings[key]:
            if sib.node_id in streams:
                continue
            streams[sib.node_id] = bundle[sib.produces_stream]
            annotate_stream(counts, sib.node_id, streams[sib.node_id], children_of)
    _translate_refs(streams)
    _check_children_declarations(spec, streams)
    return streams, ncall[0]

mod = importlib.import_module("path2_apps.bb_v1.dag_spec")
P = importlib.import_module("path2_apps.bb_v1.params")
base = P.Params.from_yaml(Path("path2_apps/bb_v1/params.yaml"))
alt = P.Params.from_dict({**base.to_dict(),
      "bo": {**base.to_dict()["bo"], "min_relative_height": 0.35}}, strict=True)
df = pd.read_pickle(sorted(glob.glob("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/*.pkl"))[1])
def sig(evs): return [(e.node_id, e.instance_id, e.start_idx, e.end_idx, e.ph_ref_ids if 0 else e.ref_ids) for e in evs]

full_base, n_base = run_streams_seeded(mod.build_pattern(base), df)
full_alt,  _      = run_streams_seeded(mod.build_pattern(alt), df)
print(f"底座参数: bo={len(full_base['bo'])} pk={len(full_base['pk'])} · detect 调用={n_base}")
print(f"另一参数: bo={len(full_alt['bo'])}  (两组 bo 流不同? {sig(full_base['bo']) != sig(full_alt['bo'])})")

print("\n--- 面 1:半截 seed 的成本(只 seed bo、不 seed pk)---")
_, n_half = run_streams_seeded(mod.build_pattern(base), df, seed={"bo": full_base["bo"]})
_, n_grp  = run_streams_seeded(mod.build_pattern(base), df,
                               seed={"bo": full_base["bo"], "pk": full_base["pk"]})
print(f"无 seed detect 调用={n_base} · 整组 seed={n_grp} · 半截 seed={n_half}"
      f"  → 半截 seed 省下的 bo 趟数 = {n_base - n_half}")

print("\n--- 面 2:喂错参数的流(缓存键写错的模拟)---")
try:
    wrong, _ = run_streams_seeded(mod.build_pattern(base), df, seed={"bo": full_alt["bo"], "pk": full_alt["pk"]})
    diff = sig(wrong["burst"]) != sig(full_base["burst"])
    print(f"未抛任何错。下游 burst 与正确结果不同? {diff} "
          f"(burst: 错={len(wrong['burst'])} 对={len(full_base['burst'])})")
except Exception as e:
    print("抛错:", type(e).__name__, str(e)[:100])

print("\n--- 面 3:seed 里是未标注事件(有人直接喂 run_bundle 的输出)---")
from path2.runner import run_bundle
raw = run_bundle(mod.build_pattern(base).nodes[0].detector, df)
try:
    st, _ = run_streams_seeded(mod.build_pattern(base), df, seed={"bo": raw["bo"], "pk": raw["pk"]})
    print(f"未抛错。bo 事件 node_id={st['bo'][0].node_id} instance_id={st['bo'][0].instance_id}")
    try:
        AnalysisResult(events=tuple(e for s in st.values() for e in s), matches=(), spec=mod.build_pattern(base))
        print("  AnalysisResult 也未抛 → 未标注事件一路流到结果层")
    except Exception as e:
        print("  AnalysisResult 抛:", type(e).__name__, str(e)[:90])
except Exception as e:
    print("抛错:", type(e).__name__, str(e)[:140])

print("\n--- 面 4:seed 里有 spec 里不存在的 node_id ---")
try:
    st, _ = run_streams_seeded(mod.build_pattern(base), df, seed={"ghost": full_base["bo"]})
    print("未抛错。streams 多出幽灵键:", "ghost" in st)
except Exception as e:
    print("抛错:", type(e).__name__, str(e)[:140])
