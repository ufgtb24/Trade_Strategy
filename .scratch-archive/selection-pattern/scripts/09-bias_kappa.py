"""09 目标池票 · 池内幸存者偏差对「成交额折扣 κ」的敏感度：其余假设固定取中间，只改 κ。

κ = 跌得一样深时，以后被摘牌的股票过成交额下限的比例 ÷ 幸存股的比例（09-bias.py 头注）。
看池子在 κ 取多少时才比全市场明显干净。
运行：uv run python .scratch/selection-pattern/scripts/09-bias_kappa.py
输出：本目录 09-bias_kappa_out.txt
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bias09", HERE / "09-bias.py")
b = importlib.util.module_from_spec(spec); sys.modules["bias09"] = b; spec.loader.exec_module(b)


def main():
    p = b.load_panel()
    top = p.mq == 4
    t0 = pd.Timestamp("2022-01-03")
    lines = ["买入日 2022-01-03，其余假设取中间；数字 = 白得的方向领先", ""]
    for pname in ("all_ext", "dv2M_px20_cap100M", "dv1M_px20_cap100M", "dv5M_px20_cap100M", "dv2M_cap100M"):
        lo, px, hi = b.POOLS[pname]
        inpool = b.pool_mask(p, lo, px, hi)
        pi = inpool.groupby(p.date).mean().mean()
        dvpass = b.pool_mask(p, lo, None, hi)
        pass_s = np.array([dvpass[top & (p.fs == i)].mean() for i in range(5)])
        q = p.loc[inpool].copy()
        q["pq"] = q.groupby("date")["M"].transform(
            lambda s: np.searchsorted(np.unique(np.quantile(s, [.2, .4, .6, .8])), s, side="left"))
        dfine = b.dead_fine("mid")
        comp = dfine * pass_s / (dfine * pass_s).sum()
        row = []
        for kappa in (0.2, 0.3, 0.4, 0.6, 0.8, 1.0):
            k_eff = kappa if lo > 0 else 1.0
            rho = float((dfine * pass_s).sum() * k_eff * b.PRICE_PASS[px]["mid"])
            cells = []
            for name, cut, ncomp in (("七成", 0.3, 3), ("九成", 0.1, 2)):
                mask = q.dd <= cut
                wq = q.loc[mask, "pq"].value_counts(normalize=True).reindex(range(5), fill_value=0).to_numpy()
                bs = q.assign(m=mask).groupby("pq")["m"].mean().reindex(range(5)).to_numpy()
                ratio = comp[:ncomp].sum() / bs[4]
                kt = lambda t: b.f_of(t, b.RATES["mid"]) / (1 - b.f_of(t, b.RATES["mid"])) * rho / pi
                cells.append(f"{name} {b.bias_series([t0], wq, bs, ratio, kt, 'mid')[0]:+.3f}")
            row.append(f"κ={kappa:g}: " + "，".join(cells))
            if lo == 0:
                break
        lines.append(f"{pname}：" + " | ".join(row))
    out = "\n".join(lines)
    print(out)
    (HERE / "09-bias_kappa_out.txt").write_text(out + "\n")


if __name__ == "__main__":
    main()
