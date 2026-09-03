"""合成实验:以「股票」为数据流的 racing 在配对噪声下的淘汰正确率与预算节省。

模拟对象与真实流水线的对应关系:
- 股票 s 有 n_s ~ Poisson(λ) 个 match(全宇宙 ~6000 股 → ~5500 match,对齐 bb_v1 250 底座);
  股票级随机效应 u_s 制造簇内相关(按股 cluster bootstrap 才有意义)。
- D 个阈值型维度、每维 L 档;match 的档位向量 ℓ_m 服从几何分布(越严越稀);
  格子 c 包含 match ⟺ ℓ_m ≥ c(逐维)。格子 (0,…,0) = 参照(宽进底座 / bo_only)。
  这正是「更严档 ⊂ 更松档」的嵌套结构:相邻格子共享绝大部分 match(配对结构)。
- 结果二态 up/down:P(up|m) = σ(logit(base_fold) + u_s + effect(ℓ_m))。
  effect 决定真实稳健区形态(平台 / 严端崩塌 / 零效应)。
- 目标函数(lead 审视报告 §五):每格 = r=1 邻域最小 × fold 最小 × 相对参照的 FP 增量;
  fold count < MIN_COUNT → 不可评估(fail)。
- oracle = 全网格 × 全宇宙(即全因子逐点全宇宙 scan 会给出的结果);
  racing 的目标是以更少 (格子,股票) 评估复现 oracle 的决策(argmax 与 δ-区域)。

racing 规则(successive-halving 骨架 + 按股 cluster bootstrap 配对淘汰):
- 股票随机排序,分阶段累计比例 PHIS;
- 活跃集 A 初始 = 全部格子;每阶段被评估的格子 E = A ∪ N(A)(幸存者的 r=1 邻域必须
  同步评估,否则邻域最小算不出来);
- 每阶段用已见股票做 B 次 cluster bootstrap,算每格 score 与 max_A score 的配对差,
  P(score_c ≥ max − DELTA) < ALPHA → 淘汰;功效线按投影 count(count/φ)判定。
- 终态:幸存者全宇宙精确;推荐 = 幸存者中 score 最大;区域 = 幸存者中 score ≥ max − DELTA。

对照:方法 6(非自适应子样本代理):20% 股票粗定位 → 点估计 score ≥ max − DELTA6 的
格子全宇宙评估。

输出:每场景 × 每维数的 (预算比例, argmax 一致率, oracle 区域被误淘汰率, 配对/独立方差比)。
用法:uv run python docs/research/2026-08-24_region-search-budget/repro/racing_sim.py
"""
from __future__ import annotations

import itertools
import time

import numpy as np


# ----------------------------------------------------------------------------
# 宇宙生成
# ----------------------------------------------------------------------------
def gen_universe(rng, *, n_stocks, lam, sigma_u, D, L, rhos, base_fold, effect_fn):
    """返回 counts[S, C, F, 2](up, total) 与格子索引表。全向量化:一次生成全部 match。"""
    n_folds = len(base_fold)
    cells = list(itertools.product(range(L), repeat=D))
    C = len(cells)
    cell_arr = np.array(cells)                                 # [C, D]
    n_match = rng.poisson(lam, size=n_stocks)
    u = rng.normal(0.0, sigma_u, size=n_stocks)
    stock_of = np.repeat(np.arange(n_stocks), n_match)         # [K]
    K = len(stock_of)
    folds = rng.integers(0, n_folds, size=K)
    U = rng.random((K, D))
    lev = np.minimum(L - 1, np.floor(np.log(U) / np.log(np.asarray(rhos)))).astype(int)  # [K, D]
    bf = np.asarray(base_fold)[folds]
    logit = np.log(bf / (1 - bf)) + u[stock_of] + effect_fn(lev, folds)
    up = (rng.random(K) < 1 / (1 + np.exp(-logit))).astype(np.int32)
    member = np.all(lev[:, None, :] >= cell_arr[None, :, :], axis=2)   # [K, C]
    counts = np.zeros((n_stocks, C, n_folds, 2), dtype=np.int32)
    k_idx, c_idx = np.nonzero(member)
    np.add.at(counts, (stock_of[k_idx], c_idx, folds[k_idx], 1), 1)
    np.add.at(counts, (stock_of[k_idx], c_idx, folds[k_idx], 0), up[k_idx])
    return counts, cell_arr


