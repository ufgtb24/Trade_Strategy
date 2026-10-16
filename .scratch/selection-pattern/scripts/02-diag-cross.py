"""02 分辨力研究 · 不独立的另一来源：不同股票、相近日期、走势相似时，结果是否一起偏。

1. 用全部股票的日收益（减去当日全市场中位数）算两两相关，当作「走势相似度」——只用价格，不用任何 pattern 成绩。
2. 在普通买入池里随机抽「同一天或相隔不到 H 天」的不同股票对，按相似度分桶，看方向残差 / 幅度残差的乘积均值
   （除以方差 = 跨股相关系数）。
3. 现役 pattern 的买点（只取位置）：同一天、不同股票的买点对，相似度平均多少；与随机股票对相比高多少。
   再用第 2 步的「相似度 → 跨股相关」表，估计这种扎堆给领先的偶然波动额外加多少（以方差占比计）。
输出：打印 + scripts/02-diag-cross.txt
"""
from __future__ import annotations

import importlib.util
import sys
from multiprocessing import Pool as MPool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location("core02", HERE / "02-core.py")
core = importlib.util.module_from_spec(spec); sys.modules["core02"] = core; spec.loader.exec_module(core)
DATA = ROOT / "datasets/pkls"


def closes(symbol):
    raw = pd.read_pickle(DATA / f"{symbol}.pkl")
    return pd.DatetimeIndex(raw.index).normalize().to_numpy(), raw["close"].to_numpy(float)


def similarity(pool) -> np.ndarray:
    cache = core.CACHE / "corr.npy"
    if cache.exists():
        return np.load(cache)
    with MPool(24) as mp:
        res = mp.map(closes, list(pool.symbols), chunksize=32)
    R = np.full((len(pool.symbols), len(pool.calendar)), np.nan, np.float32)
    for i, (dates, c) in enumerate(res):
        di = np.searchsorted(pool.calendar, dates)
        lr = np.full(len(c), np.nan); lr[1:] = np.log(c[1:] / c[:-1])
        R[i, di] = lr
    R = R - np.nanmedian(R, axis=0, keepdims=True)
    R = np.clip(R, -0.5, 0.5)
    mu = np.nanmean(R, axis=1, keepdims=True); sd = np.nanstd(R, axis=1, keepdims=True)
    X = np.nan_to_num((R - mu) / np.where(sd > 0, sd, 1), nan=0.0).astype(np.float32)
    n = (~np.isnan(R)).astype(np.float32)
    C = (X @ X.T) / np.maximum(n @ n.T, 20)
    np.fill_diagonal(C, 1.0)
    np.save(cache, C.astype(np.float32))
    return C


