"""
聚类结构对 CI 的影响：上一轮按「行」重采样的 bootstrap 是否高估了精度？
112 行只有 82 个独立 symbol、17 个独立日历周（最大单周 14 行）。
本脚本用上一轮的真实分组（sentiment_score<-0.15 = G_neg）复算 fr median 差的 CI，
对比 ① 行级 bootstrap（上一轮口径） ② 按 symbol 聚类 ③ 按日历周聚类。
"""
import json, numpy as np, datetime as dt
from collections import defaultdict
rows = [r for r in json.load(open(
    "docs/research/2026-08-16_news-sentiment-path2-integration/repro/full_metrics_20260816-193657.json"))
    if r.get("fr_recalc") is not None]
for r in rows:
    d = dt.date.fromisoformat(r["buy_date"]); r["_wk"] = d.isocalendar()[:2]
neg = [r for r in rows if r["total_count"] > 0 and r["sentiment_score"] < -0.15]
rest = [r for r in rows if r not in neg]
print(f"G_neg n={len(neg)} (fr median {np.median([r['fr_recalc'] for r in neg]):.3f}) | "
      f"rest n={len(rest)} (fr median {np.median([r['fr_recalc'] for r in rest]):.3f})")
rng = np.random.default_rng(42); NB = 10000
def ci_row(a, b):
    fa = np.array([r["fr_recalc"] for r in a]); fb = np.array([r["fr_recalc"] for r in b])
    d = np.median(rng.choice(fb, (NB, len(fb)), True), axis=1) - np.median(rng.choice(fa, (NB, len(fa)), True), axis=1)
    return np.percentile(d, [2.5, 97.5])
def ci_cluster(a, b, key):
    ga, gb = defaultdict(list), defaultdict(list)
    for r in a: ga[r[key]].append(r["fr_recalc"])
    for r in b: gb[r[key]].append(r["fr_recalc"])
    ka, kb = list(ga), list(gb); out = []
    for _ in range(NB):
        sa = np.concatenate([ga[k] for k in rng.choice(len(ka), len(ka), True).astype(int).tolist() and [ka[i] for i in rng.integers(0, len(ka), len(ka))]])
        sb = np.concatenate([gb[i] for i in [kb[j] for j in rng.integers(0, len(kb), len(kb))]])
        out.append(np.median(sb) - np.median(sa))
    return np.percentile(out, [2.5, 97.5]), len(ka), len(kb)
pt = np.median([r["fr_recalc"] for r in rest]) - np.median([r["fr_recalc"] for r in neg])
lo, hi = ci_row(neg, rest)
print(f"\n点估计 Δ(rest−neg) = {pt:+.3f}")
print(f"① 行级 bootstrap（上一轮口径）  CI = [{lo:+.3f}, {hi:+.3f}]  宽度 {hi-lo:.3f}")
for key, name in (("symbol", "② 按 symbol 聚类"), ("_wk", "③ 按日历周聚类")):
    (l, h), ka, kb = ci_cluster(neg, rest, key)
    print(f"{name}  (clusters {ka}/{kb})  CI = [{l:+.3f}, {h:+.3f}]  宽度 {h-l:.3f}")
# 通用：随机分组下 CI 宽度的膨胀倍数（不依赖具体分组）
print("\n=== 随机等分（n_t=15）下三种 bootstrap 的平均 CI 宽度 ===")
for key, name in ((None, "行级"), ("symbol", "symbol 聚类"), ("_wk", "周聚类")):
    ws = []
    for _ in range(40):
        idx = rng.permutation(len(rows)); a = [rows[i] for i in idx[:15]]; b = [rows[i] for i in idx[15:]]
        if key is None: l, h = ci_row(a, b)
        else: (l, h), _, _ = ci_cluster(a, b, key)
        ws.append(h - l)
    print(f"  {name:>12}: 平均 CI 宽度 {np.mean(ws):.3f}")