def neighbor_lists(cell_arr, L):
    """r=1 邻域(含自身),盒外不计(机制边界不计边界)。"""
    idx = {tuple(c): i for i, c in enumerate(cell_arr)}
    nbrs = []
    for c in cell_arr:
        lst = [idx[tuple(c)]]
        for d in range(len(c)):
            for delta in (-1, 1):
                cc = c.copy(); cc[d] += delta
                if 0 <= cc[d] < L:
                    lst.append(idx[tuple(cc)])
        nbrs.append(lst)
    return nbrs


# ----------------------------------------------------------------------------
# 目标函数(向量化,支持 bootstrap 批)
# ----------------------------------------------------------------------------
def scores_from_counts(tot, nbrs, *, ref, min_count, scale=1.0, active=None):
    """tot: [B, C, F, 2] → score [B, C]。
    scale: 投影系数(部分股票时 count/φ 估全宇宙 count,用于功效线)。
    active: 布尔 [C],None 表示全部;非活跃格子的 foldmin 仍参与邻域(若其被评估)。
    """
    up = tot[..., 0].astype(float)
    n = tot[..., 1].astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        fp = np.where(n > 0, up / np.maximum(n, 1), np.nan)
    inc = fp - fp[:, ref:ref + 1, :]
    inc = np.where(n * scale >= min_count, inc, np.nan)
    foldmin = np.nanmin(np.where(np.isnan(inc), np.inf, inc), axis=2)   # [B, C]
    anynan = np.isnan(inc).any(axis=2)
    foldmin = np.where(anynan, -np.inf, foldmin)
    B, C = foldmin.shape
    out = np.full((B, C), -np.inf)
    for c in range(C):
        out[:, c] = np.min(foldmin[:, nbrs[c]], axis=1)
    return out


def bootstrap_scores(rng, counts_seen, nbrs, *, B, ref, min_count, scale):
    """按股 cluster bootstrap:重抽已见股票 → 每格 score 的 B 个副本。"""
    S = counts_seen.shape[0]
    w = rng.multinomial(S, np.full(S, 1 / S), size=B).astype(float)     # [B, S]
    flat = counts_seen.reshape(S, -1).astype(float)
    tot = (w @ flat).reshape(B, *counts_seen.shape[1:])
    return scores_from_counts(tot, nbrs, ref=ref, min_count=min_count, scale=scale)


# ----------------------------------------------------------------------------
# racing
# ----------------------------------------------------------------------------
def run_racing(rng, counts, nbrs, *, phis, B, delta, alpha, ref, min_count, criterion="best"):
    S, C = counts.shape[:2]
    order = rng.permutation(S)
    active = np.ones(C, dtype=bool)
    cost = 0.0
    prev = 0
    log = []
    futile = False
    for phi in phis:
        n_seen = int(round(phi * S))
        # 被评估集 = 活跃 ∪ 活跃的邻域
        evaluated = np.zeros(C, dtype=bool)
        for c in np.flatnonzero(active):
            evaluated[nbrs[c]] = True
        cost += evaluated.sum() * (n_seen - prev)
        prev = n_seen
        if phi >= 1.0:
            break
        seen = counts[order[:n_seen]]
        # 未评估格子的数据不可用 → 置 0(它们不在任何活跃格子的邻域里,不影响活跃格子 score)
        seen = np.where(evaluated[None, :, None, None], seen, 0)
        bs = bootstrap_scores(rng, seen, nbrs, B=B, ref=ref, min_count=min_count, scale=1 / phi)
        # 配对判据:以「已见数据上点估计最优格 ĉ」为固定锚,看每格与 ĉ 的配对差分布。
        # (不能与每个副本内的 max 比——max 被选择效应抬高,会把真最优也淘汰掉。)
        pt = scores_from_counts(seen.sum(axis=0)[None], nbrs, ref=ref, min_count=min_count,
                                scale=1 / phi)[0]
        pt = np.where(active, pt, -np.inf)
        c_hat = int(np.argmax(pt))
        with np.errstate(invalid="ignore"):
            diff = bs - bs[:, c_hat:c_hat + 1]                              # [B, C]
        keep_prob = np.mean(diff >= -delta, axis=0)                         # [C]
        newly = active & (keep_prob < alpha)
        if criterion == "best_or_zero":
            # 相对参照增量明显 < 0 的格子:不可能属于任何「有增量」的区域,直接淘汰
            zero_prob = np.mean(bs >= -delta, axis=0)
            newly |= active & (zero_prob < alpha)
        if criterion == "best_futility":
            # 全局无效性早停:所有活跃格子的 P(score ≥ −δ) 都 < α → 整体停止,判「无增量区域」
            zero_prob = np.where(active, np.mean(bs >= -delta, axis=0), 0.0)
            if zero_prob.max() < alpha:
                futile = True
                active[:] = False
                log.append((phi, int(evaluated.sum()), 0, "FUTILE"))
                break
        active &= ~newly
        log.append((phi, int(evaluated.sum()), int(active.sum())))
    # 终态:幸存者(及其邻域)全宇宙精确
    full = scores_from_counts(counts.sum(axis=0)[None], nbrs, ref=ref, min_count=min_count)[0]
    final = np.where(active, full, -np.inf)
    return {"cost_frac": cost / (C * S), "active": active, "final": final, "log": log,
            "futile": futile}


