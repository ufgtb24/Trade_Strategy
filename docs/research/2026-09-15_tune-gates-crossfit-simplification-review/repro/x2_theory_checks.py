"""x2：外推理论的三处数值核对（最小模型，不模拟真实网格；真实网格结构交 simulator）。

(a) 切换门槛的决策论闭式：真实增益 g ~ N(μ, τ_g²)，训练估计 ĝ = g + ε(σ)。规则「ĝ > c 才换」。
    E[增益] = μ·(1−Φ(z)) + τ_g²/s·φ(z)，z = (c−μ)/s，s² = τ_g² + σ²；最优 c* = −μ·σ²/τ_g²（= 收缩后后验均值过 0）。
(b) 交叉拟合的行情泄漏：K 个可交换候选，2 年 × F 个股票折。块分数 = μ_j + a_{j,y} + e_{j,f,y}。
    比较「留一个格子」与「整年留出」两种切法报出的数相对未来真实值的偏差；
    预测：留格子的残余偏差 / 朴素乐观 ≈ w·τ_a² / ((w²+(1−w)²)·τ_a² + σ²)，w = 训练里留出年所占权重。
(c) 门槛的把握：前向窗非劣效 + 同号（现行与草案都用它当写入正式参数的实际门槛）。
"""
import numpy as np
from scipy.stats import norm


def part_a():
    print("== (a) 切换门槛 ==")
    for mu, tg, sig in [(0.0, 1.0, 1.26), (-0.5, 1.0, 1.26), (-0.5, 1.0, 2.2), (-1.0, 2.0, 1.26), (0.5, 1.0, 1.26)]:
        s = np.hypot(tg, sig)
        gain = lambda c: mu * (1 - norm.cdf((c - mu) / s)) + tg ** 2 / s * norm.pdf((c - mu) / s)
        cstar = -mu * sig ** 2 / tg ** 2
        cs = np.linspace(-6, 10, 16001)
        cnum = cs[np.argmax([gain(c) for c in cs])]
        print(f"μ={mu:+.1f} τ_g={tg:.1f} σ={sig:.2f}：c*公式={cstar:+.2f} 数值={cnum:+.2f}；"
              f"E增益(c*)={gain(cstar):+.3f}pt，E增益(c=0 只要估计为正就换)={gain(0):+.3f}pt，"
              f"E增益(c=−∞ 总是换)={mu:+.3f}pt；P(换|c*)={1-norm.cdf((cstar-mu)/s):.2f}")


def part_b(rng, K=50, F=5, tg=1.0, ta=1.0, sig=1.26, R=4000):
    v = 2 * F * sig ** 2  # 单个格子噪声方差，使两年合并均值方差 = σ²
    naive_b, cell_b, year_b, g_full, g_cell, g_year = [], [], [], [], [], []
    for _ in range(R):
        mu = rng.normal(0, tg, K)
        a = rng.normal(0, ta, (K, 2))
        X = mu[:, None, None] + a[:, None, :] + rng.normal(0, np.sqrt(v), (K, F, 2))
        full = X.mean(axis=(1, 2))
        j = np.argmax(full)
        naive_b.append(full[j] - mu[j])
        g_full.append(mu[j])
        tot = X.sum(axis=(1, 2))
        cv, gs = [], []
        for f in range(F):
            for y in range(2):
                tr = (tot - X[:, f, y]) / (2 * F - 1)
                jj = np.argmax(tr)
                cv.append(X[jj, f, y]); gs.append(mu[jj])
        cell_b.append(np.mean(cv) - np.mean(gs)); g_cell.append(np.mean(gs))
        cvy, gy = [], []
        for y in range(2):
            tr = X[:, :, 1 - y].mean(axis=1)
            jj = np.argmax(tr)
            cvy.append(X[jj, :, y].mean()); gy.append(mu[jj])
        year_b.append(np.mean(cvy) - np.mean(gy)); g_year.append(np.mean(gy))
    w = (F - 1) / (2 * F - 1)
    pred = w * ta ** 2 / ((w ** 2 + (1 - w) ** 2) * ta ** 2 + sig ** 2 * (2 * F) / (2 * F - 1))
    m = lambda x: f"{np.mean(x):+.3f}±{np.std(x)/np.sqrt(len(x)):.3f}"
    print(f"τ_a={ta:.1f} σ={sig:.2f}：朴素乐观 {m(naive_b)}；留格子残余偏差 {m(cell_b)}（占朴素 {np.mean(cell_b)/np.mean(naive_b):.0%}，"
          f"公式 {pred:.0%}）；整年留出偏差 {m(year_b)}；"
          f"真实增益 全数据选 {np.mean(g_full):+.3f} / 留格子内层 {np.mean(g_cell):+.3f} / 一年训练 {np.mean(g_year):+.3f}")


def part_c():
    print("== (c) 前向窗门槛：非劣效（单侧 5%，δ=2 点）+ 与训练同号 ==")
    for se in (2.7, 1.9, 1.3):
        cut = norm.ppf(0.95) * se - 2.0
        row = []
        for g in (-2.0, 0.0, 1.0, 2.5, 3.5):
            p = 1 - norm.cdf((max(cut, 0.0) - g) / se)
            row.append(f"g={g:+.1f}:{p:.2f}")
        print(f"前向 SE={se}：估计须 ≥ {max(cut, 0):.2f} 点才写入；P(写入) " + "  ".join(row))


