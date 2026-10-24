"""训练段用多长 —— 第二步：各半年的市场状态描述（只读 02-cache.parquet）。

输出 02-regime-halfyear.csv、02-regime-quarter.csv、02-daily-market.parquet（逐日市场状态，供后面按状态分组用）。

口径（全部只用截到 2025-12-31 的数据）：
  市场日收益 mkt = 当天「普通股且 20 日成交额中位 ≥100 万」的股票收盘涨跌的截尾均值（两头各截 1%），等权
  半年涨跌 = mkt 逐日复利；最大回撤 = 半年内等权指数从高点的最大跌幅
  市场波动 = mkt 日标准差 × √252
  池内典型波动 = 池内股票日 M 的中位数
  大盘带动比例 = 池内每只股票半年内日涨跌与 mkt 相关系数的平方，取中位（越大越「一起涨跌」）
  日收益自相关 = 池内每只股票半年内 r1 与前一日 r1 的相关，取中位（负 = 次日往回拉）
  隔夜占比 = 池内每只股票半年内 var(开盘跳空) / [var(开盘跳空)+var(日内)]，取中位
  极端日占比 = 池内股票日 |r1| ≥ 20% 的比例；放量日占比 = 池内股票日 vm ≥ 3 的比例
  普通买入的底色 = 池内全部股票日的 d40 均值（先上 − 先下）与 m40 中位
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
P = pd.read_parquet(HERE / "02-cache.parquet")
P["date"] = pd.to_datetime(P["date"])

liq = P[P["dv"] >= 1e6]
lo, hi = liq["r1"].quantile([0.01, 0.99])


def trimmed_mean(x):
    x = x[(x >= lo) & (x <= hi)]
    return x.mean()


mkt = liq.groupby("date")["r1"].apply(trimmed_mean).rename("mkt")
nliq = liq.groupby("date").size().rename("n_liq")
pool = P[P["pool"]].copy()
npool = pool.groupby("date").size().rename("n_pool")
daily = pd.concat([mkt, nliq, npool], axis=1).dropna(subset=["mkt"])
daily = daily[daily["n_liq"] >= 500]          # 数据最开头几天股票数不全的剔掉
lvl = (1 + daily["mkt"]).cumprod()
daily["level"] = lvl
daily["mret60"] = lvl / lvl.shift(60) - 1           # 过去 60 个交易日市场涨跌（只用当天及以前）
daily["mvol20"] = daily["mkt"].rolling(20).std() * np.sqrt(252)
daily.to_parquet(HERE / "02-daily-market.parquet")


def period_of(d: pd.Series, kind: str) -> pd.Series:
    if kind == "half":
        return d.dt.year.astype(str) + np.where(d.dt.month <= 6, "H1", "H2")
    return d.dt.year.astype(str) + "Q" + d.dt.quarter.astype(str)


def per_stock_stats(g: pd.DataFrame) -> pd.Series:
    if len(g) < 40:
        return pd.Series({"r2": np.nan, "ac1": np.nan, "ovn": np.nan})
    r = g["r1"].to_numpy(dtype=float)
    m = g["mkt"].to_numpy(dtype=float)
    ok = np.isfinite(r) & np.isfinite(m)
    r2 = np.corrcoef(r[ok], m[ok])[0, 1] ** 2 if ok.sum() > 30 else np.nan
    r_prev = g["r1_prev"].to_numpy(dtype=float)
    ok2 = np.isfinite(r) & np.isfinite(r_prev)
    ac1 = np.corrcoef(r[ok2], r_prev[ok2])[0, 1] if ok2.sum() > 30 else np.nan
    gv, iv = np.nanvar(g["gap"].to_numpy(dtype=float)), np.nanvar(g["intra"].to_numpy(dtype=float))
    ovn = gv / (gv + iv) if (gv + iv) > 0 else np.nan
    return pd.Series({"r2": r2, "ac1": ac1, "ovn": ovn})


def table(kind: str) -> pd.DataFrame:
    d = daily.copy()
    d["per"] = period_of(d.index.to_series(), kind)
    rows = {}
    for per, g in d.groupby("per"):
        level = (1 + g["mkt"]).cumprod()
        rows[per] = {
            "交易日": len(g),
            "市场涨跌": level.iloc[-1] - 1,
            "最大回撤": (level / np.maximum.accumulate(np.r_[1.0, level.to_numpy()])[1:] - 1).min(),
            "市场波动": g["mkt"].std() * np.sqrt(252),
            "池内每日股票数": g["n_pool"].mean(),
        }
    out = pd.DataFrame(rows).T
    pp = pool.copy()
    pp["per"] = period_of(pp["date"], kind)
    pp = pp.merge(daily[["mkt"]], left_on="date", right_index=True, how="inner")
    pp = pp.sort_values(["sym", "date"])
    pp["r1_prev"] = pp.groupby("sym", observed=True)["r1"].shift(1)
    # 只在连续的池内日上取前一日；隔开的日子不算
    gapdays = pp.groupby("sym", observed=True)["date"].diff().dt.days
    pp.loc[gapdays > 5, "r1_prev"] = np.nan
    g = pp.groupby("per")
    out["池内不同股票数"] = g["sym"].nunique()
    out["池内典型波动M"] = g["M"].median()
    out["极端日占比"] = g["r1"].apply(lambda x: (x.abs() >= 0.2).mean())
    out["放量日占比"] = g["vm"].apply(lambda x: (x >= 3).mean())
    lab = pp[pp["d40"] != -9]
    out["普通买入方向底色"] = lab.groupby("per")["d40"].mean()
    out["普通买入幅度中位"] = lab.groupby("per")["m40"].median()
    out["有标签股票日"] = lab.groupby("per").size()
    st = pp.groupby(["per", "sym"], observed=True).apply(per_stock_stats, include_groups=False)
    out["大盘带动比例"] = st.groupby(level=0)["r2"].median()
    out["日收益自相关"] = st.groupby(level=0)["ac1"].median()
    out["隔夜占比"] = st.groupby(level=0)["ovn"].median()
    return out


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    for kind in ["half", "quarter"]:
        t = table(kind)
        t.to_csv(HERE / f"02-regime-{'halfyear' if kind == 'half' else 'quarter'}.csv")
        print(t.round(4).to_string())
