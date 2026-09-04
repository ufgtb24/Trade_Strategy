# -*- coding: utf-8 -*-
"""验证关卡代价:修好之后 test_multivar_equiv 会第一次真的跑起来,量一下它的量级。
用该测试的 SCAN_GRID(6 维 1024 combo)在单股上跑修正版阶段-1 + solve + reify(不含 label)。"""
import sys, time
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
import pandas as pd, study_io as S
from multivar_core import classify, influence_dims, apply_overrides, detection_combos
from path2 import config
from path2.dag._graph import detector_topo_order
from path2.dag._solve import compile_plan, solve
from path2.dag._reify import reify
from path2.dag.engine import annotate_stream
from path2.runner import run_bundle
from path2_web.data import slice_window
from path2_web.scan import _list_pkls

config.set_runtime_checks(True)
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py"); mod = S.import_app(study)
SCAN_GRID = {("bo", "min_relative_height"): [0.15, 0.2], ("bo", "exceed_threshold"): [0.003, 0.01],
             ("burst", "gap_max"): [4, 8, 12, 20], ("burst", "min_bos"): [1, 2, 3, 4],
             ("tb", "stop_confirm_bars"): [1, 2, 3, 4], ("tb", "max_rise_k"): [1.0, 1.5, 2.5, 4.0]}
WHERE_LEVELS = {("burst", "first_drought_min"): [0, 20], ("burst", "distinct_pk_min"): [1, 3],
                ("burst", "vol_spike_min"): [0, 10], ("burst", "peak_age_min"): [0, 125],
                ("tb", "max_day_drop_pct"): [None, 0.2]}
WIDE = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0, "peak_age_min": 0},
        "tb": {"max_day_drop_pct": None}}
base0 = S.base_snapshot(mod, study)
cls = classify(mod, base0, SCAN_GRID, WHERE_LEVELS)
print("kinds:", {S.dotted(d): k for d, k in cls.kinds.items()})
base = apply_overrides(base0, WIDE, {})
spec0 = mod.build_pattern(mod.Params.from_dict(base, strict=True))
infl = influence_dims(spec0, cls, SCAN_GRID)
order = detector_topo_order(spec0.nodes)
children_of = {n.node_id: dict(n.children) for n in spec0.nodes if n.children}
groups = {}
for n in spec0.nodes:
    if n.detector is not None:
        groups.setdefault((id(n.detector), n.consumes_stream), []).append(n.node_id)
groups = {tuple(v): v for v in groups.values()}
gkey_of = {nid: gk for gk in groups for nid in gk}
infl_group = {gk: tuple(sorted(set().union(*(set(infl[n]) for n in gk)))) for gk in groups}
combos = detection_combos(SCAN_GRID, cls)
print("combos:", len(combos), "· 各组影响集大小:",
      {gk: len(set(tuple(c[d] for d in infl_group[gk]) for c in combos)) for gk in groups})

pkls = list(_list_pkls(str(REPO / "datasets/pkls"), r"^A[A-C]"))
done = 0
t0 = time.time()
for pkl in pkls:
    win = slice_window(pd.read_pickle(pkl), "2023-01-01", "2026-03-01")
    if len(win) < 300:
        continue
    cache = {}; nd = 0; nm = 0
    ts = time.time()
    for combo in combos:
        p = mod.Params.from_dict(apply_overrides(base, {}, combo), strict=True)
        spec = mod.build_pattern(p)
        by_id = {n.node_id: n for n in spec.nodes}
        streams, counts = {}, {}
        for nid in order:
            node = by_id[nid]
            if node.detector is None or nid in streams:
                continue
            gk = gkey_of[nid]
            ckey = (gk, tuple(combo[d] for d in infl_group[gk]))
            if ckey not in cache:
                src = (win,) if node.consumes_stream is None else (streams[node.consumes_stream], win)
                bundle = run_bundle(node.detector, *src); nd += 1
                got = {}
                for sid in gk:
                    got[sid] = bundle[by_id[sid].produces_stream]
                    annotate_stream(counts, sid, got[sid], children_of)
                cache[ckey] = got
            streams.update(cache[ckey])
        plan = compile_plan(spec)
        for sol in solve(plan, streams):
            reify(sol, streams, plan); nm += 1
    print(f"  {pkl.stem}: {time.time()-ts:.1f}s · detect {nd} · match {nm}")
    done += 1
    if done == 3:
        break
print(f"3 只股合计 {time.time()-t0:.1f}s → 全 ^A[A-C] 池(测试实际约 104 只)外推 "
      f"{(time.time()-t0)/3*104/60:.1f} 分钟(不含 label 计算,单进程)")
