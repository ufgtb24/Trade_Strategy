# -*- coding: utf-8 -*-
"""e0：只读 cells.npz 的点估计实验（无 bootstrap，秒级）。

1) 复现 notes.md §11 的 OAT 数字（生产参数点，校验读法正确）；
2) 在「生产值 ↔ 一个备选值」的 2 档子设计上算因子主效应（其余 11 维全部 2 档平均）与
   两两交互（条件效应之差），与 OAT 对照；
3) 同样的主效应在「全档外端」子设计上重算，看档位范围选择对筛选结论的敏感度。

读法：cells.npz 的 fp/count 形状 = 12 轴 + fold(2)；count = 四态和（买点日，含 none）。
"""
import itertools
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[5]
Z = np.load(ROOT / "outputs/tune_gates/bb_v1/main/cells.npz", allow_pickle=True)
FP, CNT = Z["fp"], Z["count"]
AX = ["exceed", "mrh", "gap", "rise", "span", "scb", "count", "dpk", "fd", "pa", "vs", "mdd"]
LV = dict(exceed=[0.0015, 0.003, 0.0045, 0.0075], mrh=[0.1, 0.2, 0.3, 0.5], gap=[4, 8, 12, 20],
          rise=[0.75, 1.5, 2.25, 3.75], span=[10, 20, 30, 50], scb=[1, 2, 3, 4], count=[1, 2, 3, 4],
          dpk=[1, 3, 5], fd=[0, 40, 80], pa=[0, 60, 120], vs=[0, 3, 6], mdd=[None, 0.2])
FOLDS = [str(f) for f in Z["folds"]]
POWER = 100


def idx(**kw):
    return tuple(LV[a].index(kw[a]) for a in AX)


PROD_OLD = dict(exceed=0.003, mrh=0.2, gap=8, rise=1.5, span=20, scb=1, count=1, dpk=3, fd=40, pa=60, vs=3, mdd=0.2)


def show(name, cell):
    i = idx(**cell)
    return f"{name}: " + " / ".join(f"{f} n={CNT[i][k]} FP={FP[i][k]:.4f}" for k, f in enumerate(FOLDS))


print("== 1) OAT 复现（notes §11：生产 2024 n=1865 FP=.5725 / 2025 n=2312 FP=.5342）")
print(show("生产(改前)", PROD_OLD))
for nm, ch in [("A 删峰龄", dict(pa=0)), ("C 突破幅度", dict(exceed=0.0075)), ("A+C", dict(pa=0, exceed=0.0075)),
               ("A+B+C", dict(pa=0, exceed=0.0075, scb=3)), ("span10", dict(span=10)), ("span30", dict(span=30))]:
    c = {**PROD_OLD, **ch}
    i0, i1 = idx(**PROD_OLD), idx(**c)
    d = [(FP[i1][k] - FP[i0][k]) * 100 for k in range(2)]
    r = CNT[i1].sum() / CNT[i0].sum()
    print(f"  {nm}: 买点日× {r:.3f}  ΔFP {d[0]:+.2f} / {d[1]:+.2f} pt")


