"""09 目标池票 · 池子里的分辨力：用普通买入拼「假 pattern」，对照只从同一池子里抽。

沿用 02 的算法与口径（02-core.py 的 v3 方向领先、幅度领先），只改两处：
  1. 普通买入与同日普通买入对照都只取池子里的股票日（每天在池内按 M 重新切五档）；
  2. 假 pattern 的买点只落在池子里。
两种长相（真实领先都为零）：
  clustered（扎堆）：照抄 bottom_burst 的买点结构——哪几天出手、一只股票命中几段、每段连买几天——
      每只来源股整体换成一只池内「平时波动同档」、且在这些日子大多在池内的股票（不在池内的那几天丢掉）；
      按段随机保留 q 得到更稀的同长相 pattern。
  dispersed（分散）：每段行情只买一次（同一只股票 40 个交易日内不重复买），命中很多不同股票；
      出手日期照 bottom_burst 各月的买点疏密抽（保留「同一段时间扎堆出手」），股票照 bottom_burst
      偏爱的波动档加权抽（保留「偏爱高波动」）。
  indep（参照）：池内股票日完全随机，不扎堆、不偏波动档。
不读任何 pattern 的成绩：bottom_burst 只借用买点位置（02 缓存的 buys_bottom_burst.csv）。

用法：uv run python .scratch/selection-pattern/scripts/09-sim.py <池子名> <H> [--k K] [--sims N]
输出：scripts/09-sim-<池子>-H{H}_k{k}.csv.gz
"""
from __future__ import annotations

import argparse
import zlib
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
SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad")
G: dict = {}


def load_pool_masked(H: int, k: float, mask: np.ndarray) -> core.Pool:
    """与 02-core.load_pool 相同，只保留 mask[股票, 交易日] 为真的普通买入（对照因此也只在池内）。"""
    meta = np.load(core.CACHE / "meta.npz", allow_pickle=True)
    z = np.load(core.CACHE / f"labels_H{H}_k{k:g}.npz")
    sym, d = z["sym"].astype(np.int32), z["d"].astype(np.int32)
    keep = mask[sym, d]
    sym, d = sym[keep], d[keep]
    M, dr, up = z["M"][keep].astype(np.float64), z["dir"][keep].astype(np.int8), z["up"][keep].astype(np.float64)
    n = len(d)
    bounds = np.flatnonzero(np.diff(d)) + 1
    starts = np.concatenate(([0], bounds)); ends = np.concatenate((bounds, [n]))
    binv = np.empty(n, np.int32)
    for s, e in zip(starts, ends):
        cuts = np.unique(np.quantile(M[s:e], [0.2, 0.4, 0.6, 0.8]))
        binv[s:e] = np.searchsorted(cuts, M[s:e], side="left")
    gbin = d * 5 + binv
    nb = int(gbin.max()) + 1
    cnt = np.bincount(gbin, minlength=nb).astype(np.float64)
    bdir = np.divide(np.bincount(gbin, weights=dr.astype(np.float64), minlength=nb), cnt,
                     out=np.zeros(nb), where=cnt > 0)
    df = pd.DataFrame({"g": gbin, "up": up})
    med = df.groupby("g")["up"].median()
    bmed = np.zeros(nb); bmed[med.index.to_numpy()] = med.to_numpy()
    rank = df.groupby("g")["up"].rank(pct=True).to_numpy()
    calendar, symbols = meta["calendar"], meta["symbols"]
    rowidx = np.full((len(symbols), len(calendar)), -1, np.int32)
    rowidx[sym, d] = np.arange(n, dtype=np.int32)
    order = np.argsort(up, kind="stable")
    sv = pd.Series(M).groupby(sym).median().reindex(range(len(symbols))).to_numpy()
    first = pd.Series(d).groupby(sym).min().reindex(range(len(symbols))).fillna(-1).to_numpy(int)
    last = pd.Series(d).groupby(sym).max().reindex(range(len(symbols))).fillna(-1).to_numpy(int)
    return core.Pool(H, k, sym, d, M, dr, up, gbin, cnt, bdir, bmed, dr - bdir[gbin], up - bmed[gbin], rank,
                     rowidx, order, up[order], gbin[order], np.unique(d), calendar, symbols, sv, first, last)


