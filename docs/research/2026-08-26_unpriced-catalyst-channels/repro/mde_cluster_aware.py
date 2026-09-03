"""
FinChannel 的质疑：我的 MDE 模拟按「行」独立抽，而真实数据是 112 行 → 82 symbol →
营收口径下仅 44 个独立 (symbol,财季) 对；treatment 在 **cluster 层**分配
（同一 symbol 的多行共享同一个财务量取值）⟹ 按行抽会系统性低估 MDE。

本脚本给出三个版本的对照，并回答他要的 n_treat≈25 / ≈40：
  A 行级分配（我原版，作为参照）
  B cluster 级分配 + 真实 cluster size 分布 + 实测组内相关
  C 直接按「独立 cluster 数」参数化（他真正要的：全宇宙要跑多少独立事件）
"""
import json, numpy as np
from collections import defaultdict
SRC = "docs/research/2026-08-16_news-sentiment-path2-integration/repro/full_metrics_20260816-193657.json"
rows = [r for r in json.load(open(SRC)) if r.get("fr_recalc") is not None]
by = defaultdict(list)
for r in rows: by[r["symbol"]].append(r["fr_recalc"])
fr = np.array([r["fr_recalc"] for r in rows])
sizes = np.array([len(v) for v in by.values()])
# 组内相关 ICC（单向随机效应，用 log1p 稳住右偏）
y = {s: np.log1p(np.clip(v, -0.99, None)) for s, v in by.items()}
allv = np.concatenate(list(y.values())); gm = allv.mean()
k_grp = len(y); n_tot = len(allv)
ms = np.array([len(v) for v in y.values()])
msb = sum(len(v) * (np.mean(v) - gm)**2 for v in y.values()) / (k_grp - 1)
msw = sum(((np.array(v) - np.mean(v))**2).sum() for v in y.values()) / (n_tot - k_grp)
m0 = (n_tot - (ms**2).sum() / n_tot) / (k_grp - 1)
icc = max((msb - msw) / (msb + (m0 - 1) * msw), 0.0)
print(f"[cluster 结构] 行={len(rows)} symbol={k_grp} size分布={dict(zip(*np.unique(sizes,return_counts=True)))}")
print(f"[组内相关] ICC(log1p fr, 按 symbol) = {icc:.3f}   (m0={m0:.2f})")
print(f"[含义] 多行 symbol 只占 {(sizes>1).sum()}/{k_grp}；ICC 越高，行级抽样越高估精度\n")

rng = np.random.default_rng(2026); NB = 2000
def ci_hit(a, b):
    ba = np.median(rng.choice(a, (NB, len(a)), True), axis=1)
    bb = np.median(rng.choice(b, (NB, len(b)), True), axis=1)
    lo, hi = np.percentile(ba - bb, [2.5, 97.5])
    return (lo > 0) or (hi < 0)

def power_row(n_t, n_c, c, nsim=400):
    h = 0; ds = []
    for _ in range(nsim):
        ctl = rng.choice(fr, n_c, True); trt = (1 + rng.choice(fr, n_t, True)) * c - 1
        ds.append(np.median(trt) - np.median(ctl)); h += ci_hit(trt, ctl)
    return h / nsim, float(np.median(ds))

sym_pool = list(by.values())
def power_cluster(k_t, k_c, c, nsim=400):
    """treatment 按 symbol 分配：抽 k_t 个 symbol 进 treated，整簇同时被处理。"""
    h = 0; ds = []
    for _ in range(nsim):
        it = rng.integers(0, len(sym_pool), k_t); ic = rng.integers(0, len(sym_pool), k_c)
        trt = np.concatenate([(1 + np.array(sym_pool[i])) * c - 1 for i in it])
        ctl = np.concatenate([np.array(sym_pool[i]) for i in ic])
        ds.append(np.median(trt) - np.median(ctl)); h += ci_hit(trt, ctl)
    return h / nsim, float(np.median(ds))

print("=== A/B 对照：FinChannel 要的 n_treat ≈ 25 与 ≈ 40 ===")
print(f"{'设计':<28}{'c':>6}{'Δmedian':>10}{'power':>8}")
for n_t in (25, 40):
    for c in (1.20, 1.25, 1.30, 1.35, 1.40, 1.50):
        p, d = power_row(n_t, 112 - n_t, c)
        print(f"{'A 行级 n_t='+str(n_t):<28}{c:>6.2f}{d:>10.3f}{p:>8.2f}")
        if p >= 0.8: break
    k_t = max(int(round(n_t / (len(rows) / k_grp))), 2)     # 折成 symbol 数
    for c in (1.20, 1.25, 1.30, 1.35, 1.40, 1.50):
        p, d = power_cluster(k_t, k_grp - k_t, c)
        print(f"{'B cluster 级 k_t='+str(k_t):<28}{c:>6.2f}{d:>10.3f}{p:>8.2f}")
        if p >= 0.8: break
    print("-")

print("\n=== C 全宇宙：按【独立 cluster 数】看要跑多少（1:1，每簇 1 事件）===")
print(f"{'k/arm':>7}{'c':>6}{'Δmedian':>10}{'power':>8}")
for k in (200, 400, 800, 1600, 3200):
    for c in (1.05, 1.08, 1.10, 1.15, 1.20):
        p, d = power_row(k, k, c, nsim=250)
        print(f"{k:>7}{c:>6.2f}{d:>10.3f}{p:>8.2f}")
        if p >= 0.8: break
    print("-")