def flat_dims(rng, counts_seen, cell_arr, L, *, B, eps, scale, min_count, n_pair_min=600):
    """维度等价检验(TOST 思想),两层:
    (a) 汇总对比:沿维 d 所有相邻档位对的 FP 配对差按 count 加权平均,按股 bootstrap 95% CI ⊂ [-eps, eps];
    (b) 逐对:已见样本中两格实际 count 都 ≥ n_pair_min 的相邻对,各自 95% CI ⊂ [-2eps, 2eps]。
    两层都过 → 该维「平坦」。返回布尔 [D]。"""
    S, C = counts_seen.shape[:2]
    D = cell_arr.shape[1]
    w = rng.multinomial(S, np.full(S, 1 / S), size=B).astype(float)
    tot = (w @ counts_seen.sum(axis=2).reshape(S, -1).astype(float)).reshape(B, C, 2)
    n_act = counts_seen.sum(axis=(0, 2))[:, 1]
    fp = tot[..., 0] / np.maximum(tot[..., 1], 1)
    idx = {tuple(c): i for i, c in enumerate(cell_arr)}
    out = np.zeros(D, dtype=bool)
    for d in range(D):
        pairs = []
        for i, c in enumerate(cell_arr):
            if c[d] >= L - 1:
                continue
            cc = c.copy(); cc[d] += 1
            j = idx[tuple(cc)]
            if n_act[i] * scale < min_count or n_act[j] * scale < min_count:
                continue
            pairs.append((i, j))
        if not pairs:
            continue
        ii = np.array([p[0] for p in pairs]); jj = np.array([p[1] for p in pairs])
        wts = np.minimum(n_act[ii], n_act[jj]).astype(float)
        pooled = ((fp[:, jj] - fp[:, ii]) * wts).sum(axis=1) / wts.sum()
        lo, hi = np.percentile(pooled, [2.5, 97.5])
        ok = (lo >= -eps) and (hi <= eps)
        if ok:
            for i, j in pairs:
                if n_act[i] >= n_pair_min and n_act[j] >= n_pair_min:
                    l2, h2 = np.percentile(fp[:, j] - fp[:, i], [2.5, 97.5])
                    if l2 < -2 * eps or h2 > 2 * eps:
                        ok = False; break
        out[d] = ok
    return out


def run_subsample_proxy(rng, counts, nbrs, *, phi, delta6, ref, min_count):
    """方法 6:非自适应子样本代理。"""
    S, C = counts.shape[:2]
    order = rng.permutation(S)
    n_seen = int(round(phi * S))
    seen = counts[order[:n_seen]].sum(axis=0)[None]
    sc = scores_from_counts(seen, nbrs, ref=ref, min_count=min_count, scale=1 / phi)[0]
    keep = sc >= sc.max() - delta6
    # 候选及其邻域全宇宙
    evaluated = np.zeros(C, dtype=bool)
    for c in np.flatnonzero(keep):
        evaluated[nbrs[c]] = True
    cost = C * n_seen + evaluated.sum() * (S - n_seen)
    full = scores_from_counts(counts.sum(axis=0)[None], nbrs, ref=ref, min_count=min_count)[0]
    final = np.where(keep, full, -np.inf)
    return {"cost_frac": cost / (C * S), "active": keep, "final": final}