def prepare(pool_name: str, H: int, k: float):
    masks = np.load(SCR / "09/pool_masks.npz")
    pool = load_pool_masked(H, k, masks[pool_name])
    # 「平时波动」十档：切点取全市场每只股票 M 中位数的十分位，池内股票按同一组切点归档（档号 = 绝对波动水平）
    z = np.load(core.CACHE / f"labels_H{H}_k{k:g}.npz")
    full_sv = pd.Series(z["M"].astype(np.float64)).groupby(z["sym"].astype(np.int32)).median()
    full_sv = full_sv.reindex(range(len(pool.symbols))).to_numpy()
    cuts = np.nanquantile(full_sv, np.linspace(0.1, 0.9, 9))
    vdec_full = np.where(np.isfinite(full_sv), np.searchsorted(cuts, full_sv), -1)
    vdec_pool = np.where(np.isfinite(pool.stock_vol), np.searchsorted(cuts, pool.stock_vol), -1)
    # bottom_burst 买点结构（只借位置）
    b = pd.read_csv(core.CACHE / "buys_bottom_burst.csv")
    si = pd.Index(pool.symbols).get_indexer(b["symbol"]).astype(np.int64)
    dd = np.searchsorted(pool.calendar, pd.to_datetime(b["date"]).to_numpy()).astype(np.int64)
    o = np.lexsort((dd, si)); si, dd = si[o], dd[o]
    new = np.ones(len(dd), bool); new[1:] = (si[1:] != si[:-1]) | (dd[1:] != dd[:-1] + 1)
    run = np.cumsum(new) - 1
    # 分散长相的抽样权重：日期按 bottom_burst 各月买点数（每个交易日均摊），股票按它偏爱的波动档
    cal = pd.DatetimeIndex(pool.calendar)
    month = cal.year * 12 + cal.month
    mcount = pd.Series(1, index=month[dd]).groupby(level=0).sum()
    mdays = pd.Series(1, index=month).groupby(level=0).sum()
    date_w = (mcount.reindex(month).fillna(0).to_numpy() / mdays.reindex(month).to_numpy()) + 1e-3
    dec_w = np.bincount(vdec_full[si][vdec_full[si] >= 0], minlength=10).astype(float)
    dec_w = dec_w / dec_w.sum() + 1e-3
    inpool = pool.rowidx >= 0
    cand_by_dec = {dd_: np.flatnonzero(vdec_pool == dd_) for dd_ in range(10)}
    date_start = np.searchsorted(pool.d, np.arange(pool.rowidx.shape[1]), side="left")
    date_end = np.searchsorted(pool.d, np.arange(pool.rowidx.shape[1]), side="right")
    G.update(pool=pool, vdec_full=vdec_full, vdec_pool=vdec_pool, app=(si, dd, run), date_w=date_w, dec_w=dec_w,
             inpool=inpool, cand=cand_by_dec, ds=date_start, de=date_end,
             dmin=int(pool.dates_present.min()), dmax=int(pool.dates_present.max()))


def seg_rows(D0, D1):
    return np.arange(G["ds"][D0], G["de"][D1])


def gen_clustered(rng, D0, D1, q):
    pool, inpool = G["pool"], G["inpool"]
    si, d, run = G["app"]
    m = (d >= D0) & (d <= D1)
    si, d, run = si[m], d[m], run[m]
    if q < 1:
        ur = np.unique(run)
        kept = ur[rng.random(len(ur)) < q]
        m = np.isin(run, kept); si, d = si[m], d[m]
    if not len(si):
        return np.array([], dtype=np.int64)
    src, inv = np.unique(si, return_inverse=True)
    order = np.argsort(inv, kind="stable")
    bounds = np.searchsorted(inv[order], np.arange(len(src) + 1))
    used = np.zeros(len(pool.symbols), bool)
    target = np.empty(len(src), np.int64)
    for j in rng.permutation(len(src)):
        dates = d[order[bounds[j]:bounds[j + 1]]]
        dec = G["vdec_full"][src[j]]
        decs = [dec] if dec >= 0 else list(range(10))
        cand = np.concatenate([G["cand"][x] for x in decs]) if decs else np.array([], int)
        for extra in (1, 2, 3):  # 同档没有合适的，放宽到相邻档
            if len(cand):
                break
            decs = [x for x in range(dec - extra, dec + extra + 1) if 0 <= x < 10]
            cand = np.concatenate([G["cand"][x] for x in decs])
        cov = inpool[np.ix_(cand, dates)].mean(1)
        free = ~used[cand]
        good = cand[(cov >= 0.8) & free]
        if not len(good):
            good = cand[(cov >= 0.5) & free]
        if not len(good):
            best = cov.max()
            good = cand[cov >= best - 1e-9]
        t = int(rng.choice(good)); used[t] = True; target[j] = t
    r = pool.rowidx[target[inv], d]
    return np.unique(r[r >= 0])


