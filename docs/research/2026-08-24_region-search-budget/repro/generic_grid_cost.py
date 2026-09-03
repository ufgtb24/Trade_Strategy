"""T1 通用反转(pattern 无关)与 T1+ 的实测成本(单进程 process_time,104 股)。

T1:上游流按参数 section 缓存 + 每个下游参数组合重跑**现成 detector** + ATR/M 每股一次 +
   label 按 span 记忆化 + 每格 build_pattern/compile_plan/solve/reify。
   6 维 4 档:bo 16 次 / burst 256 次(g×m 当普通构造参数)/ tb 4096 次 / solve 4096 次。
T1+:只多一条「min_bos 由 detector 声明为 count 过滤型、事后切」:burst 64 次、tb 1024 次,
   solve 仍 4096 次(在按 count 过滤后的 burst 流上)。
两种模式都经 annotate_stream(fresh counts)+ 引擎求解,与 stream_replay_equiv.py(E5)同一路径。
用法:`uv run python docs/research/2026-08-24_region-search-budget/repro/generic_grid_cost.py`
"""
from __future__ import annotations
import json, pathlib, subprocess, sys, time
from dataclasses import replace
REPO = pathlib.Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(pathlib.Path(__file__).parent))
import numpy as np, pandas as pd
from path2 import config
from path2.runner import run
from path2.dag.engine import annotate_stream
from path2.dag._solve import compile_plan, solve
from path2.dag._reify import reify
from path2.calc.atr import rolling_atr_pct_nanmedian
from path2.eval import _first_passage_at
from path2.atoms import throwback_v1 as tbm
from path2_web.data import slice_window
from path2_web.scan import _list_pkls, TRADING_TO_CALENDAR_RATIO
from path2_apps.bb_v1.dag_spec import build_pattern
from path2_apps.bb_v1.params import Params
from microbench import atr_numpy


