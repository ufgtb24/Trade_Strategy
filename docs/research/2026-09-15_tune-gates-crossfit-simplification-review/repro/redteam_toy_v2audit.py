# -*- coding: utf-8 -*-
"""red-team 玩具 v3(临时实验,不入产出):审 unifier v2 与 extrapolation 的「两段确认窗合并优效」写入门。

A 部分(同方差,16 候选,模型同 redteam_toy_cv.py):比较写入规则
  draft  argmax → 前向窗非劣效(est − z·se ≥ −δ)且同号(= 现行判读表的实际写入门)
  cv     argmax → 整年留出配对差 > 0 才开窗 → 同 draft
  v2     argmax → 跨年协方差 > 0 才开窗 → 两段按精度合并单侧优效(下界 > 0)且前向不「显著劣于」(est_f + z·se_f ≥ −δ)
  v2_ni  同 v2,兜底改成前向非劣效必须通过
  v2_cv  v2 再叠整年留出配对差 > 0
  确认窗:est_w = mu[g] + 该段行情交互(新抽,SD = tau)+ bias_w + N(0, SE_w);往前那段 bias = 幸存者偏差(对换点候选同向 +b)。
  报:终值均值、开窗率、误写率(写入且真差 ≤ 0)、写入时读数减真差的均值(过门后的虚高)。

B 部分(异方差 / 薄壳):15 个候选的买点变动比例 f = 0.05×6、0.2×6、0.5×3;单年 SE ∝ √f,年交互 SD ∝ f。
  排序:argmax d̄;EB_mu(同质先验放在配对差上,中心 = 工作点);EB_s(同质先验放在每单位变动的质量 s = d/f 上)。
  之后统一走 v2 写入门(确认窗 SE 同样 ∝ √f)。场景:全零;厚壳真 +3(f=0.5);薄壳真 +1(f=0.05)。
"""
from __future__ import annotations

import numpy as np

DELTA, Z, F, T = 2.0, 1.645, 5, 2
RULES = ("draft", "cv", "v2", "v2_ni", "v2_cv")


def train(rng, mu, tau_g, se_year):
    G = mu.size
    y = (mu[:, None, None] + rng.normal(0.0, 1.0, (G, 1, T)) * tau_g[:, None, None]
         + rng.normal(0.0, 1.0, (G, F, T)) * (se_year * np.sqrt(F))[:, None, None])
    y[0] = 0.0
    return y.mean(axis=1)


def gate(rule, g, year_cv, cov_ok, est_b, est_f, se_b, se_f):
    """返回 (开窗, 写入, 报数)。"""
    if g == 0 or (rule in ("cv", "v2_cv") and year_cv <= 0) or (rule.startswith("v2") and not cov_ok):
        return False, False, np.nan
    if rule in ("draft", "cv"):
        return True, bool(est_f - Z * se_f >= -DELTA and est_f > 0), est_f
    wb, wf = se_b ** -2, se_f ** -2
    est_c, se_c = (wb * est_b + wf * est_f) / (wb + wf), (wb + wf) ** -0.5
    fallback = est_f - Z * se_f >= -DELTA if rule == "v2_ni" else est_f + Z * se_f >= -DELTA
    return True, bool(est_c - Z * se_c > 0 and fallback), est_c


def part_a(mu, tau, bias_b, *, se_b=1.6, se_f=2.7, R=4000, seed=0):
    rng = np.random.default_rng(seed)
    G = mu.size
    acc = {k: np.zeros(4) for k in RULES}   # 终值和、开窗数、误写数、虚高和
    nw = {k: 0 for k in RULES}
    for _ in range(R):
        yt = train(rng, mu, np.full(G, tau), np.full(G, 1.77))
        ybar = yt.mean(axis=1)
        g = int(np.argmax(ybar))
        year_cv = np.mean([yt[int(np.argmax(yt[:, 1 - t])), t] for t in range(T)])
        cov_ok = float(np.mean(yt[1:, 0] * yt[1:, 1])) > 0
        est_b = mu[g] + rng.normal(0.0, tau) + bias_b + rng.normal(0.0, se_b)
        est_f = mu[g] + rng.normal(0.0, tau) + rng.normal(0.0, se_f)
        for k in RULES:
            op, wr, rep = gate(k, g, year_cv, cov_ok, est_b, est_f, se_b, se_f)
            acc[k] += [mu[g] if wr else 0.0, op, wr and mu[g] <= 0, (rep - mu[g]) if wr else 0.0]
            nw[k] += wr
    return {k: (acc[k][0] / R, acc[k][1] / R, acc[k][2] / R, acc[k][3] / max(nw[k], 1)) for k in RULES}


