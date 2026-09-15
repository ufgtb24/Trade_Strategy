"""E8:文档用的解析数字(无数据读取)。"""
import numpy as np
from scipy import stats
print("== 关3 去簇检验功效(Spearman,Fisher z,双侧 α=0.05)")
for rho in (0.05, 0.1, 0.2):
    row = []
    for n in (13, 20, 40, 300, 2000):
        zz = np.arctanh(rho) * np.sqrt(n - 3)
        row.append(f"n={n}: {stats.norm.sf(1.96 - zz) + stats.norm.cdf(-1.96 - zz):.2f}")
    print(f"  ρ={rho}: " + "  ".join(row))
print("== 两折方向一致的零假设概率")
for m in (5, 12, 21, 49):
    print(f"  m={m}: 期望两年同号 {m/2:.1f}、同为正 {m/4:.2f};至少一个同为正 {1-0.75**m:.3f}")
print("== 选择噪声分位 z_K,F = Φ⁻¹(1 − K^(−1/F)) 与 √(2lnK)")
for K in (12, 64, 648, 4096, 354294, 2654208):
    print(f"  K={K}: F=1 {stats.norm.isf(1/K):.2f}  F=2 {stats.norm.isf(K**-0.5):.2f}  √(2lnK) {np.sqrt(2*np.log(K)):.2f}")
print("== Bonferroni 双侧 z 门槛")
for m in (1, 12, 49, 100):
    print(f"  m={m}: z {stats.norm.isf(0.025/m):.2f}")
print("== 收紧效应最小可检出量 MDE(双侧 5%、功效 80% → 2.80·SE),SE = √(p(1−p)·deff/D_宽·(1−r)/r),p=0.5,deff=8")
for Dw in (10373, 1041):
    print(f"  D_宽(每年定向 bar)={Dw}: " + "  ".join(f"r={r}: {100*2.8*np.sqrt(0.25*8/Dw*(1-r)/r):.1f}pt" for r in (0.9, 0.7, 0.5, 0.3, 0.1)))
print("== 功效线处按股去簇 σ(n) = √(p(1−p)·deff/(n·0.62)),p=0.5")
for deff in (1, 5, 8):
    print(f"  deff={deff}: " + "  ".join(f"n={n}: {np.sqrt(0.25*deff/(n*0.62)):.3f}" for n in (100, 400, 1600, 6400)))
print("== 40 交易日窗数:每年", round(252/40, 1), ";凑满 20 桶需", round(20*40/252, 1), "年")
