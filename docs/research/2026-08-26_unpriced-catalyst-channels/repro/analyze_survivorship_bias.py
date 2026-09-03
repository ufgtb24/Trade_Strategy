# -*- coding: utf-8 -*-
"""幸存者偏差的**方向与量级**：StockTwits 已 404 的那批买点，前瞻收益是否更差？

若「404 组」的 fr 系统性更差，则用今天的 ticker 表回溯历史会静默丢掉差样本
→ 回测结果向上偏。这里把推论变成实测（纯本地计算，无网络）。
"""
import json
import random
import statistics as st
from pathlib import Path

EV = ('/home/yu/PycharmProjects/Trade_Strategy/outputs/path2_eval/'
      'bb_v1_eval_20260810-235006.json')
DEAD = {'ADNH', 'ALTX', 'AURFF', 'BONXF', 'EHSI', 'FUST', 'GGOXF', 'HAMRF',
        'LOTT', 'MAGE', 'SRGZ', 'TBLLF'}   # probe_full_sample 实测 404 名单

rows = json.load(open(EV))['results']
d = [(r['symbol'], r['buy_date'], r['returns']['40']) for r in rows]
lost = [x for x in d if x[0] in DEAD]
kept = [x for x in d if x[0] not in DEAD]


def boot_median(xs, n=10000, seed=0):
    rnd = random.Random(seed)
    ms = sorted(st.median(rnd.choices(xs, k=len(xs))) for _ in range(n))
    return ms[int(.025 * n)], ms[int(.975 * n)]


def desc(name, xs):
    lo, hi = boot_median(xs)
    print(f"  {name:12s} n={len(xs):3d}  median={st.median(xs):+.4f} "
          f"[95%CI {lo:+.4f}, {hi:+.4f}]  mean={st.mean(xs):+.4f}  "
          f"min={min(xs):+.4f}  max={max(xs):+.4f}")
    return {"n": len(xs), "median": st.median(xs), "ci": [lo, hi],
            "mean": st.mean(xs), "min": min(xs), "max": max(xs)}


print(f"总买点 {len(d)}；StockTwits 404 组 {len(lost)}；可回溯组 {len(kept)}")
print("\nforward_return (horizon=40) 分布：")
a = desc("404 丢失组", [x[2] for x in lost])
b = desc("可回溯组", [x[2] for x in kept])
gap = a["median"] - b["median"]
print(f"\n  中位差（丢失组 − 可回溯组）= {gap:+.4f}")

# 首次穿越率（k∈[4,6] 无法从 40 日单点收益算，这里只能报「≥k 阈值达成率」的替代）
for k in (0.04, 0.06):
    pa = sum(1 for x in lost if x[2] >= k) / len(lost)
    pb = sum(1 for x in kept if x[2] >= k) / len(kept)
    print(f"  fr40 ≥ {k:.0%} 占比：丢失组 {pa:.1%} vs 可回溯组 {pb:.1%}")

print("\n404 组明细：")
for s, bd, r in sorted(lost, key=lambda x: x[2]):
    print(f"   {s:7s} {bd}  fr40={r:+.4f}")

Path('survivorship_bias_result.json').write_text(json.dumps(
    {"lost": a, "kept": b, "median_gap": gap,
     "lost_detail": [{"symbol": s, "buy": bd, "fr40": r} for s, bd, r in lost]},
    ensure_ascii=False, indent=1))
print("\n-> survivorship_bias_result.json")
