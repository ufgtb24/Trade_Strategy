"""微基准:ATR pandas 循环 vs numpy 标量循环、first_passage 的 M(rolling nanmedian)、
bo 检测挂/不挂 gate collector(交替重复消噪)、tb evaluate 循环本体(ATR 已缓存)。
用法:`uv run python docs/research/2026-08-24_region-search-budget/repro/microbench.py`
"""
from __future__ import annotations
import json, pathlib, subprocess, sys, time
REPO = pathlib.Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))
import numpy as np, pandas as pd
from path2 import config
from path2.runner import run
from path2.calc.atr import calculate_atr, rolling_atr_pct_nanmedian
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms import throwback_v1 as tbm
from path2_web.data import slice_window
from path2_web.scan import _list_pkls
from path2_web.gate_collector import attach_and_collect, detach
from path2_apps.bb_v1.dag_spec import build_pattern
from path2_apps.bb_v1.params import Params


def atr_numpy(h, l, c, period=14):
    h = h.to_numpy(float); l = l.to_numpy(float); c = c.to_numpy(float)
    pc = np.concatenate([[np.nan], c[:-1]])
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))
    out = np.full(len(tr), np.nan)
    if len(tr) < period:
        return out
    out[period - 1] = np.nanmean(tr[:period]) if np.isnan(tr[:period]).any() else tr[:period].mean()
    a = out[period - 1]
    for i in range(period, len(tr)):
        a = (a * (period - 1) + tr[i]) / period
        out[i] = a
    return out


def main():
    DATA_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"
    REGEX = "^AA"; REPS = 3
    config.set_runtime_checks(False)
    snap = json.loads((REPO / "outputs/path2_web/scans/20260818T223413.json").read_text())["per_pattern"]["bb_v1"]["params_snapshot"]
    snap["burst"].update(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0); snap["tb"]["max_day_drop_pct"] = None
    p = Params.from_dict(snap)
    wins = [w for w in (slice_window(pd.read_pickle(pk), "2022-11-10", "2026-03-08") for pk in _list_pkls(DATA_DIR, REGEX)) if len(w) > 300]
    n = len(wins); print(f"stocks={n} bars~{int(np.mean([len(w) for w in wins]))}")
    acc = {}
    def tick(k, dt): acc[k] = acc.get(k, 0.0) + dt
    for rep in range(REPS):
        for w in wins:
            t = time.process_time(); a1 = calculate_atr(w["high"], w["low"], w["close"], 14); tick("atr_pandas", time.process_time() - t)
            t = time.process_time(); a2 = atr_numpy(w["high"], w["low"], w["close"], 14); tick("atr_numpy", time.process_time() - t)
            assert np.allclose(a1.to_numpy(), a2, rtol=0, atol=1e-12, equal_nan=True)
            t = time.process_time(); rolling_atr_pct_nanmedian(w["high"], w["low"], w["close"], 20); tick("M_rolling_nanmedian", time.process_time() - t)
            t = time.process_time(); ((pd.concat([w["high"]-w["low"], (w["high"]-w["close"].shift(1)).abs(), (w["low"]-w["close"].shift(1)).abs()],axis=1).max(axis=1))/w["close"]).rolling(20).median(); tick("M_rolling_median_cython", time.process_time() - t)
            spec = build_pattern(p); by = {x.node_id: x for x in spec.nodes}
            for gated in (False, True):
                col = attach_and_collect(spec) if gated else None
                t = time.process_time(); bos = list(run(by["bo"].detector, w)); tick(f"bo(gates={gated})", time.process_time() - t)
                if gated: detach(spec)
            t = time.process_time(); bursts = list(run(by["burst"].detector, bos, w)); tick("burst", time.process_time() - t)
            atr = a2
            tbm._atr_at = lambda _d, i, _p, _a=atr: (float(_a[i]) if _a[i] == _a[i] else 0.0)
            t = time.process_time(); tbs = list(run(by["tb"].detector, bursts, w)); tick("tb_loop(atr cached)", time.process_time() - t)
            acc["n_burst"] = acc.get("n_burst", 0) + len(bursts)
    for k, v in acc.items():
        if k == "n_burst": print(f"  bursts/stock = {v/REPS/n:.1f}"); continue
        print(f"  {k:28s} {v/REPS/n*1000:7.2f} ms/stock")


if __name__ == "__main__":
    main()
