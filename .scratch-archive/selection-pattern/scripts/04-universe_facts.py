"""04 幸存者偏差票：本地股票池的静态事实（不读任何买点之后的涨跌）。

只用每只股票买入当天及以前的数据，统计：
  1. 首个 / 末个交易日分布（新上市、有没有提前结束的序列）；
  2. 最新一天（2026-10-05，此日价格未被以后的拆股改写）的价格与成交额分布；
  3. 抽样日的横截面：按当日波动尺度（与判优尺子相同：TR/close 20 日中位数）分五档，
     看「大跌后」「暴涨后」两类状态在各档里的占比，以及这些状态中低价、低成交额、
     新上市股的比例——用来判断这两类状态比同档普通股「更像会退市的股票」多少；
  4. 幸存股里曾经跌掉 90% 以上的有多少（活下来的「濒死股」）。

注意：价格是复权价。历史上做过反向拆股的股票，早期复权价被抬高，所以「历史某天低于 1 美元」
的占比是下限；成交额 = 复权价 × 复权量，对拆股不变，可直接用。

运行：uv run python .scratch/selection-pattern/scripts/04-universe_facts.py
输出：同目录 04-universe_facts_out.txt、04-universe_states.csv
"""
import glob
import os

import numpy as np
import pandas as pd

ROOT = "/home/yu/PycharmProjects/Trade_Strategy"
PKL_DIR = os.path.join(ROOT, "datasets/pkls")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_EVERY = 5          # 每 5 个交易日抽一个横截面
SAMPLE_START = "2022-01-03"
DATA_START_TOL = "2021-10-15"   # 首日在此之前视为「数据起点就在」
BOTTOM_DD = 0.30          # 大跌后：收盘 ≤ 过去一年最高收盘的 30%（跌掉七成以上）
BOTTOM_DD_MILD = 0.50     # 较轻版本：跌掉一半以上
SPIKE_R20 = 0.50          # 暴涨后：近 20 日涨幅 ≥ 50%
NEAR_DEATH = 0.10         # 濒死：曾跌到一年内高点的 10% 以下


def load_one(path):
    df = pd.read_pickle(path)
    df = df[["high", "low", "close", "volume"]].astype(float)
    df = df[(df["close"] > 0) & (df["high"] >= df["low"])]
    return df


def per_stock_features(df):
    close, high, low = df["close"], df["high"], df["low"]
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    m = (tr / close).rolling(20).median()
    dv20 = (close * df["volume"]).rolling(20).median()
    hi252 = close.rolling(252, min_periods=1).max()
    dd = close / hi252
    r20 = close / close.shift(20) - 1
    at_high = close >= hi252 - 1e-12
    return pd.DataFrame({"close": close, "M": m, "dv20": dv20, "dd": dd, "r20": r20,
                         "at_high": at_high})