def factorial(design, label, power=POWER):
    """design: {轴: (lo 值, hi 值)}；没列出的轴固定在 PROD_OLD。
    主效应 = 对其余因子全部 2^(N-1) 组设置取平均的 FP(hi)-FP(lo)，只用两臂都过功效线的配对。"""
    axes = list(design)
    N = len(axes)
    sub_fp = np.full((2,) * N + (2,), np.nan)
    sub_n = np.zeros((2,) * N + (2,), dtype=np.int64)
    for bits in itertools.product([0, 1], repeat=N):
        c = dict(PROD_OLD)
        for a, b in zip(axes, bits):
            c[a] = design[a][b]
        i = idx(**c)
        sub_fp[bits], sub_n[bits] = FP[i], CNT[i]
    ok = sub_n >= power
    print(f"\n== {label}：{N} 因子 2 档 = {2**N} 格；过功效线 {ok.all(-1).sum()} 格（两折都 ≥{power} 买点日）")
    me = {}
    for j, a in enumerate(axes):
        hi = np.take(sub_fp, 1, axis=j); lo = np.take(sub_fp, 0, axis=j)
        okp = np.take(ok, 1, axis=j) & np.take(ok, 0, axis=j)
        d = np.where(okp, hi - lo, np.nan)
        m = [np.nanmean(d[..., k]) * 100 for k in range(2)]
        npair = okp.reshape(-1, 2).sum(0)
        nh = np.take(sub_n, 1, axis=j).sum(); nl = np.take(sub_n, 0, axis=j).sum()
        me[a] = m
        print(f"  {a:6s} {design[a][0]!s:>6}->{design[a][1]!s:<6} ME {m[0]:+6.2f} / {m[1]:+6.2f} pt  "
              f"同号={'是' if m[0]*m[1] > 0 else '否'}  买点日×{nh/nl:.3f}  配对数 {npair.tolist()}")
    print("  两两交互（条件效应之差 ME_j|k=hi − ME_j|k=lo，两折，pt）| 只列两折同号且两折 |值| 都 ≥1pt 的：")
    rows = []
    for (j, a), (k, b) in itertools.combinations(enumerate(axes), 2):
        f11 = np.take(np.take(sub_fp, 1, axis=k), 1, axis=j if j < k else j - 1)
        f10 = np.take(np.take(sub_fp, 0, axis=k), 1, axis=j if j < k else j - 1)
        f01 = np.take(np.take(sub_fp, 1, axis=k), 0, axis=j if j < k else j - 1)
        f00 = np.take(np.take(sub_fp, 0, axis=k), 0, axis=j if j < k else j - 1)
        o11 = np.take(np.take(ok, 1, axis=k), 1, axis=j if j < k else j - 1)
        o10 = np.take(np.take(ok, 0, axis=k), 1, axis=j if j < k else j - 1)
        o01 = np.take(np.take(ok, 1, axis=k), 0, axis=j if j < k else j - 1)
        o00 = np.take(np.take(ok, 0, axis=k), 0, axis=j if j < k else j - 1)
        okk = o11 & o10 & o01 & o00
        dd = np.where(okk, (f11 - f01) - (f10 - f00), np.nan)
        v = [np.nanmean(dd[..., q]) * 100 for q in range(2)]
        rows.append((a, b, v))
    big = [r for r in rows if r[2][0] * r[2][1] > 0 and min(abs(r[2][0]), abs(r[2][1])) >= 1.0]
    for a, b, v in sorted(big, key=lambda r: -min(abs(r[2][0]), abs(r[2][1]))):
        print(f"    {a}×{b}: {v[0]:+.2f} / {v[1]:+.2f}")
    allabs = np.array([[abs(r[2][0]), abs(r[2][1])] for r in rows])
    meabs = np.array([[abs(v[0]), abs(v[1])] for v in me.values()])
    print(f"  |交互| 中位 {np.nanmedian(allabs):.2f}pt  p90 {np.nanpercentile(allabs, 90):.2f}pt；|主效应| 中位 {np.nanmedian(meabs):.2f}pt")
    return me, rows


DES_PROD = dict(exceed=(0.003, 0.0075), mrh=(0.2, 0.3), gap=(8, 4), rise=(1.5, 2.25), span=(20, 10), scb=(1, 3),
                count=(1, 2), dpk=(1, 3), fd=(0, 40), pa=(0, 60), vs=(0, 3), mdd=(None, 0.2))
DES_OUTER = dict(exceed=(0.0015, 0.0075), mrh=(0.1, 0.5), gap=(20, 4), rise=(0.75, 3.75), span=(50, 10), scb=(1, 4),
                 count=(1, 4), dpk=(1, 5), fd=(0, 80), pa=(0, 120), vs=(0, 6), mdd=(None, 0.2))
DES_INNER = dict(exceed=(0.003, 0.0045), mrh=(0.2, 0.3), gap=(12, 8), rise=(1.5, 2.25), span=(30, 20), scb=(2, 3),
                 count=(1, 2), dpk=(1, 3), fd=(0, 40), pa=(0, 60), vs=(0, 3), mdd=(None, 0.2))
factorial(DES_PROD, "2) 生产值↔备选 子设计")
factorial(DES_OUTER, "3a) 外端 子设计")
factorial(DES_INNER, "3b) 内侧 子设计")

print("\n== 4) 峰龄闸 OAT 在不同「其余闸」背景下（同 D=生产），看 OAT 结论对背景的依赖")
for bg_name, bg in [("其余闸全开(生产)", {}), ("其余闸全关", dict(dpk=1, fd=0, vs=0, mdd=None))]:
    c0 = {**PROD_OLD, **bg}; c1 = {**c0, "pa": 0}
    i0, i1 = idx(**c0), idx(**c1)
    print(f"  {bg_name}: pa 60->0 ΔFP {(FP[i1][0]-FP[i0][0])*100:+.2f} / {(FP[i1][1]-FP[i0][1])*100:+.2f} pt, 买点日×{CNT[i1].sum()/CNT[i0].sum():.3f}")
    c1 = {**c0, "exceed": 0.0075}; i1 = idx(**c1)
    print(f"  {bg_name}: exceed .003->.0075 ΔFP {(FP[i1][0]-FP[i0][0])*100:+.2f} / {(FP[i1][1]-FP[i0][1])*100:+.2f} pt, 买点日×{CNT[i1].sum()/CNT[i0].sum():.3f}")
