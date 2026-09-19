"""simulator：有真值的蒙特卡洛，比较调参挑选流程「选中点的真实未来效用」与「报出数字的诚实度」。

生成结构（保留决定答案的四样东西）：
- 嵌套网格：where1 5 档 × where2 4 档（阈值谓词，紧档买点 ⊂ 松档）× 检测轴 5 档（滑动窗，相邻档共享 60% 买点）。
  底层是 260 个「原子」（买点落在哪个 where1 bin、where2 bin、检测坐标 bin），格 = 原子的并。
- 按股簇：买点以「段」为单位成簇（一段 = 1+Poisson(mu) 个买点、同段结果相同，对应长表里同一回踩被多个前缀
  重复计数），另有个股水平效应与个股×特征交互；设计效应标定到 ≈5。
- 时段冲击：每年一份「年份×参数」行情冲击 ζ_t（作用在特征基上）+ 每季 η_{t,q} + 水平冲击 b。
  训练年、确认年、部署年独立同分布抽取——部署年的行情冲击就是「行情切换」。
- 真值曲面 h(原子)：flat / mono（越严越好）/ plateau（宽平台）/ peak（薄样本角落尖峰）/ theta0opt（现行参数即最优）。

年份：训练 T 年（有数据）→ 确认 1 年（有数据，只给「+v」版本的验证门用）→ 部署 1 年（只有真值）。
效用：Q = 首次穿越率（点）；U = (首次穿越率 − 基线) × n/(n+n0)（点），n0 = 工作点期望年买点数。
所有流程报「相对工作点的增益」；G_F = 部署年真值增益，G_S = 平稳真值增益（去掉年份冲击的期望）。

用法：
  uv run python sim.py calibrate
  uv run python sim.py run --reps 600 --tag main
"""
import argparse
import itertools
import os
import time
from multiprocessing import Pool

import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import brentq
from scipy.stats import norm

P0 = 0.50            # 层匹配随机日基线（首次穿越率）
E0 = 0.03            # 工作点相对基线的真实超额（3 点）
S_DEC = 0.62         # 定向占比
SHAPE = (5, 4, 5)
C = int(np.prod(SHAPE))
REF = (1, 1, 2)
REF_FLAT = int(np.ravel_multi_index(REF, SHAPE))
M1 = np.array([.20, .20, .18, .14, .28])   # where1 各 bin 质量；档 l 含 b1>=l（保留 1/.8/.6/.42/.28）
M2 = np.array([.25, .20, .15, .40])        # where2（保留 1/.75/.55/.40）
NU = 13                                    # 检测坐标 bin；窗口 j 覆盖 [2j, 2j+4]
K_FOLD = 5
DELTA = {"Q": 2.0, "U": 1.0}               # 最小关心改进（U 口径 = 2 点 × 工作点权重 0.5）

# 时段冲击两类：局部随机场（sig_f 年 / sig_fq 季，远格方差饱和）+ 线性因子（sig_zeta 年 / sig_eta 季，远格方差随距离线性放大）
NOISE = {
    "N0": dict(sig_b=0.0, sig_bq=0.0, sig_f=0.0, sig_fq=0.0, sig_zeta=0.0, sig_eta=0.0),
    "N1": dict(sig_b=0.032, sig_bq=0.01, sig_f=0.06, sig_fq=0.06, sig_zeta=0.0, sig_eta=0.0),
    "N2": dict(sig_b=0.032, sig_bq=0.01, sig_f=0.06, sig_fq=0.06, sig_zeta=0.03, sig_eta=0.03),
}
# conf_frac：往后那段长度（年），配对 SE≈2.7 点；pre_frac：往前那段长度（年）；b_surv：往前段对「比工作点松」的格的幸存者偏差平移（点）
BASE = dict(S=250, T=2, E=10.0, mu=3.24, sig_a=0.04, sig_v=0.01, n_min=200, B=40, split_seeds=3,
            conf_frac=0.42, pre_frac=1.25, b_surv=1.0)


def _std(x, w):
    mu = (x * w).sum() / w.sum()
    sd = np.sqrt(((x - mu) ** 2 * w).sum() / w.sum())
    return (x - mu) / sd


def build_atoms():
    b1, b2, bu = [g.ravel() for g in np.meshgrid(np.arange(5), np.arange(4), np.arange(NU), indexing="ij")]
    mass = M1[b1] * M2[b2] / NU
    c1 = np.concatenate([[0], np.cumsum(M1)]); mid1 = (c1[:-1] + c1[1:]) / 2
    c2 = np.concatenate([[0], np.cumsum(M2)]); mid2 = (c2[:-1] + c2[1:]) / 2
    z1 = _std(mid1[b1], mass); z2 = _std(mid2[b2], mass); zu = _std((bu + .5) / NU, mass)
    phi = np.stack([z1, z2, zu, _std(zu ** 2, mass), _std(z1 * zu, mass)], 1)
    l1, l2, j = [g.ravel() for g in np.meshgrid(np.arange(5), np.arange(4), np.arange(5), indexing="ij")]
    M = ((b1[None] >= l1[:, None]) & (b2[None] >= l2[:, None])
         & (bu[None] >= 2 * j[:, None]) & (bu[None] <= 2 * j[:, None] + 4)).astype(float)
    coords = np.stack([l1, l2, j], 1)
    return dict(b1=b1, b2=b2, bu=bu, z1=z1, z2=z2, mass=mass, phi=phi, M=M, coords=coords,
                cell_mass=M @ mass, cell_phi=(M @ (mass[:, None] * phi)) / (M @ mass)[:, None],
                dist=np.abs(coords[:, None, :] - coords[None, :, :]).sum(-1))


AT = build_atoms()
_u = np.stack([AT["b1"], AT["b2"], AT["bu"] / 2.0], 1)
FIELD_L = np.linalg.cholesky(np.exp(-((_u[:, None] - _u[None]) ** 2).sum(-1) / 2.0) + 1e-6 * np.eye(_u.shape[0]))


def cell_avg(h):
    return AT["M"] @ (AT["mass"] * h) / AT["cell_mass"]


