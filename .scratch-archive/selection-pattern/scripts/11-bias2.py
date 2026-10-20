"""11 同日对照配对票 · 第四步补充（看过第一轮结果后加的，单独计数，不改第一轮的判据）。

为什么加：
  1. 第一轮的「当天 M 最高 / 最低一档」恰好和 M 十档、二十档配对的档界重合，这几种配对在它们身上白拿零分；
     真 pattern 的偏好不会正好卡在档界上。补两类不卡档界的假 pattern：
       平滑偏好：按 exp(β·z) 加权全算，z = 当天 M（或平时波动）池内排位的正态分数，β = ±0.5、±1
         （β = 1 时最高一档的权重约是平均的 5 倍，和 bottom_burst 偏爱最高一档的程度相当）；
         最初用的是标准化的 log 值、β = ±1、±2，权重被极少数极端行独占（一行的权重上万），弃用；
       错开档界的窗口：当天 M（或平时波动）池内排位落在 (0.87, 0.97] 或 (0.03, 0.13]。
  2. 第一轮看到白得的领先集中在波动最两头。补一份「只看不在两头的买点」：买点限于当天 M 和平时波动的
     池内排位都在 (0.02, 0.98] 之内（对照仍是整个池子），量剩下多少。
形式：整类全算（带权重）；扎堆型另算两头剔除后的 40 次。抽样误差：整只股票重抽 100 次（现行 M5）。
输出：scripts/11-bias2.csv.gz
运行：uv run python .scratch/selection-pattern/scripts/11-bias2.py
"""
from __future__ import annotations

import importlib.util
import sys
import time
import zlib
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bias11", HERE / "11-bias.py")
bias = importlib.util.module_from_spec(spec); sys.modules["bias11"] = bias; spec.loader.exec_module(bias)
core = bias.core

G = bias.G
TRIM = 0.02


def added_classes(P):
    """返回 {名称: (行号, 权重)}。平滑偏好的 z 用当天池内排位的正态分数（有界，避免极端值一行独大）。"""
    from scipy.special import ndtri

    def nscore(x):
        s = pd.Series(x)
        r = s.groupby(P["d"]).rank()
        n = s.notna().groupby(P["d"]).transform("sum")
        return ndtri(((r - 0.5) / n).to_numpy())

    zM = nscore(P["M"]); zH = nscore(P["Mh"])
    rM = core.day_rank(P, P["M"]); rH = core.day_rank(P, P["Mh"])
    A = {}
    for b in (0.5, 1.0, -0.5, -1.0):
        A[f"tiltM{b:+.1f}"] = (np.arange(P["N"]), np.exp(b * zM))
        ok = np.flatnonzero(np.isfinite(zH))
        A[f"tiltH{b:+.1f}"] = (ok, np.exp(b * zH[ok]))
    for nm, r in (("M", rM), ("H", rH)):
        A[f"{nm}_87_97"] = (np.flatnonzero((r > 0.87) & (r <= 0.97)), None)
        A[f"{nm}_03_13"] = (np.flatnonzero((r > 0.03) & (r <= 0.13)), None)
    return A, rM, rH


def task_full(args):
    name, trimmed = args
    P = G["P"]
    if name in G["A"]:
        rows, w = G["A"][name]
    else:
        rows, w = np.flatnonzero(G["C"][name]), None
    if trimmed:
        k = G["inner"][rows]
        rows = rows[k]; w = None if w is None else w[k]
    res = bias.eval_rows(rows, w)
    rng = np.random.default_rng(zlib.crc32(f"{name}{trimmed}".encode()))
    se = {}
    for sc in bias.SCOPES:
        m = bias.scope_mask(P, rows, sc)
        if m.sum() < 2:
            continue
        r = rows[m]; ww = np.ones(len(r)) if w is None else w[m]
        bs = []
        for _ in range(bias.B_SE):
            bw = core.stock_boot_weights(P, r, rng) * ww
            kk = bw > 0
            bs.append(core.leads(G["mts"]["M5"], G["S"], r[kk], bw[kk]))
        se[sc] = {f"se_{mm}": float(np.std([b[mm] for b in bs], ddof=1)) for mm in core.METRICS}
    for r in res:
        r.update({"cls": name, "form": "full", "trim": trimmed, **se.get(r["scope"], {})})
    return res


def task_clust_trim(rep):
    rng = np.random.default_rng(777_000 + rep)      # 与第一轮同一批扎堆买点，只剔两头
    rows = bias.clust_rows(rng)
    rows = rows[G["inner"][rows]]
    res = bias.eval_rows(rows)
    for r in res:
        r.update({"cls": "bb_clust", "form": "clust", "rep": rep, "trim": True})
    return res


def main():
    t0 = time.time()
    P, Y, hold, mts, S = core.load_all(core.SCHEMES + ["K5"])   # K5：看过第一轮后加的更小近邻
    C = bias.classes(P)
    A, rM, rH = added_classes(P)
    inner = (rM > TRIM) & (rM <= 1 - TRIM) & ~(np.isfinite(rH) & ((rH <= TRIM) | (rH > 1 - TRIM)))
    ndays = pd.Series(pd.DatetimeIndex(P["calendar"]).year).value_counts().to_dict()
    rowidx = np.full((len(P["symbols"]), len(P["calendar"])), -1, np.int64)
    rowidx[P["sym"], P["d"]] = np.arange(P["N"])
    b, pdec = bias.prep_bb(P)

    def day_rows_by_dec(t, lo, hi):
        s, e = P["day_start"][t], P["day_end"][t]
        r = np.arange(s, e)
        return r[(pdec[s:e] >= lo) & (pdec[s:e] <= hi)]

    G.update(P=P, Y=Y, hold=hold, mts=mts, S=S, C=C, A=A, inner=inner, ndays=ndays, rowidx=rowidx,
             bb=(b["sc"].to_numpy(), b["d"].to_numpy(), b["dec"].to_numpy(), b["seg"].to_numpy()),
             day_rows_by_dec=day_rows_by_dec)
    print(f"ready {time.time() - t0:.0f}s；两头剔除后保留的池内行 {inner.mean():.3f}", flush=True)
    tasks = [(n, False) for n in A] + [(n, True) for n in list(A) + bias.JUDGED + bias.CHECKS + ["rand"]]
    with get_context("fork").Pool(12) as mp:
        cl = mp.map_async(task_clust_trim, range(bias.N_REP), chunksize=1)
        fu = mp.map_async(task_full, tasks, chunksize=1)
        res_full = [r for ch in fu.get() for r in ch]
        res_cl = [r for ch in cl.get() for r in ch]
    reps = pd.DataFrame(res_cl)
    agg = reps.groupby(["cls", "form", "scope", "scheme", "trim"])
    mean = agg[core.METRICS + ["n", "n_stocks"]].mean().reset_index()
    sd = agg[core.METRICS].std(ddof=1).add_prefix("repsd_").reset_index(drop=True)
    out = pd.concat([pd.DataFrame(res_full), pd.concat([mean, sd], axis=1)], ignore_index=True)
    out.to_csv(HERE / "11-bias2.csv.gz", index=False)
    print(f"done {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
