# -*- coding: utf-8 -*-
"""unifier 临时实验：v2「训练期只排序、确认窗下结论」与各门控组合的对照（格间噪声独立的最简模型）。

配对增益：真持续增益 g(θ)（工作点 = 0）；训练两年 d̂_y = g + c_y + ξ_y + ε_y，c_y 为工作点共有项。
确认窗（往前段 SE_b、往后段 SE_f，各自独立的年交互与共有项）只对被选中的 θ̂ 开。
指标用真持续增益 g(θ̂)（未来期望），相对永远维持工作点（0）。

排序：A = 两年均值 argmax；C = 可信度 ρ·d̄ argmax。
门：shrunk = ρ·d̄ > δ（无确认窗）；conf = 合并确认窗 1−α 下界 > 0；cv = 整年留出（一年挑、另一年评，双向平均）> 0。
"""
import sys

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

Z = 1.6449
CORRECT = "--correct" in sys.argv                 # 写入时报截断校正后的中位无偏估计


def run(seed, scen, J, se_lo, se_hi, sd_xi=1.0, sd_c=1.0, se_b=1.45, se_f=3.0, delta=2.0):
    rng = np.random.default_rng(seed)
    if scen == "dense_tuned":
        g = rng.normal(-1.0, 1.0, J)
    elif scen == "wp_optimal":
        g = -np.abs(rng.normal(0.0, 1.0, J))
    elif scen == "null":
        g = np.zeros(J)
    elif scen == "sparse_precise":            # 唯一真 +3 落在最准的格
        g = np.zeros(J)
    elif scen == "sparse_noisy":              # 唯一真 +3 落在最不准的格
        g = np.zeros(J)
    se = rng.uniform(se_lo, se_hi, J)
    if scen == "sparse_precise":
        g[np.argmin(se)] = 3.0
    if scen == "sparse_noisy":
        g[np.argmax(se)] = 3.0
    Y = 2
    d = g + rng.normal(0, sd_c, (Y, 1)) + rng.normal(0, sd_xi, (Y, J)) + se * rng.standard_normal((Y, J))

    smu2_raw = float(np.cov(d[0], d[1])[0, 1])
    smu2 = max(1e-9, smu2_raw)                # σ_μ²→0 的极限:ρ ∝ 1/v,排序退化为按精度加权,不再并列
    sxi2 = max(0.0, float(np.var(d[0] - d[1], ddof=1) / 2 - np.mean(se ** 2)))
    rho = smu2 / (smu2 + sxi2 / Y + se ** 2 / Y)
    dbar = d.mean(0)
    iA, iC = int(np.argmax(dbar)), int(np.argmax(rho * dbar))

    def confirm(i):
        eb = g[i] + rng.normal(0, sd_c) + rng.normal(0, sd_xi) + rng.normal(0, se_b)
        ef = g[i] + rng.normal(0, sd_c) + rng.normal(0, sd_xi) + rng.normal(0, se_f)
        vb, vf = se_b ** 2 + sd_xi ** 2 + sd_c ** 2, se_f ** 2 + sd_xi ** 2 + sd_c ** 2
        w = np.array([1 / vb, 1 / vf])
        est = (w[0] * eb + w[1] * ef) / w.sum()
        s = 1 / np.sqrt(w.sum())
        passed = est - Z * s > 0
        if passed:                               # 写入条件下的中位无偏估计:截断正态 P(X≤est | X>Z·s; μ) = 0.5
            f = lambda mu: 0.5 - np.exp(norm.logsf((est - mu) / s) - norm.logsf((Z * s - mu) / s))
            gap = max((est - Z * s) / s, 1e-9)       # 刚过线时解趋于 −∞,下界要按 ln2/gap 放宽
            est = brentq(f, Z * s - (np.log(2) / gap + 20) * s, est + 5 * s) if CORRECT else est
        return passed, est

    cv = 0.5 * (d[1][int(np.argmax(d[0]))] + d[0][int(np.argmax(d[1]))]) > 0
    okA, estA = confirm(iA)
    okC, estC = confirm(iC)
    rules = {
        "A无门(总换)": (iA, True, dbar[iA]),
        "C收缩>δ无确认": (iC, rho[iC] * dbar[iC] > delta, rho[iC] * dbar[iC]),
        "A+合并确认": (iA, okA, estA),
        "C+合并确认(v2)": (iC, okC, estC),
        "A+CV门+合并确认": (iA, bool(cv and okA), estA),
        "C+CV门+合并确认": (iC, bool(cv and okC), estC),
    }
    return {k: (g[i] if w else 0.0, w, g[i], (rep - g[i]) if w else np.nan, rep - g[i]) for k, (i, w, rep) in rules.items()}


def main():
    R = 2000
    cases = [("dense_tuned", 2000, 1, 5), ("wp_optimal", 2000, 1, 5), ("null", 2000, 1, 5),
             ("sparse_precise", 16, 1, 5), ("sparse_noisy", 16, 1, 5), ("sparse_precise", 16, 2, 2)]
    for scen, J, lo, hi in cases:
        res = [run(s, scen, J, lo, hi) for s in range(R)]
        print(f"== {scen} J={J} 噪声 {lo}~{hi} 点")
        for k in res[0]:
            gain = np.array([r[k][0] for r in res]); w = np.array([r[k][1] for r in res])
            gsel = np.array([r[k][2] for r in res]); bias = np.array([r[k][3] for r in res])
            fw = np.mean(w & (gsel <= 0)); hit = np.mean(w & (gsel >= 2.0))
            ub = np.array([r[k][4] for r in res])
            print(f"   {k:<16} 增益 {gain.mean():+.3f}±{gain.std(ddof=1)/np.sqrt(R):.3f}  写入率 {w.mean():.3f}"
                  f"  误写 {fw:.3f}  写入且真≥2 {hit:.3f}  写入时报数−真 {np.nanmean(bias) if w.any() else float('nan'):+.2f}"
                  f"  不论写否报数−真 {ub.mean():+.2f}  写入时报数−真中位 {np.nanmedian(bias) if w.any() else float('nan'):+.2f}")


if __name__ == "__main__":
    main()
