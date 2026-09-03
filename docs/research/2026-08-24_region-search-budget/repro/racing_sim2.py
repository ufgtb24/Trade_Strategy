"""合成实验 2:按 integrator-skeptic 要求的真实密度两档重跑 racing。

与 racing_sim.py 的差异(全部来自实测事实):
- match 集中在少数股票上(命中股票占比 ACTIVE_FRAC,有效 cluster 数 ≪ 股票数);
- 维度分两类:nested(更严 ⊂ 更松,相邻格共享 80-95% match,如 gap_max/min_bos)与
  exclusive(相邻档 match 几乎不相交,如 stop_confirm_bars:每加一档 confirm 点后移、买点窗全换);
- 参照 = 全部 match(宽进底座),与格子分开算;
- 两档密度:wide(每格 ~5000 match、每 fold ~1200)/ tight(每格 ~150-250、每 fold ~40-65,
  低于功效线 100 → 功效线按 MIN_COUNT 参数化,tight 档用 30 才有格子可评估);
- fold 数两档:4(半年)/ 2(年);
- 两种淘汰判据:best(相对点估计最优格 −δ)/ level(相对水平线 −δ:P(score ≥ −δ) < α 淘汰,
  保留 CI 跨线的格子——这是「找区域」而非「找最优」的判据);
- 报告 10% / 25% / 50% 股票时的 (a) 假淘汰率 (b) 实际淘汰比例。

用法:uv run python docs/research/2026-08-24_region-search-budget/repro/racing_sim2.py
"""
from __future__ import annotations

import itertools
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from racing_sim import neighbor_lists  # noqa: E402


def gen_universe2(rng, *, n_stocks, active_frac, lam, sigma_u, L, dim_types, rhos,
                  base_fold, effect_fn):
    """返回 counts[S, C, F, 2] 与 ref_counts[S, F, 2](参照 = 全部 match)。"""
    n_folds = len(base_fold)
    D = len(dim_types)
    cells = list(itertools.product(range(L), repeat=D))
    cell_arr = np.array(cells)
    C = len(cells)
    active = rng.random(n_stocks) < active_frac
    n_match = np.where(active, rng.poisson(lam, size=n_stocks), 0)
    u = rng.normal(0.0, sigma_u, size=n_stocks)
    stock_of = np.repeat(np.arange(n_stocks), n_match)
    K = len(stock_of)
    folds = rng.integers(0, n_folds, size=K)
    U = rng.random((K, D))
    lev = np.minimum(L - 1, np.floor(np.log(U) / np.log(np.asarray(rhos)))).astype(int)
    # exclusive 维:档位均匀分布(每档约 1/L 的 match)
    for d, t in enumerate(dim_types):
        if t == "exclusive":
            lev[:, d] = rng.integers(0, L, size=K)
    bf = np.asarray(base_fold)[folds]
    logit = np.log(bf / (1 - bf)) + u[stock_of] + effect_fn(lev, folds)
    up = (rng.random(K) < 1 / (1 + np.exp(-logit))).astype(np.int32)
    member = np.ones((K, C), dtype=bool)
    for d, t in enumerate(dim_types):
        if t == "nested":
            member &= lev[:, d:d + 1] >= cell_arr[None, :, d]
        else:
            member &= lev[:, d:d + 1] == cell_arr[None, :, d]
    counts = np.zeros((n_stocks, C, n_folds, 2), dtype=np.int32)
    k_idx, c_idx = np.nonzero(member)
    np.add.at(counts, (stock_of[k_idx], c_idx, folds[k_idx], 1), 1)
    np.add.at(counts, (stock_of[k_idx], c_idx, folds[k_idx], 0), up[k_idx])
    ref = np.zeros((n_stocks, n_folds, 2), dtype=np.int32)
    np.add.at(ref, (stock_of, folds, 1), 1)
    np.add.at(ref, (stock_of, folds, 0), up)
    return counts, ref, cell_arr, K


def inc_and_scores(tot, ref_tot, nbrs, *, min_count, scale=1.0):
    """tot [B,C,F,2], ref_tot [B,F,2] → (inc [B,C,F](功效线不足处 NaN), score [B,C])。"""
    n = tot[..., 1].astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        fp = np.where(n > 0, tot[..., 0] / np.maximum(n, 1), np.nan)
        rfp = ref_tot[..., 0] / np.maximum(ref_tot[..., 1], 1)
    inc = fp - rfp[:, None, :]
    inc = np.where(n * scale >= min_count, inc, np.nan)
    foldmin = np.nanmin(np.where(np.isnan(inc), np.inf, inc), axis=2)
    foldmin = np.where(np.isnan(inc).any(axis=2), -np.inf, foldmin)
    B, C = foldmin.shape
    out = np.full((B, C), -np.inf)
    for c in range(C):
        out[:, c] = np.min(foldmin[:, nbrs[c]], axis=1)
    return inc, out