def paired_vs_independent_var(rng, counts, nbrs, *, B, ref, min_count):
    """相邻格子 FP 差的按股 bootstrap 方差 vs 独立假设下方差之和(仅 fold 合并、不做邻域)。"""
    S, C = counts.shape[:2]
    w = rng.multinomial(S, np.full(S, 1 / S), size=B).astype(float)
    tot = (w @ counts.sum(axis=2).reshape(S, -1).astype(float)).reshape(B, C, 2)
    fp = tot[..., 0] / np.maximum(tot[..., 1], 1)
    ratios = []
    for c in range(C):
        for nb in nbrs[c][1:]:
            if nb < c:
                continue
            var_pair = np.var(fp[:, c] - fp[:, nb])
            var_ind = np.var(fp[:, c]) + np.var(fp[:, nb])
            if var_ind > 0:
                ratios.append(var_pair / var_ind)
    return float(np.median(ratios)), float(np.max(ratios))


# ----------------------------------------------------------------------------
# 场景
# ----------------------------------------------------------------------------
def make_effect(kind, beta):
    """effect(lev[k,D], folds[k]) → logit 增量。"""
    if kind == "plateau":        # 维 0 ≥2 且维 1 ≥1 时有 edge(平台区),各 fold 一致
        return lambda lev, folds: beta * ((lev[:, 0] >= 2) & (lev[:, 1] >= 1))
    if kind == "collapse":       # 维 0 =2 是甜点,=3 反而崩塌(严端崩塌,非单调)
        return lambda lev, folds: beta * (lev[:, 0] >= 2) - 2.0 * beta * (lev[:, 0] >= 3)
    if kind == "strong":         # 平台区、强 edge(logit +2β ≈ +14pt)
        return lambda lev, folds: 2 * beta * ((lev[:, 0] >= 2) & (lev[:, 1] >= 1))
    if kind == "mostlybad":      # bb_v1 式:多数收紧降 FP,仅维 0 有 edge,其余维平坦或有害
        return lambda lev, folds: beta * (lev[:, 0] >= 2) - beta * (lev[:, 1] >= 2)
    if kind == "null":           # 无任何结构
        return lambda lev, folds: np.zeros(len(folds))
    if kind == "weakfold":       # 平台区 edge 只在 3/4 个 fold 存在(fold 0 无 edge)
        return lambda lev, folds: beta * ((lev[:, 0] >= 2) & (lev[:, 1] >= 1)) * (folds != 0)
    raise ValueError(kind)


