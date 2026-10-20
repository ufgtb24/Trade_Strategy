"""11 同日对照配对票 · 公共计算：读面板、算各把尺子的逐笔结果、各种配对的格子 / 近邻、领先与偶然波动。

面板来自 11-panel.py（只读截断副本）。所有计算只用面板里的池内股票日；对照 = 同一天、同一池子。

尺子（见 11-prereg.txt）：
  dir   首次穿越方向值（chart_workflow.labels 口径），领先 = 均值之差
  mag   前瞻收益，领先 = 中位数之差（对照混合中位数）
  R1..R6 主尺子 6 条买卖规则的每笔收益，「典型」= 中位数之差，「平均」= 均值之差
配对方式：
  cell 型：每行一个全局格子号（日期 × 档）；对照 = 同格全部行（含买点自己，同 chart_workflow/control.py）
  knn 型：同一天按（log M，log 平时波动）欧氏距离最近的 K 行（不含自己）
领先：
  均值型 = mean_w(y[买点]) − mean_w(对照均值[买点])
  中位数型 = wmedian(y[买点]) − wmedian(对照混合)；混合里每个买点合计权重 = 它自己的权重
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/28767886-41d8-46a8-b368-50cdb61bd556/scratchpad/11")
HERE = Path(__file__).resolve().parent
CHUNK = 50_000

RULES = {  # 名称: (说明, 类型, 参数)
    "R1": ("固定持有 5 日", "hold", 5),
    "R2": ("固定持有 20 日", "hold", 20),
    "R3": ("固定持有 40 日", "hold", 40),
    "R4": ("波动止损止盈 k=2，40 日到期", "volk", 2.0),
    "R5": ("波动止损止盈 k=5，40 日到期", "volk", 5.0),
    "R6": ("固定 −8% / +20%，40 日到期", "pct", (np.log(0.92), np.log(1.20))),
}
MEAN_METRICS = ["dir"] + [f"{r}_mean" for r in RULES]
MED_METRICS = ["mag"] + [f"{r}_med" for r in RULES]
METRICS = ["dir", "mag"] + [f"{r}_{t}" for r in RULES for t in ("med", "mean")]
METRIC_NAME = {"dir": "方向（首次穿越）", "mag": "幅度（前瞻收益中位）"}
for _r, (_desc, _, _) in RULES.items():
    METRIC_NAME[f"{_r}_med"] = f"{_r} {_desc} · 典型一笔"
    METRIC_NAME[f"{_r}_mean"] = f"{_r} {_desc} · 平均一笔"


def base_col(metric: str) -> str:
    """指标 → 逐行数值所在的列（R1_med 与 R1_mean 都读 R1）。"""
    return metric.split("_")[0] if metric.startswith("R") else metric


def exit_trade(lp: np.ndarray, lo, hi, chunk: int = 100_000):
    """按收盘离场：第一个 lp ≤ lo 或 ≥ hi 的观察日当日收盘卖，否则第 40 日收盘卖。

    lp：N×40 的 ln(close[t+j]/P)；lo、hi：标量或长 N 的对数线。返回 (每笔收益, 持有天数, 是否触线)。"""
    n, H = lp.shape
    lo = np.broadcast_to(np.asarray(lo, float), (n,))
    hi = np.broadcast_to(np.asarray(hi, float), (n,))
    ret = np.empty(n); hold = np.empty(n, np.int16); touched = np.empty(n, bool)
    for s in range(0, n, chunk):
        e = min(n, s + chunk)
        x = lp[s:e].astype(np.float64)
        hit = (x <= lo[s:e, None]) | (x >= hi[s:e, None])
        has = hit.any(1)
        j = np.where(has, hit.argmax(1), H - 1)
        ret[s:e] = np.expm1(x[np.arange(e - s), j])
        hold[s:e] = j + 1
        touched[s:e] = has
    return ret, hold, touched


def load_panel() -> dict:
    z = np.load(SCR / "panel.npz", allow_pickle=True)
    P = {k: z[k] for k in z.files}
    P["Mhm"] = np.where(np.isfinite(P["Mh"]), P["Mh"], P["Mh_fb"])
    d = P["d"]
    P["N"] = len(d)
    P["day_start"] = np.searchsorted(d, np.arange(len(P["calendar"])), side="left")
    P["day_end"] = np.searchsorted(d, np.arange(len(P["calendar"])), side="right")
    P["year"] = pd.DatetimeIndex(P["calendar"]).year.values[d]
    return P


def outcomes(P: dict) -> dict:
    """逐行结果：dir、mag、R1..R6 的每笔收益与持有天数。"""
    lp = P["lp"]
    Y = {"dir": P["dir"].astype(np.float64), "mag": P["mag"].astype(np.float64)}
    hold = {}
    for r, (_, kind, par) in RULES.items():
        if kind == "hold":
            Y[r] = np.expm1(lp[:, par - 1].astype(np.float64))
            hold[r] = np.full(P["N"], par, np.int16)
        elif kind == "volk":
            w = np.log1p(par * P["M"])
            Y[r], hold[r], _ = exit_trade(lp, -w, w)
        else:
            Y[r], hold[r], _ = exit_trade(lp, par[0], par[1])
    return Y, hold


def day_rank(P: dict, x: np.ndarray) -> np.ndarray:
    """同一天池内的分位（0..1，NaN 不参与、结果为 NaN）。"""
    s = pd.Series(x)
    return s.groupby(P["d"]).rank(pct=True).to_numpy()


# ---------------- 配对方式 ----------------

def cells_band(P: dict, nb: int, min_per_band: int = 20) -> np.ndarray:
    """chart_workflow/control.py 的 assign_bands（逐字调用），按 M 切至多 nb 档。"""
    import sys
    sys.path.insert(0, str(ROOT))
    from chart_workflow.control import assign_bands
    df = pd.DataFrame({"date": P["calendar"][P["d"]], "M": P["M"]})
    return assign_bands(df, max_bands=nb, min_per_band=min_per_band)


def cells_nested(P: dict, a: int, b: int) -> np.ndarray:
    """先按 M 在当天等分 a 档，再在每档里按平时波动（配对版）等分 b 档。"""
    d = P["d"]
    rM = pd.Series(P["M"]).groupby(d).rank(method="first").to_numpy() - 1
    n_day = np.bincount(d)[d]
    outer = np.minimum((rM * a // n_day).astype(np.int64), a - 1)
    key = d.astype(np.int64) * a + outer
    rH = pd.Series(P["Mhm"]).groupby(key).rank(method="first").to_numpy() - 1
    _, inv = np.unique(key, return_inverse=True)
    n_out = np.bincount(inv)[inv]
    inner = np.minimum((rH * b // n_out).astype(np.int64), b - 1)
    g = key * b + inner
    return np.unique(g, return_inverse=True)[1].astype(np.int64)


def knn_neighbors(P: dict, kmax: int = 100) -> np.ndarray:
    """每行同一天在（log M，log 平时波动）上最近的 kmax 行（不含自己），按距离从近到远。"""
    x = np.log(P["M"]); y = np.log(np.maximum(P["Mhm"], 1e-3))   # 极少数平时波动为 0 的行（69 行）下限 0.1%
    out = np.full((P["N"], kmax), -1, np.int32)
    for t in range(len(P["calendar"])):
        s, e = P["day_start"][t], P["day_end"][t]
        n = e - s
        if n == 0:
            continue
        k = min(kmax, n - 1)
        dx = x[s:e, None] - x[None, s:e]; dy = y[s:e, None] - y[None, s:e]
        dist = dx * dx + dy * dy
        np.fill_diagonal(dist, np.inf)
        part = np.argpartition(dist, k - 1, axis=1)[:, :k]
        dd = np.take_along_axis(dist, part, 1)
        o = np.argsort(dd, axis=1, kind="stable")
        out[s:e, :k] = (np.take_along_axis(part, o, 1) + s).astype(np.int32)
    return out


# ---------------- 领先 ----------------

class Matcher:
    """一种配对方式下的对照。kind = 'cell'（cell 数组）或 'knn'（近邻矩阵 + K）。"""

    def __init__(self, name: str, P: dict, Y: dict, cell=None, neigh=None, K=None):
        self.name, self.P, self.Y = name, P, Y
        self.kind = "cell" if cell is not None else "knn"
        N = P["N"]
        if self.kind == "cell":
            self.cell = cell
            self.ncell = int(cell.max()) + 1
            self.cnt = np.bincount(cell, minlength=self.ncell).astype(np.float64)
            self.size = self.cnt[cell]                        # 每行所在格的对照个数
            self.ctrl_mean = {}
            for m in MEAN_METRICS:
                v = Y[base_col(m)]
                self.ctrl_mean[m] = (np.bincount(cell, weights=v, minlength=self.ncell) / self.cnt)[cell]
        else:
            self.nb = neigh[:, :K]
            self.K = K
            valid = self.nb >= 0
            self.size = valid.sum(1).astype(np.float64)
            self.ctrl_mean = {m: np.empty(N) for m in MEAN_METRICS}
            for s in range(0, N, CHUNK):
                e = min(N, s + CHUNK)
                nb = self.nb[s:e]; ok = nb >= 0; nb0 = np.maximum(nb, 0)
                for m in MEAN_METRICS:
                    v = Y[base_col(m)]
                    self.ctrl_mean[m][s:e] = np.where(ok, v[nb0], 0.0).sum(1) / np.maximum(self.size[s:e], 1)

    def mixture_weights(self, rows: np.ndarray, w: np.ndarray | None = None, pw: np.ndarray | None = None,
                        span: tuple[int, int] | None = None):
        """对照混合在行 [lo, hi) 上的权重（买点同一天的对照都落在这段里）。w：买点权重；
        pw：对照成员的 Poisson 重抽权重（抖动用，长 N）。返回长 hi−lo 的数组。"""
        lo, hi = span if span is not None else (0, self.P["N"])
        w = np.ones(len(rows)) if w is None else w
        if self.kind == "cell":
            c0 = int(self.cell[lo:hi].min()); cs = self.cell[lo:hi] - c0
            nc = int(cs.max()) + 1
            hc = np.bincount(self.cell[rows] - c0, weights=w, minlength=nc)
            if pw is None:
                return hc[cs] / self.cnt[cs + c0]
            W = np.bincount(cs, weights=pw[lo:hi], minlength=nc)
            with np.errstate(invalid="ignore", divide="ignore"):
                f = np.where(W > 0, hc / W, 0.0)
            return pw[lo:hi] * f[cs]
        out = np.zeros(hi - lo)
        for s in range(0, len(rows), CHUNK):
            r = rows[s:s + CHUNK]; wr = w[s:s + CHUNK]
            nb = self.nb[r]
            valid = nb >= 0
            if pw is None:
                ww = np.where(valid, (wr / np.maximum(self.size[r], 1))[:, None], 0.0)
            else:
                pv = np.where(valid, pw[np.maximum(nb, 0)], 0.0)
                S = pv.sum(1)
                ww = np.where(S[:, None] > 0, pv * (wr / np.where(S > 0, S, 1))[:, None], 0.0)
            out += np.bincount(np.where(valid, nb - lo, 0).ravel(), weights=ww.ravel(), minlength=hi - lo)
        return out

    def ctrl_mean_pw(self, rows: np.ndarray, metric: str, pw: np.ndarray, span=None) -> np.ndarray:
        """Poisson 重抽对照成员后，每个买点的对照均值。"""
        v = self.Y[base_col(metric)]
        if self.kind == "cell":
            lo, hi = span if span is not None else (0, self.P["N"])
            c0 = int(self.cell[lo:hi].min()); cs = self.cell[lo:hi] - c0
            nc = int(cs.max()) + 1
            W = np.bincount(cs, weights=pw[lo:hi], minlength=nc)
            S = np.bincount(cs, weights=pw[lo:hi] * v[lo:hi], minlength=nc)
            c = self.cell[rows] - c0
            return np.where(W[c] > 0, S[c] / np.where(W[c] > 0, W[c], 1), self.ctrl_mean[metric][rows])
        nb = self.nb[rows]
        valid = nb >= 0
        pv = np.where(valid, pw[np.maximum(nb, 0)], 0.0)
        S = pv.sum(1)
        num = (pv * v[np.maximum(nb, 0)]).sum(1)
        return np.where(S > 0, num / np.where(S > 0, S, 1), self.ctrl_mean[metric][rows])


class Sorted:
    """每个中位数型指标的排序（全局一份、每年一份），用来线性时间算加权中位数。"""

    def __init__(self, Y: dict, year: np.ndarray | None = None):
        self.order, self.vals, self.N = {}, {}, None
        self.years = []                      # (起行, 止行, {指标: 年内排序}, {指标: 排好的值})
        for m in MED_METRICS:
            v = Y[base_col(m)]
            self.N = len(v)
            o = np.argsort(v, kind="stable")
            self.order[m] = o
            self.vals[m] = v[o]
        if year is not None:
            b = np.flatnonzero(np.diff(year)) + 1
            st = np.concatenate(([0], b)); en = np.concatenate((b, [len(year)]))
            for s0, e0 in zip(st, en):
                oy = {m: np.argsort(Y[base_col(m)][s0:e0], kind="stable") for m in MED_METRICS}
                vy = {m: Y[base_col(m)][s0:e0][oy[m]] for m in MED_METRICS}
                self.years.append((int(s0), int(e0), oy, vy))

    def wmedian(self, metric: str, wspan: np.ndarray, lo: int = 0, hi: int | None = None) -> float:
        """wspan：行 [lo, hi) 上的权重。累计权重第一次 ≥ 一半处的值（恰好一半时与下一个取平均）。"""
        hi = self.N if hi is None else hi
        for s0, e0, oy, vy in self.years:
            if s0 <= lo and hi <= e0:
                wy = np.zeros(e0 - s0); wy[lo - s0:hi - s0] = wspan
                return _wmed_sorted(wy[oy[metric]], vy[metric])
        wf = np.zeros(self.N); wf[lo:hi] = wspan
        return _wmed_sorted(wf[self.order[metric]], self.vals[metric])


def _wmed_sorted(ws: np.ndarray, v: np.ndarray) -> float:
    cw = np.cumsum(ws)
    tot = cw[-1]
    if tot <= 0:
        return np.nan
    half = tot / 2.0
    i = int(np.searchsorted(cw, half - 1e-12 * tot, side="left"))
    i = min(i, len(cw) - 1)
    if abs(cw[i] - half) <= 1e-9 * tot:
        j = i + 1
        while j < len(cw) and ws[j] <= 0:
            j += 1
        if j < len(cw):
            return float((v[i] + v[j]) / 2.0)
    return float(v[i])


def wmedian_small(v: np.ndarray, w: np.ndarray) -> float:
    o = np.argsort(v, kind="stable")
    v, w = v[o], w[o]
    cw = np.cumsum(w)
    half = cw[-1] / 2.0
    i = int(np.searchsorted(cw, half - 1e-12 * cw[-1], side="left"))
    i = min(i, len(v) - 1)
    if abs(cw[i] - half) <= 1e-9 * cw[-1] and i + 1 < len(v):
        return float((v[i] + v[i + 1]) / 2.0)
    return float(v[i])


def leads(mt: Matcher, S: Sorted, rows: np.ndarray, w: np.ndarray | None = None,
          metrics=METRICS, pw: np.ndarray | None = None) -> dict:
    """一组买点（行号，可带权重）在一种配对下各把尺子的领先。"""
    Y, P = mt.Y, mt.P
    w = np.ones(len(rows)) if w is None else np.asarray(w, float)
    dd = P["d"][rows]
    span = (int(P["day_start"][dd.min()]), int(P["day_end"][dd.max()]))
    out = {}
    mix = None
    for m in metrics:
        v = Y[base_col(m)]
        if m in MEAN_METRICS:
            hit = float(np.average(v[rows], weights=w))
            c = mt.ctrl_mean[m][rows] if pw is None else mt.ctrl_mean_pw(rows, m, pw, span)
            out[m] = hit - float(np.average(c, weights=w))
        else:
            if mix is None:
                mix = mt.mixture_weights(rows, w, pw, span)
            hit = wmedian_small(v[rows], w)
            out[m] = hit - S.wmedian(m, mix, *span)
    return out


def hold_mean(hold: dict, rows: np.ndarray) -> dict:
    return {r: float(hold[r][rows].mean()) for r in RULES}


# ---------------- 抽样 ----------------

def dispersed_sample(P: dict, cand: np.ndarray, n: int, rng, spacing: int = 40) -> np.ndarray:
    """从候选行里随机抽 n 个，同一只股票 spacing 个交易日内不重复买（按随机顺序贪心）。"""
    if len(cand) == 0 or n <= 0:
        return np.array([], np.int64)
    perm = cand[rng.permutation(len(cand))]
    sym, d = P["sym"], P["d"]
    last: dict = {}
    keep = []
    for r in perm:
        s = int(sym[r]); t = int(d[r])
        lst = last.get(s)
        if lst is None or all(abs(t - x) >= spacing for x in lst):
            keep.append(r)
            last.setdefault(s, []).append(t)
            if len(keep) >= n:
                break
    return np.sort(np.array(keep, np.int64))


def stock_boot_weights(P: dict, rows: np.ndarray, rng) -> np.ndarray:
    """整只股票有放回重抽：返回每个买点的重复次数。"""
    uniq, inv = np.unique(P["sym"][rows], return_inverse=True)
    cnt = rng.multinomial(len(uniq), np.full(len(uniq), 1.0 / len(uniq)))
    return cnt[inv].astype(np.float64)


# ---------------- 一次装好全部配对（父进程装好后 fork，子进程共享内存） ----------------

SCHEMES = ["M5", "M10", "M20", "M3xH3", "M5xH5", "M10xH3", "M10xH5", "M20xH3",
           "K10", "K20", "K50", "K100"]


def load_all(schemes=SCHEMES):
    P = load_panel()
    z = np.load(SCR / "build.npz")
    Y = {k[2:]: z[k] for k in z.files if k.startswith("Y_")}
    hold = {k[5:]: z[k] for k in z.files if k.startswith("hold_")}
    neigh = z["neigh"] if any(s.startswith("K") for s in schemes) else None
    mts = {}
    for s in schemes:
        if s.startswith("K"):
            mts[s] = Matcher(s, P, Y, neigh=neigh, K=int(s[1:]))
        else:
            mts[s] = Matcher(s, P, Y, cell=z[f"cell_{s}"])
    return P, Y, hold, mts, Sorted(Y, P["year"])
