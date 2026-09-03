"""S8: 回应 skeptic「exceed_threshold 不是合法的调松代理」——用**局部极值算子**的参数做等价类。

skeptic 的质疑（成立）：measure 换的是求 argmax 用的算子，同时改 peak 的**价位**和**位置**；
`exceed_threshold` 只改价位，一个 peak 的 bar 都不会移动。所以拿它当「等价放松」的对手偏弱。

本脚本把等价类换成真正能改变「哪些 bar 成为 peak」的三个参数：
  total_window / min_side_bars / min_relative_height     （peak_measure 恒 high）
在 3×3×3 网格上找与「high ∪ close 并集」bo 数最接近的一档，比较两者的**边际 bo**
（各自相对 base 新增的那批）的 label。若不可区分 ⇒ 多 measure 仍不是新自由度。

label 口径同 path2/eval.py 官方（mfr_40 / first-passage k=5 / M=ATR%(20)）。
"""
from __future__ import annotations

import itertools
import pickle
import random
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("/home/yu/PycharmProjects/Trade_Strategy-tune_v1")
sys.path.insert(0, str(REPO))

from path2.atoms.breakout import BODetector                          # noqa: E402
from path2.calc.atr import FP_ATR_WINDOW, rolling_atr_pct_nanmedian  # noqa: E402
from path2.eval import _first_passage_at                             # noqa: E402
from path2_web.data import slice_window                              # noqa: E402

PKL_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END = "2021-01-01", "2026-03-08"
HORIZON, FP_K = 40, 5.0

BASE = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
            exceed_threshold=0.003, peak_supersede_threshold=0.01,
            vol_baseline_period=63, breakout_measure="close")

GRID = [dict(total_window=tw, min_side_bars=ms, min_relative_height=mr)
        for tw, ms, mr in itertools.product((20, 24, 28), (4, 5, 6), (0.10, 0.15, 0.20))]


def process(f):
    try:
        with open(f, "rb") as fh:
            raw = pickle.load(fh)
        if not isinstance(raw, pd.DataFrame):
            return None
        win = slice_window(raw, START, END)
    except Exception:
        return None
    if len(win) < 300:
        return None
    sym = Path(f).stem
    hi, lo, cl = win["high"].values, win["low"].values, win["close"].values
    M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], FP_ATR_WINDOW).values
    n_bars = len(win)

    def bars(pm, **over):
        kw = dict(BASE); kw.update(over)
        return {e.start_idx for e in BODetector(peak_measure=pm, **kw).detect(win)}

    try:
        base = bars("high")
        clo = bars("close")
        grids = {i: bars("high", **g) for i, g in enumerate(GRID)}
    except Exception:
        return None

    union = base | clo
    out = []

    def lab(t, grp):
        if t + HORIZON >= n_bars:
            return None
        fp = _first_passage_at(hi, lo, cl, M, t, HORIZON, FP_K)
        if fp is None:
            return None
        return dict(symbol=sym, bar=t, group=grp,
                    date=str(pd.Timestamp(win["date"].iloc[t]).date()),
                    mfr=float(hi[t + 1:t + HORIZON + 1].max()) / float(cl[t]) - 1.0,
                    fp=fp, M=float(M[t]))

    for t in union - base:                      # 换 measure 换来的边际
        r = lab(t, "marg_measure")
        if r: out.append(r)
    for i in grids:                             # 调算子参数换来的边际
        for t in grids[i] - base:
            r = lab(t, f"marg_g{i:02d}")
            if r: out.append(r)
    counts = {"base": len(base), "close": len(clo), "union": len(union),
              **{f"g{i:02d}": len(grids[i]) for i in grids}}
    return out, counts


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 800
    nproc = int(sys.argv[2]) if len(sys.argv) > 2 else 14
    files = sorted(PKL_DIR.glob("*.pkl"))
    random.Random(20260831).shuffle(files)
    files = [str(x) for x in files[: n * 2]]

    rows, tot = [], {}
    done = 0
    with Pool(nproc) as pool:
        for res in pool.imap_unordered(process, files, chunksize=4):
            if res is None:
                continue
            r, c = res
            rows += r
            for k, v in c.items():
                tot[k] = tot.get(k, 0) + v
            done += 1
            if done >= n:
                pool.terminate(); break

    d = pd.DataFrame(rows)
    d.to_csv(Path(__file__).parent / "s8_retune_grid.csv", index=False)
    d["fps"] = d.fp.map({"up": 1.0, "down": -1.0}).fillna(0.0)

    print(f"样本股票数={done}  窗口 {START}~{END}  horizon={HORIZON} k={FP_K}")
    print(f"bo 总数: base(high)={tot['base']}  close={tot['close']}  union={tot['union']}")
    print("\n各网格档的 bo 总数与「与 union 的差距」(用于挑计数匹配档):")
    ranked = sorted(range(len(GRID)), key=lambda i: abs(tot[f"g{i:02d}"] - tot["union"]))
    for i in ranked[:6]:
        g = GRID[i]
        print(f"  g{i:02d} tw={g['total_window']} msb={g['min_side_bars']} "
              f"mrh={g['min_relative_height']:.2f}: bo={tot[f'g{i:02d}']} "
              f"(union={tot['union']}, 差 {tot[f'g{i:02d}']-tot['union']:+d})")

    def stat(g):
        s = d[d.group == g]
        if len(s) < 50:
            return None
        up, dn = (s.fp == "up").mean(), (s.fp == "down").mean()
        return len(s), s.mfr.median(), up - dn, s.M.median()

    print("\n边际 bo 的 label 对照(marg_measure = 加第二个 measure; marg_gXX = 只调算子参数):")
    print(f"  {'组':14s} {'n':>7s} {'mfr_med':>9s} {'FP(up-dn)':>10s} {'M_med':>8s}")
    for g in ["marg_measure"] + [f"marg_g{i:02d}" for i in ranked[:6]]:
        v = stat(g)
        if v:
            print(f"  {g:14s} {v[0]:7d} {v[1]:+9.4f} {v[2]:+10.3f} {v[3]:8.4f}")

    print("\n同股票配对差(marg_measure − marg_gXX)，|t|<2 即不可区分:")
    x = d[d.group == "marg_measure"].groupby("symbol").fps.mean()
    for i in ranked[:6]:
        y = d[d.group == f"marg_g{i:02d}"].groupby("symbol").fps.mean()
        j = pd.concat([x, y], axis=1, join="inner"); j.columns = ["x", "y"]
        dd = (j.x - j.y).dropna()
        if len(dd) < 30:
            continue
        g = GRID[i]
        print(f"  vs g{i:02d}(tw={g['total_window']},msb={g['min_side_bars']},"
              f"mrh={g['min_relative_height']:.2f}): n={len(dd):5d} "
              f"mean={dd.mean():+.4f} t={dd.mean()/(dd.std(ddof=1)/np.sqrt(len(dd))):+.2f}")


if __name__ == "__main__":
    main()
