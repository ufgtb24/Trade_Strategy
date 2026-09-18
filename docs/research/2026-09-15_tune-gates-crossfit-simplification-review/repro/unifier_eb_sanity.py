# -*- coding: utf-8 -*-
"""unifier 临时实验：随机效应收缩规则（方向 E）的代数自检，格间噪声独立的最简模型。

生成（逐格水平）：U_y(θ) = α_y + A(θ) + ξ_y(θ) + ε_y(θ)，θ=0 为工作点；工作点持续水平比网格平均高 wp_edge（被调过）。
未来一年：A(θ) + ξ_new(θ)（全市场平移 α 在差值里抵消）。真实换参增益 = 未来(θ̂) − 未来(θ0)。
对照规则（都在「估计增益 > δ 才换」下比）：
  E0  配对差、以网格均值为先验中心（初版，工作点当年偏离全额进入）
  E1  逐格水平两向随机效应：ρ(θ)(Ū(θ)−ū) − ρ0(Ū(θ0)−ū)
  E2  配对差、先验中心 0：ρ(θ)·d̄(θ)
  R1  配对差两年均值取最大
  R2  配对差两年取较差再取最大
嵌套 / 共享买点的相关结构不在这里，由 simulator 负责。
"""
import numpy as np


def run(seed, J=20000, Y=2, wp_edge=0.01, sd_A=0.01, sd_alpha=0.03, sd_xi=0.02, se_lo=0.01, se_hi=0.05,
        se_wp=0.005, delta=0.02):
    rng = np.random.default_rng(seed)
    A = sd_A * rng.standard_normal(J)
    A[0] = wp_edge
    se = rng.uniform(se_lo, se_hi, size=(Y, J))
    se[:, 0] = se_wp
    U = (sd_alpha * rng.standard_normal(Y))[:, None] + A + sd_xi * rng.standard_normal((Y, J)) + se * rng.standard_normal((Y, J))
    fut = A + sd_xi * rng.standard_normal(J)
    true_gain = fut - fut[0]

    pairs = [(a, b) for a in range(Y) for b in range(a + 1, Y)]
    sA2 = max(0.0, float(np.mean([np.cov(U[a], U[b])[0, 1] for a, b in pairs])))
    c = U - U.mean(1, keepdims=True)
    sxi2 = max(0.0, float(np.mean(c.var(0, ddof=1) - (se ** 2).mean(0))))
    Ubar, u = U.mean(0), U.mean()
    rho = sA2 / (sA2 + sxi2 / Y + (se ** 2).mean(0) / Y) if sA2 > 0 else np.zeros(J)

    d = U - U[:, [0]]
    dbar, m = d.mean(0), d[:, 1:].mean()
    se_d2 = se ** 2 + se[:, [0]] ** 2
    smu2_d = max(0.0, float(np.mean([np.cov(d[a, 1:], d[b, 1:])[0, 1] for a, b in pairs])))
    cd = d[:, 1:] - d[:, 1:].mean(1, keepdims=True)
    sxi2_d = max(0.0, float(np.mean(cd.var(0, ddof=1) - se_d2[:, 1:].mean(0))))
    rho_d = smu2_d / (smu2_d + sxi2_d / Y + se_d2.mean(0) / Y) if smu2_d > 0 else np.zeros(J)
    scores = {
        "E0": m + rho * (dbar - m),
        "E1": rho * (Ubar - u) - rho[0] * (Ubar[0] - u),
        "E2": rho * dbar,
        "E3": rho_d * dbar,
        "R1": dbar,
        "R2": d.min(0),
    }
    out = {"sA2": sA2 / sd_A ** 2 if sd_A > 0 else np.nan, "sxi2": sxi2 / sd_xi ** 2}
    for k, s in scores.items():
        s = s.copy(); s[0] = -np.inf
        i = int(np.argmax(s))
        sw = s[i] > delta
        out[k] = (true_gain[i] if sw else 0.0, sw, (s[i] - true_gain[i]) if sw else np.nan)
    return out


def main():
    R = 400
    cfgs = [("效应<噪声、工作点已调过", dict()),
            ("持续效应更大", dict(sd_A=0.02)),
            ("无持续效应", dict(sd_A=0.0)),
            ("工作点未调过、年份交互小", dict(wp_edge=0.0, sd_A=0.02, sd_xi=0.005))]
    for label, cfg in cfgs:
        res = [run(s, **cfg) for s in range(R)]
        print(f"== {label} {cfg}")
        print(f"   σ_A² 估/真 中位 {np.nanmedian([r['sA2'] for r in res]):.2f}  σ_ξ² 估/真 中位 {np.median([r['sxi2'] for r in res]):.2f}")
        for k in ["E0", "E1", "E2", "E3", "R1", "R2"]:
            g = np.array([r[k][0] for r in res]); sw = np.array([r[k][1] for r in res]); b = np.array([r[k][2] for r in res])
            bias = np.nanmean(b) * 100 if sw.any() else float("nan")
            print(f"   {k}: 实现增益 {g.mean()*100:+.2f}±{g.std(ddof=1)/np.sqrt(R)*100:.2f} 点  换参率 {sw.mean():.2f}"
                  f"  换参时报数−真实 {bias:+.2f} 点  换参时实现 {g[sw].mean()*100 if sw.any() else float('nan'):+.2f} 点")


if __name__ == "__main__":
    main()
