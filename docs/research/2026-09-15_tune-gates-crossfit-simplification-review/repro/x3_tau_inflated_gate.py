"""x3：把训练期跨格池化估出的年交互方差 τ̂² 并进确认窗方差再合并，误写率能否拉回名义 5%。

模型（单位：点）：
- 往前那段估计 = g + a_b + b_true − b_shift + e_b，SE_b = 1.6；往后那段 = g + a_f + e_f，SE_f = 2.7。
- 各段行情交互 a = 候选自身交互 ξ（SD = cand_mult·τ_cell）+ 全网格共同年偏移 γ（SD = τ_common），各段独立一抽。
- 训练期估 τ̂²：J 个独立有效格，每格两年配对差之差 d_j = Δγ + Δξ_j + Δe_j，每年单格 SE s = 1.78；
  去均值版 τ̂² = max(0, [Σ(d_j − d̄)²/(J−1) − 2s²]/2)（估不到共同偏移）；原始版不减 d̄（共同偏移只有 1 个自由度）。
- 检验：两段方差各加 τ² 后按精度合并，单侧 α = 5% 优效（合并估计 − 1.645·SE_c > 0）。
  nominal = 不加；oracle = 加真值（候选的 ξ 方差 + 共同偏移方差）；est = 加 τ̂²。
"""
import numpy as np

SE_B, SE_F, S_CELL, Z = 1.6, 2.7, 1.78, 1.6448536269514722


def run(rng, *, tau_cell, tau_common=0.0, cand_mult=1.0, J=16, b_true=0.0, b_shift=0.0, demean=True, R=200000):
    u = rng.normal(0, np.sqrt(2 * tau_cell ** 2 + 2 * S_CELL ** 2), (R, J))
    d = u + rng.normal(0, np.sqrt(2) * tau_common, (R, 1))
    if demean:
        ms = ((d - d.mean(1, keepdims=True)) ** 2).sum(1) / (J - 1)
    else:
        ms = (d ** 2).mean(1)
    tau2_hat = np.maximum(0.0, (ms - 2 * S_CELL ** 2) / 2)
    tau2_true = (cand_mult * tau_cell) ** 2 + tau_common ** 2
    out = {"τ̂ 均值": np.sqrt(tau2_hat).mean(), "P(τ̂=0)": (tau2_hat == 0).mean()}
    for g in (0.0, 1.0, 2.5):
        eb = g + rng.normal(0, np.sqrt(tau2_true), R) + b_true - b_shift + rng.normal(0, SE_B, R)
        ef = g + rng.normal(0, np.sqrt(tau2_true), R) + rng.normal(0, SE_F, R)
        for name, add in (("nominal", 0.0), ("oracle", tau2_true), ("est", tau2_hat)):
            vb, vf = SE_B ** 2 + add, SE_F ** 2 + add
            wb = (1 / vb) / (1 / vb + 1 / vf)
            se_c = 1 / np.sqrt(1 / vb + 1 / vf)
            out[f"{name} g={g:+.1f}"] = ((wb * eb + (1 - wb) * ef) - Z * se_c > 0).mean()
    return out


def show(label, o):
    print(f"{label:<46s} τ̂均值 {o['τ̂ 均值']:.2f} P(τ̂=0) {o['P(τ̂=0)']:.2f} | "
          + " | ".join(f"{m}: 0→{o[f'{m} g=+0.0']:.3f} 1→{o[f'{m} g=+1.0']:.2f} 2.5→{o[f'{m} g=+2.5']:.2f}"
                       for m in ("nominal", "oracle", "est")))


def main():
    rng = np.random.default_rng(20260915)
    print("== 主情形：交互全在格级（无共同偏移），候选交互 = 池化平均 ==")
    for tau in (0.0, 0.9, 2.0):
        for J in (16, 64):
            show(f"τ={tau} J={J}", run(rng, tau_cell=tau, J=J))
    print("== 候选落在交互更大的角落：候选 τ = 2 × 池化平均 ==")
    for tau in (0.9, 2.0):
        show(f"池化 τ={tau}，候选 {2*tau:.1f}，J=16", run(rng, tau_cell=tau, cand_mult=2.0, J=16))
    print("== 一半交互是全网格共同年偏移（总 τ=2：格级与共同各 √2）==")
    tc = np.sqrt(2.0)
    show("去均值估计（估不到共同偏移），J=16", run(rng, tau_cell=tc, tau_common=tc, J=16, demean=True))
    show("原始估计（共同偏移 1 个自由度），J=16", run(rng, tau_cell=tc, tau_common=tc, J=16, demean=False))
    print("== 幸存者偏差（τ=0.9，J=16）：放松类候选按上界 1 点平移 ==")
    show("真偏差 +1、不平移", run(rng, tau_cell=0.9, J=16, b_true=1.0, b_shift=0.0))
    show("真偏差 +1、平移 1（恰好抵消）", run(rng, tau_cell=0.9, J=16, b_true=1.0, b_shift=1.0))
    show("真偏差 0、平移 1（上界过头，保守）", run(rng, tau_cell=0.9, J=16, b_true=0.0, b_shift=1.0))


if __name__ == "__main__":
    main()