def surface(name, A):
    """原子级真值 h（概率单位）；缩放使「最好格 − 工作点」= A 点（theta0opt：最大落差 = A 点）。"""
    b1, b2, bu = AT["b1"], AT["b2"], AT["bu"]
    if name == "flat" or A == 0:
        return np.zeros(b1.size)
    if name == "mono":
        h = AT["z1"] + AT["z2"]
    elif name == "plateau":
        z1_at2 = AT["z1"][np.argmax(b1 == 2)]
        h = np.minimum(AT["z1"], z1_at2) + np.where((bu <= 2) | (bu >= 11), -0.2, 0.0)
    elif name == "peak":
        h = ((b1 == 4) & (b2 == 3) & (bu >= 10)).astype(float)
    elif name == "relax":
        # 「放松更好」：mono 的镜像，where1、where2 越松越好；最好格在最松角 (0,0,·)，买点 1.67×工作点
        h = -(AT["z1"] + AT["z2"])
    elif name == "relaxp":
        # 「放松更好」的敏感性版本：只有 where1 最松一档新纳入的买点更好，其余原子全平；
        # where1 = 0 的 20 格同为最大值（松侧平台），比工作点紧的薄格真增益恒为 0（纯噪声干扰项）
        h = (b1 == 0).astype(float)
    elif name == "theta0opt":
        h = (np.array([-1, .6, 0, -.6, -1.2])[b1] + np.array([-1, .5, -.3, -.8])[b2]
             - ((bu - 6) / 6.0) ** 2)
    else:
        raise ValueError(name)
    d = cell_avg(h); d = d - d[REF_FLAT]
    scale = (A / 100) / (np.abs(d).max() if name == "theta0opt" else d.max())
    return h * scale


# ---------------------------------------------------------------- 数据生成
def simulate(rng, cfg, h):
    """返回 (UP, D, N) 形状 (S, T+1, C)（训练 T 年 + 确认 1 年）与真值字典。"""
    S, T = cfg["S"], cfg["T"]
    Y = T + 2                                            # 训练 T 年 + 往后那段 + 往前那段（有数据）；下标 Y = 部署年（只有真值）
    lam = rng.gamma(2.0, 0.5, S)
    a_s = rng.normal(0, cfg["sig_a"], S)
    v_s = rng.normal(0, cfg["sig_v"], (S, 5))
    b_t = rng.normal(0, cfg["sig_b"], Y + 1)
    b_tq = rng.normal(0, cfg["sig_bq"], (Y + 1, 4))
    zeta = rng.normal(0, cfg["sig_zeta"], (Y + 1, 5))
    eta = rng.normal(0, cfg["sig_eta"], (Y + 1, 4, 5))
    na = AT["mass"].size
    fld = cfg["sig_f"] * (FIELD_L @ rng.normal(size=(na, Y + 1))).T                    # (Y+1, atoms)
    fldq = cfg["sig_fq"] * np.einsum("ab,tqb->tqa", FIELD_L, rng.normal(size=(Y + 1, 4, na)))
    rate = np.full(Y * 4, cfg["E"] / 4)
    rate[T * 4:(T + 1) * 4] *= cfg["conf_frac"]          # 往后那段只有约 5 个月
    rate[(T + 1) * 4:] *= cfg["pre_frac"]                # 往前那段约 15 个月
    n_ep = rng.poisson(np.outer(lam, rate)).ravel()
    stock = np.repeat(np.repeat(np.arange(S), Y * 4), n_ep)
    tq = np.repeat(np.tile(np.arange(Y * 4), S), n_ep)
    t, q = tq // 4, tq % 4
    nE = stock.size
    atom = rng.choice(AT["mass"].size, nE, p=AT["mass"])
    size = 1.0 + rng.poisson(cfg["mu"], nE)
    dirn = rng.random(nE) < S_DEC
    ph = AT["phi"][atom]
    p = (P0 + E0 + h[atom] + b_t[t] + b_tq[t, q] + (ph * (zeta[t] + eta[t, q])).sum(1)
         + fld[t, atom] + fldq[t, q, atom] + a_s[stock] + (ph * v_s[stock]).sum(1))
    p = np.clip(p, .01, .99)
    up = dirn & (rng.random(nE) < p)
    key = (stock * Y + t) * AT["mass"].size + atom
    nb = S * Y * AT["mass"].size
    Mt = AT["M"].T
    UP = np.bincount(key, size * up, nb).reshape(S, Y, -1) @ Mt
    D = np.bincount(key, size * dirn, nb).reshape(S, Y, -1) @ Mt
    N = np.bincount(key, size, nb).reshape(S, Y, -1) @ Mt
    q_stat = P0 + E0 + cell_avg(h)

    def q_year(k):
        return (q_stat + b_t[k] + b_tq[k].mean() + AT["cell_phi"] @ (zeta[k] + eta[k].mean(0))
                + cell_avg(fld[k] + fldq[k].mean(0)))

    n_true = S * cfg["E"] * (1 + cfg["mu"]) * AT["cell_mass"]
    return UP, D, N, dict(q_stat=q_stat, q_dep=q_year(Y), q_conf=q_year(T),
                          q_train=np.stack([q_year(k) for k in range(T)]), n_true=n_true)


# ---------------------------------------------------------------- 打分与规则
def sc(obj, n0, U, D, N, yrs):
    with np.errstate(invalid="ignore", divide="ignore"):
        fp = U / D
        if obj == "Q":
            return 100 * fp
        n = N / yrs
        return 100 * (fp - P0) * n / (n + n0)


def truth(obj, q, n_true, n0):
    return 100 * q if obj == "Q" else 100 * (q - P0) * n_true / (n_true + n0)


def neighbor_min(s, ev):
    ev = np.broadcast_to(ev, s.shape)
    out = np.where(ev, s, np.nan)
    for ax in (-3, -2, -1):
        for sh in (1, -1):
            nb = np.roll(s, sh, axis=ax)
            ok = np.roll(ev, sh, axis=ax).copy()
            idx = [slice(None)] * s.ndim
            idx[ax] = 0 if sh == 1 else -1
            ok[tuple(idx)] = False
            out = np.where(ev & ok, np.fmin(out, nb), out)
    return out


def view(X, W):
    """X = (UP, D, N) 形状 (S, T, C)；W 形状 (..., S, T) 的股×年权重。返回按年聚合 (..., T, C) 与每年股票占比。"""
    UP, D, N = X
    frac = W.sum(-2) / W.shape[-2]
    return (np.einsum("...st,stc->...tc", W, UP), np.einsum("...st,stc->...tc", W, D),
            np.einsum("...st,stc->...tc", W, N), frac)


def pooled_delta(obj, n0, Ut, Dt, Nt, frac):
    s = sc(obj, n0, Ut.sum(-2), Dt.sum(-2), Nt.sum(-2), frac.sum(-1)[..., None])
    return s - s[..., [REF_FLAT]]


