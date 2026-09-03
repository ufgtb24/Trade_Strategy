"""
P0-d 幸存者偏差探针 + 全宇宙样本量上限估计。
数据在主 worktree（本 worktree datasets/pkls/ 为空），只读、不写、不改。
判据：若绝大多数 pkl 的 last_date 集中在同一天（=抓取日）→ 只含在市票 → fr 绝对水平被高估。
"""
import pickle, glob, random
from collections import Counter
FS = sorted(glob.glob('/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/*.pkl'))
random.seed(42)
sample = random.sample(FS, 900)
last, first, nrows = [], [], []
bad = 0
for p in sample:
    try:
        with open(p, 'rb') as f: d = pickle.load(f)
        if len(d) == 0: bad += 1; continue
        last.append(d.index[-1].date()); first.append(d.index[0].date()); nrows.append(len(d))
    except Exception: bad += 1
print(f"[样本] 抽 {len(sample)} 个 pkl（全宇宙 {len(FS)}），读失败/空 {bad}")
cl = Counter(last)
print(f"\n[last_date 分布] 独立日期数 = {len(cl)}")
for d, n in cl.most_common(6):
    print(f"   {d}: {n:>4} ({n/len(last)*100:.1f}%)")
mx = cl.most_common(1)[0]
stale = sum(n for d, n in cl.items() if (mx[0] - d).days > 30)
print(f"\n   >>> 最新日 {mx[0]} 占 {mx[1]/len(last)*100:.1f}%")
print(f"   >>> last_date 早于最新日 30 天以上（= 退市/停牌/停更）占 {stale/len(last)*100:.1f}%  (n={stale})")
cf = Counter(first)
print(f"\n[first_date 分布] 独立日期数 = {len(cf)}, 最常见:")
for d, n in cf.most_common(4): print(f"   {d}: {n:>4} ({n/len(first)*100:.1f}%)")
import numpy as np
nr = np.array(nrows)
print(f"\n[行数] median={np.median(nr):.0f} q10={np.percentile(nr,10):.0f} q90={np.percentile(nr,90):.0f} max={nr.max()}")
print(f"[覆盖年数] median ≈ {np.median(nr)/252:.2f} 年")
yrs = nr / 252
print(f"\n[全宇宙财报事件量上限估计] 8325 票 × 平均 {yrs.mean():.2f} 年 × 4 季/年 ≈ {8325*yrs.mean()*4:,.0f} 个季度事件")
print(f"   若 XBRL 标准 tag 覆盖率 50% → ≈ {8325*yrs.mean()*4*0.5:,.0f}；再要求 surprise 可算(需上年同期) → 再打约 8 折")

# --- 追加：幸存宇宙里还剩多少「失败质量」 ---
print("\n[幸存宇宙内的失败质量]（判断缺失的退市票会补进多少左尾）")
import numpy as np
ratios = []
for p in sample:
    with open(p, 'rb') as f: d = pickle.load(f)
    if len(d) < 250: continue
    c = d['close'].values
    ratios.append(c[-1] / np.nanmax(c))
r = np.array(ratios); r = r[~np.isnan(r)]
for th in (0.10, 0.25, 0.50):
    print(f"   现价 < 历史最高价 × {th:.0%} 的票占比: {(r < th).mean()*100:.1f}%")
print(f"   现价/历史最高 的 median = {np.median(r):.3f}")
