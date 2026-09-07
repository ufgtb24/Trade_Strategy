# -*- coding: utf-8 -*-
"""修正版反转循环阶段-1(按兄弟组、键用 node_id 而非 id(detector))vs 引擎 run_streams/analyze 的逐格对拍。

只验被改动的那一段(产流 + 标注),label/fr 部分本方案不动故不重复验证。
比较两层:
  L1 流层:每个 node 的事件 (start,end,instance_id) 序列,含 pk(引擎口径 vs 工具口径)
  L2 match 层:analyze 的 match node_index spans 多重集
"""
import sys, re
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))

import pandas as pd
import study_io as S
from multivar_core import classify, influence_dims, apply_overrides, detection_combos
from path2 import config
from path2.dag._graph import detector_topo_order
from path2.dag._solve import compile_plan, solve
from path2.dag._reify import reify
from path2.dag.engine import analyze, annotate_stream, run_streams
from path2.runner import run_bundle
from path2_web.data import slice_window
from path2_web.scan import _list_pkls

config.set_runtime_checks(True)
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py")
mod = S.import_app(study)
base0 = S.base_snapshot(mod, study)
cls = classify(mod, base0, study.SCAN_GRID, study.WHERE_LEVELS)
base = apply_overrides(base0, study.WIDE_OVERRIDES, {})
spec0 = mod.build_pattern(mod.Params.from_dict(base, strict=True))
infl = influence_dims(spec0, cls, study.SCAN_GRID)
order = detector_topo_order(spec0.nodes)
children_of = {n.node_id: dict(n.children) for n in spec0.nodes if n.children}

# ---- 兄弟组:分组由 spec0 推(与 order/infl/children_of 同源),键取 node_id 元组 ----
groups, gkey_of = {}, {}
for n in spec0.nodes:
    if n.detector is None:
        continue
    groups.setdefault((id(n.detector), n.consumes_stream), []).append(n.node_id)
groups = {tuple(v): v for v in groups.values()}          # 键换成 node_id 元组(跨 spec 稳定)
for gk in groups:
    for nid in gk:
        gkey_of[nid] = gk
infl_group = {gk: tuple(sorted(set().union(*(set(infl[nid]) for nid in gk)))) for gk in groups}
print("兄弟组(node_id 键):", list(groups), "\n组影响集:", {k: [S.dotted(d) for d in v] for k, v in infl_group.items()})

combos = detection_combos(study.SCAN_GRID, cls)


def tool_streams(win, stream_cache):
    """修正版阶段-1(逐 combo 调用,stream_cache 跨 combo 共享)。"""
    out_per_combo = []
    n_detect = 0
    for combo in combos:
        p = mod.Params.from_dict(apply_overrides(base, {}, combo), strict=True)
        spec = mod.build_pattern(p)
        by_id = {n.node_id: n for n in spec.nodes}
        # 结构漂移守卫:本 combo 的兄弟划分必须与 spec0 一致
        g_now = {}
        for n in spec.nodes:
            if n.detector is not None:
                g_now.setdefault((id(n.detector), n.consumes_stream), []).append(n.node_id)
        assert {tuple(v) for v in g_now.values()} == set(groups), "兄弟划分随 combo 漂移"
        streams, counts = {}, {}
        for nid in order:
            node = by_id[nid]
            if node.detector is None or nid in streams:
                continue
            gk = gkey_of[nid]
            ckey = (gk, tuple(combo[d] for d in infl_group[gk]))
            if ckey not in stream_cache:
                src = (win,) if node.consumes_stream is None else (streams[node.consumes_stream], win)
                bundle = run_bundle(node.detector, *src)
                n_detect += 1
                got = {}
                for sib_id in gk:                       # 声明序 = spec0.nodes 序
                    sib = by_id[sib_id]
                    got[sib_id] = bundle[sib.produces_stream]
                    annotate_stream(counts, sib_id, got[sib_id], children_of)
                stream_cache[ckey] = got
            streams.update(stream_cache[ckey])
        out_per_combo.append((combo, spec, streams))
    return out_per_combo, n_detect


def spans(evs):
    return tuple((e.start_idx, e.end_idx, e.instance_id) for e in evs)


def match_keys(spec, streams):
    plan = compile_plan(spec)
    ks = []
    for sol in solve(plan, streams):
        m = reify(sol, streams, plan)
        ks.append(tuple((nid, ev.start_idx, ev.end_idx, ev.instance_id) for nid, ev in sorted(m.node_index.items())))
    return sorted(ks)


s, e = pd.to_datetime("2024-01-01"), pd.to_datetime("2026-01-01")
bs, be = "2023-01-01", "2026-03-01"
n_stock = l1_mism = l2_mism = n_cmp = n_nonempty = 0
tot_detect = 0
for pk in list(_list_pkls(str(REPO / "datasets/pkls"), r"^A[A-C]"))[:40]:
    win = slice_window(pd.read_pickle(pk), bs, be)
    if len(win) < 300:
        continue
    n_stock += 1
    cache = {}
    per_combo, nd = tool_streams(win, cache)
    tot_detect += nd
    for combo, spec, streams in per_combo:
        ref_streams = run_streams(spec, win)
        n_cmp += 1
        if {k: spans(v) for k, v in ref_streams.items()} != {k: spans(v) for k, v in streams.items()}:
            l1_mism += 1
            print("L1 MISMATCH", pk.stem, combo)
        ref_m = sorted(tuple((nid, ev.start_idx, ev.end_idx, ev.instance_id) for nid, ev in sorted(m.node_index.items()))
                       for m in analyze(spec, win).matches)
        got_m = match_keys(spec, streams)
        if ref_m:
            n_nonempty += 1
        if ref_m != got_m:
            l2_mism += 1
            print("L2 MISMATCH", pk.stem, combo, len(ref_m), len(got_m))

print(f"\n股 {n_stock} × 格 {len(combos)} = 比较 {n_cmp}(非空 match 的比较 {n_nonempty})")
print(f"L1 流层 mismatch = {l1_mism} · L2 match 层 mismatch = {l2_mism}")
print(f"工具侧 detect 调用总数 {tot_detect}(逐格重跑口径 = {n_stock} 股 × {len(combos)} 格 × 3 组 = {n_stock*len(combos)*3})")
