# -*- coding: utf-8 -*-
"""调参统计核:按股去簇的比率误差、多重比较、max-T 逐步法、簇稳健加权回归、闸存在性层匹配差。

纯 numpy / scipy / pandas,不 import 项目代码。

口径约定:
- 首次穿越率 r = ΣU / ΣD。U = up 计数,D = up+down+both 计数(定向 bar),N = 含 none 的计数。
- 所有估计量、SE、δ 一律用比例(0.02 = 2 点),报告层再乘 100。
- 误差按股去簇:股票是方差与 bootstrap 的独立单位;时间维只作旗标,不在这里处理。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


# ── 按股线性化比率误差 ──

def ratio_contrast(U, D, N, coef) -> dict:
    """若干格首次穿越率的线性组合 Σ_k c_k·r_k 及其按股线性化 SE。

    参数:
        U, D, N: 形状 (S, K) 的每股计数和(S 只股 × K 个格),调用方已按买点去重,
                 并已按折限定(分年)或两年合并。
        coef: 形状 (K,) 的系数 c_k;c_k = 0 的格不算「涉及格」。
    公式:
        r_k = ΣU_k / ΣD_k
        股票残差 E_{k,s} = (U_{k,s} − r_k·D_{k,s}) / ΣD_k(某格没有该股时计数为 0,残差即为 0)
        合成残差 T_s = Σ_k c_k·E_{k,s}
        est = Σ_k c_k·r_k;SE = √(n/(n−1)·Σ_s T_s²);z = est / SE
        n = 至少在一个涉及格里 N_{k,s} > 0 的股票数(簇数)
    返回 {"est", "se", "z", "n_clusters", "r": (K,), "n_dir": (K,) = ΣD_k}。
    涉及格 ΣD = 0 时 est/se/z 为 nan;n < 2 时 se/z 为 nan;SE = 0 时 z 为 nan。
    """
    U = np.asarray(U, dtype=float)
    D = np.asarray(D, dtype=float)
    N = np.asarray(N, dtype=float)
    c = np.asarray(coef, dtype=float)
    if U.ndim != 2 or D.shape != U.shape or N.shape != U.shape or c.shape != (U.shape[1],):
        raise ValueError(f"形状不符:U {U.shape} D {D.shape} N {N.shape} coef {c.shape}")
    n_dir = D.sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = U.sum(axis=0) / n_dir
    inv = c != 0
    ci, ri, di = c[inv], r[inv], n_dir[inv]
    est = float(ci @ ri)
    with np.errstate(divide="ignore", invalid="ignore"):
        T = ((U[:, inv] - ri * D[:, inv]) / di) @ ci
    n = int((N[:, inv] > 0).any(axis=1).sum())
    se = float(np.sqrt(n / (n - 1) * (T ** 2).sum())) if n >= 2 else float("nan")
    z = est / se if se > 0 else float("nan")
    return {"est": est, "se": se, "z": z, "n_clusters": n, "r": r, "n_dir": n_dir}


def level_se(U, D, N) -> dict:
    """单格首次穿越率的按股线性化 SE 与设计效应。

    参数:U, D, N 形状 (S,) 的每股计数和。
    公式:即 ratio_contrast 取单格、系数 1;设计效应 deff = (SE / √(r(1−r)/ΣD))²,
        分母是把全部定向 bar 当独立二项观测时的 SE。
    返回 {"r", "se", "deff", "n_dir", "n_clusters"}。
    """
    col = lambda a: np.asarray(a, dtype=float)[:, None]  # noqa: E731
    out = ratio_contrast(col(U), col(D), col(N), [1.0])
    r, n_dir, se = float(out["r"][0]), float(out["n_dir"][0]), out["se"]
    binom = np.sqrt(r * (1 - r) / n_dir) if n_dir > 0 else float("nan")
    deff = float((se / binom) ** 2) if binom > 0 else float("nan")
    return {"r": r, "se": se, "deff": deff, "n_dir": n_dir, "n_clusters": out["n_clusters"]}


# ── 多重比较 ──

def bh(pvals) -> np.ndarray:
    """Benjamini-Hochberg q 值。

    p 升序排,q_(i) = min_{j≥i} m·p_(j)/j,截到 1;q ≤ 阈值即幸存。
    NaN 的 p 排在最后、q 记 1,但仍计入 m(与 feature-study 统计电池原实现逐位一致)。
    """
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    scaled = p[order] * m / np.arange(1, m + 1)
    # 从最大名次往前累积取小;起点 1.0 即截到 1,fmin 让 NaN 不污染累积值
    q_sorted = np.fmin.accumulate(np.concatenate(([1.0], scaled[::-1])))[1:][::-1]
    q = np.empty(m)
    q[order] = q_sorted
    return q


def simes(pvals) -> float:
    """Simes 合并 p 值:p 升序排,p = min_i m·p_(i)/i(全局零假设检验,用作闸内合并)。"""
    p = np.sort(np.asarray(pvals, dtype=float))
    m = len(p)
    return float(np.min(p * m / np.arange(1, m + 1)))


def holm(pvals) -> np.ndarray:
    """Holm 调整后 p 值(控制 FWER),按输入顺序返回。

    p 升序排,p_adj_(i) = max_{l≤i} min(1, (m−l+1)·p_(l))。
    """
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    adj = np.maximum.accumulate(np.minimum(1.0, (m - np.arange(m)) * p[order]))
    out = np.empty(m)
    out[order] = adj
    return out


def z_bh_first(m: int, q: float) -> float:
    """双侧检验下 BH 第一名的 z 门槛:Φ⁻¹(1 − q/(2m)),m 为实际对比族大小。"""
    return float(stats.norm.ppf(1 - q / (2 * m)))


# ── 异质性与功效 ──

def cochran_q(est_w, se_w) -> dict | None:
    """Cochran Q 异质性检验(各时间窗估计是否一致)。

    只用 est、se 有限且 se > 0 的窗;权重 1/se²,ē 为加权均值。
    Q = Σ(e_w − ē)²/se_w²,自由度 = 窗数 − 1,p 取 χ² 上尾。
    返回 {"Q", "df", "p", "n_windows"};可用窗少于 2 个时返回 None。
    """
    e = np.asarray(est_w, dtype=float)
    s = np.asarray(se_w, dtype=float)
    ok = np.isfinite(e) & np.isfinite(s) & (s > 0)
    k = int(ok.sum())
    if k < 2:
        return None
    e, w = e[ok], 1.0 / s[ok] ** 2
    ebar = (w * e).sum() / w.sum()
    Q = float((w * (e - ebar) ** 2).sum())
    return {"Q": Q, "df": k - 1, "p": float(stats.chi2.sf(Q, k - 1)), "n_windows": k}


def power_normal(theta, se, alpha: float = 0.05) -> float:
    """正态近似下单侧检验的功效:1 − Φ(z_{1−α} − θ/se)。"""
    return float(stats.norm.sf(stats.norm.ppf(1 - alpha) - theta / se))


# ── max-T 逐步法 ──

def _stock_weights(rng: np.random.Generator, S: int, B: int) -> np.ndarray:
    """按股 multinomial bootstrap 权重 (B, S):每个副本从 S 只股里等概率有放回抽 S 次,权重 = 被抽中次数。"""
    return rng.multinomial(S, np.full(S, 1.0 / S), size=B).astype(float)


def maxT_stepdown(T_obs, T_star) -> np.ndarray:
    """Westfall–Young 逐步 max-T 调整后 p 值(单侧,T 越大越显著),按输入顺序返回。

    参数:T_obs 形状 (m,) 的观测统计量;T_star 形状 (B, m) 的零分布副本。
    算法:按 T_obs 降序排出 j(1..m),
        p̃_i = mean_b[ max_{k≥i} T*_{j(k)} ≥ T_{j(i)} ]
        p_adj_i = max_{l≤i} p̃_l(保证调整后 p 随名次单调)
    副本里为 NaN 的 T* 不参与该副本的取大;T_obs 为 NaN 的检验返回 NaN。
    """
    T = np.asarray(T_obs, dtype=float)
    Ts = np.asarray(T_star, dtype=float)
    m = len(T)
    if Ts.ndim != 2 or Ts.shape[1] != m:
        raise ValueError(f"T_star 形状应为 (B, {m}),实际 {Ts.shape}")
    order = np.argsort(-T, kind="stable")
    # 第 i 列 = 名次 i 及其之后全部检验的 T* 最大值
    tail_max = np.fmax.accumulate(Ts[:, order[::-1]], axis=1)[:, ::-1]
    p_tilde = (tail_max >= T[order]).mean(axis=0)
    out = np.empty(m)
    out[order] = np.maximum.accumulate(p_tilde)
    out[np.isnan(T)] = np.nan
    return out


def maxT_from_sums(U, D, contrasts, margins, se, B: int, seed: int) -> dict:
    """从每股计数和出发做 max-T 逐步法:m 个格对比的联合单侧检验。

    参数:
        U, D: 形状 (S, K) 的每股计数和。
        contrasts: 形状 (m, K) 的系数矩阵,第 j 行是第 j 个对比的 c_k。
        margins: 形状 (m,);优效检验取 0,非劣效检验取 δ(检验 est > −δ)。
        se: 形状 (m,) 的各对比按股线性化 SE(ratio_contrast 算出)。
        B, seed: bootstrap 副本数与种子。
    算法:
        est_j = Σ_k c_jk·r_k,T_j = (est_j + margin_j) / se_j
        副本 b:w_b ~ Multinomial(S, 1/S) 按股抽权重,r*_bk = Σ_s w·U / Σ_s w·D,
        est*_jb = Σ_k c_jk·r*_bk,T*_jb = (est*_jb − est_j) / se_j(以原估计为中心 = 零分布)
        p_adj = maxT_stepdown(T, T*)
    只有被某个对比用到的格参与计算;副本里某格 Σw·D = 0 时对应 T* 为 NaN,不参与该副本取大。
    返回 {"T": (m,), "p_adj": (m,), "est": (m,)}。
    """
    U = np.asarray(U, dtype=float)
    D = np.asarray(D, dtype=float)
    C = np.atleast_2d(np.asarray(contrasts, dtype=float))
    margins = np.asarray(margins, dtype=float)
    se = np.asarray(se, dtype=float)
    inv = (C != 0).any(axis=0)
    U, D, C = U[:, inv], D[:, inv], C[:, inv]
    est = C @ (U.sum(axis=0) / D.sum(axis=0))
    T = (est + margins) / se
    W = _stock_weights(np.random.default_rng(seed), U.shape[0], B)
    with np.errstate(divide="ignore", invalid="ignore"):
        r_star = (W @ U) / (W @ D)
    T_star = (r_star @ C.T - est) / se
    return {"T": T, "p_adj": maxT_stepdown(T, T_star), "est": est}


# ── 簇稳健加权回归 ──

def cluster_wls(y, X, w, clusters) -> dict:
    """加权最小二乘 + 按簇 CR1 稳健方差。

    参数:y (n,);X (n, k) 设计矩阵(调用方自带截距列);w (n,) 观测权重;clusters (n,) 簇标签。
    公式:
        β = (XᵀWX)⁻¹XᵀWy,残差 e = y − Xβ
        簇得分 s_g = Σ_{i∈g} x_i·w_i·e_i
        V = c·(XᵀWX)⁻¹(Σ_g s_g s_gᵀ)(XᵀWX)⁻¹,CR1 系数 c = G/(G−1)·(n−1)/(n−k)
    返回 {"beta", "se", "V", "n", "G", "k"}。
    """
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    w = np.asarray(w, dtype=float)
    n, k = X.shape
    codes, uniq = pd.factorize(pd.Series(np.asarray(clusters)))
    if (codes < 0).any():
        raise ValueError("clusters 含缺失值")
    G = len(uniq)
    XtWX = X.T @ (X * w[:, None])
    bread = np.linalg.inv(XtWX)
    beta = np.linalg.solve(XtWX, X.T @ (w * y))
    xwe = X * (w * (y - X @ beta))[:, None]
    score = np.column_stack([np.bincount(codes, weights=xwe[:, j], minlength=G) for j in range(k)])
    c = G / (G - 1) * (n - 1) / (n - k)
    V = c * bread @ (score.T @ score) @ bread
    return {"beta": beta, "se": np.sqrt(np.diag(V)), "V": V, "n": n, "G": G, "k": k}


# ── 时间窗 ──

# 交易日 → 日历天(与 path2_web.scan.TRADING_TO_CALENDAR_RATIO 同值;本模块不 import 项目代码,故就地定义)
TRADING_TO_CALENDAR = 365 / 252


def time_window_days(label_horizon: int) -> int:
    """时间窗宽(日历天)= round(label_horizon × 365/252),即窗宽与标签前瞻期的交易日数等长。"""
    return int(round(label_horizon * TRADING_TO_CALENDAR))


def _window_numbers(dates, train_start, win_days: int) -> np.ndarray:
    """每个日期的整数窗号 (date − train_start).days // win_days。"""
    days = (pd.to_datetime(pd.Series(dates)) - pd.Timestamp(train_start)).dt.days.to_numpy()
    return days // win_days