def scores2(tot, ref_tot, nbrs, *, min_count, scale=1.0):
    return inc_and_scores(tot, ref_tot, nbrs, min_count=min_count, scale=scale)[1]


def boot2(rng, counts_seen, ref_seen, nbrs, *, B, min_count, scale):
    S = counts_seen.shape[0]
    w = rng.multinomial(S, np.full(S, 1 / S), size=B).astype(float)
    tot = (w @ counts_seen.reshape(S, -1).astype(float)).reshape(B, *counts_seen.shape[1:])
    rt = (w @ ref_seen.reshape(S, -1).astype(float)).reshape(B, *ref_seen.shape[1:])
    return inc_and_scores(tot, rt, nbrs, min_count=min_count, scale=scale)


def racing_stage_stats(rng, counts, ref, nbrs, *, phis, B, delta, alpha, min_count, criterion):
    """逐阶段报告:该阶段淘汰后 (被淘汰比例, 假淘汰率)。假淘汰 = 被淘汰且属于 oracle 区域。
    oracle 区域:criterion=best → 全数据 score ≥ max − δ;criterion=level → 全数据 score ≥ −δ。"""
    S, C = counts.shape[:2]
    full = scores2(counts.sum(0)[None], ref.sum(0)[None], nbrs, min_count=min_count)[0]
    if criterion.startswith("best"):
        oracle = (full >= full.max() - delta) & np.isfinite(full)
    else:
        oracle = full >= -delta
    order = rng.permutation(S)
    active = np.ones(C, dtype=bool)
    rows = []
    for phi in phis:
        n_seen = int(round(phi * S))
        evaluated = np.zeros(C, dtype=bool)
        for c in np.flatnonzero(active):
            evaluated[nbrs[c]] = True
        seen = np.where(evaluated[None, :, None, None], counts[order[:n_seen]], 0)
        rseen = ref[order[:n_seen]]
        binc, bs = boot2(rng, seen, rseen, nbrs, B=B, min_count=min_count, scale=1 / phi)
        C_ = bs.shape[1]
        if criterion in ("best", "best_comp"):
            pt = scores2(seen.sum(0)[None], rseen.sum(0)[None], nbrs, min_count=min_count, scale=1 / phi)[0]
            pt = np.where(active, pt, -np.inf)
            c_hat = int(np.argmax(pt))
        if criterion == "best":
            # 整体 min 统计量的配对差(min 算子的向下偏置在两格间部分抵消)
            with np.errstate(invalid="ignore"):
                keep_prob = np.mean(bs - bs[:, c_hat:c_hat + 1] >= -delta, axis=0)
        elif criterion == "level":
            # 整体 min 统计量对水平线(min 算子向下偏置 → 子样本上系统性偏向淘汰,预期无效)
            keep_prob = np.mean(bs >= -delta, axis=0)
        else:
            # 分量式(componentwise):score_c ≤ inc_{n,f} 对所有 n∈N(c)∪{c}、f 成立,
            # 故只要任一分量确信低于线(或低于 ĉ 的 score − δ),score_c 就确信低——每个检验都是
            # 单个线性统计量,无 min 偏置;联合是并集 → 保守方向。
            keep_prob = np.ones(C_)
            for c in range(C_):
                comp = binc[:, nbrs[c], :]                          # [B, |N|, F]
                comp = np.where(np.isnan(comp), np.inf, comp)       # 功效不足的分量不参与淘汰
                if criterion == "level_comp":
                    ok = comp >= -delta
                else:                                               # best_comp
                    ok = comp >= bs[:, c_hat][:, None, None] - delta
                keep_prob[c] = np.min(np.mean(ok, axis=0))          # 最弱分量的保留概率
        newly = active & (keep_prob < alpha)
        active &= ~newly
        elim = ~active
        false_elim = (elim & oracle).sum() / oracle.sum() if oracle.sum() > 0 else np.nan
        rows.append((phi, elim.mean(), false_elim))
    return rows, oracle.sum(), np.isfinite(full).sum(), full.max()


