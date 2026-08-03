"""临时实验(opt · 第二轮分析):首次穿越 + 市场超额 label。

(a) 首次穿越:±X% 谁先被触及。MFE/MAE 是幅度、丢顺序;这一项把顺序补回来。
(b) 市场超额:label_excess = label − 同日横截面中位数,看 SE(lift) 能降多少。
用完删。
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "temp_code" / "out2"
THRESH = (0.05, 0.08, 0.10, 0.15)
N0 = 200
B = 600


def wmed_factory(rets, tick_idx):
    o = np.argsort(rets, kind="stable")
    return np.asarray(rets)[o], np.asarray(tick_idx)[o]


def med(pair, mult):
    r, ti = pair
    w = mult[ti]
    tot = w.sum()
    if tot <= 0:
        return np.nan
    return r[min(np.searchsorted(np.cumsum(w), tot / 2, "left"), len(r) - 1)]


def run(year):
    D = pd.read_pickle(OUT / f"rows_{year}.pkl")
    I = pd.read_pickle(OUT / f"index_{year}.pkl")
    print(f"\n{'='*78}\n### {year}   rows={len(D)}   index_days={len(I)}")

    # ---------- (a) 首次穿越 ----------
    print(f"\n--- (a) 首次穿越:20 日内 ±X% 谁先到 ---")
    print(f"{'X':>5s} {'组':<9s} {'n':>6s} {'先涨%':>7s} {'先跌%':>7s} "
          f"{'同根%':>7s} {'都没到%':>8s} {'先涨/(先涨+先跌)':>16s}")
    ratios = {}
    for X in THRESH:
        col = f"fp{X:g}"
        for c in ("pk4", "bo_only", "RAND"):
            s = D[D.cfg == c][col]
            n = len(s)
            up = (s == "up").mean()
            dn = (s == "down").mean()
            bo = (s == "both").mean()
            no = (s == "none").mean()
            r = up / (up + dn) if (up + dn) > 0 else np.nan
            ratios[(X, c)] = r
            print(f"{X:5.2f} {c:<9s} {n:6d} {up:7.1%} {dn:7.1%} {bo:7.1%} {no:8.1%} "
                  f"{r:16.3f}")
        print()

    # 对 pk4 vs bo_only 的先涨比例做 ticker bootstrap
    print("  先涨比例差（pk4 − 对照），ticker bootstrap：")
    tk = sorted(D.ticker.unique())
    tm = {t: i for i, t in enumerate(tk)}
    T = len(tk)
    rng = np.random.default_rng(31)
    mults = [np.bincount(rng.integers(0, T, T), minlength=T).astype(float)
             for _ in range(B)]
    for X in THRESH:
        col = f"fp{X:g}"
        def prep(c):
            s = D[D.cfg == c][["ticker", col]]
            s = s[s[col].isin(["up", "down"])]
            return (s[col].values == "up").astype(float), s.ticker.map(tm).values
        a_v, a_t = prep("pk4")
        for other in ("bo_only", "RAND"):
            b_v, b_t = prep(other)
            d = []
            for m in mults:
                wa, wb = m[a_t], m[b_t]
                if wa.sum() <= 0 or wb.sum() <= 0:
                    continue
                d.append((a_v * wa).sum() / wa.sum() - (b_v * wb).sum() / wb.sum())
            d = np.array(d)
            pt = a_v.mean() - b_v.mean()
            print(f"    X={X:.2f}  pk4 − {other:<8s} = {pt:+.4f}  "
                  f"SE={d.std():.4f}  t={pt/max(d.std(),1e-9):+.2f}")

    # ---------- (b) 市场超额 ----------
    print(f"\n--- (b) 市场超额 label：SE 能不能降下来 ---")
    I = I.reset_index().rename(columns={"date": "d"})
    M = D.merge(I[["d", "mh_med", "cc_med"]], left_on="date", right_on="d", how="inner")
    M["mh_ex"] = M.mh20 - M.mh_med
    M["cc_ex"] = M.cc20 - M.cc_med
    print(f"  可对齐行 {len(M)}/{len(D)}")
    tk = sorted(M.ticker.unique())
    tm = {t: i for i, t in enumerate(tk)}
    T = len(tk)
    rng = np.random.default_rng(32)
    mults = [np.bincount(rng.integers(0, T, T), minlength=T).astype(float)
             for _ in range(B)]
    print(f"\n  {'口径':<10s} {'med_pk4':>9s} {'med_base':>9s} {'lift':>8s} "
          f"{'SE(lift)':>9s} {'t':>7s} {'SE 相对原口径':>14s}")
    base_se = {}
    for col, name in (("mh20", "max-high 原口径"), ("mh_ex", "max-high 市场超额"),
                      ("cc20", "持有到期 原口径"), ("cc_ex", "持有到期 市场超额")):
        a = wmed_factory(M[M.cfg == "pk4"][col].values,
                         M[M.cfg == "pk4"].ticker.map(tm).values)
        b = wmed_factory(M[M.cfg == "bo_only"][col].values,
                         M[M.cfg == "bo_only"].ticker.map(tm).values)
        lifts = np.array([med(a, m) - med(b, m) for m in mults])
        lifts = lifts[~np.isnan(lifts)]
        ma, mb = np.median(a[0]), np.median(b[0])
        lift, se = ma - mb, lifts.std()
        key = "mh" if col.startswith("mh") else "cc"
        if col in ("mh20", "cc20"):
            base_se[key] = se
            rel = ""
        else:
            rel = f"{se/base_se[key]:.2f}x"
        print(f"  {name:<10s} {ma:9.4f} {mb:9.4f} {lift:8.4f} {se:9.4f} "
              f"{lift/max(se,1e-9):7.2f} {rel:>14s}")


def main():
    for y in (2025, 2024):
        if (OUT / f"rows_{y}.pkl").exists():
            run(y)
        else:
            print(f"\n{y} 尚未产出，跳过")


if __name__ == "__main__":
    sys.exit(main())