def time_window_codes(dates, train_start, win_days: int) -> tuple[np.ndarray, list[str]]:
    """把日期切成等宽时间窗,返回 (每行窗号字符串数组, 按序的窗号档位表)。

    窗号 = (date − train_start).days // win_days,字符串即整数本身(如 "0"、"12")。
    档位表列出数据里最小到最大窗号之间的全部窗(中间的空窗也列出),窗数由数据实际跨度决定;
    排序以档位表为准,不要按字符串排。
    """
    w = _window_numbers(dates, train_start, win_days)
    levels = [str(k) for k in range(int(w.min()), int(w.max()) + 1)] if len(w) else []
    return w.astype(str), levels


# ── 闸存在性层匹配差 ──

def layer_matched_diff(rows, keep, *, train_start, win_days: int, B: int = 300, seed: int = 0,
                       min_dir: int = 20) -> dict:
    """闸存在性层匹配差:保留臂相对池的首次穿越率差,扣掉两臂在「波动层 × 时间窗」构成上的差异。

    参数:
        rows: DataFrame[symbol, date, M, up, down, both] = 池(被判的闸放开、其余参数按目标配置的买点集合)。
              计数可以是 bar 级 0/1,也可以是买点事件级汇总;M = 买点 bar 的 ATR%(20)。
        keep: 与 rows 等长的 bool 数组,True = 保留臂(池里过这道闸的买点)。
        train_start: 训练窗起点,窗号的零点。
        win_days: 窗宽(日历天),由调用方用 time_window_days(label_horizon) 从运行口径推出。
        B, seed: 按股 multinomial bootstrap 的副本数与种子。
        min_dir: 层可用所需的池内定向 bar 下限。
    算法:
        定向 bar D = up + down + both。
        层 s = M 三分位 × 窗号:
            三分位切点 = 把池内每行按 D 展开后 M 的 1/3、2/3 分位(M ≤ q1 → 0,q1 < M ≤ q2 → 1,M > q2 → 2);
            窗号 = (date − train_start).days // win_days(同 time_window_codes);M 缺失的行不进任何层。
        可用层 = 池内定向 bar ≥ min_dir 的层。
        est = Σ_{s∈可用} w_s·(FP_s^保留 − FP_s^池),w_s = 保留臂定向 bar 在可用层内的占比
            = 保留臂可用层合并率 − Σ_s w_s·FP_s^池
        coverage = 保留臂定向 bar 落在可用层的比例;n_layers = 可用层数。
        raw_est = 保留臂合并率 − 池合并率(全部行,不分层)。
        误差:按股 multinomial bootstrap B 次,两臂共用同一组股票权重(保留臂是池的子集);
            se / raw_se = 副本估计的样本标准差(ddof=1)。可用层集合与切点固定取原样本。
            副本里保留臂在某层没有定向 bar 时该层权重为 0;池层定向 bar 为 0 时保留臂必然也为 0。
    返回 {"est", "se", "raw_est", "raw_se", "coverage", "n_layers"}。
    """
    keep = np.asarray(keep, dtype=bool)
    if len(keep) != len(rows):
        raise ValueError(f"keep 长度 {len(keep)} 与 rows 行数 {len(rows)} 不符")
    sym, syms = pd.factorize(rows["symbol"])
    S = len(syms)
    up = rows["up"].to_numpy(dtype=float)
    dirs = up + rows["down"].to_numpy(dtype=float) + rows["both"].to_numpy(dtype=float)
    M = rows["M"].to_numpy(dtype=float)

    okM = np.isfinite(M)
    expanded = np.repeat(M[okM], dirs[okM].astype(np.int64))
    tert = np.full(len(rows), -1, dtype=np.int64)
    if len(expanded):
        q1, q2 = np.quantile(expanded, [1 / 3, 2 / 3])
        tert[okM] = (M[okM] > q1).astype(np.int64) + (M[okM] > q2)
    win = _window_numbers(rows["date"], train_start, win_days)
    lay = np.full(len(rows), -1, dtype=np.int64)
    valid = tert >= 0
    lay[valid], uniq = pd.factorize(win[valid] * 3 + tert[valid])
    L = len(uniq)

    def by_stock_layer(v, mask):          # (S, L)
        m = mask & (lay >= 0)
        return np.bincount(sym[m] * L + lay[m], weights=v[m], minlength=S * L).reshape(S, L)

    def by_stock(v, mask):                # (S,)
        return np.bincount(sym[mask], weights=v[mask], minlength=S)

    every = np.ones(len(rows), dtype=bool)
    pU, pD = by_stock_layer(up, every), by_stock_layer(dirs, every)
    kU, kD = by_stock_layer(up, keep), by_stock_layer(dirs, keep)
    pU_t, pD_t = by_stock(up, every), by_stock(dirs, every)
    kU_t, kD_t = by_stock(up, keep), by_stock(dirs, keep)
    usable = pD.sum(axis=0) >= min_dir
    pU, pD, kU, kD = pU[:, usable], pD[:, usable], kU[:, usable], kD[:, usable]

    def estimate(W):                      # W (B', S) → est (B',), raw (B',)
        ku, kd, pu, pdn = W @ kU, W @ kD, W @ pU, W @ pD
        with np.errstate(divide="ignore", invalid="ignore"):
            fp_pool = np.where(pdn > 0, pu / pdn, 0.0)
            est = (ku.sum(axis=1) - (kd * fp_pool).sum(axis=1)) / kd.sum(axis=1)
            raw = (W @ kU_t) / (W @ kD_t) - (W @ pU_t) / (W @ pD_t)
        return est, raw

    est, raw = estimate(np.ones((1, S)))
    est_b, raw_b = estimate(_stock_weights(np.random.default_rng(seed), S, B))
    with np.errstate(divide="ignore", invalid="ignore"):
        coverage = float(kD.sum() / kD_t.sum())
    return {"est": float(est[0]), "se": float(np.std(est_b, ddof=1)),
            "raw_est": float(raw[0]), "raw_se": float(np.std(raw_b, ddof=1)),
            "coverage": coverage, "n_layers": int(usable.sum())}