def part_d(rng, J=16, R=200000):
    """unifier 的可靠度判据核对：E[μ_θ̂ − m] = ρ·E[max d̄ − m]，以及「抓到的神谕增益比例」≈ √ρ。"""
    print("== (d) 可靠度 ρ 与抓到的神谕增益比例（J=16 可交换独立候选）==")
    for s_mu, s_eta, s_eps in [(1.0, 0.9, 1.78), (2.0, 0.9, 1.78), (1.0, 0.0, 0.0), (1.0, 2.0, 1.78), (1.0, 0.9, 0.2)]:
        mu = rng.normal(0, s_mu, (R, J))
        dbar = mu + rng.normal(0, np.sqrt(s_eta ** 2 / 2 + s_eps ** 2 / 2), (R, J))
        k = dbar.argmax(1)
        got = mu[np.arange(R), k].mean()
        rho = s_mu ** 2 / (s_mu ** 2 + s_eta ** 2 / 2 + s_eps ** 2 / 2)
        oracle = mu.max(1).mean()
        rho_inf = s_mu ** 2 / (s_mu ** 2 + s_eta ** 2 / 2)
        print(f"σ_μ={s_mu} σ_η={s_eta} σ_ε(每年)={s_eps}：ρ={rho:.2f}；E[μ_θ̂−m]={got:.3f}，ρ·E[max d̄]={rho*dbar.max(1).mean():.3f}；"
              f"神谕 {oracle:.3f}，抓到比例 {got/oracle:.2f} vs √ρ={np.sqrt(rho):.2f}；股票无穷多时 √ρ 上限={np.sqrt(rho_inf):.2f}")


def part_e():
    """写入门槛用哪段证据：往后那段单独（现行实际门槛）/ 往前那段优效 / 两段按精度合并后优效。"""
    print("== (e) 写入门槛的把握：P(写入 | 真实增益 g) ==")
    z = norm.ppf(0.95)
    for se_b in (1.3, 1.6):
        se_f = 2.7
        se_c = 1 / np.sqrt(1 / se_b ** 2 + 1 / se_f ** 2)
        rows = {"往后 非劣效+同号(SE 2.7)": lambda g: 1 - norm.cdf((max(z * se_f - 2.0, 0.0) - g) / se_f),
                f"往前 优效(SE {se_b})": lambda g: 1 - norm.cdf((z * se_b - g) / se_b),
                f"两段合并 优效(SE {se_c:.2f})": lambda g: 1 - norm.cdf((z * se_c - g) / se_c)}
        for name, f in rows.items():
            print(f"{name:>26s}：" + "  ".join(f"g={g:+.1f}:{f(g):.2f}" for g in (-2.0, 0.0, 1.0, 2.5, 3.5)))


def part_f(rng, R=400000):
    """合并确认窗写入门在「时段交互 + 往前那段幸存者偏差」下的真实把握，以及往后兜底的写法对功效的影响。

    往前估计 = g + a_b + b + e_b(SE_b)；往后估计 = g + a_f + e_f(SE_f)；a_b、a_f ~ N(0, τ²) 各自独立（各段行情）。
    检验按名义 SE 做精度加权合并，不知道 τ 与 b 的存在。
    """
    print("== (f) 合并确认窗写入门：P(写入 | 持续增益 g)，SE_b=1.3、SE_f=2.7、δ=2 ==")
    se_b, se_f, z, delta = 1.3, 2.7, norm.ppf(0.95), 2.0
    wb = (1 / se_b ** 2) / (1 / se_b ** 2 + 1 / se_f ** 2)
    se_c = 1 / np.sqrt(1 / se_b ** 2 + 1 / se_f ** 2)
    print(f"往前那段在合并估计里的权重 = {wb:.2f}")
    for tau, b in [(0.0, 0.0), (0.9, 0.0), (2.0, 0.0), (0.9, 1.0), (0.9, -1.0)]:
        out = {"合并优效": [], "合并优效+往后非劣效(下界)": [], "合并优效+往后点估计≥−δ": []}
        for g in (-2.0, 0.0, 1.0, 2.5, 3.5):
            eb = g + rng.normal(0, tau, R) + b + rng.normal(0, se_b, R)
            ef = g + rng.normal(0, tau, R) + rng.normal(0, se_f, R)
            ec = wb * eb + (1 - wb) * ef
            sup = ec - z * se_c > 0
            out["合并优效"].append(sup.mean())
            out["合并优效+往后非劣效(下界)"].append((sup & (ef - z * se_f >= -delta)).mean())
            out["合并优效+往后点估计≥−δ"].append((sup & (ef >= -delta)).mean())
        print(f"τ={tau} 幸存者偏差 b={b:+.1f}：")
        for k, v in out.items():
            print(f"   {k:>18s}  " + "  ".join(f"g={g:+.1f}:{p:.3f}" for g, p in zip((-2, 0, 1, 2.5, 3.5), v)))


def main():
    rng = np.random.default_rng(20260915)
    part_f(rng)
    part_e()
    part_d(rng)
    part_a()
    print("== (b) 交叉拟合的行情泄漏（K=50 可交换候选，F=5 股票折）==")
    for ta in (0.0, 1.0, 2.0):
        part_b(rng, ta=ta)
    part_c()


if __name__ == "__main__":
    main()
