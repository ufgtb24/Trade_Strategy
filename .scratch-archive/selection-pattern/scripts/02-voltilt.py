"""02 分辨力研究 · 副产品核查：只偏好某种波动水平、毫无选股能力的假 pattern，能白得多少领先？分档切细能否堵上？

假 pattern：两年里随机抽 2000 个股票日，但只从「平时波动水平」（每只股票 M 的中位数，全部股票分十档）
在某一档的股票里抽。分别用同日按 M 切 5 档（v3 现行）、10 档、20 档的对照算方向领先（合并口径）与
幅度领先（中位数之差），各重复 100 次取平均。H=40、k=5。
输出：打印 + scripts/02-voltilt.txt
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("core02", HERE / "02-core.py")
core = importlib.util.module_from_spec(spec); sys.modules["core02"] = core; spec.loader.exec_module(core)


def rebin(pool, nb):
    """同日按 M 切 nb 档（与 v3 同一切法，只改分位数个数），返回新的档号与档内统计。"""
    d, M = pool.d, pool.M
    bounds = np.flatnonzero(np.diff(d)) + 1
    starts = np.concatenate(([0], bounds)); ends = np.concatenate((bounds, [len(d)]))
    qs = np.arange(1, nb) / nb
    b = np.empty(len(d), np.int64)
    for s, e in zip(starts, ends):
        cuts = np.unique(np.quantile(M[s:e], qs))
        b[s:e] = np.searchsorted(cuts, M[s:e], side="left")
    g = d.astype(np.int64) * nb + b
    n = int(g.max()) + 1
    cnt = np.bincount(g, minlength=n).astype(float)
    bdir = np.divide(np.bincount(g, weights=pool.dir.astype(float), minlength=n), cnt, out=np.zeros(n), where=cnt > 0)
    order = np.argsort(pool.up, kind="stable")
    return g, cnt, bdir, order


def amp(pool, rows, g, cnt, order):
    c = np.bincount(g[rows], minlength=len(cnt)).astype(float)
    wb = np.divide(c, cnt, out=np.zeros_like(c), where=cnt > 0)
    gs = g[order]; mask = c[gs] > 0
    ws = wb[gs[mask]]; cw = np.cumsum(ws)
    ctrl = pool.up[order][mask][np.searchsorted(cw, cw[-1] / 2)]
    return np.median(pool.up[rows]) - ctrl


def main():
    pool = core.load_pool(40)
    vdec = pd.qcut(pd.Series(pool.stock_vol).rank(method="first"), 10, labels=False).to_numpy()
    rng = np.random.default_rng(5)
    bins = {nb: rebin(pool, nb) for nb in (5, 10, 20)}
    out = ["平时波动档(0最低..9最高) | 方向领先 5档/10档/20档 | 幅度领先 5档/10档/20档（H=40，2 年 2000 买点，100 次平均）"]
    span = 504
    for dec in range(10):
        res = {nb: ([], []) for nb in bins}
        for _ in range(100):
            D0 = int(rng.integers(pool.dates_present.min(), pool.dates_present.max() - span + 2))
            rows = np.arange(np.searchsorted(pool.d, D0), np.searchsorted(pool.d, D0 + span))
            rows = rows[vdec[pool.sym[rows]] == dec]
            rows = rng.choice(rows, 2000, replace=False)
            for nb, (g, cnt, bdir, order) in bins.items():
                res[nb][0].append(float((pool.dir[rows] - bdir[g[rows]]).mean()))
                res[nb][1].append(float(amp(pool, rows, g, cnt, order)))
        out.append(f"  档 {dec}: 方向 " + " / ".join(f"{np.mean(res[nb][0]):+.3f}" for nb in bins)
                   + " | 幅度 " + " / ".join(f"{np.mean(res[nb][1]):+.4f}" for nb in bins))
    text = "\n".join(out)
    print(text)
    (HERE / "02-voltilt.txt").write_text(text + "\n")


if __name__ == "__main__":
    main()