def rule_peak(obj, n0, V, mask):
    d = pooled_delta(obj, n0, *V)
    key = np.where(mask & np.isfinite(d), d, -np.inf)
    c = key.argmax(-1)
    return c, np.take_along_axis(d, c[..., None], -1)[..., 0]


def plateau_snb(obj, n0, V, mask):
    """现行规则的邻域分：每年相对工作点增量 → 年份取较差 → r=1 邻域取最小（只在可评估格之间）。"""
    Ut, Dt, Nt, frac = V
    s_t = sc(obj, n0, Ut, Dt, Nt, frac[..., None])
    d_t = s_t - s_t[..., [REF_FLAT]]
    d_t = np.where(frac[..., None] > 0, d_t, np.inf)
    s = d_t.min(-2)
    ev = mask & np.isfinite(s)
    shp = s.shape[:-1] + SHAPE
    return neighbor_min(s.reshape(shp), ev.reshape(shp)).reshape(s.shape)


def rule_plateau(obj, n0, V, mask):
    snb = plateau_snb(obj, n0, V, mask)
    key = np.where(np.isfinite(snb), snb, -np.inf)
    c = key.argmax(-1)
    return c, np.take_along_axis(snb, c[..., None], -1)[..., 0]


RULES = {"pk": rule_peak, "pl": rule_plateau}


def var_from_psi(psi):
    S = psi.shape[0]
    return (psi ** 2).sum(0) * S / (S - 1)


def eb_arm(lev_t, s2L, mask, T):
    """unifier 方向 E（修正版）：逐格水平两向随机效应 U_y(θ) = α_y + A(θ) + ξ_y(θ) + ε_y(θ)，工作点也被收缩。
    返回 (格, 换参增益后验, 预测 SD)。"""
    m = np.where(mask & np.isfinite(lev_t).all(0))[0]
    L = lev_t[:, m]; s2 = s2L[:, m]
    pairs = list(itertools.combinations(range(T), 2))
    sA = max(0.0, float(np.mean([np.cov(L[a], L[b])[0, 1] for a, b in pairs])))
    sX = float(np.mean([max(0.0, (np.var(L[a] - L[b], ddof=1) - np.mean(s2[a] + s2[b])) / 2) for a, b in pairs]))
    Ub = L.mean(0); u = Ub.mean()
    v = sX / T + s2.mean(0) / T
    rho = sA / (sA + v) if sA > 0 else np.zeros_like(v)
    r0 = int(np.where(m == REF_FLAT)[0][0])
    gain = rho * (Ub - u) - rho[r0] * (Ub[r0] - u)
    gain[r0] = 0.0
    k = int(np.argmax(gain))
    return int(m[k]), float(gain[k]), float(np.sqrt(rho[k] * v[k] + rho[r0] * v[r0] + 2 * sX))


def eb_paired(d_t, s2P, mask, T, center):
    """unifier 方向 E0（配对差版）：d̃ = m + ρ(d̄ − m)，m = 格均值或 0。返回 (格, d̃, 预测 SD)。"""
    m = np.where(mask & (np.arange(C) != REF_FLAT) & np.isfinite(d_t).all(0))[0]
    Dm = d_t[:, m]; s2 = s2P[:, m]
    pairs = list(itertools.combinations(range(T), 2))
    sM = max(0.0, float(np.mean([np.cov(Dm[a], Dm[b])[0, 1] for a, b in pairs])))
    sE = float(np.mean([max(0.0, (np.var(Dm[a] - Dm[b], ddof=1) - np.mean(s2[a] + s2[b])) / 2) for a, b in pairs]))
    db = Dm.mean(0)
    c0 = db.mean() if center == "mean" else 0.0
    v = sE / T + s2.mean(0) / T
    rho = sM / (sM + v) if sM > 0 else np.zeros_like(v)
    dt = c0 + rho * (db - c0)
    k = int(np.argmax(dt))
    return int(m[k]), float(dt[k]), float(np.sqrt(rho[k] * v[k] + sE))


def eb_spikeslab(d_t, s2P, mask, T):
    """尖峰加平板：d(θ) ~ (1−w)·δ0 + w·N(0, s²)，噪声方差同 eb_paired 的 v(θ)；(w, s) 按边际似然在网格上取。返回 (格, 后验均值)。"""
    m = np.where(mask & (np.arange(C) != REF_FLAT) & np.isfinite(d_t).all(0))[0]
    Dm = d_t[:, m]; s2 = s2P[:, m]
    pairs = list(itertools.combinations(range(T), 2))
    sE = float(np.mean([max(0.0, (np.var(Dm[a] - Dm[b], ddof=1) - np.mean(s2[a] + s2[b])) / 2) for a, b in pairs]))
    db = Dm.mean(0)
    v = sE / T + s2.mean(0) / T
    l0 = norm.logpdf(db, 0, np.sqrt(v))
    best = None
    for s in (0.5, 1.0, 2.0, 3.0, 4.0, 6.0):
        l1 = norm.logpdf(db, 0, np.sqrt(v + s * s))
        for w in (0.01, 0.03, 0.1, 0.3, 1.0):
            ll = float((np.logaddexp(np.log1p(-w) + l0, np.log(w) + l1) if w < 1 else l1).sum())
            if best is None or ll > best[0]:
                best = (ll, s, w, l1)
    _, s, w, l1 = best
    p = np.ones_like(db) if w >= 1 else 1 / (1 + np.exp(np.log1p(-w) + l0 - np.log(w) - l1))
    post = p * s * s / (s * s + v) * db
    k = int(np.argmax(post))
    return int(m[k]), float(post[k])


def trunc_median_unbiased(est, se, z=1.645, lo_mult=60.0):
    """写入条件 est > z·se 下的中位无偏估计：解 P(X ≤ est | X > z·se; μ) = 0.5。
    刚过线时解趋于负无穷，截在 est − lo_mult·se。"""
    def f(mu):
        return 0.5 - np.exp(norm.logsf((est - mu) / se) - norm.logsf(z - mu / se))
    lo, hi = est - lo_mult * se, est + 3 * se
    if f(lo) < 0:
        return float(lo)
    if f(hi) > 0:
        return float(hi)
    return float(brentq(f, lo, hi))