def gen_dispersed(rng, D0, D1, n, tilt=True, spacing=40):
    pool = G["pool"]
    rows = seg_rows(D0, D1)
    if tilt:
        vd = G["vdec_pool"][pool.sym[rows]]
        w = G["date_w"][pool.d[rows]] * np.where(vd >= 0, G["dec_w"][np.maximum(vd, 0)], 1e-3)
    else:
        w = np.ones(len(rows))
    m = min(len(rows), int(n * 4) + 100)
    key = -np.log(rng.random(len(rows))) / w           # 指数钥匙：按权重无放回抽样
    pick = rows[np.argpartition(key, m - 1)[:m]]
    pk = key[np.argpartition(key, m - 1)[:m]]
    o = np.argsort(pk); pick = pick[o]
    if spacing:
        keep = np.zeros(len(pick), bool)
        last = {}
        for i, r in enumerate(pick):                    # 按抽中顺序，同一只股票 spacing 天内不重复
            s, dd = pool.sym[r], pool.d[r]
            lst = last.get(s)
            if lst is None or all(abs(dd - x) >= spacing for x in lst):
                keep[i] = True
                last.setdefault(s, []).append(dd)
            if keep.sum() >= n:
                break
        pick = pick[keep]
    return np.sort(pick[:n])


def stats(rows, D0, D1):
    pool = G["pool"]
    pdates = core.plan_dates(pool, D0, D1)
    Z, B, delta, nwin = core.v3_delta(pool, rows, pdates)
    amp, med, ctrl = core.amp_lead(pool, rows)
    return dict(N=len(rows), stocks=int(len(np.unique(pool.sym[rows]))), delta=delta,
                pooled=core.pooled_dir_lead(pool, rows), touched=float((pool.dir[rows] != 0).mean()),
                amp=amp, amp_med=med, amp_ctrl=ctrl, amp_excess=core.amp_lead_excess(pool, rows),
                vdec_mean=float(G["vdec_pool"][pool.sym[rows]].mean()))


def run_task(task):
    cfg, items = task
    out = []
    for idx, seed in items:
        rng = np.random.default_rng(seed)
        Y = cfg["Y"]
        span = int(round(Y * 252))
        D0 = int(rng.integers(G["dmin"], G["dmax"] - span + 2)); D1 = D0 + span - 1
        if cfg["kind"] == "clustered":
            rows = gen_clustered(rng, D0, D1, cfg["q"])
        elif cfg["kind"] == "dispersed":
            rows = gen_dispersed(rng, D0, D1, int(round(cfg["rate"] * Y)), tilt=True)
        else:
            rows = gen_dispersed(rng, D0, D1, int(round(cfg["rate"] * Y)), tilt=False, spacing=0)
        if len(rows) < 2:
            continue
        out.append({**cfg, "seed": seed, "D0": D0, "D1": D1, **stats(rows, D0, D1)})
    return out


def configs(sims):
    cs = []
    max_years = (G["dmax"] - G["dmin"] + 1) / 252
    for Y in [y for y in (1, 2, 4) if y <= max_years]:
        for q in (1, 0.3, 0.1, 0.03):
            cs.append(dict(kind="clustered", q=q, rate=np.nan, Y=Y, sims=sims))
        for rate in (100, 300, 1000, 3000):
            cs.append(dict(kind="dispersed", q=np.nan, rate=rate, Y=Y, sims=sims))
    cs.append(dict(kind="indep", q=np.nan, rate=1000, Y=2, sims=max(50, sims // 2)))
    return cs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pool")
    ap.add_argument("H", type=int)
    ap.add_argument("--k", type=float, default=5.0)
    ap.add_argument("--sims", type=int, default=200)
    ap.add_argument("--workers", type=int, default=20)
    a = ap.parse_args()
    t0 = time.time()
    prepare(a.pool, a.H, a.k)
    pool = G["pool"]
    print(f"{a.pool} H={a.H} k={a.k:g}: rows {len(pool.d):,}, stocks {len(np.unique(pool.sym))}, "
          f"touched {(pool.dir != 0).mean():.3f}, ready {time.time() - t0:.0f}s", flush=True)
    cs = configs(a.sims)
    tasks = []
    for ci, cfg in enumerate(cs):
        cfg["cid"] = ci
        base = 1_000_003 * (ci + 1) + 7919 * a.H + 104729 * (zlib.crc32(a.pool.encode()) % 1000)
        seeds = [(i, base + i) for i in range(cfg["sims"])]
        for j in range(0, len(seeds), 20):
            tasks.append((cfg, seeds[j:j + 20]))
    with get_context("fork").Pool(a.workers) as mp:
        res = mp.map(run_task, tasks, chunksize=1)
    df = pd.DataFrame([r for chunk in res for r in chunk])
    df["pool"] = a.pool; df["H"] = a.H; df["k"] = a.k
    name = f"09-sim-{a.pool}-H{a.H}_k{a.k:g}.csv.gz"
    df.to_csv(HERE / name, index=False)
    g = df.groupby("cid").agg(kind=("kind", "first"), q=("q", "first"), rate=("rate", "first"), Y=("Y", "first"),
                              N=("N", "median"), stocks=("stocks", "median"), sd_delta=("delta", "std"),
                              mean_delta=("delta", "mean"), sd_amp=("amp", "std"), mean_amp=("amp", "mean"))
    print(g.round(4).to_string())
    print(f"done {time.time() - t0:.0f}s → {name}")


if __name__ == "__main__":
    main()
