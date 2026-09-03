# -*- coding: utf-8 -*-
"""agentA:组合规则网格搜索(物理可辩护阈值)。输出 repro/agentA_grid.csv + 控制台 top。

规则形式:原子条件 (feat, op, t);规则 = 单原子 / OR / AND。删除 = 触发规则。
指标:n_keep / med / fp(=up/(up+down+both)) / drop_mean_fr / drop_med_fr。
"""
from __future__ import annotations

from pathlib import Path
from itertools import combinations

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DF = pd.read_csv(HERE / "features.csv")
OUT = HERE / "agentA_grid.csv"

# 物理可辩护阈值网格(方向:触发=负面特征越界)
GRID: dict[str, tuple[str, list[float]]] = {
    "max_drop_pct":     (">=", [0.10, 0.12, 0.15, 0.20, 0.25]),
    "max_drop_tr":      (">=", [1.5, 2.0, 2.5, 3.0]),
    "max_drop_atr":     (">=", [1.5, 2.0, 2.5, 3.0]),
    "max_bear_body_atr": (">=", [1.0, 1.5, 2.0, 2.5, 3.0]),
    "max_consec_bear":  (">=", [2, 3, 4]),
    "bear_count":       (">=", [2, 3, 4]),
    "max_consec_down":  (">=", [2, 3, 4]),
    "dd_close":         ("<=", [-0.10, -0.15, -0.20, -0.30]),
    "dd_low":           ("<=", [-0.20, -0.30, -0.40]),
    "down_slope":       (">=", [0.03, 0.05, 0.08]),
    "slope_ratio":      (">=", [0.3, 0.5, 1.0]),
    "rev_days":         (">=", [4, 5, 6]),
    "max_upper_atr":    (">=", [1.5, 2.0]),   # 对照(已知弱)
}

BASE_MED = float(DF.fr.median())
_up, _dn, _bt = DF.fp_up.sum(), DF.fp_down.sum(), DF.fp_both.sum()
BASE_FP = _up / (_up + _dn + _bt)
BASE_MEAN = float(DF.fr.mean())


def trig(feat: str, op: str, t: float) -> np.ndarray:
    v = DF[feat].to_numpy()
    return v >= t if op == ">=" else v <= t


def metrics(drop: np.ndarray) -> dict:
    kept = DF[~drop]
    up, dn, bt = kept.fp_up.sum(), kept.fp_down.sum(), kept.fp_both.sum()
    return dict(
        n_drop=int(drop.sum()), n_keep=len(kept),
        med=float(kept.fr.median()) if len(kept) else np.nan,
        fp=up / (up + dn + bt) if up + dn + bt else np.nan,
        drop_mean_fr=float(DF[drop].fr.mean()) if drop.any() else np.nan,
        drop_med_fr=float(DF[drop].fr.median()) if drop.any() else np.nan,
        kept_mean_fr=float(kept.fr.mean()) if len(kept) else np.nan,
    )


def main() -> None:
    atoms = [(f, op, t) for f, (op, ts) in GRID.items() for t in ts]
    rows = []
    for f, op, t in atoms:
        rows.append(dict(rule=f"{f}{op}{t}", kind="single", **metrics(trig(f, op, t))))
    for (f1, o1, t1), (f2, o2, t2) in combinations(atoms, 2):
        if f1 == f2:
            continue
        a, b = trig(f1, o1, t1), trig(f2, o2, t2)
        rows.append(dict(rule=f"{f1}{o1}{t1} OR {f2}{o2}{t2}", kind="or", **metrics(a | b)))
        rows.append(dict(rule=f"{f1}{o1}{t1} AND {f2}{o2}{t2}", kind="and", **metrics(a & b)))
    g = pd.DataFrame(rows)
    g["d_med"] = g.med - BASE_MED
    g["d_fp"] = g.fp - BASE_FP
    g.to_csv(OUT, index=False)
    # 好规则 = 双升 + 删掉的确实是差样本 + 保留足够多
    ok = g[(g.n_keep >= 48) & (g.d_med > 0) & (g.d_fp > 0)
           & (g.drop_mean_fr < g.kept_mean_fr)]
    print(f"base: med={BASE_MED:.4f} fp={BASE_FP:.4f} mean={BASE_MEAN:.3f}")
    print(f"grid={len(g)} 双升且删差样本且n>=48: {len(ok)}")
    cols = ["rule", "kind", "n_drop", "n_keep", "med", "fp", "d_med", "d_fp",
            "drop_mean_fr", "drop_med_fr", "kept_mean_fr"]
    print("\n== 按 med 排序 top20 ==")
    print(ok.sort_values("med", ascending=False).head(20)[cols].round(4).to_string(index=False))
    print("\n== 按 (d_med+d_fp) 排序 top20 ==")
    ok2 = ok.assign(score=ok.d_med + ok.d_fp)
    print(ok2.sort_values("score", ascending=False).head(20)[cols].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
