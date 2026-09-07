# -*- coding: utf-8 -*-
"""D1 / D2 运行期 / D4 三问的实测。

D1: gkey 含 id() 时(即使 per-combo 重算 siblings 绕过 KeyError),stream_cache 的命中率。
D2: 把 pk 从 streams 里整个拿掉,solve/reify/row_columns 会不会炸。
D4: 红线对拍的比较键,能不能抓住「跳过 pk」与「兄弟不共享 detect」这两类差异。
"""
import sys
from pathlib import Path
REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
import pandas as pd, study_io as S
from multivar_core import (classify, influence_dims, apply_overrides, detection_combos,
                           row_columns, ScanConfig)
from path2 import config
from path2.dag._graph import detector_topo_order
from path2.dag._solve import compile_plan, solve
from path2.dag._reify import reify
from path2.dag.engine import annotate_stream, analyze
from path2.runner import run_bundle
from path2_web.data import slice_window
from path2_web.scan import _list_pkls

config.set_runtime_checks(True)
study = S.load_study(S.APPS_DIR / "bb_v1" / "study.py"); mod = S.import_app(study)
base0 = S.base_snapshot(mod, study)
cls = classify(mod, base0, study.SCAN_GRID, study.WHERE_LEVELS)
base = apply_overrides(base0, study.WIDE_OVERRIDES, {})
spec0 = mod.build_pattern(mod.Params.from_dict(base, strict=True))
infl = influence_dims(spec0, cls, study.SCAN_GRID)
order = detector_topo_order(spec0.nodes)
children_of = {n.node_id: dict(n.children) for n in spec0.nodes if n.children}
combos = detection_combos(study.SCAN_GRID, cls)
print("detection_combos =", len(combos), "(核对 architect-skeptic 的 9)")

def groups_of(spec):
    g = {}
    for n in spec.nodes:
        if n.detector is not None:
            g.setdefault((id(n.detector), n.consumes_stream), []).append(n.node_id)
    return {tuple(v): v for v in g.values()}

G0 = groups_of(spec0)
gkey_of = {nid: gk for gk in G0 for nid in gk}
infl_group = {gk: tuple(sorted(set().union(*(set(infl[n]) for n in gk)))) for gk in G0}


def stage1(win, cache, mode):
    """mode: 'nodeid'(修正版) | 'idkey'(D1:键含 id) | 'skip_pk'(D2) | 'naive'(D4:逐 node 各调一次 run_bundle)"""
    out = []
    stats = {"detect": 0, "hit": 0, "miss": 0}
    for combo in combos:
        p = mod.Params.from_dict(apply_overrides(base, {}, combo), strict=True)
        spec = mod.build_pattern(p)
        by_id = {n.node_id: n for n in spec.nodes}
        Gc = groups_of(spec)                       # per-combo 重算(绕过草案层一的 KeyError)
        gof = {nid: gk for gk in Gc for nid in gk}
        idkey_of = {}
        for n in spec.nodes:
            if n.detector is not None:
                idkey_of[n.node_id] = (id(n.detector), n.consumes_stream)
        streams, counts = {}, {}
        for nid in order:
            node = by_id[nid]
            if node.detector is None or nid in streams:
                continue
            if mode == "skip_pk" and nid == "pk":
                continue
            gk = gof[nid]
            if mode == "naive":
                ck = (nid, tuple(combo[d] for d in infl[nid]))
                if ck not in cache:
                    src = (win,) if node.consumes_stream is None else (streams[node.consumes_stream], win)
                    evs = run_bundle(node.detector, *src)[node.produces_stream]
                    stats["detect"] += 1; stats["miss"] += 1
                    annotate_stream(counts, nid, evs, children_of)
                    cache[ck] = evs
                else:
                    stats["hit"] += 1
                streams[nid] = cache[ck]
                continue
            if mode == "skip_pk":
                gk = tuple(x for x in gk if x != "pk")
            key_head = idkey_of[nid] if mode == "idkey" else gk
            ck = (key_head, tuple(combo[d] for d in infl_group[gkey_of[nid]]))
            if ck not in cache:
                stats["miss"] += 1
                src = (win,) if node.consumes_stream is None else (streams[node.consumes_stream], win)
                bundle = run_bundle(node.detector, *src); stats["detect"] += 1
                got = {}
                for sid in gk:
                    got[sid] = bundle[by_id[sid].produces_stream]
                    annotate_stream(counts, sid, got[sid], children_of)
                cache[ck] = got
            else:
                stats["hit"] += 1
            streams.update(cache[ck])
        out.append((combo, spec, streams))
    return out, stats


def mkeys(spec, streams):
    plan = compile_plan(spec)
    return sorted(tuple((nid, ev.start_idx, ev.end_idx) for nid, ev in sorted(reify(sol, streams, plan).node_index.items()))
                  for sol in solve(plan, streams))


pkls = list(_list_pkls(str(REPO / "datasets/pkls"), r"^A[A-C]"))
# ---------- D1 ----------
win0 = None
for p_ in pkls:
    w = slice_window(pd.read_pickle(p_), "2023-01-01", "2026-03-01")
    if len(w) >= 300:
        win0 = w; break
for mode in ("nodeid", "idkey"):
    c = {}
    _, st = stage1(win0, c, mode)
    print(f"D1 mode={mode:7s}: detect={st['detect']} 缓存命中={st['hit']} 未命中={st['miss']} "
          f"命中率={st['hit']/(st['hit']+st['miss']):.1%} · 缓存条目={len(c)}")

# ---------- D2 运行期 + D4 ----------
n = d2_break = d4_skip_diff = d4_naive_diff = 0
d2_cols_ok = None
for p_ in pkls[:40]:
    win = slice_window(pd.read_pickle(p_), "2023-01-01", "2026-03-01")
    if len(win) < 300:
        continue
    n += 1
    ref, _ = stage1(win, {}, "nodeid")
    sk, _ = stage1(win, {}, "skip_pk")
    nv, _ = stage1(win, {}, "naive")
    for (cb, spec, s_ref), (_, _, s_sk), (_, _, s_nv) in zip(ref, sk, nv):
        try:
            k_ref, k_sk, k_nv = mkeys(spec, s_ref), mkeys(spec, s_sk), mkeys(spec, s_nv)
        except Exception as ex:
            d2_break += 1
            print("  D2 solve/reify 抛:", type(ex).__name__, ex); break
        d4_skip_diff += int(k_ref != k_sk)
        d4_naive_diff += int(k_ref != k_nv)
    if d2_cols_ok is None:
        cfg = ScanConfig(module_path=study.APP_MODULE, base_dict=base0, wide_overrides=study.WIDE_OVERRIDES,
                         scan_grid=study.SCAN_GRID, where_levels=study.WHERE_LEVELS, end_node="tb",
                         label_horizon=40, fp_k=5.0)
        cols = row_columns(cfg, cls, spec0)
        d2_cols_ok = ("pk.start" not in cols, cols)
print(f"D2 运行期: {n} 股 × {len(combos)} 格,把 pk 从 streams 拿掉后 solve/reify 抛异常次数 = {d2_break}")
print(f"D2 row_columns 是否本来就不含 pk 列: {d2_cols_ok[0]} · 列 = {d2_cols_ok[1]}")
print(f"D4: 红线比较键(node_index spans)在 {n*len(combos)} 次比较里——"
      f"「跳过 pk」被抓到 {d4_skip_diff} 次 · 「逐 node 各调一次 run_bundle」被抓到 {d4_naive_diff} 次")
