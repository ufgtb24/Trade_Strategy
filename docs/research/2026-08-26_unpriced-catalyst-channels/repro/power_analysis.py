"""
最小可行样本量 / 最小可检出效应（MDE）估计。

背景：上一轮 bb 买点样本 112 行，分组后 n 常掉到 5-14，bootstrap CI 极宽。
本脚本用**真实 fr 经验分布**（full_metrics_20260816-193657.json 的 fr_recalc）
做参数化 bootstrap 功效模拟，回答：
  - 在 n_treat ∈ {5,10,15,30,56} 下，fr median 差要多大才能让 bootstrap 95% CI 不跨 0（power=0.8）？
  - FPR_k6（组级 up/(up+down) 比率）同样条件下的 MDE 是多少？

治疗模型：treated 组的毛收益 (1+fr) 乘以常数 c（乘性移位，对右偏分布是自然的），
c 从 1.0 扫到 3.0。报告 power 与对应的 fr median 绝对差。
"""
import json, numpy as np, sys

SRC = "docs/research/2026-08-16_news-sentiment-path2-integration/repro/full_metrics_20260816-193657.json"
rows = json.load(open(SRC))
fr = np.array([r["fr_recalc"] for r in rows if r.get("fr_recalc") is not None], dtype=float)
print(f"[样本] 有效 fr 行数 = {len(fr)}, median={np.median(fr):.4f}, "
      f"q25={np.percentile(fr,25):.4f}, q75={np.percentile(fr,75):.4f}, "
      f"mean={fr.mean():.4f}, max={fr.max():.4f}")

# 独立 symbol 数（聚类结构 → 有效样本量折扣）
syms = [r["symbol"] for r in rows]
print(f"[样本] 行数={len(rows)}, 独立 symbol={len(set(syms))}, "
      f"最大单 symbol 行数={max(syms.count(s) for s in set(syms))}")
dates = sorted(r["buy_date"] for r in rows)
print(f"[样本] buy_date 范围 {dates[0]} .. {dates[-1]}")

# FPR 结构
fp6 = [r["fp"]["6"] for r in rows if r.get("fp")]
from collections import Counter
c6 = Counter(fp6)
det = c6["up"] + c6["down"]
print(f"[FPR k=6] up={c6['up']} down={c6['down']} none={c6.get('none',0)} "
      f"→ 判定率={det/len(fp6):.3f}, 基线 FPR={c6['up']/det:.3f}")

rng = np.random.default_rng(42)
NSIM, NBOOT = 600, 2000

def power_median(n_t, n_c, c, nsim=NSIM):
    """treated 组毛收益 ×c，问 bootstrap 95% CI(median_t - median_c) 不跨 0 的比例。"""
    hits, deltas = 0, []
    for _ in range(nsim):
        ctl = rng.choice(fr, n_c, replace=True)
        trt = (1.0 + rng.choice(fr, n_t, replace=True)) * c - 1.0
        d = np.median(trt) - np.median(ctl)
        deltas.append(d)
        bt = np.median(rng.choice(trt, (NBOOT, n_t), replace=True), axis=1)
        bc = np.median(rng.choice(ctl, (NBOOT, n_c), replace=True), axis=1)
        lo, hi = np.percentile(bt - bc, [2.5, 97.5])
        hits += (lo > 0) or (hi < 0)
    return hits / nsim, float(np.median(deltas))

def power_prop(n_t, n_c, p_t, p_c, det_rate, nsim=NSIM):
    """FPR 组级比率差的 bootstrap 功效。det_rate = 有判定（非 none）比例。"""
    hits = 0
    for _ in range(nsim):
        kt = rng.binomial(n_t, det_rate); kc = rng.binomial(n_c, det_rate)
        if kt < 2 or kc < 2:
            continue
        ut = rng.binomial(1, p_t, kt); uc = rng.binomial(1, p_c, kc)
        bt = rng.binomial(kt, ut.mean(), NBOOT) / kt
        bc = rng.binomial(kc, uc.mean(), NBOOT) / kc
        lo, hi = np.percentile(bt - bc, [2.5, 97.5])
        hits += (lo > 0) or (hi < 0)
    return hits / nsim

print("\n=== fr median：功效表（对照组 n_c = 112 - n_t）===")
print(f"{'n_treat':>7} {'c(乘性)':>8} {'Δfr median':>12} {'power':>7}")
out = {}
for n_t in (5, 10, 15, 30, 56):
    n_c = 112 - n_t
    for c in (1.1, 1.2, 1.4, 1.7, 2.0, 2.5, 3.0):
        p, d = power_median(n_t, n_c, c)
        print(f"{n_t:>7} {c:>8.1f} {d:>12.3f} {p:>7.2f}")
        out[(n_t, c)] = (p, d)
    print("-")

print("\n=== fr median MDE（power≥0.8 的最小 c 与对应 Δ）===")
for n_t in (5, 10, 15, 30, 56):
    ok = [(c, out[(n_t, c)]) for c in (1.1,1.2,1.4,1.7,2.0,2.5,3.0) if out[(n_t,c)][0] >= 0.8]
    if ok:
        c, (p, d) = ok[0]
        print(f"  n_treat={n_t:>3}: c={c}  Δfr median≈{d:.2f}  (power={p:.2f})")
    else:
        print(f"  n_treat={n_t:>3}: 扫描区间(c≤3.0, 即 Δ≈+2 的巨大效应)内无 power≥0.8 —— 不可检出")

base_p = c6["up"] / det
det_rate = det / len(fp6)
print(f"\n=== FPR_k6：功效表（基线 p={base_p:.3f}, 判定率={det_rate:.3f}）===")
print(f"{'n_treat':>7} {'p_treat':>8} {'Δp':>7} {'power':>7}")
for n_t in (15, 30, 56):
    n_c = 112 - n_t
    for p_t in (0.60, 0.70, 0.80, 0.90, 1.00):
        pw = power_prop(n_t, n_c, p_t, base_p, det_rate)
        print(f"{n_t:>7} {p_t:>8.2f} {p_t-base_p:>7.2f} {pw:>7.2f}")
    print("-")

print("\n=== 反推：要检出 Δfr median=+0.20（一个现实量级的效应）需要多大样本？===")
for n_t in (56, 100, 200, 400, 800):
    # 用同规模对照（1:1）近似全宇宙分层设计
    c = 1.0
    lo_c, hi_c = 1.0, 2.0
    # 二分找达到 Δ≈0.20 的 c
    for _ in range(30):
        mid = (lo_c + hi_c) / 2
        d = np.median((1 + fr) * mid - 1) - np.median(fr)
        if d < 0.20: lo_c = mid
        else: hi_c = mid
    c = (lo_c + hi_c) / 2
    p, d = power_median(n_t, n_t, c, nsim=300)
    print(f"  n_treat=n_ctl={n_t:>4}: c={c:.3f} Δ≈{d:.3f} power={p:.2f}")
