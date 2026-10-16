"""02 分辨力研究 · 副产品核查（无未来信息版）：只按买点当天已知的波动水平挑股票，能白得多少领先？

02-voltilt.py 用「整段时期 M 的中位数」给股票分档，里面含买点之后的波动（未来信息），会夸大白得的领先。
这里只用买点当天及以前的信息：
- 习惯波动档：该股过去 250 个交易日（含当天）M 的中位数，在当天全部股票里排成十档；
- 当天波动排位：当天 M 在全部股票里的分位（v3 五档就是按它切的），取最高 2% / 最低 2%。
两年随机抽 2000 个买点（只从符合条件的股票日里抽），用同日按 M 切 5 / 10 / 20 档的对照算方向领先（合并口径）
与幅度领先（中位数之差），各重复 40 次取平均。H=40、k=5。
输出：打印 + scripts/02-voltilt-past.txt
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
vt_spec = importlib.util.spec_from_file_location("vt02", HERE / "02-voltilt.py")
vt = importlib.util.module_from_spec(vt_spec); sys.modules["vt02"] = vt; vt_spec.loader.exec_module(vt)


def main():
    pool = core.load_pool(40)
    df = pd.DataFrame({"sym": pool.sym, "d": pool.d, "M": pool.M})
    df = df.sort_values(["sym", "d"])
    df["habit"] = df.groupby("sym")["M"].transform(lambda s: s.rolling(250, min_periods=120).median())
    df = df.sort_index()
    habit = df["habit"].to_numpy()
    day_rank = df.groupby("d")["M"].rank(pct=True).to_numpy()
    ok = np.isfinite(habit)
    hdec = np.full(len(habit), -1)
    hr = pd.Series(habit).where(ok).groupby(pool.d).rank(pct=True).to_numpy()
    hdec[ok] = np.minimum((hr[ok] * 10).astype(int), 9)
    bins = {nb: vt.rebin(pool, nb) for nb in (5, 10, 20)}
    rng = np.random.default_rng(11)
    span = 504
    groups = {f"习惯波动档 {k}": hdec == k for k in (0, 2, 5, 7, 8, 9)}
    groups["当天波动最高 2%"] = day_rank >= 0.98
    groups["当天波动最低 2%"] = day_rank <= 0.02
    out = ["条件 | 方向领先 5档/10档/20档 | 幅度领先 5档/10档/20档（H=40，2 年 2000 买点，40 次平均；只用买点当天已知的波动）"]
    for name, mask in groups.items():
        res = {nb: ([], []) for nb in bins}
        for _ in range(40):
            D0 = int(rng.integers(pool.dates_present.min() + 250, pool.dates_present.max() - span + 2))
            rows = np.arange(np.searchsorted(pool.d, D0), np.searchsorted(pool.d, D0 + span))
            rows = rows[mask[rows]]
            rows = rng.choice(rows, min(2000, len(rows)), replace=False)
            for nb, (g, cnt, bdir, order) in bins.items():
                res[nb][0].append(float((pool.dir[rows] - bdir[g[rows]]).mean()))
                res[nb][1].append(float(vt.amp(pool, rows, g, cnt, order)))
        out.append(f"  {name}: 方向 " + " / ".join(f"{np.mean(res[nb][0]):+.3f}" for nb in bins)
                   + " | 幅度 " + " / ".join(f"{np.mean(res[nb][1]):+.4f}" for nb in bins))
        print(out[-1], flush=True)
    (HERE / "02-voltilt-past.txt").write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
