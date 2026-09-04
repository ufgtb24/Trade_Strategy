# -*- coding: utf-8 -*-
"""方案 H 的**工具侧**可行性复核(对抗性):按 scan_one_stock 的真实控制流跑 H。

问 1: 缓存按 node 粒度 + 按 node 传 seed,实际控制流里会不会出现半截 seed(只 seed bo 不 seed pk)?
问 2: H 下每 combo 的 streams 是否 == 无 seed 全量重跑(比较面含 ref_ids)?
问 4: 陈旧/越界 seed 键(nid 不在当前 spec)会怎样——响亮还是静默?
"""
import sys, time
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
sys.path.insert(0, str(REPO / "docs/research/2026-09-04_tune-gates-multistream-adaptation/repro"))
import pandas as pd, study_io as S
from h_seed_streams import run_streams_seeded
from multivar_core import classify, influence_dims, apply_overrides, detection_combos
from path2 import config
from path2.dag.engine import run_streams
from path2_web.data import slice_window
from path2_web.scan import _list_pkls

config.set_runtime_checks(True)          # 与 multivar_scan.py:39 生产口径一致
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py"); mod = S.import_app(study)
base0 = S.base_snapshot(mod, study)
cls = classify(mod, base0, study.SCAN_GRID, study.WHERE_LEVELS)
base = apply_overrides(base0, study.WIDE_OVERRIDES, {})
spec0 = mod.build_pattern(mod.Params.from_dict(base, strict=True))
infl = influence_dims(spec0, cls, study.SCAN_GRID)      # H 下工具仍需要的唯一 spec0 派生物
combos = detection_combos(study.SCAN_GRID, cls)
SIB_GROUPS = [{"bo", "pk"}, {"burst"}, {"tb"}]           # 引擎口径的兄弟组(仅供断言用)


def sig(streams):
    return {k: [(e.node_id, e.instance_id, e.start_idx, e.end_idx, e.ref_ids) for e in v]
            for k, v in streams.items()}


pkls = [p for p in _list_pkls(str(REPO / "datasets/pkls"), r"^A[A-C]")]
n = half_seed = mism = 0
detect_calls_total = 0
t_h = 0.0
for p_ in pkls[:20]:
    win = slice_window(pd.read_pickle(p_), "2023-01-01", "2026-03-01")
    if len(win) < 300:
        continue
    n += 1
    cache = {}
    for combo in combos:
        p = mod.Params.from_dict(apply_overrides(base, {}, combo), strict=True)
        spec = mod.build_pattern(p)
        # ---- H 的工具侧控制流:按 node 语义键组 seed ----
        keys = {nid: (nid, tuple(combo[d] for d in infl[nid])) for nid in infl}
        seed = {nid: cache[k] for nid, k in keys.items() if k in cache}
        # 问 1:seed 集必须是若干完整兄弟组的并集
        for g in SIB_GROUPS:
            inter = g & set(seed)
            if inter and inter != g:
                half_seed += 1
        t0 = time.perf_counter()
        got = run_streams_seeded(spec, win, seed=seed)
        t_h += time.perf_counter() - t0
        for nid, evs in got.items():                      # 写回:store everything
            cache[keys[nid]] = evs
        # 问 2:与无 seed 全量重跑逐字比(含 ref_ids)
        ref = run_streams(spec, win)
        if sig(ref) != sig(got):
            mism += 1
            print("  MISMATCH", p_.stem, combo)
print(f"问1 半截 seed 出现次数 = {half_seed}(共 {n} 股 × {len(combos)} 格 × {len(SIB_GROUPS)} 组 = {n*len(combos)*len(SIB_GROUPS)} 次检查)")
print(f"问2 H 结果 vs 无 seed 全量重跑(比较面含 ref_ids)mismatch = {mism} / {n*len(combos)}")
print(f"    H 侧 run_streams_seeded 累计 {t_h:.2f}s / {n} 股 = {t_h/n*1000:.1f} ms/股(9 格,RUNTIME_CHECKS=True)")

# ---- 问 4:陈旧 / 越界 seed 键 ----
win = slice_window(pd.read_pickle(pkls[0]), "2023-01-01", "2026-03-01")
spec = mod.build_pattern(mod.Params.from_dict(base, strict=True))
full = run_streams(spec, win)
print("\n问4 越界 seed 键(nid 不在当前 spec)：")
for label, bad in (("多一个不存在的 nid", {**full, "ghost": []}),
                   ("只 seed bo 不 seed pk(半截)", {"bo": full["bo"]})):
    try:
        out = run_streams_seeded(spec, win, seed=bad)
        extra = set(out) - {n_.node_id for n_ in spec.nodes}
        same = sig({k: v for k, v in out.items() if k in full}) == sig(full)
        print(f"  {label}: 未抛异常 · 多出的键={sorted(extra)} · 与全量重跑同={same}")
    except Exception as ex:
        print(f"  {label}: 抛 {type(ex).__name__}: {str(ex)[:120]}")