def influence(obj, n0, UP, D, N, years, paired=True, yrs=None):
    """按股线性化影响函数 (S, C)；paired=True 返回相对工作点增益的影响，否则返回水平的影响；years = 参与合并的年下标列表；
    yrs = 这些数据折合多少年（缺省 = 年数），U 口径换算年买点数用。"""
    Us, Ds, Ns = UP[:, years].sum(1), D[:, years].sum(1), N[:, years].sum(1)
    Tn = len(years) if yrs is None else yrs
    S = UP.shape[0]
    fp = Us.sum(0) / Ds.sum(0)
    psi = (Us - fp * Ds) / Ds.sum(0)
    if obj == "Q":
        psi = 100 * psi
    else:
        n = Ns.sum(0) / Tn
        psi = 100 * (n / (n + n0) * psi + (fp - P0) * n0 / (n + n0) ** 2 * (Ns / Tn - n / S))
    return psi - psi[:, [REF_FLAT]] if paired else psi


def cov_from_psi(psi):
    S = psi.shape[0]
    return psi.T @ psi * S / (S - 1)


def _kexp0(ell):
    K = np.exp(-AT["dist"] / ell)
    return K - np.outer(K[:, REF_FLAT], K[REF_FLAT, :])


K_EXP0 = _kexp0(2.0)
_dx = AT["coords"] - AT["coords"][REF_FLAT]
K_LIN = _dx @ _dx.T                                    # 线性趋势核，工作点处自然为 0
TAU_L = (0.0, 0.5, 1.0, 2.0)
TAU_E = (0.25, 0.5, 1.0, 2.0, 4.0)


def gp_select(d, Sig, mask):
    """先验：线性趋势核 + 指数平滑核（都在工作点条件为 0）；噪声：给定协方差 Sig。
    超参按边际似然在网格上取；选后验均值最大的格，报它的后验均值。"""
    idx = np.where(mask & (np.arange(C) != REF_FLAT) & np.isfinite(d))[0]
    y = d[idx]
    Sg = Sig[np.ix_(idx, idx)]
    Kl = K_LIN[np.ix_(idx, idx)]; Ke = K_EXP0[np.ix_(idx, idx)]
    best = None
    for tl in TAU_L:
        for te in TAU_E:
            Kp = tl ** 2 * Kl + te ** 2 * Ke
            A = Kp + Sg + 1e-8 * np.eye(len(idx))
            try:
                cf = cho_factor(A, lower=True)
            except np.linalg.LinAlgError:
                continue
            al = cho_solve(cf, y)
            ll = -0.5 * y @ al - np.log(np.diag(cf[0])).sum()
            if best is None or ll > best[0]:
                best = (ll, Kp, al)
    _, Kp, al = best
    full = np.full(C, -np.inf)
    full[idx] = Kp @ al
    full[REF_FLAT] = 0.0
    c = int(full.argmax())
    return c, float(full[c])


def make_blocks(kind, S, T, folds):
    tr, ho = [], []
    if kind == "draft":          # 草案：年 × 股票折，留出一块，其余全用（含同年其它股票、同股其它年）
        for t in range(T):
            for k in range(K_FOLD):
                w = np.ones((S, T)); w[folds == k, t] = 0
                h = np.zeros((S, T)); h[folds == k, t] = 1
                tr.append(w); ho.append(h)
    elif kind == "stock":        # 只按股票折（留出股票的所有年）
        for k in range(K_FOLD):
            w = np.ones((S, T)); w[folds == k, :] = 0
            tr.append(w); ho.append(1 - w)
    elif kind == "loyo":         # 只留一年
        for t in range(T):
            w = np.ones((S, T)); w[:, t] = 0
            tr.append(w); ho.append(1 - w)
    elif kind == "strict":       # 双向剔除：训练 = 其它年 ∩ 其它股票
        for t in range(T):
            for k in range(K_FOLD):
                w = np.zeros((S, T)); w[folds != k, :] = 1; w[:, t] = 0
                h = np.zeros((S, T)); h[folds == k, t] = 1
                tr.append(w); ho.append(h)
    return np.stack(tr), np.stack(ho)


