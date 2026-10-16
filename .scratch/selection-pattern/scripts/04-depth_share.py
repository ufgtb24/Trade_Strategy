"""04 票补充：最高波动档里，不同跌幅深度的状态各占多少（幸存股实测 b_s），以及它们的低成交额占比。
只用买入当天及以前的数据。运行：uv run python .scratch/selection-pattern/scripts/04-depth_share.py
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
    f = pd.DataFrame({"M": (tr / c).rolling(20).median(), "dv20": (c * df.volume).rolling(20).median(),
                      "dd": c / c.rolling(252, min_periods=1).max()})
    rows.append(f[f.index >= "2022-01-03"].iloc[::5].dropna())
panel = pd.concat(rows).reset_index()
panel["q"] = panel.groupby("date")["M"].transform(lambda s: np.searchsorted(np.unique(np.quantile(s, [.2, .4, .6, .8])), s, side="left"))
for q in (3, 4):
    g = panel[panel.q == q]
    parts = []
    for thr in (0.5, 0.3, 0.2, 0.1):
        s = g[g.dd <= thr]
        parts.append(f"跌≥{1-thr:.0%}: 占本档 {len(s)/len(g):.3f}，其中成交额<100万 {np.mean(s.dv20 < 1e6):.2f}")
    print(f"档{q}（n={len(g)}）: " + "；".join(parts))
