"""反转循环跑满 6 维 4^6=4096 格的真实成本(子集股票,单进程 CPU 时间)+ 候选去重规模。
每股:加载/M 一次 → 对 (min_relative_height, exceed_threshold) 16 档各跑一次 bo →
burst 多 g 一次遍历 → tb 按 (last_bo, anchor) 记忆化、一次多 (K,k) → 去重 tb span 逐个打 label。
不建 4096 个 match 集合(归属由结构规则即时判定),只计数。
用法:`uv run python docs/research/2026-08-24_region-search-budget/repro/grid_cost.py`
"""
from __future__ import annotations
import json, pathlib, subprocess, sys, time
REPO = pathlib.Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(pathlib.Path(__file__).parent))
import numpy as np, pandas as pd
from path2 import config
from path2.runner import run
from path2.atoms.breakout import BODetector
from path2.calc.atr import rolling_atr_pct_nanmedian
from path2.eval import _first_passage_at
from path2_web.data import slice_window
from path2_web.scan import _list_pkls, TRADING_TO_CALENDAR_RATIO
from path2_apps.bb_v1.params import Params
from multi_value_equiv import bursts_multi_g, tb_multi, span_min_anchor
from microbench import atr_numpy


def main():
    DATA_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"
    TICKER_REGEX = "^A[A-C]"
    START_DATE, END_DATE = "2024-01-01", "2026-01-01"
    HEAD_BUFFER, LABEL_HORIZON, FP_K = 250, 40, 5.0
    GS, MS = [4, 8, 12, 20], [1, 2, 3, 4]
    KS_SCB, KS_RISE = [0, 1, 2, 3], [3.0, 5.0, 8.0, 12.0]
    MRH, EXC = [0.1, 0.15, 0.2, 0.3], [0.001, 0.003, 0.01, 0.03]
    config.set_runtime_checks(False)
    snap = json.loads((REPO / "outputs/path2_web/scans/20260818T223413.json").read_text())["per_pattern"]["bb_v1"]["params_snapshot"]
    snap["burst"].update(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0); snap["tb"]["max_day_drop_pct"] = None
    base = Params.from_dict(snap)
    tb_kw = dict(max_start_gap=base.tb.max_start_gap, max_window=base.tb.max_window,
                 judged_measure=base.tb.judged_measure, reference_measure=base.tb.reference_measure, scb_mode=base.tb.scb_mode)
    start_ts, end_ts = pd.to_datetime(START_DATE), pd.to_datetime(END_DATE)
    buf_start = str((start_ts - pd.Timedelta(days=round(HEAD_BUFFER * TRADING_TO_CALENDAR_RATIO))).date())
    buf_end = str((end_ts + pd.Timedelta(days=round(LABEL_HORIZON * TRADING_TO_CALENDAR_RATIO))).date())
    pkls = _list_pkls(DATA_DIR, TICKER_REGEX)
    acc = dict(load=0.0, prep=0.0, bo=0.0, burst=0.0, tb=0.0, label=0.0)
    cnt = dict(stocks=0, bo=0, bursts=0, anchors=0, tb_nonnull=0, spans=0, buydays=0, long_rows=0, cell_matches=0)
    acc["cells"] = 0.0
    per_stock = []
    t_all = time.process_time()
    for pk in pkls:
        t = time.process_time(); w = slice_window(pd.read_pickle(pk), buf_start, buf_end); acc["load"] += time.process_time() - t
        if len(w) < 300: continue
        cnt["stocks"] += 1
        t = time.process_time()
        atr = atr_numpy(w["high"], w["low"], w["close"], base.tb.atr_window)
        M = rolling_atr_pct_nanmedian(w["high"], w["low"], w["close"], 20).values
        hi, lo_, cl = w["high"].values, w["low"].values, w["close"].values
        lo = int(w["date"].searchsorted(start_ts, "left")); hi_i = int(w["date"].searchsorted(end_ts, "right")) - 1
        acc["prep"] += time.process_time() - t
        spans = set(); cells_out = {}; t_stock = time.process_time()
        for mrh in MRH:
            for exc in EXC:
                kw = base.bo_kwargs(); kw["min_relative_height"] = mrh; kw["exceed_threshold"] = exc
                t = time.process_time(); bos = list(run(BODetector(**kw), w)); acc["bo"] += time.process_time() - t
                cnt["bo"] += len(bos)
                t = time.process_time(); mb = bursts_multi_g(bos, w, GS, base.burst.vol_baseline_period); acc["burst"] += time.process_time() - t
                t = time.process_time()
                memo = {}
                for g in GS:
                    for b in mb[g]:
                        cnt["bursts"] += 1
                        lb = b.members[-1].end_idx
                        anchor = span_min_anchor(w, b, base.tb.reference_measure)
                        key = (lb, anchor)
                        if key in memo: continue
                        a = float(atr[lb - 1]) if lb >= 1 and atr[lb - 1] == atr[lb - 1] else 0.0
                        memo[key] = tb_multi(w, lb, anchor, a, KS_SCB, KS_RISE, **tb_kw)
                        cnt["anchors"] += 1
                        for r in memo[key].values():
                            if r is not None:
                                cnt["tb_nonnull"] += 1; spans.add((r[0], r[1]))
                acc["tb"] += time.process_time() - t
                # 长表行 = (bo档, g, burst 实例, K, k) 非空;格归属谓词物化 = 每行按 count≥m 复制到 4 个 m 档
                t = time.process_time()
                for g in GS:
                    for b in mb[g]:
                        rs = memo[(b.members[-1].end_idx, span_min_anchor(w, b, base.tb.reference_measure))]
                        for (K, k), r in rs.items():
                            if r is None: continue
                            cnt["long_rows"] += 1
                            row = (mrh, exc, g, b.count, K, k, r[0], r[1], r[2], b.first_drought, b.distinct_pk, b.max_bar_vol_ratio, b.peak_age_max)
                            for m in MS:
                                if b.count >= m:
                                    cells_out.setdefault((mrh, exc, g, m, K, k), []).append(row); cnt["cell_matches"] += 1
                acc["cells"] += time.process_time() - t
        t = time.process_time()
        for (s, e) in spans:
            cnt["spans"] += 1
            for tt in range(s, e + 1):
                if tt + LABEL_HORIZON < len(w) and lo <= tt <= hi_i:
                    _first_passage_at(hi, lo_, cl, M, tt, LABEL_HORIZON, FP_K)
                    float(hi[tt + 1: tt + LABEL_HORIZON + 1].max()) / float(cl[tt]) - 1.0
                    cnt["buydays"] += 1
        acc["label"] += time.process_time() - t
        per_stock.append(time.process_time() - t_stock)
    tot = time.process_time() - t_all
    n = cnt["stocks"]
    print(f"stocks={n} total CPU={tot:.1f}s  per-stock={tot/n*1000:.0f} ms  (6 维 4096 格全部覆盖)")
    for k, v in acc.items(): print(f"  {k:8s} {v/n*1000:7.1f} ms/stock")
    for k, v in cnt.items(): print(f"  {k:12s} {v/n:8.1f} /stock")
    ps = np.array(per_stock) * 1000
    print(f"  单股成本 p10/p50/p90/max = {np.percentile(ps,10):.0f}/{np.median(ps):.0f}/{np.percentile(ps,90):.0f}/{ps.max():.0f} ms")
    print(f"  每格增量(谓词物化,4096 格) = {acc['cells']/n/4096*1000:.4f} ms/股/格;每格平均 match 数 = {cnt['cell_matches']/n/4096:.2f}")
    print(f"外推全宇宙 8325 股: {tot/n*8325:.0f} CPU·s ≈ {tot/n*8325/8/60:.1f} min wall @8 workers")


if __name__ == "__main__":
    main()
