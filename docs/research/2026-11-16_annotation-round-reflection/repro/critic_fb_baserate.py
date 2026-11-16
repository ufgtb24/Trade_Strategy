"""critic 一次性：designer 入口二窄口径（另一段阶跃起点离本段 ≤5 根）在「用户没意见的一致正样本」和全部 hit 上的基率。
口径照抄 designer_fb_count.py 第二段，只换视野。"""
import pickle, bisect
from pathlib import Path
C = pickle.load(open(Path(__file__).parent / "cache_old.pkl", "rb"))
MATCHED = [("CAPR", "2025-12-19"), ("CRNC", "2024-11-29"), ("CRNC", "2024-12-05"), ("CRNC", "2024-12-13"),
           ("DXYZ", "2024-11-15"), ("GEVO", "2024-09-23"), ("INDO", "2022-02-04"), ("QBTS", "2024-11-29"),
           ("QBTS", "2024-12-03"), ("RGTI", "2024-11-29"), ("RGTI", "2024-12-04"), ("SMX", "2025-12-02")]
def fires(sym, pool):
    day = C[sym]["day"]; starts = sorted({r["s"] for r in C[sym]["events"]})
    fa = fb = False
    for r in pool:
        for s2 in starts:
            if r["e"] < s2 <= min(r["t"], r["e"] + 5): fa = True
            if r["s"] - 5 <= s2 <= r["s"] - 1: fb = True
    return fa, fb
n = 0
for sym, d in MATCHED:
    day = C[sym]["day"]; i0 = bisect.bisect_left(day, d)
    inview = [r for r in C[sym]["events"] if i0 - 3 <= r["t"] <= i0 + 3]
    pool = [r for r in inview if r["hit"]] or inview
    fa, fb = fires(sym, pool); n += (fa or fb)
    print(sym, d, "hit" if any(r["hit"] for r in inview) else "候选", "A" if fa else "-", "B" if fb else "-")
print("一致正样本触发:", n, "/", len(MATCHED))
tot = hitc = 0
for sym in C:
    hits = [r for r in C[sym]["events"] if r["hit"]]
    for r in hits:
        fa, fb = fires(sym, [r]); tot += 1; hitc += (fa or fb)
print("全部 hit（含全部前缀）触发:", hitc, "/", tot)

print("\n--- 公平对照：一致正样本也取 ±3 根内全部在场事件（含候选），与相反样本同口径 ---")
n = 0
for sym, d in MATCHED:
    day = C[sym]["day"]; i0 = bisect.bisect_left(day, d)
    inview = [r for r in C[sym]["events"] if i0 - 3 <= r["t"] <= i0 + 3]
    fa, fb = fires(sym, inview); n += (fa or fb)
    print(sym, d, len(inview), "A" if fa else "-", "B" if fb else "-")
print("一致正样本（全部在场事件）触发:", n, "/", len(MATCHED))
