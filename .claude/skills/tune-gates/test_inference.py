# -*- coding: utf-8 -*-
"""inference 统计核单测(显式路径跑):uv run pytest .claude/skills/tune-gates/test_inference.py -q"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
from inference import (bh, cluster_wls, cochran_q, holm, layer_matched_diff, level_se,  # noqa: E402
                       maxT_from_sums, maxT_stepdown, power_normal, ratio_contrast, simes, time_window_codes,
                       time_window_days, z_bh_first)


# ── 多重比较 ──

def _bh_fdr_reference(pvals):
    """feature-study 统计电池里 BH 的原实现(逐字抄录,作逐位对照)。"""
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    order = np.argsort(p)
    q = np.empty(n)
    prev = 1.0
    for rank_from_last, idx in enumerate(order[::-1]):
        i = n - rank_from_last          # 1-based 名次(从大到小)
        prev = min(prev, p[idx] * n / i)
        q[idx] = prev
    return q.tolist()


# Benjamini & Hochberg (1995) 原文的 15 个 p 值
BH1995_P = [0.0001, 0.0004, 0.0019, 0.0095, 0.0201, 0.0278, 0.0298, 0.0344, 0.0459,
            0.3240, 0.4262, 0.5719, 0.6528, 0.7590, 1.0000]


def test_bh_textbook_example():
    """原文结论:q=0.05 下 BH 拒绝最小的 4 个(p ≤ 0.0095),Bonferroni 类只拒 3 个。

    手算:第 4 名 0.0095 ≤ 4·0.05/15 = 0.0133;第 5~9 名 0.0201/0.0278/0.0298/0.0344/0.0459
    分别高于门槛 0.0167/0.0200/0.0233/0.0267/0.0300;第 10 名起 p 远大于门槛。
    q_(4) = min_{j≥4} 15·p_(j)/j = min(0.035625, 0.0603, 0.0695, 0.06386, 0.0645, 0.0765, …) = 0.035625。
    """
    q = bh(BH1995_P)
    assert np.flatnonzero(q <= 0.05).tolist() == [0, 1, 2, 3]
    assert q[:4] == pytest.approx([0.0015, 0.003, 0.0095, 0.035625])
    assert q[-1] == 1.0
    # 同一例 Holm(FWER 0.05):15·0.0001、14·0.0004、13·0.0019 过,12·0.0095 = 0.114 不过
    assert np.flatnonzero(holm(BH1995_P) <= 0.05).tolist() == [0, 1, 2]


def test_bh_bitwise_matches_battery():
    rng = np.random.default_rng(7)
    cases = [BH1995_P,
             rng.uniform(size=50).tolist(),
             (rng.uniform(size=1000) ** 6).tolist(),
             (rng.integers(0, 20, size=40) / 20).tolist(),      # 大量并列
             [0.3, np.nan, 0.01, 0.2, np.nan, 0.01],
             [0.5], [0.0], []]
    for p in cases:
        assert bh(p).tolist() == _bh_fdr_reference(p)


def test_simes_hand():
    # 升序 0.01, 0.03, 0.04,m=3:3·0.01/1 = 0.03、3·0.03/2 = 0.045、3·0.04/3 = 0.04 → min = 0.03
    assert simes([0.04, 0.01, 0.03]) == pytest.approx(0.03)
    assert simes([0.2]) == pytest.approx(0.2)


def test_holm_hand():
    # 升序 0.005(#3)、0.01(#0)、0.03(#2)、0.04(#1),m=4:
    # (m−l+1)·p = 4·0.005 = 0.02、3·0.01 = 0.03、2·0.03 = 0.06、1·0.04 = 0.04 → 累积取大 0.02、0.03、0.06、0.06
    np.testing.assert_allclose(holm([0.01, 0.04, 0.03, 0.005]), [0.03, 0.06, 0.06, 0.02])
    # 截到 1:2·0.6 = 1.2 → 1,1·0.7 = 0.7 → 累积取大 1
    assert holm([0.6, 0.7]).tolist() == [1.0, 1.0]


def test_z_bh_first():
    assert round(z_bh_first(36, 0.10), 2) == 2.99          # bb_v1 标定例:筛选族大小 36、q 0.10
    assert z_bh_first(1, 0.05) == pytest.approx(stats.norm.ppf(0.975))


# ── 按股线性化比率误差 ──

def test_ratio_contrast_hand_three_stocks():
    """3 只股 + 1 只只在非涉及格出现的股,格 A、B、C,对比 A − B。

    格 A:s1 U2 D4 N5;s2 U3 D4 N4;s3 U0 D0 N1(只有 none)→ ΣU 5、ΣD 8、r_A = 0.625
    格 B:s1 U1 D4;s2 U1 D2;s3 U1 D2 → ΣU 3、ΣD 8、r_B = 0.375
    格 C:只有 s4,U0 D0 N3 → ΣD = 0、r_C = nan,系数 0 不涉及,不影响估计与簇数
    est = 0.625 − 0.375 = 0.25
    E_A = ((2−2.5)/8, (3−2.5)/8, 0) = (−0.0625, 0.0625, 0)
    E_B = ((1−1.5)/8, (1−0.75)/8, (1−0.75)/8) = (−0.0625, 0.03125, 0.03125)
    T = E_A − E_B = (0, 0.03125, −0.03125),ΣT² = 0.001953125
    n = 3(s4 只在格 C 有 N),SE = √(3/2·0.001953125) = √0.0029296875 ≈ 0.0541266
    """
    U = [[2, 1, 0], [3, 1, 0], [0, 1, 0], [0, 0, 0]]
    D = [[4, 4, 0], [4, 2, 0], [0, 2, 0], [0, 0, 0]]
    N = [[5, 4, 0], [4, 2, 0], [1, 2, 0], [0, 0, 3]]
    out = ratio_contrast(U, D, N, [1, -1, 0])
    assert out["est"] == pytest.approx(0.25)
    assert out["se"] == pytest.approx(np.sqrt(0.0029296875))
    assert out["z"] == pytest.approx(0.25 / np.sqrt(0.0029296875))
    assert out["n_clusters"] == 3
    assert out["r"][:2] == pytest.approx([0.625, 0.375]) and np.isnan(out["r"][2])
    assert out["n_dir"].tolist() == [8, 8, 0]


def test_level_se_hand():
    """格 A 单独:E = (−0.0625, 0.0625, 0),n = 3,SE² = 3/2·0.0078125 = 0.01171875;
    二项 SE² = 0.625·0.375/8 = 0.029296875 → deff = 0.4。"""
    out = level_se([2, 3, 0, 0], [4, 4, 0, 0], [5, 4, 1, 0])
    assert out["r"] == pytest.approx(0.625)
    assert out["se"] == pytest.approx(np.sqrt(0.01171875))
    assert out["deff"] == pytest.approx(0.4)
    assert (out["n_dir"], out["n_clusters"]) == (8, 3)


N_SYM, N_CELLS = 60, 5


def _detail(seed=0, n_rows=1500):
    """逐买点明细:每行一个买点事件,四态计数;股票 0~9 只出现在格 0。"""
    rng = np.random.default_rng(seed)
    d = pd.DataFrame({"symbol": rng.integers(0, N_SYM, n_rows), "cell": rng.integers(0, N_CELLS, n_rows),
                      "up": rng.integers(0, 4, n_rows), "down": rng.integers(0, 4, n_rows),
                      "both": rng.integers(0, 2, n_rows), "none": rng.integers(0, 3, n_rows)})
    d = d[d[["up", "down", "both", "none"]].sum(axis=1) > 0]
    d = d[~((d.symbol < 10) & (d.cell != 0))]
    return d.reset_index(drop=True)


def _direct(d, coef):
    """直白版:每个涉及格 groupby 股票求残差和,按股对齐(缺失记 0)后合成。"""
    est, parts = 0.0, []
    for cell, c in coef.items():
        g = d[d.cell == cell]
        dec = g.up + g.down + g.both
        r = g.up.sum() / dec.sum()
        est += c * r
        parts.append(c * ((g.up - r * dec) / dec.sum()).groupby(g.symbol).sum())
    tot = pd.concat(parts, axis=1).fillna(0).sum(axis=1)
    n = len(tot)
    return est, float(np.sqrt((tot ** 2).sum() * n / (n - 1))), n


def _stock_arrays(d):
    """明细 → (S, K) 每股计数和;额外补 5 只全零股(不应计入簇数)。"""
    S = N_SYM + 5
    idx = pd.MultiIndex.from_product([range(S), range(N_CELLS)])
    dec = d.up + d.down + d.both

    def piv(v):
        return v.groupby([d.symbol, d.cell]).sum().reindex(idx, fill_value=0).to_numpy(float).reshape(S, N_CELLS)
    return piv(d.up), piv(dec), piv(dec + d.none)


@pytest.mark.parametrize("coef", [{0: 1.0}, {1: 1.0, 2: -1.0}, {1: 1.0, 2: -1.0, 3: -1.0, 4: 1.0},
                                  {0: 0.5, 3: -2.0}])
def test_ratio_contrast_matches_direct(coef):
    d = _detail()
    U, D, N = _stock_arrays(d)
    c = np.zeros(N_CELLS)
    for k, v in coef.items():
        c[k] = v
    out = ratio_contrast(U, D, N, c)
    est, se, n = _direct(d, coef)
    assert abs(out["est"] - est) < 1e-12
    assert abs(out["se"] - se) < 1e-12
    assert out["n_clusters"] == n


def test_level_se_matches_direct():
    d = _detail(seed=1)
    U, D, N = _stock_arrays(d)
    out = level_se(U[:, 2], D[:, 2], N[:, 2])
    est, se, n = _direct(d, {2: 1.0})
    dec = D[:, 2].sum()
    assert abs(out["se"] - se) < 1e-12 and out["n_clusters"] == n
    assert out["deff"] == pytest.approx((se / np.sqrt(est * (1 - est) / dec)) ** 2, rel=1e-12)


# ── max-T ──

def test_maxT_stepdown_hand():
    """T_obs = (3, 1, 2),5 个副本。降序名次:检验 0(T=3)、检验 2(T=2)、检验 1(T=1)。

    名次 1:各副本三列取大 3.5/2.1/1.2/0.5/3.1,≥3 的 2 个 → p̃ = 0.4
    名次 2:列 {2, 1} 取大 1.1/2.1/1.2/0.5/1.3,≥2 的 1 个 → p̃ = 0.2 → 调整后 max(0.4, 0.2) = 0.4
    名次 3:列 {1} 为 1.1/0/1.2/0.5/1.3,≥1 的 3 个 → p̃ = 0.6 → 调整后 0.6
    """
    T_star = [[3.5, 1.1, 0.0], [0.0, 0.0, 2.1], [0.0, 1.2, 0.0], [0.0, 0.5, 0.0], [3.1, 1.3, 0.0]]
    np.testing.assert_allclose(maxT_stepdown([3.0, 1.0, 2.0], T_star), [0.4, 0.6, 0.4])


def test_maxT_independent_is_sidak():
    """m 个独立标准正态副本:最强检验的调整后 p ≈ Šidák 1 − (1 − p)^m。"""
    rng = np.random.default_rng(1)
    m, B = 5, 200_000
    T_obs = np.array([2.5, 0.3, -0.2, 0.1, 0.0])
    p = maxT_stepdown(T_obs, rng.standard_normal((B, m)))
    p1 = stats.norm.sf(2.5)
    assert p[0] == pytest.approx(1 - (1 - p1) ** m, rel=0.05)
    assert p[0] == p.min()


def test_maxT_perfectly_correlated_is_single_test():
    """m 列完全相同:max 就是单列,调整后 p ≈ 各自的单检验 p。"""
    rng = np.random.default_rng(2)
    B = 400_000
    T_obs = np.array([2.5, 1.5, 0.5])
    z = rng.standard_normal(B)
    p = maxT_stepdown(T_obs, np.repeat(z[:, None], 3, axis=1))
    np.testing.assert_allclose(p, stats.norm.sf(T_obs), rtol=0.1)


def _sums(seed=0, S=400, rates=(0.5, 0.5, 0.62)):
    rng = np.random.default_rng(seed)
    D = rng.integers(0, 12, size=(S, 3))
    U = rng.binomial(D, rates)
    return U.astype(float), D.astype(float)


def test_maxT_from_sums_formula_and_reproducible():
    U, D = _sums()
    S, B = U.shape[0], 300
    C = np.array([[1.0, -1.0, 0.0], [0.0, -1.0, 1.0], [-1.0, 0.0, 1.0]])
    margins = np.array([0.0, 0.0, 0.02])
    se = np.array([ratio_contrast(U, D, D, c)["se"] for c in C])
    out = maxT_from_sums(U, D, C, margins, se, B=B, seed=11)

    r = U.sum(axis=0) / D.sum(axis=0)
    np.testing.assert_allclose(out["est"], C @ r, rtol=1e-12)
    np.testing.assert_allclose(out["T"], (C @ r + margins) / se, rtol=1e-12)
    # 按定义重建零分布副本:w ~ Multinomial(S, 1/S),T* = (Σw·U/Σw·D 的对比 − est) / se
    W = np.random.default_rng(11).multinomial(S, np.full(S, 1.0 / S), size=B).astype(float)
    T_star = (((W @ U) / (W @ D)) @ C.T - out["est"]) / se
    np.testing.assert_array_equal(out["p_adj"], maxT_stepdown(out["T"], T_star))
    # 同种子可复现
    again = maxT_from_sums(U, D, C, margins, se, B=B, seed=11)
    np.testing.assert_array_equal(out["p_adj"], again["p_adj"])
    # 含 0.12 真实效应的两个对比显著,零效应对比不显著;调整后 p 随 T 降序单调
    assert out["p_adj"][1] < 0.01 and out["p_adj"][2] < 0.01 and out["p_adj"][0] > 0.05
    assert np.all(np.diff(out["p_adj"][np.argsort(-out["T"])]) >= 0)


def test_maxT_from_sums_ignores_uninvolved_empty_cell():
    U, D = _sums(seed=3)
    U = np.column_stack([U, np.zeros(len(U))])
    D = np.column_stack([D, np.zeros(len(D))])         # 格 3 没有任何定向 bar,但没有对比用到它
    C = np.array([[1.0, -1.0, 0.0, 0.0]])
    se = [ratio_contrast(U, D, D, C[0])["se"]]
    out = maxT_from_sums(U, D, C, [0.0], se, B=50, seed=0)
    assert np.isfinite(out["est"]).all() and np.isfinite(out["p_adj"]).all()


# ── 簇稳健加权回归 ──

def test_cluster_wls_tiny_hand():
    """y = (1, 2, 3, 4),只有截距,权重 1,簇 (a, a, b, b)。

    β = 2.5,e = (−1.5, −0.5, 0.5, 1.5);s_a = −2、s_b = 2 → Σ s² = 8;(XᵀWX)⁻¹ = 1/4;
    c = G/(G−1)·(n−1)/(n−k) = 2/1·3/3 = 2 → V = 2·(1/4)·8·(1/4) = 1 → SE = 1。
    """
    out = cluster_wls([1, 2, 3, 4], np.ones((4, 1)), np.ones(4), ["a", "a", "b", "b"])
    assert out["beta"] == pytest.approx([2.5])
    assert out["V"][0, 0] == pytest.approx(1.0)
    assert out["se"] == pytest.approx([1.0])
    assert (out["n"], out["G"], out["k"]) == (4, 2, 1)


def test_cluster_wls_matches_explicit_matrix():
    rng = np.random.default_rng(3)
    n = 12
    x = rng.normal(size=n)
    y = 1 + 2 * x + rng.normal(size=n)
    w = rng.uniform(0.5, 2.0, n)
    g = np.array(list("aaabbbbccddd"))
    X = np.column_stack([np.ones(n), x])
    out = cluster_wls(y, X, w, g)

    Wm = np.diag(w)
    A_inv = np.linalg.inv(X.T @ Wm @ X)
    beta = A_inv @ X.T @ Wm @ y
    e = y - X @ beta
    meat = np.zeros((2, 2))
    for lab in np.unique(g):
        s = X[g == lab].T @ (w[g == lab] * e[g == lab])
        meat += np.outer(s, s)
    G, k = 4, 2
    V = G / (G - 1) * (n - 1) / (n - k) * A_inv @ meat @ A_inv
    np.testing.assert_allclose(out["beta"], beta, rtol=1e-10)
    np.testing.assert_allclose(out["V"], V, rtol=1e-10)
    np.testing.assert_allclose(out["se"], np.sqrt(np.diag(V)), rtol=1e-10)
    assert (out["n"], out["G"], out["k"]) == (n, G, k)


# ── 异质性与功效 ──

def test_cochran_q_hand():
    """可用窗 (0.1, 0.1)、(0.3, 0.1)、(0.2, 0.2);第 4 窗 se = 0 剔除。
    权重 100、100、25 → ē = (10 + 30 + 5)/225 = 0.2;Q = 0.01·100 + 0.01·100 + 0 = 2;df 2;p = e⁻¹。"""
    out = cochran_q([0.1, 0.3, 0.2, 0.9], [0.1, 0.1, 0.2, 0.0])
    assert out["Q"] == pytest.approx(2.0)
    assert out["df"] == 2 and out["n_windows"] == 3
    assert out["p"] == pytest.approx(np.exp(-1))
    assert cochran_q([0.1, 0.2], [0.1, np.nan]) is None
    assert cochran_q([], []) is None


def test_power_normal():
    assert power_normal(0.0, 1.0) == pytest.approx(0.05)
    assert power_normal(stats.norm.ppf(0.95), 1.0) == pytest.approx(0.5)
    # 2.8·SE 在单侧 2.5%(双侧 5%)下约 80% 功效
    assert round(power_normal(2.8, 1.0, alpha=0.025), 2) == 0.80
    assert power_normal(0.056, 0.02, alpha=0.025) == pytest.approx(power_normal(2.8, 1.0, alpha=0.025))


# ── 闸存在性层匹配差 ──

WIN = 30          # 合成数据用的窗宽(日历天)


def test_time_window_days():
    assert time_window_days(40) == 58          # bb_v1 当前口径:标签前瞻期 40 交易日
    assert time_window_days(252) == 365
    assert time_window_days(20) == 29           # 20·365/252 = 28.97


def test_time_window_codes():
    """起点 2024-01-01、窗宽 30:天数 −1/0/28/29/90 → 窗号 −1/0/0/0/3;档位表含中间空窗 1、2。"""
    dates = pd.Series(pd.to_datetime(["2024-01-29", "2023-12-31", "2024-01-01", "2024-01-30", "2024-03-31"]),
                      index=list("abcde"))
    codes, levels = time_window_codes(dates, "2024-01-01", WIN)
    assert codes.tolist() == ["0", "-1", "0", "0", "3"]
    assert levels == ["-1", "0", "1", "2", "3"]
    codes, levels = time_window_codes(["2024-02-15", "2024-02-20"], pd.Timestamp("2024-01-01"), WIN)
    assert codes.tolist() == ["1", "1"] and levels == ["1"]


def _bars(M, date, n_up, n_non, keep_up, keep_non, start):
    """bar 级 0/1 行:n_up 个 up bar(前 keep_up 个进保留臂)+ n_non 个 down/both 交替(前 keep_non 个进保留臂)。"""
    out = []
    for i in range(n_up + n_non):
        is_up = i < n_up
        j = i if is_up else i - n_up
        kept = j < (keep_up if is_up else keep_non)
        out.append({"symbol": f"S{(start + i) % 10}", "date": date, "M": M, "up": int(is_up),
                    "down": int(not is_up and j % 2 == 0), "both": int(not is_up and j % 2 == 1), "keep": kept})
    return out


def _hand_pool():
    """同一窗(2024-01-10,窗 0)三个 M 值各 40 个定向 bar → 三分位切点落在 1 与 2、2 与 3 之间:
        层 M=1:池 up 20 / 40(0.5);保留臂 up 8 / 10(0.8)
        层 M=2:池 up 10 / 40(0.25);保留臂 up 9 / 30(0.3)
        层 M=3:池 up 30 / 40(0.75);保留臂无
    另有窗 2(2024-03-15,74 天 // 30 = 2)的 9 个 bar,M=1/2/3 各 3 个(不改变切点),up 共 5 个,全进保留臂;
    外加 2 行只有 none 的买点(定向 bar 0,不影响任何量)。
    """
    rows = (_bars(1.0, "2024-01-10", 20, 20, 8, 2, 0) + _bars(2.0, "2024-01-10", 10, 30, 9, 21, 3)
            + _bars(3.0, "2024-01-10", 30, 10, 0, 0, 7)
            + _bars(1.0, "2024-03-15", 2, 1, 2, 1, 1) + _bars(2.0, "2024-03-15", 2, 1, 2, 1, 4)
            + _bars(3.0, "2024-03-15", 1, 2, 1, 2, 6))
    rows += [{"symbol": "S0", "date": "2024-01-10", "M": 2.0, "up": 0, "down": 0, "both": 0, "keep": True}] * 2
    df = pd.DataFrame(rows)
    return df.drop(columns="keep"), df["keep"].to_numpy()


def test_layer_matched_hand():
    """min_dir = 20:窗 2 的三层池内各 3 个定向 bar,不可用。
    est = (10/40)·(0.8 − 0.5) + (30/40)·(0.3 − 0.25) = 0.075 + 0.0375 = 0.1125
    coverage = 保留臂可用层 40 / 保留臂全部 49
    raw = 保留臂 22/49 − 池 65/129
    min_dir = 3:窗 2 三层可用且保留臂 = 池(差 0),权重按 49 重归一:
    est = (10·0.3 + 30·0.05 + 9·0)/49 = 4.5/49,coverage = 1,6 层。
    """
    rows, keep = _hand_pool()
    out = layer_matched_diff(rows, keep, train_start="2024-01-01", win_days=WIN, B=50, seed=0)
    assert out["est"] == pytest.approx(0.1125)
    assert out["coverage"] == pytest.approx(40 / 49)
    assert out["raw_est"] == pytest.approx(22 / 49 - 65 / 129)
    assert out["n_layers"] == 3
    loose = layer_matched_diff(rows, keep, train_start="2024-01-01", win_days=WIN, B=50, seed=0, min_dir=3)
    assert loose["est"] == pytest.approx(4.5 / 49)
    assert loose["coverage"] == pytest.approx(1.0)
    assert loose["n_layers"] == 6
    assert loose["raw_est"] == out["raw_est"]
    # 窗宽放大到两批日期落进同一窗:两窗合并后每层池内 43 个定向 bar,全部可用
    merged = layer_matched_diff(rows, keep, train_start="2024-01-01", win_days=120, B=50, seed=0)
    assert merged["n_layers"] == 3 and merged["coverage"] == pytest.approx(1.0)


def test_layer_matched_requires_win_days():
    rows, keep = _hand_pool()
    with pytest.raises(TypeError):
        layer_matched_diff(rows, keep, train_start="2024-01-01")


def _random_pool(seed=0, n_sym=300, bars_per=40):
    """两年 bar 级数据:M 连续,up 概率随 M 升高(0.3 → 0.7),时间无关。"""
    rng = np.random.default_rng(seed)
    n = n_sym * bars_per
    M = rng.uniform(0, 3, n)
    u = rng.random(n)
    p_up = 0.3 + 0.4 * M / 3
    up = u < p_up
    rest = (u - p_up) / (1 - p_up)                   # 非 up 时在剩余概率里均匀
    down = ~up & (rest < 0.6)
    both = ~up & (rest >= 0.6) & (rest < 0.8)       # 其余是 none
    dates = pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 730, n), unit="D")
    return pd.DataFrame({"symbol": np.repeat(np.arange(n_sym), bars_per), "date": dates, "M": M,
                         "up": up.astype(int), "down": down.astype(int), "both": both.astype(int)})


def test_layer_matched_same_distribution_is_zero():
    rows = _random_pool()
    keep = np.random.default_rng(9).random(len(rows)) < 0.5
    out = layer_matched_diff(rows, keep, train_start="2024-01-01", win_days=WIN)
    assert out["se"] > 0 and out["raw_se"] > 0
    assert abs(out["est"]) < 3 * out["se"]
    assert abs(out["raw_est"]) < 3 * out["raw_se"]
    _, levels = time_window_codes(rows["date"], "2024-01-01", WIN)
    assert out["coverage"] == 1.0 and out["n_layers"] == 3 * len(levels)


def test_layer_matched_removes_composition():
    """保留臂 = 高 M 层全部 + 其余层随机 20%:层内是全体或随机子集,层匹配差 ≈ 0;原始差因构成偏向高 M 而明显为正。"""
    rows = _random_pool(seed=4)
    dirs = (rows.up + rows.down + rows.both).to_numpy()
    q2 = np.quantile(np.repeat(rows.M.to_numpy(), dirs), 2 / 3)
    keep = (rows.M.to_numpy() > q2) | (np.random.default_rng(5).random(len(rows)) < 0.2)
    out = layer_matched_diff(rows, keep, train_start="2024-01-01", win_days=WIN)
    assert abs(out["est"]) < 3 * out["se"]
    assert out["raw_est"] > 5 * out["raw_se"]


def test_layer_matched_reproducible():
    rows = _random_pool(seed=6, n_sym=80)
    keep = np.random.default_rng(1).random(len(rows)) < 0.6
    a = layer_matched_diff(rows, keep, train_start="2024-01-01", win_days=WIN, B=100, seed=3)
    b = layer_matched_diff(rows, keep, train_start="2024-01-01", win_days=WIN, B=100, seed=3)
    c = layer_matched_diff(rows, keep, train_start="2024-01-01", win_days=WIN, B=100, seed=4)
    assert a == b
    assert c["est"] == a["est"] and c["se"] != a["se"]
