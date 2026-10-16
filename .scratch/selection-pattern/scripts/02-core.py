"""02 分辨力研究 · 公共计算：读普通买入标签、同日普通买入对照、两种领先的计算。

口径（全部照 tune-gates-v3 / path2/eval.py，不自造）：
- 标签：v3 `_daily_close_labels`（收盘首次穿越 +1/0/-1、前瞻收益 max(high[t+1..t+H])/close[t]-1、M）。
- 同日普通买入对照：每个交易日按 M 切至多五档（v3 WindowPlan 同一切法：当日 M 的 20/40/60/80 分位、
  去重后 searchsorted left），档内全部普通买入的方向均值。
- 方向领先（v3 口径）：21 个交易日滚动窗口，窗口内（先上−先下）/买点数，减同窗口对照，窗口间按
  2^(-相对年龄/252) 近期权重平均（只在有买点的窗口上归一）= v3 的 Δ = Z − B。
- 方向领先（合并口径）：全部买点的方向值均值 − 各买点所在档对照均值的均值（不分窗口、不加权）。
- 幅度领先（本研究补的口径，v3 未定义）：买点前瞻收益中位数 − 「同日同档普通买入混合分布」的中位数；
  混合分布里每个档按该档买点个数加权（与方向对照的配比相同）。另算一个检查口径：
  买点「前瞻收益 − 所在档中位数」的中位数。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad/02cache")
WINDOW_DAYS, HALF_LIFE = 21, 252.0


@dataclass
class Pool:
    H: int
    k: float
    sym: np.ndarray
    d: np.ndarray
    M: np.ndarray
    dir: np.ndarray
    up: np.ndarray
    gbin: np.ndarray          # 全局档号 = 日期*5 + 档
    bin_cnt: np.ndarray
    bin_dir: np.ndarray       # 档内方向均值（对照）
    bin_up_med: np.ndarray    # 档内前瞻收益中位数
    e_dir: np.ndarray         # 方向值 − 所在档均值
    e_up: np.ndarray          # 前瞻收益 − 所在档中位数
    u_rank: np.ndarray        # 前瞻收益在所在档内的分位（0..1）
    rowidx: np.ndarray        # [股票, 交易日] → 行号，无则 -1
    order_up: np.ndarray
    up_sorted: np.ndarray
    gbin_sorted: np.ndarray
    dates_present: np.ndarray
    calendar: np.ndarray
    symbols: np.ndarray
    stock_vol: np.ndarray     # 每只股票 M 的中位数（波动水平）
    stock_first: np.ndarray
    stock_last: np.ndarray


def load_pool(H: int, k: float = 5.0) -> Pool:
    meta = np.load(CACHE / "meta.npz", allow_pickle=True)
    z = np.load(CACHE / f"labels_H{H}_k{k:g}.npz")
    sym, d = z["sym"].astype(np.int32), z["d"].astype(np.int32)
    M, dr, up = z["M"].astype(np.float64), z["dir"].astype(np.int8), z["up"].astype(np.float64)
    n = len(d)
    # 行已按 (日期, 股票) 排序；逐日切五档（v3 WindowPlan 同一切法）
    bounds = np.flatnonzero(np.diff(d)) + 1
    starts = np.concatenate(([0], bounds)); ends = np.concatenate((bounds, [n]))
    binv = np.empty(n, np.int32)
    for s, e in zip(starts, ends):
        vol = M[s:e]
        cuts = np.unique(np.quantile(vol, [0.2, 0.4, 0.6, 0.8]))
        binv[s:e] = np.searchsorted(cuts, vol, side="left")
    gbin = d * 5 + binv
    nb = int(gbin.max()) + 1
    cnt = np.bincount(gbin, minlength=nb).astype(np.float64)
    bdir = np.divide(np.bincount(gbin, weights=dr.astype(np.float64), minlength=nb), cnt,
                     out=np.zeros(nb), where=cnt > 0)
    df = pd.DataFrame({"g": gbin, "up": up})
    med = df.groupby("g")["up"].median()
    bmed = np.zeros(nb); bmed[med.index.to_numpy()] = med.to_numpy()
    rank = df.groupby("g")["up"].rank(pct=True).to_numpy()
    calendar = meta["calendar"]; symbols = meta["symbols"]
    rowidx = np.full((len(symbols), len(calendar)), -1, np.int32)
    rowidx[sym, d] = np.arange(n, dtype=np.int32)
    order = np.argsort(up, kind="stable")
    sv = pd.Series(M).groupby(sym).median().reindex(range(len(symbols))).to_numpy()
    first = pd.Series(d).groupby(sym).min().reindex(range(len(symbols))).fillna(-1).to_numpy(int)
    last = pd.Series(d).groupby(sym).max().reindex(range(len(symbols))).fillna(-1).to_numpy(int)
    return Pool(H, k, sym, d, M, dr, up, gbin, cnt, bdir, bmed,
                dr - bdir[gbin], up - bmed[gbin], rank, rowidx, order, up[order], gbin[order],
                np.unique(d), calendar, symbols, sv, first, last)


def plan_dates(pool: Pool, D0: int, D1: int) -> np.ndarray:
    dp = pool.dates_present
    return dp[(dp >= D0) & (dp <= D1)]


def v3_delta(pool: Pool, rows: np.ndarray, pdates: np.ndarray, weights: np.ndarray | None = None):
    """v3 的 Z、B、Δ=Z−B（窗口 21 日、近期半衰 252 日、只在有买点的窗口上归一）。

    weights：每行重复次数（整只股票重抽用），缺省 1。返回 (Z, B, Δ, 有买点窗口数)。
    """
    n = len(pdates)
    di = np.searchsorted(pdates, pool.d[rows])
    w = np.ones(len(rows)) if weights is None else weights
    cnt = np.bincount(di, weights=w, minlength=n)
    sdir = np.bincount(di, weights=w * pool.dir[rows], minlength=n)
    smat = np.bincount(di, weights=w * pool.bin_dir[pool.gbin[rows]], minlength=n)
    st = np.arange(n - WINDOW_DAYS + 1); en = st + WINDOW_DAYS - 1

    def roll(v):
        p = np.concatenate(([0.0], np.cumsum(v)))
        return p[en + 1] - p[st]

    c = roll(cnt); act = c > 0
    if not act.any():
        return None, None, None, 0
    z = roll(sdir)[act] / c[act]; b = roll(smat)[act] / c[act]
    age = en[act].max() - en[act]
    tw = np.exp2(-age / HALF_LIFE); tw /= tw.sum()
    Z, B = float(tw @ z), float(tw @ b)
    return Z, B, Z - B, int(act.sum())


def pooled_dir_lead(pool: Pool, rows: np.ndarray) -> float:
    return float(pool.e_dir[rows].mean())


def amp_lead(pool: Pool, rows: np.ndarray) -> tuple[float, float, float]:
    """(买点前瞻收益中位数 − 同日同档混合分布中位数, 买点中位数, 对照中位数)。"""
    c = np.bincount(pool.gbin[rows], minlength=len(pool.bin_cnt)).astype(np.float64)
    wb = np.divide(c, pool.bin_cnt, out=np.zeros_like(c), where=pool.bin_cnt > 0)
    act = c > 0
    mask = act[pool.gbin_sorted]
    ws = wb[pool.gbin_sorted[mask]]
    cw = np.cumsum(ws)
    ctrl = float(pool.up_sorted[mask][np.searchsorted(cw, cw[-1] / 2.0)])
    med = float(np.median(pool.up[rows]))
    return med - ctrl, med, ctrl


def amp_lead_excess(pool: Pool, rows: np.ndarray) -> float:
    """检查口径：买点「前瞻收益 − 所在档中位数」的中位数。"""
    return float(np.median(pool.e_up[rows]))


def stock_bootstrap_v3(pool: Pool, rows: np.ndarray, pdates: np.ndarray, resamples: int = 200,
                       seed: int = 0, n_stocks_frozen: int | None = None) -> float:
    """v3 stock_bootstrap 同法：在冻结的股票集合（默认 = 计划里的全部股票）上整只有放回重抽，
    抽中几次就把该股全部买点计几次，报 Δ 的标准差。"""
    syms = pool.sym[rows]
    n_frozen = n_stocks_frozen
    uniq, codes = np.unique(syms, return_inverse=True)
    rng = np.random.default_rng(seed)
    # 冻结集合里没有买点的股票抽中也不贡献行；只需要对有买点的股票抽次数
    draws = rng.multinomial(n_frozen, np.full(n_frozen, 1 / n_frozen), size=resamples)[:, : len(uniq)]
    out = []
    for dr in draws:
        w = dr[codes].astype(float)
        keep = w > 0
        if not keep.any():
            continue
        _, _, delta, _ = v3_delta(pool, rows[keep], pdates, w[keep])
        out.append(delta)
    return float(np.std(out, ddof=1)) if len(out) > 1 else float("nan")
