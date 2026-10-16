"""02 分辨力研究 · 自检：本研究的向量化计算与 tune-gates-v3 WindowPlan 逐位一致。

在一年的普通买入池上建 v3 WindowPlan，随机抽几组假买点，比较 Z、B、Δ（应在 1e-12 内相同），
并比较整只股票重抽的偶然波动（随机数映射不同，只要求量级一致）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / ".claude/skills/tune-gates-v3/scripts"))
spec = importlib.util.spec_from_file_location("core02", HERE / "02-core.py")
core = importlib.util.module_from_spec(spec); sys.modules["core02"] = core; spec.loader.exec_module(core)
from scoring import WindowPlan  # noqa: E402

pool = core.load_pool(40)
D0 = int(np.searchsorted(pool.calendar, np.datetime64("2024-07-01")))
D1 = int(np.searchsorted(pool.calendar, np.datetime64("2025-06-30")))
pd_ = core.plan_dates(pool, D0, D1)
seg = np.flatnonzero((pool.d >= D0) & (pool.d <= D1))
base = pd.DataFrame({
    "symbol": pool.symbols[pool.sym[seg]], "date": pool.calendar[pool.d[seg]],
    "upside": pool.up[seg], "up": (pool.dir[seg] == 1).astype(np.int8),
    "down": (pool.dir[seg] == -1).astype(np.int8), "both": np.zeros(len(seg), np.int8),
    "none": (pool.dir[seg] == 0).astype(np.int8), "M": pool.M[seg]})
plan = WindowPlan(base, horizon=40)
rng = np.random.default_rng(1)
for n in (50, 500, 5000):
    pick = np.sort(rng.choice(len(seg), n, replace=False))
    s = plan.summarize(base.iloc[pick])
    Z, B, dl, _ = core.v3_delta(pool, seg[pick], pd_)
    boot = plan.stock_bootstrap(base.iloc[pick], resamples=200, seed=3)
    mine = core.stock_bootstrap_v3(pool, seg[pick], pd_, 200, 3, base["symbol"].nunique())
    print(f"n={n}: v3 Z={s['raw_direction_score']:.12f} B={s['matched_direction_score']:.12f} "
          f"Δ={s['direction_difference']:.12f} | mine Z={Z:.12f} B={B:.12f} Δ={dl:.12f} | "
          f"diff {abs(dl - s['direction_difference']):.1e}; boot sd v3 {boot['delta_sd']:.4f} mine {mine:.4f}")
