"""02 分辨力研究 · 不独立的来源：同一只股票相隔 ℓ 个交易日的两个普通买入，结果有多相关。

对每档观察期 H：把「方向值 − 所在档对照均值」（方向残差）和「前瞻收益在所在档内的分位」（幅度残差，
用分位避免极端涨幅主导）摆成 [股票 × 交易日] 矩阵，算同股相隔 ℓ 日的相关系数。
另报单个买点方向残差的标准差（独立时偶然波动 = 它 / √买点数）。
输出：打印 + scripts/02-diag-acf.csv
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

LAGS = [1, 2, 3, 5, 10, 20, 30, 40, 60, 80, 120, 160, 250, 375, 500]


def lag_corr(E: np.ndarray, lag: int) -> float:
    a, b = E[:, :-lag], E[:, lag:]
    m = np.isfinite(a) & np.isfinite(b)
    x, y = a[m], b[m]
    x = x - x.mean(); y = y - y.mean()
    return float((x @ y) / np.sqrt((x @ x) * (y @ y)))


rows = []
for H, k in [(5, 5.0), (20, 5.0), (40, 5.0), (120, 5.0), (5, 1.7678), (20, 3.5355), (120, 8.6603)]:
    pool = core.load_pool(H, k)
    shape = pool.rowidx.shape
    Ed = np.full(shape, np.nan); Ed[pool.sym, pool.d] = pool.e_dir
    Eu = np.full(shape, np.nan); Eu[pool.sym, pool.d] = pool.u_rank - 0.5
    sd_dir = float(pool.e_dir.std())
    sd_up = float(pool.up.std()); iqr_up = float(np.subtract(*np.percentile(pool.up, [75, 25])))
    rec = {"H": H, "k": k, "touched": float((pool.dir != 0).mean()), "sd_e_dir": sd_dir,
           "median_up": float(np.median(pool.up)), "iqr_up": iqr_up}
    for lag in LAGS:
        rec[f"dir_l{lag}"] = lag_corr(Ed, lag)
        rec[f"amp_l{lag}"] = lag_corr(Eu, lag)
    rows.append(rec)
    print(f"H={H} k={k:g} touched {rec['touched']:.3f} sd(方向残差) {sd_dir:.3f} 中位前瞻收益 {rec['median_up']:.3f}")
    print("  方向 ACF: " + " ".join(f"{l}:{rec[f'dir_l{l}']:.3f}" for l in LAGS))
    print("  幅度 ACF: " + " ".join(f"{l}:{rec[f'amp_l{l}']:.3f}" for l in LAGS))
pd.DataFrame(rows).to_csv(HERE / "02-diag-acf.csv", index=False)
