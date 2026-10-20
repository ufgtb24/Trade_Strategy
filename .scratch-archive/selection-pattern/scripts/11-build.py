"""11 同日对照配对票 · 第二步：逐行结果（各把尺子）、13 种配对的格子 / 近邻、池子日规模。

输出：scratchpad/11/build.npz（Y_*、hold_*、cell_*、neigh）与 scripts/11-build_out.txt（口径自检与规模）。
运行：uv run python .scratch/selection-pattern/scripts/11-build.py
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("core11", HERE / "11-core.py")
core = importlib.util.module_from_spec(spec); sys.modules["core11"] = core; spec.loader.exec_module(core)

CELL_SCHEMES = {"M5": ("band", 5), "M10": ("band", 10), "M20": ("band", 20),
                "M3xH3": ("nest", 3, 3), "M5xH5": ("nest", 5, 5), "M10xH3": ("nest", 10, 3),
                "M10xH5": ("nest", 10, 5), "M20xH3": ("nest", 20, 3)}
KNN_K = (10, 20, 50, 100)


def main():
    t0 = time.time()
    P = core.load_panel()
    out = []
    Y, hold = core.outcomes(P)
    w5 = np.log1p(5 * P["M"])
    r5_dir = np.where(Y["R5"] >= np.expm1(w5) - 1e-9, 1, np.where(Y["R5"] <= np.expm1(-w5) + 1e-9, -1, 0))
    agree = float((r5_dir == P["dir"]).mean())
    out.append(f"行数 {P['N']:,}，股票 {len(P['symbols'])}，决策日 {len(P['calendar'])}（"
               f"{pd.Timestamp(P['calendar'][0]).date()}..{pd.Timestamp(P['calendar'][-1]).date()}）")
    out.append(f"自检：R5 触线方向与 labels.dir 一致的比例 {agree:.6f}")
    n_day = np.bincount(P["d"])
    yr_day = pd.DatetimeIndex(P["calendar"]).year
    out.append("池子每天只数（中位 / 最少 / 最多）按年：" + "；".join(
        f"{y}: {int(np.median(n_day[yr_day == y]))} / {n_day[yr_day == y].min()} / {n_day[yr_day == y].max()}"
        for y in sorted(set(yr_day))))
    out.append("严格版平时波动缺失、配对用退路版的行占比，按年：" + "；".join(
        f"{y}: {np.mean(~np.isfinite(P['Mh'][P['year'] == y])):.3f}" for y in sorted(set(P['year']))))
    for r in core.RULES:
        out.append(f"  {r} {core.RULES[r][0]}：全池每笔收益 中位 {np.median(Y[r]):+.4f} 均值 {Y[r].mean():+.4f}，"
                   f"平均持有 {hold[r].mean():.1f} 日")
    out.append(f"  dir 均值 {Y['dir'].mean():+.4f}；mag 中位 {np.median(Y['mag']):.4f}")
    save = {f"Y_{k}": v for k, v in Y.items()}
    save.update({f"hold_{k}": v for k, v in hold.items()})
    for name, spec_ in CELL_SCHEMES.items():
        c = core.cells_band(P, spec_[1]) if spec_[0] == "band" else core.cells_nested(P, spec_[1], spec_[2])
        save[f"cell_{name}"] = c
        cnt = np.bincount(c)
        sz = cnt[c]
        out.append(f"  配对 {name}：每天格数中位 {int(np.median(np.bincount(np.unique(np.c_[P['d'], c], axis=0)[:, 0])))}，"
                   f"行所在格的成员数 中位 {int(np.median(sz))}，<10 的行占 {np.mean(sz < 10):.4f}，<20 的占 {np.mean(sz < 20):.4f}")
    neigh = core.knn_neighbors(P, max(KNN_K))
    save["neigh"] = neigh
    out.append(f"  近邻矩阵 {neigh.shape}，缺位（当天不足 K 只）比例 {np.mean(neigh < 0):.5f}")
    np.savez(core.SCR / "build.npz", **save)
    out.append(f"耗时 {time.time() - t0:.0f}s")
    txt = "\n".join(out)
    print(txt)
    (HERE / "11-build_out.txt").write_text(txt + "\n")


if __name__ == "__main__":
    main()
