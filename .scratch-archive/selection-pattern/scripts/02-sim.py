"""02 分辨力研究 · 主模拟：用普通买入拼「假 pattern」，看它对同日普通买入对照的领先偶然能偏多远。

假 pattern 没有任何选股能力（真实领先 = 0），所以它的领先在多次重复里的分布就是「偶然波动」。

两类假 pattern：
- indep：每个买点独立随机抽一个股票日（最乐观，买点完全独立）。
- runs：一段段连着几天命中同一只股票（段长几何分布，均值 L），段的起点随机。
- real：照搬现役 pattern（bottom_burst / bb_v1）的买点长相——哪些天、每只股票几段、每段几天都原样保留，
  只把每只股票整体换成另一只「波动水平同档」的股票（vol 换法；random 换法不管波动档）。
  这样同票反复、连着几天、按日期扎堆、按波动水平扎堆全部保留，而买点之后的涨跌来自无关股票，
  所以不含任何 pattern 成绩。按「段」随机保留一部分（q）得到更稀的同长相 pattern。

每个假 pattern 算：v3 方向领先 Δ、合并方向领先、幅度领先（中位数之差 / 超额中位数）、买点数、股票数；
部分重复另算 v3 的「整只股票重抽」偶然波动，用来核对 v3 自带的估计准不准。

用法：uv run python .scratch/selection-pattern/scripts/02-sim.py H [--k K] [--sims N] [--quick]
输出：scripts/02-sim-H{H}_k{k}.csv.gz（每行一次重复）
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("core02", HERE / "02-core.py")
core = importlib.util.module_from_spec(spec); sys.modules["core02"] = core; spec.loader.exec_module(core)

G: dict = {}   # fork 前在父进程准备好的共享数据


def prepare(H: int, k: float):
    pool = core.load_pool(H, k)
    vol = pd.Series(pool.stock_vol)
    vdec = pd.qcut(vol.rank(method="first"), 10, labels=False).to_numpy()
    vdec[np.isnan(pool.stock_vol)] = -1
    date_start = np.searchsorted(pool.d, np.arange(pool.rowidx.shape[1]), side="left")
    date_end = np.searchsorted(pool.d, np.arange(pool.rowidx.shape[1]), side="right")
    apps = {}
    for app in ("bottom_burst", "bb_v1"):
        b = pd.read_csv(core.CACHE / f"buys_{app}.csv")
        si = pd.Index(pool.symbols).get_indexer(b["symbol"]).astype(np.int64)
        d = np.searchsorted(pool.calendar, pd.to_datetime(b["date"]).to_numpy()).astype(np.int64)
        o = np.lexsort((d, si)); si, d = si[o], d[o]
        new = np.ones(len(d), bool); new[1:] = (si[1:] != si[:-1]) | (d[1:] != d[:-1] + 1)
        apps[app] = (si, d, np.cumsum(new) - 1)
    G.update(pool=pool, vdec=vdec, ds=date_start, de=date_end, apps=apps,
             dmin=int(pool.dates_present.min()), dmax=int(pool.dates_present.max()))


def seg_rows(D0, D1):
    return np.arange(G["ds"][D0], G["de"][D1])


def gen_indep(rng, D0, D1, n):
    rows = seg_rows(D0, D1)
    return np.sort(rng.choice(rows, size=min(n, len(rows)), replace=False))


def gen_tilt(rng, D0, D1, n, dec):
    """只在某个波动水平档（全部股票按 M 中位数分十档）的股票里独立随机抽买点：测「偏好某种波动水平」本身白得多少领先。"""
    rows = seg_rows(D0, D1)
    rows = rows[G["vdec"][G["pool"].sym[rows]] == dec]
    return np.sort(rng.choice(rows, size=min(n, len(rows)), replace=False))


def gen_runs(rng, D0, D1, n, L):
    pool = G["pool"]; rows = seg_rows(D0, D1)
    E = int(np.ceil(n / L * 1.5)) + 10
    start = rng.choice(rows, size=E)
    length = rng.geometric(1.0 / L, size=E)
    ep = np.repeat(np.arange(E), length)
    off = np.arange(len(ep)) - np.repeat(np.cumsum(length) - length, length)
    s = pool.sym[start][ep]; d = pool.d[start][ep] + off
    ok = d <= D1
    r = pool.rowidx[s[ok], d[ok]]; ep = ep[ok]
    keep = r >= 0; r, ep = r[keep], ep[keep]
    _, first = np.unique(r, return_index=True)
    first = np.sort(first)
    r, ep = r[first], ep[first]
    cum = np.arange(1, len(r) + 1)
    cut = np.searchsorted(cum, n)
    if cut < len(r):
        sel = np.isin(ep, np.unique(ep[: cut + 1]))
        r = r[sel]
    return np.sort(r)


def gen_real(rng, D0, D1, app, q, mapping):
    pool = G["pool"]; vdec = G["vdec"]
    si, d, run = G["apps"][app]
    m = (d >= D0) & (d <= D1)
    si, d, run = si[m], d[m], run[m]
    if q < 1:
        ur = np.unique(run)
        kept = ur[rng.random(len(ur)) < q]
        m = np.isin(run, kept); si, d = si[m], d[m]
    if not len(si):
        return np.array([], dtype=np.int64)
    src, inv = np.unique(si, return_inverse=True)
    lo = np.full(len(src), 10 ** 9); hi = np.full(len(src), -1)
    np.minimum.at(lo, inv, d); np.maximum.at(hi, inv, d)
    used = set(); target = np.empty(len(src), np.int64)
    first, last = pool.stock_first, pool.stock_last
    for j in rng.permutation(len(src)):
        s = src[j]
        cov = (first <= lo[j]) & (last >= hi[j]) & (first >= 0)
        if mapping == "vol" and vdec[s] >= 0:
            cov &= vdec == vdec[s]
        cand = np.flatnonzero(cov)
        cand = cand[cand != s]
        free = cand[[c not in used for c in cand]] if len(used) else cand
        pick = free if len(free) else cand
        if not len(pick):
            pick = np.flatnonzero((first <= lo[j]) & (last >= hi[j]) & (first >= 0))
        t = int(rng.choice(pick)); used.add(t); target[j] = t
    r = pool.rowidx[target[inv], d]
    return np.unique(r[r >= 0])


def stats(rows, D0, D1, boot):
    pool = G["pool"]
    pdates = core.plan_dates(pool, D0, D1)
    Z, B, delta, nwin = core.v3_delta(pool, rows, pdates)
    amp, med, ctrl = core.amp_lead(pool, rows)
    rec = dict(N=len(rows), stocks=int(len(np.unique(pool.sym[rows]))), active_windows=nwin,
               Z=Z, B=B, delta=delta, pooled=core.pooled_dir_lead(pool, rows),
               touched=float((pool.dir[rows] != 0).mean()),
               vdec_mean=float(G["vdec"][pool.sym[rows]].mean()),
               amp=amp, amp_med=med, amp_ctrl=ctrl, amp_excess=core.amp_lead_excess(pool, rows),
               boot_sd=np.nan)
    if boot:
        frozen = len(np.unique(pool.sym[seg_rows(D0, D1)]))
        rec["boot_sd"] = core.stock_bootstrap_v3(pool, rows, pdates, 200, 0, frozen)
    return rec


def run_task(task):
    cfg, items = task
    out = []
    for idx, seed in items:
        rng = np.random.default_rng(seed)
        Y = cfg["Y"]
        if cfg.get("D0") is not None:
            D0, D1 = cfg["D0"], cfg["D1"]
        else:
            span = int(round(Y * 252))
            D0 = int(rng.integers(G["dmin"], G["dmax"] - span + 2)); D1 = D0 + span - 1
        if cfg["kind"] == "indep":
            rows = gen_indep(rng, D0, D1, int(round(cfg["rate"] * Y)))
        elif cfg["kind"] == "runs":
            rows = gen_runs(rng, D0, D1, int(round(cfg["rate"] * Y)), cfg["L"])
        elif cfg["kind"] == "tilt":
            rows = gen_tilt(rng, D0, D1, int(round(cfg["rate"] * Y)), cfg["dec"])
        else:
            rows = gen_real(rng, D0, D1, cfg["app"], cfg["q"], cfg["mapping"])
        if len(rows) < 2:
            continue
        rec = stats(rows, D0, D1, boot=idx < cfg.get("boot", 0))
        out.append({**{k: v for k, v in cfg.items() if k not in ("sims",)}, "seed": seed, "D0": D0, "D1": D1, **rec})
    return out


def configs(H, sims, quick):
    pool = G["pool"]
    cal = pool.calendar
    cs = []
    years = [1, 2, 4] if not quick else [1]
    max_years = (G["dmax"] - G["dmin"] + 1) / 252
    years = [y for y in years if y <= max_years]
    for Y in years:
        for rate in [30, 100, 300, 1000, 3000]:
            cs.append(dict(kind="indep", rate=rate, Y=Y, sims=sims))
            cs.append(dict(kind="runs", rate=rate, Y=Y, L=5, sims=sims))
        for app, qs in (("bottom_burst", [1, 0.3, 0.1, 0.03]), ("bb_v1", [1, 0.3, 0.1, 0.03])):
            for q in qs:
                cs.append(dict(kind="real", app=app, q=q, mapping="vol", Y=Y, sims=sims, boot=20))
            cs.append(dict(kind="real", app=app, q=1, mapping="random", Y=Y, sims=sims, boot=0))
    for dec in (0, 3, 6, 8, 9):
        cs.append(dict(kind="tilt", rate=1000, Y=2, dec=dec, sims=max(100, sims // 4)))
    if H == 40 and pool.k == 5.0:
        # 核对 v3 已知量级：bottom_burst 全池训练段 2024-07-01..2025-10-31
        D0 = int(np.searchsorted(cal, np.datetime64("2024-07-01")))
        D1 = int(np.searchsorted(cal, np.datetime64("2025-10-31"), side="right")) - 1
        for q in [1, 0.3, 0.1]:
            cs.append(dict(kind="real", app="bottom_burst", q=q, mapping="vol", Y=round((D1 - D0 + 1) / 252, 3),
                           D0=D0, D1=D1, sims=sims, boot=40, tag="v3train"))
        for L in [1, 5]:
            cs.append(dict(kind="indep" if L == 1 else "runs", rate=5000, L=L, Y=round((D1 - D0 + 1) / 252, 3),
                           D0=D0, D1=D1, sims=sims, boot=20, tag="v3train"))
    return cs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("H", type=int)
    ap.add_argument("--k", type=float, default=5.0)
    ap.add_argument("--sims", type=int, default=400)
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    prepare(a.H, a.k)
    cs = configs(a.H, a.sims, a.quick)
    tasks = []
    for ci, cfg in enumerate(cs):
        cfg["cid"] = ci
        base = 1_000_003 * (ci + 1) + 7919 * a.H
        seeds = [(i, base + i) for i in range(cfg["sims"])]
        for j in range(0, len(seeds), 25):
            tasks.append((cfg, seeds[j:j + 25]))
    print(f"H={a.H} k={a.k:g}: pool ready {time.time() - t0:.0f}s, {len(cs)} configs, {len(tasks)} tasks", flush=True)
    with get_context("fork").Pool(a.workers) as mp:
        res = mp.map(run_task, tasks, chunksize=1)
    df = pd.DataFrame([r for chunk in res for r in chunk])
    name = f"02-sim-H{a.H}_k{a.k:g}" + ("-quick" if a.quick else "") + ".csv.gz"
    df.to_csv(HERE / name, index=False)
    print(f"done {time.time() - t0:.0f}s → {name}, rows {len(df)}")
    g = df.groupby("cid").agg(kind=("kind", "first"), app=("app", "first") if "app" in df else ("kind", "first"),
                               Y=("Y", "first"), N=("N", "median"), stocks=("stocks", "median"),
                               sd_delta=("delta", "std"), mean_delta=("delta", "mean"),
                               sd_pooled=("pooled", "std"), sd_amp=("amp", "std"), mean_amp=("amp", "mean"),
                               boot=("boot_sd", "mean"))
    print(g.to_string())


if __name__ == "__main__":
    main()
