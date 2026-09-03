"""
日历聚类何时咬人：全宇宙事件样本按财报季聚集，各季共享市场冲击。
对比 ① 两臂在各季均衡（分层设计） ② 两臂在季上不均衡（treated 集中在少数季）。
真实效应 = 0（纯 null），看 95% CI 的假阳率（名义应为 5%）。
"""
import json, numpy as np
fr = np.array([r["fr_recalc"] for r in json.load(open(
  "docs/research/2026-08-16_news-sentiment-path2-integration/repro/full_metrics_20260816-193657.json"))
  if r.get("fr_recalc") is not None])
rng = np.random.default_rng(11); NB, NSIM, K, NARM = 1500, 300, 20, 400
SIG = 0.25  # 各财报季共享的市场冲击（log 尺度 sd）

def draw(cluster_ids, shocks):
    base = rng.choice(fr, len(cluster_ids), True)
    return (1 + base) * np.exp(shocks[cluster_ids]) - 1

def fp_rate(balanced):
    hits = 0
    for _ in range(NSIM):
        shocks = rng.normal(0, SIG, K)
        if balanced:
            ca = rng.integers(0, K, NARM); cb = rng.integers(0, K, NARM)
        else:  # treated 集中在 4 个季，control 铺满 20 个季
            ca = rng.integers(0, 4, NARM); cb = rng.integers(0, K, NARM)
        a, b = draw(ca, shocks), draw(cb, shocks)
        d = np.median(rng.choice(a, (NB, NARM), True), axis=1) - np.median(rng.choice(b, (NB, NARM), True), axis=1)
        lo, hi = np.percentile(d, [2.5, 97.5]); hits += (lo > 0) or (hi < 0)
    return hits / NSIM
print(f"[null 假阳率] 名义 5%,  K={K} 季, n/arm={NARM}, 季共享冲击 sd={SIG}")
print(f"  ① 两臂各季均衡（分层设计）      : {fp_rate(True):.3f}")
print(f"  ② treated 集中在 4 季（不均衡）  : {fp_rate(False):.3f}")
