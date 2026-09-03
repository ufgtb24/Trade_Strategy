"""细化 MDE 网格：分离 n_treat 的真实功效差异 + 1:1 分层设计的样本量曲线。"""
import json, numpy as np
from collections import Counter
SRC = "docs/research/2026-08-16_news-sentiment-path2-integration/repro/full_metrics_20260816-193657.json"
rows = json.load(open(SRC))
fr = np.array([r["fr_recalc"] for r in rows if r.get("fr_recalc") is not None])
print(f"[fr 经验分布] n={len(fr)} median={np.median(fr):.4f} q10={np.percentile(fr,10):.4f} "
      f"q25={np.percentile(fr,25):.4f} q75={np.percentile(fr,75):.4f} q90={np.percentile(fr,90):.4f} max={fr.max():.2f}")
syms=[r['symbol'] for r in rows]
print(f"[聚类] 行={len(rows)} 独立symbol={len(set(syms))} 单symbol最多={max(syms.count(s) for s in set(syms))}行")
rng = np.random.default_rng(7); NBOOT=2000
def power_median(n_t,n_c,c,nsim=500):
    h=0; ds=[]
    for _ in range(nsim):
        ctl=rng.choice(fr,n_c,True); trt=(1+rng.choice(fr,n_t,True))*c-1
        ds.append(np.median(trt)-np.median(ctl))
        b=np.median(rng.choice(trt,(NBOOT,n_t),True),axis=1)-np.median(rng.choice(ctl,(NBOOT,n_c),True),axis=1)
        lo,hi=np.percentile(b,[2.5,97.5]); h+= (lo>0)or(hi<0)
    return h/nsim, float(np.median(ds))
print("\n=== 细网格（对照 n_c=112-n_t，模拟 bb 内部分组）===")
print(f"{'n_t':>4} {'c':>6} {'Δmedian':>9} {'power':>6}")
mde={}
for n_t in (5,15,30,56):
    for c in (1.20,1.25,1.30,1.35,1.40):
        p,d=power_median(n_t,112-n_t,c)
        print(f"{n_t:>4} {c:>6.2f} {d:>9.3f} {p:>6.2f}")
        if p>=0.8 and n_t not in mde: mde[n_t]=(c,d,p)
    print("-")
print("\n[bb 内部分组 MDE @power0.8]")
for n_t in (5,15,30,56):
    print(f"  n_t={n_t:>3}: " + (f"c={mde[n_t][0]:.2f} Δ≈{mde[n_t][1]:.2f}" if n_t in mde else "网格内未达"))
print("\n=== 1:1 平衡设计（全宇宙分层）样本量 → 可检出的 Δ ===")
print(f"{'n/arm':>6} {'c':>6} {'Δmedian':>9} {'power':>6}")
for n in (100,200,400,800,1600,3000):
    for c in (1.05,1.08,1.10,1.15,1.20):
        p,d=power_median(n,n,c,nsim=250)
        print(f"{n:>6} {c:>6.2f} {d:>9.3f} {p:>6.2f}")
        if p>=0.8: break
    print("-")
