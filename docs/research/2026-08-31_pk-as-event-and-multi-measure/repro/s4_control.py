"""S4: 对照 —— 「shared 组好」是 measure 的功劳,还是「突破幅度更大」这一平凡事实?

内生性质疑(skeptic 会问的第一问):shared/high_only/close_only 是按「哪个口径触发」
分的,分组本身是结果的函数。所以必须找一个 **measure-free** 的强度变量,看分组优势
能否被它吸收。用两个只依赖 K 线、不碰 detector 内部状态的量:

  excess_h = close[t] / max(high[t-W..t-1]) - 1     收盘越过前 W 根最高价的幅度
  excess_c = close[t] / max(close[t-W..t-1]) - 1    收盘越过前 W 根最高收盘的幅度

机制预期(值得单独验证):close_pk 价位恒 ≤ high_pk,故 close 口径的峰会被**更早**
击穿并 supersede 移除。于是三组其实是同一轮突破的**不同阶段**:
  close_only = 只越过收盘线(早期/弱) · shared = 同时越过两条线 · high_only = 越过
  最高价线时收盘线早已被清掉(晚期)。若如此,「两种 measure」就不是两种信息,而是
  同一条强度轴上的三个刻度。

输出:整体分组 + excess_h 分箱内分组 + 双维去簇(股内 / 40 交易日桶)。
"""
from __future__ import annotations

import pickle
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from path2.atoms.breakout import BODetector                          # noqa: E402
from path2.calc.atr import FP_ATR_WINDOW, rolling_atr_pct_nanmedian  # noqa: E402
from path2.eval import _first_passage_at, _ticker_seed               # noqa: E402
from path2_web.data import slice_window                              # noqa: E402

PKL_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END = "2021-01-01", "2026-03-08"
HORIZON = 40
FP_K = 5.0
W = 20                      # bb_v1 bo.total_window
RANDOM_DAYS = 12

BO_BASE = dict(
    total_window=20, min_side_bars=6, min_relative_height=0.2,
    exceed_threshold=0.003, peak_supersede_threshold=0.01,
    vol_baseline_period=63, breakout_measure="close",
)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    files = sorted(PKL_DIR.glob("*.pkl"))
    random.Random(20260831).shuffle(files)

    rows, base_rows = [], []
    done = 0
    for f in files:
        if done >= n:
            break
        try:
            with open(f, "rb") as fh:
                raw = pickle.load(fh)
            if not isinstance(raw, pd.DataFrame):
                continue
            win = slice_window(raw, START, END)
        except Exception:
            continue
        if len(win) < 300:
            continue
        sym = f.stem
        try:
            sh = {e.start_idx for e in BODetector(peak_measure="high", **BO_BASE).detect(win)}
            sc = {e.start_idx for e in BODetector(peak_measure="close", **BO_BASE).detect(win)}
        except Exception as e:
            print(f"skip {sym}: {e}", file=sys.stderr)
            continue
        done += 1

        hi, lo, cl = win["high"].values, win["low"].values, win["close"].values
        M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"],
                                      FP_ATR_WINDOW).values
        n_bars = len(win)
        dates = pd.to_datetime(win["date"]).values

        def lab(t):
            if t + HORIZON >= n_bars or t < W:
                return None
            return (float(hi[t + 1:t + HORIZON + 1].max()) / float(cl[t]) - 1.0,
                    float(lo[t + 1:t + HORIZON + 1].min()) / float(cl[t]) - 1.0,
                    _first_passage_at(hi, lo, cl, M, t, HORIZON, FP_K))

        for t in sorted(sh | sc):
            L = lab(t)
            if L is None:
                continue
            in_h, in_c = t in sh, t in sc
            rows.append(dict(
                symbol=sym, bar=t, date=dates[t],
                group="shared" if (in_h and in_c) else ("high_only" if in_h else "close_only"),
                excess_h=float(cl[t]) / float(hi[t - W:t].max()) - 1.0,
                excess_c=float(cl[t]) / float(cl[t - W:t].max()) - 1.0,
                day_ret=float(cl[t]) / float(cl[t - 1]) - 1.0,
                mfr=L[0], mdd=L[1], fp=L[2], M=float(M[t])))

        cand = [i for i in range(W, n_bars) if i + HORIZON < n_bars
                and np.isfinite(M[i]) and M[i] > 0]
        if cand:
            rng = np.random.default_rng(_ticker_seed(sym))
            for i in rng.choice(cand, size=min(RANDOM_DAYS, len(cand)), replace=False):
                i = int(i)
                L = lab(i)
                if L is None:
                    continue
                base_rows.append(dict(
                    symbol=sym, bar=i, date=dates[i], group="random_day",
                    excess_h=float(cl[i]) / float(hi[i - W:i].max()) - 1.0,
                    excess_c=float(cl[i]) / float(cl[i - W:i].max()) - 1.0,
                    day_ret=float(cl[i]) / float(cl[i - 1]) - 1.0,
                    mfr=L[0], mdd=L[1], fp=L[2], M=float(M[i])))

    df = pd.DataFrame(rows)
    bs = pd.DataFrame(base_rows)
    outdir = Path(__file__).parent
    df.to_csv(outdir / "s4_control.csv", index=False)
    bs.to_csv(outdir / "s4_baseline.csv", index=False)
    print(f"样本股票数 = {done}  bo n={len(df)}  基线 n={len(bs)}")
    analyse(df, bs)


