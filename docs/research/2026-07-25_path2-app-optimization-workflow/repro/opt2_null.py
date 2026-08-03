"""临时实验(opt):null harness —— 把零信号模型跑穿【真实的候选生成流程】。

mech 的建议(我采纳):不要估 K_eff,直接在零信号数据上跑一遍实际要用的那个
3x4x3 单调嵌套网格、按实际选点规则取胜者,重复上千次得到经验门槛。
这样门槛天然包含嵌套结构与选点规则,不需要任何"有效 K"假设。

同时回答 lead 的问题:「内层取平台中心而非 argmax,能省下多少选择偏差?」
  规则 A:全局 argmax
  规则 B:先按 3x3x3 邻域均值挑格点,再报该格点自身的 score(平台中心)
用完删。
"""
from __future__ import annotations

import itertools
import pathlib

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "temp_code" / "out2"
N0 = 200
REPS = 1200
RNG = np.random.default_rng(20260725)

# 三个 where 阈值 -> 每维的"通过比例"档位(选得使 n 落在真实 where 族的 83~912 量级)
F1 = (0.32, 0.22, 0.15)
F2 = (0.30, 0.24, 0.19, 0.14)
F3 = (0.30, 0.22, 0.16)
GRID = [(i, j, k) for i in range(len(F1)) for j in range(len(F2)) for k in range(len(F3))]
IDX = {g: n for n, g in enumerate(GRID)}


def neighbors(g):
    """3 维网格上的 3x3x3 邻域(含自身),越界丢弃。"""
    out = []
    for di, dj, dk in itertools.product((-1, 0, 1), repeat=3):
        h = (g[0] + di, g[1] + dj, g[2] + dk)
        if h in IDX:
            out.append(IDX[h])
    return out


NB = [neighbors(g) for g in GRID]


def main():
    D = pd.read_pickle(OUT / "rows_2025.pkl")
    pool = D[D.cfg == "bo_only"].mh20.values.astype(float)
    base = float(np.median(pool))
    N = len(pool)
    print(f"零信号池 = bo_only 买点 {N} 个, 基线 median={base:.4f}")
    print(f"网格 {len(GRID)} 个配置 (3x4x3 单调嵌套), REPS={REPS}")

    scores = np.zeros((REPS, len(GRID)))
    ns = np.zeros((REPS, len(GRID)))
    for r in range(REPS):
        u = RNG.random((3, N))
        for gi, (i, j, k) in enumerate(GRID):
            m = (u[0] >= 1 - F1[i]) & (u[1] >= 1 - F2[j]) & (u[2] >= 1 - F3[k])
            v = pool[m]
            n = len(v)
            ns[r, gi] = n
            scores[r, gi] = (n / (n + N0)) * (np.median(v) - base) if n else 0.0

    print(f"\n各配置 n 的范围: min={ns.min():.0f} median={np.median(ns):.0f} "
          f"max={ns.max():.0f}   (真实 where 族 83~2844)")
    print(f"单个配置 score 的 SD = {scores.std(axis=0).mean():.4f}  "
          f"(实测边际 SE(score) @ n=423 = 0.0128)")

    # ---- 规则 A vs 规则 B ----
    win_a = scores.max(axis=1)
    nb_mean = np.stack([scores[:, nb].mean(axis=1) for nb in NB], axis=1)
    pick_b = nb_mean.argmax(axis=1)
    win_b = scores[np.arange(REPS), pick_b]
    win_b_nb = nb_mean.max(axis=1)          # 若直接报邻域均值(更强的收缩)

    print(f"\n=== 零信号下冠军 score 的膨胀（这就是门槛）===")
    print(f"  {'规则':<34s} {'均值':>8s} {'中位':>8s} {'p90':>8s} {'p95':>8s}")
    for lbl, w in (("A · 全局 argmax", win_a),
                   ("B · 平台中心(报该点自身 score)", win_b),
                   ("B' · 平台中心(报邻域均值)", win_b_nb)):
        print(f"  {lbl:<34s} {w.mean():8.4f} {np.median(w):8.4f} "
              f"{np.percentile(w,90):8.4f} {np.percentile(w,95):8.4f}")
    print(f"\n  B 相对 A 省下: 均值 {1-win_b.mean()/win_a.mean():.1%}   "
          f"p95 {1-np.percentile(win_b,95)/np.percentile(win_a,95):.1%}")
    print(f"  B' 相对 A 省下: 均值 {1-win_b_nb.mean()/win_a.mean():.1%}   "
          f"p95 {1-np.percentile(win_b_nb,95)/np.percentile(win_a,95):.1%}")

    # ---- 嵌套 vs 独立:同样 K 的门槛差多少 ----
    print(f"\n=== 嵌套网格 vs 「独立候选」假设（同 K=36）===")
    # 独立对照:每个配置用独立抽的 u(打破嵌套)
    ind = np.zeros((REPS, len(GRID)))
    for r in range(REPS):
        for gi, (i, j, k) in enumerate(GRID):
            u = RNG.random(N)
            m = u >= 1 - F1[i] * F2[j] * F3[k]
            v = pool[m]
            n = len(v)
            ind[r, gi] = (n / (n + N0)) * (np.median(v) - base) if n else 0.0
    print(f"  嵌套网格 argmax  均值={win_a.mean():.4f}  p95={np.percentile(win_a,95):.4f}")
    print(f"  独立候选 argmax  均值={ind.max(axis=1).mean():.4f}  "
          f"p95={np.percentile(ind.max(axis=1),95):.4f}")
    print(f"  ⟹ 嵌套使门槛降低 {1-win_a.mean()/ind.max(axis=1).mean():.1%}（均值口径）")

    # ---- 冠军 n 的偏向 ----
    print(f"\n=== 冠军落在小 n 的偏向（skeptic §3.3 的机制）===")
    wn_a = ns[np.arange(REPS), scores.argmax(axis=1)]
    wn_b = ns[np.arange(REPS), pick_b]
    med_n = np.median(ns)
    print(f"  全部配置 n 中位数 = {med_n:.0f}")
    print(f"  规则 A 冠军 n 中位 = {np.median(wn_a):.0f}   "
          f"落在下四分位的比例 = {(wn_a < np.percentile(ns,25)).mean():.1%}")
    print(f"  规则 B 冠军 n 中位 = {np.median(wn_b):.0f}   "
          f"落在下四分位的比例 = {(wn_b < np.percentile(ns,25)).mean():.1%}")


if __name__ == "__main__":
    main()