def main():
    paths = sorted(glob.glob(os.path.join(PKL_DIR, "*.pkl")))
    meta, frames = [], []
    for p in paths:
        sym = os.path.basename(p)[:-4]
        df = load_one(p)
        if df.empty:
            continue
        f = per_stock_features(df)
        meta.append({"symbol": sym, "first": df.index[0], "last": df.index[-1], "rows": len(df),
                     "min_dd": float(f["dd"].min()),
                     "last_close": float(df["close"].iloc[-1]),
                     "last_dv20": float(f["dv20"].iloc[-1]) if np.isfinite(f["dv20"].iloc[-1]) else np.nan})
        f["symbol"] = sym
        f["first"] = df.index[0]
        frames.append(f)
    meta = pd.DataFrame(meta)
    cal = pd.DatetimeIndex(sorted(set().union(*[set(fr.index) for fr in frames])))
    sample_dates = cal[cal >= SAMPLE_START][::SAMPLE_EVERY]
    panel = pd.concat([fr.loc[fr.index.intersection(sample_dates)] for fr in frames])
    panel.index.name = "date"
    panel = panel.reset_index()
    panel = panel[np.isfinite(panel["M"]) & (panel["M"] > 0)]

    # 与判优尺子相同的分档：每个日期按 M 的 20/40/60/80 分位切五档
    def qbin(g):
        cuts = np.unique(np.quantile(g["M"].to_numpy(), [0.2, 0.4, 0.6, 0.8]))
        return pd.Series(np.searchsorted(cuts, g["M"].to_numpy(), side="left"), index=g.index)
    panel["q"] = panel.groupby("date", group_keys=False).apply(qbin)
    panel["young"] = (panel["first"] > pd.Timestamp(DATA_START_TOL)) & \
                     ((panel["date"] - panel["first"]).dt.days < 365)
    panel["new_list"] = panel["first"] > pd.Timestamp(DATA_START_TOL)
    panel["px_lt1"] = panel["close"] < 1
    panel["px_lt5"] = panel["close"] < 5
    panel["dv_lt1m"] = panel["dv20"] < 1e6
    panel["dv_lt5m"] = panel["dv20"] < 5e6
    panel["bottom"] = panel["dd"] <= BOTTOM_DD
    panel["bottom_mild"] = panel["dd"] <= BOTTOM_DD_MILD
    panel["spike"] = panel["r20"] >= SPIKE_R20
    panel["breakout"] = panel["at_high"] & (panel["dd"] >= 0.999)

    lines = []
    w = lines.append
    w(f"股票数 {len(meta)}；抽样横截面 {len(sample_dates)} 个（{sample_dates[0].date()}..{sample_dates[-1].date()}，每 {SAMPLE_EVERY} 个交易日）；股票日样本 {len(panel)}")
    w("")
    w("== 1. 首个 / 末个交易日 ==")
    at_start = meta["first"] <= pd.Timestamp(DATA_START_TOL)
    w(f"首日在数据起点（≤{DATA_START_TOL}）：{at_start.sum()}；之后才有数据（新上市、改名换码或转板）：{(~at_start).sum()}")
    fy = meta.loc[~at_start, "first"].dt.year.value_counts().sort_index()
    w("之后才有数据的按首日年份：" + "，".join(f"{y}: {n}" for y, n in fy.items()))
    w(f"首日最早 {meta['first'].min().date()}，最晚 {meta['first'].max().date()}")
    lv = meta["last"].value_counts().sort_index()
    w(f"末个交易日分布（最后 5 种）：{lv.tail(5).to_dict()}；早于 2026-09-01 结束的序列 {(meta['last'] < pd.Timestamp('2026-09-01')).sum()} 只")
    sfx = meta["symbol"].str.contains(r"[-.]") | ((meta["symbol"].str.len() == 5) & meta["symbol"].str[-1].isin(list("WRU")))
    w(f"疑似非普通股代码（5 位且以 W/R/U 结尾，或含 - .）：{sfx.sum()}，例：{meta.loc[sfx, 'symbol'].head(12).tolist()}")
    w("")
    w("== 2. 最新一天（价格未被以后的拆股改写）==")
    lc, ldv = meta["last_close"], meta["last_dv20"]
    w(f"收盘 <1 美元 {np.mean(lc < 1):.1%}；<5 美元 {np.mean(lc < 5):.1%}；中位 {lc.median():.2f}")
    w(f"20 日成交额中位 <100 万美元 {np.mean(ldv < 1e6):.1%}；<500 万 {np.mean(ldv < 5e6):.1%}；中位 {ldv.median()/1e6:.1f} 百万")
    w("")
    w("== 3. 幸存的濒死股 ==")
    for thr in (0.1, 0.05, 0.02):
        n = (meta["min_dd"] <= thr).sum()
        w(f"曾跌到一年内最高收盘的 {thr:.0%} 以下（跌掉 {1-thr:.0%}+）后仍活到今天：{n} 只（{n/len(meta):.1%}）")
    w("")
    w("== 4. 横截面：各波动档里的状态占比（抽样日平均，股票日加权）==")
    cols = ["px_lt1", "px_lt5", "dv_lt1m", "dv_lt5m", "young", "new_list", "bottom", "bottom_mild", "spike", "breakout"]
    tab = panel.groupby("q")[cols].mean()
    tab["M中位"] = panel.groupby("q")["M"].median()
    tab["上线涨幅(1+5M)-1"] = 5 * tab["M中位"]
    w(tab.to_string(float_format=lambda x: f"{x:.3f}"))
    w("")
    w("== 5. 状态 vs 同日同档普通股：风险特征差多少 ==")
    w("（每个状态在每个档内的特征占比，对照是同档全部股票日；只报样本 ≥200 的档）")
    rows = []
    for state in ["bottom", "bottom_mild", "spike", "breakout"]:
        for q in range(5):
            g = panel[panel["q"] == q]
            s = g[g[state]]
            if len(s) < 200:
                continue
            row = {"状态": state, "档": q, "状态样本": len(s), "占本档": len(s) / len(g)}
            for c in ["px_lt1", "px_lt5", "dv_lt1m", "dv_lt5m", "young"]:
                row[c + "_状态"] = s[c].mean()
                row[c + "_同档"] = g[c].mean()
            rows.append(row)
    comp = pd.DataFrame(rows)
    w(comp.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    w("")
    w("== 6. 状态在各档的分布（这个状态的股票日有多少落在最高波动档）==")
    for state in ["bottom", "bottom_mild", "spike", "breakout"]:
        d = panel.loc[panel[state], "q"].value_counts(normalize=True).sort_index()
        w(f"{state}: " + "，".join(f"档{k}: {v:.1%}" for k, v in d.items()) + f"（共 {panel[state].sum()}）")
    w("")
    w("== 7. 限定股票池后还剩多少状态样本 ==")
    pool_rules = {
        "全部": np.ones(len(panel), bool),
        "成交额≥100万": ~panel["dv_lt1m"].to_numpy(),
        "成交额≥500万": ~panel["dv_lt5m"].to_numpy(),
        "价≥5 & 成交额≥500万": (~panel["px_lt5"] & ~panel["dv_lt5m"]).to_numpy(),
        "价≥5 & 成交额≥500万 & 非新上市一年内": (~panel["px_lt5"] & ~panel["dv_lt5m"] & ~panel["young"]).to_numpy(),
    }
    for name, keep in pool_rules.items():
        sub = panel[keep]
        parts = [f"全部股票日 {keep.mean():.1%}"]
        for state in ["bottom", "bottom_mild", "spike", "breakout"]:
            parts.append(f"{state} 留 {sub[state].sum() / max(panel[state].sum(), 1):.1%}")
        w(f"{name}: " + "；".join(parts))
    w("")
    w("== 8. 按年份：大跌后状态的股票日占比（看 2022-2023 退市高峰期）==")
    panel["year"] = panel["date"].dt.year
    yr = panel.groupby("year")[["bottom", "bottom_mild", "spike", "px_lt1", "dv_lt1m"]].mean()
    yr["存活股数(抽样日均)"] = panel.groupby("year").size() / panel.groupby("year")["date"].nunique()
    w(yr.to_string(float_format=lambda x: f"{x:.3f}"))

    out = "\n".join(lines)
    print(out)
    with open(os.path.join(OUT_DIR, "04-universe_facts_out.txt"), "w") as fh:
        fh.write(out + "\n")
    comp.to_csv(os.path.join(OUT_DIR, "04-universe_states.csv"), index=False)


if __name__ == "__main__":
    main()