def main(MODE="T1", TICKER_REGEX="^A[A-C]"):
    DATA_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"
    START_DATE, END_DATE = "2024-01-01", "2026-01-01"
    HEAD_BUFFER, H, FPK = 250, 40, 5.0
    GS, MS, KS, RK = [4, 8, 12, 20], [1, 2, 3, 4], [0, 1, 2, 3], [3.0, 5.0, 8.0, 12.0]
    MRH, EXC = [0.1, 0.15, 0.2, 0.3], [0.001, 0.003, 0.01, 0.03]
    config.set_runtime_checks(True)
    snap = json.loads((REPO / "outputs/path2_web/scans/20260818T223413.json").read_text())["per_pattern"]["bb_v1"]["params_snapshot"]
    snap["burst"].update(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0); snap["tb"]["max_day_drop_pct"] = None
    base = Params.from_dict(snap)
    start_ts, end_ts = pd.to_datetime(START_DATE), pd.to_datetime(END_DATE)
    buf_start = str((start_ts - pd.Timedelta(days=round(HEAD_BUFFER * TRADING_TO_CALENDAR_RATIO))).date())
    buf_end = str((end_ts + pd.Timedelta(days=round(H * TRADING_TO_CALENDAR_RATIO))).date())
    atr_cache = {}
    def _atr_at(df, idx, period):
        # 缓存持 df 引用防 id 复用(df 被回收后新 df 可能拿到同一 id → 读到过期 ATR)
        ent = atr_cache.get(period)
        if ent is None or ent[0] is not df:
            ent = atr_cache[period] = (df, atr_numpy(df["high"], df["low"], df["close"], period))
        v = float(ent[1][idx]); return v if v == v else 0.0
    tbm._atr_at = _atr_at
    acc = dict(load=0.0, prep=0.0, bo=0.0, burst=0.0, tb=0.0, spec=0.0, solve=0.0, label=0.0)
    cnt = dict(stocks=0, bo_runs=0, burst_runs=0, tb_runs=0, solves=0, matches=0, spans=0)
    per_stock = []
    for pk in _list_pkls(DATA_DIR, TICKER_REGEX):
        t = time.process_time(); w = slice_window(pd.read_pickle(pk), buf_start, buf_end); acc["load"] += time.process_time() - t
        if len(w) < 300: continue
        cnt["stocks"] += 1; t_stock = time.process_time()
        t = time.process_time()
        _atr_at(w, 20, base.tb.atr_window)
        M = rolling_atr_pct_nanmedian(w["high"], w["low"], w["close"], 20).values
        hi, lo_, cl = w["high"].values, w["low"].values, w["close"].values
        lo = int(w["date"].searchsorted(start_ts, "left")); hi_i = int(w["date"].searchsorted(end_ts, "right")) - 1
        label_memo = {}
        acc["prep"] += time.process_time() - t
        for mrh in MRH:
            for exc in EXC:
                p_bo = replace(base, bo=replace(base.bo, min_relative_height=mrh, exceed_threshold=exc))
                spec_bo = build_pattern(p_bo)
                t = time.process_time(); bos = list(run(spec_bo.nodes[0].detector, w)); annotate_stream({}, "bo", bos, {}); acc["bo"] += time.process_time() - t
                cnt["bo_runs"] += 1
                for g in GS:
                    burst_by_m = {}
                    for m in MS:
                        p_gm = replace(p_bo, burst=replace(p_bo.burst, gap_max=g, min_bos=m))
                        if MODE == "T1" or m == MS[0]:
                            t = time.process_time()
                            det = build_pattern(p_gm).nodes[1].detector
                            bursts = list(run(det, bos, w)); annotate_stream({}, "burst", bursts, {"burst": {"members": "bo"}})
                            acc["burst"] += time.process_time() - t; cnt["burst_runs"] += 1
                            burst_by_m[m] = bursts
                        else:   # T1+:min_bos 事后切(count 过滤,对象共享,span 唯一故 #idx 恒 0)
                            burst_by_m[m] = [b for b in burst_by_m[MS[0]] if b.count >= m]
                    for K in KS:
                        for k in RK:
                            tb_by_m = {}
                            for m in MS:
                                p_cell = replace(p_gm, burst=replace(p_gm.burst, min_bos=m), tb=replace(p_gm.tb, stop_confirm_bars=K, big_rise_k=k))
                                t = time.process_time(); spec = build_pattern(p_cell); acc["spec"] += time.process_time() - t
                                if MODE == "T1" or m == MS[0]:
                                    t = time.process_time()
                                    counts = {}
                                    tbs = list(run(spec.nodes[2].detector, burst_by_m[m], w)); annotate_stream(counts, "tb", tbs, {})
                                    acc["tb"] += time.process_time() - t; cnt["tb_runs"] += 1
                                    tb_by_m[m] = tbs
                                else:   # T1+:tb 由 m=1 的流按源 burst 过滤(anchor_bo_id ∈ 保留 burst 的 last_bo)
                                    keep = {b.members[-1].instance_id for b in burst_by_m[m]}
                                    tb_by_m[m] = [e for e in tb_by_m[MS[0]] if e.anchor_bo_id in keep]
                                t = time.process_time()
                                streams = {"bo": bos, "burst": burst_by_m[m], "tb": tb_by_m[m]}
                                plan = compile_plan(spec)
                                matches = [reify(s, streams, plan) for s in solve(plan, streams)]
                                acc["solve"] += time.process_time() - t; cnt["solves"] += 1; cnt["matches"] += len(matches)
                                t = time.process_time()
                                for mt in matches:
                                    tb = mt.node_index["tb"]; key = (tb.start_idx, tb.end_idx)
                                    if key not in label_memo:
                                        cnt["spans"] += 1
                                        fp = {"up": 0, "down": 0, "both": 0, "none": 0}; rets = []
                                        for tt in range(key[0], key[1] + 1):
                                            if tt + H < len(w) and lo <= tt <= hi_i:
                                                s = _first_passage_at(hi, lo_, cl, M, tt, H, FPK)
                                                if s: fp[s] += 1
                                                rets.append(float(hi[tt + 1: tt + H + 1].max()) / float(cl[tt]) - 1.0)
                                        label_memo[key] = (fp, (sum(rets) / len(rets)) if rets else None)
                                acc["label"] += time.process_time() - t
        per_stock.append(time.process_time() - t_stock)
    n = cnt["stocks"]; tot = sum(acc.values())
    ps = np.array(per_stock) * 1000
    print(f"MODE={MODE} stocks={n} 合计 {tot/n*1000:.0f} ms/股 (p10/p50/p90/max {np.percentile(ps,10):.0f}/{np.median(ps):.0f}/{np.percentile(ps,90):.0f}/{ps.max():.0f})")
    for k, v in acc.items(): print(f"  {k:6s} {v/n*1000:8.1f} ms/股")
    for k, v in cnt.items(): print(f"  {k:10s} {v/n:8.1f} /股")
    print(f"  每 tb 检测 {acc['tb']/cnt['tb_runs']*1000:.3f} ms/股/次;每格 solve+reify {acc['solve']/cnt['solves']*1000:.3f} ms/股/格;每格 build_pattern {acc['spec']/cnt['solves']*1000:.3f} ms")
    print(f"  外推 6720 股: {tot/n*6720:.0f} CPU·s ≈ {tot/n*6720/8/60:.1f} min @8 workers")


if __name__ == "__main__":
    for mode in ("T1+", "T1"):
        main(MODE=mode)
