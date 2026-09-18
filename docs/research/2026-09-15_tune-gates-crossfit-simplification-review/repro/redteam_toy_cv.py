# -*- coding: utf-8 -*-
"""red-team 玩具蒙特卡洛(临时实验,不入产出)。

问题 1:「股票折 × 时段块」留一格交叉拟合,在有年交互时是否乐观;整年留出是否诚实。
问题 2:效应小于噪声、工作点接近局部最优时,草案流程会不会换到更差的点;加「维持臂」门控能否兜住。

模型(候选格相对工作点的首次穿越率差,单位:点):
  y[g, f, t] = mu[g] + gam[g, t] + eps[g, f, t]
  mu   持久效应(未来仍在);gam 年交互 ~ N(0, tau²),未来年份重抽;
  eps  股票噪声:一年全部股票合并 SE = S_YEAR,切 F 个股票折后每块 SE = S_YEAR·√F。
  g = 0 是工作点,差恒为 0。候选之间噪声独立(G 取「有效独立候选数」;真实网格相邻格共享买点)。
挑选规则 = 训练块平均差取 argmax(峰值规则,工作点在候选里)。
往后那段:est ~ N(mu[g] + 新年交互, SE_FWD²);按 validate.py 现行口径 est − 1.645·se ≥ −δ 且 est > 0 才采纳。
"""
from __future__ import annotations

import numpy as np

S_YEAR = 1.77   # 单翻转单年 SE(点):两年合并 ≈1.25 → ×√2
SE_FWD = 3.3    # 往后那段 3.5 个月的 SE(点):两年合并 SE × √(24/3.5)
DELTA = 2.0
Z = 1.645
KEYS = ("cell_cv", "year_cv", "truth_full", "truth_half", "switch", "switch_worse",
        "adopt_draft", "final_draft", "final_year_gate", "final_cell_gate",
        "switch_eb", "final_eb", "final_eb_fwd", "tau_t_hat")


def run(mu, tau, *, F=5, T=2, R=4000, seed=0):
    rng = np.random.default_rng(seed)
    G = mu.size
    rec = {k: np.empty(R) for k in KEYS}
    for r in range(R):
        gam = rng.normal(0.0, tau, (G, 1, T))
        eps = rng.normal(0.0, S_YEAR * np.sqrt(F), (G, F, T))
        y = mu[:, None, None] + gam + eps
        y[0] = 0.0
        g_full = int(np.argmax(y.mean(axis=(1, 2))))
        tot, n = y.sum(axis=(1, 2)), F * T
        cell = []
        for f in range(F):
            for t in range(T):
                g = int(np.argmax((tot - y[:, f, t]) / (n - 1)))
                cell.append(y[g, f, t])
        year, half = [], []
        for t in range(T):
            other = [u for u in range(T) if u != t]
            g = int(np.argmax(y[:, :, other].mean(axis=(1, 2))))
            year.append(y[g, :, t].mean())
            half.append(mu[g])
        est_fwd = mu[g_full] + rng.normal(0.0, tau) + rng.normal(0.0, SE_FWD)
        adopt = g_full != 0 and est_fwd - Z * SE_FWD >= -DELTA and est_fwd > 0
        rec["cell_cv"][r] = np.mean(cell)
        rec["year_cv"][r] = np.mean(year)
        rec["truth_full"][r] = mu[g_full]
        rec["truth_half"][r] = np.mean(half)
        rec["switch"][r] = g_full != 0
        rec["switch_worse"][r] = g_full != 0 and mu[g_full] < 0
        rec["adopt_draft"][r] = adopt
        rec["final_draft"][r] = mu[g_full] if adopt else 0.0
        rec["final_year_gate"][r] = mu[g_full] if (adopt and np.mean(year) > 0) else 0.0
        rec["final_cell_gate"][r] = mu[g_full] if (adopt and np.mean(cell) > 0) else 0.0
        # 经验贝叶斯对照:格间矩估计持久效应方差 tau_mu²,年交互方差 tau_t² 跨格池化;后验增益 > 0 才切换
        yt = y.mean(axis=1)
        ybar = yt.mean(axis=1)
        se2 = S_YEAR ** 2 / T
        d = yt[1:, 0] - yt[1:, 1]
        tau_t2 = max(0.0, float(np.mean(d ** 2)) / 2 - S_YEAR ** 2)
        m = float(ybar[1:].mean())
        tau_mu2 = max(0.0, float(ybar[1:].var(ddof=1)) - tau_t2 / T - se2)
        shrink = tau_mu2 / (tau_mu2 + tau_t2 / T + se2)
        post = m + shrink * (ybar[1:] - m)
        g_eb = 1 + int(np.argmax(post)) if post.max() > 0 else 0
        est_eb = mu[g_eb] + rng.normal(0.0, tau) + rng.normal(0.0, SE_FWD)
        adopt_eb = g_eb != 0 and est_eb - Z * SE_FWD >= -DELTA and est_eb > 0
        rec["switch_eb"][r] = g_eb != 0
        rec["final_eb"][r] = mu[g_eb]
        rec["final_eb_fwd"][r] = mu[g_eb] if adopt_eb else 0.0
        rec["tau_t_hat"][r] = np.sqrt(tau_t2)
    out = {k: float(v.mean()) for k, v in rec.items()}
    out["cell_cv_sd"] = float(rec["cell_cv"].std())
    out["year_cv_sd"] = float(rec["year_cv"].std())
    return out


def main():
    G = 16
    rng = np.random.default_rng(42)
    scenarios = (
        ("全零(纯噪声)", np.zeros(G)),
        ("工作点近局部最优(其余真差<=0)", np.concatenate([[0.0], -np.abs(rng.normal(0.0, 2.0, G - 1))])),
        ("一个真+3点、其余0", np.concatenate([[0.0, 3.0], np.zeros(G - 2)])),
    )
    worse = scenarios[1][1].copy()
    worse[1] = 3.0
    scenarios += (("一个真+3点、其余真差<=0", worse),)
    cols = ("cell_cv", "cell_cv_sd", "year_cv", "year_cv_sd", "truth_full", "truth_half", "switch",
            "switch_worse", "adopt_draft", "final_draft", "final_year_gate", "final_cell_gate",
            "switch_eb", "final_eb", "final_eb_fwd", "tau_t_hat")
    print("scenario | tau | " + " | ".join(cols))
    for name, mu in scenarios:
        for tau in (0.0, 1.77, 3.5):
            res = run(mu, tau)
            print(f"{name} | {tau} | " + " | ".join(f"{res[c]:+.3f}" for c in cols))


if __name__ == "__main__":
    main()
