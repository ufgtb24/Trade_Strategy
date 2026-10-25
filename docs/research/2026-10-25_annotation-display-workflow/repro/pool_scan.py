"""全池实测(截到 2025-12-31 的副本,训练段 2021-10-08..2025-12-31,26 进程):

A. 网页「扫描」原样跑一遍 bb_v1、bottom_burst(path2_web.scan.run_scan_multi,含收益标注与统计;
   结果文件写到 scratchpad,不进 outputs/)——全池扫一遍 app 要多久。
B. 全池预算所有现成 detector(与 bench_detectors 同一份接线清单)——要多久、存下来多大。
C. 改一道 where(或一个 detector 参数)松 / 紧一档,全池买点增减几个:
   买点口径 =(股票, 买点 node 事件起始日)去重(买点 node 取 eval_meta:bb_v1 是 tb,bottom_burst 是企稳段);过滤同网页扫描(成交量预筛、价格区间);
   只算起始日落在训练段内的。detector 输出确定,同一只股票的各档在同一进程里依次算。
输出 repro/out_pool.json + 终端汇总。
"""
from __future__ import annotations

import gzip
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import pandas as pd  # noqa: E402

SNAP = ROOT / "datasets/pkls_until_20251231"
SCRATCH = Path(os.environ.get("BENCH_SCRATCH", "/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/"
                              "574f78d0-24a3-4073-a533-4e7a208fa895/scratchpad"))
START, END = "2021-10-08", "2025-12-31"
WORKERS = 26
PRICE_MIN, PRICE_MAX, VOLUME_MIN = 0.5, 30, 10000   # 与 configs/path2_web.yaml 的 scan 段一致

# C 段的改动:(app, 名字, 段, 字段, 新值)
VARIANTS = [
    ("bb_v1", "distinct_pk 3→2", "burst", "distinct_pk_min", 2),
    ("bb_v1", "distinct_pk 3→4", "burst", "distinct_pk_min", 4),
    ("bb_v1", "vol_spike 3→2", "burst", "vol_spike_min", 2),
    ("bb_v1", "vol_spike 3→4", "burst", "vol_spike_min", 4),
    ("bb_v1", "first_drought 40→30", "burst", "first_drought_min", 30),
    ("bb_v1", "first_drought 40→50", "burst", "first_drought_min", 50),
    ("bb_v1", "day_drop 0.20→0.15", "tb", "max_day_drop_pct", 0.15),
    ("bb_v1", "day_drop 0.20→0.25", "tb", "max_day_drop_pct", 0.25),
    ("bb_v1", "bo 突破门槛 0.0075→0.005(detector 参数)", "bo", "exceed_threshold", 0.005),
    ("bb_v1", "bo 突破门槛 0.0075→0.01(detector 参数)", "bo", "exceed_threshold", 0.01),
    ("bottom_burst", "vol_spike 10→8", "burst", "vol_spike_min", 8),
    ("bottom_burst", "vol_spike 10→12", "burst", "vol_spike_min", 12),
]


def _mod(app):
    import importlib
    return importlib.import_module(f"path2_apps.{app}.dag_spec")


def _buy_keys(res, win, end_node, sym, lo_ts, hi_ts):
    """match 的买点 node 事件(bottom_burst 是企稳段,可能多个)起始日 → (股票, 日期) 集合。"""
    from path2.eval import _resolve_end_events
    keys = set()
    for m in res.matches:
        for ev in _resolve_end_events(m, end_node):
            d = win["date"].iat[ev.start_idx]
            c = win["close"].iat[ev.start_idx]
            if lo_ts <= d <= hi_ts and PRICE_MIN <= c <= PRICE_MAX:
                keys.add((sym, str(d.date())))
    return keys


def work_variants(sym):
    """一只股票:各 app 基线 + 各改动的买点集合。"""
    from chart_workflow.loader import load_bars
    from path2_web.data import slice_window
    df = load_bars(SNAP, sym, END)
    win = slice_window(df, START, END)
    lo_ts, hi_ts = pd.Timestamp(START), pd.Timestamp(END)
    if len(win) == 0 or win["volume"].mean() <= VOLUME_MIN:
        return sym, None
    out = {}
    for app in ("bb_v1", "bottom_burst"):
        mod = _mod(app)
        p = mod.load_params()
        out[f"{app}|基线"] = sorted(_buy_keys(mod.analyze(win, p), win, mod.eval_meta(p)["end_node"],
                                              sym, lo_ts, hi_ts))
    for app, name, sec, field, val in VARIANTS:
        mod = _mod(app)
        d = mod.load_params().to_dict()
        d[sec][field] = val
        p = mod.Params.from_dict(d)
        out[f"{app}|{name}"] = sorted(_buy_keys(mod.analyze(win, p), win, mod.eval_meta(p)["end_node"],
                                                sym, lo_ts, hi_ts))
    return sym, out