def main():
    out = []
    pool = core.load_pool(40)
    C = similarity(pool)
    off = C[np.triu_indices(len(C), 1)]
    out.append(f"走势相似度（残差日收益相关）全部股票对：均值 {off.mean():.3f}  p90 {np.quantile(off, .9):.3f}  p99 {np.quantile(off, .99):.3f}")
    rng = np.random.default_rng(0)
    for H in (20, 40, 120):
        pool = core.load_pool(H)
        n = len(pool.d)
        # 随机抽一个买点，再在 ±H 天内找另一只股票的买点；按相似度分桶
        a = rng.integers(0, n, 3_000_000)
        gap = rng.integers(-(H - 1), H, len(a))
        other = rng.integers(0, len(pool.symbols), len(a))
        d2 = pool.d[a] + gap
        ok = (d2 >= 0) & (d2 < pool.rowidx.shape[1]) & (other != pool.sym[a])
        a, d2, other = a[ok], d2[ok], other[ok]
        b = pool.rowidx[other, d2]; ok = b >= 0
        a, b = a[ok], b[ok]
        sim = C[pool.sym[a], pool.sym[b]]
        same_day = pool.d[a] == pool.d[b]
        edir = pool.e_dir[a] * pool.e_dir[b] / pool.e_dir.var()
        eu = (pool.u_rank[a] - .5) * (pool.u_rank[b] - .5) / (pool.u_rank - .5).var()
        edges = [-1, 0.0, 0.1, 0.2, 0.3, 0.5, 1.01]
        gedges = [0, 1, 6, 16, 10_000]           # 相隔天数分桶：同一天 / 1-5 / 6-15 / 16..H-1
        bucket = np.digitize(sim, edges) - 1
        gb = np.digitize(np.abs(pool.d[a] - pool.d[b]), gedges) - 1
        out.append(f"\nH={H}：不同股票、相隔不到 H 天的普通买入对（{len(a):,} 对）——按走势相似度分桶的跨股相关（方向 / 幅度）")
        rho_dir = np.zeros((len(edges) - 1, len(gedges) - 1)); rho_amp = np.zeros_like(rho_dir)
        for bk in range(len(edges) - 1):
            cells = []
            for g in range(len(gedges) - 1):
                m = (bucket == bk) & (gb == g)
                rho_dir[bk, g] = edir[m].mean() if m.any() else 0.0
                rho_amp[bk, g] = eu[m].mean() if m.any() else 0.0
                cells.append(f"隔{gedges[g]}-{min(gedges[g + 1] - 1, H - 1)}天 {rho_dir[bk, g]:+.3f}/{rho_amp[bk, g]:+.3f}")
            out.append(f"  相似度 [{edges[bk]:.1f},{edges[bk + 1]:.1f}) 占比 {(bucket == bk).mean():.3f}: " + "  ".join(cells))
        out.append(f"  全部随机对：方向相关 {edir.mean():+.4f}  幅度相关 {eu.mean():+.4f}；同一天的对：方向 {edir[same_day].mean():+.4f} 幅度 {eu[same_day].mean():+.4f}")
        if H != 40:
            continue
        for app in ("bottom_burst", "bb_v1"):
            buys = pd.read_csv(core.CACHE / f"buys_{app}.csv")
            si = pd.Index(pool.symbols).get_indexer(buys["symbol"])
            di = np.searchsorted(pool.calendar, pd.to_datetime(buys["date"]).to_numpy())
            r = pool.rowidx[si, di]; r = r[r >= 0]
            s, d = pool.sym[r], pool.d[r]
            # 相隔不到 H 天的不同股票对：相似度分布
            order = np.argsort(d); s, d = s[order], d[order]
            pa, pb = [], []
            j0 = 0
            for i in range(len(d)):
                while d[j0] <= d[i] - H:
                    j0 += 1
                js = np.arange(j0, i)
                js = js[s[js] != s[i]]
                pa.append(np.full(len(js), i)); pb.append(js)
            pa = np.concatenate(pa); pb = np.concatenate(pb)
            sim_p = C[s[pa], s[pb]]
            bk = np.digitize(sim_p, edges) - 1
            g2 = np.digitize(np.abs(d[pa] - d[pb]), gedges) - 1
            # 同样日期结构下换成随机股票：相似度按全部随机对的分布 → 期望相关取各桶按占比加权
            share = np.array([(bucket == q).mean() for q in range(len(edges) - 1)])
            base_dir = share @ rho_dir; base_amp = share @ rho_amp   # 每个相隔天数桶一个基准
            extra_dir = 2 * (rho_dir[bk, g2] - base_dir[g2]).sum() / len(r)
            extra_amp = 2 * (rho_amp[bk, g2] - base_amp[g2]).sum() / len(r)
            out.append(f"  {app}：相隔不到 {H} 天的不同股票买点对 {len(pa):,}，相似度均值 {sim_p.mean():.3f}（全部股票对 {off.mean():.3f}）"
                       f"；按分桶相关估计，走势相似给方差额外乘上 1+{extra_dir:.2f}（方向）/ 1+{extra_amp:.2f}（幅度）（以独立买点为 1 计）")
    text = "\n".join(out)
    print(text)
    (HERE / "02-diag-cross.txt").write_text(text + "\n")


if __name__ == "__main__":
    main()
