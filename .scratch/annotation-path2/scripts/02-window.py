"""训练段用多长 —— 第四步：用多长的历史去估「下一个半年」的信号领先最准（滚动外推检验）。

只读 02-signals-rows.parquet（信号行的「比同日同档普通买入多出的部分」）与 02-signals-effects.csv（各半年的偶然波动）。

做法：对每个信号 × 指标 × 目标半年 h，用 h 之前的若干个半年里该信号的全部买点合起来估领先（方向取均值、幅度取中位），
和 h 自己实测的领先比，记平方误差。不同的「取哪些历史」：
  最近 K 个半年（K=1..5）、之前全部（等权）、之前全部按 v3 近期加权（一年前权重减半）、
  「和目标同一种市场状态的半年」（用了目标半年自己的市场状态，事先不可能知道，是这种挑法能达到的上限）。
目标半年的实测值本身带偶然波动，对所有挑法是同一份，所以只比较挑法之间的差。

另算：相邻两个半年的「偏离常态」是否同向（对每个信号 × 指标，偏离 = 该半年领先 − 其余半年的平均）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
R = pd.read_parquet(HERE / "02-signals-rows.parquet")
E = pd.read_csv(HERE / "02-signals-effects.csv")
SIGS = [c[2:] for c in R.columns if c.startswith("s_")]
METS = {"方向40日": "mean", "幅度40日": "median", "方向10日": "mean", "收益10日": "median"}
PERS = ["2022H1", "2022H2", "2023H1", "2023H2", "2024H1", "2024H2", "2025H1", "2025H2"]
# 市场状态（来自 02-regime-halfyear.csv 的等权市场波动，≥0.20 记「高波动」）
REG = pd.read_csv(HERE / "02-regime-halfyear.csv", index_col=0)
HIGHVOL = {p: bool(REG.loc[p, "市场波动"] >= 0.20) for p in PERS}
UPMKT = {p: bool(REG.loc[p, "市场涨跌"] > 0) for p in PERS}
import sys
FRAC = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0     # <1：训练侧只留这一比例的股票，模拟买点稀的 pattern
DRAWS = int(sys.argv[2]) if len(sys.argv) > 2 else 1


def wmedian(x, w):
    o = np.argsort(x)
    x, w = x[o], w[o]
    c = np.cumsum(w)
    return float(x[np.searchsorted(c, c[-1] / 2)])


def estimate(x, w, how):
    if len(x) == 0:
        return np.nan
    return float(np.average(x, weights=w)) if how == "mean" else wmedian(x, w)


rows = []
for draw in range(DRAWS):
    rng = np.random.default_rng(draw)
    for s in SIGS:
        S = R[R[f"s_{s}"]]
        for m, how in METS.items():
            col = f"x_{m}"
            T = S[S[col].notna()]
            by_full = {p: T.loc[T["per"] == p, col].to_numpy(dtype=float) for p in PERS}
            if FRAC < 1:
                syms = T["sym"].astype(str).unique()
                keep = set(rng.choice(syms, max(1, int(len(syms) * FRAC)), replace=False))
                Tk = T[T["sym"].astype(str).isin(keep)]
                by = {p: Tk.loc[Tk["per"] == p, col].to_numpy(dtype=float) for p in PERS}
            else:
                by = by_full
            for hi, h in enumerate(PERS):
                if hi == 0 or len(by_full[h]) < 30 or min(len(by[p]) for p in PERS[:hi]) == 0:
                    continue
                target = estimate(by_full[h], np.ones(len(by_full[h])), how)
                prior = PERS[:hi]
                preds = {}
                for K in range(1, 6):
                    if K <= len(prior):
                        xs = np.concatenate([by[p] for p in prior[-K:]])
                        preds[f"最近{K}个半年"] = estimate(xs, np.ones(len(xs)), how)
                xs = np.concatenate([by[p] for p in prior])
                preds["之前全部"] = estimate(xs, np.ones(len(xs)), how)
                ages = np.concatenate([np.full(len(by[p]), (hi - j) * 0.5) for j, p in enumerate(prior)])
                preds["之前全部·近期加权"] = estimate(xs, 2.0 ** (-ages), how)
                for name, flag in (("同一市场状态(上限)", HIGHVOL), ("同涨跌方向(上限)", UPMKT)):
                    same = [p for p in prior if flag[p] == flag[h]]
                    if same:
                        xs2 = np.concatenate([by[p] for p in same])
                        preds[name] = estimate(xs2, np.ones(len(xs2)), how)
                for k, v in preds.items():
                    rows.append({"抽样": draw, "信号": s, "指标": m, "目标": h, "挑法": k, "预测": v,
                                 "实测": target, "平方误差": (target - v) ** 2, "可用历史": hi})
D = pd.DataFrame(rows)
D.to_csv(HERE / f"02-window-errors{'' if FRAC == 1 else f'-frac{FRAC}'}.csv", index=False)


def compare(min_hist: int, methods, exclude=()):
    sub = D[(D["可用历史"] >= min_hist) & (~D["目标"].isin(exclude))]
    keys = sub.groupby(["抽样", "信号", "指标", "目标"])["挑法"].apply(set)
    ok = keys[keys.apply(lambda st: set(methods) <= st)].index
    sub = sub.set_index(["抽样", "信号", "指标", "目标"]).loc[ok].reset_index()
    sub = sub[sub["挑法"].isin(methods)]
    # 每个指标内按「之前全部」的均方误差归一，指标之间可比
    out = {}
    for m in METS:
        t = sub[sub["指标"] == m].groupby("挑法")["平方误差"].mean()
        out[m] = (t / t["之前全部"]).reindex(methods)
    res = pd.DataFrame(out)
    res["四个指标平均"] = res.mean(axis=1)
    n_targets = sub["目标"].nunique()
    return res.round(3), n_targets, len(ok)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    base = ["最近1个半年", "最近2个半年", "最近3个半年", "之前全部", "之前全部·近期加权", "同一市场状态(上限)", "同涨跌方向(上限)"]
    for mh, excl in [(3, ()), (3, ("2025H2",)), (5, ()), (1, ())]:
        meth = base + (["最近4个半年", "最近5个半年"] if mh >= 5 else [])
        if mh < 3:
            meth = ["最近1个半年", "之前全部", "之前全部·近期加权", "同一市场状态(上限)", "同涨跌方向(上限)"]
        res, nt, nk = compare(mh, meth, excl)
        print(f"\n== 目标半年至少有 {mh} 个半年历史，{'不含 2025H2' if excl else '含 2025H2'}；目标 {nt} 个，组合 {nk} 个；数值 = 均方误差 ÷ 「之前全部」的均方误差")
        print(res.to_string())
    if FRAC < 1:
        raise SystemExit
    # 相邻半年偏离常态是否同向
    pairs = []
    for (s, m), g in E.groupby(["信号", "指标"]):
        g = g.set_index("时段").reindex(PERS)
        v = g["领先"].to_numpy()
        se = g["偶然波动"].to_numpy()
        for i in range(len(PERS) - 1):
            if np.isfinite(v[i]) and np.isfinite(v[i + 1]):
                rest = np.delete(v, [i, i + 1])
                mu = np.nanmean(rest)
                pairs.append({"信号": s, "指标": m, "前": PERS[i], "后": PERS[i + 1],
                              "前偏离": (v[i] - mu) / se[i], "后偏离": (v[i + 1] - mu) / se[i + 1]})
    Pp = pd.DataFrame(pairs)
    print("\n== 相邻两个半年的偏离常态（按各自偶然波动标准化）的相关")
    print(Pp.groupby("指标").apply(lambda g: pd.Series({"相关": g["前偏离"].corr(g["后偏离"]), "对数": len(g)}),
                                 include_groups=False).round(3))
    print("全部指标合并：", round(Pp["前偏离"].corr(Pp["后偏离"]), 3), len(Pp))
    print("不含以 2025H2 为「后」的对：", round(Pp[Pp["后"] != "2025H2"]["前偏离"].corr(Pp[Pp["后"] != "2025H2"]["后偏离"]), 3))
    Pp.to_csv(HERE / "02-window-adjacent.csv", index=False)