def work_all_atoms(sym):
    """一只股票:所有现成 detector 走引擎 + 序列化,返回 (耗时毫秒, JSON 字节, gzip 字节)。"""
    from bench_detectors import all_atoms_spec
    from chart_workflow.loader import load_bars
    from path2.dag.engine import analyze as engine_analyze
    from path2_web.data import slice_window
    from path2_web.serialize import serialize_analysis
    t0 = time.perf_counter()
    win = slice_window(load_bars(SNAP, sym, END), START, END)
    ana = serialize_analysis(engine_analyze(all_atoms_spec(), win))
    raw = json.dumps(ana, default=str, separators=(",", ":")).encode()
    return (time.perf_counter() - t0) * 1000, len(raw), len(gzip.compress(raw))


def phase_scan(app):
    from path2_web.scan import run_scan_multi
    from path2_web.serialize import serialize_pattern
    mod = _mod(app)
    p = mod.load_params()
    meta = mod.eval_meta(p)
    t0 = time.perf_counter()
    res = run_scan_multi(
        data_dir=str(SNAP), pattern_specs_json={app: serialize_pattern(mod.build_pattern(p))},
        module_paths={app: f"path2_apps.{app}.dag_spec"}, pattern_ids=[app],
        end_nodes={app: meta["end_node"]}, head_buffer_trading_days=meta["head_buffer_trading_days"],
        label_horizon=40, first_passage_enabled=True, first_passage_k=5.0,
        start_date=START, end_date=END, workers=WORKERS, ticker_regex=None,
        scan_ts=f"bench-{app}", outputs_root=str(SCRATCH / "bench_scans"),
        pattern_params_dicts={app: p.to_dict()},
        price_min=PRICE_MIN, price_max=PRICE_MAX, volume_min=VOLUME_MIN,
        view_guard={"train_end": END, "view_floor": None})
    wall = time.perf_counter() - t0
    n_match = sum(len(r["per_pattern"].get(app, {}).get("analysis", {}).get("matches", []))
                  for r in res["results"])
    size = (SCRATCH / "bench_scans" / "scans" / f"bench-{app}.json").stat().st_size
    return {"wall_s": wall, "scanned": res["scan"]["scanned"], "hits": res["scan"]["hits"],
            "errors": res["scan"]["errors"], "matches": n_match, "file_mb": size / 2**20}


def p_hit_any(n_total, n_new, k=20):
    """均匀从 n_total 个里抽 k 个,至少抽到一个新增的概率。"""
    if n_new <= 0 or n_total <= 0:
        return 0.0
    if n_total - n_new < k:
        return 1.0
    return 1 - math.comb(n_total - n_new, k) / math.comb(n_total, k)


def main():
    (SCRATCH / "bench_scans").mkdir(parents=True, exist_ok=True)
    syms = sorted(p.stem for p in SNAP.glob("*.pkl"))
    out = {"n_stocks": len(syms)}
    # A
    for app in ("bb_v1", "bottom_burst"):
        out[f"scan_{app}"] = r = phase_scan(app)
        print(f"A 网页扫描 {app}: {r['wall_s']:.1f}s,扫 {r['scanned']} 只,命中 {r['hits']} 只,"
              f"match {r['matches']} 个,错误 {r['errors']},结果文件 {r['file_mb']:.0f}MB")
    # B
    t0 = time.perf_counter()
    with ProcessPoolExecutor(WORKERS) as ex:
        rs = list(ex.map(work_all_atoms, syms, chunksize=8))
    wall = time.perf_counter() - t0
    out["precompute_all_atoms"] = {"wall_s": wall, "cpu_s": sum(r[0] for r in rs) / 1000,
                                   "json_mb": sum(r[1] for r in rs) / 2**20,
                                   "gz_mb": sum(r[2] for r in rs) / 2**20}
    b = out["precompute_all_atoms"]
    print(f"B 全池预算所有 detector: {wall:.1f}s(累计单核 {b['cpu_s']:.0f}s),"
          f"JSON {b['json_mb']:.0f}MB,gzip {b['gz_mb']:.0f}MB")
    # C
    t0 = time.perf_counter()
    with ProcessPoolExecutor(WORKERS) as ex:
        rs = list(ex.map(work_variants, syms, chunksize=8))
    print(f"C 改动对拍 {time.perf_counter() - t0:.1f}s")
    sets: dict[str, set] = {}
    for sym, d in rs:
        if d is None:
            continue
        for k, v in d.items():
            sets.setdefault(k, set()).update(map(tuple, v))
    out["variants"] = {}
    for k in sets:
        app, name = k.split("|")
        if name == "基线":
            continue
        base = sets[f"{app}|基线"]
        cur = sets[k]
        add, rem = cur - base, base - cur
        row = {"base": len(base), "after": len(cur), "added": len(add), "removed": len(rem),
               "added_stocks": len({s for s, _ in add}), "removed_stocks": len({s for s, _ in rem}),
               "p_hit_20": p_hit_any(len(cur), len(add))}
        out["variants"][k] = row
        print(f"  {app:12s} {name:38s} 基线 {row['base']:5d} → {row['after']:5d}  新增 {row['added']:4d}"
              f"({row['added_stocks']} 只)  消失 {row['removed']:4d}({row['removed_stocks']} 只)  "
              f"均匀抽 20 张碰到新增的概率 {row['p_hit_20']:.2f}")
    for app in ("bb_v1", "bottom_burst"):
        out[f"base_{app}"] = len(sets[f"{app}|基线"])
    (HERE / "out_pool.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
