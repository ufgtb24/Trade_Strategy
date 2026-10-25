"""补测(截到 2025-12-31 的副本):

1. 冷 / 热:新开进程第一次算(含 import)与第二次算,训练段全长,app 与所有 detector 分开各一个进程。
2. 批量:一个进程依次算 N 只股票(N = 20 / 50 / 200,训练段全长),分「拿 app 对标注」
   (读 K 线 + app 计算 + node 诊断 + 挂闸失败收集再算一遍)和「所有 detector」两种。
3. 显示密度:看图范围内(2025 全年约 250 根;以及截到年末的 200 根)每种事件几个、要几条泳道,
   所有 detector 对比只画 bb_v1。
4. 参数举例:挑两只股票,列 2025 年里默认参数 / bb_v1 / bottom_burst 各自画出的 bo 与 tb 日期。
用法:uv run python batch_and_density.py [cold|batch|density|example [代码...]](不给 = 全跑)。
"""
from __future__ import annotations

import dataclasses
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

SNAP = ROOT / "datasets/pkls_until_20251231"
TRAIN = ("2021-10-08", "2025-12-31")
OUT = HERE / "out_batch_density.json"


def sample_syms(n, seed=7):
    from chart_workflow.loader import load_bars
    random.seed(seed)
    syms = sorted(p.stem for p in SNAP.glob("*.pkl"))
    random.shuffle(syms)
    out = []
    for s in syms:
        if len(out) >= n:
            break
        if len(load_bars(SNAP, s, "2025-12-31")) >= 1000:
            out.append(s)
    return out


# ── 1. 冷 / 热 ──────────────────────────────────────────────
COLD_CHILD = r'''
import sys, time, json
t0 = time.perf_counter()
sys.path.insert(0, {root!r}); sys.path.insert(0, {here!r})
from chart_workflow.loader import load_bars
from path2_web.data import slice_window
from path2_web.serialize import serialize_analysis
if {what!r} == "app":
    from path2_apps.bb_v1 import dag_spec as m
    def go(win): return serialize_analysis(m.analyze(win, m.load_params()))
else:
    from bench_detectors import all_atoms_spec
    from path2.dag.engine import analyze
    def go(win): return serialize_analysis(analyze(all_atoms_spec(), win))
t_imp = time.perf_counter() - t0
ts = []
for _ in range(2):
    t1 = time.perf_counter()
    win = slice_window(load_bars({snap!r}, {sym!r}, "2025-12-31"), "2021-10-08", "2025-12-31")
    go(win)
    ts.append(time.perf_counter() - t1)
print(json.dumps({{"import_ms": t_imp * 1000, "first_ms": ts[0] * 1000, "second_ms": ts[1] * 1000}}))
'''


def cold(syms):
    rows = []
    for sym in syms:
        for what in ("app", "all"):
            code = COLD_CHILD.format(root=str(ROOT), here=str(HERE), what=what, snap=str(SNAP), sym=sym)
            t0 = time.perf_counter()
            r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
            wall = (time.perf_counter() - t0) * 1000
            d = json.loads(r.stdout.strip().splitlines()[-1])
            d.update(sym=sym, what=what, process_wall_ms=wall)
            rows.append(d)
            print(f"冷热 {sym:6s} {what:3s} 进程总 {wall:6.0f}ms  import {d['import_ms']:6.0f}ms  "
                  f"第一次 {d['first_ms']:6.1f}ms  第二次 {d['second_ms']:6.1f}ms")
    return rows


# ── 2. 批量 ─────────────────────────────────────────────────
def batch(syms_all):
    from bench_detectors import all_atoms_spec
    from chart_workflow.loader import load_bars
    from path2.dag import diagnose as dag_diagnose
    from path2.dag.engine import analyze as engine_analyze
    from path2_apps.bb_v1 import dag_spec as bb
    from path2_web.data import slice_window
    from path2_web.gate_collector import attach_and_collect, detach
    from path2_web.serialize import serialize_analysis
    p = bb.load_params()
    spec_all = all_atoms_spec()
    # 预热
    w = slice_window(load_bars(SNAP, syms_all[0], "2025-12-31"), *TRAIN)
    bb.analyze(w, p); engine_analyze(spec_all, w)

    def app_one(sym):
        win = slice_window(load_bars(SNAP, sym, "2025-12-31"), *TRAIN)
        spec = bb.build_pattern(p)
        res = engine_analyze(spec, win, p)
        serialize_analysis(res)
        dag_diagnose(spec, win, None)
        col = attach_and_collect(spec)
        try:
            r2 = engine_analyze(spec, win, None)
        finally:
            detach(spec)
        dataclasses.replace(r2, gate_failures=col.snapshot())

    def all_one(sym):
        win = slice_window(load_bars(SNAP, sym, "2025-12-31"), *TRAIN)
        serialize_analysis(engine_analyze(spec_all, win))

    rows = {}
    for n in (20, 50, 200):
        for name, fn in (("拿 app 对标注", app_one), ("所有 detector", all_one)):
            t0 = time.perf_counter()
            for s in syms_all[:n]:
                fn(s)
            wall = time.perf_counter() - t0
            rows[f"{name}@{n}"] = wall
            print(f"批量 {name:10s} {n:4d} 只: {wall:6.2f}s")
    return rows


# ── 3. 显示密度 ─────────────────────────────────────────────
def lanes(spans):
    """重叠事件最少要几条泳道 = 同一根 K 线上最多同时有几个事件。"""
    pts = sorted([(s, 0) for s, e in spans] + [(e, 1) for s, e in spans])
    cur = best = 0
    for _, kind in pts:
        cur += 1 if kind == 0 else -1
        best = max(best, cur)
    return best


