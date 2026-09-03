"""S5: 「两口径都确认」是新信息,还是既有字段的代理?

S4 已显示:bb_v1 现役 bo 流(peak=high, breakout=close)内部,同时也击穿了 close 口径
峰的那部分(shared)方向性明显好于只击穿 high 口径峰的部分(high_only)。
但 shared 可能只是既有字段的代理 —— 它可能等价于 drought 更长 / peak_age 更大 /
pk_count 更多 / 突破幅度更大。本脚本在 **bb_v1 自己的 bo 流内部** 做控制回归:

  fp_score ~ shared + drought + peak_age_max + pk_count + excess_h + log(M)

样本 = 现役 bo(不引入任何新 bo),故不存在「更多信号」的稀释问题;若 shared 的
偏系数在控制后仍显著为正,则它是既有字段吸收不掉的**新信息**,可作 where 闸候选。
去簇:股内 + 40 交易日桶(观测非独立,同股/同期重叠 40 日 label 窗共享随机源)。
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
from path2.eval import _first_passage_at                             # noqa: E402
from path2_web.data import slice_window                              # noqa: E402

PKL_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END = "2021-01-01", "2026-03-08"
HORIZON, FP_K, W = 40, 5.0, 20

BO_BASE = dict(
    total_window=20, min_side_bars=6, min_relative_height=0.2,
    exceed_threshold=0.003, peak_supersede_threshold=0.01,
    vol_baseline_period=63, breakout_measure="close",
)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    files = sorted(PKL_DIR.glob("*.pkl"))
    random.Random(20260831).shuffle(files)

    rows = []
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
            evs = list(BODetector(peak_measure="high", **BO_BASE).detect(win))
            sc = {e.start_idx for e in BODetector(peak_measure="close", **BO_BASE).detect(win)}
            sb = {e.start_idx for e in BODetector(peak_measure="body_top", **BO_BASE).detect(win)}
        except Exception as e:
            print(f"skip {sym}: {e}", file=sys.stderr)
            continue
        done += 1

        hi, lo, cl = win["high"].values, win["low"].values, win["close"].values
        M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"],
                                      FP_ATR_WINDOW).values
        n_bars = len(win)
        dates = pd.to_datetime(win["date"]).values
        for e in evs:
            t = e.start_idx
            if t + HORIZON >= n_bars or t < W:
                continue
            fp = _first_passage_at(hi, lo, cl, M, t, HORIZON, FP_K)
            rows.append(dict(
                symbol=sym, bar=t, date=dates[t],
                shared=int(t in sc), shared_body=int(t in sb),
                drought=e.drought if e.drought is not None else -1,
                pk_count=e.pk_count, peak_age_max=e.peak_age_max,
                vol_ratio=e.vol_ratio if e.vol_ratio is not None else np.nan,
                excess_h=float(cl[t]) / float(hi[t - W:t].max()) - 1.0,
                M=float(M[t]),
                mfr=float(hi[t + 1:t + HORIZON + 1].max()) / float(cl[t]) - 1.0,
                mdd=float(lo[t + 1:t + HORIZON + 1].min()) / float(cl[t]) - 1.0,
                fp=fp))

    df = pd.DataFrame(rows)
    df.to_csv(Path(__file__).parent / "s5_shared.csv", index=False)
    print(f"样本股票数={done}  现役 bo n={len(df)}  shared 占比={df.shared.mean():.3f}")
    analyse(df)


def analyse(df):
    d = df.copy()
    d["fp_score"] = d.fp.map({"up": 1.0, "down": -1.0}).fillna(0.0)
    d["date"] = pd.to_datetime(d["date"])
    d["tbucket"] = ((d["date"] - d["date"].min()).dt.days // 56)

    print("\n=== A. bb_v1 现役 bo 流内部:shared vs not ===")
    for v, name in [(1, "shared(两口径都破)"), (0, "high_only(只破high口径峰)")]:
        s = d[d.shared == v]
        up, dn = (s.fp == "up").mean(), (s.fp == "down").mean()
        print(f"  {name:22s} n={len(s):6d} mfr_med={s.mfr.median():+.4f} "
              f"mdd_med={s.mdd.median():+.4f} FPup={up:.3f} FPdn={dn:.3f} up-dn={up-dn:+.3f}")
    print("  (body_top 口径同法)")
    for v, name in [(1, "shared_body"), (0, "body_only_no")]:
        s = d[d.shared_body == v]
        up, dn = (s.fp == "up").mean(), (s.fp == "down").mean()
        print(f"  {name:22s} n={len(s):6d} mfr_med={s.mfr.median():+.4f} "
              f"FPup={up:.3f} FPdn={dn:.3f} up-dn={up-dn:+.3f}")

    print("\n=== B. 控制既有字段的 OLS(因变量 fp_score ∈ {-1,0,1}) ===")
    X = d[["shared", "drought", "peak_age_max", "pk_count", "excess_h"]].copy()
    X["logM"] = np.log(d["M"].clip(lower=1e-6))
    X["drought"] = X["drought"].clip(lower=0)
    X = X.astype(float)
    X.insert(0, "const", 1.0)
    y = d["fp_score"].values
    Xv = X.values
    beta, *_ = np.linalg.lstsq(Xv, y, rcond=None)
    resid = y - Xv @ beta
    n, k = Xv.shape
    XtXi = np.linalg.pinv(Xv.T @ Xv)
    s2 = (resid @ resid) / (n - k)
    se = np.sqrt(np.diag(XtXi) * s2)
    print(f"  {'term':14s} {'beta':>10s} {'se':>9s} {'t':>7s}   {'t_cluster(股)':>13s} {'t_cluster(期)':>13s}")
    for key in ["symbol", "tbucket"]:
        pass
    # cluster-robust se(两套)
    tcl = {}
    for key in ["symbol", "tbucket"]:
        meat = np.zeros((k, k))
        for _, idx in d.groupby(key).indices.items():
            u = (Xv[idx] * resid[idx][:, None]).sum(axis=0)
            meat += np.outer(u, u)
        V = XtXi @ meat @ XtXi
        tcl[key] = beta / np.sqrt(np.clip(np.diag(V), 1e-18, None))
    for i, nm in enumerate(X.columns):
        print(f"  {nm:14s} {beta[i]:+10.5f} {se[i]:9.5f} {beta[i]/se[i]:+7.2f}   "
              f"{tcl['symbol'][i]:+13.2f} {tcl['tbucket'][i]:+13.2f}")

    print("\n=== C. 分层:在 drought / peak_age / excess_h 分位内比较 shared ===")
    for col, qn in [("drought", 3), ("peak_age_max", 3), ("excess_h", 3), ("pk_count", 0)]:
        print(f"-- 按 {col} 分层")
        if qn:
            try:
                d["_b"] = pd.qcut(d[col], qn, duplicates="drop")
            except Exception:
                continue
        else:
            d["_b"] = d[col].clip(upper=3)
        for b, sub in d.groupby("_b", observed=True):
            a = sub[sub.shared == 1]; c = sub[sub.shared == 0]
            if len(a) < 30 or len(c) < 30:
                continue
            fa = (a.fp == "up").mean() - (a.fp == "down").mean()
            fc = (c.fp == "up").mean() - (c.fp == "down").mean()
            print(f"   {str(b):24s} shared n={len(a):5d} up-dn={fa:+.3f} | "
                  f"not n={len(c):5d} up-dn={fc:+.3f} | diff={fa-fc:+.3f}")

    print("\n=== D. 双维去簇的配对差(shared - not,同簇内) ===")
    for key in ["symbol", "tbucket"]:
        piv = d.pivot_table(index=key, columns="shared", values="fp_score", aggfunc="mean")
        if 0 in piv and 1 in piv:
            dd = (piv[1] - piv[0]).dropna()
            m, sd = dd.mean(), dd.std(ddof=1)
            print(f"  {key:8s} 簇数={len(dd):5d} mean={m:+.4f} t={m/(sd/np.sqrt(len(dd))):+.2f}")


if __name__ == "__main__":
    main()
