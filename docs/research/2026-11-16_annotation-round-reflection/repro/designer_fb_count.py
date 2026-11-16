"""一次性（designer）：改前 app 的 detector docstring 自述的两条失效边界，在第 2 步必看的 14 个视野里命中几个。

FB_A「新平台里装着另一次阶跃」（docstring 判据 4：当天自己是大阳线、甚至开了下一段阶跃，也照样是这个前缀的新平台上的一天）：
    视野里在场的 plateau 事件（hit 或候选），其新平台 [e+1, t] 内（含当天）有另一段阶跃的起点 s'。
FB_B「分几天爬上去被切成几级」（失效边界第 3 条：每级各自一段、各自一个旧平台）：
    视野里在场事件的旧平台 [s-L, s-1] 内有另一段阶跃的起点 s'（前一级阶跃落进了这一级的旧平台）。
视野：10 处反馈取范围内 t 的全部事件（hit 与候选）；4 张相反样本取样本日 ±3 根内 t 的全部事件。
口径只读 cache_old.pkl（tracer 用改前 app 抽的全部 plateau 事件）。
"""
import pickle
from pathlib import Path
HERE = Path(__file__).parent
C = pickle.load(open(HERE / "cache_old.pkl", "rb"))
VIEWS = [
    ("f-pc-90", "IXHL", "2025-08-29", "2025-09-26"), ("f-pc-92", "QBTS", "2025-03-18", "2025-03-25"),
    ("f-pc-74", "CRNC", "2025-01-07", "2025-01-30"), ("f-pc-72", "INDO", "2022-03-08", "2022-05-03"),
    ("f-pc-89", "KULR", "2024-04-12", "2024-05-20"), ("f-pc-94", "IXHL", "2025-07-25", "2025-07-25"),
    ("f-pc-95", "LUMN", "2024-08-09", "2024-10-02"), ("f-pc-104", "CAPR", "2025-12-05", "2025-12-05"),
    ("f-pc-101", "IZM", "2024-04-16", "2024-04-16"), ("f-pc-93", "TNXP", "2024-12-30", "2024-12-30"),
    ("s-pc-86", "KULR", "2024-03-27", None), ("s-pc-82", "KULR", "2024-04-01", None),
    ("s-pc-75", "KULR", "2024-11-29", None), ("s-pc-80", "KULR", "2024-12-16", None),
]
for vid, sym, a, b in VIEWS:
    day = C[sym]["day"]; evs = C[sym]["events"]
    starts = sorted({r["s"] for r in evs})
    idx = {d: i for i, d in enumerate(day)}
    def near(d):
        import bisect
        return bisect.bisect_left(day, d)
    if b is None:
        i0 = near(a); lo, hi = i0 - 3, i0 + 3
    else:
        lo, hi = near(a), near(b)
        if hi < len(day) and day[hi] > b: hi -= 1
    inview = [r for r in evs if lo <= r["t"] <= hi]
    fa, fb = set(), set()
    for r in inview:
        for s2 in starts:
            if r["e"] < s2 <= r["t"]:
                fa.add((day[r["s"]], day[s2]))
            if r["old_s"] <= s2 <= r["s"] - 1:
                fb.add((day[r["s"]], day[s2]))
    nh = sum(r["hit"] for r in inview)
    print(f"{vid:9s} {sym:5s} 在场事件{len(inview):3d}(hit {nh:3d})  A新平台含另一段阶跃起点:{'是' if fa else '否'} {sorted(fa)[:4]}  "
          f"B旧平台含另一段阶跃起点:{'是' if fb else '否'} {sorted(fb)[:4]}")

print("\n--- 收紧：只看 hit（相反样本没有 hit，看在场候选），另一段阶跃起点离本段阶跃 ≤5 根（同一波拉升被切成几级）---")
for vid, sym, a, b in VIEWS:
    day = C[sym]["day"]; evs = C[sym]["events"]
    starts = sorted({r["s"] for r in evs})
    import bisect
    if b is None:
        i0 = bisect.bisect_left(day, a); lo, hi = i0 - 3, i0 + 3
    else:
        lo = bisect.bisect_left(day, a); hi = bisect.bisect_right(day, b) - 1
    inview = [r for r in evs if lo <= r["t"] <= hi]
    pool = [r for r in inview if r["hit"]] or inview
    fa, fb = set(), set()
    for r in pool:
        for s2 in starts:
            if r["e"] < s2 <= min(r["t"], r["e"] + 5):
                fa.add((day[r["s"]], day[s2]))
            if r["s"] - 5 <= s2 <= r["s"] - 1:
                fb.add((day[r["s"]], day[s2]))
    print(f"{vid:9s} {sym:5s} {'hit' if any(r['hit'] for r in inview) else '候选'}  A:{'是' if fa else '否'} {sorted(fa)[:3]}  B:{'是' if fb else '否'} {sorted(fb)[:3]}")
