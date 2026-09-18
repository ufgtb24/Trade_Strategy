# -*- coding: utf-8 -*-
"""red-team 玩具蒙特卡洛 v2(临时实验,不入产出)。

模型同 redteam_toy_cv.py:y[g, f, t] = mu[g] + gam[g, t] + eps[g, f, t],g = 0 为工作点(差恒 0),
16 个有效独立候选,单年合并 SE = S_YEAR,5 个股票折 × 2 年。
新增:实测量级 τ = 0.9;前向窗 SE 取 2.7 / 3.3 两档;unifier 方向 E(可靠度收缩)的两种先验中心。

规则(终值 = 写入配置相对现行参数的真差,维持 = 0):
  draft   全数据 argmax,总是换
  gate    全数据 argmax,整年留出配对差 > 0 才换
  E_grid  σ_μ² = 跨格 Cov(2024 差, 2025 差);年交互 τ² = 跨格 Var(两年差)/2 − 单年 SE²;
          ρ = σ_μ²/(σ_μ² + τ²/2 + SE²/2);d̃ = m + ρ(d̄ − m),m = 候选均值;max d̃ > δ 才换
  E_wp    同上,先验中心取工作点:σ_μ² = 跨格 mean(2024 差 × 2025 差),d̃ = ρ·d̄
每条规则再报「_fwd」:换点后还要过前向窗(est − 1.645·se ≥ −δ 且 est > 0)才写入。
"""
from __future__ import annotations

import numpy as np

S_YEAR = 1.77
DELTA = 2.0
Z = 1.645
RULES = ("draft", "gate", "E_grid", "E_wp")


def run(mu, tau, se_fwd, *, F=5, T=2, R=4000, seed=0):
    rng = np.random.default_rng(seed)
    G = mu.size
    fin = {f"{k}{s}": np.zeros(R) for k in RULES for s in ("", "_fwd")}
    worse = {k: np.zeros(R) for k in RULES}
    cell_cv = np.zeros(R)
    se2 = S_YEAR ** 2 / T
    for r in range(R):
        gam = rng.normal(0.0, tau, (G, 1, T))
        eps = rng.normal(0.0, S_YEAR * np.sqrt(F), (G, F, T))
        y = mu[:, None, None] + gam + eps
        y[0] = 0.0
        yt = y.mean(axis=1)
        ybar = yt.mean(axis=1)
        g_full = int(np.argmax(ybar))
        tot, n = y.sum(axis=(1, 2)), F * T
        cell_cv[r] = np.mean([y[int(np.argmax((tot - y[:, f, t]) / (n - 1))), f, t]
                              for f in range(F) for t in range(T)])
        year_cv = np.mean([yt[int(np.argmax(yt[:, 1 - t])), t] for t in range(T)])
        a0, a1 = yt[1:, 0], yt[1:, 1]
        tau2 = max(0.0, float(np.var(a0 - a1, ddof=1)) / 2 - S_YEAR ** 2)
        s_mu2 = max(0.0, float(np.cov(a0, a1)[0, 1]))
        m = float(ybar[1:].mean())
        post_grid = m + s_mu2 / (s_mu2 + tau2 / T + se2) * (ybar[1:] - m)
        s_mu2_wp = max(0.0, float(np.mean(a0 * a1)))
        post_wp = s_mu2_wp / (s_mu2_wp + tau2 / T + se2) * ybar[1:]
        picks = {
            "draft": g_full,
            "gate": g_full if year_cv > 0 else 0,
            "E_grid": 1 + int(np.argmax(post_grid)) if post_grid.max() > DELTA else 0,
            "E_wp": 1 + int(np.argmax(post_wp)) if post_wp.max() > DELTA else 0,
        }
        for k, g in picks.items():
            fin[k][r] = mu[g]
            worse[k][r] = g != 0 and mu[g] < 0
            if g != 0:
                est = mu[g] + rng.normal(0.0, tau) + rng.normal(0.0, se_fwd)
                fin[k + "_fwd"][r] = mu[g] if (est - Z * se_fwd >= -DELTA and est > 0) else 0.0
    out = {k: float(v.mean()) for k, v in fin.items()}
    out.update({f"worse_{k}": float(v.mean()) for k, v in worse.items()})
    out["cell_cv"] = float(cell_cv.mean())
    return out


def main():
    G = 16
    rng = np.random.default_rng(42)
    worse_mu = np.concatenate([[0.0], -np.abs(rng.normal(0.0, 2.0, G - 1))])
    mixed = worse_mu.copy()
    mixed[1] = 3.0
    scenarios = (
        ("纯噪声", np.zeros(G)),
        ("工作点近最优", worse_mu),
        ("真+3其余0", np.concatenate([[0.0, 3.0], np.zeros(G - 2)])),
        ("真+3其余<=0", mixed),
    )
    cols = ("cell_cv",) + tuple(f"{k}{s}" for k in RULES for s in ("", "_fwd")) + tuple(f"worse_{k}" for k in RULES)
    print("scenario | tau | se_fwd | " + " | ".join(cols))
    for name, mu in scenarios:
        for tau in (0.0, 0.9, 1.77, 3.5):
            for se_fwd in (2.7, 3.3):
                res = run(mu, tau, se_fwd)
                print(f"{name} | {tau} | {se_fwd} | " + " | ".join(f"{res[c]:+.2f}" for c in cols))


if __name__ == "__main__":
    main()
