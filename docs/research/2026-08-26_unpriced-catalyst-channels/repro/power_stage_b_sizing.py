"""阶段 b（全宇宙）需要多少事件才够？—— 按 symbol 聚类的功效模拟。

与 Falsifier 的 power_analysis.py 分工：那份回答「bb 内 112 行的 MDE 是多少」，
本份回答「若要检出 PEAD 量级的效应，全宇宙阶段需要抽多少个独立事件」。

fr 经验分布取自 bb 的 110 行重算值（右偏、长尾）。这是保守选择：
全宇宙样本的 fr 尾部没有 bb 这么极端，方差更小、所需 n 会更少。
治疗模型 = 毛收益乘性移位 (1+fr)*c，对右偏分布是自然的。
聚类：每个 symbol 贡献 m 行且共享同一处理状态与同一潜在效应，行内相关 rho。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
SRC = (OUT.parents[1] / "2026-08-16_news-sentiment-path2-integration" / "repro"
       / "full_metrics_20260816-193657.json")

rows = json.loads(SRC.read_text())
fr = np.array([r["fr_recalc"] for r in rows if r.get("fr_recalc") is not None], float)
rng = np.random.default_rng(42)
NBOOT = 600


def sim_power(n_clusters: int, c: float, nsim: int = 200) -> tuple[float, float]:
    """1:1 分组、按 cluster 抽样（每 cluster 1 行，即最干净的独立情形）。"""
    hits, deltas = 0, []
    half = n_clusters // 2
    for _ in range(nsim):
        ctl = rng.choice(fr, half, True)
        trt = (1 + rng.choice(fr, half, True)) * c - 1
        deltas.append(np.median(trt) - np.median(ctl))
        bt = np.median(rng.choice(trt, (NBOOT, half), True), axis=1)
        bc = np.median(rng.choice(ctl, (NBOOT, half), True), axis=1)
        lo, hi = np.percentile(bt - bc, [2.5, 97.5])
        hits += (lo > 0) or (hi < 0)
    return hits / nsim, float(np.median(deltas))


print(f"[fr 经验分布] n={len(fr)} median={np.median(fr):.4f} "
      f"q25={np.percentile(fr,25):.4f} q75={np.percentile(fr,75):.4f} max={fr.max():.2f}")
print("\n乘性效应 c 与 power（1:1 分组，每 cluster 1 行）")
print(f"{'n_clusters':>10} {'c':>6} {'Δfr_median':>11} {'power':>7}")
for n in (100, 200, 400, 800, 1600, 3200):
    for c in (1.05, 1.10, 1.20):
        p, dlt = sim_power(n, c)
        print(f"{n:>10} {c:>6.2f} {dlt:>11.4f} {p:>7.2f}")

print("\n[参考] bb 内部的有效 cluster 数：营收口径 44、runway 54、净利润 67、Form4-P 11")