def part_b(mu, tau, *, R=4000, seed=1):
    rng = np.random.default_rng(seed)
    f = np.array([1.0] + [0.05] * 6 + [0.2] * 6 + [0.5] * 3)
    se_year, tau_g = 1.77 * np.sqrt(f / 0.2), tau * f / 0.2
    real = int(np.argmax(mu)) if mu.max() > 0 else -1
    out = {k: np.zeros(4) for k in ("argmax", "EB_mu", "EB_s")}   # 选中真格、选中薄壳、开窗、终值
    for _ in range(R):
        yt = train(rng, mu, tau_g, se_year)
        a0, a1, ybar = yt[1:, 0], yt[1:, 1], yt[1:].mean(axis=1)
        s2 = se_year[1:] ** 2
        s_mu2 = max(0.0, float(np.mean(a0 * a1)))
        tau2 = max(0.0, float(np.mean((a0 - a1) ** 2)) / 2 - float(np.mean(s2)))
        post_mu = s_mu2 / (s_mu2 + tau2 / T + s2 / T) * ybar
        fs = f[1:]
        a0s, a1s, s2s = a0 / fs, a1 / fs, s2 / fs ** 2
        s_s2 = max(0.0, float(np.mean(a0s * a1s)))
        tau2s = max(0.0, float(np.mean((a0s - a1s) ** 2)) / 2 - float(np.mean(s2s)))
        post_s = s_s2 / (s_s2 + tau2s / T + s2s / T) * ybar
        cov_ok = s_mu2 > 0
        for k, score in (("argmax", ybar), ("EB_mu", post_mu), ("EB_s", post_s)):
            g = 1 + int(np.argmax(score)) if (cov_ok and score.max() > 0) else 0
            se_b, se_f = 1.6 * np.sqrt(f[g] / 0.2), 2.7 * np.sqrt(f[g] / 0.2)
            est_b = mu[g] + rng.normal(0.0, tau_g[g]) + rng.normal(0.0, se_b)
            est_f = mu[g] + rng.normal(0.0, tau_g[g]) + rng.normal(0.0, se_f)
            op, wr, _ = gate("v2", g, 1.0, cov_ok, est_b, est_f, se_b, se_f)
            out[k] += [g == real, g != 0 and f[g] == 0.05, op, mu[g] if wr else 0.0]
    return {k: v / R for k, v in out.items()}


def main():
    G = 16
    rng = np.random.default_rng(42)
    worse = np.concatenate([[0.0], -np.abs(rng.normal(0.0, 2.0, G - 1))])
    mixed = worse.copy()
    mixed[1] = 3.0
    scen = (("纯噪声", np.zeros(G)), ("工作点近最优", worse),
            ("真+3其余0", np.concatenate([[0.0, 3.0], np.zeros(G - 2)])), ("真+3其余<=0", mixed))
    print("A: scenario | tau | bias_b | " + " | ".join(f"{k}(终值/开窗/误写/虚高)" for k in RULES))
    for name, mu in scen:
        for tau in (0.0, 0.9, 3.5):
            for b in (0.0, 1.0):
                res = part_a(mu, tau, b)
                print(f"{name} | {tau} | {b} | " + " | ".join("/".join(f"{x:+.2f}" for x in res[k]) for k in RULES))
    print("\nB: scenario | tau | " + " | ".join(f"{k}(选中真格/选中薄壳/开窗/终值)" for k in ("argmax", "EB_mu", "EB_s")))
    mu0 = np.zeros(16)
    thick = mu0.copy(); thick[13] = 3.0
    thin = mu0.copy(); thin[1] = 1.0
    for name, mu in (("全零", mu0), ("厚壳真+3", thick), ("薄壳真+1", thin)):
        for tau in (0.0, 0.9, 3.5):
            res = part_b(mu, tau)
            print(f"{name} | {tau} | " + " | ".join("/".join(f"{x:+.2f}" for x in res[k]) for k in ("argmax", "EB_mu", "EB_s")))


if __name__ == "__main__":
    main()