# ---------------------------------------------------------------- 一个 rep
def one_rep(args):
    scen, rep, cfg = args
    rng = np.random.default_rng([scen["sid"], rep, 20260915])
    h = surface(scen["surface"], scen["A"])
    UPa, Da, Na, tr = simulate(rng, cfg, h)
    S, T = cfg["S"], cfg["T"]
    X = (UPa[:, :T], Da[:, :T], Na[:, :T])
    Xc = (UPa[:, T:T + 1], Da[:, T:T + 1], Na[:, T:T + 1])
    Xp = (UPa[:, T + 1:T + 2], Da[:, T + 1:T + 2], Na[:, T + 1:T + 2])
    UP, D, N = X
    mask = (D.sum(0) >= cfg["n_min"]).all(0)
    n0 = tr["n_true"][REF_FLAT]
    V_all = view(X, np.ones((S, T)))
    folds = rng.permutation(S) % K_FOLD
    BLV = {k: tuple(view(X, b) for b in make_blocks(k, S, T, folds)) for k in ("draft", "stock", "loyo", "strict")}
    Wb = rng.multinomial(S, np.full(S, 1.0 / S), size=cfg["B"]).astype(float)
    Vb = view(X, np.repeat(Wb[:, :, None], T, axis=2))
    halves = [rng.random(S) < 0.5 for _ in range(cfg["split_seeds"])]
    Wwf = np.stack([np.concatenate([np.ones((S, o)), np.zeros((S, T - o))], 1) for o in range(1, T)])
    Hwf = np.stack([np.repeat(np.eye(T)[o][None, :], S, 0) for o in range(1, T)])
    Vwf, Vwfh = view(X, Wwf), view(X, Hwf)

    rows = []
    for obj in ("Q", "U"):
        TS = truth(obj, tr["q_stat"], tr["n_true"], n0)
        TF = truth(obj, tr["q_dep"], tr["n_true"], n0)
        dlt = DELTA[obj]
        # 确认年：验证门「不差出 δ 且方向一致」= 估计 > 0 且 估计 − 1.645·SE ≥ −δ
        fc, fpre = cfg["conf_frac"], cfg["pre_frac"]
        d_conf = sc(obj, n0, Xc[0].sum((0, 1)), Xc[1].sum((0, 1)), Xc[2].sum((0, 1)), fc)
        d_conf = d_conf - d_conf[REF_FLAT]
        se_conf = np.sqrt(var_from_psi(influence(obj, n0, *Xc, [0], yrs=fc)))
        # 往前那段：比工作点松的格带幸存者偏差平移（看起来更好）
        d_pre = sc(obj, n0, Xp[0].sum((0, 1)), Xp[1].sum((0, 1)), Xp[2].sum((0, 1)), fpre)
        d_pre = d_pre - d_pre[REF_FLAT]
        relax = tr["n_true"] > tr["n_true"][REF_FLAT]
        d_pre_raw = d_pre
        d_pre = d_pre + cfg["b_surv"] * relax * (1.0 if obj == "Q" else tr["n_true"] / (tr["n_true"] + n0))
        se_pre = np.sqrt(var_from_psi(influence(obj, n0, *Xp, [0], yrs=fpre)))

        def merged(c, dp=None):
            """往前段 + 往后段按精度合并，单侧优效（合并估计 − 1.645·SE > 0）。"""
            dp = d_pre if dp is None else dp
            if c == REF_FLAT:
                return False, 0.0, np.nan
            wp, wq = 1 / se_pre[c] ** 2, 1 / se_conf[c] ** 2
            em = (wp * dp[c] + wq * d_conf[c]) / (wp + wq)
            sm = 1 / np.sqrt(wp + wq)
            return bool(em - 1.645 * sm > 0), float(em), float(sm)

        def add(proc, c, rep_val=np.nan, se=np.nan, extra=np.nan, val=False):
            c = int(c)
            rows.append((obj, proc, c, TF[c] - TF[REF_FLAT], TS[c] - TS[REF_FLAT], float(rep_val), float(se),
                         float(extra)))
            if val:
                ok = c == REF_FLAT or (d_conf[c] > 0 and d_conf[c] - 1.645 * se_conf[c] >= -dlt)
                cv = c if ok else REF_FLAT
                moved = ok and c != REF_FLAT
                rows.append((obj, proc + "+v", cv, TF[cv] - TF[REF_FLAT], TS[cv] - TS[REF_FLAT],
                             float(d_conf[c]) if moved else 0.0, float(se_conf[c]) if moved else np.nan,
                             float(d_conf[c])))

        add("keep", REF_FLAT, 0.0)
        add("oracle", int(np.argmax(np.where(mask, TS, -np.inf))))
        add("random", rng.choice(np.where(mask)[0]))

        c_nv, v_nv = rule_peak(obj, n0, V_all, mask)
        c_nv = int(c_nv); v_nv = float(v_nv)
        d_pool = pooled_delta(obj, n0, *V_all)
        Sig = cov_from_psi(influence(obj, n0, UP, D, N, list(range(T))))
        se = np.sqrt(np.maximum(np.diag(Sig), 0))
        add("naive", c_nv, v_nv, se=se[c_nv], val=True)
        add("naive_gd", c_nv if v_nv > dlt else REF_FLAT, v_nv if v_nv > dlt else 0.0, val=True)

        # 现行规则 + 三个报数（邻域分 / bootstrap optimism 校正 / 对半分）
        snb0 = plateau_snb(obj, n0, V_all, mask)
        c_cur = int(np.where(np.isfinite(snb0), snb0, -np.inf).argmax()); v_cur = snb0[c_cur]
        snb_b = plateau_snb(obj, n0, Vb, mask)
        cb = np.where(np.isfinite(snb_b), snb_b, -np.inf).argmax(-1)
        opt = np.nanmean(snb_b[np.arange(cfg["B"]), cb] - snb0[cb])
        bsd = np.nanstd(snb_b[:, c_cur], ddof=1)
        sh_vals = []
        for hm in halves:
            for sel in (hm, ~hm):
                ca, _ = rule_plateau(obj, n0, view(X, np.repeat(sel.astype(float)[:, None], T, 1)), mask)
                sv = plateau_snb(obj, n0, view(X, np.repeat((~sel).astype(float)[:, None], T, 1)), mask)[int(ca)]
                if np.isfinite(sv):
                    sh_vals.append(sv)
        add("cur", c_cur, v_cur, extra=opt / bsd if bsd > 0 else np.nan, val=True)
        add("cur_corr", c_cur, v_cur - opt, se=bsd, extra=opt)
        add("cur_split", c_cur, np.mean(sh_vals) if sh_vals else np.nan)
        corrected = v_cur - opt
        gated = c_cur if (v_cur > 0 and corrected > 0) else REF_FLAT
        add("cur_gated", gated, corrected if gated != REF_FLAT else 0.0, val=True)
        add("cur_gd", c_cur if v_cur > dlt else REF_FLAT, v_cur if v_cur > dlt else 0.0, val=True)

        # 一倍标准误规则：在「最优 − 其 SE」以内选离工作点最近的格
        key = np.where(mask & np.isfinite(d_pool), d_pool, -np.inf)
        best = int(key.argmax())
        cand = np.where(key >= key[best] - se[best])[0]
        c1 = int(cand[np.lexsort((-key[cand], AT["dist"][REF_FLAT, cand]))[0]])
        add("one_se", c1, d_pool[c1], se=se[c1],
            extra=(d_pool[c_nv] - (TS[c_nv] - TS[REF_FLAT])) / se[c_nv] if se[c_nv] > 0 else np.nan, val=True)
        add("one_se_gd", c1 if d_pool[c1] > dlt else REF_FLAT, d_pool[c1] if d_pool[c1] > dlt else 0.0, val=True)

        # 交叉拟合：各规则的交叉拟合估计；草案 = 取估计更高的规则，最终点 = 该规则全数据选点，报该估计
        cells = {"pk": c_nv, "pl": c_cur}
        cvr = {}
        for kind, (Vtr, Vho) in BLV.items():
            dho = pooled_delta(obj, n0, *Vho)
            for rname, rule in RULES.items():
                cbk, _ = rule(obj, n0, Vtr, mask)
                gk = dho[np.arange(len(cbk)), cbk]
                nf = int(np.isfinite(gk).sum())
                cvr[kind, rname] = (float(np.nanmean(gk)),
                                    float(np.nanstd(gk, ddof=1) / np.sqrt(nf)) if nf > 1 else np.nan)
                add(f"cf_{kind}_{rname}", cells[rname], *cvr[kind, rname])
            rb = max(RULES, key=lambda r: cvr[kind, r][0] if np.isfinite(cvr[kind, r][0]) else -np.inf)
            v_rb, se_rb = cvr[kind, rb]
            add(f"cf_{kind}", cells[rb], v_rb, se_rb, extra=float(rb == "pl"), val=kind in ("draft", "strict"))
            if kind in ("draft", "strict", "loyo"):
                g = cells[rb] if v_rb > 0 else REF_FLAT
                add(f"cf_{kind}_g", g, v_rb if g != REF_FLAT else 0.0, val=True)
        # 单一规则 + 交叉拟合估计 > 0 才换（维持现行参数一臂）
        for kind in ("loyo", "strict", "draft"):
            for rname in RULES:
                v_k = cvr[kind, rname][0]
                g = cells[rname] if v_k > 0 else REF_FLAT
                add(f"{rname}_{kind}g", g, v_k if g != REF_FLAT else 0.0, val=True)
        # 前推滚动起点：用前 o 年挑、第 o 年打分（T=2 时只有一个起点）
        dwh = pooled_delta(obj, n0, *Vwfh)
        for rname, rule in RULES.items():
            cw, _ = rule(obj, n0, Vwf, mask)
            gw = dwh[np.arange(T - 1), cw]
            v_w = float(np.nanmean(gw))
            se_w = float(np.nanstd(gw, ddof=1) / np.sqrt(T - 1)) if T > 2 else np.nan
            add(f"wf_{rname}", cells[rname], v_w, se_w)
            g = cells[rname] if v_w > 0 else REF_FLAT
            add(f"wf_{rname}_g", g, v_w if g != REF_FLAT else 0.0, val=True)

        # 平滑先验后验（经验贝叶斯）：噪声 = 按股协方差 / 另加由年份分歧估出的时段分量
        c_eb, v_eb = gp_select(d_pool, Sig, mask)
        add("eb_stock", c_eb, v_eb, val=True)
        V1 = view(X, np.ones((S, T)))
        d_t = sc(obj, n0, V1[0], V1[1], V1[2], V1[3][:, None])
        d_t = d_t - d_t[:, [REF_FLAT]]
        dbar = d_t.mean(0)
        s2P = np.stack([var_from_psi(influence(obj, n0, UP, D, N, [t])) for t in range(T)])
        trS = float(s2P[:, mask].sum())
        Kt = 0.5 * K_LIN / np.mean(np.diag(K_LIN)[mask]) + 0.5 * K_EXP0
        dev = ((d_t[:, mask] - dbar[mask]) ** 2).sum()
        s2t = max(0.0, (dev - (1 - 1 / T) * trS) / ((T - 1) * np.trace(Kt[np.ix_(mask, mask)])))
        c_eb2, v_eb2 = gp_select(d_pool, Sig + s2t * Kt / T, mask)
        add("eb_2way", c_eb2, v_eb2, extra=s2t, val=True)

        # unifier 方向 E：逐格水平两向随机效应（修正版）/ 配对差版（中心 = 格均值 或 0），都是 >δ 才换
        lev_t = sc(obj, n0, V1[0], V1[1], V1[2], V1[3][:, None])
        s2L = np.stack([var_from_psi(influence(obj, n0, UP, D, N, [t], paired=False)) for t in range(T)])
        cA, vA, sdA = eb_arm(lev_t, s2L, mask, T)
        add("eA", cA, vA, sdA)
        add("eA_g", cA if vA > dlt else REF_FLAT, vA if vA > dlt else 0.0, sdA if vA > dlt else np.nan, val=True)
        for center, nm in (("mean", "eP"), ("zero", "ePz")):
            cP, vP, sdP = eb_paired(d_t, s2P, mask, T, center)
            add(nm, cP, vP, sdP)
            add(f"{nm}_g", cP if vP > dlt else REF_FLAT, vP if vP > dlt else 0.0, sdP if vP > dlt else np.nan, val=True)

        # v3：可信度排序 ρ·d̄（工作点中心）/ 尖峰加平板 / 核平滑 等排序，配合并确认窗门
        cV2, vV2, sdV2 = eb_paired(d_t, s2P, mask, T, "zero")
        lb_ok = vV2 - 1.645 * sdV2 > 0
        add("ePz_lb", cV2 if lb_ok else REF_FLAT, vV2 if lb_ok else 0.0)
        add("eb2_gd", c_eb2 if v_eb2 > dlt else REF_FLAT, v_eb2 if v_eb2 > dlt else 0.0)
        cSS, vSS = eb_spikeslab(d_t, s2P, mask, T)
        add("SS", cSS, vSS)
        add("SS_gd", cSS if vSS > dlt else REF_FLAT, vSS if vSS > dlt else 0.0)
        cv_ok = cvr["loyo", "pk"][0] > 0
        ranks = [("A", c_nv), ("cur", c_cur), ("V2", cV2), ("V2k", c_eb2), ("SS", cSS),
                 ("V2cv", cV2 if cv_ok else REF_FLAT), ("Acv", c_nv if cv_ok else REF_FLAT)]
        for nmr, c in ranks:
            ok, em, sm = merged(c)
            add(f"{nmr}_m", c if ok else REF_FLAT, em if ok else 0.0, sm if ok else np.nan,
                extra=trunc_median_unbiased(em, sm) if ok else np.nan)
            ok2 = ok and d_conf[c] >= -dlt
            add(f"{nmr}_mand", c if ok2 else REF_FLAT, em if ok2 else 0.0, sm if ok2 else np.nan)

        # v4：合并门第三种写法（往后段非劣效下界）、去掉幸存者平移的合并门；red-team 的三种开窗前门
        ok, em, sm = merged(c_nv)
        ok3 = ok and d_conf[c_nv] - 1.645 * se_conf[c_nv] >= -dlt
        add("A_mnil", c_nv if ok3 else REF_FLAT, em if ok3 else 0.0)
        ok0, em0, _ = merged(c_nv, d_pre_raw)
        add("A_mb0", c_nv if ok0 else REF_FLAT, em0 if ok0 else 0.0)
        idx = np.where(mask & (np.arange(C) != REF_FLAT))[0]
        m2 = float(np.mean([np.mean(d_t[a, idx] * d_t[b, idx]) for a, b in itertools.combinations(range(T), 2)]))
        pre = {"none": True, "m2": m2 > 0, "rho": vV2 > 0, "cv": cvr["loyo", "pk"][0] > 0}
        for nmr, c in (("A", c_nv), ("V2", cV2)):
            okc, emc, _ = merged(c)
            back = c != REF_FLAT and d_conf[c] + 1.645 * se_conf[c] < 0      # 往后段显著劣于 → 撤回
            for pg, passed in pre.items():
                w = passed and okc and not back
                add(f"{nmr}_pre_{pg}", c if w else REF_FLAT, emc if w else 0.0, extra=float(passed))

        # v5：合并 SE 每段加训练期跨格池化的年交互方差 τ̂²（按 σ_ξ² 矩估计）；开窗前门 G1 = 选中格 ρ·d̄ > δ，
        # G2 = 朴素取最大按股 bootstrap（连挑选重做）校正后 > 0
        pairs = list(itertools.combinations(range(T), 2))
        tau2 = float(np.mean([max(0.0, (np.var(d_t[a, idx] - d_t[b, idx], ddof=1)
                                        - np.mean(s2P[a, idx] + s2P[b, idx])) / 2) for a, b in pairs]))
        sM_ = max(0.0, float(np.mean([np.cov(d_t[a, idx], d_t[b, idx])[0, 1] for a, b in pairs])))
        v_c = tau2 / T + s2P[:, c_nv].mean() / T
        rhod = (sM_ / (sM_ + v_c) if sM_ > 0 else 0.0) * float(d_t[:, c_nv].mean())
        db_b = pooled_delta(obj, n0, *Vb)
        kb = np.where(mask & np.isfinite(db_b), db_b, -np.inf).argmax(-1)
        opt_nv = float(np.nanmean(db_b[np.arange(cfg["B"]), kb] - d_pool[kb]))
        g2 = v_nv - opt_nv > 0
        if c_nv != REF_FLAT:
            wp, wq = 1 / (se_pre[c_nv] ** 2 + tau2), 1 / (se_conf[c_nv] ** 2 + tau2)
            emt = (wp * d_pre[c_nv] + wq * d_conf[c_nv]) / (wp + wq)
            smt = 1 / np.sqrt(wp + wq)
            okt = emt - 1.645 * smt > 0
        else:
            okt, emt, smt = False, 0.0, np.nan
        mue = trunc_median_unbiased(emt, smt) if okt else np.nan
        for nmg, gate in (("A1t", True), ("A1t_G1", rhod > dlt), ("A1t_G2", g2)):
            w = bool(gate and okt)
            add(nmg, c_nv if w else REF_FLAT, emt if w else 0.0, smt if w else np.nan, extra=float(gate))
            add(nmg + "_mue", c_nv if w else REF_FLAT, mue if w else 0.0, extra=tau2)

        # v6：选候选与开窗前门是否用同一把尺子。四臂写入门统一用全式：两段合并（每段方差 + τ̂²）单侧 95% 下界 > 0
        # 且往后段点估计 ≥ −δ。rd = 全部候选格的 ρ·d̄（与 eb_paired(center="zero") 同式）。
        # R0 = d̄ 取最大、无前门；R1 = d̄ 取最大 + 选中格 ρ·d̄ > δ；R2 = ρ·d̄ 取最大 + 该值 > δ；
        # R3 = 在 ρ·d̄ > δ 的格里取 d̄ 最大（无此类格则维持工作点）。「_c」行 = 候选格本身（不过写入门），extra = 是否开窗。
        rho_v = sM_ / (sM_ + tau2 / T + s2P[:, idx].mean(0) / T) if sM_ > 0 else np.zeros(idx.size)
        rd = np.full(C, -np.inf)
        rd[idx] = rho_v * d_t[:, idx].mean(0)
        c_r2 = int(rd.argmax())
        elig = rd > dlt
        c_r3 = int(np.where(elig, d_pool, -np.inf).argmax()) if elig.any() else REF_FLAT
        for nmr, c, opened in (("R0", c_nv, c_nv != REF_FLAT), ("R1", c_nv, rd[c_nv] > dlt),
                               ("R2", c_r2, rd[c_r2] > dlt), ("R3", c_r3, c_r3 != REF_FLAT)):
            if c != REF_FLAT:
                wp, wq = 1 / (se_pre[c] ** 2 + tau2), 1 / (se_conf[c] ** 2 + tau2)
                emw = (wp * d_pre[c] + wq * d_conf[c]) / (wp + wq)
                smw = 1 / np.sqrt(wp + wq)
                okw = emw - 1.645 * smw > 0 and d_conf[c] >= -dlt
            else:
                okw, emw, smw = False, 0.0, np.nan
            w = bool(opened and okw)
            add(nmr, c if w else REF_FLAT, emw if w else 0.0, smw if w else np.nan, extra=float(opened))
            add(nmr + "_c", c, float(rd[c]) if c != REF_FLAT else 0.0, extra=float(opened))
    return scen["sid"], rep, rows


