# -*- coding: utf-8 -*-
"""草案 4.2 保留的那道「同流别名」禁令,在 4.1 按兄弟组重写之后是否还有必要?
合成一个别名拓扑(bo 与 bo2 同 detector、同 produces_stream='bo'),对拍引擎 run_streams。"""
import sys
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
import pandas as pd, study_io as S
from path2 import config
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms.throwback_v1 import ThrowbackDetectorV1
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge, Child
from path2.dag.spec import PatternSpec
from path2.dag import where as W
from path2.dag._graph import detector_topo_order
from path2.dag.engine import annotate_stream, run_streams
from path2.runner import run_bundle
from path2_web.data import slice_window
from path2_web.scan import _list_pkls

config.set_runtime_checks(True)
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py"); mod = S.import_app(study)
p = mod.Params.from_dict(S.base_snapshot(mod, study), strict=True)


def build(rh):
    det = BODetector(**{**p.bo_kwargs(), "min_relative_height": rh})
    nodes = (
        NodeSpec("bo", det, produces_stream="bo"),
        NodeSpec("bo2", det, produces_stream="bo", solve=False),      # ★ 同流别名
        NodeSpec("pk", det, produces_stream="pk", solve=False),
        NodeSpec("burst", BurstDetector(**p.burst_kwargs()), consumes_stream="bo",
                 children={"members": "bo"},
                 where=(("first_drought", W.attr("first_drought", ">=", 0)),)),
        NodeSpec("tb", ThrowbackDetectorV1(**p.throwback_kwargs()), consumes_stream="burst"),
    )
    edges = (TemporalEdge(Child("burst", "last_bo"), "tb", min_gap=1, max_gap=p.tb.max_span,
                          anchor_field="anchor_bo_id"),)
    return PatternSpec(pattern_id="alias_probe", nodes=nodes, edges=edges)


spec0 = build(0.2)
order = detector_topo_order(spec0.nodes)
children_of = {n.node_id: dict(n.children) for n in spec0.nodes if n.children}
groups = {}
for n in spec0.nodes:
    if n.detector is not None:
        groups.setdefault((id(n.detector), n.consumes_stream), []).append(n.node_id)
groups = {tuple(v): v for v in groups.values()}
gkey_of = {nid: gk for gk in groups for nid in gk}
print("兄弟组:", list(groups), "· detector_topo_order:", order)

win = slice_window(pd.read_pickle(next(iter(_list_pkls(str(REPO / "datasets/pkls"), r"^AAPL")))), "2023-01-01", "2026-03-01")
mism = 0
cache = {}
for rh in (0.1, 0.2, 0.3, 0.2, 0.1):      # 重复取值 → 走缓存命中路径
    spec = build(rh)
    by_id = {n.node_id: n for n in spec.nodes}
    streams, counts = {}, {}
    for nid in order:
        node = by_id[nid]
        if node.detector is None or nid in streams:
            continue
        gk = gkey_of[nid]
        ckey = (gk, rh)
        if ckey not in cache:
            src = (win,) if node.consumes_stream is None else (streams[node.consumes_stream], win)
            bundle = run_bundle(node.detector, *src)
            got = {}
            for sid in gk:
                got[sid] = bundle[by_id[sid].produces_stream]
                annotate_stream(counts, sid, got[sid], children_of)
            cache[ckey] = got
        streams.update(cache[ckey])
    ref = run_streams(spec, win)
    same_keys = set(ref) == set(streams)
    same_vals = all(tuple((e.start_idx, e.end_idx, e.node_id, e.instance_id) for e in ref[k])
                    == tuple((e.start_idx, e.end_idx, e.node_id, e.instance_id) for e in streams[k]) for k in ref)
    alias_ident = (streams["bo"] is streams["bo2"]) and (ref["bo"] is ref["bo2"])
    print(f"  rh={rh}: 键集同={same_keys} 值(含 node_id/instance_id)同={same_vals} 别名共用同一 list={alias_ident}"
          f" · bo2 事件的 node_id 例={ref['bo2'][0].node_id if ref['bo2'] else '空'}/{streams['bo2'][0].node_id if streams['bo2'] else '空'}")
    mism += int(not (same_keys and same_vals and alias_ident))
print("别名拓扑下 工具 vs 引擎 mismatch =", mism)
