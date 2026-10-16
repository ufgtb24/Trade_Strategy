"""02 分辨力研究 · 副产品核查：当天波动排位处于极端（最低 / 最高 2%）的全部普通买入，对同日五档对照的领先，逐年看稳不稳。

不抽样：取全部符合条件的股票日，按年算「方向值 − 所在档对照均值」的均值与「前瞻收益 − 所在档中位数」的中位数，
另报这些股票日的 M 中位数、碰到线比例、先上 / 先下比例。观察期 20 / 40 日，k=5。
输出：打印 + scripts/02-voltilt-extreme.txt
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("core02", HERE / "02-core.py")
core = importlib.util.module_from_spec(spec); sys.modules["core02"] = core; spec.loader.exec_module(core)

out = []
for H in (20, 40):
    pool = core.load_pool(H)
    rank = pd.Series(pool.M).groupby(pool.d).rank(pct=True).to_numpy()
    year = pd.DatetimeIndex(pool.calendar[pool.d]).year
    for name, m in (("当天波动最低 2%", rank <= 0.02), ("当天波动最高 2%", rank >= 0.98), ("全部", np.ones(len(rank), bool))):
        df = pd.DataFrame({"y": year[m], "e": pool.e_dir[m], "eu": pool.e_up[m], "dir": pool.dir[m]})
        by = df.groupby("y").agg(n=("e", "size"), dir_lead=("e", "mean"), amp_excess=("eu", "median"))
        out.append(f"H={H} {name}: 股票日 {m.sum():,}  M 中位 {np.median(pool.M[m]):.4f}  碰线 {(pool.dir[m] != 0).mean():.2f}  "
                   f"先上 {(pool.dir[m] == 1).mean():.2f} 先下 {(pool.dir[m] == -1).mean():.2f}  "
                   f"方向领先 {pool.e_dir[m].mean():+.3f}  幅度超额中位 {np.median(pool.e_up[m]):+.4f}")
        out.append("   逐年 方向领先: " + "  ".join(f"{y}:{v:+.3f}" for y, v in by["dir_lead"].items())
                   + " | 幅度超额中位: " + "  ".join(f"{y}:{v:+.4f}" for y, v in by["amp_excess"].items()))
text = "\n".join(out)
print(text)
(HERE / "02-voltilt-extreme.txt").write_text(text + "\n")