# ---------------------------------------------------------------- 场景与汇总
def scenarios(T=2):
    out, sid = [], 0
    for noise in ("N0", "N1", "N2"):
        for surf, amps in (("flat", [0]), ("mono", [1, 2, 4, 8]), ("plateau", [1, 2, 4, 8]),
                           ("peak", [1, 2, 4, 8]), ("theta0opt", [1, 2, 4, 8])):
            for A in amps:
                out.append(dict(sid=sid, noise=noise, surface=surf, A=A, T=T)); sid += 1
    for surf in ("relax", "relaxp"):                     # v6 新增曲面：sid 接在后面，原 51 个场景的随机种子不变
        for noise in ("N0", "N1", "N2"):
            for A in (1, 2, 4, 8):
                out.append(dict(sid=sid, noise=noise, surface=surf, A=A, T=T)); sid += 1
    return out


def cfg_for(scen, **over):
    cfg = dict(BASE); cfg.update(NOISE[scen["noise"]]); cfg["T"] = scen["T"]; cfg.update(over)
    return cfg


COLS = ["sid", "rep", "obj", "proc", "cell", "G_F", "G_S", "rep_val", "se", "extra"]


def summarize(df, scen_list):
    import pandas as pd
    meta = pd.DataFrame(scen_list)
    df = df.merge(meta, on="sid")
    orc = df[df.proc == "oracle"][["sid", "rep", "obj", "G_S", "G_F"]].rename(columns={"G_S": "O_S", "G_F": "O_F"})
    df = df.merge(orc, on=["sid", "rep", "obj"])
    df["dl"] = df.obj.map(DELTA)

    def f(g):
        rv = g.rep_val.to_numpy(); gf = g.G_F.to_numpy(); gs = g.G_S.to_numpy()
        ok = np.isfinite(rv)
        corr = np.nan
        if ok.sum() > 2 and rv[ok].std() > 1e-12 and gf[ok].std() > 1e-12:
            corr = np.corrcoef(rv[ok], gf[ok])[0, 1]
        return pd.Series(dict(
            G_S=gs.mean(), G_S_se=gs.std(ddof=1) / np.sqrt(len(gs)), G_F=gf.mean(),
            G_F_q10=np.quantile(gf, .1), G_F_q50=np.quantile(gf, .5), G_F_q90=np.quantile(gf, .9),
            O_S=g.O_S.mean(), P_worse_S=(gs < -1e-9).mean(), P_bad_S=(gs < -g.dl.iloc[0] / 2).mean(),
            P_worse_F=(gf < -1e-9).mean(), P_stay=(g.cell == REF_FLAT).mean(),
            bias=(rv[ok] - gf[ok]).mean() if ok.any() else np.nan,
            bias_S=(rv[ok] - gs[ok]).mean() if ok.any() else np.nan,
            rmse=np.sqrt(((rv[ok] - gf[ok]) ** 2).mean()) if ok.any() else np.nan,
            corr=corr, extra=np.nanmean(g.extra) if np.isfinite(g.extra).any() else np.nan,
            cov90=(np.abs(rv - gf) <= 1.645 * g.se.to_numpy())[ok & np.isfinite(g.se.to_numpy())].mean()
            if (ok & np.isfinite(g.se.to_numpy())).any() else np.nan,
            P_badF=(gf < -g.dl.iloc[0]).mean(), P_write=(g.cell != REF_FLAT).mean(), n=len(g)))
    return df.groupby(["noise", "surface", "A", "obj", "proc"], observed=True)[["cell", "G_F", "G_S", "rep_val", "se", "extra", "O_S", "dl"]] \
        .apply(f).reset_index()


