"""09 目标池票 · 第一步：每只股票每个交易日「当天就知道」的特征面板（不读任何买点之后的涨跌）。

全部只用当天及以前的 K 线：
  close  复权收盘（当时价格还原不了时，价格上限只能拿它近似，见研究文件）
  dv20   20 日成交额（复权价 × 复权量，对拆合股不变）的中位数
  M      20 日「真实波幅 / 收盘」的中位数（与判优尺子的分档变量相同）
  Mh     过去 250 天 M 的中位数（至少 60 天），即「平时波动」
  dd     收盘 / 过去 252 天最高收盘（数据起点后不足一年时用已有部分）
  r20    20 日涨幅
  nb20   过去 20 天里收盘创 60 日新高的天数（密集突破的近似，burst 情形用）
  hi252  当天收盘创 252 日新高
行列与 02 的标签缓存对齐：行 = 02cache/meta.npz 的 symbols，列 = calendar。

输出：scratchpad/09/panel.npz
运行：uv run python .scratch/selection-pattern/scripts/09-panel.py
"""
from __future__ import annotations

from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/yu/PycharmProjects/Trade_Strategy")
SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad")
CACHE02 = SCR / "02cache"
OUT = SCR / "09" / "panel.npz"
FEATS = ("close", "dv20", "M", "Mh", "dd", "r20", "nb20", "hi252")


def one(args):
    sym, calendar = args
    raw = pd.read_pickle(ROOT / "datasets/pkls" / f"{sym}.pkl")
    df = raw[["high", "low", "close", "volume"]].astype(float)
    df.index = pd.DatetimeIndex(pd.to_datetime(df.index)).normalize()
    c, h, l = df["close"], df["high"], df["low"]
    prev = c.shift(1)
    tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    M = (tr / c).rolling(20).median()
    out = {
        "close": c,
        "dv20": (c * df["volume"]).rolling(20).median(),
        "M": M,
        "Mh": M.rolling(250, min_periods=60).median(),
        "dd": c / c.rolling(252, min_periods=1).max(),
        "r20": c / c.shift(20) - 1,
        "nb20": (c >= c.rolling(60, min_periods=20).max() - 1e-12).astype(float).rolling(20).sum(),
        "hi252": (c >= c.rolling(252, min_periods=1).max() - 1e-12).astype(float),
    }
    pos = np.searchsorted(calendar, df.index.to_numpy())
    ok = (pos < len(calendar)) & (calendar[np.minimum(pos, len(calendar) - 1)] == df.index.to_numpy())
    return sym, pos[ok], {k: v.to_numpy(np.float32)[ok] for k, v in out.items()}


def main():
    meta = np.load(CACHE02 / "meta.npz", allow_pickle=True)
    symbols, calendar = meta["symbols"], meta["calendar"]
    arr = {k: np.full((len(symbols), len(calendar)), np.nan, np.float32) for k in FEATS}
    with Pool(20) as p:
        for i, (sym, pos, vals) in enumerate(p.imap(one, [(s, calendar) for s in symbols], chunksize=16)):
            assert sym == symbols[i]
            for k in FEATS:
                arr[k][i, pos] = vals[k]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez(OUT, symbols=symbols, calendar=calendar, **arr)
    print("saved", OUT, {k: float(np.isfinite(v).mean()) for k, v in arr.items()})


if __name__ == "__main__":
    main()