def make_effect2(kind, beta):
    if kind == "strong":     # 维 0(exclusive, scb 式)档 1-3 甜点(宽 3 档:r=1 邻域最小在互斥维上要求 edge 跨 3 档才有正格);维 1(nested)≥1 时平台
        return lambda lev, f: 2 * beta * (np.isin(lev[:, 0], (1, 2, 3)) & (lev[:, 1] >= 1))
    if kind == "mostlybad":  # 维 0 档 1-3 有 edge,维 2 收紧有害
        return lambda lev, f: beta * np.isin(lev[:, 0], (1, 2, 3)) - beta * (lev[:, 2] >= 2)
    if kind == "spike1":     # 维 0 只有档 2 一档甜点(宽 1 档):r=1 邻域最小应把它判为非稳健区
        return lambda lev, f: 2 * beta * ((lev[:, 0] == 2) & (lev[:, 1] >= 1))
    if kind == "null":
        return lambda lev, f: np.zeros(len(f))
    raise ValueError(kind)


def main():
    N_STOCKS = 6000
    L = 4
    DIM_TYPES = ["exclusive", "nested", "nested"]      # scb 式 / gap_max 式 / min_bos 式
    RHOS = [0.5, 0.85, 0.8]                              # exclusive 维的 ρ 不用
    SIGMA_U = 0.5
    BETA = 0.30
    B = 300
    DELTA, ALPHA = 0.01, 0.02
    PHIS = [0.10, 0.25, 0.50]
    N_SEEDS = 15
    # 密度两档:(active_frac, lam) → 全部 match 数;exclusive 维每档 1/4,nested 维档 0 全包
    REGIMES = {"wide(参照~5000, 格~1200/4档)": (0.10, 8.3, 100),
               "tight(参照~220, 格~55)":        (0.03, 1.2, 30)}
    FOLDS = {"半年4折": [0.46, 0.49, 0.55, 0.58], "年2折": [0.475, 0.565]}
    SCEN = ["strong", "spike1", "mostlybad", "null"]
    print(f"stocks={N_STOCKS} dims={DIM_TYPES} δ={DELTA} α={ALPHA} B={B} seeds={N_SEEDS}")
    for rname, (af, lam, min_count) in REGIMES.items():
        for fname, base_fold in FOLDS.items():
            for scen in SCEN:
                t0 = time.time()
                CRITS = ("best", "best_comp", "level", "level_comp")
                acc = {crit: {phi: [] for phi in PHIS} for crit in CRITS}
                meta = {"K": [], "oracle_best": [], "oracle_level": [], "evaluable": [], "max": []}
                for seed in range(N_SEEDS):
                    rng = np.random.default_rng(seed)
                    counts, ref, cell_arr, K = gen_universe2(
                        rng, n_stocks=N_STOCKS, active_frac=af, lam=lam, sigma_u=SIGMA_U, L=L,
                        dim_types=DIM_TYPES, rhos=RHOS, base_fold=base_fold,
                        effect_fn=make_effect2(scen, BETA))
                    nbrs = neighbor_lists(cell_arr, L)
                    meta["K"].append(K)
                    for crit in CRITS:
                        rows, n_or, n_ev, mx = racing_stage_stats(
                            rng, counts, ref, nbrs, phis=PHIS, B=B, delta=DELTA, alpha=ALPHA,
                            min_count=min_count, criterion=crit)
                        for phi, elim, fe in rows:
                            acc[crit][phi].append((elim, fe))
                        meta.setdefault(f"oracle_{crit}", []).append(n_or)
                    meta["evaluable"].append(n_ev); meta["max"].append(mx)
                C = len(cell_arr)
                print(f"-- {rname} | {fname} | {scen} | 全部 match {np.mean(meta['K']):.0f} | "
                      f"可评估格 {np.mean(meta['evaluable']):.1f}/{C} | oracle max {np.mean(meta['max']):+.4f} | "
                      f"区域格数 best {np.mean(meta['oracle_best']):.1f} / level {np.mean(meta['oracle_level']):.1f} | "
                      f"功效线 {min_count} | {time.time()-t0:.0f}s")
                for crit in CRITS:
                    cells = "  ".join(f"φ={phi:.2f}: 淘汰 {np.mean([e for e, _ in acc[crit][phi]]):.2f} "
                                      f"假淘汰 {np.nanmean([f for _, f in acc[crit][phi]]) if not np.all(np.isnan([f for _, f in acc[crit][phi]])) else float('nan'):.3f}"
                                      for phi in PHIS)
                    print(f"   {crit:10s} | {cells}")


if __name__ == "__main__":
    main()
