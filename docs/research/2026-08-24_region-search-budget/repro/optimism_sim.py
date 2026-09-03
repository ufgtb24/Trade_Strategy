"""选择后校正(bootstrap optimism)量级校准——在 racing_sim2 的合成数据上(integrator-final 补 lead 第 3 条)。

问题:全网格便宜后,从 C 个格子里挑「r=1 邻域最小 × fold 最小 增量」最高者,其增量估计被选择效应抬高多少?
      bootstrap optimism(每副本重选 argmax、回原数据看其增量,取均值)能不能把它校正回来?
做法:每个 seed 生成两个独立宇宙 A(选格)与 A'(同参数、独立 seed,作 out-of-sample 真值):
      naive = score_A(ĉ_A);oos = score_A'(ĉ_A)(ĉ_A 在独立数据上的真实增量);
      optimism = mean_b[ score_b(ĉ_b) − score_A(ĉ_b) ];corrected = naive − optimism;
      split-half 交叉:奇数股选格 / 偶数股评估,互换取平均(无偏但功效减半)。
场景:wide 密度、年 2 折、strong / mostlybad / null;B=200;15 seed。
用法:uv run python docs/research/2026-08-24_region-search-budget/repro/optimism_sim.py
"""
from __future__ import annotations
import sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from racing_sim import neighbor_lists           # noqa: E402
from racing_sim2 import gen_universe2, boot2, scores2, make_effect2   # noqa: E402


def main():
    N_STOCKS, L, DIM_TYPES, RHOS, SIGMA_U, BETA = 6000, 4, ["exclusive", "nested", "nested"], [0.5, 0.85, 0.8], 0.5, 0.30
    B, N_SEEDS, MIN_COUNT = 200, 15, 100
    ACTIVE_FRAC, LAM = 0.10, 8.3                 # wide 密度(参照 ~5000 match)
    BASE_FOLD = [0.475, 0.565]                   # 年 2 折
    SCEN = ["strong", "mostlybad", "null"]
    print(f"stocks={N_STOCKS} wide 年2折 B={B} seeds={N_SEEDS} 功效线={MIN_COUNT}")
    for scen in SCEN:
        t0 = time.time(); rows = []
        for seed in range(N_SEEDS):
            eff = make_effect2(scen, BETA)
            gen = lambda s: gen_universe2(np.random.default_rng(s), n_stocks=N_STOCKS, active_frac=ACTIVE_FRAC, lam=LAM,
                                          sigma_u=SIGMA_U, L=L, dim_types=DIM_TYPES, rhos=RHOS, base_fold=BASE_FOLD, effect_fn=eff)
            counts, ref, cell_arr, _ = gen(seed)
            counts2, ref2, _, _ = gen(10_000 + seed)          # 独立宇宙 A'
            nbrs = neighbor_lists(cell_arr, L)
            sc = lambda cn, rf: scores2(cn.sum(0)[None], rf.sum(0)[None], nbrs, min_count=MIN_COUNT)[0]
            full = sc(counts, ref); c_hat = int(np.argmax(full)); naive = full[c_hat]
            oos = sc(counts2, ref2)[c_hat]
            true_max = sc(counts2, ref2).max()                  # 独立宇宙自己的最优(参考:选中格离真最优多远)
            rng = np.random.default_rng(seed)
            _, bs = boot2(rng, counts, ref, nbrs, B=B, min_count=MIN_COUNT, scale=1.0)
            # 副本内只在原数据可评估的格子里重选(原数据不可评估的格在副本里偶尔越线、其 score_orig 为 -inf)
            bs_m = np.where(np.isfinite(full)[None, :], bs, -np.inf)
            ok = np.isfinite(bs_m).any(axis=1)                 # 极少数副本全部格子不可评估(某格某 fold 重采样后跌破功效线且传染邻域),剔除
            bs_m, bsn = bs_m[ok], int(ok.sum())
            cb = np.argmax(bs_m, axis=1)
            optimism = np.mean(bs_m[np.arange(bsn), cb] - full[cb])
            corrected = naive - optimism
            v = bs[:, c_hat]; v = v[np.isfinite(v)]
            ci = np.percentile(v - optimism, [2.5, 97.5])
            stab = np.mean(np.isin(cb, nbrs[c_hat]))
            # split-half 交叉
            idx = np.arange(N_STOCKS); halves = (idx % 2 == 0, idx % 2 == 1); xs = []
            for sel, ev in (halves, halves[::-1]):
                f_sel = scores2(counts[sel].sum(0)[None], ref[sel].sum(0)[None], nbrs, min_count=MIN_COUNT / 2)[0]
                c_s = int(np.argmax(f_sel))
                xs.append(scores2(counts[ev].sum(0)[None], ref[ev].sum(0)[None], nbrs, min_count=MIN_COUNT / 2)[0][c_s])
            rows.append((naive, oos, optimism, corrected, np.mean(xs), stab, true_max, ci[0], ci[1], bsn))
        r = np.array(rows)
        print(f"-- {scen} ({time.time()-t0:.0f}s)  均值±sd over {N_SEEDS} seeds")
        print(f"   naive score_A(ĉ)        {r[:,0].mean():+.4f} ± {r[:,0].std():.4f}")
        print(f"   oos  score_A'(ĉ) 真值   {r[:,1].mean():+.4f} ± {r[:,1].std():.4f}   → 实际选择偏置 naive−oos = {np.mean(r[:,0]-r[:,1]):+.4f}")
        print(f"   bootstrap optimism      {r[:,2].mean():+.4f} ± {r[:,2].std():.4f}")
        print(f"   corrected naive−opt     {r[:,3].mean():+.4f} ± {r[:,3].std():.4f}   剩余偏置 corrected−oos = {np.mean(r[:,3]-r[:,1]):+.4f}")
        print(f"   split-half 交叉         {r[:,4].mean():+.4f} ± {r[:,4].std():.4f}   剩余偏置 = {np.mean(r[:,4]-r[:,1]):+.4f}")
        print(f"   校正 CI 覆盖 oos 的比例  {np.mean((r[:,7] <= r[:,1]) & (r[:,1] <= r[:,8])):.2f};选中格稳定性 P(ĉ_b∈N(ĉ)) {r[:,5].mean():.2f};独立宇宙真最优 {r[:,6].mean():+.4f};有效副本 {r[:,9].mean():.0f}/{B}")


if __name__ == "__main__":
    main()