def density(syms):
    import pandas as pd
    from bench_detectors import all_atoms_spec
    from chart_workflow.loader import load_bars
    from path2.dag.engine import analyze as engine_analyze
    from path2_apps.bb_v1 import dag_spec as bb
    from path2_web.data import slice_window
    p = bb.load_params()
    spec_all, spec_bb = all_atoms_spec(), bb.build_pattern(p)
    stats = {}
    for sym in syms:
        win = slice_window(load_bars(SNAP, sym, "2025-12-31"), "2024-10-01", "2025-12-31")
        hi = len(win) - 1
        views = {"2025全年": int(win["date"].searchsorted(pd.Timestamp("2025-01-01"))), "末200根": hi - 199}
        res_all = engine_analyze(spec_all, win)
        res_bb = engine_analyze(spec_bb, win, p)
        matched = {id(e) for m in res_bb.matches for e in m.node_index.values()}
        for m in res_bb.matches:          # burst 的成员 bo 也算进 match
            for b in getattr(m.node_index.get("burst"), "members", ()):
                matched.add(id(b))

        def collect(res, tag, only=None):
            by_node = {}
            evs = list(res.events)
            for e in res.events:        # 容器里的子事件(企稳段)也要画
                for slot in e.child_slots().values():
                    for c in (slot if isinstance(slot, tuple) else (slot,)):
                        if c.node_id and c.node_id not in ("bo",):
                            evs.append(c)
            seen = set()
            for e in evs:
                if id(e) in seen or (only is not None and id(e) not in only):
                    continue
                seen.add(id(e))
                by_node.setdefault(e.node_id, []).append((e.start_idx, e.end_idx))
            for vname, lo in views.items():
                n_ev = n_lane = n_kind = 0
                for nid, sp in by_node.items():
                    vis = [(max(s, lo), min(e, hi)) for s, e in sp if e >= lo and s <= hi]
                    if not vis:
                        continue
                    n_kind += 1
                    n_ev += len(vis)
                    lz = lanes(vis)
                    n_lane += lz
                    stats.setdefault((tag, vname, nid), {"n": [], "lanes": []})
                    stats[(tag, vname, nid)]["n"].append(len(vis))
                    stats[(tag, vname, nid)]["lanes"].append(lz)
                for k, v in (("事件", n_ev), ("种类", n_kind), ("泳道", n_lane)):
                    stats.setdefault((tag, vname, "合计" + k), {"n": [], "lanes": []})["n"].append(v)

        collect(res_all, "所有detector")
        collect(res_bb, "bb_v1全部检测到的")
        collect(res_bb, "bb_v1只画match", only=matched)
    out = {}
    print("显示密度(每只股票一个数,下面是中位 / 90 分位 / 最多;没出现该种事件的股票不计入该行)")
    for (tag, vname, nid), v in sorted(stats.items()):
        xs = sorted(v["n"])
        q90 = xs[int(0.9 * (len(xs) - 1))]
        line = f"{tag:14s} {vname:6s} {nid:12s} 出现在 {len(xs):3d} 只 个数 {statistics.median(xs):5.1f}/{q90}/{max(xs)}"
        if v["lanes"]:
            ls = sorted(v["lanes"])
            line += f"  泳道 {statistics.median(ls):.0f}/{ls[int(0.9 * (len(ls) - 1))]}/{max(ls)}"
        print(line)
        out[f"{tag}|{vname}|{nid}"] = {"stocks": len(xs), "median": statistics.median(xs), "p90": q90,
                                       "max": max(xs), "lanes": v["lanes"] and {
                                           "median": statistics.median(v["lanes"]), "max": max(v["lanes"])}}
    return out


# ── 4. 参数举例 ─────────────────────────────────────────────
def example(syms):
    import pandas as pd
    from bench_detectors import all_atoms_spec
    from chart_workflow.loader import load_bars
    from path2.dag.engine import run_streams
    from path2_apps.bb_v1 import dag_spec as bb
    from path2_apps.bottom_burst import dag_spec as bt
    from path2_web.data import slice_window
    specs = {"默认参数": all_atoms_spec(), "bb_v1": bb.build_pattern(bb.load_params()),
             "bottom_burst": bt.build_pattern(bt.load_params())}
    tbnode = {"默认参数": "tb_v1", "bb_v1": "tb", "bottom_burst": "tb"}
    out = []
    for sym in syms:
        win = slice_window(load_bars(SNAP, sym, "2025-12-31"), "2024-10-01", "2025-12-31")
        lo = int(win["date"].searchsorted(pd.Timestamp("2025-01-01")))
        d = {"sym": sym}
        for name, spec in specs.items():
            st = run_streams(spec, win)
            day = lambda i: str(win["date"].iat[i].date())[5:]   # noqa: E731
            d[name] = {"bo": [day(e.start_idx) for e in st["bo"] if e.start_idx >= lo],
                       "tb": [f"{day(e.start_idx)}~{day(e.end_idx)}" for e in st[tbnode[name]]
                              if e.start_idx >= lo]}
        out.append(d)
        print(f"== {sym}(2025 年,月-日)")
        for name in specs:
            print(f"  {name:12s} bo {len(d[name]['bo']):2d} 个: {' '.join(d[name]['bo'])}")
        for name in specs:
            print(f"  {name:12s} tb {len(d[name]['tb']):2d} 个: {' '.join(d[name]['tb'])}")
    return out


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    res = json.loads(OUT.read_text()) if OUT.exists() else {}
    syms = sample_syms(200)
    if what in ("all", "cold"):
        res["cold"] = cold(syms[:3])
    if what in ("all", "batch"):
        res["batch"] = batch(syms)
    if what in ("all", "density"):
        res["density"] = density(syms)
    if what in ("all", "example"):
        res["example"] = example(sys.argv[2:] or ["EL"])
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