def calibrate(reps=200):
    """标定：设计效应、工作点 SE、单翻转 SE（公式 vs 实测，含时段冲击）、年交互 SD、挑选噪声倍数、耗时。"""
    for noise in ("N0", "N1", "N2"):
        scen = dict(sid=999, noise=noise, surface="flat", A=0, T=2)
        cfg = cfg_for(scen)
        h = surface("flat", 0)
        deffs, se_lvls, flips, flip_true_yr, far_true_yr, n_ref, n_corner = [], [], [], [], [], [], []
        flip_cell = int(np.ravel_multi_index((2, 1, 2), SHAPE))   # where1 收紧一档，保留 75%
        far_cell = int(np.ravel_multi_index((4, 3, 4), SHAPE))    # 最紧角
        t0 = time.time()
        for r in range(reps):
            rng = np.random.default_rng([7, r])
            UPa, Da, Na, tr = simulate(rng, cfg, h)
            UP, D = UPa[:, :2], Da[:, :2]
            Us, Ds = UP.sum(1), D.sum(1)
            fp = Us.sum(0) / Ds.sum(0)
            psi_l = 100 * (Us - fp * Ds) / Ds.sum(0)
            se_l = np.sqrt((psi_l[:, REF_FLAT] ** 2).sum() * cfg["S"] / (cfg["S"] - 1))
            p = fp[REF_FLAT]
            deffs.append((se_l / (100 * np.sqrt(p * (1 - p) / Ds[:, REF_FLAT].sum()))) ** 2)
            se_lvls.append(se_l)
            flips.append(100 * (fp[flip_cell] - fp[REF_FLAT]))
            flip_true_yr.append(100 * (tr["q_train"][:, flip_cell] - tr["q_train"][:, REF_FLAT]))
            far_true_yr.append(100 * (tr["q_train"][:, far_cell] - tr["q_train"][:, REF_FLAT]))
            n_ref.append(Na[:, :2, REF_FLAT].sum() / 2)
            n_corner.append(D[:, :, far_cell].sum() / 2)
        r_keep = AT["cell_mass"][flip_cell] / AT["cell_mass"][REF_FLAT]
        se_flip_formula = np.mean(se_lvls) * np.sqrt((1 - r_keep) / r_keep)
        print(f"[{noise}] deff={np.mean(deffs):.2f}  SE_level(两年)={np.mean(se_lvls):.2f}点  "
              f"SE_flip 公式={se_flip_formula:.2f} 实测={np.std(flips):.2f}点 → 2.8×实测={2.8*np.std(flips):.2f}点  "
              f"单年年交互SD：单翻转={np.std(np.array(flip_true_yr)):.2f} 最紧角={np.std(np.array(far_true_yr)):.2f}点  "
              f"工作点年买点={np.mean(n_ref):.0f}  最紧角定向/年={np.mean(n_corner):.0f}  {1000*(time.time()-t0)/reps:.1f}ms/sim")
    import pandas as pd
    t0 = time.time()
    scen = dict(sid=0, noise="N0", surface="flat", A=0, T=2)
    res = [one_rep((scen, r, cfg_for(scen))) for r in range(20)]
    print(f"one_rep 耗时 {1000*(time.time()-t0)/20:.0f}ms")
    df = pd.DataFrame([(s, r, *row) for s, r, rr in res for row in rr], columns=COLS)
    print("挑选噪声倍数（cur: bootstrap optimism/选中格 SD；one_se 列: 朴素取最大的真实虚高/SE）")
    print(df[df.proc.isin(["cur", "one_se"])].groupby(["obj", "proc"]).extra.mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["calibrate", "run"])
    ap.add_argument("--reps", type=int, default=600)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--T", type=int, default=2)
    ap.add_argument("--tag", default="main")
    ap.add_argument("--only", default="", help="逗号分隔的 noise 过滤，如 N0,N1")
    ap.add_argument("--surfaces", default="", help="逗号分隔的曲面过滤")
    a = ap.parse_args()
    if a.mode == "calibrate":
        calibrate()
        return
    import pandas as pd
    scen_list = scenarios(T=a.T)
    if a.only:
        scen_list = [s for s in scen_list if s["noise"] in set(a.only.split(","))]
    if a.surfaces:
        scen_list = [s for s in scen_list if s["surface"] in set(a.surfaces.split(","))]
    tasks = [(s, r, cfg_for(s)) for s in scen_list for r in range(a.reps)]
    t0 = time.time()
    all_rows = []
    with Pool(a.workers) as pool:
        for i, (sid, rep, rows) in enumerate(pool.imap_unordered(one_rep, tasks, chunksize=8)):
            all_rows.extend((sid, rep, *row) for row in rows)
            if (i + 1) % 5000 == 0:
                print(f"{i+1}/{len(tasks)}  {time.time()-t0:.0f}s", flush=True)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out, exist_ok=True)
    df = pd.DataFrame(all_rows, columns=COLS)
    for col in ("obj", "proc"):
        df[col] = df[col].astype("category")
    df.to_parquet(os.path.join(out, f"rows_{a.tag}.parquet"))
    summarize(df, scen_list).to_csv(os.path.join(out, f"summary_{a.tag}.csv"), index=False)
    print(f"done {time.time()-t0:.0f}s → {out}")


if __name__ == "__main__":
    main()
