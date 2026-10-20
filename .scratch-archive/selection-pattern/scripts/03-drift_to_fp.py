"""粗略换算：文献里「每月平均收益差 m」相当于项目方向成绩（首次穿越）领先多少。

假设：日对数收益正态、无跳跃；日内用 10 个子步近似最高 / 最低价；
波动尺度 M 取理论 ATR%（≈ 日内极差均值 + 隔夜跳空，这里直接用模拟出的真实波幅的均值）；
上行线 = close*(1+kM)、下行线 = close/(1+kM)，k=5，观察 40 个交易日（与 path2/eval.py 默认一致）。
方向成绩 = (先触上行线数 - 先触下行线数) / 全部买点数（未触线计入分母，同 tune-gates-v3）。
同一组随机数分别加漂移 m/21（每日）与 0，差值即漂移带来的方向成绩领先。
"""
import numpy as np


def simulate(sigma_d, m_month, n_paths=200_000, horizon=40, k=5.0, sub=10, seed=0):
    rng = np.random.default_rng(seed)
    mu_sub = m_month / 21 / sub
    s_sub = sigma_d / np.sqrt(sub)
    z = rng.standard_normal((n_paths, horizon * sub)) * s_sub
    # 波动尺度 M：用无漂移时一日内真实波幅的期望近似（模拟 20000 天估计）
    zz = rng.standard_normal((20000, sub)) * s_sub
    path = np.cumsum(zz, axis=1)
    hi = np.maximum(path.max(axis=1), 0)
    lo = np.minimum(path.min(axis=1), 0)
    M = float(np.mean(np.exp(hi) - np.exp(lo)))
    up_line = np.log(1 + k * M)
    out = {}
    for label, mu in (("drift", mu_sub), ("zero", 0.0)):
        x = np.cumsum(z + mu, axis=1)
        hit_up = x >= up_line
        hit_dn = x <= -up_line
        iu = np.where(hit_up.any(axis=1), hit_up.argmax(axis=1) // sub, 10**9)
        idn = np.where(hit_dn.any(axis=1), hit_dn.argmax(axis=1) // sub, 10**9)
        up = np.sum(iu < idn)
        dn = np.sum(idn < iu)
        out[label] = (up - dn) / n_paths
    return M, out["drift"] - out["zero"]


if __name__ == "__main__":
    print("日波动  每月收益差  方向成绩领先")
    for sigma_d in (0.02, 0.03, 0.05):
        for m in (0.005, 0.01, 0.02):
            M, d = simulate(sigma_d, m)
            print(f"{sigma_d:.0%}     {m:.1%}        {d:+.3f}   (M={M:.3f})")