def main():
    # ---- 参数(对齐 bb_v1 量级) ----
    N_STOCKS = 6000
    LAM = 0.92                   # 每股 match 数 Poisson 均值 → 全宇宙 ~5500 match
    SIGMA_U = 0.5                # 股票级随机效应(logit)
    L = 4                        # 每维档位
    RHOS_BY_D = {2: [0.8, 0.75], 3: [0.8, 0.75, 0.85], 4: [0.8, 0.75, 0.85, 0.8]}   # P(ℓ≥k)=ρ^k
    BASE_FOLD = [0.46, 0.49, 0.55, 0.58]                  # 4 个半年 fold 的基率(弱年/强年)
    BETA = 0.30                  # logit 增量 ≈ +7pt FP
    MIN_COUNT = 100
    PHIS = [0.10, 0.20, 0.35, 0.55, 0.80, 1.0]
    B = 300
    CONFIGS = [("best", 0.01, 0.02), ("best", 0.02, 0.05), ("best_futility", 0.01, 0.02)]
    PHI6, DELTA6 = 0.20, 0.03    # 方法 6 参数
    FLAT_EPS = 0.02              # 维度等价检验容差
    FLAT_PHIS = [0.10, 0.20, 0.35]
    N_SEEDS = 20
    SCENARIOS = ["strong", "plateau", "mostlybad", "collapse", "null"]
    DIMS = [3, 4]

    print(f"stocks={N_STOCKS} lam={LAM} folds={len(BASE_FOLD)} L={L} phis={PHIS} B={B} seeds={N_SEEDS}")
    print("== racing 配置对比(每格:cost=预算比例 / agree=argmax 与 oracle 一致率 / lost=oracle δ-区域被误淘汰比例 / surv=幸存格比例)==")
    for D in DIMS:
        for scen in SCENARIOS:
            t0 = time.time()
            acc = {cfg: {"cost": [], "agree": [], "lost": [], "surv": [], "futile": []} for cfg in CONFIGS}
            p_acc = {"cost": [], "agree": [], "lost": []}
            flat_acc = {phi: [] for phi in FLAT_PHIS}
            vr = []
            regsz, evaluable, omax = [], [], []
            for seed in range(N_SEEDS):
                rng = np.random.default_rng(seed)
                counts, cell_arr = gen_universe(
                    rng, n_stocks=N_STOCKS, lam=LAM, sigma_u=SIGMA_U, D=D, L=L,
                    rhos=RHOS_BY_D[D], base_fold=BASE_FOLD, effect_fn=make_effect(scen, BETA))
                nbrs = neighbor_lists(cell_arr, L)
                C = len(cell_arr)
                full = scores_from_counts(counts.sum(axis=0)[None], nbrs, ref=0, min_count=MIN_COUNT)[0]
                oracle_arg = int(np.argmax(full))
                for crit, delta, alpha in CONFIGS:
                    oracle_region = full >= full.max() - delta
                    res = run_racing(rng, counts, nbrs, phis=PHIS, B=B, delta=delta, alpha=alpha,
                                     ref=0, min_count=MIN_COUNT, criterion=crit)
                    a = acc[(crit, delta, alpha)]
                    a["cost"].append(res["cost_frac"])
                    a["agree"].append(int(np.argmax(res["final"])) == oracle_arg)
                    a["lost"].append(1 - np.mean(res["active"][oracle_region]))
                    a["surv"].append(res["active"].sum() / C)
                    a["futile"].append(res["futile"])
                oracle_region = full >= full.max() - 0.01
                regsz.append(oracle_region.sum()); evaluable.append(np.isfinite(full).sum()); omax.append(full.max())
                res6 = run_subsample_proxy(rng, counts, nbrs, phi=PHI6, delta6=DELTA6,
                                           ref=0, min_count=MIN_COUNT)
                p_acc["cost"].append(res6["cost_frac"])
                p_acc["agree"].append(int(np.argmax(res6["final"])) == oracle_arg)
                p_acc["lost"].append(1 - np.mean(res6["active"][oracle_region]))
                order = rng.permutation(N_STOCKS)
                for phi in FLAT_PHIS:
                    seen = counts[order[:int(phi * N_STOCKS)]]
                    flat_acc[phi].append(flat_dims(rng, seen, cell_arr, L, B=B, eps=FLAT_EPS,
                                                   scale=1 / phi, min_count=MIN_COUNT))
                if seed < 5:
                    vr.append(paired_vs_independent_var(rng, counts, nbrs, B=B, ref=0, min_count=MIN_COUNT)[0])
            print(f"-- {scen} D={D} cells={C} | oracle max score {np.mean(omax):+.4f} | oracle δ=0.01 区域格数 {np.mean(regsz):.1f} / 可评估 {np.mean(evaluable):.1f} | "
                  f"配对/独立方差比 {np.mean(vr):.3f} | {time.time()-t0:.0f}s")
            for cfg in CONFIGS:
                a = acc[cfg]
                print(f"   racing {cfg[0]:13s} δ={cfg[1]:.2f} α={cfg[2]:.2f}: cost {np.mean(a['cost']):.3f}  "
                      f"agree {np.mean(a['agree']):.2f}  lost {np.mean(a['lost']):.3f}  surv {np.mean(a['surv']):.2f}"
                      f"  futile {np.mean(a['futile']):.2f}")
            print(f"   proxy20 δ6={DELTA6}: cost {np.mean(p_acc['cost']):.3f}  agree {np.mean(p_acc['agree']):.2f}  lost {np.mean(p_acc['lost']):.3f}")
            for phi in FLAT_PHIS:
                fa = np.array(flat_acc[phi])         # [seeds, D]
                print(f"   flat-dim@{phi:.2f}: 各维判平坦率 {np.round(fa.mean(axis=0), 2).tolist()}")


if __name__ == "__main__":
    main()