def summarize(sub, name, pad=16):
    n = len(sub)
    if n < 5:
        print(f"  {name:{pad}s} n={n}")
        return
    up = (sub.fp == "up").mean()
    dn = (sub.fp == "down").mean()
    se = np.sqrt(max(up * (1 - up) + dn * (1 - dn), 1e-12) / n)   # 粗略 SE(未去簇)
    print(f"  {name:{pad}s} n={n:6d} mfr_med={sub.mfr.median():+.4f} "
          f"mdd_med={sub.mdd.median():+.4f} FPup={up:.3f} FPdn={dn:.3f} "
          f"up-dn={up - dn:+.3f}(±{1.96 * se:.3f}) exh_med={sub.excess_h.median():+.4f} "
          f"M_med={sub.M.median():.4f}")


def analyse(df, bs):
    print("\n=== A. 整体分组(未控制) ===")
    summarize(bs, "random_day")
    for g in ["shared", "high_only", "close_only"]:
        summarize(df[df.group == g], g)

    print("\n=== B. 控制突破幅度 excess_h(收盘越过前20根最高价的幅度)分箱内比较 ===")
    all_ = pd.concat([df, bs.assign(group="random_day")], ignore_index=True)
    qs = all_.excess_h.quantile([0, .2, .4, .6, .8, .9, 1.0]).values
    qs = np.unique(qs)
    all_["bin"] = pd.cut(all_.excess_h, qs, include_lowest=True)
    for b, sub in all_.groupby("bin", observed=True):
        print(f"-- excess_h ∈ {b} (n={len(sub)})")
        for g in ["random_day", "close_only", "shared", "high_only"]:
            s = sub[sub.group == g]
            if len(s) >= 30:
                summarize(s, g, pad=12)

    print("\n=== C. 只看 excess_h>0 的子样本(收盘确实越过前高)===")
    pos = df[df.excess_h > 0]
    for g in ["shared", "high_only", "close_only"]:
        summarize(pos[pos.group == g], g)
    bpos = bs[bs.excess_h > 0]
    summarize(bpos, "random_day>0")

    print("\n=== D. 双维去簇(股内取每股均值 / 40 交易日桶取桶均值)· 指标=FP(up-down) ===")
    d = df.copy()
    d["fp_score"] = d.fp.map({"up": 1, "down": -1}).fillna(0.0)
    d["date"] = pd.to_datetime(d["date"])
    t0 = d["date"].min()
    d["tbucket"] = ((d["date"] - t0).dt.days // 56)      # ~40 交易日 ≈ 56 日历日
    for key in ["symbol", "tbucket"]:
        print(f"-- 按 {key} 聚合后组间比较")
        for g in ["shared", "high_only", "close_only"]:
            s = d[d.group == g].groupby(key)["fp_score"].mean()
            if len(s) >= 5:
                m, sd = s.mean(), s.std(ddof=1)
                print(f"  {g:12s} 簇数={len(s):5d} mean={m:+.4f} "
                      f"t={m / (sd / np.sqrt(len(s))):+.2f}")
        # 组间差(配对到同一簇)
        piv = d.pivot_table(index=key, columns="group", values="fp_score", aggfunc="mean")
        for a, b in [("shared", "close_only"), ("shared", "high_only")]:
            if a in piv and b in piv:
                dd = (piv[a] - piv[b]).dropna()
                if len(dd) >= 5:
                    m, sd = dd.mean(), dd.std(ddof=1)
                    print(f"  配对差 {a}-{b}: 簇数={len(dd):5d} mean={m:+.4f} "
                          f"t={m / (sd / np.sqrt(len(dd))):+.2f}")


if __name__ == "__main__":
    main()
