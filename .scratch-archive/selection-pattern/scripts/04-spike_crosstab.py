"""04 票补充：暴涨后（近 20 日涨 ≥50%）的股票日里，有多少同时还处在大跌之后（反弹型暴涨），
以及它们的低价 / 低成交额占比。只用买入当天及以前的数据。
运行：uv run python .scratch/selection-pattern/scripts/04-spike_crosstab.py
"""
import glob, os
import numpy as np, pandas as pd

ROOT = "/home/yu/PycharmProjects/Trade_Strategy"
rows = []
for p in sorted(glob.glob(os.path.join(ROOT, "datasets/pkls/*.pkl"))):
    df = pd.read_pickle(p)[["high", "low", "close", "volume"]].astype(float)
    df = df[df.close > 0]
    c = df.close; prev = c.shift(1)
    tr = pd.concat([df.high - df.low, (df.high - prev).abs(), (df.low - prev).abs()], axis=1).max(axis=1)
    f = pd.DataFrame({"M": (tr / c).rolling(20).median(),
                      "dv20": (c * df.volume).rolling(20).median(),
                      "dd": c / c.rolling(252, min_periods=1).max(),
                      "r20": c / c.shift(20) - 1, "close": c})
    f = f[f.index >= "2022-01-03"].iloc[::5].dropna()
    rows.append(f)
panel = pd.concat(rows).reset_index()
panel["q"] = panel.groupby("date")["M"].transform(lambda s: np.searchsorted(np.unique(np.quantile(s, [.2, .4, .6, .8])), s, side="left"))
spk = panel[panel.r20 >= 0.5]
top = panel[panel.q == 4]
print(f"暴涨后股票日 {len(spk)}；其中仍在一年高点的 50% 以下（反弹型）{(spk.dd <= 0.5).mean():.1%}，30% 以下 {(spk.dd <= 0.3).mean():.1%}")
for name, s in [("反弹型暴涨(dd≤0.5)", spk[spk.dd <= 0.5]), ("高位暴涨(dd>0.5)", spk[spk.dd > 0.5]), ("最高档全部", top)]:
    print(f"{name}: n={len(s)} 价<1 {np.mean(s.close < 1):.3f} 价<5 {np.mean(s.close < 5):.3f} 成交额<100万 {np.mean(s.dv20 < 1e6):.3f} 成交额<500万 {np.mean(s.dv20 < 5e6):.3f}")
