"""训练段用多长 —— 第三步：几种常见日线量价信号的「比同日普通买入多出的部分」随时间怎么变。

只读 02-cache.parquet 与 02-daily-market.parquet。信号只用当天及以前的数据；成绩是训练段内自己算的后续涨跌。

同日对照：池内、标签有效的股票日，每天按 M 切五档（与 tune-gates-v3 相同的切法），
  每行的「多出的部分」= 自己的成绩 − 同日同档全部池内股票日的成绩（方向取均值，幅度取中位）。
  信号在某段时间的领先 = 方向：多出部分的均值；幅度：多出部分的中位数。
偶然波动：
  方向：按股票、按周两向聚类的标准误（同一只股票的买点、同一周的买点都不当独立）。
  幅度：按股票整只重抽 200 次的标准差。

输出：02-signals-effects.csv（信号 × 指标 × 半年 的领先与偶然波动），02-signals-rows.parquet（信号行，供后续）
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RNG = np.random.default_rng(0)

SIGNALS = {
    "放量大阳": lambda d: (d["r1"] >= 3 * d["M"]) & (d["vm"] >= 3),
    "大阴线": lambda d: d["r1"] <= -3 * d["M"],
    "一周跌最多10%": lambda d: d["r5_rank"] <= 0.10,
    "一周涨最多10%": lambda d: d["r5_rank"] >= 0.90,
    "创120日新高": lambda d: d["hi120"],
    "横盘后创20日新高": lambda d: (d["w40"] <= 8 * d["M"]) & d["hi20"],
    "离120日高点跌一半以上": lambda d: d["dd120"] <= -0.5,
    "深跌后放量阳线": lambda d: (d["dd120"] <= -0.4) & (d["r1"] >= 2 * d["M"]) & (d["vm"] >= 2),
    "跳空高开": lambda d: d["gap"] >= 2 * d["M"],
    "60日已涨五成": lambda d: d["r60"] >= 0.5,
    "缩量": lambda d: d["vm"] <= 0.5,
}
METRICS = {  # 名称: (标签列, 有效条件列, 汇总方式)
    "方向40日": ("d40", "d40", "mean"),
    "幅度40日": ("m40", "d40", "median"),
    "方向10日": ("d10", "d10", "mean"),
    "收益10日": ("f10", "d10", "median"),
}


def half(d: pd.Series) -> pd.Series:
    return d.dt.year.astype(str) + np.where(d.dt.month <= 6, "H1", "H2")


def load() -> pd.DataFrame:
    P = pd.read_parquet(HERE / "02-cache.parquet")
    P = P[P["pool"]].copy()
    P["date"] = pd.to_datetime(P["date"])
    P = P[P["date"] >= "2022-01-01"]          # 2021 年只有两个月且多数回看量未满，作回看缓冲
    P["r5_rank"] = P.groupby("date")["r5"].rank(pct=True)
    P["per"] = half(P["date"])
    P["week"] = P["date"].dt.to_period("W").astype(str)
    for name, (col, vcol, how) in METRICS.items():
        ok = P[vcol] != -9
        sub = P.loc[ok, ["date", "M", col]].copy()
        q = sub.groupby("date")["M"].transform(lambda m: pd.qcut(m.rank(method="first"), 5, labels=False))
        sub["q"] = q
        base = sub.groupby(["date", "q"])[col].transform(how)
        P[f"x_{name}"] = np.nan
        P.loc[ok, f"x_{name}"] = (sub[col] - base).astype(float)
    return P


def twoway_se(x: np.ndarray, g1: np.ndarray, g2: np.ndarray) -> float:
    """均值的两向聚类标准误（Cameron–Gelbach–Miller），按股票、按周。"""
    n = len(x)
    if n < 2:
        return np.nan
    e = x - x.mean()

    def v(groups):
        s = pd.Series(e).groupby(groups).sum().to_numpy()
        return (s ** 2).sum() / n ** 2

    inter = pd.Series(e).groupby([g1, g2]).sum().to_numpy()
    vi = (inter ** 2).sum() / n ** 2
    return float(np.sqrt(max(v(g1) + v(g2) - vi, v(g1), v(g2))))


def boot_median_se(x: np.ndarray, stocks: np.ndarray, reps: int = 200) -> float:
    codes, uniq = pd.factorize(stocks)
    order = np.argsort(codes, kind="stable")
    xs, cs = x[order], codes[order]
    bounds = np.r_[0, np.cumsum(np.bincount(cs, minlength=len(uniq)))]
    meds = []
    k = len(uniq)
    for _ in range(reps):
        pick = RNG.integers(0, k, k)
        idx = np.concatenate([np.arange(bounds[i], bounds[i + 1]) for i in pick])
        meds.append(np.median(xs[idx]))
    return float(np.std(meds))


def effects(P: pd.DataFrame, by: str = "per") -> pd.DataFrame:
    rows = []
    for sname, fn in SIGNALS.items():
        mask = fn(P).fillna(False).to_numpy(dtype=bool)
        S = P[mask]
        for mname, (col, vcol, how) in METRICS.items():
            xcol = f"x_{mname}"
            for per, g in S[S[xcol].notna()].groupby(by):
                x = g[xcol].to_numpy(dtype=float)
                if len(x) < 30:
                    continue
                sym = g["sym"].astype(str).to_numpy()
                if how == "mean":
                    est, se = x.mean(), twoway_se(x, sym, g["week"].to_numpy())
                else:
                    est, se = float(np.median(x)), boot_median_se(x, sym)
                rows.append({"信号": sname, "指标": mname, "时段": per, "领先": est, "偶然波动": se,
                             "买点数": len(x), "股票数": len(set(sym))})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    P = load()
    sig_cols = ["date", "sym", "per", "week", "M"] + [c for c in P.columns if c.startswith("x_")]
    for sname, fn in SIGNALS.items():
        P[f"s_{sname}"] = fn(P).fillna(False).astype(bool)
    keep = P[P[[f"s_{s}" for s in SIGNALS]].any(axis=1)]
    keep[sig_cols + [f"s_{s}" for s in SIGNALS]].to_parquet(HERE / "02-signals-rows.parquet", index=False)
    # 同时存一份全部池内股票日的「多出的部分」（只有对照差值，不含原始涨跌），供按市场状态分组
    P[sig_cols].to_parquet(HERE / "02-pool-excess.parquet", index=False)
    E = effects(P)
    E.to_csv(HERE / "02-signals-effects.csv", index=False)
    pd.set_option("display.width", 250)
    for m in METRICS:
        t = E[E["指标"] == m].pivot(index="信号", columns="时段", values="领先")
        s = E[E["指标"] == m].pivot(index="信号", columns="时段", values="偶然波动")
        print(f"\n== {m}：领先（括号外）与偶然波动")
        print(t.round(3).astype(str).add(" ±").add(s.round(3).astype(str)).to_string())
